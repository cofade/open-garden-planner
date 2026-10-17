"""Integration tests for canvas item caching, LOD, and export fidelity (issues #409, #503).

Tests:
1. DeviceCoordinateCache toggling on selection/deselection across item types
   to prevent selection handle ghosting and rotation lag.
2. Level-of-Detail (LOD) flat-fill behaviour in interactive viewport vs exports.
3. Export fidelity: export paths temporarily disable item caches and produce
   100% bit-exact output without cache degradation.

Issue #503: the LOD guard was originally ``widget is not None``, but Qt passes
``widget = 0`` for every **cached** paint — and every unselected canvas item is
``DeviceCoordinateCache`` — so the LOD branch never ran in the product while
these tests passed because they called the helper directly. The guard now keys
on the item's **cache mode** (as ``PolygonItem``'s over-budget degrade does,
#472), and ``TestTheLodFillFiresOnARealCanvas`` pins it through a real
``CanvasView`` and rendered pixels.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsScene,
    QStyleOptionGraphicsItem,
    QWidget,
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


class TestLodFlatFill:
    """Verify LOD flat fill logic, keyed on the cache mode (#409, #503)."""

    def test_lod_fires_for_a_cached_canvas_item_without_a_widget(self, qtbot) -> None:  # noqa: ARG002
        """#503: Qt passes ``widget = 0`` for every cached paint.

        An unselected item on the canvas is ``DeviceCoordinateCache``, so this
        is the exact state the product paints in — and the guard must fire.
        """
        scene = CanvasScene()
        item = CircleItem(0, 0, 50, object_type=ObjectType.TREE)
        scene.addItem(item)
        assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

        option = QStyleOptionGraphicsItem()
        img = QImage(100, 100, QImage.Format.Format_ARGB32)
        painter = QPainter(img)
        try:
            painter.scale(0.2, 0.2)  # < 0.4 threshold
            assert item.should_use_lod_flat_fill(option, widget=None, painter=painter)
        finally:
            painter.end()

    def test_lod_stays_off_when_the_caches_are_disabled(self, qtbot) -> None:  # noqa: ARG002
        """The export/print/agent render convention keeps full detail.

        Those paths disable the item caches first
        (``ExportService._disable_item_caches``) and render offscreen, so both
        discriminator halves say "not interactive".
        """
        scene = CanvasScene()
        item = CircleItem(0, 0, 50, object_type=ObjectType.TREE)
        scene.addItem(item)
        cached = ExportService._disable_item_caches(scene)
        try:
            assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache
            option = QStyleOptionGraphicsItem()
            img = QImage(100, 100, QImage.Format.Format_ARGB32)
            painter = QPainter(img)
            try:
                painter.scale(0.2, 0.2)
                assert not item.should_use_lod_flat_fill(option, widget=None, painter=painter)
            finally:
                painter.end()
        finally:
            ExportService._restore_item_caches(cached)

    def test_lod_active_at_low_zoom(self, qtbot) -> None:
        item = CircleItem(0, 0, 50, object_type=ObjectType.TREE)
        widget = QWidget()
        qtbot.addWidget(widget)

        option = QStyleOptionGraphicsItem()
        img = QImage(100, 100, QImage.Format.Format_ARGB32)
        painter = QPainter(img)
        try:
            # At zoom factor 0.2 (< 0.4 threshold)
            painter.scale(0.2, 0.2)
            assert item.should_use_lod_flat_fill(option, widget=widget, painter=painter)

            # At zoom factor 1.0 (>= 0.4 threshold)
            painter.resetTransform()
            painter.scale(1.0, 1.0)
            assert not item.should_use_lod_flat_fill(option, widget=widget, painter=painter)
        finally:
            painter.end()

    def test_lod_plant_flat_fill_color_uses_style_not_black(self, qtbot) -> None:
        from open_garden_planner.core.object_types import get_style

        # SVG plant item has no explicit tint and brush is empty QBrush
        item = CircleItem(0, 0, 50, object_type=ObjectType.TREE)
        item.fill_color = None
        assert item.fill_color is None
        assert item.brush().style() == Qt.BrushStyle.NoBrush

        lod_color = item.get_lod_fill_color()
        expected_color = get_style(ObjectType.TREE).fill_color
        assert lod_color == expected_color
        assert lod_color != QColor(0, 0, 0)
        assert lod_color != QColor(0, 0, 0, 0)

        # Output at 0.1 zoom: renders with style color, not black
        widget = QWidget()
        qtbot.addWidget(widget)
        option = QStyleOptionGraphicsItem()
        img = QImage(100, 100, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        painter = QPainter(img)
        try:
            painter.scale(0.1, 0.1)
            item.paint(painter, option, widget)
        finally:
            painter.end()

        # Center pixel must not be black (0, 0, 0)
        center_color = img.pixelColor(2, 2)
        assert center_color != QColor(0, 0, 0)


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

    Rendered at :data:`EXPORT_SCALE` on purpose. This is where the convention
    is load-bearing: a PDF/SVG export maps a whole plan to the page width (a
    50 m plan on an A4-width page is scale ~0.1), so with the caches left on
    the same render would flat-fill — a 1:1 render cannot tell the difference
    (level 1.0 keeps the LOD branch off either way). The scene is a
    ``CanvasScene`` so the items are actually cached before the convention
    disables them. The returned rect is the image's own extent (the item fills
    it).
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
#   low-zoom canvas, fixed:   samples 2 604, spread 0.00  (flat fill; with the
#                             guard disabled — the old behaviour — the same
#                             render reads 14.30, which is what the regression
#                             catches)
#   full-zoom canvas:          samples 40 425, spread 20.07 (texture)
#   export at EXPORT_SCALE:    samples 2 501, spread 14.55 (texture; with the
#                              caches NOT disabled first the same render reads
#                              0.00 — the convention is load-bearing here)
# The samples come from the item's own mapped region, never from a colour
# filter: the first version matched "blue-ish" pixels image-wide, and on the
# Linux/offscreen CI the scene's faint background passed that filter — spread
# 62.59 there against 0.00 on Windows, one red CI job, no reproduction locally.
CANVAS_FILL_SAMPLES_MIN = 1_000
FLAT_SPREAD_MAX = 4.0
TEXTURE_SPREAD_MIN = 8.0


class TestTheLodFillFiresOnARealCanvas:
    """#503 pinned through a real ``CanvasView`` and its rendered pixels.

    The measured defect: the guard tested ``widget is not None``, Qt passes
    ``widget = 0`` for every cached paint, and every unselected canvas item is
    ``DeviceCoordinateCache`` — so even zoomed far out, the canvas painted the
    full texture. A texture has luminance spread (tiles, grout); a flat fill is
    one colour. The intensity std of the fill interior tells the two apart.
    """

    def test_at_low_zoom_the_canvas_flat_fills(self, qtbot) -> None:  # noqa: ARG002
        item = _styled_textured_rectangle()
        calls: list[tuple[QWidget | None, bool]] = []
        original = item.should_use_lod_flat_fill

        def recording(
            option: QStyleOptionGraphicsItem | None,
            widget: QWidget | None,
            painter: QPainter,
            *args: float,
        ) -> bool:
            result = original(option, widget, painter, *args)
            calls.append((widget, result))
            return result

        item.should_use_lod_flat_fill = recording  # type: ignore[assignment]
        image, item_rect = _interactive_canvas_render(qtbot, item, zoom=0.25)
        # The guard must have been consulted BY Qt's real cached paint, and
        # said yes there — the pixel checks below then confirm it painted.
        assert calls, "the LOD guard was never consulted during a real cached paint"
        assert any(w is None and r for w, r in calls), (
            "no cached paint (widget=None) got True from the LOD guard at 0.25 "
            f"zoom (calls as (widget is None, returned): {[(w is None, r) for w, r in calls]})"
        )
        count, spread = _fill_intensity_stats(image, item_rect)
        assert count > CANVAS_FILL_SAMPLES_MIN, "the fill did not paint at all"
        assert spread < FLAT_SPREAD_MAX, (
            f"the canvas did not flat-fill at low zoom (spread {spread:.2f}); "
            "issue #503: the LOD branch is unreachable again"
        )

    def test_at_full_zoom_the_canvas_keeps_the_texture(self, qtbot) -> None:  # noqa: ARG002
        image, item_rect = _interactive_canvas_render(
            qtbot, _styled_textured_rectangle(), zoom=1.0
        )
        count, spread = _fill_intensity_stats(image, item_rect)
        assert count > CANVAS_FILL_SAMPLES_MIN
        assert spread > TEXTURE_SPREAD_MIN, (
            "the texture vanished at full zoom; the LOD fill must be "
            "threshold-gated, not unconditional"
        )

    def test_the_export_keeps_the_texture(self, qtbot) -> None:  # noqa: ARG002
        image, item_rect = _export_render(_styled_textured_rectangle())
        count, spread = _fill_intensity_stats(image, item_rect)
        assert count > CANVAS_FILL_SAMPLES_MIN
        assert spread > TEXTURE_SPREAD_MIN, (
            "the export lost the texture; cache-disabled render paths must "
            "keep full detail"
        )
