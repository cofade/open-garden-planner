"""The Welcome dialog opens at startup, with the recent plans (owner report on PR #584).

The suite silences the dialog for every test (``tests/conftest.py``,
``_silence_welcome_dialog``; PF-TST-11), because its ``exec()`` is modal and nobody
closes it headless. So nothing else drives the real startup path: these tests put
the real ``GardenPlannerApp._show_welcome_dialog`` back, start from the production
default (no stored value), and replace only ``exec()`` - the one call that would
block. The 500 ms startup timer, the settings read, the dialog's recent list and
the wiring of a picked plan to the window all run as in the product.

What these tests cannot see: a "show on startup" flag the user (or a stray script
writing the real settings store) has stored as false. Then the app does what the
setting says (PF-TST-27).
"""

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import AppSettings, create_qsettings, get_settings
from open_garden_planner.services import AutoSaveManager
from open_garden_planner.ui.dialogs import WelcomeDialog


@pytest.fixture
def real_startup(monkeypatch: pytest.MonkeyPatch, _silence_welcome_dialog):
    """The real Welcome path with a non-blocking ``exec()``; yields the dialogs shown."""
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", _silence_welcome_dialog)
    # a recovery prompt is modal too, and belongs to its own branch of the startup
    monkeypatch.setattr(AutoSaveManager, "find_recovery_files", classmethod(lambda _cls: []))
    shown: list[WelcomeDialog] = []
    monkeypatch.setattr(WelcomeDialog, "exec", lambda dialog: shown.append(dialog) or 0)
    return shown


def test_a_fresh_install_opens_the_welcome_dialog_with_the_recent_plans(
        qtbot, monkeypatch, tmp_path: Path, real_startup) -> None:
    # the production default: the conftest stores False for every test, a user has nothing
    create_qsettings().remove(AppSettings.KEY_SHOW_WELCOME)
    assert AppSettings.DEFAULT_SHOW_WELCOME is True
    assert get_settings().show_welcome_on_startup is True
    plan = tmp_path / "Kitchen garden.ogp"
    plan.write_text("{}", encoding="utf-8")
    get_settings().add_recent_file(str(plan))
    opened: list[str] = []
    monkeypatch.setattr(GardenPlannerApp, "_open_project_file", lambda _self, path: opened.append(path))

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitUntil(lambda: len(real_startup) == 1, timeout=5000)

    dialog = real_startup[0]
    assert dialog.parent() is win
    assert dialog._show_on_startup_checkbox.isChecked()
    items = [dialog._recent_list.item(i) for i in range(dialog._recent_list.count())]
    assert [item.data(Qt.ItemDataRole.UserRole) for item in items] == [str(plan)]
    assert items[0].text() == "Kitchen garden"
    # a double click on a recent plan opens it in this window
    dialog._recent_list.itemDoubleClicked.emit(items[0])
    assert opened == [str(plan)]
    qtbot.wait(700)
    assert len(real_startup) == 1, "the startup sequence opened the dialog more than once"


def test_switched_off_in_the_dialog_it_stays_closed_at_the_next_start(qtbot, real_startup) -> None:
    create_qsettings().remove(AppSettings.KEY_SHOW_WELCOME)
    first = GardenPlannerApp()
    qtbot.addWidget(first)
    first.show()
    qtbot.waitUntil(lambda: len(real_startup) == 1, timeout=5000)
    real_startup[0]._show_on_startup_checkbox.setChecked(False)  # the user's choice
    assert get_settings().show_welcome_on_startup is False

    second = GardenPlannerApp()
    qtbot.addWidget(second)
    second.show()
    qtbot.wait(900)  # beyond the 500 ms startup timer
    assert len(real_startup) == 1
