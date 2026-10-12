"""Pytest configuration and fixtures."""

import atexit
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Force Qt offscreen rendering before any Qt imports so no windows pop up.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ── The user's data directory ────────────────────────────────────────────────
# `services.plant_library.get_app_data_dir()` is where the app keeps what the
# user made: custom plants, plant lists, the seed inventory, companion rules,
# smart symbols, the weather cache. It reads `%APPDATA%` (Windows) or
# `$XDG_DATA_HOME` (Linux) on every call, and nothing here redirected it — so a
# test that reached the plant database panel's save path saved into the
# developer's REAL library: 207 duplicate "Walnut" entries of 209 by the time it
# was noticed (2026-10-11, §11.4), one more with every full run by anyone.
#
# Both variables point into a directory of THIS process from here on. Set at
# conftest IMPORT time for the reason given for the settings below: a store
# built while a module is imported must already land in the test location, and
# a fixture runs after collection. Child processes inherit the environment, so
# a script or the app started by a test lands there too. The environment is the
# whole mechanism on Windows and Linux — production code has no override and
# needs none. macOS reads no variable: `_rebind_get_app_data_dir` below.
#
# `PRODUCTION_DATA_ENV` keeps what the variables said before, so a test can
# prove nothing resolves there any more WITHOUT this file ever touching that
# place (tests/integration/test_app_data_isolation.py).
#
# `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` are redirected with them — on every
# platform, because a LIBRARY reads them on every platform: ezdxf (the DXF
# import and export) loads `$XDG_CONFIG_HOME/ezdxf/ezdxf.ini`, else
# `~/.config/ezdxf/ezdxf.ini`, when it is imported, and keeps its font index in
# `$XDG_CACHE_HOME/ezdxf/font_manager_cache.json`, else under `~/.cache` —
# which it BUILDS AND WRITES there when the file is missing (read in ezdxf
# 1.4.3: `_options.config_files`, `fonts.fonts._load_font_manager`). On Linux
# the two variables also move Qt's settings and cache folders and the AI-client
# paths that follow `XDG_CONFIG_HOME`: all of them into the test root, which is
# where a test's files belong.
PRODUCTION_DATA_ENV: dict[str, str | None] = {
    name: os.environ.get(name)
    for name in ("APPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")
}
TEST_DATA_ROOT = Path(tempfile.mkdtemp(prefix=f"ogp-tests-{os.getpid()}-")).resolve()
os.environ["APPDATA"] = str(TEST_DATA_ROOT / "appdata")
os.environ["XDG_DATA_HOME"] = str(TEST_DATA_ROOT / "xdg-data")
os.environ["XDG_CONFIG_HOME"] = str(TEST_DATA_ROOT / "xdg-config")
os.environ["XDG_CACHE_HOME"] = str(TEST_DATA_ROOT / "xdg-cache")
for _name in ("APPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
    Path(os.environ[_name]).mkdir()
# Removed when the interpreter exits — later than any fixture finaliser, so a
# widget closed during teardown still finds its directory. A killed run leaves
# an orphan in the temp directory, which nothing reads again (`mkdtemp` never
# hands out an existing name).
atexit.register(shutil.rmtree, TEST_DATA_ROOT, ignore_errors=True)

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# The isolated store every test reads and writes. Named here once: production
# code builds every backend from `app.settings.ORGANIZATION_NAME` /
# `APPLICATION_NAME` (ADR-041), and the two lines below rebind those names to
# these, so nothing else in the suite needs to know them.
TEST_ORGANIZATION = "cofade_test"
# Per-PROCESS application name: on the Windows registry backend two pytest
# processes on one machine (a senior-reviewer worktree, a parallel run) would
# otherwise share ONE key, and each process's per-test reset kills the other's
# live stores ("black hole": writes vanish, reads return defaults — §11.4,
# measured 2026-08-17: a Welcome dialog opening despite the flag written False,
# a snap setting reading its default right after the write). The session-end
# `clear()` in `isolate_qsettings` removes this process's key again; a crashed
# run leaves an orphan key, and PID reuse handing a later run that dirty key is
# harmless because `_reset_app_settings` wipes at SETUP, not only at teardown.
TEST_APPLICATION = f"Open Garden Planner Test {os.getpid()}"

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


def _rebind_get_app_data_dir(root: Path) -> None:
    """Point ``get_app_data_dir`` itself at ``root`` — the route for macOS.

    There the function reads no environment variable (it is
    ``~/Library/Application Support/OpenGardenPlanner``, from ``Path.home()``), so
    the redirection above cannot reach it; moving ``HOME`` would move far more
    than this one directory. The function is replaced where it is defined and in
    every already-imported module that bound the name with ``from … import``.
    Modules imported later bind the replacement.

    Not run on Windows or Linux, where the environment does the job. No Mac has
    run this branch (CI has none): the mechanism is exercised by hand in
    ``tests/integration/test_app_data_isolation.py``, the ``darwin`` condition
    below is not.
    """
    import open_garden_planner.services.plant_library as library

    original = library.get_app_data_dir

    def redirected() -> Path:
        path = root / "OpenGardenPlanner"
        path.mkdir(parents=True, exist_ok=True)
        return path

    for module in list(sys.modules.values()):
        if (getattr(module, "__name__", "").startswith("open_garden_planner")
                and getattr(module, "get_app_data_dir", None) is original):
            module.get_app_data_dir = redirected  # type: ignore[attr-defined]


if sys.platform == "darwin":
    _rebind_get_app_data_dir(TEST_DATA_ROOT / "macos")

# ── The locations Qt hands out ───────────────────────────────────────────────
# `QStandardPaths.writableLocation` is how the rest of the app finds a place to
# write: the crash log and `app.log` (AppDataLocation), the companion, climate
# and thumbnail caches (AppLocalDataLocation), and the default project folder
# under Documents — which `app.paths.get_projects_dir()` CREATES. On Windows Qt
# asks the shell for these folders, not the environment, so no variable moves
# them; in a test process they are named after pytest-qt's application
# ("pytest-qt-qapp"), which kept them out of the user's own app folder but not
# out of the user's profile: one test appended a traceback to
# `%APPDATA%/pytest-qt-qapp/crash.log` on every run (331 of them when counted).
#
# So the Python-level call is redirected for the locations the app writes to.
# Every use in `src/` is a Python call of this one function. What Qt does on its
# own in C++ (its shader and QML disk caches) still goes where Qt decides.
# A test that needs another answer monkeypatches the function as before.
from PyQt6.QtCore import QStandardPaths as _QStandardPaths  # noqa: E402

# THE stand-in is `scripts/script_isolation.redirect_qt_locations` — one function for
# the suite and for every script that isolates itself (a script runs outside pytest,
# and on Windows no environment variable moves `AppLocalDataLocation`). Loaded from
# its file and registered under its name, so that a fixture generator a test imports
# (`import script_isolation`) gets this very module and not a second state.
_isolation_spec = importlib.util.spec_from_file_location(
    "script_isolation", Path(__file__).parent.parent / "scripts" / "script_isolation.py")
assert _isolation_spec is not None and _isolation_spec.loader is not None
_script_isolation = importlib.util.module_from_spec(_isolation_spec)
sys.modules["script_isolation"] = _script_isolation
_isolation_spec.loader.exec_module(_script_isolation)
REDIRECTED_QT_LOCATIONS = _script_isolation.redirect_qt_locations(TEST_DATA_ROOT)
assert REDIRECTED_QT_LOCATIONS and _QStandardPaths.writableLocation.__name__ == "writable_location"


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
        # Per-key wipe, NOT `clear()`: on the Windows registry backend a
        # `clear()`ed QSettings deletes the whole key when it is DESTROYED, and
        # every store built between the clear() and that destruction becomes a
        # "black hole" (writes vanish, reads return defaults) — measured
        # 2026-08-17 (§11.4). `remove(key)` acts immediately and leaves the
        # key alive. (The 2026-08-17 incident itself was a SECOND pytest
        # process clear()ing the then-shared key — fixed by the per-pid
        # TEST_APPLICATION above; this is defence in depth against the same
        # mechanism inside one process.)
        store = settings_module.create_qsettings()
        for key in store.allKeys():
            store.remove(key)
        store.sync()
        settings_module._settings_instance = None  # type: ignore[attr-defined]

    def _probe_black_hole() -> str | None:
        """Detect a dead settings singleton (Windows registry backend only —
        on the INI backend a same-instance write→read hits the in-memory cache
        and this can never fire).

        Measured 2026-08-17: once ANOTHER QSettings instance — in this process or
        in another one sharing the key — has `clear()`ed the key, a surviving
        instance's writes vanish and its reads return defaults ("black hole").
        Two intermittent full-run failures had exactly that fingerprint (a
        Welcome dialog opening despite the flag written False; a
        `nearest_snap_enabled` read returning the default right after its
        write) and were caused by a concurrent pytest process (senior-reviewer
        worktree) sharing the then-fixed test key — §11.4. The key is per-pid
        now; if this ever fires again, something else is deleting the key.
        """
        inst = settings_module._settings_instance  # type: ignore[attr-defined]
        if inst is None:
            return None
        store = inst._settings
        store.setValue("_conftest/probe", 1)
        if store.value("_conftest/probe", None, type=int) != 1:
            return (
                "settings singleton is a BLACK HOLE (writes vanish, reads return "
                "defaults) — its registry key was clear()ed by another QSettings "
                "instance (another pytest process?) after it was built; see §11.4 "
                "'silence the startup Welcome dialog' addendum (2026-08-17)"
            )
        store.remove("_conftest/probe")
        return None

    def _names() -> tuple[str, str]:
        return (settings_module.ORGANIZATION_NAME, settings_module.APPLICATION_NAME)

    expected = (TEST_ORGANIZATION, TEST_APPLICATION)
    assert _names() == expected, (
        f"the settings names are {_names()} before this test, not this process's "
        f"test key {expected} — an earlier import or test rebound them"
    )
    _reset()
    yield
    verdict = _probe_black_hole()
    drifted = _names()
    if drifted != expected:
        # Restore first, so the rest of the session stays on this process's own
        # key, then fail the test that moved it: a module-scope rebinding in an
        # imported script once silently took the key over for the whole session.
        settings_module.ORGANIZATION_NAME, settings_module.APPLICATION_NAME = expected
        settings_module._settings_instance = None  # type: ignore[attr-defined]
        verdict = verdict or (
            f"this test left the settings names at {drifted} instead of the "
            f"per-process test key {expected}; restore any rebinding before the "
            "test ends (monkeypatch does)"
        )
    _reset()
    if verdict:
        pytest.fail(verdict)


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


@pytest.fixture(autouse=True, scope="session")
def _silence_welcome_dialog():
    """Never open the modal startup Welcome dialog during tests — session-wide.

    `GardenPlannerApp` arms `QTimer.singleShot(500, self._startup_sequence)`,
    which opens the MODAL `WelcomeDialog` via `dialog.exec()` when
    `show_welcome_on_startup` is on (the production default). Headless, nobody
    closes it, so the first event loop after the timer fires — a `qtbot.wait`
    in the test body, or pytest-qt's teardown `processEvents()` — parks the
    whole session inside the modal loop forever, with an EMPTY log (§11.4
    "silence the startup Welcome dialog"; re-hit 2026-08-17 in
    `test_trellis.py` and `test_idle_scene_quiescence.py`, Package 3a).

    This is the class-level no-op that `test_icon_system` and
    `test_theme_switch_chrome` applied per file (and `test_dynamic_input_overlay`
    stubs the whole `_startup_sequence`); six more files wrote the settings key
    instead; 34 files construct `GardenPlannerApp` in total. It is deliberately NOT settings-based: a per-test
    `KEY_SHOW_WELCOME=False` write was observed to lose a race with the 500 ms
    timer once in a full run (the read returned the default inside a
    `qtbot.wait` even though both a conftest and a module fixture had written
    False beforehand); patching the method is airtight regardless of what the
    store says. `_disable_welcome_dialog` below still keeps the store honest.
    """
    from open_garden_planner.app.application import GardenPlannerApp

    original = GardenPlannerApp._show_welcome_dialog
    GardenPlannerApp._show_welcome_dialog = lambda _self: None  # type: ignore[method-assign]
    yield
    GardenPlannerApp._show_welcome_dialog = original  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _disable_welcome_dialog(_reset_app_settings):
    """Belt to `_silence_welcome_dialog`'s braces: the store says "no Welcome
    dialog" too, so anything that consults `show_welcome_on_startup` (not just
    the startup path) sees the test-appropriate value. Same ordering contract
    as `_disable_agent_api_server`.
    """
    from open_garden_planner.app.settings import AppSettings, create_qsettings

    create_qsettings().setValue(AppSettings.KEY_SHOW_WELCOME, False)
    yield
