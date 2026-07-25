"""Live theme-switch chrome integration (#279, ADR-039).

§8.10 policy: boot the real app in both modes and prove the previously
theme-blind surfaces now follow the palette — weather day cards, the
notification banners, urgency colors — and that widget-level QSS no longer
carries baked colors (the global stylesheet + dynamic properties style them).
"""

# ruff: noqa: ARG001, ARG002, ARG005

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from open_garden_planner.ui.theme import ThemeColors, ThemeMode, apply_theme
from open_garden_planner.ui.views.tasks_view import _urgency_color
from open_garden_planner.ui.widgets.task_reminder_bar import TaskReminderBar
from open_garden_planner.ui.widgets.update_bar import UpdateBar
from open_garden_planner.ui.widgets.weather_widget import _DayCell


def _make_app(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    # Silence the 500 ms startup timer's MODAL Welcome dialog — headless, its
    # exec() blocks pytest-qt forever in tests that outlive the timer (§11.4).
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda self: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


@pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
def test_app_boots_styled_in_each_mode(qtbot, monkeypatch, mode) -> None:
    app = QApplication.instance()
    apply_theme(app, mode)
    try:
        win = _make_app(qtbot, monkeypatch)
        colors = ThemeColors.get_colors(mode)
        stylesheet = app.styleSheet()
        assert colors["accent"] in stylesheet
        assert colors["warning_bg"] in stylesheet  # TaskReminderBar banner
        assert colors["info_bg"] in stylesheet  # UpdateBar banner
        assert win.isEnabled()
    finally:
        apply_theme(app, ThemeMode.LIGHT)


def test_banners_carry_no_widget_level_colors(qtbot) -> None:
    """The bars are styled purely by objectName rules in the global QSS —
    the old hardcoded #e67e22 / #1a73e8 widget stylesheets are gone."""
    reminder = TaskReminderBar()
    update = UpdateBar()
    qtbot.addWidget(reminder)
    qtbot.addWidget(update)
    assert reminder.objectName() == "TaskReminderBar"
    assert update.objectName() == "UpdateBar"
    assert "#e67e22" not in reminder.styleSheet()
    assert "#1a73e8" not in update.styleSheet()
    assert reminder.styleSheet() == ""
    assert update.styleSheet() == ""


def test_weather_day_cell_is_property_styled(qtbot) -> None:
    """Day cards follow the theme via weatherCard/frostSeverity properties —
    the hardcoded-light #fafafa/#f8d7da/#fff3cd stylesheets are gone."""
    cell = _DayCell()
    qtbot.addWidget(cell)
    assert cell.property("weatherCard") is True
    assert "#fafafa" not in cell.styleSheet()

    cell.set_frost_severity("red")
    assert cell.property("frostSeverity") == "red"
    assert "#f8d7da" not in cell.styleSheet()

    cell.set_frost_severity(None)
    assert not cell.property("frostSeverity")


def test_urgency_colors_follow_the_palette(qtbot) -> None:
    app = QApplication.instance()
    try:
        apply_theme(app, ThemeMode.LIGHT)
        assert _urgency_color("overdue") == ThemeColors.LIGHT["error"]
        assert _urgency_color("this_week") == ThemeColors.LIGHT["caution"]

        apply_theme(app, ThemeMode.DARK)
        assert _urgency_color("overdue") == ThemeColors.DARK["error"]
        assert _urgency_color("upcoming") == ThemeColors.DARK["success"]
    finally:
        apply_theme(app, ThemeMode.LIGHT)
