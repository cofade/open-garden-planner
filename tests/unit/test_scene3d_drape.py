"""The 2D sun analysis draped over the 3D ground (Phase 17 L2.1, #386).

``core/scene3d/drape.py`` lays the canvas's two sun maps on the 3D ground as one mesh
each. Held here to what the canvas shows: the hours-of-sun map's row 0 is the SOUTH
edge (pinned the canvas's way, by where a value lands), its colours are the
canvas's ramp in linear light, the shadow drape covers exactly the area the overlay
paints inside the plan, and the probe names the cell the canvas draws under a
point. Plus the progressive map of the day sweep (L2.2): sample by sample, it adds
up to the whole day.
"""

from __future__ import annotations

import math
from datetime import date, timedelta, timezone

import numpy as np
import pytest

from open_garden_planner.core.heatmap_render import build_sun_lut
from open_garden_planner.core.scene3d import drape as drape_module
from open_garden_planner.core.scene3d.color import srgb8_to_linear
from open_garden_planner.core.scene3d.drape import (
    DRAPE_LIFT_CM,
    FALLBACK_STEP_CM,
    SHADE_MULTIPLIER,
    drape_factor,
    shadow_drape,
    sun_hours_drape,
)
from open_garden_planner.core.shade_aggregation import (
    SAMPLE_STEP_MINUTES,
    HeatmapGrid,
    IdentifiedCaster,
    SunHoursMap,
    compute_sun_exposure,
    daylight_samples,
    point_rasterizer_reference,
)
from open_garden_planner.models.plant_data import SunRequirement
from open_garden_planner.services.sun_mismatch_service import band_of

LUT = build_sun_lut()


def area(mesh) -> float:
    """The area the mesh covers, seen from above (cm²)."""
    p = mesh.positions.astype(np.float64)
    tri = mesh.indices.astype(np.int64)
    a, b, c = p[tri[:, 0]], p[tri[:, 1]], p[tri[:, 2]]
    return float(0.5 * np.abs(np.cross(b - a, c - a)[:, 2]).sum())


def linear(rgba) -> np.ndarray:
    return np.asarray(srgb8_to_linear(tuple(int(v) for v in rgba)), dtype=np.float32)


# ── the hours-of-sun drape ───────────────────────────────────────────────────


