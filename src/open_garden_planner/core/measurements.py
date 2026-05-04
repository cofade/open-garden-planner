"""Measurement utilities for calculating area and perimeter of shapes."""

import math

from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.geometry import Point, Polygon


def calculate_area_and_perimeter(item: QGraphicsItem) -> tuple[float, float] | None:
    """Calculate area and perimeter/circumference for a graphics item.

    Args:
        item: The graphics item to measure

    Returns:
        Tuple of (area_cm2, perimeter_cm) or None if item type not supported.
        For circles, perimeter is the circumference.
    """
    # Import here to avoid circular dependency
    from open_garden_planner.ui.canvas.items import (
        CircleItem,
        EllipseItem,
        PolygonItem,
        RectangleItem,
    )

    if isinstance(item, RectangleItem):
        rect = item.rect()
        width = rect.width()
        height = rect.height()
        area = width * height
        perimeter = 2 * (width + height)
        return (area, perimeter)

    elif isinstance(item, PolygonItem):
        qt_polygon = item.polygon()
        # Convert QPolygonF to our Polygon primitive
        vertices = [
            Point(qt_polygon.at(i).x(), qt_polygon.at(i).y())
            for i in range(qt_polygon.count())
        ]
        polygon = Polygon(vertices=vertices)
        # Use absolute value for area (handles CW/CCW vertex order)
        return (abs(polygon.area), polygon.perimeter)

    elif isinstance(item, CircleItem):
        radius = item.radius
        area = math.pi * radius * radius
        circumference = 2 * math.pi * radius
        return (area, circumference)

    elif isinstance(item, EllipseItem):
        # Semi-axes from the bounding rect (US-12.10/F9).
        rect = item.rect()
        a = rect.width() / 2.0
        b = rect.height() / 2.0
        area = math.pi * a * b
        # Ramanujan's second approximation — accurate to <0.001% even for
        # extreme aspect ratios; closed-form integral is unnecessary here.
        h = ((a - b) ** 2) / ((a + b) ** 2) if (a + b) > 0 else 0.0
        perimeter = math.pi * (a + b) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h)))
        return (area, perimeter)

    return None


def format_area(area_cm2: float) -> str:
    """Format area for display with appropriate units.

    Args:
        area_cm2: Area in square centimeters

    Returns:
        Formatted string (e.g., "2.35 m²", "45.2 cm²")
    """
    if area_cm2 >= 10000:  # >= 1 m²
        area_m2 = area_cm2 / 10000
        return f"{area_m2:.2f} m²"
    else:
        return f"{area_cm2:.1f} cm²"


def format_length(length_cm: float) -> str:
    """Format length for display with appropriate units.

    Args:
        length_cm: Length in centimeters

    Returns:
        Formatted string (e.g., "2.35 m", "45.2 cm")
    """
    if length_cm >= 100:  # >= 1 m
        length_m = length_cm / 100
        return f"{length_m:.2f} m"
    else:
        return f"{length_cm:.1f} cm"
