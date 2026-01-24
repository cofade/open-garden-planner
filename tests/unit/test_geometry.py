"""Unit tests for geometry primitives."""

import math

import pytest

from open_garden_planner.core.geometry.primitives import (
    BoundingBox,
    Point,
    Polygon,
    Polyline,
)


class TestPoint:
    """Tests for the Point class."""

    def test_creation(self) -> None:
        """Test basic point creation."""
        p = Point(100.0, 200.0)
        assert p.x == 100.0
        assert p.y == 200.0
        assert p.z == 0.0  # Default z

    def test_creation_with_z(self) -> None:
        """Test point creation with z coordinate."""
        p = Point(100.0, 200.0, 50.0)
        assert p.z == 50.0

    def test_origin(self) -> None:
        """Test origin factory method."""
        p = Point.origin()
        assert p.x == 0.0
        assert p.y == 0.0
        assert p.z == 0.0

    def test_addition(self) -> None:
        """Test vector addition."""
        p1 = Point(100.0, 200.0)
        p2 = Point(50.0, 30.0)
        result = p1 + p2
        assert result.x == 150.0
        assert result.y == 230.0

    def test_subtraction(self) -> None:
        """Test vector subtraction."""
        p1 = Point(100.0, 200.0)
        p2 = Point(50.0, 30.0)
        result = p1 - p2
        assert result.x == 50.0
        assert result.y == 170.0

    def test_scalar_multiplication(self) -> None:
        """Test multiplication by scalar."""
        p = Point(100.0, 200.0)
        result = p * 2.0
        assert result.x == 200.0
        assert result.y == 400.0

    def test_right_scalar_multiplication(self) -> None:
        """Test right multiplication by scalar."""
        p = Point(100.0, 200.0)
        result = 2.0 * p
        assert result.x == 200.0
        assert result.y == 400.0

    def test_division(self) -> None:
        """Test division by scalar."""
        p = Point(100.0, 200.0)
        result = p / 2.0
        assert result.x == 50.0
        assert result.y == 100.0

    def test_negation(self) -> None:
        """Test negation."""
        p = Point(100.0, 200.0)
        result = -p
        assert result.x == -100.0
        assert result.y == -200.0

    def test_distance_to(self) -> None:
        """Test 2D distance calculation."""
        p1 = Point(0.0, 0.0)
        p2 = Point(300.0, 400.0)
        assert p1.distance_to(p2) == 500.0  # 3-4-5 triangle scaled

    def test_distance_to_same_point(self) -> None:
        """Test distance to same point is zero."""
        p = Point(100.0, 200.0)
        assert p.distance_to(p) == 0.0

    def test_distance_to_3d(self) -> None:
        """Test 3D distance calculation."""
        p1 = Point(0.0, 0.0, 0.0)
        p2 = Point(100.0, 200.0, 200.0)
        expected = math.sqrt(100**2 + 200**2 + 200**2)
        assert p1.distance_to_3d(p2) == pytest.approx(expected)

    def test_midpoint(self) -> None:
        """Test midpoint calculation."""
        p1 = Point(0.0, 0.0)
        p2 = Point(100.0, 200.0)
        mid = p1.midpoint(p2)
        assert mid.x == 50.0
        assert mid.y == 100.0

    def test_rotate_around_90_degrees(self) -> None:
        """Test rotation by 90 degrees."""
        p = Point(100.0, 0.0)
        center = Point.origin()
        rotated = p.rotate_around(center, 90.0)
        assert rotated.x == pytest.approx(0.0, abs=1e-10)
        assert rotated.y == pytest.approx(100.0, abs=1e-10)

    def test_rotate_around_180_degrees(self) -> None:
        """Test rotation by 180 degrees."""
        p = Point(100.0, 50.0)
        center = Point.origin()
        rotated = p.rotate_around(center, 180.0)
        assert rotated.x == pytest.approx(-100.0, abs=1e-10)
        assert rotated.y == pytest.approx(-50.0, abs=1e-10)

    def test_rotate_around_custom_center(self) -> None:
        """Test rotation around a non-origin center."""
        p = Point(200.0, 100.0)
        center = Point(100.0, 100.0)
        rotated = p.rotate_around(center, 90.0)
        assert rotated.x == pytest.approx(100.0, abs=1e-10)
        assert rotated.y == pytest.approx(200.0, abs=1e-10)

    def test_snap_to_grid(self) -> None:
        """Test snapping to grid."""
        p = Point(123.0, 267.0)
        snapped = p.snap_to_grid(50.0)
        assert snapped.x == 100.0
        assert snapped.y == 250.0

    def test_snap_to_grid_rounds_correctly(self) -> None:
        """Test that snap rounds to nearest, not floor."""
        p = Point(126.0, 275.0)
        snapped = p.snap_to_grid(50.0)
        assert snapped.x == 150.0  # 126 is closer to 150 than 100
        assert snapped.y == 300.0  # 275 is closer to 300 than 250

    def test_to_tuple(self) -> None:
        """Test conversion to 2D tuple."""
        p = Point(100.0, 200.0, 50.0)
        t = p.to_tuple()
        assert t == (100.0, 200.0)

    def test_to_tuple_3d(self) -> None:
        """Test conversion to 3D tuple."""
        p = Point(100.0, 200.0, 50.0)
        t = p.to_tuple_3d()
        assert t == (100.0, 200.0, 50.0)

    def test_from_tuple(self) -> None:
        """Test creation from tuple."""
        p = Point.from_tuple((100.0, 200.0))
        assert p.x == 100.0
        assert p.y == 200.0
        assert p.z == 0.0

    def test_immutability(self) -> None:
        """Test that Point is immutable (frozen dataclass)."""
        p = Point(100.0, 200.0)
        with pytest.raises(AttributeError):
            p.x = 300.0  # type: ignore[misc]


