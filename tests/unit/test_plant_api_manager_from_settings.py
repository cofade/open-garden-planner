"""``PlantAPIManager.from_settings`` is the one credential path (PR #1000 review)."""

from types import SimpleNamespace

import pytest

from open_garden_planner.services import PlantAPIManager

_ENV = ("TREFLE_API_TOKEN", "PERENUAL_API_KEY", "PERMAPEOPLE_KEY_ID", "PERMAPEOPLE_KEY_SECRET")


def _preferences(**values):
    base = {"trefle_api_token": "", "perenual_api_key": "", "permapeople_key_id": "", "permapeople_key_secret": ""}
    base.update(values)
    return SimpleNamespace(**base)


@pytest.fixture
def clean_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_no_credentials_configure_no_source(clean_env):
    assert PlantAPIManager.from_settings(_preferences()).configured_source_count == 0


def test_preferences_keys_configure_their_sources(clean_env):
    manager = PlantAPIManager.from_settings(
        _preferences(trefle_api_token="t", perenual_api_key="p"),
    )
    assert manager.configured_source_count == 2


def test_environment_fills_an_unset_preference(clean_env):
    clean_env.setenv("PERENUAL_API_KEY", "from-env")
    assert PlantAPIManager.from_settings(_preferences()).configured_source_count == 1
