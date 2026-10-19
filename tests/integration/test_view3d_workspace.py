"""The Plan / 3D / Split workspace in the real main window (Phase 17 L1.3, §8.10).

A real ``GardenPlannerApp`` started with the internal switch ``OGP_QUICK3D=1``, its
3D engine replaced at the documented seam (``Workspace.engine_factory``) by a
recording host and a ``RecordingSink``: the user switches modes, edits the plan,
changes the sim date and time, creates and opens documents, and closes the app —
and the exact engine calls are asserted. Nothing is rendered here; the same
workflow runs through the real Qt Quick 3D host in
``test_view3d_workspace_render.py`` (opt-in, ``OGP_RENDER3D=1``).

Also here: gate G1 (without the switch the app is what it was and the engine is
never imported; with it, Plan mode is today's layout), what gate G10 leaves to this
story since master fixed #428 itself (a replaced document reaches the workspace
through ``CanvasScene.document_replaced`` alone; an open that FAILS leaves the 3D
view as it was) and the acceptance criterion that what 3D cannot build is shown to
the user.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QAction, QColor, QPolygonF
from PyQt6.QtWidgets import QMenu, QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.commands import (
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
    ResizeItemCommand,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import GroundSpec, RecordingSink
from open_garden_planner.core.scene3d.builders import plants
from open_garden_planner.core.scene3d.camera import Bounds, frame_pose
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rect_like_geometry,
    build_rect_resize,
)
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d import snapshot as snapshot_module
from open_garden_planner.ui.view3d.init_guard import Init3DGuard
from open_garden_planner.ui.view3d.sync_controller import NO_LOCATION_SUN
from open_garden_planner.ui.view3d.workspace import View3DState, Workspace, WorkspaceMode
from tests.integration.quick3d_render_support import isolated_env
from tests.integration.test_scene3d_plants import drop
from tests.integration.test_scene3d_snapshot import _recolour as recolour_fill
from tests.integration.test_view3d_workspace_widget import (
    FakeHost,
    pipeline_settled,
    wait_for_pipeline,
)

REPO = Path(__file__).resolve().parents[2]
PLANS = REPO / "tests" / "fixtures" / "plans"
BERLIN = {"latitude": 52.52, "longitude": 13.405}
PLAN, VIEW3D, SPLIT = WorkspaceMode.PLAN, WorkspaceMode.VIEW3D, WorkspaceMode.SPLIT
BEGIN, COMMIT = ("begin", None), ("commit", None)
GROUND, SUN = ("set_ground", None), ("set_sun", None)
SWITCH = "OGP_QUICK3D"


class Engines:
    """The stand-in engine factory: what was built, and with which mode."""

    def __init__(self) -> None:
        self.calls: list[bool] = []
        self.hosts: list[FakeHost] = []
        self.sinks: list[RecordingSink] = []
        #: the workspace these engines are built for (``build_app3d`` sets it)
        self.workspace: Workspace | None = None

    def factory(self, prefer_software: bool) -> tuple[FakeHost, RecordingSink]:
        self.calls.append(prefer_software)
        self.hosts.append(FakeHost(prefer_software))
        self.sinks.append(RecordingSink())
        return self.hosts[-1], self.sinks[-1]

    @property
    def sink(self) -> RecordingSink:
        return self.sinks[-1]

    @property
    def host(self) -> FakeHost:
        return self.hosts[-1]


def _quiet_boxes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *_a, **_k: QMessageBox.StandardButton.Ok)


def build_app3d(qtbot: Any, monkeypatch: pytest.MonkeyPatch,
                tmp_path: Path) -> tuple[GardenPlannerApp, Engines]:
    """The main window with the workspace switched on and the engine replaced — what
    the ``app3d`` fixture of this module (and of ``test_view3d_plan_revision.py``) is."""
    monkeypatch.setenv(SWITCH, "1")
    _quiet_boxes(monkeypatch)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    engines = Engines()
    workspace = window._workspace
    assert isinstance(workspace, Workspace)
    workspace.engine_factory = engines.factory                       # THE SEAM
    engines.workspace = workspace
    workspace._guard = Init3DGuard(tmp_path / "log", is_running=lambda _pid: False)
    window.show()
    qtbot.waitExposed(window)
    window.canvas_view.set_snap_enabled(False)
    return window, engines


@pytest.fixture()
def app3d(qtbot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[GardenPlannerApp, Engines]:
    """The main window with the workspace switched on and the engine replaced."""
    return build_app3d(qtbot, monkeypatch, tmp_path)


def first_pass(workspace: Workspace, qtbot: Any, timeout: int = 5000) -> Any:
    """Wait for the first pass of the document 3D was just opened on, and return the
    controller. NOT a fixed wait: that pass is HELD until its "Building the 3D view…"
    notice was painted, or for ``BUILD_NOTICE_WAIT_MS`` (250 ms) when the label is
    never painted, and then runs ``CATCH_UP_MS`` later (ADR-065). Measured on the dev
    box: about 55 ms with the paint, about 300 ms without — and a CI runner under load
    can be the second case (the refused-item test below once read the indicator 120 ms
    after the switch, found it empty, and the pass ran in its teardown)."""
    qtbot.waitUntil(lambda: workspace.controller is not None
                    and workspace.controller.apply_count >= 1 and pipeline_settled(workspace),
                    timeout=timeout)
    return workspace.controller


def _calls(engines: Engines, qtbot: Any, ms: int = 80) -> list[tuple[str, str | None]]:
    """The engine calls since the last read, once no pass is on its way (by condition:
    a pass held for its notice is later than any fixed wait on a loaded runner)."""
    assert engines.workspace is not None
    wait_for_pipeline(engines.workspace, qtbot, ms)
    calls = engines.sink.ops()
    engines.sink.clear_calls()
    return calls


# ── gate G1 ──────────────────────────────────────────────────────────────────


def test_without_the_switch_the_main_window_is_what_it_was(qtbot, monkeypatch) -> None:
    monkeypatch.delenv(SWITCH, raising=False)
    _quiet_boxes(monkeypatch)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    assert window._workspace is None
    assert window._main_splitter.widget(0) is window.canvas_view
    assert window.canvas_view.parentWidget() is window._main_splitter
    assert window.findChildren(Workspace) == []
    titles = [menu.title() for menu in window._view_menu.findChildren(QMenu)]
    assert "&Workspace" not in titles
    assert not [a for a in window.findChildren(QAction)
                if a.shortcut().toString() in {"Alt+1", "Alt+2", "Alt+3"}]
    assert window._view3d_action.text() == "&3D View…", "the shipped 3D window is still there"


@pytest.mark.parametrize("value", ["", "0", "true", "yes", " 1", "2"])
def test_only_the_exact_value_switches_the_workspace_on(qtbot, monkeypatch, value: str) -> None:
    monkeypatch.setenv(SWITCH, value)
    _quiet_boxes(monkeypatch)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    assert window._workspace is None


def test_the_switch_is_read_in_one_place() -> None:
    """Decision 1: one function reads the variable; nothing else may name it."""
    source = REPO / "src" / "open_garden_planner"
    naming = sorted(str(path.relative_to(source)).replace("\\", "/")
                    for path in source.rglob("*.py")
                    if SWITCH in path.read_text(encoding="utf-8"))
    assert naming == ["app/settings.py"]
    settings_source = (source / "app" / "settings.py").read_text(encoding="utf-8")
    assert settings_source.count("os.environ") == 1
    callers = sorted(str(path.relative_to(source)).replace("\\", "/")
                     for path in source.rglob("*.py")
                     if "quick3d_workspace_enabled()" in path.read_text(encoding="utf-8"))
    assert callers == ["app/application.py", "app/settings.py"]


def test_with_the_switch_plan_mode_is_todays_layout(app3d) -> None:
    window, engines = app3d
    workspace = window._workspace
    assert window._main_splitter.widget(0) is workspace
    assert window._main_splitter.widget(1) is window.sidebar
    assert workspace.mode is PLAN and workspace.view3d_state is View3DState.NOT_STARTED
    assert engines.calls == [] and workspace.pane is None
    # the canvas fills the workspace: the area it had, to the pixel
    assert window.canvas_view.isVisible()
    assert window.canvas_view.size() == workspace.size()
    assert window.canvas_view.mapTo(workspace, window.canvas_view.rect().topLeft()).isNull()
    # every canvas overlay is where it was: a child of the canvas view
    assert window._minimap.parentWidget() is window.canvas_view


def test_the_view_menu_offers_the_three_modes_with_shortcuts_nobody_else_has(app3d) -> None:
    window, _engines = app3d
    workspace = window._workspace
    submenus = {menu.title(): menu for menu in window._view_menu.findChildren(QMenu)}
    menu = submenus["&Workspace"]
    texts = [action.text() for action in menu.actions() if not action.isSeparator()]
    assert texts == ["&Plan", "&3D", "&Split", "&Reset 3D View"]
    modes = workspace.mode_actions()
    assert menu.actions()[:3] == modes and all(action.isCheckable() for action in modes)
    taken: dict[str, list[str]] = {}
    for action in window.findChildren(QAction):
        key = action.shortcut().toString()
        if key:
            taken.setdefault(key, []).append(action.text())
    for action in modes:
        assert taken[action.shortcut().toString()] == [action.text()]
    # … and the shipped 3D window's action is untouched
    assert window._view3d_action.text() == "&3D View…"


_G1_CHILD = r'''
import hashlib, json, os, sys
from pathlib import Path
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv[:1])
from open_garden_planner.app.application import GardenPlannerApp
import open_garden_planner.app.settings as app_settings
assert app_settings.ORGANIZATION_NAME == "cofade_test", "the child must not use the real settings"
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard)
GardenPlannerApp._show_welcome_dialog = lambda self: None
window = GardenPlannerApp()
window.showNormal()
window.resize(1400, 900)
window._open_project_file(sys.argv[1])
window.canvas_view.fit_in_view()
for _ in range(40):
    QCoreApplication.processEvents()
canvas = window.canvas_view
origin = canvas.mapTo(window, canvas.rect().topLeft())
image = canvas.grab().toImage()
bits = image.constBits(); bits.setsize(image.sizeInBytes())
loaded = sorted(m for m in sys.modules if m.startswith((
    "PyQt6.QtQuick", "PyQt6.QtQml", "open_garden_planner.ui.view3d")))
out = {
    "workspace": type(window._workspace).__name__,
    "splitter0": type(window._main_splitter.widget(0)).__name__,
    "canvas": [origin.x(), origin.y(), canvas.width(), canvas.height()],
    "pixels": hashlib.sha256(bytes(bits)).hexdigest(),
    "image": [image.width(), image.height()],
    "loaded": loaded,
    "items": len(window.canvas_scene.items()),
    "store": app_settings.create_qsettings().applicationName(),
}
window.close()
for _ in range(10):
    QCoreApplication.processEvents()
out["loaded_after_close"] = sorted(m for m in sys.modules if m.startswith((
    "PyQt6.QtQuick", "PyQt6.QtQml", "open_garden_planner.ui.view3d.quick3d")))
print("RESULT " + json.dumps(out))
'''


def _g1_child(scratch: Path, switch: str) -> dict[str, Any]:
    """``switch``: the variable's value in the child — set explicitly either way, so
    that what the developer's own shell exports cannot decide the test."""
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _G1_CHILD, str(PLANS / "bench_small.ogp")],
        env=isolated_env(scratch, QT_QPA_PLATFORM="offscreen", OGP_QUICK3D=switch),
        capture_output=True, text=True, timeout=170, cwd=scratch)
    assert proc.returncode == 0, proc.stderr[-3000:]
    (line,) = [line for line in proc.stdout.splitlines() if line.startswith("RESULT ")]
    return json.loads(line[len("RESULT "):])


