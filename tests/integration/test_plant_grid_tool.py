"""Plant-grid drafts only become real objects when confirmed."""

import pytest
from PyQt6.QtCore import QLineF, QPoint, QPointF, Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QDialog, QMessageBox, QSpinBox, QToolButton

from open_garden_planner.app.settings import AppSettings
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import PLANT_FILL_SCALE, CircleItem
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.resize_handle import (
    HANDLE_COLOR,
    ROTATION_HANDLE_COLOR,
    ROTATION_HANDLE_OFFSET,
)
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog
from open_garden_planner.ui.widgets.toolbar import MainToolbar


@pytest.mark.parametrize(("grouped", "angle"), [(False, 27), (True, 142)])
def test_plant_grid_preview_transform_commit_and_undo(qtbot, monkeypatch, grouped, angle):
    scene = CanvasScene(width_cm=1500, height_cm=1500)
    bed = RectangleItem(80, 80, 640, 600, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    view = CanvasView(scene)
    view.set_snap_enabled(False)
    qtbot.addWidget(view)
    view.resize(1000, 800)
    view.show()
    view.set_zoom(1.0)
    view.centerOn(300, 300)
    viewport = view.viewport()
    toolbar = MainToolbar()
    qtbot.addWidget(toolbar)
    toolbar.tool_selected.connect(view.set_active_tool)
    grid_button = toolbar._buttons[ToolType.PLANT_GRID]
    assert not grid_button.icon().isNull()
    grid_button.click()
    grid = view.active_tool
    assert grid.tool_type == ToolType.PLANT_GRID
    AppSettings().plant_grid_dimensions = (4, 5)
    picked = PlantSpeciesData("Malus domestica", "Apple", max_height_cm=500)

    def choose_dimensions(dialog):
        rows, cols = dialog.findChildren(QSpinBox)
        assert (rows.value(), cols.value()) == (4, 5)
        rows.setValue(2)
        cols.setValue(3)
        return QDialog.DialogCode.Accepted

    def choose_plant(dialog):
        dialog._selected_plant = picked
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", choose_dimensions)
    monkeypatch.setattr(PlantSearchDialog, "exec", choose_plant)

    def click(point):
        qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=view.mapFromScene(point))

    def drag(start, finish, *, handle=None, during=None):
        qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=view.mapFromScene(start))
        if handle is not None:
            assert grid._drag == handle
        qtbot.mouseMove(viewport, view.mapFromScene(finish))
        if during is not None:
            during()
        qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=view.mapFromScene(finish))

    click(QPointF(100, 100))
    assert AppSettings().plant_grid_dimensions == (2, 3)
    qtbot.mouseMove(viewport, view.mapFromScene(QPointF(400, 500)))
    click(QPointF(400, 500))
    assert grid._editing
    assert grid._controls.isVisible()
    preview = grid._controls.findChild(QToolButton, "eye")
    assert not preview.isChecked()
    previewed = []

    def paint_preview(_painter, rect, _kind, *, species):
        previewed.append((rect.width(), species))
        return True

    monkeypatch.setattr("open_garden_planner.ui.canvas.plant_grid_tool.paint_plant", paint_preview)
    preview.click()
    viewport.grab()
    # The preview sprite is as wide as the placed plant's sprite.
    assert previewed[-6:] == [(pytest.approx(grid._diameter * PLANT_FILL_SCALE), "Apple")] * 6
    preview.click()
    previewed.clear()
    viewport.grab()
    assert not previewed
    assert not any(isinstance(item, CircleItem) for item in scene.items())

    for zoom in (0.5, 1.0):
        view.set_zoom(zoom)
        view.centerOn(300, 300)
        handles = grid._handles()
        handle = QPointF(view.mapFromScene(handles["rotate"]))
        edge = QPointF(view.mapFromScene(handles[(0, -1)]))
        assert QLineF(handle, edge).length() == pytest.approx(ROTATION_HANDLE_OFFSET, abs=1)
        frame = viewport.grab()
        image = frame.toImage()
        dpr = frame.devicePixelRatio()
        for key, color in ((-1, HANDLE_COLOR), ("rotate", ROTATION_HANDLE_COLOR)):
            point = view.mapFromScene(handles[key if key == "rotate" else (key, -1)])
            assert image.pixelColor(round(point.x() * dpr), round(point.y() * dpr)) == color

    # A second finger takes over an in-progress grid move. Keep the draft
    # at its prior position while the view releases the synthetic press.
    start = grid._center
    press = view.mapFromScene(start)
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=press)
    qtbot.mouseMove(viewport, view.mapFromScene(start + QPointF(30, 0)))
    assert grid._center != start
    view._touch_mouse_press = (QPointF(press), Qt.MouseButton.LeftButton)
    view._cancel_touch_press()
    assert grid._editing and grid._center == start and grid._drag is None
    assert view.command_manager.undo_depth == 0

    def assert_live_move():
        assert grid._center == QPointF(350, 350)

    drag(QPointF(250, 300), QPointF(350, 350), handle="move", during=assert_live_move)
    assert grid._center == QPointF(350, 350)
    edge = grid._handles()[(1, 0)]
    drag(edge, edge + QPointF(100, 0))
    assert grid._width == pytest.approx(400)
    assert grid._width / 2 + grid._center.x() == pytest.approx(600)
    assert grid._center.x() - grid._width / 2 == pytest.approx(200)

    def unexpected_dialog(_dialog):
        pytest.fail("Transforming the grid should not open a dialog")

    monkeypatch.setattr(QDialog, "exec", unexpected_dialog)
    assert "diameter" in grid._handles()
    assert grid._size_slider.isHidden()
    grid._controls.findChild(QToolButton, "measure").click()
    assert grid._size_slider.isVisible()
    assert not grid._controls.findChild(QToolButton, "shrub").icon().isNull()
    grid._size_slider.setValue(160)
    assert grid._diameter == 160
    size_handle = grid._handles()["diameter"]
    increase = 20
    expected_size = grid._diameter + 2 * increase
    drag(size_handle, size_handle + QPointF(increase, 0), handle="diameter")
    assert grid._diameter == pytest.approx(expected_size, abs=1)
    assert grid._size_edited
    assert grid._size_slider.value() == round(grid._diameter)
    grid._controls.findChild(QToolButton, "measure").click()
    assert grid._size_slider.isHidden()
    assert "diameter" in grid._handles()

    rotate = grid._handles()["rotate"]
    offset = rotate - grid._center
    drag(rotate, grid._center + QTransform().rotate(angle).map(offset))
    assert grid._angle == pytest.approx(angle, abs=1)
    diameter = grid._diameter
    positions = [grid._transform().map(p) for p in grid._centers()]
    expected = {(p.x(), p.y()) for p in positions}
    confirm = grid._controls.findChild(QToolButton, "check")
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Cancel)
    confirm.click()
    assert grid._editing and grid._controls.isVisible()
    assert not any(isinstance(item, CircleItem) for item in scene.items())
    assert view.command_manager.undo_depth == 0

    response = QMessageBox.StandardButton.Yes if grouped else QMessageBox.StandardButton.No
    asked = []

    def answer(*args):
        asked.append(args)
        return response

    monkeypatch.setattr(QMessageBox, "question", answer)
    confirm.click()
    assert len(asked) == 1
    planted = [item for item in scene.items() if isinstance(item, CircleItem)]
    assert len(planted) == 6
    assert sum(isinstance(item, GroupItem) for item in scene.items()) == int(grouped)
    assert all(isinstance(item.parentItem(), GroupItem) == grouped for item in planted)
    centers = [item.mapToScene(item.rect().center()) for item in planted]
    for actual, target in zip(sorted((p.x(), p.y()) for p in centers), sorted(expected), strict=True):
        assert actual == pytest.approx(target)
    assert all(item.object_type == ObjectType.TREE and item.radius == diameter / 2 for item in planted)
    assert all(item.parent_bed_id == bed.item_id for item in planted)
    # The chosen size is a drawn footprint, never a measured current spread:
    # that field would switch on growth scaling and shrink the tree's height.
    assert all(
        "current_spread_cm" not in item.metadata.get("plant_instance", {}) for item in planted
    )
    # As after a single drop, the new plants (or their group) are selected.
    selected = scene.selectedItems()
    if grouped:
        assert len(selected) == 1 and isinstance(selected[0], GroupItem)
    else:
        assert set(selected) == set(planted)
    assert view.command_manager.undo_depth == 1
    view.command_manager.undo()
    assert not any(isinstance(item, CircleItem) for item in scene.items())
    assert not any(isinstance(item, GroupItem) for item in scene.items())
    view.command_manager.redo()
    assert len([item for item in scene.items() if isinstance(item, CircleItem)]) == 6
    assert sum(isinstance(item, GroupItem) for item in scene.items()) == int(grouped)

    view.set_active_tool(ToolType.PLANT_GRID)
    monkeypatch.setattr(QDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    click(QPointF(100, 100))
    click(QPointF(400, 500))
    grid._controls.findChild(QToolButton, "cross").click()
    assert view.active_tool.tool_type == ToolType.SELECT
    assert grid._origin is None
    assert grid._controls.isHidden()
    assert view.command_manager.undo_depth == 1


    view.set_active_tool(ToolType.PLANT_GRID)
    click(QPointF(100, 100))
    click(QPointF(400, 500))

    def replace_plan_during_confirmation(*_args):
        scene.clear()
        view.command_manager.clear()
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", replace_plan_during_confirmation)
    confirm.click()
    assert not any(isinstance(item, CircleItem) for item in scene.items())
    assert not any(isinstance(item, GroupItem) for item in scene.items())
    assert grid._controls.isHidden()
    assert view.command_manager.undo_depth == 0


# --- PR #1000 review: Esc, setup cancels, refusal, control strip, credentials ---


def _grid_view(qtbot):
    scene = CanvasScene(width_cm=1500, height_cm=1500)
    view = CanvasView(scene)
    view.set_snap_enabled(False)
    qtbot.addWidget(view)
    view.resize(1000, 800)
    view.show()
    view.set_zoom(1.0)
    view.centerOn(300, 300)
    return scene, view


def _click(qtbot, view, point):
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(point))


