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

from unittest.mock import MagicMock

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

DETAIL_RESPONSE = {
    "data": {
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
        }
    }
}


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
        # Identity fields must survive the enrichment round-trip too.
        assert enriched.common_name == "Carrot"
        assert enriched.scientific_name == "Daucus carota"

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

        qtbot.mouseClick(dialog.ok_button, Qt.MouseButton.LeftButton)

        assert dialog.result() == dialog.DialogCode.Accepted
        plant = dialog.selected_plant
        assert plant is not None
        assert plant.common_name == "Carrot"
        assert plant.sun_requirement.value == "unknown"

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
