"""Midpoint snap provider.

Yields the midpoint of every straight edge from items near the cursor.
Also yields the angular midpoint of any ``ArcItem`` (Phase 13 B2): the
arc has no straight edges, but its midpoint is the CAD-conventional snap
point for centering symmetric constructions.
"""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.snap.geometry import item_edges
from open_garden_planner.core.snap.provider import (
    SnapCandidate,
    SnapCandidateKind,
    SnapProvider,
)


class MidpointSnapProvider(SnapProvider):
    """Snap to the midpoint of any straight edge or arc."""

    kind = SnapCandidateKind.MIDPOINT
    priority = 30

    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
        reference_point: QPointF | None = None,  # noqa: ARG002
    ) -> Iterable[SnapCandidate]:
        # Local import to avoid a circular dependency at module import.
        from open_garden_planner.ui.canvas.items import ArcItem

        for item in items:
            if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            brect = item.sceneBoundingRect()
            if not (
                brect.left() - threshold <= scene_pos.x() <= brect.right() + threshold
                and brect.top() - threshold
                <= scene_pos.y()
                <= brect.bottom() + threshold
            ):
                continue
            if isinstance(item, ArcItem):
                yield SnapCandidate(
                    point=item.midpoint(),
                    kind=SnapCandidateKind.MIDPOINT,
                    priority=self.priority,
                    item=item,
                )
                continue
            for edge in item_edges(item):
                mid = QPointF(
                    (edge.x1() + edge.x2()) / 2.0,
                    (edge.y1() + edge.y2()) / 2.0,
                )
                yield SnapCandidate(
                    point=mid,
                    kind=SnapCandidateKind.MIDPOINT,
                    priority=self.priority,
                    item=item,
                )
