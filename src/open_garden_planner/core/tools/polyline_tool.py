"""Polyline drawing tool for fences, walls, and paths."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsPathItem

from open_garden_planner.core.object_types import ObjectType

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class PolylineTool(BaseTool):
    """Tool for drawing polylines (open paths) by clicking vertices.

    Usage:
        - Click to add vertices
        - Double-click or press Enter to finish
        - Press Escape to cancel
        - Press Backspace to remove last vertex
    """

    tool_type = ToolType.FENCE
    display_name = "Polyline"
    shortcut = ""  # Will be set by specific instances
    cursor = Qt.CursorShape.CrossCursor

    VERTEX_MARKER_SIZE = 8.0

    def __init__(
        self,
        view: "CanvasView",
        object_type: ObjectType = ObjectType.FENCE,
    ) -> None:
        """Initialize the polyline tool.

        Args:
            view: The canvas view
            object_type: Type of property object to create
        """
        super().__init__(view)
        self._object_type = object_type
        self._points: list[QPointF] = []
        self._preview_path: QGraphicsPathItem | None = None
        self._vertex_markers: list[QGraphicsEllipseItem] = []
        self._is_drawing = False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Add vertex on left click."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Add point
        self._points.append(scene_pos)
        self._add_vertex_marker(scene_pos)

        if not self._is_drawing:
            self._is_drawing = True
            self._create_preview_path()

        self._update_preview_path(scene_pos)
        return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Update rubber band line while drawing."""
        if not self._is_drawing or not self._points:
            return False

        self._update_preview_path(scene_pos)
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        """Mouse release - no action needed for polyline."""
        return False

    def mouse_double_click(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        """Finish polyline on double-click."""
        if self._is_drawing and len(self._points) >= 2:
            self._finish_polyline()
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
            and len(self._points) >= 2
        ):
            self._finish_polyline()
            return True
        if event.key() == Qt.Key.Key_Backspace and self._is_drawing and self._points:
            self._remove_last_point()
            return True
        return False

    def cancel(self) -> None:
        """Cancel current drawing operation."""
        self._cleanup_preview()
        self._reset_state()

    def _reset_state(self) -> None:
        """Reset tool state."""
        self._points = []
        self._preview_path = None
        self._vertex_markers = []
        self._is_drawing = False

    def _create_preview_path(self) -> None:
        """Create preview path item."""
        self._preview_path = QGraphicsPathItem()
        self._preview_path.setPen(QPen(QColor(0, 100, 255), 2, Qt.PenStyle.DashLine))
        self._view.scene().addItem(self._preview_path)

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

    def _update_preview_path(self, cursor_pos: QPointF) -> None:
        """Update the preview path to show current polyline + rubber band."""
        if not self._preview_path or not self._points:
            return

        path = QPainterPath()
        path.moveTo(self._points[0])

        # Draw all segments
        for point in self._points[1:]:
            path.lineTo(point)

        # Add rubber band to cursor
        path.lineTo(cursor_pos)

        self._preview_path.setPath(path)

    def _remove_last_point(self) -> None:
        """Remove the last added point."""
        if self._points:
            self._points.pop()
        if self._vertex_markers:
            marker = self._vertex_markers.pop()
            self._view.scene().removeItem(marker)

        # Update preview
        if self._points:
            self._update_preview_path(self._points[-1])
        else:
            self.cancel()

    def _finish_polyline(self) -> None:
        """Finalize the polyline."""
        self._cleanup_preview()

        if len(self._points) >= 2:
            from open_garden_planner.ui.canvas.items import PolylineItem
            item = PolylineItem(self._points, object_type=self._object_type)
            self._view.add_item(item, "polyline")

        self._reset_state()

    def _cleanup_preview(self) -> None:
        """Remove all preview items from scene."""
        if self._preview_path:
            self._view.scene().removeItem(self._preview_path)
        for marker in self._vertex_markers:
            self._view.scene().removeItem(marker)
