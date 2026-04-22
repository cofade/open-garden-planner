"""Ellipse drawing tool."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem

from open_garden_planner.core.object_types import ObjectType

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class EllipseTool(BaseTool):
    """Tool for drawing axis-aligned or rotatable ellipses.

    Usage:
        - Click and drag to define bounding rectangle → ellipse drawn inside
        - Hold Shift while dragging to constrain to circle
        - Hold Alt to draw from center outward
        - Press Escape to cancel
    """

    tool_type = ToolType.ELLIPSE
    display_name = QT_TR_NOOP("Ellipse")
    shortcut = "E"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(
        self,
        view: "CanvasView",
        object_type: ObjectType = ObjectType.GENERIC_ELLIPSE,
    ) -> None:
        super().__init__(view)
        self._object_type = object_type
        self._start_point: QPointF | None = None
        self._preview_item: QGraphicsEllipseItem | None = None
        self._is_drawing = False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        self._start_point = self._view.snap_point(scene_pos)
        self._is_drawing = True

        self._preview_item = QGraphicsEllipseItem()
        self._preview_item.setPen(QPen(QColor(0, 100, 255), 1, Qt.PenStyle.DashLine))
        self._preview_item.setBrush(QBrush(QColor(100, 100, 255, 50)))
        self._view.scene().addItem(self._preview_item)

        return True

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if not self._is_drawing or not self._preview_item:
            return False

        snapped_pos = self._view.snap_point(scene_pos)
        rect = self._calculate_rect(self._start_point, snapped_pos, event)
        self._preview_item.setRect(rect)
        return True

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if not self._is_drawing or event.button() != Qt.MouseButton.LeftButton:
            return False

        if self._preview_item:
            self._view.scene().removeItem(self._preview_item)
            self._preview_item = None

        snapped_pos = self._view.snap_point(scene_pos)
        rect = self._calculate_rect(self._start_point, snapped_pos, event)
        if rect.width() > 1 and rect.height() > 1:
            from open_garden_planner.ui.canvas.items import EllipseItem
            scene = self._view.scene()
            layer_id = scene.active_layer.id if hasattr(scene, 'active_layer') and scene.active_layer else None
            item = EllipseItem(
                rect.x(),
                rect.y(),
                rect.width(),
                rect.height(),
                object_type=self._object_type,
                layer_id=layer_id,
            )
            self._view.add_item(item, "ellipse")

        self._reset_state()
        return True

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._is_drawing:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        if self._preview_item:
            self._view.scene().removeItem(self._preview_item)
            self._preview_item = None
        self._reset_state()

    def _reset_state(self) -> None:
        self._start_point = None
        self._preview_item = None
        self._is_drawing = False

    def _calculate_rect(
        self,
        start: QPointF,
        end: QPointF,
        event: QMouseEvent,
    ) -> QRectF:
        """Calculate bounding rect. Shift=circle, Alt=from center."""
        modifiers = event.modifiers()
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)

        if alt:
            # Draw from center: start is center, end defines semi-axes
            rx = abs(end.x() - start.x())
            ry = abs(end.y() - start.y())
            if shift:
                rx = ry = max(rx, ry)
            return QRectF(start.x() - rx, start.y() - ry, rx * 2, ry * 2)

        # Draw from corner
        width = end.x() - start.x()
        height = end.y() - start.y()
        if shift:
            size = max(abs(width), abs(height))
            width = size if width >= 0 else -size
            height = size if height >= 0 else -size

        x = min(start.x(), start.x() + width)
        y = min(start.y(), start.y() + height)
        return QRectF(x, y, abs(width), abs(height))
