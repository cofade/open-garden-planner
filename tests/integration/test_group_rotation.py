"""A selected group turns as one unit (#1022).

The behaviour is the single-item rotation contract applied one level up: one
handle above the group's own outline, a pivot at that outline's centre, Shift
snapping from the shared handle, and one undo step for the whole gesture.
Members keep their local geometry; Qt's group transform is what turns their
scene positions together, so a composed layout keeps its arrangement.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.agent_api import queries
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    CalloutItem,
    CircleItem,
    GroupItem,
    RectangleItem,
    TextItem,
)
from open_garden_planner.ui.canvas.items.handle_geometry import selection_frame_rect
from open_garden_planner.ui.canvas.roof_ridge_link import build_linked_ridge, linked_ridge


def _rect(
    scene: CanvasScene,
    x: float,
    y: float,
    w: float = 100.0,
    h: float = 100.0,
    kind: ObjectType = ObjectType.GENERIC_RECTANGLE,
) -> RectangleItem:
    item = RectangleItem(x, y, w, h, object_type=kind, layer_id=scene.active_layer.id)
    scene.addItem(item)
    return item


def _centre(item: RectangleItem) -> QPointF:
    return item.mapToScene(item.rect().center())


def _grouped(canvas: CanvasView, *items) -> GroupItem:
    scene = canvas.scene()
    scene.clearSelection()
    for item in items:
        item.setSelected(True)
    canvas.group_selected()
    return next(
        item for item in scene.items()
        if isinstance(item, GroupItem) and item.parentItem() is None
    )


def _show(canvas: CanvasView) -> None:
    canvas.resize(900, 650)
    canvas.show()
    QApplication.processEvents()


def _handle(group: GroupItem):
    handle = group._rotation_handle
    assert handle is not None, "a selected group must own a rotation handle"
    return handle


def _drag(group: GroupItem, start_deg: float, end_deg: float) -> None:
    """Drag the group handle on a circle around its outline centre."""
    pivot = selection_frame_rect(group).center()
    pivot_scene = group.mapToScene(pivot)
    radius = max(selection_frame_rect(group).width(), 40.0) + 60.0
    handle = _handle(group)

    def point(deg: float) -> QPointF:
        rad = math.radians(deg)
        return pivot_scene + QPointF(radius * math.cos(rad), radius * math.sin(rad))

    assert handle.begin_drag(point(start_deg))
    handle.apply_drag(point(end_deg))
    handle.end_drag()


def test_a_real_viewport_drag_turns_the_selected_group_and_is_one_undo_step(
    canvas: CanvasView,
) -> None:
    """The pointer route, not just the handle methods (#1022 review P0).

    Qt delivers a press on a selected Qt group's child handle to the group, so a
    direct handle-method test can pass while a user drag only moves the group.
    """
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 200.0, 200.0, 100.0, 80.0)
    second = _rect(scene, 400.0, 200.0, 100.0, 80.0)
    group = _grouped(canvas, first, second)
    scene.clearSelection()
    group.setSelected(True)
    canvas.set_zoom(1.0)
    canvas.centerOn(QPointF(350.0, 240.0))
    QApplication.processEvents()
    before = (_centre(first), _centre(second))
    depth = len(canvas.command_manager._undo_stack)

    handle = _handle(group)
    pivot = group.mapToScene(selection_frame_rect(group).center())
    start = handle.scenePos()
    end = pivot + QPointF(0.0, 150.0)
    QTest.mousePress(
        canvas.viewport(), Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(start),
    )
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene((start + end) / 2.0))
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(end))
    QTest.mouseRelease(
        canvas.viewport(), Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(end),
    )
    QApplication.processEvents()

    assert group.rotation_angle > 45.0, group.rotation_angle
    assert len(canvas.command_manager._undo_stack) == depth + 1
    first_now, second_now = _centre(first), _centre(second)
    assert math.dist(
        (first_now.x(), first_now.y()), (second_now.x(), second_now.y())
    ) == pytest.approx(
        math.dist((before[0].x(), before[0].y()), (before[1].x(), before[1].y())),
        abs=2.0,
    )
    canvas.command_manager.undo()
    assert group.rotation_angle == pytest.approx(0.0, abs=0.1)
    assert _centre(first).x() == pytest.approx(before[0].x(), abs=0.01)
    assert _centre(first).y() == pytest.approx(before[0].y(), abs=0.01)
    assert _centre(second).x() == pytest.approx(before[1].x(), abs=0.01)


def test_a_selected_group_draws_exactly_one_rotation_handle(canvas: CanvasView) -> None:
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 100.0, 100.0)
    second = _rect(scene, 300.0, 100.0)
    group = _grouped(canvas, first, second)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()

    handles = [
        child for child in group.childItems()
        if type(child).__name__ == "RotationHandle"
    ]
    assert len(handles) == 1
    assert handles[0].isVisible()


def test_a_drilled_member_hides_the_group_handle_and_shows_its_own(
    canvas: CanvasView,
) -> None:
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 100.0, 100.0)
    second = _rect(scene, 300.0, 100.0)
    group = _grouped(canvas, first, second)
    scene.clearSelection()
    group.setSelected(True)
    canvas.begin_group_drill_down(first)
    QApplication.processEvents()

    assert not _handle(group).isVisible()
    assert first._rotation_handle is not None
    assert first._rotation_handle.isVisible()

    canvas._clear_group_drill_down()
    QApplication.processEvents()
    assert _handle(group).isVisible()
    assert first._rotation_handle is not None
    assert not first._rotation_handle.isVisible()


def test_dragging_the_group_handle_turns_every_member_about_the_outline_centre(
    canvas: CanvasView,
) -> None:
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0)
    second = _rect(scene, 200.0, 0.0)
    group = _grouped(canvas, first, second)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()

    before_first = _centre(first)
    before_second = _centre(second)
    _drag(group, 0.0, 90.0)

    # A positive Qt rotation is clockwise in the y-down canvas frame.
    assert _centre(first).x() == pytest.approx(150.0, abs=0.01)
    assert _centre(first).y() == pytest.approx(-50.0, abs=0.01)
    assert _centre(second).x() == pytest.approx(150.0, abs=0.01)
    assert _centre(second).y() == pytest.approx(150.0, abs=0.01)
    assert group.rotation_angle == pytest.approx(90.0, abs=0.01)
    # The arrangement is rigid: the members' separation is unchanged.
    assert math.dist(
        (_centre(first).x(), _centre(first).y()),
        (_centre(second).x(), _centre(second).y()),
    ) == pytest.approx(
        math.dist((before_first.x(), before_first.y()),
                  (before_second.x(), before_second.y())),
        abs=0.01,
    )


def test_one_undo_restores_the_group_angle_and_every_member_position(
    canvas: CanvasView,
) -> None:
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0)
    second = _rect(scene, 200.0, 0.0)
    group = _grouped(canvas, first, second)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    before_first = _centre(first)
    before_second = _centre(second)
    depth = len(canvas.command_manager._undo_stack)

    _drag(group, 0.0, 90.0)
    assert len(canvas.command_manager._undo_stack) == depth + 1

    canvas.command_manager.undo()
    assert group.rotation_angle == pytest.approx(0.0, abs=0.01)
    assert _centre(first).x() == pytest.approx(before_first.x(), abs=0.01)
    assert _centre(first).y() == pytest.approx(before_first.y(), abs=0.01)
    assert _centre(second).x() == pytest.approx(before_second.x(), abs=0.01)
    assert _centre(second).y() == pytest.approx(before_second.y(), abs=0.01)


def test_shift_snaps_the_group_angle_to_fifteen_degrees(
    canvas: CanvasView, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0)
    second = _rect(scene, 200.0, 0.0)
    group = _grouped(canvas, first, second)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    import open_garden_planner.ui.canvas.items.resize_handle as resize_handle

    class _ShiftHeld:
        @staticmethod
        def keyboardModifiers() -> Qt.KeyboardModifier:
            return Qt.KeyboardModifier.ShiftModifier

    monkeypatch.setattr(resize_handle, "QApplication", _ShiftHeld)

    _drag(group, 0.0, 22.0)
    assert group.rotation_angle == pytest.approx(15.0, abs=0.01)


def test_a_nested_group_turns_as_one_rigid_composition(canvas: CanvasView) -> None:
    _show(canvas)
    scene = canvas.scene()
    inner_first = _rect(scene, 0.0, 0.0, 60.0, 60.0)
    inner_second = _rect(scene, 100.0, 0.0, 60.0, 60.0)
    inner = _grouped(canvas, inner_first, inner_second)
    outer_member = _rect(scene, 300.0, 0.0, 60.0, 60.0)
    outer = _grouped(canvas, inner, outer_member)
    scene.clearSelection()
    outer.setSelected(True)
    QApplication.processEvents()

    inner_centre_before = inner.mapToScene(selection_frame_rect(inner).center())
    member_before = _centre(outer_member)
    separation = math.dist(
        (inner_centre_before.x(), inner_centre_before.y()),
        (member_before.x(), member_before.y()),
    )

    _drag(outer, 0.0, 90.0)

    assert outer.rotation_angle == pytest.approx(90.0, abs=0.01)
    # The inner group keeps its own angle; the outer frame carries it.
    assert inner.rotation_angle == pytest.approx(0.0, abs=0.01)
    inner_centre_after = inner.mapToScene(selection_frame_rect(inner).center())
    member_after = _centre(outer_member)
    assert math.dist(
        (inner_centre_after.x(), inner_centre_after.y()),
        (member_after.x(), member_after.y()),
    ) == pytest.approx(separation, abs=0.01)


def test_a_grouped_bed_keeps_its_plant_links_and_carries_them_after_a_turn(
    canvas: CanvasView,
) -> None:
    _show(canvas)
    scene = canvas.scene()
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    peer = _rect(scene, 400.0, 0.0)
    group = _grouped(canvas, bed, peer)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    _drag(group, 0.0, 30.0)

    assert plant.parent_bed_id == bed.item_id
    assert plant.item_id in bed.child_item_ids
    assert bed.contains(bed.mapFromScene(plant.mapToScene(plant.rect().center()))), (
        "plant follows the turned bed"
    )
    before_plant = plant.scenePos()

    from open_garden_planner.core.commands import MoveItemsCommand

    canvas.command_manager.execute(MoveItemsCommand([group], QPointF(25.0, 0.0)))
    moved = plant.scenePos() - before_plant
    assert (moved.x(), moved.y()) == pytest.approx((25.0, 0.0))
    assert plant.parent_bed_id == bed.item_id
    canvas.command_manager.execute(MoveItemsCommand([group], QPointF(0.0, 25.0)))
    assert plant.parent_bed_id == bed.item_id
    # One Ctrl+Z puts the second move, the first move and the link back together.
    canvas.command_manager.undo()
    canvas.command_manager.undo()
    assert plant.scenePos() == before_plant
    assert plant.parent_bed_id == bed.item_id


def test_a_grouped_house_ridge_follows_the_group_turn(canvas: CanvasView) -> None:
    _show(canvas)
    scene = canvas.scene()
    house = _rect(scene, 100.0, 100.0, 300.0, 200.0, kind=ObjectType.HOUSE)
    ridge = build_linked_ridge(house, scene.active_layer.id)
    assert ridge is not None
    scene.addItem(ridge)
    before = [(point.x(), point.y()) for point in ridge.points]
    peer = _rect(scene, 500.0, 0.0)
    group = _grouped(canvas, house, peer)
    group._apply_rotation(90.0)
    group.update()
    QApplication.processEvents()

    after = [(point.x(), point.y()) for point in ridge.points]
    assert after != before
    assert linked_ridge(house) is ridge
    # The ridge stays on the house's turned outline: each endpoint is within
    # the house's scene bounding box.
    bounds = house.sceneBoundingRect().adjusted(-1, -1, 1, 1)
    for x, y in after:
        assert bounds.contains(QPointF(x, y)), (x, y, bounds)


def test_a_grouped_ellipse_exports_its_turned_major_axis_to_dxf(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    """DXF reads the local ellipse angle, so a group's turn must reach the vector."""
    import ezdxf

    from open_garden_planner.services.dxf_service import DxfExportService
    from open_garden_planner.ui.canvas.items import EllipseItem

    _show(canvas)
    scene = canvas.scene()
    ellipse = EllipseItem(
        100.0, 100.0, 200.0, 100.0,
        object_type=ObjectType.GENERIC_ELLIPSE, layer_id=scene.active_layer.id,
    )
    peer = _rect(scene, 400.0, 100.0)
    scene.addItem(ellipse)
    group = _grouped(canvas, ellipse, peer)
    group._apply_rotation(90.0)
    target = tmp_path / "grouped-ellipse.dxf"
    DxfExportService.export(scene, target)

    doc = ezdxf.readfile(str(target))
    ellipses = list(doc.modelspace().query("ELLIPSE"))
    assert len(ellipses) == 1
    axis = ellipses[0].dxf.major_axis
    assert abs(axis.x) < 0.1
    assert abs(axis.y) == pytest.approx(100.0, abs=0.1)


def test_a_command_only_group_turn_carries_the_plant_like_the_agent(
    canvas: CanvasView,
) -> None:
    """The Agent API turns through a command, not a handle; the plan must match."""
    from open_garden_planner.core.commands import RotateItemCommand
    from open_garden_planner.ui.canvas.geometry_apply import apply_rotation

    _show(canvas)
    scene = canvas.scene()
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    peer = _rect(scene, 500.0, 0.0)
    group = _grouped(canvas, bed, peer)
    before = plant.mapToScene(plant.rect().center())

    group.begin_rotation_plan()
    command = RotateItemCommand(
        group, 0.0, 90.0, apply_rotation,
        followers=group.rotation_follower_snapshots(90.0),
    )
    canvas.command_manager.execute(command)
    group.finish_rotation_plan()
    after = plant.mapToScene(plant.rect().center())
    assert (after.x(), after.y()) != (before.x(), before.y())
    assert plant.parent_bed_id == bed.item_id

    canvas.command_manager.undo()
    restored = plant.mapToScene(plant.rect().center())
    assert restored.x() == pytest.approx(before.x(), abs=0.01)
    assert restored.y() == pytest.approx(before.y(), abs=0.01)
    canvas.command_manager.redo()
    again = plant.mapToScene(plant.rect().center())
    assert again.x() == pytest.approx(after.x(), abs=0.01)
    assert again.y() == pytest.approx(after.y(), abs=0.01)


def test_a_grouped_plant_that_leaves_its_bed_is_unlinked_in_the_same_step(
    canvas: CanvasView,
) -> None:
    """A Plant Grid group's own plants are reconciled; a bed's are not."""
    _show(canvas)
    scene = canvas.scene()
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    peer = _rect(scene, 1000.0, 1000.0)
    group = _grouped(canvas, plant, peer)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    _drag(group, 0.0, 180.0)

    assert plant.parent_bed_id is None
    assert plant.item_id not in bed.child_item_ids
    canvas.command_manager.undo()
    assert plant.parent_bed_id == bed.item_id
    assert plant.item_id in bed.child_item_ids


def test_a_plant_turning_with_its_own_bed_keeps_the_link(canvas: CanvasView) -> None:
    """A rigid bed+plant pair must not be re-homed by a stationary smaller bed.

    The containment rule only re-decides plants whose parent did NOT turn with
    them (#1022 review); otherwise the smallest-bed rule can steal a plant that
    moved together with its own bed.
    """
    _show(canvas)
    scene = canvas.scene()
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    peer = _rect(scene, 400.0, 100.0)
    group = _grouped(canvas, bed, peer)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()

    pivot = group.rotation_pivot_scene()
    centre = plant.mapToScene(plant.rect().center())
    # A +90° turn sends (dx, dy) to (-dy, dx) about the pivot.
    dx, dy = centre.x() - pivot.x(), centre.y() - pivot.y()
    target = QPointF(pivot.x() - dy, pivot.y() + dx)
    steal = _rect(
        scene, target.x() - 20.0, target.y() - 20.0, 40.0, 40.0,
        kind=ObjectType.RAISED_BED,
    )

    _drag(group, 0.0, 90.0)

    landed = plant.mapToScene(plant.rect().center())
    assert landed.x() == pytest.approx(target.x(), abs=0.5)
    assert landed.y() == pytest.approx(target.y(), abs=0.5)
    assert plant.parent_bed_id == bed.item_id
    assert plant.item_id in bed.child_item_ids
    assert plant.item_id not in steal.child_item_ids

    canvas.command_manager.undo()
    assert plant.parent_bed_id == bed.item_id
    assert plant.item_id in bed.child_item_ids


def test_a_grouped_bed_and_plant_keep_the_link_through_save_and_reload(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    """Both link endpoints can be group members; the fields must persist (#1022).

    The group serializer writes its children directly, so the relationship
    fields must be added to each grouped record, not only to top-level ones.
    """
    _show(canvas)
    scene = canvas.scene()
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    peer = _rect(scene, 600.0, 100.0)
    group = _grouped(canvas, bed, plant, peer)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    _drag(group, 0.0, 37.0)
    assert plant.parent_bed_id == bed.item_id

    target = tmp_path / "grouped-bed.ogp"
    ProjectManager().save(scene, target)
    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    loaded_bed = loaded_scene.find_item_by_id(bed.item_id)
    loaded_plant = loaded_scene.find_item_by_id(plant.item_id)
    assert loaded_bed is not None
    assert loaded_plant is not None
    assert loaded_plant.parent_bed_id == loaded_bed.item_id
    assert loaded_plant.item_id in loaded_bed.child_item_ids


def test_a_sub_threshold_turn_rolls_back_a_carried_plant(
    canvas: CanvasView,
) -> None:
    """A carried plant must not turn for a group angle below the 0.01° gate."""
    _show(canvas)
    scene = canvas.scene()
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    group = _grouped(canvas, bed, _rect(scene, 600.0, 100.0))
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    start_centre = plant.mapToScene(plant.rect().center())
    start_angle = plant.rotation_angle
    depth = len(canvas.command_manager._undo_stack)

    _drag(group, 0.0, 0.0000005)

    assert group.rotation_angle == pytest.approx(0.0)
    assert group._pivot_initialized is False
    assert plant.rotation_angle == pytest.approx(start_angle)
    assert plant.mapToScene(plant.rect().center()).x() == pytest.approx(
        start_centre.x(), abs=1e-6
    )
    assert plant.mapToScene(plant.rect().center()).y() == pytest.approx(
        start_centre.y(), abs=1e-6
    )
    assert len(canvas.command_manager._undo_stack) == depth


def test_a_linked_plant_on_a_locked_layer_refuses_the_turn(canvas: CanvasView) -> None:
    """A follower outside the Qt tree can still be locked (#1022 review)."""
    from open_garden_planner.models.layer import Layer

    _show(canvas)
    scene = canvas.scene()
    locked = Layer(name="Locked")
    locked.locked = True
    scene.add_layer(locked)
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=locked.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    group = _grouped(canvas, bed, _rect(scene, 600.0, 100.0))
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    depth = len(canvas.command_manager._undo_stack)

    handle = _handle(group)
    assert canvas.begin_drill_handle_drag(handle, handle.scenePos()) is False
    assert group.rotation_angle == pytest.approx(0.0)
    assert group._rotation_plan_active is False
    assert len(canvas.command_manager._undo_stack) == depth


def test_a_linked_plant_in_another_group_refuses_the_turn(canvas: CanvasView) -> None:
    _show(canvas)
    scene = canvas.scene()
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    _grouped(canvas, plant, _rect(scene, 800.0, 800.0))
    peer = _rect(scene, 500.0, 0.0)
    group = _grouped(canvas, bed, peer)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    handle = _handle(group)
    assert canvas.begin_drill_handle_drag(handle, handle.scenePos()) is False


def test_a_constrained_member_refuses_the_group_turn(canvas: CanvasView) -> None:
    """A group turn must not move a FIXED/constrained descendant (#1022)."""
    from uuid import uuid4

    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import AnchorType

    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0, 100.0, 80.0)
    second = _rect(scene, 200.0, 0.0, 100.0, 80.0)
    group = _grouped(canvas, first, second)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    scene.constraint_graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER),
        AnchorRef(uuid4(), AnchorType.CENTER),
        100.0,
    )
    handle = _handle(group)
    assert canvas.begin_drill_handle_drag(handle, handle.scenePos()) is False
    assert group.rotation_angle == pytest.approx(0.0)


