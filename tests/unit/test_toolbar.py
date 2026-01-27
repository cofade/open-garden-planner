"""Unit tests for the MainToolbar widget."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QToolBar

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.widgets import MainToolbar


class TestMainToolbar:
    """Tests for the MainToolbar class."""

    @pytest.fixture
    def toolbar(self, qtbot):
        """Create a MainToolbar widget."""
        toolbar = MainToolbar()
        qtbot.addWidget(toolbar)
        return toolbar

    def test_creation(self, toolbar) -> None:
        """Test toolbar can be created."""
        assert toolbar is not None
        assert isinstance(toolbar, QToolBar)

    def test_title(self, toolbar) -> None:
        """Test toolbar has correct title."""
        assert toolbar.windowTitle() == "Tools"

    def test_not_movable(self, toolbar) -> None:
        """Test toolbar is not movable."""
        assert toolbar.isMovable() is False

    def test_horizontal_orientation(self, toolbar) -> None:
        """Test toolbar is horizontal."""
        assert toolbar.orientation() == Qt.Orientation.Horizontal

    def test_has_select_button(self, toolbar) -> None:
        """Test toolbar has Select button."""
        assert ToolType.SELECT in toolbar._buttons
        assert toolbar._buttons[ToolType.SELECT].text() == "Select"

    def test_has_rectangle_button(self, toolbar) -> None:
        """Test toolbar has Rectangle button."""
        assert ToolType.RECTANGLE in toolbar._buttons
        assert toolbar._buttons[ToolType.RECTANGLE].text() == "Rectangle"

    def test_has_polygon_button(self, toolbar) -> None:
        """Test toolbar has Polygon button."""
        assert ToolType.POLYGON in toolbar._buttons
        assert toolbar._buttons[ToolType.POLYGON].text() == "Polygon"

    def test_select_is_default(self, toolbar) -> None:
        """Test Select tool is checked by default."""
        assert toolbar._buttons[ToolType.SELECT].isChecked()

    def test_buttons_are_checkable(self, toolbar) -> None:
        """Test all buttons are checkable."""
        for button in toolbar._buttons.values():
            assert button.isCheckable()

    def test_buttons_are_exclusive(self, toolbar, qtbot) -> None:
        """Test only one button can be checked at a time."""
        # Click Rectangle button
        qtbot.mouseClick(toolbar._buttons[ToolType.RECTANGLE], Qt.MouseButton.LeftButton)

        assert toolbar._buttons[ToolType.RECTANGLE].isChecked()
        assert not toolbar._buttons[ToolType.SELECT].isChecked()
        assert not toolbar._buttons[ToolType.POLYGON].isChecked()

    def test_tool_selected_signal(self, toolbar, qtbot) -> None:
        """Test tool_selected signal is emitted when button clicked."""
        with qtbot.waitSignal(toolbar.tool_selected, timeout=1000) as blocker:
            qtbot.mouseClick(toolbar._buttons[ToolType.RECTANGLE], Qt.MouseButton.LeftButton)

        assert blocker.args == [ToolType.RECTANGLE]

    def test_set_active_tool(self, toolbar) -> None:
        """Test set_active_tool updates button state."""
        toolbar.set_active_tool(ToolType.POLYGON)

        assert toolbar._buttons[ToolType.POLYGON].isChecked()
        assert not toolbar._buttons[ToolType.SELECT].isChecked()

    def test_select_button_shortcut(self, toolbar) -> None:
        """Test Select button has V shortcut."""
        shortcut = toolbar._buttons[ToolType.SELECT].shortcut()
        assert shortcut.toString() == "V"

    def test_rectangle_button_shortcut(self, toolbar) -> None:
        """Test Rectangle button has R shortcut."""
        shortcut = toolbar._buttons[ToolType.RECTANGLE].shortcut()
        assert shortcut.toString() == "R"

    def test_polygon_button_shortcut(self, toolbar) -> None:
        """Test Polygon button has P shortcut."""
        shortcut = toolbar._buttons[ToolType.POLYGON].shortcut()
        assert shortcut.toString() == "P"

    def test_button_tooltips(self, toolbar) -> None:
        """Test buttons have tooltips."""
        for button in toolbar._buttons.values():
            assert button.toolTip() != ""
