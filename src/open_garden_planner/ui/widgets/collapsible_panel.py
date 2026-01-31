"""Collapsible panel widget for sidebar organization."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class CollapsiblePanel(QWidget):
    """A collapsible panel with a header and content area.

    The panel can be collapsed/expanded by clicking the header.
    """

    expanded_changed = pyqtSignal(bool)

    def __init__(
        self,
        title: str,
        content: QWidget | None = None,
        parent: QWidget | None = None,
        expanded: bool = True,
    ) -> None:
        """Initialize the collapsible panel.

        Args:
            title: Panel title displayed in header
            content: Widget to display in the content area
            parent: Parent widget
            expanded: Initial expanded state
        """
        super().__init__(parent)
        self._title = title
        self._expanded = expanded
        self._content_widget = content

        self._setup_ui()
        self.set_expanded(expanded, emit=False)

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header frame with background
        self._header = QFrame()
        self._header.setFrameShape(QFrame.Shape.StyledPanel)
        self._header.setStyleSheet("""
            QFrame {
                background-color: palette(button);
                border: 1px solid palette(mid);
                border-radius: 3px;
            }
            QFrame:hover {
                background-color: palette(light);
            }
        """)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.mousePressEvent = lambda _: self.toggle()

        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(6, 4, 6, 4)

        # Expand/collapse indicator
        self._indicator = QLabel()
        self._indicator.setFixedWidth(16)
        header_layout.addWidget(self._indicator)

        # Title label
        title_label = QLabel(self._title)
        title_label.setStyleSheet("font-weight: bold; border: none;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        layout.addWidget(self._header)

        # Content area
        if self._content_widget:
            layout.addWidget(self._content_widget)

    def set_content(self, widget: QWidget) -> None:
        """Set the content widget.

        Args:
            widget: Widget to display in content area
        """
        if self._content_widget:
            self._content_widget.setParent(None)

        self._content_widget = widget
        if widget:
            self.layout().addWidget(widget)
            widget.setVisible(self._expanded)

    def is_expanded(self) -> bool:
        """Check if panel is expanded.

        Returns:
            True if expanded, False if collapsed
        """
        return self._expanded

    def set_expanded(self, expanded: bool, emit: bool = True) -> None:
        """Set the expanded state.

        Args:
            expanded: True to expand, False to collapse
            emit: Whether to emit the expanded_changed signal
        """
        self._expanded = expanded

        # Update indicator
        self._indicator.setText("▼" if expanded else "▶")

        # Show/hide content
        if self._content_widget:
            self._content_widget.setVisible(expanded)

        if emit:
            self.expanded_changed.emit(expanded)

    def toggle(self) -> None:
        """Toggle the expanded state."""
        self.set_expanded(not self._expanded)

    def expand(self) -> None:
        """Expand the panel."""
        self.set_expanded(True)

    def collapse(self) -> None:
        """Collapse the panel."""
        self.set_expanded(False)
