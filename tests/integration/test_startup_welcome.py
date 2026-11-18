"""The Welcome dialog opens at startup, with the recent plans (owner report on PR #584).

The suite silences the dialog for every test (``tests/conftest.py``,
``_silence_welcome_dialog``; PF-TST-11), because its ``exec()`` is modal and nobody
closes it headless. So nothing else drives the real startup path. These tests put
the real ``GardenPlannerApp._show_welcome_dialog`` back and start from the
production default (no stored value). Three things are stood in for:

- ``WelcomeDialog.exec`` records the dialog instead of blocking. Any other modal at
  startup fails the test instead of hanging the run: a Python-level ``QDialog.exec``
  and the static ``QMessageBox`` helpers (``question`` and its siblings run their own
  modal loop in C++, past any ``exec`` patch) raise;
- ``AutoSaveManager.find_recovery_files`` finds nothing, or one recovery file where a
  test drives the real recovery prompt with a scripted answer;
- the window's handlers for a picked plan, New and Open record their calls, so what
  runs as in the product is the WIRING of the dialog to the window, not the opening.

The 500 ms startup timer, the settings read and the dialog's recent list run as in
the product. Each window's end of ``_startup_sequence`` is observed by a spy, so no
assertion depends on how long the timer is (PF-TST-25).

What these tests cannot see: a "show on startup" flag stored as false - by the user,
or by a script that wrote the real settings store (PF-TST-27). Then the app does what
the setting says.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QMessageBox

import open_garden_planner.app.settings as settings_module
from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import AppSettings, create_qsettings, get_settings
from open_garden_planner.services import AutoSaveManager
from open_garden_planner.ui.dialogs import WelcomeDialog


@dataclass
class Startup:
    shown: list[WelcomeDialog] = field(default_factory=list)
    finished: list[GardenPlannerApp] = field(default_factory=list)
    calls: list[tuple[str, object]] = field(default_factory=list)

    def start(self, qtbot) -> GardenPlannerApp:
        """A new main window, shown, once its startup sequence has run."""
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        win.show()
        qtbot.waitUntil(lambda: win in self.finished, timeout=5000)
        return win


@pytest.fixture
def startup(monkeypatch: pytest.MonkeyPatch, _silence_welcome_dialog) -> Startup:
    state = Startup()
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", _silence_welcome_dialog)
    monkeypatch.setattr(AutoSaveManager, "find_recovery_files", classmethod(lambda _cls: []))
    monkeypatch.setattr(WelcomeDialog, "exec", lambda dialog: state.shown.append(dialog) or 0)

    def unexpected_modal(dialog: QDialog) -> int:
        raise AssertionError(f"an unexpected modal dialog at startup: {type(dialog).__name__}")

    monkeypatch.setattr(QDialog, "exec", unexpected_modal)

    def unexpected_box(*_args, **_kwargs) -> QMessageBox.StandardButton:
        raise AssertionError("an unexpected message box at startup")

    for helper in ("question", "information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, helper, staticmethod(unexpected_box))
    sequence = GardenPlannerApp._startup_sequence

    def observed(self: GardenPlannerApp) -> None:
        sequence(self)
        state.finished.append(self)

    monkeypatch.setattr(GardenPlannerApp, "_startup_sequence", observed)
    for name in ("_open_project_file", "_on_new_project", "_on_open_project"):
        monkeypatch.setattr(GardenPlannerApp, name,
                            lambda _self, *args, name=name: state.calls.append((name, args)))
    # the production default: the conftest stores False for every test, a user has nothing
    create_qsettings().remove(AppSettings.KEY_SHOW_WELCOME)
    return state


def test_a_fresh_install_opens_the_welcome_dialog_with_the_recent_plans(
        qtbot, tmp_path: Path, startup: Startup) -> None:
    assert AppSettings.DEFAULT_SHOW_WELCOME is True
    assert get_settings().show_welcome_on_startup is True
    plan = tmp_path / "Kitchen garden.ogp"
    plan.write_text("{}", encoding="utf-8")
    get_settings().add_recent_file(str(plan))

    win = startup.start(qtbot)

    assert len(startup.shown) == 1
    dialog = startup.shown[0]
    assert dialog.parent() is win
    assert dialog._show_on_startup_checkbox.isChecked()
    items = [dialog._recent_list.item(i) for i in range(dialog._recent_list.count())]
    assert [item.data(Qt.ItemDataRole.UserRole) for item in items] == [str(plan)]
    assert items[0].text() == "Kitchen garden"
    # a double click on a recent plan, New and Open reach this window's handlers
    dialog._recent_list.itemDoubleClicked.emit(items[0])
    dialog.new_project_requested.emit()
    dialog.open_project_requested.emit()
    assert [name for name, _args in startup.calls] == [
        "_open_project_file", "_on_new_project", "_on_open_project"]
    assert startup.calls[0][1] == (str(plan),)


def test_switched_off_in_the_dialog_it_stays_closed_at_the_next_start(
        qtbot, monkeypatch, startup: Startup) -> None:
    startup.start(qtbot)
    assert len(startup.shown) == 1
    startup.shown[0]._show_on_startup_checkbox.setChecked(False)  # the user's choice
    assert get_settings().show_welcome_on_startup is False
    # the next start reads through a new settings object, not the one the dialog wrote
    monkeypatch.setattr(settings_module, "_settings_instance", None)

    second = startup.start(qtbot)

    assert second in startup.finished
    assert len(startup.shown) == 1


@pytest.mark.parametrize(("answer", "welcome", "loaded", "deleted"), [
    (QMessageBox.StandardButton.No, 1, 0, 0),
    (QMessageBox.StandardButton.Discard, 1, 0, 1),
    (QMessageBox.StandardButton.Yes, 0, 1, 0),
])
def test_the_recovery_prompt_comes_first_and_only_a_recovery_skips_the_welcome(
        qtbot, monkeypatch, tmp_path: Path, startup: Startup,
        answer: QMessageBox.StandardButton, welcome: int, loaded: int, deleted: int) -> None:
    autosave = tmp_path / ".ogp_autosave_untitled.ogp"
    monkeypatch.setattr(AutoSaveManager, "find_recovery_files",
                        classmethod(lambda _cls: [(autosave, {"timestamp": "2026-10-24 12:00"})]))

    def question(*_args, **_kwargs) -> QMessageBox.StandardButton:
        startup.calls.append(("question", ()))
        return answer

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    monkeypatch.setattr(GardenPlannerApp, "_load_recovery_file",
                        lambda _self, path: startup.calls.append(("load", (path,))))
    monkeypatch.setattr(AutoSaveManager, "delete_recovery_file",
                        classmethod(lambda _cls, path: startup.calls.append(("delete", (path,)))))

    startup.start(qtbot)

    names = [name for name, _args in startup.calls]
    assert names[0] == "question"
    assert (names.count("load"), names.count("delete")) == (loaded, deleted)
    assert len(startup.shown) == welcome


def test_real_entrypoint_shows_modal_welcome_dialog_without_stubs(tmp_path: Path) -> None:
    """Exercise ``main()`` end-to-end with zero dialog/window stubs.

    Unlike the in-process fixture above, this runs the real application entry
    point from scratch with an empty isolated settings store and verifies that a
    real visible, modal ``WelcomeDialog`` actually opens and closes cleanly on
    first startup.
    """
    import os
    import subprocess
    import sys

    probe = tmp_path / "verify_startup_welcome.py"
    probe.write_text(
        """import atexit
