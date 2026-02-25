"""Base class for drawing and editing tools."""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class ToolType(Enum):
    """Enumeration of available tool types."""

    SELECT = auto()
    MEASURE = auto()
    CONSTRAINT = auto()             # Distance constraint
    CONSTRAINT_HORIZONTAL = auto()  # Horizontal alignment constraint
    CONSTRAINT_VERTICAL = auto()    # Vertical alignment constraint
    CONSTRAINT_ANGLE = auto()       # Angle constraint (3-point)
    CONSTRAINT_SYMMETRY = auto()    # Symmetry constraint (mirror across H/V axis)
    CONSTRAINT_COINCIDENT = auto()  # Coincident constraint (merge two anchor points)

    # Property object types (polygon-based)
    HOUSE = auto()
    GARAGE_SHED = auto()
    TERRACE_PATIO = auto()
    DRIVEWAY = auto()
    POND_POOL = auto()
    GREENHOUSE = auto()
    GARDEN_BED = auto()
    LAWN = auto()

    # Property object types (polyline-based)
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

    # Generic geometric shapes (backwards compatibility)
    RECTANGLE = auto()
    POLYGON = auto()
    CIRCLE = auto()

    # Construction geometry (helper lines/circles, not in exports)
    CONSTRUCTION_LINE = auto()
    CONSTRUCTION_CIRCLE = auto()


class BaseTool(ABC):
    """Abstract base class for all drawing tools.

    Tools handle mouse and keyboard events to create or modify
    items on the canvas.
    """

    tool_type: ToolType
    display_name: str
    shortcut: str
    cursor: Qt.CursorShape = Qt.CursorShape.ArrowCursor

    def __init__(self, view: "CanvasView") -> None:
        """Initialize the tool.

        Args:
            view: The canvas view this tool operates on.
        """
        self._view = view
        self._active = False

    @property
    def view(self) -> "CanvasView":
        """The canvas view this tool operates on."""
        return self._view

    @property
    def is_active(self) -> bool:
        """Whether this tool is currently active."""
        return self._active

    def activate(self) -> None:
        """Called when this tool becomes the active tool."""
        self._active = True
        self._view.setCursor(self.cursor)

    def deactivate(self) -> None:
        """Called when switching away from this tool."""
        self._active = False
        self.cancel()

    @abstractmethod
    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse press.

        Args:
            event: The mouse event.
            scene_pos: Position in scene coordinates (optionally snapped).

        Returns:
            True if the event was handled.
        """
        pass

    @abstractmethod
    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse move.

        Args:
            event: The mouse event.
            scene_pos: Position in scene coordinates (optionally snapped).

        Returns:
            True if the event was handled.
        """
        pass

    @abstractmethod
    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse release.

        Args:
            event: The mouse event.
            scene_pos: Position in scene coordinates (optionally snapped).

        Returns:
            True if the event was handled.
        """
        pass

    def mouse_double_click(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        """Handle mouse double click.

        Args:
            _event: The mouse event.
            _scene_pos: Position in scene coordinates (optionally snapped).

        Returns:
            True if the event was handled.
        """
        return False

    def key_press(self, _event: QKeyEvent) -> bool:
        """Handle key press.

        Args:
            _event: The key event.

        Returns:
            True if the event was handled.
        """
        return False

    def cancel(self) -> None:  # noqa: B027
        """Cancel the current drawing operation.

        Override in subclasses to clean up any in-progress operations.
        Default implementation does nothing.
        """
