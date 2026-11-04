"""Integration tests: a shape converted into a HOUSE gains its roof ridge (#690).

A HOUSE's ``ROOF_RIDGE`` is derived geometry owned by the polygon (ADR-046).
Drawing a house polygon with the polygon tool creates it, and the Agent API's
``create_object`` creates it; converting an existing rectangle/polygon through
the Properties panel or the Change Type menu used to leave the house without
one — geometrically fine in 3D but missing the 2D ridge line (and the roof
tiles the ridge frame places).

The ridge must be created in the SAME undo step as the type change, survive
redo without a new UUID, and go away again when the shape stops being a HOUSE.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtWidgets import QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core.commands import ChangeObjectTypeCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolylineItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.roof_ridge_link import (
    build_linked_ridge,
    linked_ridge,
    outline_polygon,
)
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel


def _scene_view(qtbot) -> tuple[CanvasScene, CanvasView]:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    return scene, view


def _house_rect(scene: CanvasScene) -> RectangleItem:
    rect = RectangleItem(
        100,
        50,
        400,
        200,
        object_type=ObjectType.GENERIC_RECTANGLE,
        layer_id=scene.active_layer.id,
    )
    scene.addItem(rect)
    return rect


def _ridge_of(item) -> PolylineItem | None:
    ridge = linked_ridge(item)
    assert ridge is None or isinstance(ridge, PolylineItem)
    return ridge


def _expected_ridge_endpoints(item) -> tuple[QPointF, QPointF]:
    """The canonical geometry, mapped through the item's own transform."""
    polygon = outline_polygon(item)
    assert polygon is not None
    local_1, local_2 = compute_roof_ridge_endpoints(polygon, QPointF(0.0, 0.0))
    return item.mapToScene(local_1), item.mapToScene(local_2)


