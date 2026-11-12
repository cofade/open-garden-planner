"""Measurement utilities for calculating area and perimeter of shapes."""

import math

from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.geometry import Point, Polygon
from open_garden_planner.core.i18n import format_decimal, format_trimmed


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


# The round distances a scale bar may show, in cm, ascending. The canvas's bar
# and the PDF report's bar both pick from this one list (#782).
SCALE_BAR_NICE_DISTANCES_CM: tuple[int, ...] = (
    1,
    2,
    5,
    10,
    20,
    50,
    100,
    200,
    500,
    1000,
    2000,
    5000,
    10000,
)


def format_scale_distance(cm: float) -> str:
    """A scale bar's label for a distance in cm: "50 cm", "2 m", "1.5 km"."""
    if cm >= 100000:
        return f"{format_trimmed(cm / 100000)} km"
    if cm >= 100:
        return f"{format_trimmed(cm / 100)} m"
    return f"{format_trimmed(cm)} cm"


def format_area(area_cm2: float) -> str:
    """Format area for display with appropriate units.

    Args:
        area_cm2: Area in square centimeters

    Returns:
        Formatted string in the UI language's number format
        (e.g., "2.35 m²", "45.2 cm²"; "2,35 m²" in German)
    """
    if area_cm2 >= 10000:  # >= 1 m²
        area_m2 = area_cm2 / 10000
        return f"{format_decimal(area_m2, 2)} m²"
    else:
        return f"{format_decimal(area_cm2, 1)} cm²"


def format_length(length_cm: float) -> str:
    """Format length for display with appropriate units.

    Args:
        length_cm: Length in centimeters

    Returns:
        Formatted string in the UI language's number format
        (e.g., "2.35 m", "45.2 cm"; "2,35 m" in German)
    """
    if length_cm >= 100:  # >= 1 m
        length_m = length_cm / 100
        return f"{format_decimal(length_m, 2)} m"
    else:
        return f"{format_decimal(length_cm, 1)} cm"
