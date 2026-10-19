"""The Plan / 3D / Split workspace widget with a stand-in engine (L1.3, ADR-065).

``ui/view3d/workspace.Workspace`` around a real canvas, with the engine replaced
at its documented seam (``engine_factory``) by a host that records what it is told
and a ``RecordingSink``. No GPU, no Qt Quick: modes, lazy start, pause and
catch-up, the camera rule, the crash marker and its notices, what 3D could not
build. The real engine runs the same paths in ``test_view3d_workspace_render.py``.
"""

from __future__ import annotations

import logging
import time as stopwatch
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from open_garden_planner.core.commands import (
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
    ResizeItemCommand,
    RotateItemCommand,
)
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import RecordingSink
from open_garden_planner.core.scene3d.camera import FOV_DEG, Bounds, frame_pose
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rect_like_geometry,
    apply_rotation,
    build_rect_resize,
)
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d import sync_controller
from open_garden_planner.ui.view3d import workspace as workspace_module
from open_garden_planner.ui.view3d.init_guard import COMPAT_NAME, Init3DGuard, marker_name
from open_garden_planner.ui.view3d.workspace import (
    MIN_PANE_WIDTH,
    View3DState,
    Workspace,
    WorkspaceMode,
)
from tests.integration.test_scene3d_snapshot import _recolour as recolour_fill
from tests.integration.test_view3d_sync_controller import NOON

PLAN, VIEW3D, SPLIT = WorkspaceMode.PLAN, WorkspaceMode.VIEW3D, WorkspaceMode.SPLIT
ME = 4242
NOTICE = "Building the 3D view\N{HORIZONTAL ELLIPSIS}"


class FakeHealth:
    def __init__(self) -> None:
        self.frames_presented = 0
        self.qml_warning_count = 0
        self.scene_graph_error: str | None = None


class FakeHost:
    """What the workspace needs from ``Quick3DHost`` — and a record of what it was told."""

    def __init__(self, prefer_software: bool) -> None:
        self.prefer_software = prefer_software
        self.cameras: list[tuple[Any, Any, float]] = []
        self.filters: list[Any] = []
        self.health_now = FakeHealth()
        self.size = (800.0, 500.0)
        self.widget: QWidget | None = None
        self.closed = False
        self.releases = 0
        self.release_error: Exception | None = None
        #: Every call that would take a FRAME from the live view. The workspace makes
        #: none by itself (the memory rule, ADR-065); the real host has all four.
        self.frames_taken: list[str] = []

    def release_cached_resources(self) -> None:
        self.releases += 1
        if self.release_error is not None:
            raise self.release_error

    def grab(self) -> None:
        self.frames_taken.append("grab")

    def wait_ready(self, _timeout_s: float = 1.0) -> bool:
        self.frames_taken.append("wait_ready")
        return True

    def pick(self, _x: float, _y: float) -> None:
        self.frames_taken.append("pick")

    def project(self, _point: Any) -> None:
        self.frames_taken.append("project")

    def container(self, parent: QWidget | None = None) -> QWidget:
        self.widget = QWidget(parent)
        return self.widget

    def install_event_filter(self, watcher: Any) -> None:
        self.filters.append(watcher)

    def set_camera(self, eye: Any, target: Any, fov_deg: float = 40.0) -> None:
        self.cameras.append((eye, target, fov_deg))

    def view_size(self) -> tuple[float, float]:
        return self.size

    def health(self) -> FakeHealth:
        return self.health_now

    def close(self) -> None:
        self.closed = True
        if self.widget is not None:
            self.widget.deleteLater()


class Bench:
    """A window with the workspace in it, the engine replaced at the seam."""

    def __init__(self, view: CanvasView, qtbot: Any, folder: Path, *,
                 fail_first: Exception | None = None, ui_state: Any = None) -> None:
        self.view, self.qtbot, self.folder = view, qtbot, folder
        self.scene, self.commands = view.scene(), view.command_manager
        self.clock = SimClock(NOON)
        self.hosts: list[FakeHost] = []
        self.sinks: list[RecordingSink] = []
        self.factory_calls: list[bool] = []
        self.fail_next = fail_first
        self.window = QWidget()
        self.window.resize(1200, 700)
        layout = QVBoxLayout(self.window)
        layout.setContentsMargins(0, 0, 0, 0)
        self.guard = Init3DGuard(folder, pid=ME, is_running=lambda _pid: False)
        self.workspace = Workspace(view, engine_factory=self._factory, guard=self.guard)
        self.workspace.connect_plan(self.scene, self.clock, lambda: None, self.commands, ui_state)
        layout.addWidget(self.workspace)
        qtbot.addWidget(self.window)
        self.window.show()
        qtbot.waitExposed(self.window)

    def _factory(self, prefer_software: bool) -> tuple[FakeHost, RecordingSink]:
        self.factory_calls.append(prefer_software)
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        host, sink = FakeHost(prefer_software), RecordingSink()
        self.hosts.append(host)
        self.sinks.append(sink)
        return host, sink

    @property
    def host(self) -> FakeHost:
        return self.hosts[-1]

    @property
    def sink(self) -> RecordingSink:
        return self.sinks[-1]

    def settle(self, ms: int = 80) -> None:
        self.qtbot.wait(ms)

    def files(self) -> list[str]:
        return sorted(path.name for path in self.folder.iterdir())

    def bed(self, x: float = 400.0, y: float = 300.0) -> RectangleItem:
        item = RectangleItem(x, y, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                             layer_id=self.scene.active_layer.id)
        self.commands.execute(CreateItemCommand(self.scene, item, "bed"))
        return item

    def poll(self) -> None:
        self.workspace._poll_health()


@pytest.fixture()
def bench(canvas: CanvasView, qtbot, tmp_path: Path) -> Bench:
    return Bench(canvas, qtbot, tmp_path)


# ── modes and the lazy start ─────────────────────────────────────────────────


def test_it_starts_as_the_plan_and_nothing_3d_exists(bench: Bench) -> None:
    workspace = bench.workspace
    assert workspace.mode is PLAN and workspace.view3d_state is View3DState.NOT_STARTED
    assert workspace.pane is None and workspace.controller is None and workspace.host is None
    assert bench.factory_calls == [] and bench.files() == []
    assert bench.view.isVisible()
    assert bench.view.size() == workspace.size(), "the canvas has the whole area, as before"
    plan, view3d, split = workspace.mode_actions()
    assert (plan.isChecked(), view3d.isChecked(), split.isChecked()) == (True, False, False)
    assert workspace.reset_view_action.isEnabled() is False
    assert workspace._floating.isVisible()
    assert [button.text() for button in workspace._floating.buttons] == ["Plan", "3D", "Split"]


