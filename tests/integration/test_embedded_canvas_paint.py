"""The canvas paints its whole viewport when it is a child of a window.

In the main window the canvas's viewport sits below the toolbars. Qt paints a
child widget into the window's backing store, so the painter's device transform
carries the child's offset. ``sprite_raster.device_bounds`` answered in the
widget's own coordinates, and everything that intersects with it (the kept grid
layer, an uncached sprite, the shadow overlay) lost a strip as tall as that
offset at the bottom of the viewport. Every earlier canvas test showed a
top-level view, whose offset is zero.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest
from PyQt6.QtCore import QRect, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPaintEvent
from PyQt6.QtWidgets import QApplication, QGraphicsItem, QWidget

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.sprite_raster import device_bounds
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem
from open_garden_planner.ui.canvas.shadow_feather import paint_feather
from open_garden_planner.ui.canvas.sun_shadow_controller import SunShadowOverlayItem
from tests.canvas_host import HEADER_PX, embed_canvas, grab_viewport


class _Probe(QWidget):
    """A child widget that records what ``device_bounds`` says while it paints."""

    def __init__(self) -> None:
        super().__init__()
        self.bounds = QRectF()
        self.own = QRectF()

    def paintEvent(self, _event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        self.bounds = device_bounds(painter)
        self.own = painter.deviceTransform().mapRect(QRectF(self.rect()))
        painter.end()


def _window_with(child: QWidget, qtbot: object) -> QWidget:
    return embed_canvas(child, qtbot)


def test_a_child_widgets_bounds_are_where_its_painter_paints(qtbot: object) -> None:
    probe = _Probe()
    window = _window_with(probe, qtbot)
    window.grab()
    assert probe.own.top() >= HEADER_PX - 1, "the probe is not painted at an offset"
    grown = probe.bounds.adjusted(-1.0, -1.0, 1.0, 1.0)
    assert grown.contains(probe.own), (
        f"device_bounds says {probe.bounds}, the painter paints the widget at {probe.own}"
    )


def test_the_grid_reaches_the_bottom_of_an_embedded_canvas(qtbot: object) -> None:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    scene.set_shadows_enabled(False)
    view = CanvasView(scene)
    window = _window_with(view, qtbot)
    view.fit_in_view()
    QApplication.processEvents()

    def grab() -> QImage:
        view.viewport().repaint()
        return window.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)

    view.set_grid_visible(True)
    with_grid = grab()
    view.set_grid_visible(False)
    without = grab()

    viewport = view.viewport()
    assert viewport is not None
    origin = viewport.mapTo(window, viewport.rect().topLeft())
    plan = view.mapFromScene(scene.canvas_rect).boundingRect().translated(origin)
    plan = plan.intersected(QRect(origin, viewport.size())).adjusted(4, 4, -4, -4)
    strip = QRect(plan.left(), plan.bottom() - HEADER_PX // 2, plan.width(), HEADER_PX // 2)
    changed = sum(
        1
        for y in range(strip.top(), strip.bottom())
        for x in range(strip.left(), strip.right(), 3)
        if with_grid.pixel(x, y) != without.pixel(x, y)
    )
    assert changed > 50, (
        f"the grid changes {changed} sampled pixels in the bottom {HEADER_PX // 2} px of the "
        "plan: the embedded canvas does not paint its grid there"
    )


@pytest.mark.parametrize("kind", ["feather", "shadow-overlay", "selected-oversized-sprite"])
def test_shadow_pixels_reach_the_bottom_in_a_window(qtbot, kind):
    """Compare the bottom of a real embedded paint with the standalone control.

    The shade crosses the viewport's bottom edge; a missing strip cannot hide
    in the empty page below it. The feather case exercises its own layer path.
    """
    shade = QPainterPath()
    shade.addRect(QRectF(160, 0, 180, 350))
    windows = []

    class FeatherItem(QGraphicsItem):
        def boundingRect(self):
            return QRectF(0, 0, 600, 500)

        def paint(self, painter, option, widget=None):
            paint_feather(painter, self.boundingRect(), self.boundingRect(),
                          shade, (), QColor(0, 0, 0, 100))

    def capture(embedded):
        scene = CanvasScene(600, 500)
        scene.set_shadows_enabled(False)
        if kind == "selected-oversized-sprite":
            item = CircleItem(300, 250, 260, object_type=ObjectType.TREE)
            item._item_id = uuid.UUID(int=1)  # same stable sprite rotation in both controls
            item.setSelected(True)  # bypass Qt's pixmap cache: paint into the backing store
        else:
            item = FeatherItem() if kind == "feather" else SunShadowOverlayItem()
        if kind == "shadow-overlay":
            item.set_clip_rect(scene.canvas_rect)
            item.set_shadow_path(shade)
        scene.addItem(item)
        view = CanvasView(scene)
        view.set_grid_visible(False)
        if embedded:
            windows.append(embed_canvas(view, qtbot, size=(700, 520)))
        else:
            qtbot.addWidget(view)
            view.setFixedSize(700, 520)
            view.show()
            qtbot.waitExposed(view)
        view.set_zoom(2.0)
        view.centerOn(300, 250 if kind == "selected-oversized-sprite" else 180)
        QApplication.processEvents()
        image = grab_viewport(view).convertToFormat(QImage.Format.Format_RGBA8888)
        raw = image.constBits()
        return np.frombuffer(raw.asstring(image.sizeInBytes()), dtype=np.uint8).reshape(
            image.height(), image.bytesPerLine() // 4, 4
        )[:, :image.width(), :3].copy()

    standalone, embedded = capture(False), capture(True)
    bottom = np.abs(embedded[-100:, 80:-80].astype(int) - standalone[-100:, 80:-80])
    assert bottom.max() <= 1, f"{kind}: the embedded paint differs by {bottom.max()} levels"
    assert standalone[-100:, 80:-80].min() < 230, "the control paints no edge in this strip"
