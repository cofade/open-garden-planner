"""Line presets and type changes restore exact appearances (#524–#526)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QComboBox, QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.item_look import adopt_pen, style_gaps
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle, get_style
from open_garden_planner.ui.canvas.items import PolylineItem
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel


@pytest.fixture()
def line_panel(canvas: Any, qtbot: Any) -> tuple[PolylineItem, PropertiesPanel]:
    item = PolylineItem([QPointF(100, 100), QPointF(400, 100), QPointF(400, 300)],
                        object_type=ObjectType.PATH)
    canvas.scene().addItem(item)
    panel = PropertiesPanel(canvas.command_manager)
    qtbot.addWidget(panel)
    panel.set_selected_items([item])
    return item, panel


def custom_pen(item: PolylineItem, width: float = 12.0) -> QPen:
    pen = item.pen()
    pen.setColor(QColor("#102030"))
    pen.setWidthF(width)
    pen.setStyle(Qt.PenStyle.DashLine)
    adopt_pen(item, pen)
    return QPen(pen)


def choose(panel: PropertiesPanel, value: ObjectType | PathFenceStyle) -> None:
    combos = [combo for combo in panel.findChildren(QComboBox) if combo.findData(value) >= 0]
    assert len(combos) == 1
    combos[0].setCurrentIndex(combos[0].findData(value))


def context_type(item: PolylineItem, target: ObjectType, monkeypatch: Any) -> None:
    def pick(menu: QMenu, *_: Any) -> Any:
        matches = [action for parent in menu.actions() if parent.menu() is not None
                   for action in parent.menu().actions() if action.data() is target]
        assert len(matches) == 1
        return matches[0]

    monkeypatch.setattr(QMenu, "exec", pick)
    event = MagicMock(spec=QGraphicsSceneContextMenuEvent)
    event.screenPos.return_value = QPoint(0, 0)
    item.contextMenuEvent(event)


@pytest.mark.parametrize("before", [PathFenceStyle.NONE, PathFenceStyle.GRAVEL_PATH])
@pytest.mark.parametrize("after", [PathFenceStyle.NONE, PathFenceStyle.GRAVEL_PATH,
                                   PathFenceStyle.WOODEN_BOARDWALK])
def test_preset_history_restores_the_complete_pen(
        canvas: Any, line_panel: Any, qtbot: Any, before: PathFenceStyle, after: PathFenceStyle,
) -> None:
    item, panel = line_panel
    item.path_fence_style = before
    item.apply_style_preset()
    original = custom_pen(item, 5.0)
    original.setColor(QColor("#a0522d"))
    adopt_pen(item, original)
    panel.set_selected_items([item])
    count = len(canvas.command_manager._undo_stack)
    choose(panel, after)
    changed = QPen(item.pen())
    assert item.path_fence_style is after
    if before is after:
        assert changed == original
        assert len(canvas.command_manager._undo_stack) == count
        return
    assert len(canvas.command_manager._undo_stack) == count + 1
    for _ in range(2):
        canvas.command_manager.undo()
        assert item.path_fence_style is before and item.pen() == original
        assert style_gaps(item) == []
        canvas.command_manager.redo()
        assert item.path_fence_style is after and item.pen() == changed
        assert style_gaps(item) == []
    qtbot.wait(1)


@pytest.mark.parametrize("surface", ["panel", "context"])
@pytest.mark.parametrize("preset", [PathFenceStyle.NONE, PathFenceStyle.GRAVEL_PATH])
@pytest.mark.parametrize("target", [ObjectType.FENCE, ObjectType.WALL])
def test_type_changes_clear_presets_and_restore_exactly(
        canvas: Any, line_panel: Any, qtbot: Any, monkeypatch: Any, surface: str,
        preset: PathFenceStyle, target: ObjectType,
) -> None:
    item, panel = line_panel
    item.path_fence_style = preset
    item.apply_style_preset()
    original = custom_pen(item)
    panel.set_selected_items([item])
    count = len(canvas.command_manager._undo_stack)
    if surface == "panel":
        choose(panel, target)
    else:
        item.setSelected(True)
        context_type(item, target, monkeypatch)
    style = get_style(target)
    changed = QPen(item.pen())
    assert item.object_type is target
    assert item.path_fence_style is PathFenceStyle.NONE
    assert changed.color() == style.stroke_color and changed.widthF() == style.stroke_width
    assert changed.capStyle() is Qt.PenCapStyle.RoundCap
    assert changed.joinStyle() is Qt.PenJoinStyle.RoundJoin
    assert style_gaps(item) == []
    assert len(canvas.command_manager._undo_stack) == count + 1
    for _ in range(2):
        canvas.command_manager.undo()
        assert item.object_type is ObjectType.PATH and item.path_fence_style is preset
        assert item.pen() == original and style_gaps(item) == []
        canvas.command_manager.redo()
        assert item.object_type is target and item.path_fence_style is PathFenceStyle.NONE
        assert item.pen() == changed and style_gaps(item) == []
    qtbot.wait(1)


def test_panel_type_change_keeps_round_caps_and_joins(line_panel: Any, qtbot: Any) -> None:
    item, panel = line_panel
    choose(panel, ObjectType.WALL)
    assert item.pen().capStyle() is Qt.PenCapStyle.RoundCap
    assert item.pen().joinStyle() is Qt.PenJoinStyle.RoundJoin
    qtbot.wait(1)


def test_same_type_does_not_reset_a_preset_or_add_history(canvas: Any, line_panel: Any) -> None:
    item, panel = line_panel
    item.path_fence_style = PathFenceStyle.GRAVEL_PATH
    original = custom_pen(item)
    count = len(canvas.command_manager._undo_stack)
    item._dispatch_change_type(ObjectType.PATH)
    panel._on_property_changed(item, "object_type", ObjectType.PATH)
    assert item.path_fence_style is PathFenceStyle.GRAVEL_PATH and item.pen() == original
    assert len(canvas.command_manager._undo_stack) == count


@pytest.mark.parametrize("edit", [PathFenceStyle.GRAVEL_PATH, ObjectType.WALL])
def test_history_outlives_panel(canvas: Any, qtbot: Any, edit: Any) -> None:
    item = PolylineItem([QPointF(100, 100), QPointF(400, 100)], object_type=ObjectType.PATH)
    canvas.scene().addItem(item)
    # Deliberately unmanaged by qtbot: this test destroys the receiver itself.
    panel = PropertiesPanel(canvas.command_manager)
    panel.set_selected_items([item])
    original = custom_pen(item)
    choose(panel, edit)
    sip.delete(panel)
    qtbot.wait(1)
    canvas.command_manager.undo()
    assert item.pen() == original


def test_preset_and_type_history_survive_project_roundtrips(
        canvas: Any, line_panel: Any, qtbot: Any,
) -> None:
    item, panel = line_panel
    item.path_fence_style = PathFenceStyle.GRAVEL_PATH
    original = custom_pen(item)
    choose(panel, ObjectType.WALL)
    for undone in (False, True):
        if undone:
            canvas.command_manager.undo()
        data = ProjectManager._serialize_item(item)
        loaded = ProjectManager._deserialize_item(data)
        assert isinstance(loaded, PolylineItem)
        assert loaded.object_type is item.object_type
        assert loaded.path_fence_style is item.path_fence_style
        assert loaded.pen() == item.pen()
        assert style_gaps(loaded) == []
        assert ProjectManager._serialize_item(loaded) == data
        if undone:
            assert loaded.pen() == original
    qtbot.wait(1)


def test_type_change_selection_keeps_one_command_per_line(canvas: Any, line_panel: Any) -> None:
    item, _ = line_panel
    second = PolylineItem([QPointF(100, 400), QPointF(400, 400)], object_type=ObjectType.PATH,
                          path_fence_style=PathFenceStyle.GRAVEL_PATH)
    canvas.scene().addItem(second)
    first_pen, second_pen = custom_pen(item), custom_pen(second, 7.0)
    item.setSelected(True)
    second.setSelected(True)
    count = len(canvas.command_manager._undo_stack)
    item._dispatch_change_type(ObjectType.WALL)
    assert len(canvas.command_manager._undo_stack) == count + 2
    assert item.object_type is second.object_type is ObjectType.WALL
    canvas.command_manager.undo()
    canvas.command_manager.undo()
    assert item.pen() == first_pen and second.pen() == second_pen
    assert second.path_fence_style is PathFenceStyle.GRAVEL_PATH


def test_snapshots_do_not_share_mutable_qt_values(line_panel: Any) -> None:
    from open_garden_planner.core.item_look import apply_line_look, capture_line_look

    item, _ = line_panel
    original = custom_pen(item)
    snapshot = capture_line_look(item)
    custom_pen(item, 30)
    apply_line_look(item, snapshot)
    assert item.pen() == original
    custom_pen(item, 45)
    apply_line_look(item, snapshot)
    assert item.pen() == original


@pytest.mark.parametrize("surface", ["panel", "context"])
def test_real_app_marks_type_edits_and_history_dirty(qtbot: Any, monkeypatch: Any, surface: str) -> None:
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda *_: None)
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    item = PolylineItem([QPointF(100, 100), QPointF(400, 100)], object_type=ObjectType.PATH)
    app.canvas_scene.addItem(item)
    item.setSelected(True)
    app.properties_panel.set_selected_items([item])
    pm, manager = app._project_manager, app.canvas_view.command_manager
    pm.mark_clean()
    try:
        if surface == "panel":
            choose(app.properties_panel, ObjectType.WALL)
        else:
            context_type(item, ObjectType.WALL, monkeypatch)
        assert pm.is_dirty
        pm.mark_clean()
        manager.undo()
        assert pm.is_dirty and item.object_type is ObjectType.PATH
        pm.mark_clean()
        manager.redo()
        assert pm.is_dirty and item.object_type is ObjectType.WALL
        qtbot.wait(1)
        combos = app.properties_panel.findChildren(QComboBox)
        assert any(combo.currentData() is ObjectType.WALL for combo in combos)
    finally:
        pm.mark_clean()


def test_ground_snapshot_and_pixels_follow_type_undo(canvas: Any, line_panel: Any, qtbot: Any) -> None:
    from datetime import date

    import numpy as np

    from tests.integration.ground_bake_support import Bake

    item, panel = line_panel
    item.path_fence_style = PathFenceStyle.GRAVEL_PATH
    original = custom_pen(item)
    pipeline = Bake(canvas.scene(), at_date=date(2026, 6, 21))
    pipeline.step()
    pipeline.finish()
    before = pipeline.image().copy()
    records = pipeline.records
    choose(panel, ObjectType.WALL)
    pipeline.step()
    pipeline.finish()
    assert pipeline.records != records
    assert not np.array_equal(pipeline.image(), before)
    canvas.command_manager.undo()
    pipeline.step()
    pipeline.finish()
    assert item.pen() == original and pipeline.records == records
    assert np.array_equal(pipeline.image(), before)
    qtbot.wait(1)
