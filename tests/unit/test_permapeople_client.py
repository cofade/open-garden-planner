"""Unit tests for PermapeopleClient.is_available() (issue #294).

The connectivity probe must request a bounded page, not the full unfiltered
plant list -- the root cause of "Could not connect to Permapeople. Please
check your credentials." being shown for perfectly valid credentials.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from open_garden_planner.models.plant_data import PlantCycle
from open_garden_planner.services.plant_api.base import PlantAPIError
from open_garden_planner.services.plant_api.permapeople_client import PermapeopleClient


def _fake_response(status_code: int) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    return response


class TestIsAvailable:
    def test_false_when_credentials_missing(self) -> None:
        # Empty key_id/key_secret fall back to the environment variables
        # inside __init__ -- the autouse _isolate_plant_api_credentials
        # fixture (conftest.py) keeps a real local .env from leaking in here.
        client = PermapeopleClient(key_id="", key_secret="")
        client._session.get = MagicMock()

        assert client.is_available() is False
        client._session.get.assert_not_called()

    def test_true_on_200(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        client._session.get = MagicMock(return_value=_fake_response(200))

        assert client.is_available() is True

    def test_false_on_401_invalid_credentials(self) -> None:
        client = PermapeopleClient(key_id="bad-id", key_secret="bad-secret")
        client._session.get = MagicMock(return_value=_fake_response(401))

        assert client.is_available() is False

    def test_false_on_403_forbidden(self) -> None:
        client = PermapeopleClient(key_id="bad-id", key_secret="bad-secret")
        client._session.get = MagicMock(return_value=_fake_response(403))

        assert client.is_available() is False

    def test_raises_on_server_error(self) -> None:
        """A 5xx/429 is a server-side problem, not a rejected credential
        (issue #294 follow-up): it must not collapse into the same False as
        401/403, or "check your credentials" reappears for an outage.
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        client._session.get = MagicMock(return_value=_fake_response(503))

        with pytest.raises(PlantAPIError):
            client.is_available()

    def test_raises_on_network_timeout(self) -> None:
        """A genuine network failure must surface distinctly from a rejected
        credential (issue #294 follow-up): swallowing it to a bare False is
        what let the Preferences dialog blame "check your credentials" for a
        connectivity problem that had nothing to do with the credentials.
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        client._session.get = MagicMock(side_effect=requests.exceptions.ReadTimeout("timed out"))

        with pytest.raises(PlantAPIError):
            client.is_available()

    def test_probe_requests_a_bounded_page_not_the_full_list(self) -> None:
        """Regression pin for issue #294.

        The unfiltered default page (~100 full records, ~250KB) measured
        6.1-6.4s against the live API -- over the timeout that was in force,
        so valid credentials were reported as a connection failure. The
        probe must ask for a single record.
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        mock_get = MagicMock(return_value=_fake_response(200))
        client._session.get = mock_get

        client.is_available()

        _, kwargs = mock_get.call_args
        assert kwargs["params"].get("per_page") == 1, (
            "is_available() must bound the page size -- fetching the full "
            "plant list is what caused the original timeout-driven false negative"
        )


def _data_item(key: str, value) -> dict:
    return {"key": key, "value": value}


class TestParseSpeciesNullSafety:
    """Regression pins for issue #296.

    A present key with a JSON ``null`` value is common in real Permapeople
    records. Every lookup that chains ``.lower()``/``.split()`` off a
    ``data_dict`` value used to crash the whole record on such a null,
    silently dropping it from search results (caught by a bare
    ``except Exception`` in ``search()``).
    """

    def test_null_values_in_data_array_do_not_crash(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 1,
            "name": "Test Plant",
            "scientific_name": "Testus nullicus",
            "data": [
                _data_item("Light requirement", None),
                _data_item("Water requirement", None),
                _data_item("Growth", None),
                _data_item("Edible", None),
                _data_item("Family", "Testaceae"),
            ],
        }

        result = client._parse_species(payload)

        assert result.family == "Testaceae"
        assert result.edible is False

    def test_missing_name_and_scientific_name_fall_back_to_unknown(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {"id": 1, "name": None, "scientific_name": None, "data": []}

        result = client._parse_species(payload)

        assert result.common_name == "Unknown"
        assert result.scientific_name == "Unknown"

    def test_null_id_does_not_become_the_string_none(self) -> None:
        """str(data.get("id", "")) turned a null id into the literal string
        "None" -- species_key() (ADR-016) prefers source_id, so every such
        record collapsed onto the same key "none" (#296 review).
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {"id": None, "name": "Test", "scientific_name": "Testus", "data": []}

        result = client._parse_species(payload)

        assert result.source_id == ""

    def test_null_description_does_not_become_none(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {"id": 1, "name": "Test", "scientific_name": "Testus", "data": [], "description": None}

        result = client._parse_species(payload)

        assert result.description == ""

    def test_null_data_array_does_not_crash(self) -> None:
        """A `"data": null` record must not crash iterating `data.get("data", [])`
        (the default only applies when the key is absent, same class of bug
        as the crashes above).
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {"id": 1, "name": "Test", "scientific_name": "Testus", "data": None}

        result = client._parse_species(payload)

        assert result.family == ""

    def test_non_string_data_value_does_not_crash(self) -> None:
        """A data-array value that's a JSON number/bool (not a string) must
        not crash the .lower() calls downstream -- data_dict is typed
        dict[str, str] but nothing enforced that against a real API payload.
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 1,
            "name": "Test",
            "scientific_name": "Testus",
            "data": [_data_item("Edible", True)],
        }

        result = client._parse_species(payload)

        assert result.edible is True


class TestParseSpeciesFieldMapping:
    """Field-mapping fixes from the #296 audit.

    Fixture values are the actual live values observed for Apple/Tomato
    during the audit, so these tests double as a live-data regression pin.
    """

    def test_life_cycle_maps_to_cycle(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 99,
            "name": "Apple",
            "scientific_name": "Malus domestica",
            "data": [_data_item("Life cycle", "Perennial")],
        }

        result = client._parse_species(payload)

        assert result.cycle == PlantCycle.PERENNIAL

    def test_multi_value_life_cycle_prefers_annual(self) -> None:
        """"Annual, Perennial" (Permapeople's actual Tomato record) -- keeps
        the same annual > biennial > perennial precedence used elsewhere in
        this file (Trefle/Perenual duration parsing).
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 182,
            "name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "data": [_data_item("Life cycle", "Annual, Perennial")],
        }

        result = client._parse_species(payload)

        assert result.cycle == PlantCycle.ANNUAL

    def test_height_and_width_convert_meters_to_cm(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 99,
            "name": "Apple",
            "scientific_name": "Malus domestica",
            "data": [_data_item("Height", "10.0"), _data_item("Width", "9")],
        }

        result = client._parse_species(payload)

        assert result.max_height_cm == 1000.0
        assert result.max_spread_cm == 900.0

    def test_missing_height_and_width_stay_none(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {"id": 1, "name": "Test", "scientific_name": "Testus", "data": []}

        result = client._parse_species(payload)

        assert result.max_height_cm is None
        assert result.max_spread_cm is None

    def test_height_range_with_unit_suffix_uses_upper_bound(self) -> None:
        """Live-observed format: some records give a range with a trailing
        unit suffix (e.g. "15-32m") instead of a bare number. The upper
        bound is the mature-size figure we want.
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 1,
            "name": "Test",
            "scientific_name": "Testus",
            "data": [_data_item("Height", "15-32m")],
        }

        result = client._parse_species(payload)

        assert result.max_height_cm == 3200.0

    def test_genus_is_read_from_data_array(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 99,
            "name": "Apple",
            "scientific_name": "Malus domestica",
            "data": [_data_item("Genus", "Malus")],
        }

        result = client._parse_species(payload)

        assert result.genus == "Malus"

    def test_soil_ph_range_maps_to_ph_min_max(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 182,
            "name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "data": [_data_item("Soil pH", "6.2-6.8")],
        }

        result = client._parse_species(payload)

        assert result.ph_min == 6.2
        assert result.ph_max == 6.8

    def test_soil_ph_range_with_en_dash_still_parses(self) -> None:
        """At least one live Permapeople record uses an en dash instead of a
        plain hyphen as the range separator.
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 1,
            "name": "Test",
            "scientific_name": "Testus",
            "data": [_data_item("Soil pH", "4.5–8.7")],
        }

        result = client._parse_species(payload)

        assert result.ph_min == 4.5
        assert result.ph_max == 8.7

    def test_single_soil_ph_value_stays_none(self) -> None:
        """A single value (no range) is an optimum, not a hard band -- setting
        both ph_min and ph_max to it collapses the acceptable range to zero
        width and made soil_service's tight (+/-0.05) tolerance fire a false
        mismatch for any real-world reading that wasn't that exact value
        (live-observed: Permapeople's "Walking onion" record, #296 review).
        """
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 1,
            "name": "Test",
            "scientific_name": "Testus",
            "data": [_data_item("Soil pH", "6.5")],
        }

        result = client._parse_species(payload)

        assert result.ph_min is None
        assert result.ph_max is None

    def test_missing_soil_ph_stays_none(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {"id": 1, "name": "Test", "scientific_name": "Testus", "data": []}

        result = client._parse_species(payload)

        assert result.ph_min is None
        assert result.ph_max is None

    def test_images_map_to_image_and_thumbnail_url(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {
            "id": 99,
            "name": "Apple",
            "scientific_name": "Malus domestica",
            "data": [],
            "images": {
                "thumb": "https://cdn.permapeople.org/thumb",
                "title": "https://cdn.permapeople.org/title",
            },
        }

        result = client._parse_species(payload)

        assert result.image_url == "https://cdn.permapeople.org/title"
        assert result.thumbnail_url == "https://cdn.permapeople.org/thumb"

    def test_missing_images_stay_empty_strings(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        payload = {"id": 1, "name": "Test", "scientific_name": "Testus", "data": []}

        result = client._parse_species(payload)

        assert result.image_url == ""
        assert result.thumbnail_url == ""


class TestGetByIdSourceIdContract:
    """Pins the id-space assumption `PlantAPIClient.get_by_id()`'s docstring
    depends on (#297 senior-review round 3): unlike Trefle's nested
    `main_species` indirection, Permapeople's `/plants/{id}` returns the
    requested record directly at the top level, so `source_id` (`str(
    data.get("id") or "")`) should equal the requested id by construction.
    Reasoned from the request/response shape in `get_by_id()` and
    `_parse_species()`, NOT captured from a live call -- unlike the
    equivalent Trefle test, which pins a live-captured shape.
    """

    def test_get_by_id_source_id_matches_requested_id(self) -> None:
        client = PermapeopleClient(key_id="id", key_secret="secret")
        requested_id = "99"

        with patch.object(client, "_session") as mock_session:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "id": 99,
                "name": "Apple",
                "scientific_name": "Malus domestica",
                "data": [],
            }
            mock_session.get.return_value = mock_response

            result = client.get_by_id(requested_id)

        assert result.source_id == requested_id
