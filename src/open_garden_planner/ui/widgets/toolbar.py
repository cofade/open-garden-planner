"""Main toolbar with core drawing and selection tools (CAD-style).

Object-category dropdowns and the global object search live in the
separate `CategoryToolbar`, added to the right of the constraint toolbar.
"""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QToolBar,
    QToolButton,
    QWidget,
)

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.icons import get_icon


class MainToolbar(QToolBar):
    """CAD-style top toolbar with core tools: Select, Measure, annotations.

    Signals:
        tool_selected: Emitted when a tool button is clicked (ToolType)
    """

    tool_selected = pyqtSignal(ToolType)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(self.tr("Tools"), parent)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._buttons: dict[ToolType, QToolButton] = {}
        self._icon_names: dict[ToolType, str] = {}

        self._setup_toolbar()
        self._connect_signals()

    def _load_icon(self, icon_name: str) -> QIcon | None:
        """Load a themed icon from the central provider (ui/icons.py)."""
        return get_icon(icon_name)

    def _setup_toolbar(self) -> None:
        self.setMovable(False)
        self.setOrientation(Qt.Orientation.Horizontal)
        self.setIconSize(QSize(24, 24))

        self._add_tool_button(
            ToolType.SELECT, "select", self.tr("Select (V)"),
            self.tr("Select and move objects"), "V",
        )
        self._add_tool_button(
            ToolType.MEASURE, "measure", self.tr("Measure (M)"),
            self.tr("Measure distances between two points"), "M",
        )
        self._add_tool_button(
            ToolType.TEXT, "text_annotation", self.tr("Text"),
            self.tr("Place a text annotation"), "",
        )
        self._add_tool_button(
            ToolType.CALLOUT, "callout_annotation", self.tr("Callout"),
            self.tr("Place a callout annotation with leader line"), "",
        )
        self._add_tool_button(
            ToolType.JOURNAL_PIN, "journal_pin", self.tr("Journal Pin"),
            self.tr("Drop a garden-journal note pin"), "J",
        )

        self._buttons[ToolType.SELECT].setChecked(True)

    def _add_tool_button(
        self,
        tool_type: ToolType,
        icon_name: str,
        label: str,
        tooltip: str,
        shortcut: str,
    ) -> None:
        button = QToolButton()
        button.setCheckable(True)
        button.setToolTip(f"{tooltip} ({shortcut})" if shortcut else tooltip)

        self._icon_names[tool_type] = icon_name
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
        for tool_type, button in self._buttons.items():
            button.clicked.connect(
                lambda _checked, tt=tool_type: self.tool_selected.emit(tt)
            )

    def set_active_tool(self, tool_type: ToolType) -> None:
        if tool_type in self._buttons:
            self._buttons[tool_type].setChecked(True)

    def refresh_theme_icons(self) -> None:
        """Re-request all button icons after a theme switch (see §8.21)."""
        for tool_type, icon_name in self._icon_names.items():
            icon = self._load_icon(icon_name)
            if icon is not None:
                self._buttons[tool_type].setIcon(icon)
