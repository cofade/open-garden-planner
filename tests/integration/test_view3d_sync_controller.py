"""The 3D sync controller against a real canvas and a ``RecordingSink`` (L1.3, ADR-065).

``ui/view3d/sync_controller.Scene3DController`` is the wiring between the plan and
the 3D engine: change signals in, at most one pipeline pass per event-loop turn
out. Everything here runs without a GPU — the sink is the recording double — and
through the REAL signals: the scene's ``plan_changed`` (its plan revision: items,
the undo stack, layers, the canvas size), ``QGraphicsScene.changed`` (a repaint —
which starts no pass, only the net's quiet timer) and the sim clock's two channels.
Gates of the story pinned here: G4 (paused while hidden; one catch-up pass that
equals a from-scratch apply) and G9 (time → light only; date → the dated plants
regrow, nothing else; a destroyed subscriber is never called; a repaint is not a
snapshot). The same in the real main window: ``test_view3d_plan_revision.py``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsScene

from open_garden_planner.core.commands import (
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
    ResizeItemCommand,
)
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import (
    GroundSpec,
    Record,
    RecordingSink,
    SceneSync,
    SinkProtocolError,
    SunState,
)
from open_garden_planner.core.scene3d import polygon as polygon_module
from open_garden_planner.core.scene3d.builders import plants, production_registry
from open_garden_planner.core.scene3d.camera import Bounds
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.core.solar import solar_position
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rect_like_geometry,
    build_rect_resize,
)
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d import snapshot as snapshot_module
from open_garden_planner.ui.view3d import sync_controller
from open_garden_planner.ui.view3d.snapshot import SkipReason, snapshot_records
from open_garden_planner.ui.view3d.sync_controller import (
    NO_LOCATION_SUN,
    Scene3DController,
    TickReport,
    plain_ground,
)
from tests.integration.test_scene3d_plants import drop
from tests.integration.test_scene3d_snapshot import _recolour as recolour_fill

BERLIN = {"latitude": 52.52, "longitude": 13.405}
NOON = datetime(2026, 6, 21, 12, 0)
BEGIN, COMMIT = ("begin", None), ("commit", None)
GROUND, SUN = ("set_ground", None), ("set_sun", None)


class Rig:
    """A canvas, a clock, a recording sink and the controller between them — wired
    the way the workspace wires them."""

    def __init__(self, view: CanvasView, qtbot: Any, *, location: dict[str, float] | None = None,
                 sink: Any = None, registry: Any = None, quiet_ms: int | None = None) -> None:
        self.view, self.qtbot = view, qtbot
        self.scene = view.scene()
        self.commands = view.command_manager
        self.clock = SimClock(NOON)
        self.location = location
        self.sink = sink if sink is not None else RecordingSink()
        # nothing else is wired: the scene announces its own plan (items, the undo
        # stack, layers, the canvas size) and the controller listens to the scene
        self.controller = Scene3DController(
            self.scene, self.clock, lambda: self.location, self.sink, registry,
            **({} if quiet_ms is None else {"quiet_ms": quiet_ms}))
        self.reports: list[TickReport] = []
        self.controller.applied.connect(self.reports.append)
        self.item: Any = None   # the net's tests keep their one bed here

    def settle(self) -> list[tuple[str, str | None]]:
        """Let the event loop run until the pipeline is quiet; the sink calls since
        the last ``settle``."""
        self.qtbot.wait(70)
        calls = self.recorder.ops()
        self.recorder.clear_calls()
        return calls

    @property
    def recorder(self) -> RecordingSink:
        return self.sink if isinstance(self.sink, RecordingSink) else self.sink.inner

    def bed(self, x: float = 400.0, y: float = 300.0) -> RectangleItem:
        item = RectangleItem(x, y, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                             layer_id=self.scene.active_layer.id)
        self.commands.execute(CreateItemCommand(self.scene, item, "bed"))
        return item

    def assert_equals_a_from_scratch_apply(self) -> None:
        """Incremental == full rebuild, for what the controller sent."""
        sync = self.controller.sync
        fresh_sink = RecordingSink()
        fresh = SceneSync(fresh_sink, sync.registry)
        fresh.apply(snapshot_records(self.scene, self.clock.plan_date),
                    sun=sync.sun, ground=sync.ground)
        assert self.recorder.state() == fresh_sink.state() == sync.expected_state()


@pytest.fixture()
def rig(canvas: CanvasView, qtbot) -> Rig:
    return Rig(canvas, qtbot)


# ── G4: paused while hidden, one catch-up pass ───────────────────────────────


def test_nothing_happens_before_3d_is_ever_shown(rig: Rig) -> None:
    rig.bed()
    assert rig.settle() == []
    assert rig.controller.snapshot_count == 0 and rig.controller.apply_count == 0
    assert rig.controller.dirty is True


def test_the_first_show_is_one_pass_with_sun_and_ground_in_the_same_transaction(rig: Rig) -> None:
    bed = rig.bed()
    rig.controller.set_active(True)
    assert rig.controller.snapshot_count == 0, "the pass waits for the event loop: the pane paints first"
    assert rig.settle() == [BEGIN, ("add", str(bed.item_id)), GROUND, SUN, COMMIT]
    assert (rig.controller.snapshot_count, rig.controller.apply_count) == (1, 1)
    assert rig.recorder.ground == GroundSpec(5000.0, 3000.0)
    assert rig.recorder.sun == NO_LOCATION_SUN
    rig.assert_equals_a_from_scratch_apply()
    report = rig.reports[-1]
    assert report.snapshot and report.records == 1 and report.changes.added == (str(bed.item_id),)


def test_hidden_edits_cause_no_snapshot_and_no_sink_call_and_one_catch_up_pass(rig: Rig) -> None:
    """Gate G4. Every kind of change while 3D is hidden leaves a flag and nothing else."""
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    rig.controller.set_active(False)
    before = (rig.controller.snapshot_count, rig.controller.apply_count, rig.controller.light_count)

    tree = CircleItem(1500.0, 900.0, 120.0, object_type=ObjectType.TREE,
                      layer_id=rig.scene.active_layer.id)
    edits = 0
    rig.commands.execute(CreateItemCommand(rig.scene, tree, "tree"))
    rig.commands.execute(MoveItemsCommand([bed], QPointF(137.25, -42.5)))
    rig.commands.execute(recolour_fill(bed, QColor(200, 30, 30)))
    old, new = build_rect_resize(bed, 500.0, 120.0, keep_center=True)
    rig.commands.execute(ResizeItemCommand(bed, old, new, apply_rect_like_geometry))
    rig.commands.undo()
    rig.commands.redo()
    rig.commands.execute(DeleteItemsCommand(rig.scene, [tree]))
    rig.commands.undo()
    edits += 8
    for index in range(20):
        rig.commands.execute(MoveItemsCommand([bed], QPointF(1.0 + index, 0.5)))
        edits += 1
    rig.clock.set_date(date(2026, 8, 1))
    rig.clock.set_time_of_day(time(17, 30))
    bed.metadata[METADATA_KEY] = 75.0
    rig.controller.mark_dirty()
    rig.controller.refresh_sun()
    rig.controller.document_changed()
    assert edits == 28

    assert rig.settle() == []
    assert (rig.controller.snapshot_count, rig.controller.apply_count,
            rig.controller.light_count) == before
    assert rig.controller.dirty is True

    rig.controller.set_active(True)
    calls = rig.settle()
    assert calls[0] == BEGIN and calls[-1] == COMMIT and calls.count(BEGIN) == 1
    assert (rig.controller.snapshot_count, rig.controller.apply_count) == (before[0] + 1, before[1] + 1)
    assert rig.controller.dirty is False
    rig.assert_equals_a_from_scratch_apply()


def test_coming_back_with_nothing_changed_costs_nothing(rig: Rig) -> None:
    rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    counts = (rig.controller.snapshot_count, rig.controller.apply_count)
    for _ in range(5):
        rig.controller.set_active(False)
        rig.controller.set_active(True)
    assert rig.settle() == []
    assert (rig.controller.snapshot_count, rig.controller.apply_count) == counts


def test_hiding_cancels_a_pass_that_was_only_scheduled(rig: Rig) -> None:
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    counts = rig.controller.snapshot_count
    rig.commands.execute(MoveItemsCommand([bed], QPointF(10.0, 0.0)))
    rig.controller.set_active(False)   # before the event loop ran
    assert rig.settle() == []
    assert rig.controller.snapshot_count == counts and rig.controller.dirty is True
    rig.controller.flush()             # "run what is pending" is not a way round the pause
    assert rig.recorder.ops() == [] and rig.controller.snapshot_count == counts


# ── the edit session ─────────────────────────────────────────────────────────


def test_an_edit_session_sends_the_minimal_calls_one_pass_per_turn(rig: Rig) -> None:
    rig.controller.set_active(True)
    assert rig.settle() == [BEGIN, GROUND, SUN, COMMIT]  # an empty plan: its ground and light

    bed = rig.bed()
    bed_id = str(bed.item_id)
    assert rig.settle() == [BEGIN, ("add", bed_id), COMMIT]

    rig.commands.execute(MoveItemsCommand([bed], QPointF(137.25, -42.5)))
    assert rig.settle() == [BEGIN, ("update_transform", bed_id), COMMIT]

    rig.commands.execute(recolour_fill(bed, QColor(200, 30, 30)))
    assert rig.settle() == [BEGIN, ("update_material", bed_id), COMMIT]

    old, new = build_rect_resize(bed, 500.0, 120.0, keep_center=True)
    rig.commands.execute(ResizeItemCommand(bed, old, new, apply_rect_like_geometry))
    assert rig.settle() == [BEGIN, ("replace_geometry", bed_id), COMMIT]

    rig.commands.execute(DeleteItemsCommand(rig.scene, [bed]))
    assert rig.settle() == [BEGIN, ("remove", bed_id), COMMIT]
    rig.commands.undo()
    assert rig.settle() == [BEGIN, ("add", bed_id), COMMIT]

    snapshots = rig.controller.snapshot_count
    bed.setSelected(True)     # a selection repaints the scene: no pass, and nothing to send
    bed.setSelected(False)
    assert rig.settle() == [] and rig.controller.snapshot_count == snapshots
    rig.assert_equals_a_from_scratch_apply()
    assert rig.controller.recovery_count == 0 and rig.controller.last_error is None
    assert rig.controller.unannounced_changes == 0, "every edit above announced itself"


def test_many_edits_in_one_turn_of_the_event_loop_are_one_snapshot(rig: Rig) -> None:
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    snapshots = rig.controller.snapshot_count
    for index in range(40):
        rig.commands.execute(MoveItemsCommand([bed], QPointF(1.0 + index, 0.0)))
    rig.controller.flush()
    assert rig.controller.snapshot_count == snapshots + 1
    assert rig.recorder.ops() == [BEGIN, ("update_transform", str(bed.item_id)), COMMIT]


def test_one_command_is_one_snapshot_although_several_signals_announce_it(rig: Rig) -> None:
    """A move by command announces itself more than once — the item's own notice, the
    undo stack's ``stack_changed`` — and the scene's ``changed`` follows a moment later
    (it is queued). The announcements share one pass (a posted event, one per turn),
    and the repaint is explained by them: it starts nothing."""
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    for index in range(10):
        snapshots = rig.controller.snapshot_count
        rig.commands.execute(MoveItemsCommand([bed], QPointF(3.0 + index, 1.0)))
        assert rig.controller.snapshot_count == snapshots, "not inside the command"
        calls = rig.settle()
        assert calls == [BEGIN, ("update_transform", str(bed.item_id)), COMMIT]
        assert rig.controller.snapshot_count == snapshots + 1


def test_a_height_typed_into_the_metadata_reaches_3d_through_the_undo_stack_signal(rig: Rig) -> None:
    """A metadata-only edit repaints nothing and moves no item: the undo stack's
    ``stack_changed`` is its announcement (the scene's plan revision follows it)."""
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    bed.metadata[METADATA_KEY] = 75.0
    rig.commands.stack_changed.emit()
    assert rig.settle() == [BEGIN, ("replace_geometry", str(bed.item_id)), COMMIT]


def test_a_metadata_write_round_the_undo_stack_reaches_3d_through_the_nudge(rig: Rig) -> None:
    """… and a writer that goes round the stack too says so itself:
    ``CanvasScene.note_plan_changed()`` — at once, not after the quiet time."""
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    bed.metadata[METADATA_KEY] = 75.0
    rig.scene.note_plan_changed()
    assert rig.settle() == [BEGIN, ("replace_geometry", str(bed.item_id)), COMMIT]
    assert rig.reports[-1].reconciled is False and rig.controller.unannounced_changes == 0


def test_an_edit_reaches_3d_while_the_canvas_itself_is_hidden(rig: Rig) -> None:
    """3D mode hides the canvas view. An item's own notice does not need a view."""
    bed = rig.bed()
    rig.view.hide()
    rig.controller.set_active(True)
    rig.settle()
    bed.setPos(bed.pos() + QPointF(50.0, 0.0))   # no command, no stack signal: the item alone
    assert rig.settle() == [BEGIN, ("update_transform", str(bed.item_id)), COMMIT]


def test_a_resized_canvas_moves_the_ground(rig: Rig) -> None:
    rig.controller.set_active(True)
    rig.settle()
    rig.scene.resize_canvas(8000.0, 6000.0)
    assert rig.settle() == [BEGIN, GROUND, COMMIT]
    assert rig.recorder.ground == GroundSpec(8000.0, 6000.0)
    assert rig.controller.plan_bounds() == Bounds.of_plan(8000.0, 6000.0, 0.0)


# ── the net: a repaint is not an edit; an edit nobody announced still arrives ──
#
# ``QGraphicsScene.changed`` fires for every repaint. It starts no pass (the reviewer
# counted, in the real window: 10 time changes with the sun simulation on = 10 whole-
# plan snapshots, 20 preview mouse moves = 20). It (re)starts one quiet timer, and
# after the quiet time one reconciliation pass runs — which finds nothing unless an
# edit path forgot to announce itself.

QUIET = 150   # ms — the net's quiet time in these tests (the app's: NET_QUIET_MS)


def _net_rig(canvas: CanvasView, qtbot: Any, **options: Any) -> Rig:
    rig = Rig(canvas, qtbot, quiet_ms=QUIET, **options)
    rig.item = rig.bed()
    rig.controller.set_active(True)
    rig.qtbot.wait(QUIET * 3)   # the first pass — and whatever its own repaint asked for
    rig.recorder.clear_calls()
    return rig


def _turns(count: int = 3) -> None:
    """Let queued signals and posted events be delivered — without letting time pass."""
    for _ in range(count):
        QApplication.processEvents()


def _select(rig: Rig) -> None:
    rig.item.setSelected(not rig.item.isSelected())


def _preview(rig: Rig) -> None:
    rubber = QGraphicsRectItem(QRectF(100.0, 100.0, 40.0, 30.0))
    rig.scene.addItem(rubber)
    _turns(1)
    rubber.setRect(QRectF(100.0, 100.0, 80.0, 60.0))
    _turns(1)
    rig.scene.removeItem(rubber)


@pytest.mark.parametrize("repaint", [
    _select, _preview, lambda rig: rig.item.update(), lambda rig: rig.scene.update(),
    lambda rig: rig.item.setOpacity(0.5 if rig.item.opacity() == 1.0 else 1.0),
], ids=["selection", "tool_preview", "item_update", "scene_update", "opacity"])
def test_a_repaint_takes_no_snapshot_and_one_reconciliation_once_the_scene_is_quiet(
        canvas: CanvasView, qtbot, repaint: Any) -> None:
    rig = _net_rig(canvas, qtbot)
    controller = rig.controller
    snapshots, reconciled = controller.snapshot_count, controller.reconcile_count
    changed: list[int] = []
    rig.scene.changed.connect(lambda *_regions: changed.append(1))
    for _ in range(20):
        repaint(rig)
        _turns()
    assert len(changed) >= 10, "the scene did repaint, again and again"
    assert controller.snapshot_count == snapshots, "… and not one snapshot was taken for it"
    assert rig.recorder.ops() == []
    qtbot.wait(QUIET * 3)
    assert controller.snapshot_count == snapshots + 1, "ONE pass, once the scene was quiet"
    assert controller.reconcile_count == reconciled + 1
    report = rig.reports[-1]
    assert report.reconciled is True and report.snapshot is True and report.changes.is_empty
    assert rig.recorder.ops() == [], "it found nothing: no engine call"
    assert controller.unannounced_changes == 0
    qtbot.wait(QUIET * 3)
    assert controller.snapshot_count == snapshots + 1, "and then nothing: no timer spins"


def test_the_apps_quiet_time_is_twice_the_sun_animations_tick() -> None:
    """While "Animate" runs, the shadows repaint every tick. A quiet time below the tick
    would reconcile BETWEEN two ticks — a snapshot per tick again."""
    from open_garden_planner.ui.widgets import sun_sim_toolbar

    assert sync_controller.NET_QUIET_MS == 400
    assert sync_controller.NET_QUIET_MS >= 2 * sun_sim_toolbar._ANIMATE_INTERVAL_MS
    assert sync_controller.NET_MAX_WAIT_S * 1000.0 > 10 * sync_controller.NET_QUIET_MS


def test_an_edit_nobody_announced_is_in_3d_after_the_quiet_time_and_is_counted(
        canvas: CanvasView, qtbot, caplog: pytest.LogCaptureFixture) -> None:
    """A writer that changes what an item IS — here its height, in ``metadata`` —
    without a command, without moving it and without the nudge, but with a repaint
    (the shipped ad-hoc "nudge" was ``item.update()``). Nothing announces it; the net
    finds it: applied after the quiet time, counted, one DEBUG line that says what
    KIND of difference it was and names no item."""
    rig = _net_rig(canvas, qtbot)
    controller, bed = rig.controller, rig.item
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        bed.metadata[METADATA_KEY] = 75.0
        bed.update()
        _turns()
        assert rig.recorder.ops() == [] and controller.unannounced_changes == 0, "not at once"
        qtbot.wait(QUIET * 3)
    assert rig.recorder.ops() == [BEGIN, ("replace_geometry", str(bed.item_id)), COMMIT]
    assert controller.unannounced_changes == 1 and rig.reports[-1].reconciled is True
    said = [record for record in caplog.records
            if record.name == LOGGER and "without an announcement" in record.getMessage()]
    assert [(record.levelno, record.getMessage()) for record in said] == [(logging.DEBUG, (
        "3D sync: the plan changed without an announcement (geometry 1); the quiet-time "
        "pass found and applied it"))]
    assert str(bed.item_id) not in said[0].getMessage()
    rig.assert_equals_a_from_scratch_apply()
    # the same edit ANNOUNCED is there at once and counts nothing
    rig.recorder.clear_calls()
    bed.metadata[METADATA_KEY] = 90.0
    rig.scene.note_plan_changed()
    assert rig.settle() == [BEGIN, ("replace_geometry", str(bed.item_id)), COMMIT]
    assert controller.unannounced_changes == 1


def test_a_write_that_neither_announces_nor_repaints_waits_for_the_next_repaint(
        canvas: CanvasView, qtbot) -> None:
    """The limit, stated: the net is started by a repaint. A write that tells nobody
    AND paints nothing is invisible to everything that follows the scene, until
    anything at all repaints it — a hover is enough."""
    rig = _net_rig(canvas, qtbot)
    controller, bed = rig.controller, rig.item
    bed.metadata[METADATA_KEY] = 75.0
    qtbot.wait(QUIET * 3)
    assert rig.recorder.ops() == [] and controller.unannounced_changes == 0
    bed.setSelected(True)                       # any repaint
    qtbot.wait(QUIET * 3)
    assert rig.recorder.ops() == [BEGIN, ("replace_geometry", str(bed.item_id)), COMMIT]
    assert controller.unannounced_changes == 1


def test_a_pass_for_an_announced_change_leaves_the_net_nothing_to_do(
        canvas: CanvasView, qtbot) -> None:
    """A repaint started the quiet timer; then an announced change runs its pass, and
    that pass read the whole plan: the timer is stopped, and the edit's own repaint —
    explained by its announcement — does not start it again."""
    rig = _net_rig(canvas, qtbot)
    controller, bed = rig.controller, rig.item
    snapshots, reconciled = controller.snapshot_count, controller.reconcile_count
    bed.update()
    _turns()
    rig.commands.execute(MoveItemsCommand([bed], QPointF(25.0, 0.0)))
    qtbot.wait(QUIET * 3)
    assert rig.recorder.ops() == [BEGIN, ("update_transform", str(bed.item_id)), COMMIT]
    assert controller.snapshot_count == snapshots + 1
    assert controller.reconcile_count == reconciled and rig.reports[-1].reconciled is False


def test_a_repaint_after_the_pass_of_its_announcement_starts_no_quiet_timer(
        canvas: CanvasView, qtbot) -> None:
    """A writer that nudges FIRST and repaints after (``note_plan_changed()``, then
    ``item.update()``): the pass is posted before the scene's queued ``changed``, runs
    first, and the repaint arrives with no pass owed. It is still explained — the
    revision moved since the last repaint — so it starts no quiet timer: an announced
    edit costs ONE snapshot, not a second one 400 ms later that finds nothing."""
    rig = _net_rig(canvas, qtbot)
    controller, bed = rig.controller, rig.item
    snapshots, reconciled = controller.snapshot_count, controller.reconcile_count
    bed.metadata[METADATA_KEY] = 75.0
    rig.scene.note_plan_changed()               # the pass is posted now …
    bed.update()                                # … the scene's changed after it
    _turns()
    assert controller.snapshot_count == snapshots + 1, "the announced pass ran"
    assert controller.idle, "the repaint after it was explained: no quiet timer"
    qtbot.wait(QUIET * 3)
    assert controller.snapshot_count == snapshots + 1
    assert controller.reconcile_count == reconciled and controller.unannounced_changes == 0


def test_a_quiet_time_cut_short_by_hiding_is_owed_when_3d_comes_back(
        canvas: CanvasView, qtbot) -> None:
    """An unannounced write was repainted and the quiet timer ran — then 3D was hidden
    before it fired, and nothing repainted while it was hidden. Coming back owes that
    look: the timer starts again, and the write reaches 3D one quiet time later."""
    rig = _net_rig(canvas, qtbot)
    controller, bed = rig.controller, rig.item
    bed.metadata[METADATA_KEY] = 75.0           # no command, no nudge …
    bed.update()                                # … a repaint only
    _turns()
    assert not controller.idle, "the quiet timer runs"
    controller.set_active(False)                # hidden before it fires
    qtbot.wait(QUIET * 3)
    assert rig.recorder.ops() == [] and controller.unannounced_changes == 0
    controller.set_active(True)                 # nothing was repainted in between
    qtbot.wait(QUIET * 3)
    assert rig.recorder.ops() == [BEGIN, ("replace_geometry", str(bed.item_id)), COMMIT]
    assert controller.unannounced_changes == 1


def test_the_net_does_not_run_while_3d_is_hidden_and_once_when_it_comes_back(
        canvas: CanvasView, qtbot) -> None:
    rig = _net_rig(canvas, qtbot)
    controller, bed = rig.controller, rig.item
    snapshots = controller.snapshot_count
    bed.update()
    _turns()                                    # the timer runs …
    controller.set_active(False)                # … and 3D is hidden before it fires
    bed.metadata[METADATA_KEY] = 75.0           # an unannounced edit while hidden
    bed.update()
    qtbot.wait(QUIET * 3)
    assert controller.snapshot_count == snapshots and rig.recorder.ops() == []
    assert controller.dirty is False, "a repaint is not a change of the plan"
    controller.set_active(True)
    _turns()
    assert controller.snapshot_count == snapshots, "coming back is not a pass either"
    qtbot.wait(QUIET * 3)
    assert controller.snapshot_count == snapshots + 1 and controller.unannounced_changes == 1
    assert rig.recorder.ops() == [BEGIN, ("replace_geometry", str(bed.item_id)), COMMIT]
    # hidden and shown with nothing repainted in between: nothing at all
    controller.set_active(False)
    controller.set_active(True)
    qtbot.wait(QUIET * 3)
    assert controller.snapshot_count == snapshots + 1


def test_a_scene_that_is_never_quiet_is_reconciled_after_the_longest_wait(
        canvas: CanvasView, qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    """The sun animated for minutes repaints every 200 ms: the quiet time never
    comes. After ``NET_MAX_WAIT_S`` of repaints the pass runs with the next turn."""
    import time as real_time
    import types

    now = [1000.0]
    monkeypatch.setattr(sync_controller, "time", types.SimpleNamespace(
        monotonic=lambda: now[0], perf_counter=real_time.perf_counter))
    rig = Rig(canvas, qtbot, quiet_ms=60_000)   # a quiet time that never comes in this test
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    controller = rig.controller
    snapshots = controller.snapshot_count
    for second in range(4):                     # four seconds of repaints: inside the wait
        now[0] = 1000.0 + second
        bed.update()
        _turns()
        qtbot.wait(20)
    assert controller.snapshot_count == snapshots
    now[0] = 1000.0 + sync_controller.NET_MAX_WAIT_S + 0.5
    bed.metadata[METADATA_KEY] = 75.0           # (unannounced, to see the pass apply it)
    bed.update()
    _turns()
    qtbot.wait(40)
    assert controller.snapshot_count == snapshots + 1 and rig.reports[-1].reconciled is True
    assert controller.unannounced_changes == 1
    now[0] += 1.0                               # the next run of repaints starts a new wait
    bed.update()
    _turns()
    qtbot.wait(40)
    assert controller.snapshot_count == snapshots + 1


def test_a_net_that_fires_while_an_announced_pass_is_on_its_way_stands_down(
        canvas: CanvasView, qtbot) -> None:
    """A controller whose pass waits LONGER than the quiet time (``tick_ms`` above it;
    the app's is 0): the quiet timer of an earlier repaint fires while an ANNOUNCED pass
    is still on its way. The net stands down — that pass reads everything — so the
    change is applied once, by its own pass, and never counted as one nobody announced."""
    scene = canvas.scene()
    bed = RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                        layer_id=scene.active_layer.id)
    canvas.command_manager.execute(CreateItemCommand(scene, bed, "bed"))
    sink = RecordingSink()
    controller = Scene3DController(scene, SimClock(NOON), lambda: None, sink,
                                   quiet_ms=QUIET, tick_ms=QUIET * 4)
    controller.set_active(True)
    qtbot.waitUntil(lambda: controller.apply_count >= 1 and controller.idle, timeout=5000)
    sink.clear_calls()
    applies = controller.apply_count
    reconciled, snapshots = controller.reconcile_count, controller.snapshot_count
    bed.update()                                # an unexplained repaint: the quiet timer runs
    _turns()
    bed.metadata[METADATA_KEY] = 75.0
    scene.note_plan_changed()                   # announced; its pass waits QUIET * 4
    qtbot.waitUntil(lambda: controller.apply_count > applies and controller.idle, timeout=5000)
    assert sink.ops() == [BEGIN, ("replace_geometry", str(bed.item_id)), COMMIT]
    assert controller.snapshot_count == snapshots + 1, "one pass, not the net's and then its own"
    assert controller.reconcile_count == reconciled and controller.unannounced_changes == 0
    assert controller.last_tick is not None and controller.last_tick.reconciled is False
    controller.shutdown()


def test_a_scene_that_announces_nothing_is_kept_in_step_by_the_net_alone(qtbot) -> None:
    """A plain ``QGraphicsScene`` has no plan revision. The controller still follows
    it — late by the quiet time, and every edit counted as unannounced."""
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0.0, 0.0, 5000.0, 3000.0))
    bed = RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    sink = RecordingSink()
    controller = Scene3DController(scene, SimClock(NOON), lambda: None, sink, quiet_ms=QUIET)
    controller.set_active(True)
    qtbot.wait(QUIET * 3)
    assert sink.item_ids() == (str(bed.item_id),)
    sink.clear_calls()
    bed.setPos(bed.pos() + QPointF(50.0, 0.0))
    _turns()
    assert sink.ops() == []
    qtbot.wait(QUIET * 3)
    assert sink.ops() == [BEGIN, ("update_transform", str(bed.item_id)), COMMIT]
    assert controller.unannounced_changes == 1
    controller.shutdown()


