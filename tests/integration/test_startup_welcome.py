"""The Welcome dialog opens at startup, with the recent plans (owner report on PR #584).

The suite silences the dialog for every test (``tests/conftest.py``,
``_silence_welcome_dialog``; PF-TST-11), because its ``exec()`` is modal and nobody
closes it headless. So nothing else drives the real startup path. These tests put
the real ``GardenPlannerApp._show_welcome_dialog`` back and start from the
production default (no stored value). Three things are stood in for:

- ``WelcomeDialog.exec`` records the dialog instead of blocking (any other modal
  ``QDialog.exec`` at startup fails the test instead of hanging the run);
- ``AutoSaveManager.find_recovery_files`` finds nothing, or ``_check_recovery_files``
  is replaced where a test is about the recovery branch;
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
from PyQt6.QtWidgets import QDialog

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


@pytest.mark.parametrize("recovered", [False, True])
def test_a_recovery_prompt_comes_first_and_a_declined_one_still_shows_the_welcome(
        qtbot, monkeypatch, startup: Startup, recovered: bool) -> None:
    def recovery(_self: GardenPlannerApp) -> bool:
        startup.calls.append(("recovery", ()))
        return recovered

    monkeypatch.setattr(GardenPlannerApp, "_check_recovery_files", recovery)

    startup.start(qtbot)

    assert startup.calls[0][0] == "recovery"
    assert len(startup.shown) == (0 if recovered else 1)
