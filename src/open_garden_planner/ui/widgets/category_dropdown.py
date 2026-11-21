"""Popup dropdown showing thumbnails of items in a single category.

Opens directly under a toolbar category button. Supports click-to-activate
and drag-to-canvas, plus an in-popup search field that filters thumbnails.
"""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QMimeData, QPoint, QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import (
    QContextMenuEvent,
    QDrag,
    QShowEvent,
)
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.theme import set_text_role
from open_garden_planner.ui.widgets.elided_label import ElidedLabel
from open_garden_planner.ui.widgets.gallery_data import (
    THUMB_SIZE,
    GalleryCategory,
    GalleryItem,
    gallery_matches,
)

if TYPE_CHECKING:
    from open_garden_planner.models.plant_data import PlantSpeciesData
    from open_garden_planner.models.plant_lists import PlantListStore

GRID_COLS = 3
DRAG_THRESHOLD = 10
TILE_WIDTH = THUMB_SIZE + 16
TILE_HEIGHT = THUMB_SIZE + 24
TILE_SPACING = 4
RESULT_GUTTER = 36  # Popup margins and room for the scrollbar.


class _ThumbnailButton(QToolButton):
    """Single thumbnail button inside the dropdown grid."""

    clicked_item = pyqtSignal(object)

    def __init__(self, item: GalleryItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item = item
        self._drag_start_pos: QPoint | None = None

        self.setFixedSize(TILE_WIDTH, TILE_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._list_store: PlantListStore | None = None
        if self._item.species:
            from open_garden_planner.models.plant_lists import (
                get_plant_list_store,
            )

            self._list_store = get_plant_list_store()
            self._list_store.changed.connect(self._on_store_changed)

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
        from open_garden_planner.ui.icons import get_pixmap

        pm = get_pixmap("star", size=14)
        if pm is not None:
            star_badge.setPixmap(pm)
        star_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        star_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        star_badge.setFixedSize(14, 14)
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

    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        self._update_favorite_state()

    def _on_store_changed(self) -> None:
        """Update favorite star badge and tooltip when store changes."""
        self._update_favorite_state()

    def _get_species_obj(self) -> "PlantSpeciesData":
        from open_garden_planner.models.plant_data import (
            PlantSpeciesData,
        )
        from open_garden_planner.services.bundled_species_db import (
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
        from open_garden_planner.models.plant_lists import (
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
            self.setToolTip(
                QCoreApplication.translate(
                    "CategoryDropdown", "{name} (Favorite)"
                ).format(name=self._item.name)
            )
        else:
            self.setToolTip(self._item.name)

    _update_tooltip = _update_favorite_state

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        """Show context menu for plant gallery items (Favorites and List management)."""
        if not self._item.species or event is None:
            super().contextMenuEvent(event)
            return

        from open_garden_planner.models.plant_lists import (
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
            if fav_action is not None:
                fav_action.triggered.connect(lambda: store.toggle_favorite(obj))
        else:
            fav_action = menu.addAction(
                QCoreApplication.translate("CategoryDropdown", "Add to Favorites")
            )
            if fav_action is not None:
                fav_action.triggered.connect(lambda: store.toggle_favorite(obj))

        custom_lists = [pl for pl in store.all_lists() if pl.id != store.FAVORITES_ID]
        if custom_lists:
            sub_menu = menu.addMenu(
                QCoreApplication.translate("CategoryDropdown", "Add to List")
            )
            if sub_menu is not None:
                for pl in custom_lists:
                    action = sub_menu.addAction(pl.name)
                    if action is not None:
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
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._category = category
        self._buttons: list[_ThumbnailButton] = []
        self._columns = GRID_COLS
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("CategoryDropdown")
        # Styled by theme.py's #CategoryDropdown rule; a custom QWidget only
        # paints a stylesheet background with WA_StyledBackground set.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self._layout = layout

        self._header = ElidedLabel(self._category.name)
        set_text_role(self._header, "h2")
        self._header.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._header)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText(self.tr("Filter…"))
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search_box)
        from open_garden_planner.ui.widgets.trait_filters import TraitFilters

        self.trait_filters = TraitFilters()
        self.trait_filters.changed.connect(lambda: self._apply_filter(self._search_box.text()))
        # Set the parent before changing visibility, or Qt shows this as a window.
        self._trait_scroll = QScrollArea(self)
        self._trait_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._trait_scroll.setWidgetResizable(True)
        self._trait_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._trait_scroll.setWidget(self.trait_filters)
        self._trait_scroll.setVisible(
            any(item.species or item.plant_category for item in self._category.items)
        )
        layout.addWidget(self._trait_scroll)

        self._results = QScrollArea()
        self._results.setFrameShape(QScrollArea.Shape.NoFrame)
        self._results.setWidgetResizable(True)
        self._results.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        grid_widget = QWidget()
        self._grid = QGridLayout(grid_widget)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(TILE_SPACING)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self._results.setWidget(grid_widget)
        layout.addWidget(self._results, stretch=1)

        self._empty = QLabel(self.tr("No matching items"), grid_widget)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grid.addWidget(self._empty, 0, 0, 1, GRID_COLS)
        for item in self._category.items:
            btn = _ThumbnailButton(item, grid_widget)
            btn.clicked_item.connect(self._on_item_clicked)
            self._buttons.append(btn)
        self._apply_filter("")

    def _on_item_clicked(self, item: GalleryItem) -> None:
        self.tool_selected.emit(item.tool_type)
        self.item_selected.emit(item)
        self.close()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        layers = self.trait_filters.layers
        functions = self.trait_filters.functions
        index = 0
        for btn in self._buttons:
            self._grid.removeWidget(btn)
            visible = gallery_matches(btn.item, needle, layers=layers, functions=functions)
            if visible:
                row, column = divmod(index, self._columns)
                self._grid.addWidget(btn, row, column)
                index += 1
            btn.setVisible(visible)
        self._empty.setVisible(index == 0)
        for bar in (self._results.verticalScrollBar(), self._results.horizontalScrollBar()):
            if bar is not None:
                bar.setValue(0)

    def refresh_thumbnails(self) -> None:
        """Re-pull each button's pixmap after a theme switch (see §8.21)."""
        for btn in self._buttons:
            btn.update_thumbnail()

    def show_below(self, anchor: QWidget) -> None:
        """Start a fresh browse session within the anchor screen's work area."""
        screen = anchor.screen()
        if screen is None:
            return
        work_area = screen.availableGeometry()
        columns = (work_area.width() - RESULT_GUTTER + TILE_SPACING) // (TILE_WIDTH + TILE_SPACING)
        self._columns = max(1, min(GRID_COLS, columns))
        with QSignalBlocker(self._search_box):
            self._search_box.clear()
        self.trait_filters.clear()
        self._apply_filter("")
        self._size_trait_controls(work_area.width(), work_area.height())
        layout = self._layout
        layout.activate()
        anchor_top = anchor.mapToGlobal(QPoint())
        anchor_bottom = anchor_top.y() + anchor.height()
        below = work_area.bottom() + 1 - anchor_bottom
        above = anchor_top.y() - work_area.top()
        chrome_height = layout.minimumSize().height()
        desired_height = chrome_height + self._grid.sizeHint().height()
        open_above = below < desired_height and above > below
        room = above if open_above else below
        minimum = chrome_height + min(TILE_HEIGHT, self._grid.sizeHint().height())
        available_height = work_area.height()
        if room >= minimum:
            available_height = min(available_height, room)
        height = min(desired_height, available_height)
        desired_width = max(
            layout.sizeHint().width(),
            self._header.sizeHint().width() + 12,
            self._grid.sizeHint().width() + RESULT_GUTTER,
        )
        if not self._trait_scroll.isHidden():
            desired_width = max(desired_width, self.trait_filters.sizeHint().width() + 32)
        width = min(desired_width, work_area.width())
        x = max(work_area.left(), min(anchor_top.x(), work_area.right() + 1 - width))
        y = anchor_top.y() - height if open_above else anchor_bottom
        y = max(work_area.top(), min(y, work_area.bottom() + 1 - height))
        self.setGeometry(x, y, width, height)
        self.show()
        self._search_box.setFocus()

    def _size_trait_controls(self, screen_width: int, screen_height: int) -> None:
        if self._trait_scroll.isHidden():
            return
        self.ensurePolished()
        style = self.style()
        scrollbar = style.pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent) if style else 0
        margins = self._layout.contentsMargins()
        self.trait_filters.fit_width(screen_width - margins.left() - margins.right() - scrollbar)
        hint = self.trait_filters.sizeHint()
        # Budget the chips after reserving the search and a whole results row.
        self._trait_scroll.setFixedHeight(0)
        self._layout.activate()
        headroom = screen_height - self._layout.minimumSize().height() - TILE_HEIGHT
        self._trait_scroll.setFixedHeight(min(hint.height(), screen_height // 2, max(0, headroom)))
        for bar in (self._trait_scroll.verticalScrollBar(), self._trait_scroll.horizontalScrollBar()):
            if bar is not None:
                bar.setValue(0)


# Backwards compatibility / descriptive alias
CategoryItemButton = _ThumbnailButton