def test_a_failing_pass_is_not_tried_again_by_a_repaint_and_says_so_once(
        canvas: CanvasView, qtbot, caplog: pytest.LogCaptureFixture) -> None:
    """An engine that is gone for good: every change of the plan tries again (nothing
    is lost) — a repaint does not. And the log gets ONE ERROR line per distinct failure
    of the outage, not two per failed pass; the same failure again is a DEBUG line. The
    next pass that goes through ends the outage, and a new one is said again."""
    sink = FailingSink()
    rig = _net_rig(canvas, qtbot, sink=sink)
    controller, bed = rig.controller, rig.item
    errors: list[str] = []
    controller.failed.connect(errors.append)
    sink.fail_on, sink.failures_left = "begin", 10**6
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        for index in range(5):
            rig.commands.execute(MoveItemsCommand([bed], QPointF(1.0 + index, 0.0)))
            rig.settle()
        lines, debug = _own_records(caplog)
        assert [line.split(" (RuntimeError: ")[0] for line in lines] == [
            "3D sync: a pass failed; resetting the 3D scene and applying again",
            "3D sync: the 3D scene could not be rebuilt"], "two lines for five failed passes"
        again = [record.getMessage() for record in debug if record.getMessage().endswith("- again")]
        # the four passes after the first find the sync refusing every apply (it knows
        # an engine call failed) and go straight to the rebuild — which fails the same way
        assert len(again) == 4 and all("could not be rebuilt" in line for line in again)
        assert len(errors) == 5, "every change of the plan tried again"

        reconciled = controller.reconcile_count
        for _ in range(5):                      # repaints, and the quiet time after them
            bed.update()
            _turns()
        qtbot.wait(QUIET * 3)
        assert len(errors) == 5 and controller.reconcile_count == reconciled, (
            "a repaint is no reason to try a failing pass again")
        assert controller.dirty is True

        sink.failures_left = 0                  # the engine is back
        rig.commands.execute(MoveItemsCommand([bed], QPointF(1.0, 0.0)))
        rig.settle()
        assert controller.last_error is None
        rig.assert_equals_a_from_scratch_apply()

        caplog.clear()
        sink.failures_left = 2                  # … and gone again: a NEW outage
        rig.commands.execute(MoveItemsCommand([bed], QPointF(1.0, 0.0)))
        rig.settle()
        lines, _debug = _own_records(caplog)
        assert len(lines) == 2, "said again: the outage before it had ended"


