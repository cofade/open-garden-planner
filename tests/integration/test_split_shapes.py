"""End-to-end split-along-a-line workflow (#664).

The tool is started from the shape's context menu, takes two snapped scene
points, previews the line and pieces, and replaces the source with polygons in
one undo step. The source's layer, look, fill transform, label state and
metadata survive; linked, constrained, planted, grouped and tracked shapes are
refused before any mutation.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainterPath
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core.constraints import AnchorRef, ConstraintType
from open_garden_planner.core.fill_patterns import FillPattern, FillTransform
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.shape_boolean import _polygon_area, item_to_painter_path
from open_garden_planner.core.shape_split import split_item_into_local_polygons
from open_garden_planner.core.tools import ToolType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    GroupItem,
    PolygonItem,
    RectangleItem,
)


def _add(canvas, item, *, select: bool = True):
    scene = canvas.scene()
    item.layer_id = scene.active_layer.id
    scene.addItem(item)
    if select:
        scene.clearSelection()
        item.setSelected(True)
    return item


def _add_pieces(scene) -> list[PolygonItem]:
    return [item for item in scene.items() if isinstance(item, PolygonItem)]


def _split(canvas, source, first: QPointF, second: QPointF, mouse_event) -> None:
    assert canvas.start_split_shape(source) is True
    tool = canvas._split_tool
    assert tool.mouse_press(mouse_event, first) is True
    assert tool.mouse_press(mouse_event, second) is True


def test_a_vertical_cut_keeps_look_metadata_and_is_one_undo_step(
    canvas, mouse_event
) -> None:
    scene = canvas.scene()
    source = RectangleItem(
        100, 100, 200, 100, object_type=ObjectType.TERRACE_PATIO
    )
    source.fill_color = QColor("#123456")
    source.stroke_color = QColor("#654321")
    source.fill_pattern = FillPattern.GRAVEL
    source.fill_transform = FillTransform(
        angle_deg=25.0, scale=1.5, offset_x_cm=4.0, offset_y_cm=-3.0
    )
    source.metadata["future_field"] = {"keep": True}
    source.label_visible = False
    source.area_label_visible = False
    source._setup_styling()
    _add(canvas, source)
    original_rank = source.stack_order
    before = ProjectManager().snapshot_dict(scene)["objects"]

    _split(canvas, source, QPointF(200, 0), QPointF(200, 400), mouse_event)

    pieces = _add_pieces(scene)
    assert len(pieces) == 2
    assert source.scene() is None
    for piece in pieces:
        assert piece.layer_id == source.layer_id
        assert piece.object_type is ObjectType.TERRACE_PATIO
        assert piece.fill_color == QColor("#123456")
        assert piece.stroke_color == QColor("#654321")
        assert piece.fill_pattern is FillPattern.GRAVEL
        assert piece.fill_transform == source.fill_transform
        assert piece.brush().transform() == source.brush().transform()
        assert piece.metadata["future_field"] == {"keep": True}
        assert piece.label_visible is False
        assert piece.stack_order == original_rank
    assert canvas.command_manager.undo_depth == 1

    canvas.command_manager.undo()
    assert source.scene() is scene
    assert all(piece.scene() is None for piece in pieces)
    assert ProjectManager().snapshot_dict(scene)["objects"] == before

    canvas.command_manager.redo()
    assert len(_add_pieces(scene)) == 2


def test_the_cad_toolbar_starts_a_scene_wide_cut(qtbot, canvas) -> None:
    from open_garden_planner.ui.widgets.constraint_toolbar import ConstraintToolbar

    # A selection is deliberately present: Split must no longer arm it, because
    # the toolbar tool cuts every shape the two-point line crosses (#664).
    _add(canvas, RectangleItem(100, 100, 200, 100))
    toolbar = ConstraintToolbar()
    qtbot.addWidget(toolbar)
    toolbar.tool_selected.connect(canvas.set_active_tool)
    button = toolbar._buttons[ToolType.SPLIT]
    assert button.shortcut().toString() == "Shift+S"
    assert not button.icon().isNull()
    messages: list[str] = []
    canvas.status_message.connect(messages.append)

    button.click()
    QTest.qWait(10)

    assert canvas.tool_manager.active_tool_type is ToolType.SPLIT
    assert canvas._split_tool.source_id is None
    assert messages[-1] == "Click the first point of the cutting line. Esc cancels."


def test_the_cad_toolbar_stays_active_without_a_selection(qtbot, canvas) -> None:
    from open_garden_planner.ui.widgets.constraint_toolbar import ConstraintToolbar

    canvas.scene().clearSelection()
    toolbar = ConstraintToolbar()
    qtbot.addWidget(toolbar)
    toolbar.tool_selected.connect(canvas.set_active_tool)
    messages: list[str] = []
    canvas.status_message.connect(messages.append)

    toolbar._buttons[ToolType.SPLIT].click()
    QTest.qWait(10)

    assert messages[-1] == "Click the first point of the cutting line. Esc cancels."
    assert canvas.tool_manager.active_tool_type is ToolType.SPLIT
    assert canvas._split_tool.source_id is None


def test_the_cad_toolbar_splits_every_shape_the_line_crosses(
    qtbot, canvas, mouse_event
) -> None:
    from open_garden_planner.ui.widgets.constraint_toolbar import ConstraintToolbar

    first = _add(canvas, RectangleItem(100, 100, 200, 100), select=False)
    second = _add(canvas, RectangleItem(400, 100, 200, 100), select=False)
    untouched = _add(canvas, RectangleItem(900, 100, 200, 100), select=False)
    canvas.scene().clearSelection()
    toolbar = ConstraintToolbar()
    qtbot.addWidget(toolbar)
    toolbar.tool_selected.connect(canvas.set_active_tool)
    toolbar._buttons[ToolType.SPLIT].click()
    tool = canvas._split_tool

    assert tool.source_id is None
    assert tool.mouse_press(mouse_event, QPointF(0, 150)) is True
    assert tool.mouse_press(mouse_event, QPointF(700, 150)) is True

    pieces = _add_pieces(canvas.scene())
    assert len(pieces) == 4
    assert first.scene() is None
    assert second.scene() is None
    assert untouched.scene() is canvas.scene()
    assert canvas.command_manager.undo_depth == 1


def test_real_viewport_clicks_split_every_crossed_shape(qtbot, canvas) -> None:
    """The gesture works through the view's real mouse dispatch, not only calls."""
    canvas.resize(800, 600)
    canvas.show()
    canvas.centerOn(QPointF(350, 150))
    qtbot.wait(50)
    first = _add(canvas, RectangleItem(100, 100, 200, 100), select=False)
    second = _add(canvas, RectangleItem(400, 100, 200, 100), select=False)
    canvas.set_active_tool(ToolType.SPLIT)

    for scene_point in (QPointF(0, 150), QPointF(700, 150)):
        viewport_point = canvas.mapFromScene(scene_point)
        QTest.mouseClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_point,
        )
        qtbot.wait(10)

    assert first.scene() is None
    assert second.scene() is None
    assert len(_add_pieces(canvas.scene())) == 4
    assert canvas.command_manager.undo_depth == 1


