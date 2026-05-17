"""Click-time point snapper.

Glues together the spatial index and the provider registry into a
single ``snap(scene_pos)`` query, suitable for use by drawing tools
during placement.

Typical lifecycle:

    snapper = PointSnapper(registry)
    snapper.update_scene(view.scene().items())  # call on scene changes
    hit = snapper.snap(QPointF(123, 456), threshold=15)

When the index is unavailable (no items), the registry falls back to
iterating the raw item list.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.snap.provider import SnapCandidate
from open_garden_planner.core.snap.registry import DEFAULT_THRESHOLD, SnapRegistry
from open_garden_planner.core.snap.spatial_index import QuadTree, build_from_items


class PointSnapper:
    """Combines a :class:`SnapRegistry` with a quadtree pre-filter."""

    def __init__(self, registry: SnapRegistry) -> None:
        self._registry = registry
        self._index: QuadTree | None = None
        self._items: list[QGraphicsItem] = []

    @property
    def registry(self) -> SnapRegistry:
        return self._registry

    def update_scene(
        self,
        items: list[QGraphicsItem],
        scene_bounds: QRectF | None = None,
    ) -> None:
        """Rebuild the spatial index from a fresh item list."""
        self._items = list(items)
        self._index = build_from_items(self._items, scene_bounds=scene_bounds)

    def clear(self) -> None:
        self._items = []
        self._index = None

    def snap(
        self,
        scene_pos: QPointF,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> SnapCandidate | None:
        if not self._items or self._index is None:
            return None
        # Widen the query region: intersection candidates can sit on
        # edges that originate outside the immediate window.
        margin = threshold * 4
        region = QRectF(
            scene_pos.x() - margin,
            scene_pos.y() - margin,
            margin * 2,
            margin * 2,
        )
        candidates = self._index.query(region)
        if not candidates:
            return None
        return self._registry.best(scene_pos, candidates, threshold)
