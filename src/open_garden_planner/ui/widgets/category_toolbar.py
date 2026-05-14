"""Toolbar with object-category dropdowns and the global search field.

Sits to the right of the MainToolbar and ConstraintToolbar — gives one-click
access to every placeable object, organised by category. Mirrors the click
flow that used to live in the sidebar's `GalleryPanel`.
"""

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QSizePolicy, QToolBar, QToolButton, QWidget

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.widgets.category_dropdown import CategoryDropdown
from open_garden_planner.ui.widgets.gallery_data import (
    GalleryCategory,
    build_toolbar_categories,
)
from open_garden_planner.ui.widgets.global_search import GlobalSearchField

_ICONS_DIR = Path(__file__).parent.parent.parent / "resources" / "icons" / "tools"


class CategoryToolbar(QToolBar):
    """Category-buttons + global search, positioned right of constraints."""

    tool_selected = pyqtSignal(ToolType)
    item_selected = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(self.tr("Categories"), parent)

        self._categories: list[GalleryCategory] = build_toolbar_categories()
        self._category_buttons: list[QToolButton] = []
        self._category_dropdowns: list[CategoryDropdown] = []
        self._search_field: GlobalSearchField | None = None

        self._setup_toolbar()

    def _load_icon(self, icon_name: str) -> QIcon | None:
        if not icon_name:
            return None
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

        for category in self._categories:
            self._add_category_button(category)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        self._search_field = GlobalSearchField(self._categories, self)
        self._search_field.tool_selected.connect(self.tool_selected)
        self._search_field.item_selected.connect(self.item_selected)
        self.addWidget(self._search_field)

        focus_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        focus_shortcut.activated.connect(self._focus_search)

    def _add_category_button(self, category: GalleryCategory) -> None:
        button = QToolButton()
        button.setCheckable(False)
        button.setToolTip(category.name)
        button.setFixedSize(36, 36)

        icon = self._load_icon(category.icon_name)
        if icon:
            button.setIcon(icon)
            button.setIconSize(QSize(24, 24))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        else:
            button.setText(category.name[:2])

        dropdown = CategoryDropdown(category)
        dropdown.tool_selected.connect(self.tool_selected)
        dropdown.item_selected.connect(self.item_selected)

        button.clicked.connect(lambda _checked, b=button, d=dropdown: d.show_below(b))

        self.addWidget(button)
        self._category_buttons.append(button)
        self._category_dropdowns.append(dropdown)

    def _focus_search(self) -> None:
        if self._search_field is not None:
            self._search_field.setFocus()
            self._search_field.selectAll()