def test_shift_constrains_the_line_to_45_degree_steps(canvas, mouse_event) -> None:
    shift = MagicMock(spec=QMouseEvent)
    shift.modifiers.return_value = Qt.KeyboardModifier.ShiftModifier
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool
    assert tool.mouse_press(mouse_event, QPointF(0, 0)) is True

    assert tool._end(QPointF(100, 30), shift) == QPointF(
        math.hypot(100, 30), 0
    )
    vertical = tool._end(QPointF(30, 100), shift)
    assert vertical.x() == pytest.approx(0.0)
    assert vertical.y() == pytest.approx(math.hypot(30, 100))


def test_a_scene_wide_cut_undoes_all_sources_in_one_step(canvas, mouse_event) -> None:
    scene = canvas.scene()
    first = _add(canvas, RectangleItem(100, 100, 200, 100), select=False)
    second = _add(canvas, RectangleItem(400, 100, 200, 100), select=False)
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool

    tool.mouse_press(mouse_event, QPointF(0, 150))
    tool.mouse_press(mouse_event, QPointF(700, 150))
    assert canvas.command_manager.undo_depth == 1

    canvas.command_manager.undo()

    assert first.scene() is scene
    assert second.scene() is scene
    assert _add_pieces(scene) == []
    assert canvas.command_manager.undo_depth == 0


