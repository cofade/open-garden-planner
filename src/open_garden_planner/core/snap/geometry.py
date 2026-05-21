"""Low-level geometry helpers for the snap engine."""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtWidgets import QGraphicsItem


def item_edges(item: QGraphicsItem) -> Iterable[QLineF]:
    """Yield the straight edges of an item in scene coordinates.

    Returns nothing for items without linear edges (circles, ellipses,
    points).  Used by midpoint and intersection providers.
    """
    from open_garden_planner.ui.canvas.items import (
        PolygonItem,
        PolylineItem,
        RectangleItem,
    )
    from open_garden_planner.ui.canvas.items.construction_item import (
        ConstructionLineItem,
    )

    if isinstance(item, RectangleItem):
        rect = item.rect()
        corners = [
            item.mapToScene(rect.topLeft()),
            item.mapToScene(rect.topRight()),
            item.mapToScene(rect.bottomRight()),
            item.mapToScene(rect.bottomLeft()),
        ]
        for i in range(4):
            yield QLineF(corners[i], corners[(i + 1) % 4])
    elif isinstance(item, PolygonItem):
        poly = item.polygon()
        n = poly.count()
        if n < 2:
            return
        for i in range(n):
            p1 = item.mapToScene(poly.at(i))
            p2 = item.mapToScene(poly.at((i + 1) % n))
            yield QLineF(p1, p2)
    elif isinstance(item, PolylineItem):
        pts = item.points
        if len(pts) < 2:
            return
        for i in range(len(pts) - 1):
            yield QLineF(item.mapToScene(pts[i]), item.mapToScene(pts[i + 1]))
    elif isinstance(item, ConstructionLineItem):
        line = item.line()
        yield QLineF(item.mapToScene(line.p1()), item.mapToScene(line.p2()))


def segment_intersection(a: QLineF, b: QLineF) -> QPointF | None:
    """Return the intersection point of two finite line segments.

    Returns ``None`` for parallel/collinear segments or when the
    intersection falls outside either segment.
    """
    x1, y1 = a.x1(), a.y1()
    x2, y2 = a.x2(), a.y2()
    x3, y3 = b.x1(), b.y1()
    x4, y4 = b.x2(), b.y2()

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if denom == 0:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    eps = 1e-9
    if t < -eps or t > 1 + eps or u < -eps or u > 1 + eps:
        return None
    return QPointF(x1 + t * (x2 - x1), y1 + t * (y2 - y1))
