"""Garden journal pin tool (US-12.9).

Activated from the toolbar (or shortcut ``J``). One left-click forwards
the scene position to the host application via
:meth:`CanvasView.request_journal_note`; the application then opens
:class:`JournalNoteDialog` for a fresh note pre-populated with that
position. On accept the resulting :class:`AddJournalNoteCommand` creates
both the pin item on the canvas and the underlying ``JournalNote`` dict
in the project's ``garden_journal_notes`` store.
"""
from __future__ import annotations

from PyQt6.QtCore import QT_TR_NOOP, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from .base_tool import BaseTool, ToolType


class JournalPinTool(BaseTool):
    """Single-click tool that drops a garden-journal pin at the cursor."""

    tool_type = ToolType.JOURNAL_PIN
    display_name = QT_TR_NOOP("Journal Pin")
    shortcut = "J"
    cursor = Qt.CursorShape.CrossCursor

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if hasattr(self._view, "request_journal_note"):
            self._view.request_journal_note(scene_pos.x(), scene_pos.y())
        # After placement, drop back to the select tool — placing one pin per
        # click is the expected workflow (matches text/callout convention).
        self._view.set_active_tool(ToolType.SELECT)
        return True

    def mouse_move(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self._view.set_active_tool(ToolType.SELECT)
            return True
        return False
