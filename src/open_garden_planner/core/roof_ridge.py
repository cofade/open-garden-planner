"""Roof-ridge geometry for HOUSE polygons — the ONE canonical computation.

A HOUSE gets an auto-created ``ROOF_RIDGE`` polyline along its longest
bounding-box axis, clipped to the actual polygon boundary. This lived inside
``PolygonTool._create_roof_ridge``; the agent's ``create_object`` (US-D2.5)
must produce the SAME ridge an interactive draw produces, so the geometry was
extracted here and both callers share it — the "one canonical path, never a
second one" discipline (§8.19, the ``geometry_apply``/``arrange`` precedent).

Qt geometry only (QPointF/QPolygonF/QRectF); no scene, no items, no commands — so it
is callable from any construction path (tool, loader, agent provider).
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPolygonF

#: Minimum ridge length in cm. Below this, a ridge is degenerate.
MIN_RIDGE_CM = 1.0


def _dominant_direction_and_center(
    polygon: QPolygonF,
) -> tuple[QPointF, QPointF]:
    """Find the dominant axis direction (unit QPointF) and center QPointF of the polygon.

    Uses Minimum Area Bounding Box (MABB) across edge orientations and vertex
    covariance (PCA), ensuring robust alignment for angled houses, chamfered
    facades, and subdivided walls without distortion.
    """
    n = polygon.count()
    if n < 3:
        bbox = polygon.boundingRect()
        direction = (
            QPointF(1.0, 0.0) if bbox.width() >= bbox.height() else QPointF(0.0, 1.0)
        )
        return direction, bbox.center()

    pts = [polygon.at(i) for i in range(n)]

    # Candidate directions: every edge of the polygon
    candidates: list[tuple[float, float]] = []
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length > 1e-6:
            candidates.append((dx / length, dy / length))

    # Add PCA principal axis of vertices
    mean_x = sum(p.x() for p in pts) / n
    mean_y = sum(p.y() for p in pts) / n
    cxx = sum((p.x() - mean_x) ** 2 for p in pts) / n
    cyy = sum((p.y() - mean_y) ** 2 for p in pts) / n
    cxy = sum((p.x() - mean_x) * (p.y() - mean_y) for p in pts) / n
    theta = 0.5 * math.atan2(2.0 * cxy, cxx - cyy)
    candidates.append((math.cos(theta), math.sin(theta)))

    best_area = float("inf")
    best_dir = QPointF(1.0, 0.0)
    best_center = polygon.boundingRect().center()

    for along_x, along_y in candidates:
        if along_x < -1e-9 or (abs(along_x) <= 1e-9 and along_y < 0):
            along_x = -along_x
            along_y = -along_y
        across_x = -along_y
        across_y = along_x

        us = [p.x() * along_x + p.y() * along_y for p in pts]
        vs = [p.x() * across_x + p.y() * across_y for p in pts]

        span_u = max(us) - min(us)
        span_v = max(vs) - min(vs)
        area = span_u * span_v

        if area < best_area - 1e-6:
            best_area = area
            mid_u = (min(us) + max(us)) / 2.0
            mid_v = (min(vs) + max(vs)) / 2.0
            cx = mid_u * along_x + mid_v * across_x
            cy = mid_u * along_y + mid_v * across_y
            best_center = QPointF(cx, cy)
            if span_u >= span_v:
                best_dir = QPointF(along_x, along_y)
            else:
                d = QPointF(across_x, across_y)
                if d.x() < -1e-9 or (abs(d.x()) <= 1e-9 and d.y() < 0):
                    d = QPointF(-d.x(), -d.y())
                best_dir = d

    return best_dir, best_center


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
        distinct intersections were found or the intersection span is under ``MIN_RIDGE_CM``.
    """
    dx, dy = direction.x(), direction.y()
    ox, oy = origin.x(), origin.y()
    line_len = math.hypot(dx, dy)
    if line_len < 1e-9:
        return None

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

    # Deduplicate parameter values to handle vertices and tangential contacts
    unique_ts: list[float] = []
    for t in sorted(ts):
        if not unique_ts or abs(t - unique_ts[-1]) > 1e-6:
            unique_ts.append(t)

    if len(unique_ts) < 2:
        return None

    t_min, t_max = unique_ts[0], unique_ts[-1]
    if (t_max - t_min) * line_len < MIN_RIDGE_CM:
        return None

    return (
        QPointF(ox + t_min * dx, oy + t_min * dy),
        QPointF(ox + t_max * dx, oy + t_max * dy),
    )


def _clip_line_to_bbox(
    bbox: QRectF, center: QPointF, direction: QPointF
) -> tuple[QPointF, QPointF]:
    """Clip infinite line through center along direction to bounding box boundary segments."""
    dx, dy = direction.x(), direction.y()
    cx, cy = center.x(), center.y()
    ts: list[float] = []

    if abs(dy) > 1e-9:
        for y_edge in (bbox.top(), bbox.bottom()):
            t = (y_edge - cy) / dy
            x_val = cx + t * dx
            if bbox.left() - 1e-6 <= x_val <= bbox.right() + 1e-6:
                ts.append(t)

    if abs(dx) > 1e-9:
        for x_edge in (bbox.left(), bbox.right()):
            t = (x_edge - cx) / dx
            y_val = cy + t * dy
            if bbox.top() - 1e-6 <= y_val <= bbox.bottom() + 1e-6:
                ts.append(t)

    unique_ts: list[float] = []
    for t in sorted(ts):
        if not unique_ts or abs(t - unique_ts[-1]) > 1e-6:
            unique_ts.append(t)

    if len(unique_ts) >= 2:
        t_min, t_max = unique_ts[0], unique_ts[-1]
        line_len = math.hypot(dx, dy)
        if (t_max - t_min) * line_len >= MIN_RIDGE_CM:
            return (
                QPointF(cx + t_min * dx, cy + t_min * dy),
                QPointF(cx + t_max * dx, cy + t_max * dy),
            )

    return center, center


def compute_roof_ridge_endpoints(
    polygon: QPolygonF, pos: QPointF
) -> tuple[QPointF, QPointF]:
    """Scene-frame endpoints of a HOUSE's roof ridge.

    The ridge runs along the polygon's dominant axis (aligned with its longest edge
    or bbox) through the center, clipped to the actual polygon boundary.

    Args:
        polygon: The house item's LOCAL ``polygon()`` (item coordinates).
        pos: The house item's scene ``pos()`` — the local-frame origin the
            returned scene-frame endpoints are offset by.

    Returns:
        ``(p1, p2)`` in scene coordinates, ready to feed a ``PolylineItem``
        with ``ObjectType.ROOF_RIDGE``.
    """
    direction, center = _dominant_direction_and_center(polygon)

    # Clip ridge line to actual polygon boundary (not just bbox)
    pts = intersect_line_polygon(polygon, center, direction)
    if pts is not None:
        p1 = QPointF(pos.x() + pts[0].x(), pos.y() + pts[0].y())
        p2 = QPointF(pos.x() + pts[1].x(), pos.y() + pts[1].y())
    else:
        # Fallback clipped strictly to bounding box segments
        bbox = polygon.boundingRect()
        bp1, bp2 = _clip_line_to_bbox(bbox, center, direction)
        p1 = QPointF(pos.x() + bp1.x(), pos.y() + bp1.y())
        p2 = QPointF(pos.x() + bp2.x(), pos.y() + bp2.y())

    return p1, p2
