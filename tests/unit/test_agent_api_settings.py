"""Lock the Agent API settings defaults (US-D1.1 product decision).

Asserts the class constants directly — the autouse `_disable_agent_api_server`
fixture overrides the runtime *value* in tests, but not the declared default.
"""

from __future__ import annotations

from open_garden_planner.app.settings import AppSettings


def test_agent_api_enabled_defaults_on() -> None:
    # Default ON (read-only, loopback) so AI assistants connect without users
    # having to discover a Preferences toggle.
    assert AppSettings.DEFAULT_AGENT_API_ENABLED is True


def test_agent_api_port_default() -> None:
    assert AppSettings.DEFAULT_AGENT_API_PORT == 8765
    assert AppSettings.MIN_AGENT_API_PORT == 1024
    assert AppSettings.MAX_AGENT_API_PORT == 65535


def test_agent_api_writes_default_off() -> None:
    # Writes are OFF by default: agent editing is an explicit opt-in on top of
    # the bearer token, over the loopback-trust model (US-D2.0).
    assert AppSettings.DEFAULT_AGENT_API_WRITES_ENABLED is False
    assert AppSettings().agent_api_writes_enabled is False


def test_agent_api_writes_round_trip() -> None:
    settings = AppSettings()
    settings.agent_api_writes_enabled = True
    assert AppSettings().agent_api_writes_enabled is True


def test_agent_api_token_autogenerates_and_persists() -> None:
    settings = AppSettings()
    token = settings.agent_api_token
    assert isinstance(token, str)
    assert len(token) >= 32
    # Stable across reads and across fresh instances (persisted, not re-rolled).
    assert settings.agent_api_token == token
    assert AppSettings().agent_api_token == token


def test_regenerate_agent_api_token_changes_it() -> None:
    settings = AppSettings()
    first = settings.agent_api_token
    second = settings.regenerate_agent_api_token()
    assert second != first
    assert AppSettings().agent_api_token == second
