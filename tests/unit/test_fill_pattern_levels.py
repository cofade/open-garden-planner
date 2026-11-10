"""Fill tiles by level (#785): the detail tile above 100 %, the 256-px tile at
100 % and below — and always the same picture in the same place.

The levels are ``core.fill_patterns``' (its module docstring); the rule that
picks one is ``core.raster_resolution``'s.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QTransform

from open_garden_planner.core import fill_patterns
from open_garden_planner.core.fill_patterns import (
    DETAIL_LEVEL,
    LEVEL_TILE_CACHE_MAX_BYTES,
    FillPattern,
    FillTransform,
    brush_for_painter,
    clear_texture_cache,
    create_pattern_brush,
    level_tile,
    tile_level,
)

_ROOT = Path(__file__).resolve().parents[2]
_TEXTURES = _ROOT / "src" / "open_garden_planner" / "resources" / "textures"
_TEXTURED = [pattern for pattern in FillPattern if pattern is not FillPattern.SOLID]
_GREEN = QColor(96, 150, 70)

_spec = importlib.util.spec_from_file_location(
    "check_texture_tileability", _ROOT / "scripts" / "check_texture_tileability.py"
)
assert _spec is not None and _spec.loader is not None
tileability = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("check_texture_tileability", tileability)
_spec.loader.exec_module(tileability)


@pytest.fixture(autouse=True)
def _fresh_caches(qtbot):
    clear_texture_cache()
    yield
    clear_texture_cache()


def _rgb(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :3].astype(np.float64).copy()


def _fill(brush: QBrush, scale: float, size: int = 240, *, rotation: float = 0.0,
          mirror: float = 1.0, ratio: float = 1.0, refine: bool = True) -> np.ndarray:
    """A plane filled with ``brush`` under a painter at ``scale`` px per cm —
    refined for that painter the way every fill painter does it."""
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.setDevicePixelRatio(ratio)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.scale(scale / ratio, scale / ratio * mirror)
    painter.rotate(rotation)
    if refine:
        brush = brush_for_painter(brush, painter) or brush
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(brush)
    painter.drawRect(QRectF(-5000, -5000, 10000, 10000))
    painter.end()
    return _rgb(image)


def _box(pixels: np.ndarray, factor: int) -> np.ndarray:
    height, width = pixels.shape[0] // factor, pixels.shape[1] // factor
    cut = pixels[: height * factor, : width * factor]
    return cut.reshape(height, factor, width, factor, -1).mean(axis=(1, 3))


def _gradient_energy(pixels: np.ndarray) -> float:
    lum = pixels @ np.array([0.299, 0.587, 0.114])
    return float((np.diff(lum, axis=1) ** 2).mean() + (np.diff(lum, axis=0) ** 2).mean())


class TestTileLevel:
    @pytest.mark.parametrize(
        ("scale", "level"),
        [(1.0, 1.0), (1.5, 2.0), (2.0, 2.0), (9.5, 2.0), (0.56, 1.0), (0.3, 1.0),
         (0.12, 1.0), (0.001, 1.0)],
    )
    def test_a_fill_takes_the_level_its_scale_calls_for(self, scale: float, level: float) -> None:
        assert tile_level(scale) == level

    def test_the_finest_tile_is_the_detail_tile(self) -> None:
        assert DETAIL_LEVEL == 2.0 and tile_level(1000.0) == DETAIL_LEVEL


class TestHundredPercentAndBelowIsUnchanged:
    """What a fill looks like at 100 % zoom — and zoomed out — must not move by
    one level of one pixel: there the brush is the brush it always was."""

    @pytest.mark.parametrize("pattern", _TEXTURED, ids=lambda p: p.name)
    @pytest.mark.parametrize("scale", [1.0, 0.56, 0.25, 0.1])
    def test_the_brush_is_left_alone(self, pattern: FillPattern, scale: float) -> None:
        brush = create_pattern_brush(pattern, _GREEN)
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        painter.scale(scale, scale)
        refined = brush_for_painter(brush, painter)
        painter.end()
        assert refined is None

    @pytest.mark.parametrize("rotation", [0.0, 30.0])
    @pytest.mark.parametrize("scale", [1.0, 0.25])
    def test_pixels_are_identical(self, rotation: float, scale: float) -> None:
        brush = create_pattern_brush(FillPattern.BRICK, _GREEN,
                                     FillTransform(angle_deg=20.0, offset_x_cm=7.0))
        refined = _fill(brush, scale, rotation=rotation)
        plain = _fill(brush, scale, rotation=rotation, refine=False)
        assert np.array_equal(refined, plain)

    def test_a_solid_brush_and_a_foreign_texture_are_left_alone(self) -> None:
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        painter.scale(4.0, 4.0)
        assert brush_for_painter(QBrush(_GREEN), painter) is None
        foreign = QImage(16, 16, QImage.Format.Format_RGB32)
        foreign.fill(_GREEN)
        assert brush_for_painter(QBrush(foreign), painter) is None
        painter.end()


class TestDetailTile:
    @pytest.mark.parametrize("pattern", _TEXTURED, ids=lambda p: p.name)
    def test_every_pattern_has_one_and_it_is_the_same_picture(self, pattern: FillPattern) -> None:
        """The 256-px tile is the 2x2 box average of the detail tile — tinted
        too, because both are normalised with the same mean."""
        base = _rgb(create_pattern_brush(pattern, _GREEN).textureImage())
        detail = level_tile(pattern, _GREEN, DETAIL_LEVEL)
        assert detail is not None and detail.width() == detail.height() == 512
        difference = np.abs(_box(_rgb(detail.toImage()), 2) - base)
        # Rounding of the two tiles and of the tint (measured: mean 0.23-0.53).
        # Only a highlight the tint clips at 255 differs by more — it is clipped
        # per detail pixel, before the average — and that is under 1 % of a tile
        # (compost's eggshell flecks are the most: 99th percentile 1.5).
        assert difference.mean() < 0.6, difference.mean()
        assert np.percentile(difference, 99.0) <= 2.5, np.percentile(difference, 99.0)

    @pytest.mark.parametrize("pattern", _TEXTURED, ids=lambda p: p.name)
    def test_it_tiles(self, pattern: FillPattern) -> None:
        """A seam at the tile border is a failure: the detail tile passes the
        gate the 256-px tile passes (``scripts/check_texture_tileability.py``)."""
        from PIL import Image

        name = fill_patterns._TEXTURE_FILES[pattern]
        with Image.open(_TEXTURES / "x2" / f"{name}.png") as image:
            assert image.size == (512, 512) and image.mode == "RGB"
            across, along = tileability.seam_ratios(image)
        assert max(across, along) <= tileability.SEAM_RATIO_THRESHOLD, (name, across, along)

    def test_an_opaque_colour_keeps_an_opaque_tile(self) -> None:
        """A per-pixel alpha channel would make every textured item blend on
        every repaint (NFR-PERF-01): an opaque fill's tile has none, at any level."""
        assert not level_tile(FillPattern.GRASS, _GREEN, DETAIL_LEVEL).hasAlphaChannel()
        translucent = QColor(96, 150, 70, 120)
        tile = level_tile(FillPattern.GRASS, translucent, DETAIL_LEVEL)
        assert tile.hasAlphaChannel()
        alpha = tile.toImage().convertToFormat(QImage.Format.Format_ARGB32).pixelColor(3, 3)
        assert alpha.alpha() == 120

    def test_there_is_no_other_level(self) -> None:
        for level in (1.0, 0.5, 4.0):
            assert level_tile(FillPattern.GRASS, _GREEN, level) is None
        assert level_tile(FillPattern.SOLID, _GREEN, DETAIL_LEVEL) is None

    def test_a_missing_detail_file_keeps_the_tile(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(fill_patterns, "_DETAIL_DIR", tmp_path)
        brush = create_pattern_brush(FillPattern.GRASS, _GREEN)
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        painter.scale(4.0, 4.0)
        assert brush_for_painter(brush, painter) is None
        painter.end()


class TestSharpWhenZoomedIn:
    @pytest.mark.parametrize("pattern", [FillPattern.GRASS, FillPattern.SOIL, FillPattern.WOOD,
                                         FillPattern.BRICK, FillPattern.CONCRETE],
                             ids=lambda p: p.name)
    @pytest.mark.parametrize("rotation", [0.0, 30.0])
    @pytest.mark.parametrize("scale", [2.0, 4.0, 10.0])
    def test_a_fill_carries_more_detail_than_the_upscaled_tile(
        self, pattern: FillPattern, rotation: float, scale: float
    ) -> None:
        """Gradient energy against the fill as it was painted before #785 (the
        256-px tile, upscaled by the painter). Measured 1.58-2.96 for these
        five; the regression — no refinement — reads 1.00."""
        brush = create_pattern_brush(pattern, _GREEN)
        refined = _gradient_energy(_fill(brush, scale, rotation=rotation))
        upscaled = _gradient_energy(_fill(brush, scale, rotation=rotation, refine=False))
        assert refined > 1.4 * upscaled, (refined, upscaled)

    @pytest.mark.parametrize("pattern", _TEXTURED, ids=lambda p: p.name)
    def test_every_pattern_gains(self, pattern: FillPattern) -> None:
        """All 24, the smooth ones too (water and stone gain least: 1.15)."""
        brush = create_pattern_brush(pattern, _GREEN)
        refined = _gradient_energy(_fill(brush, 4.0))
        upscaled = _gradient_energy(_fill(brush, 4.0, refine=False))
        assert refined > 1.1 * upscaled, (refined, upscaled)

    def test_a_high_density_display_counts_as_zoom(self) -> None:
        """100 % zoom at a device pixel ratio of 2 is two pixels per cm."""
        brush = create_pattern_brush(FillPattern.GRASS, _GREEN)
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        image.setDevicePixelRatio(2.0)
        painter = QPainter(image)
        refined = brush_for_painter(brush, painter)
        painter.end()
        assert refined is not None and refined.texture().width() == 512


class TestSamePictureSamePlace:
    """A refined fill is the fill it replaces, finer: averaged back down it is
    that fill, under every transform a brush can carry."""

    @pytest.mark.parametrize(
        "transform",
        [None, FillTransform(angle_deg=33.0), FillTransform(scale=1.7),
         FillTransform(offset_x_cm=13.0, offset_y_cm=-41.0),
         FillTransform(angle_deg=-70.0, scale=0.6, offset_x_cm=5.0, offset_y_cm=9.0)],
        ids=["identity", "angle", "scale", "offset", "all"],
    )
    @pytest.mark.parametrize("rotation", [0.0, 30.0])
    @pytest.mark.parametrize("mirror", [1.0, -1.0])
    def test_the_detail_level_averages_back_to_the_tile(
        self, transform: FillTransform | None, rotation: float, mirror: float
    ) -> None:
        brush = create_pattern_brush(FillPattern.BRICK, _GREEN, transform)
        # painted at 4 px per cm and averaged 4x4: one value per cm either way
        refined = _box(_fill(brush, 4.0, 640, rotation=rotation, mirror=mirror), 4)
        plain = _box(_fill(brush, 4.0, 640, rotation=rotation, mirror=mirror, refine=False), 4)

        def error(dx: int, dy: int) -> float:
            moved = np.roll(np.roll(plain, dy, axis=0), dx, axis=1)
            return float(np.sqrt(((refined[2:-2, 2:-2] - moved[2:-2, 2:-2]) ** 2).mean()))

        here = error(0, 0)
        # Where it is, the two differ by the upscaled tile's own blur (measured
        # 3.1, 5.3 for a tile drawn 1.7 times larger); one centimetre off in any
        # direction they differ by 12-26.
        for one, other in ((error(1, 0), error(-1, 0)), (error(0, 1), error(0, -1))):
            assert here < 0.6 * min(one, other), (here, one, other)
            # ... and half a centimetre off would favour one side: the two sides
            # of the right place are as wrong as each other (measured within 4 %
            # over this 1.6 m window; half a centimetre off reads 50 % and more).
            assert abs(one - other) < 0.12 * max(one, other), (one, other)

    def test_a_brush_stretch_is_part_of_the_scale(self) -> None:
        """A pattern drawn twice as large shows each texture pixel on two
        device pixels at 100 % zoom: it needs the detail tile there already."""
        brush = create_pattern_brush(FillPattern.GRASS, _GREEN, FillTransform(scale=2.0))
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        refined = brush_for_painter(brush, painter)
        painter.end()
        assert refined is not None and refined.texture().width() == 512
        assert refined.transform().m11() == pytest.approx(1.0)  # 2.0 / level 2

    def test_the_ridge_frame_survives(self) -> None:
        """roof_paint replaces the brush transform with its ridge frame, then
        refines: the frame (a turn, a mirror) is kept under the 1 / level scale."""
        brush = create_pattern_brush(FillPattern.ROOF_TILES, _GREEN)
        frame = QTransform().translate(40.0, 25.0).rotate(37.0).scale(1.0, -1.0)
        brush.setTransform(frame)
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        painter.scale(3.0, 3.0)
        refined = brush_for_painter(brush, painter)
        painter.end()
        assert refined is not None
        assert refined.transform() == QTransform.fromScale(0.5, 0.5) * frame


class TestCacheBound:
    def test_level_tiles_are_bounded_in_bytes(self) -> None:
        """Every colour of every pattern at every level cannot outgrow the
        stated budget (48 MB): a level-2 tile is 1 MB."""
        assert LEVEL_TILE_CACHE_MAX_BYTES == 48 * 1024 * 1024
        cache = fill_patterns._level_tiles
        for shade in range(60):
            color = QColor(40 + shade * 3, 120, 60)
            for pattern in (FillPattern.GRASS, FillPattern.SOIL):
                assert level_tile(pattern, color, DETAIL_LEVEL) is not None
                assert cache.bytes_used <= LEVEL_TILE_CACHE_MAX_BYTES
        assert cache.bytes_used <= LEVEL_TILE_CACHE_MAX_BYTES
        assert len(cache) <= 48  # 1 MB each

    def test_a_tile_is_made_once(self) -> None:
        first = level_tile(FillPattern.GRASS, _GREEN, DETAIL_LEVEL)
        second = level_tile(FillPattern.GRASS, _GREEN, DETAIL_LEVEL)
        assert first.cacheKey() == second.cacheKey()

    def test_clearing_the_texture_cache_drops_the_levels(self) -> None:
        level_tile(FillPattern.GRASS, _GREEN, DETAIL_LEVEL)
        clear_texture_cache()
        assert len(fill_patterns._level_tiles) == 0
        assert fill_patterns._brush_tiles == {}