def _accept_setup(monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)

    def choose_plant(dialog):
        dialog._selected_plant = PlantSpeciesData("Lactuca sativa", "Lettuce", max_height_cm=30)
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(PlantSearchDialog, "exec", choose_plant)


def _start_draft(qtbot, view, *, editing=True):
    view.set_active_tool(ToolType.PLANT_GRID)
    grid = view.active_tool
    _click(qtbot, view, QPointF(100, 100))
    if editing:
        _click(qtbot, view, QPointF(400, 500))
        assert grid._editing and grid._controls.isVisible()
    else:
        assert grid._origin is not None and not grid._editing
    return grid


@pytest.mark.parametrize("editing", [False, True])
def test_escape_ends_the_draft_through_the_view_rule(qtbot, monkeypatch, editing):
    """Esc is the view's single rule (#829): the tool ends, the draft is gone."""
    scene, view = _grid_view(qtbot)
    _accept_setup(monkeypatch)
    grid = _start_draft(qtbot, view, editing=editing)
    view.setFocus()
    qtbot.keyClick(view, Qt.Key.Key_Escape)
    assert view.active_tool.tool_type == ToolType.SELECT
    assert grid._origin is None and not grid._editing
    assert grid._controls is None or grid._controls.isHidden()
    assert not any(isinstance(item, CircleItem) for item in scene.items())
    assert view.command_manager.undo_depth == 0


