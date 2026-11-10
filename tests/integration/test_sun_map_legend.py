"""The hours-of-sun map carries a key (#794).

Until #794 the map had no key ("the labels are the key", FR-SUN-05): a number on
a contour says what the line is, not what a colour is.

What is pinned here, on a real map computed by the real worker:

* the canvas shows a colour bar with the hours on it while a map is shown — in
  the scale bar's strip, clear of the scale bar and the minimap, readable in
  both themes on every ground, in the map's own tints;
* a picture of the plan (PNG, the Agent API's render, SVG) carries the key too,
  sized with the picture's text; the canvas does not show that one, nor does
  the minimap.

The hour labels are measured in ``tests/integration/test_sun_map_labels.py``.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from PyQt6.QtCore import QEvent, QObject, QPointF, QRect, QRectF
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.heatmap_render import sun_legend
from open_garden_planner.core.legibility import MIN_TEXT_CONTRAST
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.sun_heatmap import (
    SunHeatmapController,
    SunHeatmapOverlayItem,
    SunMapLabelItem,
    build_heatmap_image,
)
from open_garden_planner.ui.canvas.sun_legend import (
    SunLegendKey,
    SunMapLegendItem,
    hour_text,
    legend_font,
    legend_title,
    sun_legend_size,
)
from open_garden_planner.ui.theme import ThemeColors
from open_garden_planner.ui.widgets.minimap_widget import MinimapWidget
from tests.integration.test_canvas_legibility import (
    BACKGROUNDS,
    _grab,
    _label_contrast,
    _solid,
)
from tests.integration.test_sun_map_labels import export, garden, pixels

BERLIN = {"latitude": 52.52, "longitude": 13.405}
SUMMER = date(2026, 6, 21)
KEY = SunLegendKey(sun_legend(16.5 * 60), SUMMER)   # type: ignore[arg-type]


@pytest.fixture
def mapped(qtbot):
    """The garden in a view, with a finished map and the application's wiring."""
    scene = garden()
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1150, 820)
    view.show()
    qtbot.waitExposed(view)
    view.fit_in_view()
    controller = SunHeatmapController(scene, lambda: BERLIN)
    controller.computed.connect(lambda _shown: view.set_sun_legend(controller.legend_key()))
    with qtbot.waitSignal(controller.finished, timeout=120000) as blocker:
        assert controller.run_for_day(SUMMER)
    assert blocker.args == [True]
    QApplication.processEvents()
    yield view, scene, controller
    controller.shutdown()


# --------------------------------------------------------------------------
# The key on the canvas
# --------------------------------------------------------------------------


def test_the_canvas_shows_the_key_while_a_map_is_shown(mapped) -> None:
    view, _scene, controller = mapped
    with_key = _grab(view)
    rect = view.sun_legend_rect()
    assert not rect.isEmpty()
    viewport = view.viewport().rect()
    assert viewport.contains(rect)
    # bottom left, on the scale bar's line
    assert rect.left() < 60
    assert rect.bottom() <= viewport.height() - CanvasView._SCALE_BAR_MARGIN + 1
    assert rect.bottom() >= viewport.height() - CanvasView.SCALE_BAR_RESERVED_PX

    controller.clear()
    QApplication.processEvents()
    assert view.sun_legend() is None
    without = _grab(view)
    assert view.sun_legend_rect().isEmpty()
    # the strip changed where the key was ...
    was = pixels(with_key)[rect.top(): rect.bottom(), rect.left(): rect.right()]
    now = pixels(without)[rect.top(): rect.bottom(), rect.left(): rect.right()]
    assert (np.abs(was - now).sum(axis=2) > 90).mean() > 0.2
    # ... and nothing of a key is left
    view.set_sun_legend(None)
    assert np.array_equal(pixels(_grab(view)), pixels(without))


