"""Integration tests for clipboard unification across item types (Issue #400, AUD-002, TD-018).

Tests:
1. Ratchet test: CanvasView serialization methods delegate directly to ProjectManager.
2. Copy/paste of a plant preserves spacing override, frost flag, and label visibility.
3. Copy/paste of polyline preserves path_fence_style.
4. Copy/paste supports ArcItem with offset geometry.
5. Copy/paste supports BezierItem with offset anchors and handles.
6. Copy/paste of GroupItem mints new UUIDs for group and all children.
7. Copy/paste supports CalloutItem and offset target.
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.plant_renderer import PlantCategory
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    BezierItem,
    CalloutItem,
    CircleItem,
    GroupItem,
    PolylineItem,
    RectangleItem,
)


def test_canvas_view_delegates_to_project_manager(qtbot: Any) -> None:
    """Ratchet test: CanvasView serialization methods must delegate to ProjectManager."""
    from open_garden_planner.core.project import ProjectManager

    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)

    rect = RectangleItem(10.0, 20.0, 100.0, 50.0)
    ser_view = view._serialize_item(rect)
    ser_pm = ProjectManager._serialize_item(rect)
    assert ser_view == ser_pm

    ser_core_view = view._serialize_item_core(rect)
    ser_core_pm = ProjectManager._serialize_item_core(rect)
    assert ser_core_view == ser_core_pm

    assert ser_view is not None
    deser_view = view._deserialize_item(ser_view)
    assert isinstance(deser_view, RectangleItem)


def test_copy_paste_plant_preserves_spacing_and_frost_and_label(qtbot: Any) -> None:
    """Copy/paste of a plant must preserve spacing override, frost flag, and label visibility (AUD-002)."""
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)

    plant = CircleItem(
        center_x=200.0,
        center_y=200.0,
        radius=30.0,
        object_type=ObjectType.PERENNIAL,
        name="Heirloom Tomato",
    )
    plant.plant_category = PlantCategory.VEGETABLE
    plant.plant_species = "Solanum lycopersicum"
    plant.spacing_radius_cm = 45.0
    plant.frost_protection_needed = True
    plant.label_visible = False
    original_id = plant.item_id

    scene.addItem(plant)
    plant.setSelected(True)

    view.copy_selected()
    view.paste()

    # Find the pasted plant (selected item)
    pasted = [it for it in scene.items() if isinstance(it, CircleItem) and it.isSelected()]
    assert len(pasted) == 1
    p = pasted[0]

    assert p.item_id != original_id
    assert p.name == "Heirloom Tomato"
    assert p.plant_species == "Solanum lycopersicum"
    assert p.plant_category == PlantCategory.VEGETABLE
    assert p.spacing_radius_cm == 45.0
    assert p.frost_protection_needed is True
    assert p.label_visible is False


def test_copy_paste_polyline_preserves_fence_style(qtbot: Any) -> None:
    """Copy/paste of polyline must preserve path_fence_style (AUD-002)."""
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)

    poly = PolylineItem(
        [QPointF(0.0, 0.0), QPointF(100.0, 0.0), QPointF(100.0, 100.0)],
        object_type=ObjectType.FENCE,
        name="Garden Picket Fence",
    )
    poly.path_fence_style = PathFenceStyle.WOODEN_FENCE
    original_id = poly.item_id

    scene.addItem(poly)
    poly.setSelected(True)

    view.copy_selected()
    view.paste()

    pasted = [it for it in scene.items() if isinstance(it, PolylineItem) and it.isSelected()]
    assert len(pasted) == 1
    p = pasted[0]

    assert p.item_id != original_id
    assert p.path_fence_style == PathFenceStyle.WOODEN_FENCE


def test_copy_paste_arc_item(qtbot: Any) -> None:
    """Copy/paste must support ArcItem and offset center and through points (AUD-002)."""
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)

    arc = ArcItem(
        center=QPointF(100.0, 100.0),
        radius=50.0,
        start_deg=0.0,
        span_deg=90.0,
        name="Path Arc",
        through=QPointF(135.35, 135.35),
    )
    original_id = arc.item_id

    scene.addItem(arc)
    arc.setSelected(True)

    view.copy_selected()
    view.paste()

    pasted = [it for it in scene.items() if isinstance(it, ArcItem) and it.isSelected()]
    assert len(pasted) == 1
    p = pasted[0]

    assert p.item_id != original_id
    assert p.name == "Path Arc"
    assert p.radius == 50.0
    # Center should be shifted by paste_offset
    assert p.center.x() == pytest.approx(100.0 + view._paste_offset, rel=1e-3)
    assert p.center.y() == pytest.approx(100.0 + view._paste_offset, rel=1e-3)


def test_copy_paste_bezier_item(qtbot: Any) -> None:
    """Copy/paste must support BezierItem and offset anchor/handle geometry."""
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)

    bezier = BezierItem(
        anchors=[QPointF(0.0, 0.0), QPointF(100.0, 100.0)],
        handles_in=[QPointF(0.0, 0.0), QPointF(70.0, 100.0)],
        handles_out=[QPointF(30.0, 0.0), QPointF(100.0, 100.0)],
        name="Curved Bed",
    )
    original_id = bezier.item_id

    scene.addItem(bezier)
    bezier.setSelected(True)

    view.copy_selected()
    view.paste()

    pasted = [it for it in scene.items() if isinstance(it, BezierItem) and it.isSelected()]
    assert len(pasted) == 1
    p = pasted[0]

    assert p.item_id != original_id
    assert p.name == "Curved Bed"
    assert p._anchors[0].x() == pytest.approx(0.0 + view._paste_offset, rel=1e-3)


def test_copy_paste_group_item_mints_new_ids_for_children(qtbot: Any) -> None:
    """Copy/paste of a group item must mint fresh UUIDs for the group and all its children."""
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)

    group = GroupItem(name="Compound Structure")
    child1 = RectangleItem(0.0, 0.0, 60.0, 40.0)
    child2 = CircleItem(30.0, 20.0, 15.0)
    group.addToGroup(child1)
    group.addToGroup(child2)

    orig_grp_id = group.item_id
    orig_c1_id = child1.item_id
    orig_c2_id = child2.item_id

    scene.addItem(group)
    group.setSelected(True)

    view.copy_selected()
    view.paste()

    pasted = [it for it in scene.items() if isinstance(it, GroupItem) and it.isSelected()]
    assert len(pasted) == 1
    p_grp = pasted[0]

    assert p_grp.item_id != orig_grp_id
    p_children = [c for c in p_grp.childItems() if hasattr(c, "item_id")]
    assert len(p_children) == 2
    for child in p_children:
        assert child.item_id not in (orig_c1_id, orig_c2_id, orig_grp_id)


def test_copy_paste_group_remaps_bed_links_inside_the_copy(
    qtbot: Any, tmp_path: Any,
) -> None:
    """A copied bed and its plant must link to each other, never to the source."""
    from open_garden_planner.core.project import ProjectManager

    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)

    bed = RectangleItem(
        100.0, 100.0, 200.0, 200.0, object_type=ObjectType.RAISED_BED
    )
    plant = CircleItem(
        150.0, 150.0, 15.0, object_type=ObjectType.PERENNIAL
    )
    scene.addItem(bed)
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    peer = RectangleItem(600.0, 100.0, 100.0, 100.0)
    scene.addItem(peer)
    scene.clearSelection()
    for item in (bed, plant, peer):
        item.setSelected(True)
    view.group_selected()
    group = next(
        item for item in scene.items()
        if isinstance(item, GroupItem) and item.parentItem() is None
    )
    scene.clearSelection()
    group.setSelected(True)
    view.copy_selected()
    view.paste()

    pasted_group = next(
        item for item in scene.items()
        if isinstance(item, GroupItem) and item.isSelected()
    )
    pasted_bed = next(
        child for child in pasted_group.childItems()
        if getattr(child, "object_type", None) is ObjectType.RAISED_BED
    )
    pasted_plant = next(
        child for child in pasted_group.childItems()
        if getattr(child, "object_type", None) is ObjectType.PERENNIAL
    )
    assert pasted_plant.parent_bed_id == pasted_bed.item_id
    assert pasted_plant.item_id in pasted_bed.child_item_ids
    assert pasted_bed.item_id != bed.item_id
    assert plant.parent_bed_id == bed.item_id
    assert pasted_plant.item_id not in bed.child_item_ids

    target = tmp_path / "copied-group.ogp"
    ProjectManager().save(scene, target)
    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    loaded_bed = loaded_scene.find_item_by_id(pasted_bed.item_id)
    loaded_plant = loaded_scene.find_item_by_id(pasted_plant.item_id)
    assert loaded_bed is not None
    assert loaded_plant is not None
    assert loaded_plant.parent_bed_id == loaded_bed.item_id
    assert loaded_plant.item_id in loaded_bed.child_item_ids


def test_copy_and_duplicate_keep_one_consistent_link_for_a_grouped_bed(
    qtbot: Any,
) -> None:
    """A nested bed's claim and a top-level follower must not both survive."""
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)

    bed = RectangleItem(
        100.0, 100.0, 200.0, 200.0, object_type=ObjectType.RAISED_BED
    )
    plant = CircleItem(150.0, 150.0, 15.0, object_type=ObjectType.PERENNIAL)
    scene.addItem(bed)
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    peer = RectangleItem(600.0, 100.0, 100.0, 100.0)
    scene.addItem(peer)
    scene.clearSelection()
    for item in (bed, peer):
        item.setSelected(True)
    view.group_selected()
    group = next(
        item for item in scene.items()
        if isinstance(item, GroupItem) and item.parentItem() is None
    )

    offset = view._paste_offset
    target = QPointF(
        plant.mapToScene(plant.rect().center()).x() + offset,
        plant.mapToScene(plant.rect().center()).y() + offset,
    )
    _smaller = RectangleItem(
        target.x() - 20.0, target.y() - 20.0, 40.0, 40.0,
        object_type=ObjectType.RAISED_BED,
    )
    scene.addItem(_smaller)

    scene.clearSelection()
    group.setSelected(True)
    plant.setSelected(True)
    view.copy_selected()
    view.paste()

    pasted_group = next(
        item for item in scene.items()
        if isinstance(item, GroupItem) and item.isSelected()
    )
    pasted_bed = next(
        child for child in pasted_group.childItems()
        if getattr(child, "object_type", None) is ObjectType.RAISED_BED
    )
    pasted_plant = next(
        item for item in scene.items()
        if isinstance(item, CircleItem) and item.isSelected()
    )

    def claimants(plant_id: Any) -> list[RectangleItem]:
        return [
            item for item in scene.items()
            if isinstance(item, RectangleItem)
            and plant_id in item.child_item_ids
        ]

    pasted_claimants = claimants(pasted_plant.item_id)
    assert len(pasted_claimants) == 1
    assert pasted_plant.parent_bed_id == pasted_claimants[0].item_id
    assert pasted_plant.item_id not in pasted_bed.child_item_ids

    view.duplicate_selected()
    duplicated_plant = next(
        item for item in scene.items()
        if isinstance(item, CircleItem) and item.isSelected()
    )
    duplicated_claimants = claimants(duplicated_plant.item_id)
    assert len(duplicated_claimants) == 1
    assert duplicated_plant.parent_bed_id == duplicated_claimants[0].item_id


