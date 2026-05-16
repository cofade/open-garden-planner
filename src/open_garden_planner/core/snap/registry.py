"""Provider registry and orchestration for point-snap queries."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.snap.provider import SnapCandidate, SnapProvider

DEFAULT_THRESHOLD = 15.0


class SnapRegistry:
    """Collects active :class:`SnapProvider`s and runs them on a query.

    The registry stays unaware of how providers are configured (View
    menu, settings, etc.); callers add/remove instances directly.  This
    keeps the engine layer free of UI concerns.
    """

    def __init__(self, providers: Sequence[SnapProvider] = ()) -> None:
        self._providers: list[SnapProvider] = list(providers)

    def add(self, provider: SnapProvider) -> None:
        self._providers.append(provider)

    def remove(self, provider_type: type[SnapProvider]) -> None:
        self._providers = [p for p in self._providers if not isinstance(p, provider_type)]

    def has(self, provider_type: type[SnapProvider]) -> bool:
        return any(isinstance(p, provider_type) for p in self._providers)

    def providers(self) -> list[SnapProvider]:
        return list(self._providers)

    def best(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> SnapCandidate | None:
        """Return the closest candidate within ``threshold`` or ``None``.

        Tie-breaking: lower ``priority`` wins (endpoint > intersection >
        midpoint > center > edge by default).  Items are iterated once
        and shared across all providers.
        """
        items_list = list(items)
        threshold_sq = threshold * threshold

        best: SnapCandidate | None = None
        best_dist_sq = threshold_sq
        for provider in self._providers:
            for candidate in provider.candidates(scene_pos, items_list, threshold):
                dx = candidate.point.x() - scene_pos.x()
                dy = candidate.point.y() - scene_pos.y()
                d_sq = dx * dx + dy * dy
                if d_sq > threshold_sq:
                    continue
                if best is None or (
                    candidate.priority < best.priority
                    or (candidate.priority == best.priority and d_sq < best_dist_sq)
                ):
                    best = candidate
                    best_dist_sq = d_sq
        return best
