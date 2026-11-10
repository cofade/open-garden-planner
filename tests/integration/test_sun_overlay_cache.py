"""The sun-shadow overlay is rasterised once per solve and zoom, then blitted (#784).

Before #784 the overlay was an uncached item: every repaint of the canvas — a
pan, a hover, another item's update — stroked its four antialiased feather pens
again (95 % of a 100 ms paint on the family-garden example). It is
``DeviceCoordinateCache`` now, like every other canvas item, and while a zoom
is under way it shows its last picture scaled instead of rasterising at every
wheel step.

These tests COUNT paints instead of timing them (§8.10.10): a count holds on any
machine under any load. The wall-clock ratio is pinned on the quiet runner by
``tests/perf/test_sun_overlay_repaint.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QGraphicsItem

from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    STATE_ACTIVE,
    SunShadowController,
    SunShadowOverlayItem,
)

BERLIN = {"latitude": 52.52, "longitude": 13.405}
SUNS = {
    "noon": datetime(2026, 6, 21, 11, 0, tzinfo=UTC),
    "evening": datetime(2026, 6, 21, 17, 30, tzinfo=UTC),
}

#: A cached overlay is painted into a transparent pixmap and that is laid over
#: the plan; an uncached one is painted onto the plan directly. The same four
#: translucent strokes and the fill, composited in two steps instead of five:
#: the two differ by the rounding of 8-bit premultiplied alpha, measured 3 at most.
CACHE_TOLERANCE = 3


def _scene() -> tuple[CanvasScene, SunShadowController]:
    scene = CanvasScene(1200.0, 900.0)
    for x, y, w, h, height in ((300, 300, 160, 90, 320.0), (640, 420, 60, 200, 180.0),
                               (820, 250, 120, 120, 250.0)):
        item = RectangleItem(x, y, w, h, object_type=ObjectType.GENERIC_RECTANGLE)
        item.metadata[METADATA_KEY] = height
        scene.addItem(item)
    for x, y in ((480, 620), (760, 640)):
        scene.addItem(CircleItem(x, y, 70, object_type=ObjectType.TREE))
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(SUNS["noon"])
    controller.set_enabled(True)
    assert controller.state == STATE_ACTIVE
    return scene, controller


def _overlay(scene: CanvasScene) -> SunShadowOverlayItem:
    (overlay,) = [item for item in scene.items() if isinstance(item, SunShadowOverlayItem)]
    return overlay


@pytest.fixture
def staged(qtbot):
    scene, controller = _scene()
    view = CanvasView(scene)
    view.resize(900, 700)
    view.show()
    qtbot.addWidget(view)
    qtbot.waitExposed(view)
    view.fit_in_view()
    QApplication.processEvents()
    view.viewport().repaint()
    return scene, controller, view


@pytest.fixture
def paints(monkeypatch):
    """How often the overlay's ``paint`` ran since the fixture was asked for."""
    calls: list[int] = []
    real = SunShadowOverlayItem.paint

    def counting(self, painter, option, widget=None):
        calls.append(1)
        real(self, painter, option, widget)

    monkeypatch.setattr(SunShadowOverlayItem, "paint", counting)
    return calls


def _pixels(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :3].astype(np.int16).copy()


