"""Seasonal soil-test reminder badge (US-12.10e).

A small clock-icon badge anchored at the top-right corner of a bed when
:func:`SoilService.is_test_overdue` returns True. Clicking the badge
emits the ``clicked`` signal with the bed UUID; the application opens
:class:`SoilTestDialog` for that bed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsObject

if TYPE_CHECKING:
    from PyQt6.QtWidgets import (
        QGraphicsSceneMouseEvent,
        QStyleOptionGraphicsItem,
        QWidget,
    )

BADGE_SIZE = 16.0
OFFSET_X = 8.0
OFFSET_Y = 8.0

_FILL_COLOR = QColor(245, 158, 11)        # amber
_OUTLINE_COLOR = QColor(120, 70, 0)
_HAND_COLOR = QColor(40, 30, 0)


class SoilBadgeItem(QGraphicsObject):
    """Clock badge anchored to a bed's top-right corner."""

    clicked = pyqtSignal(str)

    def __init__(self, parent_item: QGraphicsItem, bed_id: str) -> None:
        super().__init__()
        self._parent_item = parent_item
        self._bed_id = bed_id

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(10_002)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self.tr("Soil test overdue — click to record"))

    @property
    def bed_id(self) -> str:
        return self._bed_id

    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt API)
        half = BADGE_SIZE / 2.0
        return QRectF(-half, -half, BADGE_SIZE, BADGE_SIZE)

    def paint(
        self,
        painter: QPainter,
        _option: QStyleOptionGraphicsItem,
        _widget: QWidget | None = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        half = BADGE_SIZE / 2.0
        rect = QRectF(-half, -half, BADGE_SIZE, BADGE_SIZE)

        painter.setPen(QPen(_OUTLINE_COLOR, 1.0))
        painter.setBrush(QBrush(_FILL_COLOR))
        painter.drawEllipse(rect)

        # Clock hands: 12 o'clock (vertical) + 3 o'clock (horizontal), from centre.
        hand_pen = QPen(_HAND_COLOR, 1.2)
        hand_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(hand_pen)
        painter.drawLine(QPointF(0, 0), QPointF(0, -BADGE_SIZE * 0.32))
        painter.drawLine(QPointF(0, 0), QPointF(BADGE_SIZE * 0.28, 0))

    def update_position(self) -> None:
        """Re-anchor the badge to the parent bed's top-right (screen-fixed offset)."""
        if self._parent_item is None or self._parent_item.scene() is None:
            return

        scale = 1.0
        views = self._parent_item.scene().views()
        if views:
            transform_scale = views[0].transform().m11()
            if transform_scale > 0:
                scale = transform_scale

        offset_x = OFFSET_X / scale
        offset_y = OFFSET_Y / scale

        rect = self._parent_item.boundingRect()
        local_corner = QPointF(rect.right() + offset_x, rect.top() - offset_y)
        scene_pos = self._parent_item.mapToScene(local_corner)
        self.setPos(scene_pos)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._bed_id)
            event.accept()
            return
        super().mousePressEvent(event)
