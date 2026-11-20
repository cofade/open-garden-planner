"""End-to-end behaviour of the reference-point object (#666, ADR-080).

Covers the whole user path: placement, contour binding, parent translation,
edit, undo/redo, copy, layers and a save/reload that remains readable by an
older version as a plain small circle.
"""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.commands import MoveItemsCommand, MoveToLayerCommand
from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import FILE_VERSION, ProjectManager
from open_garden_planner.core.reference_points import (
    is_reference_point,
    on_contour,
    parent_id,
    size_mode,
)
from open_garden_planner.core.tools import ToolType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui import reference_points
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    RectangleItem,
    ReferencePointItem,
)


@pytest.fixture
def canvas(qtbot):
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    return scene, view


def _place(monkeypatch, view, options: reference_points.PointProperties, at: QPointF):
    monkeypatch.setattr(reference_points, "point_dialog", lambda *_args: options)
    assert reference_points.place_reference_point(view, at)
    return next(item for item in view._canvas_scene.items() if is_reference_point(item))


def _options(**overrides) -> reference_points.PointProperties:
    values = {
        "name": "Stake A",
        "parent_id": None,
        "on_contour": False,
        "size_mode": "plan_cm",
        "size": 6.0,
        "color": "#168c9e",
        "stroke_width": 1.8,
    }
    values.update(overrides)
    return reference_points.PointProperties(**values)


def test_place_independent_point_is_one_undo_step(canvas, monkeypatch):
    scene, view = canvas
    before = view.command_manager.undo_depth
    point = _place(monkeypatch, view, _options(), QPointF(240, 180))

    assert isinstance(point, ReferencePointItem)
    assert point.object_type == ObjectType.GENERIC_CIRCLE
    assert point.pos() == QPointF(240, 180)
    # The exact centre is the position in every mode.
    assert point.mapToScene(point.rect().center()) == QPointF(240, 180)
    assert point.name == "Stake A"
    assert parent_id(point.metadata) is None
    assert not on_contour(point.metadata)
    assert view.command_manager.undo_depth == before + 1

    anchors = get_anchor_points(point)
    assert [anchor.anchor_type for anchor in anchors] == [AnchorType.CENTER]
    assert anchors[0].point == QPointF(240, 180)

    view.command_manager.undo()
    assert point.scene() is None
    view.command_manager.redo()
    assert point.scene() is scene
    assert point.pos() == QPointF(240, 180)


def test_contour_bound_point_is_projected_and_follows_a_parent_move(canvas, monkeypatch):
    scene, view = canvas
    parent = RectangleItem(100, 100, 400, 200, object_type=ObjectType.GENERIC_RECTANGLE)
    scene.addItem(parent)
    point = _place(
        monkeypatch,
        view,
        _options(parent_id=parent.item_id, on_contour=True),
        QPointF(300, 102),
    )
    assert point.pos() == QPointF(300, 100)  # on the top edge, not 2 cm above it
    assert parent_id(point.metadata) == parent.item_id
    assert on_contour(point.metadata)

    depth = view.command_manager.undo_depth
    view.command_manager.execute(MoveItemsCommand([parent], QPointF(35, 60)))
    assert parent.pos() == QPointF(35, 60)
    assert point.pos() == QPointF(335, 160)
    assert view.command_manager.undo_depth == depth + 1

    view.command_manager.undo()
    assert parent.pos() == QPointF(0, 0)
    assert point.pos() == QPointF(300, 100)
    view.command_manager.redo()
    assert point.pos() == QPointF(335, 160)