def test_entering_3d_builds_the_engine_once_and_frames_the_plan(bench: Bench) -> None:
    bed = bench.bed()
    workspace = bench.workspace
    workspace.set_mode(VIEW3D)
    assert bench.factory_calls == [False]
    assert workspace.view3d_state is View3DState.STARTING
    assert bench.files() == [marker_name(ME)], "the start is marked before the engine is built"
    assert not bench.view.isVisible() and workspace.pane is not None and workspace.pane.isVisible()
    assert workspace._pane_switch.isVisible() and not workspace._floating.isVisible()
    assert workspace.status_text() == "Building the 3D view…"
    assert bench.sink.item_ids() == (), "the first pass waits for the event loop"
    bench.settle()
    assert bench.sink.item_ids() == (str(bed.item_id),)
    assert workspace.status_text() == ""
    assert workspace.controller is not None and workspace.controller.active
    # the first open frames the plan — exactly the Qt-free fit, in the engine's hands
    pose = frame_pose(Bounds.of_plan(5000.0, 3000.0, 40.0), 800.0 / 500.0)
    assert workspace.camera.pose == pose and workspace.camera.moving is False
    assert bench.host.cameras[-1] == (pose.eye, pose.target_scene, FOV_DEG)
    assert workspace.reset_view_action.isEnabled() is True
    assert len(bench.host.filters) == 1, "the orbit input listens on the engine's window"


def test_the_one_host_is_kept_and_only_hidden_and_shown(bench: Bench) -> None:
    workspace = bench.workspace
    for mode in (VIEW3D, PLAN, SPLIT, PLAN, VIEW3D, SPLIT, VIEW3D, PLAN):
        workspace.set_mode(mode)
        bench.settle(30)
        assert workspace.mode is mode
        assert bench.view.isVisible() is (mode is not VIEW3D)
        assert workspace.pane is not None and workspace.pane.isVisible() is (mode is not PLAN)
        assert workspace._floating.isVisible() is (mode is not VIEW3D)
        assert workspace._pane_switch.isVisible() is (mode is VIEW3D)
        assert workspace.controller is not None
        assert workspace.controller.active is (mode is not PLAN)
        checked = [action.isChecked() for action in workspace.mode_actions()]
        assert checked == [mode is PLAN, mode is VIEW3D, mode is SPLIT]
    assert bench.factory_calls == [False] and len(bench.hosts) == 1
    assert bench.host.closed is False


def test_the_mode_actions_switch_the_mode_like_the_buttons(bench: Bench) -> None:
    workspace = bench.workspace
    plan, view3d, split = workspace.mode_actions()
    seen: list[WorkspaceMode] = []
    workspace.mode_changed.connect(seen.append)
    split.trigger()
    view3d.trigger()
    view3d.trigger()          # the checked one again: nothing
    workspace._pane_switch.buttons[0].click()   # "Plan" in the 3D pane's own switch
    assert seen == [SPLIT, VIEW3D, PLAN] and plan.isChecked()
    assert [action.shortcut().toString() for action in (plan, view3d, split)] == [
        "Alt+1", "Alt+2", "Alt+3"]


def test_in_split_mode_neither_side_can_be_dragged_shut(bench: Bench) -> None:
    workspace = bench.workspace
    workspace.set_mode(SPLIT)
    bench.settle()
    splitter, pane = workspace.splitter, workspace.pane
    assert pane is not None and min(splitter.sizes()) > 0
    handle = splitter.handle(1)
    for target_x in (5000, -5000, 5000):     # far right, far left, and back
        start = handle.rect().center()
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(handle, QPoint(start.x() + target_x, start.y()))
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                           QPoint(start.x() + target_x, start.y()))
        bench.settle(30)
        canvas_width, pane_width = splitter.sizes()
        assert pane_width >= MIN_PANE_WIDTH and canvas_width > 0
        assert pane.isVisible() and bench.view.isVisible()
        assert workspace.controller is not None and workspace.controller.active
    splitter.setSizes([10_000, 0])
    assert splitter.sizes()[1] >= MIN_PANE_WIDTH


def test_the_pipeline_is_paused_in_plan_mode_and_catches_up_once(bench: Bench) -> None:
    bed = bench.bed()
    workspace = bench.workspace
    workspace.set_mode(SPLIT)
    bench.settle()
    controller = workspace.controller
    assert controller is not None
    workspace.set_mode(PLAN)
    snapshots = controller.snapshot_count
    bench.sink.clear_calls()
    for index in range(25):
        bench.commands.execute(MoveItemsCommand([bed], QPointF(1.0 + index, 0.0)))
    bench.clock.set_date(date(2026, 9, 1))
    bench.settle()
    assert controller.snapshot_count == snapshots and bench.sink.ops() == []
    workspace.set_mode(VIEW3D)
    bench.settle()
    assert controller.snapshot_count == snapshots + 1
    assert bench.sink.state() == controller.sync.expected_state()


def test_a_minimised_window_pauses_the_pipeline_too(bench: Bench) -> None:
    workspace = bench.workspace
    workspace.set_mode(VIEW3D)
    bench.settle()
    controller = workspace.controller
    assert controller is not None and controller.active
    bench.window.showMinimized()
    bench.settle(50)
    if not bench.window.isMinimized():
        pytest.skip("this platform does not minimise a window")
    assert controller.active is False
    bench.window.showNormal()
    bench.settle(50)
    assert controller.active is True


def test_fullscreen_preview_hides_the_workspaces_own_controls(bench: Bench) -> None:
    workspace = bench.workspace
    workspace.set_chrome_visible(False)
    assert not workspace._floating.isVisible()
    workspace.set_mode(SPLIT)
    assert not workspace._floating.isVisible() and not workspace.pane.strip.isVisible()
    workspace.set_chrome_visible(True)
    assert workspace._floating.isVisible() and workspace.pane.strip.isVisible()


# ── the "building" notice is painted before the first snapshot ───────────────


class PaintLog(QObject):
    """What a label showed each time it was PAINTED. An event filter runs before the
    widget handles the event: the text the label has then is the text it paints.
    ``swallow``: the label is never painted at all."""

    def __init__(self, label: Any, *, swallow: bool = False) -> None:
        super().__init__(label)
        self._label, self._swallow = label, swallow
        self.texts: list[str] = []
        label.installEventFilter(self)

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        if watched is self._label and event is not None and event.type() == QEvent.Type.Paint:
            self.texts.append(self._label.text())
            return self._swallow
        return False