def test_a_failure_that_recovers_every_time_is_said_once_too(
        canvas: CanvasView, qtbot, caplog: pytest.LogCaptureFixture) -> None:
    """A sink that fails every move and recovers through the reset: each pass goes
    through in the end, but not CLEANLY — the outage is not over, one line says it."""
    sink = FailingSink()
    rig = _net_rig(canvas, qtbot, sink=sink)
    bed = rig.item
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        for index in range(4):
            sink.fail_on, sink.failures_left = "update_transform", 1
            rig.commands.execute(MoveItemsCommand([bed], QPointF(1.0 + index, 0.0)))
            rig.settle()
        lines, _debug = _own_records(caplog)
    assert rig.controller.recovery_count == 4
    assert len(lines) == 1 and "resetting the 3D scene" in lines[0]


# ── G9: the sim clock ────────────────────────────────────────────────────────


def test_a_time_change_moves_the_light_and_takes_no_snapshot(canvas: CanvasView, qtbot) -> None:
    rig = Rig(canvas, qtbot, location=dict(BERLIN))
    rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    snapshots, applies = rig.controller.snapshot_count, rig.controller.apply_count

    rig.clock.set_time_of_day(time(17, 30))
    assert rig.settle() == [BEGIN, SUN, COMMIT]
    assert (rig.controller.snapshot_count, rig.controller.apply_count) == (snapshots, applies)
    assert rig.controller.light_count == 1
    expected = solar_position(BERLIN["latitude"], BERLIN["longitude"], rig.clock.utc)
    assert rig.recorder.sun == SunState.from_solar_position(expected)
    assert rig.reports[-1].snapshot is False


