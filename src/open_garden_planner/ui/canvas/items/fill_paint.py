"""Paint a shape item's own fill at the resolution it is shown at (#785).

A rectangle, circle, ellipse or polygon item paints its fill and outline through
its Qt base class (``QGraphicsRectItem.paint`` and friends), which reads the
item's own ``QBrush`` — a pattern tile of 1 texture pixel per centimetre. That
is right at 100 % zoom and an upscaled bitmap above it.

The tile a fill needs depends on the painter (the canvas at this zoom, an
export at that scale, the minimap), so it cannot be the item's brush: an item
is painted by several painters. ``paint_shape`` therefore asks
``core.fill_patterns.brush_for_painter`` for the brush *this* painter needs and,
when that is another one, draws what the base class would have drawn with it —
the same pen, the same shape, the same selection highlight. When the brush is
right as it is (a solid colour, 100 % zoom) the base class paints, exactly as
before.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QStyle,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.fill_patterns import brush_for_painter

#: A full ellipse in Qt's sixteenths of a degree.
_FULL_TURN = 360 * 16


def paint_shape(
    item: Any,
    painter: QPainter,
    option: QStyleOptionGraphicsItem,
    widget: QWidget | None,
    base_paint: Callable[[QPainter, QStyleOptionGraphicsItem, QWidget | None], None],
) -> None:
    """Paint ``item``'s fill and outline as ``base_paint`` (its Qt base class's
    ``paint``) does, with the fill tile at ``painter``'s resolution."""
    brush = brush_for_painter(item.brush(), painter)
    if brush is None:
        base_paint(painter, option, widget)
        return
    if isinstance(item, QGraphicsRectItem):
        painter.setPen(item.pen())
        painter.setBrush(brush)
        painter.drawRect(item.rect())
    elif (
        isinstance(item, QGraphicsEllipseItem)
        # Qt's own rule (QGraphicsEllipseItem::paint): a whole number of turns
        # is an ellipse; anything else, a span of 0 included, is a pie, which
        # stays Qt's to draw.
        and item.spanAngle() != 0
        and abs(item.spanAngle()) % _FULL_TURN == 0
    ):
        painter.setPen(item.pen())
        painter.setBrush(brush)
        painter.drawEllipse(item.rect())
    elif isinstance(item, QGraphicsPolygonItem):
        painter.setPen(item.pen())
        painter.setBrush(brush)
        painter.drawPolygon(item.polygon(), item.fillRule())
    else:  # a shape this module does not know how to draw: Qt's own paint
        base_paint(painter, option, widget)
        return
    if option is not None and option.state & QStyle.StateFlag.State_Selected:
        _highlight_selected(item, painter, option)


def _highlight_selected(
    item: Any, painter: QPainter, option: QStyleOptionGraphicsItem
) -> None:
    """Qt's own selection frame (``qt_graphicsItem_highlightSelected``): a
    cosmetic dashed rectangle around the bounding rect, inset by half the pen."""
    transform = painter.transform()
    unit = transform.mapRect(QRectF(0.0, 0.0, 1.0, 1.0))
    if max(unit.width(), unit.height()) < 1e-12:
        return
    bounds = item.boundingRect()
    mapped = transform.mapRect(bounds)
    if min(mapped.width(), mapped.height()) < 1.0:
        return
    pad = item.pen().widthF() / 2.0
    frame = bounds.adjusted(pad, pad, -pad, -pad)
    foreground = option.palette.windowText().color()
    background = QColor(
        0 if foreground.red() > 127 else 255,
        0 if foreground.green() > 127 else 255,
        0 if foreground.blue() > 127 else 255,
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(background, 0, Qt.PenStyle.SolidLine))
    painter.drawRect(frame)
    painter.setPen(QPen(option.palette.windowText(), 0, Qt.PenStyle.DashLine))
    painter.drawRect(frame)


__all__ = ["paint_shape"]