def test_g1_the_engine_is_never_imported_and_the_canvas_is_pixel_identical(tmp_path: Path) -> None:
    """Gate G1, in two fresh processes that build the real app, open a plan and close.

    WITHOUT the switch: nothing of ``ui/view3d`` and no Qt Quick binding is loaded,
    before or after the close. WITH it: the workspace module is loaded and still no
    engine — and the canvas has the same place, the same size and the same PIXELS."""
    (tmp_path / "off").mkdir()
    (tmp_path / "on").mkdir()
    off = _g1_child(tmp_path / "off", "")
    on = _g1_child(tmp_path / "on", "1")
    assert off["workspace"] == "NoneType" and off["splitter0"] == "CanvasView"
    assert off["loaded"] == [] and off["loaded_after_close"] == []
    assert on["workspace"] == "Workspace" and on["splitter0"] == "Workspace"
    assert not [name for name in on["loaded"] if "Quick" in name or "Qml" in name
                or "quick3d" in name], on["loaded"]
    assert "open_garden_planner.ui.view3d.workspace" in on["loaded"]
    assert on["loaded_after_close"] == [], "closing without ever opening 3D loads no engine"
    assert on["items"] == off["items"] > 90
    assert on["canvas"] == off["canvas"], "the canvas area has today's geometry"
    assert on["image"] == off["image"] and on["pixels"] == off["pixels"], (
        "the canvas view's own pixels are identical with and without the workspace")
    assert off["store"].startswith("Open Garden Planner Test Child ")


