"""Unit tests for TrefleClient._parse_species() field mapping (issue #296).

First-ever test coverage for this client. Pins the field mappings added by
the #296 audit -- ph_minimum/ph_maximum, soil_nutriments -> nutrient_demand,
and foliage.color/texture -- using live-observed values (Trefle's Carrot
record: ph 6.5-7.0, soil_nutriments 6).
"""

from __future__ import annotations

from open_garden_planner.services.plant_api.trefle_client import TrefleClient


class TestSoilAndPhMapping:
    def test_ph_minimum_and_maximum_map_directly(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {
            "id": 1,
            "common_name": "Carrot",
            "scientific_name": "Daucus carota",
            "specifications": {"ph_minimum": 6.5, "ph_maximum": 7.0},
        }

        result = client._parse_species(payload)

        assert result.ph_min == 6.5
        assert result.ph_max == 7.0

    def test_missing_ph_stays_none(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {"id": 1, "common_name": "Test", "scientific_name": "Testus"}

        result = client._parse_species(payload)

        assert result.ph_min is None
        assert result.ph_max is None

    def test_soil_nutriments_high_maps_to_heavy_demand(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {
            "id": 1,
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "growth": {"soil_nutriments": 8},
        }

        result = client._parse_species(payload)

        assert result.nutrient_demand == "heavy"

    def test_soil_nutriments_mid_maps_to_medium_demand(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {
            "id": 1,
            "common_name": "Carrot",
            "scientific_name": "Daucus carota",
            "growth": {"soil_nutriments": 6},
        }

        result = client._parse_species(payload)

        assert result.nutrient_demand == "medium"

    def test_soil_nutriments_low_maps_to_light_demand(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {
            "id": 1,
            "common_name": "Test",
            "scientific_name": "Testus",
            "growth": {"soil_nutriments": 2},
        }

        result = client._parse_species(payload)

        assert result.nutrient_demand == "light"

    def test_missing_soil_nutriments_stays_none(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {"id": 1, "common_name": "Test", "scientific_name": "Testus", "growth": {}}

        result = client._parse_species(payload)

        assert result.nutrient_demand is None


class TestFoliageMapping:
    def test_foliage_color_list_joins_and_texture_maps(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {
            "id": 1,
            "common_name": "Test",
            "scientific_name": "Testus",
            "foliage": {"color": ["green", "silver"], "texture": "fine"},
        }

        result = client._parse_species(payload)

        assert result.foliage_color == "green, silver"
        assert result.foliage_texture == "fine"

    def test_missing_foliage_stays_empty_strings(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {"id": 1, "common_name": "Test", "scientific_name": "Testus"}

        result = client._parse_species(payload)

        assert result.foliage_color == ""
        assert result.foliage_texture == ""

    def test_null_foliage_values_do_not_crash(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {
            "id": 1,
            "common_name": "Test",
            "scientific_name": "Testus",
            "foliage": {"color": None, "texture": None},
        }

        result = client._parse_species(payload)

        assert result.foliage_color == ""
        assert result.foliage_texture == ""


class TestEdibleNullSafety:
    def test_null_edible_does_not_crash_and_is_falsy(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {"id": 1, "common_name": "Test", "scientific_name": "Testus", "edible": None}

        result = client._parse_species(payload)

        assert result.edible is False
