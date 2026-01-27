"""Unit tests for the ToolManager class."""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QObject

from open_garden_planner.core.tools import (
    SelectTool,
    ToolManager,
    ToolType,
)


class TestToolManager:
    """Tests for the ToolManager class."""

    @pytest.fixture
    def mock_view(self):
        """Create a mock canvas view."""
        view = MagicMock()
        view.setCursor = MagicMock()
        return view

    @pytest.fixture
    def tool_manager(self, mock_view):
        """Create a ToolManager with mock view."""
        return ToolManager(mock_view)

    def test_creation(self, tool_manager) -> None:
        """Test ToolManager can be created."""
        assert tool_manager is not None
        assert isinstance(tool_manager, QObject)

    def test_no_active_tool_initially(self, tool_manager) -> None:
        """Test no tool is active initially."""
        assert tool_manager.active_tool is None
        assert tool_manager.active_tool_type is None

    def test_register_tool(self, tool_manager, mock_view) -> None:
        """Test registering a tool."""
        select_tool = SelectTool(mock_view)
        tool_manager.register_tool(select_tool)

        # Tool is registered but not active yet
        assert tool_manager.active_tool is None

    def test_set_active_tool(self, tool_manager, mock_view) -> None:
        """Test setting the active tool."""
        select_tool = SelectTool(mock_view)
        tool_manager.register_tool(select_tool)

        tool_manager.set_active_tool(ToolType.SELECT)

        assert tool_manager.active_tool == select_tool
        assert tool_manager.active_tool_type == ToolType.SELECT

    def test_set_unregistered_tool_does_nothing(self, tool_manager) -> None:
        """Test setting an unregistered tool type."""
        tool_manager.set_active_tool(ToolType.SELECT)
        assert tool_manager.active_tool is None

    def test_tool_changed_signal(self, tool_manager, mock_view, qtbot) -> None:
        """Test tool_changed signal is emitted."""
        select_tool = SelectTool(mock_view)
        tool_manager.register_tool(select_tool)

        with qtbot.waitSignal(tool_manager.tool_changed, timeout=1000) as blocker:
            tool_manager.set_active_tool(ToolType.SELECT)

        assert blocker.args == ["Select"]

    def test_switching_tools_deactivates_previous(self, tool_manager, mock_view) -> None:
        """Test switching tools deactivates the previous tool."""
        select_tool = SelectTool(mock_view)
        tool_manager.register_tool(select_tool)

        # Create a mock tool to track deactivation
        mock_tool = MagicMock()
        mock_tool.tool_type = ToolType.RECTANGLE
        mock_tool.display_name = "Rectangle"
        tool_manager.register_tool(mock_tool)

        # Activate rectangle tool
        tool_manager.set_active_tool(ToolType.RECTANGLE)

        # Now switch to select tool
        tool_manager.set_active_tool(ToolType.SELECT)

        # Verify deactivate was called on rectangle tool
        mock_tool.deactivate.assert_called_once()

    def test_active_tool_type_property(self, tool_manager, mock_view) -> None:
        """Test active_tool_type property."""
        select_tool = SelectTool(mock_view)
        tool_manager.register_tool(select_tool)

        assert tool_manager.active_tool_type is None

        tool_manager.set_active_tool(ToolType.SELECT)

        assert tool_manager.active_tool_type == ToolType.SELECT
