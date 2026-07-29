"""The test harness must never touch the user's real settings store (issue #285).

This is the end-to-end half of #285: build the whole application, exercise the
settings paths it runs at startup and shutdown, and prove every read and write
landed in the isolated test store.

Why a full-app test and not a unit assertion: the escape hatch #283 found was
invisible at unit level. ``AppSettings`` was isolated and looked fine; the leak
was ``UiStateStore``, reached only through ``GardenPlannerApp``'s constructor
(``_restore_ui_state``) and its ``closeEvent`` (``_save_ui_state``), which
pytest-qt triggers at teardown for every registered widget. Measured
consequence: 40 teardowns x 3 keys = 120 writes into the developer's own
registry from one test file, and a #283 assertion that failed *with* the fix
applied because a stale real-world toolbar layout was the actual variable.

The spy records Python-level access only — which is the entire surface this app
uses. Access from inside Qt's own C++ (a native dialog remembering its last
directory, say) is neither visible here nor this project's to control.
"""

# ruff: noqa: ARG002

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QSettings

import open_garden_planner.app.settings as settings_module
from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.app.ui_state import UiStateStore


def _active_store() -> tuple[str, str]:
    """The (organization, application) pair the app is pointed at right now.

    Read at call time, never at import: ``conftest.isolate_qsettings`` rebinds
    these two names when the session's first test starts, which is *after* this
    module is imported during collection.
    """
    return (settings_module.ORGANIZATION_NAME, settings_module.APPLICATION_NAME)


class _StoreAccessRecorder:
    """Record every Python-level settings read/write, tagged with its store.

    Reads matter as much as writes: the #283 symptom was a *read* of the
    developer's saved toolbar layout making an assertion machine-dependent.
    """

    def __init__(self) -> None:
        self.reads: list[tuple[tuple[str, str], str]] = []
        self.writes: list[tuple[tuple[str, str], str]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original_value = QSettings.value
        original_set_value = QSettings.setValue

        def _store(settings: QSettings) -> tuple[str, str]:
            return (settings.organizationName(), settings.applicationName())

        def value(settings: QSettings, key: str, *args: Any, **kwargs: Any) -> Any:
            self.reads.append((_store(settings), key))
            return original_value(settings, key, *args, **kwargs)

        def set_value(settings: QSettings, key: str, val: Any) -> None:
            self.writes.append((_store(settings), key))
            original_set_value(settings, key, val)

        # PyQt6 permits assignment on its wrappertype, verified on this Qt build;
        # monkeypatch restores the C++ slots at teardown.
        monkeypatch.setattr(QSettings, "value", value)
        monkeypatch.setattr(QSettings, "setValue", set_value)

    def stores_touched(self) -> set[tuple[str, str]]:
        return {store for store, _ in [*self.reads, *self.writes]}

    def keys_written(self) -> set[str]:
        return {key for _, key in self.writes}


@pytest.fixture(autouse=True)
def _no_welcome_dialog(_reset_app_settings: Any) -> None:
    """Suppress the deferred modal Welcome dialog (§11.4: it hangs the suite).

    Depends on the conftest reset so this write survives the per-test clear.
    """
    get_settings().show_welcome_on_startup = False


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _StoreAccessRecorder:
    rec = _StoreAccessRecorder()
    rec.install(monkeypatch)
    return rec


class TestFullAppLifecycleStaysInTheTestStore:
    def test_startup_and_shutdown_never_touch_the_real_store(
        self,
        isolate_qsettings: tuple[str, str],
        recorder: _StoreAccessRecorder,
        qtbot: Any,
    ) -> None:
        """The #285 acceptance criterion, stated as an assertion.

        ``isolate_qsettings`` yields the production (organization, application)
        pair it displaced, so this never hardcodes — and never goes stale on —
        the real store's identity.
        """
        real_store = isolate_qsettings

        window = GardenPlannerApp()  # __init__ -> _restore_ui_state() reads
        qtbot.addWidget(window)
        settings = get_settings()
        settings.show_labels = not settings.show_labels  # an AppSettings write
        window._save_ui_state()  # exactly what closeEvent does

        # Anti-vacuity, in both directions: a spy that recorded nothing, or an
        # app that persisted nothing, would satisfy the real-store check below
        # while proving nothing at all.
        assert recorder.reads, "no settings were read — the spy proves nothing"
        assert recorder.writes, "no settings were written — the spy proves nothing"
        ui_keys = {k for k in recorder.keys_written() if k.startswith("UiState/")}
        assert ui_keys, f"UiStateStore never persisted; keys: {recorder.keys_written()}"

        offenders = [
            (kind, key)
            for kind, entries in (("read", recorder.reads), ("write", recorder.writes))
            for store, key in entries
            if store == real_store
        ]
        assert offenders == [], (
            f"the real user store {real_store} was accessed: {offenders}"
        )
        # Stricter, and what actually keeps the suite reproducible: a rogue
        # third store would also be a leak, even under a different name.
        assert recorder.stores_touched() == {_active_store()}

    def test_both_stores_share_the_isolated_backend(
        self, recorder: _StoreAccessRecorder, qtbot: Any
    ) -> None:
        """One chokepoint, so isolating it covers preferences *and* UI state.

        Pins the property that made ``_isolate_ui_state`` deletable, rather than
        the fixture that used to provide it.
        """
        window = GardenPlannerApp()
        qtbot.addWidget(window)

        assert window._ui_state._settings.fileName() == (
            get_settings()._settings.fileName()
        )
        assert UiStateStore()._settings.organizationName() == _active_store()[0]
        assert recorder.stores_touched() == {_active_store()}
