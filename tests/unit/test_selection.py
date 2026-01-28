"""Unit tests for selection functionality."""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsRectItem

from open_garden_planner.core.tools import SelectTool, ToolType
from open_garden_planner.ui.canvas.items import RectangleItem


class TestSelectToolBoxSelection:
    """Tests for SelectTool box selection."""

    @pytest.fixture
    def mock_view(self):
        """Create a mock canvas view with scene."""
        scene = MagicMock()
        scene.items.return_value = []
        scene.itemAt.return_value = None
        view = MagicMock()
        view.scene.return_value = scene
        view.transform.return_value = MagicMock()
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

    def test_initial_state(self, mock_view) -> None:
        """Test SelectTool starts with no box selection."""
        tool = SelectTool(mock_view)
        assert tool._box_start is None
        assert tool._box_item is None
        assert not tool._is_box_selecting

    def test_click_on_empty_starts_box_selection(self, mock_view) -> None:
        """Test clicking on empty area starts box selection."""
        tool = SelectTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton
        event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
        scene_pos = QPointF(100, 100)

        tool.mouse_press(event, scene_pos)

        assert tool._box_start == scene_pos
        assert tool._is_box_selecting

    def test_right_click_does_not_start_box(self, mock_view) -> None:
        """Test right click doesn't start box selection."""
        tool = SelectTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.RightButton
        scene_pos = QPointF(100, 100)

        result = tool.mouse_press(event, scene_pos)

        assert result is False
        assert not tool._is_box_selecting

    def test_click_on_item_does_not_start_box(self, mock_view) -> None:
        """Test clicking on an item doesn't start box selection."""
        # Set up mock to return an item at the click position
        mock_item = MagicMock()
        mock_item.flags.return_value = QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
        mock_view.scene().itemAt.return_value = mock_item

        tool = SelectTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton
        event.modifiers.return_value = Qt.KeyboardModifier.NoModifier  # No shift
        scene_pos = QPointF(100, 100)

        result = tool.mouse_press(event, scene_pos)

        assert result is False  # Without Shift, delegates to view
        assert not tool._is_box_selecting

    def test_cancel_clears_box_state(self, mock_view) -> None:
        """Test cancel clears box selection state."""
        tool = SelectTool(mock_view)
        event = MagicMock(spec=QMouseEvent)
        event.button.return_value = Qt.MouseButton.LeftButton
        event.modifiers.return_value = Qt.KeyboardModifier.NoModifier

        # Start box selection
        tool.mouse_press(event, QPointF(100, 100))
        assert tool._is_box_selecting

        # Cancel
        tool.cancel()

        assert tool._box_start is None
        assert tool._box_item is None
        assert not tool._is_box_selecting

    def test_enclosing_color_is_blue(self, mock_view) -> None:
        """Test enclosing selection uses blue color."""
        tool = SelectTool(mock_view)
        # Blue color (0, 120, 215)
        assert tool.ENCLOSING_COLOR.red() == 0
        assert tool.ENCLOSING_COLOR.green() == 120
        assert tool.ENCLOSING_COLOR.blue() == 215

    def test_crossing_color_is_green(self, mock_view) -> None:
        """Test crossing selection uses green color."""
        tool = SelectTool(mock_view)
        # Green color (0, 180, 0)
        assert tool.CROSSING_COLOR.red() == 0
        assert tool.CROSSING_COLOR.green() == 180
        assert tool.CROSSING_COLOR.blue() == 0


class TestRectangleItemContextMenu:
    """Tests for RectangleItem context menu."""

    def test_has_context_menu_event(self) -> None:
        """Test RectangleItem has contextMenuEvent method."""
        item = RectangleItem(0, 0, 100, 50)
        assert hasattr(item, "contextMenuEvent")
        assert callable(item.contextMenuEvent)


class TestCanvasViewKeyboard:
    """Tests for canvas view keyboard handling."""

    def test_delete_key_removes_selected_items(self, qtbot) -> None:
        """Test Delete key removes selected items."""
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
        from open_garden_planner.ui.canvas.canvas_view import CanvasView

        scene = CanvasScene(width_cm=1000, height_cm=1000)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Add and select an item
        item = RectangleItem(100, 100, 50, 50)
        scene.addItem(item)
        item.setSelected(True)

        assert len(scene.items()) >= 1  # At least our item

        # Call delete directly (simulating Delete key)
        view._delete_selected_items()

        # Item should be removed
        assert item not in scene.items()

    def test_arrow_key_moves_selected_items(self, qtbot) -> None:
        """Test arrow keys move selected items."""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent

        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
        from open_garden_planner.ui.canvas.canvas_view import CanvasView

        scene = CanvasScene(width_cm=1000, height_cm=1000)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Add and select an item
        item = RectangleItem(100, 100, 50, 50)
        scene.addItem(item)
        item.setSelected(True)

        initial_x = item.pos().x()

        # Create arrow key event
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Right,
            Qt.KeyboardModifier.NoModifier,
        )

        # Call move directly
        view._move_selected_items(event)

        # Item should have moved by grid size (50cm default)
        assert item.pos().x() == initial_x + view.grid_size

    def test_shift_arrow_moves_by_1cm(self, qtbot) -> None:
        """Test Shift+arrow moves by 1cm."""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent

        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
        from open_garden_planner.ui.canvas.canvas_view import CanvasView

        scene = CanvasScene(width_cm=1000, height_cm=1000)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Add and select an item
        item = RectangleItem(100, 100, 50, 50)
        scene.addItem(item)
        item.setSelected(True)

        initial_x = item.pos().x()

        # Create Shift+arrow key event
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Right,
            Qt.KeyboardModifier.ShiftModifier,
        )

        # Call move directly
        view._move_selected_items(event)

        # Item should have moved by 1cm
        assert item.pos().x() == initial_x + 1.0
