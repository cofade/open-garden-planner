"""Which object labels are shown when there is not room for all (Qt-free, #793).

A label keeps its size on screen while the plan under it zooms, so on a plan
zoomed out the labels of neighbouring objects run into each other and the ones
of small objects are larger than what they name. Two rules, both in screen
pixels, decide which are painted:

1. **Size.** An object smaller on screen than ``LABEL_MIN_OWNER_PX`` gets no
   label: the text would cover it and its neighbours.
2. **Room.** Labels never overlap. They are placed in order of importance, and
   one that would touch a label already placed is left out: the larger object
   wins, as on a map.

A selected object's labels are exempt from the size rule and are placed first,
so the object being worked on always names itself.

The labels of ONE object (its name and the area hung under it) are a stack, not
neighbours: they lie closer than the gap by construction and do not exclude
each other. They stand and fall together: when the name has no room, the area
is left out too, or it would hang under nothing.

The layout looks at every label, never only at the ones in a repainted
region: a partial repaint must reach the same answer as a full one.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass

#: An object smaller than this on screen (its longer side, pixels) shows no label.
LABEL_MIN_OWNER_PX = 14.0
#: Clear space kept between two labels, pixels.
LABEL_GAP_PX = 3.0

_CELL_PX = 96.0


@dataclass(frozen=True)
class LabelCandidate:
    """One label that wants to be shown.

    Attributes:
        rect: Where it would be painted, device pixels ``(left, top, right, bottom)``.
        owner_extent_px: The longer side of its object on screen, pixels.
        pinned: Its object is selected: exempt from the size rule, placed first.
        rank: Order among the labels of one object (name 0, area 1).
        tie: Any stable value that orders two otherwise equal labels.
        owner: What identifies its object, or ``None`` for a label on its own.
            Labels with the same owner are one stack.
    """

    rect: tuple[float, float, float, float]
    owner_extent_px: float
    pinned: bool = False
    rank: int = 0
    tie: str = ""
    owner: Hashable | None = None


def place_labels(
    candidates: Sequence[LabelCandidate],
    *,
    min_owner_px: float = LABEL_MIN_OWNER_PX,
    gap_px: float = LABEL_GAP_PX,
) -> list[int]:
    """Indices of the candidates to paint, in the order they were placed."""
    order = sorted(
        (
            index
            for index, candidate in enumerate(candidates)
            if candidate.pinned or candidate.owner_extent_px >= min_owner_px
        ),
        key=lambda index: (
            not candidates[index].pinned,
            -candidates[index].owner_extent_px,
            candidates[index].rank,
            candidates[index].tie,
            index,
        ),
    )
    cells: dict[tuple[int, int], list[tuple[float, float, float, float, Hashable | None]]] = {}
    placed: list[int] = []
    left_out: set[Hashable] = set()
    for index in order:
        owner = candidates[index].owner
        if owner is not None and owner in left_out:
            continue
        left, top, right, bottom = candidates[index].rect
        grown = (left - gap_px, top - gap_px, right + gap_px, bottom + gap_px)
        keys = [
            (column, row)
            for column in range(int(grown[0] // _CELL_PX), int(grown[2] // _CELL_PX) + 1)
            for row in range(int(grown[1] // _CELL_PX), int(grown[3] // _CELL_PX) + 1)
        ]
        if any(
            grown[0] < other[2] and other[0] < grown[2] and grown[1] < other[3] and other[1] < grown[3]
            for key in keys
            for other in cells.get(key, ())
            if owner is None or other[4] != owner
        ):
            if owner is not None:
                left_out.add(owner)
            continue
        placed.append(index)
        for key in keys:
            cells.setdefault(key, []).append((left, top, right, bottom, owner))
    return placed
