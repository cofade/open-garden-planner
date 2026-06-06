"""Nearest-point snap provider (Phase 13 Package B — US-B4).

Yields the closest point on the geometric outline of any selectable
item near the cursor. Acts as a fallback below endpoint, center,
intersection, midpoint, and edge-cardinal — useful for picking
anywhere along an edge without manually positioning to an exact
midpoint or vertex.

Projection strategy is dispatched per item type:

- Rectangles / polygons / polylines / construction lines: project onto
  the closest of the item's straight edges (linear projection with
  parameter clamping).
- Circles / construction circles: analytic projection onto the
  circumference (closest point on a circle from an external point).
- Arcs: project onto the underlying circle, then clamp the angle to
  the arc's sweep — if the projection falls outside the sweep, the
  candidate is the nearer arc endpoint instead.
- Bezier curves and other ``QGraphicsPathItem`` subclasses: uniformly
  sample ``QPainterPath.pointAtPercent`` and refine around the best
  bucket to get sub-cm precision on typical 100-cm curves.

Priority is 45 — below endpoint (10), intersection (15), center (20),
midpoint (30), and edge-cardinal (40), so any "special" snap wins. The
nearest point is the safety net.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from open_garden_planner.core.snap.geometry import item_edges
from open_garden_planner.core.snap.provider import (
    SnapCandidate,
    SnapCandidateKind,
    SnapProvider,
)

# QPainterPath sampling resolution for curved items.
_COARSE_SAMPLES = 64
_REFINE_SAMPLES = 16


class NearestSnapProvider(SnapProvider):
    """Snap to the nearest point on the outline of any visible item."""

    kind = SnapCandidateKind.NEAREST
    priority = 45

    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
        reference_point: QPointF | None = None,  # noqa: ARG002
    ) -> Iterable[SnapCandidate]:
        # Local imports to avoid a circular dependency at module load.
        from open_garden_planner.ui.canvas.items import (
            ArcItem,
            CircleItem,
            EllipseItem,
        )
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
        )

        thr_sq = threshold * threshold
        for item in items:
            if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            brect = item.sceneBoundingRect()
            if not (
                brect.left() - threshold <= scene_pos.x() <= brect.right() + threshold
                and brect.top() - threshold <= scene_pos.y() <= brect.bottom() + threshold
            ):
                continue

            nearest: QPointF | None = None
            # Set only when the projection lands on a specific straight
            # edge; circle/arc/path projections leave it None.
            edge_index: int | None = None
            if isinstance(item, ArcItem):
                nearest = _nearest_on_arc(item, scene_pos)
            elif isinstance(item, (CircleItem, ConstructionCircleItem)):
                nearest = _nearest_on_circle(item, scene_pos)
            elif isinstance(item, EllipseItem):
                # Sample via the underlying QPainterPath (an ellipse).
                nearest = _nearest_on_path_item(item, scene_pos)
            else:
                # Try straight-edge projection first (cheap and exact);
                # if that yields nothing, fall back to path sampling so
                # bezier curves work without an explicit branch.
                edge_index, nearest = _nearest_on_straight_edges(item, scene_pos)
                if nearest is None and isinstance(item, QGraphicsPathItem):
                    nearest = _nearest_on_path_item(item, scene_pos)

            if nearest is None:
                continue
            dx = nearest.x() - scene_pos.x()
            dy = nearest.y() - scene_pos.y()
            if dx * dx + dy * dy > thr_sq:
                continue
            yield SnapCandidate(
                point=nearest,
                kind=SnapCandidateKind.NEAREST,
                priority=self.priority,
                item=item,
                source_edge_index=edge_index,
            )


# ---------------------------------------------------------------------------
# Per-shape projection helpers
# ---------------------------------------------------------------------------


def _project_on_segment(p: QPointF, line: QLineF) -> QPointF:
    """Foot of perpendicular from ``p`` onto the segment, clamped to [p1, p2]."""
    x1, y1 = line.x1(), line.y1()
    x2, y2 = line.x2(), line.y2()
    dx = x2 - x1
    dy = y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return QPointF(x1, y1)
    t = ((p.x() - x1) * dx + (p.y() - y1) * dy) / len_sq
    t = max(0.0, min(1.0, t))
    return QPointF(x1 + t * dx, y1 + t * dy)


def _nearest_on_straight_edges(
    item: QGraphicsItem, scene_pos: QPointF
) -> tuple[int | None, QPointF | None]:
    """Closest point on any straight edge yielded by item_edges.

    Returns ``(edge_index, point)``; ``(None, None)`` when the item has no
    straight edges. ``edge_index`` identifies which edge won so callers can
    build an edge-anchored constraint.
    """
    best: QPointF | None = None
    best_index: int | None = None
    best_dsq = float("inf")
    for edge_index, edge in enumerate(item_edges(item)):
        pt = _project_on_segment(scene_pos, edge)
        dx = pt.x() - scene_pos.x()
        dy = pt.y() - scene_pos.y()
        dsq = dx * dx + dy * dy
        if dsq < best_dsq:
            best_dsq = dsq
            best = pt
            best_index = edge_index
    return best_index, best


def _nearest_on_circle(item: QGraphicsItem, scene_pos: QPointF) -> QPointF | None:
    """Closest point on a circle's circumference, in scene coordinates."""
    # CircleItem stores center via a "center" property in some forms; both
    # subclasses use an underlying QGraphicsEllipseItem rect.
    rect = item.rect()  # type: ignore[attr-defined]
    local_center = QPointF(
        rect.x() + rect.width() / 2.0,
        rect.y() + rect.height() / 2.0,
    )
    radius = rect.width() / 2.0
    if radius <= 0:
        return None
    cx_scene = item.mapToScene(local_center)
    dx = scene_pos.x() - cx_scene.x()
    dy = scene_pos.y() - cx_scene.y()
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        # Cursor sits exactly at center — return any point on the circle.
        return QPointF(cx_scene.x() + radius, cx_scene.y())
    return QPointF(
        cx_scene.x() + dx * radius / dist,
        cx_scene.y() + dy * radius / dist,
    )


