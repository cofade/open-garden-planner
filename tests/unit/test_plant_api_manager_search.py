"""Unit tests for PlantAPIManager.search() zero-result vs. failure semantics
(issue #302).

A search for a real but unlisted variety (e.g. "mahachanok", a mango variety
no configured database lists) was misreported as "All plant APIs failed"
even though every configured client answered cleanly with an empty list.
The manager must distinguish:

- Every *configured* client answered (even with []) -> honest "no match",
  return [].
- No configured client answered and at least one raised -> genuine failure,
  raise.
- No configured clients at all -> nothing was attempted, return [].

Follow-up (#302 round 2): `configured_source_count` originally counted
`len(self._clients)`, which is always >= 1 in real use because
`PlantAPIManager`'s constructor appends a Trefle/Perenual/Permapeople client
even without real credentials (their `__init__` never raises on a missing
token/key) -- making "no plant databases are configured" unreachable
outside tests. It is now based on each client's `is_configured()`, and
`search()` skips (never attempts, never counts as failed) any client that
isn't.

These are pure-manager tests: most use a bare `_FakeClient` stand-in with
just the ``name``/``search``/``is_available``/``is_configured`` surface
`PlantAPIManager` touches, injected directly via ``manager._clients`` after
constructing ``PlantAPIManager()`` with no credentials. One test
(``TestRealClientsUnconfigured``) instead builds a manager the real way --
via the real Trefle/Perenual/Permapeople clients, with both the constructor
args AND the credential environment variables cleared -- to prove the
"nothing configured" state is reachable through the actual construction
path, not just by hand-assigning ``_clients``. The custom plant library is
stubbed to always report no matches so these tests only exercise the API
fallback chain, following the ``_StubLibrary`` pattern in
``tests/integration/test_plant_search_enrichment.py``.
"""

from __future__ import annotations

import pytest

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services.plant_api.base import PlantAPIError
from open_garden_planner.services.plant_api.manager import PlantAPIManager
from open_garden_planner.services.plant_api.perenual_client import PerenualClient
from open_garden_planner.services.plant_api.permapeople_client import PermapeopleClient
from open_garden_planner.services.plant_api.trefle_client import TrefleClient


class _StubLibrary:
    """Stand-in for the custom plant library -- always reports no matches."""

    def search_plants(self, query: str) -> list:  # noqa: ARG002
        return []


class _FakeClient:
    """Minimal stand-in for a `PlantAPIClient` -- only the surface
    `PlantAPIManager.search()` actually touches (`name`, `search`,
    `is_configured`).
    """

    def __init__(
        self,
        name: str,
        *,
        results: list | None = None,
        error: Exception | None = None,
        configured: bool = True,
    ) -> None:
        self._name = name
        self._results = results if results is not None else []
        self._error = error
        self._configured = configured

    @property
    def name(self) -> str:
        return self._name

    def search(self, query: str, limit: int) -> list:  # noqa: ARG002
        if self._error is not None:
            raise self._error
        return self._results

    def get_by_id(self, plant_id: str) -> PlantSpeciesData:  # pragma: no cover - unused here
        raise NotImplementedError

    def is_available(self) -> bool:  # pragma: no cover - unused here
        return True

    def is_configured(self) -> bool:
        return self._configured


