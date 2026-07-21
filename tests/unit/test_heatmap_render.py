"""Unit tests for the Qt-free heatmap rendering helpers (US-E4 redesign).

Pins the sun ramp LUT (monotone dark→light, alpha fading out toward full sun)
and the marching-squares iso-contour extractor on hand-computable grids.
"""

from __future__ import annotations

import numpy as np

from open_garden_planner.core.heatmap_render import (
    build_sun_lut,
    hour_levels,
    iso_segments,
    sun_fraction,
)


class TestSunLut:
    def test_shape_and_dtype(self) -> None:
        lut = build_sun_lut(256)
        assert lut.shape == (256, 4)
        assert lut.dtype == np.uint8

    def test_brightness_increases_with_sun(self) -> None:
        """Fewer sun hours (low index) render darker; more render lighter.

        uint8 rounding adds ±1 noise between adjacent indices (and the teal→green
        stretch is near-flat in luminance), so assert the ramp's ENVELOPE and its
        control stops rise — not strict step-by-step monotonicity.
        """
        lut = build_sun_lut(256)
        luminance = lut[:, :3].astype(int).sum(axis=1)
        assert luminance[0] < luminance[-1]
        assert int(luminance.argmin()) == 0, "deep shade must be the darkest"
        assert int(luminance.argmax()) == len(luminance) - 1, (
            "full sun must be the brightest"
        )
        stops = luminance[[0, 70, 140, 205, 255]]
        assert np.all(np.diff(stops) >= 0), "luminance rises across the ramp"

    def test_alpha_fades_toward_full_sun(self) -> None:
        """Deep shade is the most opaque; full sun is nearly transparent."""
        lut = build_sun_lut(256)
        alpha = lut[:, 3].astype(int)
        assert alpha[0] > alpha[-1]
        assert int(alpha.argmax()) == 0, "deep shade must be the most opaque"
        assert int(alpha.argmin()) == len(alpha) - 1, (
            "full sun must be the most transparent"
        )


class TestSunFraction:
    def test_normalizes_and_clamps(self) -> None:
        minutes = np.array([[0.0, 240.0], [480.0, 600.0]], dtype=np.float32)
        frac = sun_fraction(minutes, 480.0)
        assert frac[0, 0] == 0.0
        assert frac[0, 1] == 0.5
        assert frac[1, 0] == 1.0
        assert frac[1, 1] == 1.0  # clamped

    def test_zero_daylight_is_all_shade(self) -> None:
        minutes = np.array([[0.0, 100.0]], dtype=np.float32)
        frac = sun_fraction(minutes, 0.0)
        assert np.all(frac == 0.0)


class TestHourLevels:
    def test_excludes_the_maximum(self) -> None:
        # 540 min = 9 h exactly → the 9 h line has no cell above it.
        assert hour_levels(540.0) == [60, 120, 180, 240, 300, 360, 420, 480]

    def test_partial_hour(self) -> None:
        assert hour_levels(200.0) == [60, 120, 180]

    def test_below_one_hour(self) -> None:
        assert hour_levels(45.0) == []


class TestIsoSegments:
    def test_vertical_contour_on_a_column_ramp(self) -> None:
        """grid[r, c] = c*100 → a threshold of 150 crosses between columns 1
        and 2, so every segment lies on the vertical line x = 1.5."""
        grid = np.tile(np.arange(5) * 100.0, (5, 1)).astype(np.float32)
        segments = iso_segments(grid, 150.0)
        assert segments, "a straddling threshold must yield segments"
        for (x1, _), (x2, _) in segments:
            assert x1 == 150.0 / 100.0  # linear crossing at col 1.5
            assert x2 == 150.0 / 100.0

    def test_no_crossing_returns_empty(self) -> None:
        grid = np.full((4, 4), 300.0, dtype=np.float32)
        assert iso_segments(grid, 150.0) == []

    def test_degenerate_grid_is_safe(self) -> None:
        assert iso_segments(np.zeros((1, 5), dtype=np.float32), 0.0) == []