class TestSunHoursDrape:
    grid = HeatmapGrid(x0_cm=100.0, y0_cm=200.0, cell_cm=50.0, cols=3, rows=2)

    def test_row_zero_lies_at_the_south_edge(self) -> None:
        """A sunny SOUTH row and a shaded north row: the sunny colour lands at the
        smaller scene north — the canvas's convention, with no flip anywhere."""
        minutes = np.array([[600.0, 600.0, 600.0], [0.0, 0.0, 0.0]])
        mesh = sun_hours_drape(minutes, self.grid, 600.0, LUT)
        # vertex rows: grid edge, row 0 centre, row 1 centre, far edge (x 3 + 2 columns)
        width = self.grid.cols + 2
        south_centre = mesh.positions[1 * width + 1]
        north_centre = mesh.positions[2 * width + 1]
        assert south_centre[1] == pytest.approx(200.0 + 25.0)
        assert north_centre[1] == pytest.approx(200.0 + 75.0)
        np.testing.assert_allclose(mesh.colors[1 * width + 1], linear(LUT[-1]), atol=1e-6)
        np.testing.assert_allclose(mesh.colors[2 * width + 1], linear(LUT[0]), atol=1e-6)

    def test_vertices_sit_on_cell_centres_and_the_clamped_edge(self) -> None:
        minutes = np.arange(6, dtype=float).reshape(2, 3) * 100.0
        mesh = sun_hours_drape(minutes, self.grid, 600.0, LUT)
        xs = sorted(set(np.round(mesh.positions[:, 0], 6)))
        ys = sorted(set(np.round(mesh.positions[:, 1], 6)))
        assert xs == [100.0, 125.0, 175.0, 225.0, 250.0]
        assert ys == [200.0, 225.0, 275.0, 300.0]
        assert np.all(mesh.positions[:, 2] == pytest.approx(DRAPE_LIFT_CM))
        width = self.grid.cols + 2
        # the south-west corner vertex repeats cell (0, 0); the north-east one cell (1, 2)
        np.testing.assert_allclose(mesh.colors[0], mesh.colors[1 * width + 1])
        np.testing.assert_allclose(mesh.colors[-1], mesh.colors[2 * width + 3])
        mesh.validate()

    def test_colours_are_the_canvas_ramp_in_linear_light(self) -> None:
        minutes = np.array([[0.0, 150.0, 300.0], [450.0, 600.0, 600.0]])
        mesh = sun_hours_drape(minutes, self.grid, 600.0, LUT)
        width = self.grid.cols + 2
        for row in range(2):
            for col in range(3):
                share = minutes[row, col] / 600.0
                expected = LUT[int(round(share * (len(LUT) - 1)))]
                np.testing.assert_allclose(mesh.colors[(row + 1) * width + col + 1],
                                           linear(expected), atol=1e-6)

    def test_polar_night_is_all_shade(self) -> None:
        mesh = sun_hours_drape(np.zeros((2, 3)), self.grid, 0.0, LUT)
        np.testing.assert_allclose(mesh.colors, np.tile(linear(LUT[0]), (mesh.vertex_count, 1)),
                                   atol=1e-6)

    def test_a_grid_of_another_shape_is_refused(self) -> None:
        with pytest.raises(ValueError, match="shape"):
            sun_hours_drape(np.zeros((3, 3)), self.grid, 600.0, LUT)

    def test_a_large_map_is_averaged_for_the_drape_alone(self) -> None:
        grid = HeatmapGrid(0.0, 0.0, 10.0, cols=120, rows=90)
        assert drape_factor(grid, 1000) > 1
        minutes = np.full((90, 120), 300.0)
        minutes[:45] = 600.0  # the south half sunny
        mesh = sun_hours_drape(minutes, grid, 600.0, LUT, max_vertices=1000)
        assert mesh.vertex_count <= 1000
        # still covers the whole grid, edge to edge
        assert mesh.positions[:, 0].min() == 0.0 and mesh.positions[:, 0].max() == 1200.0
        assert mesh.positions[:, 1].min() == 0.0 and mesh.positions[:, 1].max() == 900.0
        south = mesh.colors[mesh.positions[:, 1] < 200.0]
        np.testing.assert_allclose(south, np.tile(linear(LUT[-1]), (len(south), 1)), atol=1e-6)

    def test_the_drape_factor_is_one_while_the_map_fits(self) -> None:
        assert drape_factor(HeatmapGrid(0.0, 0.0, 10.0, cols=300, rows=200)) == 1


# ── the shadow drape ─────────────────────────────────────────────────────────


def square(x0: float, y0: float, size: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]


