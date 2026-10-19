"""The 3D sync pipeline's controller (Phase 17 L1.3, ADR-065). Engine-free.

    scene.plan_changed / date_changed ─► dirty ─► tick ─►
        snapshot_records(scene, clock.plan_date) ─► SceneSync.apply(records, sun, ground) ─► sink
    scene.changed (a repaint nobody announced) ─► quiet for NET_QUIET_MS ─► the same pass, once

One QObject per main window. It owns a ``SceneSync`` and an ``EngineSink`` it was
handed (``Quick3DSink`` in the app, ``RecordingSink`` in the tests — the seam),
listens to the canvas scene and the one ``SimClock``, and turns "the plan
changed" into at most ONE pipeline pass per event-loop turn.

WHAT STARTS A PASS (ADR-065 decision 5). A whole-plan snapshot is O(total
vertices) even when every record is cached, and ``QGraphicsScene.changed`` fires
for every REPAINT: a hover, a selection, a tool's preview under the mouse, the
sun's shadow while the time slider moves or "Animate" runs. So ``changed`` starts
no pass. Two layers instead:

- **the fast path — what is announced.** The scene keeps a PLAN REVISION that
  moves exactly when plan content changed (``CanvasScene.plan_changed``: an item
  added, removed, moved, turned, shown, hidden, restacked; a command executed,
  undone or redone; a layer; the canvas size; and ``note_plan_changed()`` for a
  writer that goes round all of those). A revision that moved marks the records
  dirty AT ONCE: the pass runs with the next turn of the event loop.
- **the net — what is not.** A ``changed`` that no announcement explains (the
  revision did not move since the ``changed`` before it) snapshots nothing; it
  (re)starts ONE single-shot timer, ``NET_QUIET_MS``. When the scene has been
  quiet for that long, ONE reconciliation pass runs. It normally finds nothing.
  If it finds a difference, an edit path is missing its announcement: the pass
  applies it — so no edit stays out of 3D for longer than the quiet time,
  whatever wrote it — counts it (``unannounced_changes``) and logs one DEBUG line
  with the kinds that differed. No ``changed``, no timer: an idle scene costs
  nothing. A scene that is NEVER quiet (the sun animated for minutes) is
  reconciled every ``NET_MAX_WAIT_S`` all the same. The timer runs only while 3D
  is visible; a repaint while it is hidden leaves a flag, and coming back starts
  the timer once.

The rules it enforces:

- **Paused while 3D is hidden.** ``set_active(False)`` leaves flags and nothing
  else: no snapshot, no diff, no sink call, no timer. ``set_active(True)`` runs
  one catch-up pass if the plan, the date or the light changed — a plain
  ``apply`` of the current snapshot, which ``SceneSync`` guarantees equals a
  from-scratch apply — and starts the net's timer once if all that happened was
  a repaint.
- **One tick, one transaction.** Records, sun and ground travel in one
  ``sync.apply`` (L1.1). A time-of-day change is LIGHT ONLY: one ``set_sun``, no
  snapshot (the plan did not change). A date change regrows the plants: a tick.
  Writes that arrive faster than ticks coalesce in the flags — an animated date
  never queues more than one pending regrow.
- **A snapshot only on a change of the plan, or once after a quiet time — never
  on a timer that spins, and never per repaint** (above).
- **A document change is not a reset.** A new or opened plan is just another
  snapshot; ``apply`` removes what is gone. ``SceneSync.reset()`` is RECOVERY:
  after a sink call raised or the sync is poisoned, the controller resets and
  applies once more, logs it, and never lets the error reach the event loop. If
  that fails too it gives up for this tick (``failed``).
- **A pass that keeps failing is tried again when something changed, and says so
  once.** The next change of the plan, of the date or of the light tries again; a
  mere repaint does not (the net stands down while a pass is owed). The log gets
  ONE ERROR line per distinct failure of an outage — the same failure again is a
  DEBUG line — and the next pass that goes through ends the outage.
- **What 3D could not build is reported, not hidden.** ``skipped`` (the record
  layer refused an item: ``SkipReason``) and ``failures`` (a builder raised) are
  kept from the last tick; ``problems_changed`` fires when they change.

THE GROUND SEAM (L1.5). ``set_ground_stage(stage)`` installs the function that
makes the tick's ``GroundSpec``: ``stage(previous, records, width_cm, depth_cm)``
with the records applied last (``{}`` after a reset) and the new snapshot. It
runs BEFORE ``apply`` so that what it returns travels in the same transaction as
the geometry; a baker diffs the two snapshots with ``core.scene3d.diff`` — the
function ``SceneSync`` itself uses, on the same inputs. The default is the bare
plan rectangle. A stage that raises is contained (logged; the bare rectangle is
sent instead). THE PASS IS RE-RUNNABLE: ``mark_dirty()`` — also from inside the
stage, or from a slot on ``applied`` — asks for another pass in the next turn of
the event loop (the flags are cleared when a pass STARTS). A ground that is made
in slices (a bake that stops at a time budget and leaves tiles for later) asks
for its next slice that way; nothing here assumes that one pass paints it all.

NO PASS TAKES A FRAME. This module never asks the engine for one (it has only the
sink), and the workspace keeps the same rule for the host: a readback renders a
frame that is never presented (ADR-065 decision 17). A view that presents nothing
is not held back either — the pass applies, and Qt draws when it draws.

GUI thread only. No Qt Quick import: this module runs in the GPU-less tier.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    BuildFailure,
    EngineSink,
    GroundSpec,
    Record,
    SceneDiff,
    SceneSync,
    SunState,
)
from open_garden_planner.core.scene3d.camera import Bounds
from open_garden_planner.core.sim_clock import SimChange, SimClock
from open_garden_planner.core.solar import solar_position
from open_garden_planner.ui.sim_clock_subscription import connect_qobject

from .snapshot import SkippedItem, snapshot_records

_LOG: Final = logging.getLogger(__name__)

#: How long a change waits for its pass: 0 = the next turn of the event loop (a posted
#: event, so every change signal of one turn shares one snapshot); a positive value
#: is a timer of that interval.
TICK_MS: Final = 0
_PASS_EVENT: Final = QEvent.Type(QEvent.registerEventType())
#: The catch-up pass after 3D became visible waits this long, so that the pane (and
#: its "building" note) is painted before a first build that can take a second.
CATCH_UP_MS: Final = 25
#: THE NET's quiet time (module docstring): a repaint that no announcement explains
#: is looked at once the scene has been quiet for this long. Twice the sun
#: animation's tick (200 ms, ``ui/widgets/sun_sim_toolbar``) on purpose: while
#: "Animate" runs, the shadows repaint every tick, and a quiet time below that
#: would reconcile between two ticks — a snapshot per tick, the very cost this
#: exists to avoid (pinned). It is also the longest an UNANNOUNCED edit stays out
#: of 3D once the canvas is still.
NET_QUIET_MS: Final = 400
#: … and a scene that is never still for that long is reconciled this often anyway.
NET_MAX_WAIT_S: Final = 5.0
#: How many distinct failures of one outage are remembered (and so logged at ERROR
#: once each); a failure beyond that is a DEBUG line.
_MAX_FAILURES_REMEMBERED: Final = 32
#: The sun without a garden location — the documented fallback of FR-SUN-06 (the
#: shipped 3D view's): a southern midday sun.
NO_LOCATION_SUN: Final = SunState(elevation_deg=50.0, azimuth_deg=180.0)

LocationProvider = Callable[[], Mapping[str, Any] | None]
#: ``stage(previous_records, records, width_cm, depth_cm) -> GroundSpec`` (module docstring).
GroundStage = Callable[[Mapping[str, Record], Mapping[str, Record], float, float], GroundSpec]


def _kinds(changes: SceneDiff) -> str:
    """What differed, for one log line: counts by kind — never an id or a name."""
    parts = [f"{name} {len(ids)}" for name, ids in (
        ("added", changes.added), ("removed", changes.removed), ("geometry", changes.geometry),
        ("transform", changes.transform), ("material", changes.material)) if ids]
    if changes.reordered:
        parts.append("reordered")
    return ", ".join(parts)


def plain_ground(_previous: Mapping[str, Record], _records: Mapping[str, Record],
                 width_cm: float, depth_cm: float) -> GroundSpec:
    """The default ground stage: the bare plan rectangle (L1.5 replaces it)."""
    return GroundSpec(width_cm, depth_cm)


@dataclass(frozen=True, slots=True)
class TickReport:
    """One pipeline pass that reached ``SceneSync`` — what ``applied`` carries."""

    #: The diff of the records (empty for a light-only pass).
    changes: SceneDiff
    #: False for a light-only pass (a time-of-day change): no snapshot was taken.
    snapshot: bool
    records: int
    snapshot_ms: float
    apply_ms: float
    #: True when this pass had to reset the sync first (a sink failure before it).
    recovered: bool = False
    #: Items whose engine Models were DESTROYED since the pass before: removed
    #: items, items whose geometry was replaced (new geometry is a new Model), and
    #: everything a reset cleared. Qt keeps graphics state for every Model it once
    #: drew until it is told to let go; the workspace counts these to know when
    #: (ADR-065, "what a destroyed Model leaves behind").
    retired: int = 0
    #: True for THE NET's pass: no announcement asked for it, the scene had been
    #: quiet for ``NET_QUIET_MS`` after a repaint. ``changes`` is empty then unless
    #: an edit path forgot to announce itself (``Scene3DController.unannounced_changes``).
    reconciled: bool = False

    @property
    def total_ms(self) -> float:
        return self.snapshot_ms + self.apply_ms


class Scene3DController(QObject):
    """Keeps an ``EngineSink`` in step with the canvas scene (module docstring)."""

    #: A pass reached the sync: ``TickReport``.
    applied = pyqtSignal(object)
    #: ``skipped`` / ``failures`` differ from the pass before.
    problems_changed = pyqtSignal()
    #: The first pass of a document (first open, new, open, recovery load) is in the
    #: sink: the workspace frames the camera — once.
    document_shown = pyqtSignal()
    #: A pass failed even after a reset; the text is for the log and a notice.
    failed = pyqtSignal(str)

    def __init__(self, scene: QGraphicsScene, clock: SimClock, location: LocationProvider,
                 sink: EngineSink, registry: BuilderRegistry | None = None, *,
                 parent: QObject | None = None, tick_ms: int = TICK_MS,
                 quiet_ms: int | None = None) -> None:
        """``scene``: the canvas scene. A ``CanvasScene`` announces its plan's
        changes (``plan_changed``); any other ``QGraphicsScene`` announces nothing
        and is kept in step by the net alone — after its quiet time, never at once.
        ``quiet_ms``: the net's quiet time (default ``NET_QUIET_MS``)."""
        super().__init__(parent)
        if registry is None:
            from open_garden_planner.core.scene3d.builders import production_registry

            registry = production_registry()
        self._scene = scene
        self._clock = clock
        self._location = location
        self._sync = SceneSync(sink, registry)
        self._ground_stage: GroundStage = plain_ground
        self._active = False
        self._records_dirty = True   # nothing was ever applied
        self._sun_dirty = True
        self._document_pending = True  # the first pass shows a document
        self._skipped: tuple[SkippedItem, ...] = ()
        self._failures: dict[str, BuildFailure] = {}
        self._last_error: str | None = None
        self._retired_by_reset = 0  # items a reset destroyed, not yet reported
        #: Failures of the current outage that were logged at ERROR already, and
        #: whether the pass that is running has failed at anything (module docstring).
        self._failures_logged: set[tuple[str, str, str]] = set()
        self._failed_in_pass = False
        #: Instruments (the gates read them): whole-plan snapshots taken, passes that
        #: called ``SceneSync.apply``, light-only passes, recoveries, the last pass …
        self.snapshot_count = 0
        self.apply_count = 0
        self.light_count = 0
        self.recovery_count = 0
        self.last_tick: TickReport | None = None
        #: … the net's passes, and how many of them found a difference: an edit path
        #: that changed the plan without announcing it. 0 on a healthy app — every
        #: edit path is pinned to announce itself — and the number a missing
        #: announcement shows up as.
        self.reconcile_count = 0
        self.unannounced_changes = 0
        self._tick_ms = tick_ms
        self._posted = False  # a pass event is in the queue
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tick)
        # THE NET: one single-shot timer, (re)started by a repaint nobody announced
        self._quiet_ms = NET_QUIET_MS if quiet_ms is None else quiet_ms
        self._net = QTimer(self)
        self._net.setSingleShot(True)
        self._net.timeout.connect(self._reconcile)
        self._net_since = 0.0     # when the timer was first started in this run of repaints
        self._net_owed = False    # a repaint arrived while 3D was hidden
        self._revision_at_changed = self._revision()
        announced = getattr(scene, "plan_changed", None)  # a CanvasScene has it
        if announced is not None:
            announced.connect(self._on_plan_changed)
        scene.changed.connect(self._on_scene_changed)
        scene.sceneRectChanged.connect(self._on_rect_changed)
        connect_qobject(clock.date_changed, self._on_date_changed)
        connect_qobject(clock.instant_changed, self._on_instant_changed)

    # ── reads ────────────────────────────────────────────────────────────────

    @property
    def sync(self) -> SceneSync:
        return self._sync

    @property
    def active(self) -> bool:
        return self._active

    @property
    def dirty(self) -> bool:
        """Something changed that the sink has not been told."""
        return self._records_dirty or self._sun_dirty

    @property
    def idle(self) -> bool:
        """Nothing is on its way: no pass owed, none posted, and the net's quiet timer
        is not running. (An instrument for tests and gates; a paused controller with
        a flag set is not idle.)"""
        with contextlib.suppress(RuntimeError):  # the #230 teardown guard
            return not (self.dirty or self._posted or self._net_owed
                        or self._timer.isActive() or self._net.isActive())
        return True

    @property
    def skipped(self) -> tuple[SkippedItem, ...]:
        """Items the record layer left out of the last snapshot, and why."""
        return self._skipped

    @property
    def failures(self) -> Mapping[str, BuildFailure]:
        """Items whose builder failed, as of the last pass."""
        return dict(self._failures)

    @property
    def problem_count(self) -> int:
        return len(self._skipped) + len(self._failures)

    @property
    def last_error(self) -> str | None:
        """Why the last pass was given up; None once a pass went through."""
        return self._last_error

    def plan_bounds(self) -> Bounds:
        """The plan rectangle and the highest thing standing on it (applied records)."""
        width, depth = self._plan_size()
        top = 0.0
        for record in self._sync.records.values():
            if record.height_cm is not None:
                top = max(top, record.transform.base_cm + record.height_cm)
        return Bounds.of_plan(width, depth, top)

    # ── control ──────────────────────────────────────────────────────────────

    def set_active(self, active: bool) -> None:
        """3D became visible (True) or hidden (False). Hidden: flags only."""
        if active == self._active:
            return
        self._active = active
        if not active:
            with contextlib.suppress(RuntimeError):  # the #230 teardown guard
                self._timer.stop()
                if self._net.isActive():
                    self._net.stop()
                    self._net_owed = True  # looked at when 3D comes back
            return
        if self.dirty:
            self._schedule(max(self._tick_ms, CATCH_UP_MS))  # … and that pass reads everything
        elif self._net_owed:
            self._arm_net()

    def mark_dirty(self) -> None:
        """The plan changed, or may have: a pass with the next turn of the event loop.

        The slot of the scene's ``plan_changed``, and the call for whoever knows of a
        change no signal carries (a ground stage with work left). NOT for a repaint:
        ``QGraphicsScene.changed`` goes to the net (module docstring)."""
        self._records_dirty = True
        self._schedule(self._tick_ms)

    def refresh_sun(self, *_arguments: object) -> None:
        """The garden's location changed: the light follows; the plan did not change."""
        self._sun_dirty = True
        self._schedule(self._tick_ms)

    def document_changed(self) -> None:
        """A new, opened or recovered plan replaced the scene's content.

        Not a reset: the next pass is a plain apply of the new snapshot. What it
        does: drop what 3D remembers of the old plan, mark the records dirty, and
        announce the new document once it is in the sink (``document_shown`` — the
        camera frames it).
        """
        self._drop_plan_memories()
        self._document_pending = True
        self.mark_dirty()

    def set_ground_stage(self, stage: GroundStage | None) -> None:
        """Install the function that makes each tick's ``GroundSpec`` (L1.5's baker);
        None restores the bare rectangle. The next pass re-sends the ground."""
        self._ground_stage = stage if stage is not None else plain_ground
        self.mark_dirty()

    def reset(self) -> None:
        """The ENGINE's scene was rebuilt (a fresh host): forget what was sent; the
        next pass sends everything again. Contained like any sink failure."""
        self._retired_by_reset += len(self._sync.records)
        try:
            self._sync.reset()
        except Exception as error:  # noqa: BLE001 - a dead engine must not take the app down
            self._log_failure("reset failed; the next pass tries again", error)
        self._records_dirty = self._sun_dirty = True
        self._schedule(self._tick_ms)

    def flush(self) -> None:
        """Run a pending pass now (tests, and a caller that needs the scene current)."""
        with contextlib.suppress(RuntimeError):
            self._timer.stop()
        self._tick()

    def shutdown(self) -> None:
        """Stop for good (the 3D view closes, or the main window does). The sink is
        not touched; what 3D remembers of the plan is dropped — a closed view keeps
        no plan's worth of memory alive."""
        self._drop_plan_memories()
        self._active = False
        self._net_owed = False
        with contextlib.suppress(RuntimeError):
            self._timer.stop()
            self._net.stop()
        scene = self._scene
        connections: list[tuple[Any, Callable[..., None]]] = [
            (scene.changed, self._on_scene_changed),
            (scene.sceneRectChanged, self._on_rect_changed)]
        announced = getattr(scene, "plan_changed", None)
        if announced is not None:
            connections.append((announced, self._on_plan_changed))
        for signal, slot in connections:
            with contextlib.suppress(RuntimeError, TypeError):
                signal.disconnect(slot)

    # ── internals ────────────────────────────────────────────────────────────

    def _drop_plan_memories(self) -> None:
        """Everything the pipeline keeps PER PLAN goes — on a document change and when
        the 3D view closes. ONE place, so that a new memory is one line here.

        Both memories would otherwise outlive their plan: what a snapshot asks for
        is never dropped while snapshots go on, and with the view closed none runs
        (the contract story measured about 30 MB for a large plan's outlines)."""
        from open_garden_planner.core.scene3d.builders.plants import clear_shape_cache

        from .snapshot import clear_outline_cache

        clear_shape_cache()    # the plant builder's shapes
        clear_outline_cache()  # the record layer's outlines: regions, cuts, ring facts

    def _schedule(self, delay_ms: int) -> None:
        if not self._active:
            return  # paused: the flag is all that happens
        with contextlib.suppress(RuntimeError):  # the #230 teardown guard
            if self._timer.isActive() or self._posted:
                return  # a pass is on its way already: this change rides with it
            if delay_ms > 0:
                self._timer.start(delay_ms)
            else:
                # "The next turn of the event loop" as a POSTED EVENT, not a timer of
                # interval zero: posted events are delivered before the timers that are
                # due, and a zero timer waits behind the 2D side's debounced work
                # (spacing, companions, the minimap) — measured on the large bench
                # plan: 5 % of the passes started more than 228 ms late (ADR-065).
                # NORMAL priority (postEvent's default), on purpose: the scene's own
                # queued ``changed`` for the same edit was posted first and is delivered
                # first, so the undo stack's signal and the scene's share ONE pass. (At
                # high priority the pass ran before it, and ``changed`` then cost a
                # second snapshot.)
                self._posted = True
                QCoreApplication.postEvent(self, QEvent(_PASS_EVENT))

    def event(self, event: QEvent | None) -> bool:
        if event is not None and event.type() == _PASS_EVENT:
            self._posted = False
            self._tick()
            return True
        return super().event(event)

    def _revision(self) -> int | None:
        """The scene's plan revision; None for a scene that keeps none."""
        revision = getattr(self._scene, "plan_revision", None)
        return revision if isinstance(revision, int) else None

    def _expire_explanation(self) -> None:
        """From now on only a new announcement explains a repaint (``_pass_records``)."""
        with contextlib.suppress(RuntimeError):  # the #230 teardown guard
            self._revision_at_changed = self._revision()

    def _on_plan_changed(self, _revision: int = 0) -> None:
        self.mark_dirty()  # the fast path: the plan's content changed, and says so

    def _on_rect_changed(self, *_rect: object) -> None:
        self.mark_dirty()  # the scene's own rectangle moved: the ground follows

    def _on_scene_changed(self, *regions: object) -> None:
        """Something was REPAINTED. That is no reason for a pass (module docstring):
        a repaint that an announcement explains is left alone, any other one is
        looked at once — when the scene has been quiet for a while.

        A ``changed`` with an EMPTY list reports no repaint: it is Qt's echo of one
        already reported. With a listener on ``changed`` an item's ``update()`` is
        emitted at once from the dirty-item pass, and the queued ``_q_emitUpdated``
        that the same update had asked for arrives after it and finds nothing left
        (measured: every ``item.update()`` gave ``changed([rect])`` then
        ``changed([])``). Taken as a repaint, the echo of an ANNOUNCED write whose
        repaint lands after its pass — the Properties panel repaints, then nudges —
        was "unexplained" and cost a second whole-plan snapshot a quiet time later,
        finding nothing."""
        if regions and isinstance(regions[0], list) and not regions[0]:
            return
        revision = self._revision()
        explained = revision != self._revision_at_changed  # a scene without one: never
        self._revision_at_changed = revision
        if explained or self._records_dirty:
            return  # announced — or a pass is owed anyway, and that pass reads everything
        if not self._active:
            self._net_owed = True  # paused: a flag is all that happens
            return
        self._arm_net()

    def _arm_net(self) -> None:
        """(Re)start the quiet timer — and bound the wait in a scene that is never
        quiet: after ``NET_MAX_WAIT_S`` of repaints the pass runs with the next turn."""
        self._net_owed = False
        now = time.monotonic()
        with contextlib.suppress(RuntimeError):  # the #230 teardown guard
            if not self._net.isActive():
                self._net_since = now
            waited_out = now - self._net_since >= NET_MAX_WAIT_S
            self._net.start(0 if waited_out else self._quiet_ms)

    def _reconcile(self) -> None:
        """THE NET's pass: the scene was repainted, nobody announced a change, and it
        has been quiet since. Read the plan once and apply what differs (normally
        nothing)."""
        if not self._active or self._records_dirty:
            # paused; or a pass is owed and will read everything — also a pass that
            # FAILED: a repaint is no reason to try a failing pass again
            return
        self._failed_in_pass = False
        self._pass_records(reconciling=True)

    def _on_date_changed(self, _day: date) -> None:
        self.mark_dirty()  # growth is keyed on the plan date: the plants regrow

    def _on_instant_changed(self, _change: SimChange) -> None:
        self._sun_dirty = True  # the light follows every instant
        self._schedule(self._tick_ms)

    def _tick(self) -> None:
        if not self._active:
            return
        self._failed_in_pass = False
        if self._records_dirty:
            self._pass_records()
        elif self._sun_dirty:
            self._pass_light()

    def _pass_light(self) -> None:
        self._sun_dirty = False
        started = time.perf_counter()
        try:
            self._sync.set_sun(self._sun())
        except Exception as error:  # noqa: BLE001 - recover through the full pass
            self._log_failure("sending the sun failed; rebuilding the 3D scene", error)
            self._records_dirty = True
            self._pass_records()
            return
        self.light_count += 1
        self._done(TickReport(SceneDiff(), False, len(self._sync.records), 0.0,
                              (time.perf_counter() - started) * 1000.0))

    def _pass_records(self, *, reconciling: bool = False) -> None:
        self._records_dirty = self._sun_dirty = False
        # whatever was repainted before this line is in the snapshot this pass takes:
        # the net has nothing left to look at
        self._net_owed = False
        with contextlib.suppress(RuntimeError):  # the #230 teardown guard
            self._net.stop()
        started = time.perf_counter()
        skipped: list[SkippedItem] = []
        try:
            # THE ONE snapshotting scene of the process. The record layer's outline
            # memories ride a process-wide generation clock: one scene snapshotted
            # tick after tick is answered from memory; several scenes taking turns
            # would recompute everything on every tick. The workspace has one canvas
            # scene and one controller — keep it that way (L1.1's contract).
            records = snapshot_records(self._scene, self._clock.plan_date, skipped=skipped)
        except Exception as error:  # noqa: BLE001 - one item never raises; this is the scene itself
            self._give_up("the plan could not be read for the 3D view", error)
            return
        self.snapshot_count += 1
        snapshot_ms = (time.perf_counter() - started) * 1000.0
        sun = self._sun()
        width, depth = self._plan_size()
        started = time.perf_counter()
        changes: SceneDiff | None = None
        if self._sync.poisoned:
            # An engine call failed earlier and the sync refuses every apply until it is
            # reset: go straight there. The failure that left it so was logged when it
            # happened — by this class, in a pass; if it was not (somebody else's call
            # failed), say once that the scene is being rebuilt, and why. Nothing has
            # failed in THIS pass: if the rebuild goes through, the outage is over.
            if not self._failures_logged:
                self._failures_logged.add(("unknown state", "", ""))
                _LOG.warning("3D sync: the 3D scene was left in an unknown state by a failed "
                             "engine call; rebuilding it")
        else:
            try:
                changes = self._sync.apply(
                    records, sun=sun,
                    ground=self._ground(self._sync.records, records, width, depth))
            except Exception as error:  # noqa: BLE001 - whatever a sink raised
                self._log_failure(
                    "a pass failed; resetting the 3D scene and applying again", error)
        recovered = changes is None
        if changes is None:
            self.recovery_count += 1
            self._retired_by_reset += len(self._sync.records)
            try:
                self._sync.reset()
                changes = self._sync.apply(
                    records, sun=sun, ground=self._ground({}, records, width, depth))
            except Exception as again:  # noqa: BLE001 - give up for this tick, never crash
                self._give_up("the 3D scene could not be rebuilt", again)
                return
        self.apply_count += 1
        self._last_error = None
        if not self._failed_in_pass:
            self._failures_logged.clear()  # a pass in which nothing failed ends the outage
        if reconciling:
            self.reconcile_count += 1
            if not changes.is_empty:
                # an edit path changed the plan and told nobody: it is in 3D now (this
                # pass applied it), late by the quiet time — and it is counted, so that
                # a missing announcement is a number and not a feeling
                self.unannounced_changes += 1
                _LOG.debug("3D sync: the plan changed without an announcement (%s); the "
                           "quiet-time pass found and applied it", _kinds(changes))
        # This pass read the whole plan, so every announcement before it is spent. A
        # repaint of the SAME turn may still be its edit's own (it lands after the
        # pass); one turn later, a repaint is explained only by a NEW announcement.
        # Without the expiry an announcement that repaints nothing (a typed height
        # through its command) left "the revision moved" standing, and the next
        # UNANNOUNCED write's repaint read as explained: the net never armed and the
        # write stayed out of 3D (scoped re-check 2026-10-19, P1-B).
        QTimer.singleShot(0, self._expire_explanation)
        self._set_problems(tuple(skipped), dict(self._sync.failures))
        retired = self._retired_by_reset + len(changes.removed) + len(changes.geometry)
        self._retired_by_reset = 0
        self._done(TickReport(changes, True, len(records), snapshot_ms,
                              (time.perf_counter() - started) * 1000.0, recovered, retired,
                              reconciling))
        if self._document_pending:
            self._document_pending = False
            self.document_shown.emit()

    def _done(self, report: TickReport) -> None:
        self.last_tick = report
        self.applied.emit(report)

    def _log_failure(self, what: str, error: BaseException) -> None:
        """ONE line at ERROR — what failed, the exception's type and its message, the
        message normalised and capped — and the traceback at DEBUG only; the SAME
        failure again, before a pass went through without one, is a DEBUG line.

        An exception here can quote the plan (an item's id, a name, a value), and a
        traceback's last line is that message as it came: a line break in it would
        write a log line of its own into ``app.log``, the file a user sends to
        support (``core/plain_text.py``, §8.11). The log file records INFO and up,
        so the traceback is there for a developer who asks for DEBUG, and nowhere
        else. And a pass that fails the same way on every change would otherwise
        write that file full: one line says it, the next clean pass ends the outage.
        """
        self._failed_in_pass = True
        kind, message = log_text(type(error).__name__), log_text(error)
        signature = (what, kind, message)
        known = self._failures_logged
        if signature in known or len(known) >= _MAX_FAILURES_REMEMBERED:
            _LOG.debug("3D sync: %s (%s: %s) - again", what, kind, message)
            return
        known.add(signature)
        _LOG.error("3D sync: %s (%s: %s)", what, kind, message)
        _LOG.debug("3D sync: %s - traceback", what, exc_info=error)

    def _give_up(self, what: str, error: BaseException) -> None:
        self._log_failure(what, error)
        # nothing was lost: the next CHANGE — of the plan, the date or the light —
        # tries again; a repaint does not (``_reconcile``)
        self._records_dirty = self._sun_dirty = True
        # one normalised, capped line: this text travels (a signal, a property) and an
        # exception's message may quote the plan
        self._last_error = f"{what}: {log_text(error)}"
        self.failed.emit(self._last_error)

    def _set_problems(self, skipped: tuple[SkippedItem, ...],
                      failures: dict[str, BuildFailure]) -> None:
        if skipped == self._skipped and failures == self._failures:
            return
        self._skipped, self._failures = skipped, failures
        self.problems_changed.emit()

    def _ground(self, previous: Mapping[str, Record], records: Mapping[str, Record],
                width_cm: float, depth_cm: float) -> GroundSpec | None:
        if width_cm <= 0.0 or depth_cm <= 0.0:
            return None  # a scene without a plan rectangle: no ground to place
        try:
            return self._ground_stage(previous, records, width_cm, depth_cm)
        except Exception as error:  # noqa: BLE001 - a broken baker must not blank the garden
            self._log_failure("the ground stage failed; the bare plan rectangle is shown", error)
            return GroundSpec(width_cm, depth_cm)

    def _plan_size(self) -> tuple[float, float]:
        scene = self._scene
        width, depth = getattr(scene, "width_cm", None), getattr(scene, "height_cm", None)
        if isinstance(width, (int, float)) and isinstance(depth, (int, float)):
            return float(width), float(depth)
        rect = scene.sceneRect()
        return float(rect.width()), float(rect.height())

    def _sun(self) -> SunState:
        location = self._location()
        latitude = location.get("latitude") if isinstance(location, Mapping) else None
        longitude = location.get("longitude") if isinstance(location, Mapping) else None
        if latitude is None or longitude is None:
            return NO_LOCATION_SUN
        try:
            return SunState.from_solar_position(
                solar_position(float(latitude), float(longitude), self._clock.utc))
        except (TypeError, ValueError):
            _LOG.warning("3D sync: no sun for location %s; using the default light",
                         log_text(repr(location)))
            return NO_LOCATION_SUN
