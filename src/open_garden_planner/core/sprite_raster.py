"""Paint a vector sprite at the resolution it is shown at (#785).

A plant or object sprite is an SVG; the canvas wants a bitmap, because one is
tinted and many are drawn. ``paint_sprite`` is the one place that turns the
first into the second for a painter, and it asks ``core.raster_resolution`` how
fine:

- **a sprite of ordinary size** is rasterised at the painter's level
  (``painter_level`` — its scale rounded up to a power of two), kept in
  ``SPRITE_CACHE`` and drawn into its exact rectangle. The pixel size is the
  cache key, so two zooms inside one level share a pixmap and a new level is a
  new one.
- **a sprite that would need more than ``MAX_CACHED_SIDE_PX`` on a side** (a
  5 m tree at 400 %) is not rasterised whole — that pixmap is 16 MB at 2048 px
  and 100 MB at 5000. Only the part of it the device can show is drawn, straight
  from the vector into a layer of that part's size, at the device's own
  resolution. Measured (#785): a 9000-px tree clipped to a 1500 x 900 window
  costs 6-16 ms, against 66 ms and 16 MB for the 2048-px pixmap that would still
  be shown 4.4 times too large. At most a handful of such sprites fit a window
  at once (each covers a third of it or more) and Qt's device cache keeps their
  picture between paints, so nothing is cached here.

The memory bound is ``SPRITE_CACHE``'s: ``SPRITE_CACHE_MAX_BYTES`` in at most
``SPRITE_CACHE_MAX_ENTRIES`` pixmaps, none larger than ``MAX_CACHED_SIDE_PX``
squared (4 MB). The layer of an oversized sprite is transient and at most
``MAX_LAYER_PIXELS``.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Final

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap, QTransform

from .raster_resolution import device_scale, raster_level, raw_device_scale

#: The longest side a cached sprite pixmap may have; a larger one is drawn from
#: the vector for the exposed part only (module docstring).
MAX_CACHED_SIDE_PX: Final = 1024

#: No sprite pixmap is smaller than this on a side (the renderers' own minimum).
MIN_SIDE_PX: Final = 4

#: The cache's bound — bytes first, entries as a backstop for a plan of
#: thousands of tiny sprites.
SPRITE_CACHE_MAX_BYTES: Final = 64 * 1024 * 1024
SPRITE_CACHE_MAX_ENTRIES: Final = 4096

#: The most pixels the transient layer of an oversized sprite may have (64 MB);
#: beyond it the layer is coarser than the device, never larger.
MAX_LAYER_PIXELS: Final = 16 * 1024 * 1024

#: How much of a tint colour is laid over the sprite's own pixels.
TINT_ALPHA: Final = 60

SpriteDraw = Callable[[QPainter, QRectF], None]


class PixmapLru:
    """A pixmap cache bounded in bytes and entries, least recently used out first.

    A pixmap larger than the whole budget is never stored (the caller still
    gets it): one oversized entry must not evict everything else.
    """

    def __init__(self, max_bytes: int, max_entries: int) -> None:
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._entries: OrderedDict[Hashable, tuple[QPixmap, int]] = OrderedDict()
        self._bytes = 0

    @property
    def bytes_used(self) -> int:
        return self._bytes

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: Hashable) -> bool:
        return key in self._entries

    def get(self, key: Hashable) -> QPixmap | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._entries.move_to_end(key)
        return entry[0]

    def put(self, key: Hashable, pixmap: QPixmap) -> None:
        size = pixmap.width() * pixmap.height() * 4
        old = self._entries.pop(key, None)
        if old is not None:
            self._bytes -= old[1]
        if size > self.max_bytes:
            return
        while self._entries and (
            len(self._entries) >= self.max_entries or self._bytes + size > self.max_bytes
        ):
            _, (_, dropped) = self._entries.popitem(last=False)
            self._bytes -= dropped
        self._entries[key] = (pixmap, size)
        self._bytes += size

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0


#: Every sprite the canvas paints, plants and objects alike.
SPRITE_CACHE: Final = PixmapLru(SPRITE_CACHE_MAX_BYTES, SPRITE_CACHE_MAX_ENTRIES)


def sprite_pixel_size(width: float, height: float, level: float) -> tuple[int, int]:
    """The pixmap size of a ``width`` x ``height`` (item units) sprite at ``level``."""
    return (
        max(math.ceil(width * level - 1e-6), MIN_SIDE_PX),
        max(math.ceil(height * level - 1e-6), MIN_SIDE_PX),
    )


def _transparent_image(width_px: int, height_px: int) -> QImage | None:
    """A new transparent image to paint a sprite into; None when there is no
    memory for it. Every bitmap this module makes is made here."""
    image = QImage(width_px, height_px, QImage.Format.Format_ARGB32_Premultiplied)
    if image.isNull():
        return None
    image.fill(Qt.GlobalColor.transparent)
    return image


def rasterise(
    width_px: int, height_px: int, draw: SpriteDraw, tint: QColor | None = None
) -> QPixmap | None:
    """``draw`` into a new transparent ``width_px`` x ``height_px`` pixmap, tinted."""
    image = _transparent_image(width_px, height_px)
    if image is None:
        return None
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        draw(painter, QRectF(0.0, 0.0, float(width_px), float(height_px)))
        _lay_tint(painter, image.rect(), tint)
    finally:
        painter.end()
    pixmap = QPixmap.fromImage(image)
    return None if pixmap.isNull() else pixmap


def paint_sprite(
    painter: QPainter,
    target: QRectF,
    key: Hashable,
    draw: SpriteDraw,
    *,
    tint: QColor | None = None,
    cache: PixmapLru = SPRITE_CACHE,
) -> bool:
    """Paint the sprite ``draw`` describes into ``target`` (item units), as fine
    as ``painter`` shows it (module docstring).

    ``draw(p, rect)`` draws the whole sprite into ``rect`` of ``p`` and nothing
    else; it is called with a pixmap's painter or with a layer's. ``key`` names
    the picture apart from its size and tint (a file, a turn, a rotation).
    False when nothing could be painted (a degenerate rectangle, no memory).
    """
    width, height = target.width(), target.height()
    if not (math.isfinite(width) and math.isfinite(height) and width > 0.0 and height > 0.0):
        return False
    level = raster_level(device_scale(painter))
    width_px, height_px = sprite_pixel_size(width, height, level)
    if max(width_px, height_px) > MAX_CACHED_SIDE_PX:
        return _paint_exposed(painter, target, draw, tint)
    cache_key = (key, width_px, height_px, tint.rgba() if tint is not None else None)
    pixmap = cache.get(cache_key)
    if pixmap is None:
        pixmap = rasterise(width_px, height_px, draw, tint)
        if pixmap is None:
            return False
        cache.put(cache_key, pixmap)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawPixmap(target, pixmap, QRectF(0.0, 0.0, float(width_px), float(height_px)))
    return True


def _lay_tint(painter: QPainter, rect: QRect, tint: QColor | None) -> None:
    """Wash ``tint`` over what is already painted in ``rect`` (device pixels)."""
    if tint is None or tint.alpha() <= 0:
        return
    painter.resetTransform()
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    painter.fillRect(rect, QColor(tint.red(), tint.green(), tint.blue(), TINT_ALPHA))


def _device_bounds(painter: QPainter) -> QRectF:
    """The painter's device in the pixels its device transform maps to."""
    device = painter.device()
    if device is None:
        return QRectF()
    # An image or a pixmap (Qt's own item cache among them) reports the pixels it
    # has; a widget reports device-independent ones.
    ratio = 1.0 if isinstance(device, QImage | QPixmap) else device.devicePixelRatioF()
    return QRectF(0.0, 0.0, device.width() * ratio, device.height() * ratio)


