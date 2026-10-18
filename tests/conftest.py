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
def _reclaim_widgets(qtbot: object):  # noqa: ARG001 - see below
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

    **The cause, as far as it was established — and the limit of that.** Nothing calls
    `deleteLater()` on those apps: `qtbot.addWidget` closes a widget at teardown, and
    closing is not deleting. The Python wrapper is collected (only 2 of the 30 apps were
    still reachable) while the C++ object and its ~1 270 children survive to process exit.
    `gc.collect()` does not help — it freed 8 337 objects and moved the widget count from
    38 271 to only 37 638, so the survivors are not reachable as collectable cycles.
    **What holds them is NOT identified.** A referrer probe walked into PyQt6/sip
    bookkeeping and stopped there, so "strong references" is the reading consistent with
    the `gc` measurement, not a proven mechanism — and the chokepoint below does not need
    it to be true. Naming it here would be the same error as a docstring that calls
    `sendPostedEvents(None, 0)` the right call and measures the wrong one.

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
    `None, 0` — the shape that looks right — flushes nothing, and measuring that
    wrong call is how the first attempt at this "proved" the chokepoint ineffective.
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
