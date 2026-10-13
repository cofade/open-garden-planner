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

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QSettings

import open_garden_planner.app.settings as settings_module
from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.app.ui_state import UiStateStore


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Requires real Linux file permissions")
@pytest.mark.parametrize("mask", [0o022, 0o000])
def test_a1_linux_native_settings_are_private_across_sync_and_migration(tmp_path, mask):
    # Fresh process: XDG lookup, Qt caches and umask cannot poison other tests.
    code = '''
import os, stat
from pathlib import Path
from PyQt6.QtCore import QSettings, QCoreApplication
from open_garden_planner.app import settings
app = QCoreApplication([])
os.umask(int(os.environ["A1_UMASK"]))
settings.ORGANIZATION_NAME = "a1_synthetic"
settings.APPLICATION_NAME = "permissions"
s = settings.create_qsettings()
p = Path(s.fileName())
s.setValue("api_keys/test", "synthetic-fixture")
s.sync()
assert stat.S_IMODE(p.stat().st_mode) == 0o600
os.chmod(p, 0o644)
s2 = settings.create_qsettings()
assert stat.S_IMODE(p.stat().st_mode) == 0o600
assert s2.value("api_keys/test") == "synthetic-fixture"
for n in range(3):
    s2.setValue("ui_state/counter", n)
    app.processEvents()
    s2.sync()
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
assert s2.value("api_keys/test") == "synthetic-fixture"
print("A1 Linux settings: 0600 after creation, migration and repeated atomic sync")
'''
    env = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path), A1_UMASK=str(mask),
               PYTHONPATH=str(Path(settings_module.__file__).resolve().parents[2]))
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a1_windows_backend_does_not_attempt_posix_protection(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows registry behavior")
    monkeypatch.setattr(settings_module, "_secure_linux_settings",
                        lambda *_: pytest.fail("POSIX protection called for registry backend"))
    backend = settings_module.create_qsettings()
    backend.setValue("a1/synthetic", "fixture")
    backend.sync()
    assert settings_module.create_qsettings().value("a1/synthetic") == "fixture"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Requires Linux descriptors and symlinks")
def test_a1_linux_safe_symlink_special_file_and_permission_failure(tmp_path):
    code = '''
import os
from pathlib import Path
from open_garden_planner.app.settings import _secure_linux_settings, SettingsSecurityError
root = Path(os.environ["A1_FIXTURE"])
target = root / "real.conf"
target.write_text("synthetic-fixture")
target.chmod(0o644)
link = root / "linked.conf"
link.symlink_to(target)
_secure_linux_settings(link)
assert target.stat().st_mode & 0o777 == 0o600
assert target.read_text() == "synthetic-fixture"
fifo = root / "special.conf"
os.mkfifo(fifo)
try:
    _secure_linux_settings(fifo)
except SettingsSecurityError:
    pass
else:
    raise AssertionError("Non-regular settings file was accepted")
original = os.fchmod
def refuse(*args):
    raise PermissionError("fixture refusal")
os.fchmod = refuse
try:
    _secure_linux_settings(target)
except SettingsSecurityError:
    pass
else:
    raise AssertionError("Permission failure was ignored")
finally:
    os.fchmod = original
assert target.read_text() == "synthetic-fixture"
'''
    env = dict(os.environ, A1_FIXTURE=str(tmp_path),
               PYTHONPATH=str(Path(settings_module.__file__).resolve().parents[2]))
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def _active_store() -> tuple[str, str]:
    """The (organization, application) pair the app is pointed at right now.

    Read at call time rather than captured at import, so this reports the live
    redirection whenever it happened. (Today ``tests/conftest.py`` rebinds the
    two names at its own import time — before this module is even imported — so
    a module-level constant would in fact work; reading at call time simply does
    not depend on that ordering.)
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
