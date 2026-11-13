"""Room for the canvas items' device caches (#784).

Every unselected canvas item is ``DeviceCoordinateCache`` (#430): Qt rasterises
it once and blits that picture until the item or the zoom changes. Qt keeps
those pictures in the process-wide ``QPixmapCache`` — whose default limit is
**10 MB**. One lawn that covers a 1453 x 898 viewport is 5.2 MB; the family
garden example at fit needs 17 MB for its 101 visible items (measured, #784).
Past the limit Qt evicts, and an evicted item is painted again on the next
frame: the cache thrashes, and a repaint that should be a hundred blits costs
what a hundred paints cost (146 ms against 11 ms on that plan; a 40-px pan step
138 ms against 21 ms). A picture larger than the whole limit — the lawn on a 4K
display is 33 MB — is never kept at all.

``ensure_item_cache_budget`` raises the limit to ``ITEM_CACHE_BUDGET_KB``. That
is a ceiling, not an allocation: the cache holds what the visible items need
(their device rectangles, 4 bytes a pixel) and evicts the least recently used
beyond it. 256 MB is that need for a 4K viewport with every pixel covered about
seven items deep; the family garden at 4K needs about 110 MB.
"""

from __future__ import annotations

from typing import Final

from PyQt6.QtGui import QPixmapCache

#: The ceiling of ``QPixmapCache`` while a canvas exists, in kilobytes (Qt's unit).
ITEM_CACHE_BUDGET_KB: Final = 256 * 1024


def ensure_item_cache_budget() -> None:
    """Raise ``QPixmapCache``'s limit to the canvas's budget (never lower it:
    an embedding application may have asked for more)."""
    if QPixmapCache.cacheLimit() < ITEM_CACHE_BUDGET_KB:
        QPixmapCache.setCacheLimit(ITEM_CACHE_BUDGET_KB)


__all__ = ["ITEM_CACHE_BUDGET_KB", "ensure_item_cache_budget"]
