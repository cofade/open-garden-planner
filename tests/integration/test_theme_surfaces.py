"""Every surface #791 names follows the app's theme, whatever the Windows mode.

Each test renders the real widget and measures what it painted, in all four
combinations of app theme and Windows mode: the Planting Calendar chart (it was a
white block, and 56 % of a 1920 px window), the canvas rulers, the soil
sparkline, the seed-viability cells, the Find Plants count, the seed statistics,
the unchecked check boxes and the toolbar's overflow button — and, end to end,
the same things inside the real main window.

Measured ratios are printed (``pytest -s``) as ``[CONTRAST] …`` lines.
"""

from __future__ import annotations

import datetime

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QMessageBox,
    QScrollArea,
    QStyle,
    QStyleOptionButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.models.seed_inventory import ViabilityStatus
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.dialogs import seed_inventory_dialog
from open_garden_planner.ui.theme import ThemeColors, ThemeMode, apply_theme, contrast_ratio
from open_garden_planner.ui.views import planting_calendar_view as calendar
from open_garden_planner.ui.widgets.soil_sparkline_widget import SoilSparklineWidget
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

#: qtbot keeps a weak reference only: a host nobody holds takes its children with it
_HOSTS: list[QWidget] = []


@pytest.fixture(autouse=True)
def _release_hosts():
    yield
    _HOSTS.clear()


@pytest.fixture
def themed(qapp: QApplication):
    """Apply a theme on a simulated Windows mode; leave the suite's light theme behind."""

    def _apply(mode: ThemeMode, windows_dark: bool) -> dict[str, str]:
        simulate_windows_mode(qapp, windows_dark)
        apply_theme(qapp, mode)
        return ThemeColors.get_colors(mode)

    yield _apply
    simulate_windows_mode(qapp, False)
    apply_theme(qapp, ThemeMode.LIGHT)


def _host(qtbot, child: QWidget, width: int = 1300, height: int = 300) -> QWidget:
    host = QWidget()
    _HOSTS.append(host)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(child)
    qtbot.addWidget(host)
    host.resize(width, height)
    host.show()
    qtbot.waitExposed(host)
    return host


def _report(surface: str, mode: ThemeMode, windows_dark: bool, ratio: float) -> None:
    windows = "dark" if windows_dark else "light"
    print(f"[CONTRAST] {surface} | app {mode.value} / Windows {windows} | {ratio:.2f}")


# ── The Planting Calendar chart ──────────────────────────────────────────────

_SPECIES = PlantSpeciesData(scientific_name="Solanum lycopersicum", common_name="Tomato")


def _chart(qtbot) -> calendar._GanttWidget:
    """The chart with three rows and one bar of every series in the first row."""
    year = datetime.date.today().year
    rows = [
        calendar._PlantRow(display_name=name, species=_SPECIES, species_key=name.lower())
        for name in ("Tomato", "Lettuce", "Basil")
    ]
    windows = {
        "tomato": [
            calendar._GanttWindow(
                datetime.date(year, month, 5), datetime.date(year, month, 25), task_type)
            for month, task_type in zip((2, 4, 6, 8), calendar._GANTT_COLORS, strict=True)
        ]
    }
    chart = calendar._GanttWidget()
    chart.set_data(rows, year, None, None, windows)
    _host(qtbot, chart, height=calendar._HEADER_H + 3 * calendar._ROW_H + 20)
    return chart


@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_the_planting_calendar_chart_paints_in_the_theme(
        themed, qtbot, mode, windows_dark) -> None:
    """It was a white block with black text in the dark theme."""
    colors = themed(mode, windows_dark)
    chart = _chart(qtbot)
    image = grab_image(chart)
    header_h, row_h = calendar._HEADER_H, calendar._ROW_H

    # Rows, the alternate row and the header are the theme's surfaces.
    assert image.pixelColor(150, header_h + 4).name() == colors["input"]
    assert image.pixelColor(150, header_h + row_h + 4).name() == colors["background_alt"]
    assert image.pixelColor(150, 4).name() == colors["surface"]

    name = text_contrast(chart, QRect(8, header_h + 2, calendar._NAME_W - 16, row_h - 4))
    header = text_contrast(chart, QRect(4, 2, calendar._NAME_W - 8, header_h - 6))
    _report("calendar chart: plant name", mode, windows_dark, name)
    _report("calendar chart: header", mode, windows_dark, header)
    assert name >= TEXT_CONTRAST
    assert header >= TEXT_CONTRAST


