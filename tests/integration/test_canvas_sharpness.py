"""End-to-end: the plan canvas is sharp at every zoom and cheap to pan (#785, #784).

A real ``CanvasScene`` in a real ``CanvasView``: zoom in and the plant, the
furniture and the textured fill carry detail the 1-px-per-cm bitmap never had;
export at 300 dpi or render for the Agent API and each is rasterised for that
painter; pan and nothing is painted again.

How sharpness is measured: the item's interior at zoom Z against the SAME
interior at 100 % upscaled Z times (smooth) — which is, pixel for pixel, what
the canvas showed at zoom Z before #785. The ratio of their gradient energies
is about 1 for the defect and 1.7-24 for the fix (measured per kind below). The
interior is taken well inside the outline, so a crisp vector edge or a drop
shadow cannot pass for a sharp sprite.

A rotated item reads higher on both sides of the fix, because its 100 % picture
is already resampled once (the reference is softer than the defect was), so the
bar is set per rotation. Rotation is a parameter because a defect proportional
to rotation is zero at rotation 0.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPixmapCache
from PyQt6.QtWidgets import QApplication, QGraphicsItem

from open_garden_planner.agent_api.render import render_canvas_image
from open_garden_planner.core import sprite_raster
from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.item_cache import ITEM_CACHE_BUDGET_KB
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem

CANVAS_W, CANVAS_H = 1200.0, 900.0

# Each kind: how to build it centred on (600, 450), half the side of the square
# of its interior that is measured (cm), and the least gain in gradient energy
# over the upscaled 1-px-per-cm picture, unrotated and rotated 30 degrees.
#
# Measured on master (53b48405) / with the fix, lowest of 400 %, 1000 % and the
# 300-dpi export:
#   plant circle         1.04 / 4.31     rotated 1.83 / 7.33
#   furniture rectangle  1.19 / 3.23     rotated 1.39 / 4.45
#   textured polygon     1.10 / 1.67     rotated 1.55 / 2.37
# (a fill tile has two texture pixels per cm, a sprite as many as the zoom asks for)
ItemFactory = Callable[[], QGraphicsItem]


def _plant() -> QGraphicsItem:
    return CircleItem(600, 450, 40, object_type=ObjectType.TREE)


def _furniture() -> QGraphicsItem:
    return RectangleItem(510, 410, 180, 80, object_type=ObjectType.BENCH)


def _textured_polygon() -> QGraphicsItem:
    points = [QPointF(500, 370), QPointF(700, 380), QPointF(710, 530), QPointF(490, 520)]
    return PolygonItem(points, object_type=ObjectType.GARDEN_BED, fill_pattern=FillPattern.SOIL)


KINDS: dict[str, tuple[ItemFactory, float, dict[float, float]]] = {
    "plant-circle": (_plant, 16.0, {0.0: 2.5, 30.0: 2.5}),
    "furniture-rectangle": (_furniture, 16.0, {0.0: 2.2, 30.0: 2.5}),
    "textured-polygon": (_textured_polygon, 30.0, {0.0: 1.4, 30.0: 1.95}),
}


def _pixels(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, : image.width(), :3].astype(np.float64).copy()


def _gradient_energy(pixels: np.ndarray) -> float:
    lum = pixels @ np.array([0.299, 0.587, 0.114])
    return float((np.diff(lum, axis=1) ** 2).mean() + (np.diff(lum, axis=0) ** 2).mean())


def _upscaled(image: QImage, factor: float) -> np.ndarray:
    """``image`` shown ``factor`` times larger, smoothly — the canvas before #785."""
    return _pixels(
        image.scaled(
            round(image.width() * factor),
            round(image.height() * factor),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


def _build(kind: str, rotation: float) -> tuple[CanvasScene, QGraphicsItem, float, float]:
    factory, half, gains = KINDS[kind]
    scene = CanvasScene(CANVAS_W, CANVAS_H)
    scene.set_shadows_enabled(False)
    item = factory()
    scene.addItem(item)
    if rotation:
        item.setTransformOriginPoint(QPointF(600, 450))
        item.setRotation(rotation)
    return scene, item, half, gains[rotation]


@pytest.fixture
def make_view(qtbot):
    def make(scene: CanvasScene) -> CanvasView:
        view = CanvasView(scene)
        view.resize(900, 700)
        view.show()
        qtbot.addWidget(view)
        qtbot.waitExposed(view)
        QApplication.processEvents()
        return view

    return make


def _interior(view: CanvasView, zoom: float, half_cm: float) -> QImage:
    """The square of ``half_cm`` around the scene's middle as the view shows it
    at ``zoom`` (device pixels)."""
    view.set_zoom(zoom)
    view.centerOn(QPointF(600, 450))
    QApplication.processEvents()
    image = view.viewport().grab().toImage()
    ratio = image.devicePixelRatio()
    center = view.mapFromScene(QPointF(600, 450))
    half = int(half_cm * zoom)
    # the viewport is 900 x 700: stay inside it at 1000 %
    half = min(half, 300)
    return image.copy(
        int((center.x() - half) * ratio),
        int((center.y() - half) * ratio),
        int(2 * half * ratio),
        int(2 * half * ratio),
    )


class TestZoomedInIsSharp:
    @pytest.mark.parametrize("zoom", [4.0, 10.0])
    @pytest.mark.parametrize("rotation", [0.0, 30.0])
    @pytest.mark.parametrize("kind", list(KINDS))
    def test_an_item_carries_detail_at_the_zoom_it_is_shown_at(
        self, make_view, kind: str, rotation: float, zoom: float
    ) -> None:
        scene, _item, half, gain = _build(kind, rotation)
        view = make_view(scene)
        at_hundred = _interior(view, 1.0, half)
        shown = _pixels(_interior(view, zoom, half))
        # the same square at 100 %, enlarged: what the canvas showed before
        before = _upscaled(at_hundred, shown.shape[0] / at_hundred.height())
        ratio = _gradient_energy(shown) / _gradient_energy(before)
        assert ratio >= gain, f"{kind} at {zoom:g}x, rotated {rotation:g}: gain {ratio:.2f}"

    @pytest.mark.parametrize("kind", ["plant-circle", "furniture-rectangle"])
    def test_a_sprite_stays_where_it_was(self, make_view, kind: str) -> None:
        """Sharp but shifted is a failure: averaged back to 1 px per cm, the
        400 % picture is the 100 % picture."""
        scene, _item, half, _gain = _build(kind, 0.0)
        view = make_view(scene)
        at_hundred = _pixels(_interior(view, 1.0, half))
        shown = _pixels(_interior(view, 4.0, half))
        side = at_hundred.shape[0]
        averaged = shown[: side * 4, : side * 4].reshape(side, 4, side, 4, 3).mean(axis=(1, 3))

        def error(dx: int, dy: int) -> float:
            moved = np.roll(np.roll(at_hundred, dy, axis=0), dx, axis=1)
            return float(np.sqrt(((averaged[2:-2, 2:-2] - moved[2:-2, 2:-2]) ** 2).mean()))

        here = error(0, 0)
        for shift in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            assert here < error(*shift), (kind, here, shift, error(*shift))


class TestExportsAreSharp:
    @pytest.mark.parametrize("rotation", [0.0, 30.0])
    @pytest.mark.parametrize("kind", list(KINDS))
    def test_a_300_dpi_png_is_rasterised_at_300_dpi(
        self, qtbot, tmp_path, kind: str, rotation: float
    ) -> None:
        """A 300-dpi export of a 12 m plan on 40 cm of paper is 3.94 px per cm:
        its sprites and fills are rasterised for that, not enlarged from 1."""
        scene, _item, half, gain = _build(kind, rotation)
        fine_path, coarse_path = tmp_path / "fine.png", tmp_path / "coarse.png"
        ExportService.export_to_png(scene, fine_path, dpi=300, output_width_cm=40.0)
        # 1 px per cm: 1200 px wide at 300 dpi is 10.16 cm of paper
        ExportService.export_to_png(scene, coarse_path, dpi=300, output_width_cm=10.16)
        fine, coarse = QImage(str(fine_path)), QImage(str(coarse_path))
        scale = fine.width() / CANVAS_W
        assert scale == pytest.approx(3.94, abs=0.01)
        assert coarse.width() / CANVAS_W == pytest.approx(1.0, abs=0.01)

        def crop(image: QImage, px_per_cm: float) -> QImage:
            side = int(2 * half * px_per_cm)
            # the export is north-up: y = 450 is the image's middle either way
            return image.copy(
                int((600 - half) * px_per_cm), int((450 - half) * px_per_cm), side, side
            )

        shown = _pixels(crop(fine, scale))
        before = _upscaled(crop(coarse, 1.0), shown.shape[0] / (2 * half))
        ratio = _gradient_energy(shown) / _gradient_energy(before)
        assert ratio >= gain, f"{kind} rotated {rotation:g}: gain {ratio:.2f}"

    @pytest.mark.parametrize("kind", ["plant-circle", "furniture-rectangle"])
    def test_the_agent_api_render_is_rasterised_for_its_own_image(self, qtbot, kind: str) -> None:
        scene, _item, half, gain = _build(kind, 0.0)
        region = (600 - half, 450 - half, 2 * half, 2 * half)
        fine = render_canvas_image(scene, region, None, int(2 * half * 16))  # 16 px per cm
        coarse = render_canvas_image(scene, region, None, 1)  # the tool's smallest image
        assert fine["px_per_cm"] == pytest.approx(16.0)
        factor = fine["px_per_cm"] / coarse["px_per_cm"]
        assert factor >= 4.0  # the smallest image is 4 px per cm of this region
        shown = _pixels(QImage.fromData(fine["png_bytes"]))
        before = _upscaled(QImage.fromData(coarse["png_bytes"]), factor)
        ratio = _gradient_energy(shown) / _gradient_energy(before)
        # master 1.1 (4 px per cm enlarged is what 16 px per cm showed); the fix 2.2+
        assert ratio >= 1.6, f"{kind}: gain {ratio:.2f} (the bar for a zoom is {gain})"

    def test_a_minimap_keeps_one_pixel_per_cm(self, qtbot, monkeypatch) -> None:
        """Zoomed out — the minimap paints the scene at a few percent — a sprite
        is the 1-px-per-cm bitmap it always was (``raster_resolution.MIN_LEVEL``)."""
        scene, _item, _half, _gain = _build("plant-circle", 0.0)
        made: list[int] = []
        real = sprite_raster.rasterise

        def spy(width, height, draw, tint=None):
            made.append(max(width, height))
            return real(width, height, draw, tint)

        monkeypatch.setattr(sprite_raster, "rasterise", spy)
        sprite_raster.clear_sprite_cache()
        image = QImage(120, 90, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        from PyQt6.QtGui import QPainter

        painter = QPainter(image)
        scene.render(painter, QRectF(0, 0, 120, 90), QRectF(0, 0, CANVAS_W, CANVAS_H))
        painter.end()
        # an 80 cm tree, drawn 1.15 times its footprint: 92 cm -> 92 px
        assert made == [92], made


class TestPanIsCheap:
    def test_the_item_cache_has_room_for_a_plan(self, qtbot) -> None:
        """Qt keeps item caches in QPixmapCache, 10 MB by default — one lawn at
        full HD is 8 MB. A scene raises it (#784); without that the cache
        thrashes and every repaint paints every item again."""
        CanvasScene(CANVAS_W, CANVAS_H)
        assert QPixmapCache.cacheLimit() >= ITEM_CACHE_BUDGET_KB == 256 * 1024

    def test_zoom_in_then_pan_repaints_nothing(self, make_view, monkeypatch) -> None:
        """The workflow: zoom in on a bed (sharp), then pan. A plant that stays
        in view is a blit of its cache, not a paint."""
        scene = CanvasScene(CANVAS_W, CANVAS_H)
        lawn = RectangleItem(100, 100, 1000, 700, object_type=ObjectType.LAWN,
                             fill_pattern=FillPattern.GRASS)
        scene.addItem(lawn)
        plants = [CircleItem(560 + 40 * i, 450, 15, object_type=ObjectType.PERENNIAL)
                  for i in range(3)]
        for plant in plants:
            scene.addItem(plant)
        view = make_view(scene)
        view.set_zoom(4.0)
        view.centerOn(QPointF(600, 450))
        QApplication.processEvents()
        view.viewport().repaint()

        from open_garden_planner.ui.canvas.items import circle_item

        painted: list[str] = []
        real = circle_item.paint_plant

        def spy(painter, rect, **kwargs):
            painted.append(kwargs.get("item_id", ""))
            return real(painter, rect, **kwargs)

        monkeypatch.setattr(circle_item, "paint_plant", spy)
        bar = view.horizontalScrollBar()
        for _ in range(5):
            bar.setValue(bar.value() + 12)  # 3 cm at 400 %: every plant stays in view
            view.viewport().repaint()
        assert painted == [], f"{len(painted)} plant paints during a pan"
        # ... and the pictures that were blitted are the sharp ones
        sizes = [key[1] for key in sprite_raster.SPRITE_CACHE._entries if key[0][0] == "plant"]
        assert max(sizes) == 138  # 30 cm x 1.15 fill scale x level 4
