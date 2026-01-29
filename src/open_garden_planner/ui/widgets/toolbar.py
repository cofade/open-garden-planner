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

        self.addSeparator()

        # Generic shapes
        self._add_tool_button(
            ToolType.RECTANGLE,
            "Rectangle",
            "Draw rectangle (R)\nHold Shift for square",
            "R",
        )

        self._add_tool_button(
            ToolType.POLYGON,
            "Polygon",
            "Draw polygon (P)\nClick to add vertices, double-click to close",
            "P",
        )

        self._add_tool_button(
            ToolType.CIRCLE,
            "Circle",
            "Draw circle (C)\nClick center, then click rim point",
            "C",
        )

        self.addSeparator()

        # Property objects - Structures
        self._add_tool_button(
            ToolType.HOUSE,
            "House",
            "Draw house footprint (H)\nClick to add vertices, double-click to close",
            "H",
        )

        self._add_tool_button(
            ToolType.GARAGE_SHED,
            "Garage/Shed",
            "Draw garage/shed footprint\nClick to add vertices, double-click to close",
            "",
        )

        self._add_tool_button(
            ToolType.GREENHOUSE,
            "Greenhouse",
            "Draw greenhouse\nClick to add vertices, double-click to close",
            "",
        )

        # Property objects - Hardscape
        self._add_tool_button(
            ToolType.TERRACE_PATIO,
            "Terrace",
            "Draw terrace/patio (T)\nClick to add vertices, double-click to close",
            "T",
        )

        self._add_tool_button(
            ToolType.DRIVEWAY,
            "Driveway",
            "Draw driveway (D)\nClick to add vertices, double-click to close",
            "D",
        )

        # Property objects - Linear features
        self._add_tool_button(
            ToolType.FENCE,
            "Fence",
            "Draw fence (F)\nClick to add points, double-click to finish",
            "F",
        )

        self._add_tool_button(
            ToolType.WALL,
            "Wall",
            "Draw wall (W)\nClick to add points, double-click to finish",
            "W",
        )

        self._add_tool_button(
            ToolType.PATH,
            "Path",
            "Draw path (L)\nClick to add points, double-click to finish",
            "L",
        )

        # Property objects - Water features
        self._add_tool_button(
            ToolType.POND_POOL,
            "Pond/Pool",
            "Draw pond or pool\nClick to add vertices, double-click to close",
            "",
        )

        self.addSeparator()

        # Measure tool
        self._add_tool_button(
            ToolType.MEASURE,
            "Measure",
            "Measure distances (M)\nClick two points to measure",
            "M",
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
