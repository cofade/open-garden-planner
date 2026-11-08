"""End-to-end group drill-down selection (#771).

The first click selects the group; a second click on a member gives that member
edit focus without ungrouping. The group stays the Qt selection, so a view-level
``effective_selection`` is what the panels consume. A body drag and the arrow
keys move the focused member in its group's frame; changing its layer, cutting
or deleting it is refused.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QMenu, QMessageBox

from open_garden_planner.core.commands import GroupCommand
from open_garden_planner.ui.canvas.items import GroupItem, RectangleItem
from open_garden_planner.ui.canvas.items.group_item import is_drillable_group
from open_garden_planner.ui.canvas.items.smart_symbol_item import SmartSymbolItem
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel


def _show(canvas) -> None:
    canvas.resize(900, 650)
    canvas.show()
    QTest.qWaitForWindowExposed(canvas)
    canvas.set_zoom(2)
    canvas.centerOn(QPointF(150, 50))
    QTest.qWait(20)


def _group(canvas) -> tuple[GroupItem, RectangleItem, RectangleItem]:
    scene = canvas.scene()
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(200, 0, 100, 100)
    for item in (first, second):
        item.layer_id = scene.active_layer.id
        scene.addItem(item)
        item.setSelected(True)
    canvas.group_selected()
    group = next(item for item in scene.items() if isinstance(item, GroupItem))
    return group, first, second


def _click_scene(canvas, point: QPointF) -> None:
    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(point)
    )
    QTest.qWait(10)


def _drill(canvas, child: RectangleItem) -> None:
    center = child.sceneBoundingRect().center()
    _click_scene(canvas, center)
    _click_scene(canvas, center)


def test_second_click_focuses_the_member_then_outside_restores_the_group(canvas) -> None:
    _show(canvas)
    group, first, _second = _group(canvas)
    canvas.scene().clearSelection()

    _click_scene(canvas, first.sceneBoundingRect().center())
    assert canvas.scene().selectedItems() == [group]
    assert canvas.drill_down_item is None

    _click_scene(canvas, first.sceneBoundingRect().center())
    assert canvas.drill_down_item is first
    assert canvas.effective_selection() == [first]
    assert group._drill_down_child is first
    assert not bool(group.flags() & group.GraphicsItemFlag.ItemIsMovable)

    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(700, 500))
    QTest.qWait(20)
    assert canvas.drill_down_item is None
    assert canvas.effective_selection() == []
    assert group._drill_down_child is None
    assert bool(group.flags() & group.GraphicsItemFlag.ItemIsMovable)


def test_a_body_drag_moves_the_member_not_the_group_and_undoes_in_one_step(canvas) -> None:
    _show(canvas)
    group, first, _second = _group(canvas)
    canvas.scene().clearSelection()
    _drill(canvas, first)
    assert canvas.drill_down_item is first

    group_pos = QPointF(group.pos())
    start = QPointF(first.pos())
    undo_before = canvas.command_manager.undo_depth
    point = canvas.mapFromScene(first.sceneBoundingRect().center())
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(canvas.viewport(), point + QPoint(30, 20))
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point + QPoint(30, 20))
    QTest.qWait(20)

    assert group.pos() == group_pos
    assert first.pos() != start
    assert canvas.command_manager.undo_depth == undo_before + 1
    canvas.command_manager.undo()
    assert first.pos() == start
    assert group.pos() == group_pos


def test_a_focused_member_handle_resizes_only_that_member(canvas) -> None:
    _show(canvas)
    group, first, _second = _group(canvas)
    canvas.scene().clearSelection()
    _drill(canvas, first)
    assert canvas.drill_down_item is first

    handle = first._resize_handles[0]
    handle.update_position()
    group_pos = QPointF(group.pos())
    before = first.rect()
    undo_before = canvas.command_manager.undo_depth
    point = canvas.mapFromScene(handle.scenePos())
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(canvas.viewport(), point + QPoint(-30, -30))
    QTest.mouseRelease(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=point + QPoint(-30, -30)
    )
    QTest.qWait(20)

    assert first.rect() != before
    assert group.pos() == group_pos
    assert canvas.command_manager.undo_depth == undo_before + 1
    canvas.command_manager.undo()
    assert first.rect() == before


def test_a_focused_member_rotation_handle_rotates_only_that_member(canvas) -> None:
    _show(canvas)
    group, first, _second = _group(canvas)
    canvas.scene().clearSelection()
    _drill(canvas, first)
    handle = first._rotation_handle
    handle.update_position()
    group_pos = QPointF(group.pos())
    before = first.rotation()
    undo_before = canvas.command_manager.undo_depth
    point = canvas.mapFromScene(handle.scenePos())

    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(canvas.viewport(), point + QPoint(40, 20))
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point + QPoint(40, 20))
    QTest.qWait(20)

    assert first.rotation() != before
    assert group.pos() == group_pos
    assert canvas.command_manager.undo_depth == undo_before + 1
    canvas.command_manager.undo()
    assert first.rotation() == pytest.approx(before)


def test_a_transformed_group_rotation_uses_one_frame(canvas) -> None:
    import math

    _show(canvas)
    group, first, _second = _group(canvas)
    group.setPos(50, 60)
    group.setRotation(30)
    first.setPos(200, 100)
    canvas.scene().clearSelection()
    group.setSelected(True)
    canvas.begin_group_drill_down(first)
    handle = first._rotation_handle
    handle.update_position()
    start = handle.scenePos()
    target = start + QPointF(40, 20)
    centre = first.mapToScene(first.rect().center())
    expected = math.degrees(
        math.atan2(target.y() - centre.y(), target.x() - centre.x())
        - math.atan2(start.y() - centre.y(), start.x() - centre.x())
    )
    before = first.rotation()

    assert canvas.begin_drill_handle_drag(handle, start) is True
    canvas._move_drill_handle(target)
    canvas._finish_drill_handle()

    assert first.rotation() == pytest.approx(before + expected, abs=0.6)


def test_a_drilled_handle_resize_is_clamped_to_the_canvas(canvas) -> None:
    from open_garden_planner.ui.canvas.items.resize_handle import HandlePosition

    _show(canvas)
    scene = canvas.scene()
    first = RectangleItem(0, 0, 150, 100)
    second = RectangleItem(300, 0, 100, 100)
    for item in (first, second):
        item.layer_id = scene.active_layer.id
        scene.addItem(item)
        item.setSelected(True)
    canvas.group_selected()
    group = next(item for item in scene.items() if isinstance(item, GroupItem))
    group.setPos(4800, 0)
    scene.clearSelection()
    group.setSelected(True)
    canvas.begin_group_drill_down(first)
    handle = next(
        item for item in first._resize_handles
        if item.handle_position is HandlePosition.MIDDLE_RIGHT
    )
    handle.update_position()
    assert canvas.begin_drill_handle_drag(handle, handle.scenePos()) is True
    canvas._move_drill_handle(QPointF(5200, handle.scenePos().y()))
    canvas._finish_drill_handle()

    assert first.sceneBoundingRect().right() <= 5000.0 + 1e-6


def test_a_rotated_group_handle_keeps_the_dragged_corner_under_the_pointer(canvas) -> None:
    _show(canvas)
    group, first, _second = _group(canvas)
    group.setRotation(30)
    canvas.scene().clearSelection()
    group.setSelected(True)
    canvas.begin_group_drill_down(first)
    handle = first._resize_handles[0]
    handle.update_position()
    start_scene = first.mapToScene(
        QPointF(first.rect().left(), first.rect().top())
    )
    delta = QPointF(30, 20)

    assert canvas.begin_drill_handle_drag(handle, start_scene) is True
    canvas._move_drill_handle(start_scene + delta)
    canvas._finish_drill_handle()

    end_scene = first.mapToScene(
        QPointF(first.rect().left(), first.rect().top())
    )
    assert end_scene.x() == pytest.approx(start_scene.x() + delta.x(), abs=0.5)
    assert end_scene.y() == pytest.approx(start_scene.y() + delta.y(), abs=0.5)


def test_escape_mid_drag_commits_one_undo_step(canvas) -> None:
    _show(canvas)
    group, first, _second = _group(canvas)
    canvas.scene().clearSelection()
    _drill(canvas, first)
    group_pos = QPointF(group.pos())
    start = QPointF(first.pos())
    undo_before = canvas.command_manager.undo_depth
    point = canvas.mapFromScene(first.sceneBoundingRect().center())

    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(canvas.viewport(), point + QPoint(25, 15))
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point + QPoint(25, 15))
    QTest.qWait(20)

    assert canvas.drill_down_item is None
    assert group.pos() == group_pos
    assert first.pos() != start
    assert canvas.command_manager.undo_depth == undo_before + 1
    canvas.command_manager.undo()
    assert first.pos() == start


def test_a_nested_focus_drag_moves_only_the_leaf(canvas) -> None:
    _show(canvas)
    scene = canvas.scene()
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(200, 0, 100, 100)
    shell = RectangleItem(400, 0, 100, 100)
    for item in (first, second, shell):
        item.layer_id = scene.active_layer.id
        scene.addItem(item)
    first.setSelected(True)
    second.setSelected(True)
    canvas.command_manager.execute(GroupCommand(scene, [first, second]))
    inner = next(item for item in scene.items() if isinstance(item, GroupItem))
    inner.setSelected(True)
    shell.setSelected(True)
    canvas.group_selected()
    outer = next(
        item
        for item in scene.items()
        if isinstance(item, GroupItem) and item is not inner
    )
    scene.clearSelection()
    outer.setSelected(True)
    canvas.begin_group_drill_down(inner)
    canvas.begin_group_drill_down(first)

    outer_pos = QPointF(outer.pos())
    inner_pos = QPointF(inner.pos())
    start = QPointF(first.pos())
    point = canvas.mapFromScene(first.sceneBoundingRect().center())
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(canvas.viewport(), point + QPoint(20, 10))
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point + QPoint(20, 10))
    QTest.qWait(20)

    assert first.pos() != start
    assert outer.pos() == outer_pos
    assert inner.pos() == inner_pos


def test_a_fixed_group_refuses_member_movement(canvas) -> None:
    from open_garden_planner.core.constraints import AnchorRef, ConstraintType
    from open_garden_planner.core.measure_snapper import AnchorType

    _show(canvas)
    group, first, _second = _group(canvas)
    anchor = AnchorRef(group.item_id, AnchorType.CENTER)
    canvas.scene().constraint_graph.add_constraint(
        anchor, anchor, 0, constraint_type=ConstraintType.FIXED,
        target_x=0, target_y=0,
    )
    canvas.scene().clearSelection()
    group.setSelected(True)
    canvas.begin_group_drill_down(first)
    start = QPointF(first.pos())
    messages: list[str] = []
    canvas.status_message.connect(messages.append)

    assert canvas.begin_drill_down_drag(first, first.sceneBoundingRect().center()) is False
    handle = first._resize_handles[0]
    handle.update_position()
    assert canvas.begin_drill_handle_drag(handle, handle.scenePos()) is False
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    QTest.qWait(20)

    assert first.pos() == start
    assert messages and "constrained member or group" in messages[0]


def test_the_properties_panel_clamps_a_position_move_to_the_canvas(qtbot, canvas) -> None:
    _show(canvas)
    item = RectangleItem(4900, 0, 100, 100)
    item.layer_id = canvas.scene().active_layer.id
    canvas.scene().addItem(item)
    panel = PropertiesPanel(canvas.command_manager)
    qtbot.addWidget(panel)
    panel.set_selected_items([item])
    x_spin = next(
        spin for spin in panel.findChildren(QDoubleSpinBox) if spin.prefix() == "X: "
    )
    x_spin.setValue(4980.0)
    QTest.qWait(20)

    assert item.sceneBoundingRect().right() <= 5000.0 + 1e-6


def test_arrow_keys_move_the_focused_member(canvas) -> None:
    _show(canvas)
    group, first, _second = _group(canvas)
    canvas.scene().clearSelection()
    _drill(canvas, first)
    assert canvas.drill_down_item is first

    group_pos = QPointF(group.pos())
    start = QPointF(first.pos())
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    QTest.qWait(20)

    assert first.pos() != start
    assert group.pos() == group_pos
    canvas.command_manager.undo()
    assert first.pos() == start


def test_a_rotated_group_keeps_the_scene_delta_when_moving_the_member(canvas) -> None:
    scene = canvas.scene()
    group, first, _second = _group(canvas)
    group.setRotation(30)
    scene.clearSelection()
    group.setSelected(True)
    canvas.begin_group_drill_down(first)

    start_scene = first.mapToScene(first.boundingRect().center())
    canvas.begin_drill_down_drag(first, start_scene)
    canvas._move_drill_down_item(start_scene + QPointF(20, 10))
    canvas._finish_drill_down_drag()

    end_scene = first.mapToScene(first.boundingRect().center())
    assert end_scene.x() == pytest.approx(start_scene.x() + 20.0, abs=0.01)
    assert end_scene.y() == pytest.approx(start_scene.y() + 10.0, abs=0.01)


def test_the_properties_panel_shows_the_member_and_disables_its_layer(qtbot, canvas) -> None:
    _show(canvas)
    _group_obj, first, _second = _group(canvas)
    canvas.scene().clearSelection()
    _drill(canvas, first)
    panel = PropertiesPanel(canvas.command_manager)
    qtbot.addWidget(panel)
    panel.set_selected_items(canvas.effective_selection())

    layer_combos = [
        combo
        for combo in panel.findChildren(QComboBox)
        if combo.count() == len(canvas.scene().layers)
        and combo.currentData() == first.layer_id
    ]
    assert layer_combos
    assert all(not combo.isEnabled() for combo in layer_combos)


def test_the_properties_panel_can_resize_the_member(qtbot, canvas) -> None:
    _show(canvas)
    group, first, _second = _group(canvas)
    canvas.scene().clearSelection()
    _drill(canvas, first)
    panel = PropertiesPanel(canvas.command_manager)
    qtbot.addWidget(panel)
    panel.set_selected_items(canvas.effective_selection())
    group_pos = QPointF(group.pos())
    undo_before = canvas.command_manager.undo_depth

    width_spins = [
        spin for spin in panel.findChildren(QDoubleSpinBox) if spin.prefix() == "W: "
    ]
    assert len(width_spins) == 1
    width_spins[0].setValue(150.0)

    assert first.rect().width() == pytest.approx(150.0)
    assert group.pos() == group_pos
    assert canvas.command_manager.undo_depth == undo_before + 1


def test_cut_and_delete_are_refused_while_a_member_is_focused(canvas) -> None:
    _show(canvas)
    group, first, _second = _group(canvas)
    canvas.scene().clearSelection()
    _drill(canvas, first)

    messages: list[str] = []
    canvas.status_message.connect(messages.append)
    canvas.cut_selected()
    canvas._delete_selected_items()

    assert first.scene() is canvas.scene()
    assert group.scene() is canvas.scene()
    assert len(messages) == 2
    assert all("Press Esc" in message for message in messages)


def test_nested_groups_drill_one_level_at_a_time(canvas) -> None:
    scene = canvas.scene()
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(200, 0, 100, 100)
    shell = RectangleItem(400, 0, 100, 100)
    for item in (first, second, shell):
        item.layer_id = scene.active_layer.id
        scene.addItem(item)
    first.setSelected(True)
    second.setSelected(True)
    canvas.command_manager.execute(GroupCommand(scene, [first, second]))
    inner = next(item for item in scene.items() if isinstance(item, GroupItem))
    inner.setSelected(True)
    shell.setSelected(True)
    canvas.group_selected()
    outer = next(
        item
        for item in scene.items()
        if isinstance(item, GroupItem) and item is not inner
    )
    scene.clearSelection()
    outer.setSelected(True)

    assert canvas.drill_target_at(QPointF(50, 50)) is inner
    canvas.begin_group_drill_down(inner)
    assert canvas.drill_target_at(QPointF(50, 50)) is first


def test_a_smart_symbol_is_not_drillable(qtbot) -> None:
    symbol = SmartSymbolItem("raised_bed_rows", 1, {"rows": 4})
    assert is_drillable_group(symbol) is False


def test_the_layer_context_menu_is_absent_for_a_member(canvas) -> None:
    _show(canvas)
    _group_obj, first, _second = _group(canvas)
    menu = QMenu()
    assert first._build_move_to_layer_menu(menu) is None


def test_the_running_app_panel_follows_drill_down_focus(qtbot, monkeypatch) -> None:
    """The view's signal, not Qt's selectionChanged, refreshes the panels (#771)."""
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard,
    )
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    scene = window.canvas_scene
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(200, 0, 100, 100)
    for item in (first, second):
        item.layer_id = scene.active_layer.id
        scene.addItem(item)
        item.setSelected(True)
    window.canvas_view.group_selected()
    group = next(item for item in scene.items() if isinstance(item, GroupItem))
    scene.clearSelection()
    group.setSelected(True)

    window.canvas_view.begin_group_drill_down(first)
    assert window.properties_panel._current_items == [first]

    window.canvas_view.end_group_drill_down()
    assert window.properties_panel._current_items == [group]