def test_time_changes_faster_than_passes_are_one_light_update(canvas: CanvasView, qtbot) -> None:
    rig = Rig(canvas, qtbot, location=dict(BERLIN))
    rig.controller.set_active(True)
    rig.settle()
    for minute in range(30):
        rig.clock.set_time_of_day(time(13, minute))
    assert rig.settle() == [BEGIN, SUN, COMMIT]
    assert rig.controller.light_count == 1


def test_without_a_location_the_documented_default_sun_is_sent_once(rig: Rig) -> None:
    rig.controller.set_active(True)
    rig.settle()
    assert rig.recorder.sun == NO_LOCATION_SUN == SunState(50.0, 180.0)   # FR-SUN-06
    rig.clock.set_time_of_day(time(18, 0))
    assert rig.settle() == [], "the same sun again is not sent"
    rig.location = dict(BERLIN)
    rig.controller.refresh_sun()
    assert rig.settle() == [BEGIN, SUN, COMMIT]


def test_a_date_change_regrows_the_dated_plants_and_nothing_else(canvas: CanvasView, qtbot) -> None:
    """Gate G9. An apple tree measured on its planting day grows with the plan date; a
    tomato planted next May has not been planted yet and a bed never grows."""
    rig = Rig(canvas, qtbot, location=dict(BERLIN))
    bed = rig.bed(2000.0, 1500.0)
    apple = drop(canvas, "TREE:species=apple tree", QPointF(900.0, 700.0))
    apple.metadata["plant_instance"] = {
        "planting_date": "2024-04-01", "current_height_cm": 180.0, "current_spread_cm": 120.0}
    spruce = drop(canvas, "TREE:species=spruce", QPointF(3000.0, 700.0))   # no planting date
    rig.controller.set_active(True)
    rig.settle()
    snapshots = rig.controller.snapshot_count

    rig.clock.set_date(date(2027, 6, 21))
    calls = rig.settle()
    assert calls == [BEGIN, ("replace_geometry", str(apple.item_id)), SUN, COMMIT]
    assert rig.controller.snapshot_count == snapshots + 1
    assert {str(bed.item_id), str(spruce.item_id)} <= set(rig.recorder.item_ids())
    rig.assert_equals_a_from_scratch_apply()


