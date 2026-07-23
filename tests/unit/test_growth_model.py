"""Unit tests for the growth model (US-E8, #263).

Owner-chosen redesign: the plant's OWN measured ``current_height_cm`` /
``current_spread_cm`` anchors the low end of the curve (not the species
minimum), and growth engages only when a planting date AND a current size
are both present.
"""

from __future__ import annotations

from datetime import date

import pytest

from open_garden_planner.core.growth_model import (
    YEARS_TO_MATURITY_DEFAULT,
    YEARS_TO_MATURITY_TREE,
    current_height_from_metadata,
    current_spread_from_metadata,
    grown_height_cm,
    grown_spread_cm,
    planting_date_from_metadata,
    stamp_default_planting_date,
    years_to_maturity,
)

# Reference species: mature 200 cm, maturity 3 y (perennial default — no
# days_to_maturity data). ``min_height_cm`` is deliberately present and
# deliberately IGNORED by the current-anchored model.
SPECIES = {"min_height_cm": 30.0, "max_height_cm": 200.0}
PLANTED = {
    "plant_instance": {"planting_date": "2026-04-01", "current_height_cm": 30.0}
}


class TestCurrentAnchoredCurve:
    def test_at_planting_is_the_measured_current_height(self) -> None:
        assert grown_height_cm(SPECIES, PLANTED, date(2026, 4, 1)) == 30.0

    def test_linear_midpoint_at_one_and_a_half_years(self) -> None:
        value = grown_height_cm(SPECIES, PLANTED, date(2027, 10, 1))
        assert value == pytest.approx(115.0, abs=0.5)

    def test_clamped_at_maturity(self) -> None:
        assert grown_height_cm(SPECIES, PLANTED, date(2030, 1, 1)) == 200.0

    def test_future_planting_clamps_to_current_height(self) -> None:
        planted = {
            "plant_instance": {
                "planting_date": "2030-01-01",
                "current_height_cm": 30.0,
            }
        }
        assert grown_height_cm(SPECIES, planted, date(2026, 1, 1)) == 30.0

    def test_species_minimum_is_ignored(self) -> None:
        """The curve starts at the MEASURED height, not the species min."""
        planted = {
            "plant_instance": {
                "planting_date": "2026-04-01",
                "current_height_cm": 150.0,
            }
        }
        # Species min is 30, but the plant was measured at 150.
        assert grown_height_cm(SPECIES, planted, date(2026, 4, 1)) == 150.0

    def test_already_taller_than_mature_stays_flat_at_max(self) -> None:
        planted = {
            "plant_instance": {
                "planting_date": "2026-04-01",
                "current_height_cm": 250.0,
            }
        }
        assert grown_height_cm(SPECIES, planted, date(2026, 4, 1)) == 200.0
        assert grown_height_cm(SPECIES, planted, date(2040, 1, 1)) == 200.0


class TestGrowthDisengages:
    """None => the height resolver falls back to current-else-mature."""

    def test_no_planting_date_is_none(self) -> None:
        no_date = {"plant_instance": {"current_height_cm": 30.0}}
        assert grown_height_cm(SPECIES, no_date, date(2027, 1, 1)) is None
        assert grown_height_cm(SPECIES, {}, date(2027, 1, 1)) is None
        assert grown_height_cm(SPECIES, None, date(2027, 1, 1)) is None

    def test_no_current_height_is_none(self) -> None:
        """An un-measured plant does NOT grow — it stays at mature size."""
        dated_only = {"plant_instance": {"planting_date": "2026-04-01"}}
        assert grown_height_cm(SPECIES, dated_only, date(2027, 1, 1)) is None

    def test_no_species_max_is_none(self) -> None:
        assert grown_height_cm({}, PLANTED, date(2027, 1, 1)) is None


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

    def test_annual_cycle_without_days_via_real_serializer(self) -> None:
        """Fixture built through the REAL PlantSpeciesData.to_dict() so the
        cycle key can never drift from the serializer again (the review
        caught a phantom 'plant_cycle' key pinned by a hand-built dict)."""
        from open_garden_planner.models.plant_data import (
            PlantCycle,
            PlantSpeciesData,
        )

        species = PlantSpeciesData(
            scientific_name="Lactuca sativa",
            common_name="Lettuce",
            cycle=PlantCycle.ANNUAL,
            max_height_cm=30.0,
        ).to_dict()
        assert "cycle" in species and "plant_cycle" not in species
        horizon = years_to_maturity(species, "PERENNIAL")
        assert horizon == pytest.approx(150.0 / 365.0)

    def test_annual_ramps_within_the_season(self) -> None:
        annual = {
            "max_height_cm": 120.0,
            "days_to_maturity_min": 60,
            "days_to_maturity_max": 80,
        }
        planted = {
            "plant_instance": {
                "planting_date": "2026-05-01",
                "current_height_cm": 10.0,
            }
        }
        # 70-day average maturity → full size well within the season.
        mid = grown_height_cm(annual, planted, date(2026, 6, 5))
        full = grown_height_cm(annual, planted, date(2026, 8, 1))
        assert full == 120.0
        assert 10.0 < mid < 120.0


