"""Integration tests for canvas item caching, LOD, and export fidelity (issue #409).

Tests:
1. DeviceCoordinateCache toggling on selection/deselection across item types
   to prevent selection handle ghosting and rotation lag.
2. Level-of-Detail (LOD) flat-fill behaviour in interactive viewport vs exports.
3. Export fidelity: export paths temporarily disable item caches and produce
   100% bit-exact output without cache degradation.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QStyleOptionGraphicsItem, QWidget

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
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
    """Verify LOD flat fill logic."""

    def test_lod_inactive_when_widget_is_none(self, qtbot) -> None:  # noqa: ARG002
        item = CircleItem(0, 0, 50, object_type=ObjectType.TREE)
        option = QStyleOptionGraphicsItem()
        img = QImage(100, 100, QImage.Format.Format_ARGB32)
        painter = QPainter(img)
        try:
            # widget is None simulates export / print / offscreen rendering
            assert not item.should_use_lod_flat_fill(option, widget=None, painter=painter)
        finally:
            painter.end()

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