def test_an_animated_date_never_queues_more_than_one_regrow(canvas: CanvasView, qtbot) -> None:
    rig = Rig(canvas, qtbot)
    apple = drop(canvas, "TREE:species=apple tree", QPointF(900.0, 700.0))
    apple.metadata["plant_instance"] = {
        "planting_date": "2024-04-01", "current_height_cm": 180.0, "current_spread_cm": 120.0}
    rig.controller.set_active(True)
    rig.settle()
    snapshots = rig.controller.snapshot_count
    for day in range(1, 29):
        rig.clock.set_date(date(2027, 2, day))
    calls = rig.settle()
    assert rig.controller.snapshot_count == snapshots + 1
    assert calls == [BEGIN, ("replace_geometry", str(apple.item_id)), COMMIT]


def test_a_destroyed_controller_is_never_called_again(canvas: CanvasView, qtbot) -> None:
    """Gate G9, third part — through the real clock and the real scene."""
    rig = Rig(canvas, qtbot, location=dict(BERLIN))
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    sip.delete(rig.controller)
    rig.clock.set_date(date(2027, 1, 1))          # would raise from inside the dead slot
    rig.clock.set_time_of_day(time(9, 0))
    bed.setPos(bed.pos() + QPointF(5.0, 0.0))
    rig.qtbot.wait(50)
    assert rig.recorder.ops() == []
    assert rig.clock.date_changed.receiver_count() == 0
    assert rig.clock.instant_changed.receiver_count() == 0


# ── a new document ───────────────────────────────────────────────────────────


