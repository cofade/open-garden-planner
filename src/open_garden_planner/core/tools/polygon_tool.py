"""Polygon drawing tool."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPolygonItem

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class PolygonTool(BaseTool):
    """Tool for drawing polygons by clicking vertices.

    Usage:
        - Click to add vertices
        - Double-click, press Enter, or click first point to close
        - Press Escape to cancel
        - Press Backspace to remove last vertex
    """

    tool_type = ToolType.POLYGON
    display_name = "Polygon"
    shortcut = "P"
    cursor = Qt.CursorShape.CrossCursor

    CLOSE_THRESHOLD = 15.0  # Scene units (cm) for closing detection
    VERTEX_MARKER_SIZE = 8.0

    def __init__(self, view: "CanvasView") -> None:
        super().__init__(view)
        self._vertices: list[QPointF] = []
        self._preview_line: QGraphicsLineItem | None = None
        self._preview_polygon: QGraphicsPolygonItem | None = None
        self._vertex_markers: list[QGraphicsEllipseItem] = []
        self._is_drawing = False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Add vertex on left click."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Check if clicking near first vertex to close (need 3+ vertices)
        if (
            self._is_drawing
            and len(self._vertices) >= 3
            and self._is_near_first_vertex(scene_pos)
        ):
            self._close_polygon()
            return True

        # Add vertex
        self._vertices.append(scene_pos)
        self._add_vertex_marker(scene_pos)

        if not self._is_drawing:
            self._is_drawing = True
            self._create_preview_items()

        self._update_preview_polygon()
        return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Update rubber band line while drawing."""
        if not self._is_drawing or not self._vertices:
            return False

        # Update rubber band line from last vertex to cursor
        if self._preview_line:
            last = self._vertices[-1]
            self._preview_line.setLine(last.x(), last.y(), scene_pos.x(), scene_pos.y())

        # Highlight first vertex if near (visual feedback for closing)
        if len(self._vertices) >= 3 and self._vertex_markers:
            is_near = self._is_near_first_vertex(scene_pos)
            marker = self._vertex_markers[0]
            if is_near:
                marker.setBrush(QBrush(QColor(255, 200, 0)))  # Yellow highlight
            else:
                marker.setBrush(QBrush(QColor(0, 100, 255)))  # Normal blue

        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        """Mouse release - no action needed for polygon."""
        return False

    def mouse_double_click(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        """Close polygon on double-click."""
        if self._is_drawing and len(self._vertices) >= 3:
            self._close_polygon()
            return True
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        """Handle keyboard input."""
        if event.key() == Qt.Key.Key_Escape and self._is_drawing:
            self.cancel()
            return True
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and self._is_drawing
            and len(self._vertices) >= 3
        ):
            self._close_polygon()
            return True
        if event.key() == Qt.Key.Key_Backspace and self._is_drawing and self._vertices:
            self._remove_last_vertex()
            return True
        return False

    def cancel(self) -> None:
        """Cancel current drawing operation."""
        self._cleanup_preview()
        self._reset_state()

    def _reset_state(self) -> None:
        """Reset tool state."""
        self._vertices = []
        self._preview_line = None
        self._preview_polygon = None
        self._vertex_markers = []
        self._is_drawing = False

    def _create_preview_items(self) -> None:
        """Create preview graphics items."""
        # Rubber band line
        self._preview_line = QGraphicsLineItem()
        self._preview_line.setPen(QPen(QColor(0, 100, 255), 1, Qt.PenStyle.DashLine))
        self._view.scene().addItem(self._preview_line)

        # Preview polygon fill
        self._preview_polygon = QGraphicsPolygonItem()
        self._preview_polygon.setPen(QPen(QColor(0, 100, 255), 1, Qt.PenStyle.DashLine))
        self._preview_polygon.setBrush(QBrush(QColor(100, 100, 255, 50)))
        self._view.scene().addItem(self._preview_polygon)

    def _add_vertex_marker(self, pos: QPointF) -> None:
        """Add visual marker at vertex position."""
        size = self.VERTEX_MARKER_SIZE / self._view.zoom_factor
        marker = QGraphicsEllipseItem(
            pos.x() - size / 2,
            pos.y() - size / 2,
            size,
            size,
        )
        marker.setPen(QPen(QColor(0, 100, 255), 1))
        marker.setBrush(QBrush(QColor(0, 100, 255)))
        self._view.scene().addItem(marker)
        self._vertex_markers.append(marker)

    def _update_preview_polygon(self) -> None:
        """Update the preview polygon shape."""
        if self._preview_polygon and len(self._vertices) >= 2:
            polygon = QPolygonF(self._vertices)
            self._preview_polygon.setPolygon(polygon)

    def _remove_last_vertex(self) -> None:
        """Remove the last added vertex."""
        if self._vertices:
            self._vertices.pop()
        if self._vertex_markers:
            marker = self._vertex_markers.pop()
            self._view.scene().removeItem(marker)
        self._update_preview_polygon()

        # If no vertices left, cancel drawing
        if not self._vertices:
            self.cancel()

    def _is_near_first_vertex(self, pos: QPointF) -> bool:
        """Check if position is within close threshold of first vertex."""
        if not self._vertices:
            return False
        first = self._vertices[0]
        dx = pos.x() - first.x()
        dy = pos.y() - first.y()
        threshold = self.CLOSE_THRESHOLD / self._view.zoom_factor
        return (dx * dx + dy * dy) < (threshold * threshold)

    def _close_polygon(self) -> None:
        """Finalize the polygon."""
        self._cleanup_preview()

        if len(self._vertices) >= 3:
            from open_garden_planner.ui.canvas.items import PolygonItem
            item = PolygonItem(self._vertices)
            self._view.add_item(item, "polygon")

        self._reset_state()

    def _cleanup_preview(self) -> None:
        """Remove all preview items from scene."""
        if self._preview_line:
            self._view.scene().removeItem(self._preview_line)
        if self._preview_polygon:
            self._view.scene().removeItem(self._preview_polygon)
        for marker in self._vertex_markers:
            self._view.scene().removeItem(marker)
