"""Integration tests for Callout / leader line annotation tool (US-11.10).

Tests exercise the full click → drag → release gesture and verify that:
- A CalloutItem is placed in the scene
- The item has the correct target position and box offset
- Editing mode is activated on placement
- Escape cancels an in-progress drag (no item placed)
- Serialization round-trip preserves target and content
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.callout_item import CalloutItem


def _mouse_event(button: Qt.MouseButton = Qt.MouseButton.LeftButton) -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = button
    event.buttons.return_value = button
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _key_event(key: Qt.Key) -> MagicMock:
    event = MagicMock(spec=QKeyEvent)
    event.key.return_value = key
    return event


def _callouts(view: CanvasView) -> list[CalloutItem]:
    return [i for i in view.scene().items() if isinstance(i, CalloutItem)]


def _draw_callout(
    view: CanvasView,
    target: QPointF,
    box_pos: QPointF,
) -> None:
    """Simulate click at target, drag to box_pos, release."""
    view.set_active_tool(ToolType.CALLOUT)
    tool = view.tool_manager.active_tool
    press_event = _mouse_event()
    move_event = _mouse_event()
    release_event = _mouse_event()

    tool.mouse_press(press_event, target)
    tool.mouse_move(move_event, box_pos)
    tool.mouse_release(release_event, box_pos)


class TestBasicPlacement:
    def test_drag_places_callout_item(self, canvas: CanvasView, qtbot: object) -> None:
        _draw_callout(canvas, QPointF(100, 100), QPointF(300, 50))
        assert len(_callouts(canvas)) == 1

    def test_callout_target_is_scene_position(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        target = QPointF(150, 200)
        _draw_callout(canvas, target, QPointF(350, 100))
        item = _callouts(canvas)[0]
        assert abs(item.pos().x() - target.x()) < 1.0
        assert abs(item.pos().y() - target.y()) < 1.0

    def test_box_offset_reflects_drag(self, canvas: CanvasView, qtbot: object) -> None:
        target = QPointF(100, 100)
        box_pos = QPointF(300, 40)
        _draw_callout(canvas, target, box_pos)
        item = _callouts(canvas)[0]
        assert abs(item._box_offset.x() - (box_pos.x() - target.x())) < 1.0
        assert abs(item._box_offset.y() - (box_pos.y() - target.y())) < 1.0

    def test_minimum_offset_applied_on_tiny_drag(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Tiny drags get a default offset so the box is not on top of the tip."""
        _draw_callout(canvas, QPointF(100, 100), QPointF(105, 105))
        item = _callouts(canvas)[0]
        magnitude = (item._box_offset.x() ** 2 + item._box_offset.y() ** 2) ** 0.5
        assert magnitude > 20.0

    def test_placement_enters_editing_mode(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        _draw_callout(canvas, QPointF(100, 100), QPointF(300, 50))
        item = _callouts(canvas)[0]
        assert item._editing


class TestCancel:
    def test_escape_during_drag_places_no_item(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        canvas.set_active_tool(ToolType.CALLOUT)
        tool = canvas.tool_manager.active_tool
        tool.mouse_press(_mouse_event(), QPointF(100, 100))
        tool.mouse_move(_mouse_event(), QPointF(300, 50))
        consumed = tool.key_press(_key_event(Qt.Key.Key_Escape))
        assert consumed is True
        assert len(_callouts(canvas)) == 0

    def test_escape_when_idle_switches_to_select(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        canvas.set_active_tool(ToolType.CALLOUT)
        tool = canvas.tool_manager.active_tool
        consumed = tool.key_press(_key_event(Qt.Key.Key_Escape))
        assert consumed is True
        assert canvas.tool_manager.active_tool.tool_type == ToolType.SELECT


class TestUndo:
    def test_undo_removes_callout(self, canvas: CanvasView, qtbot: object) -> None:
        _draw_callout(canvas, QPointF(100, 100), QPointF(300, 50))
        assert len(_callouts(canvas)) == 1
        canvas.command_manager.undo()
        assert len(_callouts(canvas)) == 0

    def test_redo_restores_callout(self, canvas: CanvasView, qtbot: object) -> None:
        _draw_callout(canvas, QPointF(100, 100), QPointF(300, 50))
        canvas.command_manager.undo()
        canvas.command_manager.redo()
        assert len(_callouts(canvas)) == 1


class TestSerialization:
    def test_save_load_preserves_target_and_offset(
        self, canvas: CanvasView, qtbot: object, tmp_path: object
    ) -> None:
        from open_garden_planner.core.project import ProjectManager

        target = QPointF(200, 300)
        box_pos = QPointF(400, 200)
        _draw_callout(canvas, target, box_pos)

        item = _callouts(canvas)[0]
        # Commit editing so content is stable
        item._commit_edit()

        orig_pos = item.pos()
        orig_offset = item._box_offset

        pm = ProjectManager()
        path = tmp_path / "callout_test.ogp"  # type: ignore[operator]
        pm.save(canvas.scene(), path)

        canvas.scene().clear()
        pm.load(canvas.scene(), path)

        reloaded = _callouts(canvas)
        assert len(reloaded) == 1

        r = reloaded[0]
        assert abs(r.pos().x() - orig_pos.x()) < 1.0
        assert abs(r.pos().y() - orig_pos.y()) < 1.0
        assert abs(r._box_offset.x() - orig_offset.x()) < 1.0
        assert abs(r._box_offset.y() - orig_offset.y()) < 1.0