def _nearest_on_arc(item: QGraphicsItem, scene_pos: QPointF) -> QPointF | None:
    """Closest point on an arc.

    Projects onto the underlying circle, then constrains to the arc's
    angular sweep. If the projection falls outside the sweep, returns
    the nearer arc endpoint.
    """
    from open_garden_planner.ui.canvas.items import ArcItem

    assert isinstance(item, ArcItem)
    center = item.center  # scene coords
    radius = item.radius
    if radius <= 0:
        return None
    dx = scene_pos.x() - center.x()
    dy = scene_pos.y() - center.y()
    if dx == 0 and dy == 0:
        return None  # ambiguous; let other providers handle it

    # ArcItem stores math-convention angles (CCW from +X with Y-up). The
    # canvas applies a Y-flip in the view, but the *scene-coord* y is
    # still measured downward (Qt's default), so the math-convention
    # angle of a scene-coord point uses ``atan2(y, x)`` directly because
    # ArcItem.start_point / midpoint / end_point follow the same
    # convention (see arc_item.py).
    angle_deg = math.degrees(math.atan2(dy, dx))
    start = item.start_deg
    span = item.span_deg

    # Normalize: rotate so the arc begins at 0, then check 0..span.
    rel = ((angle_deg - start) % 360 + 360) % 360
    # span is signed (CCW positive, CW negative); convert to an unsigned
    # forward sweep starting at start_deg.
    if span >= 0:
        in_sweep = rel <= span + 1e-9
    else:
        rel_neg = ((360 - rel) % 360)  # equivalent CW-relative angle
        in_sweep = rel_neg <= -span + 1e-9

    if in_sweep:
        dist = math.hypot(dx, dy)
        return QPointF(
            center.x() + dx * radius / dist,
            center.y() + dy * radius / dist,
        )

    # Outside sweep — pick the closer endpoint.
    p_start = item.start_point()
    p_end = item.end_point()
    d_start = math.hypot(p_start.x() - scene_pos.x(), p_start.y() - scene_pos.y())
    d_end = math.hypot(p_end.x() - scene_pos.x(), p_end.y() - scene_pos.y())
    return p_start if d_start <= d_end else p_end


def _nearest_on_path_item(
    item: QGraphicsItem, scene_pos: QPointF
) -> QPointF | None:
    """Sample a ``QGraphicsPathItem``'s path and refine around the best bucket.

    Uses ``QPainterPath.pointAtPercent`` for sampling. Coarse pass at
    ``_COARSE_SAMPLES`` divisions, then a refine pass at
    ``_REFINE_SAMPLES`` divisions inside the closest bucket.
    """
    if not hasattr(item, "path"):
        return None
    path: QPainterPath = item.path()
    if path.isEmpty():
        return None

    def _sample(t: float) -> QPointF:
        local = path.pointAtPercent(t)
        return item.mapToScene(local)

    # Coarse sweep.
    best_t = 0.0
    best_pt: QPointF | None = None
    best_dsq = float("inf")
    for i in range(_COARSE_SAMPLES + 1):
        t = i / _COARSE_SAMPLES
        pt = _sample(t)
        dx = pt.x() - scene_pos.x()
        dy = pt.y() - scene_pos.y()
        dsq = dx * dx + dy * dy
        if dsq < best_dsq:
            best_dsq = dsq
            best_t = t
            best_pt = pt

    # Refine inside [best_t - step, best_t + step].
    step = 1.0 / _COARSE_SAMPLES
    lo = max(0.0, best_t - step)
    hi = min(1.0, best_t + step)
    for i in range(_REFINE_SAMPLES + 1):
        t = lo + (hi - lo) * (i / _REFINE_SAMPLES)
        pt = _sample(t)
        dx = pt.x() - scene_pos.x()
        dy = pt.y() - scene_pos.y()
        dsq = dx * dx + dy * dy
        if dsq < best_dsq:
            best_dsq = dsq
            best_pt = pt
    return best_pt
