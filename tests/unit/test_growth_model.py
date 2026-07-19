"""Unit tests for the growth model (US-E8, #263) — the issue's gate table."""

from __future__ import annotations

from datetime import date

import pytest

from open_garden_planner.core.growth_model import (
    YEARS_TO_MATURITY_DEFAULT,
    YEARS_TO_MATURITY_TREE,
    grown_height_cm,
    grown_spread_cm,
    planting_date_from_metadata,
    years_to_maturity,
)

# The issue's reference species: min 30 / max 200, maturity 3 y (via the
# perennial default — no days_to_maturity data).
SPECIES = {"min_height_cm": 30.0, "max_height_cm": 200.0}
PLANTED = {"plant_instance": {"planting_date": "2026-04-01"}}


class TestIssueGateTable:
    def test_at_planting_is_minimum(self) -> None:
        assert grown_height_cm(SPECIES, PLANTED, date(2026, 4, 1)) == 30.0

    def test_linear_midpoint_at_one_and_a_half_years(self) -> None:
        value = grown_height_cm(SPECIES, PLANTED, date(2027, 10, 1))
        assert value == pytest.approx(115.0, abs=0.5)

    def test_clamped_at_maturity(self) -> None:
        assert grown_height_cm(SPECIES, PLANTED, date(2030, 1, 1)) == 200.0

    def test_no_planting_date_is_none(self) -> None:
        assert grown_height_cm(SPECIES, {}, date(2027, 1, 1)) is None
        assert grown_height_cm(SPECIES, None, date(2027, 1, 1)) is None

    def test_annual_ramps_within_the_season(self) -> None:
        annual = {
            "max_height_cm": 120.0,
            "days_to_maturity_min": 60,
            "days_to_maturity_max": 80,
        }
        planted = {"plant_instance": {"planting_date": "2026-05-01"}}
        # 70-day average maturity → full size well within the season.
        mid = grown_height_cm(annual, planted, date(2026, 6, 5))
        full = grown_height_cm(annual, planted, date(2026, 8, 1))
        assert full == 120.0
        assert 12.0 < mid < 120.0  # ramping, min-fallback = 10% of max


class TestMaturityHorizon:
    def test_tree_default_ten_years(self) -> None:
        assert years_to_maturity({}, "TREE") == YEARS_TO_MATURITY_TREE

    def test_perennial_default_three_years(self) -> None:
        assert years_to_maturity({}, "SHRUB") == YEARS_TO_MATURITY_DEFAULT
        assert years_to_maturity({}, "PERENNIAL") == YEARS_TO_MATURITY_DEFAULT

    def test_days_to_maturity_wins_over_defaults(self) -> None:
        assert years_to_maturity(
            {"days_to_maturity_min": 365, "days_to_maturity_max": 365}, "TREE"
        ) == pytest.approx(1.0)

    def test_annual_cycle_without_days(self) -> None:
        horizon = years_to_maturity({"plant_cycle": "Annual"}, "PERENNIAL")
        assert horizon == pytest.approx(150.0 / 365.0)


class TestSpreadAndParsing:
    def test_spread_interpolates_like_height(self) -> None:
        species = {"min_spread_cm": 50.0, "max_spread_cm": 400.0}
        planted = {"plant_instance": {"planting_date": "2026-01-01"}}
        at_half = grown_spread_cm(species, planted, date(2027, 7, 2))
        assert at_half == pytest.approx(225.0, abs=1.0)

    def test_min_fallback_is_ten_percent(self) -> None:
        species = {"max_spread_cm": 300.0}
        planted = {"plant_instance": {"planting_date": "2026-01-01"}}
        assert grown_spread_cm(species, planted, date(2026, 1, 1)) == pytest.approx(
            30.0
        )

    def test_planting_date_parsing(self) -> None:
        assert planting_date_from_metadata(
            {"plant_instance": {"planting_date": "2026-04-01"}}
        ) == date(2026, 4, 1)
        assert planting_date_from_metadata(
            {"plant_instance": {"planting_date": "garbage"}}
        ) is None
        assert planting_date_from_metadata({"plant_instance": {}}) is None
        assert planting_date_from_metadata(None) is None

    def test_future_planting_clamps_to_minimum(self) -> None:
        planted = {"plant_instance": {"planting_date": "2030-01-01"}}
        assert grown_height_cm(SPECIES, planted, date(2026, 1, 1)) == 30.0