@pytest.mark.parametrize("cancelled", ["dimensions", "species"])
def test_cancelling_a_setup_dialog_leaves_no_draft(qtbot, monkeypatch, cancelled):
    scene, view = _grid_view(qtbot)
    asked_species = []

    def dimensions(_dialog):
        return QDialog.DialogCode.Rejected if cancelled == "dimensions" else QDialog.DialogCode.Accepted

    def species(_dialog):
        asked_species.append(True)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", dimensions)
    monkeypatch.setattr(PlantSearchDialog, "exec", species)
    view.set_active_tool(ToolType.PLANT_GRID)
    grid = view.active_tool
    _click(qtbot, view, QPointF(100, 100))
    assert asked_species == ([True] if cancelled == "species" else [])
    assert view.active_tool.tool_type == ToolType.SELECT
    assert grid._origin is None and grid._species is None
    assert not any(isinstance(item, CircleItem) for item in scene.items())
    assert view.command_manager.undo_depth == 0


def test_a_grid_outside_the_plan_is_refused_before_any_question(qtbot, monkeypatch):
    scene, view = _grid_view(qtbot)
    _accept_setup(monkeypatch)
    grid = _start_draft(qtbot, view)
    messages = []
    view.status_message.connect(messages.append)
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_args: pytest.fail("A refused grid must not ask about grouping"),
    )
    # Move the draft by its body until its first column lies left of the plan.
    start = grid._center
    finish = start - QPointF(300, 0)
    viewport = view.viewport()
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=view.mapFromScene(start))
    qtbot.mouseMove(viewport, view.mapFromScene(finish))
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=view.mapFromScene(finish))
    assert grid._center.x() == pytest.approx(finish.x())
    grid._controls.findChild(QToolButton, "check").click()
    assert messages and "inside the plan" in messages[-1]
    assert grid._editing and grid._controls.isVisible()
    assert not any(isinstance(item, CircleItem) for item in scene.items())
    assert view.command_manager.undo_depth == 0