def test_a_shape_on_the_lines_extension_is_not_split(canvas, mouse_event) -> None:
    target = _add(canvas, RectangleItem(900, 100, 200, 100), select=False)
    messages: list[str] = []
    canvas.status_message.connect(messages.append)
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool

    # Collinear with the shape but nowhere near it: the DRAWN segment decides.
    tool.mouse_press(mouse_event, QPointF(0, 150))
    tool.mouse_press(mouse_event, QPointF(500, 150))

    assert target.scene() is canvas.scene()
    assert _add_pieces(canvas.scene()) == []
    assert canvas.command_manager.undo_depth == 0
    assert messages[-1] == (
        "The cutting line must cross a closed shape. Choose another second point."
    )


def test_a_line_starting_inside_a_shape_still_splits_it(canvas, mouse_event) -> None:
    source = _add(canvas, RectangleItem(100, 100, 400, 200), select=False)
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool

    # One pick inside the shape, one outside: the supporting axis still divides it.
    tool.mouse_press(mouse_event, QPointF(200, 200))
    tool.mouse_press(mouse_event, QPointF(800, 200))

    assert source.scene() is None
    assert len(_add_pieces(canvas.scene())) == 2
    assert canvas.command_manager.undo_depth == 1


def test_a_scene_wide_cut_skips_a_grouped_shape(canvas, mouse_event) -> None:
    scene = canvas.scene()
    first = _add(canvas, RectangleItem(100, 100, 200, 100), select=True)
    second = RectangleItem(400, 100, 200, 100)
    _add(canvas, second, select=True)
    first.setSelected(True)
    second.setSelected(True)
    canvas.group_selected()
    depth = canvas.command_manager.undo_depth
    messages: list[str] = []
    canvas.status_message.connect(messages.append)
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool

    tool.mouse_press(mouse_event, QPointF(0, 150))
    tool.mouse_press(mouse_event, QPointF(700, 150))

    assert first.scene() is scene
    assert second.scene() is scene
    assert _add_pieces(scene) == []
    assert canvas.command_manager.undo_depth == depth
    assert messages[-1] == "Nothing was split: Ungroup the shape before splitting it"


def test_a_scene_wide_cut_skips_a_plant_but_splits_the_bed(
    canvas, mouse_event
) -> None:
    bed = _add(canvas, RectangleItem(100, 100, 400, 100), select=False)
    plant = _add(
        canvas,
        CircleItem(300, 150, 40, object_type=ObjectType.TREE),
        select=False,
    )
    messages: list[str] = []
    canvas.status_message.connect(messages.append)
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool

    tool.mouse_press(mouse_event, QPointF(0, 150))
    tool.mouse_press(mouse_event, QPointF(600, 150))

    assert bed.scene() is None
    assert plant.scene() is canvas.scene()
    assert len(_add_pieces(canvas.scene())) == 2
    assert "1 crossed object could not be split" in messages[-1]
    assert canvas.command_manager.undo_depth == 1


def test_a_line_crossing_only_a_plant_explains_why_nothing_split(
    canvas, mouse_event
) -> None:
    plant = _add(
        canvas,
        CircleItem(300, 150, 40, object_type=ObjectType.TREE),
        select=False,
    )
    messages: list[str] = []
    canvas.status_message.connect(messages.append)
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool

    tool.mouse_press(mouse_event, QPointF(0, 150))
    tool.mouse_press(mouse_event, QPointF(600, 150))

    assert plant.scene() is canvas.scene()
    assert canvas.command_manager.undo_depth == 0
    assert messages[-1] == "Nothing was split: Plants and linked objects cannot be split"


