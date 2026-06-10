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
    from PyQt6.QtGui import QPainterPath

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


def arc_to_painter_path(
    center: QPointF,
    radius: float,
    start_deg: float,
    span_deg: float,
) -> QPainterPath:
    """Build a ``QPainterPath`` for a circular arc from exact cubic-Bézier segments.

    ``QPainterPath.arcMoveTo`` / ``arcTo`` drift the *rendered* endpoints — their
    internal angle→point conversion lands a few mm past the analytic endpoint on a
    shallow, large-radius arc (issue #195). This builder instead places each
    Bézier segment's **anchor points exactly** on the analytic circle, so the
    rendered curve starts at ``start_deg`` and ends at ``start_deg + span_deg`` to
    full double precision and passes through ``ArcItem.start_point()`` /
    ``end_point()`` / ``midpoint()``.

    Angles use the same math convention as ``ArcItem``: degrees CCW from +X, with
    the point at angle θ being ``center + radius·(cos θ, sin θ)``. ``span_deg`` is
    signed (positive CCW, negative CW); the signed ``tan(Δ/4)`` control factor
    extends the handles in the correct sweep direction for either sign.
    """
    from PyQt6.QtGui import QPainterPath

    path = QPainterPath()
    cx, cy = center.x(), center.y()
    start_rad = math.radians(start_deg)
    span_rad = math.radians(span_deg)

    path.moveTo(cx + radius * math.cos(start_rad), cy + radius * math.sin(start_rad))
    if abs(span_rad) < 1e-12:
        return path

    # Split into ≤45° segments. Each segment's anchor points are exact on the
    # circle (so the arc's start/end are exact — the whole point of #195); the
    # cubic only approximates the *interior*, with max radial error ≈ O(θ⁶·r):
    # ~2.7e-4·r at 90°, but ~4e-6·r at 45° (sub-0.05 mm even at a 10 m radius).
    n_segments = max(1, math.ceil(abs(span_rad) / (math.pi / 4.0)))
    seg = span_rad / n_segments
    k = (4.0 / 3.0) * math.tan(seg / 4.0)

    phi = start_rad
    for _ in range(n_segments):
        phi_next = phi + seg
        cos0, sin0 = math.cos(phi), math.sin(phi)
        cos1, sin1 = math.cos(phi_next), math.sin(phi_next)
        # Anchor points lie exactly on the arc.
        p0x, p0y = cx + radius * cos0, cy + radius * sin0
        p3x, p3y = cx + radius * cos1, cy + radius * sin1
        # Control points run along the tangents (derivative of (cos φ, sin φ)).
        c1x, c1y = p0x + k * radius * (-sin0), p0y + k * radius * cos0
        c2x, c2y = p3x - k * radius * (-sin1), p3y - k * radius * cos1
        path.cubicTo(c1x, c1y, c2x, c2y, p3x, p3y)
        phi = phi_next

    return path


# ---------------------------------------------------------------------------
# Fillet / Chamfer corner geometry (Phase 13 Package B — US-B3)
# ---------------------------------------------------------------------------


def fillet_corner(
    p_prev: QPointF,
    p_corner: QPointF,
    p_next: QPointF,
    radius: float,
) -> tuple[QPointF, QPointF, QPointF, float, float] | None:
    """Compute a fillet arc tangent to two edges meeting at ``p_corner``.

    The corner is formed by the edges ``p_prev → p_corner`` and
    ``p_corner → p_next``. The fillet replaces the sharp corner with a
    circular arc of the given radius, tangent to both edges. The tangent
    points lie on the edges at distance ``radius / tan(α)`` from the
    corner, where ``2α`` is the interior angle.

    Args:
        p_prev: Previous vertex (start of incoming edge).
        p_corner: The corner vertex being filleted.
        p_next: Next vertex (end of outgoing edge).
        radius: Desired arc radius (must be positive).

    Returns:
        ``(tangent_in, tangent_out, arc_center, start_deg, span_deg)``
        where ``tangent_in`` lies on ``p_prev → p_corner``, ``tangent_out``
        lies on ``p_corner → p_next``, ``arc_center`` is the arc center
        on the bisector at distance ``radius / sin(α)``, and the angles
        follow the math convention used by ``ArcItem`` (CCW from +X,
        signed span). Span magnitude equals ``π - 2α``.

        Returns ``None`` if the radius is too large to fit between the
        corner and either neighbouring vertex, if the corner is
        degenerate (straight, doubled-back, or zero-length edge), or if
        ``radius <= 0``.
    """
    if radius <= 0:
        return None

    ax = p_prev.x() - p_corner.x()
    ay = p_prev.y() - p_corner.y()
    cx_ = p_next.x() - p_corner.x()
    cy_ = p_next.y() - p_corner.y()

    len_a = math.hypot(ax, ay)
    len_c = math.hypot(cx_, cy_)
    if len_a < PARALLEL_EPSILON or len_c < PARALLEL_EPSILON:
        return None

    u1x, u1y = ax / len_a, ay / len_a
    u2x, u2y = cx_ / len_c, cy_ / len_c

    cos_2a = u1x * u2x + u1y * u2y
    cos_2a = max(-1.0, min(1.0, cos_2a))
    if cos_2a > 1.0 - 1e-9 or cos_2a < -1.0 + 1e-9:
        return None

    two_alpha = math.acos(cos_2a)
    alpha = two_alpha / 2.0
    sin_a = math.sin(alpha)
    tan_a = math.tan(alpha)
    if sin_a < 1e-9 or tan_a < 1e-9:
        return None

    edge_offset = radius / tan_a
    if edge_offset > len_a + 1e-9 or edge_offset > len_c + 1e-9:
        return None

    tangent_in = QPointF(
        p_corner.x() + u1x * edge_offset,
        p_corner.y() + u1y * edge_offset,
    )
    tangent_out = QPointF(
        p_corner.x() + u2x * edge_offset,
        p_corner.y() + u2y * edge_offset,
    )

    bx_, by_ = u1x + u2x, u1y + u2y
    bl = math.hypot(bx_, by_)
    if bl < 1e-9:
        return None
    bx_ /= bl
    by_ /= bl

    center_dist = radius / sin_a
    center = QPointF(
        p_corner.x() + bx_ * center_dist,
        p_corner.y() + by_ * center_dist,
    )

    theta_in = math.atan2(tangent_in.y() - center.y(), tangent_in.x() - center.x())
    theta_out = math.atan2(tangent_out.y() - center.y(), tangent_out.x() - center.x())

    span = theta_out - theta_in
    while span > math.pi:
        span -= 2.0 * math.pi
    while span < -math.pi:
        span += 2.0 * math.pi

    return tangent_in, tangent_out, center, math.degrees(theta_in), math.degrees(span)