@pytest.fixture(autouse=True)
def _stub_custom_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every manager under test must not hit the real on-disk plant library."""
    monkeypatch.setattr(
        "open_garden_planner.services.plant_library.get_plant_library",
        lambda: _StubLibrary(),
    )


def _manager_with(clients: list) -> PlantAPIManager:
    """Build a manager with no real credentials, then swap in test clients."""
    manager = PlantAPIManager()
    manager._clients = clients
    return manager


class TestZeroResultsIsNotFailure:
    def test_all_clients_return_empty_list_returns_empty_no_raise(self) -> None:
        manager = _manager_with(
            [
                _FakeClient("Trefle", results=[]),
                _FakeClient("Perenual", results=[]),
                _FakeClient("Permapeople", results=[]),
            ]
        )

        results = manager.search("mahachanok")

        assert results == []

    def test_one_client_raises_other_returns_empty_returns_empty_no_raise(self) -> None:
        manager = _manager_with(
            [
                _FakeClient("Trefle", error=PlantAPIError("connection reset")),
                _FakeClient("Perenual", results=[]),
            ]
        )

        results = manager.search("mahachanok")

        assert results == []


class TestGenuineFailureStillRaises:
    def test_every_client_raises_raises_plant_api_error_with_prefix(self) -> None:
        manager = _manager_with(
            [
                _FakeClient("Trefle", error=PlantAPIError("timeout")),
                _FakeClient("Perenual", error=PlantAPIError("401 Unauthorized")),
            ]
        )

        with pytest.raises(PlantAPIError) as excinfo:
            manager.search("tomato")

        assert str(excinfo.value).startswith("All plant APIs failed")


class TestUnconfiguredClientsAreSkipped:
    """A client with no credentials must never be attempted and must never
    count toward a failure or toward `configured_source_count`.
    """

    def test_unconfigured_client_is_skipped_not_attempted(self) -> None:
        def _boom(*_args, **_kwargs):
            raise AssertionError("search() must not be called on an unconfigured client")

        unconfigured = _FakeClient("Trefle", configured=False)
        unconfigured.search = _boom  # type: ignore[method-assign]
        manager = _manager_with([unconfigured, _FakeClient("Perenual", results=[])])

        results = manager.search("mahachanok")

        assert results == []

    def test_unconfigured_client_does_not_count_as_raised(self) -> None:
        """The only client in the chain is unconfigured (never attempted) --
        must still return [] rather than raise. Not being configured is not
        a failure, just nothing to try.
        """
        manager = _manager_with([_FakeClient("Trefle", configured=False)])

        results = manager.search("mahachanok")

        assert results == []

    def test_configured_source_count_excludes_unconfigured_clients(self) -> None:
        manager = _manager_with(
            [
                _FakeClient("Trefle", configured=True),
                _FakeClient("Perenual", configured=False),
                _FakeClient("Permapeople", configured=True),
            ]
        )

        assert manager.configured_source_count == 2


class TestNoConfiguredClients:
    def test_no_clients_and_no_custom_results_returns_empty(self) -> None:
        manager = _manager_with([])

        results = manager.search("tomato")

        assert results == []

    def test_configured_source_count_reflects_configured_client_count(self) -> None:
        manager = _manager_with([])
        assert manager.configured_source_count == 0

        manager = _manager_with([_FakeClient("Trefle"), _FakeClient("Perenual")])
        assert manager.configured_source_count == 2


class TestRealClientsUnconfigured:
    """Proves the "nothing configured" state is reachable through the real
    construction path (#302 round 2 follow-up), not just by hand-assigning
    ``_clients`` -- ``PlantAPIManager()``'s real Trefle/Perenual/Permapeople
    clients always construct successfully even without credentials, so this
    also clears the environment-variable fallback each one reads when no
    constructor arg is given.
    """

    def test_no_tokens_and_no_env_vars_yields_zero_configured_sources(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(TrefleClient.API_TOKEN_ENV_VAR, "")
        monkeypatch.setenv(PerenualClient.API_KEY_ENV_VAR, "")
        monkeypatch.setenv(PermapeopleClient.KEY_ID_ENV_VAR, "")
        monkeypatch.setenv(PermapeopleClient.KEY_SECRET_ENV_VAR, "")

        manager = PlantAPIManager()

        assert manager.configured_source_count == 0

    def test_no_tokens_and_no_env_vars_search_returns_empty_no_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(TrefleClient.API_TOKEN_ENV_VAR, "")
        monkeypatch.setenv(PerenualClient.API_KEY_ENV_VAR, "")
        monkeypatch.setenv(PermapeopleClient.KEY_ID_ENV_VAR, "")
        monkeypatch.setenv(PermapeopleClient.KEY_SECRET_ENV_VAR, "")

        manager = PlantAPIManager()

        results = manager.search("mahachanok")

        assert results == []
