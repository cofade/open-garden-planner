"""Roof-ridge geometry for HOUSE polygons — the ONE canonical computation.

A HOUSE gets an auto-created ``ROOF_RIDGE`` polyline along its longest
bounding-box axis, clipped to the actual polygon boundary. This lived inside
``PolygonTool._create_roof_ridge``; the agent's ``create_object`` (US-D2.5)
must produce the SAME ridge an interactive draw produces, so the geometry was
extracted here and both callers share it — the "one canonical path, never a
second one" discipline (§8.19, the ``geometry_apply``/``arrange`` precedent).

Qt geometry only (QPointF/QPolygonF); no scene, no items, no commands — so it
is callable from any construction path (tool, loader, agent provider).
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF


def intersect_line_polygon(
    polygon: QPolygonF, origin: QPointF, direction: QPointF
) -> tuple[QPointF, QPointF] | None:
    """Find the two points where an infinite line crosses the polygon boundary.

    Args:
        polygon: The polygon to intersect with (item-local coordinates).
        origin: A point on the line.
        direction: The line direction (need not be normalised).

    Returns:
        ``(p_min, p_max)`` along the direction, or ``None`` if fewer than two
        intersections were found.
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


def compute_roof_ridge_endpoints(
    polygon: QPolygonF, pos: QPointF
) -> tuple[QPointF, QPointF]:
    """Scene-frame endpoints of a HOUSE's roof ridge.

    The ridge runs along the polygon's longest bounding-box axis through the
    bbox centre, clipped to the actual polygon boundary (falling back to the
    bbox edges when the clip finds fewer than two crossings).

    Args:
        polygon: The house item's LOCAL ``polygon()`` (item coordinates).
        pos: The house item's scene ``pos()`` — the local-frame origin the
            returned scene-frame endpoints are offset by.

    Returns:
        ``(p1, p2)`` in scene coordinates, ready to feed a ``PolylineItem``
        with ``ObjectType.ROOF_RIDGE``.
    """
    bbox = polygon.boundingRect()

    # Choose ridge direction from longest bbox axis
    cx = bbox.center().x()
    cy = bbox.center().y()
    direction = (
        QPointF(1.0, 0.0) if bbox.width() >= bbox.height() else QPointF(0.0, 1.0)
    )

    # Clip ridge line to actual polygon boundary (not just bbox)
    pts = intersect_line_polygon(polygon, QPointF(cx, cy), direction)
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
    return p1, p2
