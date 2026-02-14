"""Object type definitions for property objects."""

from dataclasses import dataclass
from enum import Enum, auto

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication, Qt
from PyQt6.QtGui import QColor

from .fill_patterns import FillPattern


class PathFenceStyle(Enum):
    """Visual style presets for path and fence polylines."""

    # Path styles
    NONE = auto()  # Plain line (no style preset)
    GRAVEL_PATH = auto()
    STEPPING_STONES = auto()
    PAVED_PATH = auto()
    WOODEN_BOARDWALK = auto()
    DIRT_PATH = auto()

    # Fence styles
    WOODEN_FENCE = auto()
    METAL_FENCE = auto()
    CHAIN_LINK = auto()
    HEDGE_FENCE = auto()
    STONE_WALL = auto()


@dataclass(frozen=True)
class PathFenceStyleInfo:
    """Display info for a path/fence style preset."""

    display_name: str
    category: str  # "path" or "fence"
    stroke_color: QColor
    stroke_width: float
    description: str = ""


# Style presets with default visual properties
PATH_FENCE_STYLES: dict[PathFenceStyle, PathFenceStyleInfo] = {
    PathFenceStyle.NONE: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("None (Plain)"),
        category="",
        stroke_color=QColor(160, 82, 45),
        stroke_width=3.0,
    ),
    PathFenceStyle.GRAVEL_PATH: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Gravel"),
        category="path",
        stroke_color=QColor(180, 170, 150),
        stroke_width=8.0,
    ),
    PathFenceStyle.STEPPING_STONES: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Stepping Stones"),
        category="path",
        stroke_color=QColor(160, 160, 155),
        stroke_width=6.0,
    ),
    PathFenceStyle.PAVED_PATH: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Paved"),
        category="path",
        stroke_color=QColor(140, 140, 140),
        stroke_width=10.0,
    ),
    PathFenceStyle.WOODEN_BOARDWALK: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Wooden Boardwalk"),
        category="path",
        stroke_color=QColor(160, 120, 70),
        stroke_width=10.0,
    ),
    PathFenceStyle.DIRT_PATH: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Dirt"),
        category="path",
        stroke_color=QColor(150, 110, 60),
        stroke_width=6.0,
    ),
    PathFenceStyle.WOODEN_FENCE: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Wooden Fence"),
        category="fence",
        stroke_color=QColor(139, 90, 43),
        stroke_width=3.0,
    ),
    PathFenceStyle.METAL_FENCE: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Metal/Wrought Iron"),
        category="fence",
        stroke_color=QColor(60, 60, 60),
        stroke_width=2.5,
    ),
    PathFenceStyle.CHAIN_LINK: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Chain Link"),
        category="fence",
        stroke_color=QColor(160, 165, 170),
        stroke_width=2.0,
    ),
    PathFenceStyle.HEDGE_FENCE: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Hedge"),
        category="fence",
        stroke_color=QColor(60, 120, 40),
        stroke_width=8.0,
    ),
    PathFenceStyle.STONE_WALL: PathFenceStyleInfo(
        display_name=QT_TR_NOOP("Stone Wall"),
        category="fence",
        stroke_color=QColor(130, 130, 120),
        stroke_width=5.0,
    ),
}


def get_path_fence_style_info(style: PathFenceStyle) -> PathFenceStyleInfo:
    """Get display info for a path/fence style."""
    return PATH_FENCE_STYLES[style]


