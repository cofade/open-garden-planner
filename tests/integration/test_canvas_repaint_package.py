"""Canvas repaint regressions for #847, #848 and #878."""

from __future__ import annotations

import math
from unittest.mock import patch

import numpy as np
import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core import sprite_raster
from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.item_look import adopt_pen, fill_brush
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.sprite_raster import KeptLayer
from open_garden_planner.core.tools import ToolType
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolygonItem, RectangleItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.widgets.minimap_widget import MinimapWidget
from tests.canvas_host import grab_viewport
from tests.integration.test_tool_preview_repaint import _drag_to
from tests.large_plan import show_large_plan


def test_partial_paint_keeps_the_new_grid_picture(qtbot):
    layer = KeptLayer()
    image = QImage(200, 200, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    whole = QRectF(0, 0, 200, 200)
    calls = []

    def draw(p, rect):
        calls.append(rect)
        p.fillRect(rect, QColor("red"))

    try:
        layer.paint(painter, whole, whole, 1, draw)
        for _ in range(5):
            layer.paint(painter, whole, QRectF(50, 50, 20, 20), 2, draw)
    finally:
        painter.end()
    assert layer.builds == 2
    assert len(calls) == 2


def test_fractional_display_pan_reuses_each_pixel_phase(qtbot):
    layer = KeptLayer()
    image = QImage(200, 200, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    whole = QRectF(-1000, -1000, 2000, 2000)
    painter = QPainter(image)
    try:
        for step in range(8):
            painter.setTransform(QTransform.fromTranslate(step * 1.5, 0))
            layer.paint(painter, whole, whole, 1, lambda p, rect: p.fillRect(rect, QColor("red")))
    finally:
        painter.end()
    assert layer.builds <= 3, "150% display scaling must not rebuild on every odd-pixel pan"


def test_grid_phases_invalidate_and_stay_in_one_memory_budget(qtbot, monkeypatch):
    monkeypatch.setattr(sprite_raster, "MAX_LAYER_PIXELS", 50000)
    layer = KeptLayer()
    image = QImage(180, 180, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    whole = QRectF(-1000, -1000, 2000, 2000)
    painter = QPainter(image)

    def draw(p, rect):
        p.fillRect(rect, QColor("red"))

    try:
        for step in range(8):
            painter.setTransform(QTransform.fromTranslate(step * 1.25, 0))
            layer.paint(painter, whole, whole, 1, draw)
            assert 0 < layer.bytes_used <= 4 * 50000
        assert layer.builds > 4, "the reduced budget must evict earlier phases"
        before = layer.builds
        layer.paint(painter, whole, whole, 2, draw)
        assert layer.builds == before + 1
        assert not layer._phases, "a new picture must discard all old phases"
        painter.scale(1.1, 1.1)
        layer.paint(painter, whole, whole, 2, draw)
        assert layer.builds == before + 2
        assert not layer._phases, "a new scale must discard all old phases"
    finally:
        painter.end()
    layer.clear()
    assert layer.bytes_used == 0 and not layer._phases


def _pixels(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(image.constBits().asstring(image.sizeInBytes()), dtype=np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4
    )[:, :image.width()].copy()


@pytest.mark.parametrize("ratio", [1.25, 1.5])
def test_kept_pan_phases_have_the_direct_painters_pixels(qtbot, ratio):
    layer = KeptLayer()
    whole = QRectF(-1000, -1000, 2000, 2000)

    def draw(p, rect):
        p.fillRect(rect, QColor("white"))
        p.setPen(QPen(QColor("red"), 0))
        for x in range(-1000, 1000, 20):
            p.drawLine(QPointF(x, -1000), QPointF(x, 1000))
        p.fillRect(QRectF(30, 30, 50, 50), QColor("blue"))

    for step in range(12):
        pictures = []
        for kept in (True, False):
            image = QImage(180, 180, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.translate(step * ratio, 0)
            if kept:
                layer.paint(painter, whole, whole, 1, draw)
            else:
                draw(painter, whole)
            painter.end()
            pictures.append(_pixels(image))
        assert np.array_equal(*pictures), (ratio, step)
    assert layer.builds <= 5


def test_selected_and_exported_long_line_keep_the_stored_width(qtbot):
    item = PolylineItem([QPointF(100 + i, 200) for i in range(300)])
    adopt_pen(item, QPen(QColor("magenta"), 20))
    scene = CanvasScene(600, 500)
    scene.set_shadows_enabled(False)
    scene.addItem(item)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(650, 550)
    view.show()
    view.set_zoom(1)
    view.centerOn(300, 250)
    QApplication.processEvents()

    def ink(image):
        px = _pixels(image)
        return np.count_nonzero((px[:, :, 0] > 220) & (px[:, :, 1] < 200) & (px[:, :, 2] > 220))

    hairline = ink(grab_viewport(view))
    item.setSelected(True)
    selected = ink(grab_viewport(view))
    image = QImage(600, 500, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    render_scene_region(scene, painter, QRectF(image.rect()), scene.canvas_rect)
    painter.end()
    assert hairline > 0
    assert selected > hairline * 8
    assert ink(image) > hairline * 8
    assert item.pen().widthF() == 20
    assert len(item.points) == 300


def test_rectangle_preview_does_not_rebuild_the_snap_index(qtbot):
    view, scene, items = show_large_plan(qtbot, count=100)
    view.set_active_tool(ToolType.RECTANGLE)
    viewport = view.viewport()
    QTest.mouseMove(viewport, QPoint(400, 400))
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=QPoint(400, 400))
    QApplication.processEvents()
    view._ensure_snap_index()
    with patch.object(view._point_snapper, "update_scene", wraps=view._point_snapper.update_scene) as build:
        for step in range(5):
            _drag_to(view, QPoint(410 + step * 4, 410))
        assert build.call_count == 0
        items[0].moveBy(100, 0)
        view._ensure_snap_index()
        assert build.call_count == 1, "a real edit must rebuild before the next query"
    view.active_tool.cancel()


def test_minimap_does_not_reset_body_caches(qtbot):
    class CountedRectangle(RectangleItem):
        paints = 0

        def paint(self, *args):
            self.paints += 1
            return super().paint(*args)

    scene = CanvasScene(1000, 800)
    item = CountedRectangle(200, 200, 100, 100)
    scene.addItem(item)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(700, 500)
    view.show()
    view.fit_in_view()
    QApplication.processEvents()
    minimap = MinimapWidget(view, scene)
    minimap._update_timer.stop()
    view.viewport().repaint()
    with patch.object(item, "setCacheMode", wraps=item.setCacheMode) as modes:
        minimap._do_update()
        assert modes.call_count == 0
    paints = item.paints
    view.viewport().repaint()
    assert item.paints == paints, "the minimap discarded the body's viewport cache"


def test_long_polygon_keeps_its_filled_minimap_picture(qtbot):
    scene = CanvasScene(1000, 800)
    item = PolygonItem(
        [QPointF(500 + 200 * math.cos(i * math.tau / 300),
                 400 + 200 * math.sin(i * math.tau / 300)) for i in range(300)],
        object_type=ObjectType.LAWN, fill_pattern=FillPattern.SOLID,
    )
    item.fill_color = QColor("magenta")
    item.setBrush(fill_brush(item, item.fill_color))
    scene.addItem(item)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(700, 500)
    view.show()
    view.fit_in_view()
    QApplication.processEvents()
    minimap = MinimapWidget(view, scene)
    minimap._update_timer.stop()
    minimap._do_update()
    thumbnail = minimap._thumbnail.toImage()
    assert thumbnail.pixelColor(thumbnail.width() // 2, thumbnail.height() // 2) == QColor("magenta")


@pytest.mark.parametrize("count", [256, 257, 16000])
def test_long_unselected_line_uses_a_cosmetic_outline(qtbot, count):
    item = PolylineItem([QPointF(i * 300 / count, (i % 2) * 300) for i in range(count)])
    pen = QPen(QColor("magenta"), 20)
    adopt_pen(item, pen)
    item.shadows_enabled = False
    scene = CanvasScene(600, 600)
    scene.addItem(item)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(600, 600)
    view.show()
    view.fit_in_view()
    QApplication.processEvents()
    # Record the real cached viewport paint, including Qt's null widget argument.
    strokes = []
    real = QPainter.drawPath

    def stroke(painter, path):
        strokes.append(QPen(painter.pen()))
        return real(painter, path)

    with patch.object(QPainter, "drawPath", stroke):
        item.update()
        view.viewport().repaint()
    assert any(p.isCosmetic() and p.widthF() == 1 for p in strokes) == (count > 256)
    assert item.points == [QPointF(i * 300 / count, (i % 2) * 300) for i in range(count)]


def test_rectangle_tool_hover_and_drag_do_not_walk_whole_plan(qtbot, monkeypatch) -> None:
    """#847/#919 counting gate: RectangleTool hover and drag on 853 objects
    must not trigger whole-plan ``boundingRect`` walks or full-viewport snap repaints.
    """
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QMouseEvent

    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    view, _scene, _items = show_large_plan(qtbot)
    view.set_snap_enabled(True)
    view.set_grid_visible(False)
    view.set_active_tool(ToolType.RECTANGLE)
    view._ensure_snap_index()
    QApplication.processEvents()

    bounding_calls = 0
    real_rect = CircleItem.boundingRect

    def counted_rect(self: CircleItem) -> QRectF:
        nonlocal bounding_calls
        bounding_calls += 1
        return real_rect(self)

    monkeypatch.setattr(CircleItem, "boundingRect", counted_rect)

    # Hover moves
    moves = 10
    for step in range(moves):
        pt = QPointF(300.0 + step * 10.0, 300.0 + step * 5.0)
        ev = QMouseEvent(
            QEvent.Type.MouseMove,
            pt,
            pt,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(view.viewport(), ev)
        QApplication.processEvents()

    hover_calls = bounding_calls
    assert hover_calls / moves <= 40, (
        f"RectangleTool hover called CircleItem.boundingRect {hover_calls / moves:.1f}x/move"
    )

    # Drag moves
    bounding_calls = 0
    press_pt = QPointF(300.0, 300.0)
    QApplication.sendEvent(
        view.viewport(),
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            press_pt,
            press_pt,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.processEvents()
    for step in range(moves):
        pt = QPointF(315.0 + step * 15.0, 310.0 + step * 10.0)
        ev = QMouseEvent(
            QEvent.Type.MouseMove,
            pt,
            pt,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(view.viewport(), ev)
        QApplication.processEvents()

    drag_calls = bounding_calls
    # Before #919/#847 each move walked ~1,600 CircleItem.boundingRect calls;
    # with BSP indexing + dirty-rect snap updates, only items overlapping the
    # growing preview rect and dynamic input overlay are visited (~76/move).
    assert drag_calls / moves <= 150, (
        f"RectangleTool drag called CircleItem.boundingRect {drag_calls / moves:.1f}x/move"
    )
    view.active_tool.cancel()


def test_circle_spacing_ring_and_bounding_rect_caches(qtbot, monkeypatch) -> None:
    """#847/#919: CircleItem caches spacing conflict geometry and boundingRect,
    and invalidates cleanly when geometry, state, or plan date changes.
    """
    from datetime import date

    from open_garden_planner.ui.canvas.items import circle_item as circle_mod
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    scene = CanvasScene(1000, 800)
    scene.set_shadows_enabled(False)
    plant = CircleItem(
        400.0,
        400.0,
        25.0,
        object_type=ObjectType.PERENNIAL,
        name="P1",
        metadata={"plant_species": {"common_name": "P1", "max_spread_cm": 90.0}},
    )
    plant.spacing_radius_cm = 45.0
    plant.set_spacing_overlap("overlap", [(440.0, 400.0, 45.0)])
    scene.addItem(plant)

    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(600, 500)
    view.show()
    view.fit_in_view()
    QApplication.processEvents()

    arc_calls = 0
    real_arcs = circle_mod.spacing_conflict_arcs

    def counted_arcs(*args, **kwargs):
        nonlocal arc_calls
        arc_calls += 1
        return real_arcs(*args, **kwargs)

    monkeypatch.setattr(circle_mod, "spacing_conflict_arcs", counted_arcs)

    # First paint already cached the spacing ring; repeated repaints hit cache.
    for _ in range(5):
        plant.update()
        view.viewport().repaint()
    assert arc_calls == 0, f"spacing_conflict_arcs recomputed {arc_calls}x without state change"

    # Position change invalidates the cached spacing ring once.
    plant.setPos(20.0, 0.0)
    plant.update()
    view.viewport().repaint()
    assert arc_calls == 1

    # Repeated repaints at the new position hit the cache again.
    for _ in range(3):
        plant.update()
        view.viewport().repaint()
    assert arc_calls == 1

    # Bounding rect cache invalidates across geometry & diagnostic state changes.
    base_rect = plant.boundingRect()
    assert plant.boundingRect() == base_rect

    plant.set_antagonist_warning(True)
    with_warn = plant.boundingRect()
    assert with_warn != base_rect

    plant.set_companion_highlight("beneficial")
    with_highlight = plant.boundingRect()
    assert with_highlight != with_warn

    plant.shadows_enabled = True
    with_shadow = plant.boundingRect()
    assert with_shadow != with_highlight

    plant.spacing_radius_cm = 120.0
    with_big_spacing = plant.boundingRect()
    assert with_big_spacing.width() > with_shadow.width()

    plant.setRect(0.0, 0.0, 100.0, 100.0)
    assert plant.boundingRect() != with_big_spacing

    pen = plant.pen()
    pen.setWidthF(12.0)
    plant.setPen(pen)
    with_thick_pen = plant.boundingRect()
    assert with_thick_pen.width() > plant.rect().width()

    # Plan date change invalidates via prepareGeometryChange in refresh_timeline.
    plant.metadata["plant_instance"] = {
        "planting_date": "2026-01-01",
        "current_spread_cm": 10.0,
    }
    plant.prepareGeometryChange()
    scene._painted_plan_date = date(2026, 6, 1)
    r1 = plant.boundingRect()
    assert r1 is not None