def test_two_turns_and_a_return_to_zero_carry_a_plant_once(
    canvas: CanvasView,
) -> None:
    """Each turn applies a DELTA to the captured follower pose (#1022 review)."""
    _show(canvas)
    scene = canvas.scene()
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    peer = _rect(scene, 500.0, 0.0)
    group = _grouped(canvas, bed, peer)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    start_angle = plant.rotation_angle
    start_centre = plant.mapToScene(plant.rect().center())

    _drag(group, 0.0, 90.0)
    assert plant.rotation_angle == pytest.approx(start_angle + 90.0, abs=0.1)
    _drag(group, 90.0, 0.0)
    assert plant.rotation_angle == pytest.approx(start_angle, abs=0.1)
    assert plant.mapToScene(plant.rect().center()).x() == pytest.approx(
        start_centre.x(), abs=0.1
    )
    assert plant.mapToScene(plant.rect().center()).y() == pytest.approx(
        start_centre.y(), abs=0.1
    )
    assert plant.parent_bed_id == bed.item_id


def test_a_fixed_linked_plant_refuses_the_group_turn(canvas: CanvasView) -> None:
    """A linked plant is outside the Qt tree but the turn moves it (#1022)."""
    from uuid import uuid4

    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import AnchorType

    _show(canvas)
    scene = canvas.scene()
    bed = _rect(scene, 100.0, 100.0, 200.0, 200.0, kind=ObjectType.RAISED_BED)
    plant = CircleItem(
        150.0, 150.0, 15.0,
        object_type=ObjectType.PERENNIAL, layer_id=scene.active_layer.id,
    )
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    scene.constraint_graph.add_constraint(
        AnchorRef(plant.item_id, AnchorType.CENTER),
        AnchorRef(uuid4(), AnchorType.CENTER),
        100.0,
    )
    peer = _rect(scene, 500.0, 0.0)
    group = _grouped(canvas, bed, peer)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    handle = _handle(group)
    assert canvas.begin_drill_handle_drag(handle, handle.scenePos()) is False
    assert group.rotation_angle == pytest.approx(0.0)


