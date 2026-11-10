"""Paint the soft edge of the sun shadow as a smooth falloff (#793).

``core.soft_edge`` holds the arithmetic and the reason; this module is the Qt
half. The shade is rasterised on the falloff's coarse lattice, the falloff is
computed there, and the result is enlarged into a layer in device pixels
(``core.sprite_raster.paint_layer``) in which the shade itself is cut out
again — at the device's resolution, with the shade's exact outline. So the
edge of the shade stays where its geometry puts it, the interior keeps its
flat tone, and no painter is handed a clip to honour: an SVG gets a picture,
not a ``<clipPath>`` its reader may ignore (PF-CAN-53).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath

from open_garden_planner.core.raster_resolution import device_scale, raw_device_scale
from open_garden_planner.core.soft_edge import (
    FEATHER_REACH_CM,
    MAX_FIELD_CELLS,
    FeatherGrid,
    feather_grid,
    feather_weight,
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


def falloff_image(
    shade: QPainterPath,
    tones: Sequence[ToneRegion],
    color: QColor,
    grid: FeatherGrid,
    cells: tuple[int, int, int, int],
) -> QImage | None:
    """The falloff over the lattice cells ``(left, top, right, bottom)`` —
    right and bottom excluded — as a premultiplied picture, one pixel a cell.

    ``shade`` is the whole shade; ``tones`` are its regions when they differ in
    tone (empty: the shade is one solid tone). ``color`` is the solid shade's
    colour and alpha. Inside the shade the picture goes on getting darker
    (``core.soft_edge.MAX_WEIGHT``): the caller cuts the shade out. None when
    there is no memory for it.
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
    weight = feather_weight(coverage, grid, strength)[margin:-margin, margin:-margin]
    alpha = np.minimum(
        weight * np.float32(color.alpha()) + np.float32(0.5), np.float32(255.0)
    ).astype(np.uint8)
    pixels = _premultiplied(color)[alpha]
    picture = QImage(
        pixels.tobytes(), right - left, bottom - top, (right - left) * 4,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    return picture.copy()  # its own memory, not the temporary buffer's


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
        # one cell of margin: the enlargement reads a cell's neighbours
        span = (shown.width() / grid.cell_cm + 2.0) * (shown.height() / grid.cell_cm + 2.0)
        if span > MAX_FIELD_CELLS:
            grid = grid.coarser(math.sqrt(span / MAX_FIELD_CELLS))
        cell = grid.cell_cm
        cells = (
            math.floor(shown.left() / cell) - 1,
            math.floor(shown.top() / cell) - 1,
            math.ceil(shown.right() / cell) + 1,
            math.ceil(shown.bottom() / cell) + 1,
        )
        picture = falloff_image(shade, tones, color, grid, cells)
        if picture is None:
            return
        layer.save()
        layer.setClipRect(clip_rect, Qt.ClipOperation.IntersectClip)
        layer.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # a cell's value is the falloff at its CENTRE: the picture's pixel
        # centres lie on the cell centres
        layer.drawImage(
            QRectF(
                cells[0] * cell, cells[1] * cell,
                (cells[2] - cells[0]) * cell, (cells[3] - cells[1]) * cell,
            ),
            picture,
            QRectF(picture.rect()),
        )
        # the shade itself is drawn by the overlay, with its own flat tone
        layer.setRenderHint(QPainter.RenderHint.Antialiasing)
        layer.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        layer.fillPath(shade, QColor(0, 0, 0))
        layer.restore()

    paint_layer(painter, bounds, draw)


__all__ = ["FEATHER_REACH_CM", "ToneRegion", "falloff_image", "paint_feather"]
