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


# ── One real font engine for the whole suite (PF-TST-26, #562/#573) ──────────
# Windows' `offscreen` platform has no font database: every family resolves to a
# box engine whose glyphs are all one em wide (Verdana 9 pt "Today" measures
# 60 px, really 34–37 px). A row count or a rounding claim measured there says
# nothing about a real font, which is why the Plan & Sun strip's layout tests
# failed locally and passed on CI's Linux (which has fontconfig). Register a
# real Windows face once, and make it the application font, so every test in the
# session measures the same real engine. `test_plan_timeline.py` used to
# register `arial.ttf` inside one test and never remove it; that leak is gone.
_WINDOWS_TEST_FONTS = ("verdana.ttf", "arial.ttf", "segoeui.ttf")
_REAL_FONT_CANDIDATES = (
    "Verdana", "DejaVu Sans", "Noto Sans", "Liberation Sans", "Arial", "Segoe UI",
)


def _register_windows_offscreen_fonts() -> str | None:
    """Register real Windows faces when the platform has none; the chosen family.

    Returns ``None`` when the process already has a real font database (native
    Windows, or ``minimal:enable_fonts``) or when no Windows face can be found.
    """
    from PyQt6.QtGui import QFont, QFontDatabase, QFontMetrics

    if sys.platform != "win32":
        return None
    probe = QFontMetrics(QFont())
    if QFontDatabase.families() and probe.horizontalAdvance("i") != probe.horizontalAdvance("W"):
        return None  # a real database already
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    families: list[str] = []
    for filename in _WINDOWS_TEST_FONTS:
        path = fonts / filename
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    if not families:
        return None
    return next((family for family in _REAL_FONT_CANDIDATES if family in families), families[0])


@pytest.fixture(scope="session")
def ui_font_family(qapp) -> str:
    """The real family the suite's text metrics are measured with (PF-TST-26).

    On Windows' offscreen platform this registers the real Windows faces and
    sets the application font to one of them; on Linux/macOS fontconfig already
    provides real metrics, so the first available family is reported and the
    application font is left alone. The Plan & Sun layout tests set this family
    explicitly rather than naming one that exists only on Windows.
    """
    from PyQt6.QtGui import QFont, QFontDatabase

    registered = _register_windows_offscreen_fonts()
    if registered is not None:
        qapp.setFont(QFont(registered, 10))
        return registered
    families = set(QFontDatabase.families())
    for family in _REAL_FONT_CANDIDATES:
        if family in families:
            return family
    return qapp.font().family()


@pytest.fixture(autouse=True, scope="session")
def deterministic_ui_font(ui_font_family):
    """Session-wide: every test measures the same real font engine (PF-TST-26)."""
    yield


@pytest.fixture(autouse=True)
def _restore_settings_guard_environment():
    """Put the settings-guard markers back around every test.

    ``main()`` sets ``OGP_PRODUCT_PROCESS`` and never clears it. ``monkeypatch``
    cannot undo a direct ``os.environ`` write, so a test that calls ``main()``
    would otherwise grant every later test in that xdist worker the product's
    permission — and a future guard test that forgot to delete it would pass
    vacuously.
    """
    names = ("OGP_PRODUCT_PROCESS", "OGP_ALLOW_PRODUCTION_SETTINGS")
    before = {name: os.environ.get(name) for name in names}
    yield
    for name, value in before.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture(autouse=True)
