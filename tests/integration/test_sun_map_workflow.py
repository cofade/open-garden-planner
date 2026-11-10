"""End to end: Hours of Sun in the real window (#794, #793).

The user's workflow through the real application: open a plan, press "Hours of
Sun", look at the map, export it, press the button again. What the change
promises is checked where the user would see it:

1. the canvas shows the key while the map is shown, and not before or after;
2. the time-of-day shadows are not painted over the map — and are still solved,
   for the 3D view;
3. the hours on the contours are the plan's own kind of label;
4. the sun-mismatch badge is drawn for the painter;
5. a PNG of the plan carries the key and no badge;
6. switching the map off, and replacing the document, takes all of it away.
"""

from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.items.garden_item import SunBadgeItem
from open_garden_planner.ui.canvas.sun_heatmap import SunMapLabelItem
from open_garden_planner.ui.canvas.sun_legend import SunMapLegendItem
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    STATE_ACTIVE,
    SunShadowOverlayItem,
)
from open_garden_planner.ui.theme import ThemeMode, apply_theme, is_dark_theme

DAY = date(2026, 6, 21)
REFERENCE = Path(__file__).parents[1] / "fixtures" / "sun_reference_berlin.ogp"


@pytest.fixture
def window(qtbot, monkeypatch):
    previous_theme = ThemeMode.DARK if is_dark_theme() else ThemeMode.LIGHT
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    win.resize(1500, 950)
    win.show()
    qtbot.waitExposed(win)
    win._load_project_file(str(REFERENCE))
    win._sim_clock.set_date(DAY)
    win._sim_clock.set_time_of_day(time(15))
    win.canvas_view.fit_in_view()
    QApplication.processEvents()
    yield win
    win._sun_heatmap.shutdown()
    apply_theme(QApplication.instance(), previous_theme)


def _press_hours_of_sun(win: GardenPlannerApp, qtbot, on: bool) -> None:
    button = win._sun_toolbar._heatmap_button
    if button.isChecked() != on:
        button.click()
    if on:
        ready = win._live_sun_map.ensure_current()
        qtbot.waitUntil(ready.done, timeout=60000)
        ready.result()
    QApplication.processEvents()


def _grab(win: GardenPlannerApp) -> np.ndarray:
    QApplication.processEvents()
    image = win.canvas_view.viewport().grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :3].astype(np.int16).copy()


def _shadow_overlay(win: GardenPlannerApp) -> SunShadowOverlayItem:
    (overlay,) = [item for item in win.canvas_scene.items() if isinstance(item, SunShadowOverlayItem)]
    return overlay