class TestSpread:
    def test_spread_interpolates_from_current_spread(self) -> None:
        species = {"min_spread_cm": 50.0, "max_spread_cm": 400.0}
        planted = {
            "plant_instance": {
                "planting_date": "2026-01-01",
                "current_spread_cm": 50.0,
            }
        }
        at_half = grown_spread_cm(species, planted, date(2027, 7, 2))
        assert at_half == pytest.approx(225.0, abs=1.0)

    def test_no_current_spread_is_none(self) -> None:
        species = {"max_spread_cm": 300.0}
        planted = {"plant_instance": {"planting_date": "2026-01-01"}}
        assert grown_spread_cm(species, planted, date(2026, 1, 1)) is None


class TestMetadataAccessors:
    def test_planting_date_parsing(self) -> None:
        assert planting_date_from_metadata(
            {"plant_instance": {"planting_date": "2026-04-01"}}
        ) == date(2026, 4, 1)
        assert planting_date_from_metadata(
            {"plant_instance": {"planting_date": "garbage"}}
        ) is None
        assert planting_date_from_metadata({"plant_instance": {}}) is None
        assert planting_date_from_metadata(None) is None

    def test_current_size_accessors(self) -> None:
        meta = {
            "plant_instance": {
                "current_height_cm": 120.0,
                "current_spread_cm": 80.0,
            }
        }
        assert current_height_from_metadata(meta) == 120.0
        assert current_spread_from_metadata(meta) == 80.0

    def test_current_size_rejects_zero_and_junk(self) -> None:
        """0 is the panel's 'unset' sentinel (shown as an em dash)."""
        assert current_height_from_metadata(
            {"plant_instance": {"current_height_cm": 0}}
        ) is None
        assert current_height_from_metadata(
            {"plant_instance": {"current_height_cm": None}}
        ) is None
        assert current_height_from_metadata(
            {"plant_instance": {"current_height_cm": True}}
        ) is None
        assert current_height_from_metadata({}) is None
        assert current_height_from_metadata(None) is None


class TestDefaultPlantingDateStamp:
    def test_stamps_today_when_absent(self) -> None:
        metadata: dict = {}
        stamp_default_planting_date(metadata, date(2026, 7, 23))
        assert metadata["plant_instance"]["planting_date"] == "2026-07-23"

    def test_never_overwrites_an_existing_date(self) -> None:
        metadata = {"plant_instance": {"planting_date": "2020-03-01"}}
        stamp_default_planting_date(metadata, date(2026, 7, 23))
        assert metadata["plant_instance"]["planting_date"] == "2020-03-01"

    def test_preserves_other_instance_keys(self) -> None:
        metadata = {"plant_instance": {"current_height_cm": 150.0}}
        stamp_default_planting_date(metadata, date(2026, 7, 23))
        assert metadata["plant_instance"]["current_height_cm"] == 150.0
        assert metadata["plant_instance"]["planting_date"] == "2026-07-23"

    def test_none_metadata_is_a_noop(self) -> None:
        stamp_default_planting_date(None, date(2026, 7, 23))  # must not raise