# ── the §8.10 workflow ───────────────────────────────────────────────────────


def test_the_workflow_plan_split_edit_pause_clock_new_open_close(
        app3d, qtbot, mouse_event, monkeypatch: pytest.MonkeyPatch) -> None:
    window, engines = app3d
    workspace, canvas = window._workspace, window.canvas_view
    scene, commands = window.canvas_scene, canvas.command_manager
    plan_action, view3d_action, split_action = workspace.mode_actions()

    # ── the user draws in Plan mode: nothing 3D exists ───────────────────────
    canvas.set_active_tool(ToolType.RAISED_BED)
    tool = canvas.tool_manager.active_tool
    tool.mouse_press(mouse_event, QPointF(400.0, 300.0))
    tool.mouse_move(mouse_event, QPointF(700.0, 500.0))
    tool.mouse_release(mouse_event, QPointF(700.0, 500.0))
    bed = next(item for item in scene.items() if isinstance(item, RectangleItem))
    apple = drop(canvas, "TREE:species=apple tree", QPointF(2500.0, 1500.0))
    apple.metadata["plant_instance"] = {
        "planting_date": "2024-04-01", "current_height_cm": 180.0, "current_spread_cm": 120.0}
    bed_id, apple_id = str(bed.item_id), str(apple.item_id)
    qtbot.wait(60)
    assert engines.calls == [] and workspace.controller is None

    # ── Split, from the View menu: the engine is built once, the plan appears ─
    split_action.trigger()
    assert workspace.mode is SPLIT and engines.calls == [False]
    assert canvas.isVisible() and workspace.pane.isVisible()
    calls = _calls(engines, qtbot)
    assert calls[0] == BEGIN and calls[-3:] == [GROUND, SUN, COMMIT]
    assert sorted(calls[1:-3]) == sorted([("add", bed_id), ("add", apple_id)])
    sink, controller = engines.sink, workspace.controller
    assert sink.ground == GroundSpec(5000.0, 3000.0) and sink.sun == NO_LOCATION_SUN
    assert workspace.view3d_state is View3DState.STARTING
    engines.host.health_now.frames_presented = 1
    qtbot.waitUntil(lambda: workspace.view3d_state is View3DState.RUNNING, timeout=3000)
    framed = workspace.camera.pose
    assert framed == frame_pose(controller.plan_bounds(), 800.0 / 500.0)

    # ── an edit session: each edit is its minimal engine call ────────────────
    commands.execute(MoveItemsCommand([bed], QPointF(137.25, -42.5)))
    assert _calls(engines, qtbot) == [BEGIN, ("update_transform", bed_id), COMMIT]
    commands.execute(recolour_fill(bed, QColor(200, 30, 30)))
    assert _calls(engines, qtbot) == [BEGIN, ("update_material", bed_id), COMMIT]
    old, new = build_rect_resize(bed, 500.0, 120.0, keep_center=True)
    commands.execute(ResizeItemCommand(bed, old, new, apply_rect_like_geometry))
    assert _calls(engines, qtbot) == [BEGIN, ("replace_geometry", bed_id), COMMIT]
    fence = PolylineItem([QPointF(100.0, 100.0), QPointF(900.0, 100.0)],
                         object_type=ObjectType.FENCE, layer_id=scene.active_layer.id)
    commands.execute(CreateItemCommand(scene, fence, "fence"))
    fence_id = str(fence.item_id)
    assert _calls(engines, qtbot) == [BEGIN, ("add", fence_id), COMMIT]
    commands.execute(DeleteItemsCommand(scene, [fence]))
    assert _calls(engines, qtbot) == [BEGIN, ("remove", fence_id), COMMIT]
    commands.undo()
    assert _calls(engines, qtbot) == [BEGIN, ("add", fence_id), COMMIT]
    commands.redo()
    assert _calls(engines, qtbot) == [BEGIN, ("remove", fence_id), COMMIT]
    assert workspace.camera.pose is framed, "not one of these edits moved the camera"

    # ── another tab hides the workspace: the pipeline pauses, then catches up ─
    snapshots = controller.snapshot_count
    window._tab_widget.setCurrentIndex(1)
    assert controller.active is False
    for step in range(10):
        commands.execute(MoveItemsCommand([bed], QPointF(5.0 + step, 0.0)))
    assert _calls(engines, qtbot) == [] and controller.snapshot_count == snapshots
    window._tab_widget.setCurrentIndex(0)
    # a pass is owed: it starts once its notice was painted, not inside the tab switch
    assert controller.active is False and workspace.status_text() != ""
    qtbot.waitUntil(lambda: controller.active, timeout=3000)
    assert _calls(engines, qtbot) == [BEGIN, ("update_transform", bed_id), COMMIT]
    assert controller.snapshot_count == snapshots + 1
    # … and so does Plan mode
    plan_action.trigger()
    commands.execute(MoveItemsCommand([bed], QPointF(-3.0, 0.0)))
    assert _calls(engines, qtbot) == [] and controller.active is False
    view3d_action.trigger()
    assert not canvas.isVisible() and workspace.mode is VIEW3D
    assert _calls(engines, qtbot) == [BEGIN, ("update_transform", bed_id), COMMIT]
    assert engines.calls == [False], "one engine for the life of the window"

    # ── the sim clock, through the toolbar's own slot ────────────────────────
    window._project_manager.set_location(dict(BERLIN))
    assert _calls(engines, qtbot) == [BEGIN, SUN, COMMIT]      # a location: a real sun
    window._on_sun_sim_datetime(datetime(2026, 6, 21, 12, 0))  # a known moment to start from
    _calls(engines, qtbot)
    snapshots = controller.snapshot_count
    window._on_sun_sim_datetime(datetime(2026, 6, 21, 9, 15))  # the same day: time only
    assert _calls(engines, qtbot) == [BEGIN, SUN, COMMIT]
    assert controller.snapshot_count == snapshots
    window._on_sun_sim_datetime(datetime(2028, 6, 21, 9, 15))  # two years on: the tree grew
    assert _calls(engines, qtbot) == [BEGIN, ("replace_geometry", apple_id), SUN, COMMIT]
    assert workspace.camera.pose is framed
    assert sink.state() == controller.sync.expected_state()

    # ── a new document: a plain apply, the camera frames it once ─────────────
    cleared: list[int] = []
    monkeypatch.setattr(plants, "clear_shape_cache", lambda: cleared.append(1))
    sent = len(engines.host.cameras)
    window._new_project_document(width_cm=2000.0, height_cm=1000.0)
    calls = _calls(engines, qtbot)
    assert cleared == [1] and ("clear", None) not in calls
    assert sorted(c for c in calls if c[0] == "remove") == sorted(
        [("remove", bed_id), ("remove", apple_id)])
    assert sink.item_ids() == () and sink.ground == GroundSpec(2000.0, 1000.0)
    assert workspace.camera.pose == frame_pose(Bounds.of_plan(2000.0, 1000.0), 800.0 / 500.0)
    assert len(engines.host.cameras) == sent + 1

    # ── an opened document ───────────────────────────────────────────────────
    window._load_project_file(str(PLANS / "bench_small.ogp"))
    qtbot.waitUntil(lambda: len(sink.item_ids()) == 98, timeout=20000)
    qtbot.wait(120)
    assert cleared == [1, 1]
    assert len(engines.host.cameras) == sent + 2, "framed once more, for the opened plan"
    assert workspace.camera.pose == frame_pose(controller.plan_bounds(), 800.0 / 500.0)
    assert math.isclose(controller.plan_bounds().max_east, scene.width_cm)
    assert sink.state() == controller.sync.expected_state()
    assert controller.problem_count == 0 and workspace.problems_text() == ""
    assert controller.recovery_count == 0 and controller.last_error is None

    # ── closing the app with 3D visible ──────────────────────────────────────
    host = engines.host
    assert window.close() is True
    assert host.closed is True and workspace.controller is None
    assert sorted((workspace.guard._directory).iterdir()) == []   # no marker left behind


