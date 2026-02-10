"""Keyboard shortcuts reference dialog."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class ShortcutsDialog(QDialog):
    """Dialog showing all keyboard shortcuts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the shortcuts dialog."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Keyboard Shortcuts"))
        self.setMinimumSize(500, 600)
        self._setup_ui()

    def _localize_shortcut(self, shortcut: str) -> str:
        """Localize keyboard modifier names for display.

        Translates standard English key names to localized equivalents
        (e.g., Ctrl→Strg, Shift→Umschalt, Delete→Entf for German).
        """
        result = shortcut
        result = result.replace("Ctrl", self.tr("Ctrl"))
        result = result.replace("Shift", self.tr("Shift"))
        result = result.replace("Delete", self.tr("Delete"))
        result = result.replace("Escape", self.tr("Escape"))
        result = result.replace("Alt", self.tr("Alt"))
        return result

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Create scroll area for shortcuts
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # Container widget for all shortcut groups
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(16)

        # File operations
        file_group = self._create_shortcut_group(self.tr("File"), [
            (self._localize_shortcut("Ctrl+N"), self.tr("New Project")),
            (self._localize_shortcut("Ctrl+O"), self.tr("Open Project")),
            (self._localize_shortcut("Ctrl+S"), self.tr("Save")),
            (self._localize_shortcut("Ctrl+Shift+S"), self.tr("Save As")),
            (self._localize_shortcut("Alt+F4"), self.tr("Exit")),
        ])
        container_layout.addWidget(file_group)

        # Edit operations
        edit_group = self._create_shortcut_group(self.tr("Edit"), [
            (self._localize_shortcut("Ctrl+Z"), self.tr("Undo")),
            (self._localize_shortcut("Ctrl+Y"), self.tr("Redo")),
            (self._localize_shortcut("Ctrl+X"), self.tr("Cut")),
            (self._localize_shortcut("Ctrl+C"), self.tr("Copy")),
            (self._localize_shortcut("Ctrl+V"), self.tr("Paste")),
            (self._localize_shortcut("Ctrl+D"), self.tr("Duplicate")),
            (self._localize_shortcut("Delete"), self.tr("Delete selected")),
            (self._localize_shortcut("Ctrl+A"), self.tr("Select All")),
        ])
        container_layout.addWidget(edit_group)

        # View operations
        view_group = self._create_shortcut_group(self.tr("View"), [
            (self._localize_shortcut("Ctrl++"), self.tr("Zoom In")),
            (self._localize_shortcut("Ctrl+-"), self.tr("Zoom Out")),
            (self._localize_shortcut("Ctrl+0"), self.tr("Fit to Window")),
            ("G", self.tr("Toggle Grid")),
            ("S", self.tr("Toggle Snap to Grid")),
            ("F11", self.tr("Fullscreen Preview")),
            (self._localize_shortcut("Escape"), self.tr("Exit Fullscreen Preview")),
            (self.tr("Scroll Wheel"), self.tr("Zoom")),
            (self.tr("Middle Mouse Drag"), self.tr("Pan")),
        ])
        container_layout.addWidget(view_group)

        # Drawing tools
        tools_group = self._create_shortcut_group(self.tr("Drawing Tools"), [
            ("V", self.tr("Select Tool")),
            ("M", self.tr("Measure Tool")),
            ("R", self.tr("Rectangle")),
            ("P", self.tr("Polygon")),
            ("C", self.tr("Circle")),
        ])
        container_layout.addWidget(tools_group)

        # Property objects
        property_group = self._create_shortcut_group(self.tr("Property Objects"), [
            ("H", self.tr("House")),
            ("T", self.tr("Terrace/Patio")),
            ("D", self.tr("Driveway")),
            ("B", self.tr("Garden Bed")),
            ("F", self.tr("Fence")),
            ("W", self.tr("Wall")),
            ("L", self.tr("Path")),
        ])
        container_layout.addWidget(property_group)

        # Plant tools
        plant_group = self._create_shortcut_group(self.tr("Plant Tools"), [
            ("1", self.tr("Tree")),
            ("2", self.tr("Shrub")),
            ("3", self.tr("Perennial")),
            (self._localize_shortcut("Ctrl+K"), self.tr("Search Plant Database")),
        ])
        container_layout.addWidget(plant_group)

        # Object manipulation
        manipulation_group = self._create_shortcut_group(self.tr("Object Manipulation"), [
            (self.tr("Arrow Keys"), self.tr("Move selected (by grid size)")),
            (self.tr("Shift+Arrow Keys"), self.tr("Move selected (by 1cm)")),
            (self.tr("Double-click"), self.tr("Edit object label")),
        ])
        container_layout.addWidget(manipulation_group)

        container_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Close button
        close_btn = QPushButton(self.tr("Close"))
        close_btn.clicked.connect(self.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _create_shortcut_group(
        self, title: str, shortcuts: list[tuple[str, str]]
    ) -> QGroupBox:
        """Create a group box with shortcuts.

        Args:
            title: Group title
            shortcuts: List of (shortcut, description) tuples

        Returns:
            QGroupBox containing the shortcuts
        """
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        for shortcut, description in shortcuts:
            row = QHBoxLayout()

            # Shortcut label (styled as keyboard key - theme-aware)
            shortcut_label = QLabel(shortcut)
            shortcut_label.setStyleSheet(
                "QLabel {"
                "  background-color: palette(button);"
                "  color: palette(button-text);"
                "  border: 1px solid palette(mid);"
                "  border-radius: 3px;"
                "  padding: 2px 6px;"
                "  font-family: monospace;"
                "  font-weight: bold;"
                "}"
            )
            shortcut_label.setFixedWidth(140)
            shortcut_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Description label
            desc_label = QLabel(description)

            row.addWidget(shortcut_label)
            row.addWidget(desc_label)
            row.addStretch()

            layout.addLayout(row)

        return group
