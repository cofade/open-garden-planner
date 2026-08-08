"""Unit tests for PermapeopleClient.is_available() (issue #294).

The connectivity probe must request a bounded page, not the full unfiltered
plant list -- the root cause of "Could not connect to Permapeople. Please
check your credentials." being shown for perfectly valid credentials.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

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
