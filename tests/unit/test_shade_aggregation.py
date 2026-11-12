"""Unit tests for the Qt-free shade aggregation core (US-E4, #259).

The centerpiece is the campaign's HAND-COMPUTABLE TOY CASE (oracle-sourced,
5-min sampling reference): a 200 cm east–west wall on flat ground in Berlin,
evaluated 50 cm NORTH of the wall (northern hemisphere → the sun tracks the
southern sky → the wall's north side is the dark side):

- Dec 21: **0 min** of direct sun — winter azimuth stays in (90°, 270°) all
  day, so the shadow always reaches north; escaping a 200 cm wall at 50 cm
  would need α ≥ 75.96°, Berlin's winter max is 14.04°. Exactly zero.
- Jun 21: **540 min (9.0 h)** — lit ~03:00–07:30 UTC (sun NE→E, northward
  reach < 50 cm), shaded ~07:30–14:40 (reach 73–111 cm), lit again ~14:40
  to sunset (~19:20, az → 309° NW).
"""

from __future__ import annotations

from datetime import date

import pytest

from open_garden_planner.core.shade_aggregation import (
    BAND_THRESHOLDS_MINUTES,
    SAMPLE_STEP_MINUTES,
    HeatmapGrid,
    IdentifiedCaster,
    SunReceiver,
    compute_heatmap,
    compute_sun_exposure,
    daylight_samples,
    point_rasterizer_reference,
)

BERLIN_LAT, BERLIN_LON = 52.52, 13.405

# 4 km east–west wall centered on y = 0, height 200 cm — long enough that
# end effects at the evaluation point (x = 0) are nil, and effectively
# line-thin (1 cm) so the geometry matches the oracle's idealized wall LINE
# with the point exactly 50 cm north (a thick wall moves the north face
# closer to the point and shifts the lit/shade crossings by minutes).
WALL_FOOTPRINT = [
    (-200_000.0, -0.5),
    (200_000.0, -0.5),
    (200_000.0, 0.5),
    (-200_000.0, 0.5),
]
WALL_CASTERS = [(WALL_FOOTPRINT, 200.0)]

# One 10 cm cell centered on the toy evaluation point (0, 50).
POINT_GRID = HeatmapGrid(x0_cm=-5.0, y0_cm=45.0, cell_cm=10.0, cols=1, rows=1)


def _toy_minutes(day: date, step_minutes: int = SAMPLE_STEP_MINUTES) -> float:
    minutes = compute_heatmap(
        WALL_CASTERS,
        BERLIN_LAT,
        BERLIN_LON,
        day,
        POINT_GRID,
        point_rasterizer_reference,
        step_minutes=step_minutes,
    )
    assert minutes is not None
    return float(minutes[0, 0])


class TestToyCase:
    def test_winter_solstice_zero_sun(self) -> None:
        assert _toy_minutes(date(2026, 12, 21)) == 0.0

    def test_summer_solstice_nine_hours(self) -> None:
        assert _toy_minutes(date(2026, 6, 21)) == pytest.approx(540.0, abs=15.0)

    def test_step_sensitivity(self) -> None:
        # 5-min sampling (the oracle's reference step) agrees with the
        # 15-min production step to within one production sample.
        fine = _toy_minutes(date(2026, 6, 21), step_minutes=5)
        coarse = _toy_minutes(date(2026, 6, 21))
        assert fine == pytest.approx(540.0, abs=5.0)
        assert abs(fine - coarse) <= 15.0

    def test_point_just_south_of_wall(self) -> None:
        # Control: 50 cm SOUTH of the wall. NOT full daylight — Berlin's
        # midsummer sun rises at azimuth ≈ 51° (north of east) and sets
        # ≈ 309° (north of west), so early morning / late evening shadows
        # fall SOUTH and shade this point too. It must still get clearly
        # more sun than the north point (which loses the whole midday).
        south_grid = HeatmapGrid(
            x0_cm=-5.0, y0_cm=-55.0, cell_cm=10.0, cols=1, rows=1
        )
        minutes = compute_heatmap(
            WALL_CASTERS,
            BERLIN_LAT,
            BERLIN_LON,
            date(2026, 6, 21),
            south_grid,
            point_rasterizer_reference,
        )
        daylight_min = (
            len(daylight_samples(BERLIN_LAT, BERLIN_LON, date(2026, 6, 21)))
            * SAMPLE_STEP_MINUTES
        )
        assert minutes is not None
        south = float(minutes[0, 0])
        north = _toy_minutes(date(2026, 6, 21))
        assert north < south < daylight_min


