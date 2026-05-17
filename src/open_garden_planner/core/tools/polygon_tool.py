"""Polygon drawing tool."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPolygonItem

from open_garden_planner.core.object_types import ObjectType

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView
    from open_garden_planner.ui.canvas.items import PolygonItem


class PolygonTool(BaseTool):
    """Tool for drawing polygons by clicking vertices.

    Usage:
        - Click to add vertices
        - Double-click, press Enter, or click first point to close
        - Press Escape to cancel
        - Press Backspace to remove last vertex
    """

    tool_type = ToolType.POLYGON
    display_name = QT_TR_NOOP("Polygon")
    shortcut = "P"
    cursor = Qt.CursorShape.CrossCursor

    CLOSE_THRESHOLD = 15.0  # Scene units (cm) for closing detection
    VERTEX_MARKER_SIZE = 8.0

    def __init__(
        self,
        view: "CanvasView",
        object_type: ObjectType = ObjectType.GENERIC_POLYGON,
    ) -> None:
        """Initialize the polygon tool.

        Args:
            view: The canvas view
            object_type: Type of property object to create
        """
        super().__init__(view)
        self._object_type = object_type
        self._vertices: list[QPointF] = []
        self._preview_line: QGraphicsLineItem | None = None
        self._preview_polygon: QGraphicsPolygonItem | None = None
        self._vertex_markers: list[QGraphicsEllipseItem] = []
        self._is_drawing = False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Add vertex on left click."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Snap the position to grid if enabled
        snapped_pos = self._view.snap_point(scene_pos)

        # Check if clicking near first vertex to close (need 3+ vertices)
        if (
            self._is_drawing
            and len(self._vertices) >= 3
            and self._is_near_first_vertex(snapped_pos)
        ):
            self._close_polygon()
            return True

        # Add vertex
        self._vertices.append(snapped_pos)
        self._add_vertex_marker(snapped_pos)

        if not self._is_drawing:
            self._is_drawing = True
            self._create_preview_items()

        self._update_preview_polygon()
        return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Update rubber band line while drawing."""
        if not self._is_drawing or not self._vertices:
            return False

        # Snap the position to grid if enabled
        snapped_pos = self._view.snap_point(scene_pos)

        # Update rubber band line from last vertex to cursor
        if self._preview_line:
            last = self._vertices[-1]
            self._preview_line.setLine(last.x(), last.y(), snapped_pos.x(), snapped_pos.y())

        # Highlight first vertex if near (visual feedback for closing)
        if len(self._vertices) >= 3 and self._vertex_markers:
            is_near = self._is_near_first_vertex(snapped_pos)
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

    @property
    def last_point(self) -> QPointF | None:
        """Anchor for relative/polar typed input."""
        if self._vertices:
            return QPointF(self._vertices[-1])
        return None

    def commit_typed_coordinate(self, point: QPointF) -> bool:
        """Add a vertex at ``point`` exactly (no grid snap)."""
        self._vertices.append(QPointF(point))
        self._add_vertex_marker(point)
        if not self._is_drawing:
            self._is_drawing = True
            self._create_preview_items()
        self._update_preview_polygon()
        return True

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
            # Get active layer from scene
            scene = self._view.scene()
            layer_id = scene.active_layer.id if hasattr(scene, 'active_layer') and scene.active_layer else None
            item = PolygonItem(self._vertices, object_type=self._object_type, layer_id=layer_id)
            self._view.add_item(item, "polygon")

            # Auto-create a roof ridge when placing a HOUSE polygon
            if self._object_type == ObjectType.HOUSE:
                self._create_roof_ridge(item, layer_id)

        self._reset_state()

    @staticmethod
    def _intersect_line_polygon(
        polygon: "QPolygonF", origin: QPointF, direction: QPointF
    ) -> tuple[QPointF, QPointF] | None:
        """Find the two points where an infinite line crosses the polygon boundary.

        Args:
            polygon: The polygon to intersect with
            origin: A point on the line
            direction: The line direction (need not be normalised)

        Returns:
            (p_min, p_max) along the direction, or None if < 2 intersections found.
        """
        dx, dy = direction.x(), direction.y()
        ox, oy = origin.x(), origin.y()
        n = polygon.count()
        ts: list[float] = []

        for i in range(n):
            v1 = polygon.at(i)
            v2 = polygon.at((i + 1) % n)
            ex = v2.x() - v1.x()
            ey = v2.y() - v1.y()
            denom = dx * ey - dy * ex
            if abs(denom) < 1e-10:
                continue
            rx = v1.x() - ox
            ry = v1.y() - oy
            t = (rx * ey - ry * ex) / denom
            u = (rx * dy - ry * dx) / denom
            if -1e-6 <= u <= 1.0 + 1e-6:
                ts.append(t)

        if len(ts) < 2:
            return None

        ts.sort()
        t_min, t_max = ts[0], ts[-1]
        return (
            QPointF(ox + t_min * dx, oy + t_min * dy),
            QPointF(ox + t_max * dx, oy + t_max * dy),
        )

    def _create_roof_ridge(self, polygon_item: "PolygonItem", layer_id: object) -> None:
        """Auto-create a roof ridge polyline as a sibling of a HOUSE polygon.

        The ridge is placed along the polygon's longest bounding-box axis,
        clipped to the actual polygon boundary. Both items store cross-references
        in their metadata so the polygon can mirror its tile texture.

        Args:
            polygon_item: The newly created HOUSE polygon item
            layer_id: Layer to place the ridge on
        """
        from open_garden_planner.core.object_types import ObjectType as OT
        from open_garden_planner.ui.canvas.items import PolylineItem

        polygon = polygon_item.polygon()
        bbox = polygon.boundingRect()
        pos = polygon_item.pos()

        # Choose ridge direction from longest bbox axis
        cx = bbox.center().x()
        cy = bbox.center().y()
        direction = QPointF(1.0, 0.0) if bbox.width() >= bbox.height() else QPointF(0.0, 1.0)

        # Clip ridge line to actual polygon boundary (not just bbox)
        pts = self._intersect_line_polygon(polygon, QPointF(cx, cy), direction)
        if pts is not None:
            # Convert from polygon-item-local coords to scene coords
            p1 = QPointF(pos.x() + pts[0].x(), pos.y() + pts[0].y())
            p2 = QPointF(pos.x() + pts[1].x(), pos.y() + pts[1].y())
        else:
            # Fallback to bbox edges
            cx_s = pos.x() + cx
            cy_s = pos.y() + cy
            if bbox.width() >= bbox.height():
                p1 = QPointF(pos.x() + bbox.left(), cy_s)
                p2 = QPointF(pos.x() + bbox.right(), cy_s)
            else:
                p1 = QPointF(cx_s, pos.y() + bbox.top())
                p2 = QPointF(cx_s, pos.y() + bbox.bottom())

        ridge = PolylineItem([p1, p2], object_type=OT.ROOF_RIDGE, layer_id=layer_id)

        # Store cross-references in metadata
        ridge.set_metadata("owner_polygon_id", str(polygon_item.item_id))
        polygon_item.set_metadata("ridge_item_id", str(ridge.item_id))

        self._view.add_item(ridge, "ridge")

    def _cleanup_preview(self) -> None:
        """Remove all preview items from scene."""
        if self._preview_line:
            self._view.scene().removeItem(self._preview_line)
        if self._preview_polygon:
            self._view.scene().removeItem(self._preview_polygon)
        for marker in self._vertex_markers:
            self._view.scene().removeItem(marker)
