"""Integration test: PlantSearchDialog distinguishes a zero-result search
from a genuine API failure (issue #302).

Before this fix, `PlantAPIManager.search()` raised `PlantAPIError("All plant
APIs failed")` whenever the final result list was empty -- even when every
configured client answered cleanly with zero matches (e.g. searching for
"mahachanok", a real mango variety no configured database lists). The
dialog then showed a scary "Search failed" label plus a QMessageBox
suggesting the user check their internet connection and API credentials,
even though connectivity and credentials were both fine.

Only the HTTP layer (``requests.Session.get``) is mocked, exercising the
real dialog + manager wiring end to end, following the same pattern as
``tests/integration/test_plant_search_enrichment.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from open_garden_planner.services.plant_api import PlantAPIManager
from open_garden_planner.services.plant_api.perenual_client import PerenualClient
from open_garden_planner.services.plant_api.permapeople_client import PermapeopleClient
from open_garden_planner.services.plant_api.trefle_client import TrefleClient
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog

EMPTY_SEARCH_RESPONSE = {"data": []}


class _StubLibrary:
    """Stand-in for the real custom-plant library -- see
    ``tests/integration/test_plant_search_enrichment.py`` for the rationale
    (the real library reads/writes OS app-data and isn't test-isolated).
    """

    def search_plants(self, query: str) -> list:  # noqa: ARG002
        return []


@pytest.fixture(autouse=True)
def _stub_custom_library(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "open_garden_planner.services.plant_library.get_plant_library",
        lambda: _StubLibrary(),
    )


class TestZeroResultsIsNotReportedAsFailure:
    def test_zero_results_shows_no_match_status_and_no_message_box(
        self, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every configured client answers cleanly with zero matches -- this
        is an honest "no match", not a failure. No QMessageBox, no
        credentials-hint text.
        """

        def _empty_get(url, params=None, timeout=None):  # noqa: ARG001
            response = MagicMock()
            response.status_code = 200
            response.raise_for_status = MagicMock()
            response.json.return_value = EMPTY_SEARCH_RESPONSE
            return response

        monkeypatch.setattr("requests.Session.get", MagicMock(side_effect=_empty_get))

        manager = PlantAPIManager(trefle_api_token="fake-token")
        dlg = PlantSearchDialog(manager)
        qtbot.addWidget(dlg)

        with patch(
            "open_garden_planner.ui.dialogs.plant_search_dialog.QMessageBox.warning"
        ) as mock_warn:
            dlg.search_input.setText("mahachanok")
            dlg._perform_search()

        assert "No plants matched" in dlg.status_label.text()
        mock_warn.assert_not_called()
        assert dlg.results_list.count() == 0

    def test_genuine_api_failure_still_shows_search_failed_and_warns(
        self, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real technical failure (every client errors out, e.g. an HTTP
        500) must still be reported as a failure with the credentials-hint
        QMessageBox -- this path must remain intact after the #302 fix.
        """

        def _failing_get(url, params=None, timeout=None):  # noqa: ARG001
            response = MagicMock()
            response.status_code = 500
            response.raise_for_status = MagicMock(
                side_effect=requests.HTTPError("500 Server Error")
            )
            return response

        monkeypatch.setattr("requests.Session.get", MagicMock(side_effect=_failing_get))

        manager = PlantAPIManager(trefle_api_token="fake-token")
        dlg = PlantSearchDialog(manager)
        qtbot.addWidget(dlg)

        with patch(
            "open_garden_planner.ui.dialogs.plant_search_dialog.QMessageBox.warning"
        ) as mock_warn:
            dlg.search_input.setText("mahachanok")
            dlg._perform_search()

        assert dlg.status_label.text().startswith("Search failed")
        mock_warn.assert_called_once()

    def test_no_configured_sources_mentions_preferences_not_a_match_miss(
        self, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No API client is configured at all -- distinct from "searched and
        found nothing": tell the user where to fix it (Preferences) rather
        than implying their query was just unmatched.

        Built the real way (#302 round 2): `PlantAPIManager`'s client
        constructors never raise on a missing token/key (each falls back to
        an empty string), so all three of Trefle/Perenual/Permapeople still
        get constructed and appended to `_clients` here -- `_clients` is
        deliberately left alone. What makes this "nothing configured" is
        each client's `is_configured()` being False, which requires clearing
        both the constructor args (all None/default) AND the environment
        variables each client falls back to when no arg is given.
        """
        monkeypatch.setenv(TrefleClient.API_TOKEN_ENV_VAR, "")
        monkeypatch.setenv(PerenualClient.API_KEY_ENV_VAR, "")
        monkeypatch.setenv(PermapeopleClient.KEY_ID_ENV_VAR, "")
        monkeypatch.setenv(PermapeopleClient.KEY_SECRET_ENV_VAR, "")

        manager = PlantAPIManager()
        assert manager.configured_source_count == 0

        dlg = PlantSearchDialog(manager)
        qtbot.addWidget(dlg)

        with patch(
            "open_garden_planner.ui.dialogs.plant_search_dialog.QMessageBox.warning"
        ) as mock_warn:
            dlg.search_input.setText("mahachanok")
            dlg._perform_search()

        assert "No plant databases are configured" in dlg.status_label.text()
        mock_warn.assert_not_called()
