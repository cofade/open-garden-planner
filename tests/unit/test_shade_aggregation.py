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

import numpy as np
import pytest

from open_garden_planner.core.shade_aggregation import (
    BAND_THRESHOLDS_MINUTES,
    SAMPLE_STEP_MINUTES,
    HeatmapGrid,
    accumulate_sun_minutes,
    band_grid,
    band_index,
    compute_heatmap,
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


class TestBands:
    def test_band_index_thresholds(self) -> None:
        assert band_index(0) == 0
        assert band_index(119) == 0
        assert band_index(120) == 1
        assert band_index(239) == 1
        assert band_index(240) == 2
        assert band_index(359) == 2
        assert band_index(360) == 3
        assert band_index(1440) == 3

    def test_band_grid_matches_scalar(self) -> None:
        values = np.array([[0, 119, 120], [240, 360, 1000]], dtype=np.float32)
        expected = np.array(
            [[band_index(v) for v in row] for row in values], dtype=np.uint8
        )
        assert np.array_equal(band_grid(values), expected)

    def test_thresholds_are_the_documented_bands(self) -> None:
        assert BAND_THRESHOLDS_MINUTES == (120, 240, 360)


class TestPlumbing:
    def test_accumulate_sun_minutes(self) -> None:
        shaded = np.array([[True, False]])
        clear = np.array([[False, False]])
        minutes = accumulate_sun_minutes([shaded, clear], 1, 2, step_minutes=15)
        assert minutes[0, 0] == 15.0
        assert minutes[0, 1] == 30.0

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
