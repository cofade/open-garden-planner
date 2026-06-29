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