def test_returning_a_group_to_zero_keeps_its_pivot_and_members(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    """The pivot is not derived from the angle (#1022 review P0).

    Rotate, edit a member, return to 0, then save/reload: the saved pivot must
    still place every member, and the next turn must use it.
    """
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0, 100.0, 80.0)
    second = _rect(scene, 200.0, 0.0, 100.0, 80.0)
    group = _grouped(canvas, first, second)
    group._apply_rotation(37.0)
    scene.clearSelection()
    group.setSelected(True)
    canvas.begin_group_drill_down(first)
    first.setPos(first.pos() + QPointF(30.0, 10.0))
    canvas._clear_group_drill_down()
    group._apply_rotation(0.0)
    before = sorted(
        (round(_centre(item).x(), 3), round(_centre(item).y(), 3))
        for item in (first, second)
    )

    target = tmp_path / "zero-group.ogp"
    ProjectManager().save(scene, target)
    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    loaded_group = next(
        item for item in loaded_scene.items() if isinstance(item, GroupItem)
    )
    assert loaded_group._pivot_initialized is True
    loaded = sorted(
        (
            round(item.mapToScene(selection_frame_rect(item).center()).x(), 3),
            round(item.mapToScene(selection_frame_rect(item).center()).y(), 3),
        )
        for item in loaded_scene.items()
        if item.parentItem() is loaded_group and hasattr(item, "item_id")
    )
    assert loaded == before
    # The next turn uses the saved pivot, so the frame centre cannot move it.
    before_centres = [
        item.mapToScene(selection_frame_rect(item).center())
        for item in loaded_scene.items()
        if item.parentItem() is loaded_group and hasattr(item, "item_id")
    ]
    loaded_group._apply_rotation(10.0)
    after_centres = [
        item.mapToScene(selection_frame_rect(item).center())
        for item in loaded_scene.items()
        if item.parentItem() is loaded_group and hasattr(item, "item_id")
    ]
    assert after_centres != before_centres


