"""Tests for measurement utilities."""

import math

from PyQt6.QtCore import QPointF

from open_garden_planner.core.measurements import (
    calculate_area_and_perimeter,
    format_area,
    format_length,
)
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem


def test_rectangle_measurements(qtbot):
    """Test area and perimeter calculation for rectangles."""
    # Create a 100cm x 200cm rectangle
    rect = RectangleItem(0, 0, 100, 200)

    result = calculate_area_and_perimeter(rect)
    assert result is not None

    area, perimeter = result
    assert area == 20000  # 100 * 200 = 20000 cm²
    assert perimeter == 600  # 2 * (100 + 200) = 600 cm


def test_polygon_measurements(qtbot):
    """Test area and perimeter calculation for polygons."""
    # Create a square polygon: 100cm x 100cm
    vertices = [
        QPointF(0, 0),
        QPointF(100, 0),
        QPointF(100, 100),
        QPointF(0, 100),
    ]
    polygon = PolygonItem(vertices)

    result = calculate_area_and_perimeter(polygon)
    assert result is not None

    area, perimeter = result
    assert abs(area - 10000) < 0.01  # 100 * 100 = 10000 cm²
    assert abs(perimeter - 400) < 0.01  # 4 * 100 = 400 cm


def test_circle_measurements(qtbot):
    """Test area and circumference calculation for circles."""
    # Create a circle with radius 50cm
    circle = CircleItem(center_x=100, center_y=100, radius=50)

    result = calculate_area_and_perimeter(circle)
    assert result is not None

    area, circumference = result
    expected_area = math.pi * 50 * 50  # π * r²
    expected_circumference = 2 * math.pi * 50  # 2 * π * r

    assert abs(area - expected_area) < 0.01
    assert abs(circumference - expected_circumference) < 0.01


def test_triangle_polygon_measurements(qtbot):
    """Test area and perimeter for a triangular polygon."""
    # Create a right triangle: base=30cm, height=40cm
    vertices = [
        QPointF(0, 0),
        QPointF(30, 0),
        QPointF(0, 40),
    ]
    polygon = PolygonItem(vertices)

    result = calculate_area_and_perimeter(polygon)
    assert result is not None

    area, perimeter = result
    # Area of right triangle = (base * height) / 2 = (30 * 40) / 2 = 600
    assert abs(area - 600) < 0.01
    # Perimeter = 30 + 40 + hypotenuse = 30 + 40 + 50 = 120
    assert abs(perimeter - 120) < 0.01


def test_format_area_small():
    """Test area formatting for values less than 1 m²."""
    # Small area in cm²
    assert format_area(500.0) == "500.0 cm²"
    assert format_area(9999.9) == "9999.9 cm²"


def test_format_area_large():
    """Test area formatting for values >= 1 m²."""
    # Large area in m²
    assert format_area(10000.0) == "1.00 m²"
    assert format_area(23500.0) == "2.35 m²"
    assert format_area(100000.0) == "10.00 m²"


def test_format_length_small():
    """Test length formatting for values less than 1 m."""
    # Small length in cm
    assert format_length(50.0) == "50.0 cm"
    assert format_length(99.9) == "99.9 cm"


def test_format_length_large():
    """Test length formatting for values >= 1 m."""
    # Large length in m
    assert format_length(100.0) == "1.00 m"
    assert format_length(235.5) == "2.35 m"
    assert format_length(1000.0) == "10.00 m"


def test_unsupported_item_type(qtbot):
    """Test that unsupported item types return None."""
    from PyQt6.QtWidgets import QGraphicsEllipseItem

    # Create an item that's not RectangleItem, PolygonItem, or CircleItem
    ellipse = QGraphicsEllipseItem(0, 0, 100, 50)

    result = calculate_area_and_perimeter(ellipse)
    assert result is None


def test_clockwise_polygon_measurements(qtbot):
    """Test that area is absolute value regardless of vertex order."""
    # Create a square with clockwise vertices
    vertices_cw = [
        QPointF(0, 0),
        QPointF(0, 100),
        QPointF(100, 100),
        QPointF(100, 0),
    ]
    polygon_cw = PolygonItem(vertices_cw)

    # Create a square with counter-clockwise vertices
    vertices_ccw = [
        QPointF(0, 0),
        QPointF(100, 0),
        QPointF(100, 100),
        QPointF(0, 100),
    ]
    polygon_ccw = PolygonItem(vertices_ccw)

    result_cw = calculate_area_and_perimeter(polygon_cw)
    result_ccw = calculate_area_and_perimeter(polygon_ccw)

    assert result_cw is not None
    assert result_ccw is not None

    # Both should have the same positive area
    area_cw, _ = result_cw
    area_ccw, _ = result_ccw

    assert abs(area_cw - 10000) < 0.01
    assert abs(area_ccw - 10000) < 0.01