@pytest.mark.xfail(sys.platform != "win32", reason="fails on the Linux CI runner: #897", strict=False)
def test_hours_of_sun_from_the_button_to_the_export_and_back(window, qtbot, tmp_path) -> None:
    win = window
    view, scene = win.canvas_view, win.canvas_scene

    # -- before: the time-of-day shadows, no key --------------------------------
    assert win._sun_controller.state == STATE_ACTIVE
    assert _shadow_overlay(win).isVisible()
    shadows_at_three = win._sun_controller.drape_polygons()
    assert shadows_at_three
    before = _grab(win)
    assert view.sun_legend() is None and view.sun_legend_rect().isEmpty()
    assert not [item for item in scene.items() if isinstance(item, SunMapLegendItem)]

    # -- the map on ---------------------------------------------------------------
    _press_hours_of_sun(win, qtbot, True)
    assert win._sun_heatmap.heatmap_visible()
    with_map = _grab(win)

    # 1. the key, on the canvas, in the scale bar's strip
    key = view.sun_legend()
    assert key is not None and key.day == DAY
    rect = view.sun_legend_rect()
    assert not rect.isEmpty() and view.viewport().rect().contains(rect)
    # in the scale bar's strip, or one strip higher where the canvas is narrow
    # (the suite's window leaves it a third of a screen) — never on the scale bar
    assert rect.bottom() >= view.viewport().height() - 2 * view.SCALE_BAR_RESERVED_PX
    assert not QRectF(rect).intersects(view._scale_bar_rect())
    strip = (slice(rect.top(), rect.bottom()), slice(rect.left(), rect.right()))
    assert (np.abs(with_map[strip] - before[strip]).sum(axis=2) > 90).mean() > 0.2

    # 2. no time-of-day shadow over the map; solved all the same
    assert not _shadow_overlay(win).isVisible()
    assert win._sun_controller.state == STATE_ACTIVE
    assert win._sun_controller.drape_polygons() == shadows_at_three
    win._sim_clock.set_time_of_day(time(18))
    QApplication.processEvents()
    assert win._sun_controller.drape_polygons() != shadows_at_three, "the 3D drape still follows the clock"
    assert not _shadow_overlay(win).isVisible()
    later = _grab(win)
    assert np.array_equal(later, with_map), "the map is the day's total: the time of day changes nothing"

    # 3. the hours on the contours are the plan's own labels, painted above the plants
    hours = [item for item in scene.items() if isinstance(item, SunMapLabelItem)]
    assert hours
    shown = {id(label) for label, _device, _box in scene.plan_labels_shown(view.viewportTransform())}
    assert any(id(label) in shown for label in hours)

    # 4. the mismatch badge is an icon drawn for the painter
    qtbot.waitUntil(lambda: any(
        isinstance(item, SunBadgeItem) and item.isVisible() for item in scene.items()), timeout=20000)
    badge = next(item for item in scene.items() if isinstance(item, SunBadgeItem) and item.isVisible())
    assert badge._icon_name == "sun_warning"

    # 5. a PNG of the plan: the key, and no badge
    legend_item = next(item for item in scene.items() if isinstance(item, SunMapLegendItem))
    assert not legend_item.isVisible()
    png = tmp_path / "plan.png"
    win._sun_export_gate.run_gui(
        lambda: ExportService.export_to_png(scene, png, dpi=150, output_width_cm=20.0))
    assert not legend_item.isVisible() and badge.isVisible()
    picture = QImage(str(png))
    scene.removeItem(legend_item)
    bare = tmp_path / "bare.png"
    ExportService.export_to_png(scene, bare, dpi=150, output_width_cm=20.0)
    scene.addItem(legend_item)

    def rgb(image: QImage) -> np.ndarray:
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        bits = image.constBits()
        bits.setsize(image.sizeInBytes())
        rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
        return rows[:, : image.width(), :3].astype(np.int16).copy()

    key_pixels = np.abs(rgb(picture) - rgb(QImage(str(bare)))).sum(axis=2) > 60
    rows, columns = np.nonzero(key_pixels)
    assert rows.size > 300, "the exported picture has no key"
    assert rows.min() > 0.8 * picture.height() and columns.max() < 0.7 * picture.width()
    badge.setVisible(False)
    no_badge = tmp_path / "no_badge.png"
    ExportService.export_to_png(scene, no_badge, dpi=150, output_width_cm=20.0)
    badge.setVisible(True)
    assert np.array_equal(rgb(picture), rgb(QImage(str(no_badge)))), "the badge got into the picture"

    # -- the map off again -----------------------------------------------------------
    _press_hours_of_sun(win, qtbot, False)
    assert view.sun_legend() is None
    without_map = _grab(win)
    assert view.sun_legend_rect().isEmpty()
    assert (np.abs(without_map[strip] - with_map[strip]).sum(axis=2) > 90).mean() > 0.2, "the key is still painted"
    assert not [item for item in scene.items() if isinstance(item, (SunMapLegendItem, SunMapLabelItem))]
    assert _shadow_overlay(win).isVisible(), "the time-of-day shadows are back"
    assert win._sun_controller.drape_polygons()


def test_a_new_document_takes_the_key_with_the_map(window, qtbot) -> None:
    win = window
    _press_hours_of_sun(win, qtbot, True)
    assert win.canvas_view.sun_legend() is not None
    win._load_project_file(str(REFERENCE))
    QApplication.processEvents()
    assert win.canvas_view.sun_legend() is None
    assert not win._sun_toolbar._heatmap_button.isChecked()
    assert not win._sun_controller.map_shown
    assert not [item for item in win.canvas_scene.items() if isinstance(item, SunMapLegendItem)]
    qtbot.waitUntil(lambda: any(
        isinstance(item, SunShadowOverlayItem) and item.isVisible() for item in win.canvas_scene.items()),
        timeout=10000)
