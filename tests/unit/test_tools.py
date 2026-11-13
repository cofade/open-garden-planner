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
    TextTool,
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
        # snap_point returns the input point unchanged (simulating snap disabled)
        view.snap_point = lambda p: p
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
        # snap_point returns the input point unchanged (simulating snap disabled)
        view.snap_point = lambda p: p
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
        # snap_point returns the input point unchanged (simulating snap disabled)
        view.snap_point = lambda p: p
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


class TestTextTool:
    """Unit tests for the TextTool class."""

    @pytest.fixture
    def mock_view(self):
        """Create a mock canvas view."""
        view = MagicMock()
        view.setCursor = MagicMock()
        view.scene = MagicMock()
        view.command_manager = MagicMock()
        return view

    def test_tool_properties(self, mock_view) -> None:
        """Test TextTool has correct type, display name, and cursor."""
        tool = TextTool(mock_view)
        assert tool.tool_type == ToolType.TEXT
        assert tool.display_name == "Text"
        assert tool.cursor == Qt.CursorShape.IBeamCursor
        assert tool.shortcut == ""

    def test_cancel_when_nothing_pending_is_safe(self, mock_view) -> None:
        """Cancelling an idle tool does nothing and does not crash."""
        tool = TextTool(mock_view)
        tool.cancel()
        assert tool._pending_item is None
        assert tool._pending_command is None
        mock_view.command_manager.discard.assert_not_called()

    def test_cancel_empty_annotation_discards_command_and_removes_item(
        self, mock_view
    ) -> None:
        """Escape on empty text annotation discards command and removes item."""
        tool = TextTool(mock_view)
        scene = MagicMock()
        mock_view.scene.return_value = scene
        mock_view.command_manager.discard.return_value = True

        mock_item = MagicMock()
        mock_item.toPlainText.return_value = ""
        mock_item.scene.return_value = scene
        mock_command = MagicMock()

        tool._pending_item = mock_item
        tool._pending_command = mock_command

        tool.cancel()

        assert tool._pending_item is None
        assert tool._pending_command is None
        mock_view.command_manager.discard.assert_called_once_with(mock_command)
        scene.removeItem.assert_called_once_with(mock_item)

    def test_cancel_non_empty_annotation_keeps_item_and_command(
        self, mock_view
    ) -> None:
        """Escape on text annotation with content retains item and history."""
        tool = TextTool(mock_view)
        scene = MagicMock()
        mock_view.scene.return_value = scene

        mock_item = MagicMock()
        mock_item.toPlainText.return_value = "Non-empty note"
        mock_item.scene.return_value = scene
        mock_command = MagicMock()

        tool._pending_item = mock_item
        tool._pending_command = mock_command

        tool.cancel()

        assert tool._pending_item is None
        assert tool._pending_command is None
        mock_view.command_manager.discard.assert_not_called()
        scene.removeItem.assert_not_called()

    def test_cancel_when_discard_fails_keeps_item_in_scene(
        self, mock_view
    ) -> None:
        """If discard fails (e.g. interleaved command), item stays in scene."""
        tool = TextTool(mock_view)
        scene = MagicMock()
        mock_view.scene.return_value = scene
        mock_view.command_manager.discard.return_value = False

        mock_item = MagicMock()
        mock_item.toPlainText.return_value = ""
        mock_item.scene.return_value = scene
        mock_command = MagicMock()

        tool._pending_item = mock_item
        tool._pending_command = mock_command

        tool.cancel()

        mock_view.command_manager.discard.assert_called_once_with(mock_command)
        scene.removeItem.assert_not_called()

    def test_repeated_cancel_is_idempotent(self, mock_view) -> None:
        """Calling cancel repeatedly only discards and removes once."""
        tool = TextTool(mock_view)
        scene = MagicMock()
        mock_view.scene.return_value = scene
        mock_view.command_manager.discard.return_value = True

        mock_item = MagicMock()
        mock_item.toPlainText.return_value = ""
        mock_item.scene.return_value = scene
        mock_command = MagicMock()

        tool._pending_item = mock_item
        tool._pending_command = mock_command

        tool.cancel()
        tool.cancel()

        mock_view.command_manager.discard.assert_called_once_with(mock_command)
        scene.removeItem.assert_called_once_with(mock_item)