def test_the_key_names_the_day_and_the_hours_in_the_applications_language(mapped) -> None:
    view, _scene, controller = mapped
    key = view.sun_legend()
    assert key is not None and key == controller.legend_key()
    assert key.day == SUMMER
    assert legend_title(key.day) == "Hours of sun · 2026-06-21"
    assert hour_text(4) == controller.tr("{n} h").format(n=4) == "4 h"
    # the day's daylight in Berlin on 21 June: sixteen and three quarter hours
    assert [tick.hour for tick in key.legend.ticks] == list(range(17))


@pytest.mark.parametrize("zoom", [0.25, 1.0, 2.0, 4.0])
def test_the_key_stays_put_whatever_the_zoom_and_pan(mapped, zoom: float) -> None:
    view, _scene, _controller = mapped
    _grab(view)
    at_fit = view.sun_legend_rect()
    view.set_zoom(zoom)
    view.centerOn(QPointF(1700.0, 1100.0))
    _grab(view)
    rect = view.sun_legend_rect()
    assert not rect.isEmpty()
    viewport = view.viewport().rect()
    assert rect.left() == at_fit.left()
    assert viewport.height() - rect.bottom() == view.viewport().height() - rect.bottom()
    assert rect.bottom() <= viewport.height() - CanvasView._SCALE_BAR_MARGIN + 1


