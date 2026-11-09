"""At what resolution a picture is rasterised — the one rule (#785).

A plant sprite, an object sprite and a fill-texture tile are bitmaps drawn
through a painter whose scale is not theirs to choose: the canvas at 1000 %
zoom on a 150 % display, a 300-dpi PNG export, the minimap at 8 %, a printer at
1200 dpi. Until #785 every one of them was rasterised at **1 pixel per
centimetre of plan** whatever the painter, so anything above 100 % zoom was an
upscaled bitmap beside crisp vector outlines.

The rule, asked by every bitmap painter and stated nowhere else:

1. ``device_scale(painter)`` — the device pixels one item unit (1 cm) covers
   under the painter *right now*: its device transform (world scale, item and
   group rotation, mirroring, the device pixel ratio — all of it), the larger of
   the two axes.
2. ``raster_level(scale)`` — that scale rounded **up** to a power of two
   (``LEVEL_STEP``), so a bitmap is never shown larger than it was rasterised and
   is minified by less than ``LEVEL_STEP`` — and a smooth zoom re-rasterises
   once per doubling, not once per wheel step. The level is part of every cache
   key (through the pixel size it yields).

Two painters are not asked for their scale:

- a device finer than ``MAX_PRINT_DPI`` (a printer at 1200 dpi) is treated as
  that many dots per inch: a sprite on paper is rasterised at 300 dpi, not at
  the spool-filling resolution of the print head;
- a painter that *records* instead of rasterising (SVG, ``QPicture``) is
  replayed at a size nobody knows yet, so it keeps the 1 px per cm it always
  had (``RECORDED_SCALE``).

This module holds no cache and no pixmap: ``core.sprite_raster`` (sprites) and
``core.fill_patterns`` (fill tiles) apply the rule.
"""

from __future__ import annotations

import math
from typing import Final

from PyQt6.QtGui import QPaintEngine, QPainter

#: One level per doubling. Rounding UP means the bitmap is minified by a factor
#: in [1, 2) — bilinear filtering is alias-free there — and never magnified.
LEVEL_STEP: Final = 2.0

#: The coarsest and finest level. 1/16 px per cm is a 16-px tile for a 2.56 m
#: pattern (the minimap of a large plan); 256 px per cm is past the view's
#: maximum zoom (5000 %) on a 300 % display.
MIN_LEVEL: Final = 1.0 / 16.0
MAX_LEVEL: Final = 256.0

#: A scale this close above a level still takes that level: a 100 % view whose
#: transform carries float noise must not jump to the next one.
LEVEL_TOLERANCE: Final = 0.01

#: A paint device finer than this is rasterised for as if it had this many dots
#: per inch — bitmap detail past 300 dpi on paper is not visible and costs
#: (1200 / 300)² = 16 times the pixels.
MAX_PRINT_DPI: Final = 300.0

#: The scale a recording painter (SVG, QPicture) is given: the 1 px per cm every
#: bitmap had before #785.
RECORDED_SCALE: Final = 1.0

_RECORDING_ENGINES: Final = (QPaintEngine.Type.SVG, QPaintEngine.Type.Picture)


def raw_device_scale(painter: QPainter) -> float:
    """Device pixels per item unit under ``painter``'s current transform — the
    larger axis, signs dropped (a mirrored fill is as fine as an upright one).
    1.0 for a degenerate or non-finite transform."""
    transform = painter.deviceTransform()
    across = math.hypot(transform.m11(), transform.m12())
    along = math.hypot(transform.m21(), transform.m22())
    scale = max(across, along)
    if not math.isfinite(scale) or scale <= 0.0:
        return 1.0
    return scale


def device_scale(painter: QPainter) -> float:
    """The pixels per item unit a bitmap drawn through ``painter`` should have
    (module docstring): the painter's own scale, but 300 dpi at most on a finer
    device and ``RECORDED_SCALE`` on a recording one."""
    engine = painter.paintEngine()
    if engine is not None and engine.type() in _RECORDING_ENGINES:
        return RECORDED_SCALE
    scale = raw_device_scale(painter)
    device = painter.device()
    if device is not None:
        dpi = float(device.logicalDpiX())
        if dpi > MAX_PRINT_DPI:
            scale *= MAX_PRINT_DPI / dpi
    return scale


def raster_level(scale: float) -> float:
    """``scale`` rounded up to a level (a power of ``LEVEL_STEP``), within
    ``[MIN_LEVEL, MAX_LEVEL]``. A non-finite or non-positive scale is level 1."""
    if not math.isfinite(scale) or scale <= 0.0:
        return 1.0
    if scale <= MIN_LEVEL:
        return MIN_LEVEL
    exponent = math.ceil(math.log(scale, LEVEL_STEP) - LEVEL_TOLERANCE)
    return float(min(LEVEL_STEP**exponent, MAX_LEVEL))


def painter_level(painter: QPainter) -> float:
    """The level a bitmap drawn through ``painter`` is rasterised at."""
    return raster_level(device_scale(painter))


__all__ = [
    "LEVEL_STEP",
    "LEVEL_TOLERANCE",
    "MAX_LEVEL",
    "MAX_PRINT_DPI",
    "MIN_LEVEL",
    "RECORDED_SCALE",
    "device_scale",
    "painter_level",
    "raster_level",
    "raw_device_scale",
]
