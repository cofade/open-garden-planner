"""Pytest configuration and fixtures."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Force Qt offscreen rendering before any Qt imports so no windows pop up.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(autouse=True, scope="session")
def isolate_qsettings():
    """Redirect QSettings to a test-only registry key for the entire test session.

    This prevents tests from polluting the real user settings (e.g. recent files).
    The test key is cleared at the end of the session.
    """
    from PyQt6.QtCore import QSettings

    def _test_init(self: object) -> None:
        self._settings = QSettings("cofade_test", "Open Garden Planner Test")  # type: ignore[attr-defined]

    import open_garden_planner.app.settings as settings_module

    original_init = settings_module.AppSettings.__init__
    settings_module.AppSettings.__init__ = _test_init  # type: ignore[method-assign]

    # Capture the process-global default QSettings format and restore it at
    # teardown. This is a tripwire for a future setDefaultFormat() leak only
    # (those statics are never auto-reverted by Qt); it does NOT cover a
    # setPath()-only leak. Nothing leaks today — test_ui_state.py now isolates
    # via monkeypatch instead of the global statics — so this is pure insurance.
    original_format = QSettings.defaultFormat()

    # Also reset the module-level singleton so a fresh test instance is created
    settings_module._settings_instance = None  # type: ignore[attr-defined]

    yield

    # Clean up: clear the test registry key and restore original init + format
    QSettings("cofade_test", "Open Garden Planner Test").clear()
    QSettings.setDefaultFormat(original_format)
    settings_module.AppSettings.__init__ = original_init  # type: ignore[method-assign]
    settings_module._settings_instance = None  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _reset_app_settings():
    """Give every test a pristine settings store, independent of run order.

    Clears the isolated test key and resets the lazy singleton both before and
    after each test, so values written by one test cannot leak into the next
    (nor survive from a prior crashed session).
    """
    from PyQt6.QtCore import QSettings

    import open_garden_planner.app.settings as settings_module

    def _reset() -> None:
        QSettings("cofade_test", "Open Garden Planner Test").clear()
        settings_module._settings_instance = None  # type: ignore[attr-defined]

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def _no_weather_network():
    """Stub out the weather fetch thread so tests never make real network requests."""
    with patch("open_garden_planner.ui.widgets.weather_widget._WeatherFetchWorker"):
        yield


@pytest.fixture(autouse=True)
def _disable_agent_api_server():
    """Never auto-start the embedded Agent API server during tests.

    The server defaults to ON in production (US-D1.1) but tests must not bind a
    real loopback port; force it off in the isolated settings store. Runs after
    `_reset_app_settings` (which clears the store) so the value sticks for the
    test. Tests that exercise the server build `AgentApiServer` directly.
    """
    from PyQt6.QtCore import QSettings

    QSettings("cofade_test", "Open Garden Planner Test").setValue(
        "agent_api/enabled", False
    )
    yield
