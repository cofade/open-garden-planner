"""Pure geometry helpers for CAD trim/extend operations.

All functions operate on PyQt6 QPointF values. No Qt widgets are imported.
Callers are responsible for converting item-local coordinates to scene
coordinates before calling these functions.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

if TYPE_CHECKING:
    pass

HOVER_TOLERANCE: float = 10.0
PARALLEL_EPSILON: float = 1e-9
DEDUP_EPSILON: float = 1e-4
ENDPOINT_EPSILON: float = 1e-6


def point_to_segment_distance(
    pt: QPointF,
    p1: QPointF,
    p2: QPointF,
) -> tuple[float, float]:
    """Return (distance, t) where t∈[0,1] is the projection parameter along p1→p2.

    t=0 means p1 is closest, t=1 means p2 is closest.
    """
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    len_sq = dx * dx + dy * dy
    if len_sq < PARALLEL_EPSILON:
        dist = math.hypot(pt.x() - p1.x(), pt.y() - p1.y())
        return dist, 0.0
    t = ((pt.x() - p1.x()) * dx + (pt.y() - p1.y()) * dy) / len_sq
    t = max(0.0, min(1.0, t))
    proj_x = p1.x() + t * dx
    proj_y = p1.y() + t * dy
    dist = math.hypot(pt.x() - proj_x, pt.y() - proj_y)
    return dist, t


def segment_segment_intersection(
    a1: QPointF,
    a2: QPointF,
    b1: QPointF,
    b2: QPointF,
) -> tuple[float, float] | None:
    """Parametric intersection of segment A (a1→a2) and segment B (b1→b2).

    Returns (t_a, t_b) where both are in [0,1], or None if no intersection
    (parallel, collinear, or outside segment range).
    """
    da_x = a2.x() - a1.x()
    da_y = a2.y() - a1.y()
    db_x = b2.x() - b1.x()
    db_y = b2.y() - b1.y()

    denom = da_x * db_y - da_y * db_x
    if abs(denom) < PARALLEL_EPSILON:
        return None

    dp_x = b1.x() - a1.x()
    dp_y = b1.y() - a1.y()

    t_a = (dp_x * db_y - dp_y * db_x) / denom
    t_b = (dp_x * da_y - dp_y * da_x) / denom

    if 0.0 <= t_a <= 1.0 and 0.0 <= t_b <= 1.0:
        return t_a, t_b
    return None


def collect_intersections_on_segment(
    seg_p1: QPointF,
    seg_p2: QPointF,
    other_segs: list[tuple[QPointF, QPointF]],
) -> list[float]:
    """Return sorted t-values in (ε, 1-ε) where other_segs cross seg_p1→seg_p2.

    Endpoint touches (t≈0 or t≈1) are excluded. Near-duplicate t-values
    (within DEDUP_EPSILON) are collapsed to one entry.
    """
    raw: list[float] = []
    for b1, b2 in other_segs:
        result = segment_segment_intersection(seg_p1, seg_p2, b1, b2)
        if result is not None:
            t_a, _ = result
            if ENDPOINT_EPSILON < t_a < 1.0 - ENDPOINT_EPSILON:
                raw.append(t_a)

    raw.sort()

    deduped: list[float] = []
    for t in raw:
        if not deduped or t - deduped[-1] > DEDUP_EPSILON:
            deduped.append(t)
    return deduped


def interpolate(p1: QPointF, p2: QPointF, t: float) -> QPointF:
    """Linear interpolation: p1 + t*(p2-p1)."""
    return QPointF(
        p1.x() + t * (p2.x() - p1.x()),
        p1.y() + t * (p2.y() - p1.y()),
    )


def polyline_to_scene_segments(
    item: object,
) -> list[tuple[QPointF, QPointF]]:
    """Convert a PolylineItem's local points to scene-coordinate segment pairs."""
    pts: list[QPointF] = item.points  # type: ignore[attr-defined]
    result = []
    for i in range(len(pts) - 1):
        p1 = item.mapToScene(pts[i])  # type: ignore[attr-defined]
        p2 = item.mapToScene(pts[i + 1])  # type: ignore[attr-defined]
        result.append((p1, p2))
    return result


def polygon_to_scene_segments(
    item: object,
) -> list[tuple[QPointF, QPointF]]:
    """Convert a PolygonItem's vertices to scene-coordinate segment pairs (closed)."""
    poly = item.polygon()  # type: ignore[attr-defined]
    n = poly.count()
    result = []
    for i in range(n):
        p1 = item.mapToScene(poly.at(i))  # type: ignore[attr-defined]
        p2 = item.mapToScene(poly.at((i + 1) % n))  # type: ignore[attr-defined]
        result.append((p1, p2))
    return result


def rectangle_to_scene_segments(
    item: object,
) -> list[tuple[QPointF, QPointF]]:
    """Convert a RectangleItem's four edges to scene-coordinate segment pairs.

    Vertex order: top-left → top-right → bottom-right → bottom-left (closed).
    """
    rect = item.rect()  # type: ignore[attr-defined]
    corners_local = [
        QPointF(rect.left(), rect.top()),
        QPointF(rect.right(), rect.top()),
        QPointF(rect.right(), rect.bottom()),
        QPointF(rect.left(), rect.bottom()),
    ]
    result = []
    n = len(corners_local)
    for i in range(n):
        p1 = item.mapToScene(corners_local[i])  # type: ignore[attr-defined]
        p2 = item.mapToScene(corners_local[(i + 1) % n])  # type: ignore[attr-defined]
        result.append((p1, p2))
    return result
