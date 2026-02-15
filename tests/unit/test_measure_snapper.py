"""Tests for the measure tool anchor snapper."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.measure_snapper import (
    AnchorPoint,
    AnchorType,
    find_nearest_anchor,
    get_anchor_points,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)


@pytest.fixture
def scene(qtbot) -> CanvasScene:
    """Create a canvas scene for testing."""
    return CanvasScene(2000, 2000)


class TestGetAnchorPoints:
    """Tests for get_anchor_points function."""

    def test_rectangle_returns_nine_anchors(self, qtbot, scene: CanvasScene) -> None:
        """Rectangle should have center + 4 edge midpoints + 4 corners."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        assert len(anchors) == 9

    def test_rectangle_center_anchor(self, qtbot, scene: CanvasScene) -> None:
        """Rectangle center should be at geometric center."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        centers = [a for a in anchors if a.anchor_type == AnchorType.CENTER]
        assert len(centers) == 1
        center = centers[0].point
        # Rect is at (100, 100) with w=200, h=100 -> center at (200, 150)
        assert abs(center.x() - 200.0) < 0.5
        assert abs(center.y() - 150.0) < 0.5

    def test_rectangle_edge_anchors(self, qtbot, scene: CanvasScene) -> None:
        """Rectangle edges should have midpoint anchors."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        edge_types = {a.anchor_type for a in anchors if a.anchor_type not in (AnchorType.CENTER, AnchorType.CORNER)}
        assert AnchorType.EDGE_TOP in edge_types
        assert AnchorType.EDGE_BOTTOM in edge_types
        assert AnchorType.EDGE_LEFT in edge_types
        assert AnchorType.EDGE_RIGHT in edge_types

    def test_rectangle_corner_anchors(self, qtbot, scene: CanvasScene) -> None:
        """Rectangle should have 4 corner anchors."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        corners = [a for a in anchors if a.anchor_type == AnchorType.CORNER]
        assert len(corners) == 4

    def test_rectangle_corner_positions(self, qtbot, scene: CanvasScene) -> None:
        """Rectangle corners should be at the four corners of the rect."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        corners = sorted(
            [a for a in anchors if a.anchor_type == AnchorType.CORNER],
            key=lambda a: (a.point.x(), a.point.y()),
        )
        # Expected corners: (100,100), (100,200), (300,100), (300,200)
        assert abs(corners[0].point.x() - 100.0) < 0.5
        assert abs(corners[0].point.y() - 100.0) < 0.5
        assert abs(corners[3].point.x() - 300.0) < 0.5
        assert abs(corners[3].point.y() - 200.0) < 0.5

    def test_rectangle_top_edge_position(self, qtbot, scene: CanvasScene) -> None:
        """Rectangle top edge midpoint should be at correct position."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        top_anchors = [a for a in anchors if a.anchor_type == AnchorType.EDGE_TOP]
        assert len(top_anchors) == 1
        top = top_anchors[0].point
        # Top midpoint: x=200 (center x), y=100 (top of rect)
        assert abs(top.x() - 200.0) < 0.5
        assert abs(top.y() - 100.0) < 0.5

    def test_circle_returns_five_anchors(self, qtbot, scene: CanvasScene) -> None:
        """Circle should have center + 4 cardinal edge points."""
        item = CircleItem(300, 300, 50)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        assert len(anchors) == 5

    def test_circle_center_anchor(self, qtbot, scene: CanvasScene) -> None:
        """Circle center should be at the specified center point."""
        item = CircleItem(300, 300, 50)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        centers = [a for a in anchors if a.anchor_type == AnchorType.CENTER]
        assert len(centers) == 1
        center = centers[0].point
        assert abs(center.x() - 300.0) < 0.5
        assert abs(center.y() - 300.0) < 0.5

    def test_circle_edge_anchors(self, qtbot, scene: CanvasScene) -> None:
        """Circle should have top, bottom, left, right edge anchors."""
        item = CircleItem(300, 300, 50)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        edge_types = {a.anchor_type for a in anchors if a.anchor_type != AnchorType.CENTER}
        assert AnchorType.EDGE_TOP in edge_types
        assert AnchorType.EDGE_BOTTOM in edge_types
        assert AnchorType.EDGE_LEFT in edge_types
        assert AnchorType.EDGE_RIGHT in edge_types

    def test_circle_top_edge_position(self, qtbot, scene: CanvasScene) -> None:
        """Circle top edge should be at center_y - radius."""
        item = CircleItem(300, 300, 50)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        top = [a for a in anchors if a.anchor_type == AnchorType.EDGE_TOP][0]
        assert abs(top.point.x() - 300.0) < 0.5
        assert abs(top.point.y() - 250.0) < 0.5

    def test_polygon_has_center_anchor(self, qtbot, scene: CanvasScene) -> None:
        """Polygon should have a center anchor."""
        vertices = [QPointF(0, 0), QPointF(200, 0), QPointF(200, 100), QPointF(0, 100)]
        item = PolygonItem(vertices)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        centers = [a for a in anchors if a.anchor_type == AnchorType.CENTER]
        assert len(centers) == 1

    def test_polygon_has_edge_midpoint_anchors(self, qtbot, scene: CanvasScene) -> None:
        """Polygon should have vertex, edge midpoint and center anchors."""
        vertices = [QPointF(0, 0), QPointF(200, 0), QPointF(200, 100), QPointF(0, 100)]
        item = PolygonItem(vertices)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        # 1 center + 4 vertices + 4 edge midpoints = 9
        assert len(anchors) == 9

    def test_polygon_has_corner_anchors(self, qtbot, scene: CanvasScene) -> None:
        """Polygon should have a CORNER anchor for each vertex."""
        vertices = [QPointF(0, 0), QPointF(200, 0), QPointF(200, 100), QPointF(0, 100)]
        item = PolygonItem(vertices)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        corners = [a for a in anchors if a.anchor_type == AnchorType.CORNER]
        assert len(corners) == 4

    def test_polygon_triangle(self, qtbot, scene: CanvasScene) -> None:
        """Triangle polygon: 1 center + 3 vertices + 3 edge midpoints = 7."""
        vertices = [QPointF(100, 0), QPointF(200, 100), QPointF(0, 100)]
        item = PolygonItem(vertices)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        assert len(anchors) == 7

    def test_polyline_has_center_endpoints_and_midpoints(self, qtbot, scene: CanvasScene) -> None:
        """Polyline should have center + endpoints + segment midpoints."""
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)]
        item = PolylineItem(points)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        # 1 center + 3 endpoints + 2 segment midpoints = 6
        assert len(anchors) == 6

    def test_polyline_single_segment(self, qtbot, scene: CanvasScene) -> None:
        """Polyline with 2 points: 1 center + 2 endpoints + 1 midpoint = 4."""
        points = [QPointF(0, 0), QPointF(200, 0)]
        item = PolylineItem(points)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        assert len(anchors) == 4

    def test_polyline_endpoint_anchors(self, qtbot, scene: CanvasScene) -> None:
        """Polyline should have ENDPOINT anchors for all vertices."""
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)]
        item = PolylineItem(points)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        endpoints = [a for a in anchors if a.anchor_type == AnchorType.ENDPOINT]
        assert len(endpoints) == 3

    def test_polyline_endpoint_positions(self, qtbot, scene: CanvasScene) -> None:
        """Polyline endpoints should match the original point positions."""
        points = [QPointF(0, 0), QPointF(200, 0)]
        item = PolylineItem(points)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        endpoints = sorted(
            [a for a in anchors if a.anchor_type == AnchorType.ENDPOINT],
            key=lambda a: a.point.x(),
        )
        assert abs(endpoints[0].point.x() - 0.0) < 0.5
        assert abs(endpoints[0].point.y() - 0.0) < 0.5
        assert abs(endpoints[1].point.x() - 200.0) < 0.5
        assert abs(endpoints[1].point.y() - 0.0) < 0.5

    def test_anchor_references_item(self, qtbot, scene: CanvasScene) -> None:
        """Each anchor should reference the source item."""
        item = RectangleItem(0, 0, 100, 100)
        scene.addItem(item)
        anchors = get_anchor_points(item)
        for anchor in anchors:
            assert anchor.item is item


class TestFindNearestAnchor:
    """Tests for find_nearest_anchor function."""

    def test_finds_closest_anchor(self, qtbot, scene: CanvasScene) -> None:
        """Should find the nearest anchor point within threshold."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        # Click near center (200, 150) with small offset
        result = find_nearest_anchor(QPointF(203, 148), list(scene.items()))
        assert result is not None
        assert result.anchor_type == AnchorType.CENTER

    def test_returns_none_beyond_threshold(self, qtbot, scene: CanvasScene) -> None:
        """Should return None when no anchor is within threshold."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        # Click far from any anchor
        result = find_nearest_anchor(QPointF(500, 500), list(scene.items()))
        assert result is None

    def test_snaps_to_edge_midpoint(self, qtbot, scene: CanvasScene) -> None:
        """Should snap to an edge midpoint when closer than center."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        # Click near the top edge midpoint (200, 100)
        result = find_nearest_anchor(QPointF(200, 103), list(scene.items()))
        assert result is not None
        assert result.anchor_type == AnchorType.EDGE_TOP

    def test_custom_threshold(self, qtbot, scene: CanvasScene) -> None:
        """Should respect custom threshold."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        # Use a very small threshold
        result = find_nearest_anchor(QPointF(205, 155), list(scene.items()), threshold=2.0)
        assert result is None

    def test_skips_non_garden_items(self, qtbot, scene: CanvasScene) -> None:
        """Should skip items that aren't GardenItemMixin instances."""
        from PyQt6.QtWidgets import QGraphicsRectItem
        # Add a plain QGraphicsRectItem (not a GardenItem)
        plain_item = QGraphicsRectItem(100, 100, 200, 100)
        plain_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        scene.addItem(plain_item)
        result = find_nearest_anchor(QPointF(200, 150), list(scene.items()))
        assert result is None

    def test_skips_non_selectable_items(self, qtbot, scene: CanvasScene) -> None:
        """Should skip items that aren't selectable (locked/hidden layers)."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        # Make non-selectable
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        result = find_nearest_anchor(QPointF(200, 150), list(scene.items()))
        assert result is None

    def test_multiple_items_picks_closest(self, qtbot, scene: CanvasScene) -> None:
        """When multiple items are nearby, should pick the closest anchor."""
        item1 = RectangleItem(100, 100, 100, 100)
        item2 = RectangleItem(300, 100, 100, 100)
        scene.addItem(item1)
        scene.addItem(item2)
        # Click near item1 center (150, 150)
        result = find_nearest_anchor(QPointF(152, 148), list(scene.items()))
        assert result is not None
        assert result.item is item1

    def test_circle_center_snap(self, qtbot, scene: CanvasScene) -> None:
        """Should snap to circle center point."""
        item = CircleItem(300, 300, 50)
        scene.addItem(item)
        result = find_nearest_anchor(QPointF(302, 298), list(scene.items()))
        assert result is not None
        assert result.anchor_type == AnchorType.CENTER
        assert abs(result.point.x() - 300.0) < 0.5
        assert abs(result.point.y() - 300.0) < 0.5

    def test_snaps_to_rectangle_corner(self, qtbot, scene: CanvasScene) -> None:
        """Should snap to a rectangle corner when closest."""
        item = RectangleItem(100, 100, 200, 100)
        scene.addItem(item)
        # Click near top-left corner (100, 100)
        result = find_nearest_anchor(QPointF(102, 102), list(scene.items()))
        assert result is not None
        assert result.anchor_type == AnchorType.CORNER
        assert abs(result.point.x() - 100.0) < 0.5
        assert abs(result.point.y() - 100.0) < 0.5

    def test_snaps_to_polygon_vertex(self, qtbot, scene: CanvasScene) -> None:
        """Should snap to a polygon vertex (corner)."""
        vertices = [QPointF(0, 0), QPointF(200, 0), QPointF(200, 100), QPointF(0, 100)]
        item = PolygonItem(vertices)
        scene.addItem(item)
        # Click near vertex (200, 0)
        result = find_nearest_anchor(QPointF(198, 2), list(scene.items()))
        assert result is not None
        assert result.anchor_type == AnchorType.CORNER
        assert abs(result.point.x() - 200.0) < 0.5
        assert abs(result.point.y() - 0.0) < 0.5

    def test_snaps_to_polyline_endpoint(self, qtbot, scene: CanvasScene) -> None:
        """Should snap to a polyline endpoint."""
        points = [QPointF(0, 0), QPointF(200, 0)]
        item = PolylineItem(points)
        scene.addItem(item)
        # Click near start point (0, 0)
        result = find_nearest_anchor(QPointF(3, 2), list(scene.items()))
        assert result is not None
        assert result.anchor_type == AnchorType.ENDPOINT
        assert abs(result.point.x() - 0.0) < 0.5
        assert abs(result.point.y() - 0.0) < 0.5