def test_a_saved_group_keeps_its_angle_and_composition(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0, 100.0, 80.0)
    second = _rect(scene, 200.0, 0.0, 100.0, 80.0)
    group = _grouped(canvas, first, second)
    group._apply_rotation(37.0)
    before = sorted(
        (round(_centre(item).x(), 3), round(_centre(item).y(), 3))
        for item in (first, second)
    )

    target = tmp_path / "rotated-group.ogp"
    ProjectManager().save(scene, target)

    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    loaded_group = next(
        item for item in loaded_scene.items() if isinstance(item, GroupItem)
    )
    loaded_children = sorted(
        (
            round(item.mapToScene(selection_frame_rect(item).center()).x(), 3),
            round(item.mapToScene(selection_frame_rect(item).center()).y(), 3),
        )
        for item in loaded_scene.items()
        if item.parentItem() is loaded_group and hasattr(item, "item_id")
    )
    assert loaded_group.rotation() == pytest.approx(37.0, abs=0.01)
    assert loaded_children == before


def test_a_member_edit_after_a_turn_survives_save_and_reload(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    """The pivot is part of the saved transform (#1022 review P0).

    A drilled-down move changes the frame centre. Re-pivoting on reload would
    shift every member, so the pivot is written with the angle.
    """
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0, 100.0, 80.0)
    second = _rect(scene, 200.0, 0.0, 100.0, 80.0)
    group = _grouped(canvas, first, second)
    group._apply_rotation(37.0)
    scene.clearSelection()
    group.setSelected(True)
    canvas.begin_group_drill_down(first)
    first.setPos(first.pos() + QPointF(30.0, 10.0))
    canvas._clear_group_drill_down()
    before = sorted(
        (round(_centre(item).x(), 3), round(_centre(item).y(), 3))
        for item in (first, second)
    )

    target = tmp_path / "member-edited-group.ogp"
    ProjectManager().save(scene, target)
    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    loaded_group = next(
        item for item in loaded_scene.items() if isinstance(item, GroupItem)
    )
    loaded_children = sorted(
        (
            round(item.mapToScene(selection_frame_rect(item).center()).x(), 3),
            round(item.mapToScene(selection_frame_rect(item).center()).y(), 3),
        )
        for item in loaded_scene.items()
        if item.parentItem() is loaded_group and hasattr(item, "item_id")
    )
    assert loaded_children == before


