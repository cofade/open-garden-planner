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

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, GroupItem, RectangleItem
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
    before_plant = plant.scenePos()

    from open_garden_planner.core.commands import MoveItemsCommand

    canvas.command_manager.execute(MoveItemsCommand([group], QPointF(25.0, 0.0)))
    moved = plant.scenePos() - before_plant
    assert (moved.x(), moved.y()) == pytest.approx((25.0, 0.0))
    # One Ctrl+Z puts the group and the linked plant back together.
    canvas.command_manager.undo()
    assert plant.scenePos() == before_plant


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


def test_ungroup_bakes_the_turn_into_the_members_and_survives_reload(
    canvas: CanvasView, tmp_path: Path,
) -> None:
    """`removeFromGroup` leaves the group's rotation in the member transform.

    The file stores the member's own angle, so ungroup must move that rotation
    into the member's own transform or a nonsquare rectangle loses it on reload
    (#1022 review P0).
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
    canvas.command_manager.execute(UngroupCommand(scene, group))
    assert first.parentItem() is None and second.parentItem() is None
    assert first.rotation_angle == pytest.approx(33.0, abs=0.01)
    assert second.rotation_angle == pytest.approx(33.0, abs=0.01)

    # Undo must put the local transforms back, not compose the group turn twice.
    canvas.command_manager.undo()
    assert first.parentItem() is group
    assert first.rotation_angle == pytest.approx(0.0, abs=0.01)
    canvas.command_manager.redo()
    assert first.parentItem() is None

    target = tmp_path / "ungrouped-turn.ogp"
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
