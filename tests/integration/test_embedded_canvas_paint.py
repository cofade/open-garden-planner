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

from PyQt6.QtCore import QRect, QRectF
from PyQt6.QtGui import QImage, QPainter, QPaintEvent
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from open_garden_planner.core.sprite_raster import device_bounds
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView

HEADER_PX = 180


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
    window = QWidget()
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    header = QWidget()
    header.setFixedHeight(HEADER_PX)
    layout.addWidget(header)
    layout.addWidget(child)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.resize(700, 700)
    window.show()
    qtbot.waitExposed(window)  # type: ignore[attr-defined]
    QApplication.processEvents()
    return window


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
