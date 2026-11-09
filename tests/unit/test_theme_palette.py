"""The app's theme decides the palette too, whatever the Windows mode (#791).

Root cause pinned here: ``apply_theme()`` used to write a stylesheet only. The
application palette and Qt's colour scheme stayed the operating system's, so
everything that reads them — ``palette(text)`` in a widget stylesheet, link colours
in rich text, the native style's check boxes and the toolbar's overflow button —
followed Windows instead of the app. With the app's light theme on a dark Windows
that is white text on cream (1.05:1).

Every check renders the real widget and measures what it painted, in all four
combinations of app theme and Windows mode.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.ui import theme
from open_garden_planner.ui.theme import ThemeColors, ThemeMode, apply_theme
from tests.chrome_measure import (
    GRAPHIC_CONTRAST,
    TEXT_CONTRAST,
    background_of,
    contrast,
    grab_image,
    ink_contrast,
    simulate_windows_mode,
    text_contrast,
)

_COMBINATIONS = [
    pytest.param(ThemeMode.LIGHT, False, id="light-app-on-light-windows"),
    pytest.param(ThemeMode.LIGHT, True, id="light-app-on-dark-windows"),
    pytest.param(ThemeMode.DARK, False, id="dark-app-on-light-windows"),
    pytest.param(ThemeMode.DARK, True, id="dark-app-on-dark-windows"),
]


@pytest.fixture
def themed(qapp: QApplication):
    """Apply a theme on a simulated Windows mode; leave the suite's light theme behind."""

    def _apply(mode: ThemeMode, windows_dark: bool) -> dict[str, str]:
        simulate_windows_mode(qapp, windows_dark)
        apply_theme(qapp, mode)
        return ThemeColors.get_colors(mode)

    yield _apply
    apply_theme(qapp, ThemeMode.LIGHT)


#: qtbot keeps a weak reference only: a host nobody holds takes its children with it
_HOSTS: list[QWidget] = []


@pytest.fixture(autouse=True)
def _release_hosts():
    yield
    _HOSTS.clear()


def _host(qtbot, *children: QWidget) -> QWidget:
    host = QWidget()
    _HOSTS.append(host)
    layout = QVBoxLayout(host)
    for child in children:
        layout.addWidget(child)
    qtbot.addWidget(host)
    host.resize(320, 60 * len(children))
    host.show()
    qtbot.waitExposed(host)
    return host


@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_the_application_palette_is_the_themes(themed, qapp, mode, windows_dark) -> None:
    colors = themed(mode, windows_dark)
    palette = qapp.palette()
    expected = {
        QPalette.ColorRole.Window: "background",
        QPalette.ColorRole.WindowText: "text_primary",
        QPalette.ColorRole.Base: "input",
        QPalette.ColorRole.Text: "text_primary",
        QPalette.ColorRole.Button: "button",
        QPalette.ColorRole.ButtonText: "text_primary",
        QPalette.ColorRole.PlaceholderText: "text_secondary",
        QPalette.ColorRole.Link: "link",
    }
    for role, token in expected.items():
        assert palette.color(QPalette.ColorGroup.Active, role).name() == colors[token], (
            f"{role.name} is not the theme's {token}"
        )
    assert palette.color(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
    ).name() == colors["text_disabled"]


@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_palette_text_in_a_widget_stylesheet_is_readable(
        themed, qtbot, mode, windows_dark) -> None:
    """``color: palette(text)`` — the Find Plants count and the seed statistics."""
    colors = themed(mode, windows_dark)
    label = QLabel("61 plant(s) in project")
    label.setStyleSheet("color: palette(text);")
    _host(qtbot, label)
    assert text_contrast(label) >= TEXT_CONTRAST
    assert contrast(colors["text_primary"], colors["background"]) >= TEXT_CONTRAST