def test_ungroup_refuses_a_rotated_group_and_keeps_its_geometry(
    canvas: CanvasView,
) -> None:
    """The format stores a member's own angle, not the group matrix (#1022).

    A rotated group must be turned back before ungrouping; copying the composed
    matrix into every member would lose arcs and zero-net-angle pairs on reload.
    """
    from open_garden_planner.core.commands import UngroupCommand

    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 100.0, 100.0, 120.0, 60.0)
    second = _rect(scene, 300.0, 100.0, 120.0, 60.0)
    group = _grouped(canvas, first, second)
    group._apply_rotation(33.0)
    before = sorted(
        (round(_centre(item).x(), 3), round(_centre(item).y(), 3))
        for item in (first, second)
    )
    with pytest.raises(ValueError, match="rotated group"):
        UngroupCommand(scene, group)
    assert first.parentItem() is group and second.parentItem() is group
    assert sorted(
        (round(_centre(item).x(), 3), round(_centre(item).y(), 3))
        for item in (first, second)
    ) == before


def test_undo_removes_the_pivot_a_reverted_turn_introduced(
    canvas: CanvasView,
) -> None:
    """A no-op drag and an undone turn must not leave a saved pivot (#1022)."""
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 100.0, 100.0, 100.0, 80.0)
    second = _rect(scene, 300.0, 100.0, 100.0, 80.0)
    group = _grouped(canvas, first, second)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    assert group._pivot_initialized is False
    depth = len(canvas.command_manager._undo_stack)

    _drag(group, 0.0, 0.0)
    assert group._pivot_initialized is False
    assert group.transformOriginPoint().isNull()
    assert len(canvas.command_manager._undo_stack) == depth

    _drag(group, 0.0, 0.0000005)
    assert group.rotation_angle == pytest.approx(0.0)
    assert group.is_turned() is False
    assert group._pivot_initialized is False
    assert len(canvas.command_manager._undo_stack) == depth

    _drag(group, 0.0, 37.0)
    assert group._pivot_initialized is True
    saved_pivot = QPointF(group.transformOriginPoint())
    assert saved_pivot.isNull() is False

    canvas.command_manager.undo()
    assert group._pivot_initialized is False
    assert group.transformOriginPoint().isNull()
    canvas.command_manager.redo()
    assert group._pivot_initialized is True
    assert group.transformOriginPoint() == saved_pivot