import os
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, QTimer
from PyQt6.QtWidgets import QApplication

# Isolate settings + Qt user locations without mutating show_welcome_on_startup.
from open_garden_planner.config import settings

settings.ORGANIZATION_NAME = "cofade_test"
settings.APPLICATION_NAME = f"Open Garden Planner Real Startup {os.getpid()}"
QStandardPaths.setTestModeEnabled(True)

from open_garden_planner import main as app_main
from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import AppSettings, create_qsettings
from open_garden_planner.services import AutoSaveManager
from open_garden_planner.ui.dialogs import WelcomeDialog

# Clear only this throwaway test key after startup finishes.
def _cleanup() -> None:
    s = create_qsettings()
    s.clear()
    s.sync()

atexit.register(_cleanup)
create_qsettings().clear()
AutoSaveManager.find_recovery_files = classmethod(lambda _cls: [])

seen: dict[str, object] = {}
orig_init = GardenPlannerApp.__init__

def _observe_window(self: GardenPlannerApp, *args: object, **kwargs: object) -> None:
    orig_init(self, *args, **kwargs)
    seen["window"] = self
    deadline_ms = [6000]

    def _poll_modal() -> None:
        modal = QApplication.activeModalWidget()
        if isinstance(modal, WelcomeDialog) and modal.isVisible():
            seen["dialog_visible"] = modal.isVisible()
            seen["dialog_modal"] = modal.isModal()
            seen["checkbox_checked"] = modal._show_on_startup_checkbox.isChecked()
            modal.reject()
            QTimer.singleShot(50, _verify_after_close)
            return
        deadline_ms[0] -= 25
        if deadline_ms[0] <= 0:
            seen["timeout"] = True
            QApplication.exit(2)
            return
        QTimer.singleShot(25, _poll_modal)

    def _verify_after_close() -> None:
        win = seen["window"]
        seen["window_visible_after_close"] = win.isVisible()
        seen["still_modal"] = QApplication.activeModalWidget() is not None
        win.close()
        QApplication.exit(0)

    QTimer.singleShot(50, _poll_modal)

GardenPlannerApp.__init__ = _observe_window  # type: ignore[method-assign]
sys.argv = ["open-garden-planner"]
rc = app_main.main()
assert rc == 0, f"main() exited with {rc}, seen={seen}"
assert seen.get("dialog_visible") is True, f"WelcomeDialog never became visible: {seen}"
assert seen.get("dialog_modal") is True, f"WelcomeDialog was not modal: {seen}"
assert seen.get("checkbox_checked") is True, f"Checkbox not checked by default: {seen}"
assert seen.get("window_visible_after_close") is True, f"Main window hidden after close: {seen}"
assert seen.get("still_modal") is False, f"Unexpected modal remained open: {seen}"
print("REAL_STARTUP_WELCOME_OK")
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    for var in ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA"):
        env[var] = str(profile_root)
    result = subprocess.run(
        [sys.executable, str(probe)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    assert "REAL_STARTUP_WELCOME_OK" in result.stdout

