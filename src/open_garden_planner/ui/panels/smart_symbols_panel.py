"""Smart Symbols library panel (US-C4).

Lists the available parametric symbols (bundled + user). Double-clicking a
symbol (or pressing Insert) emits ``symbol_selected(symbol_id)``; the
application drops a :class:`SmartSymbolItem` with default params on the canvas.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services.smart_symbol_library import get_smart_symbol_library


class SmartSymbolsPanel(QWidget):
    """A searchable list of parametric smart symbols."""

    symbol_selected = pyqtSignal(str)  # symbol_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self.reload()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._search = QLineEdit()
        self._search.setPlaceholderText(self.tr("Search symbols…"))
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._emit_for_item)
        layout.addWidget(self._list)

        self._insert_btn = QPushButton(self.tr("Insert"))
        self._insert_btn.clicked.connect(self._emit_for_current)
        layout.addWidget(self._insert_btn)

    def reload(self) -> None:
        """Re-read the library and repopulate the list."""
        from open_garden_planner.app.settings import get_settings

        lang = get_settings().language
        self._list.clear()
        for definition in get_smart_symbol_library().definitions():
            item = QListWidgetItem(definition.display_name(lang))
            item.setData(Qt.ItemDataRole.UserRole, definition.id)
            item.setToolTip(definition.category)
            self._list.addItem(item)
        self._apply_filter(self._search.text())

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _emit_for_item(self, item: QListWidgetItem) -> None:
        symbol_id = item.data(Qt.ItemDataRole.UserRole)
        if symbol_id:
            self.symbol_selected.emit(str(symbol_id))

    def _emit_for_current(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            self._emit_for_item(item)
