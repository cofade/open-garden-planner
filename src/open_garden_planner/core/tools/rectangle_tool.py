"""Rectangle drawing tool."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsRectItem

from open_garden_planner.core.object_types import ObjectType

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class RectangleTool(BaseTool):
    """Tool for drawing axis-aligned rectangles.

    Usage:
        - Click and drag to draw rectangle
        - Hold Shift while dragging to constrain to square
        - Press Escape to cancel
    """

    tool_type = ToolType.RECTANGLE
    display_name = "Rectangle"
    shortcut = "R"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(
        self,
        view: "CanvasView",
        object_type: ObjectType = ObjectType.GENERIC_RECTANGLE,
    ) -> None:
        """Initialize the rectangle tool.

        Args:
            view: The canvas view
            object_type: Type of property object to create
        """
        super().__init__(view)
        self._object_type = object_type
        self._start_point: QPointF | None = None
        self._preview_item: QGraphicsRectItem | None = None
        self._is_drawing = False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Start drawing rectangle on left click."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        self._start_point = scene_pos
        self._is_drawing = True

        # Create preview rectangle
        self._preview_item = QGraphicsRectItem()
        self._preview_item.setPen(QPen(QColor(0, 100, 255), 1, Qt.PenStyle.DashLine))
        self._preview_item.setBrush(QBrush(QColor(100, 100, 255, 50)))
        self._view.scene().addItem(self._preview_item)

        return True

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Update preview rectangle while dragging."""
        if not self._is_drawing or not self._preview_item:
            return False

        rect = self._calculate_rect(self._start_point, scene_pos, event)
        self._preview_item.setRect(rect)

        return True

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Finalize rectangle on mouse release."""
        if not self._is_drawing or event.button() != Qt.MouseButton.LeftButton:
            return False

        # Remove preview
        if self._preview_item:
            self._view.scene().removeItem(self._preview_item)
            self._preview_item = None

        # Create final rectangle if it has area
        rect = self._calculate_rect(self._start_point, scene_pos, event)
        if rect.width() > 1 and rect.height() > 1:  # Minimum size
            from open_garden_planner.ui.canvas.items import RectangleItem
            # Get active layer from scene
            scene = self._view.scene()
            layer_id = scene.active_layer.id if hasattr(scene, 'active_layer') and scene.active_layer else None
            item = RectangleItem(
                rect.x(),
                rect.y(),
                rect.width(),
                rect.height(),
                object_type=self._object_type,
                layer_id=layer_id,
            )
            self._view.add_item(item, "rectangle")

        self._reset_state()
        return True

    def key_press(self, event: QKeyEvent) -> bool:
        """Handle Escape to cancel drawing."""
        if event.key() == Qt.Key.Key_Escape and self._is_drawing:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        """Cancel current drawing operation."""
        if self._preview_item:
            self._view.scene().removeItem(self._preview_item)
            self._preview_item = None
        self._reset_state()

    def _reset_state(self) -> None:
        """Reset tool state."""
        self._start_point = None
        self._preview_item = None
        self._is_drawing = False

    def _calculate_rect(
        self,
        start: QPointF,
        end: QPointF,
        event: QMouseEvent,
    ) -> QRectF:
        """Calculate rectangle, with Shift for square constraint."""
        width = end.x() - start.x()
        height = end.y() - start.y()

        # Shift key constrains to square
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            size = max(abs(width), abs(height))
            width = size if width >= 0 else -size
            height = size if height >= 0 else -size

        # Normalize to positive width/height
        x = min(start.x(), start.x() + width)
        y = min(start.y(), start.y() + height)

        return QRectF(x, y, abs(width), abs(height))