def test_a_point_selected_with_its_parent_moves_once_and_undoes(canvas, monkeypatch):
    scene, view = canvas
    parent = RectangleItem(0, 100, 400, 200, object_type=ObjectType.GENERIC_RECTANGLE)
    scene.addItem(parent)
    point = _place(
        monkeypatch,
        view,
        _options(parent_id=parent.item_id, on_contour=True),
        QPointF(300, 100),
    )
    scene.clearSelection()
    parent.setSelected(True)
    point.setSelected(True)
    # The drag bookkeeping: both are in the direct set, the point was moved
    # live first and projected against the parent's old place.
    view._drag_start_positions = {
        point: QPointF(point.pos()),
        parent: QPointF(parent.pos()),
    }
    point.setPos(335, 100)
    parent.setPos(35, 60)
    depth = view.command_manager.undo_depth
    view._finalize_drag_move()

    assert view.command_manager.undo_depth == depth + 1
    assert parent.pos() == QPointF(35, 60)
    assert point.pos() == QPointF(335, 160)  # on the moved top edge, not (370, 160)

    view.command_manager.undo()
    assert parent.pos() == QPointF(0, 0)
    assert point.pos() == QPointF(300, 100)
    view.command_manager.redo()
    assert parent.pos() == QPointF(35, 60)
    assert point.pos() == QPointF(335, 160)


def test_bound_point_refuses_to_leave_the_contour_and_can_be_detached(canvas, monkeypatch):
    scene, view = canvas
    parent = RectangleItem(100, 100, 400, 200, object_type=ObjectType.GENERIC_RECTANGLE)
    scene.addItem(parent)
    point = _place(
        monkeypatch,
        view,
        _options(parent_id=parent.item_id, on_contour=True),
        QPointF(300, 100),
    )

    point.setPos(300, 250)
    assert point.pos() == QPointF(300, 300)  # projected to the nearest (bottom) edge

    options = _options(parent_id=None, on_contour=False)
    monkeypatch.setattr(reference_points, "point_dialog", lambda *_args: options)
    reference_points.edit_reference_point(point)
    assert parent_id(point.metadata) is None
    point.setPos(300, 250)
    assert point.pos() == QPointF(300, 250)


def test_edit_is_one_undo_step(canvas, monkeypatch):
    scene, view = canvas
    point = _place(monkeypatch, view, _options(), QPointF(240, 180))
    depth = view.command_manager.undo_depth
    changed = _options(
        name="Corner post",
        size_mode="screen_px",
        size=24.0,
        color="#ff8800",
        stroke_width=3.0,
    )
    monkeypatch.setattr(reference_points, "point_dialog", lambda *_args: changed)
    reference_points.edit_reference_point(point)

    assert view.command_manager.undo_depth == depth + 1
    assert point.name == "Corner post"
    assert size_mode(point.metadata) == "screen_px"
    assert point.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    assert point.mapToScene(point.rect().center()) == QPointF(240, 180)

    view.command_manager.undo()
    assert point.name == "Stake A"
    assert size_mode(point.metadata) == "plan_cm"
    assert not point.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    assert point.mapToScene(point.rect().center()) == QPointF(240, 180)


def test_editing_a_point_on_a_locked_layer_is_refused(canvas, monkeypatch):
    scene, view = canvas
    point = _place(monkeypatch, view, _options(), QPointF(240, 180))
    layer = scene.get_layer_by_id(point.layer_id)
    assert layer is not None
    layer.locked = True
    monkeypatch.setattr(
        reference_points, "point_dialog", lambda *_args: _options(name="Changed")
    )
    reference_points.edit_reference_point(point)
    assert point.name == "Stake A"


def test_the_dialog_preselects_a_contour_parent(canvas, monkeypatch):
    from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QSpinBox

    scene, view = canvas
    parent = RectangleItem(100, 100, 400, 200, object_type=ObjectType.GENERIC_RECTANGLE)
    scene.addItem(parent)

    captured = {}

    def accept(dialog):
        parents = dialog.findChild(QComboBox, "reference_point_parent")
        contour = dialog.findChild(QCheckBox, "reference_point_on_contour")
        size = dialog.findChild(QSpinBox, "reference_point_size")
        captured["parent"] = parents.currentData()
        captured["contour"] = contour.isChecked()
        captured["size"] = size.value()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", accept)
    result = reference_points.point_dialog(view, None, QPointF(300, 102))
    assert result is not None
    assert captured == {"parent": parent.item_id, "contour": True, "size": 6}
    assert result.parent_id == parent.item_id
    assert result.on_contour
    assert result.size == pytest.approx(6.0)


