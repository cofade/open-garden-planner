"""Tests for the measure tool."""

from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QPointF, Qt

from open_garden_planner.core.tools import MeasureTool, ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView


@pytest.fixture
def measure_tool(qtbot):
    """Create a measure tool with scene and view.

    Args:
        qtbot: PyQt test fixture

    Returns:
        Tuple of (tool, view, scene)
    """
    scene = CanvasScene(1000, 1000)
    view = CanvasView(scene)
    qtbot.addWidget(view)

    tool = MeasureTool(view)
    return tool, view, scene


class TestMeasureTool:
    """Tests for MeasureTool class."""

    def test_tool_type(self, qtbot, measure_tool):
        """Test that tool has correct type."""
        tool, view, scene = measure_tool
        assert tool.tool_type == ToolType.MEASURE

    def test_display_name(self, qtbot, measure_tool):
        """Test tool display name."""
        tool, view, scene = measure_tool
        assert tool.display_name == "Measure"

    def test_shortcut(self, qtbot, measure_tool):
        """Test keyboard shortcut."""
        tool, view, scene = measure_tool
        assert tool.shortcut == "M"

    def test_cursor(self, qtbot, measure_tool):
        """Test that tool uses crosshair cursor."""
        tool, view, scene = measure_tool
        assert tool.cursor.shape() == Qt.CursorShape.CrossCursor

    def test_initial_state(self, qtbot, measure_tool):
        """Test initial state of measure tool."""
        tool, view, scene = measure_tool
        assert tool._first_point is None
        assert tool._graphics_items == []

    def test_first_click_sets_point(self, qtbot, measure_tool):
        """Test that first click sets the first point."""
        tool, view, scene = measure_tool
        tool.activate()

        point = QPointF(100, 100)
        event = Mock()
        event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event, point)

        assert tool._first_point == point

    def test_second_click_completes_measurement(self, qtbot, measure_tool):
        """Test that second click completes the measurement."""
        tool, view, scene = measure_tool
        tool.activate()

        # First click
        point1 = QPointF(100, 100)
        event1 = Mock()
        event1.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event1, point1)

        # Second click
        point2 = QPointF(200, 100)
        event2 = Mock()
        event2.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event2, point2)

        # After second click, first point should be reset for next measurement
        assert tool._first_point is None

    def test_right_click_ignored(self, qtbot, measure_tool):
        """Test that right click doesn't set points."""
        tool, view, scene = measure_tool
        tool.activate()

        point = QPointF(100, 100)
        event = Mock()
        event.button.return_value = Qt.MouseButton.RightButton
        result = tool.mouse_press(event, point)

        assert result is False
        assert tool._first_point is None

    def test_escape_cancels_measurement(self, qtbot, measure_tool):
        """Test that ESC cancels current measurement."""
        tool, view, scene = measure_tool
        tool.activate()

        # Start measurement
        point = QPointF(100, 100)
        event = Mock()
        event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event, point)
        assert tool._first_point is not None

        # Press ESC
        key_event = Mock()
        key_event.key.return_value = Qt.Key.Key_Escape
        tool.key_press(key_event)

        # Should be cancelled
        assert tool._first_point is None

    def test_cancel_clears_state(self, qtbot, measure_tool):
        """Test that cancel() clears measurement state."""
        tool, view, scene = measure_tool
        tool.activate()

        # Start measurement
        point = QPointF(100, 100)
        event = Mock()
        event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event, point)

        # Cancel
        tool.cancel()

        # State should be cleared
        assert tool._first_point is None

    def test_activate_clears_measurement(self, qtbot, measure_tool):
        """Test that activating the tool clears any existing measurement."""
        tool, view, scene = measure_tool

        # Set some state
        tool._first_point = QPointF(50, 50)

        # Activate should clear it
        tool.activate()
        assert tool._first_point is None

    def test_deactivate_clears_measurement(self, qtbot, measure_tool):
        """Test that deactivating the tool clears measurement."""
        tool, view, scene = measure_tool
        tool.activate()

        # Start measurement
        point = QPointF(100, 100)
        event = Mock()
        event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event, point)
        assert tool._first_point is not None

        # Deactivate
        tool.deactivate()

        # Should be cleared
        assert tool._first_point is None

    def test_mouse_move_with_first_point_updates_preview(self, qtbot, measure_tool):
        """Test that mouse move shows preview when first point is set."""
        tool, view, scene = measure_tool
        tool.activate()

        # Set first point
        point1 = QPointF(100, 100)
        event1 = Mock()
        event1.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event1, point1)

        # Move mouse
        point2 = QPointF(200, 150)
        move_event = Mock()
        result = tool.mouse_move(move_event, point2)

        assert result is True
        assert len(tool._graphics_items) > 0  # Should have preview items

    def test_mouse_move_without_first_point(self, qtbot, measure_tool):
        """Test that mouse move does nothing without first point."""
        tool, view, scene = measure_tool
        tool.activate()

        # Move mouse without setting first point
        point = QPointF(200, 150)
        move_event = Mock()
        result = tool.mouse_move(move_event, point)

        assert result is False

    def test_measurement_creates_line_item(self, qtbot, measure_tool):
        """Test that measurement creates a line item in the scene."""
        tool, view, scene = measure_tool
        tool.activate()

        initial_item_count = len(scene.items())

        # Complete measurement
        point1 = QPointF(0, 0)
        point2 = QPointF(100, 0)

        event1 = Mock()
        event1.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event1, point1)

        event2 = Mock()
        event2.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event2, point2)

        # Should have added items to scene (line, crosshairs, text)
        assert len(scene.items()) > initial_item_count

    def test_sequential_measurements(self, qtbot, measure_tool):
        """Test that multiple measurements can be made sequentially."""
        tool, view, scene = measure_tool
        tool.activate()

        # First measurement
        event = Mock()
        event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event, QPointF(0, 0))
        tool.mouse_press(event, QPointF(100, 0))
        assert tool._first_point is None  # Reset after measurement

        # Second measurement
        tool.mouse_press(event, QPointF(200, 200))
        assert tool._first_point is not None  # New measurement started
        tool.mouse_press(event, QPointF(300, 200))
        assert tool._first_point is None  # Reset again