def test_nesting_a_turned_group_survives_two_save_reload_cycles(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    """A turned group nested in another group must keep its member poses.

    Qt adjusts a nested item's pos when it enters the outer group; the saved
    pivot and angle must reproduce that pose, twice in a row.
    """
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0, 100.0, 80.0)
    second = _rect(scene, 200.0, 0.0, 100.0, 80.0)
    inner = _grouped(canvas, first, second)
    inner._apply_rotation(37.0)
    peer = _rect(scene, 600.0, 0.0, 80.0, 80.0)
    scene.clearSelection()
    inner.setSelected(True)
    peer.setSelected(True)
    canvas.group_selected()
    QApplication.processEvents()

    def centres(target_scene: CanvasScene) -> list[tuple[float, float]]:
        return sorted(
            (
                round(item.mapToScene(item.rect().center()).x(), 3),
                round(item.mapToScene(item.rect().center()).y(), 3),
            )
            for item in target_scene.items()
            if isinstance(item, RectangleItem)
        )

    before = centres(scene)

    outer = next(
        item for item in scene.items()
        if isinstance(item, GroupItem) and item.parentItem() is None
    )
    saved_outer = ProjectManager._serialize_item(outer)
    assert saved_outer is not None
    saved_inner = next(
        child for child in saved_outer["children"] if child.get("type") == "group"
    )
    xs: list[float] = []
    ys: list[float] = []
    for member in inner.childItems():
        if isinstance(member, RectangleItem):
            polygon = member.mapToScene(member.rect())
            xs.extend(point.x() for point in polygon)
            ys.extend(point.y() for point in polygon)
    live_box = (
        min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys),
    )
    for got, expected in zip(queries.object_bbox(saved_inner), live_box, strict=True):
        assert got == pytest.approx(expected, abs=0.01)

    target = tmp_path / "nested-turned.ogp"
    ProjectManager().save(scene, target)
    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    assert centres(loaded_scene) == before

    second_target = tmp_path / "nested-turned-2.ogp"
    ProjectManager().save(loaded_scene, second_target)
    loaded_again = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_again, second_target)
    assert centres(loaded_again) == before


