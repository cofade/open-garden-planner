"""``SceneSync`` — snapshots in, minimal engine calls out (Phase 17 L1.1, ADR-064).

Owns the last applied records and an ``EngineSink``. ``apply(records)`` diffs
the new snapshot against the last one, runs builders ONLY for added items and
items whose geometry changed, and drives the sink inside one
``begin()``/``commit()`` — or makes no call at all when nothing the engine shows
changed. A move is one ``update_transform``; a recolour is one
``update_material``; neither calls a builder. A sun or ground handed to the same
``apply`` travels in the same transaction.

The invariant every test of this module asserts: after any sequence of calls the
sink holds exactly what ONE ``apply`` of the latest snapshot would put into an
empty sink — incremental == full rebuild (``expected_state`` is that reference).
It also holds across a change of the builder registry: an item whose builder was
registered or replaced after it was built is rebuilt by the next ``apply``.

Failure rules (decided in ADR-064, pinned by ``tests/unit/test_scene3d_sync.py``):

- A BUILDER that raises is contained. All builders run before the sink is
  touched, so a transaction is never half applied. The failing item is given no
  parts, the failure is logged and listed in ``failures``, and the rest of the
  scene is applied. Builders are pure, so the failing builder is not run again
  until that item's geometry (or its builder) changes; the entry goes when a
  rebuild succeeds or the item is removed. (``KeyboardInterrupt`` and friends are
  not failures: they propagate, and — raised before ``begin()`` — leave sink and
  sync untouched.)
- A SINK that raises leaves the engine in an unknown state. The exception
  propagates and the sync is *poisoned*: every later call raises
  ``SyncStateError`` until ``reset()``.
- ``reset()`` is the recovery, and it goes through the protocol: it calls
  ``sink.clear()`` — legal at any time, even inside the transaction the failure
  left open — and forgets everything, so the next ``apply`` re-adds every item
  and re-sends sun and ground. If ``clear()`` itself raises, the sync stays
  poisoned. What the sync cannot see is a sink that *ignores* ``clear()``:
  compare the sink's own state with ``expected_state()`` to catch that.

When ``reset()`` is needed: after a ``SyncStateError`` / a sink failure, and
when the engine's scene was destroyed behind the sync's back (the 3D view was
closed and rebuilt, the graphics device was lost). It is NOT needed for a new or
newly opened plan: a plain ``apply`` of the new snapshot removes what is gone and
adds what is new.

Qt-free and thread-agnostic: call it from the thread that owns the sink.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType

from .build import Builder, BuilderRegistry, checked_parts
from .mesh import MeshPart
from .record import Record
from .scene_diff import SceneDiff, diff
from .sink import EngineSink, GroundSpec, RecordingSink, SinkState, SunState

_log = logging.getLogger(__name__)


class SyncStateError(RuntimeError):
    """The sync cannot be used until ``reset()`` (a sink call failed)."""


@lru_cache(maxsize=64)
def _stand_in(name: str) -> type[Exception]:
    return type(name, (Exception,), {"__module__": __name__})


@dataclass(frozen=True, slots=True)
class BuildFailure:
    """A builder raised (or broke its contract) for one item.

    Plain data, safe to keep — like the snapshot's ``SkippedItem``: of the
    exception it holds the type's NAME and the message, never the exception
    itself (its traceback keeps the whole ``apply`` frame alive: the records,
    the built meshes, the sink). The exception goes to the log.
    """

    item_id: str
    kind: str
    error_type: str  # the exception's class name
    error_message: str  # str(exception)

    @property
    def error(self) -> Exception:
        """A STAND-IN for the exception the builder raised — for code written
        when this was the exception itself: an exception whose class has the same
        NAME and whose text is the same message, with no traceback. Not the
        original object, and not an instance of the original class: test
        ``error_type`` instead of ``isinstance``."""
        return _stand_in(self.error_type)(self.error_message)


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
        self._built_with: dict[str, Builder] = {}
        self._failures: dict[str, BuildFailure] = {}
        self._sun: SunState | None = None
        self._ground: GroundSpec | None = None
        self._poisoned = False
        self._build_count = 0
        self._quiet = False
        self._registry_version: int | None = None  # the registry as the held items were built

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

    @property
    def sun(self) -> SunState | None:
        """The sun last sent to the sink (None before the first, and after ``reset``)."""
        return self._sun

    @property
    def ground(self) -> GroundSpec | None:
        """The ground last sent to the sink."""
        return self._ground

    def expected_state(self) -> SinkState:
        """What a sink that honours the protocol holds right now: the state ONE
        ``apply`` of the current snapshot, sun and ground gives an empty sink.

        The reference for "incremental == full rebuild", and the only way to catch
        a sink that ignores a call (``clear()`` above all) — compare it with the
        sink's own account of itself: ``assert sink.state() == sync.expected_state()``.
        It runs every builder again, so it belongs in tests and diagnostics.

        Precondition: nothing was registered in the registry since the last
        ``apply``. The reference is built with the registry as it is NOW; between
        a registration and the next ``apply`` the sink still holds what the old
        builders made, and the two differ until that ``apply`` has run.
        """
        empty_sink = RecordingSink()
        reference = SceneSync(empty_sink, self._registry, validate=self._validate)
        reference._quiet = True  # the failures were logged when they first happened
        reference.apply(self._records, sun=self._sun, ground=self._ground)
        return empty_sink.state()

    # ── driving the sink ────────────────────────────────────────────────────

    def apply(
        self,
        records: Mapping[str, Record],
        *,
        sun: SunState | None = None,
        ground: GroundSpec | None = None,
    ) -> SceneDiff:
        """Bring the sink to ``records`` (bottom-to-top) with the fewest calls.

        ``sun`` / ``ground``, when given and different from what the sink already
        has, are sent in the SAME transaction — a clock tick that moves the sun
        and grows the plants is one ``begin``/``commit``. ``None`` leaves them as
        they are. Returns the diff of the records against the previously applied
        snapshot; an item rebuilt only because its builder changed is not in it
        (its record did not change). See the module docstring for what happens
        when a builder or the sink raises.
        """
        self._require_usable()
        new = dict(records)
        changes = diff(self._records, new)
        fresh = (*changes.added, *changes.geometry)
        builder_for = self._registry.builder_for
        version = getattr(self._registry, "version", None)
        restyled: tuple[str, ...] = ()
        if version is None or version != self._registry_version:
            # something was registered since the held items were built (or the
            # registry cannot say): find the items whose builder is another now
            rebuilt_anyway = set(changes.geometry)
            restyled = tuple(
                item_id for item_id, built_with in self._built_with.items()
                if item_id in new and item_id not in rebuilt_anyway
                and builder_for(new[item_id].kind) is not built_with
            )
        built: dict[str, tuple[MeshPart, ...]] = {}
        builders: dict[str, Builder] = {}
        failed: dict[str, BuildFailure] = {}
        for item_id in (*fresh, *restyled):  # BEFORE the sink is touched
            record = new[item_id]
            builder = builder_for(record.kind)
            builders[item_id] = builder
            try:
                built[item_id] = self._build(builder, record)
            except Exception as error:  # any builder defect is contained (module docstring)
                built[item_id] = ()
                failed[item_id] = BuildFailure(item_id, record.kind, type(error).__name__, str(error))
                if not self._quiet:
                    _log.error("3D builder for %s item %r failed; it is shown without a solid",
                               record.kind, item_id, exc_info=error)
        send_sun = sun is not None and sun != self._sun
        send_ground = ground is not None and ground != self._ground
        if changes.touches_sink or restyled or send_sun or send_ground:
            def send() -> None:
                self._send(changes, new, built, restyled)
                if send_ground and ground is not None:
                    self._sink.set_ground(ground)
                if send_sun and sun is not None:
                    self._sink.set_sun(sun)

            self._transact(send)
        for item_id in (*changes.removed, *fresh, *restyled):
            self._failures.pop(item_id, None)
            self._built_with.pop(item_id, None)
        self._failures.update(failed)
        self._built_with.update(builders)
        self._registry_version = version
        self._records = new
        if send_sun:
            self._sun = sun
        if send_ground:
            self._ground = ground
        return changes

    def set_sun(self, sun: SunState) -> bool:
        """Tell the sink where the sun is, in a transaction of its own; a repeat of
        the last value sends nothing. Returns True when a call was made. To send
        it together with a snapshot, pass ``sun=`` to ``apply``."""
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
        """Start over: ``sink.clear()``, then forget everything.

        After it the sink holds nothing and neither does the sync — records,
        failures, the poison flag and the sun/ground it remembered — so the next
        ``apply`` re-adds every item and the next sun and ground are sent again.
        Legal in any state, including poisoned with the sink's transaction still
        open (``clear()`` aborts it). If ``clear()`` raises, the exception
        propagates and the sync is (still) poisoned.
        """
        self._records = {}
        self._built_with = {}
        self._registry_version = None
        self._failures = {}
        self._sun = None
        self._ground = None
        try:
            self._sink.clear()
        except BaseException:
            self._poisoned = True
            raise
        self._poisoned = False

    # ── internals ───────────────────────────────────────────────────────────

    def _require_usable(self) -> None:
        if self._poisoned:
            raise SyncStateError(
                "a sink call failed earlier, so the engine's scene is unknown: "
                "call reset() (it clears the sink) before applying again"
            )

    def _build(self, builder: Builder, record: Record) -> tuple[MeshPart, ...]:
        self._build_count += 1
        parts = checked_parts(builder(record))
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
              built: Mapping[str, tuple[MeshPart, ...]], restyled: tuple[str, ...]) -> None:
        sink = self._sink
        for item_id in changes.removed:
            sink.remove(item_id)
        for item_id in changes.added:
            record = new[item_id]
            sink.add(item_id, built[item_id], record.transform, record.material)
        for item_id in (*changes.geometry, *restyled):
            sink.replace_geometry(item_id, built[item_id])
        for item_id in changes.transform:
            sink.update_transform(item_id, new[item_id].transform)
        for item_id in changes.material:
            sink.update_material(item_id, new[item_id].material)
