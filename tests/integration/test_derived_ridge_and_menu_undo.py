"""Integration tests for issue #712:
- Derived ridge follow-ups: groupable ridges, copy ridges, legacy link sanitising, remaining menu undo
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core.commands import (
    ArrayAlongPathCommand,
    CircularArrayCommand,
    GridArrayCommand,
    LinearArrayCommand,
    MirrorItemsCommand,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectData, ProjectManager
from open_garden_planner.core.tools.offset_tool import OffsetTool
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    BezierItem,
    CalloutItem,
    ConstructionCircleItem,
    ConstructionLineItem,
    PolylineItem,
    TextItem,
)
from open_garden_planner.ui.canvas.items.group_item import (
    GroupItem,
    groupable_selection,
)
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.roof_ridge_link import (
    build_linked_ridge,
    linked_ridge,
)

if TYPE_CHECKING:
    import pytest


def _scene_view(qtbot: pytest.QtBot) -> tuple[CanvasScene, CanvasView]:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    return scene, view


def _create_house(scene: CanvasScene, x: float = 100.0, y: float = 100.0) -> tuple[PolygonItem, PolylineItem]:
    pts = [
        QPointF(x, y),
        QPointF(x + 400.0, y),
        QPointF(x + 400.0, y + 200.0),
        QPointF(x, y + 200.0),
    ]
    house = PolygonItem(pts, object_type=ObjectType.HOUSE, layer_id=scene.active_layer.id)
    scene.addItem(house)
    ridge = build_linked_ridge(house, scene.active_layer.id)
    assert ridge is not None
    scene.addItem(ridge)
    return house, ridge


# ==============================================================================
# 1. Groupable ridges
# ==============================================================================


def test_roof_ridge_excluded_from_groupable_selection(qtbot) -> None:
    """A derived ROOF_RIDGE cannot be grouped independently (issue #712 item 1)."""
    scene, view = _scene_view(qtbot)
    house, ridge = _create_house(scene, 100, 100)
    rect = RectangleItem(600, 100, 200, 100, object_type=ObjectType.GENERIC_RECTANGLE, layer_id=scene.active_layer.id)
    scene.addItem(rect)

    # Selecting only a ridge and an unrelated rectangle: groupable_selection has only 1 item
    selected = [ridge, rect]
    groupable = groupable_selection(selected)
    assert groupable == [rect], "ROOF_RIDGE must be excluded from groupable selection"

    # group_selected should refuse since count < 2
    for item in scene.items():
        item.setSelected(item in selected)
    view.group_selected()
    assert not any(isinstance(i, GroupItem) for i in scene.items()), "Group should not be formed"

    # Selecting house, rect, and ridge: house and rect are grouped, ridge stays sibling
    selected_all = [house, rect, ridge]
    for item in scene.items():
        item.setSelected(item in selected_all)
    view.group_selected()
    groups = [i for i in scene.items() if isinstance(i, GroupItem)]
    assert len(groups) == 1
    group = groups[0]
    assert house.parentItem() is group
    assert rect.parentItem() is group
    assert ridge.parentItem() is None, "Ridge must remain a top-level sibling, not inside group"

    # Moving the group keeps the house's ridge synchronized
    old_p1 = ridge.points[0]
    group.setPos(50, 50)
    new_p1 = ridge.points[0]
    assert new_p1 != old_p1, "Group movement must update nested house ridge"


# ==============================================================================
# 2. Mirror / offset / array copies of a HOUSE have linked ridges
# ==============================================================================


def test_linear_array_house_builds_linked_ridges(qtbot) -> None:
    """LinearArrayCommand creates fresh linked ridges for house copies (issue #712 item 2)."""
    scene, view = _scene_view(qtbot)
    house, ridge = _create_house(scene, 100, 100)

    # Make 2 copies
    copy1 = PolygonItem([QPointF(p.x() + 500, p.y()) for p in house.polygon()], object_type=ObjectType.HOUSE, layer_id=scene.active_layer.id)
    copy2 = PolygonItem([QPointF(p.x() + 1000, p.y()) for p in house.polygon()], object_type=ObjectType.HOUSE, layer_id=scene.active_layer.id)

    cmd = LinearArrayCommand(scene, [copy1, copy2])
    view.command_manager.execute(cmd)

    r1 = linked_ridge(copy1)
    r2 = linked_ridge(copy2)
    assert r1 is not None and r2 is not None
    assert r1 is not ridge and r2 is not ridge
    assert r1 is not r2
    assert r1.metadata["owner_polygon_id"] == str(copy1.item_id)
    assert r2.metadata["owner_polygon_id"] == str(copy2.item_id)
    assert copy1.metadata["ridge_item_id"] == str(r1.item_id)
    assert copy2.metadata["ridge_item_id"] == str(r2.item_id)

    # One undo removes both copies and their ridges
    view.command_manager.undo()
    assert copy1.scene() is None and copy2.scene() is None
    assert r1.scene() is None and r2.scene() is None
    assert ridge.scene() is scene

    # Redo restores them with the same IDs
    view.command_manager.redo()
    assert copy1.scene() is scene and copy2.scene() is scene
    assert r1.scene() is scene and r2.scene() is scene
    assert linked_ridge(copy1) is r1
    assert linked_ridge(copy2) is r2


def test_grid_circular_and_path_array_house_ridges(qtbot) -> None:
    """Grid, Circular, and Path array commands also build linked ridges."""
    scene, view = _scene_view(qtbot)
    house, _ = _create_house(scene, 100, 100)

    # Grid array
    g_copy = PolygonItem([QPointF(p.x(), p.y() + 300) for p in house.polygon()], object_type=ObjectType.HOUSE, layer_id=scene.active_layer.id)
    g_cmd = GridArrayCommand(scene, [g_copy])
    view.command_manager.execute(g_cmd)
    g_ridge = linked_ridge(g_copy)
    assert g_ridge is not None and g_ridge.scene() is scene
    view.command_manager.undo()
    assert g_copy.scene() is None and g_ridge.scene() is None

    # Circular array
    c_copy = PolygonItem([QPointF(p.x() + 600, p.y() + 300) for p in house.polygon()], object_type=ObjectType.HOUSE, layer_id=scene.active_layer.id)
    c_cmd = CircularArrayCommand(scene, [c_copy])
    view.command_manager.execute(c_cmd)
    c_ridge = linked_ridge(c_copy)
    assert c_ridge is not None and c_ridge.scene() is scene
    view.command_manager.undo()
    assert c_copy.scene() is None and c_ridge.scene() is None

    # Array along path
    p_copy = PolygonItem([QPointF(p.x() + 800, p.y() + 300) for p in house.polygon()], object_type=ObjectType.HOUSE, layer_id=scene.active_layer.id)
    p_cmd = ArrayAlongPathCommand(scene, [p_copy])
    view.command_manager.execute(p_cmd)
    p_ridge = linked_ridge(p_copy)
    assert p_ridge is not None and p_ridge.scene() is scene
    view.command_manager.undo()
    assert p_copy.scene() is None and p_ridge.scene() is None


def test_mirror_group_with_house_builds_copy_ridge(qtbot) -> None:
    """Mirroring a group containing a HOUSE in copy mode builds a ridge for the copied house."""
    scene, view = _scene_view(qtbot)
    house, ridge = _create_house(scene, 100, 100)
    group = GroupItem(layer_id=scene.active_layer.id)
    scene.addItem(group)
    group.addToGroup(house)

    # Mirror copy of the group
    mirrored_group = GroupItem(layer_id=scene.active_layer.id)
    mirrored_house = PolygonItem(
        [QPointF(-p.x(), p.y()) for p in house.polygon()],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    mirrored_group.addToGroup(mirrored_house)

    cmd = MirrorItemsCommand(scene, [group], [mirrored_group], copy=True)
    view.command_manager.execute(cmd)

    copy_ridge = linked_ridge(mirrored_house)
    assert copy_ridge is not None
    assert copy_ridge is not ridge
    assert copy_ridge.scene() is scene
    assert copy_ridge.metadata["owner_polygon_id"] == str(mirrored_house.item_id)
    assert mirrored_house.metadata["ridge_item_id"] == str(copy_ridge.item_id)

    # Undo removes the mirrored group and the copy ridge
    view.command_manager.undo()
    assert mirrored_group.scene() is None
    assert copy_ridge.scene() is None
    assert ridge.scene() is scene

    # Redo restores both
    view.command_manager.redo()
    assert mirrored_group.scene() is scene
    assert copy_ridge.scene() is scene


def test_offset_house_builds_copy_ridge(qtbot) -> None:
    """OffsetTool on a HOUSE polygon builds a fresh linked ridge in one undo step."""
    scene, view = _scene_view(qtbot)
    house, _ = _create_house(scene, 100, 100)

    house.setSelected(True)
    tool = OffsetTool(view)
    tool.activate()

    # Click outward offset at (550, 200) - 50 cm away from right edge (500, 200)
    mock_event = MagicMock()
    mock_event.button.return_value = Qt.MouseButton.LeftButton
    tool.mouse_press(mock_event, QPointF(550, 200))

    # There should now be 2 houses and 2 ridges in the scene
    houses = [i for i in scene.items() if isinstance(i, PolygonItem) and i.object_type == ObjectType.HOUSE]
    ridges = [i for i in scene.items() if isinstance(i, PolylineItem) and i.object_type == ObjectType.ROOF_RIDGE]
    assert len(houses) == 2, f"Expected 2 houses, found {len(houses)}"
    assert len(ridges) == 2, f"Expected 2 ridges, found {len(ridges)}"

    offset_house = next(h for h in houses if h is not house)
    offset_ridge = linked_ridge(offset_house)
    assert offset_ridge is not None
    assert offset_ridge.metadata["owner_polygon_id"] == str(offset_house.item_id)

    # One undo removes both the offset house and its ridge
    view.command_manager.undo()
    assert offset_house.scene() is None
    assert offset_ridge.scene() is None
    assert len([i for i in scene.items() if isinstance(i, PolygonItem) and i.object_type == ObjectType.HOUSE]) == 1


# ==============================================================================
# 3. Legacy ridge link sanitising at load
# ==============================================================================


def test_project_load_sanitises_legacy_ridge_links() -> None:
    """Project load drops invalid or stale ridge links (issue #712 item 3)."""
    pm = ProjectManager()
    h_id = uuid.uuid4()
    r_id = uuid.uuid4()
    foreign_h_id = uuid.uuid4()

    # 1. Non-house with ridge_item_id -> should be dropped
    rect_id = uuid.uuid4()
    rect_data = {
        "item_id": str(rect_id),
        "type": "rectangle",
        "object_type": "GENERIC_RECTANGLE",
        "x": 0.0,
        "y": 0.0,
        "width": 100.0,
        "height": 100.0,
        "metadata": {"ridge_item_id": str(uuid.uuid4())},
    }

    # 2. House with dead ridge_item_id -> should be dropped
    dead_house_id = uuid.uuid4()
    dead_house_data = {
        "item_id": str(dead_house_id),
        "type": "polygon",
        "object_type": "HOUSE",
        "points": [{"x": 0.0, "y": 0.0}, {"x": 200.0, "y": 0.0}, {"x": 200.0, "y": 100.0}, {"x": 0.0, "y": 100.0}],
        "metadata": {"ridge_item_id": str(uuid.uuid4())},
    }

    # 3. House pointing to an item that is NOT a ROOF_RIDGE -> dropped
    other_poly_id = uuid.uuid4()
    other_poly_data = {
        "item_id": str(other_poly_id),
        "type": "polygon",
        "object_type": "GARDEN_BED",
        "points": [{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.0}, {"x": 100.0, "y": 100.0}],
    }
    invalid_target_house_id = uuid.uuid4()
    invalid_target_house = {
        "item_id": str(invalid_target_house_id),
        "type": "polygon",
        "object_type": "HOUSE",
        "points": [{"x": 0.0, "y": 0.0}, {"x": 200.0, "y": 0.0}, {"x": 200.0, "y": 100.0}, {"x": 0.0, "y": 100.0}],
        "metadata": {"ridge_item_id": str(other_poly_id)},
    }

    # 4. House pointing to a ridge owned by a DIFFERENT house -> dropped
    stolen_ridge_id = uuid.uuid4()
    stolen_ridge_data = {
        "item_id": str(stolen_ridge_id),
        "type": "polyline",
        "object_type": "ROOF_RIDGE",
        "points": [{"x": 0.0, "y": 50.0}, {"x": 200.0, "y": 50.0}],
        "metadata": {"owner_polygon_id": str(foreign_h_id)},
    }
    thief_house_id = uuid.uuid4()
    thief_house_data = {
        "item_id": str(thief_house_id),
        "type": "polygon",
        "object_type": "HOUSE",
        "points": [{"x": 0.0, "y": 0.0}, {"x": 200.0, "y": 0.0}, {"x": 200.0, "y": 100.0}, {"x": 0.0, "y": 100.0}],
        "metadata": {"ridge_item_id": str(stolen_ridge_id)},
    }

    # 5. Legitimate house + ridge -> preserved
    valid_house_data = {
        "item_id": str(h_id),
        "type": "polygon",
        "object_type": "HOUSE",
        "points": [{"x": 0.0, "y": 0.0}, {"x": 300.0, "y": 0.0}, {"x": 300.0, "y": 150.0}, {"x": 0.0, "y": 150.0}],
        "metadata": {"ridge_item_id": str(r_id)},
    }
    valid_ridge_data = {
        "item_id": str(r_id),
        "type": "polyline",
        "object_type": "ROOF_RIDGE",
        "points": [{"x": 0.0, "y": 75.0}, {"x": 300.0, "y": 75.0}],
        "metadata": {"owner_polygon_id": str(h_id)},
    }

    # 6. Orphan ROOF_RIDGE whose owner is dead -> owner_polygon_id dropped
    orphan_ridge_id = uuid.uuid4()
    orphan_ridge_data = {
        "item_id": str(orphan_ridge_id),
        "type": "polyline",
        "object_type": "ROOF_RIDGE",
        "points": [{"x": 10.0, "y": 10.0}, {"x": 50.0, "y": 10.0}],
        "metadata": {"owner_polygon_id": str(uuid.uuid4())},
    }

    project_data = ProjectData(
        canvas_width=1000,
        canvas_height=1000,
        objects=[
            rect_data,
            dead_house_data,
            other_poly_data,
            invalid_target_house,
            stolen_ridge_data,
            thief_house_data,
            valid_house_data,
            valid_ridge_data,
            orphan_ridge_data,
        ],
    )

    items, _, _, _ = pm._prepare_scene_data(project_data)
    by_id = {it.item_id: it for it in items if hasattr(it, "item_id")}

    # Assertions
    rect_item = by_id[rect_id]
    assert "ridge_item_id" not in getattr(rect_item, "metadata", {}), "Non-house must lose ridge_item_id"

    dead_house_item = by_id[dead_house_id]
    assert "ridge_item_id" not in getattr(dead_house_item, "metadata", {}), "Dead ridge link must be dropped"

    invalid_target_item = by_id[invalid_target_house_id]
    assert "ridge_item_id" not in getattr(invalid_target_item, "metadata", {}), "Non-ridge target link must be dropped"

    thief_house_item = by_id[thief_house_id]
    assert "ridge_item_id" not in getattr(thief_house_item, "metadata", {}), "Foreign-owned ridge link must be dropped"

    valid_house_item = by_id[h_id]
    valid_ridge_item = by_id[r_id]
    assert valid_house_item.metadata.get("ridge_item_id") == str(r_id), "Valid link must be kept"
    assert valid_ridge_item.metadata.get("owner_polygon_id") == str(h_id), "Valid reverse link must be kept"

    orphan_ridge_item = by_id[orphan_ridge_id]
    assert "owner_polygon_id" not in getattr(orphan_ridge_item, "metadata", {}), "Dead owner_polygon_id must be dropped"


# ==============================================================================
# 4. Arc / Bezier / construction context-menu Delete and Delete key undoable
# ==============================================================================


def _simulate_context_menu_delete(item, expected_label: str) -> None:
    event = MagicMock(spec=QGraphicsSceneContextMenuEvent)
    event.screenPos.return_value = QPointF(0, 0).toPoint()
    real_exec = QMenu.exec

    def patched_exec(self, *args, **kwargs):
        for act in self.actions():
            if expected_label in act.text():
                return act
        return None

    QMenu.exec = patched_exec
    try:
        item.contextMenuEvent(event)
    finally:
        QMenu.exec = real_exec


def test_arc_menu_and_key_delete_undoable(qtbot) -> None:
    """ArcItem menu Delete and Delete key go through the command stack (issue #712 item 4)."""
    scene, view = _scene_view(qtbot)
    arc = ArcItem(QPointF(100, 100), 50.0, 0.0, 90.0, layer_id=scene.active_layer.id)
    scene.addItem(arc)
    assert arc.scene() is scene

    # Context menu delete
    _simulate_context_menu_delete(arc, "Delete Arc")
    assert arc.scene() is None, "Arc should be removed from scene"

    # Undo
    view.command_manager.undo()
    assert arc.scene() is scene, "Undo must restore Arc"

    # Redo
    view.command_manager.redo()
    assert arc.scene() is None, "Redo must remove Arc again"

    view.command_manager.undo()
    assert arc.scene() is scene

    # Delete key
    key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    arc.keyPressEvent(key_event)
    assert arc.scene() is None, "Delete key must delete Arc via command stack"

    view.command_manager.undo()
    assert arc.scene() is scene, "Undo must restore Arc after Delete key"


def test_bezier_menu_and_key_delete_undoable(qtbot) -> None:
    """BezierItem menu Delete and Delete key go through the command stack."""
    scene, view = _scene_view(qtbot)
    bezier = BezierItem(
        anchors=[QPointF(0, 0), QPointF(200, 0)],
        handles_in=[QPointF(0, 0), QPointF(150, 100)],
        handles_out=[QPointF(50, 100), QPointF(200, 0)],
        layer_id=scene.active_layer.id,
    )
    scene.addItem(bezier)
    assert bezier.scene() is scene

    _simulate_context_menu_delete(bezier, "Delete Bezier")
    assert bezier.scene() is None
    view.command_manager.undo()
    assert bezier.scene() is scene

    key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    bezier.keyPressEvent(key_event)
    assert bezier.scene() is None
    view.command_manager.undo()
    assert bezier.scene() is scene


def test_construction_items_menu_and_key_delete_undoable(qtbot) -> None:
    """ConstructionLineItem and ConstructionCircleItem delete goes through command stack."""
    scene, view = _scene_view(qtbot)
    line = ConstructionLineItem(QPointF(0, 0), QPointF(200, 200))
    circle = ConstructionCircleItem(100, 100, 50)
    scene.addItem(line)
    scene.addItem(circle)

    # Line menu delete
    _simulate_context_menu_delete(line, "Delete Construction Line")
    assert line.scene() is None
    view.command_manager.undo()
    assert line.scene() is scene

    # Circle menu delete
    _simulate_context_menu_delete(circle, "Delete Construction Circle")
    assert circle.scene() is None
    view.command_manager.undo()
    assert circle.scene() is scene

    # Line delete key
    key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    line.keyPressEvent(key_event)
    assert line.scene() is None
    view.command_manager.undo()
    assert line.scene() is scene


def test_callout_and_text_items_menu_delete_undoable(qtbot) -> None:
    """CalloutItem and TextItem menu Delete goes through command stack."""
    scene, view = _scene_view(qtbot)
    callout = CalloutItem(target=QPointF(0, 0), box_offset=QPointF(50, 50), content="Note", layer_id=scene.active_layer.id)
    text = TextItem(100.0, 100.0, content="Label", layer_id=scene.active_layer.id)
    scene.addItem(callout)
    scene.addItem(text)

    _simulate_context_menu_delete(callout, "Delete")
    assert callout.scene() is None
    view.command_manager.undo()
    assert callout.scene() is scene

    _simulate_context_menu_delete(text, "Delete")
    assert text.scene() is None
    view.command_manager.undo()
    assert text.scene() is scene