@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_every_bar_of_the_chart_stands_out_on_its_row(
        themed, qtbot, mode, windows_dark) -> None:
    """Harvest's dark red is 2.2:1 on the dark theme's rows; the series adapt."""
    colors = themed(mode, windows_dark)
    chart = _chart(qtbot)
    image = grab_image(chart)
    row = QColor(colors["input"])
    year = datetime.date.today().year
    bar_y = calendar._HEADER_H + calendar._ROW_H // 2
    for month, (task_type, base) in zip((2, 4, 6, 8), calendar._GANTT_COLORS.items(), strict=True):
        painted = image.pixelColor(int(chart._x(datetime.date(year, month, 15))), bar_y)
        assert painted.name() == calendar._series_qcolor(base).name(), task_type
        ratio = contrast_ratio(painted, row)
        _report(f"calendar chart: {task_type} bar", mode, windows_dark, ratio)
        if mode is ThemeMode.DARK:
            assert ratio >= GRAPHIC_CONTRAST, task_type
        else:
            # The light theme draws the reference colours, unchanged.
            assert painted.name() == base.name(), task_type


def test_the_chart_fills_its_scroll_area_and_scrolls_below_its_minimum(qtbot, qapp) -> None:
    """It was a fixed 1074 px block: 56 % of a 1920 px window."""
    chart = calendar._GanttWidget()
    chart.set_data([calendar._PlantRow("Tomato", _SPECIES, "tomato")],
                   datetime.date.today().year, None, None, {})
    area = QScrollArea()
    area.setWidgetResizable(True)   # as PlantingCalendarView builds it
    area.setWidget(chart)
    _host(qtbot, area, width=1900)
    qapp.processEvents()

    assert chart.width() == area.viewport().width() > calendar._TOTAL_W
    # December ends at the chart's right edge: the twelve months share the width.
    year = datetime.date.today().year
    assert chart._x(datetime.date(year, 12, 31)) == pytest.approx(chart.width(), abs=6)
    assert chart._month_x(12) == chart.width()

    area.window().resize(700, 300)
    qapp.processEvents()
    assert chart.width() == calendar._TOTAL_W
    assert area.horizontalScrollBar().maximum() > 0


# ── The canvas rulers ────────────────────────────────────────────────────────

@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_the_canvas_rulers_follow_the_theme(themed, qtbot, mode, windows_dark) -> None:
    """They stayed light grey in the dark theme."""
    colors = themed(mode, windows_dark)
    scene = CanvasScene()
    view = CanvasView(scene)
    _host(qtbot, view, width=900, height=500)
    qtbot.wait(50)
    viewport = view.viewport()
    strip = QRect(view.RULER_SIZE + 4, 0, 600, view.RULER_SIZE - 2)
    image = grab_image(viewport, strip)

    labels = ink_contrast(image)
    _report("ruler: tick labels", mode, windows_dark, labels)
    assert background_of(image).name() == colors["surface"]
    assert labels >= TEXT_CONTRAST


# ── The soil sparkline and the seed-viability cells ──────────────────────────

@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_the_soil_sparkline_paints_in_the_theme(themed, qtbot, mode, windows_dark) -> None:
    """Another white chart: white paper and near-black ink in the dark theme."""
    colors = themed(mode, windows_dark)
    chart = SoilSparklineWidget("ph")
    chart.set_data([SoilTestRecord(date="2026-03-01", ph=6.2),
                    SoilTestRecord(date="2026-06-01", ph=6.8)])
    _host(qtbot, chart, width=300, height=80)
    image = grab_image(chart)
    ratio = ink_contrast(image)
    _report("soil sparkline: line and labels", mode, windows_dark, ratio)
    assert background_of(image).name() == colors["input"]
    assert ratio >= TEXT_CONTRAST