def test_copy_and_layer_follow_the_ordinary_object_rules(canvas, monkeypatch):
    scene, view = canvas
    point = _place(monkeypatch, view, _options(), QPointF(240, 180))
    scene.clearSelection()
    point.setSelected(True)
    depth = view.command_manager.undo_depth
    view.duplicate_selected()
    copies = [
        item for item in scene.items() if is_reference_point(item) and item is not point
    ]
    assert len(copies) == 1
    assert copies[0].item_id != point.item_id
    assert view.command_manager.undo_depth == depth + 1

    layer = Layer(name="Stakes")
    scene.add_layer(layer)
    view.command_manager.execute(
        MoveToLayerCommand([point], layer.id, scene, layer.name)
    )
    assert point.layer_id == layer.id
    view.command_manager.undo()
    assert point.layer_id != layer.id


def test_save_reload_keeps_the_reference_and_old_versions_still_read_it(
    canvas, qtbot, monkeypatch, tmp_path
):
    scene, view = canvas
    parent = RectangleItem(100, 100, 400, 200, object_type=ObjectType.GENERIC_RECTANGLE)
    scene.addItem(parent)
    point = _place(
        monkeypatch,
        view,
        _options(parent_id=parent.item_id, on_contour=True),
        QPointF(300, 100),
    )
    identity = point.item_id
    path = tmp_path / "references.ogp"
    ProjectManager().save(scene, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    record = next(obj for obj in raw["objects"] if obj["item_id"] == str(identity))
    # The record is the ordinary circle record - no new type, no FILE_VERSION bump.
    assert record["type"] == "circle"
    assert record["object_type"] == "GENERIC_CIRCLE"
    assert record["metadata"]["reference_point"] is True
    assert raw["version"] == FILE_VERSION

    restored_scene = CanvasScene(width_cm=5000, height_cm=3000)
    other_view = CanvasView(restored_scene)
    qtbot.addWidget(other_view)
    try:
        ProjectManager().load(restored_scene, path)
        restored = restored_scene.find_item_by_id(identity)
        assert isinstance(restored, ReferencePointItem)
        assert restored.name == "Stake A"
        assert parent_id(restored.metadata) == parent.item_id
        assert restored.mapToScene(restored.rect().center()) == QPointF(300, 100)
    finally:
        other_view.deleteLater()

    # An older version ignores the metadata and reads a small circle.
    legacy = json.loads(path.read_text(encoding="utf-8"))
    for obj in legacy["objects"]:
        if obj.get("item_id") == str(identity):
            obj.pop("metadata", None)
    legacy_path = tmp_path / "legacy.ogp"
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    legacy_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(legacy_scene, legacy_path)
    fallback = legacy_scene.find_item_by_id(identity)
    assert isinstance(fallback, CircleItem)
    assert not isinstance(fallback, ReferencePointItem)
    assert fallback.radius == pytest.approx(3.0)


def _click(view, scene_pos: QPointF) -> bool:
    """Deliver a left press through the active tool, as CanvasView would."""
    from types import SimpleNamespace

    tool = view._tool_manager.active_tool
    event = SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton)
    return bool(tool.mouse_press(event, scene_pos))


def test_tool_places_a_point_and_returns_to_select(canvas, monkeypatch):
    scene, view = canvas
    monkeypatch.setattr(reference_points, "point_dialog", lambda *_args: _options())
    view.set_active_tool(ToolType.REFERENCE_POINT)
    assert view._tool_manager.active_tool_type == ToolType.REFERENCE_POINT

    assert _click(view, QPointF(300, 200))
    assert view._tool_manager.active_tool_type == ToolType.SELECT
    point = next(item for item in scene.items() if is_reference_point(item))
    assert point.pos() == QPointF(300, 200)


def test_screen_mode_symbol_does_not_scale_with_the_view(canvas, monkeypatch):
    scene, view = canvas
    point = _place(
        monkeypatch,
        view,
        _options(size_mode="screen_px", size=20.0),
        QPointF(240, 180),
    )
    assert point.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    assert point.pos() == QPointF(240, 180)
    assert point.rect().width() == pytest.approx(20.0)

    monkeypatch.setattr(
        reference_points,
        "point_dialog",
        lambda *_args: _options(size_mode="screen_px", size=20.0),
    )
    reference_points.edit_reference_point(point)
    # Unchanged properties are still one call and must not move the centre.
    assert point.pos() == QPointF(240, 180)
