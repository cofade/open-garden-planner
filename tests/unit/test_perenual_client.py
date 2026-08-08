"""Unit tests for PerenualClient._parse_species() (issue #296).

First-ever test coverage for this client. The primary target is a real,
live-reproduced crash: a present key with a JSON null value (common in
Perenual's public dataset for sparse records) used to reach a bare
.lower()/.join() and raise AttributeError, silently dropping the whole
record from search results.
"""

from __future__ import annotations

from open_garden_planner.models.plant_data import PlantCycle, SunRequirement, WaterNeeds
from open_garden_planner.services.plant_api.perenual_client import PerenualClient


class TestParseSpeciesNullSafety:
    def test_null_cycle_watering_sunlight_do_not_crash(self) -> None:
        client = PerenualClient(api_key="key")
        payload = {
            "id": 1,
            "common_name": "Test",
            "scientific_name": ["Testus nullicus"],
            "cycle": None,
            "watering": None,
            "sunlight": None,
            "description": None,
        }

        result = client._parse_species(payload)

        assert result.cycle == PlantCycle.UNKNOWN
        assert result.water_needs == WaterNeeds.UNKNOWN
        assert result.sun_requirement == SunRequirement.UNKNOWN
        assert result.description == ""

    def test_null_scientific_name_and_common_name_fall_back_to_unknown(self) -> None:
        client = PerenualClient(api_key="key")
        payload = {"id": 1, "common_name": None, "scientific_name": None}

        result = client._parse_species(payload)

        assert result.common_name == "Unknown"
        assert result.scientific_name == "Unknown"

    def test_empty_scientific_name_list_falls_back_to_unknown(self) -> None:
        client = PerenualClient(api_key="key")
        payload = {"id": 1, "common_name": "Test", "scientific_name": []}

        result = client._parse_species(payload)

        assert result.scientific_name == "Unknown"

    def test_premium_gated_upsell_string_does_not_crash_or_misparse(self) -> None:
        """Live-observed: a premium-gated record returns the literal string
        "Upgrade Plans To Premium/Supreme - ..." for cycle/watering/sunlight
        instead of real data or null. `sunlight` in particular must not be
        treated as a list (join()ing a string iterates it character by
        character) -- it should simply fail to match and stay UNKNOWN.
        """
        client = PerenualClient(api_key="key")
        upsell = "Upgrade Plans To Premium/Supreme - https://perenual.com/subscription-api-pricing. I'm sorry"
        payload = {
            "id": 3849,
            "common_name": "hosta",
            "scientific_name": ["Hosta 'Cherry Tomato'"],
            "cycle": upsell,
            "watering": upsell,
            "sunlight": upsell,
        }

        result = client._parse_species(payload)

        assert result.cycle == PlantCycle.UNKNOWN
        assert result.water_needs == WaterNeeds.UNKNOWN
        assert result.sun_requirement == SunRequirement.UNKNOWN


class TestParseSpeciesPositiveControl:
    def test_well_formed_payload_parses_correctly(self) -> None:
        client = PerenualClient(api_key="key")
        payload = {
            "id": 42,
            "common_name": "Sunflower",
            "scientific_name": ["Helianthus annuus"],
            "cycle": "annual",
            "watering": "average",
            "sunlight": ["full sun"],
            "description": "A tall annual flower.",
            "default_image": {"original_url": "https://example/img.jpg", "thumbnail": "https://example/thumb.jpg"},
        }

        result = client._parse_species(payload)

        assert result.common_name == "Sunflower"
        assert result.scientific_name == "Helianthus annuus"
        assert result.cycle == PlantCycle.ANNUAL
        assert result.water_needs == WaterNeeds.MEDIUM
        assert result.sun_requirement == SunRequirement.FULL_SUN
        assert result.description == "A tall annual flower."
        assert result.image_url == "https://example/img.jpg"
        assert result.thumbnail_url == "https://example/thumb.jpg"