class TestRasterisedOncePerSolve:
    def test_the_overlay_is_device_cached(self, staged) -> None:
        scene, _controller, _view = staged
        assert _overlay(scene).cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_a_repaint_does_not_paint_it_again(self, staged, paints) -> None:
        _scene_, _controller, view = staged
        for _ in range(6):
            view.viewport().repaint()
        assert len(paints) == 0

    def test_a_pan_does_not_paint_it_again(self, staged, paints) -> None:
        """The whole overlay is in view at fit: a pan moves its picture."""
        scene, controller, view = staged
        view.set_zoom(view.zoom_factor * 1.05)  # scroll bars need something to scroll
        view.centerOn(QPointF(600, 450))
        view.viewport().repaint()
        controller.settle_overlay()
        view.viewport().repaint()
        assert len(paints) == 2  # it is in view: the zoom step, then its rasterisation
        paints.clear()
        bar = view.horizontalScrollBar()
        for _ in range(6):
            bar.setValue(bar.value() + 3)
            view.viewport().repaint()
        assert len(paints) == 0

    def test_a_new_solve_paints_it_once(self, staged, paints) -> None:
        _scene_, controller, view = staged
        controller.set_sim_datetime(SUNS["evening"])
        for _ in range(4):
            view.viewport().repaint()
        assert len(paints) == 1

    def test_a_zoom_paints_it_once(self, staged, paints) -> None:
        _scene_, _controller, view = staged
        view.set_zoom(view.zoom_factor * 1.2)
        view.centerOn(QPointF(600, 450))
        for _ in range(4):
            view.viewport().repaint()
        assert len(paints) == 1

    def test_another_items_update_does_not_paint_it(self, staged, paints) -> None:
        scene, _controller, view = staged
        plant = next(item for item in scene.items() if isinstance(item, CircleItem))
        for _ in range(4):
            plant.update()
            view.viewport().repaint()
        assert len(paints) == 0


class TestZoomGesture:
    """A zoom invalidates the device cache at every step. The overlay answers a
    step with the picture of its last rasterisation, scaled, and rasterises for
    the new zoom once — when the steps have stopped."""

    def test_wheel_steps_do_not_rasterise(self, staged) -> None:
        scene, _controller, view = staged
        overlay = _overlay(scene)
        rasterised = overlay.exact_paints
        assert rasterised >= 1
        for _ in range(8):
            view.set_zoom(view.zoom_factor * 1.1)
            view.centerOn(QPointF(600, 450))
            view.viewport().repaint()
        assert overlay.exact_paints == rasterised

    def test_the_zoom_settles_into_one_rasterisation(self, staged, qtbot) -> None:
        scene, _controller, view = staged
        overlay = _overlay(scene)
        for _ in range(5):
            view.set_zoom(view.zoom_factor * 1.1)
            view.centerOn(QPointF(600, 450))
            view.viewport().repaint()
        rasterised = overlay.exact_paints
        # the controller's own timer, not a call from the test
        qtbot.waitUntil(lambda: overlay._pending is None, timeout=3000)
        view.viewport().repaint()
        view.viewport().repaint()
        assert overlay.exact_paints == rasterised + 1

    def test_the_picture_of_a_step_is_the_shadow_scaled(self, staged) -> None:
        """What a wheel step shows is the overlay — softer, in the same place."""
        scene, controller, view = staged
        view.set_zoom(view.zoom_factor * 1.6)
        view.centerOn(QPointF(600, 450))
        QApplication.processEvents()
        stepped = _pixels(view.viewport().grab().toImage())
        controller.settle_overlay()
        settled = _pixels(view.viewport().grab().toImage())
        _overlay(scene).setVisible(False)
        without = _pixels(view.viewport().grab().toImage())
        shadow = np.abs(settled - without).max(axis=2) > 20  # the overlay's pixels
        assert shadow.mean() > 0.05
        difference = np.abs(stepped - settled).max(axis=2)
        assert difference[shadow].mean() < 2.0  # the same tone over the shadow
        assert (difference > 30).mean() < 0.02  # edges only: a 1.6x enlarged outline

    def test_a_zoom_far_past_the_picture_is_rasterised_at_once(self, staged) -> None:
        """The kept picture stands in only while it is enlarged a little. Zoomed
        in far past it (here 6 times) it would be a blur, and there the
        rasterisation it stands in for is cheap — little of the shadow is in
        view (family garden: 6-13 ms at 447 %, against 60-130 ms at fit)."""
        scene, _controller, view = staged
        overlay = _overlay(scene)
        rasterised = overlay.exact_paints
        view.set_zoom(view.zoom_factor * 6.0)
        view.centerOn(QPointF(600, 450))
        view.viewport().repaint()
        assert overlay.exact_paints == rasterised + 1
        assert overlay._pending is None  # nothing was deferred
        # ... and a step from THERE is a small enlargement of nothing kept (the
        # overlay is too large for a picture at this zoom): rasterised as well
        view.set_zoom(view.zoom_factor * 1.1)
        view.centerOn(QPointF(600, 450))
        view.viewport().repaint()
        assert overlay.exact_paints == rasterised + 2

    def test_a_new_solve_during_a_zoom_is_rasterised_at_once(self, staged) -> None:
        """A scrub must show the sun where it is: a picture of the previous
        solve is never shown for a new one."""
        scene, controller, view = staged
        overlay = _overlay(scene)
        view.set_zoom(view.zoom_factor * 1.3)
        view.centerOn(QPointF(600, 450))
        view.viewport().repaint()
        rasterised = overlay.exact_paints
        controller.set_sim_datetime(SUNS["evening"])
        view.viewport().repaint()
        assert overlay.exact_paints == rasterised + 1

    def test_an_overlay_nobody_settles_never_defers(self, qtbot) -> None:
        scene = CanvasScene(600.0, 400.0)
        overlay = SunShadowOverlayItem()
        scene.addItem(overlay)
        path = QPainterPath()
        path.addRect(QRectF(100, 100, 200, 100))
        overlay.set_clip_rect(QRectF(0, 0, 600, 400))
        overlay.set_shadow_path(path)
        view = CanvasView(scene)
        view.resize(500, 400)
        view.show()
        qtbot.addWidget(view)
        qtbot.waitExposed(view)
        view.centerOn(QPointF(200, 150))
        QApplication.processEvents()
        view.viewport().repaint()
        before = overlay.exact_paints
        assert before >= 1
        for _ in range(3):
            view.set_zoom(view.zoom_factor * 1.2)
            view.centerOn(QPointF(200, 150))
            view.viewport().repaint()
        assert overlay.exact_paints == before + 3