@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
@pytest.mark.parametrize("status", list(ViabilityStatus))
def test_seed_viability_colours_are_the_themes(themed, mode, windows_dark, status) -> None:
    """The dialog chose between four tables of its own by the PALETTE's lightness."""
    colors = themed(mode, windows_dark)
    surface, _ink = seed_inventory_dialog._STATUS_TOKENS[status]
    background = seed_inventory_dialog._status_bg(status)
    assert background.name() == colors[surface]
    ratio = contrast_ratio(seed_inventory_dialog._status_fg(status), background)
    _report(f"seed viability: {status.value}", mode, windows_dark, ratio)
    assert ratio >= TEXT_CONTRAST


# ── End to end: the real main window ─────────────────────────────────────────

def _indicator_rect(box: QCheckBox) -> QRect:
    option = QStyleOptionButton()
    option.initFrom(box)
    return box.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, box)


@pytest.mark.parametrize(("mode", "windows_dark"), _COMBINATIONS)
def test_the_main_window_follows_the_theme_whatever_windows_says(
        themed, qtbot, monkeypatch, mode, windows_dark) -> None:
    """One window, every surface #791 names, measured where the user sees it."""
    from open_garden_planner.app.application import GardenPlannerApp

    colors = themed(mode, windows_dark)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda self: None)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    window.showNormal()
    window.resize(1500, 900)
    qtbot.waitExposed(window)
    qtbot.wait(50)

    # The application palette is the theme's, not Windows'.
    assert QApplication.palette().window().color().name() == colors["background"]

    # Find Plants: the count line and an unchecked filter box.
    window._sidebar_controller._on_title_click("plant_search")
    panel = window.plant_search_panel
    qtbot.waitUntil(lambda: panel.results_label.isVisible() and panel.height() > 150, timeout=5000)
    qtbot.wait(350)   # the accordion's expand animation
    count = text_contrast(panel.results_label)
    _report("Find Plants: count line", mode, windows_dark, count)
    assert count >= TEXT_CONTRAST

    panel.tree_checkbox.setChecked(False)
    qtbot.wait(30)
    box = grab_image(panel.tree_checkbox, _indicator_rect(panel.tree_checkbox))
    outline = max(contrast(box.pixelColor(x, box.height() // 2), colors["background"])
                  for x in range(box.width()))
    _report("Find Plants: unchecked check box outline", mode, windows_dark, outline)
    assert outline >= GRAPHIC_CONTRAST

    # The rulers of the real canvas.
    view = window.canvas_view
    ruler = grab_image(view.viewport(), QRect(view.RULER_SIZE + 4, 0, 500, view.RULER_SIZE - 2))
    assert background_of(ruler).name() == colors["surface"]
    assert ink_contrast(ruler) >= TEXT_CONTRAST

    # Seed Inventory: the statistics line.
    window._tab_widget.setCurrentWidget(window.seed_inventory_view)
    qtbot.wait(50)
    stats = text_contrast(window.seed_inventory_view._stats_lbl)
    _report("Seed Inventory: statistics line", mode, windows_dark, stats)
    assert stats >= TEXT_CONTRAST

    # Planting Calendar: the chart is as wide as the tab.
    window._tab_widget.setCurrentWidget(window.calendar_view)
    qtbot.wait(50)
    assert window.calendar_view._scroll.widgetResizable()

    # The toolbar's overflow button: at the window's minimum width the widest
    # toolbar has a row of its own and still does not fit.
    window._tab_widget.setCurrentIndex(0)
    window.resize(window.minimumWidth(), 700)
    qtbot.wait(150)
    overflow = [
        button for button in window.constraint_toolbar.findChildren(QToolButton)
        if button.objectName() == "qt_toolbar_ext_button" and button.isVisible()
    ]
    assert overflow, "the constraint toolbar no longer overflows at the minimum width"
    glyph = ink_contrast(grab_image(overflow[0]))
    _report("toolbar overflow button", mode, windows_dark, glyph)
    assert glyph >= GRAPHIC_CONTRAST
