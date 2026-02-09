"""Alignment and distribution tools for multi-selected objects.

Provides functions to compute per-item movement deltas for alignment
(left, right, top, bottom, center H, center V) and distribution
(equal horizontal/vertical spacing).
"""

from __future__ import annotations

from enum import Enum, auto

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem


class AlignMode(Enum):
    """Alignment modes for multi-selection."""

    LEFT = auto()
    RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()
    CENTER_H = auto()
    CENTER_V = auto()


class DistributeMode(Enum):
    """Distribution modes for multi-selection."""

    HORIZONTAL = auto()
    VERTICAL = auto()


def align_items(
    items: list[QGraphicsItem],
    mode: AlignMode,
) -> list[tuple[QGraphicsItem, QPointF]]:
    """Compute per-item movement deltas for alignment.

    The alignment reference is the bounding box of the entire selection.
    For example, LEFT aligns all items to the leftmost edge of the selection.

    Args:
        items: The items to align (must have 2+ items for meaningful result).
        mode: The alignment mode.

    Returns:
        List of (item, delta) tuples where delta is the QPointF movement.
        Items that don't need to move have delta (0, 0).
    """
    if len(items) < 2:
        return []

    rects = [(item, item.sceneBoundingRect()) for item in items]
    result: list[tuple[QGraphicsItem, QPointF]] = []

    if mode == AlignMode.LEFT:
        target = min(r.left() for _, r in rects)
        for item, rect in rects:
            dx = target - rect.left()
            result.append((item, QPointF(dx, 0)))

    elif mode == AlignMode.RIGHT:
        target = max(r.right() for _, r in rects)
        for item, rect in rects:
            dx = target - rect.right()
            result.append((item, QPointF(dx, 0)))

    elif mode == AlignMode.TOP:
        target = min(r.top() for _, r in rects)
        for item, rect in rects:
            dy = target - rect.top()
            result.append((item, QPointF(0, dy)))

    elif mode == AlignMode.BOTTOM:
        target = max(r.bottom() for _, r in rects)
        for item, rect in rects:
            dy = target - rect.bottom()
            result.append((item, QPointF(0, dy)))

    elif mode == AlignMode.CENTER_H:
        # Align to the horizontal center of the bounding box
        all_left = min(r.left() for _, r in rects)
        all_right = max(r.right() for _, r in rects)
        target = (all_left + all_right) / 2.0
        for item, rect in rects:
            dx = target - rect.center().x()
            result.append((item, QPointF(dx, 0)))

    elif mode == AlignMode.CENTER_V:
        # Align to the vertical center of the bounding box
        all_top = min(r.top() for _, r in rects)
        all_bottom = max(r.bottom() for _, r in rects)
        target = (all_top + all_bottom) / 2.0
        for item, rect in rects:
            dy = target - rect.center().y()
            result.append((item, QPointF(0, dy)))

    return result


def distribute_items(
    items: list[QGraphicsItem],
    mode: DistributeMode,
) -> list[tuple[QGraphicsItem, QPointF]]:
    """Compute per-item movement deltas for equal-spacing distribution.

    Items are distributed so that the space between them is equal.
    The first and last items (by position) stay in place.

    Args:
        items: The items to distribute (must have 3+ items for meaningful result).
        mode: The distribution mode (horizontal or vertical).

    Returns:
        List of (item, delta) tuples.
    """
    if len(items) < 3:
        return []

    rects = [(item, item.sceneBoundingRect()) for item in items]

    if mode == DistributeMode.HORIZONTAL:
        # Sort by horizontal center position
        rects.sort(key=lambda pair: pair[1].center().x())

        # Total extent from first center to last center
        first_center = rects[0][1].center().x()
        last_center = rects[-1][1].center().x()
        total_span = last_center - first_center

        if total_span == 0:
            return [(item, QPointF(0, 0)) for item in items]

        step = total_span / (len(rects) - 1)

        result: list[tuple[QGraphicsItem, QPointF]] = []
        for i, (item, rect) in enumerate(rects):
            target_center = first_center + step * i
            dx = target_center - rect.center().x()
            result.append((item, QPointF(dx, 0)))

        return result

    else:  # VERTICAL
        # Sort by vertical center position
        rects.sort(key=lambda pair: pair[1].center().y())

        first_center = rects[0][1].center().y()
        last_center = rects[-1][1].center().y()
        total_span = last_center - first_center

        if total_span == 0:
            return [(item, QPointF(0, 0)) for item in items]

        step = total_span / (len(rects) - 1)

        result = []
        for i, (item, rect) in enumerate(rects):
            target_center = first_center + step * i
            dy = target_center - rect.center().y()
            result.append((item, QPointF(0, dy)))

        return result
