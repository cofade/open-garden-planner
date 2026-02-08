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
    LAWN = auto()

    # Polyline-based structures
    FENCE = auto()
    WALL = auto()
    PATH = auto()

    # Plant types (circle-based)
    TREE = auto()
    SHRUB = auto()
    PERENNIAL = auto()

    # Hedge section (rectangle-based, SVG-rendered)
    HEDGE_SECTION = auto()

    # Outdoor furniture (rectangle-based, SVG-rendered)
    TABLE_RECTANGULAR = auto()
    TABLE_ROUND = auto()
    CHAIR = auto()
    BENCH = auto()
    PARASOL = auto()
    LOUNGER = auto()
    BBQ_GRILL = auto()
    FIRE_PIT = auto()
    PLANTER_POT = auto()

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
        fill_color=QColor(210, 230, 245, 140),  # Light sky-blue glass
        stroke_color=QColor(160, 165, 170),  # Silver / aluminium
        stroke_width=2.5,
        display_name="Greenhouse",
        fill_pattern=FillPattern.GLASS,
    ),
    ObjectType.GARDEN_BED: ObjectStyle(
        fill_color=QColor(139, 90, 43, 120),  # Brown soil
        stroke_color=QColor(34, 139, 34),  # Forest green border
        stroke_width=2.5,
        display_name="Garden Bed",
        fill_pattern=FillPattern.SOIL,
    ),
    ObjectType.LAWN: ObjectStyle(
        fill_color=QColor(100, 180, 60, 120),  # Fresh green
        stroke_color=QColor(60, 130, 30),  # Darker green
        stroke_width=2.0,
        display_name="Lawn",
        fill_pattern=FillPattern.GRASS,
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
    ObjectType.HEDGE_SECTION: ObjectStyle(
        fill_color=QColor(60, 120, 40, 180),  # Hedge green
        stroke_color=QColor(40, 90, 25),  # Dark hedge green
        stroke_width=1.5,
        display_name="Hedge Section",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.TABLE_RECTANGULAR: ObjectStyle(
        fill_color=QColor(160, 120, 80, 180),  # Warm wood
        stroke_color=QColor(100, 70, 40),  # Dark wood
        stroke_width=1.5,
        display_name="Table (Rectangular)",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.TABLE_ROUND: ObjectStyle(
        fill_color=QColor(160, 120, 80, 180),  # Warm wood
        stroke_color=QColor(100, 70, 40),  # Dark wood
        stroke_width=1.5,
        display_name="Table (Round)",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.CHAIR: ObjectStyle(
        fill_color=QColor(140, 105, 70, 180),  # Medium wood
        stroke_color=QColor(90, 60, 30),  # Dark wood
        stroke_width=1.5,
        display_name="Chair",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.BENCH: ObjectStyle(
        fill_color=QColor(150, 110, 70, 180),  # Wood
        stroke_color=QColor(90, 60, 30),  # Dark wood
        stroke_width=1.5,
        display_name="Bench",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.PARASOL: ObjectStyle(
        fill_color=QColor(230, 220, 200, 160),  # Cream/beige
        stroke_color=QColor(180, 160, 130),  # Warm gray
        stroke_width=1.5,
        display_name="Parasol",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.LOUNGER: ObjectStyle(
        fill_color=QColor(180, 180, 180, 180),  # Light gray metal
        stroke_color=QColor(120, 120, 120),  # Medium gray
        stroke_width=1.5,
        display_name="Lounger",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.BBQ_GRILL: ObjectStyle(
        fill_color=QColor(60, 60, 60, 200),  # Dark charcoal
        stroke_color=QColor(40, 40, 40),  # Near black
        stroke_width=1.5,
        display_name="BBQ/Grill",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.FIRE_PIT: ObjectStyle(
        fill_color=QColor(140, 100, 70, 180),  # Stone brown
        stroke_color=QColor(80, 60, 40),  # Dark brown
        stroke_width=1.5,
        display_name="Fire Pit",
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.PLANTER_POT: ObjectStyle(
        fill_color=QColor(180, 120, 60, 180),  # Terracotta
        stroke_color=QColor(140, 80, 30),  # Dark terracotta
        stroke_width=1.5,
        display_name="Planter/Pot",
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
