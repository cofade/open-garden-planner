"""Tests for US-8.4: Plant Calendar Data Model."""

import pytest

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services.planting_calendar_db import (
    get_calendar_db,
    get_calendar_entry,
    merge_calendar_data,
)


# ---------------------------------------------------------------------------
# PlantSpeciesData calendar fields
# ---------------------------------------------------------------------------


class TestPlantSpeciesDataCalendarFields:
    """Calendar fields are stored and round-trip correctly on PlantSpeciesData."""

    def test_default_calendar_fields_are_none(self) -> None:
        plant = PlantSpeciesData(scientific_name="Foo bar", common_name="Foo")
        assert plant.indoor_sow_start is None
        assert plant.indoor_sow_end is None
        assert plant.direct_sow_start is None
        assert plant.direct_sow_end is None
        assert plant.transplant_start is None
        assert plant.transplant_end is None
        assert plant.harvest_start is None
        assert plant.harvest_end is None
        assert plant.days_to_germination_min is None
        assert plant.days_to_germination_max is None
        assert plant.days_to_maturity_min is None
        assert plant.days_to_maturity_max is None
        assert plant.frost_tolerance is None
        assert plant.min_germination_temp_c is None
        assert plant.seed_depth_cm is None

    def test_calendar_fields_stored(self) -> None:
        plant = PlantSpeciesData(
            scientific_name="Solanum lycopersicum",
            common_name="Tomato",
            indoor_sow_start=-8,
            indoor_sow_end=-6,
            direct_sow_start=None,
            transplant_start=2,
            transplant_end=4,
            harvest_start=10,
            harvest_end=20,
            days_to_germination_min=5,
            days_to_germination_max=10,
            days_to_maturity_min=60,
            days_to_maturity_max=85,
            frost_tolerance="tender",
            min_germination_temp_c=18.0,
            seed_depth_cm=0.6,
        )
        assert plant.indoor_sow_start == -8
        assert plant.frost_tolerance == "tender"
        assert plant.seed_depth_cm == 0.6
        assert plant.direct_sow_start is None

    def test_to_dict_includes_calendar_fields(self) -> None:
        plant = PlantSpeciesData(
            scientific_name="Solanum lycopersicum",
            common_name="Tomato",
            indoor_sow_start=-8,
            frost_tolerance="tender",
            seed_depth_cm=0.6,
        )
        d = plant.to_dict()
        assert d["indoor_sow_start"] == -8
        assert d["frost_tolerance"] == "tender"
        assert d["seed_depth_cm"] == 0.6
        assert "direct_sow_start" in d
        assert d["direct_sow_start"] is None

    def test_from_dict_round_trip(self) -> None:
        plant = PlantSpeciesData(
            scientific_name="Solanum lycopersicum",
            common_name="Tomato",
            indoor_sow_start=-8,
            indoor_sow_end=-6,
            transplant_start=2,
            transplant_end=4,
            harvest_start=10,
            harvest_end=20,
            days_to_germination_min=5,
            days_to_germination_max=10,
            days_to_maturity_min=60,
            days_to_maturity_max=85,
            frost_tolerance="tender",
            min_germination_temp_c=18.0,
            seed_depth_cm=0.6,
        )
        restored = PlantSpeciesData.from_dict(plant.to_dict())
        assert restored.indoor_sow_start == -8
        assert restored.indoor_sow_end == -6
        assert restored.transplant_start == 2
        assert restored.harvest_end == 20
        assert restored.days_to_germination_min == 5
        assert restored.days_to_maturity_max == 85
        assert restored.frost_tolerance == "tender"
        assert restored.min_germination_temp_c == 18.0
        assert restored.seed_depth_cm == 0.6

    def test_from_dict_missing_calendar_fields_default_none(self) -> None:
        """from_dict gracefully handles older dicts without calendar fields."""
        d = {
            "scientific_name": "Foo bar",
            "common_name": "Foo",
            "cycle": "unknown",
            "growth_rate": "unknown",
            "flower_type": "unknown",
            "pollination_type": "unknown",
            "sun_requirement": "unknown",
            "water_needs": "unknown",
        }
        plant = PlantSpeciesData.from_dict(d)
        assert plant.indoor_sow_start is None
        assert plant.frost_tolerance is None


# ---------------------------------------------------------------------------
# PlantingCalendarDB: get_calendar_db / get_calendar_entry
# ---------------------------------------------------------------------------


class TestGetCalendarDb:
    """The curated database loads and has the required minimum species count."""

    def test_db_has_minimum_50_species(self) -> None:
        db = get_calendar_db()
        assert len(db) >= 50

    def test_db_keys_are_lowercase_scientific_names(self) -> None:
        db = get_calendar_db()
        for key in db:
            assert key == key.lower(), f"Key not lowercase: {key!r}"

    def test_tomato_present(self) -> None:
        db = get_calendar_db()
        assert "solanum lycopersicum" in db

    def test_basil_present(self) -> None:
        db = get_calendar_db()
        assert "ocimum basilicum" in db