def test_the_tool_stays_armed_for_another_cut_after_a_scene_wide_split(
    canvas, mouse_event
) -> None:
    _add(canvas, RectangleItem(100, 100, 200, 100), select=False)
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool

    tool.mouse_press(mouse_event, QPointF(0, 150))
    tool.mouse_press(mouse_event, QPointF(400, 150))

    assert canvas.tool_manager.active_tool_type is ToolType.SPLIT
    assert tool._start is None

    # The context-menu action is one-shot and returns to Select.
    source = _add(canvas, RectangleItem(600, 300, 200, 100), select=False)
    assert canvas.start_split_shape(source) is True
    tool.mouse_press(mouse_event, QPointF(500, 350))
    tool.mouse_press(mouse_event, QPointF(900, 350))
    assert canvas.tool_manager.active_tool_type is ToolType.SELECT


def test_a_scoped_context_menu_split_leaves_other_crossed_shapes_alone(
    canvas, mouse_event
) -> None:
    chosen = _add(canvas, RectangleItem(100, 100, 200, 100), select=False)
    neighbour = _add(canvas, RectangleItem(400, 100, 200, 100), select=False)
    assert canvas.start_split_shape(chosen) is True
    tool = canvas._split_tool

    tool.mouse_press(mouse_event, QPointF(0, 150))
    tool.mouse_press(mouse_event, QPointF(700, 150))

    assert chosen.scene() is None
    assert neighbour.scene() is canvas.scene()
    assert len(_add_pieces(canvas.scene())) == 2


def test_the_preview_shows_the_pieces_of_every_crossed_shape(
    canvas, mouse_event
) -> None:
    _add(canvas, RectangleItem(100, 100, 200, 100), select=False)
    _add(canvas, RectangleItem(400, 100, 200, 100), select=False)
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool
    assert tool.mouse_press(mouse_event, QPointF(0, 150)) is True

    assert tool.mouse_move(mouse_event, QPointF(700, 150)) is True

    assert len(tool._preview_pieces) == 4
    assert tool._preview_line is not None


def test_a_multi_shape_split_survives_save_and_reopen(
    canvas, mouse_event, tmp_path
) -> None:
    _add(canvas, RectangleItem(100, 100, 200, 100), select=False)
    _add(canvas, RectangleItem(400, 100, 200, 100), select=False)
    canvas.set_active_tool(ToolType.SPLIT)
    tool = canvas._split_tool
    tool.mouse_press(mouse_event, QPointF(0, 150))
    tool.mouse_press(mouse_event, QPointF(700, 150))
    geometry = sorted(
        (piece.polygon() for piece in _add_pieces(canvas.scene())),
        key=lambda poly: (poly.boundingRect().x(), poly.boundingRect().y()),
    )

    path = tmp_path / "multi-split.ogp"
    ProjectManager().save(canvas.scene(), path)
    restored = canvas.scene()
    ProjectManager().load(restored, path)

    pieces = [item for item in restored.items() if isinstance(item, PolygonItem)]
    assert len(pieces) == 4
    restored_geometry = sorted(
        (piece.polygon() for piece in pieces),
        key=lambda poly: (poly.boundingRect().x(), poly.boundingRect().y()),
    )
    assert restored_geometry == geometry


def test_the_split_shortcut_does_not_collide_with_snap(qtbot) -> None:
    """The shortcut must not collide with the main window's S (Snap to Grid).

    A ``QToolButton`` shortcut and a ``QAction`` shortcut on the same key make
    Qt fire NEITHER (measured on this Qt version); the first version of this
    tool shipped with ``S`` and was dead for exactly that reason. Offscreen Qt
    has no focus window, so this pins the configuration rather than a key press.
    """
    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import get_settings

    get_settings().show_welcome_on_startup = False
    window = GardenPlannerApp()
    qtbot.addWidget(window)

    split = window.constraint_toolbar._buttons[ToolType.SPLIT]
    assert split.shortcut().toString() == "Shift+S"
    assert window.snap_action.shortcut().toString() == "S"
    assert split.shortcut() != window.snap_action.shortcut()


