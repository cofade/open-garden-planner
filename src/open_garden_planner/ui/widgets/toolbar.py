"""Main toolbar with core drawing and selection tools (CAD-style)."""

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QButtonGroup,
    QToolBar,
    QToolButton,
    QWidget,
)

from open_garden_planner.core.tools import ToolType

_ICONS_DIR = Path(__file__).parent.parent.parent / "resources" / "icons" / "tools"


class MainToolbar(QToolBar):
    """CAD-style top toolbar with core tools: Select, Measure, basic shapes.

    All garden-specific objects (structures, plants, surfaces, etc.) live
    in the Object Gallery sidebar panel instead.

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

    def _load_icon(self, icon_name: str) -> QIcon | None:
        """Load an SVG icon from the tools icon directory.

        Args:
            icon_name: SVG filename without extension

        Returns:
            QIcon if found, None otherwise
        """
        svg_path = _ICONS_DIR / f"{icon_name}.svg"
        if not svg_path.exists():
            return None
        renderer = QSvgRenderer(str(svg_path))
        if not renderer.isValid():
            return None
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def _setup_toolbar(self) -> None:
        """Create tool buttons."""
        self.setMovable(False)
        self.setOrientation(Qt.Orientation.Horizontal)
        self.setIconSize(QSize(24, 24))

        # --- Selection & Measurement ---
        self._add_tool_button(
            ToolType.SELECT, "select", "Select (V)",
            "Select and move objects", "V",
        )
        self._add_tool_button(
            ToolType.MEASURE, "measure", "Measure (M)",
            "Measure distances between two points", "M",
        )

        # Select tool is default
        self._buttons[ToolType.SELECT].setChecked(True)

    def _add_tool_button(
        self,
        tool_type: ToolType,
        icon_name: str,
        label: str,
        tooltip: str,
        shortcut: str,
    ) -> None:
        """Add a tool button with icon and tooltip.

        Args:
            tool_type: The tool type this button activates
            icon_name: SVG icon filename (without .svg)
            label: Short label for the button
            tooltip: Detailed tooltip text
            shortcut: Keyboard shortcut letter
        """
        button = QToolButton()
        button.setCheckable(True)
        button.setToolTip(f"{tooltip} ({shortcut})" if shortcut else tooltip)

        # Load SVG icon
        icon = self._load_icon(icon_name)
        if icon:
            button.setIcon(icon)
            button.setIconSize(QSize(24, 24))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        else:
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        button.setFixedSize(36, 36)
        if shortcut:
            button.setShortcut(shortcut)

        self._button_group.addButton(button)
        self._buttons[tool_type] = button
        self.addWidget(button)

    def _connect_signals(self) -> None:
        """Connect button signals."""
        for tool_type, button in self._buttons.items():
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
