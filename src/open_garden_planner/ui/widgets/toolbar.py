"""Main toolbar for drawing tools."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QToolBar,
    QToolButton,
    QWidget,
)

from open_garden_planner.core.tools import ToolType


class MainToolbar(QToolBar):
    """Toolbar with exclusive tool buttons.

    Signals:
        tool_selected: Emitted when a tool button is clicked (ToolType)
    """

    tool_selected = pyqtSignal(ToolType)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the toolbar.

        Args:
            parent: Parent widget
        """
        super().__init__("Tools", parent)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._buttons: dict[ToolType, QToolButton] = {}

        self._setup_toolbar()
        self._connect_signals()

    def _setup_toolbar(self) -> None:
        """Create tool buttons."""
        self.setMovable(False)
        self.setOrientation(Qt.Orientation.Horizontal)

        # Select tool
        self._add_tool_button(
            ToolType.SELECT,
            "Select",
            "Select and move objects (V)",
            "V",
        )

        # Rectangle tool
        self._add_tool_button(
            ToolType.RECTANGLE,
            "Rectangle",
            "Draw rectangles (R)\nHold Shift for square",
            "R",
        )

        # Polygon tool
        self._add_tool_button(
            ToolType.POLYGON,
            "Polygon",
            "Draw polygons (P)\nClick to add vertices\nDouble-click or Enter to close",
            "P",
        )

        # Select tool is default
        self._buttons[ToolType.SELECT].setChecked(True)

    def _add_tool_button(
        self,
        tool_type: ToolType,
        text: str,
        tooltip: str,
        shortcut: str,
    ) -> None:
        """Add a tool button to the toolbar.

        Args:
            tool_type: The tool type this button activates
            text: Button text
            tooltip: Tooltip text
            shortcut: Keyboard shortcut letter
        """
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCheckable(True)
        button.setShortcut(shortcut)

        # Style for visibility
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setMinimumWidth(70)

        self._button_group.addButton(button)
        self._buttons[tool_type] = button
        self.addWidget(button)

    def _connect_signals(self) -> None:
        """Connect button signals."""
        for tool_type, button in self._buttons.items():
            # Capture tool_type in closure
            button.clicked.connect(
                lambda _checked, tt=tool_type: self._on_button_clicked(tt)
            )

    def _on_button_clicked(self, tool_type: ToolType) -> None:
        """Handle button click.

        Args:
            tool_type: The tool type that was selected
        """
        self.tool_selected.emit(tool_type)

    def set_active_tool(self, tool_type: ToolType) -> None:
        """Update the toolbar to reflect the active tool.

        Args:
            tool_type: The currently active tool
        """
        if tool_type in self._buttons:
            self._buttons[tool_type].setChecked(True)