def test_a_document_change_is_a_plain_apply_and_announces_the_document_once(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    cleared: list[int] = []
    monkeypatch.setattr(plants, "clear_shape_cache", lambda: cleared.append(1))
    shown: list[int] = []
    rig.controller.document_shown.connect(lambda: shown.append(1))
    old = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    assert shown == [1], "the first pass shows a document"

    rig.scene.clear()                      # what "new plan" and "open" do
    rig.scene.resize_canvas(2000.0, 1000.0)
    new = rig.bed(100.0, 100.0)
    rig.controller.document_changed()
    calls = rig.settle()
    assert cleared == [1]
    assert ("clear", None) not in calls, "a document change is not a reset"
    assert calls == [BEGIN, ("remove", str(old.item_id)), ("add", str(new.item_id)), GROUND, COMMIT]
    assert shown == [1, 1]
    rig.commands.execute(MoveItemsCommand([new], QPointF(10.0, 0.0)))
    rig.settle()
    assert shown == [1, 1], "an edit never announces a document"
    assert rig.controller.plan_bounds() == Bounds.of_plan(2000.0, 1000.0, 40.0)


def test_a_document_changed_while_hidden_is_announced_when_3d_comes_back(rig: Rig) -> None:
    shown: list[int] = []
    rig.controller.document_shown.connect(lambda: shown.append(1))
    rig.controller.set_active(True)
    rig.settle()
    rig.controller.set_active(False)
    rig.controller.document_changed()
    rig.controller.document_changed()      # opened twice while hidden: still one document
    rig.settle()
    assert shown == [1]
    rig.controller.set_active(True)
    rig.settle()
    assert shown == [1, 1]


# ── failures: contained, logged, recovered ───────────────────────────────────


class FailingSink:
    """A sink that raises on a chosen call — the engine failing in mid-transaction."""

    def __init__(self) -> None:
        self.inner = RecordingSink()
        self.fail_on: str | None = None
        self.failures_left = 0

    def __getattr__(self, name: str) -> Any:
        target = getattr(self.inner, name)
        if not callable(target) or name != self.fail_on:
            return target

        def call(*arguments: Any, **options: Any) -> Any:
            if self.failures_left > 0:
                self.failures_left -= 1
                raise RuntimeError(f"the engine refused {name}()")
            return target(*arguments, **options)

        return call


def test_a_sink_that_fails_is_reset_and_reapplied_and_nothing_reaches_the_event_loop(
        canvas: CanvasView, qtbot, caplog: pytest.LogCaptureFixture) -> None:
    sink = FailingSink()
    rig = Rig(canvas, qtbot, sink=sink)
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()

    sink.fail_on, sink.failures_left = "update_transform", 1
    with caplog.at_level(logging.ERROR):
        rig.commands.execute(MoveItemsCommand([bed], QPointF(50.0, 0.0)))
        calls = rig.settle()
    assert rig.controller.recovery_count == 1
    assert ("clear", None) in calls                       # the recovery goes through the protocol
    assert calls[-4:] == [("add", str(bed.item_id)), GROUND, SUN, COMMIT]
    assert rig.reports[-1].recovered is True
    assert rig.controller.last_error is None and rig.controller.sync.poisoned is False
    assert any("resetting the 3D scene" in record.message for record in caplog.records)
    rig.assert_equals_a_from_scratch_apply()


def test_a_sink_that_keeps_failing_is_given_up_for_this_pass_and_tried_again_later(
        canvas: CanvasView, qtbot) -> None:
    sink = FailingSink()
    rig = Rig(canvas, qtbot, sink=sink)
    errors: list[str] = []
    rig.controller.failed.connect(errors.append)
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()

    sink.fail_on, sink.failures_left = "begin", 2          # the pass and its recovery
    rig.commands.execute(MoveItemsCommand([bed], QPointF(50.0, 0.0)))
    rig.settle()
    assert len(errors) == 1 and "could not be rebuilt" in errors[0]
    assert rig.controller.last_error == errors[0]
    assert rig.controller.dirty is True, "nothing was lost: the next change tries again"

    rig.commands.execute(MoveItemsCommand([bed], QPointF(1.0, 0.0)))   # the engine is back
    rig.settle()
    assert rig.controller.last_error is None
    rig.assert_equals_a_from_scratch_apply()


def test_a_poisoned_sync_is_recovered_by_the_next_pass(
        rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    with pytest.raises(SinkProtocolError):                 # somebody broke the protocol …
        rig.controller.sync._transact(lambda: rig.recorder.remove("nobody"))
    assert rig.controller.sync.poisoned is True
    rig.recorder.clear_calls()
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        rig.commands.execute(MoveItemsCommand([bed], QPointF(5.0, 0.0)))
        calls = rig.settle()
    assert rig.controller.recovery_count == 1 and calls[0] == ("clear", None)
    assert rig.controller.sync.poisoned is False
    rig.assert_equals_a_from_scratch_apply()
    # the pass does not run into the sync's refusal first: it rebuilds, and — nobody
    # having logged the failed call — says once why
    lines, _debug = _own_records(caplog)
    assert lines == ["3D sync: the 3D scene was left in an unknown state by a failed engine "
                     "call; rebuilding it"]
    assert rig.reports[-1].recovered is True


def test_reset_after_the_engine_scene_was_rebuilt_sends_everything_again(rig: Rig) -> None:
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    rig.controller.reset()
    calls = rig.settle()
    assert calls == [("clear", None), BEGIN, ("add", str(bed.item_id)), GROUND, SUN, COMMIT]


# ── what 3D could not build ──────────────────────────────────────────────────


def test_an_item_the_record_layer_refuses_is_reported_and_fixing_it_clears_the_report(
        rig: Rig) -> None:
    changed: list[int] = []
    rig.controller.problems_changed.connect(lambda: changed.append(rig.controller.problem_count))
    good, bad = rig.bed(), rig.bed(1500.0, 1500.0)
    bad.metadata[METADATA_KEY] = float("inf")              # a height nobody can build
    rig.controller.set_active(True)
    rig.settle()
    assert [(s.item_id, s.kind, s.reason) for s in rig.controller.skipped] == [
        (str(bad.item_id), "RAISED_BED", SkipReason.OUT_OF_RANGE)]
    assert rig.controller.problem_count == 1 and changed == [1]
    assert rig.recorder.item_ids() == (str(good.item_id),), "the rest of the plan is shown"

    rig.commands.execute(MoveItemsCommand([good], QPointF(5.0, 0.0)))
    rig.settle()
    assert changed == [1], "the same report again is not news"

    bad.metadata[METADATA_KEY] = 80.0                      # the user fixes it
    rig.commands.stack_changed.emit()
    rig.settle()
    assert rig.controller.skipped == () and changed == [1, 0]
    assert set(rig.recorder.item_ids()) == {str(good.item_id), str(bad.item_id)}


def test_a_builder_that_fails_is_reported_too(canvas: CanvasView, qtbot) -> None:
    registry = production_registry()

    def broken(record: Record) -> tuple:
        raise ValueError(f"cannot build {record.kind}")

    registry.register("RAISED_BED", broken, replace=True)
    rig = Rig(canvas, qtbot, registry=registry)
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    failure = rig.controller.failures[str(bed.item_id)]
    assert (failure.kind, failure.error_type) == ("RAISED_BED", "ValueError")
    assert rig.controller.problem_count == 1
    assert rig.recorder.item(str(bed.item_id)).parts == ()   # shown without a solid


# ── the ground seam (L1.5) ───────────────────────────────────────────────────


def test_the_ground_stage_sees_both_snapshots_and_its_ground_rides_the_transaction(
        rig: Rig) -> None:
    seen: list[tuple[list[str], list[str], float, float]] = []

    def stage(previous: Any, records: Any, width: float, depth: float) -> GroundSpec:
        seen.append((list(previous), list(records), width, depth))
        return GroundSpec(width / 2.0, depth / 2.0)        # anything a baker decides

    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    rig.controller.set_ground_stage(stage)
    assert rig.settle() == [BEGIN, GROUND, COMMIT]
    assert seen == [([str(bed.item_id)], [str(bed.item_id)], 5000.0, 3000.0)]
    assert rig.recorder.ground == GroundSpec(2500.0, 1500.0)

    second = rig.bed(2000.0, 2000.0)
    assert rig.settle() == [BEGIN, ("add", str(second.item_id)), COMMIT]
    # the pass that added it was handed "what the engine holds" and "what it will hold"
    both = [str(bed.item_id), str(second.item_id)]
    assert ([str(bed.item_id)], both, 5000.0, 3000.0) in seen
    assert seen[-1][1] == both

    rig.controller.set_ground_stage(None)
    assert rig.settle() == [BEGIN, GROUND, COMMIT]
    assert rig.recorder.ground == GroundSpec(5000.0, 3000.0)
    assert plain_ground({}, {}, 12.0, 34.0) == GroundSpec(12.0, 34.0)


def test_a_ground_stage_that_raises_does_not_blank_the_garden(
        rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    def broken(*_arguments: Any) -> GroundSpec:
        raise RuntimeError("the baker fell over")

    bed = rig.bed()
    rig.controller.set_ground_stage(broken)
    rig.controller.set_active(True)
    with caplog.at_level(logging.ERROR):
        calls = rig.settle()
    assert calls == [BEGIN, ("add", str(bed.item_id)), GROUND, SUN, COMMIT]
    assert rig.recorder.ground == GroundSpec(5000.0, 3000.0)
    assert any("ground stage failed" in record.message for record in caplog.records)
    assert rig.controller.recovery_count == 0


def test_after_a_reset_the_ground_stage_is_told_that_nothing_is_in_the_engine(
        canvas: CanvasView, qtbot) -> None:
    sink = FailingSink()
    rig = Rig(canvas, qtbot, sink=sink)
    previous_seen: list[list[str]] = []

    def stage(previous: Any, _records: Any, width: float, depth: float) -> GroundSpec:
        previous_seen.append(list(previous))
        return GroundSpec(width, depth)

    bed = rig.bed()
    rig.controller.set_ground_stage(stage)
    rig.controller.set_active(True)
    rig.settle()
    sink.fail_on, sink.failures_left = "update_transform", 1
    rig.commands.execute(MoveItemsCommand([bed], QPointF(50.0, 0.0)))
    rig.settle()
    assert previous_seen[-2:] == [[str(bed.item_id)], []]


def test_a_ground_made_in_slices_asks_for_the_next_pass_from_inside_the_pass(rig: Rig) -> None:
    """A bake may stop at a time budget and leave tiles for later (the ground story's
    contract): the pass that hands the ground to the engine can be asked for again from
    INSIDE the pass — nothing here builds on "one pass paints the whole ground". Each
    slice is a pass of its own turn of the event loop, the ground rides its
    transaction, no geometry is sent again, and the asking ends when the work does."""
    slices_left = [4]
    widths: list[float] = []

    def stage(previous: Any, records: Any, width: float, depth: float) -> GroundSpec:
        if slices_left[0] > 0:
            slices_left[0] -= 1
            rig.controller.mark_dirty()                    # "I have work left"
        painted = 4 - slices_left[0]
        widths.append(float(painted))
        assert list(previous) == list(records) or painted == 1, "the plan did not change between slices"
        return GroundSpec(width + painted, depth)          # the ground as far as it is painted

    bed = rig.bed()
    rig.controller.set_ground_stage(stage)
    rig.controller.set_active(True)
    turns: list[int] = []
    rig.controller.applied.connect(lambda _report: turns.append(rig.controller.snapshot_count))
    rig.qtbot.waitUntil(lambda: slices_left[0] == 0 and not rig.controller.dirty, timeout=3000)
    calls = rig.settle()
    assert widths == [1.0, 2.0, 3.0, 4.0, 4.0], "four slices, then one pass that asked for no more"
    assert turns == [1, 2, 3, 4, 5], "one pass per slice, each a pass of its own"
    assert calls == [BEGIN, ("add", str(bed.item_id)), GROUND, SUN, COMMIT,
                     BEGIN, GROUND, COMMIT, BEGIN, GROUND, COMMIT, BEGIN, GROUND, COMMIT]
    assert rig.recorder.ground == GroundSpec(5004.0, 3000.0)
    assert rig.settle() == [], "and then it is quiet: nobody is asked for ever"


# ── security add-on: a failure never writes a log line of its own (§8.11) ────

FORGED = "\n2026-10-12 00:00:00 ERROR root: FORGED LINE"
LOGGER = "open_garden_planner.ui.view3d.sync_controller"


def _own_records(caplog: pytest.LogCaptureFixture) -> tuple[list[str], list[logging.LogRecord]]:
    """The controller's records: the ones the log file keeps (WARNING and above) as
    their messages, each checked to be ONE line without a traceback; and the DEBUG ones."""
    ours = [record for record in caplog.records if record.name == LOGGER]
    kept = [record for record in ours if record.levelno >= logging.WARNING]
    for record in kept:
        assert record.exc_info is None and record.exc_text is None, record.getMessage()
        assert len(record.getMessage().splitlines()) == 1, record.getMessage()
    return ([record.getMessage() for record in kept],
            [record for record in ours if record.levelno == logging.DEBUG])


def test_a_plan_that_cannot_be_read_is_one_log_line(
        rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def unreadable(*_arguments: Any, **_options: Any) -> dict:
        raise RuntimeError("item 'x'" + FORGED)

    monkeypatch.setattr(sync_controller, "snapshot_records", unreadable)
    errors: list[str] = []
    rig.controller.failed.connect(errors.append)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        rig.controller.set_active(True)
        rig.settle()
    lines, debug = _own_records(caplog)
    assert lines == ["3D sync: the plan could not be read for the 3D view (RuntimeError: "
                     "item 'x' 2026-10-12 00:00:00 ERROR root: FORGED LINE)"]
    assert len(debug) == 1 and debug[0].exc_info is not None, "the traceback: at DEBUG only"
    # what travels on (a signal, a property) is one harmless line as well
    assert errors == [rig.controller.last_error] and len(errors[0].splitlines()) == 1


@pytest.mark.parametrize(("fail_on", "failures", "expected"), [
    ("update_transform", 1, ["a pass failed; resetting the 3D scene and applying again"]),
    ("begin", 2, ["a pass failed; resetting the 3D scene and applying again",
                  "the 3D scene could not be rebuilt"]),
])
def test_an_engine_error_that_quotes_the_plan_is_one_log_line_per_event(
        canvas: CanvasView, qtbot, caplog: pytest.LogCaptureFixture, fail_on: str,
        failures: int, expected: list[str]) -> None:
    """A sink error names the item it failed on — an id read from the plan file."""

    class Quoting(FailingSink):
        def __getattr__(self, name: str) -> Any:
            call = super().__getattr__(name)
            if name != self.fail_on or not callable(call):
                return call

            def raising(*arguments: Any, **options: Any) -> Any:
                try:
                    return call(*arguments, **options)
                except RuntimeError as error:
                    raise RuntimeError(f"{error} for item 'x'{FORGED}\N{LINE SEPARATOR}and more") from None

            return raising

    sink = Quoting()
    rig = Rig(canvas, qtbot, sink=sink)
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    sink.fail_on, sink.failures_left = fail_on, failures
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        rig.commands.execute(MoveItemsCommand([bed], QPointF(50.0, 0.0)))
        rig.settle()
    lines, debug = _own_records(caplog)
    assert [line.split(" (RuntimeError: ")[0] for line in lines] == [
        f"3D sync: {what}" for what in expected]
    assert all(line.endswith("FORGED LINE and more)") for line in lines)
    assert len(debug) == len(expected) and all(record.exc_info for record in debug)


def test_a_ground_stage_or_a_location_that_quotes_the_plan_is_one_log_line(
        canvas: CanvasView, qtbot, caplog: pytest.LogCaptureFixture) -> None:
    def broken(*_arguments: Any) -> GroundSpec:
        raise RuntimeError("tile of 'x'" + FORGED)

    rig = Rig(canvas, qtbot,
              location={"latitude": "52" + FORGED + "x" * 100_000, "longitude": 13.4})
    rig.controller.set_ground_stage(broken)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        rig.controller.set_active(True)
        rig.settle()
    lines, _debug = _own_records(caplog)
    assert len(lines) == 2
    assert any(line.startswith("3D sync: no sun for location {'latitude': '52")
               for line in lines)
    assert max(map(len, lines)) < 500, "a value of any size is one capped line"
    assert any(line.startswith("3D sync: the ground stage failed") for line in lines)
    assert rig.recorder.sun == NO_LOCATION_SUN


def test_a_failing_build_adds_no_record_of_this_storys_own(
        canvas: CanvasView, qtbot, caplog: pytest.LogCaptureFixture) -> None:
    """A builder that fails is contained and logged by the scene contract
    (``core/scene3d/sync.py``), not here: this story's modules add nothing to the log
    for it — the user is told through the problems list, whose texts are made
    harmless on the way (``test_view3d_workspace_widget.py``)."""
    registry = production_registry()

    def broken(record: Record) -> tuple:
        raise ValueError(f"cannot build {record.name}{FORGED}")

    registry.register("RAISED_BED", broken, replace=True)
    rig = Rig(canvas, qtbot, registry=registry)
    bed = rig.bed()
    bed.name = "North bed" + FORGED
    with caplog.at_level(logging.DEBUG):
        rig.controller.set_active(True)
        rig.settle()
    assert rig.controller.problem_count == 1
    ours = [record for record in caplog.records
            if record.name.startswith("open_garden_planner.ui.view3d.")
            and not record.name.endswith(".snapshot")]
    assert ours == []


def test_shutdown_stops_everything(rig: Rig) -> None:
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    rig.controller.shutdown()
    rig.commands.execute(MoveItemsCommand([bed], QPointF(50.0, 0.0)))
    rig.clock.set_date(date(2027, 3, 3))
    assert rig.settle() == []
    assert rig.controller.active is False


# ── what a pass retired in the engine ────────────────────────────────────────


def test_a_pass_says_how_many_items_lost_their_models(rig: Rig) -> None:
    """``TickReport.retired``: the items whose engine Models this pass destroyed — a
    removed item and one whose geometry was replaced. Qt keeps graphics state for
    every Model it once drew until it is told to let go (ADR-065); the workspace
    counts these to know when."""
    bed = rig.bed()
    other = rig.bed(1200.0, 900.0)
    rig.controller.set_active(True)
    rig.settle()
    assert rig.reports[-1].retired == 0, "a first pass only adds"

    rig.commands.execute(MoveItemsCommand([bed], QPointF(40.0, 0.0)))
    rig.settle()
    assert rig.reports[-1].retired == 0, "a move keeps the Model"
    rig.commands.execute(recolour_fill(bed, QColor(10, 200, 30)))
    rig.settle()
    assert rig.reports[-1].retired == 0, "a recolour keeps the Model"

    old, new = build_rect_resize(bed, 500.0, 120.0, keep_center=True)
    rig.commands.execute(ResizeItemCommand(bed, old, new, apply_rect_like_geometry))
    rig.settle()
    assert rig.reports[-1].retired == 1, "new geometry is a new Model: the old one is destroyed"

    rig.commands.execute(DeleteItemsCommand(rig.scene, [bed, other]))
    rig.settle()
    assert rig.reports[-1].retired == 2

    rig.clock.set_time_of_day(time(9, 0))
    rig.settle()
    assert rig.reports[-1].snapshot is False and rig.reports[-1].retired == 0


def test_a_reset_and_a_recovery_count_everything_they_destroyed(canvas: CanvasView, qtbot) -> None:
    sink = FailingSink()
    rig = Rig(canvas, qtbot, sink=sink)
    bed = rig.bed()
    rig.bed(1200.0, 900.0)
    rig.bed(2200.0, 900.0)
    rig.controller.set_active(True)
    rig.settle()

    rig.controller.reset()                 # the whole engine scene goes: three items
    rig.settle()
    assert rig.reports[-1].retired == 3

    sink.fail_on, sink.failures_left = "update_transform", 1
    rig.commands.execute(MoveItemsCommand([bed], QPointF(50.0, 0.0)))
    rig.settle()
    assert rig.reports[-1].recovered is True
    assert rig.reports[-1].retired == 3, "the recovery cleared the sink: every Model was destroyed"

    rig.commands.execute(MoveItemsCommand([bed], QPointF(5.0, 0.0)))
    rig.settle()
    assert rig.reports[-1].retired == 0, "counted once"


def test_what_3d_remembers_of_a_plan_goes_with_the_plan_and_with_the_view(
        rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plant builder's shape cache and the record layer's outline memories are per
    plan: dropped on a document change AND when the 3D view closes — a closed view
    must not keep a plan's worth of memory alive."""
    cleared: list[str] = []
    monkeypatch.setattr(plants, "clear_shape_cache", lambda: cleared.append("shapes"))
    monkeypatch.setattr(snapshot_module, "clear_outline_cache", lambda: cleared.append("outlines"))
    bed = rig.bed()
    rig.controller.set_active(True)
    rig.settle()
    rig.commands.execute(MoveItemsCommand([bed], QPointF(5.0, 0.0)))
    rig.clock.set_date(date(2026, 9, 9))
    rig.settle()
    assert cleared == [], "an edit session and a date change drop nothing"
    rig.controller.document_changed()
    assert cleared == ["shapes", "outlines"]
    rig.settle()
    rig.controller.shutdown()
    assert cleared == ["shapes", "outlines"] * 2


def _outlines_held() -> int:
    """How many outlines the record layer remembers right now — every ring-keyed memory
    there is (the contract story's own instrument, ``cache_info().entries``)."""
    return sum(memory.cache_info().entries for memory in polygon_module._memories)


def _hedge(rig: Rig, east: float, width: float = 300.0) -> PolygonItem:
    """A drawn hedge. Outlines are remembered by SHAPE: another width, another entry."""
    item = PolygonItem(
        [QPointF(east, 200.0), QPointF(east + width, 220.0), QPointF(east + width + 20.0, 520.0),
         QPointF(east + 40.0, 560.0)],
        object_type=ObjectType.HEDGE_POLYGON, layer_id=rig.scene.active_layer.id)
    rig.commands.execute(CreateItemCommand(rig.scene, item, "hedge"))
    return item


def test_the_old_plans_outlines_are_gone_with_the_plan_and_with_the_view(rig: Rig) -> None:
    """The real memories, not a stand-in. What a snapshot asks for stays remembered
    while snapshots go on — a plan that is gone would stay until two more snapshots
    had run, and with the view closed none does (about 30 MB for a large plan,
    measured by the contract story). After a document change the old plan's entries
    are gone AT ONCE, and the new plan's first snapshot is a first tick."""
    snapshot_module.clear_outline_cache()
    for index in range(3):
        _hedge(rig, 300.0 + 600.0 * index, 300.0 + 45.0 * index)
    rig.controller.set_active(True)
    rig.settle()
    three = _outlines_held()
    assert three >= 3, "three drawn outlines of three shapes are remembered"
    snapshots = rig.controller.snapshot_count

    rig.scene.clear()                      # a new plan …
    rig.controller.document_changed()
    assert _outlines_held() == 0, "… and not one outline of the old one is kept"
    _hedge(rig, 900.0, 512.0)
    rig.settle()
    assert rig.controller.snapshot_count == snapshots + 1
    one = _outlines_held()
    assert one * 3 == three, "the first snapshot of the new plan judged and cut ITS outline afresh"

    rig.controller.shutdown()              # the 3D view closes
    assert _outlines_held() == 0
