"""One-click placement of a named reference point (#666, ADR-080)."""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from .base_tool import BaseTool, ToolType


class ReferencePointTool(BaseTool):
    """A click opens the reference-point dialog at the clicked coordinate."""

    tool_type = ToolType.REFERENCE_POINT
    display_name = QCoreApplication.translate("ReferencePoints", "Reference point")
    shortcut = ""
    cursor = Qt.CursorShape.CrossCursor
    # The click owns the point: do not let another item's anchor move it first.
    skip_anchor_snap = True

    def _translated_name(self) -> str:
        return QCoreApplication.translate("ReferencePoints", "Reference point")

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        from open_garden_planner.ui.reference_points import place_reference_point

        placed = place_reference_point(self.view, scene_pos)
        self.view.set_active_tool(ToolType.SELECT)
        return placed

    def mouse_move(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self.view.set_active_tool(ToolType.SELECT)
            return True
        return False

    def cancel(self) -> None:
        """Leaving the tool needs no half-finished geometry to discard."""

    def draw_preview(self, _painter: object) -> None:
        """The tool has no rubber-band preview."""
