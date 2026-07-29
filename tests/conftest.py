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

# The isolated store every test reads and writes. Named here once: production
# code builds its backend from `app.settings.ORGANIZATION_NAME` /
# `APPLICATION_NAME`, and `isolate_qsettings` below rebinds those two names to
# these for the session, so nothing else in the suite needs to know them.
TEST_ORGANIZATION = "cofade_test"
TEST_APPLICATION = "Open Garden Planner Test"


@pytest.fixture(autouse=True, scope="session")
def isolate_qsettings():
    """Redirect EVERY app settings store to a test-only key for the whole session.

    This prevents tests from polluting the real user settings (recent files,
    window geometry, toolbar layout). The test key is cleared at teardown.

    How it covers everything (issue #285, ADR-041): `app/settings.py` owns the
    single construction site `create_qsettings()`, which reads the org/app names
    from its module globals on *every* call. Rebinding those two names therefore
    redirects every store built afterwards — `AppSettings` and `UiStateStore`
    alike — and no import style in a future consumer can escape it. It does NOT
    retarget a store that already exists (a `QSettings` binds its org/app at
    construction), which is why the `_settings_instance` singleton is nulled
    below and why `test_settings_chokepoint.py` forbids building a store at
    import time. Before #285 this fixture replaced `AppSettings.__init__`, which
    `UiStateStore` bypassed entirely; full-app tests then read *and overwrote*
    the developer's real window state (docs §11.4, measured in #283).

    Yields the *production* ``(organization, application)`` pair it displaced, so
    a test can assert that pair is never touched without hardcoding it (see
    ``tests/integration/test_settings_isolation.py``).
    """
    from PyQt6.QtCore import QSettings

    import open_garden_planner.app.settings as settings_module

    original_names = (
        settings_module.ORGANIZATION_NAME,
        settings_module.APPLICATION_NAME,
    )
    settings_module.ORGANIZATION_NAME = TEST_ORGANIZATION
    settings_module.APPLICATION_NAME = TEST_APPLICATION

    # Capture the process-global default QSettings format so teardown can both
    # repair it and *report* a leak (those statics are never auto-reverted by
    # Qt). This is the suite's only sanctioned call to one of them, and it does
    # NOT cover a setPath()-only leak. Nothing leaks today — `src/` is gated
    # (tests/unit/test_settings_chokepoint.py) and test_ui_state.py isolates by
    # redirecting the factory — so this is insurance that now speaks up.
    original_format = QSettings.defaultFormat()

    # Also reset the module-level singleton so a fresh test instance is created
    settings_module._settings_instance = None  # type: ignore[attr-defined]

    yield original_names

    # Clean up while the redirection is still in place, then restore it.
    settings_module.create_qsettings().clear()
    leaked_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(original_format)
    (
        settings_module.ORGANIZATION_NAME,
        settings_module.APPLICATION_NAME,
    ) = original_names
    settings_module._settings_instance = None  # type: ignore[attr-defined]

    # Repair first (so the process is left clean either way), then fail loudly.
    # A tripwire that silently fixes the damage reports nothing and lets the
    # §11.4 "every getter returns its coded default" mode come back unnoticed.
    assert leaked_format == original_format, (
        "a test called QSettings.setDefaultFormat() and left it set — that static "
        "is process-global and poisons every store built later in the session "
        "(docs §11.4). Redirect app/settings.create_qsettings() instead."
    )


@pytest.fixture(autouse=True)
def _reset_app_settings():
    """Give every test a pristine settings store, independent of run order.

    Clears the isolated test key and resets the lazy singleton both before and
    after each test, so values written by one test cannot leak into the next
    (nor survive from a prior crashed session). Because the whole app shares one
    backend, this also clears the `UiState/` geometry keys.
    """
    import open_garden_planner.app.settings as settings_module

    def _reset() -> None:
        settings_module.create_qsettings().clear()
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
def _disable_agent_api_server(_reset_app_settings):
    """Never auto-start the embedded Agent API server during tests.

    The server defaults to ON in production (US-D1.1) but tests must not bind a
    real loopback port. Depends on `_reset_app_settings` so this runs strictly
    AFTER its store-clearing setup (autouse same-scope order is not otherwise
    guaranteed — an earlier version ran first and had its write wiped by the
    clear). Tests that exercise the server build `AgentApiServer` directly.
    """
    from open_garden_planner.app.settings import AppSettings, create_qsettings

    create_qsettings().setValue(AppSettings.KEY_AGENT_API_ENABLED, False)
    yield
