"""Integration tests: undo/redo through real UI gestures.

Each test performs an action via the tool API (not direct method calls)
and then exercises the command manager's undo/redo stack.

This ensures the Command pattern is wired correctly end-to-end:
  tool gesture → CreateItemCommand pushed → undo removes item → redo restores it.
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

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


def _draw_rect(view: CanvasView, x1: float, y1: float, x2: float, y2: float) -> None:
    """Draw one rectangle via the RectangleTool (activates the tool first)."""
    event = _left_click_event()
    view.set_active_tool(ToolType.RECTANGLE)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(x1, y1))
    tool.mouse_move(event, QPointF(x2, y2))
    tool.mouse_release(event, QPointF(x2, y2))


def _rect_count(view: CanvasView) -> int:
    return sum(1 for i in view.scene().items() if isinstance(i, RectangleItem))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUndoRedo:
    """Undo/redo via the CommandManager after real tool gestures."""

    def test_draw_then_undo_removes_item(self, canvas: CanvasView, qtbot: object) -> None:
        """Drawing a rectangle and undoing removes it from the scene."""
        assert _rect_count(canvas) == 0

        _draw_rect(canvas, 100, 100, 400, 300)
        assert _rect_count(canvas) == 1, "Item should appear after draw"

        canvas.command_manager.undo()
        assert _rect_count(canvas) == 0, "Item should be gone after undo"

    def test_draw_undo_redo_restores_item(self, canvas: CanvasView, qtbot: object) -> None:
        """Undo followed by redo puts the item back in the scene."""
        _draw_rect(canvas, 100, 100, 400, 300)
        canvas.command_manager.undo()
        assert _rect_count(canvas) == 0

        canvas.command_manager.redo()
        assert _rect_count(canvas) == 1, "Item should be restored after redo"

    def test_undo_stack_tracks_multiple_actions(self, canvas: CanvasView, qtbot: object) -> None:
        """Three separate draws create three undo steps."""
        _draw_rect(canvas, 100, 100, 200, 200)
        _draw_rect(canvas, 300, 100, 400, 200)
        _draw_rect(canvas, 500, 100, 600, 200)
        assert _rect_count(canvas) == 3

        canvas.command_manager.undo()
        assert _rect_count(canvas) == 2

        canvas.command_manager.undo()
        assert _rect_count(canvas) == 1

        canvas.command_manager.undo()
        assert _rect_count(canvas) == 0

    def test_redo_not_available_after_new_action(self, canvas: CanvasView, qtbot: object) -> None:
        """After undo + new draw, redo stack is cleared."""
        _draw_rect(canvas, 100, 100, 300, 200)
        canvas.command_manager.undo()

        # New action after undo — clears the redo stack
        _draw_rect(canvas, 200, 200, 400, 300)
        assert not canvas.command_manager.can_redo, (
            "Redo should be unavailable after a new action post-undo"
        )

    def test_undo_not_available_on_empty_scene(self, canvas: CanvasView, qtbot: object) -> None:
        """Fresh canvas has nothing to undo."""
        assert not canvas.command_manager.can_undo

    def test_cancel_draw_produces_no_undo_entry(self, canvas: CanvasView, qtbot: object) -> None:
        """Cancelling a draw mid-gesture leaves the undo stack empty."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(100, 100))
        tool.cancel()

        assert _rect_count(canvas) == 0
        assert not canvas.command_manager.can_undo, (
            "Cancelled draw should not push to undo stack"
        )
