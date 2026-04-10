"""Integration tests: tool activation and switching.

Verifies that:
  - The default active tool is SELECT.
  - Switching tools works correctly.
  - Switching while a draw is in progress cleanly cancels the draw.
  - Completing a draw auto-switches back to SELECT (add_item behaviour).
  - Escape key cancels an active drawing gesture.
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _escape_key_event() -> MagicMock:
    event = MagicMock(spec=QKeyEvent)
    event.key.return_value = Qt.Key.Key_Escape
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _rect_count(view: CanvasView) -> int:
    return sum(1 for i in view.scene().items() if isinstance(i, RectangleItem))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestToolSwitching:
    """Tool activation and switching integration tests."""

    def test_default_tool_is_select(self, canvas: CanvasView, qtbot: object) -> None:
        """After CanvasView initialisation the SELECT tool is active."""
        assert canvas.tool_manager.active_tool_type == ToolType.SELECT

    def test_switch_to_rectangle(self, canvas: CanvasView, qtbot: object) -> None:
        """set_active_tool(RECTANGLE) makes RECTANGLE the active tool."""
        canvas.set_active_tool(ToolType.RECTANGLE)
        assert canvas.tool_manager.active_tool_type == ToolType.RECTANGLE

    def test_switch_to_circle(self, canvas: CanvasView, qtbot: object) -> None:
        """set_active_tool(CIRCLE) makes CIRCLE the active tool."""
        canvas.set_active_tool(ToolType.CIRCLE)
        assert canvas.tool_manager.active_tool_type == ToolType.CIRCLE

    def test_switch_to_polygon(self, canvas: CanvasView, qtbot: object) -> None:
        """set_active_tool(POLYGON) makes POLYGON the active tool."""
        canvas.set_active_tool(ToolType.POLYGON)
        assert canvas.tool_manager.active_tool_type == ToolType.POLYGON

    def test_switch_from_select_to_rectangle_and_back(self, canvas: CanvasView, qtbot: object) -> None:
        """Switching between tools updates active_tool_type each time."""
        assert canvas.tool_manager.active_tool_type == ToolType.SELECT
        canvas.set_active_tool(ToolType.RECTANGLE)
        assert canvas.tool_manager.active_tool_type == ToolType.RECTANGLE
        canvas.set_active_tool(ToolType.SELECT)
        assert canvas.tool_manager.active_tool_type == ToolType.SELECT

    def test_tool_changed_signal_emitted(self, canvas: CanvasView, qtbot: object) -> None:
        """tool_manager.tool_changed is emitted when switching tools."""
        with qtbot.waitSignal(canvas.tool_manager.tool_changed, timeout=500):
            canvas.set_active_tool(ToolType.RECTANGLE)

    def test_switch_while_drawing_cancels_draw(self, canvas: CanvasView, qtbot: object) -> None:
        """Switching away from a tool mid-draw cancels the ongoing gesture.

        BaseTool.deactivate() calls self.cancel() — so no partial item should remain
        and the old tool's drawing state should be reset.
        """
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        # Start a draw gesture but don't release
        tool.mouse_press(event, QPointF(100, 100))
        assert tool._is_drawing is True

        # Switch tool — deactivate() calls cancel()
        canvas.set_active_tool(ToolType.SELECT)

        # Previous tool state should be reset
        assert tool._is_drawing is False
        assert tool._preview_item is None
        # No item should have been created
        assert _rect_count(canvas) == 0

    def test_draw_tool_stays_active_after_completing_draw(self, canvas: CanvasView, qtbot: object) -> None:
        """After completing a draw gesture the tool remains active (not auto-switched).

        CanvasView.add_item() does NOT switch to SELECT for tool-based draws.
        (SELECT auto-switch only happens for gallery drag-drop, not tool gestures.)
        The user must press Escape or select SELECT explicitly.
        """
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_move(event, QPointF(400, 300))
        tool.mouse_release(event, QPointF(400, 300))

        # Tool stays as RECTANGLE — draw again immediately is possible
        assert canvas.tool_manager.active_tool_type == ToolType.RECTANGLE

    def test_escape_cancels_active_draw_gesture(self, canvas: CanvasView, qtbot: object) -> None:
        """Escape key during a draw cancels the gesture (no item created)."""
        click = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(click, QPointF(100, 100))
        assert tool._is_drawing is True

        # Simulate Escape via the tool's key_press handler
        esc = _escape_key_event()
        tool.key_press(esc)

        assert tool._is_drawing is False
        assert _rect_count(canvas) == 0
