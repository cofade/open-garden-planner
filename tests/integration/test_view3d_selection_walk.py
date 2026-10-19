"""Selection sync, the info card and walk mode in the real main window (L1.8, §8.10).

A real ``GardenPlannerApp`` with the workspace switched on, its 3D engine replaced at
the documented seam (``Workspace.engine_factory``) by a ``RecordingSink`` and a host
whose ``pick`` answers from a script and whose view is a REAL ``QWindow`` in a window
container, the workspace's filters installed on it. Every click and key of the 3D view
is delivered by ``QTest`` to that window — keys to whichever window HAS the keyboard
(``QGuiApplication.focusWindow()``) — so they take Qt's own path through
``ShortcutOverride`` and the main window's shortcut map, the path the S key was lost on
(review 1). One user's session, end to end:

1. draw a raised bed with the real tool, drop a plant on it, build a wall with a
   60 cm garden gate — in Plan mode, where nothing 3D exists;
2. Split; select the bed with a real mouse click on the canvas — the engine is
   handed its ring, the card below the 3D view names it;
3. click the plant in the 3D view — the canvas selection, the property panel and
   the status bar are what a canvas click on the plant gives; the card says its
   species, its height and the bed it stands on;
4. lock the bed's layer and click the bed in 3D again — it cannot be selected, the
   click goes through it to the wall behind;
5. walk: the 3D view takes the keyboard; no single-key shortcut of the main window
   (derived from the live app) fires for a walker's key, S walks back instead of
   toggling Snap to Grid; through the gate, then against the wall — stopped at the
   masonry, not at the 5 cm line the plan drew;
6. leave: the orbit view is back, the plan was never touched.

What is drawn on screen by all of this is ``test_view3d_selection_render.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QAction, QGuiApplication, QShortcut
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractButton, QApplication, QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.commands import CreateItemCommand, SetLayerPropertyCommand
from open_garden_planner.core.measurements import format_length
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import RecordingSink
from open_garden_planner.core.scene3d.builders import walls
from open_garden_planner.core.scene3d.camera import FOV_DEG
from open_garden_planner.core.scene3d.selection import selection_of
from open_garden_planner.core.scene3d.walk import (
    EYE_HEIGHTS_CM,
    WALK_FOV_DEG,
    WALK_SPEED_CM_S,
    WALKER_RADIUS_CM,
    is_free,
)
from open_garden_planner.core.tools import ToolType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d.init_guard import Init3DGuard
from open_garden_planner.ui.view3d.walk_mode import WALKER_KEYS
from open_garden_planner.ui.view3d.workspace import Workspace, WorkspaceMode
from tests.integration.test_scene3d_plants import drop
from tests.integration.test_view3d_selection_workspace import PickHost

SPLIT = WorkspaceMode.SPLIT
BEGIN, COMMIT, SELECT = ("begin", None), ("commit", None), ("set_selection", None)
LEFT, NONE = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
PLAIN = Qt.KeyboardModifier.NoModifier
WALL_NORTH = 2000.0          # the wall runs east-west along this line
GATE_AT, GATE_CM = 2500.0, 60.0


@dataclass
class Hit:
    item_id: str
    behind: tuple[Any, ...] = ()


class Engines:
    def __init__(self) -> None:
        self.hosts: list[PickHost] = []
        self.sinks: list[RecordingSink] = []

    def factory(self, prefer_software: bool) -> tuple[PickHost, RecordingSink]:
        self.hosts.append(PickHost(prefer_software))
        self.sinks.append(RecordingSink())
        return self.hosts[-1], self.sinks[-1]

    @property
    def host(self) -> PickHost:
        return self.hosts[-1]

    @property
    def sink(self) -> RecordingSink:
        return self.sinks[-1]


@pytest.fixture()
def app3d(qtbot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[GardenPlannerApp, Engines]:
    monkeypatch.setenv("OGP_QUICK3D", "1")
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    engines = Engines()
    workspace = window._workspace
    assert isinstance(workspace, Workspace)
    workspace.engine_factory = engines.factory                       # THE SEAM
    workspace._guard = Init3DGuard(tmp_path / "log", is_running=lambda _pid: False)
    window.resize(1500, 900)
    window.show()
    qtbot.waitExposed(window)
    window.canvas_view.set_snap_enabled(False)
    return window, engines


class View3D:
    """The 3D view's input, delivered by Qt: clicks to the host's real window, keys to
    the window that has the keyboard."""

    def __init__(self, engines: Engines) -> None:
        self.engines = engines

    def click(self, *ray: Any, modifiers=PLAIN) -> None:
        ids = [str(item.item_id) for item in ray]
        self.engines.host.answer = Hit(ids[0], tuple(Hit(i) for i in ids[1:])) if ids else None
        QTest.mouseClick(self.engines.host.window, LEFT, modifiers, QPoint(300, 200))

    def key(self, key: Qt.Key, down: bool = True) -> bool:
        """``key`` pressed (or released) where the keyboard is; True when a filter of
        the workspace took it (it never reached the window's tail filter)."""
        target = QGuiApplication.focusWindow()
        assert target is not None, "no window has the keyboard"
        kind = "KeyPress" if down else "KeyRelease"
        tail = self.engines.host.tail.events
        before = sum(event.name == kind for event in tail)
        (QTest.keyPress if down else QTest.keyRelease)(target, key)
        return target is self.engines.host.window and sum(event.name == kind for event in tail) == before


def single_key_shortcuts(window: GardenPlannerApp) -> list[tuple[int, str, Any]]:
    """Every shortcut of the LIVE main window that is one key without a modifier:
    actions, buttons (the tool buttons carry the tool keys) and ``QShortcut``s —
    ``(key, name, the object)``. Derived, never listed from memory (review 1)."""
    found: list[tuple[int, str, Any]] = []

    def add(sequence: Any, name: str, owner: Any) -> None:
        if sequence.count() == 1 and sequence[0].keyboardModifiers() == PLAIN:
            found.append((int(sequence[0].key().value), name, owner))

    for action in window.findChildren(QAction):
        for sequence in action.shortcuts():
            add(sequence, f"action {action.text()!r}", action)
    for button in window.findChildren(QAbstractButton):
        add(button.shortcut(), f"button {button.toolTip() or button.text()!r}", button)
    for shortcut in window.findChildren(QShortcut):
        add(shortcut.key(), "QShortcut", shortcut)
    return found


def canvas_click(window: GardenPlannerApp, x: float, y: float) -> None:
    canvas = window.canvas_view
    point = canvas.mapFromScene(QPointF(x, y))
    QTest.mouseClick(canvas.viewport(), LEFT, PLAIN, QPoint(point.x(), point.y()))


def wall(scene: Any, commands: Any, west: float, east: float, layer: Layer) -> PolylineItem:
    made = PolylineItem([QPointF(west, WALL_NORTH), QPointF(east, WALL_NORTH)],
                        object_type=ObjectType.WALL, layer_id=layer.id)
    commands.execute(CreateItemCommand(scene, made, "wall"))
    made.setSelected(False)
    return made


def test_select_in_2d_click_in_3d_lock_the_layer_and_walk_through_the_gate(
        app3d, qtbot, mouse_event) -> None:
    window, engines = app3d
    workspace, canvas = window._workspace, window.canvas_view
    scene, commands = window.canvas_scene, canvas.command_manager
    view3d = View3D(engines)

    # ── 1. the plan, drawn in Plan mode: nothing 3D exists ───────────────────
    canvas.set_active_tool(ToolType.RAISED_BED)
    tool = canvas.tool_manager.active_tool
    tool.mouse_press(mouse_event, QPointF(600.0, 500.0))
    tool.mouse_move(mouse_event, QPointF(1000.0, 800.0))
    tool.mouse_release(mouse_event, QPointF(1000.0, 800.0))
    canvas.set_active_tool(ToolType.SELECT)
    bed = next(item for item in scene.items() if isinstance(item, RectangleItem))
    bed.name = "Kitchen bed"
    herb = drop(canvas, "PERENNIAL:species=lavender", QPointF(800.0, 650.0))
    assert herb.parent_bed_id == bed.item_id, "dropped on the bed: it stands on its soil"
    walls_layer = Layer(name="Walls")
    scene.add_layer(walls_layer)
    half = GATE_CM / 2.0
    west_wall = wall(scene, commands, 200.0, GATE_AT - half, walls_layer)
    east_wall = wall(scene, commands, GATE_AT + half, 4800.0, walls_layer)
    scene.clearSelection()
    bed_id, herb_id, wall_id = str(bed.item_id), str(herb.item_id), str(west_wall.item_id)
    assert workspace.controller is None and workspace.info_card is None and workspace.walk is None

    # ── 2. Split; a real click on the canvas selects the bed ─────────────────
    workspace.mode_actions()[2].trigger()
    controller = workspace.controller
    qtbot.waitUntil(lambda: controller.apply_count >= 1 and not controller.dirty, timeout=5000)
    sink, card = engines.sink, workspace.info_card
    assert set(sink.item_ids()) == {bed_id, herb_id, wall_id, str(east_wall.item_id)}
    assert sink.selection.ids == () and not card.isVisible()
    qtbot.wait(40)
    sink.clear_calls()
    canvas_click(window, 650.0, 760.0)                 # on the bed, beside the plant
    assert scene.selectedItems() == [bed]
    qtbot.waitUntil(lambda: sink.selection.ids == (bed_id,), timeout=3000)
    assert sink.ops() == [BEGIN, SELECT, COMMIT], "the ring, and no model touched"
    assert sink.selection == selection_of(controller.sync.records, [bed_id])
    record = controller.sync.records[bed_id]
    assert card.isVisible() and card.title() == "Kitchen bed"
    assert card.value("Type:") == "Raised Bed"
    assert card.value("Height:") == format_length(record.height_cm)
    assert card.value("Size:") == "4.00 m × 3.00 m"
    status_for_bed = window.selection_label.text()
    assert status_for_bed.startswith("1 object") and window.properties_panel._current_items == [bed]

    # ── 3. a click in the 3D view selects the plant, as a canvas click would ──
    undo_before, dirty_before = commands.can_undo, window._project_manager.is_dirty
    stack_before = len(commands._undo_stack)  # noqa: SLF001 - "no command was pushed"
    view3d.click(herb, bed)                            # the ray meets the plant, then its bed
    assert scene.selectedItems() == [herb]
    assert engines.host.frames_taken == ["pick"], "one click: one pick"
    qtbot.waitUntil(lambda: sink.selection.ids == (herb_id,), timeout=3000)
    plant = controller.sync.records[herb_id]
    assert plant.transform.base_cm > 0.0, "the ring is drawn at the bed's soil, where the plant stands"
    assert float(sink.selection.ring.positions[:, 2].min()) == pytest.approx(plant.transform.base_cm + 1.0)
    species = herb.metadata["plant_species"]
    assert species["common_name"] == "Lavender" and herb.plant_species == "lavender"
    assert card.title() == "Perennial" and card.value("Species:") == "Lavender", (
        "the name a gardener reads, not the key the sprite is looked up by")
    assert card.value("Scientific name:") == species["scientific_name"] != ""
    assert card.value("Bed:") == "Kitchen bed"
    assert card.value("Canopy diameter:") == format_length(2.0 * float(plant.params["radius_cm"]))
    assert card.value("Height:") == ("not known" if plant.height_cm is None
                                     else format_length(plant.height_cm))
    in_3d = (window.selection_label.text(), list(window.properties_panel._current_items))
    scene.clearSelection()
    canvas_click(window, 800.0, 650.0)                 # the SAME selection made on the canvas
    assert scene.selectedItems() == [herb]
    assert in_3d == (window.selection_label.text(), list(window.properties_panel._current_items)), (
        "the status bar and the property panel cannot tell the two clicks apart")
    assert (commands.can_undo, window._project_manager.is_dirty) == (undo_before, dirty_before)
    assert len(commands._undo_stack) == stack_before, "a selection is no edit"  # noqa: SLF001
    view3d.click()                                     # the ground
    assert scene.selectedItems() == [] and not card.isVisible()
    assert window.selection_label.text() == "No selection"

    # ── 4. lock the bed's layer: not selectable from 3D; the click goes through ─
    bed_layer = scene.get_layer_by_id(bed.layer_id)
    commands.execute(SetLayerPropertyCommand(scene, bed_layer, "locked", False, True))
    qtbot.wait(60)
    assert bed_id in sink.item_ids(), "a locked layer is still SHOWN in 3D"
    view3d.click(bed)                                  # nothing behind it
    assert scene.selectedItems() == [] and not card.isVisible()
    view3d.click(herb, bed, west_wall)                 # both locked; the wall behind is not
    assert scene.selectedItems() == [west_wall]
    qtbot.waitUntil(lambda: sink.selection.ids == (wall_id,), timeout=3000)
    assert card.value("Type:") == "Wall" and card.value("Length:") == format_length(GATE_AT - half - 200.0)
    commands.undo()                                    # the lock, undone like any edit
    view3d.click(bed)
    assert scene.selectedItems() == [bed]

    # ── 5. walk: through the gate, then against the wall ─────────────────────
    camera = workspace.camera
    qtbot.waitUntil(lambda: not camera.moving, timeout=5000)
    camera._pose = camera._goal = type(camera.pose)(   # noqa: SLF001 - the user looked here:
        (GATE_AT, WALL_NORTH - 400.0), 1500.0, 0.0, 35.0)   # south of the gate, facing north
    workspace._apply_camera()  # noqa: SLF001
    orbit_pose, orbit_call = camera.pose, engines.host.cameras[-1]
    dirty, stack = window._project_manager.is_dirty, len(commands._undo_stack)  # noqa: SLF001
    # the CONTROL: not walking, a key pressed into the 3D view is the main window's
    # shortcut there (S: Snap to Grid) — the path the walker's S was lost on is live
    engines.host.focus()
    qtbot.waitUntil(lambda: QGuiApplication.focusWindow() is engines.host.window, timeout=3000)
    qtbot.wait(100)
    snap = window.snap_action.isChecked()
    QTest.keyClick(QGuiApplication.focusWindow(), Qt.Key.Key_S)
    assert window.snap_action.isChecked() is not snap, "control: S toggles Snap to Grid here"
    QTest.keyClick(QGuiApplication.focusWindow(), Qt.Key.Key_S)
    assert window.snap_action.isChecked() is snap
    canvas.setFocus()                                  # the plan has the keyboard again
    qtbot.waitUntil(lambda: QApplication.focusWidget() is canvas, timeout=3000)
    qtbot.wait(100)

    focus_calls = engines.host.focus_calls
    workspace.walk_action.trigger()
    walk = workspace.walk
    assert workspace.walking and len(engines.host.filters) == 2
    qtbot.waitUntil(lambda: QGuiApplication.focusWindow() is engines.host.window, timeout=3000)
    qtbot.wait(100)                                    # the platform's focus events
    assert engines.host.focus_calls == focus_calls + 1, "Walk gave the 3D view the keyboard"
    now = [1000.0]
    walk.clock = lambda: now[0]
    start = walk.state
    assert start.shown == (GATE_AT, WALL_NORTH - 400.0) and start.yaw_deg == 0.0
    assert engines.host.cameras[-1] == ((GATE_AT, WALL_NORTH - 400.0, EYE_HEIGHTS_CM[0]),
                                        (GATE_AT, WALL_NORTH - 300.0, EYE_HEIGHTS_CM[0]), WALK_FOV_DEG)
    assert set(walk.world.solid_ids) == {bed_id, wall_id, str(east_wall.item_id)}, (
        "the bed and the two walls block; the lavender does not")

    def hold(key: Qt.Key, seconds: float) -> None:
        """Hold a key for ``seconds`` of the walker's clock, a 60 Hz frame at a time."""
        assert view3d.key(key) is True
        for _ in range(round(seconds * 60)):
            now[0] += 1.0 / 60.0
            walk.step()
        assert view3d.key(key, down=False) is True

    # every walker's key against every single-key shortcut of the live main window
    shortcuts = single_key_shortcuts(window)
    clashing = [(key, name, owner) for key, name, owner in shortcuts
                if Qt.Key(key) in WALKER_KEYS]
    print(f"\n[single-key shortcuts] {len(shortcuts)} in the main window "
          f"({sorted(Qt.Key(key).name for key, _name, _owner in shortcuts)}); on a walker's key: "
          f"{sorted({name for _key, name, _owner in clashing})}")
    assert any(owner is window.snap_action for _key, _name, owner in clashing), (
        "the derivation finds the shortcut the review reproduced")
    fired: list[str] = []
    for _key, name, owner in clashing:
        signal = owner.activated if isinstance(owner, QShortcut) else (
            owner.triggered if isinstance(owner, QAction) else owner.pressed)
        signal.connect(lambda *_a, label=name: fired.append(label))
    tool, snap = canvas.tool_manager.active_tool_type, window.snap_action.isChecked()
    for key in sorted(WALKER_KEYS - {Qt.Key.Key_Shift, Qt.Key.Key_Escape}, key=int):   # all eight
        here = walk.state.shown
        hold(key, 0.2)
        assert walk.state.shown != here, f"{key.name} walks"
        hold({Qt.Key.Key_W: Qt.Key.Key_S, Qt.Key.Key_S: Qt.Key.Key_W, Qt.Key.Key_A: Qt.Key.Key_D,
              Qt.Key.Key_D: Qt.Key.Key_A, Qt.Key.Key_Up: Qt.Key.Key_Down,
              Qt.Key.Key_Down: Qt.Key.Key_Up, Qt.Key.Key_Left: Qt.Key.Key_Right,
              Qt.Key.Key_Right: Qt.Key.Key_Left}[key], 0.2)   # and back
        assert walk.state.shown == pytest.approx(here, abs=1e-6)
    assert fired == [], "no shortcut of the main window fired for a walker's key"
    assert canvas.tool_manager.active_tool_type == tool and window.snap_action.isChecked() is snap
    start = walk.state
    hold(Qt.Key.Key_S, 1.0)                            # the review's key: a second back
    assert walk.state.shown[1] == pytest.approx(start.shown[1] - WALK_SPEED_CM_S, abs=1e-6)
    assert window.snap_action.isChecked() is snap and fired == []
    hold(Qt.Key.Key_W, 1.0)
    assert walk.state.shown == pytest.approx(start.shown, abs=1e-6)

    hold(Qt.Key.Key_W, 6.0)                            # 8.4 m north: the gate is 4 m ahead
    through = walk.state.shown
    assert through[0] == pytest.approx(GATE_AT, abs=0.5), "straight through the middle"
    assert through[1] == pytest.approx(WALL_NORTH - 400.0 + WALK_SPEED_CM_S * 6.0, abs=1.0)
    assert through[1] > WALL_NORTH + 300.0, "a 60 cm garden gate lets the walker pass"
    assert engines.host.cameras[-1][0][:2] == through

    hold(Qt.Key.Key_D, 2.0)                            # 2.8 m to the east, north of the east wall
    hold(Qt.Key.Key_S, 8.0)                            # back south: into the wall
    stopped = walk.state.shown
    record = controller.sync.records[str(east_wall.item_id)]
    masonry = walls.body_thickness_cm(record) / 2.0 + walls.COPING_OVERSAIL_CM
    assert masonry == 19.0 and (record.path_width_cm or 0.0) / 2.0 < 5.0, (
        "the plan drew a line of a few centimetres; the wall is built 30 cm thick, coping 38")
    assert stopped[1] == pytest.approx(WALL_NORTH + masonry + WALKER_RADIUS_CM, abs=0.05), (
        "stopped by what is SHOWN: the coping's edge, not the drawn stroke")
    assert is_free(walk.world, *stopped)
    hold(Qt.Key.Key_A, 1.0)                            # along the wall: it slides
    assert walk.state.shown[1] == pytest.approx(stopped[1], abs=1e-6)
    assert walk.state.shown[0] == pytest.approx(stopped[0] - WALK_SPEED_CM_S, abs=1e-6)

    # … and a click still selects while walking
    view3d.click(east_wall)
    assert scene.selectedItems() == [east_wall] and workspace.walking

    # ── 6. leave: the orbit view is back, the plan was never touched ─────────
    assert view3d.key(Qt.Key.Key_Escape) is True
    assert not workspace.walking and not workspace.walk_action.isChecked()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is canvas, timeout=3000)
    assert canvas.tool_manager.active_tool_type == tool, "Escape left walk mode, not the tool"
    assert camera.pose is orbit_pose and engines.host.cameras[-1] == orbit_call
    assert engines.host.cameras[-1][2] == FOV_DEG
    assert window._project_manager.is_dirty == dirty
    assert len(commands._undo_stack) == stack  # noqa: SLF001
    assert engines.host.frames_taken == ["pick"] * 6, (
        "six clicks in the 3D view, six picks: no walking, looking or selecting took a frame")