def test_a_pan_paints_the_key_again_where_it_stands(mapped) -> None:
    """Qt scrolls the viewport's pixels and repaints only the strip that came
    into view. The key stands on the viewport: its own rectangle is repainted."""
    view, _scene, _controller = mapped
    view.set_zoom(2.0)
    view.centerOn(QPointF(1200.0, 800.0))
    _grab(view)
    rect = view.sun_legend_rect()

    class Spy(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.regions = []

        def eventFilter(self, _obj, event) -> bool:
            if event.type() == QEvent.Type.Paint:
                self.regions.append(event.region())
            return False

    spy = Spy()
    view.viewport().installEventFilter(spy)
    bar = view.horizontalScrollBar()
    bar.setValue(bar.value() + 37)
    QApplication.processEvents()
    view.viewport().removeEventFilter(spy)
    assert spy.regions, "the pan painted nothing"
    painted = spy.regions[0]
    for region in spy.regions[1:]:
        painted = painted.united(region)
    assert painted.contains(rect), "the key's own rectangle was not painted again"


@pytest.mark.parametrize("width", [1150, 760, 560])
def test_the_key_keeps_clear_of_the_scale_bar_and_the_minimap(mapped, width: int) -> None:
    view, scene, _controller = mapped
    minimap = MinimapWidget(view, scene)
    view.resize(width, 620)
    view.set_zoom(2.0)                       # zoomed in: the minimap shows
    view.centerOn(QPointF(1200.0, 800.0))
    QApplication.processEvents()
    minimap.set_visible(True)
    QApplication.processEvents()
    _grab(view)
    rect = QRectF(view.sun_legend_rect())
    assert not rect.isEmpty(), width
    assert not rect.intersects(view._scale_bar_rect())
    if minimap.isVisible():
        corner = view.viewport().mapFrom(view, minimap.geometry().topLeft())
        assert not rect.intersects(QRectF(QRect(corner, minimap.size())))
    assert view.viewport().rect().contains(rect.toAlignedRect())


def test_a_viewport_with_no_room_shows_no_key_rather_than_one_on_the_scale_bar(mapped) -> None:
    view, _scene, _controller = mapped
    view.resize(240, 300)
    view.set_zoom(0.1)
    QApplication.processEvents()
    _grab(view)
    rect = QRectF(view.sun_legend_rect())
    assert rect.isEmpty() or not rect.intersects(view._scale_bar_rect())


def test_the_key_is_smaller_without_its_title_and_then_it_fits(qtbot) -> None:
    font = legend_font()
    full = sun_legend_size(KEY, font)
    bare = sun_legend_size(KEY, font, with_title=False)
    assert bare.width() < full.width() - 80
    assert bare.height() <= full.height()
    # both fit the strip the overlay widgets keep clear for the scale bar
    room = CanvasView.SCALE_BAR_RESERVED_PX - CanvasView._SCALE_BAR_MARGIN
    assert full.height() <= room + 4, full.height()


@pytest.mark.parametrize("background", list(BACKGROUNDS))
@pytest.mark.parametrize("theme", ["LIGHT", "DARK"])
def test_the_key_reads_on_every_ground_in_both_themes(qtbot, background: str, theme: str) -> None:
    scene = CanvasScene(3000, 2000)
    scene.set_shadows_enabled(False)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    qtbot.waitExposed(view)
    view.apply_theme_colors(getattr(ThemeColors, theme))
    _solid(scene, BACKGROUNDS[background])
    view.set_sun_legend(KEY)
    with_key = _grab(view)
    rect = view.sun_legend_rect()
    assert not rect.isEmpty()
    view.set_sun_legend(None)
    without = _grab(view)
    ink = QColor(view._scale_bar_fg)
    # the title, left of the bar
    title = QRect(rect.left(), rect.top(), 150, rect.height())
    ratio = _label_contrast(with_key, without, ink, title)
    assert ratio >= MIN_TEXT_CONTRAST, f"key title on {background}, {theme}: {ratio:.2f}:1"
    # the hours, above the bar
    hours = QRect(rect.right() - 250, rect.top(), 250, 16)
    ratio = _label_contrast(with_key, without, ink, hours)
    assert ratio >= MIN_TEXT_CONTRAST, f"key hours on {background}, {theme}: {ratio:.2f}:1"


def test_the_bar_has_the_maps_own_tints_at_the_hours_it_names(mapped) -> None:
    """Pixels, not tables: the bar under the mark of ``h`` hours shows what the
    map paints for ``h`` hours on the bare plan."""
    view, scene, controller = mapped
    key = view.sun_legend()
    assert key is not None
    picture = _grab(view)
    rect = view.sun_legend_rect()
    rows = pixels(picture)
    # the bar: the lowest stretch of the key, right of the title
    bar_row = rect.bottom() - 6
    ground = scene.CANVAS_COLOR
    font = legend_font()
    from open_garden_planner.ui.canvas.sun_legend import _layout

    layout = _layout(key, font, with_title=True)
    bar_left = rect.left() + layout.bar.left()
    for hours in (1, 3, 7, 11, 15):
        minutes = hours * 60.0 + 30.0        # between two marks: no tick line there
        map_pixel = build_heatmap_image(np.array([[minutes]]), key.legend.daylight_minutes).pixelColor(0, 0)
        assert (map_pixel.red(), map_pixel.green(), map_pixel.blue(), map_pixel.alpha()) == key.legend.color_at(minutes)
        share = map_pixel.alphaF()
        wanted = [
            map_pixel.red() * share + ground.red() * (1 - share),
            map_pixel.green() * share + ground.green() * (1 - share),
            map_pixel.blue() * share + ground.blue() * (1 - share),
        ]
        x = round(bar_left + minutes / key.legend.daylight_minutes * layout.bar.width())
        got = rows[bar_row, x]
        assert np.abs(got - np.array(wanted)).max() <= 8, (hours, got.tolist(), wanted)
    # ... and it runs from the map's darkest tint to its lightest
    left = rows[bar_row, round(bar_left + 3)].sum()
    right = rows[bar_row, round(bar_left + layout.bar.width() - 3)].sum()
    assert left < right - 150
    assert controller.heatmap_visible()


# --------------------------------------------------------------------------
# The key in a picture of the plan
# --------------------------------------------------------------------------


def _legend_item(scene: CanvasScene) -> SunMapLegendItem:
    (item,) = [item for item in scene.items() if isinstance(item, SunMapLegendItem)]
    return item


def test_a_picture_of_the_plan_carries_the_key(mapped) -> None:
    _view, scene, controller = mapped
    item = _legend_item(scene)
    assert item.legend_key() == controller.legend_key()
    assert not item.isVisible(), "on the canvas the view draws the key, not the scene"
    with_key = export(scene)
    assert not item.isVisible(), "the export left the key switched on"

    # the same picture with the key taken out of the scene
    scene.removeItem(item)
    without = export(scene)
    scene.addItem(item)
    changed = np.abs(pixels(with_key) - pixels(without)).sum(axis=2) > 60
    rows, columns = np.nonzero(changed)
    assert rows.size > 400, "no key in the picture"
    height, width = changed.shape
    # in the plan's south-west corner, inside the picture
    assert columns.min() >= 4 and columns.max() < 0.6 * width
    assert rows.min() > 0.85 * height and rows.max() <= height - 4
    # and it reads there
    box = QRect(int(columns.min()), int(rows.min()), int(np.ptp(columns)) + 1, int(np.ptp(rows)) + 1)
    assert _label_contrast(with_key, without, item.brush().color(), box) >= MIN_TEXT_CONTRAST


def test_the_key_in_a_picture_grows_with_the_pictures_text(mapped) -> None:
    """An export gives constant-size text the size its output needs (PF-CAN-08);
    the key is found the same way and all its measures follow its font."""
    _view, scene, _controller = mapped
    item = _legend_item(scene)

    def key_height(point_size: int) -> int:
        with_key = export(scene, 2400, point_size)
        scene.removeItem(item)
        without = export(scene, 2400, point_size)
        scene.addItem(item)
        rows, _columns = np.nonzero(np.abs(pixels(with_key) - pixels(without)).sum(axis=2) > 60)
        return int(np.ptp(rows)) + 1

    small, large = key_height(10), key_height(20)
    assert large == pytest.approx(2 * small, rel=0.15)
    assert item.font().pointSize() == legend_font().pointSize(), "the export left its font on the key"


def test_the_canvas_never_shows_the_pictures_key(mapped) -> None:
    """One key on the canvas: the view's. The scene's is for pictures only."""
    view, scene, _controller = mapped
    item = _legend_item(scene)
    view.set_zoom(1.0)
    view.centerOn(QPointF(200.0, 100.0))     # the plan's south-west corner, where the item stands
    shown = pixels(_grab(view))
    scene.removeItem(item)
    assert np.array_equal(shown, pixels(_grab(view)))


def test_every_export_path_shows_the_key_through_the_one_seam(mapped) -> None:
    _view, scene, _controller = mapped
    item = _legend_item(scene)
    hidden, selected = ExportService._hide_overlay_items(scene)
    try:
        assert item.isVisible()
    finally:
        ExportService._restore_overlay_items(hidden, selected)
    assert not item.isVisible()
    # a second, nested use of the seam (the PDF report renders inside one) leaves it to the outer
    outer, outer_selected = ExportService._hide_overlay_items(scene)
    inner, inner_selected = ExportService._hide_overlay_items(scene)
    ExportService._restore_overlay_items(inner, inner_selected)
    assert item.isVisible()
    ExportService._restore_overlay_items(outer, outer_selected)
    assert not item.isVisible()


def test_the_svg_and_the_png_export_carry_the_key(mapped, tmp_path) -> None:
    _view, scene, _controller = mapped
    png = tmp_path / "plan.png"
    ExportService.export_to_png(scene, png, dpi=150, output_width_cm=20.0)
    picture = QImage(str(png))
    item = _legend_item(scene)
    scene.removeItem(item)
    bare = tmp_path / "bare.png"
    ExportService.export_to_png(scene, bare, dpi=150, output_width_cm=20.0)
    scene.addItem(item)
    changed = np.abs(pixels(picture) - pixels(QImage(str(bare)))).sum(axis=2) > 60
    assert changed.sum() > 400
    rows, _columns = np.nonzero(changed)
    assert rows.min() > 0.8 * changed.shape[0]

    svg = tmp_path / "plan.svg"
    ExportService.export_to_svg(scene, svg)
    text = svg.read_text(encoding="utf-8")
    scene.removeItem(item)
    bare_svg = tmp_path / "bare.svg"
    ExportService.export_to_svg(scene, bare_svg)
    scene.addItem(item)
    assert len(text) > len(bare_svg.read_text(encoding="utf-8")) + 2000
    assert not item.isVisible()


def test_the_minimap_shows_no_key(mapped) -> None:
    view, scene, _controller = mapped
    minimap = MinimapWidget(view, scene)
    minimap.set_visible(True)
    minimap._do_update()
    first = pixels(minimap._thumbnail.toImage())
    scene.removeItem(_legend_item(scene))
    minimap._do_update()
    assert np.array_equal(first, pixels(minimap._thumbnail.toImage()))


def test_no_label_of_the_plan_touches_the_key_on_the_canvas(mapped) -> None:
    """An hour's label half under the key reads as one of the key's numbers:
    the key takes its room in the label pass (§8.9.15)."""
    view, scene, controller = mapped
    _grab(view)
    rect = QRectF(view.sun_legend_rect())
    # a label right where the key lies
    under = SunMapLabelItem("6 h")
    under.setPos(view.mapToScene(rect.center().toPoint()))
    scene.addItem(under)
    _grab(view)
    blocked = scene.label_blockers(view.viewport())
    assert [QRectF(one) for one in blocked] == [rect]
    shown = scene.plan_labels_shown(view.viewportTransform(), blocked)
    assert under not in [label for label, _device, _box in shown]
    for _label, _device, box in shown:
        assert not box.intersects(rect)
    assert shown, "the other labels are still there"

    # no key, no blocker: the label has its room back, and is painted
    with_key = pixels(_grab(view))
    controller.computed.disconnect()
    view.set_sun_legend(None)
    _grab(view)
    assert scene.label_blockers(view.viewport()) == ()
    without_key = pixels(_grab(view))
    assert under in [label for label, _d, _b in scene.plan_labels_shown(view.viewportTransform())]
    box = under.deviceTransform(view.viewportTransform()).mapRect(under.text_rect()).toAlignedRect()
    patch = (slice(box.top(), box.bottom()), slice(box.left(), box.right()))
    assert (without_key[patch].sum(axis=2) < 200).sum() >= 12, "the label is not painted"
    assert with_key.shape == without_key.shape


def test_no_label_of_the_plan_touches_the_key_in_a_picture(mapped) -> None:
    _view, scene, _controller = mapped
    item = _legend_item(scene)
    # a label on the plan's south-west corner, where a picture has its key
    under = SunMapLabelItem("6 h")
    under.setPos(160.0, 60.0)
    scene.addItem(under)
    with_label = pixels(export(scene))
    under.setVisible(False)
    assert np.array_equal(with_label, pixels(export(scene))), "the label was painted under the key"
    # without the key the label is in the picture
    under.setVisible(True)
    scene.removeItem(item)
    lone = pixels(export(scene))
    under.setVisible(False)
    assert (np.abs(lone - pixels(export(scene))).sum(axis=2) > 90).sum() > 30
    scene.addItem(item)


def test_a_cleared_map_takes_its_key_out_of_the_scene(mapped) -> None:
    _view, scene, controller = mapped
    controller.clear()
    assert not [item for item in scene.items() if isinstance(item, SunMapLegendItem)]
    assert controller.legend_key() is None
    assert not [item for item in scene.items() if isinstance(item, SunHeatmapOverlayItem) and item.isVisible()]


def test_the_key_is_never_saved(mapped, tmp_path) -> None:
    from open_garden_planner.core import ProjectManager

    _view, scene, _controller = mapped
    path = tmp_path / "plan.ogp"
    ProjectManager().save(scene, path)
    fresh = CanvasScene()
    ProjectManager().load(fresh, path)
    assert not [item for item in fresh.items() if isinstance(item, SunMapLegendItem)]
    assert len([item for item in fresh.items() if hasattr(item, "object_type")]) == 9