def test_copy_paste_callout_item(qtbot: Any) -> None:
    """Copy/paste must support CalloutItem and offset target position."""
    scene = CanvasScene()
    view = CanvasView(scene)
    qtbot.addWidget(view)

    callout = CalloutItem(
        target=QPointF(50.0, 50.0),
        box_offset=QPointF(40.0, -30.0),
        content="Important Soil Note",
    )
    orig_id = callout.item_id

    scene.addItem(callout)
    callout.setSelected(True)

    view.copy_selected()
    view.paste()

    pasted = [it for it in scene.items() if isinstance(it, CalloutItem) and it.isSelected()]
    assert len(pasted) == 1
    p = pasted[0]

    assert p.item_id != orig_id
    assert p.content == "Important Soil Note"
    assert p.pos().x() == pytest.approx(50.0 + view._paste_offset, rel=1e-3)
    assert p.pos().y() == pytest.approx(50.0 + view._paste_offset, rel=1e-3)


def test_offset_item_dict_nested_position() -> None:
    """_offset_item_dict must offset nested position dicts such as in BackgroundImageItem (FIND-07)."""
    from open_garden_planner.ui.canvas.canvas_view import _offset_item_dict

    data = {
        "type": "background_image",
        "position": {"x": 100.0, "y": 200.0},
        "opacity": 0.8,
    }
    offset = _offset_item_dict(data, 20.0, 30.0)
    assert offset["position"]["x"] == 120.0
    assert offset["position"]["y"] == 230.0
