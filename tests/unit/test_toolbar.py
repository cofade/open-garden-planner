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

    def test_has_measure_button(self, toolbar) -> None:
        """Test toolbar has Measure button."""
        assert ToolType.MEASURE in toolbar._buttons

    def test_toolbar_has_core_tools(self, toolbar) -> None:
        """Test toolbar has Select, Measure, Text, Callout and Journal Pin tools."""
        assert len(toolbar._buttons) == 5
        assert ToolType.TEXT in toolbar._buttons
        assert ToolType.CALLOUT in toolbar._buttons
        assert ToolType.JOURNAL_PIN in toolbar._buttons

    def test_select_is_default(self, toolbar) -> None:
        """Test Select tool is checked by default."""
        assert toolbar._buttons[ToolType.SELECT].isChecked()

    def test_buttons_are_checkable(self, toolbar) -> None:
        """Test all buttons are checkable."""
        for button in toolbar._buttons.values():
            assert button.isCheckable()

    def test_buttons_are_exclusive(self, toolbar, qtbot) -> None:
        """Test only one button can be checked at a time."""
        # Click Measure button
        qtbot.mouseClick(toolbar._buttons[ToolType.MEASURE], Qt.MouseButton.LeftButton)

        assert toolbar._buttons[ToolType.MEASURE].isChecked()
        assert not toolbar._buttons[ToolType.SELECT].isChecked()

    def test_tool_selected_signal(self, toolbar, qtbot) -> None:
        """Test tool_selected signal is emitted when button clicked."""
        with qtbot.waitSignal(toolbar.tool_selected, timeout=1000) as blocker:
            qtbot.mouseClick(toolbar._buttons[ToolType.MEASURE], Qt.MouseButton.LeftButton)

        assert blocker.args == [ToolType.MEASURE]

    def test_set_active_tool(self, toolbar) -> None:
        """Test set_active_tool updates button state."""
        toolbar.set_active_tool(ToolType.MEASURE)

        assert toolbar._buttons[ToolType.MEASURE].isChecked()
        assert not toolbar._buttons[ToolType.SELECT].isChecked()

    def test_set_active_tool_measure_checks_only_measure(self, toolbar) -> None:
        """set_active_tool(MEASURE) checks MEASURE and nothing else (#304)."""
        toolbar.set_active_tool(ToolType.MEASURE)

        checked = toolbar._button_group.checkedButton()
        assert checked is toolbar._buttons[ToolType.MEASURE]

    def test_set_active_tool_non_main_tool_unchecks_select(self, toolbar) -> None:
        """A tool with no button here (e.g. a constraint tool) must not leave
        SELECT highlighted — this was the #304 duplicated-highlight bug."""
        toolbar.set_active_tool(ToolType.CONSTRAINT_EQUAL)

        assert toolbar._button_group.checkedButton() is None
        assert not toolbar._buttons[ToolType.SELECT].isChecked()

    def test_set_active_tool_reselecting_select_rechecks_it(self, toolbar) -> None:
        """After a non-main tool unchecked everything, switching back to
        SELECT must re-check it."""
        toolbar.set_active_tool(ToolType.CONSTRAINT_EQUAL)
        assert toolbar._button_group.checkedButton() is None

        toolbar.set_active_tool(ToolType.SELECT)

        assert toolbar._buttons[ToolType.SELECT].isChecked()
        assert toolbar._button_group.checkedButton() is toolbar._buttons[ToolType.SELECT]

    def test_select_button_shortcut(self, toolbar) -> None:
        """Test Select button has V shortcut."""
        shortcut = toolbar._buttons[ToolType.SELECT].shortcut()
        assert shortcut.toString() == "V"

    def test_measure_button_shortcut(self, toolbar) -> None:
        """Test Measure button has M shortcut."""
        shortcut = toolbar._buttons[ToolType.MEASURE].shortcut()
        assert shortcut.toString() == "M"

    def test_button_tooltips(self, toolbar) -> None:
        """Test buttons have tooltips."""
        for button in toolbar._buttons.values():
            assert button.toolTip() != ""
