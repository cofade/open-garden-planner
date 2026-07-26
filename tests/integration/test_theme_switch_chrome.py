"""Live theme-switch chrome integration (#279, ADR-039).

§8.10 policy: boot the real app in both modes and prove the previously
theme-blind surfaces now follow the palette — weather day cards, the
notification banners, urgency colors — and that widget-level QSS no longer
carries baked colors (the global stylesheet + dynamic properties style them).
"""

# ruff: noqa: ARG001, ARG002, ARG005

import pytest
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from open_garden_planner.ui.theme import (
    ThemeColors,
    ThemeMode,
    apply_theme,
    generate_stylesheet,
)
from open_garden_planner.ui.views.planting_calendar_view import _urgency_qcolor
from open_garden_planner.ui.views.tasks_view import _urgency_color
from open_garden_planner.ui.widgets.task_reminder_bar import TaskReminderBar
from open_garden_planner.ui.widgets.update_bar import UpdateBar
from open_garden_planner.ui.widgets.weather_widget import _DayCell

#: Every dynamic-property / objectName selector the widgets rely on. This
#: BINDS the property names set in widget code to the QSS rules that consume
#: them — renaming either side without the other now fails loudly instead of
#: silently killing the styling (ADR-039 review round P1).
_BOUND_SELECTORS = (
    'QFrame[weatherCard="true"]',
    '[frostSeverity="orange"]',
    '[frostSeverity="red"]',
    'QLineEdit[inputError="true"]',
    'QPushButton[buttonRole="primary"]',
    'QPushButton[buttonRole="secondary"]',
    'QLabel[textRole="h1"]',
    'QLabel[textRole="h2"]',
    'QLabel[textRole="hint"]',
    'QLabel[textRole="placeholder"]',
    'QLabel[colorRole="error"]',
    'QLabel[colorRole="secondary"]',
    "#TaskReminderBar",
    "#UpdateBar",
    "#constraintsDeleteAllBtn",
    "#CategoryDropdown",
    "#GlobalSearchResults",
)


def _grab_contains(widget: QWidget, hex_color: str, tolerance: int = 25) -> bool:
    """True if the rendered widget contains a pixel close to hex_color."""
    image = widget.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    target = QColor(hex_color)
    for x in range(image.width()):
        for y in range(image.height()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 200:
                continue
            distance = (
                abs(pixel.red() - target.red())
                + abs(pixel.green() - target.green())
                + abs(pixel.blue() - target.blue())
            )
            if distance <= tolerance:
                return True
    return False


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
        assert colors["warning"] in stylesheet  # saturated TaskReminderBar banner
        assert colors["warning_bg"] in stylesheet  # weather frost-card tint
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


def test_calendar_and_tasks_share_one_urgency_scale(qtbot) -> None:
    """Both surfaces read theme.URGENCY_TOKENS — and the four active levels
    stay pairwise distinct in BOTH palettes (the dark-mode collapse P1)."""
    app = QApplication.instance()
    try:
        for mode, palette in (
            (ThemeMode.LIGHT, ThemeColors.LIGHT),
            (ThemeMode.DARK, ThemeColors.DARK),
        ):
            apply_theme(app, mode)
            assert _urgency_qcolor("this_week").name() == palette["caution"]
            assert _urgency_qcolor("overdue").name() == _urgency_color("overdue")
            names = {
                _urgency_qcolor(key).name()
                for key in ("overdue", "today", "this_week", "coming_up")
            }
            assert len(names) == 4, names
    finally:
        apply_theme(app, ThemeMode.LIGHT)


@pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
def test_dynamic_property_selectors_present_in_stylesheet(qtbot, mode) -> None:
    stylesheet = generate_stylesheet(mode)
    for selector in _BOUND_SELECTORS:
        assert selector in stylesheet, selector


def test_frost_tint_actually_renders_pixels(qtbot) -> None:
    """Property → QSS rule → pixels: a renamed property or deleted rule now
    fails here instead of silently killing the tint (review-round P1)."""
    app = QApplication.instance()
    apply_theme(app, ThemeMode.LIGHT)
    cell = _DayCell()
    qtbot.addWidget(cell)
    cell.set_frost_severity("red")
    assert _grab_contains(cell, ThemeColors.LIGHT["error_bg"], tolerance=10)
    cell.set_frost_severity("orange")
    assert _grab_contains(cell, ThemeColors.LIGHT["warning_bg"], tolerance=10)


def test_reminder_bar_renders_saturated_warning(qtbot) -> None:
    """The banner must stay LOUD (§11.4: the quiet reminder was never seen)."""
    app = QApplication.instance()
    apply_theme(app, ThemeMode.LIGHT)
    bar = TaskReminderBar()
    qtbot.addWidget(bar)
    bar.show_reminder(3)
    bar.resize(400, 40)
    assert _grab_contains(bar, ThemeColors.LIGHT["warning"], tolerance=10)
