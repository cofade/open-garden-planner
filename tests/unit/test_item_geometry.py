"""Editing frames have one definition, including nested groups."""

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.item_geometry import scene_frame_rect, selection_frame_rect
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem
from open_garden_planner.ui.canvas.items.group_item import GroupItem


def test_legacy_handle_import_is_the_canonical_function(qtbot):
    from open_garden_planner.ui.canvas.items.handle_geometry import selection_frame_rect as legacy

    assert legacy is selection_frame_rect


@pytest.mark.parametrize("angle", [0, 37, 215])
def test_nested_group_frame_excludes_member_diagnostics(qtbot, angle):
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    scene = CanvasScene()
    tree = CircleItem(300, 300, 50, object_type=ObjectType.TREE)
    tree.metadata["plant_species"] = {"max_spread_cm": 1000}
    second = RectangleItem(400, 450, 120, 100)
    inner, outer = GroupItem(), GroupItem()
    for item in (tree, second, inner, outer):
        scene.addItem(item)
    inner.addToGroup(tree)
    inner.addToGroup(second)
    outer.addToGroup(inner)
    outer.setTransformOriginPoint(QPointF(300, 300))
    outer.setRotation(angle)
    before = scene_frame_rect(outer)
    scene.set_spacing_circles_visible(True)
    tree.set_spacing_overlap("overlap")
    assert scene_frame_rect(outer) == before
    scene.clear()