def get_translated_path_fence_style_name(style: PathFenceStyle) -> str:
    """Get the translated display name for a path/fence style."""
    info = PATH_FENCE_STYLES[style]
    return QCoreApplication.translate("PathFenceStyle", info.display_name)


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

    # Garden infrastructure (SVG-rendered)
    RAISED_BED = auto()
    COMPOST_BIN = auto()
    COLD_FRAME = auto()
    RAIN_BARREL = auto()
    WATER_TAP = auto()
    TOOL_SHED = auto()

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
        fill_color=QColor(210, 180, 140, 255),  # Tan
        stroke_color=QColor(139, 90, 43),  # Brown
        stroke_width=2.5,
        display_name=QT_TR_NOOP("House"),
        fill_pattern=FillPattern.ROOF_TILES,
    ),
    ObjectType.GARAGE_SHED: ObjectStyle(
        fill_color=QColor(169, 169, 169, 255),  # Gray
        stroke_color=QColor(105, 105, 105),  # Dim gray
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Garage/Shed"),
        fill_pattern=FillPattern.CONCRETE,
    ),
    ObjectType.TERRACE_PATIO: ObjectStyle(
        fill_color=QColor(222, 184, 135, 255),  # Burlywood
        stroke_color=QColor(160, 82, 45),  # Sienna
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Terrace/Patio"),
        fill_pattern=FillPattern.WOOD,
    ),
    ObjectType.DRIVEWAY: ObjectStyle(
        fill_color=QColor(112, 128, 144, 255),  # Slate gray
        stroke_color=QColor(47, 79, 79),  # Dark slate gray
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Driveway"),
        fill_pattern=FillPattern.GRAVEL,
    ),
    ObjectType.POND_POOL: ObjectStyle(
        fill_color=QColor(64, 164, 223, 255),  # Water blue
        stroke_color=QColor(25, 25, 112),  # Midnight blue
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Pond/Pool"),
        fill_pattern=FillPattern.WATER,
    ),
    ObjectType.GREENHOUSE: ObjectStyle(
        fill_color=QColor(210, 230, 245, 255),  # Light sky-blue glass
        stroke_color=QColor(160, 165, 170),  # Silver / aluminium
        stroke_width=2.5,
        display_name=QT_TR_NOOP("Greenhouse"),
        fill_pattern=FillPattern.GLASS,
    ),
    ObjectType.GARDEN_BED: ObjectStyle(
        fill_color=QColor(139, 90, 43, 255),  # Brown soil
        stroke_color=QColor(34, 139, 34),  # Forest green border
        stroke_width=2.5,
        display_name=QT_TR_NOOP("Garden Bed"),
        fill_pattern=FillPattern.SOIL,
    ),
    ObjectType.LAWN: ObjectStyle(
        fill_color=QColor(100, 180, 60, 255),  # Fresh green
        stroke_color=QColor(60, 130, 30),  # Darker green
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Lawn"),
        fill_pattern=FillPattern.GRASS,
    ),
    ObjectType.TREE: ObjectStyle(
        fill_color=QColor(34, 139, 34, 255),  # Forest green
        stroke_color=QColor(85, 107, 47),  # Dark olive green
        stroke_width=3.0,
        display_name=QT_TR_NOOP("Tree"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.SHRUB: ObjectStyle(
        fill_color=QColor(107, 142, 35, 255),  # Olive drab
        stroke_color=QColor(85, 107, 47),  # Dark olive green
        stroke_width=2.5,
        display_name=QT_TR_NOOP("Shrub"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.PERENNIAL: ObjectStyle(
        fill_color=QColor(154, 205, 50, 255),  # Yellow green
        stroke_color=QColor(34, 139, 34),  # Forest green
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Perennial"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.FENCE: ObjectStyle(
        fill_color=QColor(139, 69, 19, 0),  # Brown (no fill for lines)
        stroke_color=QColor(139, 69, 19),  # Saddle brown
        stroke_width=3.0,
        display_name=QT_TR_NOOP("Fence"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.WALL: ObjectStyle(
        fill_color=QColor(128, 128, 128, 0),  # Gray (no fill for lines)
        stroke_color=QColor(105, 105, 105),  # Dim gray
        stroke_width=4.0,
        display_name=QT_TR_NOOP("Wall"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.PATH: ObjectStyle(
        fill_color=QColor(210, 180, 140, 0),  # Tan (no fill for lines)
        stroke_color=QColor(160, 82, 45),  # Sienna
        stroke_width=5.0,
        display_name=QT_TR_NOOP("Path"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.HEDGE_SECTION: ObjectStyle(
        fill_color=QColor(60, 120, 40, 255),  # Hedge green
        stroke_color=QColor(40, 90, 25),  # Dark hedge green
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Hedge Section"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.TABLE_RECTANGULAR: ObjectStyle(
        fill_color=QColor(160, 120, 80, 255),  # Warm wood
        stroke_color=QColor(100, 70, 40),  # Dark wood
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Table (Rectangular)"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.TABLE_ROUND: ObjectStyle(
        fill_color=QColor(160, 120, 80, 255),  # Warm wood
        stroke_color=QColor(100, 70, 40),  # Dark wood
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Table (Round)"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.CHAIR: ObjectStyle(
        fill_color=QColor(140, 105, 70, 255),  # Medium wood
        stroke_color=QColor(90, 60, 30),  # Dark wood
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Chair"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.BENCH: ObjectStyle(
        fill_color=QColor(150, 110, 70, 255),  # Wood
        stroke_color=QColor(90, 60, 30),  # Dark wood
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Bench"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.PARASOL: ObjectStyle(
        fill_color=QColor(230, 220, 200, 255),  # Cream/beige
        stroke_color=QColor(180, 160, 130),  # Warm gray
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Parasol"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.LOUNGER: ObjectStyle(
        fill_color=QColor(180, 180, 180, 255),  # Light gray metal
        stroke_color=QColor(120, 120, 120),  # Medium gray
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Lounger"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.BBQ_GRILL: ObjectStyle(
        fill_color=QColor(60, 60, 60, 255),  # Dark charcoal
        stroke_color=QColor(40, 40, 40),  # Near black
        stroke_width=1.5,
        display_name=QT_TR_NOOP("BBQ/Grill"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.FIRE_PIT: ObjectStyle(
        fill_color=QColor(140, 100, 70, 255),  # Stone brown
        stroke_color=QColor(80, 60, 40),  # Dark brown
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Fire Pit"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.PLANTER_POT: ObjectStyle(
        fill_color=QColor(180, 120, 60, 255),  # Terracotta
        stroke_color=QColor(140, 80, 30),  # Dark terracotta
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Planter/Pot"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.RAISED_BED: ObjectStyle(
        fill_color=QColor(139, 90, 43, 255),  # Wood brown
        stroke_color=QColor(100, 60, 20),  # Dark wood
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Raised Bed"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.COMPOST_BIN: ObjectStyle(
        fill_color=QColor(90, 70, 40, 255),  # Dark brown
        stroke_color=QColor(60, 45, 25),  # Very dark brown
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Compost Bin"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.COLD_FRAME: ObjectStyle(
        fill_color=QColor(200, 220, 240, 255),  # Light glass blue
        stroke_color=QColor(150, 155, 160),  # Silver aluminum
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Cold Frame"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.RAIN_BARREL: ObjectStyle(
        fill_color=QColor(60, 100, 60, 255),  # Dark green
        stroke_color=QColor(40, 70, 40),  # Darker green
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Rain Barrel"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.WATER_TAP: ObjectStyle(
        fill_color=QColor(160, 170, 180, 255),  # Steel gray
        stroke_color=QColor(100, 110, 120),  # Dark steel
        stroke_width=1.5,
        display_name=QT_TR_NOOP("Water Tap"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.TOOL_SHED: ObjectStyle(
        fill_color=QColor(160, 130, 90, 255),  # Light wood
        stroke_color=QColor(100, 75, 45),  # Dark wood
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Tool Shed"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.GENERIC_RECTANGLE: ObjectStyle(
        fill_color=QColor(144, 238, 144, 255),  # Light green
        stroke_color=QColor(34, 139, 34),  # Forest green
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Rectangle"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.GENERIC_POLYGON: ObjectStyle(
        fill_color=QColor(173, 216, 230, 255),  # Light blue
        stroke_color=QColor(70, 130, 180),  # Steel blue
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Polygon"),
        fill_pattern=FillPattern.SOLID,
    ),
    ObjectType.GENERIC_CIRCLE: ObjectStyle(
        fill_color=QColor(255, 182, 193, 255),  # Light pink
        stroke_color=QColor(219, 112, 147),  # Pale violet red
        stroke_width=2.0,
        display_name=QT_TR_NOOP("Circle"),
        fill_pattern=FillPattern.SOLID,
    ),
}


def get_style(object_type: ObjectType) -> ObjectStyle:
    """Get the default style for an object type."""
    return OBJECT_STYLES[object_type]


def get_translated_display_name(object_type: ObjectType) -> str:
    """Get the translated display name for an object type.

    Uses QCoreApplication.translate() to look up the translation
    at display time. The source strings are marked with QT_TR_NOOP()
    in OBJECT_STYLES for extraction by pylupdate6.
    """
    style = OBJECT_STYLES[object_type]
    return QCoreApplication.translate("ObjectType", style.display_name)