class TestBoundingBox:
    """Tests for the BoundingBox class."""

    def test_creation(self) -> None:
        """Test basic bounding box creation."""
        bb = BoundingBox(Point(0.0, 0.0), Point(100.0, 200.0))
        assert bb.min_point == Point(0.0, 0.0)
        assert bb.max_point == Point(100.0, 200.0)

    def test_width_height(self) -> None:
        """Test width and height properties."""
        bb = BoundingBox(Point(50.0, 100.0), Point(250.0, 400.0))
        assert bb.width == 200.0
        assert bb.height == 300.0

    def test_center(self) -> None:
        """Test center calculation."""
        bb = BoundingBox(Point(0.0, 0.0), Point(100.0, 200.0))
        assert bb.center == Point(50.0, 100.0)

    def test_area(self) -> None:
        """Test area calculation."""
        bb = BoundingBox(Point(0.0, 0.0), Point(100.0, 200.0))
        assert bb.area == 20000.0

    def test_contains_point_inside(self) -> None:
        """Test point containment - inside."""
        bb = BoundingBox(Point(0.0, 0.0), Point(100.0, 100.0))
        assert bb.contains_point(Point(50.0, 50.0)) is True

    def test_contains_point_on_edge(self) -> None:
        """Test point containment - on edge (should be inside)."""
        bb = BoundingBox(Point(0.0, 0.0), Point(100.0, 100.0))
        assert bb.contains_point(Point(0.0, 50.0)) is True
        assert bb.contains_point(Point(100.0, 50.0)) is True

    def test_contains_point_outside(self) -> None:
        """Test point containment - outside."""
        bb = BoundingBox(Point(0.0, 0.0), Point(100.0, 100.0))
        assert bb.contains_point(Point(150.0, 50.0)) is False

    def test_intersects_overlapping(self) -> None:
        """Test intersection - overlapping boxes."""
        bb1 = BoundingBox(Point(0.0, 0.0), Point(100.0, 100.0))
        bb2 = BoundingBox(Point(50.0, 50.0), Point(150.0, 150.0))
        assert bb1.intersects(bb2) is True
        assert bb2.intersects(bb1) is True

    def test_intersects_separate(self) -> None:
        """Test intersection - separate boxes."""
        bb1 = BoundingBox(Point(0.0, 0.0), Point(100.0, 100.0))
        bb2 = BoundingBox(Point(200.0, 200.0), Point(300.0, 300.0))
        assert bb1.intersects(bb2) is False

    def test_intersects_touching(self) -> None:
        """Test intersection - touching boxes (edge shared = intersecting)."""
        bb1 = BoundingBox(Point(0.0, 0.0), Point(100.0, 100.0))
        bb2 = BoundingBox(Point(100.0, 0.0), Point(200.0, 100.0))
        # Touching at edge is considered intersection (shared boundary)
        assert bb1.intersects(bb2) is True

    def test_intersects_adjacent_no_touch(self) -> None:
        """Test intersection - adjacent but not touching boxes."""
        bb1 = BoundingBox(Point(0.0, 0.0), Point(100.0, 100.0))
        bb2 = BoundingBox(Point(101.0, 0.0), Point(200.0, 100.0))
        # Gap between boxes - no intersection
        assert bb1.intersects(bb2) is False

    def test_contains_box(self) -> None:
        """Test box containment."""
        outer = BoundingBox(Point(0.0, 0.0), Point(200.0, 200.0))
        inner = BoundingBox(Point(50.0, 50.0), Point(150.0, 150.0))
        assert outer.contains_box(inner) is True
        assert inner.contains_box(outer) is False

    def test_expanded(self) -> None:
        """Test expanding bounding box."""
        bb = BoundingBox(Point(50.0, 50.0), Point(100.0, 100.0))
        expanded = bb.expanded(10.0)
        assert expanded.min_point == Point(40.0, 40.0)
        assert expanded.max_point == Point(110.0, 110.0)

    def test_from_points(self) -> None:
        """Test creating bounding box from points."""
        points = [
            Point(50.0, 20.0),
            Point(10.0, 80.0),
            Point(90.0, 40.0),
        ]
        bb = BoundingBox.from_points(points)
        assert bb.min_point == Point(10.0, 20.0)
        assert bb.max_point == Point(90.0, 80.0)

    def test_from_points_empty(self) -> None:
        """Test creating bounding box from empty list."""
        bb = BoundingBox.from_points([])
        assert bb.min_point == Point.origin()
        assert bb.max_point == Point.origin()

    def test_union(self) -> None:
        """Test union of bounding boxes."""
        boxes = [
            BoundingBox(Point(0.0, 0.0), Point(50.0, 50.0)),
            BoundingBox(Point(100.0, 100.0), Point(200.0, 200.0)),
        ]
        union = BoundingBox.union(boxes)
        assert union.min_point == Point(0.0, 0.0)
        assert union.max_point == Point(200.0, 200.0)


