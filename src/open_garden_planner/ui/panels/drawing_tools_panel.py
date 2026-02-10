"""Drawing tools panel with SVG icon-based tool buttons."""

from pathlib import Path

from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.tools import ToolType


class DrawingToolsPanel(QWidget):
    """Panel with SVG icon-based buttons for all drawing tools.

    Tools are organized into categories with colorful, descriptive icons.
    Icons are loaded from SVG files in resources/icons/tools/.
    Falls back to emoji if SVG file not found.
    """

    tool_selected = pyqtSignal(ToolType)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the drawing tools panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._buttons: dict[ToolType, QToolButton] = {}
        self._icons_dir = Path(__file__).parent.parent.parent / "resources" / "icons" / "tools"
        self._setup_ui()

    def _load_icon(self, icon_name: str, fallback_emoji: str) -> QIcon | str:
        """Load an SVG icon or fall back to emoji.

        Args:
            icon_name: Name of the SVG file (without .svg extension)
            fallback_emoji: Emoji to use if SVG not found

        Returns:
            QIcon if SVG found, emoji string otherwise
        """
        svg_path = self._icons_dir / f"{icon_name}.svg"
        if svg_path.exists():
            # Load SVG and create QIcon
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QPainter

            renderer = QSvgRenderer(str(svg_path))
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.GlobalColor.transparent)  # Transparent background
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return QIcon(pixmap)
        return fallback_emoji

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # SELECTION & MEASUREMENT
        self._add_category(self.tr("Selection & Measurement"), layout)
        grid1 = QGridLayout()
        grid1.setSpacing(0)
        self._add_tool(grid1, 0, 0, ToolType.SELECT, "select", "↖️", "Select (V)", "V")
        self._add_tool(grid1, 0, 1, ToolType.MEASURE, "measure", "📐", "Measure (M)", "M")
        layout.addLayout(grid1)

        # BASIC SHAPES
        self._add_category(self.tr("Basic Shapes"), layout)
        grid2 = QGridLayout()
        grid2.setSpacing(0)
        self._add_tool(grid2, 0, 0, ToolType.RECTANGLE, "rectangle", "⬜", "Rectangle (R)", "R")
        self._add_tool(grid2, 0, 1, ToolType.POLYGON, "polygon", "⬢", "Polygon (P)", "P")
        self._add_tool(grid2, 0, 2, ToolType.CIRCLE, "circle", "⭕", "Circle (C)", "C")
        layout.addLayout(grid2)

        # STRUCTURES
        self._add_category(self.tr("Structures"), layout)
        grid3 = QGridLayout()
        grid3.setSpacing(0)
        self._add_tool(grid3, 0, 0, ToolType.HOUSE, "house", "🏠", "House (H)", "H")
        self._add_tool(grid3, 0, 1, ToolType.GARAGE_SHED, "shed", "🛖", "Garage/Shed", "")
        self._add_tool(grid3, 0, 2, ToolType.GREENHOUSE, "greenhouse", "🪟", "Greenhouse", "")
        layout.addLayout(grid3)

        # HARDSCAPE
        self._add_category(self.tr("Hardscape"), layout)
        grid4 = QGridLayout()
        grid4.setSpacing(0)
        self._add_tool(grid4, 0, 0, ToolType.TERRACE_PATIO, "terrace", "🟫", "Terrace (T)", "T")
        self._add_tool(grid4, 0, 1, ToolType.DRIVEWAY, "driveway", "🛣️", "Driveway (D)", "D")
        self._add_tool(grid4, 0, 2, ToolType.POND_POOL, "pond", "💧", "Pond/Pool", "")
        layout.addLayout(grid4)

        # LINEAR FEATURES
        self._add_category(self.tr("Linear Features"), layout)
        grid5 = QGridLayout()
        grid5.setSpacing(0)
        self._add_tool(grid5, 0, 0, ToolType.FENCE, "fence", "🪵", "Fence (F)", "F")
        self._add_tool(grid5, 0, 1, ToolType.WALL, "wall", "🧱", "Wall (W)", "W")
        self._add_tool(grid5, 0, 2, ToolType.PATH, "path", "👣", "Path (L)", "L")
        layout.addLayout(grid5)

        # GARDEN
        self._add_category(self.tr("Garden"), layout)
        grid6 = QGridLayout()
        grid6.setSpacing(0)
        self._add_tool(grid6, 0, 0, ToolType.GARDEN_BED, "garden_bed", "🌱", "Garden Bed (B)", "B")
        layout.addLayout(grid6)

        # PLANTS
        self._add_category(self.tr("Plants"), layout)
        grid7 = QGridLayout()
        grid7.setSpacing(0)
        self._add_tool(grid7, 0, 0, ToolType.TREE, "tree", "🌳", "Tree (1)", "1")
        self._add_tool(grid7, 0, 1, ToolType.SHRUB, "shrub", "🪴", "Shrub (2)", "2")
        self._add_tool(grid7, 0, 2, ToolType.PERENNIAL, "flower", "🌸", "Perennial (3)", "3")
        layout.addLayout(grid7)

        layout.addStretch()

        # Select tool is default
        if ToolType.SELECT in self._buttons:
            self._buttons[ToolType.SELECT].setChecked(True)

    def _add_category(self, title: str, layout: QVBoxLayout) -> None:
        """Add a category header label.

        Args:
            title: Category title
            layout: Layout to add to
        """
        label = QLabel(title)
        layout.addWidget(label)

    def _add_tool(
        self,
        grid: QGridLayout,
        row: int,
        col: int,
        tool_type: ToolType,
        icon_name: str,
        fallback_emoji: str,
        tooltip: str,
        shortcut: str,
    ) -> None:
        """Add a tool button to the grid.

        Args:
            grid: Grid layout to add to
            row: Row position
            col: Column position
            tool_type: The tool type
            icon_name: Name of SVG icon file (without .svg)
            fallback_emoji: Emoji to use if SVG not found
            tooltip: Tooltip text
            shortcut: Keyboard shortcut
        """
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setCheckable(True)
        button.setFixedSize(44, 44)

        # Load icon (SVG or emoji fallback)
        icon_or_emoji = self._load_icon(icon_name, fallback_emoji)
        if isinstance(icon_or_emoji, QIcon):
            button.setIcon(icon_or_emoji)
            button.setIconSize(QSize(32, 32))
        else:
            # Fallback to emoji
            button.setText(icon_or_emoji)
            font = button.font()
            font.setPointSize(18)
            button.setFont(font)

        # Set keyboard shortcut
        if shortcut:
            button.setShortcut(shortcut)

        self._button_group.addButton(button)
        self._buttons[tool_type] = button

        # Connect signal
        button.clicked.connect(lambda: self.tool_selected.emit(tool_type))

        grid.addWidget(button, row, col)

    def set_active_tool(self, tool_type: ToolType) -> None:
        """Set the active tool.

        Args:
            tool_type: The tool type to activate
        """
        if tool_type in self._buttons:
            self._buttons[tool_type].setChecked(True)
