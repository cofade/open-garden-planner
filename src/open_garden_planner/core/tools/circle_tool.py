"""Circle drawing tool."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem

from open_garden_planner.core.object_types import ObjectType

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class CircleTool(BaseTool):
    """Tool for drawing circles by clicking center then rim.

    Usage:
        - First click: Set center point
        - Second click: Set radius (rim point)
        - Press Escape to cancel
    """

    tool_type = ToolType.CIRCLE
    display_name = "Circle"
    shortcut = "C"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(
        self,
        view: "CanvasView",
        object_type: ObjectType = ObjectType.GENERIC_CIRCLE,
    ) -> None:
        """Initialize the circle tool.

        Args:
            view: The canvas view
            object_type: Type of property object to create
        """
        super().__init__(view)
        self._object_type = object_type
        self._center_point: QPointF | None = None
        self._preview_circle: QGraphicsEllipseItem | None = None
        self._preview_line: QGraphicsLineItem | None = None
        self._is_drawing = False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle click for center or rim point."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        if not self._is_drawing:
            # First click: set center
            self._center_point = scene_pos
            self._is_drawing = True

            # Create preview circle (starts with zero radius)
            self._preview_circle = QGraphicsEllipseItem()
            self._preview_circle.setPen(
                QPen(QColor(0, 100, 255), 1, Qt.PenStyle.DashLine)
            )
            self._preview_circle.setBrush(QBrush(QColor(100, 100, 255, 50)))
            self._view.scene().addItem(self._preview_circle)

            # Create preview line from center to rim
            self._preview_line = QGraphicsLineItem()
            self._preview_line.setPen(
                QPen(QColor(100, 100, 100), 1, Qt.PenStyle.DashLine)
            )
            self._view.scene().addItem(self._preview_line)

            return True
        else:
            # Second click: finalize circle
            self._finalize_circle(scene_pos)
            return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Update preview circle while selecting rim point."""
        if not self._is_drawing or not self._preview_circle or not self._center_point:
            return False

        # Calculate radius from center to current mouse position
        radius = QLineF(self._center_point, scene_pos).length()

        # Update preview circle
        top_left_x = self._center_point.x() - radius
        top_left_y = self._center_point.y() - radius
        diameter = radius * 2
        self._preview_circle.setRect(top_left_x, top_left_y, diameter, diameter)

        # Update preview line
        if self._preview_line:
            self._preview_line.setLine(
                self._center_point.x(),
                self._center_point.y(),
                scene_pos.x(),
                scene_pos.y(),
            )

        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        """No-op for circle tool (uses click, not drag)."""
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        """Handle Escape to cancel drawing."""
        if event.key() == Qt.Key.Key_Escape and self._is_drawing:
            self.cancel()
            return True
        return False

    def _finalize_circle(self, rim_pos: QPointF) -> None:
        """Create final circle item."""
        if not self._center_point:
            return

        # Calculate radius
        radius = QLineF(self._center_point, rim_pos).length()

        # Remove preview items
        self._cleanup_preview()

        # Create final circle if it has a meaningful radius
        if radius > 1:  # Minimum radius in cm
            from open_garden_planner.ui.canvas.items import CircleItem
            # Get active layer from scene
            scene = self._view.scene()
            layer_id = scene.active_layer.id if hasattr(scene, 'active_layer') and scene.active_layer else None
            item = CircleItem(
                self._center_point.x(),
                self._center_point.y(),
                radius,
                object_type=self._object_type,
                layer_id=layer_id,
            )
            self._view.add_item(item, "circle")

        self._reset_state()

    def _cleanup_preview(self) -> None:
        """Remove preview items from scene."""
        if self._preview_circle:
            self._view.scene().removeItem(self._preview_circle)
            self._preview_circle = None
        if self._preview_line:
            self._view.scene().removeItem(self._preview_line)
            self._preview_line = None

    def _reset_state(self) -> None:
        """Reset tool state for next circle."""
        self._center_point = None
        self._is_drawing = False

    def cancel(self) -> None:
        """Cancel the current circle drawing operation."""
        self._cleanup_preview()
        self._reset_state()