class TestShadowDrape:
    def test_a_shadow_inside_the_plan_is_covered_exactly(self) -> None:
        mesh = shadow_drape([square(100.0, 100.0, 200.0)], 1000.0, 800.0)
        assert area(mesh) == pytest.approx(200.0 * 200.0, rel=1e-6)
        assert np.all(mesh.positions[:, 2] == pytest.approx(DRAPE_LIFT_CM))
        # the vertex colour is the shade layer's MULTIPLIER, linear, opaque
        np.testing.assert_allclose(mesh.colors, np.tile((*SHADE_MULTIPLIER, 1.0), (mesh.vertex_count, 1)),
                                   atol=1e-12)
        mesh.validate()

    def test_a_shadow_is_cut_at_the_plan_edge_as_the_canvas_cuts_it(self) -> None:
        mesh = shadow_drape([square(900.0, -100.0, 300.0)], 1000.0, 800.0)
        assert area(mesh) == pytest.approx(100.0 * 200.0, rel=1e-6)
        assert mesh.positions[:, 0].max() <= 1000.0 + 1e-6
        assert mesh.positions[:, 1].min() >= -1e-6

    def test_a_union_hole_stays_sunny(self) -> None:
        outer = square(0.0, 0.0, 400.0)
        hole = list(reversed(square(100.0, 100.0, 200.0)))  # clockwise, as pyclipper gives it
        mesh = shadow_drape([outer, hole], 1000.0, 800.0)
        assert area(mesh) == pytest.approx(400.0 ** 2 - 200.0 ** 2, rel=1e-6)

    def test_night_shades_the_whole_plan(self) -> None:
        mesh = shadow_drape([square(0.0, 0.0, 5000.0)], 1000.0, 800.0)
        assert area(mesh) == pytest.approx(1000.0 * 800.0, rel=1e-6)

    def test_nothing_in_nothing_out(self) -> None:
        assert shadow_drape([], 1000.0, 800.0).vertex_count == 0
        assert shadow_drape([square(2000.0, 2000.0, 10.0)], 1000.0, 800.0).vertex_count == 0

    def test_a_region_the_triangulator_refuses_is_laid_as_a_raster(self, monkeypatch) -> None:
        def refuse(*_args, **_kwargs):
            raise ValueError("refused")

        monkeypatch.setattr(drape_module, "triangulate_region", refuse)
        outer = square(0.0, 0.0, 400.0)
        hole = list(reversed(square(100.0, 100.0, 200.0)))
        mesh = shadow_drape([outer, hole], 1000.0, 800.0)
        exact = 400.0 ** 2 - 200.0 ** 2
        # exact to the raster step along the boundary: perimeter x step
        assert abs(area(mesh) - exact) <= (4 * 400.0 + 4 * 200.0) * FALLBACK_STEP_CM
        mesh.validate()

    def test_rings_that_do_not_group_keep_their_holes_sunny(self, monkeypatch) -> None:
        """Senior review of #386: when the rings could not be grouped into outers and
        holes, every outer was laid alone and a sunny island inside a shadow union was
        filled with shade. The whole set is now one even-odd raster."""
        def refuse(*_args, **_kwargs):
            raise ValueError("refused")

        monkeypatch.setattr(drape_module, "group_rings", refuse)
        outer = square(0.0, 0.0, 400.0)
        hole = list(reversed(square(100.0, 100.0, 200.0)))
        mesh = shadow_drape([outer, hole], 1000.0, 800.0)
        exact = 400.0 ** 2 - 200.0 ** 2
        assert abs(area(mesh) - exact) <= (4 * 400.0 + 4 * 200.0) * FALLBACK_STEP_CM
        centre = mesh.positions[:, :2]
        inside_hole = ((centre[:, 0] > 110) & (centre[:, 0] < 290)
                       & (centre[:, 1] > 110) & (centre[:, 1] < 290))
        assert not inside_hole.any()   # no drape vertex inside the sunny island
        mesh.validate()


def test_the_shade_only_darkens_and_is_tinted_like_the_canvas_shadow() -> None:
    """3D review of #386: the shade MULTIPLIES the frame, so each channel is below 1 (a
    shadow never brightens), and the channels keep the order of the canvas overlay's
    shadow colour — blue kept most, then green, red least."""
    from open_garden_planner.ui.canvas.sun_shadow_controller import _SHADOW_COLOR

    red, green, blue = SHADE_MULTIPLIER
    assert 0.0 < red < green < blue < 1.0
    canvas = _SHADOW_COLOR
    assert canvas.red() < canvas.green() < canvas.blue()


# ── the probe ────────────────────────────────────────────────────────────────


class TestProbe:
    grid = HeatmapGrid(x0_cm=0.0, y0_cm=0.0, cell_cm=100.0, cols=4, rows=3)
    sun_map = SunHoursMap(date(2026, 6, 21), grid, np.arange(12, dtype=np.float32).reshape(3, 4) * 60.0,
                          720.0)

    def test_the_probe_names_the_cell_the_canvas_draws_there(self) -> None:
        assert self.sun_map.minutes_at(50.0, 50.0) == 0.0          # row 0 = south
        assert self.sun_map.minutes_at(350.0, 250.0) == 11 * 60.0  # the north-east cell
        assert self.sun_map.minutes_at(150.0, 50.0) == 60.0

    def test_outside_the_grid_there_is_no_answer(self) -> None:
        for east, north in ((-1.0, 50.0), (50.0, 300.0), (400.0, 10.0), (math.nan, 1.0),
                            (math.inf, 1.0)):
            assert self.sun_map.minutes_at(east, north) is None

    @pytest.mark.parametrize(("minutes", "band"), [
        (0.0, SunRequirement.FULL_SHADE), (119.9, SunRequirement.FULL_SHADE),
        (120.0, SunRequirement.PARTIAL_SHADE), (239.0, SunRequirement.PARTIAL_SHADE),
        (240.0, SunRequirement.PARTIAL_SUN), (359.0, SunRequirement.PARTIAL_SUN),
        (360.0, SunRequirement.FULL_SUN), (900.0, SunRequirement.FULL_SUN),
    ])
    def test_the_band_is_the_glossarys(self, minutes: float, band: SunRequirement) -> None:
        assert band_of(minutes) is band

    @pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf, True, "60"])
    def test_a_value_that_is_no_duration_has_no_band(self, bad) -> None:
        with pytest.raises(ValueError):
            band_of(bad)


