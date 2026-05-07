"""Unit tests for US-10.5: Crop rotation data model."""
from __future__ import annotations

import pytest

from open_garden_planner.models.crop_rotation import (
    NUTRIENT_DEMANDS,
    SEASONS,
    CropRotationHistory,
    PlantingRecord,
)


# ─── PlantingRecord Tests ─────────────────────────────────────────────────────


class TestPlantingRecord:
    def test_create_record(self) -> None:
        record = PlantingRecord(
            year=2025,
            season="spring",
            species_name="Solanum lycopersicum",
            common_name="Tomato",
            family="Solanaceae",
            nutrient_demand="heavy",
            area_id="bed-001",
        )
        assert record.year == 2025
        assert record.season == "spring"
        assert record.species_name == "Solanum lycopersicum"
        assert record.common_name == "Tomato"
        assert record.family == "Solanaceae"
        assert record.nutrient_demand == "heavy"
        assert record.area_id == "bed-001"

    def test_to_dict(self) -> None:
        record = PlantingRecord(
            year=2024,
            season="summer",
            species_name="Cucumis sativus",
            common_name="Cucumber",
            family="Cucurbitaceae",
            nutrient_demand="heavy",
            area_id="bed-002",
        )
        d = record.to_dict()
        assert d["year"] == 2024
        assert d["season"] == "summer"
        assert d["species_name"] == "Cucumis sativus"
        assert d["common_name"] == "Cucumber"
        assert d["family"] == "Cucurbitaceae"
        assert d["nutrient_demand"] == "heavy"
        assert d["area_id"] == "bed-002"

    def test_from_dict(self) -> None:
        d = {
            "year": 2023,
            "season": "fall",
            "species_name": "Phaseolus vulgaris",
            "common_name": "Bean (Bush)",
            "family": "Fabaceae",
            "nutrient_demand": "fixer",
            "area_id": "bed-003",
        }
        record = PlantingRecord.from_dict(d)
        assert record.year == 2023
        assert record.season == "fall"
        assert record.family == "Fabaceae"
        assert record.nutrient_demand == "fixer"

    def test_from_dict_defaults(self) -> None:
        d = {"year": 2024, "season": "spring"}
        record = PlantingRecord.from_dict(d)
        assert record.species_name == ""
        assert record.common_name == ""
        assert record.family == ""
        assert record.nutrient_demand == ""
        assert record.area_id == ""

    def test_roundtrip(self) -> None:
        original = PlantingRecord(
            year=2025,
            season="winter",
            species_name="Vicia faba",
            common_name="Broad Bean",
            family="Fabaceae",
            nutrient_demand="fixer",
            area_id="bed-004",
        )
        restored = PlantingRecord.from_dict(original.to_dict())
        assert restored.year == original.year
        assert restored.season == original.season
        assert restored.species_name == original.species_name
        assert restored.common_name == original.common_name
        assert restored.family == original.family
        assert restored.nutrient_demand == original.nutrient_demand
        assert restored.area_id == original.area_id


# ─── CropRotationHistory Tests ────────────────────────────────────────────────


@pytest.fixture
def sample_history() -> CropRotationHistory:
    """History with records across 3 years, 2 beds."""
    records = [
        PlantingRecord(2023, "spring", "Solanum lycopersicum", "Tomato", "Solanaceae", "heavy", "bed-A"),
        PlantingRecord(2023, "summer", "Cucumis sativus", "Cucumber", "Cucurbitaceae", "heavy", "bed-B"),
        PlantingRecord(2024, "spring", "Phaseolus vulgaris", "Bean", "Fabaceae", "fixer", "bed-A"),
        PlantingRecord(2024, "spring", "Brassica oleracea var. capitata", "Cabbage", "Brassicaceae", "heavy", "bed-B"),
        PlantingRecord(2025, "spring", "Daucus carota", "Carrot", "Apiaceae", "light", "bed-A"),
    ]
    return CropRotationHistory(records=records)