class TestPolygon:
    """Tests for the Polygon class."""

    def test_rectangle_creation(self) -> None:
        """Test rectangle factory method."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 200.0)
        assert len(rect) == 4
        assert rect[0] == Point(0.0, 0.0)
        assert rect[1] == Point(100.0, 0.0)
        assert rect[2] == Point(100.0, 200.0)
        assert rect[3] == Point(0.0, 200.0)

    def test_is_closed(self) -> None:
        """Test is_closed property."""
        poly = Polygon(vertices=[Point(0.0, 0.0), Point(100.0, 0.0)])
        assert poly.is_closed is False

        poly = Polygon(vertices=[
            Point(0.0, 0.0),
            Point(100.0, 0.0),
            Point(50.0, 100.0),
        ])
        assert poly.is_closed is True

    def test_bounding_box(self) -> None:
        """Test bounding box of polygon."""
        poly = Polygon(vertices=[
            Point(10.0, 20.0),
            Point(100.0, 20.0),
            Point(100.0, 80.0),
            Point(10.0, 80.0),
        ])
        bb = poly.bounding_box
        assert bb.min_point == Point(10.0, 20.0)
        assert bb.max_point == Point(100.0, 80.0)

    def test_center(self) -> None:
        """Test centroid calculation."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 100.0)
        center = rect.center
        assert center.x == 50.0
        assert center.y == 50.0

    def test_area_rectangle(self) -> None:
        """Test area of a rectangle."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 200.0)
        # Counter-clockwise vertices give positive area
        assert abs(rect.area) == pytest.approx(20000.0)

    def test_area_triangle(self) -> None:
        """Test area of a triangle."""
        triangle = Polygon(vertices=[
            Point(0.0, 0.0),
            Point(100.0, 0.0),
            Point(50.0, 100.0),
        ])
        # Area = 0.5 * base * height = 0.5 * 100 * 100 = 5000
        assert abs(triangle.area) == pytest.approx(5000.0)

    def test_perimeter_rectangle(self) -> None:
        """Test perimeter of a rectangle."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 200.0)
        assert rect.perimeter == pytest.approx(600.0)  # 2*(100+200)

    def test_perimeter_triangle(self) -> None:
        """Test perimeter of a triangle."""
        triangle = Polygon(vertices=[
            Point(0.0, 0.0),
            Point(300.0, 0.0),
            Point(0.0, 400.0),
        ])
        # 300 + 400 + 500 (3-4-5 triangle scaled)
        assert triangle.perimeter == pytest.approx(1200.0)

    def test_contains_point_inside(self) -> None:
        """Test point inside polygon."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 100.0)
        assert rect.contains_point(Point(50.0, 50.0)) is True

    def test_contains_point_outside(self) -> None:
        """Test point outside polygon."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 100.0)
        assert rect.contains_point(Point(150.0, 50.0)) is False

    def test_contains_point_concave(self) -> None:
        """Test point containment in concave polygon."""
        # L-shaped polygon
        l_shape = Polygon(vertices=[
            Point(0.0, 0.0),
            Point(100.0, 0.0),
            Point(100.0, 50.0),
            Point(50.0, 50.0),
            Point(50.0, 100.0),
            Point(0.0, 100.0),
        ])
        # Inside the L
        assert l_shape.contains_point(Point(25.0, 75.0)) is True
        # In the cutout (outside)
        assert l_shape.contains_point(Point(75.0, 75.0)) is False

    def test_translate(self) -> None:
        """Test polygon translation."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 100.0)
        translated = rect.translate(Point(50.0, 50.0))
        assert translated[0] == Point(50.0, 50.0)
        assert translated[2] == Point(150.0, 150.0)
        # Original unchanged
        assert rect[0] == Point(0.0, 0.0)

    def test_rotate(self) -> None:
        """Test polygon rotation."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 100.0)
        # Rotate 90 degrees around center (50, 50)
        rotated = rect.rotate(90.0)
        # After 90 degree rotation around center, corners should swap
        assert rotated[0].x == pytest.approx(100.0, abs=1e-10)
        assert rotated[0].y == pytest.approx(0.0, abs=1e-10)

    def test_scale(self) -> None:
        """Test polygon scaling."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 100.0)
        scaled = rect.scale(2.0)
        # Scaled around center (50, 50), so corners move outward
        assert scaled[0] == Point(-50.0, -50.0)
        assert scaled[2] == Point(150.0, 150.0)

    def test_iteration(self) -> None:
        """Test iterating over polygon vertices."""
        rect = Polygon.rectangle(0.0, 0.0, 100.0, 100.0)
        vertices = list(rect)
        assert len(vertices) == 4
        assert vertices[0] == Point(0.0, 0.0)


class TestPolyline:
    """Tests for the Polyline class."""

    def test_length_straight_line(self) -> None:
        """Test length of a straight line."""
        line = Polyline(points=[Point(0.0, 0.0), Point(100.0, 0.0)])
        assert line.length == 100.0

    def test_length_multiple_segments(self) -> None:
        """Test length with multiple segments."""
        line = Polyline(points=[
            Point(0.0, 0.0),
            Point(100.0, 0.0),
            Point(100.0, 100.0),
        ])
        assert line.length == 200.0  # 100 + 100

    def test_length_empty(self) -> None:
        """Test length of empty polyline."""
        line = Polyline(points=[])
        assert line.length == 0.0

    def test_length_single_point(self) -> None:
        """Test length of single point polyline."""
        line = Polyline(points=[Point(0.0, 0.0)])
        assert line.length == 0.0

    def test_bounding_box(self) -> None:
        """Test bounding box of polyline."""
        line = Polyline(points=[
            Point(10.0, 20.0),
            Point(100.0, 50.0),
            Point(50.0, 80.0),
        ])
        bb = line.bounding_box
        assert bb.min_point == Point(10.0, 20.0)
        assert bb.max_point == Point(100.0, 80.0)

    def test_len(self) -> None:
        """Test len() on polyline."""
        line = Polyline(points=[Point(0.0, 0.0), Point(100.0, 0.0)])
        assert len(line) == 2