# ── the progressive map of the day sweep (L2.2) ──────────────────────────────


class TestProgressiveMap:
    lat, lon, day = 52.52, 13.40, date(2026, 6, 21)
    grid = HeatmapGrid(0.0, 0.0, 50.0, cols=8, rows=6)

    def result(self):
        caster = IdentifiedCaster("wall", ((
            (150.0, 100.0), (250.0, 100.0), (250.0, 120.0), (150.0, 120.0)),), 200.0)
        return compute_sun_exposure([caster], (), self.lat, self.lon, self.day, self.grid,
                                    point_rasterizer_reference)

    def sun_map(self) -> SunHoursMap:
        result = self.result()
        daylight = len(daylight_samples(self.lat, self.lon, self.day)) * SAMPLE_STEP_MINUTES
        return SunHoursMap(self.day, self.grid, result.minutes, float(daylight),
                           samples=result.samples, sample_shade=result.sample_shade)

    def test_every_sample_is_kept_with_its_mask(self) -> None:
        result = self.result()
        assert len(result.samples) == len(daylight_samples(self.lat, self.lon, self.day))
        assert result.sample_shade is not None
        assert result.sample_shade.shape == (len(result.samples), 6, 1)

    BERLIN = timezone(timedelta(hours=2))

    def test_the_sweep_adds_up_to_the_whole_day(self) -> None:
        sun_map = self.sun_map()
        assert sun_map.progressive
        np.testing.assert_array_equal(sun_map.minutes_through(24 * 60 - 1, self.BERLIN),
                                      sun_map.minutes)
        np.testing.assert_array_equal(sun_map.minutes_through(0, self.BERLIN), np.zeros((6, 8)))

    def test_the_sweep_only_ever_grows(self) -> None:
        sun_map = self.sun_map()
        previous = np.zeros((6, 8))
        for minute in range(0, 24 * 60, 30):
            now = sun_map.minutes_through(minute, self.BERLIN)
            assert np.all(now >= previous)
            previous = now

    def test_far_from_greenwich_the_sweep_takes_samples_by_their_time_of_day(self) -> None:
        """Sydney: the map's UTC day runs from 10:00 local to 10:00 the next day — its
        morning samples carry the NEXT local date. Taken by time of day, a sweep through
        the local day still ends on the whole map; at local noon the morning is in."""
        lat, lon, sydney = -33.87, 151.21, timezone(timedelta(hours=10))
        caster = IdentifiedCaster("wall", ((
            (150.0, 100.0), (250.0, 100.0), (250.0, 120.0), (150.0, 120.0)),), 200.0)
        result = compute_sun_exposure([caster], (), lat, lon, self.day, self.grid,
                                      point_rasterizer_reference)
        sun_map = SunHoursMap(self.day, self.grid, result.minutes, 600.0, samples=result.samples,
                              sample_shade=result.sample_shade)
        minutes = sun_map.sample_minutes_of_day(sydney)
        assert min(minutes) < 10 * 60 < max(minutes)       # a morning and an afternoon
        np.testing.assert_array_equal(sun_map.minutes_through(24 * 60 - 1, sydney), sun_map.minutes)
        morning = sun_map.minutes_through(12 * 60, sydney)
        assert morning.max() > 0.0 and np.all(morning <= sun_map.minutes)

    def test_the_masks_are_dropped_beyond_their_bound(self, monkeypatch) -> None:
        from open_garden_planner.core import shade_aggregation

        monkeypatch.setattr(shade_aggregation, "MAX_SAMPLE_SHADE_BYTES", 10)
        result = self.result()
        assert result.sample_shade is None
        sun_map = SunHoursMap(self.day, self.grid, result.minutes, 900.0, samples=result.samples)
        assert not sun_map.progressive and sun_map.minutes_through(1439, self.BERLIN) is None
