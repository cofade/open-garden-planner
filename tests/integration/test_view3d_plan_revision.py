"""What starts a 3D pass in the real main window — and what does not (L1.3, ADR-060 decision 5).

The first delivery wired ``QGraphicsScene.changed`` straight to "the plan is dirty":
every REPAINT of the canvas was a whole-plan snapshot. Counted by the reviewer in the
real ``GardenPlannerApp``, Split, exact numbers from the recording sink: 10 time
changes with the sun simulation on = 10 snapshots; 20 preview mouse moves of the
polygon tool, nothing created = 20; three selections and a clear = 4 — and "Animate"
is a timer. A preview mouse-move cost 6.7 ms in Split against 1.0 ms in Plan on the
small bench plan, 18.3 against 0.7 ms on the large one.

Now there are two layers (``ui/view3d/sync_controller.py``): the scene's PLAN
REVISION starts a pass at once, and a repaint that no announcement explains starts
one quiet timer, after which ONE reconciliation pass runs — which finds nothing
unless an edit path forgot to announce itself, and counts it if it did.

Here, in a real ``GardenPlannerApp`` with the engine replaced at the documented seam
(a recording host and a ``RecordingSink``; nothing is rendered):

- the GATES: a time sweep with the sun simulation ON, twenty preview moves, three
  selections and a clear, a hover over items, "Animate" running for two seconds —
  each ZERO snapshots while it happens and at most ONE after the quiet time, and that
  one finds nothing;
- the ANNOUNCEMENT MATRIX: every edit path of the §8.10 workflow, undo / redo, layer
  visibility / lock / opacity, arrange, group / ungroup, paste, duplicate, a handle
  drag, an Agent API write, the Properties-panel edits that write ``metadata``
  directly — each moves the plan revision, each is in 3D by a pass it announced, and
  the net never finds anything (``unannounced_changes == 0``);
- the COST: a preview mouse-move turn in Split against Plan, on both bench plans,
  with a bound on the ratio;
- the net itself in the real window: a write nobody announced is in 3D after the
  quiet time, and is counted.
"""

from __future__ import annotations

import statistics
import time as stopwatch
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGraphicsSceneMouseEvent,
    QSpinBox,
)

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core import container_model
from open_garden_planner.core.commands import (
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
    ResizeItemCommand,
    RotateItemCommand,
)
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import RecordingSink, SceneSync
from open_garden_planner.core.stacking import ArrangeMode
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rect_like_geometry,
    apply_rotation,
    build_rect_resize,
)
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.resize_handle import ResizeHandle
from open_garden_planner.ui.view3d import sync_controller
from open_garden_planner.ui.view3d.snapshot import snapshot_records
from open_garden_planner.ui.view3d.sync_controller import TickReport
from open_garden_planner.ui.view3d.workspace import WorkspaceMode
from open_garden_planner.ui.widgets import sun_sim_toolbar
from tests.integration.test_scene3d_plants import drop
from tests.integration.test_scene3d_snapshot import _recolour as recolour_fill
from tests.integration.test_view3d_workspace import Engines, build_app3d

REPO = Path(__file__).resolve().parents[2]
PLANS = REPO / "tests" / "fixtures" / "plans"
BERLIN = {"latitude": 52.52, "longitude": 13.405}
PLAN, VIEW3D, SPLIT = WorkspaceMode.PLAN, WorkspaceMode.VIEW3D, WorkspaceMode.SPLIT
#: What this run measured — printed with the module, for the report.
MEASURED: dict[str, Any] = {}


