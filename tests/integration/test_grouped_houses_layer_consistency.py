"""Integration tests for grouping houses from different layers (issue #741)."""

import uuid

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from open_garden_planner.core.commands import CommandManager, GroupCommand, UngroupCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.roof_ridge_link import build_linked_ridge


def _make_house(scene: CanvasScene, x: float, y: float, w: float, h: float, layer_id: uuid.UUID) -> tuple[PolygonItem, object]:
    pts = [QPointF(x, y), QPointF(x + w, y), QPointF(x + w, y + h), QPointF(x, y + h)]
    house = PolygonItem(QPolygonF(pts), object_type=ObjectType.HOUSE, layer_id=layer_id)
    scene.addItem(house)
    ridge = build_linked_ridge(house, layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    return house, ridge


def test_grouping_houses_from_different_layers_normalises_layers(qtbot: object) -> None:
    """Grouping two houses from different layers consolidates members and ridges onto group layer."""
    scene = CanvasScene()
    mgr = CommandManager()

    layer1 = Layer(name="Layer 1")
    layer2 = Layer(name="Layer 2")
    scene.set_layers([layer1, layer2])

    house_a, ridge_a = _make_house(scene, 0, 0, 100, 100, layer1.id)
    house_b, ridge_b = _make_house(scene, 200, 0, 100, 100, layer2.id)

    assert house_a.layer_id == layer1.id
    assert ridge_a.layer_id == layer1.id
    assert house_b.layer_id == layer2.id
    assert ridge_b.layer_id == layer2.id

    # Group House A and House B
    cmd = GroupCommand(scene, [house_a, house_b])
    mgr.execute(cmd)

    group = house_a.parentItem()
    assert group is not None
    group_layer = group.layer_id
    assert group_layer == layer1.id

    # All members and their linked ridges are consolidated onto group's layer
    assert house_a.layer_id == group_layer
    assert house_b.layer_id == group_layer
    assert ridge_a.layer_id == group_layer
    assert ridge_b.layer_id == group_layer

    # Toggle Layer 2 visibility off: group, members and ridges STAY visible
    scene.update_layer_visibility(layer2.id, False)
    assert house_a.isVisible()
    assert house_b.isVisible()
    assert ridge_a.isVisible()
    assert ridge_b.isVisible()

    # Toggle Layer 1 visibility off: group, members and ridges are ALL hidden
    scene.update_layer_visibility(layer1.id, False)
    assert not house_a.isVisible()
    assert not house_b.isVisible()
    assert not ridge_a.isVisible()
    assert not ridge_b.isVisible()

    # Toggle Layer 1 visibility back on: all visible
    scene.update_layer_visibility(layer1.id, True)
    assert house_a.isVisible()
    assert house_b.isVisible()
    assert ridge_a.isVisible()
    assert ridge_b.isVisible()

    # Undo: restores original individual layers
    mgr.undo()
    assert house_a.parentItem() is None
    assert house_b.parentItem() is None
    assert house_a.layer_id == layer1.id
    assert ridge_a.layer_id == layer1.id
    assert house_b.layer_id == layer2.id
    assert ridge_b.layer_id == layer2.id

    # Layer 2 is currently hidden: so House B and its ridge are hidden
    assert house_a.isVisible()
    assert ridge_a.isVisible()
    assert not house_b.isVisible()
    assert not ridge_b.isVisible()

    # Redo: grouped again, all visible under Layer 1
    mgr.redo()
    assert house_a.parentItem() is not None
    assert house_b.parentItem() is not None
    assert house_b.layer_id == layer1.id
    assert ridge_b.layer_id == layer1.id
    assert house_b.isVisible()
    assert ridge_b.isVisible()

    # Ungroup: keeps members and ridges on the group layer
    ungroup_cmd = UngroupCommand(scene, house_a.parentItem())
    mgr.execute(ungroup_cmd)
    assert house_a.parentItem() is None
    assert house_b.parentItem() is None
    assert house_a.layer_id == layer1.id
    assert house_b.layer_id == layer1.id
    assert ridge_a.layer_id == layer1.id
    assert ridge_b.layer_id == layer1.id


def test_visibility_resolves_ridge_layer_through_owner_group_fallback(qtbot: object) -> None:
    """Visibility resolves a ridge's layer through its owner's group as a fallback for plans saved earlier."""
    scene = CanvasScene()
    layer1 = Layer(name="Layer 1")
    layer2 = Layer(name="Layer 2")
    scene.set_layers([layer1, layer2])

    house, ridge = _make_house(scene, 0, 0, 100, 100, layer2.id)
    # Put house in a group on Layer 1, but simulate an old plan where ridge.layer_id is still Layer 2
    from open_garden_planner.ui.canvas.items.group_item import GroupItem
    group = GroupItem(layer_id=layer1.id)
    scene.addItem(group)
    group.addToGroup(house)
    ridge.layer_id = layer2.id

    # Layer 2 is hidden, Layer 1 is visible
    scene.update_layer_visibility(layer2.id, False)
    scene.update_layer_visibility(layer1.id, True)

    # Ridge should be VISIBLE because owner house is in group on Layer 1 (fallback)
    scene._update_items_visibility()
    assert ridge.isVisible()

    # Layer 1 is hidden
    scene.update_layer_visibility(layer1.id, False)
    assert not ridge.isVisible()