class TestDaylightWindow:
    def test_berlin_summer_daylight_duration(self) -> None:
        # Berlin Jun 21 ≈ 16.7 h of daylight.
        samples = daylight_samples(BERLIN_LAT, BERLIN_LON, date(2026, 6, 21))
        hours = len(samples) * SAMPLE_STEP_MINUTES / 60.0
        assert 16.0 < hours < 17.5

    def test_polar_night_is_empty(self) -> None:
        assert daylight_samples(70.0, 20.0, date(2026, 12, 21)) == []

    def test_midnight_sun_is_full_day(self) -> None:
        samples = daylight_samples(70.0, 20.0, date(2026, 6, 21))
        assert len(samples) == 24 * 60 // SAMPLE_STEP_MINUTES

    def test_polar_night_heatmap_is_all_zero(self) -> None:
        minutes = compute_heatmap(
            WALL_CASTERS,
            70.0,
            20.0,
            date(2026, 12, 21),
            POINT_GRID,
            point_rasterizer_reference,
        )
        assert minutes is not None
        assert float(minutes.max()) == 0.0


class TestPlanNorth:
    def test_the_plan_north_turns_the_heatmap(self) -> None:
        """#663: a caster's daily map follows the plan frame, not just the clock."""
        day = date(2026, 6, 21)
        north_up = compute_heatmap(
            WALL_CASTERS, BERLIN_LAT, BERLIN_LON, day, POINT_GRID,
            point_rasterizer_reference, north_angle_deg=0.0,
        )
        north_down = compute_heatmap(
            WALL_CASTERS, BERLIN_LAT, BERLIN_LON, day, POINT_GRID,
            point_rasterizer_reference, north_angle_deg=180.0,
        )
        assert north_up is not None and north_down is not None
        # The toy point is 50 cm NORTH of the wall in the scene. With the
        # plan's north down, the sun's path is turned 180° and that side is
        # the sunlit one, so the point collects clearly more sun.
        assert float(north_up[0, 0]) == pytest.approx(540.0, abs=15.0)
        assert float(north_down[0, 0]) > float(north_up[0, 0]) + 60.0

    def test_the_same_wall_turns_the_map_a_quarter_turn(self) -> None:
        day = date(2026, 6, 21)
        plain = compute_heatmap(
            WALL_CASTERS, BERLIN_LAT, BERLIN_LON, day, POINT_GRID,
            point_rasterizer_reference, north_angle_deg=0.0,
        )
        turned = compute_heatmap(
            WALL_CASTERS, BERLIN_LAT, BERLIN_LON, day, POINT_GRID,
            point_rasterizer_reference, north_angle_deg=90.0,
        )
        assert plain is not None and turned is not None
        assert float(turned[0, 0]) != float(plain[0, 0])

    def test_the_shipped_exposure_entry_point_forwards_the_north(self) -> None:
        """The app calls compute_sun_exposure (via SunHeatmapController), not
        compute_heatmap: pin the 0/180 direction through that seam."""
        day = date(2026, 6, 21)
        receiver = SunReceiver("point", 0.0, 50.0)
        wall = IdentifiedCaster("wall", (WALL_FOOTPRINT,), 200.0)
        north_up = compute_sun_exposure(
            [wall], [receiver], BERLIN_LAT, BERLIN_LON, day, POINT_GRID,
            point_rasterizer_reference, north_angle_deg=0.0,
        )
        north_down = compute_sun_exposure(
            [wall], [receiver], BERLIN_LAT, BERLIN_LON, day, POINT_GRID,
            point_rasterizer_reference, north_angle_deg=180.0,
        )
        assert north_up is not None and north_down is not None
        up = float(dict(north_up.receiver_minutes)["point"])
        down = float(dict(north_down.receiver_minutes)["point"])
        assert up == pytest.approx(540.0, abs=15.0)
        assert down > up + 60.0


class TestBands:
    def test_thresholds_are_the_documented_bands(self) -> None:
        assert BAND_THRESHOLDS_MINUTES == (120, 240, 360)


class TestPlumbing:
    def test_grid_cell_round_trip(self) -> None:
        grid = HeatmapGrid.for_rect(0.0, 0.0, 3000.0, 2000.0, cell_cm=10.0)
        assert (grid.cols, grid.rows) == (300, 200)
        row, col = grid.cell_at(*grid.cell_center(42, 137))
        assert (row, col) == (42, 137)

    def test_cancel_returns_none(self) -> None:
        result = compute_heatmap(
            WALL_CASTERS,
            BERLIN_LAT,
            BERLIN_LON,
            date(2026, 6, 21),
            POINT_GRID,
            point_rasterizer_reference,
            should_cancel=lambda: True,
        )
        assert result is None

    def test_progress_reports_every_sample(self) -> None:
        calls: list[tuple[int, int]] = []
        compute_heatmap(
            [],
            BERLIN_LAT,
            BERLIN_LON,
            date(2026, 6, 21),
            POINT_GRID,
            point_rasterizer_reference,
            progress=lambda done, total: calls.append((done, total)),
        )
        assert calls
        assert calls[-1][0] == calls[-1][1] == len(calls)