def test_the_context_menu_shows_a_refusal_reason_as_its_tooltip(canvas, monkeypatch) -> None:
    scene = canvas.scene()
    locked = Layer(name="Locked", locked=True, z_order=2)
    scene.add_layer(locked)
    source = RectangleItem(100, 100, 200, 100)
    source.layer_id = locked.id
    scene.addItem(source)
    captured: dict[str, object] = {}

    def inspect_menu(menu, *_args):
        action = next(
            entry for entry in menu.actions() if entry.objectName() == "split_shape"
        )
        captured["enabled"] = action.isEnabled()
        captured["tooltip"] = action.toolTip()
        captured["tips"] = menu.toolTipsVisible()
        return None

    monkeypatch.setattr(QMenu, "exec", inspect_menu)
    source.contextMenuEvent(MagicMock(spec=QGraphicsSceneContextMenuEvent))

    assert captured["enabled"] is False
    assert captured["tooltip"] == "The shape is on a locked layer"
    assert captured["tips"] is True


def test_the_context_menu_offers_a_dispatchable_split_action(canvas, monkeypatch) -> None:
    source = _add(canvas, RectangleItem(100, 100, 200, 100))
    captured: dict[str, str] = {}

    def choose_split(menu, *_args):
        action = next(
            entry for entry in menu.actions() if entry.objectName() == "split_shape"
        )
        captured["text"] = action.text()
        action.trigger()
        return action

    monkeypatch.setattr(QMenu, "exec", choose_split)
    source.contextMenuEvent(MagicMock(spec=QGraphicsSceneContextMenuEvent))

    assert captured["text"].startswith("Split Along Line")
    assert canvas.tool_manager.active_tool_type is ToolType.SPLIT


def test_the_preview_follows_the_second_point_and_escape_leaves_no_command(
    canvas, mouse_event
) -> None:
    source = _add(canvas, RectangleItem(100, 100, 200, 100))
    assert canvas.start_split_shape(source) is True
    tool = canvas._split_tool

    assert tool.mouse_press(mouse_event, QPointF(200, 0)) is True
    assert tool._preview_line is not None
    assert tool.mouse_move(mouse_event, QPointF(200, 400)) is True
    assert len(tool._preview_pieces) == 2
    assert tool._preview_line is not None

    escape = MagicMock(spec=QKeyEvent)
    escape.key.return_value = Qt.Key.Key_Escape
    assert tool.key_press(escape) is True

    assert tool._preview_line is None
    assert tool._preview_pieces == []
    assert source.scene() is canvas.scene()
    assert canvas.command_manager.undo_depth == 0
    assert canvas.tool_manager.active_tool_type is ToolType.SELECT


def test_a_cut_that_misses_the_shape_keeps_the_first_point_and_changes_nothing(
    canvas, mouse_event
) -> None:
    source = _add(canvas, RectangleItem(100, 100, 200, 100))
    assert canvas.start_split_shape(source) is True
    tool = canvas._split_tool
    tool.mouse_press(mouse_event, QPointF(400, 0))

    assert tool.mouse_press(mouse_event, QPointF(400, 500)) is True

    assert source.scene() is canvas.scene()
    assert canvas.command_manager.undo_depth == 0
    assert tool._start == QPointF(400, 0)
    assert canvas.tool_manager.active_tool_type is ToolType.SPLIT


@pytest.mark.parametrize(
    "item_factory",
    [
        lambda: CircleItem(100, 100, 80),
        lambda: EllipseItem(100, 100, 200, 100),
        lambda: PolygonItem(
            [
                QPointF(100, 100),
                QPointF(300, 100),
                QPointF(300, 200),
                QPointF(100, 200),
            ]
        ),
    ],
    ids=["circle", "ellipse", "polygon"],
)
def test_circle_ellipse_and_polygon_split_into_polygons(canvas, mouse_event, item_factory) -> None:
    source = _add(canvas, item_factory())
    centre = source.sceneBoundingRect().center()
    _split(
        canvas,
        source,
        QPointF(centre.x(), centre.y() - 500),
        QPointF(centre.x(), centre.y() + 500),
        mouse_event,
    )

    pieces = _add_pieces(canvas.scene())
    assert len(pieces) == 2
    assert all(piece.scene() is canvas.scene() for piece in pieces)
    assert canvas.command_manager.undo_depth == 1


