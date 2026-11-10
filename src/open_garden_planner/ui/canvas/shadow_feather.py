"""Paint the soft edge of the sun shadow as a smooth falloff (#793).

``core.soft_edge`` holds the arithmetic and the reason; this module is the Qt
half. The shade is rasterised on the falloff's coarse lattice, the falloff is
computed there, and the result is enlarged into a layer in device pixels
(``core.sprite_raster.paint_layer``) in which the shade itself is cut out
again — at the device's resolution, with the shade's exact outline. So the
edge of the shade stays where its geometry puts it, the interior keeps its
flat tone, and no painter is handed a clip to honour: an SVG gets a picture,
not a ``<clipPath>`` its reader may ignore (PF-CAN-53).

The lattice is the plan's and the device scale's alone: anchored at the
item's origin, its pitch ``feather_grid`` of the painter's scale. What a paint
exposes decides which cells are computed, never where they lie — a field of
more than ``MAX_FIELD_CELLS`` is computed in bands of that many cells.

The layer is composed in four steps, all in device pixels (``paint_feather``):

1. the falloff's weight, enlarged, as a MASK in which the shade's own tone is
   half a byte (``falloff_pictures``);
2. the mask added to itself with saturation: the weight clamped to 1. This is
   what keeps sunlit ground in an inside corner, a cusp, a hole or a slot from
   being painted darker than the shade (``core.soft_edge``), and it is exact
   because it comes after the enlargement;
3. the shade's colour laid into the mask — one colour for a solid shade, the
   enlarged tone of the shade beside each place where its regions differ;
4. the shade cut out.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath

from open_garden_planner.core.raster_resolution import device_scale, raw_device_scale
from open_garden_planner.core.soft_edge import (
    FEATHER_REACH_CM,
    MASK_FULL_WEIGHT,
    MAX_FIELD_CELLS,
    FeatherGrid,
    feather_fields,
    feather_grid,
)
from open_garden_planner.core.sprite_raster import paint_layer

#: A region of the shade with its own tone: its outline and its occlusion (0..1).
ToneRegion = tuple[QPainterPath, float]

_COVERAGE = QColor(0, 255, 0)


def _channels(image: QImage) -> np.ndarray:
    """The pixels of an ARGB32 image as ``(rows, columns, 4)`` bytes: B, G, R, A."""
    bits = image.constBits()
    if bits is None:
        raise MemoryError("the falloff's raster could not be read")
    rows: np.ndarray = np.frombuffer(
        bits.asstring(image.sizeInBytes()), dtype=np.uint8
    ).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :]


def _premultiplied(color: QColor) -> np.ndarray:
    """``color`` at every alpha 0 to 255 as premultiplied ARGB32 pixels."""
    alpha = np.arange(256, dtype=np.uint32)
    pixel = alpha << 24
    for shift, value in ((16, color.red()), (8, color.green()), (0, color.blue())):
        pixel |= ((alpha * value + 127) // 255) << shift
    return pixel


def _picture(pixels: np.ndarray) -> QImage:
    """``pixels`` (rows of premultiplied ARGB32) as an image with its own memory."""
    rows, columns = pixels.shape
    picture = QImage(
        pixels.tobytes(), columns, rows, columns * 4, QImage.Format.Format_ARGB32_Premultiplied
    )
    return picture.copy()  # not the temporary buffer's


def falloff_pictures(
    shade: QPainterPath,
    tones: Sequence[ToneRegion],
    color: QColor,
    grid: FeatherGrid,
    cells: tuple[int, int, int, int],
) -> tuple[QImage, QImage | None] | None:
    """The falloff over the lattice cells ``(left, top, right, bottom)`` —
    right and bottom excluded — as two pictures, one pixel a cell: its weight
    as a mask, and its tint.

    ``shade`` is the whole shade; ``tones`` are its regions when they differ in
    tone (empty: the shade is one solid tone). ``color`` is the solid shade's
    colour and alpha.

    The **mask** holds the weight in its alpha, with the shade's own tone at
    half a byte (``core.soft_edge.MASK_FULL_WEIGHT``): inside the shade and in
    concave places it goes on rising, and the caller clamps it after enlarging
    it. The **tint** is the shade's colour at the tone of the shade beside each
    cell; ``None`` for a solid shade, whose tint is ``color`` everywhere. None
    altogether when there is no memory for the raster.
    """
    left, top, right, bottom = cells
    # what the blur reaches into the picture from outside it
    margin = grid.blur_cells + 1
    width, height = right - left + 2 * margin, bottom - top + 2 * margin
    raster = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    if raster.isNull():
        return None
    raster.fill(Qt.GlobalColor.transparent)
    painter = QPainter(raster)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        # coverage in green, tone in red; added, so two regions that share a
        # cell fill it together instead of the second covering the first
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.scale(1.0 / grid.cell_cm, 1.0 / grid.cell_cm)
        painter.translate(
            -(left - margin) * grid.cell_cm, -(top - margin) * grid.cell_cm
        )
        painter.fillPath(shade, _COVERAGE)
        for outline, occlusion in tones:
            painter.fillPath(
                outline, QColor(max(0, min(255, round(255.0 * occlusion))), 0, 0)
            )
    finally:
        painter.end()
    channels = _channels(raster)
    coverage = np.ascontiguousarray(channels[:, :, 1])
    strength = np.ascontiguousarray(channels[:, :, 2]) if tones else None
    weight, tone = feather_fields(coverage, grid, strength)
    inner = (slice(margin, -margin), slice(margin, -margin))
    per_byte = np.float32(255.0 / MASK_FULL_WEIGHT)
    mask = np.minimum(weight[inner] * per_byte + np.float32(0.5), np.float32(255.0))
    # black at that alpha: only the alpha is read (the tint brings the colour)
    mask_picture = _picture(mask.astype(np.uint32) << 24)
    if tone is None:
        return mask_picture, None
    alpha = np.minimum(
        tone[inner] * np.float32(color.alpha()) + np.float32(0.5), np.float32(255.0)
    ).astype(np.uint8)
    return mask_picture, _picture(_premultiplied(color)[alpha])


def paint_feather(
    painter: QPainter,
    bounds: QRectF,
    clip_rect: QRectF,
    shade: QPainterPath,
    tones: Sequence[ToneRegion],
    color: QColor,
) -> None:
    """Paint the falloff around ``shade`` inside ``clip_rect``, outside the shade.

    ``bounds`` is what the overlay paints in (its bounding rectangle). Nothing
    is painted where the falloff would be shorter than a pixel and a half.
    """
    if feather_grid(device_scale(painter)) is None:
        return

    def draw(layer: QPainter, target: QRectF) -> None:
        grid = feather_grid(raw_device_scale(layer))
        device = layer.device()
        to_item, invertible = layer.transform().inverted()
        if grid is None or device is None or not invertible:
            return
        # where there can be a falloff at all: on the device, on the canvas,
        # within reach of the shade
        near = FEATHER_REACH_CM + 2.0 * grid.cell_cm
        shown = (
            to_item.mapRect(QRectF(0.0, 0.0, device.width(), device.height()))
            .intersected(target)
            .intersected(clip_rect)
            .intersected(shade.boundingRect().adjusted(-near, -near, near, near))
        )
        if shown.isEmpty():
            return
        if not isinstance(device, QImage):
            return  # ``paint_layer`` hands out an image; nothing else can be read back
        cell = grid.cell_cm
        # one cell of margin: the enlargement reads a cell's neighbours
        left = math.floor(shown.left() / cell) - 1
        top = math.floor(shown.top() / cell) - 1
        right = math.ceil(shown.right() / cell) + 1
        bottom = math.ceil(shown.bottom() / cell) + 1
        # The field in bands of at most MAX_FIELD_CELLS, each on the one
        # lattice (module docstring); nearly always there is one band.
        rows = max(1, MAX_FIELD_CELLS // (right - left))
        to_device = layer.transform()

        def device_row(lattice_row: int) -> int:
            # where a band ends on the device: one expression for the band
            # above and the band below, so each pixel row is in exactly one
            return round(to_device.map(QPointF(0.0, lattice_row * cell)).y())

        layer.save()
        layer.setClipRect(clip_rect, Qt.ClipOperation.IntersectClip)
        layer.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for first in range(top, bottom, rows):
            last = min(first + rows, bottom)
            ends = sorted((device_row(first), device_row(last)))
            pixels = QRect(0, ends[0], device.width(), ends[1] - ends[0]).intersected(device.rect())
            if pixels.isEmpty():
                continue
            # ... with the row beyond each of its ends, for the enlargement
            cells = (left, max(top, first - 1), right, min(bottom, last + 1))
            pictures = falloff_pictures(shade, tones, color, grid, cells)
            if pictures is None:
                continue
            mask, tint = pictures
            # a cell's value is the falloff at its CENTRE: the pictures' pixel
            # centres lie on the cell centres
            field = QRectF(
                left * cell, cells[1] * cell, (right - left) * cell, (cells[3] - cells[1]) * cell
            )
            layer.save()
            layer.resetTransform()
            layer.setClipRect(pixels, Qt.ClipOperation.IntersectClip)
            layer.setTransform(to_device)
            # 1. the weight, enlarged: the shade's own tone is half a byte of alpha
            layer.drawImage(field, mask, QRectF(mask.rect()))
            # 2. ... added to itself, saturating: the weight clamped to the
            # shade's tone, pixel by pixel. After the enlargement — a clamp on
            # the lattice leaves a cell's width of ground darker than the shade
            # along every concave outline.
            layer.save()
            layer.resetTransform()            # the clip stays: it is the device's
            layer.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            layer.drawImage(pixels.topLeft(), device.copy(pixels))
            layer.restore()
            # 3. the shade's colour into the mask
            layer.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            if tint is None:
                layer.fillRect(field, color)
            else:
                layer.drawImage(field, tint, QRectF(tint.rect()))
            layer.restore()
        # 4. the shade itself is drawn by the overlay, with its own flat tone
        layer.setRenderHint(QPainter.RenderHint.Antialiasing)
        layer.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        layer.fillPath(shade, QColor(0, 0, 0))
        layer.restore()

    paint_layer(painter, bounds, draw)


__all__ = ["FEATHER_REACH_CM", "ToneRegion", "falloff_pictures", "paint_feather"]
