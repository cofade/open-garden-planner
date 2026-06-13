"""Integration test: undo/redo marks the project dirty (issue #209).

Regression guard for the data-loss bug where undoing or redoing after a save
left the document falsely "clean" — closing then discarded the change with no
"unsaved changes" prompt.

The fix added a `stack_changed` signal on the CommandManager (emitted by
execute/undo/redo, but NOT clear) that `GardenPlannerApp` wires to
`ProjectManager.mark_dirty`. The bare `canvas` fixture has no ProjectManager,
so we wire one here exactly as application.py does.
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView


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


class TestUndoRedoMarksDirty:
    """stack_changed → mark_dirty on execute, undo, and redo."""

    def test_undo_redo_mark_project_dirty(self, canvas: CanvasView, qtbot: object) -> None:
        manager = ProjectManager()
        # Mirror application.py wiring.
        canvas.command_manager.stack_changed.connect(manager.mark_dirty)

        # Execute path still dirties.
        manager.mark_clean()
        _draw_rect(canvas, 100, 100, 400, 300)
        assert manager.is_dirty, "Drawing (execute) must mark the project dirty"

        # The bug: undo after a save left the document 'clean'.
        manager.mark_clean()
        canvas.command_manager.undo()
        assert manager.is_dirty, "Undo must mark the project dirty (issue #209)"

        # ...and redo too.
        manager.mark_clean()
        canvas.command_manager.redo()
        assert manager.is_dirty, "Redo must mark the project dirty (issue #209)"

    def test_stack_changed_emitted_on_execute_undo_redo(
        self, canvas: CanvasView, qtbot
    ) -> None:
        cmd_mgr = canvas.command_manager

        with qtbot.waitSignal(cmd_mgr.stack_changed):
            _draw_rect(canvas, 100, 100, 400, 300)

        with qtbot.waitSignal(cmd_mgr.stack_changed):
            cmd_mgr.undo()

        with qtbot.waitSignal(cmd_mgr.stack_changed):
            cmd_mgr.redo()
