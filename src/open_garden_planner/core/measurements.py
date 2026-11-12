"""Measurement utilities for calculating area and perimeter of shapes."""

import math

from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core.geometry import Point, Polygon
from open_garden_planner.core.measurement_display import area_text as format_area
from open_garden_planner.core.measurement_display import length_text as format_length
from open_garden_planner.core.units import UnitSystem, nice_distances

__all__ = ["calculate_area_and_perimeter", "format_length", "format_area", "format_scale_distance", "SCALE_BAR_NICE_DISTANCES_CM"]


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

SCALE_BAR_NICE_DISTANCES_CM = nice_distances(UnitSystem.METRIC)


def format_scale_distance(cm: float) -> str:
    from open_garden_planner.core.units import LengthStyle
    return format_length(cm, style=LengthStyle.SCALE_BAR)
