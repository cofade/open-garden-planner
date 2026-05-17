"""Midpoint snap provider.

Yields the midpoint of every straight edge from items near the cursor.
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
    """Snap to the midpoint of any straight edge."""

    kind = SnapCandidateKind.MIDPOINT
    priority = 30

    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
    ) -> Iterable[SnapCandidate]:
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