def test_properties_panel_conversion_creates_the_linked_ridge(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    panel = PropertiesPanel(command_manager=view.command_manager)

    panel._on_property_changed(rect, "object_type", ObjectType.HOUSE)

    assert rect.object_type == ObjectType.HOUSE
    ridge = _ridge_of(rect)
    assert ridge is not None, "a HOUSE converted from a rectangle must get a ridge"
    assert str(rect.item_id) == ridge.metadata["owner_polygon_id"]
    assert ridge.scene() is scene
    assert len(view.command_manager._undo_stack) == 1

    p1, p2 = _expected_ridge_endpoints(rect)
    assert ridge.points[0] == p1 and ridge.points[-1] == p2


def test_undo_removes_the_ridge_and_redo_restores_the_same_one(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    panel = PropertiesPanel(command_manager=view.command_manager)
    panel._on_property_changed(rect, "object_type", ObjectType.HOUSE)
    ridge = _ridge_of(rect)
    assert ridge is not None
    ridge_id = ridge.item_id

    view.command_manager.undo()
    assert rect.object_type == ObjectType.GENERIC_RECTANGLE
    assert ridge.scene() is None
    assert linked_ridge(rect) is None  # no longer in the scene

    view.command_manager.redo()
    restored = _ridge_of(rect)
    assert restored is ridge
    assert restored.item_id == ridge_id, "redo must not mint a new ridge identity"
    assert restored.scene() is scene
    assert len(view.command_manager._undo_stack) == 1


def test_context_menu_change_type_uses_the_same_command(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    rect.setSelected(True)

    rect._dispatch_change_type(ObjectType.HOUSE)

    ridge = _ridge_of(rect)
    assert ridge is not None
    assert len(view.command_manager._undo_stack) == 1
    view.command_manager.undo()
    assert ridge.scene() is None


def test_polygon_conversion_creates_the_ridge_too(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    polygon = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.GENERIC_POLYGON,
        layer_id=scene.active_layer.id,
    )
    polygon.setPos(200, 200)
    scene.addItem(polygon)

    polygon._dispatch_change_type(ObjectType.HOUSE)

    ridge = _ridge_of(polygon)
    assert ridge is not None
    p1, p2 = _expected_ridge_endpoints(polygon)
    assert ridge.points[0] == p1 and ridge.points[-1] == p2


def test_converting_away_from_house_removes_the_ridge_and_undo_restores_it(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    panel = PropertiesPanel(command_manager=view.command_manager)
    panel._on_property_changed(rect, "object_type", ObjectType.HOUSE)
    ridge = _ridge_of(rect)
    assert ridge is not None

    panel._on_property_changed(rect, "object_type", ObjectType.GARDEN_BED)
    assert rect.object_type == ObjectType.GARDEN_BED
    assert ridge.scene() is None
    assert linked_ridge(rect) is None

    view.command_manager.undo()
    assert rect.object_type == ObjectType.HOUSE
    assert ridge.scene() is scene
    assert linked_ridge(rect) is ridge


def test_converting_without_a_house_does_not_create_a_ridge(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    panel = PropertiesPanel(command_manager=view.command_manager)

    panel._on_property_changed(rect, "object_type", ObjectType.GARDEN_BED)

    assert rect.object_type == ObjectType.GARDEN_BED
    assert _ridge_of(rect) is None


def test_ridge_geometry_follows_a_rotated_shape(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    rect.setTransformOriginPoint(rect.rect().center())
    rect.setRotation(90.0)
    rect.rotation_angle = 90.0

    ridge = build_linked_ridge(rect, rect.layer_id)
    assert ridge is not None
    p1, p2 = _expected_ridge_endpoints(rect)
    assert ridge.points[0] == p1 and ridge.points[-1] == p2
    # A quarter turn swaps the long axis: the ridge now runs vertically.
    assert abs(p1.x() - p2.x()) < 1e-6
    assert abs(p1.y() - p2.y()) > 300.0


def test_moving_a_house_to_another_layer_moves_its_ridge(qtbot) -> None:
    from open_garden_planner.core.commands import MoveToLayerCommand
    from open_garden_planner.models.layer import Layer

    scene, view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    scene.addItem(house)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    original_layer = ridge.layer_id

    target = Layer(name="Target", z_order=99)
    scene.add_layer(target)
    command = MoveToLayerCommand([house], target.id, scene, target.name)
    view.command_manager.execute(command)

    assert house.layer_id == target.id
    assert ridge.layer_id == target.id
    assert command.description == "Move 1 item(s) to layer 'Target'"

    view.command_manager.undo()
    assert house.layer_id == original_layer
    assert ridge.layer_id == original_layer


def test_converting_away_removes_a_ridge_constraint_and_undo_restores_it(qtbot) -> None:
    """A ridge is constrainable; removing it must remove its graph anchors too."""
    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import AnchorType

    scene, view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(400, 0), QPointF(400, 200), QPointF(0, 200)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    peer = RectangleItem(600, 0, 50, 50, layer_id=scene.active_layer.id)
    scene.addItem(house)
    scene.addItem(peer)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    graph = scene.constraint_graph
    graph.add_constraint(
        AnchorRef(item_id=ridge.item_id, anchor_type=AnchorType.CENTER),
        AnchorRef(item_id=peer.item_id, anchor_type=AnchorType.CENTER),
        50.0,
    )

    panel = PropertiesPanel(command_manager=view.command_manager)
    panel._on_property_changed(house, "object_type", ObjectType.GARDEN_BED)

    assert graph.constraints == {}
    assert ridge.scene() is None

    view.command_manager.undo()
    assert ridge.scene() is scene
    assert len(graph.constraints) == 1


def test_grouping_a_house_lifts_its_ridge_above_the_group(qtbot) -> None:
    """The ridge of a grouped house must stay visible, not fall behind it.

    A ridge is a top-level sibling of its house. Once the house joins a group,
    the normalizer resolves the ridge's owner to the GROUP; without a refresh
    at grouping time the ridge keeps its pre-group z (above the house, below
    the new group) and only its ends peek out (manual test 2.7).
    """
    from open_garden_planner.core.commands import GroupCommand

    scene, _view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    other = RectangleItem(400, 0, 50, 50, layer_id=scene.active_layer.id)
    scene.addItem(house)
    scene.addItem(other)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    assert ridge.zValue() > house.zValue()

    GroupCommand(scene, [house, other]).execute()
    group = house.parentItem()
    assert group is not None
    assert ridge.scene() is scene
    assert ridge.zValue() > group.zValue(), (
        "the grouped house's ridge renders behind the group"
    )


def test_a_group_offers_move_to_layer_and_moves_its_nested_ridge(qtbot) -> None:
    """A group is a layered item: its menu must move it (and its ridge) too."""
    from open_garden_planner.core.commands import GroupCommand
    from open_garden_planner.models.layer import Layer

    scene, _view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    other = RectangleItem(400, 0, 50, 50, layer_id=scene.active_layer.id)
    scene.addItem(house)
    scene.addItem(other)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    GroupCommand(scene, [house, other]).execute()
    group = house.parentItem()
    assert group is not None

    target = Layer(name="Target", z_order=99)
    scene.add_layer(target)
    menu = QMenu()
    layer_menu = group._build_move_to_layer_menu(menu)
    assert layer_menu is not None, "a group with a second layer offers Move to Layer"
    assert [action.text() for action in layer_menu.actions()] == ["Target"]

    group._dispatch_move_to_layer(target.id)
    assert group.layer_id == target.id
    assert ridge.layer_id == target.id


def test_moving_a_group_to_another_layer_moves_a_nested_houses_ridge(qtbot) -> None:
    from open_garden_planner.core.commands import GroupCommand, MoveToLayerCommand
    from open_garden_planner.models.layer import Layer

    scene, view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    other = RectangleItem(400, 0, 50, 50, layer_id=scene.active_layer.id)
    scene.addItem(house)
    scene.addItem(other)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    GroupCommand(scene, [house, other]).execute()
    group = house.parentItem()
    assert group is not None
    original_layer = ridge.layer_id

    target = Layer(name="Target", z_order=99)
    scene.add_layer(target)
    command = MoveToLayerCommand([group], target.id, scene, target.name)
    view.command_manager.execute(command)

    assert ridge.layer_id == target.id
    assert house.layer_id == target.id, "a group's members follow it to the target"
    assert other.layer_id == target.id
    assert command.description == "Move 1 item(s) to layer 'Target'"

    view.command_manager.undo()
    assert ridge.layer_id == original_layer
    assert house.layer_id == scene.active_layer.id
    assert other.layer_id == scene.active_layer.id


def test_a_group_controls_its_members_visibility_by_its_own_layer(qtbot) -> None:
    """A plan saved before the group-layer fix must still render as one unit.

    This is the owner's file from manual test 2.7: the group is on layer 2,
    while the two shapes it contains still carry layer 1. Hiding layer 1 must
    not take the group's members with it.
    """
    from open_garden_planner.core.commands import GroupCommand
    from open_garden_planner.models.layer import Layer

    scene, _view = _scene_view(qtbot)
    source = scene.active_layer
    house = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.HOUSE,
        layer_id=source.id,
    )
    other = RectangleItem(400, 0, 50, 50, layer_id=source.id)
    scene.addItem(house)
    scene.addItem(other)
    ridge = build_linked_ridge(house, source.id)
    assert ridge is not None
    scene.addItem(ridge)
    GroupCommand(scene, [house, other]).execute()
    group = house.parentItem()
    assert group is not None

    target = Layer(name="Target", z_order=99)
    scene.add_layer(target)
    # Simulate the saved state: only the group wrapper and its derived ridge
    # moved; the members kept the layer they were drawn on.
    group.layer_id = target.id
    ridge.layer_id = target.id

    source.visible = False
    target.visible = True
    target.opacity = 0.4
    scene._update_items_visibility()
    assert group.isVisible()
    assert house.isVisible(), "the grouped house followed its old layer"
    assert other.isVisible(), "the grouped rectangle followed its old layer"
    assert group.opacity() == pytest.approx(0.4)
    assert house.opacity() == pytest.approx(1.0), "group opacity must not be squared"
    assert other.opacity() == pytest.approx(1.0)

    source.visible = True
    target.visible = False
    scene._update_items_visibility()
    assert not group.isVisible()
    assert not house.isVisible()
    assert not other.isVisible()


def test_ungrouping_keeps_members_on_the_groups_layer(qtbot) -> None:
    """A legacy group's members join its layer when the group is dissolved.

    Undo restores each member's own layer, so ungroup/undo stays symmetric.
    """
    from open_garden_planner.core.commands import GroupCommand, UngroupCommand
    from open_garden_planner.models.layer import Layer

    scene, view = _scene_view(qtbot)
    source = scene.active_layer
    house = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.HOUSE,
        layer_id=source.id,
    )
    other = RectangleItem(400, 0, 50, 50, layer_id=source.id)
    scene.addItem(house)
    scene.addItem(other)
    GroupCommand(scene, [house, other]).execute()
    group = house.parentItem()
    assert group is not None

    target = Layer(name="Target", z_order=99)
    scene.add_layer(target)
    # The saved state from before the layer-ownership fix: wrapper and ridge
    # moved, members still on the layer they were drawn on.
    group.layer_id = target.id

    view.command_manager.execute(UngroupCommand(scene, group))
    assert house.parentItem() is None
    assert house.layer_id == target.id
    assert other.layer_id == target.id

    view.command_manager.undo()
    assert house.parentItem() is not None
    assert house.layer_id == source.id
    assert other.layer_id == source.id


def test_the_command_does_not_mint_a_second_ridge_on_repeat_execute(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)

    def apply(itm, state):
        for key, value in state.items():
            if hasattr(itm, key):
                setattr(itm, key, value)
        if hasattr(itm, "_setup_styling"):
            itm._setup_styling()

    old_state = {"object_type": ObjectType.GENERIC_RECTANGLE}
    new_state = {"object_type": ObjectType.HOUSE}
    command = ChangeObjectTypeCommand(scene, rect, old_state, new_state, apply)

    command.execute()
    ridge = _ridge_of(rect)
    assert ridge is not None
    command.undo()
    command.execute()
    command.undo()
    command.execute()
    assert _ridge_of(rect) is ridge
    assert len([i for i in scene.items() if isinstance(i, PolylineItem)]) == 1


def test_undo_of_a_same_type_house_change_removes_the_created_ridge(qtbot) -> None:
    """A HOUSE with no ridge that is "changed" to HOUSE still gains one.

    Undo must remove it again: the pre-command item had no ridge, so leaving it
    makes undo asymmetric (round-6 review P2).
    """
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    rect.object_type = ObjectType.HOUSE  # a legacy/pre-fix HOUSE without a ridge
    assert "ridge_item_id" not in rect.metadata

    def apply(itm, state):
        for key, value in state.items():
            if hasattr(itm, key):
                setattr(itm, key, value)
        if hasattr(itm, "_setup_styling"):
            itm._setup_styling()

    command = ChangeObjectTypeCommand(
        scene,
        rect,
        {"object_type": ObjectType.HOUSE},
        {"object_type": ObjectType.HOUSE},
        apply,
    )
    command.execute()
    ridge = _ridge_of(rect)
    assert ridge is not None and ridge.scene() is scene

    command.undo()
    assert ridge.scene() is None
    assert "ridge_item_id" not in rect.metadata

    command.execute()
    assert ridge.scene() is scene
    assert linked_ridge(rect) is ridge


def test_undo_restores_a_legacy_ridge_link_on_a_non_house(qtbot) -> None:
    """A pre-#690 plan can keep a ridge while its shape is not a HOUSE.

    Converting it to HOUSE adopts that live ridge; undo must restore the
    one-sided link, not clear it, or the ridge stays visible unowned and redo
    builds a second one (round-7 review P2).
    """
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    ridge = build_linked_ridge(rect, rect.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    panel = PropertiesPanel(command_manager=view.command_manager)
    panel._on_property_changed(rect, "object_type", ObjectType.HOUSE)
    assert linked_ridge(rect) is ridge

    view.command_manager.undo()
    assert rect.object_type == ObjectType.GENERIC_RECTANGLE
    assert rect.metadata.get("ridge_item_id") == str(ridge.item_id)
    assert ridge.scene() is scene

    view.command_manager.redo()
    assert linked_ridge(rect) is ridge
    assert len(
        [i for i in scene.items() if isinstance(i, PolylineItem)
         and i.object_type == ObjectType.ROOF_RIDGE]
    ) == 1, "redo built a second ridge"


def test_deleting_a_ridge_directly_clears_its_owners_link(qtbot) -> None:
    """A free-standing ridge is selectable; deleting it must clear the owner's
    ``ridge_item_id`` in the same step, or the house claims a missing ridge."""
    scene, view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(400, 0), QPointF(400, 200), QPointF(0, 200)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    scene.addItem(house)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    assert house.metadata.get("ridge_item_id") == str(ridge.item_id)

    ridge.setSelected(True)
    house.setSelected(False)
    view._delete_selected_items()

    assert ridge.scene() is None
    assert "ridge_item_id" not in house.metadata

    view.command_manager.undo()
    assert ridge.scene() is scene
    assert house.metadata.get("ridge_item_id") == str(ridge.item_id)


def test_a_grouped_house_carries_its_ridge_on_a_group_move(qtbot) -> None:
    from open_garden_planner.core.commands import GroupCommand

    scene, view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    other = RectangleItem(0, 0, 50, 50, layer_id=scene.active_layer.id)
    scene.addItem(other)
    scene.addItem(house)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    GroupCommand(scene, [house, other]).execute()
    group = house.parentItem()
    assert group is not None

    before = [QPointF(p) for p in ridge.points]
    group.setPos(group.pos() + QPointF(600.0, 250.0))

    delta_x = ridge.points[0].x() - before[0].x()
    delta_y = ridge.points[0].y() - before[0].y()
    assert (delta_x, delta_y) == (600.0, 250.0)


def test_ungrouping_a_moved_group_does_not_double_the_ridge(qtbot) -> None:
    from open_garden_planner.core.commands import GroupCommand

    scene, view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    other = RectangleItem(0, 0, 50, 50, layer_id=scene.active_layer.id)
    scene.addItem(house)
    scene.addItem(other)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    GroupCommand(scene, [house, other]).execute()
    group = house.parentItem()
    assert group is not None
    group.setPos(group.pos() + QPointF(300.0, 200.0))
    after_move = [QPointF(p) for p in ridge.points]

    group.setSelected(True)
    view.ungroup_selected()

    assert [QPointF(p) for p in ridge.points] == after_move
    assert house.pos() == QPointF(300.0, 200.0)


def test_deleting_a_group_removes_its_nested_house_ridge(qtbot) -> None:
    from open_garden_planner.core.commands import GroupCommand

    scene, view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(300, 0), QPointF(300, 150), QPointF(0, 150)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    other = RectangleItem(0, 0, 50, 50, layer_id=scene.active_layer.id)
    scene.addItem(house)
    scene.addItem(other)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    GroupCommand(scene, [house, other]).execute()
    group = house.parentItem()
    assert group is not None

    group.setSelected(True)
    view._delete_selected_items()

    assert group.scene() is None
    assert ridge.scene() is None, "the ridge of a grouped house was left in the plan"


def test_a_converted_rectangle_ridge_follows_move_resize_and_rotation(qtbot) -> None:
    from open_garden_planner.ui.canvas.geometry_apply import apply_rect_like_geometry

    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    rect._dispatch_change_type(ObjectType.HOUSE)
    ridge = _ridge_of(rect)
    assert ridge is not None

    rect.setPos(rect.pos() + QPointF(250.0, 100.0))
    p1, p2 = _expected_ridge_endpoints(rect)
    assert ridge.points[0] == p1 and ridge.points[-1] == p2

    center = rect.mapToScene(rect.rect().center())
    apply_rect_like_geometry(
        rect,
        {
            "rect_x": 0.0,
            "rect_y": 0.0,
            "width": 600.0,
            "height": 120.0,
            "pos_x": center.x() - 300.0,
            "pos_y": center.y() - 60.0,
        },
    )
    p1, p2 = _expected_ridge_endpoints(rect)
    assert ridge.points[0] == p1 and ridge.points[-1] == p2
    assert abs(p2.x() - p1.x()) > 500.0  # the ridge spans the new long axis

    rect._apply_rotation(90.0)
    p1, p2 = _expected_ridge_endpoints(rect)
    assert ridge.points[0] == p1 and ridge.points[-1] == p2
    assert abs(p1.x() - p2.x()) < 1e-6  # a quarter turn makes the ridge vertical


def test_leaving_house_drops_the_link_and_undo_restores_it(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(0, 0), QPointF(400, 0), QPointF(400, 200), QPointF(0, 200)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    scene.addItem(house)
    first = build_linked_ridge(house, house.layer_id)
    assert first is not None
    scene.addItem(first)
    assert linked_ridge(house) is first

    panel = PropertiesPanel(command_manager=view.command_manager)
    panel._on_property_changed(house, "object_type", ObjectType.GARDEN_BED)
    assert "ridge_item_id" not in house.metadata
    assert first.scene() is None

    panel._on_property_changed(house, "object_type", ObjectType.HOUSE)
    second = _ridge_of(house)
    assert second is not None and second is not first

    # Undo the second conversion, then the first: the ORIGINAL link and the
    # original ridge must come back, not just a ridge in the scene.
    view.command_manager.undo()
    assert "ridge_item_id" not in house.metadata
    assert second.scene() is None
    view.command_manager.undo()
    assert house.metadata.get("ridge_item_id") == str(first.item_id)
    assert linked_ridge(house) is first
    assert first.scene() is scene


def test_a_dangling_link_is_cleared_when_the_house_stops_being_one(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    rect.object_type = ObjectType.HOUSE
    rect.set_metadata("ridge_item_id", str(uuid.uuid4()))  # names nothing
    panel = PropertiesPanel(command_manager=view.command_manager)

    panel._on_property_changed(rect, "object_type", ObjectType.GARDEN_BED)

    assert "ridge_item_id" not in rect.metadata


def test_a_non_house_type_change_never_leaves_a_stale_ridge_link(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    rect._dispatch_change_type(ObjectType.HOUSE)
    panel = PropertiesPanel(command_manager=view.command_manager)
    panel._on_property_changed(rect, "object_type", ObjectType.GARDEN_BED)
    panel._on_property_changed(rect, "object_type", ObjectType.LAWN)
    assert "ridge_item_id" not in rect.metadata


def test_a_copied_link_cannot_adopt_the_source_ridge(qtbot) -> None:
    """A mirror/legacy copy carries the metadata verbatim; the reverse link
    refuses it, so moving or deleting the copy never touches the source."""
    scene, view = _scene_view(qtbot)
    source = _house_rect(scene)
    source._dispatch_change_type(ObjectType.HOUSE)
    source_ridge = _ridge_of(source)
    assert source_ridge is not None

    clone = PolygonItem(
        [QPointF(0, 0), QPointF(400, 0), QPointF(400, 200), QPointF(0, 200)],
        object_type=ObjectType.HOUSE,
        metadata=dict(source.metadata),
        layer_id=scene.active_layer.id,
    )
    scene.addItem(clone)
    assert _ridge_of(clone) is None  # the reverse owner link does not match

    before = [QPointF(p) for p in source_ridge.points]
    clone.setPos(900.0, 900.0)
    assert source_ridge.points == before

    clone.setSelected(True)
    source.setSelected(False)
    view._delete_selected_items()
    assert source_ridge.scene() is scene
    assert linked_ridge(source) is source_ridge


def test_duplicating_a_house_gets_its_own_ridge(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    original = _house_rect(scene)
    original._dispatch_change_type(ObjectType.HOUSE)
    original_ridge = _ridge_of(original)
    assert original_ridge is not None

    original.setSelected(True)
    view.duplicate_selected()
    copies = [
        item
        for item in scene.items()
        if isinstance(item, RectangleItem) and item is not original
    ]
    assert len(copies) == 1
    copy = copies[0]
    copy_ridge = _ridge_of(copy)
    assert copy_ridge is not None and copy_ridge is not original_ridge
    assert copy_ridge.metadata["owner_polygon_id"] == str(copy.item_id)

    before = [QPointF(p) for p in original_ridge.points]
    copy.setPos(copy.pos() + QPointF(900.0, 0.0))
    assert original_ridge.points == before, "the copy re-targeted the original's ridge"

    copy.setSelected(True)
    original.setSelected(False)
    view._delete_selected_items()
    assert original_ridge.scene() is scene
    assert linked_ridge(original) is original_ridge


def test_copying_a_lone_ridge_pastes_nothing_and_adds_no_undo_step(qtbot) -> None:
    """A derived ridge without its owner is dropped — silently doing nothing is
    still a lie and an empty undo step (round-7 review P2)."""
    scene, view = _scene_view(qtbot)
    ridge = PolylineItem(
        [QPointF(100, 100), QPointF(500, 100)],
        object_type=ObjectType.ROOF_RIDGE,
        layer_id=scene.active_layer.id,
    )
    ridge.set_metadata("owner_polygon_id", str(uuid.uuid4()))  # owner not copied
    scene.addItem(ridge)
    ridge.setSelected(True)
    view.copy_selected()

    statuses: list[str] = []
    view.status_message.connect(statuses.append)
    depth = len(view.command_manager._undo_stack)
    view.paste()
    assert statuses[-1] == "Nothing to paste"
    assert len(view.command_manager._undo_stack) == depth

    ridge.setSelected(True)
    view.duplicate_selected()
    assert statuses[-1] == "Nothing to duplicate"
    assert len(view.command_manager._undo_stack) == depth
    assert ridge.scene() is scene


def test_ridge_metadata_is_a_stable_uuid_pair(qtbot) -> None:
    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    ridge = build_linked_ridge(rect, rect.layer_id)
    assert ridge is not None
    assert uuid.UUID(ridge.metadata["owner_polygon_id"]) == rect.item_id
    assert uuid.UUID(rect.metadata["ridge_item_id"]) == ridge.item_id


def _context_event() -> MagicMock:
    event = MagicMock(spec=QGraphicsSceneContextMenuEvent)
    event.screenPos.return_value = QPoint(0, 0)
    return event


def test_context_menu_delete_removes_the_ridge_in_the_same_undo_step(
    qtbot, monkeypatch
) -> None:
    """The polygon menu's Delete used ``scene.removeItem`` directly.

    That bypassed the command stack *and* the ridge expansion: the house
    vanished, its free-standing ridge stayed (round-5 review of #690).
    """
    scene, view = _scene_view(qtbot)
    house = PolygonItem(
        [QPointF(100, 100), QPointF(500, 100), QPointF(500, 300), QPointF(100, 300)],
        object_type=ObjectType.HOUSE,
        layer_id=scene.active_layer.id,
    )
    scene.addItem(house)
    ridge = build_linked_ridge(house, house.layer_id)
    assert ridge is not None
    scene.addItem(ridge)
    house.setSelected(True)

    def fake_exec(menu_self, *_args, **_kwargs):
        return next(
            (a for a in menu_self.actions() if a.text() == "Delete"), None
        )

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    house.contextMenuEvent(_context_event())

    assert house.scene() is None
    assert ridge.scene() is None, "the menu delete left the linked ridge behind"
    assert view.command_manager.can_undo

    view.command_manager.undo()
    assert house.scene() is scene
    assert ridge.scene() is scene
    assert linked_ridge(house) is ridge


def test_converted_rectangle_corner_drag_re_derives_the_ridge(qtbot) -> None:
    """A corner drag changes ``rect()`` without moving ``pos()``.

    No ``itemChange`` fires, so a converted rectangle's ridge needs its own
    hook in ``_move_corner_to`` (round-5 review of #690).
    """
    from open_garden_planner.ui.canvas.items.resize_handle import RectCorner

    scene, view = _scene_view(qtbot)
    rect = _house_rect(scene)
    rect._dispatch_change_type(ObjectType.HOUSE)
    ridge = _ridge_of(rect)
    assert ridge is not None
    before = [QPointF(p) for p in ridge.points]

    rect._move_corner_to(
        RectCorner.BOTTOM_RIGHT,
        QPointF(100.0, 80.0),
        rect.rect(),
        rect.pos(),
    )

    p1, p2 = _expected_ridge_endpoints(rect)
    assert ridge.points[0] == p1 and ridge.points[-1] == p2
    assert [QPointF(p) for p in ridge.points] != before, (
        "the corner drag did not reach the ridge hook"
    )
