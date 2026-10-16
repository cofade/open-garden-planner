"""Global object search field shown in the toolbar.

Live-searches across all gallery items as the user types. A results list
appears beneath the input; Enter or click on a result activates the
matching tool, mirroring the click flow of the category dropdowns.

The results popup is a `Qt.ToolTip` window (instead of `Qt.Popup`) so it
does *not* steal keyboard focus from the QLineEdit — otherwise every
keystroke after the first would land on the popup and be lost.
"""


from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.widgets.gallery_data import (
    GalleryCategory,
    GalleryItem,
    all_items,
)

MAX_RESULTS = 12


class _ResultsPopup(QWidget):
    """Non-activating popup list shown directly below the search field.

    Uses `Qt.ToolTip` + `WA_ShowWithoutActivating` so that showing this
    window does not move keyboard focus away from the search QLineEdit.
    """

    item_chosen = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("GlobalSearchResults")
        # Styled by theme.py's #GlobalSearchResults rule; a custom QWidget
        # only paints a stylesheet background with WA_StyledBackground set.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        from open_garden_planner.ui.widgets.trait_filters import TraitFilters

        self.trait_filters = TraitFilters(self)
        layout.addWidget(self.trait_filters)

        self._list = QListWidget()
        self._list.setIconSize(QSize(32, 32))
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.itemClicked.connect(self._on_item_activated)
        layout.addWidget(self._list)

        self.setFixedWidth(max(500, self.trait_filters.minimumSizeHint().width() + 16))

    def populate(self, items: list[GalleryItem]) -> None:
        self._list.clear()
        for item in items:
            list_item = QListWidgetItem(item.name)
            if item.thumbnail and not item.thumbnail.isNull():
                list_item.setIcon(QIcon(item.thumbnail))
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self._list.addItem(list_item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        self.setFixedHeight(min(280, max(40, self._list.count() * 40 + 16)) + self.trait_filters.sizeHint().height())

    def _on_item_activated(self, list_item: QListWidgetItem) -> None:
        item = list_item.data(Qt.ItemDataRole.UserRole)
        if item is not None:
            self.item_chosen.emit(item)
            self.hide()

    def activate_current(self) -> None:
        current = self._list.currentItem()
        if current is not None:
            self._on_item_activated(current)

    def move_selection(self, delta: int) -> None:
        row = self._list.currentRow() + delta
        row = max(0, min(self._list.count() - 1, row))
        self._list.setCurrentRow(row)


class GlobalSearchField(QLineEdit):
    """Toolbar search field with live results popup across all categories."""

    tool_selected = pyqtSignal(ToolType)
    item_selected = pyqtSignal(object)

    def __init__(
        self,
        categories: list[GalleryCategory],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._all_items = all_items(categories)
        self._popup = _ResultsPopup(self)
        self._popup.item_chosen.connect(self._on_item_chosen)

        self.setPlaceholderText(self.tr("Search object…"))
        self.setToolTip(self.tr("Search object…"))
        self.setClearButtonEnabled(True)
        self.setFixedWidth(240)
        self.textChanged.connect(self._on_text_changed)
        self._popup.trait_filters.changed.connect(lambda: self._on_text_changed(self.text()))

        # Tool-tip windows never auto-close on outside click; do it manually
        # whenever focus leaves the search field and is *not* taken by the
        # popup itself. Qt automatically disconnects app.focusChanged when
        # this QObject is destroyed.
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)

    def _on_text_changed(self, text: str) -> None:
        needle = text.strip().lower()
        filters = self._popup.trait_filters
        if not needle and not (filters.layers or filters.functions):
            self._popup.hide()
            return
        from open_garden_planner.ui.widgets.gallery_data import gallery_matches

        hits = [it for it in self._all_items if gallery_matches(
            it, needle, layers=filters.layers, functions=filters.functions)][:MAX_RESULTS]
        if not hits and not (filters.layers or filters.functions):
            self._popup.hide()
            return
        self._popup.populate(hits)
        bottom_left = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.move(bottom_left)
        self._popup.show()

    def _on_focus_changed(self, _old: QWidget | None, new: QWidget | None) -> None:
        # This is connected to the *application*-wide focusChanged, which
        # outlives the field. During teardown a stray callback can arrive after
        # this field's (or its popup's) C++ object is gone — ignore it rather
        # than raise from the dangling connection.
        try:
            if not self._popup.isVisible():
                return
            # Keep popup open if focus stays in the field or its clear-button
            # children, hide it otherwise.
            if new is self:
                return
            if new is not None and self._popup.isAncestorOf(new):
                return
            if new is not None and self.isAncestorOf(new):
                return
            self._popup.hide()
        except RuntimeError:
            return

    def _on_item_chosen(self, item: GalleryItem) -> None:
        self.tool_selected.emit(item.tool_type)
        self.item_selected.emit(item)
        self.clear()
        self._popup.hide()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if self._popup.isVisible():
            if key == Qt.Key.Key_Down:
                self._popup.move_selection(1)
                return
            if key == Qt.Key.Key_Up:
                self._popup.move_selection(-1)
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._popup.activate_current()
                return
            if key == Qt.Key.Key_Escape:
                self._popup.hide()
                self.clear()
                return
        super().keyPressEvent(event)