def _reset_app_settings():
    """Give every test a pristine settings store, independent of run order.

    Clears the isolated test key and resets the lazy singleton both before and
    after each test, so values written by one test cannot leak into the next
    (nor survive from a prior crashed session). Because the whole app shares one
    backend, this also clears the `UiState/` geometry keys.
    """
    import open_garden_planner.app.settings as settings_module
    from open_garden_planner.app.settings import AppSettings

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
        # Re-assert the Agent API guard INSIDE the wipe, atomically with it.
        #
        # It used to be written by a separate autouse fixture that merely
        # *depended* on this one, which left a real gap: between this wipe and
        # that write the key did not exist, so `agent_api_enabled` read
        # `DEFAULT_AGENT_API_ENABLED` (True) and `agent_api_port` read its
        # default (8765). A GardenPlannerApp built by an earlier test arms
        # `QTimer.singleShot(1500, self._maybe_start_agent_api)`. That is a BOUND
        # METHOD, not a lambda, and PyQt auto-disconnects a bound-method slot when its
        # receiver is destroyed - so what keeps the window alive is the leak itself, not
        # the slot: nothing ever destroyed the window, so the timer stayed connected and
        # fired. The account is in `tests/integration/conftest.py`'s
        # `_no_leaked_agent_api_thread` docstring, and the fixture it describes is
        # `_reclaim_widgets` in THIS file. A timer landing in the gap started a REAL
        # AgentApiServer on 8765, and two workers doing that collided with
        # `OSError: [Errno 10048]` (measured #509 under `pytest -n 8`). The gap
        # was always there — serial runs simply made it microseconds wide against
        # a 1500 ms timer. See `_disable_agent_api_server`, which now asserts
        # this instead of writing it.
        store.setValue(AppSettings.KEY_AGENT_API_ENABLED, False)
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
def _no_weather_network(request):
    """Stub out the weather fetch thread so tests never make real network requests."""
    if "real_weather_worker" in request.keywords:
        yield
        return
    with patch("open_garden_planner.ui.widgets.weather_widget._WeatherFetchWorker"):
        yield


@pytest.fixture(autouse=True)
def _disable_agent_api_server(_reset_app_settings):
    """Never auto-start the embedded Agent API server during tests.

    The server defaults to ON in production (US-D1.1) but tests must not bind a
    real loopback port. Tests that exercise the server build `AgentApiServer`
    directly, on an OS-assigned port.

    The False is written inside `_reset_app_settings._reset()`, atomically with the
    key wipe, and this fixture ASSERTS it rather than writing it. That is the whole
    point of the split: when the write lived here instead, the instant between the
    wipe and this write had no `agent_api/enabled` key at all, so a read returned
    the production default (True) and a read of the port returned 8765 — and an
    earlier test's deferred `_maybe_start_agent_api` timer landing in that window
    started a real server. See the note in `_reset()`. Asserting rather than
    writing also means a regression here is loud instead of silent.

    **The read must ask for a bool.** `QSettings.value(key, default)` returns the raw
    QVariant, so `setValue(key, False)` reads back as the STRING `'false'` — and
    `assert value is not True` then passes for `'false'` *and* for the `None` that
    means "key absent", which is precisely the dangerous state this fixture exists to
    name. `type=bool` is how the product itself reads it (`app/settings.py:677-683`),
    so this reads it the same way and asserts `is False` (#509, senior review).
    """
    from open_garden_planner.app.settings import AppSettings, create_qsettings

    value = create_qsettings().value(AppSettings.KEY_AGENT_API_ENABLED, True, type=bool)
    assert value is False, (
        f"the Agent API guard reads {value!r}, not False — a test could bind a real "
        "loopback port (the product default is on, and the port default is 8765). "
        "The write belongs in _reset_app_settings._reset(), immediately after the "
        "key wipe, not here (#509)."
    )