class TestPorousFenceAndPitchedRoofAggregation:
    def test_porous_fence_fractional_sun_and_plant_exposure(self) -> None:
        # Wooden fence along x-axis at y=0, height 150cm
        fence_pts = ((-200_000.0, 0.0), (200_000.0, 0.0))
        fence_footprint = (
            (-200_000.0, -2.0),
            (200_000.0, -2.0),
            (200_000.0, 2.0),
            (-200_000.0, 2.0),
        )
        caster = IdentifiedCaster(
            item_id="fence",
            footprints=(fence_footprint,),
            height_cm=150.0,
            fence_style="WOODEN_FENCE",
            fence_points=fence_pts,
            fence_width_cm=4.0,
        )
        receiver = SunReceiver(item_id="tomato", x_cm=0.0, y_cm=50.0)

        # On winter solstice, opaque wall gets 0.0 min. Porous fence allows fractional sunlight through!
        res = compute_sun_exposure(
            [caster],
            [receiver],
            BERLIN_LAT,
            BERLIN_LON,
            date(2026, 12, 21),
            POINT_GRID,
            point_rasterizer_reference,
            include_sample_masks=True,
        )
        assert res is not None
        rec_dict = dict(res.receiver_minutes)
        hours = rec_dict["tomato"]
        assert hours > 0.0
        # Heatmap grid should also record > 0 minutes
        assert float(res.minutes[0, 0]) > 0.0
        # Transmittance array is retained
        assert res.sample_transmittance is not None
        assert res.sample_transmittance.shape == (len(res.samples), 1, 1)

    def test_elevated_receiver_behind_pitched_roof_slicing(self) -> None:
        from open_garden_planner.core.scene3d.builders.buildings import (
            pitched_roof_triangles,
        )
        from open_garden_planner.core.scene3d.record import (
            PARAM_ROOF_PITCH,
            PARAM_ROOF_STYLE,
        )

        rect_pts = (
            (-500.0, -400.0),
            (500.0, -400.0),
            (500.0, 400.0),
            (-500.0, 400.0),
        )
        tris = pitched_roof_triangles(
            "HOUSE",
            "rectangle",
            rect_pts,
            300.0,
            params={
                PARAM_ROOF_STYLE: "gable",
                PARAM_ROOF_PITCH: 35.0,
            },
        )
        caster = IdentifiedCaster(
            item_id="house",
            footprints=(rect_pts,),
            height_cm=300.0,
            roof_triangles=tris,
        )

        # Ground receiver at (0, 500)
        rec_ground = SunReceiver(item_id="plant_ground", x_cm=0.0, y_cm=500.0, elevation_cm=0.0)
        # Elevated receiver at (0, 500) raised to 250cm (above eaves ~212cm, so obstacle slice is small)
        rec_elevated = SunReceiver(item_id="plant_elevated", x_cm=0.0, y_cm=500.0, elevation_cm=250.0)

        grid = HeatmapGrid(x0_cm=-50.0, y0_cm=450.0, cell_cm=100.0, cols=1, rows=1)
        res = compute_sun_exposure(
            [caster],
            [rec_ground, rec_elevated],
            BERLIN_LAT,
            BERLIN_LON,
            date(2026, 6, 21),
            grid,
            point_rasterizer_reference,
        )
        assert res is not None
        rec_dict = dict(res.receiver_minutes)
        # Elevated receiver must get significantly more sun than ground receiver
        assert rec_dict["plant_elevated"] > rec_dict["plant_ground"]

    def test_sample_masks_drop_when_bytes_exceed_cap(self, monkeypatch) -> None:
        import open_garden_planner.core.shade_aggregation as sa

        caster = IdentifiedCaster(
            item_id="fence",
            footprints=(((-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)),),
            height_cm=100.0,
            fence_style="WOODEN_FENCE",
            fence_points=((0.0, -10.0), (0.0, 10.0)),
        )
        monkeypatch.setattr(sa, "MAX_SAMPLE_SHADE_BYTES", 10)
        res = compute_sun_exposure(
            [caster],
            [],
            BERLIN_LAT,
            BERLIN_LON,
            date(2026, 6, 21),
            POINT_GRID,
            point_rasterizer_reference,
            include_sample_masks=True,
        )
        assert res is not None
        # Both sample_shade and sample_transmittance must be dropped to protect memory
        assert res.sample_shade is None
        assert res.sample_transmittance is None

