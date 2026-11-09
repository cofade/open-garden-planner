"""End-to-end split-along-a-line workflow (#664).

The tool is started from the shape's context menu, takes two snapped scene
points, previews the line and pieces, and replaces the source with polygons in
one undo step. The source's layer, look, fill transform, label state and
metadata survive; linked, constrained, planted, grouped and tracked shapes are
refused before any mutation.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QPainterPath
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


def test_the_cad_toolbar_arms_the_selected_shape(qtbot, canvas) -> None:
    from open_garden_planner.ui.widgets.constraint_toolbar import ConstraintToolbar

    source = _add(canvas, RectangleItem(100, 100, 200, 100))
    toolbar = ConstraintToolbar()
    qtbot.addWidget(toolbar)
    toolbar.tool_selected.connect(canvas.set_active_tool)
    button = toolbar._buttons[ToolType.SPLIT]
    assert button.shortcut().toString() == "S"
    assert not button.icon().isNull()

    button.click()
    QTest.qWait(10)

    assert canvas.tool_manager.active_tool_type is ToolType.SPLIT
    assert canvas._split_tool.source_id == source.item_id


def test_the_cad_toolbar_explains_a_missing_selection(qtbot, canvas) -> None:
    from open_garden_planner.ui.widgets.constraint_toolbar import ConstraintToolbar

    canvas.scene().clearSelection()
    toolbar = ConstraintToolbar()
    qtbot.addWidget(toolbar)
    toolbar.tool_selected.connect(canvas.set_active_tool)
    messages: list[str] = []
    canvas.status_message.connect(messages.append)

    toolbar._buttons[ToolType.SPLIT].click()
    QTest.qWait(10)

    assert messages[-1] == "Select one closed shape to split"
    assert canvas.tool_manager.active_tool_type is ToolType.SELECT


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
