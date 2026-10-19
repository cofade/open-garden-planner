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

THE GROUND (L1.5). With a ``ground_baker`` the sync also keeps the plan's baked
ground in step: every ``apply`` hands the baker the snapshot, the SAME diff the
builders are run from and the ids the scene holds a solid for, and the tiles it
returns travel as the ground of the same transaction — one edit, one snapshot,
one diff, builders and bake. A record is painted on the ground when the snapshot
gave it a paint description (it has no height and is not a plant) AND no builder
made a solid for it.

- PENDING GROUND WORK. A baker may stop before every tile is painted (its time
  budget): the ground sent then holds the tiles it had for the rest — a stale
  picture there, never a wrong one elsewhere. ``ground_pending`` says so. Every
  ``apply`` goes on with the pending tiles; ``continue_ground()`` is the pass for
  a caller that has nothing new to apply (no diff, no builder: one bake, and one
  transaction when a tile changed). While ground work is pending, the sink's
  ground is BEHIND ``expected_state()`` in exactly the pending tiles and equal to
  it in everything else; once it is not, the invariant above holds in full. The
  failure rules do not change while work is pending: a sink that raises in a
  continuation poisons the sync like any other sink call.
- A BAKER THAT RAISES is contained like a builder: the failure is logged and kept
  in ``ground_failure``, the ground the sink shows stays (bare, if the plan's
  rectangle changed), the baker is RESTARTED (``GroundBaking.restart``: it
  forgets what its tiles were painted with — pending work too — and keeps handing
  out their pictures until each is painted anew, so the edit after a failure does
  not blank the ground) and the rest of the scene is applied. And like a
  builder's, the failure is REMEMBERED: the
  bake is not tried again until something it depends on changes — a record, the
  set of items with a solid, the plan's rectangle — so an idle tick neither
  bakes nor logs again.
- ``reset()`` clears the baker too: tiles, pending work and the remembered failure.

SELECTION (L1.8, ADR-065). ``select(ids)`` remembers which items are selected and
calls nothing; the ring that shows them (``selection.selection_of`` — one mesh)
goes to the sink through ``set_selection``, and only when the ring the engine
would draw differs from the one it has: in the transaction of the next ``apply``
— so a selected item that moves takes its ring along with the move — or in one
of its own (``send_selection`` / ``set_selection``). What is remembered is the
WISH: a selected item that is deleted loses its ring and gets it back when an
undo brings the item back; ``reset()`` forgets what was sent, not what was asked.

Qt-free and thread-agnostic: call it from the thread that owns the sink.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType

from open_garden_planner.core.plain_text import log_text

from .build import Builder, BuilderRegistry, checked_parts
from .ground import GroundBaking
from .mesh import MeshPart
from .record import Record
from .scene_diff import SceneDiff, diff
from .selection import EMPTY_SELECTION, Selection, selection_of
from .sink import EngineSink, GroundSpec, RecordingSink, SinkState, SunState

