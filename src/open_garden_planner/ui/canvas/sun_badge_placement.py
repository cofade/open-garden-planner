"""Fit a badge inside the undecorated local plant footprint."""

from typing import Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsEllipseItem


def plant_footprint(plant: Any) -> QPainterPath:
    """Use base geometry, never shape()/boundingRect() containing decorations."""
    path = QPainterPath()
    if isinstance(plant, QGraphicsEllipseItem):
        path.addEllipse(plant.rect())
    elif hasattr(plant, "polygon"):
        path.addPolygon(plant.polygon())
        path.closeSubpath()
    elif hasattr(plant, "path"):
        path = QPainterPath(plant.path())
    elif hasattr(plant, "rect"):
        path.addRect(plant.rect())
    return path


def badge_rectangle(path: QPainterPath) -> QRectF | None:
    """Bounded search, largest tested square first, preferring the centre.

    Qt's path containment checks the whole rectangle, including concavities
    and holes. Empty/open footprints with no interior cannot host a badge.
    """
    bounds = path.boundingRect()
    size = min(bounds.width(), bounds.height()) * .4
    if size <= 0:
        return None
    centres = [bounds.center()]
    centres.extend(QPointF(bounds.left() + bounds.width() * (x + .5) / 16,
                          bounds.top() + bounds.height() * (y + .5) / 16)
                   for y in range(16) for x in range(16))
    for _ in range(8):
        for centre in centres:
            rectangle = QRectF(centre.x() - size / 2, centre.y() - size / 2, size, size)
            if path.contains(rectangle):
                return rectangle
        size *= .5
    return None
