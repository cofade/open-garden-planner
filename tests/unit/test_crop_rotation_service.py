"""Unit tests for US-10.6: Crop rotation service and recommendations."""
from __future__ import annotations

import pytest

from open_garden_planner.models.crop_rotation import (
    CropRotationHistory,
    PlantingRecord,
)
from open_garden_planner.services.crop_rotation_service import (
    CropRotationService,
    RotationStatus,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def empty_service() -> CropRotationService:
    return CropRotationService()


@pytest.fixture
def service_with_history() -> CropRotationService:
    """Service with 3 years of history for bed-A."""
    records = [
        PlantingRecord(2023, "spring", "Solanum lycopersicum", "Tomato", "Solanaceae", "heavy", "bed-A"),
        PlantingRecord(2024, "spring", "Lactuca sativa", "Lettuce", "Asteraceae", "medium", "bed-A"),
        PlantingRecord(2025, "spring", "Daucus carota", "Carrot", "Apiaceae", "light", "bed-A"),
    ]
    return CropRotationService(history=CropRotationHistory(records=records))


@pytest.fixture
def service_with_violation() -> CropRotationService:
    """Service where same family was planted in consecutive years."""
    records = [
        PlantingRecord(2024, "spring", "Solanum lycopersicum", "Tomato", "Solanaceae", "heavy", "bed-B"),
        PlantingRecord(2025, "spring", "Solanum tuberosum", "Potato", "Solanaceae", "heavy", "bed-B"),
    ]
    return CropRotationService(history=CropRotationHistory(records=records))


# ─── Recommendation Tests ────────────────────────────────────────────────────


class TestGetRecommendation:
    def test_unknown_when_no_history(self, empty_service: CropRotationService) -> None:
        rec = empty_service.get_recommendation("bed-X")
        assert rec.status == RotationStatus.UNKNOWN
        assert rec.suggested_demand == "heavy"
        assert rec.avoid_families == []

    def test_good_rotation(self, service_with_history: CropRotationService) -> None:
        rec = service_with_history.get_recommendation("bed-A")
        assert rec.status == RotationStatus.GOOD
        assert rec.area_id == "bed-A"
        assert len(rec.last_records) == 3

    def test_violation_same_family(self, service_with_violation: CropRotationService) -> None:
        rec = service_with_violation.get_recommendation("bed-B")
        assert rec.status == RotationStatus.VIOLATION
        assert "Solanaceae" in rec.reason

    def test_avoid_families_populated(self, service_with_history: CropRotationService) -> None:
        rec = service_with_history.get_recommendation("bed-A")
        assert "Solanaceae" in rec.avoid_families
        assert "Asteraceae" in rec.avoid_families
        assert "Apiaceae" in rec.avoid_families

    def test_suggested_demand_follows_cycle(self, service_with_history: CropRotationService) -> None:
        # Last was "light", next should be "fixer"
        rec = service_with_history.get_recommendation("bed-A")
        assert rec.suggested_demand == "fixer"

    def test_suboptimal_demand_mismatch(self) -> None:
        """Heavy followed by light (should be medium) → suboptimal."""
        records = [
            PlantingRecord(2024, "spring", "Solanum lycopersicum", "Tomato", "Solanaceae", "heavy", "bed-C"),
            PlantingRecord(2025, "spring", "Daucus carota", "Carrot", "Apiaceae", "light", "bed-C"),
        ]
        service = CropRotationService(history=CropRotationHistory(records=records))
        rec = service.get_recommendation("bed-C")
        assert rec.status == RotationStatus.SUBOPTIMAL


# ─── Plant Placement Check Tests ─────────────────────────────────────────────


class TestCheckPlantPlacement:
    def test_good_placement_no_history(self, empty_service: CropRotationService) -> None:
        status, reason = empty_service.check_plant_placement(
            "bed-X", "Solanaceae", "heavy"
        )
        assert status == RotationStatus.GOOD

    def test_violation_same_family_recent(self, service_with_violation: CropRotationService) -> None:
        # Trying to plant another Solanaceae in bed-B after two consecutive Solanaceae
        status, reason = service_with_violation.check_plant_placement(
            "bed-B", "Solanaceae", "heavy"
        )
        assert status == RotationStatus.VIOLATION
        assert "Solanaceae" in reason

    def test_suboptimal_wrong_demand(self, service_with_history: CropRotationService) -> None:
        # Last was light, ideal is fixer, but we're placing heavy
        status, reason = service_with_history.check_plant_placement(
            "bed-A", "Poaceae", "heavy"
        )
        assert status == RotationStatus.SUBOPTIMAL
        assert "fixer" in reason

    def test_good_placement_correct_demand_new_family(self, service_with_history: CropRotationService) -> None:
        # Last was light, ideal is fixer, placing fixer with new family
        status, reason = service_with_history.check_plant_placement(
            "bed-A", "Fabaceae", "fixer"
        )
        # Fabaceae is NOT in recent history, demand matches → good
        assert status == RotationStatus.GOOD

    def test_good_placement_fully_new(self) -> None:
        """Completely new family + correct demand → good."""
        records = [
            PlantingRecord(2025, "spring", "Solanum lycopersicum", "Tomato", "Solanaceae", "heavy", "bed-D"),
        ]
        service = CropRotationService(history=CropRotationHistory(records=records))
        status, reason = service.check_plant_placement(
            "bed-D", "Amaranthaceae", "medium"
        )
        assert status == RotationStatus.GOOD


# ─── Demand Cycle Tests ──────────────────────────────────────────────────────


class TestDemandCycle:
    def test_heavy_to_medium(self) -> None:
        assert CropRotationService._next_demand("heavy") == "medium"

    def test_medium_to_light(self) -> None:
        assert CropRotationService._next_demand("medium") == "light"

    def test_light_to_fixer(self) -> None:
        assert CropRotationService._next_demand("light") == "fixer"

    def test_fixer_to_heavy(self) -> None:
        assert CropRotationService._next_demand("fixer") == "heavy"

    def test_unknown_defaults_to_heavy(self) -> None:
        assert CropRotationService._next_demand("unknown") == "heavy"
        assert CropRotationService._next_demand("") == "heavy"


# ─── Service State Tests ─────────────────────────────────────────────────────


class TestServiceState:
    def test_history_property(self) -> None:
        service = CropRotationService()
        assert len(service.history.records) == 0

    def test_set_history(self) -> None:
        service = CropRotationService()
        new_history = CropRotationHistory(records=[
            PlantingRecord(2025, "spring", "Tomato", "Tomato", "Solanaceae", "heavy", "bed-1"),
        ])
        service.history = new_history
        assert len(service.history.records) == 1

    def test_custom_cooldown(self) -> None:
        records = [
            PlantingRecord(2022, "spring", "Tomato", "Tomato", "Solanaceae", "heavy", "bed-E"),
            PlantingRecord(2023, "spring", "Bean", "Bean", "Fabaceae", "fixer", "bed-E"),
            PlantingRecord(2024, "spring", "Carrot", "Carrot", "Apiaceae", "light", "bed-E"),
            PlantingRecord(2025, "spring", "Tomato", "Tomato", "Solanaceae", "heavy", "bed-E"),
        ]
        # With default cooldown of 3, Solanaceae from 2022 would be in window
        service_3 = CropRotationService(
            history=CropRotationHistory(records=records), family_cooldown=3
        )
        rec_3 = service_3.get_recommendation("bed-E")
        # 2022 is within 3 years of max year 2025 (2025-3+1=2023, 2022 < 2023)
        # But Solanaceae appears in 2022 AND 2025, so it repeats
        assert "Solanaceae" in rec_3.avoid_families

        # With cooldown of 1, only 2025 matters
        service_1 = CropRotationService(
            history=CropRotationHistory(records=records), family_cooldown=1
        )
        rec_1 = service_1.get_recommendation("bed-E")
        assert rec_1.avoid_families == ["Solanaceae"]
