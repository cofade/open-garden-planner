"""Tool manager for coordinating drawing tools."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class ToolManager(QObject):
    """Manages the active drawing tool and tool switching.

    Signals:
        tool_changed: Emitted when the active tool changes (tool_name: str)
    """

    tool_changed = pyqtSignal(str)

    def __init__(self, view: "CanvasView") -> None:
        """Initialize the tool manager.

        Args:
            view: The canvas view tools operate on.
        """
        super().__init__()
        self._view = view
        self._tools: dict[ToolType, BaseTool] = {}
        self._active_tool: BaseTool | None = None

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool with the manager.

        Args:
            tool: The tool to register.
        """
        self._tools[tool.tool_type] = tool

    def set_active_tool(self, tool_type: ToolType) -> None:
        """Switch to the specified tool.

        Args:
            tool_type: The type of tool to activate.
        """
        if self._active_tool:
            self._active_tool.deactivate()

        self._active_tool = self._tools.get(tool_type)
        if self._active_tool:
            self._active_tool.activate()
            self.tool_changed.emit(self._active_tool.display_name)

    @property
    def active_tool(self) -> BaseTool | None:
        """The currently active tool."""
        return self._active_tool

    @property
    def active_tool_type(self) -> ToolType | None:
        """The type of the currently active tool."""
        if self._active_tool:
            return self._active_tool.tool_type
        return None
