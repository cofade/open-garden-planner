"""Canvas repaint regressions for #847, #848 and #878."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.item_look import adopt_pen
from open_garden_planner.core.sprite_raster import KeptLayer
from open_garden_planner.core.tools import ToolType
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
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