class TestCropRotationHistory:
    def test_add_record(self) -> None:
        history = CropRotationHistory()
        record = PlantingRecord(2025, "spring", "Tomato", "Tomato", "Solanaceae", "heavy", "bed-1")
        history.add_record(record)
        assert len(history.records) == 1
        assert history.records[0] is record

    def test_remove_record(self) -> None:
        record = PlantingRecord(2025, "spring", "Tomato", "Tomato", "Solanaceae", "heavy", "bed-1")
        history = CropRotationHistory(records=[record])
        history.remove_record(record)
        assert len(history.records) == 0

    def test_get_records_for_area(self, sample_history: CropRotationHistory) -> None:
        records = sample_history.get_records_for_area("bed-A")
        assert len(records) == 3
        # Should be sorted year descending
        assert records[0].year == 2025
        assert records[1].year == 2024
        assert records[2].year == 2023

    def test_get_records_for_area_empty(self, sample_history: CropRotationHistory) -> None:
        records = sample_history.get_records_for_area("nonexistent")
        assert records == []

    def test_get_records_for_year(self, sample_history: CropRotationHistory) -> None:
        records = sample_history.get_records_for_year(2024)
        assert len(records) == 2

    def test_get_families_for_area(self, sample_history: CropRotationHistory) -> None:
        families = sample_history.get_families_for_area("bed-A", last_n_years=3)
        assert "Solanaceae" in families
        assert "Fabaceae" in families
        assert "Apiaceae" in families

    def test_get_families_for_area_limited_years(self, sample_history: CropRotationHistory) -> None:
        families = sample_history.get_families_for_area("bed-A", last_n_years=1)
        # Only 2025 records
        assert families == ["Apiaceae"]

    def test_get_families_for_area_empty(self, sample_history: CropRotationHistory) -> None:
        families = sample_history.get_families_for_area("nonexistent")
        assert families == []

    def test_to_dict(self, sample_history: CropRotationHistory) -> None:
        d = sample_history.to_dict()
        assert "records" in d
        assert len(d["records"]) == 5
        assert d["records"][0]["year"] == 2023

    def test_from_dict(self) -> None:
        d = {
            "records": [
                {
                    "year": 2025,
                    "season": "spring",
                    "species_name": "Tomato",
                    "family": "Solanaceae",
                    "nutrient_demand": "heavy",
                    "area_id": "bed-1",
                }
            ]
        }
        history = CropRotationHistory.from_dict(d)
        assert len(history.records) == 1
        assert history.records[0].family == "Solanaceae"

    def test_from_dict_empty(self) -> None:
        history = CropRotationHistory.from_dict({})
        assert len(history.records) == 0

    def test_roundtrip(self, sample_history: CropRotationHistory) -> None:
        d = sample_history.to_dict()
        restored = CropRotationHistory.from_dict(d)
        assert len(restored.records) == len(sample_history.records)
        for orig, rest in zip(sample_history.records, restored.records):
            assert orig.year == rest.year
            assert orig.season == rest.season
            assert orig.species_name == rest.species_name
            assert orig.family == rest.family
            assert orig.nutrient_demand == rest.nutrient_demand
            assert orig.area_id == rest.area_id


# ─── Constants Tests ──────────────────────────────────────────────────────────


class TestConstants:
    def test_nutrient_demands(self) -> None:
        assert "heavy" in NUTRIENT_DEMANDS
        assert "medium" in NUTRIENT_DEMANDS
        assert "light" in NUTRIENT_DEMANDS
        assert "fixer" in NUTRIENT_DEMANDS

    def test_seasons(self) -> None:
        assert "spring" in SEASONS
        assert "summer" in SEASONS
        assert "fall" in SEASONS
        assert "winter" in SEASONS


# ─── Planting Calendar Integration Tests ──────────────────────────────────────


class TestPlantingCalendarCropRotationData:
    """Verify that plant_species.json has family and nutrient_demand for all species."""

    def test_all_species_have_family(self) -> None:
        import json
        from pathlib import Path

        calendar_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "open_garden_planner"
            / "resources"
            / "data"
            / "plant_species.json"
        )
        with open(calendar_path, encoding="utf-8") as f:
            data = json.load(f)

        for plant in data["plants"]:
            assert plant.get("family"), (
                f"{plant['common_name']} ({plant['scientific_name']}) missing family"
            )

    def test_all_species_have_nutrient_demand(self) -> None:
        import json
        from pathlib import Path

        calendar_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "open_garden_planner"
            / "resources"
            / "data"
            / "plant_species.json"
        )
        with open(calendar_path, encoding="utf-8") as f:
            data = json.load(f)

        for plant in data["plants"]:
            assert plant.get("nutrient_demand") in NUTRIENT_DEMANDS, (
                f"{plant['common_name']} ({plant['scientific_name']}) has invalid "
                f"nutrient_demand: {plant.get('nutrient_demand')}"
            )

    def test_at_least_60_species(self) -> None:
        import json
        from pathlib import Path

        calendar_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "open_garden_planner"
            / "resources"
            / "data"
            / "plant_species.json"
        )
        with open(calendar_path, encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["plants"]) >= 60


# ─── PlantSpeciesData Integration ─────────────────────────────────────────────


class TestPlantSpeciesDataNutrientDemand:
    """Verify nutrient_demand field in PlantSpeciesData model."""

    def test_nutrient_demand_field_exists(self) -> None:
        from open_garden_planner.models.plant_data import PlantSpeciesData

        plant = PlantSpeciesData(
            scientific_name="Solanum lycopersicum",
            common_name="Tomato",
            nutrient_demand="heavy",
        )
        assert plant.nutrient_demand == "heavy"

    def test_nutrient_demand_default_none(self) -> None:
        from open_garden_planner.models.plant_data import PlantSpeciesData

        plant = PlantSpeciesData(
            scientific_name="Test",
            common_name="Test",
        )
        assert plant.nutrient_demand is None

    def test_nutrient_demand_serialization(self) -> None:
        from open_garden_planner.models.plant_data import PlantSpeciesData

        plant = PlantSpeciesData(
            scientific_name="Solanum lycopersicum",
            common_name="Tomato",
            nutrient_demand="heavy",
        )
        d = plant.to_dict()
        assert d["nutrient_demand"] == "heavy"

        restored = PlantSpeciesData.from_dict(d)
        assert restored.nutrient_demand == "heavy"

    def test_nutrient_demand_none_serialization(self) -> None:
        from open_garden_planner.models.plant_data import PlantSpeciesData

        plant = PlantSpeciesData(
            scientific_name="Test",
            common_name="Test",
        )
        d = plant.to_dict()
        assert d["nutrient_demand"] is None

        restored = PlantSpeciesData.from_dict(d)
        assert restored.nutrient_demand is None