def test_a_twenty_centimetre_gap_does_not_let_the_walker_through(app3d, qtbot) -> None:
    """Gate G5 in the real app: the same wall with a 20 cm gap."""
    window, engines = app3d
    workspace, scene = window._workspace, window.canvas_scene
    commands = window.canvas_view.command_manager
    layer = scene.active_layer
    wall(scene, commands, 200.0, GATE_AT - 10.0, layer)
    wall(scene, commands, GATE_AT + 10.0, 4800.0, layer)
    scene.clearSelection()
    workspace.set_mode(SPLIT)
    controller = workspace.controller
    qtbot.waitUntil(lambda: controller.apply_count >= 1 and not controller.dirty, timeout=5000)
    camera = workspace.camera
    camera._pose = camera._goal = type(camera.pose)(   # noqa: SLF001
        (GATE_AT, WALL_NORTH - 300.0), 1500.0, 0.0, 35.0)
    assert workspace.set_walking(True) is True
    walk = workspace.walk
    now = [0.0]
    walk.clock = lambda: now[0]
    view3d = View3D(engines)
    view3d.key(Qt.Key.Key_W)
    for _ in range(600):
        now[0] += 1.0 / 60.0
        walk.step()
    assert walk.state.shown[1] < WALL_NORTH - 15.0, "it never gets past the near face"
    assert is_free(walk.world, *walk.state.shown)


def test_closing_the_app_while_walking_with_a_selection_is_quiet(app3d, qtbot) -> None:
    window, engines = app3d
    workspace, scene = window._workspace, window.canvas_scene
    bed = RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                        layer_id=scene.active_layer.id)
    window.canvas_view.command_manager.execute(CreateItemCommand(scene, bed, "bed"))
    workspace.set_mode(SPLIT)
    controller = workspace.controller
    qtbot.waitUntil(lambda: controller.apply_count >= 1 and not controller.dirty, timeout=5000)
    bed.setSelected(True)
    assert workspace.set_walking(True) is True
    View3D(engines).key(Qt.Key.Key_W)
    qtbot.wait(40)
    window._project_manager.mark_clean()
    window.close()
    assert workspace.controller is None and workspace.walk is None and not workspace.walking
    assert engines.host.closed is True
    scene.clearSelection()                             # late signals reach nobody
