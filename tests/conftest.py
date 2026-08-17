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
# code builds every backend from `app.settings.ORGANIZATION_NAME` /
# `APPLICATION_NAME` (ADR-041), and the two lines below rebind those names to
# these, so nothing else in the suite needs to know them.
TEST_ORGANIZATION = "cofade_test"
TEST_APPLICATION = "Open Garden Planner Test"

# Redirect at conftest IMPORT time, not inside a fixture. pytest imports this
# file before it collects any test module in this tree, hence before any
# `open_garden_planner` module a test imports — so every store the app builds is
# constructed *after* the redirection and lands in the test key, even one built
# while a module is being imported. A fixture, however early-scoped, runs after
# collection and could never cover that: a QSettings binds its organization and
# application at construction and cannot be retargeted afterwards.
#
# This is what makes the isolation hold by construction rather than by everyone
# remembering not to cache a store at import time (which the gate in
# tests/unit/test_settings_chokepoint.py additionally discourages, as
# belt-and-braces). Deliberately below the sys.path setup above, hence E402.
import open_garden_planner.app.settings as _app_settings  # noqa: E402

PRODUCTION_STORE = (
    _app_settings.ORGANIZATION_NAME,
    _app_settings.APPLICATION_NAME,
)
_app_settings.ORGANIZATION_NAME = TEST_ORGANIZATION
_app_settings.APPLICATION_NAME = TEST_APPLICATION


@pytest.fixture(autouse=True, scope="session")
def isolate_qsettings():
    """Session bookkeeping for the import-time redirection above.

    The redirection itself is not here — see the module-scope comment: it has to
    happen at conftest import time to cover a store built while a module is
    imported. This fixture owns what only a fixture can do: resetting the lazy
    `AppSettings` singleton, clearing the test key at the end of the session, and
    tripping on a leaked process-global QSettings format.

    Yields the *production* ``(organization, application)`` pair the redirection
    displaced, so a test can assert that pair is never touched without
    hardcoding it (see ``tests/integration/test_settings_isolation.py``).

    Before #285 this fixture *was* the isolation, by replacing
    `AppSettings.__init__` — which `UiStateStore` bypassed entirely, so full-app
    tests read *and overwrote* the developer's real window state (§11.4, #283).
    """
    from PyQt6.QtCore import QSettings

    import open_garden_planner.app.settings as settings_module

    # Narrow but real: catches a test that rebound the names and failed to undo
    # it, and a future edit that moves the module-scope lines into a conditional.
    # (It cannot detect their outright removal — this fixture would be gone too;
    # `test_settings_chokepoint.py::TestTheRedirectionMechanismItself` parses the
    # conftest AST for that.)
    assert settings_module.ORGANIZATION_NAME == TEST_ORGANIZATION, (
        "the import-time redirection at the top of conftest.py is not in effect — "
        "the suite would be reading and writing the real user store (#285)"
    )

    # Capture the process-global default QSettings format so teardown can both
    # repair it and *report* a leak (those statics are never auto-reverted by
    # Qt). This is the suite's only sanctioned call to one of them, and it does
    # NOT cover a setPath()-only leak. Nothing leaks today — both trees are gated
    # (tests/unit/test_settings_chokepoint.py) and test_ui_state.py isolates by
    # redirecting the factory — so this is insurance that now speaks up.
    original_format = QSettings.defaultFormat()

    # Also reset the module-level singleton so a fresh test instance is created
    settings_module._settings_instance = None  # type: ignore[attr-defined]

    yield PRODUCTION_STORE

    # Repair the format static FIRST: if something leaked `IniFormat`, the clear
    # below would otherwise target an INI store and leave the registry test key
    # behind — precisely in the scenario the tripwire exists for.
    leaked_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(original_format)

    settings_module.create_qsettings().clear()
    settings_module._settings_instance = None  # type: ignore[attr-defined]
    # The names are deliberately NOT restored: the redirection is process-wide by
    # design and the process ends here, so restoring would only create a window
    # in which late teardown code could reach the real store.

    # Now fail loudly. A tripwire that silently fixes the damage reports nothing
    # and lets the §11.4 "every getter returns its coded default" mode come back
    # unnoticed. pytest attributes a session-finalizer error to the last test it
    # ran, so the message has to name the real cause itself.
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
def _isolate_plant_api_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent a developer's real plant-API .env credentials from leaking
    into tests.

    open_garden_planner.main calls load_dotenv() at import time, so any test
    that imports it (directly or transitively) sets these vars in the shared
    pytest process's os.environ for the rest of the session -- masking a
    plant-API client's "credentials missing" path with a real key (issue
    #294 investigation). Sourced from each client's own *_ENV_VAR constant so
    a rename can't silently stop being covered here. (OGP_GOOGLE_MAPS_KEY has
    the same leak risk but is covered locally where it's used --
    tests/integration/test_map_picker_dialog.py's with_api_key fixture.)

    Imports are local, not module-scope: the ADR-041 rebinding above must run
    before any open_garden_planner module is imported (ADR-041's own
    comment), and services.plant_api.* transitively pulls in a long import
    chain via services/__init__.py -- module-scope imports here would sit
    above that rebinding and quietly reopen the #283/#285 hazard.
    """
    from open_garden_planner.services.plant_api.perenual_client import PerenualClient
    from open_garden_planner.services.plant_api.permapeople_client import (
        PermapeopleClient,
    )
    from open_garden_planner.services.plant_api.trefle_client import TrefleClient

    for var in (
        PermapeopleClient.KEY_ID_ENV_VAR,
        PermapeopleClient.KEY_SECRET_ENV_VAR,
        PerenualClient.API_KEY_ENV_VAR,
        TrefleClient.API_TOKEN_ENV_VAR,
    ):
        monkeypatch.delenv(var, raising=False)


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


@pytest.fixture(autouse=True)
def _disable_welcome_dialog(_reset_app_settings):
    """Never open the modal startup Welcome dialog during tests.

    `GardenPlannerApp` arms `QTimer.singleShot(500, self._startup_sequence)`,
    which opens the MODAL `WelcomeDialog` via `dialog.exec()` when
    `show_welcome_on_startup` is on (the production default). Headless, nobody
    closes it, so the first event processing after the timer fires — typically
    pytest-qt's teardown `processEvents()` of a full-app test that outlived
    500 ms — parks the whole session inside the modal loop forever, with an
    EMPTY log (§11.4 "silence the startup Welcome dialog"; re-hit 2026-08-17 in
    `test_trellis.py`, Package 3a). Per-file monkeypatches
    (`test_icon_system._make_app`) guarded ~1 of ~32 app-building files; this
    guards all of them. Same ordering contract as `_disable_agent_api_server`.
    """
    from open_garden_planner.app.settings import AppSettings, create_qsettings

    create_qsettings().setValue(AppSettings.KEY_SHOW_WELCOME, False)
    yield
