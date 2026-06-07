"""Perpendicular snap provider (Phase 13 Package B — US-B5).

Yields the foot of perpendicular from the active drawing tool's
``reference_point`` (typically the previous click of a multi-click
draw operation) onto a nearby edge or curve. Active only when a
reference point is supplied — without one the concept is undefined
and the provider yields nothing.

For straight edges the foot is the analytic perpendicular projection
of ``reference_point`` onto the line through the segment; the
candidate is emitted only when the foot lies *within* the segment.
For circles and arcs the perpendicular point is along the radial
from the centre through ``reference_point`` — i.e. the same point a
"nearest from reference" would produce — because the tangent to a
circle is perpendicular to its radius.

Priority 25 — beats midpoint (30), nearest (45), and edge-cardinal
(40); endpoints (10) and intersections (15) still win when they
coincide with the perpendicular foot.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.snap.geometry import item_edges
from open_garden_planner.core.snap.provider import (
    SnapCandidate,
    SnapCandidateKind,
    SnapProvider,
)


class PerpendicularSnapProvider(SnapProvider):
    """Snap to the foot of perpendicular from the tool's last_point."""

    kind = SnapCandidateKind.PERPENDICULAR
    priority = 25

    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
        reference_point: QPointF | None = None,
    ) -> Iterable[SnapCandidate]:
        if reference_point is None:
            return  # perpendicular has no meaning without a draw-from anchor
        from open_garden_planner.ui.canvas.items import (
            ArcItem,
            CircleItem,
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

            # Each foot is paired with the source edge index it projected
            # onto, or None for circle/arc radial feet (no straight edge).
            feet: list[tuple[int | None, QPointF]] = []
            if isinstance(item, ArcItem):
                foot = _perp_on_arc(item, reference_point)
                if foot is not None:
                    feet.append((None, foot))
            elif isinstance(item, (CircleItem, ConstructionCircleItem)):
                foot = _perp_on_circle(item, reference_point)
                if foot is not None:
                    feet.append((None, foot))
            else:
                # One perpendicular foot per straight edge — lets the
                # cursor-distance filter pick the edge the user meant.
                feet.extend(_perp_feet_on_straight_edges(item, reference_point))

            for edge_index, foot in feet:
                dx = foot.x() - scene_pos.x()
                dy = foot.y() - scene_pos.y()
                if dx * dx + dy * dy > thr_sq:
                    continue
                yield SnapCandidate(
                    point=foot,
                    kind=SnapCandidateKind.PERPENDICULAR,
                    priority=self.priority,
                    item=item,
                    source_edge_index=edge_index,
                )


# ---------------------------------------------------------------------------
# Per-shape perpendicular foot helpers
# ---------------------------------------------------------------------------


def _foot_on_segment_strict(
    p: QPointF, line: QLineF
) -> QPointF | None:
    """Foot of perpendicular from ``p`` onto a segment, or ``None`` if outside.

    Unlike ``nearest._project_on_segment`` (which clamps to [p1, p2]),
    perpendicular returns ``None`` when the foot falls outside the
    segment — that case isn't actually a perpendicular drop and the
    user expects no snap.
    """
    x1, y1 = line.x1(), line.y1()
    x2, y2 = line.x2(), line.y2()
    dx = x2 - x1
    dy = y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return None
    t = ((p.x() - x1) * dx + (p.y() - y1) * dy) / len_sq
    if t < 0.0 or t > 1.0:
        return None
    return QPointF(x1 + t * dx, y1 + t * dy)


def _perp_feet_on_straight_edges(
    item: QGraphicsItem, ref: QPointF
) -> list[tuple[int, QPointF]]:
    """All valid perpendicular feet from ``ref`` to each straight edge.

    Returns ``(edge_index, foot)`` pairs so the caller can record which
    edge each candidate belongs to. The caller filters by cursor distance
    so the user picks the edge by hover. Edges where the foot falls outside
    the segment are omitted entirely.
    """
    feet: list[tuple[int, QPointF]] = []
    for edge_index, edge in enumerate(item_edges(item)):
        foot = _foot_on_segment_strict(ref, edge)
        if foot is not None:
            feet.append((edge_index, foot))
    return feet


def _perp_on_circle(item: QGraphicsItem, ref: QPointF) -> QPointF | None:
    """Perpendicular point on circle = radial projection of ``ref``."""
    rect = item.rect()  # type: ignore[attr-defined]
    local_center = QPointF(
        rect.x() + rect.width() / 2.0,
        rect.y() + rect.height() / 2.0,
    )
    radius = rect.width() / 2.0
    if radius <= 0:
        return None
    cx_scene = item.mapToScene(local_center)
    dx = ref.x() - cx_scene.x()
    dy = ref.y() - cx_scene.y()
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        # ref sits exactly at centre — no unique perpendicular direction.
        return None
    return QPointF(
        cx_scene.x() + dx * radius / dist,
        cx_scene.y() + dy * radius / dist,
    )


def _perp_on_arc(item: QGraphicsItem, ref: QPointF) -> QPointF | None:
    """Perpendicular point on an arc: radial projection clamped to sweep."""
    from open_garden_planner.ui.canvas.items import ArcItem

    assert isinstance(item, ArcItem)
    center = item.center
    radius = item.radius
    if radius <= 0:
        return None
    dx = ref.x() - center.x()
    dy = ref.y() - center.y()
    if dx == 0 and dy == 0:
        return None

    angle_deg = math.degrees(math.atan2(dy, dx))
    start = item.start_deg
    span = item.span_deg
    rel = ((angle_deg - start) % 360 + 360) % 360
    if span >= 0:
        in_sweep = rel <= span + 1e-9
    else:
        rel_neg = (360 - rel) % 360
        in_sweep = rel_neg <= -span + 1e-9

    if not in_sweep:
        return None  # perpendicular foot would lie outside the arc itself

    dist = math.hypot(dx, dy)
    return QPointF(
        center.x() + dx * radius / dist,
        center.y() + dy * radius / dist,
    )