@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_a_rich_text_link_is_readable(themed, qtbot, mode, windows_dark) -> None:
    themed(mode, windows_dark)
    label = QLabel("<a href='https://example.org'>Wikipedia</a>")
    _host(qtbot, label)
    assert text_contrast(label) >= TEXT_CONTRAST


def _indicator_rect(button: QWidget) -> QRect:
    option = QStyleOptionButton()
    option.initFrom(button)
    element = (QStyle.SubElement.SE_CheckBoxIndicator if isinstance(button, QCheckBox)
               else QStyle.SubElement.SE_RadioButtonIndicator)
    return button.style().subElementRect(element, option, button)


@pytest.mark.parametrize("kind", [QCheckBox, QRadioButton])
@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_an_unchecked_indicator_shows_against_the_window(
        themed, qtbot, mode, windows_dark, kind) -> None:
    """An empty box must be seen as a box: its outline against the window (3:1)."""
    colors = themed(mode, windows_dark)
    button = kind("Show this screen on startup")
    _host(qtbot, button)
    rect = _indicator_rect(button)
    assert rect.width() >= 12 and rect.height() >= 12
    image = grab_image(button, rect)
    outline = max(
        (contrast(image.pixelColor(x, y), colors["background"])
         for x in range(image.width()) for y in range(image.height())),
        default=1.0,
    )
    assert outline >= GRAPHIC_CONTRAST


@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_a_checked_box_shows_its_mark(themed, qtbot, mode, windows_dark) -> None:
    colors = themed(mode, windows_dark)
    box = QCheckBox("Trees")
    box.setChecked(True)
    _host(qtbot, box)
    image = grab_image(box, _indicator_rect(box))
    # filled in the accent colour, and the mark stands out from the fill
    assert contrast(background_of(image), colors["background"]) >= GRAPHIC_CONTRAST
    assert ink_contrast(image) >= GRAPHIC_CONTRAST


@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_a_check_box_in_a_list_shows_against_the_list(
        themed, qtbot, mode, windows_dark) -> None:
    """The plant details' "Recorded functions" rows are checkable list items."""
    colors = themed(mode, windows_dark)
    rows = QListWidget()
    item = QListWidgetItem("Nitrogen fixer")
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(Qt.CheckState.Unchecked)
    rows.addItem(item)
    _host(qtbot, rows)
    row = rows.visualItemRect(item)
    image = grab_image(rows.viewport(), QRect(row.left(), row.top(), 26, row.height()))
    outline = max(
        (contrast(image.pixelColor(x, y), colors["input"])
         for x in range(image.width()) for y in range(image.height())),
        default=1.0,
    )
    assert outline >= GRAPHIC_CONTRAST


def test_system_mode_asks_the_operating_system_not_its_own_palette(
        qapp, monkeypatch) -> None:
    """The trap behind the palette fix: once the app owns the palette, a detection
    that reads the palette reads the app's last theme and never the system again."""
    try:
        for system_dark in (True, False, True):
            monkeypatch.setattr(
                theme, "_system_color_scheme",
                lambda dark=system_dark: Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light,
            )
            # an explicit theme of the OTHER kind first: its palette must not decide
            apply_theme(qapp, ThemeMode.LIGHT if system_dark else ThemeMode.DARK)
            apply_theme(qapp, ThemeMode.SYSTEM)
            assert theme.is_dark_theme() is system_dark
            assert QColor(qapp.palette().color(QPalette.ColorRole.Window)).name() == (
                ThemeColors.DARK if system_dark else ThemeColors.LIGHT)["background"]
    finally:
        monkeypatch.undo()
        apply_theme(qapp, ThemeMode.LIGHT)


def test_both_palettes_reach_text_contrast_for_links_and_secondary_text() -> None:
    for colors in (ThemeColors.LIGHT, ThemeColors.DARK):
        for surface in ("background", "surface", "input"):
            assert contrast(colors["link"], colors[surface]) >= TEXT_CONTRAST
            assert contrast(colors["text_secondary"], colors[surface]) >= TEXT_CONTRAST
