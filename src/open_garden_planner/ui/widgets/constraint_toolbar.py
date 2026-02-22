"""FreeCAD-style horizontal constraint toolbar.

Shows all constraint tools in a row. Implemented tools are fully active;
not-yet-implemented tools appear grayed out with a "coming soon" tooltip.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QCoreApplication, QSize, Qt, pyqtSignal
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


class _ToolEntry(NamedTuple):
    """Descriptor for one button in the constraint toolbar."""

    icon_name: str
    tooltip_key: str       # untranslated English string (translated at runtime)
    shortcut: str
    tool_type: ToolType | None  # None → not yet implemented (disabled button)


# Separator sentinel
_SEP = None

# Full toolbar layout: implemented tools first, then grouped by category.
_TOOLBAR_ENTRIES: list[_ToolEntry | None] = [
    # ── Dimensional ──────────────────────────────────────────────────────────
    _ToolEntry("constraint_distance",   "Distance Constraint (K)", "K", ToolType.CONSTRAINT),
    _ToolEntry("constraint_h_distance", "Horizontal Distance (coming soon)", "",  None),
    _ToolEntry("constraint_v_distance", "Vertical Distance (coming soon)",   "",  None),
    _SEP,
    # ── Geometric alignment ───────────────────────────────────────────────────
    _ToolEntry("constraint_horizontal", "Horizontal Alignment", "", ToolType.CONSTRAINT_HORIZONTAL),
    _ToolEntry("constraint_vertical",   "Vertical Alignment",   "", ToolType.CONSTRAINT_VERTICAL),
    _SEP,
    # ── Geometric relational ──────────────────────────────────────────────────
    _ToolEntry("constraint_coincident",    "Coincident (coming soon)",    "", None),
    _ToolEntry("constraint_parallel",      "Parallel (coming soon)",      "", None),
    _ToolEntry("constraint_perpendicular", "Perpendicular (coming soon)", "", None),
    _ToolEntry("constraint_equal",         "Equal Size (coming soon)",    "", None),
    _ToolEntry("constraint_fixed",         "Fix in Place (coming soon)",  "", None),
    _SEP,
    # ── Advanced ──────────────────────────────────────────────────────────────
    _ToolEntry("constraint_angle",     "Angle Constraint", "", ToolType.CONSTRAINT_ANGLE),
    _ToolEntry("constraint_symmetric", "Symmetry (coming soon)",         "", None),
]


class ConstraintToolbar(QToolBar):
    """Horizontal toolbar with all constraint tools (FreeCAD Sketcher style).

    Implemented tools are enabled and checkable. Not-yet-implemented tools
    are shown with grayed-out icons and disabled, acting as a roadmap preview.

    Signals:
        tool_selected: Emitted when an enabled tool button is clicked (ToolType).
    """

    tool_selected = pyqtSignal(ToolType)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            QCoreApplication.translate("ConstraintToolbar", "Constraints"), parent
        )
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._buttons: dict[ToolType, QToolButton] = {}

        self._setup_toolbar()

    def _load_icon(self, icon_name: str) -> QIcon | None:
        """Load an SVG icon from the tools icon directory, rendered at 28×28 px."""
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
        self.setMovable(False)
        self.setOrientation(Qt.Orientation.Horizontal)
        self.setIconSize(QSize(24, 24))

        for entry in _TOOLBAR_ENTRIES:
            if entry is _SEP:
                self.addSeparator()
                continue

            implemented = entry.tool_type is not None
            tooltip = QCoreApplication.translate("ConstraintToolbar", entry.tooltip_key)

            button = QToolButton()
            button.setCheckable(implemented)
            button.setEnabled(implemented)
            button.setToolTip(f"{tooltip} ({entry.shortcut})" if entry.shortcut else tooltip)
            button.setFixedSize(36, 36)

            icon = self._load_icon(entry.icon_name)
            if icon:
                button.setIcon(icon)
                button.setIconSize(QSize(24, 24))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            else:
                # Fallback text label derived from icon name
                button.setText(entry.icon_name.replace("constraint_", "").upper()[:3])
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

            if implemented:
                if entry.shortcut:
                    button.setShortcut(entry.shortcut)
                self._button_group.addButton(button)
                self._buttons[entry.tool_type] = button  # type: ignore[index]
                tool_type = entry.tool_type
                button.clicked.connect(
                    lambda _checked, tt=tool_type: self.tool_selected.emit(tt)
                )

            self.addWidget(button)

    def set_active_tool(self, tool_type: ToolType) -> None:
        """Highlight the button for the given tool type (called on external tool change).

        Args:
            tool_type: The tool type that became active.
        """
        if tool_type in self._buttons:
            self._buttons[tool_type].setChecked(True)
        else:
            # A non-constraint tool is active — uncheck all constraint buttons
            checked = self._button_group.checkedButton()
            if checked:
                self._button_group.setExclusive(False)
                checked.setChecked(False)
                self._button_group.setExclusive(True)