def test_a_rotated_source_keeps_its_rotation_and_material_direction(
    canvas, mouse_event, tmp_path
) -> None:
    source = RectangleItem(100, 100, 400, 200)
    source._apply_rotation(37)
    source.fill_transform = FillTransform(angle_deg=25.0, scale=1.5)
    source._setup_styling()
    _add(canvas, source)
    original = item_to_painter_path(source)
    assert original is not None
    centre = original.boundingRect().center()

    _split(
        canvas,
        source,
        centre - QPointF(0, 500),
        centre + QPointF(0, 500),
        mouse_event,
    )

    pieces = _add_pieces(canvas.scene())
    assert len(pieces) == 2
    combined = QPainterPath()
    for piece in pieces:
        piece_path = item_to_painter_path(piece)
        assert piece_path is not None
        combined = combined.united(piece_path)
        assert piece.rotation() == pytest.approx(source.rotation())
        assert piece.brush().transform() == source.brush().transform()
    assert _polygon_area(original.subtracted(combined).toFillPolygon()) < 1e-6

    path = tmp_path / "rotated-split.ogp"
    ProjectManager().save(canvas.scene(), path)
    restored = canvas.scene()
    ProjectManager().load(restored, path)
    restored_path = QPainterPath()
    for item in restored.items():
        if isinstance(item, PolygonItem):
            piece_path = item_to_painter_path(item)
            assert piece_path is not None
            restored_path = restored_path.united(piece_path)
    assert _polygon_area(combined.subtracted(restored_path).toFillPolygon()) < 1e-6


def test_a_save_and_reopen_preserves_the_pieces(canvas, mouse_event, tmp_path) -> None:
    source = _add(canvas, RectangleItem(100, 100, 200, 100))
    source.metadata["future_field"] = {"keep": True}
    _split(canvas, source, QPointF(200, 0), QPointF(200, 400), mouse_event)
    geometry = [piece.polygon() for piece in _add_pieces(canvas.scene())]

    path = tmp_path / "split.ogp"
    ProjectManager().save(canvas.scene(), path)
    restored = canvas.scene()
    ProjectManager().load(restored, path)

    pieces = [item for item in restored.items() if isinstance(item, PolygonItem)]
    assert len(pieces) == 2
    assert [piece.polygon() for piece in pieces] == geometry
    assert all(piece.metadata["future_field"] == {"keep": True} for piece in pieces)

    # A second save/reload must be stable (issue #664 acceptance).
    second = tmp_path / "split-second.ogp"
    ProjectManager().save(restored, second)
    ProjectManager().load(restored, second)
    again = [item for item in restored.items() if isinstance(item, PolygonItem)]
    assert [piece.polygon() for piece in again] == geometry


def test_a_deleted_source_clears_the_piece_preview(canvas, mouse_event) -> None:
    source = _add(canvas, RectangleItem(100, 100, 200, 100))
    assert canvas.start_split_shape(source) is True
    tool = canvas._split_tool
    assert tool.mouse_press(mouse_event, QPointF(200, 0)) is True
    assert tool.mouse_move(mouse_event, QPointF(200, 400)) is True
    assert tool._preview_pieces

    canvas.scene().removeItem(source)
    assert tool.mouse_move(mouse_event, QPointF(220, 400)) is True

    assert tool._preview_pieces == []
    assert tool._preview_line is None


def test_the_vertex_cap_message_is_not_overwritten(canvas, mouse_event, monkeypatch) -> None:
    from open_garden_planner.ui.canvas.items import polygon_item

    monkeypatch.setattr(polygon_item, "MAX_POLYGON_VERTICES", 4)
    source = _add(canvas, RectangleItem(100, 100, 200, 100))
    assert canvas.start_split_shape(source) is True
    tool = canvas._split_tool
    tool.mouse_press(mouse_event, QPointF(200, 0))
    messages: list[str] = []
    canvas.status_message.connect(messages.append)

    assert tool.mouse_press(mouse_event, QPointF(200, 400)) is True

    assert source.scene() is canvas.scene()
    assert canvas.command_manager.undo_depth == 0
    assert messages and "vertices" in messages[-1]