def test_a_recovered_document_is_a_document_change_too(app3d, qtbot, tmp_path: Path) -> None:
    window, engines = app3d
    workspace = window._workspace
    workspace.set_mode(VIEW3D)
    first_pass(workspace, qtbot)            # the first document is framed before counting
    sent = len(engines.host.cameras)
    recovery = tmp_path / "recovery.ogp"
    recovery.write_bytes((PLANS / "bench_small.ogp").read_bytes())
    window._load_recovery_file(recovery)
    qtbot.waitUntil(lambda: len(engines.sink.item_ids()) == 98, timeout=20000)
    qtbot.wait(120)
    assert len(engines.host.cameras) == sent + 1


def test_the_shipped_3d_window_is_still_driven_with_the_workspace_on(app3d, qtbot) -> None:
    """The Qt 3D window and its wiring stay exactly as they are until L1.10."""
    window, _engines = app3d
    stand_in = MagicMock()
    window._view3d_window = stand_in
    window._sim_clock.set_datetime(datetime(2026, 6, 21, 12, 0))
    stand_in.reset_mock()
    window._on_sun_sim_datetime(datetime(2026, 6, 21, 15, 0))
    assert stand_in.set_sun.call_count == 1 and stand_in.rebuild.call_count == 0
    window._on_sun_sim_datetime(datetime(2026, 7, 1, 15, 0))
    assert stand_in.rebuild.call_count == 1
    window._view3d_window = None
    qtbot.wait(20)


