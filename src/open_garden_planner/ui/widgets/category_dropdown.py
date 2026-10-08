"""Popup dropdown showing thumbnails of items in a single category.

Opens directly under a toolbar category button. Supports click-to-activate
and drag-to-canvas, plus an in-popup search field that filters thumbnails.
"""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QMimeData, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.theme import set_text_role
from open_garden_planner.ui.widgets.gallery_data import (
    THUMB_SIZE,
    GalleryCategory,
    GalleryItem,
)

if TYPE_CHECKING:
    from open_garden_planner.models.plant_data import PlantSpeciesData

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
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if self._item.species:
            from open_garden_planner.models.plant_lists import (  # noqa: PLC0415
                get_plant_list_store,
            )

            self._list_store = get_plant_list_store()
            self._list_store.changed.connect(self._on_store_changed)
        else:
            self._list_store = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        thumb_label = QLabel()
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self._thumb_label = thumb_label
        if item.thumbnail and not item.thumbnail.isNull():
            self.update_thumbnail()
        else:
            thumb_label.setText("?")
            thumb_label.setStyleSheet("font-size: 20px;")
        layout.addWidget(thumb_label)

        star_badge = QLabel(thumb_label)
        star_badge.setText("⭐")
        star_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        star_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        star_badge.setFixedSize(14, 14)
        star_badge.setStyleSheet(
            "font-size: 10px; background: rgba(0, 0, 0, 0.55); border-radius: 7px; padding: 0px;"
        )
        star_badge.move(THUMB_SIZE - 15, 1)
        star_badge.setVisible(False)
        self._star_badge = star_badge

        name_label = QLabel(item.name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 9px;")
        name_label.setMaximumHeight(20)
        layout.addWidget(name_label)

        self._update_favorite_state()

        # Styled by theme.py's #CategoryDropdown QToolButton rules — the old
        # palette()-based QSS tracked the OS palette, not our theme.
        self.clicked.connect(lambda: self.clicked_item.emit(self._item))

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        self._update_favorite_state()

    def _on_store_changed(self) -> None:
        """Update favorite star badge and tooltip when store changes."""
        self._update_favorite_state()

    def _get_species_obj(self) -> "PlantSpeciesData":
        from open_garden_planner.models.plant_data import (  # noqa: PLC0415
            PlantSpeciesData,
        )
        from open_garden_planner.services.bundled_species_db import (  # noqa: PLC0415
            lookup_species,
        )

        meta = lookup_species(self._item.species) or lookup_species(self._item.name)
        if meta:
            return PlantSpeciesData.from_dict(meta)
        return PlantSpeciesData(
            scientific_name=self._item.species,
            common_name=self._item.name,
        )

    def _update_favorite_state(self) -> None:
        """Update button star badge and tooltip if item is favorited."""
        if not self._item.species:
            self.setToolTip(self._item.name)
            if hasattr(self, "_star_badge"):
                self._star_badge.setVisible(False)
            return
        from open_garden_planner.models.plant_lists import (  # noqa: PLC0415
            get_plant_list_store,
        )

        store = get_plant_list_store()
        obj = self._get_species_obj()
        is_fav = (
            store.is_favorite(obj)
            or store.is_favorite(self._item.species)
            or store.is_favorite(self._item.name)
        )
        if hasattr(self, "_star_badge"):
            self._star_badge.setVisible(is_fav)
        if is_fav:
            self.setToolTip(f"⭐ {self._item.name}")
        else:
            self.setToolTip(self._item.name)

    _update_tooltip = _update_favorite_state

    def contextMenuEvent(self, event) -> None:  # noqa: N802 — Qt override
        """Show context menu for plant gallery items (Favorites and List management)."""
        if not self._item.species:
            super().contextMenuEvent(event)
            return

        from open_garden_planner.models.plant_lists import (  # noqa: PLC0415
            get_plant_list_store,
        )

        store = get_plant_list_store()
        obj = self._get_species_obj()
        is_fav = store.is_favorite(obj) or store.is_favorite(self._item.species) or store.is_favorite(self._item.name)

        menu = QMenu(self)

        if is_fav:
            fav_action = menu.addAction(
                QCoreApplication.translate("CategoryDropdown", "Remove from Favorites")
            )
            fav_action.triggered.connect(lambda: store.toggle_favorite(obj))
        else:
            fav_action = menu.addAction(
                QCoreApplication.translate("CategoryDropdown", "Add to Favorites")
            )
            fav_action.triggered.connect(lambda: store.toggle_favorite(obj))

        custom_lists = [pl for pl in store.all_lists() if pl.id != store.FAVORITES_ID]
        if custom_lists:
            sub_menu = menu.addMenu(
                QCoreApplication.translate("CategoryDropdown", "Add to List")
            )
            for pl in custom_lists:
                action = sub_menu.addAction(pl.name)
                action.triggered.connect(
                    lambda _checked=False, target_id=pl.id: store.add_entry(
                        target_id, self._get_species_obj()
                    )
                )

        menu.exec(event.globalPos())

    @property
    def item(self) -> GalleryItem:
        return self._item

    def update_thumbnail(self) -> None:
        """Refresh the pixmap from the (possibly re-rendered) gallery item."""
        if self._item.thumbnail is None or self._item.thumbnail.isNull():
            return
        scaled = self._item.thumbnail.scaled(
            THUMB_SIZE - 4,
            THUMB_SIZE - 4,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumb_label.setPixmap(scaled)

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
        # Styled by theme.py's #CategoryDropdown rule; a custom QWidget only
        # paints a stylesheet background with WA_StyledBackground set.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        header = QLabel(self._category.name)
        set_text_role(header, "h2")
        header.setStyleSheet("padding: 2px 4px;")
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

    def refresh_thumbnails(self) -> None:
        """Re-pull each button's pixmap after a theme switch (see §8.21)."""
        for btn in self._buttons:
            btn.update_thumbnail()

    def show_below(self, anchor: QWidget) -> None:
        """Show the popup directly beneath the given anchor widget."""
        self._search_box.clear()
        self._search_box.setFocus()
        for btn in self._buttons:
            btn._update_favorite_state()
        anchor_bottom_left = anchor.mapToGlobal(anchor.rect().bottomLeft())
        self.move(anchor_bottom_left)
        self.show()


# Backwards compatibility / descriptive alias
CategoryItemButton = _ThumbnailButton