class TestPixelsUnchanged:
    @pytest.mark.parametrize("sun", list(SUNS))
    @pytest.mark.parametrize("zoom", [0.6, 1.0, 3.0])
    def test_the_cached_overlay_is_the_painted_overlay(self, staged, sun: str, zoom: float) -> None:
        """The picture of the cached overlay against the picture the item's own
        ``paint`` puts on the plan directly — which is the overlay as it was
        before #784: three zooms, two sun positions."""
        scene, controller, view = staged
        controller.set_sim_datetime(SUNS[sun])
        view.set_zoom(zoom)
        view.centerOn(QPointF(600, 450))
        QApplication.processEvents()
        controller.settle_overlay()  # the zoom has stopped
        overlay = _overlay(scene)
        cached = _pixels(view.viewport().grab().toImage())
        overlay.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        direct = _pixels(view.viewport().grab().toImage())
        overlay.setVisible(False)
        without = _pixels(view.viewport().grab().toImage())
        assert np.abs(direct - without).max() > 20  # the overlay is in this picture
        difference = np.abs(cached - direct)
        assert difference.max() <= CACHE_TOLERANCE, difference.max()

    @pytest.mark.parametrize("sun", list(SUNS))
    def test_an_export_is_painted_directly(self, staged, sun: str) -> None:
        """An export disables every item cache first, so its overlay is the
        item's own paint — not one level of one pixel differs."""
        scene, controller, _view = staged
        controller.set_sim_datetime(SUNS[sun])
        overlay = _overlay(scene)

        def export() -> np.ndarray:
            image = QImage(1800, 1350, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            try:
                render_scene_region(scene, painter, QRectF(0, 0, 1800, 1350),
                                    QRectF(0, 0, 1200, 900), y_flip=True)
            finally:
                painter.end()
            return _pixels(image)

        cached_mode = export()
        assert overlay.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache  # restored
        overlay.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        assert np.array_equal(cached_mode, export())

    def test_the_drape_polygons_are_what_is_painted(self, staged) -> None:
        """The 3D ground drape lays ``drape_polygons`` on the ground; caching the
        2D picture changes nothing it reads."""
        scene, controller, _view = staged
        polygons = controller.drape_polygons()
        assert polygons
        path_polygons = _overlay(scene).path().toSubpathPolygons()
        assert len(path_polygons) == len(polygons)
