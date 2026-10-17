"""Integration tests for canvas item caching, export fidelity, and texture loss.

Tests:
1. DeviceCoordinateCache toggling on selection/deselection across item types
   to prevent selection handle ghosting and rotation lag.
2. Export fidelity: export paths temporarily disable item caches and produce
   100% bit-exact output without cache degradation.
3. ``TestTexturesAreNeverDropped``: a real ``CanvasView`` renders a textured,
   tinted item at five zoom levels and the export path at export scale, and
   asserts the texture survives each one.

Issue #503: the #409 canvas carried a low-zoom "level-of-detail" flat fill that
replaced every texture below 40 % zoom. It never ran (its guard tested
``widget is not None``, but Qt passes ``widget = 0`` for every **cached** paint
and every unselected canvas item is ``DeviceCoordinateCache``), and when
measured on the 990-item reference plan it bought nothing — fit-in-view read
10.58 ms without it and 10.64 ms with it, because ``DeviceCoordinateCache``
already amortises the textured paint into a one-off cost. The owner's manual
pass confirmed the cost was real: they work at 20-25 % zoom, well under the
threshold, where the branch would have hidden every texture. The branch and its
threshold were removed; what replaced it is the negative pin in (3), so the
detail cannot be silently subtracted again.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsScene,
)

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    BezierItem,
    CalloutItem,
    CircleItem,
    EllipseItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
    TextItem,
)


class TestItemCacheToggling:
    """Verify items enable DeviceCoordinateCache when unselected and NoCache when selected."""

    def test_circle_item_cache_toggles(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        item = CircleItem(0, 0, 50, object_type=ObjectType.TREE)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_rectangle_item_cache_toggles(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        item = RectangleItem(0, 0, 100, 50, object_type=ObjectType.RAISED_BED)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_polygon_item_cache_toggles(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(50, 80)]
        item = PolygonItem(QPolygonF(points), object_type=ObjectType.GARDEN_BED)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_ellipse_item_cache_toggles(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        item = EllipseItem(0, 0, 80, 40, object_type=ObjectType.CONTAINER_ROUND)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_polyline_item_cache_toggles(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)]
        item = PolylineItem(points, object_type=ObjectType.FENCE)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_callout_item_cache_toggles(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        item = CalloutItem(target=QPointF(0, 0), box_offset=QPointF(20, 20), content="Test Callout")
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_text_item_cache_toggles(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        item = TextItem(0, 0, content="Sample Text")
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_arc_item_cache_toggles(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        item = ArcItem(center=QPointF(0, 0), radius=50, start_deg=0, span_deg=90)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

    def test_bezier_item_cache_toggles(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        anchors = [QPointF(0, 0), QPointF(100, 100)]
        handles_in = [QPointF(0, 0), QPointF(50, 100)]
        handles_out = [QPointF(50, 0), QPointF(100, 100)]
        item = BezierItem(anchors=anchors, handles_in=handles_in, handles_out=handles_out)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        item.setSelected(True)
        assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache

        item.setSelected(False)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache


class TestExportCacheFidelity:
    """Verify exports disable item caches and preserve exact visual output."""

    def test_export_service_disables_and_restores_caches(self, qtbot) -> None:  # noqa: ARG002
        scene = QGraphicsScene()
        c1 = CircleItem(0, 0, 50, object_type=ObjectType.TREE)
        r1 = RectangleItem(0, 0, 100, 50, object_type=ObjectType.RAISED_BED)
        r2 = RectangleItem(100, 100, 100, 50, object_type=ObjectType.LAWN)
        scene.addItem(c1)
        scene.addItem(r1)
        scene.addItem(r2)

        # r2 is selected before export -> its cache mode is NoCache
        r2.setSelected(True)
        assert r2.cacheMode() == QGraphicsItem.CacheMode.NoCache
        assert c1.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        assert r1.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        hidden_overlay, prior_selection = ExportService._hide_overlay_items(scene)
        assert r2 in prior_selection
        cached = ExportService._disable_item_caches(scene)
        assert c1.cacheMode() == QGraphicsItem.CacheMode.NoCache
        assert r1.cacheMode() == QGraphicsItem.CacheMode.NoCache

        ExportService._restore_overlay_items(hidden_overlay, prior_selection)
        ExportService._restore_item_caches(cached)

        # Unselected items restore to DeviceCoordinateCache
        assert c1.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        assert r1.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
        # Selected item remains selected and MUST remain NoCache to prevent handle ghosting
        assert r2.isSelected() is True
        assert r2.cacheMode() == QGraphicsItem.CacheMode.NoCache

    def test_render_scene_region_preserves_bit_exact_export(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene()
        c1 = CircleItem(10, 10, 30, object_type=ObjectType.TREE)
        r1 = RectangleItem(50, 50, 80, 40, object_type=ObjectType.RAISED_BED)
        scene.addItem(c1)
        scene.addItem(r1)

        target_rect = QRectF(0, 0, 200, 200)
        source_rect = QRectF(0, 0, 200, 200)

        # Render 1: via render_scene_region (which uses _uncached_items)
        img1 = QImage(200, 200, QImage.Format.Format_ARGB32)
        img1.fill(QColor("white"))
        p1 = QPainter(img1)
        try:
            render_scene_region(scene, p1, target_rect, source_rect, y_flip=False)
        finally:
            p1.end()

        # Render 2: baseline with caches explicitly disabled
        c1.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        r1.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        img2 = QImage(200, 200, QImage.Format.Format_ARGB32)
        img2.fill(QColor("white"))
        p2 = QPainter(img2)
        try:
            scene.render(p2, target_rect, source_rect)
        finally:
            p2.end()

        assert img1 == img2, "render_scene_region export pixels differ from uncached baseline"


# ── Issue #503: the LOD flat fill must fire on a real canvas ──────────────
#
# Deep blue — not any object type's default, distant in intensity from the
# white page and any pen in play — so a flat fill and its tinted texture land
# in distinct, measurable intensity ranges.
FLAT_FILL = QColor("#ff1f4fd8")
TEXTURE = FillPattern.ROOF_TILES
# What an export render shrinks a plan to: a PDF/SVG export maps a whole plan
# to the page width, which for a 50 m plan on an A4-width page is scale ~0.1
# (72-96 dpi); the load-bearing cases are large canvases on small pages, while
# a plan small enough to be enlarged onto the page sits above 0.4 where the
# LOD branch cannot fire at all. 1:1 renders cannot see the branch either.
EXPORT_SCALE = 0.25


def _styled_textured_rectangle() -> RectangleItem:
    item = RectangleItem(200, 200, 600, 400, object_type=ObjectType.GENERIC_RECTANGLE)
    item.fill_pattern = TEXTURE
    item.fill_color = QColor(FLAT_FILL)
    item.setBrush(create_pattern_brush(TEXTURE, QColor(FLAT_FILL)))
    return item


def _interactive_canvas_render(qtbot: object, item: RectangleItem, *, zoom: float) -> tuple[QImage, QRectF]:
    """What the canvas shows at ``zoom``: a real CanvasView, caches ON, fresh.

    Returns the rendered viewport image and the item's rectangle **in image
    coordinates** (mapped through the view transform), so assertions sample the
    item's own region and nothing else. A colour-matching bounding box was the
    first version of this helper; on the Linux/offscreen CI the scene's faint
    background pixels passed the colour filter and poisoned the sample (CI
    measured spread 62.59 where Windows measured 0.00), so the region is
    computed, not discovered.
    """
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    scene.addItem(item)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.resize(700, 700)
    view.show()
    QApplication.processEvents()
    view.set_zoom(zoom)
    view.centerOn(QPointF(500, 400))  # the rectangle's centre, scene coords
    QApplication.processEvents()
    view.resetCachedContent()  # force every device cache to rebuild -> paint() runs
    QApplication.processEvents()
    image = QImage(view.viewport().size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        view.viewport().render(painter)
    finally:
        painter.end()
    item_rect = view.mapFromScene(item.sceneBoundingRect()).boundingRect()
    return image, QRectF(item_rect)


def _export_render(item: RectangleItem) -> tuple[QImage, QRectF]:
    """What an export shows: the project's own cache-disabling convention.

    The scene is a ``CanvasScene`` so the items are actually cached before the
    convention disables them. The returned rect is the image's own extent (the
    item fills it).
    """
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    scene.addItem(item)
    assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache
    cached = ExportService._disable_item_caches(scene)
    try:
        source = item.sceneBoundingRect()
        image = QImage(
            max(1, int(source.width() * EXPORT_SCALE)),
            max(1, int(source.height() * EXPORT_SCALE)),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(QColor("white"))
        painter = QPainter(image)
        try:
            painter.scale(EXPORT_SCALE, EXPORT_SCALE)
            scene.render(
                painter,
                QRectF(0, 0, source.width(), source.height()),
                source,
            )
        finally:
            painter.end()
    finally:
        ExportService._restore_item_caches(cached)
    return image, QRectF(0, 0, image.width(), image.height())


def _fill_intensity_stats(image: QImage, region: QRectF) -> tuple[int, float]:
    """(sample count, intensity std) over ``region``'s interior pixels.

    A flat fill is one colour (std ~ 0); a tinted texture carries the tile
    texture's luminance spread. ``region`` is inset 10 % so the antialiased
    item edge and the outline do not masquerade as texture.
    """
    ix = region.width() * 0.1
    iy = region.height() * 0.1
    x0, y0 = int(region.left() + ix), int(region.top() + iy)
    x1, y1 = int(region.right() - ix), int(region.bottom() - iy)
    values: list[float] = []
    for y in range(max(0, y0), min(image.height(), y1 + 1), 2):
        for x in range(max(0, x0), min(image.width(), x1 + 1), 2):
            colour = QColor(image.pixel(x, y))
            values.append((colour.red() + colour.green() + colour.blue()) / 3.0)
    assert values, "the sample region lies outside the image"
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return len(values), var ** 0.5


# Calibrated bounds, measured on this harness (explicit, so a harness change
# fails loudly instead of sliding silently):
#   low-zoom canvas (0.25):   samples ~2 600, spread 14.6  (texture)
#   full-zoom canvas (1.0):   samples 40 425, spread 20.07 (texture)
#   export at EXPORT_SCALE:   samples 2 501, spread 14.55 (texture)
# The bound is one-sided on purpose: it says the texture IS there, with no
# ceiling on its contrast. A future change may legitimately soften a texture,
# and it must not be able to do so by deleting it.
# The samples come from the item's own mapped region, never from a colour
# filter: the first version matched "blue-ish" pixels image-wide, and on the
# Linux/offscreen CI the scene's faint background passed that filter — spread
# 62.59 there against 0.00 on Windows, one red CI job, no reproduction locally.
CANVAS_FILL_SAMPLES_MIN = 1_000
TEXTURE_SPREAD_MIN = 8.0


class TestTexturesAreNeverDropped:
    """The canvas keeps every texture at every zoom level (#503).

    A texture has luminance spread (tiles, grout); a flat fill is one colour,
    so the intensity std of a fill's interior tells the two apart. This class
    asserts the *absence* of the regression rather than the presence of a
    feature: the #409 low-zoom flat fill was removed in #503 because it was
    measured to buy nothing (docs/11 §11.4.11), and removing dead code leaves
    no test behind to catch it creeping back. These three are the pin.

    Measured on the 990-item reference plan, the removed branch changed nothing:
    fit-in-view read 10.58 ms with it disabled and 10.64 ms with it live, and
    every NFR-PERF-01 budget test passes either way — ``DeviceCoordinateCache``
    already amortises the textured paint into a one-off cost, so the LOD could
    only ever subtract detail. The owner works at 20-25 % zoom, where the
    removed threshold (0.4) would have hidden every texture.
    """

    @pytest.mark.parametrize("zoom", [0.1, 0.25, 0.4, 0.75, 1.0])
    def test_the_canvas_keeps_the_texture_at_every_zoom(
        self, qtbot: object, zoom: float
    ) -> None:  # noqa: ARG002
        image, item_rect = _interactive_canvas_render(
            qtbot, _styled_textured_rectangle(), zoom=zoom
        )
        count, spread = _fill_intensity_stats(image, item_rect)
        # Scale-free "it really painted" floor: the sampler steps 2 px in both
        # axes over a region inset 10 %, so it sees ~57 % of the area at every
        # zoom. An absolute count would fail the 0.1 case for being small
        # rather than for being wrong, which is how a real failure gets
        # mistaken for a calibration nit.
        assert count * 10 > int(item_rect.width() * item_rect.height()), (
            f"the sampled region held almost nothing ({count} px) — the fill "
            f"did not paint at zoom {zoom}"
        )
        assert spread > TEXTURE_SPREAD_MIN, (
            f"the texture was replaced by a flat fill at zoom {zoom} "
            f"(fill spread {spread:.2f}); #503 removed the low-zoom flat fill "
            "because it cost detail and bought no measurable time"
        )

    def test_the_export_keeps_the_texture(self, qtbot) -> None:  # noqa: ARG002
        image, item_rect = _export_render(_styled_textured_rectangle())
        count, spread = _fill_intensity_stats(image, item_rect)
        assert count > CANVAS_FILL_SAMPLES_MIN
        assert spread > TEXTURE_SPREAD_MIN, (
            "the export lost the texture; cache-disabled render paths must "
            "keep full detail"
        )