class TestGetCalendarEntry:
    """get_calendar_entry returns correct data and handles edge cases."""

    def test_returns_tomato_data(self) -> None:
        entry = get_calendar_entry("Solanum lycopersicum")
        assert entry is not None
        assert entry["frost_tolerance"] == "tender"
        assert entry["indoor_sow_start"] == -8
        assert entry["seed_depth_cm"] == pytest.approx(0.6)

    def test_case_insensitive_lookup(self) -> None:
        lower = get_calendar_entry("solanum lycopersicum")
        upper = get_calendar_entry("SOLANUM LYCOPERSICUM")
        mixed = get_calendar_entry("Solanum Lycopersicum")
        assert lower == upper == mixed

    def test_unknown_species_returns_none(self) -> None:
        assert get_calendar_entry("Imaginus plantus") is None

    def test_hardy_species_has_correct_tolerance(self) -> None:
        # Carrot is frost hardy
        entry = get_calendar_entry("Daucus carota")
        assert entry is not None
        assert entry["frost_tolerance"] == "hardy"

    def test_entry_has_expected_fields(self) -> None:
        entry = get_calendar_entry("Solanum lycopersicum")
        assert entry is not None
        for field in (
            "frost_tolerance",
            "days_to_germination_min",
            "days_to_germination_max",
            "days_to_maturity_min",
            "days_to_maturity_max",
            "min_germination_temp_c",
            "seed_depth_cm",
        ):
            assert field in entry, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# merge_calendar_data
# ---------------------------------------------------------------------------


class TestMergeCalendarData:
    """merge_calendar_data applies correct priority: local DB > existing > API."""

    def test_local_db_wins_over_api(self) -> None:
        plant_dict: dict = {
            "scientific_name": "Solanum lycopersicum",
            "common_name": "Tomato",
        }
        api_dict = {"frost_tolerance": "hardy", "seed_depth_cm": 99.0}
        result = merge_calendar_data(plant_dict, api_dict)
        # Local DB says tender / 0.6
        assert result["frost_tolerance"] == "tender"
        assert result["seed_depth_cm"] == pytest.approx(0.6)

    def test_local_db_wins_over_existing_plant_value(self) -> None:
        plant_dict = {
            "scientific_name": "Solanum lycopersicum",
            "common_name": "Tomato",
            "frost_tolerance": "half-hardy",  # wrong pre-existing value
        }
        result = merge_calendar_data(plant_dict)
        assert result["frost_tolerance"] == "tender"

    def test_existing_plant_value_wins_over_api_when_no_local(self) -> None:
        plant_dict = {
            "scientific_name": "Imaginus plantus",
            "common_name": "Imaginary Plant",
            "frost_tolerance": "half-hardy",
        }
        api_dict = {"frost_tolerance": "tender"}
        result = merge_calendar_data(plant_dict, api_dict)
        # No local entry → existing value wins over API
        assert result["frost_tolerance"] == "half-hardy"

    def test_api_fills_missing_field_when_no_local_and_no_existing(self) -> None:
        plant_dict = {
            "scientific_name": "Imaginus plantus",
            "common_name": "Imaginary Plant",
        }
        api_dict = {"frost_tolerance": "tender", "seed_depth_cm": 1.5}
        result = merge_calendar_data(plant_dict, api_dict)
        assert result["frost_tolerance"] == "tender"
        assert result["seed_depth_cm"] == pytest.approx(1.5)

    def test_all_calendar_fields_filled_from_local_db(self) -> None:
        plant_dict: dict = {
            "scientific_name": "Solanum lycopersicum",
            "common_name": "Tomato",
        }
        result = merge_calendar_data(plant_dict)
        assert result["indoor_sow_start"] == -8
        assert result["indoor_sow_end"] == -6
        assert result["transplant_start"] == 2
        assert result["harvest_start"] == 10
        assert result["days_to_germination_min"] == 5
        assert result["days_to_maturity_min"] == 60

    def test_unknown_species_no_api_leaves_none(self) -> None:
        plant_dict: dict = {
            "scientific_name": "Imaginus plantus",
            "common_name": "Imaginary Plant",
        }
        result = merge_calendar_data(plant_dict)
        assert result.get("frost_tolerance") is None
        assert result.get("seed_depth_cm") is None

    def test_original_dict_not_mutated(self) -> None:
        plant_dict: dict = {
            "scientific_name": "Solanum lycopersicum",
            "common_name": "Tomato",
        }
        original_keys = set(plant_dict.keys())
        merge_calendar_data(plant_dict)
        assert set(plant_dict.keys()) == original_keys