@pytest.fixture(autouse=True)
def _reclaim_widgets(qtbot: object):
    """Destroy the widget graph a test leaves behind, so the next one does not pay for it.

    This is the measured root cause of the suite's single largest cost block
    (#509), and the numbers are stark. A clean process holds **0** widgets and an
    `apply_theme()` round-trip costs **1.3 ms**. After `tests/ui/test_main_window.py`
    — 30 tests, each building a full `GardenPlannerApp` — the process holds
    **38 271** widgets and **1 580** top-level widgets, of which **0 % are visible**,
    and one `apply_theme()` round-trip costs **22 478 ms**. That is why
    `test_iconography_3c.py` takes 2.1 s alone and 96.7 s in the suite: the theme
    tests are not slow, they are paying for everyone else's leaked widget graphs
    through `apply_theme()`'s `app.allWidgets()` walk.

    **The cause, as far as it was established (#515).** Nothing calls
    `deleteLater()` on those apps: `qtbot.addWidget` closes a widget at teardown, and
    closing is not deleting. The Python wrapper is collected while the C++ object and its
    ~1 270 children survive to process exit. A large part of the population is ordinary
    uncollected cyclic garbage (reclaimed by `gc.collect()`), while a residual graph survives
    every collection pass held outside Python's reachable object graph (e.g. C++-side active
    window / focus references cleared by `deleteLater()`). Moreover, `deleteLater()` alone
    does not delete until the event loop processes deferred deletions — so the explicit event
    loop flush with `sendPostedEvents(DeferredDelete)` is the load-bearing half of this fixture.

    **The fix, in one place.** Two things deliver the ordering. Measured with
    `--setup-show` on `tests/integration/test_agent_api_server.py`:

        with the `qtbot` request     _no_leaked_agent_api_thread -> _reclaim_widgets -> qtbot
        without it                   _no_leaked_agent_api_thread -> qtbot -> _reclaim_widgets

    So the **root-conftest position** delivers the FIRST arrow: this fixture finalises after
    `tests/integration/conftest.py`'s `_no_leaked_agent_api_thread` has walked
    `topLevelWidgets()` to stop any server an app still owns, and that holds whichever way
    the request goes - it is what keeps the leak warning able to fire. The `qtbot` request
    delivers the SECOND: it orders this fixture ahead of qtbot's own teardown. Reclaiming
    earlier would delete those windows first and the leak warning would never fire — a gate
    that silently stops reporting. Measured effect of this exact
    sequence on that same 38 271-widget process: **38 271 -> 0 widgets, 1 580 -> 0
    top-level widgets.** That is the count this fixture can report; it says nothing
    about what would survive if `deleteLater()` were dropped, because the alternative
    was never measured, only this one.

    `sendPostedEvents` must name `QEvent.Type.DeferredDelete` explicitly. Passing
    `None, 0` flushes no deferred deletions, as Qt requires the specific event type.
    """
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication

    if os.environ.get("OGP_TEST_MEASURE_WIDGET_LEAK") == "1":
        # #515: the probe needs the RAW leak this fixture reclaims, so it can measure the
        # population rather than its absence. The suite never sets this; every normal run
        # reclaims as before. scripts/probe_widget_leaks.py is the only writer.
        yield
        return

    yield

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            # Already deleted on the C++ side; the wrapper outlived it.
            pass
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


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

    It yields the real method: `tests/integration/test_startup_welcome.py` puts it
    back for its tests, so the startup path itself is pinned (owner report on PR #584 -
    with every test silenced, nothing would notice the dialog going missing).
    """
    from open_garden_planner.app.application import GardenPlannerApp

    original = GardenPlannerApp._show_welcome_dialog
    # what is handed on must be the product's method, not an earlier patch of it
    assert original.__qualname__ == "GardenPlannerApp._show_welcome_dialog", original
    GardenPlannerApp._show_welcome_dialog = lambda _self: None  # type: ignore[method-assign]
    yield original
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


# ── Windows Power Throttling Opt-Out (#616) ──────────────────────────────────
def disable_windows_power_throttling() -> bool:
    """Opt the current process out of Windows EcoQoS power throttling (#616).

    On Windows 11, power throttling can raise timings ~1.8x partway through
    a test run when threads are classified as background/EcoQoS.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.DWORD),
                ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetProcessInformation.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.SetProcessInformation.restype = wintypes.BOOL

        state = PROCESS_POWER_THROTTLING_STATE()
        state.Version = 1  # PROCESS_POWER_THROTTLING_CURRENT_VERSION
        state.ControlMask = 1  # PROCESS_POWER_THROTTLING_EXECUTION_SPEED
        state.StateMask = 0

        res = kernel32.SetProcessInformation(
            kernel32.GetCurrentProcess(),
            4,  # ProcessPowerThrottling
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
        return bool(res)
    except Exception:
        return False


def get_windows_power_throttling_state() -> tuple[int, int] | None:
    """Read current Windows power throttling (ControlMask, StateMask) or None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.DWORD),
                ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetProcessInformation.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.GetProcessInformation.restype = wintypes.BOOL

        state = PROCESS_POWER_THROTTLING_STATE()
        state.Version = 1
        res = kernel32.GetProcessInformation(
            kernel32.GetCurrentProcess(),
            4,
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
        if res:
            return state.ControlMask, state.StateMask
        return None
    except Exception:
        return None


def pytest_configure(config: pytest.Config) -> None:
    """Global test configuration hook.

    Opts out of Windows power throttling (EcoQoS) on Windows when running tests,
    preventing 1.8x timing drift on Windows dev machines (#616).
    """
    if sys.platform == "win32":
        disable_windows_power_throttling()
