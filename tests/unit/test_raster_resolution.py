"""The one rule for the resolution of a bitmap (#785): ``core.raster_resolution``.

Every plant sprite, object sprite and fill tile asks these functions how fine
it must be, so what is pinned here holds for all of them at once.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QBuffer, QIODevice, QRectF, QSize
from PyQt6.QtGui import QImage, QPageSize, QPainter, QPdfWriter
from PyQt6.QtSvg import QSvgGenerator

from open_garden_planner.core.raster_resolution import (
    LEVEL_STEP,
    MAX_LEVEL,
    MAX_PRINT_DPI,
    MIN_LEVEL,
    RECORDED_SCALE,
    device_scale,
    painter_level,
    raster_level,
)


class TestRasterLevel:
    @pytest.mark.parametrize(
        ("scale", "level"),
        [
            (1.0, 1.0),
            (1.004, 1.0),  # float noise on a 100 % view stays at level 1
            (1.1, 2.0),
            (2.0, 2.0),
            (2.91, 4.0),  # the balcony example's fit zoom
            (4.0, 4.0),
            (9.53, 16.0),  # the raised-bed example at 953 %
            (0.56, 1.0),  # the family garden at fit
            (0.5, 1.0),
            (0.25, 1.0),  # where the owner works
            (0.08, 1.0),  # a minimap
        ],
    )
    def test_scale_rounds_up_to_a_power_of_two(self, scale: float, level: float) -> None:
        assert raster_level(scale) == level

    @pytest.mark.parametrize("scale", [1.0, 1.5, 3.9, 7.0, 37.0, 150.0])
    def test_a_bitmap_is_never_magnified_and_minified_by_less_than_one_step(
        self, scale: float
    ) -> None:
        level = raster_level(scale)
        # shown at scale / level of its own size: within (1 / step, 1] (+ tolerance)
        assert scale / level <= 1.0 + 0.01
        assert scale / level > 1.0 / LEVEL_STEP

    @pytest.mark.parametrize("scale", [0.02, 0.1, 0.25, 0.56, 0.99])
    def test_below_100_percent_a_bitmap_is_the_one_it_always_was(self, scale: float) -> None:
        """Zoomed out, the look is not this rule's to change (``MIN_LEVEL``): a
        coarser level would trade the moire for the contrast a texture reads by."""
        assert raster_level(scale) == MIN_LEVEL == 1.0

    def test_levels_are_bounded(self) -> None:
        assert raster_level(1e-9) == MIN_LEVEL
        assert raster_level(1e9) == MAX_LEVEL

    @pytest.mark.parametrize("bad", [0.0, -3.0, math.nan, math.inf, -math.inf])
    def test_a_degenerate_scale_is_level_one(self, bad: float) -> None:
        assert raster_level(bad) == 1.0

    def test_a_zoom_sweep_visits_one_level_per_doubling(self) -> None:
        """The cache stays small because the levels are few: 1 % to 5000 % zoom
        on a 300 % display is a factor of 15000 and at most 14 levels."""
        levels = {raster_level(0.01 * 1.1**step * 3.0) for step in range(0, 90)}
        assert len(levels) <= 14


def _image(width: int = 64, height: int = 64, ratio: float = 1.0) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    return image


class TestDeviceScale:
    def test_identity_is_one_pixel_per_unit(self, qtbot) -> None:
        image = _image()
        painter = QPainter(image)
        assert device_scale(painter) == pytest.approx(1.0)
        assert painter_level(painter) == 1.0
        painter.end()

    @pytest.mark.parametrize("zoom", [0.25, 1.0, 4.0, 9.53])
    @pytest.mark.parametrize("rotation", [0.0, 30.0, 90.0, 217.0])
    @pytest.mark.parametrize("mirror", [(1.0, 1.0), (1.0, -1.0), (-1.0, 1.0)])
    def test_zoom_is_read_through_rotation_and_mirroring(
        self, qtbot, zoom: float, rotation: float, mirror: tuple[float, float]
    ) -> None:
        """A defect proportional to rotation is zero at rotation 0: the scale
        of a rotated item (or one in a rotated group, or a flipped fill) is the
        scale, not a component of it."""
        image = _image()
        painter = QPainter(image)
        painter.scale(zoom, zoom)
        painter.rotate(rotation)
        painter.scale(*mirror)
        assert device_scale(painter) == pytest.approx(zoom, rel=1e-9)
        painter.end()

    def test_the_larger_axis_wins(self, qtbot) -> None:
        image = _image()
        painter = QPainter(image)
        painter.scale(2.0, 5.0)
        assert device_scale(painter) == pytest.approx(5.0)
        painter.end()

    def test_the_device_pixel_ratio_counts(self, qtbot) -> None:
        """100 % zoom on a 200 % display is two device pixels per cm."""
        image = _image(ratio=2.0)
        painter = QPainter(image)
        painter.scale(1.5, 1.5)
        assert device_scale(painter) == pytest.approx(3.0)
        assert painter_level(painter) == 4.0
        painter.end()

    def test_a_printer_is_rasterised_for_at_300_dpi(self, qtbot) -> None:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        writer = QPdfWriter(buffer)
        writer.setResolution(1200)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        painter = QPainter(writer)
        painter.scale(8.0, 8.0)  # 8 device dots per cm of plan at 1200 dpi
        assert device_scale(painter) == pytest.approx(8.0 * MAX_PRINT_DPI / 1200.0)
        painter.end()

    def test_a_300_dpi_device_is_not_reduced(self, qtbot) -> None:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        writer = QPdfWriter(buffer)
        writer.setResolution(300)
        painter = QPainter(writer)
        painter.scale(3.0, 3.0)
        assert device_scale(painter) == pytest.approx(3.0)
        painter.end()

    def test_a_recording_painter_keeps_one_pixel_per_cm(self, qtbot) -> None:
        """A painter on a ``QSvgGenerator`` is replayed at a size nobody knows:
        its bitmaps stay as they were before #785. (The app's SVG export paints
        on its own recording device, which states its scale —
        ``tests/integration/test_canvas_sharpness.py``.)"""
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        generator = QSvgGenerator()
        generator.setOutputDevice(buffer)
        generator.setSize(QSize(400, 300))
        generator.setViewBox(QRectF(0, 0, 400, 300))
        painter = QPainter(generator)
        painter.scale(7.0, 7.0)
        assert device_scale(painter) == RECORDED_SCALE
        assert painter_level(painter) == 1.0
        painter.end()
