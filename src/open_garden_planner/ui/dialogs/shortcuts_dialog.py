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
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(500, 600)
        self._setup_ui()

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
        file_group = self._create_shortcut_group("File", [
            ("Ctrl+N", "New Project"),
            ("Ctrl+O", "Open Project"),
            ("Ctrl+S", "Save"),
            ("Ctrl+Shift+S", "Save As"),
            ("Alt+F4", "Exit"),
        ])
        container_layout.addWidget(file_group)

        # Edit operations
        edit_group = self._create_shortcut_group("Edit", [
            ("Ctrl+Z", "Undo"),
            ("Ctrl+Y", "Redo"),
            ("Ctrl+X", "Cut"),
            ("Ctrl+C", "Copy"),
            ("Ctrl+V", "Paste"),
            ("Ctrl+D", "Duplicate"),
            ("Delete", "Delete selected"),
            ("Ctrl+A", "Select All"),
        ])
        container_layout.addWidget(edit_group)

        # View operations
        view_group = self._create_shortcut_group("View", [
            ("Ctrl++", "Zoom In"),
            ("Ctrl+-", "Zoom Out"),
            ("Ctrl+0", "Fit to Window"),
            ("G", "Toggle Grid"),
            ("S", "Toggle Snap to Grid"),
            ("Scroll Wheel", "Zoom"),
            ("Middle Mouse Drag", "Pan"),
        ])
        container_layout.addWidget(view_group)

        # Drawing tools
        tools_group = self._create_shortcut_group("Drawing Tools", [
            ("V", "Select Tool"),
            ("M", "Measure Tool"),
            ("R", "Rectangle"),
            ("P", "Polygon"),
            ("C", "Circle"),
        ])
        container_layout.addWidget(tools_group)

        # Property objects
        property_group = self._create_shortcut_group("Property Objects", [
            ("H", "House"),
            ("T", "Terrace/Patio"),
            ("D", "Driveway"),
            ("B", "Garden Bed"),
            ("F", "Fence"),
            ("W", "Wall"),
            ("L", "Path"),
        ])
        container_layout.addWidget(property_group)

        # Plant tools
        plant_group = self._create_shortcut_group("Plant Tools", [
            ("1", "Tree"),
            ("2", "Shrub"),
            ("3", "Perennial"),
            ("Ctrl+K", "Search Plant Database"),
        ])
        container_layout.addWidget(plant_group)

        # Object manipulation
        manipulation_group = self._create_shortcut_group("Object Manipulation", [
            ("Arrow Keys", "Move selected (by grid size)"),
            ("Shift+Arrow Keys", "Move selected (by 1cm)"),
            ("Double-click", "Edit object label"),
        ])
        container_layout.addWidget(manipulation_group)

        container_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Close button
        close_btn = QPushButton("Close")
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

            # Shortcut label (styled as keyboard key - dark theme)
            shortcut_label = QLabel(shortcut)
            shortcut_label.setStyleSheet(
                "QLabel {"
                "  background-color: #3c3c3c;"
                "  color: #e0e0e0;"
                "  border: 1px solid #555555;"
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
