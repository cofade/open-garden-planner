"""Unit tests for the Qt-free heatmap rendering helpers (US-E4 redesign).

Pins the sun ramp LUT (monotone dark→light, alpha fading out toward full sun)
and the marching-squares iso-contour extractor on hand-computable grids.
"""

from __future__ import annotations

import numpy as np

from open_garden_planner.core.heatmap_render import (
    build_sun_lut,
    hour_is_labelled,
    hour_levels,
    iso_segments,
    label_candidates_along,
    label_points_along,
    ramp_index,
    smooth_field,
    stitch_segments,
    sun_fraction,
    sun_legend,
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
        # The design's selling point: full sun is nearly transparent (the
        # garden shows through), deep shade clearly reads as shade.
        assert alpha[-1] < 60, "full sun must be nearly transparent"
        assert alpha[0] > 120, "deep shade must be clearly visible"


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


class TestSmoothField:
    def test_preserves_shape_and_constant(self) -> None:
        grid = np.full((6, 8), 300.0, dtype=np.float32)
        out = smooth_field(grid, passes=3)
        assert out.shape == grid.shape
        assert np.allclose(out, 300.0)  # a flat field is unchanged

    def test_zero_passes_is_a_copy(self) -> None:
        grid = np.array([[0.0, 600.0]], dtype=np.float32)
        out = smooth_field(grid, passes=0)
        assert np.array_equal(out, grid)
        assert out is not grid

    def test_softens_a_step_edge(self) -> None:
        """A hard 0|600 step is spread into intermediate values, but the
        left→right ramp direction is preserved (no overshoot)."""
        row = np.where(np.arange(10) < 5, 0.0, 600.0)
        grid = np.tile(row, (5, 1)).astype(np.float32)
        out = smooth_field(grid, passes=2)
        profile = out[2, :]
        assert ((profile > 0.0) & (profile < 600.0)).any(), "edge not softened"
        assert np.all(np.diff(profile) >= -1e-4), "blur must not overshoot"
        assert profile.min() >= 0.0 and profile.max() <= 600.0


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

    def test_saddle_splits_into_two_segments(self) -> None:
        """Diagonally-opposite corners above the threshold => all four edges
        cross; the saddle resolves to two segments (top-left / right-bottom),
        each crossing at an edge midpoint."""
        grid = np.array([[600.0, 0.0], [0.0, 600.0]], dtype=np.float32)
        segments = iso_segments(grid, 300.0)
        assert len(segments) == 2
        points = {p for seg in segments for p in seg}
        assert points == {(0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)}


class TestStitchSegments:
    def test_open_curve_is_one_polyline(self) -> None:
        segments = [((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (2.0, 0.0))]
        polylines = stitch_segments(segments)
        assert len(polylines) == 1
        assert polylines[0][0] == (0.0, 0.0)
        assert polylines[0][-1] == (2.0, 0.0)
        assert len(polylines[0]) == 3

    def test_closed_loop_is_one_component(self) -> None:
        corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        segments = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
        polylines = stitch_segments(segments)
        assert len(polylines) == 1
        assert set(polylines[0]) == set(corners)  # visits every corner
        assert polylines[0][0] == polylines[0][-1]  # and closes

    def test_two_disjoint_loops(self) -> None:
        a = [((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (0.0, 0.0))]
        b = [((5.0, 5.0), (6.0, 5.0)), ((6.0, 5.0), (5.0, 5.0))]
        assert len(stitch_segments(a + b)) == 2


class TestLabelPointsAlong:
    def test_even_spacing_along_a_line(self) -> None:
        out = label_points_along([(0.0, 0.0), (10.0, 0.0)], spacing=5.0)
        assert out == [(2.5, 0.0), (7.5, 0.0)]

    def test_short_component_gets_exactly_one(self) -> None:
        out = label_points_along([(0.0, 0.0), (1.0, 0.0)], spacing=100.0)
        assert len(out) == 1

    def test_single_point_is_returned(self) -> None:
        assert label_points_along([(3.0, 4.0)], spacing=5.0) == [(3.0, 4.0)]


class TestLabelCandidatesAlong:
    """A label takes the evenly spaced place, or the nearest free one (#794)."""

    def test_the_first_candidate_is_the_evenly_spaced_place(self) -> None:
        line = [(0.0, 0.0), (10.0, 0.0)]
        places = label_candidates_along(line, spacing=5.0, step=1.0)
        assert [group[0] for group in places] == label_points_along(line, spacing=5.0)

    def test_the_others_lie_along_the_line_nearest_first(self) -> None:
        (places,) = label_candidates_along([(0.0, 0.0), (10.0, 0.0)], spacing=10.0, step=1.0)
        assert places[0] == (5.0, 0.0)
        away = [abs(x - 5.0) for x, _y in places]
        assert away == sorted(away)
        assert {y for _x, y in places} == {0.0}
        assert min(x for x, _y in places) >= 0.0 and max(x for x, _y in places) <= 10.0

    def test_no_candidate_strays_into_the_next_labels_stretch(self) -> None:
        first, second = label_candidates_along([(0.0, 0.0), (20.0, 0.0)], spacing=10.0, step=1.0)
        assert max(x for x, _y in first) < 10.0 <= min(x for x, _y in second)

    def test_it_follows_a_bend(self) -> None:
        (places,) = label_candidates_along(
            [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0)], spacing=8.0, step=1.0)
        assert places[0] == (4.0, 0.0)
        assert (3.0, 0.0) in places and (4.0, 1.0) in places

    def test_a_degenerate_line_has_its_one_place(self) -> None:
        assert label_candidates_along([(3.0, 4.0)], spacing=5.0, step=1.0) == [[(3.0, 4.0)]]
        assert label_candidates_along([(1.0, 1.0), (1.0, 1.0)], spacing=5.0, step=1.0) == [[(1.0, 1.0)]]


class TestSunLegend:
    """The key of the map is made of what the map is made of (#794)."""

    def test_no_daylight_no_key(self) -> None:
        assert sun_legend(0.0) is None
        assert sun_legend(float("nan")) is None

    def test_the_bar_is_the_maps_ramp_row_for_row(self) -> None:
        legend = sun_legend(16.5 * 60)
        assert legend is not None
        lut = build_sun_lut()
        assert len(legend.colors) == lut.shape[0]
        assert np.array_equal(np.array(legend.colors, dtype=np.uint8), lut)

    def test_a_tick_at_no_sun_and_at_every_hour_the_map_contours(self) -> None:
        daylight = 16.5 * 60
        legend = sun_legend(daylight)
        assert legend is not None
        assert [tick.hour for tick in legend.ticks] == [0] + [
            minutes // 60 for minutes in hour_levels(daylight)
        ]
        for tick in legend.ticks:
            assert tick.position == tick.hour * 60 / daylight
            assert 0.0 <= tick.position < 1.0

    def test_the_numbered_hours_are_the_numbered_contours(self) -> None:
        legend = sun_legend(16.5 * 60)
        assert legend is not None
        for tick in legend.ticks:
            assert tick.labelled == hour_is_labelled(tick.hour)
        assert [tick.hour for tick in legend.ticks if tick.labelled] == [0, 2, 4, 6, 8, 10, 12, 14, 16]

    def test_a_winter_day_has_a_shorter_scale_not_other_colours(self) -> None:
        summer, winter = sun_legend(16.5 * 60), sun_legend(7.5 * 60)
        assert summer is not None and winter is not None
        assert winter.colors == summer.colors
        assert [tick.hour for tick in winter.ticks] == [0, 1, 2, 3, 4, 5, 6, 7]

    def test_the_colour_of_an_hour_is_the_colour_the_map_gives_it(self) -> None:
        """The drift guard: the map's pixels and the legend look their tint up
        through one function (``ramp_index``) in one table."""
        daylight = 16.5 * 60
        legend = sun_legend(daylight)
        assert legend is not None
        lut = build_sun_lut()
        minutes = np.linspace(-30.0, daylight + 90.0, 487)
        rows = ramp_index(sun_fraction(minutes, daylight), lut.shape[0])
        for value, row in zip(minutes.tolist(), rows.tolist(), strict=True):
            assert legend.color_at(value) == tuple(int(channel) for channel in lut[row])

    def test_the_ramp_is_stated_in_one_place(self) -> None:
        """Nobody but ``core/heatmap_render`` holds a colour of the ramp: a
        second table is how a legend and its map come to disagree."""
        import re
        from pathlib import Path

        import open_garden_planner

        root = Path(open_garden_planner.__file__).parent
        stops = re.compile(r"_SUN_RAMP_STOPS")
        users = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if stops.search(path.read_text(encoding="utf-8"))
        )
        assert users == ["core/heatmap_render.py"]
        # ... and its indigo and amber ends appear as literals nowhere else
        ends = re.compile(r"\b39\s*,\s*46\s*,\s*92\b|\b250\s*,\s*233\s*,\s*181\b")
        holders = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if ends.search(path.read_text(encoding="utf-8"))
        )
        assert holders == ["core/heatmap_render.py"]