def test_fullscreen_preview_hides_the_mode_switch_with_the_rest_of_the_ui(app3d, qtbot) -> None:
    window, _engines = app3d
    workspace = window._workspace
    assert workspace._floating.isVisible()
    window._enter_preview_mode()
    qtbot.wait(80)
    assert not workspace._floating.isVisible()
    window._exit_preview_mode()
    qtbot.wait(30)
    assert workspace._floating.isVisible()


def test_closing_with_3d_hidden_or_never_opened_is_quiet(app3d, qtbot) -> None:
    window, engines = app3d
    workspace = window._workspace
    workspace.set_mode(SPLIT)
    qtbot.wait(80)
    workspace.set_mode(PLAN)          # hidden again
    host = engines.host
    assert window.close() is True
    assert host.closed is True


def test_closing_without_ever_opening_3d_builds_no_engine(app3d) -> None:
    window, engines = app3d
    assert window.close() is True
    assert engines.calls == [] and window._workspace.guard.mode is None


# ── acceptance: what 3D could not build is shown ─────────────────────────────


def _ring(count: int, radius: float = 600.0) -> list[QPointF]:
    return [QPointF(1500.0 + radius * math.cos(2 * math.pi * k / count),
                    1500.0 + radius * math.sin(2 * math.pi * k / count)) for k in range(count)]