def test_ungrouping_a_loaded_nested_group_survives_save_and_reload(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    """A loaded nesting translation must bake into members losslessly."""
    from open_garden_planner.core.commands import UngroupCommand

    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0, 100.0, 80.0)
    second = _rect(scene, 200.0, 0.0, 100.0, 80.0)
    inner = _grouped(canvas, first, second)
    inner._apply_rotation(37.0)
    peer = _rect(scene, 600.0, 0.0, 80.0, 80.0)
    scene.clearSelection()
    inner.setSelected(True)
    peer.setSelected(True)
    canvas.group_selected()
    QApplication.processEvents()

    target = tmp_path / "nested-ungroup.ogp"
    ProjectManager().save(scene, target)
    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    def centres(target_scene: CanvasScene) -> list[tuple[float, float]]:
        return sorted(
            (
                round(item.mapToScene(item.rect().center()).x(), 3),
                round(item.mapToScene(item.rect().center()).y(), 3),
            )
            for item in target_scene.items()
            if isinstance(item, RectangleItem)
        )

    outer = next(
        item for item in loaded_scene.items()
        if isinstance(item, GroupItem) and item.parentItem() is None
    )
    nested_inner = next(
        item for item in outer.childItems() if isinstance(item, GroupItem)
    )
    assert nested_inner.transform().isIdentity() is False
    before_outer_ungroup = centres(loaded_scene)
    UngroupCommand(loaded_scene, outer).execute()
    assert centres(loaded_scene) == before_outer_ungroup

    imported_inner = next(
        item for item in loaded_scene.items()
        if isinstance(item, GroupItem) and item.parentItem() is None
    )
    imported_inner._apply_rotation(0.0)
    before_inner_ungroup = centres(loaded_scene)
    UngroupCommand(loaded_scene, imported_inner).execute()
    assert centres(loaded_scene) == before_inner_ungroup

    before = centres(loaded_scene)
    reopened_target = tmp_path / "nested-ungroup-2.ogp"
    ProjectManager().save(loaded_scene, reopened_target)
    reopened = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(reopened, reopened_target)
    assert centres(reopened) == before


