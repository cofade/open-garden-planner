"""Tests for drawing tools panel."""

import pytest

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.panels import DrawingToolsPanel


def test_drawing_tools_panel_creation(qtbot):  # noqa: ARG001
    """Test that a drawing tools panel can be created."""
    panel = DrawingToolsPanel()
    qtbot.addWidget(panel)

    assert panel is not None
    assert len(panel._buttons) > 0


def test_drawing_tools_panel_has_all_tools(qtbot):  # noqa: ARG001
    """Test that all expected tools are present."""
    panel = DrawingToolsPanel()
    qtbot.addWidget(panel)

    # Check that key tools are present
    expected_tools = [
        ToolType.SELECT,
        ToolType.RECTANGLE,
        ToolType.POLYGON,
        ToolType.CIRCLE,
        ToolType.HOUSE,
        ToolType.TREE,
        ToolType.SHRUB,
        ToolType.PERENNIAL,
        ToolType.MEASURE,
    ]

    for tool in expected_tools:
        assert tool in panel._buttons, f"Tool {tool} not found in panel"


def test_drawing_tools_panel_default_tool(qtbot):  # noqa: ARG001
    """Test that SELECT tool is checked by default."""
    panel = DrawingToolsPanel()
    qtbot.addWidget(panel)

    assert panel._buttons[ToolType.SELECT].isChecked()


def test_drawing_tools_panel_tool_selection(qtbot):  # noqa: ARG001
    """Test selecting a tool."""
    panel = DrawingToolsPanel()
    qtbot.addWidget(panel)

    # Track tool selections
    selected_tools = []

    def on_tool_selected(tool: ToolType):
        selected_tools.append(tool)

    panel.tool_selected.connect(on_tool_selected)

    # Click a tool button
    panel._buttons[ToolType.RECTANGLE].click()

    assert len(selected_tools) == 1
    assert selected_tools[0] == ToolType.RECTANGLE
    assert panel._buttons[ToolType.RECTANGLE].isChecked()


def test_drawing_tools_panel_set_active_tool(qtbot):  # noqa: ARG001
    """Test programmatically setting the active tool."""
    panel = DrawingToolsPanel()
    qtbot.addWidget(panel)

    # Set a tool as active
    panel.set_active_tool(ToolType.POLYGON)

    assert panel._buttons[ToolType.POLYGON].isChecked()
    assert not panel._buttons[ToolType.SELECT].isChecked()


def test_drawing_tools_panel_exclusive_selection(qtbot):  # noqa: ARG001
    """Test that only one tool can be selected at a time."""
    panel = DrawingToolsPanel()
    qtbot.addWidget(panel)

    # Select first tool
    panel._buttons[ToolType.RECTANGLE].setChecked(True)
    assert panel._buttons[ToolType.RECTANGLE].isChecked()

    # Select second tool
    panel._buttons[ToolType.CIRCLE].setChecked(True)
    assert panel._buttons[ToolType.CIRCLE].isChecked()
    assert not panel._buttons[ToolType.RECTANGLE].isChecked()
