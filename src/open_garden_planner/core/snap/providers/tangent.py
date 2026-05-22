"""Tangent snap provider (Phase 13 Package B — US-B6).

Yields tangent points on circles and arcs *from* the active drawing
tool's ``reference_point``. A tangent line from an external point ``R``
to a circle ``(C, r)`` touches the circle at one of two points where
the radius ``CT`` is perpendicular to ``RT``. Both candidates are
emitted; the cursor's hover distance picks which side the user meant.

For arcs the same geometry applies, with the extra constraint that a
tangent point must fall within the arc's angular sweep — out-of-sweep
candidates are dropped.

If ``reference_point`` is inside the circle (or exactly at the centre)
no tangent exists and the provider yields nothing for that item.

Priority 26 — sits just below perpendicular (25) so that, in the rare
case a perpendicular foot and a tangent point are co-located, the
perpendicular wins (it is the more general construct). Endpoints,
intersections, and centres still dominate.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.snap.provider import (
    SnapCandidate,
    SnapCandidateKind,
    SnapProvider,
)


class TangentSnapProvider(SnapProvider):
    """Snap to a tangent point on a circle or arc from the tool's anchor."""

    kind = SnapCandidateKind.TANGENT
    priority = 26

    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
        reference_point: QPointF | None = None,
    ) -> Iterable[SnapCandidate]:
        if reference_point is None:
            return
        from open_garden_planner.ui.canvas.items import ArcItem, CircleItem
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

            tangents: list[QPointF]
            if isinstance(item, ArcItem):
                tangents = _tangents_on_arc(item, reference_point)
            elif isinstance(item, (CircleItem, ConstructionCircleItem)):
                tangents = _tangents_on_circle(item, reference_point)
            else:
                continue

            for t in tangents:
                dx = t.x() - scene_pos.x()
                dy = t.y() - scene_pos.y()
                if dx * dx + dy * dy > thr_sq:
                    continue
                yield SnapCandidate(
                    point=t,
                    kind=SnapCandidateKind.TANGENT,
                    priority=self.priority,
                    item=item,
                )


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _circle_center_radius(item: QGraphicsItem) -> tuple[QPointF, float] | None:
    """Return (scene-coord centre, radius) for any circular item."""
    rect = item.rect()  # type: ignore[attr-defined]
    radius = rect.width() / 2.0
    if radius <= 0:
        return None
    local_center = QPointF(
        rect.x() + rect.width() / 2.0,
        rect.y() + rect.height() / 2.0,
    )
    return item.mapToScene(local_center), radius


def _tangents_on_circle(
    item: QGraphicsItem, ref: QPointF
) -> list[QPointF]:
    """The two tangent points from ``ref`` onto a circle.

    Returns ``[]`` when ``ref`` is inside the circle (no tangent exists)
    or exactly at the centre (no unique direction).
    """
    cr = _circle_center_radius(item)
    if cr is None:
        return []
    center, radius = cr
    dx = ref.x() - center.x()
    dy = ref.y() - center.y()
    d_sq = dx * dx + dy * dy
    r_sq = radius * radius
    if d_sq < r_sq - 1e-9:
        return []  # ref strictly inside the circle
    if d_sq < 1e-12:
        return []  # ref at centre

    # Angle from the centre to the reference, plus the half-angle the
    # tangent points subtend off that direction.
    theta_cr = math.atan2(dy, dx)
    # Clamp the acos argument to handle ref-on-circle (d == r).
    arg = radius / math.sqrt(d_sq)
    arg = max(-1.0, min(1.0, arg))
    alpha = math.acos(arg)

    out: list[QPointF] = []
    for sign in (+1.0, -1.0):
        ang = theta_cr + sign * alpha
        out.append(
            QPointF(
                center.x() + radius * math.cos(ang),
                center.y() + radius * math.sin(ang),
            )
        )
    # When ref sits exactly on the circle the two solutions collapse;
    # de-duplicate so we don't emit twice.
    if len(out) == 2:
        a, b = out
        if abs(a.x() - b.x()) < 1e-9 and abs(a.y() - b.y()) < 1e-9:
            return [a]
    return out


def _tangents_on_arc(item: QGraphicsItem, ref: QPointF) -> list[QPointF]:
    """Tangent points on the underlying circle, filtered to the arc's sweep."""
    from open_garden_planner.ui.canvas.items import ArcItem

    assert isinstance(item, ArcItem)
    cr = _circle_center_radius(_ArcCircleProxy(item))
    if cr is None:
        return []
    center, radius = cr
    pts = _tangents_on_circle(_ArcCircleProxy(item), ref)
    if not pts:
        return []
    start = item.start_deg
    span = item.span_deg
    out: list[QPointF] = []
    for p in pts:
        ang = math.degrees(math.atan2(p.y() - center.y(), p.x() - center.x()))
        rel = ((ang - start) % 360 + 360) % 360
        if span >= 0:
            in_sweep = rel <= span + 1e-6
        else:
            rel_neg = (360 - rel) % 360
            in_sweep = rel_neg <= -span + 1e-6
        if in_sweep:
            out.append(p)
    return out


class _ArcCircleProxy:
    """Thin shim that lets ``_circle_center_radius`` and
    ``_tangents_on_circle`` work against an ``ArcItem`` by exposing the
    underlying circle's ``rect()`` and ``mapToScene``.

    Avoids duplicating the tangent math in a second function.
    """

    def __init__(self, arc: object) -> None:
        self._arc = arc

    def rect(self) -> object:
        from PyQt6.QtCore import QRectF

        center = self._arc._center  # type: ignore[attr-defined]
        radius = self._arc.radius  # type: ignore[attr-defined]
        return QRectF(
            center.x() - radius,
            center.y() - radius,
            2 * radius,
            2 * radius,
        )

    def mapToScene(self, point: QPointF) -> QPointF:
        return self._arc.mapToScene(point)  # type: ignore[attr-defined]

    def flags(self) -> object:  # pragma: no cover — never queried here
        return self._arc.flags()  # type: ignore[attr-defined]