def test_a_pre_rotated_text_note_survives_group_and_ungroup(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    """Qt's group compensation must be added to a TextItem's saved anchor."""
    from open_garden_planner.core.commands import UngroupCommand

    _show(canvas)
    scene = canvas.scene()
    note = TextItem(100.0, 100.0, content="Hello garden note")
    scene.addItem(note)
    note._apply_rotation(45.0)
    peer = _rect(scene, 500.0, 100.0)
    group = _grouped(canvas, note, peer)
    QApplication.processEvents()

    def live_box(target_scene: CanvasScene) -> tuple[float, float, float, float]:
        note_item = next(
            item for item in target_scene.items() if isinstance(item, TextItem)
        )
        box = note_item.mapToScene(note_item.boundingRect()).boundingRect()
        peer_item = next(
            item for item in target_scene.items()
            if isinstance(item, RectangleItem)
            and getattr(item, "object_type", None) is ObjectType.GENERIC_RECTANGLE
        )
        peer_box = peer_item.mapToScene(peer_item.rect()).boundingRect()
        union = box.united(peer_box)
        return (union.left(), union.top(), union.right(), union.bottom())

    saved = ProjectManager._serialize_item(group)
    assert saved is not None
    x, y, w, h = queries.object_bbox(saved)
    left, top, right, bottom = live_box(scene)
    assert x == pytest.approx(left, abs=3.0)
    assert y == pytest.approx(top, abs=3.0)
    assert x + w == pytest.approx(right, abs=3.0)
    assert y + h == pytest.approx(bottom, abs=3.0)

    target = tmp_path / "pre-rotated-text.ogp"
    ProjectManager().save(scene, target)
    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    loaded_box = live_box(loaded_scene)
    for got, expected in zip(loaded_box, (left, top, right, bottom), strict=True):
        assert got == pytest.approx(expected, abs=0.01)

    loaded_group = next(
        item for item in loaded_scene.items()
        if isinstance(item, GroupItem)
    )
    UngroupCommand(loaded_scene, loaded_group).execute()
    ungrouped_box = live_box(loaded_scene)
    for got, expected in zip(ungrouped_box, (left, top, right, bottom), strict=True):
        assert got == pytest.approx(expected, abs=0.01)

    second = tmp_path / "pre-rotated-text-ungrouped.ogp"
    ProjectManager().save(loaded_scene, second)
    reopened = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(reopened, second)
    reopened_box = live_box(reopened)
    for got, expected in zip(reopened_box, (left, top, right, bottom), strict=True):
        assert got == pytest.approx(expected, abs=0.01)


def test_a_grouped_callout_box_matches_its_live_geometry(canvas: CanvasView) -> None:
    """Own turn and group turn compose about the saved callout bounds."""
    _show(canvas)
    scene = canvas.scene()
    callout = CalloutItem(
        target=QPointF(100.0, 100.0),
        box_offset=QPointF(100.0, 50.0),
        content="A",
    )
    scene.addItem(callout)
    callout._apply_rotation(30.0)
    peer = _rect(scene, 500.0, 100.0)
    group = _grouped(canvas, callout, peer)
    group._apply_rotation(45.0)
    saved = ProjectManager._serialize_item(group)
    assert saved is not None
    x, y, w, h = queries.object_bbox(saved)
    callout_box = callout.mapToScene(callout.boundingRect()).boundingRect()
    peer_box = peer.mapToScene(peer.rect()).boundingRect()
    live = callout_box.united(peer_box)
    assert x == pytest.approx(live.left(), abs=3.0)
    assert y == pytest.approx(live.top(), abs=3.0)
    assert x + w == pytest.approx(live.right(), abs=3.0)
    assert y + h == pytest.approx(live.bottom(), abs=3.0)


def test_a_grouped_text_note_box_matches_its_reflected_geometry(
    canvas: CanvasView,
) -> None:
    """The note's local Y reflection must be composed before the group box."""
    _show(canvas)
    scene = canvas.scene()
    note = TextItem(100.0, 100.0, content="Hello garden note")
    scene.addItem(note)
    peer = _rect(scene, 500.0, 100.0)
    group = _grouped(canvas, note, peer)
    group._apply_rotation(45.0)
    saved = ProjectManager._serialize_item(group)
    assert saved is not None
    x, y, w, h = queries.object_bbox(saved)
    note_box = note.mapToScene(note.boundingRect()).boundingRect()
    peer_box = peer.mapToScene(peer.rect()).boundingRect()
    live = note_box.united(peer_box)
    assert x == pytest.approx(live.left(), abs=3.0)
    assert y == pytest.approx(live.top(), abs=3.0)
    assert x + w == pytest.approx(live.right(), abs=3.0)
    assert y + h == pytest.approx(live.bottom(), abs=3.0)


def test_a_small_turned_group_can_return_to_zero(canvas: CanvasView) -> None:
    """A 0.005° group is turned; releasing it at 0° must commit that change."""
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0, 100.0, 80.0)
    second = _rect(scene, 200.0, 0.0, 100.0, 80.0)
    group = _grouped(canvas, first, second)
    group._apply_rotation(0.005)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()
    depth = len(canvas.command_manager._undo_stack)

    _drag(group, 0.0, -0.005)

    assert group.rotation_angle == pytest.approx(0.0)
    assert group.is_turned() is False
    assert len(canvas.command_manager._undo_stack) == depth + 1


def test_a_turn_back_to_a_rounded_zero_is_saved_as_zero(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    """A gesture target inside the zero tolerance commits as exactly 0°."""
    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 0.0, 0.0, 100.0, 80.0)
    second = _rect(scene, 200.0, 0.0, 100.0, 80.0)
    group = _grouped(canvas, first, second)
    group._apply_rotation(45.0000005)
    scene.clearSelection()
    group.setSelected(True)
    QApplication.processEvents()

    _drag(group, 0.0, -45.0)

    assert group.rotation_angle == pytest.approx(0.0)
    assert group.is_turned() is False
    target = tmp_path / "rounded-zero.ogp"
    ProjectManager().save(scene, target)
    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    loaded_group = next(
        item for item in loaded_scene.items() if isinstance(item, GroupItem)
    )
    assert loaded_group.rotation_angle == pytest.approx(0.0)


def test_an_unrotated_group_ungroups_and_survives_reload(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    from open_garden_planner.core.commands import UngroupCommand

    _show(canvas)
    scene = canvas.scene()
    first = _rect(scene, 100.0, 100.0, 120.0, 60.0)
    second = _rect(scene, 300.0, 100.0, 120.0, 60.0)
    group = _grouped(canvas, first, second)
    before = sorted(
        (round(_centre(item).x(), 3), round(_centre(item).y(), 3))
        for item in (first, second)
    )
    canvas.command_manager.execute(UngroupCommand(scene, group))
    assert first.parentItem() is None and second.parentItem() is None
    canvas.command_manager.undo()
    assert first.parentItem() is group
    canvas.command_manager.redo()
    assert first.parentItem() is None

    target = tmp_path / "ungrouped.ogp"
    ProjectManager().save(scene, target)
    loaded_scene = CanvasScene(width_cm=5000, height_cm=3000)
    ProjectManager().load(loaded_scene, target)
    loaded = sorted(
        (
            round(item.mapToScene(item.rect().center()).x(), 3),
            round(item.mapToScene(item.rect().center()).y(), 3),
        )
        for item in loaded_scene.items()
        if isinstance(item, RectangleItem)
    )
    assert loaded == before
