"""Snap provider abstraction.

A ``SnapProvider`` enumerates ``SnapCandidate`` points around a query
position.  The ``PointSnapper`` runs every enabled provider and picks
the closest candidate within the configured threshold.

Each provider owns one snap *mode* (endpoint, center, midpoint,
intersection, etc.).  Modes can be enabled/disabled individually by the
user via the View menu.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem


class SnapCandidateKind(Enum):
    """Type of a snap candidate, used to pick a visual glyph."""

    ENDPOINT = auto()
    CENTER = auto()
    EDGE = auto()
    MIDPOINT = auto()
    INTERSECTION = auto()


@dataclass(frozen=True)
class SnapCandidate:
    """A point produced by a :class:`SnapProvider`.

    Lower ``priority`` wins on ties (endpoint beats midpoint beats edge).
    """

    point: QPointF
    kind: SnapCandidateKind
    priority: int = 100
    item: QGraphicsItem | None = None


class SnapProvider(ABC):
    """Abstract source of snap candidates."""

    kind: SnapCandidateKind
    priority: int = 100

    @abstractmethod
    def candidates(
        self,
        scene_pos: QPointF,
        items: Iterable[QGraphicsItem],
        threshold: float,
    ) -> Iterable[SnapCandidate]:
        """Yield candidates within ``threshold`` of ``scene_pos``."""
        raise NotImplementedError
