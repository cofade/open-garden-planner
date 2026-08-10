"""Unit tests for TrefleClient._parse_species() field mapping (issue #296).

First-ever test coverage for this client. Pins the field mappings added by
the #296 audit -- ph_minimum/ph_maximum, soil_nutriments -> nutrient_demand,
and foliage.color/texture -- using live-observed values (Trefle's Carrot
record: ph 6.5-7.0, soil_nutriments 6).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from open_garden_planner.services.plant_api.trefle_client import TrefleClient

# Trimmed from a live `GET /api/v1/species/daucus-carota` response captured
# during the #296 audit -- pins the real object nesting (ph_minimum/maximum
# and soil_nutriments live under `growth`, NOT `specifications`; the first
# cut of this fix read them from `specifications` and shipped a payload here
# that matched that mistake instead of the real API, so the test passed on
# broken code). Trimmed to just the fields these tests exercise.
LIVE_CARROT_DETAIL = {
    "id": 171170,
    "common_name": "Carrot",
    "scientific_name": "Daucus carota",
    "specifications": {
        "growth_habit": "Forb/herb",
        "average_height": {"cm": None},
        "maximum_height": {"cm": None},
        "nitrogen_fixation": None,
    },
    "growth": {
        "ph_maximum": 7.0,
        "ph_minimum": 6.5,
        "light": 8,
        "atmospheric_humidity": 5,
        "soil_nutriments": 6,
        "soil_salinity": 0,
    },
}


class TestSoilAndPhMapping:
    def test_ph_minimum_and_maximum_map_directly(self) -> None:
        client = TrefleClient(api_token="token")

        result = client._parse_species(LIVE_CARROT_DETAIL)

        assert result.ph_min == 6.5
        assert result.ph_max == 7.0

    def test_ph_under_specifications_is_not_read(self) -> None:
        """Regression pin for the growth-vs-specifications mixup (#296 review).

        Trefle never actually puts ph_minimum/ph_maximum under
        `specifications` -- if a future edit moves the read back there by
        mistake, this payload (real shape, no `growth` block) must still
        come back None rather than silently succeed.
        """
        client = TrefleClient(api_token="token")
        payload = {
            "id": 1,
            "common_name": "Test",
            "scientific_name": "Testus",
            "specifications": {"ph_minimum": 6.5, "ph_maximum": 7.0},
        }

        result = client._parse_species(payload)

        assert result.ph_min is None
        assert result.ph_max is None

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

        result = client._parse_species(LIVE_CARROT_DETAIL)

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

    def test_non_list_foliage_color_does_not_crash(self) -> None:
        """Defensive: nothing in a live sample shows foliage.color as
        anything but a list, but a bare-string value must not reach
        " ".join() char-by-char the way Perenual's premium-gated `sunlight`
        did (#296).
        """
        client = TrefleClient(api_token="token")
        payload = {
            "id": 1,
            "common_name": "Test",
            "scientific_name": "Testus",
            "foliage": {"color": "green", "texture": "fine"},
        }

        result = client._parse_species(payload)

        assert result.foliage_color == ""

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


class TestSourceIdNullSafety:
    def test_null_id_does_not_become_the_string_none(self) -> None:
        client = TrefleClient(api_token="token")
        payload = {"id": None, "common_name": "Test", "scientific_name": "Testus"}

        result = client._parse_species(payload)

        assert result.source_id == ""


class TestGetByIdSourceIdContract:
    """Pins the id-space behavior `PlantAPIClient.get_by_id()`'s docstring
    depends on (#297 senior-review round 2): a `/plants/{id}` response's
    top-level `data.id` (a Trefle "plant" record) is live-confirmed to be a
    DIFFERENT id than `data.main_species.id` (the species record) for the
    same request -- captured live for carrot (requested 171170, top-level
    data.id came back 171241, main_species.id came back 171170) and
    reproduced on tomato/apple/basil during the #297 investigation.
    `get_by_id()` must take `source_id` from the nested `main_species.id`,
    which is what a caller actually requested and what `PlantSearchDialog`'s
    validation guard (`detail.source_id != plant.source_id`) depends on to
    tell a genuine response apart from an empty/wrong one.
    """

    def test_get_by_id_source_id_matches_requested_id_not_top_level_data_id(self) -> None:
        client = TrefleClient(api_token="token")
        requested_id = "171170"
        # Shape captured live from GET /api/v1/plants/171170 during the #297
        # investigation, trimmed to the fields this test exercises.
        response_payload = {
            "data": {
                "id": 171241,  # a different, unrelated "plant" id -- must be ignored
                "main_species": {
                    "id": 171170,
                    "common_name": "Carrot",
                    "scientific_name": "Daucus carota",
                },
            }
        }

        with patch.object(client, "_session") as mock_session:
            mock_response = MagicMock()
            mock_response.json.return_value = response_payload
            mock_session.get.return_value = mock_response

            result = client.get_by_id(requested_id)

        assert result.source_id == requested_id
