"""Round-trip tests for ``PlantSpeciesData.to_dict`` / ``from_dict``.

Regression coverage for the silent serialization gap that made US-12.10d
plant-soil mismatch warnings fail: ``n_demand`` / ``p_demand`` / ``k_demand``
were defined on the dataclass but never serialized, so any plant whose
metadata was written to canvas state and read back lost those fields.

The full-roundtrip test below would have caught it.
"""
from __future__ import annotations

from dataclasses import fields

from open_garden_planner.models.plant_data import (
    FlowerType,
    GrowthRate,
    PlantCycle,
    PlantSpeciesData,
    PollinationType,
    SunRequirement,
    WaterNeeds,
)


def _full_spec() -> PlantSpeciesData:
    """A spec with every field set to a non-default value."""
    return PlantSpeciesData(
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        family="Solanaceae",
        genus="Solanum",
        cycle=PlantCycle.PERENNIAL,
        growth_rate=GrowthRate.FAST,
        flower_type=FlowerType.MONOECIOUS,
        pollination_type=PollinationType.SELF_FERTILE,
        min_height_cm=120.0,
        max_height_cm=240.0,
        min_spread_cm=40.0,
        max_spread_cm=60.0,
        sun_requirement=SunRequirement.FULL_SUN,
        water_needs=WaterNeeds.HIGH,
        hardiness_zone_min=10,
        hardiness_zone_max=11,
        soil_type="Well-drained loam",
        ph_min=5.8,
        ph_max=7.0,
        edible=True,
        edible_parts=["fruit"],
        flowering=True,
        flower_color="yellow",
        foliage_color="green",
        foliage_texture="medium",
        image_url="https://example.com/tomato.jpg",
        thumbnail_url="https://example.com/tomato_thumb.jpg",
        data_source="custom",
        source_id="42",
        description="Classic garden tomato.",
        indoor_sow_start=-8,
        indoor_sow_end=-6,
        direct_sow_start=2,
        direct_sow_end=4,
        transplant_start=4,
        transplant_end=6,
        harvest_start=12,
        harvest_end=20,
        days_to_germination_min=5,
        days_to_germination_max=10,
        days_to_maturity_min=70,
        days_to_maturity_max=85,
        frost_tolerance="tender",
        min_germination_temp_c=15.0,
        seed_depth_cm=0.6,
        prick_out_after_days=14,
        harden_off_days=7,
        nutrient_demand="heavy",
        n_demand="high",
        p_demand="medium",
        k_demand="high",
        raw_data={"perenual_id": 12345},
    )


class TestPlantSpeciesDataRoundTrip:
    def test_every_dataclass_field_appears_in_to_dict(self) -> None:
        """to_dict() must serialize every field on the dataclass."""
        spec = _full_spec()
        d = spec.to_dict()
        for f in fields(PlantSpeciesData):
            assert f.name in d, f"{f.name!r} missing from to_dict() output"

    def test_full_roundtrip_preserves_every_value(self) -> None:
        """from_dict(to_dict(x)) must equal x for every populated field."""
        original = _full_spec()
        revived = PlantSpeciesData.from_dict(original.to_dict())
        assert revived == original, (
            "Round-trip changed at least one field. "
            "If a new field was added to the dataclass, update both "
            "to_dict() and from_dict()."
        )

    def test_npk_demand_survives_roundtrip(self) -> None:
        """Regression: US-12.10d mismatch detection silently dropped these."""
        spec = PlantSpeciesData(
            scientific_name="X",
            common_name="X",
            n_demand="high",
            p_demand="low",
            k_demand="medium",
        )
        revived = PlantSpeciesData.from_dict(spec.to_dict())
        assert revived.n_demand == "high"
        assert revived.p_demand == "low"
        assert revived.k_demand == "medium"

    def test_legacy_dict_without_npk_demand_loads_as_none(self) -> None:
        """Older saved files lack n/p/k_demand; from_dict must default to None."""
        legacy = {
            "scientific_name": "X",
            "common_name": "X",
            "cycle": "unknown",
            "growth_rate": "unknown",
            "flower_type": "unknown",
            "pollination_type": "unknown",
            "sun_requirement": "unknown",
            "water_needs": "unknown",
            "nutrient_demand": "heavy",
        }
        revived = PlantSpeciesData.from_dict(legacy)
        assert revived.n_demand is None
        assert revived.p_demand is None
        assert revived.k_demand is None
        assert revived.nutrient_demand == "heavy"
