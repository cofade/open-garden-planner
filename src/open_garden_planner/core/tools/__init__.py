"""Lazy public compatibility exports (audit A4)."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .arc_tool import ArcTool
    from .base_tool import BaseTool, ToolType
    from .bezier_tool import BezierTool
    from .callout_tool import CalloutTool
    from .chamfer_tool import ChamferTool
    from .circle_tool import CircleTool
    from .constraint_tool import (
        AngleConstraintTool,
        CoincidentConstraintTool,
        ConstraintTool,
        EdgeLengthConstraintTool,
        EqualConstraintTool,
        FixedConstraintTool,
        HorizontalConstraintTool,
        HorizontalDistanceConstraintTool,
        ParallelConstraintTool,
        PerpendicularConstraintTool,
        SymmetryConstraintTool,
        VerticalConstraintTool,
        VerticalDistanceConstraintTool,
    )
    from .construction_tool import ConstructionCircleTool, ConstructionLineTool
    from .ellipse_tool import EllipseTool
    from .fillet_tool import FilletTool
    from .journal_pin_tool import JournalPinTool
    from .measure_tool import MeasureTool
    from .mirror_tool import MirrorTool
    from .offset_tool import OffsetTool
    from .polygon_tool import PolygonTool
    from .polyline_tool import PolylineTool
    from .rectangle_tool import RectangleTool
    from .select_tool import SelectTool
    from .text_tool import TextTool
    from .tool_manager import ToolManager
    from .trim_tool import TrimExtendTool

    __all__ = [
        "AngleConstraintTool",
        "ArcTool",
        "BaseTool",
        "BezierTool",
        "CalloutTool",
        "ChamferTool",
        "CircleTool",
        "CoincidentConstraintTool",
        "ConstraintTool",
        "EdgeLengthConstraintTool",
        "EllipseTool",
        "EqualConstraintTool",
        "FilletTool",
        "FixedConstraintTool",
        "ConstructionCircleTool",
        "ConstructionLineTool",
        "HorizontalConstraintTool",
        "HorizontalDistanceConstraintTool",
        "JournalPinTool",
        "MeasureTool",
        "MirrorTool",
        "OffsetTool",
        "ParallelConstraintTool",
        "PerpendicularConstraintTool",
        "PolygonTool",
        "PolylineTool",
        "RectangleTool",
        "SelectTool",
        "SymmetryConstraintTool",
        "TextTool",
        "ToolManager",
        "ToolType",
        "TrimExtendTool",
        "VerticalConstraintTool",
        "VerticalDistanceConstraintTool",
    ]

_EXPORTS = {
    "ArcTool": ("open_garden_planner.core.tools.arc_tool", "ArcTool"),
    "BaseTool": ("open_garden_planner.core.tools.base_tool", "BaseTool"),
    "ToolType": ("open_garden_planner.core.tools.base_tool", "ToolType"),
    "BezierTool": ("open_garden_planner.core.tools.bezier_tool", "BezierTool"),
    "CalloutTool": ("open_garden_planner.core.tools.callout_tool", "CalloutTool"),
    "ChamferTool": ("open_garden_planner.core.tools.chamfer_tool", "ChamferTool"),
    "CircleTool": ("open_garden_planner.core.tools.circle_tool", "CircleTool"),
    "AngleConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "AngleConstraintTool",
    ),
    "CoincidentConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "CoincidentConstraintTool",
    ),
    "ConstraintTool": ("open_garden_planner.core.tools.constraint_tool", "ConstraintTool"),
    "EdgeLengthConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "EdgeLengthConstraintTool",
    ),
    "EqualConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "EqualConstraintTool",
    ),
    "FixedConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "FixedConstraintTool",
    ),
    "HorizontalConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "HorizontalConstraintTool",
    ),
    "HorizontalDistanceConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "HorizontalDistanceConstraintTool",
    ),
    "ParallelConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "ParallelConstraintTool",
    ),
    "PerpendicularConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "PerpendicularConstraintTool",
    ),
    "SymmetryConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "SymmetryConstraintTool",
    ),
    "VerticalConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "VerticalConstraintTool",
    ),
    "VerticalDistanceConstraintTool": (
        "open_garden_planner.core.tools.constraint_tool",
        "VerticalDistanceConstraintTool",
    ),
    "ConstructionCircleTool": (
        "open_garden_planner.core.tools.construction_tool",
        "ConstructionCircleTool",
    ),
    "ConstructionLineTool": (
        "open_garden_planner.core.tools.construction_tool",
        "ConstructionLineTool",
    ),
    "EllipseTool": ("open_garden_planner.core.tools.ellipse_tool", "EllipseTool"),
    "FilletTool": ("open_garden_planner.core.tools.fillet_tool", "FilletTool"),
    "JournalPinTool": ("open_garden_planner.core.tools.journal_pin_tool", "JournalPinTool"),
    "MeasureTool": ("open_garden_planner.core.tools.measure_tool", "MeasureTool"),
    "MirrorTool": ("open_garden_planner.core.tools.mirror_tool", "MirrorTool"),
    "OffsetTool": ("open_garden_planner.core.tools.offset_tool", "OffsetTool"),
    "PolygonTool": ("open_garden_planner.core.tools.polygon_tool", "PolygonTool"),
    "PolylineTool": ("open_garden_planner.core.tools.polyline_tool", "PolylineTool"),
    "RectangleTool": ("open_garden_planner.core.tools.rectangle_tool", "RectangleTool"),
    "SelectTool": ("open_garden_planner.core.tools.select_tool", "SelectTool"),
    "TextTool": ("open_garden_planner.core.tools.text_tool", "TextTool"),
    "ToolManager": ("open_garden_planner.core.tools.tool_manager", "ToolManager"),
    "TrimExtendTool": ("open_garden_planner.core.tools.trim_tool", "TrimExtendTool"),
}

__all__ = [
    "AngleConstraintTool",
    "ArcTool",
    "BaseTool",
    "BezierTool",
    "CalloutTool",
    "ChamferTool",
    "CircleTool",
    "CoincidentConstraintTool",
    "ConstraintTool",
    "EdgeLengthConstraintTool",
    "EllipseTool",
    "EqualConstraintTool",
    "FilletTool",
    "FixedConstraintTool",
    "ConstructionCircleTool",
    "ConstructionLineTool",
    "HorizontalConstraintTool",
    "HorizontalDistanceConstraintTool",
    "JournalPinTool",
    "MeasureTool",
    "MirrorTool",
    "OffsetTool",
    "ParallelConstraintTool",
    "PerpendicularConstraintTool",
    "PolygonTool",
    "PolylineTool",
    "RectangleTool",
    "SelectTool",
    "SymmetryConstraintTool",
    "TextTool",
    "ToolManager",
    "ToolType",
    "TrimExtendTool",
    "VerticalConstraintTool",
    "VerticalDistanceConstraintTool",
]


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