@pytest.fixture()
def app3d(qtbot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[GardenPlannerApp, Engines]:
    return build_app3d(qtbot, monkeypatch, tmp_path)


@pytest.fixture(scope="module", autouse=True)
def _report() -> Any:
    yield
    if MEASURED:
        import json

        print(f"\n[plan revision] measured:\n{json.dumps(MEASURED, indent=1)}")  # noqa: T201


class Live:
    """The real window with a small garden on it and the 3D pipeline running."""

    def __init__(self, app3d: tuple[GardenPlannerApp, Engines], qtbot: Any, *,
                 garden: bool = True) -> None:
        self.window, self.engines = app3d
        self.qtbot = qtbot
        self.workspace = self.window._workspace
        self.canvas = self.window.canvas_view
        self.scene = self.window.canvas_scene
        self.commands = self.canvas.command_manager
        self.reports: list[TickReport] = []
        self.repaints: list[float] = []
        self.scene.changed.connect(lambda *_regions: self.repaints.append(stopwatch.monotonic()))
        if not garden:
            return   # the caller opens a plan of its own
        self.window._project_manager.set_location(dict(BERLIN))
        self.window._sim_clock.set_datetime(datetime(2026, 6, 21, 8, 0))
        self.bed = self.add(RectangleItem(400.0, 300.0, 300.0, 200.0,
                                          object_type=ObjectType.RAISED_BED,
                                          layer_id=self.scene.active_layer.id), "bed")
        self.shed = self.add(RectangleItem(1800.0, 1400.0, 400.0, 300.0,
                                           object_type=ObjectType.GARAGE_SHED,
                                           layer_id=self.scene.active_layer.id), "shed")
        self.apple = drop(self.canvas, "TREE:species=apple tree", QPointF(2800.0, 900.0))
        self.apple.metadata["plant_instance"] = {
            "planting_date": "2024-04-01", "current_height_cm": 180.0, "current_spread_cm": 120.0}

    def add(self, item: Any, label: str) -> Any:
        self.commands.execute(CreateItemCommand(self.scene, item, label))
        return item

    @property
    def controller(self) -> Any:
        return self.workspace.controller

    def start(self, mode: WorkspaceMode = SPLIT) -> None:
        self.workspace.set_mode(mode)
        self.qtbot.waitUntil(lambda: self.controller is not None
                             and self.controller.apply_count >= 1, timeout=30000)
        self.controller.applied.connect(self.reports.append)
        self.quiet()

    def quiet(self, stable_turns: int = 10, limit_turns: int = 800) -> None:
        """Wait until the pipeline has nothing on its way — the net's quiet time
        included — and stays so for ``stable_turns`` waits of 25 ms in a row (the 2D
        side's own debounced work may repaint once more and start the quiet timer
        again). A condition, not a measurement: no clock is read here, and nothing
        about how long it took is asserted (ADR-058)."""
        idle_turns = 0
        for _turn in range(limit_turns):
            self.qtbot.wait(25)
            idle_turns = idle_turns + 1 if self.controller.idle else 0
            if idle_turns >= stable_turns:
                return
        raise AssertionError("the 3D pipeline never became quiet")

    def counts(self) -> tuple[int, int, int]:
        controller = self.controller
        return controller.snapshot_count, controller.reconcile_count, controller.unannounced_changes

    def assert_3d_is_the_plan(self, what: str = "") -> None:
        """What the engine was told equals a from-scratch apply of the plan as it is —
        with its selection ring (L1.8: the sink holds the ring of what is selected)."""
        from open_garden_planner.ui.view3d.selection_bridge import selected_record_ids

        sync = self.controller.sync
        fresh_sink = RecordingSink()
        fresh = SceneSync(fresh_sink, sync.registry)
        fresh.select(selected_record_ids(self.scene))
        fresh.apply(snapshot_records(self.scene, self.window._sim_clock.plan_date),
                    sun=sync.sun, ground=sync.ground)
        assert self.engines.sink.state() == fresh_sink.state() == sync.expected_state(), what


def _turns(count: int = 3) -> None:
    for _ in range(count):
        QApplication.processEvents()


# ── the gates: a repaint is not a snapshot ───────────────────────────────────


def _time_sweep_with_the_sun_simulation_on(live: Live, mouse_event: MagicMock) -> dict[str, Any]:
    window = live.window
    lights = live.controller.light_count
    slider = window._sun_toolbar._slider
    for minutes in range(9 * 60, 9 * 60 + 10 * 45, 45):    # ten times of day, 09:00 … 15:45
        slider.setValue(minutes)
        live.qtbot.wait(30)
    return {"light_passes": live.controller.light_count - lights}


def _twenty_preview_moves(live: Live, mouse_event: MagicMock) -> dict[str, Any]:
    canvas = live.canvas
    canvas.set_active_tool(ToolType.POLYGON)
    tool = canvas.tool_manager.active_tool
    items_before = len(live.scene.items())
    tool.mouse_press(mouse_event, QPointF(3200.0, 2000.0))
    tool.mouse_release(mouse_event, QPointF(3200.0, 2000.0))
    for step in range(20):
        tool.mouse_move(mouse_event, QPointF(3220.0 + 12.0 * step, 2010.0 + 7.0 * step))
        _turns()
    garden_items = [item for item in live.scene.items() if hasattr(item, "item_id")]
    assert len(garden_items) == 3, "nothing was created: three items, as before"
    assert len(live.scene.items()) > items_before, "the preview IS in the scene"
    canvas.set_active_tool(ToolType.SELECT)
    return {}


def _three_selections_and_a_clear(live: Live, mouse_event: MagicMock) -> dict[str, Any]:
    for item in (live.bed, live.shed, live.apple):
        live.scene.clearSelection()
        item.setSelected(True)
        _turns()
        live.qtbot.wait(20)
    live.scene.clearSelection()
    _turns()
    return {}


def _a_hover_over_items(live: Live, mouse_event: MagicMock) -> dict[str, Any]:
    """A real hover, through the view's event pipeline: onto each handle of the
    selected bed (it lights up — proof that the hover arrived) and off it again."""
    canvas, viewport = live.canvas, live.canvas.viewport()
    canvas.set_zoom(1.0)
    live.bed.setSelected(True)
    _turns()
    handles = [child for child in live.bed.childItems() if isinstance(child, ResizeHandle)]
    assert len(handles) >= 4
    lit = 0
    for handle in handles[:4] * 2:
        canvas.centerOn(handle.scenePos())      # scrolls the view; the scene is untouched
        _turns()
        spot = canvas.mapFromScene(handle.scenePos())
        idle = handle.brush().color().name()
        QTest.mouseMove(viewport, spot + QPoint(30, 30))    # approach, then enter
        QTest.mouseMove(viewport, spot)
        _turns()
        lit += handle.brush().color().name() != idle
        QTest.mouseMove(viewport, spot + QPoint(30, 30))    # … and off it
        _turns()
        live.qtbot.wait(10)
    assert lit >= 6, f"the mouse did hover: {lit} of 8 handles lit up under it"
    live.scene.clearSelection()
    return {}


def _animate_for_two_seconds(live: Live, mouse_event: MagicMock) -> dict[str, Any]:
    window = live.window
    button = window._sun_toolbar._animate_button
    lights = live.controller.light_count
    button.setChecked(True)
    live.qtbot.wait(2000)
    button.setChecked(False)
    return {"light_passes": live.controller.light_count - lights}


ACTIVITIES: dict[str, tuple[Callable[[Live, MagicMock], dict[str, Any]], bool, int]] = {
    # name: (what the user does, whether the sun simulation is on, and how many times at
    # least the scene must report a repaint for it — ``QGraphicsScene.changed``, the signal
    # that used to start a snapshot each time. Qt reports the handles' hover highlights
    # of one run of mouse moves as ONE change; that they lit up is asserted on its own.)
    "a_time_sweep_with_the_sun_simulation_on": (_time_sweep_with_the_sun_simulation_on, True, 10),
    "twenty_preview_moves": (_twenty_preview_moves, False, 20),
    "three_selections_and_a_clear": (_three_selections_and_a_clear, False, 4),
    "a_hover_over_items": (_a_hover_over_items, False, 1),
    "animate_for_two_seconds": (_animate_for_two_seconds, True, 5),
}


def _live_for(app3d: Any, qtbot: Any, activity: str) -> Live:
    _act, sun_on, _least = ACTIVITIES[activity]
    live = Live(app3d, qtbot)
    if sun_on:
        assert live.window._sun_toolbar.isVisible()
    live.start()
    return live


@pytest.mark.parametrize("activity", list(ACTIVITIES))
def test_a_repaint_in_the_real_window_never_starts_a_pass_of_its_own(
        app3d, qtbot, mouse_event, activity: str) -> None:
    """The gates in the form that holds on any machine under any load — counts and
    orderings only (the default tier runs beside other workers, ADR-058). Whatever
    the activity repaints: NO pass is started for it (every pass from its first
    repaint to the quiet after it is the net's), every one of the net's passes finds
    nothing, and the engine holds the plan. How MANY net passes run depends on how
    long this machine left the canvas still in between: the strict count — zero
    while it happens, at most one after — is the ``perf`` twin below, on a quiet
    runner."""
    act, _sun_on, least_repaints = ACTIVITIES[activity]
    live = _live_for(app3d, qtbot, activity)
    controller = live.controller
    live.quiet()
    snapshots, reconciled, _unannounced = live.counts()
    seen, first_repaint = len(live.reports), len(live.repaints)
    extra = act(live, mouse_event)
    live.quiet()
    repaints = len(live.repaints) - first_repaint
    assert repaints >= least_repaints, (
        f"{activity}: the scene reported {repaints} repaints, expected {least_repaints} or more")
    passes = [report for report in live.reports[seen:] if report.snapshot]
    assert [report for report in passes if not report.reconciled] == [], (
        f"{activity}: a repaint started a pass of its own")
    assert all(report.changes.is_empty for report in passes), f"{activity}: the net found something"
    assert controller.snapshot_count - snapshots == len(passes)
    assert controller.reconcile_count - reconciled == len(passes)
    assert controller.unannounced_changes == 0
    if "light_passes" in extra:
        assert extra["light_passes"] >= 5, "the light did follow the time"
    live.assert_3d_is_the_plan(activity)
    MEASURED.setdefault("gates (default tier)", {})[activity] = {
        "repaints": repaints, "net_passes": len(passes), **extra}


@pytest.mark.perf
@pytest.mark.parametrize("activity", list(ACTIVITIES))
def test_a_repaint_in_the_real_window_takes_no_snapshot_while_it_happens(
        app3d, qtbot, mouse_event, activity: str) -> None:
    """The gates, strictly — on the quiet runner (``perf``: this reads the wall clock).
    With the app's own quiet time (``NET_QUIET_MS``): ZERO snapshots while the
    activity runs, at most ONE after the quiet time — and that one finds nothing.
    Whether the scene really was repainted, and never quiet for as long as the quiet
    time in between, is measured, not assumed: a run in which this machine let a gap
    that long open up is repeated (three attempts)."""
    act, _sun_on, least_repaints = ACTIVITIES[activity]
    live = _live_for(app3d, qtbot, activity)
    controller = live.controller
    quiet_s = sync_controller.NET_QUIET_MS / 1000.0
    for attempt in range(3):
        live.quiet()
        snapshots, reconciled, _unannounced = live.counts()
        first_repaint = len(live.repaints)
        started = stopwatch.monotonic()
        extra = act(live, mouse_event)
        during = controller.snapshot_count - snapshots
        stamps = [started, *live.repaints[first_repaint:], stopwatch.monotonic()]
        longest_gap = max(later - earlier for earlier, later in zip(stamps, stamps[1:], strict=False))
        if longest_gap < quiet_s * 0.9 or attempt == 2:
            break
    repaints = len(live.repaints) - first_repaint
    assert repaints >= least_repaints, (
        f"{activity}: the scene reported {repaints} repaints, expected {least_repaints} or more")
    assert longest_gap < quiet_s, (
        f"{activity}: the canvas was quiet for {longest_gap:.2f} s inside the activity on this "
        "machine, three times — the gate was not exercised")
    assert during == 0, f"{activity}: {during} snapshot(s) while it happened"
    live.quiet()
    after = controller.snapshot_count - snapshots
    assert after <= 1, f"{activity}: {after} snapshots after the quiet time"
    assert controller.reconcile_count - reconciled == after, "… and it was the net's pass"
    if after:
        report = live.reports[-1]
        assert report.reconciled is True and report.changes.is_empty, "it found nothing"
    assert controller.unannounced_changes == 0
    if "light_passes" in extra:
        assert extra["light_passes"] >= 5, "the light did follow the time"
    live.assert_3d_is_the_plan(activity)
    MEASURED.setdefault("gates", {})[activity] = {
        "repaints": repaints, "longest_gap_ms": round(longest_gap * 1000.0),
        "snapshots_while_it_happened": during, "snapshots_after_the_quiet_time": after,
        "attempts": attempt + 1, **extra}


def test_the_animation_ticks_inside_the_quiet_time() -> None:
    """Why the quiet time is what it is: "Animate" repaints the shadows every tick."""
    assert sun_sim_toolbar._ANIMATE_INTERVAL_MS * 2 <= sync_controller.NET_QUIET_MS


# ── the announcement matrix ──────────────────────────────────────────────────


def _handle_drag(live: Live) -> None:
    """Three mouse moves on the bed's real resize handle — no release, no command yet."""
    live.scene.clearSelection()
    live.bed.setSelected(True)
    _turns()
    handle = next(child for child in live.bed.childItems() if isinstance(child, ResizeHandle))
    start = handle.scenePos()
    mouse = MagicMock(spec=QGraphicsSceneMouseEvent)
    mouse.button.return_value = Qt.MouseButton.LeftButton
    mouse.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    mouse.scenePos.return_value = start
    handle.mousePressEvent(mouse)
    for step in (1, 2, 3):
        mouse.scenePos.return_value = start + QPointF(12.0 * step, 8.0 * step)
        handle.mouseMoveEvent(mouse)
        _turns()
    live.handle, live.handle_mouse = handle, mouse      # type: ignore[attr-defined]


def _handle_release(live: Live) -> None:
    live.handle.mouseReleaseEvent(live.handle_mouse)    # type: ignore[attr-defined]
    live.scene.clearSelection()


def _draw_a_bed_with_the_tool(live: Live, mouse_event: MagicMock) -> None:
    canvas = live.canvas
    canvas.set_active_tool(ToolType.RAISED_BED)
    tool = canvas.tool_manager.active_tool
    tool.mouse_press(mouse_event, QPointF(900.0, 1900.0))
    tool.mouse_move(mouse_event, QPointF(1200.0, 2100.0))
    tool.mouse_release(mouse_event, QPointF(1200.0, 2100.0))
    canvas.set_active_tool(ToolType.SELECT)
    live.drawn = next(item for item in live.scene.items()          # type: ignore[attr-defined]
                      if isinstance(item, RectangleItem) and item not in (live.bed, live.shed))


def _resize(live: Live) -> None:
    old, new = build_rect_resize(live.bed, 500.0, 120.0, keep_center=True)
    live.commands.execute(ResizeItemCommand(live.bed, old, new, apply_rect_like_geometry))


def _select(live: Live, *items: Any) -> None:
    live.scene.clearSelection()
    for item in items:
        item.setSelected(True)


def _group(live: Live) -> None:
    _select(live, live.bed, live.drawn)                             # type: ignore[attr-defined]
    live.canvas._group_selected()
    live.group = next(item for item in live.scene.items()           # type: ignore[attr-defined]
                      if isinstance(item, GroupItem))


def _ungroup(live: Live) -> None:
    _select(live, live.group)                                       # type: ignore[attr-defined]
    live.canvas._ungroup_selected()
    live.scene.clearSelection()


def _paste(live: Live) -> None:
    _select(live, live.shed)
    live.canvas.copy_selected()
    live.canvas.paste()
    live.scene.clearSelection()


def _duplicate(live: Live) -> None:
    _select(live, live.shed)
    live.canvas.duplicate_selected()
    live.scene.clearSelection()


def _arrange(live: Live) -> None:
    _select(live, live.bed)        # the first item drawn: under everything else
    live.canvas.arrange_selected(ArrangeMode.BRING_TO_FRONT)
    live.scene.clearSelection()


def _container_through_the_panel(live: Live, what: str) -> None:
    """The real Properties panel, its real widgets: the two edits of finding P1-3."""
    panel = live.window.properties_panel
    _select(live, live.pot)                                         # type: ignore[attr-defined]
    live.window._update_properties_panel()
    _turns()
    if what == "height":
        spin = next(box for box in panel.findChildren(QSpinBox)
                    if box.maximum() == 300 and box.suffix() == " cm")
        assert spin.value() == 30
        spin.setValue(70)
    else:
        combo = next(box for box in panel.findChildren(QComboBox)
                     if box.findData(container_model.METAL) >= 0)
        assert combo.currentData() == container_model.PLASTIC
        combo.setCurrentIndex(combo.findData(container_model.METAL))
    live.scene.clearSelection()


def _add_the_pot(live: Live) -> None:
    live.pot = live.add(CircleItem(3600.0, 2200.0, 40.0,            # type: ignore[attr-defined]
                                   object_type=ObjectType.CONTAINER_ROUND,
                                   layer_id=live.scene.active_layer.id), "pot")


def _plant_instance_field(live: Live) -> None:
    """The plant panel's instance fields write ``metadata`` without a command (the
    shipped ad-hoc nudge of §11.4, which now moves the revision too)."""
    panel = live.window.plant_database_panel
    panel._current_plant_item = live.apple
    panel._update_instance_metadata("current_height_cm", 260.0)


def _species_max_height(live: Live) -> None:
    """A SPECIES field of the plant panel (max height), through its real spin box: it
    writes ``metadata["plant_species"]`` without a command. Found by the scoped
    re-check: it moved no revision and reached 3D only by the net."""
    window = live.window
    _select(live, live.apple)
    window.plant_database_panel.set_selected_items([live.apple])
    _turns()
    spin = window.plant_database_panel.max_height_spin
    spin.setValue(spin.value() + 150.0)
    live.scene.clearSelection()


def _layer(live: Live) -> Any:
    return live.scene.active_layer


#: Every way the plan is edited, in the order one window lives through them. The second
#: field: must the 3D scene DIFFER afterwards (False: the edit changes the plan and no
#: record — a lock, an opacity, a soil volume — and a pass that finds nothing is right)?
EDIT_PATHS: list[tuple[str, bool, Callable[[Live, MagicMock], Any]]] = [
    ("draw a bed with the tool", True, _draw_a_bed_with_the_tool),
    ("drop a plant from the gallery", True, lambda live, _e: drop(
        live.canvas, "SHRUB:species=hydrangea", QPointF(1500.0, 600.0))),
    ("move by command", True, lambda live, _e: live.commands.execute(
        MoveItemsCommand([live.bed], QPointF(137.25, -42.5)))),
    ("recolour", True, lambda live, _e: live.commands.execute(
        recolour_fill(live.bed, QColor(200, 30, 30)))),
    ("resize by command", True, lambda live, _e: _resize(live)),
    ("rotate by command", True, lambda live, _e: live.commands.execute(
        RotateItemCommand(live.shed, 0.0, 33.0, apply_rotation))),
    ("undo", True, lambda live, _e: live.commands.undo()),
    ("redo", True, lambda live, _e: live.commands.redo()),
    ("drag an item (no command yet)", True, lambda live, _e: live.shed.setPos(
        live.shed.pos() + QPointF(60.0, 25.0))),
    ("a resize handle drag (three mouse moves)", True, lambda live, _e: _handle_drag(live)),
    ("the handle's release (its command)", False, lambda live, _e: _handle_release(live)),
    ("a typed height (the undo stack's signal)", True, lambda live, _e: (
        live.shed.metadata.__setitem__(METADATA_KEY, 310.0), live.commands.stack_changed.emit())),
    ("hide the layer", True, lambda live, _e: live.scene.update_layer_visibility(
        _layer(live).id, False)),
    ("show the layer", True, lambda live, _e: live.scene.update_layer_visibility(
        _layer(live).id, True)),
    ("lock the layer", False, lambda live, _e: live.scene.update_layer_lock(_layer(live).id, True)),
    ("unlock the layer", False, lambda live, _e: live.scene.update_layer_lock(
        _layer(live).id, False)),
    ("the layer's opacity", False, lambda live, _e: live.scene.update_layer_opacity(
        _layer(live).id, 0.6)),
    ("arrange: bring to front", False, lambda live, _e: _arrange(live)),
    ("group", False, lambda live, _e: _group(live)),
    ("move the group", True, lambda live, _e: live.group.setPos(      # type: ignore[attr-defined]
        live.group.pos() + QPointF(80.0, 40.0))),                     # type: ignore[attr-defined]
    ("ungroup", False, lambda live, _e: _ungroup(live)),
    ("copy and paste", True, lambda live, _e: _paste(live)),
    ("duplicate", True, lambda live, _e: _duplicate(live)),
    ("an Agent API write (move_object)", True, lambda live, _e: live.window._do_agent_move_object(
        str(live.bed.item_id), 30.0, 10.0)),
    ("add a container", True, lambda live, _e: _add_the_pot(live)),
    ("the container's height in the Properties panel", True,
     lambda live, _e: _container_through_the_panel(live, "height")),
    ("the container's material in the Properties panel", True,
     lambda live, _e: _container_through_the_panel(live, "material")),
    ("a plant's measured height in the plant panel", True,
     lambda live, _e: _plant_instance_field(live)),
    ("a species' max height in the plant panel (its spin box)", True,
     lambda live, _e: _species_max_height(live)),
    ("resize the canvas", True, lambda live, _e: live.scene.resize_canvas(6000.0, 4000.0)),
    ("delete by command", True, lambda live, _e: live.commands.execute(
        DeleteItemsCommand(live.scene, [live.apple]))),
    ("the nudge itself", False, lambda live, _e: live.scene.note_plan_changed()),
]


def test_every_edit_path_announces_itself_and_the_net_finds_nothing(
        app3d, qtbot, mouse_event, monkeypatch: pytest.MonkeyPatch) -> None:
    """The matrix, in one window that lives through every edit path in turn. For each:
    the scene's plan revision moved; the 3D scene is the plan again by a pass that
    was ANNOUNCED (the first pass after the edit is never the net's); a reconciliation
    that ran afterwards found nothing; ``unannounced_changes`` stays 0."""
    monkeypatch.setattr(sync_controller, "NET_QUIET_MS", 150)   # the matrix, faster
    live = Live(app3d, qtbot)
    live.start()
    controller = live.controller
    rows: dict[str, list[int]] = {}
    for name, must_differ, edit in EDIT_PATHS:
        live.quiet()
        revision, seen = live.scene.plan_revision, len(live.reports)
        engine_calls = len(live.engines.sink.ops())
        edit(live, mouse_event)
        assert live.scene.plan_revision > revision, f"{name}: the plan revision did not move"
        live.quiet()
        passes = live.reports[seen:]
        snapshots = [report for report in passes if report.snapshot]
        assert snapshots, f"{name}: no pass followed it"
        assert snapshots[0].reconciled is False, f"{name}: it reached 3D by the net, not at once"
        found_late = [report for report in snapshots if report.reconciled
                      and not report.changes.is_empty]
        assert not found_late, f"{name}: the net found {found_late[0].changes}"
        assert controller.unannounced_changes == 0, name
        if must_differ:
            assert len(live.engines.sink.ops()) > engine_calls, f"{name}: the engine was told nothing"
        live.assert_3d_is_the_plan(name)
        rows[name] = [live.scene.plan_revision - revision,
                      sum(1 for report in snapshots if not report.reconciled),
                      sum(1 for report in snapshots if report.reconciled)]
    assert controller.recovery_count == 0 and controller.last_error is None
    MEASURED["matrix (revision moves, announced passes, net passes)"] = rows


# ── P1-3: container material and height through the real panel ───────────────


def test_a_containers_height_and_material_typed_into_the_properties_panel_reach_3d(
        app3d, qtbot) -> None:
    """Finding P1-3, measured before the fix: spin 30 → 70 and combo → metal through
    the real panel left ``metadata`` at 70 / metal and the 3D record at 30 / plastic
    after 400 ms — 0 snapshots, 0 engine calls. Both handlers write ``metadata``
    directly; they announce it now, and repaint the item."""
    live = Live(app3d, qtbot)
    _add_the_pot(live)
    live.start()
    pot_id = str(live.pot.item_id)                                  # type: ignore[attr-defined]
    record = live.controller.sync.records[pot_id]
    assert record.height_cm == 30.0 and record.params["container_material"] == "plastic"

    repaints, calls, seen = len(live.repaints), len(live.engines.sink.ops()), len(live.reports)
    _container_through_the_panel(live, "height")
    qtbot.waitUntil(lambda: live.controller.sync.records[pot_id].height_cm == 70.0, timeout=5000)
    assert live.pot.metadata["container_height_cm"] == 70.0         # type: ignore[attr-defined]
    # at once: by a pass the edit ANNOUNCED, not by the net after the quiet time
    # (L1.8: selecting the pot for the panel first sends its selection ring, in a pass
    # of its own that reads nothing of the plan — snapshot False, reconciled False)
    passes = [report for report in live.reports[seen:] if report.snapshot or report.reconciled]
    assert passes[0].snapshot and passes[0].reconciled is False
    assert ("replace_geometry", pot_id) in live.engines.sink.ops()[calls:]
    assert len(live.repaints) > repaints, "and the item was repainted (the sun's shadow listens)"

    calls, seen = len(live.engines.sink.ops()), len(live.reports)
    _container_through_the_panel(live, "material")
    qtbot.waitUntil(lambda: live.controller.sync.records[pot_id].params["container_material"]
                    == "metal", timeout=5000)
    assert live.pot.metadata["container_material"] == "metal"       # type: ignore[attr-defined]
    passes = [report for report in live.reports[seen:] if report.snapshot or report.reconciled]
    assert passes[0].snapshot and passes[0].reconciled is False
    assert len(live.engines.sink.ops()) > calls, "the engine was told"
    live.quiet()
    assert live.controller.unannounced_changes == 0
    live.assert_3d_is_the_plan()


def test_the_other_direct_writes_of_the_properties_panel_announce_themselves_too(
        app3d, qtbot) -> None:
    """Seven handlers of the Properties panel write into the item without a command
    (a follow-up issue: not undoable). Every one of them moves the plan revision."""
    live = Live(app3d, qtbot)
    _add_the_pot(live)
    panel = live.window.properties_panel
    source = Path(type(panel).__module__.replace(".", "/"))
    text = (REPO / "src" / source.with_suffix(".py")).read_text(encoding="utf-8")
    assert text.count("self._announce_direct_edit(item)") == 7
    # … and through the real widgets, for the two forms that have them
    from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox

    moved: dict[str, int] = {}

    def through(label: str, act: Callable[[], Any]) -> None:
        before = live.scene.plan_revision
        act()
        moved[label] = live.scene.plan_revision - before

    _select(live, live.pot)                                         # type: ignore[attr-defined]
    live.window._update_properties_panel()
    _turns()
    drainage = next(box for box in panel.findChildren(QCheckBox)
                    if "drainage" in box.text().lower())
    through("container drainage", lambda: drainage.setChecked(not drainage.isChecked()))
    volume = next(box for box in panel.findChildren(QDoubleSpinBox) if box.suffix() == " L")
    through("container soil volume", lambda: volume.setValue(12.5))
    _select(live, live.bed)
    live.window._update_properties_panel()
    _turns()
    depth = next(box for box in panel.findChildren(QSpinBox)
                 if box.maximum() == 200 and box.suffix() == " cm")
    through("soil depth", lambda: depth.setValue(depth.value() + 5))
    grid = next(box for box in panel.findChildren(QCheckBox) if "grid" in box.text().lower())
    through("grid on", lambda: grid.setChecked(not grid.isChecked()))
    spacing = next(box for box in panel.findChildren(QDoubleSpinBox)
                   if box.suffix() == " cm" and box.maximum() == 200.0)
    through("grid spacing", lambda: spacing.setValue(spacing.value() + 5.0))
    assert all(count >= 1 for count in moved.values()), moved
    assert len(moved) == 5


# ── the net, in the real window ──────────────────────────────────────────────


def test_a_write_nobody_announced_is_in_3d_after_the_quiet_time_and_is_counted(
        app3d, qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_controller, "NET_QUIET_MS", 150)
    live = Live(app3d, qtbot)
    live.start()
    controller, shed = live.controller, live.shed
    live.quiet()
    calls = len(live.engines.sink.ops())
    shed.metadata[METADATA_KEY] = 420.0      # no command, no nudge …
    shed.update()                            # … a repaint only
    _turns()
    assert len(live.engines.sink.ops()) == calls and controller.unannounced_changes == 0
    live.quiet()
    assert ("replace_geometry", str(shed.item_id)) in live.engines.sink.ops()[calls:]
    assert controller.unannounced_changes == 1 and live.reports[-1].reconciled is True
    live.assert_3d_is_the_plan()


# ── the cost of a preview mouse move, Split against Plan ─────────────────────

#: A preview mouse-move turn in Split may cost at most this many times what it costs in
#: Plan. Before the plan revision: 6.7 (small bench plan) and 26 (large) — a whole-plan
#: snapshot per move. With it the pipeline does nothing for a preview; the bound leaves
#: room for a loaded machine, not for a snapshot.
PREVIEW_MOVE_RATIO_BOUND = 2.0


def _preview_move_ms(live: Live, mouse_event: MagicMock, moves: int) -> list[float]:
    canvas = live.canvas
    canvas.set_active_tool(ToolType.POLYGON)
    tool = canvas.tool_manager.active_tool
    tool.mouse_press(mouse_event, QPointF(300.0, 300.0))
    tool.mouse_release(mouse_event, QPointF(300.0, 300.0))
    _turns()
    costs = []
    for step in range(moves):
        started = stopwatch.perf_counter()
        tool.mouse_move(mouse_event, QPointF(320.0 + 9.0 * step, 310.0 + 5.0 * step))
        _turns()
        costs.append((stopwatch.perf_counter() - started) * 1000.0)
    canvas.set_active_tool(ToolType.SELECT)
    _turns()
    return costs


@pytest.mark.perf
@pytest.mark.parametrize("plan", ["bench_small", "bench_large"])
def test_a_preview_mouse_move_costs_in_split_what_it_costs_in_plan(
        app3d, qtbot, mouse_event, plan: str) -> None:
    """The reviewer's measurement again, and a bound on it. 160 preview moves of the
    polygon tool in Split and 160 in Plan, in alternating rounds of 40 (the machine's
    load cancels): the median cost of a mouse-move turn, and the ratio.

    And no move is a snapshot. The only pass that may run inside a round is the net's
    — after the canvas was not repainted for a whole quiet time, which the wall clock
    also reads when the 2D side keeps the GUI thread busy that long (the first move of
    a tool on a large plan). Those gaps are counted, and the passes may not outnumber
    them; before the plan revision it was one snapshot per move."""
    window, _engines = app3d
    window._open_project_file(str(PLANS / f"{plan}.ogp"))
    live = Live(app3d, qtbot, garden=False)
    live.start()
    workspace, controller = live.workspace, live.controller
    controller.mark_dirty()                      # what ONE snapshot of this plan costs,
    controller.flush()                           # for the scale of the numbers below
    one_snapshot_ms = controller.last_tick.snapshot_ms
    live.quiet()
    quiet_s = sync_controller.NET_QUIET_MS / 1000.0
    split_ms: list[float] = []
    plan_ms: list[float] = []
    snapshots_in_split = quiet_gaps = 0
    for _round in range(4):
        workspace.set_mode(PLAN)
        _turns()
        plan_ms += _preview_move_ms(live, mouse_event, 40)
        workspace.set_mode(SPLIT)
        live.quiet()
        before, seen, first = controller.snapshot_count, len(live.reports), len(live.repaints)
        started = stopwatch.monotonic()
        split_ms += _preview_move_ms(live, mouse_event, 40)
        stamps = [started, *live.repaints[first:], stopwatch.monotonic()]
        quiet_gaps += sum(1 for earlier, later in zip(stamps, stamps[1:], strict=False)
                          if later - earlier >= quiet_s)
        snapshots_in_split += controller.snapshot_count - before
        assert all(report.reconciled and report.changes.is_empty
                   for report in live.reports[seen:] if report.snapshot), "only the net, finding nothing"
    assert snapshots_in_split <= quiet_gaps, (
        f"160 preview moves in Split: {snapshots_in_split} snapshots, {quiet_gaps} quiet gaps")
    split, plain = statistics.median(split_ms), statistics.median(plan_ms)
    ratio = split / plain
    MEASURED.setdefault("preview move, ms per turn", {})[plan] = {
        "records": len(controller.sync.records), "split_median": round(split, 3),
        "plan_median": round(plain, 3), "ratio": round(ratio, 2),
        "split_p95": round(sorted(split_ms)[int(len(split_ms) * 0.95)], 3),
        "plan_p95": round(sorted(plan_ms)[int(len(plan_ms) * 0.95)], 3),
        "one_snapshot_ms": round(one_snapshot_ms, 2),
        "snapshots_in_160_split_moves": snapshots_in_split, "quiet_gaps_in_them": quiet_gaps}
    assert ratio <= PREVIEW_MOVE_RATIO_BOUND, MEASURED["preview move, ms per turn"][plan]
