"""Snap providers built on top of the legacy anchor system.

Wraps :func:`open_garden_planner.core.measure_snapper.get_anchor_points`
so existing geometry helpers are reused rather than duplicated.
"""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
from open_garden_planner.core.snap.provider import (
    SnapCandidate,
    SnapCandidateKind,
    SnapProvider,
)

_EDGE_TYPES: frozenset[AnchorType] = frozenset(
    {
        AnchorType.EDGE_TOP,
        AnchorType.EDGE_BOTTOM,
        AnchorType.EDGE_LEFT,
        AnchorType.EDGE_RIGHT,
    }
)


def _items_within(
    scene_pos: QPointF,
    items: Iterable[QGraphicsItem],
    threshold: float,
) -> Iterable[QGraphicsItem]:
    """Coarse pre-filter: discard items whose bounding rect is far away."""
    for item in items:
        if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
            continue
        brect = item.sceneBoundingRect()
        # Expand by threshold and check containment of scene_pos.
        if (
            brect.left() - threshold <= scene_pos.x() <= brect.right() + threshold
            and brect.top() - threshold <= scene_pos.y() <= brect.bottom() + threshold
        ):
            yield item


class EndpointSnapProvider(SnapProvider):
    """Snap to vertices / endpoints (``AnchorType.ENDPOINT`` and ``CORNER``)."""

    kind = SnapCandidateKind.ENDPOINT
    priority = 10

    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
    ) -> Iterable[SnapCandidate]:
        for item in _items_within(scene_pos, items, threshold):
            for anchor in get_anchor_points(item):
                if anchor.anchor_type in (AnchorType.ENDPOINT, AnchorType.CORNER):
                    yield SnapCandidate(
                        point=anchor.point,
                        kind=SnapCandidateKind.ENDPOINT,
                        priority=self.priority,
                        item=item,
                    )


class CenterSnapProvider(SnapProvider):
    """Snap to item centers."""

    kind = SnapCandidateKind.CENTER
    priority = 20

    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
    ) -> Iterable[SnapCandidate]:
        for item in _items_within(scene_pos, items, threshold):
            for anchor in get_anchor_points(item):
                if anchor.anchor_type == AnchorType.CENTER:
                    yield SnapCandidate(
                        point=anchor.point,
                        kind=SnapCandidateKind.CENTER,
                        priority=self.priority,
                        item=item,
                    )


class EdgeCardinalSnapProvider(SnapProvider):
    """Snap to N/E/S/W cardinal points on rect/circle/ellipse items."""

    kind = SnapCandidateKind.EDGE
    priority = 40

    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
    ) -> Iterable[SnapCandidate]:
        for item in _items_within(scene_pos, items, threshold):
            for anchor in get_anchor_points(item):
                if anchor.anchor_type in _EDGE_TYPES:
                    yield SnapCandidate(
                        point=anchor.point,
                        kind=SnapCandidateKind.EDGE,
                        priority=self.priority,
                        item=item,
                    )