def test_a_plan_with_a_refused_item_shows_the_indicator_and_fixing_it_clears_it(
        app3d, qtbot) -> None:
    """Addendum point 12. A polygon traced with 6,000 points is drawn by the canvas and
    refused by the record layer (``outline_too_large``): it is absent from 3D, and the
    workspace says so until the outline has fewer points.

    The indicator is filled by the pass that finds the problem, in the same call
    (``problems_changed`` is a direct connection): it is read AT that pass's
    ``applied`` — never later than the pass, and never by a fixed wait, because the
    first pass of a document is held for its notice (``first_pass``). This test
    waited 120 ms once and read ``''`` on a loaded CI runner: the pass came after it."""
    window, engines = app3d
    workspace, scene = window._workspace, window.canvas_scene
    commands = window.canvas_view.command_manager
    traced = PolygonItem(_ring(6000), object_type=ObjectType.GARDEN_BED, name="Traced bed",
                         layer_id=scene.active_layer.id)
    commands.execute(CreateItemCommand(scene, traced, "bed"))
    workspace.set_mode(SPLIT)
    controller = workspace.controller
    shown_at_pass: list[str] = []
    controller.applied.connect(lambda _report: shown_at_pass.append(workspace.problems_text()))
    first_pass(workspace, qtbot)
    assert shown_at_pass[0] == "1 object is not shown in 3D", "set by the pass that found it"
    assert workspace.problems_text() == "1 object is not shown in 3D"
    assert str(traced.item_id) not in engines.sink.item_ids()
    workspace._problems_button.click()
    dialog = workspace.problems_dialog
    assert dialog.row_text(0) == (
        "Traced bed (Garden Bed): its outline has too many points for the 3D view")
    dialog.activate_row(0)
    assert traced.isSelected()

    passes = controller.apply_count
    traced.setPolygon(QPolygonF(_ring(40)))      # the user simplifies the outline …
    scene.note_plan_changed()                    # … and a writer round the undo stack says so
    qtbot.waitUntil(lambda: controller.apply_count > passes and pipeline_settled(workspace),
                    timeout=5000)
    assert shown_at_pass[-1] == "", "cleared by the pass that built it"
    assert workspace.problems_text() == "" and dialog.row_count() == 0
    assert str(traced.item_id) in engines.sink.item_ids()
    dialog.close()


