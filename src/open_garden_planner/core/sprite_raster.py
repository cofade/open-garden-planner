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
- **a sprite whose level asks for more than ``MAX_CACHED_SIDE_PX`` on a side
  while the device shows no more than that of it** (a 3.45 m tree at 224 %:
  773 device pixels, 1380 at level 4) is rasterised at ``MAX_CACHED_SIDE_PX``
  — never enlarged, minified by less than the level would be — and cached
  like any other.
- **a sprite the device shows more than ``MAX_CACHED_SIDE_PX`` of** (a 5 m
  tree at 400 %) is not rasterised whole — that pixmap is 16 MB at 2048 px
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

That bound has to hold what ONE frame draws, or the frame evicts its own
sprites and every zoom step rasterises them again. What a frame draws grows
with the viewport: its sprites cover the viewport's device pixels, at up to
four pixmap pixels a device pixel (the level is the zoom rounded UP to a power
of two). So a canvas states its viewport (``ensure_sprite_cache_room``) and the
bound is raised to ``sprite_cache_budget`` of it, up to
``SPRITE_CACHE_CEILING_BYTES``. Measured (review of #785): the 853-object plan
in a 3840 x 2000 viewport at 207 % needs 121 sprites of level 4 at once; with
64 MB each zoom step there rasterised 134 sprites again and took 1.3 s.
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
#: thousands of tiny sprites. The bytes are the bound for a viewport of up to
#: two megapixels; a larger one raises it (``sprite_cache_budget``).
SPRITE_CACHE_MAX_BYTES: Final = 64 * 1024 * 1024
SPRITE_CACHE_MAX_ENTRIES: Final = 4096

#: What the cache may hold for each device pixel of the viewport: 4 bytes a
#: pixmap pixel, up to 4 pixmap pixels a device pixel (a level is at most twice
#: the zoom, on both axes), and sprites that lie two deep (a sprite reaches
#: past its plant by a fifth, and plants stand under trees).
SPRITE_CACHE_BYTES_PER_DEVICE_PIXEL: Final = 32

#: ... and the most it is ever given: a ceiling, not an allocation. The cache
#: holds what was drawn and evicts beyond it. A 3840 x 2160 viewport comes to
#: 253 MB of it.
SPRITE_CACHE_CEILING_BYTES: Final = 256 * 1024 * 1024

#: The most pixels the transient layer of an oversized sprite may have (64 MB);
#: beyond it the layer is coarser than the device, never larger.
MAX_LAYER_PIXELS: Final = 16 * 1024 * 1024

#: How far past the viewport a kept layer reaches once a pan has run out of it
#: (``KeptLayer``), device pixels on every side: six 40-pixel pan steps.
KEPT_LAYER_MARGIN_PX: Final = 256

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
    scale = device_scale(painter)
    width_px, height_px = sprite_pixel_size(width, height, raster_level(scale))
    longest = max(width_px, height_px)
    if longest > MAX_CACHED_SIDE_PX:
        if max(width, height) * scale > MAX_CACHED_SIDE_PX:
            return _paint_exposed(painter, target, draw, tint)
        # The level's bitmap is too large to keep, but the device shows no more
        # of this sprite than the largest one that may be kept: that one is
        # still at least as fine as the device, and it is cached — the exposed
        # route would draw the vector again at every zoom step.
        fit = MAX_CACHED_SIDE_PX / longest
        width_px = max(math.ceil(width_px * fit - 1e-6), MIN_SIDE_PX)
        height_px = max(math.ceil(height_px * fit - 1e-6), MIN_SIDE_PX)
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


def device_bounds(painter: QPainter) -> QRectF:
    """The painter's device in the pixels its device transform maps to."""
    device = painter.device()
    if device is None:
        return QRectF()
    # An image or a pixmap (Qt's own item cache among them) reports the pixels it
    # has; a widget reports device-independent ones.
    ratio = 1.0 if isinstance(device, QImage | QPixmap) else device.devicePixelRatioF()
    # A child widget is painted into its window's backing store: the device
    # transform then carries the child's offset in the window, which the painter's
    # own transform does not. The bounds sit at that offset (the canvas's viewport
    # lies below the toolbars; without it the bottom strip of the viewport was lost).
    left = top = 0.0
    own, invertible = painter.combinedTransform().inverted()
    if invertible:
        redirection = own * painter.deviceTransform()
        left, top = redirection.dx(), redirection.dy()
    return QRectF(left, top, device.width() * ratio, device.height() * ratio)


def _exposed_area(painter: QPainter, target: QRectF) -> tuple[QTransform, QTransform, QRect] | None:
    """The painter's device transform, its inverse, and what its device shows
    of ``target`` in whole device pixels; None when the transform has no inverse."""
    to_device = painter.deviceTransform()
    from_device, invertible = to_device.inverted()
    if not invertible:
        return None
    exposed = to_device.mapRect(target).intersected(device_bounds(painter))
    if painter.hasClipping():
        exposed = exposed.intersected(to_device.mapRect(painter.clipBoundingRect()))
    return to_device, from_device, exposed.toAlignedRect()


def _render_layer(
    to_device: QTransform,
    area: QRect,
    shrink: float,
    target: QRectF,
    draw: SpriteDraw,
    tint: QColor | None,
) -> QImage | None:
    """``draw`` into a new transparent layer that covers ``area`` of the device
    (whole device pixels), ``shrink`` times as fine. Every layer is made here."""
    layer = _transparent_image(
        max(math.ceil(area.width() * shrink), 1), max(math.ceil(area.height() * shrink), 1)
    )
    if layer is None:
        return None
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
    return layer


def _lay_layer(
    painter: QPainter, from_device: QTransform, area: QRect, layer: QImage, source: QRectF
) -> None:
    """Lay ``source`` of ``layer`` down on ``area`` of the device, untransformed."""
    painter.save()
    # World transform that makes the painter's DEVICE transform the identity:
    # device = world x rest, so world' = device^-1 x world gives world' x rest = 1.
    painter.setWorldTransform(from_device * painter.worldTransform())
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QRectF(area), layer, source)
    painter.restore()