def _paint_exposed(
    painter: QPainter, target: QRectF, draw: SpriteDraw, tint: QColor | None
) -> bool:
    """An oversized sprite: draw only what the device shows of it, from the
    vector, into a layer in device pixels (so nothing is resampled), and lay
    that layer down untransformed."""
    to_device = painter.deviceTransform()
    from_device, invertible = to_device.inverted()
    if not invertible:
        return False
    exposed = to_device.mapRect(target).intersected(_device_bounds(painter))
    if painter.hasClipping():
        exposed = exposed.intersected(to_device.mapRect(painter.clipBoundingRect()))
    area = exposed.toAlignedRect()
    if area.isEmpty():
        return True  # nothing of it is on the device: painted, in full
    # Coarser than the device where the rule says so (a 1200-dpi printer, a
    # recording painter) or where the layer would not fit its budget.
    shrink = min(1.0, device_scale(painter) / raw_device_scale(painter))
    pixels = area.width() * area.height() * shrink * shrink
    if pixels > MAX_LAYER_PIXELS:
        shrink *= math.sqrt(MAX_LAYER_PIXELS / pixels)
    layer = _transparent_image(
        max(math.ceil(area.width() * shrink), 1), max(math.ceil(area.height() * shrink), 1)
    )
    if layer is None:
        return False
    layer_painter = QPainter(layer)
    try:
        layer_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        layer_painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        layer_painter.setTransform(
            to_device
            * QTransform.fromTranslate(-area.x(), -area.y())
            * QTransform.fromScale(shrink, shrink)
        )
        draw(layer_painter, target)
        _lay_tint(layer_painter, layer.rect(), tint)
    finally:
        layer_painter.end()
    painter.save()
    # World transform that makes the painter's DEVICE transform the identity:
    # device = world x rest, so world' = device^-1 x world gives world' x rest = 1.
    painter.setWorldTransform(from_device * painter.worldTransform())
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QRectF(area), layer, QRectF(layer.rect()))
    painter.restore()
    return True


def clear_sprite_cache() -> None:
    """Drop every cached canvas sprite."""
    SPRITE_CACHE.clear()


__all__ = [
    "MAX_CACHED_SIDE_PX",
    "MAX_LAYER_PIXELS",
    "MIN_SIDE_PX",
    "SPRITE_CACHE",
    "SPRITE_CACHE_MAX_BYTES",
    "SPRITE_CACHE_MAX_ENTRIES",
    "TINT_ALPHA",
    "PixmapLru",
    "clear_sprite_cache",
    "paint_sprite",
    "rasterise",
    "sprite_pixel_size",
]