# ── gate G10: #428, and what a FAILED open leaves alone ──────────────────────
#
# #428 itself — "a sun map still computing never paints onto the next document" — is
# master's fix (v1.30.1: ``CanvasScene.document_replaced`` -> ``_reset_sun_document``)
# and master's tests: ``tests/integration/test_sun_document_lifecycle.py``. This story's
# own mechanism for it ran BEFORE a load could fail and threw away the map of the plan
# that stayed open; it is gone. What is pinned here is what master's tests do not say:
# the 3D workspace hears of a replaced document from that same signal and from nothing
# else, and an open that fails leaves the 3D view exactly as it was.


def _split_with_a_bed(window: GardenPlannerApp, engines: Engines, qtbot: Any) -> Any:
    scene, commands = window.canvas_scene, window.canvas_view.command_manager
    bed = RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                        layer_id=scene.active_layer.id)
    commands.execute(CreateItemCommand(scene, bed, "bed"))
    window._workspace.set_mode(SPLIT)
    qtbot.waitUntil(lambda: engines.sinks and engines.sink.item_ids() == (str(bed.item_id),),
                    timeout=5000)
    engines.host.health_now.frames_presented = 1
    qtbot.waitUntil(lambda: window._workspace.view3d_state is View3DState.RUNNING, timeout=3000)
    return bed


def _bad_file(tmp_path: Path) -> Path:
    broken = tmp_path / "broken.ogp"
    broken.write_text("{broken", encoding="utf-8")
    return broken


def _open_from_the_file_menu(window: GardenPlannerApp, tmp_path: Path) -> None:
    window._open_project_file(str(_bad_file(tmp_path)))            # File > Open: a dialog, no raise


def _open_a_recent_file_that_moved(window: GardenPlannerApp, tmp_path: Path) -> None:
    window._on_open_recent_file(str(tmp_path / "moved-away.ogp"))  # Open Recent: the file is gone