def _paint_exposed(
    painter: QPainter, target: QRectF, draw: SpriteDraw, tint: QColor | None
) -> bool:
    """An oversized sprite: draw only what the device shows of it, from the
    vector, into a layer in device pixels (so nothing is resampled), and lay
    that layer down untransformed."""
    found = _exposed_area(painter, target)
    if found is None:
        return False
    to_device, from_device, area = found
    if area.isEmpty():
        return True  # nothing of it is on the device: painted, in full
    # Coarser than the device where the rule says so (a 1200-dpi printer, a
    # recording painter) or where the layer would not fit its budget.
    shrink = min(1.0, device_scale(painter) / raw_device_scale(painter))
    pixels = area.width() * area.height() * shrink * shrink
    if pixels > MAX_LAYER_PIXELS:
        shrink *= math.sqrt(MAX_LAYER_PIXELS / pixels)
    layer = _render_layer(to_device, area, shrink, target, draw, tint)
    if layer is None:
        return False
    _lay_layer(painter, from_device, area, layer, QRectF(layer.rect()))
    return True


def paint_layer(painter: QPainter, target: QRectF, draw: SpriteDraw) -> bool:
    """Paint what ``draw`` describes through a layer in device pixels.

    For a picture that is neither a sprite nor worth keeping: something that
    has to be composed before it is laid down (the sun shadow's soft edge is a
    field with the shade cut out of it). ``draw(p, target)`` paints into a
    transparent layer that covers what ``painter``'s device shows of
    ``target`` and nothing else; the layer has the device's resolution — 300
    dpi at most on a finer one, 1 px per cm on a recording painter — and is
    laid down untransformed, so it is the same picture in a view, an export, an
    SVG and a print, and needs no clip of its own. False when nothing could be
    painted.
    """
    return _paint_exposed(painter, target, draw, None)


