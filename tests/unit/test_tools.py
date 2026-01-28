"""Unit tests for drawing tools."""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from open_garden_planner.core.tools import (
    CircleTool,
    PolygonTool,
    RectangleTool,
    SelectTool,
    ToolType,
)


class TestToolType:
    """Tests for the ToolType enum."""

    def test_select_exists(self) -> None:
        """Test SELECT tool type exists."""
        assert ToolType.SELECT is not None

    def test_rectangle_exists(self) -> None:
        """Test RECTANGLE tool type exists."""
        assert ToolType.RECTANGLE is not None

    def test_polygon_exists(self) -> None:
        """Test POLYGON tool type exists."""
        assert ToolType.POLYGON is not None

    def test_circle_exists(self) -> None:
        """Test CIRCLE tool type exists."""
        assert ToolType.CIRCLE is not None

    def test_unique_values(self) -> None:
        """Test all tool types have unique values."""
        values = [t.value for t in ToolType]
        assert len(values) == len(set(values))


class TestSelectTool:
    """Tests for the SelectTool class."""

    @pytest.fixture
    def mock_view(self):
        """Create a mock canvas view."""
        view = MagicMock()
        view.setCursor = MagicMock()
        return view

    def test_tool_type(self, mock_view) -> None:
        """Test SelectTool has correct tool type."""
        tool = SelectTool(mock_view)
        assert tool.tool_type == ToolType.SELECT

    def test_display_name(self, mock_view) -> None:
        """Test SelectTool has correct display name."""
        tool = SelectTool(mock_view)
        assert tool.display_name == "Select"

    def test_shortcut(self, mock_view) -> None:
        """Test SelectTool has correct shortcut."""
        tool = SelectTool(mock_view)
        assert tool.shortcut == "V"

    def test_cursor(self, mock_view) -> None:
        """Test SelectTool has arrow cursor."""
        tool = SelectTool(mock_view)
        assert tool.cursor == Qt.CursorShape.ArrowCursor

    def test_mouse_press_returns_false(self, mock_view) -> None:
        """Test mouse_press delegates to view (returns False)."""
        tool = SelectTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        scene_pos = QPointF(100, 100)
        assert tool.mouse_press(event, scene_pos) is False

    def test_mouse_move_returns_false(self, mock_view) -> None:
        """Test mouse_move delegates to view (returns False)."""
        tool = SelectTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        scene_pos = QPointF(100, 100)
        assert tool.mouse_move(event, scene_pos) is False

    def test_mouse_release_returns_false(self, mock_view) -> None:
        """Test mouse_release delegates to view (returns False)."""
        tool = SelectTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        scene_pos = QPointF(100, 100)
        assert tool.mouse_release(event, scene_pos) is False


class TestRectangleTool:
    """Tests for the RectangleTool class."""

    @pytest.fixture
    def mock_view(self):
        """Create a mock canvas view with scene."""
        scene = MagicMock()
        view = MagicMock()
        view.scene.return_value = scene
        view.setCursor = MagicMock()
        return view

    def test_tool_type(self, mock_view) -> None:
        """Test RectangleTool has correct tool type."""
        tool = RectangleTool(mock_view)
        assert tool.tool_type == ToolType.RECTANGLE

    def test_display_name(self, mock_view) -> None:
        """Test RectangleTool has correct display name."""
        tool = RectangleTool(mock_view)
        assert tool.display_name == "Rectangle"

    def test_shortcut(self, mock_view) -> None:
        """Test RectangleTool has correct shortcut."""
        tool = RectangleTool(mock_view)
        assert tool.shortcut == "R"

    def test_cursor(self, mock_view) -> None:
        """Test RectangleTool has crosshair cursor."""
        tool = RectangleTool(mock_view)
        assert tool.cursor == Qt.CursorShape.CrossCursor

    def test_initial_state(self, mock_view) -> None:
        """Test RectangleTool starts in IDLE state."""
        tool = RectangleTool(mock_view)
        assert not tool._is_drawing
        assert tool._start_point is None
        assert tool._preview_item is None

    def test_mouse_press_starts_drawing(self, mock_view) -> None:
        """Test mouse press with left button starts drawing."""
        tool = RectangleTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton
        scene_pos = QPointF(100, 100)

        result = tool.mouse_press(event, scene_pos)

        assert result is True
        assert tool._is_drawing is True
        assert tool._start_point == scene_pos
        assert tool._preview_item is not None

    def test_mouse_press_ignores_right_click(self, mock_view) -> None:
        """Test mouse press ignores non-left clicks."""
        tool = RectangleTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.RightButton
        scene_pos = QPointF(100, 100)

        result = tool.mouse_press(event, scene_pos)

        assert result is False
        assert tool._is_drawing is False

    def test_cancel_resets_state(self, mock_view) -> None:
        """Test cancel clears drawing state."""
        tool = RectangleTool(mock_view)
        # Start drawing first
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event, QPointF(100, 100))

        # Cancel
        tool.cancel()

        assert tool._is_drawing is False
        assert tool._start_point is None
        assert tool._preview_item is None