def _open_through_the_agent(window: GardenPlannerApp, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        window._do_agent_open_plan(str(_bad_file(tmp_path)), force=True)


@pytest.mark.parametrize("failing_open", [
    _open_from_the_file_menu, _open_a_recent_file_that_moved, _open_through_the_agent,
], ids=["file_open_bad_file", "open_recent_moved_file", "agent_open_plan_bad_file"])
def test_an_open_that_fails_leaves_the_3d_view_its_camera_and_its_memories_as_they_were(
        app3d, qtbot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failing_open: Any) -> None:
    """The review's P1-1, on all three ways a load can fail. Before: this story cleared
    the hours-of-sun map (and unchecked its button) BEFORE ``ProjectManager.load`` had
    validated anything. Now nothing of the document is touched until the scene says
    ``document_replaced`` — which a failed validation never reaches."""
    window, engines = app3d
    errors: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **_k: errors.append(str(args[2])))
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    window._project_manager.set_location(dict(BERLIN))
    bed = _split_with_a_bed(window, engines, qtbot)
    workspace, controller = window._workspace, window._workspace.controller
    heatmap, button = window._sun_heatmap, window._sun_toolbar._heatmap_button
    with qtbot.waitSignal(heatmap.finished, timeout=60000):
        window._on_heatmap_requested()
    assert heatmap.heatmap_visible() and button.isChecked()

    workspace.camera.orbit(40.0, 12.0)                 # the user has looked around
    workspace.camera.snap()
    workspace._apply_camera()
    pose, sent = workspace.camera.pose, len(engines.host.cameras)
    dropped: list[str] = []
    monkeypatch.setattr(plants, "clear_shape_cache", lambda: dropped.append("shapes"))
    monkeypatch.setattr(snapshot_module, "clear_outline_cache", lambda: dropped.append("outlines"))
    shown: list[int] = []
    controller.document_shown.connect(lambda: shown.append(1))
    qtbot.wait(120)
    engines.sink.clear_calls()
    counts = (controller.snapshot_count, controller.apply_count, controller.recovery_count)
    records = dict(controller.sync.records)

    failing_open(window, tmp_path)
    qtbot.wait(200)

    assert errors or failing_open is _open_through_the_agent, "the GUI paths said what failed"
    # the plan that stays open is untouched …
    assert bed.scene() is window.canvas_scene
    assert heatmap.heatmap_visible() and button.isChecked(), "its hours-of-sun map stays (P1-1)"
    # … and so is its 3D view: no pass, no notice, no camera move, nothing forgotten
    assert (controller.snapshot_count, controller.apply_count, controller.recovery_count) == counts
    assert engines.sink.ops() == [] and controller.sync.records == records
    assert workspace.status_text() == "" and controller.dirty is False
    assert workspace.camera.pose is pose and len(engines.host.cameras) == sent
    assert dropped == [] and shown == []
    heatmap.shutdown()


def test_a_replaced_document_reaches_the_workspace_through_the_scenes_signal_alone(
        app3d, qtbot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The positive control of the test above, and the ONE mechanism: every way the
    document is replaced — new, open, recovery, the agent — makes the scene emit
    ``document_replaced`` once, the workspace's slot runs once, the plan's memories
    are dropped, and the camera frames the new plan once."""
    window, engines = app3d
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    _split_with_a_bed(window, engines, qtbot)
    workspace, controller = window._workspace, window._workspace.controller
    emitted: list[int] = []
    window.canvas_scene.document_replaced.connect(lambda: emitted.append(1))
    told: list[int] = []
    original = controller.document_changed
    monkeypatch.setattr(controller, "document_changed",
                        lambda: (told.append(1), original())[1])
    recovery = tmp_path / "recovery.ogp"
    recovery.write_bytes((PLANS / "bench_small.ogp").read_bytes())
    ways = [
        lambda: window._new_project_document(width_cm=2000.0, height_cm=1000.0),
        lambda: window._open_project_file(str(PLANS / "bench_small.ogp")),
        lambda: window._load_recovery_file(recovery),
        lambda: window._do_agent_open_plan(str(PLANS / "bench_small.ogp"), force=True),
    ]
    for count, replace in enumerate(ways, start=1):
        sent = len(engines.host.cameras)
        replace()
        assert (len(emitted), len(told)) == (count, count), "one signal, one slot call"
        qtbot.waitUntil(lambda: not controller.dirty and workspace.status_text() == "",
                        timeout=20000)
        qtbot.wait(120)
        assert len(engines.host.cameras) == sent + 1, "framed once for the new document"
    source = (REPO / "src" / "open_garden_planner" / "app" / "application.py").read_text(
        encoding="utf-8")
    assert "document_changed" not in source, "the main window tells the workspace nothing by hand"