def chamfer_corner(
    p_prev: QPointF,
    p_corner: QPointF,
    p_next: QPointF,
    distance: float,
) -> tuple[QPointF, QPointF] | None:
    """Compute a chamfer (straight bevel) at ``p_corner``.

    The two cut points sit at ``distance`` along each adjacent edge from
    the corner. The corner is replaced by a straight segment connecting
    them.

    Args:
        p_prev: Previous vertex.
        p_corner: The corner vertex being chamfered.
        p_next: Next vertex.
        distance: Cut-back distance along each edge (must be positive).

    Returns:
        ``(cut_in, cut_out)`` where ``cut_in`` lies on
        ``p_prev → p_corner`` and ``cut_out`` lies on
        ``p_corner → p_next``. Returns ``None`` if ``distance`` exceeds
        either edge length, if an edge is zero-length, or if
        ``distance <= 0``.
    """
    if distance <= 0:
        return None

    ax = p_prev.x() - p_corner.x()
    ay = p_prev.y() - p_corner.y()
    cx_ = p_next.x() - p_corner.x()
    cy_ = p_next.y() - p_corner.y()

    len_a = math.hypot(ax, ay)
    len_c = math.hypot(cx_, cy_)
    if len_a < PARALLEL_EPSILON or len_c < PARALLEL_EPSILON:
        return None
    if distance > len_a + 1e-9 or distance > len_c + 1e-9:
        return None

    cut_in = QPointF(
        p_corner.x() + (ax / len_a) * distance,
        p_corner.y() + (ay / len_a) * distance,
    )
    cut_out = QPointF(
        p_corner.x() + (cx_ / len_c) * distance,
        p_corner.y() + (cy_ / len_c) * distance,
    )
    return cut_in, cut_out


# ---------------------------------------------------------------------------
# Mirror / reflection helpers (US-B4)
# ---------------------------------------------------------------------------


def reflect_point(p: QPointF, a: QPointF, b: QPointF) -> QPointF:
    """Reflect ``p`` across the infinite line through ``a`` and ``b``.

    Projects ``p`` onto the line to find the foot of the perpendicular,
    then mirrors ``p`` to the opposite side: ``2·foot - p``.

    The caller must guarantee ``a != b`` (a non-zero axis); a degenerate
    axis (``|b-a|`` below ``PARALLEL_EPSILON``) returns ``p`` unchanged.
    """
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    len_sq = dx * dx + dy * dy
    if len_sq < PARALLEL_EPSILON:
        return QPointF(p)
    t = ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / len_sq
    foot_x = a.x() + t * dx
    foot_y = a.y() + t * dy
    return QPointF(2.0 * foot_x - p.x(), 2.0 * foot_y - p.y())


def reflect_angle_deg(angle_deg: float, a: QPointF, b: QPointF) -> float:
    """Reflect an orientation ``angle_deg`` across the axis ``a → b``.

    A reflection across a line at direction angle ``φ`` maps an orientation
    ``θ`` to ``2φ - θ``. Result is normalised to ``[0, 360)``. Uses the same
    screen convention (degrees, clockwise-positive in Qt's y-down space) as
    ``RotationHandleMixin._apply_rotation`` / ``rotation_angle``.
    """
    phi = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
    return (2.0 * phi - angle_deg) % 360.0


def snap_point_to_axis_step(
    origin: QPointF, target: QPointF, step_deg: float = 45.0
) -> QPointF:
    """Snap the ``origin → target`` direction to the nearest multiple of ``step_deg``.

    Keeps the original distance from ``origin``; only the angle is quantised.
    Used to constrain a mirror axis to 0/45/90° while the user holds Shift.
    Returns ``target`` unchanged when it coincides with ``origin``.
    """
    dx = target.x() - origin.x()
    dy = target.y() - origin.y()
    dist = math.hypot(dx, dy)
    if dist < PARALLEL_EPSILON:
        return QPointF(target)
    angle = math.atan2(dy, dx)
    step_rad = math.radians(step_deg)
    snapped = round(angle / step_rad) * step_rad
    return QPointF(
        origin.x() + dist * math.cos(snapped),
        origin.y() + dist * math.sin(snapped),
    )
