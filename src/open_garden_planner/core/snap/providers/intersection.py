"""Intersection snap provider.

Pairs every segment near the cursor with every other and emits the
intersection point.  Pairs are capped to bound worst-case latency on
dense scenes.
"""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.snap.geometry import item_edges, segment_intersection
from open_garden_planner.core.snap.provider import (
    SnapCandidate,
    SnapCandidateKind,
    SnapProvider,
)

# Cap the number of segments we feed into the O(n*m) intersection loop.
# 60 segments => up to 3600 pairwise checks - still well below 1ms.
MAX_SEGMENTS_PER_QUERY = 60


class IntersectionSnapProvider(SnapProvider):
    """Snap to intersections of straight edges."""

    kind = SnapCandidateKind.INTERSECTION
    priority = 15

    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
    ) -> Iterable[SnapCandidate]:
        segments: list[tuple[QLineF, QGraphicsItem]] = []
        for item in items:
            if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            brect = item.sceneBoundingRect()
            # Expand by threshold; an edge may pass through the query area
            # even if its bounding rect just misses it.
            if (
                brect.right() + threshold < scene_pos.x() - threshold
                or brect.left() - threshold > scene_pos.x() + threshold
                or brect.bottom() + threshold < scene_pos.y() - threshold
                or brect.top() - threshold > scene_pos.y() + threshold
            ):
                continue
            for edge in item_edges(item):
                segments.append((edge, item))
                if len(segments) >= MAX_SEGMENTS_PER_QUERY:
                    break
            if len(segments) >= MAX_SEGMENTS_PER_QUERY:
                break

        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                edge_a, item_a = segments[i]
                edge_b, item_b = segments[j]
                if item_a is item_b:
                    # Skip self-intersections of the same item (would yield
                    # noise for polygons whose own edges meet at vertices).
                    continue
                hit = segment_intersection(edge_a, edge_b)
                if hit is None:
                    continue
                dx = hit.x() - scene_pos.x()
                dy = hit.y() - scene_pos.y()
                if dx * dx + dy * dy > threshold * threshold:
                    continue
                yield SnapCandidate(
                    point=QPointF(hit),
                    kind=SnapCandidateKind.INTERSECTION,
                    priority=self.priority,
                    item=item_a,
                )