class TestPolygonTool:
    """Tests for the PolygonTool class."""

    @pytest.fixture
    def mock_view(self):
        """Create a mock canvas view with scene."""
        scene = MagicMock()
        view = MagicMock()
        view.scene.return_value = scene
        view.setCursor = MagicMock()
        view.zoom_factor = 1.0
        return view

    def test_tool_type(self, mock_view) -> None:
        """Test PolygonTool has correct tool type."""
        tool = PolygonTool(mock_view)
        assert tool.tool_type == ToolType.POLYGON

    def test_display_name(self, mock_view) -> None:
        """Test PolygonTool has correct display name."""
        tool = PolygonTool(mock_view)
        assert tool.display_name == "Polygon"

    def test_shortcut(self, mock_view) -> None:
        """Test PolygonTool has correct shortcut."""
        tool = PolygonTool(mock_view)
        assert tool.shortcut == "P"

    def test_cursor(self, mock_view) -> None:
        """Test PolygonTool has crosshair cursor."""
        tool = PolygonTool(mock_view)
        assert tool.cursor == Qt.CursorShape.CrossCursor

    def test_initial_state(self, mock_view) -> None:
        """Test PolygonTool starts in IDLE state."""
        tool = PolygonTool(mock_view)
        assert not tool._is_drawing
        assert len(tool._vertices) == 0

    def test_mouse_press_adds_vertex(self, mock_view) -> None:
        """Test mouse press adds a vertex."""
        tool = PolygonTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton
        scene_pos = QPointF(100, 100)

        result = tool.mouse_press(event, scene_pos)

        assert result is True
        assert tool._is_drawing is True
        assert len(tool._vertices) == 1
        assert tool._vertices[0] == scene_pos

    def test_multiple_clicks_add_vertices(self, mock_view) -> None:
        """Test multiple clicks add multiple vertices."""
        tool = PolygonTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton

        tool.mouse_press(event, QPointF(0, 0))
        tool.mouse_press(event, QPointF(100, 0))
        tool.mouse_press(event, QPointF(100, 100))

        assert len(tool._vertices) == 3

    def test_cancel_resets_state(self, mock_view) -> None:
        """Test cancel clears all vertices."""
        tool = PolygonTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton

        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_press(event, QPointF(200, 100))

        tool.cancel()

        assert tool._is_drawing is False
        assert len(tool._vertices) == 0

    def test_key_escape_cancels(self, mock_view) -> None:
        """Test pressing Escape cancels drawing."""
        tool = PolygonTool(mock_view)
        mouse_event = MagicMock(spec=QMouseEvent)
        mouse_event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(mouse_event, QPointF(100, 100))

        key_event = MagicMock(spec=QKeyEvent)
        key_event.key.return_value = Qt.Key.Key_Escape

        result = tool.key_press(key_event)

        assert result is True
        assert tool._is_drawing is False

    def test_close_threshold(self, mock_view) -> None:
        """Test close threshold constant."""
        tool = PolygonTool(mock_view)
        assert tool.CLOSE_THRESHOLD == 15.0