def _note_each_snapshot(monkeypatch: pytest.MonkeyPatch, note: Any) -> None:
    """Call ``note()`` at the START of every whole-plan snapshot the pipeline takes."""
    real = sync_controller.snapshot_records

    def watched(*arguments: Any, **options: Any) -> Any:
        note()
        return real(*arguments, **options)

    monkeypatch.setattr(sync_controller, "snapshot_records", watched)


def test_the_building_notice_is_painted_before_the_first_snapshot_starts(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    """A first pass costs the sum of its items — seconds for a hostile plan — and the
    GUI thread is inside it: what the pane shows when the snapshot STARTS is what the
    user looks at until it ends. So the notice must have been painted by then, and
    not by luck of the event loop: here every timer of the start is overdue before
    the loop runs again (a busy GUI thread), which is when a timer would win."""
    bench.bed()
    workspace = bench.workspace
    seen: list[tuple[str, bool, list[str]]] = []
    paints: list[PaintLog] = []
    _note_each_snapshot(monkeypatch, lambda: seen.append(
        (workspace.status_text(), workspace._status_label.isVisible(), list(paints[0].texts))))
    workspace.set_mode(SPLIT)
    paints.append(PaintLog(workspace._status_label))
    assert workspace.status_text() == NOTICE and seen == []
    stopwatch.sleep(0.12)
    bench.qtbot.waitUntil(lambda: bool(seen), timeout=3000)
    text, visible, painted = seen[0]
    assert text == NOTICE and visible is True
    assert NOTICE in painted, "the notice was painted before the snapshot began"
    bench.settle()
    assert workspace.status_text() == "" and len(seen) == 1


def test_a_notice_that_is_never_painted_does_not_hold_3d_back(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace_module, "BUILD_NOTICE_WAIT_MS", 120)
    bed = bench.bed()
    workspace = bench.workspace
    workspace.set_mode(SPLIT)
    log = PaintLog(workspace._status_label, swallow=True)
    bench.settle(40)
    assert bench.sink.item_ids() == (), "it waits for the notice first"
    bench.qtbot.waitUntil(lambda: bench.sink.item_ids() == (str(bed.item_id),), timeout=3000)
    assert workspace.controller is not None and workspace.controller.active
    assert log.texts and set(log.texts) == {NOTICE}, "the label was asked to paint, and could not"


def test_with_its_controls_hidden_3d_does_not_wait_for_a_notice_nobody_can_read(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace_module, "BUILD_NOTICE_WAIT_MS", 60_000)
    bed = bench.bed()
    bench.workspace.set_chrome_visible(False)     # the fullscreen preview
    bench.workspace.set_mode(SPLIT)
    bench.settle()
    assert bench.sink.item_ids() == (str(bed.item_id),)


def test_hiding_3d_before_the_notice_was_painted_starts_nothing(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace_module, "BUILD_NOTICE_WAIT_MS", 40)
    bench.bed()
    workspace = bench.workspace
    workspace.set_mode(SPLIT)
    workspace.set_mode(PLAN)                      # before the event loop ran once
    bench.settle(150)
    assert bench.sink.item_ids() == () and workspace.controller is not None
    assert workspace.controller.active is False and workspace.controller.snapshot_count == 0


def test_a_new_document_is_announced_before_its_first_snapshot_too(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = bench.workspace
    bench.bed()
    workspace.set_mode(SPLIT)
    bench.settle()
    assert workspace.status_text() == ""
    paints = PaintLog(workspace._status_label)
    seen: list[tuple[str, list[str]]] = []
    _note_each_snapshot(monkeypatch, lambda: seen.append(
        (workspace.status_text(), list(paints.texts))))

    bench.scene.clear()                           # what "open" does, in one turn of the loop:
    new = bench.bed(100.0, 100.0)                 # the scene itself says "document replaced"
    assert workspace.status_text() == NOTICE and seen == []
    stopwatch.sleep(0.12)
    bench.qtbot.waitUntil(lambda: bool(seen), timeout=3000)
    text, painted = seen[0]
    assert text == NOTICE and NOTICE in painted
    bench.settle()
    assert bench.sink.item_ids() == (str(new.item_id),) and workspace.status_text() == ""
    assert len(seen) == 1, "the new document is ONE snapshot"


# ── what a destroyed Model leaves behind in the engine ───────────────────────


class Releases:
    """A workspace in Split mode over ``beds`` raised beds, the thresholds small and the
    clock in the test's hands."""

    def __init__(self, bench: Bench, monkeypatch: pytest.MonkeyPatch, *, after: int,
                 at_once: int = 10_000, beds: int = 6) -> None:
        monkeypatch.setattr(workspace_module, "RELEASE_AFTER_RETIRED", after)
        monkeypatch.setattr(workspace_module, "RELEASE_NOW_RETIRED", at_once)
        self.now = 1000.0
        monkeypatch.setattr(workspace_module, "_now", lambda: self.now)
        self.bench = bench
        self.beds = [bench.bed(300.0 + 420.0 * index, 300.0) for index in range(beds)]
        bench.workspace.set_mode(SPLIT)
        bench.settle()

    def delete(self, count: int) -> None:
        gone, self.beds = self.beds[:count], self.beds[count:]
        self.bench.commands.execute(DeleteItemsCommand(self.bench.scene, gone))
        self.bench.settle()

    def idle(self) -> None:
        self.now += workspace_module.RELEASE_IDLE_S


def test_enough_destroyed_models_and_a_quiet_pipeline_release_the_engines_caches(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    """Qt keeps graphics state for every Model it once drew, until it is told to let go
    (measured: 0.1 to 0.35 MB per Model, ADR-065). The workspace tells it — when
    enough Models were destroyed AND the pipeline has been quiet for a moment."""
    rig = Releases(bench, monkeypatch, after=3)
    host = bench.host
    rig.idle()
    bench.poll()
    assert host.releases == 0, "building a plan destroys nothing"
    rig.delete(2)
    rig.idle()
    bench.poll()
    assert host.releases == 0, "two Models: below the threshold"
    rig.delete(1)
    bench.poll()
    assert host.releases == 0, "three, but the pipeline worked a moment ago"
    rig.idle()
    bench.poll()
    assert host.releases == 1
    rig.idle()
    bench.poll()
    assert host.releases == 1, "it counts from zero again"


def test_a_flood_of_destroyed_models_is_released_at_once(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    """An animated date regrows every dated plant on every tick: the pipeline is never
    quiet, and waiting for quiet would keep hundreds of megabytes. Above the second
    threshold the release happens with the pass, whatever the clock says."""
    rig = Releases(bench, monkeypatch, after=2, at_once=4)
    rig.delete(3)
    assert bench.host.releases == 0
    rig.delete(1)
    assert bench.host.releases == 1, "four destroyed: released with the pass, no poll, no quiet"
    rig.idle()
    bench.poll()
    assert bench.host.releases == 1


def test_a_new_document_releases_what_the_old_one_left(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Releases(bench, monkeypatch, after=5)
    bench.scene.clear()                           # CanvasScene.document_replaced tells it
    bench.bed(100.0, 100.0)
    bench.settle(150)
    assert bench.workspace.controller is not None and not bench.workspace.controller.dirty
    rig.idle()
    bench.poll()
    assert bench.host.releases == 1, "six Models of the old plan were destroyed"


def test_nothing_is_released_while_3d_is_hidden(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Releases(bench, monkeypatch, after=2)
    rig.delete(2)
    bench.workspace.set_mode(PLAN)
    rig.idle()
    bench.poll()
    assert bench.host.releases == 0, "a hidden view is left alone"
    bench.workspace.set_mode(SPLIT)
    bench.settle()
    rig.idle()
    bench.poll()
    assert bench.host.releases == 1, "and what was owed is released when it is back"


def test_a_host_that_cannot_release_is_one_log_line_and_no_loop(
        bench: Bench, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    rig = Releases(bench, monkeypatch, after=2)
    bench.host.release_error = RuntimeError("the device said no\n2026-10-12 ERROR forged line")
    rig.delete(2)
    rig.idle()
    with caplog.at_level(logging.DEBUG, logger="open_garden_planner.ui.view3d.workspace"):
        bench.poll()
        bench.poll()
        bench.poll()
    assert bench.host.releases == 1, "asked once; the count starts again"
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1 and "\n" not in errors[0].getMessage()
    assert "cached graphics state" in errors[0].getMessage()
    assert bench.workspace.view3d_state is not View3DState.FAILED, "the view goes on"


# ── nothing takes a frame from the live view (the memory rule) ───────────────

#: The host calls that render a frame of their own. Measured (ADR-048 addendum
#: "L1.3"): a frame rendered for a readback is never presented, and what it holds
#: stays until a presented frame ends — in a view that presents nothing, for good.
FRAME_TAKERS = frozenset({"grab", "grabWindow", "grabFramebuffer", "wait_ready", "pick", "project"})
WORKSPACE_MODULES = ("workspace.py", "sync_controller.py", "orbit_input.py",
                     "problems_dialog.py", "init_guard.py",
                     "selection_bridge.py", "info_card.py", "walk_mode.py")  # L1.8's three
#: The ONE frame-taking call the workspace makes, by name and by place (L1.8): the
#: click handler of the 3D view picks — a user's own action, once per click.
THE_CLICK = ("orbit_input.py", "_release", "pick")


def test_no_steady_path_takes_a_frame_from_the_live_view(
        bench: Bench, monkeypatch: pytest.MonkeyPatch) -> None:
    """What the workspace does BY ITSELF — the pass, the health poll, the camera's
    timer, a resize, the splitter, a release, a document change, hiding and showing —
    asks the host for no frame: no ``grab()``, no ``wait_ready()``, no ``pick()`` /
    ``project()``. (A click that picks is a user's own action and another story's.)"""
    rig = Releases(bench, monkeypatch, after=2)
    workspace, host = bench.workspace, bench.host
    controller = workspace.controller
    assert controller is not None
    bed = rig.beds[-1]
    passes = controller.apply_count
    for index in range(12):                                  # the pass, again and again
        bench.commands.execute(MoveItemsCommand([bed], QPointF(2.0 + index, 1.0)))
        bench.settle(10)
        bench.poll()                                         # the health poll
    assert controller.apply_count >= passes + 12
    bench.clock.set_time_of_day(time(9, 30))                 # the light
    bench.clock.set_date(date(2027, 5, 2))
    rig.delete(2)                                            # … a release of the caches
    rig.idle()
    bench.poll()
    assert host.releases == 1
    host.filters[0].eventFilter(None, _wheel(2))             # the camera's timer
    bench.qtbot.waitUntil(lambda: not workspace.camera.moving, timeout=5000)
    bench.window.resize(900, 520)                            # a resize
    bench.settle(40)
    sizes = workspace.splitter.sizes()                       # the splitter
    workspace.splitter.setSizes([sizes[0] - 120, sizes[1] + 120])
    workspace.splitter.splitterMoved.emit(sizes[0] - 120, 1)
    bench.settle(40)
    for mode in (PLAN, SPLIT, VIEW3D, SPLIT):                # hiding and showing
        workspace.set_mode(mode)
        bench.settle(40)
    bench.scene.clear()                                      # a new document
    bench.bed(100.0, 100.0)
    bench.settle(150)
    host.health_now.frames_presented = 3
    bench.poll()
    workspace.reset_view()
    bench.qtbot.waitUntil(lambda: not workspace.camera.moving, timeout=5000)
    assert len(host.cameras) > 3 and not controller.dirty, "all of it really ran"
    assert host.frames_taken == []


def test_the_workspaces_modules_never_ask_a_host_for_a_frame() -> None:
    """The same rule, read from the source: not one call of a frame-taking method in the
    modules of the workspace — but ONE, allowed by name and by place (L1.8): the click
    handler of ``orbit_input.py`` calls ``pick``, once, and nothing that runs by itself
    does. Not in a move handler, not in a timer slot, not in any other module."""
    import ast

    folder = Path(workspace_module.__file__).resolve().parent
    found = []
    for name in WORKSPACE_MODULES:
        tree = ast.parse((folder / name).read_text(encoding="utf-8"), filename=name)
        for function in (node for node in ast.walk(tree)
                         if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda)):
            where = getattr(function, "name", "<lambda>")
            found += [(name, where, node.func.attr) for node in ast.walk(function)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and node.func.attr in FRAME_TAKERS]
        calls = sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in FRAME_TAKERS for node in ast.walk(tree))
        assert calls == sum(1 for hit in found if hit[0] == name), f"{name}: a call at module level"
    assert found == [THE_CLICK]
    # … and the click is a RELEASE handler: no move, wheel or key handler reaches it
    orbit = ast.parse((folder / "orbit_input.py").read_text(encoding="utf-8"))
    callers = sorted(function.name for function in ast.walk(orbit)
                     if isinstance(function, ast.FunctionDef) and any(
                         isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                         and node.func.attr == "_release" for node in ast.walk(function)))
    assert callers == ["eventFilter"]
    source = ast.get_source_segment(
        (folder / "orbit_input.py").read_text(encoding="utf-8"),
        next(node for node in ast.walk(orbit)
             if isinstance(node, ast.FunctionDef) and node.name == "eventFilter")) or ""
    release = source.index("self._release(event)")
    assert source.rindex("MouseButtonRelease", 0, release) > source.rindex("MouseButtonPress", 0, release)
    # the control: the scan sees such a call where there is one (the engine's own driver)
    offscreen = (folder / "quick3d" / "offscreen.py").read_text(encoding="utf-8")
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr in FRAME_TAKERS for node in ast.walk(ast.parse(offscreen)))


# ── gate G3: edits never move the camera ─────────────────────────────────────


def test_no_edit_moves_the_camera_and_a_document_change_frames_once(bench: Bench) -> None:
    """Gate G3 (default tier): the pose is compared EXACTLY around each of 100 scripted
    edits of every kind, a date change and a time change; then a new document."""
    workspace = bench.workspace
    bed = bench.bed()
    workspace.set_mode(SPLIT)
    bench.settle()
    camera, host = workspace.camera, bench.host
    # the user has looked around: the pose is not the framed one
    camera.orbit(47.0, 11.0)
    camera.zoom(0.6)
    camera.pan(350.0, -120.0)
    camera.snap()
    workspace._apply_camera()
    pose, sent = camera.pose, len(host.cameras)
    layer = bench.scene.active_layer.id

    def tree(index: int) -> CircleItem:
        return CircleItem(1000.0 + 13.0 * index, 900.0, 60.0, object_type=ObjectType.TREE,
                          layer_id=layer)

    edits: list[Any] = []
    for index in range(17):
        extra = tree(index)
        old, new = build_rect_resize(bed, 300.0 + 10 * index, 200.0, keep_center=True)
        edits += [
            lambda i=index: bench.commands.execute(MoveItemsCommand([bed], QPointF(3.0 + i, -2.0))),
            lambda i=index: bench.commands.execute(recolour_fill(bed, QColor(10 * i, 90, 30))),
            lambda o=old, n=new: bench.commands.execute(
                ResizeItemCommand(bed, o, n, apply_rect_like_geometry)),
            lambda e=extra: bench.commands.execute(CreateItemCommand(bench.scene, e, "tree")),
            lambda e=extra: bench.commands.execute(DeleteItemsCommand(bench.scene, [e])),
            bench.commands.undo,
        ]
    edits = edits[:92] + [
        bench.commands.redo,
        lambda: bench.commands.execute(RotateItemCommand(bed, 0.0, 33.0, apply_rotation)),
        lambda: bench.clock.set_date(date(2027, 3, 1)),
        lambda: bench.clock.set_time_of_day(time(8, 15)),
        lambda: bed.setSelected(True),
        lambda: bench.scene.resize_canvas(9000.0, 7000.0),   # the canvas itself: still an edit
        lambda: bed.metadata.__setitem__(METADATA_KEY, 120.0) or bench.commands.stack_changed.emit(),
        lambda: workspace.location_changed({"latitude": 52.5, "longitude": 13.4}),
    ]
    assert len(edits) == 100
    applied = workspace.controller.apply_count + workspace.controller.light_count
    for edit in edits:
        edit()
        bench.settle(15)
        assert camera.pose is pose and camera.goal == pose and camera.moving is False
        assert len(host.cameras) == sent, "nothing told the engine to move the camera"
    assert workspace.controller.apply_count + workspace.controller.light_count > applied + 50

    # a document change DOES frame — once
    bench.scene.clear()                           # the scene's own signal is the mechanism
    bench.scene.resize_canvas(2000.0, 1000.0)
    bench.settle()
    framed = frame_pose(Bounds.of_plan(2000.0, 1000.0, 0.0), 800.0 / 500.0)
    assert camera.pose == framed and len(host.cameras) == sent + 1
    bench.bed(100.0, 100.0)
    bench.settle()
    assert camera.pose == framed and len(host.cameras) == sent + 1, "and the next edit does not"


def test_the_camera_survives_hide_show_and_mode_switches(bench: Bench) -> None:
    workspace = bench.workspace
    workspace.set_mode(VIEW3D)
    bench.settle()
    workspace.camera.orbit(90.0, 20.0)
    workspace.camera.snap()
    pose = workspace.camera.pose
    for mode in (PLAN, SPLIT, VIEW3D, PLAN, VIEW3D):
        workspace.set_mode(mode)
        bench.settle(30)
        assert workspace.camera.pose is pose
    assert bench.host.cameras[-1][0] == pose.eye, "a re-shown view is given the pose again"


def _wheel(notches: int = 1) -> QWheelEvent:
    return QWheelEvent(QPointF(50.0, 50.0), QPointF(50.0, 50.0), QPoint(0, 0),
                       QPoint(0, 120 * notches), Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)


def test_input_moves_the_camera_and_the_step_timer_stops_when_it_is_at_rest(bench: Bench) -> None:
    workspace = bench.workspace
    workspace.set_mode(VIEW3D)
    bench.settle()
    camera, host, timer = workspace.camera, bench.host, workspace._camera_timer
    assert timer.isActive() is False, "an idle view has no timer"
    start, sent = camera.pose, len(host.cameras)
    assert host.filters[0].eventFilter(None, _wheel(3)) is True
    assert timer.isActive() is True and camera.moving is True
    bench.qtbot.waitUntil(lambda: not camera.moving, timeout=5000)
    bench.settle(40)
    assert timer.isActive() is False
    assert camera.pose == camera.goal and camera.pose.distance_cm < start.distance_cm
    assert len(host.cameras) > sent + 3, "the damped pose was shown on its way"
    assert host.cameras[-1][0] == camera.pose.eye


def test_a_camera_in_motion_stops_stepping_while_hidden_and_resumes(bench: Bench) -> None:
    workspace = bench.workspace
    workspace.set_mode(VIEW3D)
    bench.settle()
    camera, timer = workspace.camera, workspace._camera_timer
    bench.host.filters[0].eventFilter(None, _wheel(-5))
    assert timer.isActive()
    workspace.set_mode(PLAN)
    assert timer.isActive() is False
    assert camera.moving is True, "the goal is kept"
    workspace.set_mode(VIEW3D)
    assert timer.isActive() is True
    bench.qtbot.waitUntil(lambda: not camera.moving, timeout=5000)


def test_reset_view_and_home_frame_the_plan_again(bench: Bench) -> None:
    workspace = bench.workspace
    bench.bed()
    workspace.set_mode(VIEW3D)
    bench.settle()
    framed = workspace.camera.pose
    workspace.camera.orbit(120.0, 30.0)
    workspace.camera.snap()
    workspace.reset_view_action.trigger()
    assert workspace.camera.goal == framed and workspace.camera.moving is True
    bench.qtbot.waitUntil(lambda: not workspace.camera.moving, timeout=5000)
    assert workspace.camera.pose == framed
    workspace.camera.zoom(3.0)
    workspace.camera.snap()
    QTest.keyClick(bench.window, Qt.Key.Key_A)      # any key elsewhere: nothing
    from PyQt6.QtGui import QKeyEvent
    bench.host.filters[0].eventFilter(None, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Home,
                                                      Qt.KeyboardModifier.NoModifier))
    assert workspace.camera.goal == framed


# ── the crash marker and its notices ─────────────────────────────────────────


def test_the_first_presented_frame_clears_the_marker(bench: Bench) -> None:
    workspace = bench.workspace
    workspace.set_mode(VIEW3D)
    bench.settle()
    bench.poll()
    assert workspace.view3d_state is View3DState.STARTING and bench.files() == [marker_name(ME)]
    bench.host.health_now.frames_presented = 1
    bench.poll()
    assert workspace.view3d_state is View3DState.RUNNING and bench.files() == []
    assert workspace.compat_text() == "" and workspace.message_text() == ""


def test_the_health_poll_runs_only_while_3d_is_shown(bench: Bench) -> None:
    workspace = bench.workspace
    assert workspace._health_timer.isActive() is False
    workspace.set_mode(SPLIT)
    assert workspace._health_timer.isActive() is True
    bench.host.health_now.frames_presented = 1
    bench.qtbot.waitUntil(lambda: workspace.view3d_state is View3DState.RUNNING, timeout=3000)
    workspace.set_mode(PLAN)
    assert workspace._health_timer.isActive() is False


def test_a_death_last_time_means_software_mode_with_one_notice_and_a_way_back(
        canvas: CanvasView, qtbot, tmp_path: Path) -> None:
    Init3DGuard(tmp_path, pid=7777).begin()        # a process that never came back
    bench = Bench(canvas, qtbot, tmp_path)
    workspace = bench.workspace
    workspace.set_mode(VIEW3D)
    assert bench.factory_calls == [True], "the engine is asked for the software adapter"
    assert bench.files() == sorted([COMPAT_NAME, marker_name(ME)])
    assert workspace.compat_text() == (
        "3D is running in compatibility mode (software rendering) because it did not "
        "start properly last time.")
    button = workspace._compat_button
    assert button.isVisible() and button.text() == "Try Hardware Next Time"
    bench.host.health_now.frames_presented = 1
    bench.poll()
    assert bench.files() == [COMPAT_NAME] and workspace.view3d_state is View3DState.RUNNING
    button.click()
    assert bench.files() == []
    assert not button.isVisible()
    assert workspace.compat_text() == (
        "Hardware rendering will be tried the next time the application starts.")
    assert bench.factory_calls == [True], "this session's view is not rebuilt"


def test_software_mode_kept_from_an_earlier_session_says_so_plainly(
        canvas: CanvasView, qtbot, tmp_path: Path) -> None:
    (tmp_path / COMPAT_NAME).write_text("", encoding="utf-8")
    bench = Bench(canvas, qtbot, tmp_path)
    bench.workspace.set_mode(SPLIT)
    assert bench.factory_calls == [True]
    assert bench.workspace.compat_text() == (
        "3D is running in compatibility mode (software rendering).")


def test_no_graphics_device_is_a_message_not_a_crash_and_not_a_retry_loop(bench: Bench) -> None:
    workspace = bench.workspace
    bed = bench.bed()
    workspace.set_mode(SPLIT)
    bench.settle()
    host = bench.host
    host.health_now.scene_graph_error = "Failed to initialize graphics backend for D3D11."
    bench.poll()
    assert workspace.view3d_state is View3DState.UNAVAILABLE
    assert host.closed is True and workspace.host is None and workspace.controller is None
    assert bench.files() == [], "Qt reported it and the process lives: not a crash"
    assert workspace.message_text() == (
        "3D is unavailable on this graphics device. The rest of the application is not "
        "affected.\n\nDetails: Failed to initialize graphics backend for D3D11.")
    assert workspace._health_timer.isActive() is False
    assert workspace.reset_view_action.isEnabled() is False
    # the 2D app goes on: edits, mode switches, a new document
    bench.commands.execute(MoveItemsCommand([bed], QPointF(20.0, 0.0)))
    for mode in (PLAN, VIEW3D, SPLIT, PLAN):
        workspace.set_mode(mode)
    workspace.document_changed()
    workspace.location_changed()
    bench.settle()
    assert bench.factory_calls == [False], "no second engine was built"
    # the one thing on offer: software rendering from the next start on
    workspace.set_mode(VIEW3D)
    button = workspace.pane.message_button
    assert button.isVisible() and button.text() == "Use Compatibility Mode Next Time"
    button.click()
    assert bench.files() == [COMPAT_NAME] and button.isEnabled() is False
    assert button.text() == "Compatibility mode will be used the next time the application starts."


def test_no_graphics_device_in_software_mode_offers_nothing_more(
        canvas: CanvasView, qtbot, tmp_path: Path) -> None:
    (tmp_path / COMPAT_NAME).write_text("", encoding="utf-8")
    bench = Bench(canvas, qtbot, tmp_path)
    bench.workspace.set_mode(VIEW3D)
    bench.host.health_now.scene_graph_error = "no device"
    bench.poll()
    assert bench.workspace.view3d_state is View3DState.UNAVAILABLE
    assert bench.workspace.pane.message_button.isVisible() is False
    assert bench.workspace.compat_text() == ""


def test_an_engine_that_cannot_be_built_is_a_message_and_can_be_tried_again(
        canvas: CanvasView, qtbot, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    bench = Bench(canvas, qtbot, tmp_path,
                  fail_first=ImportError("DLL load failed while importing QtQuick3D"))
    workspace = bench.workspace
    bed = bench.bed()
    with caplog.at_level("ERROR"):
        workspace.set_mode(VIEW3D)
    assert workspace.view3d_state is View3DState.FAILED
    assert workspace.message_text() == (
        "The 3D view could not be started. The rest of the application is not affected."
        "\n\nDetails: DLL load failed while importing QtQuick3D")
    assert bench.files() == [], "Python caught it: not a crash"
    assert workspace.controller is None and workspace.host is None
    assert any("could not be started" in record.message for record in caplog.records)
    workspace.set_mode(PLAN)
    bench.commands.execute(MoveItemsCommand([bed], QPointF(20.0, 0.0)))   # 2D is unaffected
    workspace.set_mode(VIEW3D)
    assert bench.factory_calls == [False], "switching modes is not a retry"
    button = workspace.pane.message_button
    assert button.text() == "Try Again"
    button.click()
    assert bench.factory_calls == [False, False]
    assert workspace.view3d_state is View3DState.STARTING and workspace.message_text() == ""
    bench.settle()
    assert bench.sink.item_ids() == (str(bed.item_id),)


def test_trouble_in_a_running_view_is_a_quiet_line_in_the_strip(bench: Bench) -> None:
    workspace = bench.workspace
    workspace.set_mode(VIEW3D)
    bench.settle()
    bench.host.health_now.qml_warning_count = 2
    bench.poll()
    assert workspace.status_text() == "The 3D view reported a problem. Details are in the log file."
    workspace.controller.failed.emit("the engine refused")
    assert workspace.status_text() == (
        "The 3D view could not be updated. It will try again with the next change.")
    bench.bed()
    bench.settle()
    assert workspace.status_text() == "", "a pass that went through clears it"


# ── what 3D could not build (acceptance criterion) ───────────────────────────


def test_a_refused_item_shows_a_count_a_list_and_selects_on_activation(bench: Bench) -> None:
    workspace = bench.workspace
    good, bad = bench.bed(), bench.bed(1500.0, 1500.0)
    bad.name = "North bed"
    bad.metadata[METADATA_KEY] = float("inf")
    workspace.set_mode(SPLIT)
    bench.settle()
    assert workspace.problems_text() == "1 object is not shown in 3D"
    assert workspace._problems_button.isVisible()
    workspace._problems_button.click()
    dialog = workspace.problems_dialog
    assert dialog is not None and dialog.isVisible() and not dialog.isModal()
    assert dialog.row_count() == 1
    assert dialog.row_text(0) == (
        "North bed (Raised Bed): one of its sizes is outside what the 3D view can show")
    assert not bad.isSelected()
    good.setSelected(True)
    dialog.activate_row(0)
    assert bad.isSelected() and not good.isSelected()

    second = bench.bed(2500.0, 500.0)
    second.metadata[METADATA_KEY] = 1e300
    bench.commands.stack_changed.emit()
    bench.settle()
    assert workspace.problems_text() == "2 objects are not shown in 3D"
    assert dialog.row_count() == 2, "the open list follows the plan"

    bad.metadata[METADATA_KEY] = 80.0            # the user fixes both
    second.metadata[METADATA_KEY] = 60.0
    bench.commands.stack_changed.emit()
    bench.settle()
    assert workspace.problems_text() == "" and not workspace._problems_button.isVisible()
    assert dialog.row_count() == 0


def test_every_reason_code_has_words_of_its_own(bench: Bench) -> None:
    from open_garden_planner.ui.view3d.problems_dialog import BUILD_FAILED, View3DProblemsDialog
    from open_garden_planner.ui.view3d.snapshot import SkipReason

    dialog = View3DProblemsDialog(bench.window)
    general = dialog.reason_text("a code nobody knows")
    texts = [dialog.reason_text(code) for code in [*[r.value for r in SkipReason], BUILD_FAILED]]
    assert general not in texts and len(set(texts)) == len(SkipReason) + 1
    assert dialog.kind_text("RAISED_BED") == "Raised Bed"
    assert dialog.kind_text("NOT_A_KIND") == "NOT_A_KIND"


# ── security add-on: a plan file is untrusted input (§8.11) ──────────────────

HOSTILE = '<b>x</b><img src="file:///C:/Windows/win.ini">'


def _rendered(rich: str) -> str:
    """What Qt's rich-text engine shows for a string (a tooltip's text)."""
    from PyQt6.QtGui import QTextDocument

    document = QTextDocument()
    document.setHtml(rich)
    return document.toPlainText()


def test_a_hostile_name_is_shown_as_its_characters_everywhere(bench: Bench) -> None:
    """An item named with markup, whose build fails with a message that quotes the
    name: the row, the tooltip and every label of the 3D pane show the literal
    text, and nothing renders it."""
    from PyQt6.QtCore import Qt as QtNamespace
    from PyQt6.QtWidgets import QLabel, QStyledItemDelegate

    from open_garden_planner.core.plain_text import TOOLTIP_MAX_CHARS

    workspace = bench.workspace
    bed = bench.bed()
    bed.name = HOSTILE
    workspace.set_mode(SPLIT)
    bench.settle()

    def broken(record: Any) -> tuple:
        raise ValueError(f"cannot build {record.name}")

    workspace.controller.sync.registry.register("RAISED_BED", broken, replace=True)
    workspace.controller.mark_dirty()
    bench.settle()
    assert workspace.problems_text() == "1 object is not shown in 3D"
    workspace.show_problems()
    dialog = workspace.problems_dialog
    row = dialog._list.item(0)

    # the row: plain text by the DEFAULT delegate, the name as its characters
    assert type(dialog._list.itemDelegate()) is QStyledItemDelegate
    assert dialog.row_text(0) == f"{HOSTILE} (Raised Bed): its 3D model could not be built"

    # the tooltip: Qt would sniff the raw detail for markup — it gets the escaped form
    raw_detail = f"ValueError: cannot build {HOSTILE}"
    tooltip = row.toolTip()
    assert "<img" not in tooltip and "<b>" not in tooltip
    assert _rendered(tooltip) == raw_detail
    assert len(_rendered(tooltip)) <= TOOLTIP_MAX_CHARS + 1
    # positive control: the same detail, unescaped, IS markup to Qt and loses its tags
    assert QtNamespace.mightBeRichText(raw_detail) is True
    assert _rendered(raw_detail) != raw_detail

    # every label of the pane and of the dialog is told its format: plain
    labels = [*workspace.findChildren(QLabel), *dialog.findChildren(QLabel)]
    assert len(labels) >= 4
    assert all(label.textFormat() == QtNamespace.TextFormat.PlainText for label in labels)


def test_a_huge_hostile_name_costs_a_capped_row_and_a_capped_tooltip(bench: Bench) -> None:
    from open_garden_planner.core.plain_text import ELLIPSIS, NAME_MAX_CHARS, TOOLTIP_MAX_CHARS

    workspace = bench.workspace
    bed = bench.bed()
    bed.name = "<table><tr><td>" * 100_000 + "\nsecond line"
    workspace.set_mode(SPLIT)
    bench.settle()

    def broken(record: Any) -> tuple:
        raise ValueError(record.name)

    workspace.controller.sync.registry.register("RAISED_BED", broken, replace=True)
    workspace.controller.mark_dirty()
    bench.settle()
    workspace.show_problems()
    dialog = workspace.problems_dialog
    row_text = dialog.row_text(0)
    assert row_text.startswith("<table><tr><td>") and "\n" not in row_text
    assert len(row_text) <= NAME_MAX_CHARS + 1 + len(" (Raised Bed): its 3D model could not be built")
    shown = _rendered(dialog._list.item(0).toolTip())
    assert len(shown) == TOOLTIP_MAX_CHARS + 1 and shown.endswith(ELLIPSIS)


def test_a_hostile_error_message_stays_text_in_the_message_that_replaces_the_view(
        canvas: CanvasView, qtbot, tmp_path: Path) -> None:
    from PyQt6.QtCore import Qt as QtNamespace

    from open_garden_planner.core.plain_text import ELLIPSIS, NOTICE_MAX_CHARS

    hostile = "<h1>Your licence expired</h1><a href='http://evil.example'>renew</a>" * 5_000
    bench = Bench(canvas, qtbot, tmp_path, fail_first=ImportError(hostile))
    bench.workspace.set_mode(VIEW3D)
    label = bench.workspace.pane.message_label
    assert label.textFormat() == QtNamespace.TextFormat.PlainText
    text = bench.workspace.message_text()
    assert "<h1>Your licence expired</h1>" in text, "the characters, not a headline"
    details = text.split("Details: ", 1)[1]
    assert len(details) == NOTICE_MAX_CHARS + 1 and details.endswith(ELLIPSIS)
    # the same for Qt's own report of a graphics failure
    bench.workspace.pane.message_button.click()          # "Try Again": the engine builds now
    bench.host.health_now.scene_graph_error = "<img src='file:///c:/x'>" + "x" * 5_000
    bench.poll()
    details = bench.workspace.message_text().split("Details: ", 1)[1]
    assert details.startswith("<img src='file:///c:/x'>") and len(details) == NOTICE_MAX_CHARS + 1


FORGED = "\n2026-10-12 00:00:00 ERROR root: FORGED LINE"


def _one_line_records(caplog: pytest.LogCaptureFixture, logger: str) -> list[str]:
    """The story's own records at WARNING and above — each must be ONE line: no line
    break in the message and no traceback attached (its last line is the raw message)."""
    records = [record for record in caplog.records
               if record.name == logger and record.levelno >= 30]
    for record in records:
        assert record.exc_info is None and record.exc_text is None, record.getMessage()
        assert len(record.getMessage().splitlines()) == 1, record.getMessage()
    return [record.getMessage() for record in records]


def test_a_failed_start_is_one_log_line_whatever_the_error_says(
        canvas: CanvasView, qtbot, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Security add-on: ``app.log`` is line-oriented and goes to support. The traceback
    is there for a developer who asks for DEBUG — not at the level the file records."""
    from open_garden_planner.ui.view3d import workspace as workspace_module

    bench = Bench(canvas, qtbot, tmp_path, fail_first=ImportError("no engine" + FORGED))
    with caplog.at_level("DEBUG", logger=workspace_module.__name__):
        bench.workspace.set_mode(VIEW3D)
        bench.workspace.pane.message_button.click()      # the engine builds now
        bench.host.health_now.scene_graph_error = "no device" + FORGED + "\u2028again"
        bench.poll()
    lines = _one_line_records(caplog, workspace_module.__name__)
    assert lines == [
        "The 3D view could not be started (ImportError: no engine 2026-10-12 00:00:00 ERROR "
        "root: FORGED LINE)",
        "3D is unavailable on this graphics device: no device 2026-10-12 00:00:00 ERROR "
        "root: FORGED LINE again",
    ]
    debug = [record for record in caplog.records
             if record.name == workspace_module.__name__ and record.levelno == 10]
    assert any(record.exc_info for record in debug), "the traceback: at DEBUG, and only there"


def test_the_start_guard_logs_one_line_for_a_folder_it_cannot_use(
        tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from open_garden_planner.ui.view3d import init_guard

    not_a_folder = tmp_path / "evil\u2028name"
    not_a_folder.write_text("x", encoding="utf-8")
    guard = Init3DGuard(not_a_folder)
    with caplog.at_level("DEBUG", logger=init_guard.__name__):
        guard.begin()
        guard.use_software_next_time()
        guard.try_hardware_next_time()
    lines = _one_line_records(caplog, init_guard.__name__)
    assert len(lines) >= 2 and all("cannot" in line for line in lines)
    assert all("\u2028" not in line for line in lines), "a path is quoted, not printed"


# ── teardown ─────────────────────────────────────────────────────────────────


def test_closing_with_a_start_still_pending_is_not_a_crash(bench: Bench) -> None:
    workspace = bench.workspace
    workspace.set_mode(VIEW3D)
    bench.settle()
    assert bench.files() == [marker_name(ME)]
    host = bench.host
    workspace.shutdown()
    assert bench.files() == [] and host.closed is True
    assert workspace.controller is None and workspace.host is None
    assert not workspace._camera_timer.isActive() and not workspace._health_timer.isActive()
    workspace.shutdown()                         # twice: nothing left to do
    bench.bed()                                  # the scene outlives the pipeline
    bench.settle()


def test_closing_without_ever_opening_3d_touches_nothing(bench: Bench) -> None:
    bench.workspace.shutdown()
    assert bench.files() == [] and bench.factory_calls == []


def test_the_split_position_is_kept_for_the_next_session(canvas: CanvasView, qtbot,
                                                         tmp_path: Path) -> None:
    from open_garden_planner.app.ui_state import UiStateStore
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    bench = Bench(canvas, qtbot, tmp_path, ui_state=UiStateStore())
    bench.workspace.set_mode(SPLIT)
    bench.settle()
    bench.workspace.splitter.setSizes([800, 400])
    bench.workspace._remember_split()
    kept = bench.workspace.splitter.sizes()
    assert kept[0] - kept[1] > 300, "a position nobody would take for the half-and-half default"
    bench.workspace.shutdown()

    # The next session: another window, another workspace, the same settings store —
    # the product's own path (``_apply_split``). Not a bare splitter that is never
    # shown: such a widget is not polished, and under an application style sheet (a
    # theme left by an earlier test) its handle has another width than a shown one's.
    folder = tmp_path / "next-session"
    folder.mkdir()
    second_view = CanvasView(CanvasScene(width_cm=5000, height_cm=3000))
    qtbot.addWidget(second_view)
    again = Bench(second_view, qtbot, folder, ui_state=UiStateStore())
    assert again.window.size() == bench.window.size()
    again.workspace.set_mode(SPLIT)
    again.settle()
    assert again.workspace.splitter.sizes() == kept


def test_a_plan_mode_close_does_not_overwrite_a_kept_split_position(
        canvas: CanvasView, qtbot, tmp_path: Path) -> None:
    from open_garden_planner.app import settings as app_settings
    from open_garden_planner.app.ui_state import UiStateStore

    bench = Bench(canvas, qtbot, tmp_path, ui_state=UiStateStore())
    bench.workspace.set_mode(SPLIT)
    bench.workspace.set_mode(PLAN)
    bench.workspace.shutdown()
    assert app_settings.create_qsettings().value("UiState/splitter_workspace") is None
