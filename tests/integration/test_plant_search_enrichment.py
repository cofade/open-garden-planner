"""Integration test: PlantSearchDialog enriches the confirmed plant with the
full detail record before returning it (issue #297).

Trefle's `/plants/search` response is sparse -- live-confirmed against the
real API during the #297 investigation: it carries only identity/taxonomy
fields (`id`, `common_name`, `scientific_name`, `family`, `genus`,
`image_url`, ...) and omits `growth`/`specifications`/`foliage` entirely.
`TrefleClient._parse_species()` reads sun/water/pH/nutrient/foliage from
those three objects, so a search-result `PlantSpeciesData` always has them at
their UNKNOWN/None defaults -- regardless of the #296 field-mapping fix --
unless something separately fetches the detail record. `get_by_id()` already
existed but nothing called it from the search-selection flow.

Only the HTTP layer (``requests.Session.get``) is mocked, so this exercises
the real dialog wiring end to end: search -> select -> confirm -> enriched
result, following the same real-widget-plus-mocked-HTTP pattern as
``test_plant_api_test_button.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from PyQt6.QtCore import Qt

from open_garden_planner.services.plant_api import PlantAPIManager
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog

# Trimmed to the fields these tests exercise; shape verified live against
# Trefle's real /plants/search and /plants/{id} responses during the #297
# investigation (search has no growth/specifications/foliage at all).
SEARCH_RESPONSE = {
    "data": [
        {
            "id": 171170,
            "common_name": "Carrot",
            "scientific_name": "Daucus carota",
            "family": "Apiaceae",
            "genus": "Daucus",
            "image_url": "https://example.com/carrot.jpg",
        }
    ]
}

# The top-level `data.id` (a Trefle "plant" record) is deliberately DIFFERENT
# from `data.main_species.id` (the species record) -- live-verified against
# the real API for carrot/tomato/apple/basil during the #297 review: a
# senior-review pass raised (and this fixture asymmetry disproves) the
# concern that get_by_id() might read the wrong nested id and silently
# mutate source_id/species_key. get_by_id() must read main_species.id (which
# equals the original search result's id in every live sample), not this
# top-level one.
DETAIL_RESPONSE = {
    "data": {
        "id": 171241,
        "main_species": {
            "id": 171170,
            "common_name": "Carrot",
            "scientific_name": "Daucus carota",
            "family": "Apiaceae",
            "genus": "Daucus",
            "image_url": "https://example.com/carrot.jpg",
            "growth": {
                "light": 8,
                "atmospheric_humidity": 5,
                "ph_minimum": 6.5,
                "ph_maximum": 7.0,
                "soil_nutriments": 6,
            },
            "foliage": {"color": ["green"], "texture": "fine"},
        },
    }
}

EMPTY_DETAIL_RESPONSE = {"data": {"main_species": {}}}

MALFORMED_DETAIL_RESPONSE = {"data": ["not", "a", "dict"]}


def _fake_get(url, params=None, timeout=None):
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = DETAIL_RESPONSE if url.endswith("/plants/171170") else SEARCH_RESPONSE
    return response


class _EmptyLibrary:
    """Stand-in for the user's real custom-plant library.

    ``PlantLibrary`` reads/writes a real file under the OS app-data
    directory and isn't isolated by ``tests/conftest.py`` -- searching
    "carrot" for real could pick up a developer's own custom entry and make
    this test's result set non-deterministic. None of these tests are about
    the custom-library merge path, so it's stubbed to always report no
    matches.
    """

    def search_plants(self, query: str) -> list:
        return []


@pytest.fixture()
def dialog(qtbot, monkeypatch):
    monkeypatch.setattr("requests.Session.get", MagicMock(side_effect=_fake_get))
    monkeypatch.setattr(
        "open_garden_planner.services.plant_library.get_plant_library",
        lambda: _EmptyLibrary(),
    )
    manager = PlantAPIManager(trefle_api_token="fake-token")
    dlg = PlantSearchDialog(manager)
    qtbot.addWidget(dlg)
    dlg.search_input.setText("carrot")
    dlg._perform_search()
    dlg.results_list.setCurrentRow(0)
    return dlg


class TestSearchResultEnrichment:
    def test_search_result_is_sparse_before_accept(self, dialog: PlantSearchDialog) -> None:
        """Baseline: proves the search response really is missing the fields
        (i.e. this isn't a test artifact) before the fix's behavior is
        exercised below.
        """
        plant = dialog.selected_plant
        assert plant is not None
        assert plant.sun_requirement.value == "unknown"
        assert plant.water_needs.value == "unknown"
        assert plant.ph_min is None
        assert plant.foliage_color == ""

    def test_accept_enriches_with_growth_specifications_data(
        self, dialog: PlantSearchDialog, qtbot
    ) -> None:
        qtbot.mouseClick(dialog.ok_button, Qt.MouseButton.LeftButton)

        assert dialog.result() == dialog.DialogCode.Accepted
        enriched = dialog.selected_plant
        assert enriched is not None
        assert enriched.sun_requirement.value == "full_sun"
        assert enriched.water_needs.value == "medium"
        assert enriched.ph_min == 6.5
        assert enriched.ph_max == 7.0
        assert enriched.nutrient_demand == "medium"
        assert enriched.foliage_color == "green"
        assert enriched.foliage_texture == "fine"
        # Identity fields must survive the enrichment round-trip too -- and
        # source_id must come from main_species.id (171170, matching the
        # original search result), not the DETAIL_RESPONSE's distinct
        # top-level data.id (171241). See the DETAIL_RESPONSE comment above.
        assert enriched.common_name == "Carrot"
        assert enriched.scientific_name == "Daucus carota"
        assert enriched.source_id == "171170"

    def test_enrichment_failure_falls_back_to_sparse_result(
        self, dialog: PlantSearchDialog, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A detail-fetch failure after a successful search (offline, rate
        limited, ...) must not block the user from using their selection --
        one of the tradeoffs #297 explicitly flagged for the fix to handle.
        """
        monkeypatch.setattr(
            "requests.Session.get",
            MagicMock(side_effect=requests.exceptions.ConnectionError("offline")),
        )

        with patch(
            "open_garden_planner.ui.dialogs.plant_search_dialog.QMessageBox.warning"
        ) as mock_warn:
            qtbot.mouseClick(dialog.ok_button, Qt.MouseButton.LeftButton)

        assert dialog.result() == dialog.DialogCode.Accepted
        plant = dialog.selected_plant
        assert plant is not None
        assert plant.common_name == "Carrot"
        assert plant.sun_requirement.value == "unknown"
        # A silent fallback would reproduce #297's own symptom -- the user
        # must be told their selection has limited data.
        mock_warn.assert_called_once()

    def test_malformed_detail_response_falls_back_and_warns(
        self, dialog: PlantSearchDialog, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 200 response whose body doesn't match the expected shape must
        not crash the dialog (only `requests.RequestException` was wrapped
        into `PlantAPIError` before this fix -- everything else reached
        `_parse_species()` uncaught).
        """

        def _malformed_get(url, params=None, timeout=None):
            response = MagicMock()
            response.status_code = 200
            response.raise_for_status = MagicMock()
            response.json.return_value = MALFORMED_DETAIL_RESPONSE
            return response

        monkeypatch.setattr("requests.Session.get", MagicMock(side_effect=_malformed_get))

        with patch(
            "open_garden_planner.ui.dialogs.plant_search_dialog.QMessageBox.warning"
        ) as mock_warn:
            qtbot.mouseClick(dialog.ok_button, Qt.MouseButton.LeftButton)

        assert dialog.result() == dialog.DialogCode.Accepted
        plant = dialog.selected_plant
        assert plant is not None
        assert plant.common_name == "Carrot"
        assert plant.sun_requirement.value == "unknown"
        mock_warn.assert_called_once()

    def test_empty_detail_response_falls_back_and_warns(
        self, dialog: PlantSearchDialog, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 200 response that parses cleanly but describes no real plant
        (empty body, deleted record, ...) must not silently overwrite a good
        search result with an 'Unknown' one.
        """

        def _empty_get(url, params=None, timeout=None):
            response = MagicMock()
            response.status_code = 200
            response.raise_for_status = MagicMock()
            response.json.return_value = (
                EMPTY_DETAIL_RESPONSE if url.endswith("/plants/171170") else SEARCH_RESPONSE
            )
            return response

        monkeypatch.setattr("requests.Session.get", MagicMock(side_effect=_empty_get))

        with patch(
            "open_garden_planner.ui.dialogs.plant_search_dialog.QMessageBox.warning"
        ) as mock_warn:
            qtbot.mouseClick(dialog.ok_button, Qt.MouseButton.LeftButton)

        assert dialog.result() == dialog.DialogCode.Accepted
        plant = dialog.selected_plant
        assert plant is not None
        assert plant.common_name == "Carrot"
        mock_warn.assert_called_once()

    def test_confirm_enriches_only_the_selected_row_not_every_browsed_row(
        self, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deliberate rate-limit tradeoff: browsing several results before
        confirming one must cost exactly one detail request, not one per
        visible row.
        """
        multi_search_response = {
            "data": [
                {"id": 171170, "common_name": "Carrot", "scientific_name": "Daucus carota"},
                {"id": 269338, "common_name": "Tomato", "scientific_name": "Solanum lycopersicum"},
                {"id": 265263, "common_name": "Apple", "scientific_name": "Malus domestica"},
            ]
        }

        def _multi_fake_get(url, params=None, timeout=None):
            response = MagicMock()
            response.status_code = 200
            response.raise_for_status = MagicMock()
            response.json.return_value = (
                DETAIL_RESPONSE if url.endswith("/plants/171170") else multi_search_response
            )
            return response

        mock_get = MagicMock(side_effect=_multi_fake_get)
        monkeypatch.setattr("requests.Session.get", mock_get)
        monkeypatch.setattr(
            "open_garden_planner.services.plant_library.get_plant_library",
            lambda: _EmptyLibrary(),
        )
        manager = PlantAPIManager(trefle_api_token="fake-token")
        dlg = PlantSearchDialog(manager)
        qtbot.addWidget(dlg)
        dlg.search_input.setText("veg")
        dlg._perform_search()
        assert dlg.results_list.count() == 3

        # Browse all three rows -- selection-change must not itself enrich.
        for row in range(3):
            dlg.results_list.setCurrentRow(row)
        dlg.results_list.setCurrentRow(0)  # confirm the carrot

        qtbot.mouseClick(dlg.ok_button, Qt.MouseButton.LeftButton)

        # Exactly 2 requests total: 1 search + 1 detail fetch for the single
        # confirmed row -- not 1 (search) + 3 (one per browsed row).
        assert mock_get.call_count == 2
        assert dlg.selected_plant.sun_requirement.value == "full_sun"

    def test_null_common_name_detail_is_accepted_not_rejected(
        self, dialog: PlantSearchDialog, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression pin (senior-review round 2): a first cut of the
        identity-validation guard also rejected `common_name in ("", "Unknown")`,
        reasoning that meant a bad response. Trefle genuinely omits
        common_name for many real, scientific-name-only species -- rejecting
        on that basis discarded a fully-populated, correctly-identified
        detail record for exactly the plants this fix exists to help, while
        telling the user their data was "limited" when it wasn't. The only
        valid identity check is source_id matching the requested id.
        """
        unnamed_species_detail = {
            "data": {
                "main_species": {
                    "id": 171170,
                    "common_name": None,
                    "scientific_name": "Daucus carota",
                    "growth": {"light": 8, "atmospheric_humidity": 5},
                }
            }
        }

        def _unnamed_get(url, params=None, timeout=None):
            response = MagicMock()
            response.status_code = 200
            response.raise_for_status = MagicMock()
            response.json.return_value = (
                unnamed_species_detail if url.endswith("/plants/171170") else SEARCH_RESPONSE
            )
            return response

        monkeypatch.setattr("requests.Session.get", MagicMock(side_effect=_unnamed_get))

        with patch(
            "open_garden_planner.ui.dialogs.plant_search_dialog.QMessageBox.warning"
        ) as mock_warn:
            qtbot.mouseClick(dialog.ok_button, Qt.MouseButton.LeftButton)

        mock_warn.assert_not_called()
        enriched = dialog.selected_plant
        assert enriched is not None
        assert enriched.source_id == "171170"
        assert enriched.sun_requirement.value == "full_sun"

    def test_custom_library_result_is_not_enriched(
        self, dialog: PlantSearchDialog, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Custom plants have no online detail endpoint -- confirming one
        must not attempt (and fail) an online fetch.
        """
        from open_garden_planner.models.plant_data import PlantSpeciesData

        custom_plant = PlantSpeciesData(
            scientific_name="Testus customus",
            common_name="Custom Test Plant",
            data_source="custom",
            source_id="local-1",
        )
        dialog._selected_plant = custom_plant
        mock_get = MagicMock(side_effect=AssertionError("should not fetch for custom plants"))
        monkeypatch.setattr("requests.Session.get", mock_get)

        qtbot.mouseClick(dialog.ok_button, Qt.MouseButton.LeftButton)

        mock_get.assert_not_called()
        assert dialog.selected_plant is custom_plant
