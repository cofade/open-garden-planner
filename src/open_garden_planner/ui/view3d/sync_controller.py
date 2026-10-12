"""The 3D sync pipeline's controller (Phase 17 L1.3, ADR-065). Engine-free.

    scene.changed / stack_changed / date_changed ─► dirty ─► tick ─►
        snapshot_records(scene, clock.plan_date) ─► SceneSync.apply(records, sun, ground) ─► sink

One QObject per main window. It owns a ``SceneSync`` and an ``EngineSink`` it was
handed (``Quick3DSink`` in the app, ``RecordingSink`` in the tests — the seam),
listens to the canvas scene and the one ``SimClock``, and turns "something
changed" into at most ONE pipeline pass per event-loop turn.

The rules it enforces:

- **Paused while 3D is hidden.** ``set_active(False)`` leaves two flags and
  nothing else: no snapshot, no diff, no sink call, no timer. ``set_active(True)``
  runs one catch-up pass if a flag is set — a plain ``apply`` of the current
  snapshot, which ``SceneSync`` guarantees equals a from-scratch apply.
- **One tick, one transaction.** Records, sun and ground travel in one
  ``sync.apply`` (L1.1). A time-of-day change is LIGHT ONLY: one ``set_sun``, no
  snapshot (the plan did not change). A date change regrows the plants: a tick.
  Writes that arrive faster than ticks coalesce in the flags — an animated date
  never queues more than one pending regrow.
- **A snapshot only on a real change, never on a timer.** A whole-plan snapshot
  is O(total vertices) even when every record is cached (measured in ADR-065);
  the tick timer is single-shot and started by a change signal only.
- **A document change is not a reset.** A new or opened plan is just another
  snapshot; ``apply`` removes what is gone. ``SceneSync.reset()`` is RECOVERY:
  after a sink call raised or the sync is poisoned, the controller resets and
  applies once more, logs it, and never lets the error reach the event loop. If
  that fails too it gives up for this tick (``failed``), and the next change
  tries again.
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
#: The sun without a garden location — the documented fallback of FR-SUN-06 (the
#: shipped 3D view's): a southern midday sun.
NO_LOCATION_SUN: Final = SunState(elevation_deg=50.0, azimuth_deg=180.0)

LocationProvider = Callable[[], Mapping[str, Any] | None]
#: ``stage(previous_records, records, width_cm, depth_cm) -> GroundSpec`` (module docstring).
GroundStage = Callable[[Mapping[str, Record], Mapping[str, Record], float, float], GroundSpec]


def _log_failure(what: str, error: BaseException) -> None:
    """ONE line at ERROR — what failed, the exception's type and its message, the
    message normalised and capped — and the traceback at DEBUG only.

    An exception here can quote the plan (an item's id, a name, a value), and a
    traceback's last line is that message as it came: a line break in it would
    write a log line of its own into ``app.log``, the file a user sends to
    support (``core/plain_text.py``, §8.11). The log file records INFO and up, so
    the traceback is there for a developer who asks for DEBUG, and nowhere else.
    """
    _LOG.error("3D sync: %s (%s: %s)", what, log_text(type(error).__name__), log_text(error))
    _LOG.debug("3D sync: %s - traceback", what, exc_info=error)


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
                 parent: QObject | None = None, tick_ms: int = TICK_MS) -> None:
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
        #: Instruments (the gates read them): whole-plan snapshots taken, passes that
        #: called ``SceneSync.apply``, light-only passes, recoveries, the last pass.
        self.snapshot_count = 0
        self.apply_count = 0
        self.light_count = 0
        self.recovery_count = 0
        self.last_tick: TickReport | None = None
        self._tick_ms = tick_ms
        self._posted = False  # a pass event is in the queue
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tick)
        scene.changed.connect(self._on_scene_changed)
        scene.sceneRectChanged.connect(self._on_scene_changed)
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
            return
        if self.dirty:
            self._schedule(max(self._tick_ms, CATCH_UP_MS))

    def mark_dirty(self) -> None:
        """Something about the plan may have changed (wire change signals here)."""
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
            _log_failure("reset failed; the next pass tries again", error)
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
        with contextlib.suppress(RuntimeError):
            self._timer.stop()
        for signal in (self._scene.changed, self._scene.sceneRectChanged):
            with contextlib.suppress(RuntimeError, TypeError):
                signal.disconnect(self._on_scene_changed)

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

    def _on_scene_changed(self, *_regions: object) -> None:
        self.mark_dirty()

    def _on_date_changed(self, _day: date) -> None:
        self.mark_dirty()  # growth is keyed on the plan date: the plants regrow

    def _on_instant_changed(self, _change: SimChange) -> None:
        self._sun_dirty = True  # the light follows every instant
        self._schedule(self._tick_ms)

    def _tick(self) -> None:
        if not self._active:
            return
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
            _log_failure("sending the sun failed; rebuilding the 3D scene", error)
            self._records_dirty = True
            self._pass_records()
            return
        self.light_count += 1
        self._done(TickReport(SceneDiff(), False, len(self._sync.records), 0.0,
                              (time.perf_counter() - started) * 1000.0))

    def _pass_records(self) -> None:
        self._records_dirty = self._sun_dirty = False
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
        recovered = False
        try:
            changes = self._sync.apply(
                records, sun=sun, ground=self._ground(self._sync.records, records, width, depth))
        except Exception as error:  # noqa: BLE001 - SyncStateError, or whatever a sink raised
            _log_failure("a pass failed; resetting the 3D scene and applying again", error)
            self.recovery_count += 1
            recovered = True
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
        self._set_problems(tuple(skipped), dict(self._sync.failures))
        retired = self._retired_by_reset + len(changes.removed) + len(changes.geometry)
        self._retired_by_reset = 0
        self._done(TickReport(changes, True, len(records), snapshot_ms,
                              (time.perf_counter() - started) * 1000.0, recovered, retired))
        if self._document_pending:
            self._document_pending = False
            self.document_shown.emit()

    def _done(self, report: TickReport) -> None:
        self.last_tick = report
        self.applied.emit(report)

    def _give_up(self, what: str, error: BaseException) -> None:
        _log_failure(what, error)
        self._records_dirty = self._sun_dirty = True  # the next change tries again
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
            _log_failure("the ground stage failed; the bare plan rectangle is shown", error)
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