_NO_CHANGE = SceneDiff()

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
                 validate: bool = False, ground_baker: GroundBaking | None = None) -> None:
        self._sink = sink
        self._registry = registry if registry is not None else BuilderRegistry()
        self._validate = validate
        self._baker = ground_baker
        self._solid: frozenset[str] = frozenset()
        self._ground_failure: tuple[str, str] | None = None
        #: what the bake that failed was asked for (plan rectangle, solids): while it
        #: is asked for the same again, it is not run again
        self._ground_failed_for: tuple[GroundSpec, frozenset[str]] | None = None
        self._records: dict[str, Record] = {}
        self._built_with: dict[str, Builder] = {}
        self._failures: dict[str, BuildFailure] = {}
        self._sun: SunState | None = None
        self._ground: GroundSpec | None = None
        self._poisoned = False
        self._build_count = 0
        self._quiet = False
        self._registry_version: int | None = None  # the registry as the held items were built
        self._selected: frozenset[str] = frozenset()   # what is asked for (L1.8)
        self._selection: Selection = EMPTY_SELECTION   # the ring the sink was last sent
        self._selection_stale = False                  # asked for since it was last compared

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
        """The ground last sent to the sink — with its baked tiles, when the sync
        has a ground baker."""
        return self._ground

    @property
    def ground_baker(self) -> GroundBaking | None:
        return self._baker

    @property
    def solid_ids(self) -> frozenset[str]:
        """The items the scene holds a solid for (a builder made at least one
        triangle). Every other item is on the ground, or nowhere."""
        return self._solid

    @property
    def ground_failure(self) -> tuple[str, str] | None:
        """``(error type, message)`` when the ground baker raised at the last bake
        (the ground shown is then stale or bare), else None. It stays — and the
        bake is not run again — until a record, the solids or the plan change."""
        return self._ground_failure

    @property
    def ground_pending(self) -> bool:
        """True while the ground baker has tiles left to paint for what was last
        applied (module docstring): run another pass — ``continue_ground()``, or
        the next ``apply``."""
        return self._baker is not None and self._baker.pending > 0

    @property
    def selected_ids(self) -> frozenset[str]:
        """The ids asked to be shown as selected (``select``) — the wish, whether or
        not each has a record right now."""
        return self._selected

    @property
    def selection(self) -> Selection:
        """The selection ring last sent to the sink (empty before the first, and
        after ``reset``)."""
        return self._selection

    def expected_state(self) -> SinkState:
        """What a sink that honours the protocol holds right now: the state ONE
        ``apply`` of the current snapshot, sun and ground gives an empty sink.

        The reference for "incremental == full rebuild", and the only way to catch
        a sink that ignores a call (``clear()`` above all) — compare it with the
        sink's own account of itself: ``assert sink.state() == sync.expected_state()``.
        It runs every builder again, so it belongs in tests and diagnostics.

        The reference's GROUND is the finished one. While ``ground_pending`` is
        true the sink's ground is behind it in the pending tiles (and equal in
        every other tile, and in everything that is not ground).

        Precondition: nothing was registered in the registry since the last
        ``apply``. The reference is built with the registry as it is NOW; between
        a registration and the next ``apply`` the sink still holds what the old
        builders made, and the two differ until that ``apply`` has run.
        """
        empty_sink = RecordingSink()
        baker = self._baker.fresh() if self._baker is not None else None
        reference = SceneSync(empty_sink, self._registry, validate=self._validate,
                              ground_baker=baker)
        reference._quiet = True  # the failures were logged when they first happened
        ground = self._ground
        if ground is not None and baker is not None:
            ground = ground.plan  # the tiles are the reference baker's to make, from scratch
        if self._selection.ids:  # the ring the sink HOLDS: a wish not yet sent is not in it
            reference.select(self._selection.ids)
        reference.apply(self._records, sun=self._sun, ground=ground)
        while reference.ground_pending:  # a reference baker with a budget of its own
            reference.continue_ground()
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
        they are. With a ground baker, ``ground`` is the plan's rectangle and the
        baker lays the tiles on it; the baked ground travels in the same
        transaction whenever a tile changed — also when ``ground`` is not given
        again. Returns the diff of the records against the previously applied
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
        solid = self._solid
        if fresh or restyled or changes.removed:
            solid = frozenset(
                (solid - set(changes.removed) - set(built))
                | {item_id for item_id, parts in built.items()
                   if any(part.mesh.vertex_count for part in parts)})
        # a restyled item's record did not change, but whether it has a solid may have:
        # the diff no longer names everything the ground depends on
        ground = self._bake(new, None if restyled else changes, solid, ground)
        send_sun = sun is not None and sun != self._sun
        send_ground = ground is not None and ground != self._ground
        ring = self._pending_selection(changes, new)  # None: the ring shown is the ring owed
        if changes.touches_sink or restyled or send_sun or send_ground or ring is not None:
            def send() -> None:
                self._send(changes, new, built, restyled)
                if send_ground and ground is not None:
                    self._sink.set_ground(ground)
                if send_sun and sun is not None:
                    self._sink.set_sun(sun)
                if ring is not None:
                    self._sink.set_selection(ring)

            self._transact(send)
        self._selection_sent(ring)
        for item_id in (*changes.removed, *fresh, *restyled):
            self._failures.pop(item_id, None)
            self._built_with.pop(item_id, None)
        self._failures.update(failed)
        self._built_with.update(builders)
        self._registry_version = version
        self._records = new
        self._solid = solid
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
        """Tell the sink the plan's ground; a repeat of the last value sends nothing.
        With a ground baker the tiles for the current records are laid on it."""
        self._require_usable()
        baked = self._bake(self._records, _NO_CHANGE, self._solid, ground)
        if baked is None or baked == self._ground:
            return False
        self._transact(lambda: self._sink.set_ground(baked))
        self._ground = baked
        return True

    def continue_ground(self) -> bool:
        """One more pass of pending ground work, for the records last applied: one
        ``bake`` — no diff, no builder — and, when a tile changed, one transaction
        that sends the ground. Returns ``ground_pending``: True while there is
        more to do. Without pending work it does nothing and returns False."""
        self._require_usable()
        if not self.ground_pending:
            return False
        baked = self._bake(self._records, _NO_CHANGE, self._solid, None)
        if baked is not None and baked != self._ground:
            self._transact(lambda: self._sink.set_ground(baked))
            self._ground = baked
        return self.ground_pending

    def select(self, ids: Iterable[str]) -> None:
        """Remember which items are selected. NO sink call: the ring goes out with
        the next ``apply`` or ``send_selection``. Legal in every state — also
        poisoned: remembering touches nothing."""
        selected = frozenset(str(item_id) for item_id in ids)
        if selected != self._selected:
            self._selected = selected
            self._selection_stale = True

    def send_selection(self) -> bool:
        """Send the selection ring in a transaction of its own, if the ring the
        engine would draw is not the one it has. Returns True when a call was made."""
        self._require_usable()
        ring = self._pending_selection(SceneDiff(), self._records)
        if ring is not None:
            self._transact(lambda: self._sink.set_selection(ring))
        self._selection_sent(ring)
        return ring is not None

    def set_selection(self, ids: Iterable[str]) -> bool:
        """``select(ids)`` and ``send_selection()``: tell the sink what is selected
        now. Returns True when a call was made. To send it together with a
        snapshot, ``select`` first and ``apply``."""
        self.select(ids)
        return self.send_selection()

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
        self._solid = frozenset()
        self._ground_failure = None
        self._ground_failed_for = None
        if self._baker is not None:
            self._baker.clear()
        self._selection = EMPTY_SELECTION  # what was SENT; what is selected stays asked for
        self._selection_stale = bool(self._selected)
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

    def _bake(self, records: Mapping[str, Record], changes: SceneDiff | None,
              solid: frozenset[str], ground: GroundSpec | None) -> GroundSpec | None:
        """The ground to send: ``ground`` (else the one the sink has) with the baker's
        tiles for ``records`` laid on it; ``ground`` itself without a baker or
        without a plan rectangle. Runs BEFORE the sink is touched, like a builder,
        and is contained like one (module docstring)."""
        plan = ground if ground is not None else self._ground
        baker = self._baker
        if baker is None or plan is None:
            return ground
        asked_for = (plan.plan, solid)
        if (self._ground_failure is not None and self._ground_failed_for == asked_for
                and changes is not None and changes.is_empty):
            return self._stale_ground(plan)  # it failed for exactly this: not tried again
        try:
            tiles = baker.bake(records, changes, solid, plan.width_cm, plan.depth_cm)
        except Exception as error:  # a ground that cannot be baked must not stop the scene
            self._ground_failure = (type(error).__name__, str(error))
            self._ground_failed_for = asked_for
            if not self._quiet:
                # ONE normalised, capped line (an exception's message can quote the plan:
                # core/plain_text.py, §8.11) and the traceback at DEBUG only
                _log.error("the 3D ground could not be baked; it stays as it was (%s: %s)",
                           log_text(type(error).__name__), log_text(error))
                _log.debug("the 3D ground could not be baked - traceback", exc_info=error)
            # its books are not the ground of these records — its pictures are what
            # the sink shows, and stay until the baker has painted each tile anew
            baker.restart()
            return self._stale_ground(plan)
        self._ground_failure = None
        self._ground_failed_for = None
        return GroundSpec(plan.width_cm, plan.depth_cm, tiles)

    def _stale_ground(self, plan: GroundSpec) -> GroundSpec:
        """The ground to show when the bake failed: the tiles the sink has, on the
        same plan rectangle; bare on another (the old tiles lie on another grid)."""
        shown = self._ground
        same_plan = shown is not None and shown.plan == plan.plan
        return GroundSpec(plan.width_cm, plan.depth_cm,
                          shown.tiles if shown is not None and same_plan else ())

    def _pending_selection(self, changes: SceneDiff, new: Mapping[str, Record]) -> Selection | None:
        """The ring to send with ``new`` — or None when the sink's ring is the ring
        owed. Asked BEFORE the sink is touched. The ring is rebuilt only when the
        wish changed or the diff touches a selected item's outline or pose (a
        recolour does not), and sent only when it then differs."""
        if not self._selection_stale:
            if not self._selected:
                return None
            moved = (*changes.added, *changes.removed, *changes.geometry, *changes.transform)
            if self._selected.isdisjoint(moved):
                return None
        ring = selection_of(new, self._selected)
        return None if ring == self._selection else ring

    def _selection_sent(self, ring: Selection | None) -> None:
        if ring is not None:
            self._selection = ring
        self._selection_stale = False

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
