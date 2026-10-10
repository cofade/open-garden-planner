"""``SceneSync`` — snapshots in, minimal engine calls out (Phase 17 L1.1, ADR-054).

Owns the last applied records and an ``EngineSink``. ``apply(records)`` diffs
the new snapshot against the last one, runs builders ONLY for added items and
items whose geometry changed, and drives the sink inside one
``begin()``/``commit()`` — or makes no call at all when nothing the engine shows
changed. A move is one ``update_transform``; a recolour is one
``update_material``; neither calls a builder.

The invariant every test of this module asserts: after any sequence of
``apply`` calls the sink holds exactly what ONE ``apply`` of the latest snapshot
would put into an empty sink — incremental == full rebuild.

Failure rules (decided in ADR-054, pinned by ``tests/unit/test_scene3d_sync.py``):

- A BUILDER that raises is contained. All builders run before the sink is
  touched, so a transaction is never half applied. The failing item is given no
  parts, the failure is logged and listed in ``failures``, and the rest of the
  scene is applied. Builders are pure, so the failing builder is not run again
  until that item's geometry changes; the entry goes when a rebuild succeeds or
  the item is removed. (``KeyboardInterrupt`` and friends are not failures: they
  propagate, and — raised before ``begin()`` — leave sink and sync untouched.)
- A SINK that raises leaves the engine in an unknown state. The exception
  propagates and the sync is *poisoned*: every later call raises
  ``SyncStateError`` until the owner tears the engine scene down and calls
  ``reset()``. Sending diffs against a state the engine may not hold would be a
  wrong frame that looks right.

Qt-free and thread-agnostic: call it from the thread that owns the sink.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .build import BuilderRegistry, checked_parts
from .diff import SceneDiff, diff
from .mesh import MeshPart
from .record import Record
from .sink import EngineSink, GroundSpec, SunState

_log = logging.getLogger(__name__)


class SyncStateError(RuntimeError):
    """The sync cannot be used until ``reset()`` (a sink call failed)."""


@dataclass(frozen=True, slots=True)
class BuildFailure:
    """A builder raised (or broke its contract) for one item."""

    item_id: str
    kind: str
    error: Exception


class SceneSync:
    """Keeps an ``EngineSink`` in step with successive snapshots (module docstring).

    ``registry`` maps kinds to builders (default: only ``default_builder``).
    ``validate=True`` runs ``MeshPart.validate`` on everything a builder returns
    and treats a rejected mesh as a builder failure — for tests and diagnostics;
    production leaves it off (builders are gated by ``build.verify_builder``).
    """

    def __init__(self, sink: EngineSink, registry: BuilderRegistry | None = None, *,
                 validate: bool = False) -> None:
        self._sink = sink
        self._registry = registry if registry is not None else BuilderRegistry()
        self._validate = validate
        self._records: dict[str, Record] = {}
        self._failures: dict[str, BuildFailure] = {}
        self._sun: SunState | None = None
        self._ground: GroundSpec | None = None
        self._poisoned = False
        self._build_count = 0

    # ── state ───────────────────────────────────────────────────────────────

    @property
    def sink(self) -> EngineSink:
        return self._sink

    @property
    def registry(self) -> BuilderRegistry:
        return self._registry

    @property
    def records(self) -> Mapping[str, Record]:
        """The last applied snapshot (read-only, bottom-to-top)."""
        return MappingProxyType(self._records)

    @property
    def failures(self) -> Mapping[str, BuildFailure]:
        """Items whose builder failed for their CURRENT geometry (read-only)."""
        return MappingProxyType(self._failures)

    @property
    def poisoned(self) -> bool:
        """True after a sink call raised; ``reset()`` clears it."""
        return self._poisoned

    @property
    def build_count(self) -> int:
        """Builder invocations so far — the instrument behind "a move builds nothing"."""
        return self._build_count

    # ── driving the sink ────────────────────────────────────────────────────

    def apply(self, records: Mapping[str, Record]) -> SceneDiff:
        """Bring the sink to ``records`` (bottom-to-top) with the fewest calls.

        Returns the diff against the previously applied snapshot. See the module
        docstring for what happens when a builder or the sink raises.
        """
        self._require_usable()
        new = dict(records)
        changes = diff(self._records, new)
        built: dict[str, tuple[MeshPart, ...]] = {}
        failed: dict[str, BuildFailure] = {}
        for item_id in (*changes.added, *changes.geometry):  # BEFORE the sink is touched
            record = new[item_id]
            try:
                built[item_id] = self._build(record)
            except Exception as error:  # any builder defect is contained (module docstring)
                built[item_id] = ()
                failed[item_id] = BuildFailure(item_id, record.kind, error)
                _log.error("3D builder for %s item %r failed; it is shown without a solid",
                           record.kind, item_id, exc_info=error)
        if changes.touches_sink:
            self._transact(lambda: self._send(changes, new, built))
        for item_id in (*changes.removed, *changes.added, *changes.geometry):
            self._failures.pop(item_id, None)
        self._failures.update(failed)
        self._records = new
        return changes

    def set_sun(self, sun: SunState) -> bool:
        """Tell the sink where the sun is; a repeat of the last value sends nothing.
        Returns True when a call was made."""
        self._require_usable()
        if sun == self._sun:
            return False
        self._transact(lambda: self._sink.set_sun(sun))
        self._sun = sun
        return True

    def set_ground(self, ground: GroundSpec) -> bool:
        """Tell the sink the plan's ground; a repeat of the last value sends nothing."""
        self._require_usable()
        if ground == self._ground:
            return False
        self._transact(lambda: self._sink.set_ground(ground))
        self._ground = ground
        return True

    def reset(self) -> None:
        """Forget everything: the engine scene was torn down (or must be).

        The next ``apply`` re-adds every item and the next ``set_sun`` /
        ``set_ground`` is sent again. The caller guarantees the sink is empty;
        the sync never clears an engine itself.
        """
        self._records = {}
        self._failures = {}
        self._sun = None
        self._ground = None
        self._poisoned = False

    # ── internals ───────────────────────────────────────────────────────────

    def _require_usable(self) -> None:
        if self._poisoned:
            raise SyncStateError(
                "a sink call failed earlier, so the engine's scene is unknown: tear it down "
                "and call reset() before applying again"
            )

    def _build(self, record: Record) -> tuple[MeshPart, ...]:
        self._build_count += 1
        parts = checked_parts(self._registry.build(record))
        if self._validate:
            for part in parts:
                part.validate()
        return parts

    def _transact(self, send: Callable[[], None]) -> None:
        try:
            self._sink.begin()
            send()
            self._sink.commit()
        except BaseException:
            self._poisoned = True
            raise

    def _send(self, changes: SceneDiff, new: Mapping[str, Record],
              built: Mapping[str, tuple[MeshPart, ...]]) -> None:
        sink = self._sink
        for item_id in changes.removed:
            sink.remove(item_id)
        for item_id in changes.added:
            record = new[item_id]
            sink.add(item_id, built[item_id], record.transform, record.material)
        for item_id in changes.geometry:
            sink.replace_geometry(item_id, built[item_id])
        for item_id in changes.transform:
            sink.update_transform(item_id, new[item_id].transform)
        for item_id in changes.material:
            sink.update_material(item_id, new[item_id].material)