class TestCircleTool:
    """Tests for the CircleTool class."""

    @pytest.fixture
    def mock_view(self):
        """Create a mock canvas view with scene."""
        scene = MagicMock()
        view = MagicMock()
        view.scene.return_value = scene
        view.setCursor = MagicMock()
        return view

    def test_tool_type(self, mock_view) -> None:
        """Test CircleTool has correct tool type."""
        tool = CircleTool(mock_view)
        assert tool.tool_type == ToolType.CIRCLE

    def test_display_name(self, mock_view) -> None:
        """Test CircleTool has correct display name."""
        tool = CircleTool(mock_view)
        assert tool.display_name == "Circle"

    def test_shortcut(self, mock_view) -> None:
        """Test CircleTool has correct shortcut."""
        tool = CircleTool(mock_view)
        assert tool.shortcut == "C"

    def test_cursor(self, mock_view) -> None:
        """Test CircleTool has crosshair cursor."""
        tool = CircleTool(mock_view)
        assert tool.cursor == Qt.CursorShape.CrossCursor

    def test_initial_state(self, mock_view) -> None:
        """Test CircleTool starts in idle state."""
        tool = CircleTool(mock_view)
        assert not tool._is_drawing
        assert tool._center_point is None
        assert tool._preview_circle is None
        assert tool._preview_line is None

    def test_first_click_sets_center(self, mock_view) -> None:
        """Test first click sets center point."""
        tool = CircleTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton
        scene_pos = QPointF(100, 100)

        result = tool.mouse_press(event, scene_pos)

        assert result is True
        assert tool._is_drawing is True
        assert tool._center_point == scene_pos
        assert tool._preview_circle is not None
        assert tool._preview_line is not None

    def test_mouse_press_ignores_right_click(self, mock_view) -> None:
        """Test mouse press ignores non-left clicks."""
        tool = CircleTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.RightButton
        scene_pos = QPointF(100, 100)

        result = tool.mouse_press(event, scene_pos)

        assert result is False
        assert tool._is_drawing is False

    def test_mouse_move_updates_preview(self, mock_view) -> None:
        """Test mouse move updates preview circle."""
        tool = CircleTool(mock_view)
        # Start drawing
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event, QPointF(100, 100))

        # Move mouse
        result = tool.mouse_move(event, QPointF(150, 100))

        assert result is True
        assert tool._preview_circle is not None

    def test_mouse_move_idle_returns_false(self, mock_view) -> None:
        """Test mouse move when not drawing returns false."""
        tool = CircleTool(mock_view)
        event = MagicMock(spec=QMouseEvent)

        result = tool.mouse_move(event, QPointF(150, 100))

        assert result is False

    def test_cancel_resets_state(self, mock_view) -> None:
        """Test cancel clears drawing state."""
        tool = CircleTool(mock_view)
        # Start drawing first
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(event, QPointF(100, 100))

        # Cancel
        tool.cancel()

        assert tool._is_drawing is False
        assert tool._center_point is None
        assert tool._preview_circle is None
        assert tool._preview_line is None

    def test_key_escape_cancels(self, mock_view) -> None:
        """Test pressing Escape cancels drawing."""
        tool = CircleTool(mock_view)
        mouse_event = MagicMock(spec=QMouseEvent)
        mouse_event.button.return_value = Qt.MouseButton.LeftButton
        tool.mouse_press(mouse_event, QPointF(100, 100))

        key_event = MagicMock(spec=QKeyEvent)
        key_event.key.return_value = Qt.Key.Key_Escape

        result = tool.key_press(key_event)

        assert result is True
        assert tool._is_drawing is False

    def test_mouse_release_returns_false(self, mock_view) -> None:
        """Test mouse_release is no-op for circle tool."""
        tool = CircleTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        scene_pos = QPointF(100, 100)

        result = tool.mouse_release(event, scene_pos)

        assert result is False
