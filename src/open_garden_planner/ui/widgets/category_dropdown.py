"""Popup dropdown showing thumbnails of items in a single category.

Opens directly under a toolbar category button. Supports click-to-activate
and drag-to-canvas, plus an in-popup search field that filters thumbnails.
"""

from PyQt6.QtCore import QMimeData, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.widgets.gallery_data import (
    THUMB_SIZE,
    GalleryCategory,
    GalleryItem,
)

GRID_COLS = 3
DRAG_THRESHOLD = 10


class _ThumbnailButton(QToolButton):
    """Single thumbnail button inside the dropdown grid."""

    clicked_item = pyqtSignal(object)

    def __init__(self, item: GalleryItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item = item
        self._drag_start_pos: QPoint | None = None

        self.setFixedSize(THUMB_SIZE + 16, THUMB_SIZE + 24)
        self.setToolTip(item.name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        thumb_label = QLabel()
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        if item.thumbnail and not item.thumbnail.isNull():
            scaled = item.thumbnail.scaled(
                THUMB_SIZE - 4,
                THUMB_SIZE - 4,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb_label.setPixmap(scaled)
        else:
            thumb_label.setText("?")
            thumb_label.setStyleSheet("font-size: 20px;")
        layout.addWidget(thumb_label)

        name_label = QLabel(item.name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 9px;")
        name_label.setMaximumHeight(20)
        layout.addWidget(name_label)

        self.setStyleSheet("""
            QToolButton {
                border: 1px solid transparent;
                border-radius: 4px;
                background: transparent;
                padding: 2px;
            }
            QToolButton:hover {
                border: 1px solid palette(highlight);
                background: palette(midlight);
            }
            QToolButton:pressed { background: palette(mid); }
        """)

        self.clicked.connect(lambda: self.clicked_item.emit(self._item))

    @property
    def item(self) -> GalleryItem:
        return self._item

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._drag_start_pos is None:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < DRAG_THRESHOLD:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        drag_data = f"gallery:{self._item.tool_type.name}"
        if self._item.species:
            drag_data += f":species={self._item.species}"
        if self._item.plant_category:
            drag_data += f":category={self._item.plant_category.name}"
        mime_data.setText(drag_data)
        drag.setMimeData(mime_data)

        if self._item.thumbnail and not self._item.thumbnail.isNull():
            drag_pixmap = self._item.thumbnail.scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            drag.setPixmap(drag_pixmap)
            drag.setHotSpot(QPoint(24, 24))

        drag.exec(Qt.DropAction.CopyAction)


class CategoryDropdown(QWidget):
    """Popup panel listing all items of one category as a thumbnail grid.

    Constructed once per toolbar category button. Opens beneath the button
    when triggered, closes on click-outside or after an item is chosen.
    """

    tool_selected = pyqtSignal(ToolType)
    item_selected = pyqtSignal(object)

    def __init__(self, category: GalleryCategory, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self._category = category
        self._buttons: list[_ThumbnailButton] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("CategoryDropdown")
        self.setStyleSheet("""
            #CategoryDropdown {
                background: palette(window);
                border: 1px solid palette(mid);
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        header = QLabel(self._category.name)
        header.setStyleSheet("font-weight: bold; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(header)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText(self.tr("Filter…"))
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search_box)

        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(4)

        for i, item in enumerate(self._category.items):
            row = i // GRID_COLS
            col = i % GRID_COLS
            btn = _ThumbnailButton(item)
            btn.clicked_item.connect(self._on_item_clicked)
            grid_layout.addWidget(btn, row, col)
            self._buttons.append(btn)

        layout.addWidget(grid_widget)

        self.adjustSize()
        max_width = (THUMB_SIZE + 16) * GRID_COLS + 32
        self.setFixedWidth(max_width)

    def _on_item_clicked(self, item: GalleryItem) -> None:
        self.tool_selected.emit(item.tool_type)
        self.item_selected.emit(item)
        self.close()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for btn in self._buttons:
            visible = not needle or needle in btn.item.name.lower()
            btn.setVisible(visible)

    def show_below(self, anchor: QWidget) -> None:
        """Show the popup directly beneath the given anchor widget."""
        self._search_box.clear()
        self._search_box.setFocus()
        anchor_bottom_left = anchor.mapToGlobal(anchor.rect().bottomLeft())
        self.move(anchor_bottom_left)
        self.show()
