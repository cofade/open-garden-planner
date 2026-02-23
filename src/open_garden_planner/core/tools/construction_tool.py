"""Construction geometry drawing tools.

Construction lines and circles are helper geometry that guide placement
but are excluded from exports and prints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

_PREVIEW_COLOR = QColor(30, 130, 220, 150)


class ConstructionLineTool(BaseTool):
    """Tool for drawing construction line segments.

    Click first endpoint, then second endpoint to create a dashed
    light-blue construction line.

    Usage:
        - First click: set start point
        - Second click: finish line
        - Escape: cancel
    """

    tool_type = ToolType.CONSTRUCTION_LINE
    display_name = "Construction Line"
    shortcut = ""
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._start: QPointF | None = None
        self._preview: QGraphicsLineItem | None = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        snapped = self._view.snap_point(scene_pos)

        if self._start is None:
            # First click: record start point and create preview
            self._start = snapped
            self._preview = QGraphicsLineItem(
                QLineF(self._start, self._start)
            )
            pen = QPen(_PREVIEW_COLOR, 1.2, Qt.PenStyle.DashLine)
            self._preview.setPen(pen)
            self._view.scene().addItem(self._preview)
        else:
            # Second click: finalize the line
            self._finish(snapped)

        return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        if self._start is None or self._preview is None:
            return False
        snapped = self._view.snap_point(scene_pos)
        self._preview.setLine(QLineF(self._start, snapped))
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._start is not None:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        if self._preview is not None:
            self._view.scene().removeItem(self._preview)
            self._preview = None
        self._start = None

    def _finish(self, end: QPointF) -> None:
        if self._preview is not None:
            self._view.scene().removeItem(self._preview)
            self._preview = None

        if self._start is not None and QLineF(self._start, end).length() > 0.5:
            from open_garden_planner.ui.canvas.items.construction_item import (
                ConstructionLineItem,
            )
            item = ConstructionLineItem(self._start, end)
            self._view.add_item(item, "construction_line")

        self._start = None


class ConstructionCircleTool(BaseTool):
    """Tool for drawing construction circles.

    First click sets the center, second click sets the radius.

    Usage:
        - First click: set center
        - Second click: finish circle
        - Escape: cancel
    """

    tool_type = ToolType.CONSTRUCTION_CIRCLE
    display_name = "Construction Circle"
    shortcut = ""
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._center: QPointF | None = None
        self._preview: QGraphicsEllipseItem | None = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        snapped = self._view.snap_point(scene_pos)

        if self._center is None:
            self._center = snapped
            self._preview = QGraphicsEllipseItem(
                snapped.x(), snapped.y(), 0, 0
            )
            pen = QPen(_PREVIEW_COLOR, 1.2, Qt.PenStyle.DashLine)
            self._preview.setPen(pen)
            self._preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._view.scene().addItem(self._preview)
        else:
            self._finish(snapped)

        return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        if self._center is None or self._preview is None:
            return False
        snapped = self._view.snap_point(scene_pos)
        radius = QLineF(self._center, snapped).length()
        self._preview.setRect(
            self._center.x() - radius,
            self._center.y() - radius,
            radius * 2,
            radius * 2,
        )
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._center is not None:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        if self._preview is not None:
            self._view.scene().removeItem(self._preview)
            self._preview = None
        self._center = None

    def _finish(self, rim: QPointF) -> None:
        if self._preview is not None:
            self._view.scene().removeItem(self._preview)
            self._preview = None

        if self._center is not None:
            radius = QLineF(self._center, rim).length()
            if radius > 0.5:
                from open_garden_planner.ui.canvas.items.construction_item import (
                    ConstructionCircleItem,
                )
                item = ConstructionCircleItem(
                    self._center.x(), self._center.y(), radius
                )
                self._view.add_item(item, "construction_circle")

        self._center = None
