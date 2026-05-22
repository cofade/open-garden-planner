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


# ---------------------------------------------------------------------------
# Arc geometry (Phase 13 Package B — US-B2)
# ---------------------------------------------------------------------------

# Tolerance below which three points are treated as collinear (no unique
# circle). Expressed as the absolute value of twice the signed triangle
# area (cm² × 2). A sagitta < 0.1 cm on a 100 cm chord — visually flat —
# yields ``abs(d) ≈ 20`` and is treated as a curve; a sagitta < 0.005 cm
# yields ``abs(d) ≈ 1`` and is treated as a line, catching click-jitter
# without rejecting genuinely curved input.
COLLINEAR_TOLERANCE: float = 1.0


def arc_from_three_points(
    p1: QPointF,
    p2: QPointF,
    p3: QPointF,
) -> tuple[QPointF, float, float, float] | None:
    """Compute the unique circular arc through three points.

    The arc passes through ``p1`` (start), ``p2`` (through-point), and
    ``p3`` (end). The through-point determines which of the two possible
    arc sweeps between the endpoints is chosen.

    Args:
        p1: Start point of the arc.
        p2: Through-point lying on the arc between p1 and p3.
        p3: End point of the arc.

    Returns:
        ``(center, radius, start_deg, span_deg)`` where:
            - ``center`` is the QPointF arc center,
            - ``radius`` is the arc radius (always positive),
            - ``start_deg`` is the start angle in degrees, CCW from +X,
              measured from the center to ``p1``,
            - ``span_deg`` is the signed sweep in degrees (positive CCW,
              negative CW); always non-zero, magnitude in ``(0, 360)``.

        Returns ``None`` if the three points are collinear (no unique
        circle exists), letting callers fall back to a polyline.
    """
    ax, ay = p1.x(), p1.y()
    bx, by = p2.x(), p2.y()
    cx, cy = p3.x(), p3.y()

    # Twice the signed area of the triangle (p1, p2, p3). Zero iff the
    # points are collinear; sign indicates winding (positive = CCW).
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < COLLINEAR_TOLERANCE:
        return None

    a_sq = ax * ax + ay * ay
    b_sq = bx * bx + by * by
    c_sq = cx * cx + cy * cy

    center_x = (a_sq * (by - cy) + b_sq * (cy - ay) + c_sq * (ay - by)) / d
    center_y = (a_sq * (cx - bx) + b_sq * (ax - cx) + c_sq * (bx - ax)) / d
    center = QPointF(center_x, center_y)

    radius = math.hypot(ax - center_x, ay - center_y)

    # Angles from the center to each input point.
    a1 = math.atan2(ay - center_y, ax - center_x)
    a2 = math.atan2(by - center_y, bx - center_x)
    a3 = math.atan2(cy - center_y, cx - center_x)

    # Pick the sweep direction so the arc passes through the
    # through-point. d > 0 means p1 -> p2 -> p3 winds CCW around the
    # center (because we constructed d from the same vectors); d < 0
    # means CW.
    if d > 0:
        # CCW from a1 to a3.
        span = a3 - a1
        if span <= 0:
            span += 2.0 * math.pi
    else:
        # CW from a1 to a3 — span is negative.
        span = a3 - a1
        if span >= 0:
            span -= 2.0 * math.pi

    start_deg = math.degrees(a1)
    span_deg = math.degrees(span)

    # Sanity: the through-point really should lie on the arc, but
    # numerical noise can push it just outside. We don't reject — the
    # arc still passes within micro-cm of p2 in practice. The unit
    # tests verify this.
    _ = a2  # noqa: F841

    return center, radius, start_deg, span_deg
