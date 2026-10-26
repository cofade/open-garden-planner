"""Thumbnail catalog reused by Welcome and File > New from example."""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.app.settings import active_language
from open_garden_planner.services.example_library import gallery_entries


class TemplateGallery(QWidget):
    """Select a bundled example or a local template, then open an untitled copy."""

    template_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        intro = QLabel(self.tr("Open an example or local template as an untitled copy."))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(QSize(180, 110))
        self.list.setGridSize(QSize(210, 155))
        self.list.setWordWrap(True)
        for entry in gallery_entries(active_language()):
            row = QListWidgetItem(entry.name)
            row.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            row.setToolTip("\n".join(part for part in [entry.description, entry.license,
                                                   entry.attribution] if part))
            if entry.thumbnail:
                row.setIcon(QIcon(str(entry.thumbnail)))
            self.list.addItem(row)
        layout.addWidget(self.list, 1)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.description)
        self.open_button = QPushButton(self.tr("Open Selected"))
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open)
        layout.addWidget(self.open_button)
        self.list.currentItemChanged.connect(self._selection_changed)
        self.list.itemDoubleClicked.connect(self._open)

    def _selection_changed(self) -> None:
        row = self.list.currentItem()
        self.open_button.setEnabled(row is not None)
        self.description.setText(row.toolTip() if row else "")

    def _open(self) -> None:
        row = self.list.currentItem()
        if row:
            self.template_selected.emit(row.data(Qt.ItemDataRole.UserRole))