def test_a_locked_layer_refuses_the_split(canvas) -> None:
    scene = canvas.scene()
    locked = Layer(name="Locked", locked=True, z_order=2)
    scene.add_layer(locked)
    source = RectangleItem(100, 100, 200, 100)
    source.layer_id = locked.id
    scene.addItem(source)

    messages: list[str] = []
    canvas.status_message.connect(messages.append)
    assert canvas.start_split_shape(source) is False
    assert messages == ["The shape is on a locked layer"]
    assert source.scene() is scene
    assert canvas.command_manager.undo_depth == 0


def test_a_constrained_shape_refuses_the_split(canvas) -> None:
    source = _add(canvas, RectangleItem(100, 100, 200, 100))
    anchor = AnchorRef(source.item_id, AnchorType.CENTER)
    canvas.scene().constraint_graph.add_constraint(
        anchor, anchor, 0, constraint_type=ConstraintType.FIXED,
        target_x=0, target_y=0,
    )

    assert canvas.start_split_shape(source) is False
    assert source.scene() is canvas.scene()
    assert canvas.command_manager.undo_depth == 0


def test_a_container_without_a_polygonal_form_is_refused(canvas) -> None:
    source = _add(
        canvas,
        RectangleItem(100, 100, 200, 100, object_type=ObjectType.CONTAINER),
    )
    messages: list[str] = []
    canvas.status_message.connect(messages.append)

    assert canvas.start_split_shape(source) is False
    assert messages == ["This shape type has no polygonal form to split into"]
    assert source.scene() is canvas.scene()


def test_a_raised_bed_becomes_a_garden_bed(canvas, mouse_event) -> None:
    source = _add(
        canvas,
        RectangleItem(100, 100, 200, 100, object_type=ObjectType.RAISED_BED),
    )
    _split(canvas, source, QPointF(200, 0), QPointF(200, 400), mouse_event)

    pieces = _add_pieces(canvas.scene())
    assert len(pieces) == 2
    assert all(piece.object_type is ObjectType.GARDEN_BED for piece in pieces)


def test_a_plant_or_group_member_refuses_the_split(canvas) -> None:
    plant = _add(canvas, CircleItem(100, 100, 40, object_type=ObjectType.TREE))
    assert canvas.start_split_shape(plant) is False

    scene = canvas.scene()
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(200, 0, 100, 100)
    _add(canvas, first, select=True)
    scene.addItem(second)
    first.setSelected(True)
    second.setSelected(True)
    canvas.group_selected()
    group = next(item for item in scene.items() if isinstance(item, GroupItem))
    member = next(item for item in group.childItems() if isinstance(item, RectangleItem))

    assert canvas.start_split_shape(member) is False
    assert member.scene() is scene


def test_project_tracking_records_refuse_the_split(canvas) -> None:
    source = _add(canvas, RectangleItem(100, 100, 200, 100))
    manager = ProjectManager()
    manager.set_soil_test_history(
        str(source.item_id), SimpleNamespace(to_dict=lambda: {"records": []})
    )
    canvas._project_manager = manager

    assert canvas.start_split_shape(source) is False
    assert source.scene() is canvas.scene()
    assert canvas.command_manager.undo_depth == 0


def test_the_local_piece_geometry_reconstructs_the_source(canvas) -> None:
    source = RectangleItem(100, 100, 400, 200)
    source._apply_rotation(23)
    pieces = split_item_into_local_polygons(
        source, QPointF(300, -100), QPointF(300, 500)
    )
    assert len(pieces) == 2
    total = sum(
        _polygon_area(source.mapToScene(piece)) for piece in pieces
    )
    assert total == pytest.approx(80000.0, rel=1e-6)
