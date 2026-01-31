"""Object type definitions for property objects."""

from dataclasses import dataclass
from enum import Enum, auto

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from .fill_patterns import FillPattern


class StrokeStyle(Enum):
    """Stroke/line styles for object outlines."""

    SOLID = auto()
    DASHED = auto()
    DOTTED = auto()
    DASH_DOT = auto()

    def to_qt_pen_style(self) -> Qt.PenStyle:
        """Convert to Qt pen style.

        Returns:
            Corresponding Qt.PenStyle enum value
        """
        mapping = {
            StrokeStyle.SOLID: Qt.PenStyle.SolidLine,
            StrokeStyle.DASHED: Qt.PenStyle.DashLine,
            StrokeStyle.DOTTED: Qt.PenStyle.DotLine,
            StrokeStyle.DASH_DOT: Qt.PenStyle.DashDotLine,
        }
        return mapping[self]


class ObjectType(Enum):
    """Types of property objects in the garden planner."""

    # Polygon-based structures
    HOUSE = auto()
    GARAGE_SHED = auto()
    TERRACE_PATIO = auto()
    DRIVEWAY = auto()
    POND_POOL = auto()
    GREENHOUSE = auto()
    GARDEN_BED = auto()

    # Polyline-based structures
    FENCE = auto()
    WALL = auto()
    PATH = auto()

    # Plant types (circle-based)
    TREE = auto()
    SHRUB = auto()
    PERENNIAL = auto()

    # Generic geometric shapes (for backwards compatibility)
    GENERIC_RECTANGLE = auto()
    GENERIC_POLYGON = auto()
    GENERIC_CIRCLE = auto()


@dataclass(frozen=True)
class ObjectStyle:
    """Styling configuration for an object type."""

    fill_color: QColor
    stroke_color: QColor
    stroke_width: float
    display_name: str
    fill_pattern: FillPattern = FillPattern.SOLID
    stroke_style: StrokeStyle = StrokeStyle.SOLID


# Default styles for each object type
OBJECT_STYLES: dict[ObjectType, ObjectStyle] = {
    ObjectType.HOUSE: ObjectStyle(
        fill_color=QColor(210, 180, 140, 120),  # Tan
        stroke_color=QColor(139, 90, 43),  # Brown
        stroke_width=2.5,
        display_name="House",
        fill_pattern=FillPattern.ROOF_TILES,
    ),
    ObjectType.GARAGE_SHED: ObjectStyle(
        fill_color=QColor(169, 169, 169, 120),  # Gray
        stroke_color=QColor(105, 105, 105),  # Dim gray
        stroke_width=2.0,
        display_name="Garage/Shed",
        fill_pattern=FillPattern.CONCRETE,
    ),
    ObjectType.TERRACE_PATIO: ObjectStyle(
        fill_color=QColor(222, 184, 135, 120),  # Burlywood
        stroke_color=QColor(160, 82, 45),  # Sienna
        stroke_width=2.0,
        display_name="Terrace/Patio",
        fill_pattern=FillPattern.WOOD,
    ),
    ObjectType.DRIVEWAY: ObjectStyle(
        fill_color=QColor(112, 128, 144, 120),  # Slate gray
        stroke_color=QColor(47, 79, 79),  # Dark slate gray
        stroke_width=2.0,
        display_name="Driveway",
        fill_pattern=FillPattern.GRAVEL,
    ),
    ObjectType.POND_POOL: ObjectStyle(
        fill_color=QColor(64, 164, 223, 120),  # Water blue
        stroke_color=QColor(25, 25, 112),  # Midnight blue
        stroke_width=2.0,
        display_name="Pond/Pool",
        fill_pattern=FillPattern.WATER,
    ),
    ObjectType.GREENHOUSE: ObjectStyle(
        fill_color=QColor(240, 255, 240, 80),  # Honeydew (transparent)
        stroke_color=QColor(34, 139, 34),  # Forest green
        stroke_width=2.5,
        display_name="Greenhouse",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.GARDEN_BED: ObjectStyle(
        fill_color=QColor(139, 90, 43, 120),  # Brown soil
        stroke_color=QColor(34, 139, 34),  # Forest green border
        stroke_width=2.5,
        display_name="Garden Bed",
        fill_pattern=FillPattern.SOIL,
    ),
    ObjectType.TREE: ObjectStyle(
        fill_color=QColor(34, 139, 34, 100),  # Forest green
        stroke_color=QColor(85, 107, 47),  # Dark olive green
        stroke_width=3.0,
        display_name="Tree",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.SHRUB: ObjectStyle(
        fill_color=QColor(107, 142, 35, 120),  # Olive drab
        stroke_color=QColor(85, 107, 47),  # Dark olive green
        stroke_width=2.5,
        display_name="Shrub",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.PERENNIAL: ObjectStyle(
        fill_color=QColor(154, 205, 50, 100),  # Yellow green
        stroke_color=QColor(34, 139, 34),  # Forest green
        stroke_width=2.0,
        display_name="Perennial",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.FENCE: ObjectStyle(
        fill_color=QColor(139, 69, 19, 0),  # Brown (no fill for lines)
        stroke_color=QColor(139, 69, 19),  # Saddle brown
        stroke_width=3.0,
        display_name="Fence",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.WALL: ObjectStyle(
        fill_color=QColor(128, 128, 128, 0),  # Gray (no fill for lines)
        stroke_color=QColor(105, 105, 105),  # Dim gray
        stroke_width=4.0,
        display_name="Wall",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.PATH: ObjectStyle(
        fill_color=QColor(210, 180, 140, 0),  # Tan (no fill for lines)
        stroke_color=QColor(160, 82, 45),  # Sienna
        stroke_width=5.0,
        display_name="Path",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.GENERIC_RECTANGLE: ObjectStyle(
        fill_color=QColor(144, 238, 144, 100),  # Light green
        stroke_color=QColor(34, 139, 34),  # Forest green
        stroke_width=2.0,
        display_name="Rectangle",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.GENERIC_POLYGON: ObjectStyle(
        fill_color=QColor(173, 216, 230, 100),  # Light blue
        stroke_color=QColor(70, 130, 180),  # Steel blue
        stroke_width=2.0,
        display_name="Polygon",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.GENERIC_CIRCLE: ObjectStyle(
        fill_color=QColor(255, 182, 193, 100),  # Light pink
        stroke_color=QColor(219, 112, 147),  # Pale violet red
        stroke_width=2.0,
        display_name="Circle",
        fill_pattern=FillPattern.SOLID,
    ),
}


def get_style(object_type: ObjectType) -> ObjectStyle:
    """Get the default style for an object type."""
    return OBJECT_STYLES[object_type]