def test_control_strip_follows_view_changes_but_never_moves_in_a_paint(qtbot, monkeypatch):
    """A paint only reads (ADR-082); zoom and scroll place the strip."""
    _scene, view = _grid_view(qtbot)
    _accept_setup(monkeypatch)
    grid = _start_draft(qtbot, view)
    controls = grid._controls
    controls.move(0, 0)
    view.viewport().grab()
    assert controls.pos() == QPoint(0, 0)
    view.set_zoom(0.5)
    assert controls.pos() != QPoint(0, 0)
    placed = controls.pos()
    view.horizontalScrollBar().setValue(view.horizontalScrollBar().value() + 40)
    assert controls.pos() != placed
    # A resize at a zoom with no scroll range re-centres the scene through the
    # view's alignment, which no scroll signal reports (round-2 review).
    view.set_zoom(0.2)
    placed = controls.pos()
    view.resize(1400, 1000)
    qtbot.waitUntil(lambda: controls.pos() != placed)


def test_a_pinch_while_the_extent_is_completed_returns_to_the_rubber_band(qtbot, monkeypatch):
    """The second finger takes over the press that fixed the extent."""
    _scene, view = _grid_view(qtbot)
    _accept_setup(monkeypatch)
    grid = _start_draft(qtbot, view, editing=False)
    viewport = view.viewport()
    corner = view.mapFromScene(QPointF(400, 500))
    qtbot.mouseMove(viewport, corner)
    extent = (QPointF(grid._center), grid._width, grid._height)
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=corner)
    assert grid._editing
    view._touch_mouse_press = (QPointF(corner), Qt.MouseButton.LeftButton)
    view._cancel_touch_press()
    assert not grid._editing and grid._origin is not None
    assert (grid._center, grid._width, grid._height) == extent
    assert grid._controls.isHidden()
    assert view.cursor().shape() == grid.cursor
    assert view.command_manager.undo_depth == 0


def test_species_picker_uses_the_preferences_credentials(qtbot, monkeypatch):
    """Plant Grid searches with the keys from Preferences, like the main search."""
    from types import SimpleNamespace

    from open_garden_planner.config import settings as settings_module

    for name in ("TREFLE_API_TOKEN", "PERENUAL_API_KEY", "PERMAPEOPLE_KEY_ID", "PERMAPEOPLE_KEY_SECRET"):
        monkeypatch.delenv(name, raising=False)
    # Build the view first: it imports the tool module lazily, and a tool
    # module imported after the patch below would bind the fake settings.
    _scene, view = _grid_view(qtbot)
    preferences = SimpleNamespace(
        trefle_api_token="token-from-preferences", perenual_api_key="",
        permapeople_key_id="", permapeople_key_secret="",
    )
    monkeypatch.setattr(settings_module, "get_settings", lambda: preferences)
    managers = []

    def capture(dialog):
        managers.append(dialog._api_manager)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(PlantSearchDialog, "exec", capture)
    view.set_active_tool(ToolType.PLANT_GRID)
    _click(qtbot, view, QPointF(100, 100))
    assert len(managers) == 1
    assert managers[0].configured_source_count == 1


def test_hover_takes_the_cursor_back_after_the_view_resets_it(qtbot, monkeypatch):
    """A middle-button pan release sets the tool cursor; the next hover restores the handle's."""
    _scene, view = _grid_view(qtbot)
    _accept_setup(monkeypatch)
    grid = _start_draft(qtbot, view)
    viewport = view.viewport()
    body = view.mapFromScene(grid._center + QPointF(20, 20))
    qtbot.mouseMove(viewport, body)
    assert grid._hover == "move"
    assert view.cursor().shape() == Qt.CursorShape.OpenHandCursor
    qtbot.mousePress(viewport, Qt.MouseButton.MiddleButton, pos=body)
    qtbot.mouseRelease(viewport, Qt.MouseButton.MiddleButton, pos=body)
    assert view.cursor().shape() != Qt.CursorShape.OpenHandCursor
    qtbot.mouseMove(viewport, body + QPoint(2, 2))
    assert grid._hover == "move"
    assert view.cursor().shape() == Qt.CursorShape.OpenHandCursor