class KeptLayer:
    """A layer in device pixels that a widget keeps between its paints (#793).

    ``paint_layer`` makes its layer for one paint and drops it. That is right
    for a picture that differs at every paint, and wrong for one that is the
    same until the scene or the zoom changes and is then painted again and
    again: the canvas grid with every standing object cut out of it. This
    keeps such a layer, under a ``key`` that names what it was made from, and
    a paint lays the exposed part of it down: no allocation, no ``draw``.

    A pan moves the layer with the plan. Its place is kept as the device
    transform's translation, so a repaint after a pan lays it down moved by
    whole device pixels (a pan by part of one, at a fractional display
    scaling, is drawn afresh: nothing is resampled). What a pan brings into
    view lies outside a layer that covers the viewport alone, so a layer made
    because a pan ran out of it reaches ``margin_px`` further on every side —
    and only then: the layer made after a scene change or a zoom step is one
    viewport, because most of those are followed by another.

    The layer is made on a paint that covers all the widget shows of
    ``whole``, or when a pan ran out of the one that is held. A partial
    repaint of ANOTHER picture (the key or the zoom changed) is painted
    through ``paint_layer``'s own route for its rectangle — what every paint
    did until the second review of the 2D branch — and makes no layer: a drag
    repaints two small rectangles a frame, and must not pay a viewport for
    them.

    Bound: ``MAX_LAYER_PIXELS`` (64 MB) — a viewport that large gets no
    margin, and a larger one no kept layer at all. ``bytes_used`` says what is
    held, ``builds`` counts the layers made (counted, never timed: §8.10.10).
    """

    def __init__(self, margin_px: int = KEPT_LAYER_MARGIN_PX) -> None:
        self._margin = margin_px
        self._layer: QImage | None = None
        self._key: Hashable = None
        self._scale: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self._origin: tuple[float, float] = (0.0, 0.0)
        self._area = QRect()
        self.builds = 0

    def clear(self) -> None:
        """Drop the layer (the picture is switched off, the plan is replaced)."""
        self._layer = None
        self._key = None

    @property
    def bytes_used(self) -> int:
        """The bytes of the layer that is held."""
        return 0 if self._layer is None else self._layer.sizeInBytes()

    def paint(
        self, painter: QPainter, whole: QRectF, exposed: QRectF, key: Hashable, draw: SpriteDraw
    ) -> bool:
        """Paint ``exposed`` of the picture ``draw`` describes over ``whole``
        (both in the painter's coordinates), from the kept layer where it holds
        it. ``draw(p, part)`` paints ``part`` of the picture and nothing else.
        False when nothing could be painted."""
        wanted = exposed.intersected(whole)
        found = _exposed_area(painter, wanted)
        if found is None:
            return False
        to_device, from_device, area = found
        if area.isEmpty():
            return True
        scale = (to_device.m11(), to_device.m12(), to_device.m21(), to_device.m22())
        origin = (to_device.dx(), to_device.dy())
        layer = self._layer
        same_picture = layer is not None and self._key == key and self._scale == scale
        moved = (origin[0] - self._origin[0], origin[1] - self._origin[1])
        steps = (round(moved[0]), round(moved[1]))
        # ... and it lies a whole number of device pixels from where it was made
        in_step = (
            same_picture
            and abs(moved[0] - steps[0]) < 1e-6
            and abs(moved[1] - steps[1]) < 1e-6
        )
        if layer is not None and in_step:
            held = self._area.translated(steps[0], steps[1])
            if held.contains(area):
                source = QRectF(area.translated(-held.x(), -held.y()))
                _lay_layer(painter, from_device, area, layer, source)
                return True
        bounds = device_bounds(painter).toAlignedRect()
        shown = to_device.mapRect(whole).toAlignedRect()
        # Qt hands a paint of the whole viewport a rectangle that may stop a
        # pixel short of its edge.
        whole_view = area.adjusted(-2, -2, 2, 2).contains(shown.intersected(bounds))
        if (not in_step and not whole_view) or device_scale(painter) < raw_device_scale(painter):
            return _paint_exposed(painter, wanted, draw, None)
        # A pan ran out of the layer: the next one reaches further.
        margin = self._margin if in_step else 0
        region = shown.intersected(bounds.adjusted(-margin, -margin, margin, margin))
        if region.width() * region.height() > MAX_LAYER_PIXELS:
            region = shown.intersected(bounds)
        if region.width() * region.height() > MAX_LAYER_PIXELS:
            self.clear()
            return _paint_exposed(painter, wanted, draw, None)
        layer = _render_layer(
            to_device, region, 1.0, from_device.mapRect(QRectF(region)), draw, None
        )
        if layer is None:
            self.clear()
            return False
        self._layer, self._key, self._scale, self._origin, self._area = (
            layer, key, scale, origin, region,
        )
        self.builds += 1
        _lay_layer(
            painter, from_device, area, layer, QRectF(area.translated(-region.x(), -region.y()))
        )
        return True


def sprite_cache_budget(device_pixels: float) -> int:
    """The bytes ``SPRITE_CACHE`` may hold for a viewport of ``device_pixels``:
    ``SPRITE_CACHE_BYTES_PER_DEVICE_PIXEL`` each, never under
    ``SPRITE_CACHE_MAX_BYTES`` and never over ``SPRITE_CACHE_CEILING_BYTES``."""
    wanted = SPRITE_CACHE_BYTES_PER_DEVICE_PIXEL * max(device_pixels, 0.0)
    if not math.isfinite(wanted):
        return SPRITE_CACHE_CEILING_BYTES
    return int(min(max(wanted, SPRITE_CACHE_MAX_BYTES), SPRITE_CACHE_CEILING_BYTES))


def ensure_sprite_cache_room(device_pixels: float, cache: PixmapLru = SPRITE_CACHE) -> None:
    """Give ``cache`` room for a viewport of ``device_pixels`` (module docstring).

    Raised, never lowered: two views share the cache, and a window dragged to
    a smaller screen keeps what it already holds. One comparison when there is
    room already, so a view may call it at every paint.
    """
    budget = sprite_cache_budget(device_pixels)
    if cache.max_bytes < budget:
        cache.max_bytes = budget


def clear_sprite_cache() -> None:
    """Drop every cached canvas sprite. Called where a plan is closed or
    replaced (``CanvasScene.clear``); the cache's bound stays what the largest
    viewport made it."""
    SPRITE_CACHE.clear()


__all__ = [
    "KEPT_LAYER_MARGIN_PX",
    "MAX_CACHED_SIDE_PX",
    "MAX_LAYER_PIXELS",
    "MIN_SIDE_PX",
    "SPRITE_CACHE",
    "SPRITE_CACHE_BYTES_PER_DEVICE_PIXEL",
    "SPRITE_CACHE_CEILING_BYTES",
    "SPRITE_CACHE_MAX_BYTES",
    "SPRITE_CACHE_MAX_ENTRIES",
    "TINT_ALPHA",
    "KeptLayer",
    "PixmapLru",
    "clear_sprite_cache",
    "device_bounds",
    "ensure_sprite_cache_room",
    "paint_layer",
    "paint_sprite",
    "rasterise",
    "sprite_cache_budget",
    "sprite_pixel_size",
]
