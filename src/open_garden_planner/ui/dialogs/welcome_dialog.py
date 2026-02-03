"""Welcome dialog shown at application startup."""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.app.settings import get_settings


class WelcomeDialog(QDialog):
    """Welcome screen shown at application startup.

    Displays the application logo, recent projects list, and quick actions
    for creating a new project or opening an existing one.

    Signals:
        new_project_requested: Emitted when user clicks "New Project"
        open_project_requested: Emitted when user clicks "Open Project"
        recent_project_selected: Emitted with file path when user selects a recent project
    """

    new_project_requested = pyqtSignal()
    open_project_requested = pyqtSignal()
    recent_project_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the Welcome dialog."""
        super().__init__(parent)

        self.setWindowTitle("Welcome to Open Garden Planner")
        self.setModal(True)
        self.setMinimumSize(600, 500)
        self.setMaximumSize(800, 700)

        self._selected_file: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # Banner/Logo at top
        self._setup_banner(layout)

        # Main content area with recent projects and actions
        content_layout = QHBoxLayout()
        content_layout.setSpacing(30)

        # Left side: Recent Projects
        self._setup_recent_projects(content_layout)

        # Right side: Actions
        self._setup_actions(content_layout)

        layout.addLayout(content_layout, stretch=1)

        # Bottom: Don't show again checkbox
        self._setup_footer(layout)

    def _setup_banner(self, layout: QVBoxLayout) -> None:
        """Set up the banner image at the top."""
        banner_label = QLabel()
        banner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Load banner image
        resources_dir = Path(__file__).parent.parent.parent / "resources" / "icons"
        banner_path = resources_dir / "banner.png"

        if banner_path.exists():
            pixmap = QPixmap(str(banner_path))
            # Scale to fit dialog width while maintaining aspect ratio
            scaled = pixmap.scaledToWidth(
                540, Qt.TransformationMode.SmoothTransformation
            )
            banner_label.setPixmap(scaled)
        else:
            # Fallback if banner not found
            banner_label.setText("Open Garden Planner")
            font = QFont()
            font.setPointSize(24)
            font.setBold(True)
            banner_label.setFont(font)

        layout.addWidget(banner_label)

    def _setup_recent_projects(self, layout: QHBoxLayout) -> None:
        """Set up the recent projects list."""
        recent_widget = QWidget()
        recent_layout = QVBoxLayout(recent_widget)
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.setSpacing(10)

        # Header
        header = QLabel("Recent Projects")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header.setFont(header_font)
        recent_layout.addWidget(header)

        # List widget for recent files - use native styling
        self._recent_list = QListWidget()
        self._recent_list.setAlternatingRowColors(True)
        self._recent_list.itemDoubleClicked.connect(self._on_recent_double_clicked)
        self._recent_list.itemSelectionChanged.connect(self._on_selection_changed)

        # Populate recent files
        self._populate_recent_files()

        recent_layout.addWidget(self._recent_list, stretch=1)

        # Clear recent button - use native styling
        clear_btn = QPushButton("Clear Recent")
        clear_btn.clicked.connect(self._on_clear_recent)
        recent_layout.addWidget(clear_btn)

        layout.addWidget(recent_widget, stretch=2)

    def _setup_actions(self, layout: QHBoxLayout) -> None:
        """Set up the action buttons."""
        actions_widget = QWidget()
        actions_layout = QVBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(15)

        # Header
        header = QLabel("Get Started")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header.setFont(header_font)
        actions_layout.addWidget(header)

        # Primary button style (green background - works in both themes)
        primary_button_style = """
            QPushButton {
                padding: 15px 20px;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:hover {
                background-color: #43A047;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
        """

        # Secondary button style (green border - works in both themes)
        secondary_button_style = """
            QPushButton {
                padding: 15px 20px;
                font-size: 14px;
                border: 2px solid #4CAF50;
                border-radius: 6px;
                color: #4CAF50;
            }
            QPushButton:hover {
                background-color: rgba(76, 175, 80, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(76, 175, 80, 0.2);
            }
            QPushButton:disabled {
                border-color: palette(mid);
                color: palette(mid);
            }
        """

        # New Project button (primary)
        new_project_btn = QPushButton("New Project")
        new_project_btn.setStyleSheet(primary_button_style)
        new_project_btn.clicked.connect(self._on_new_project)
        actions_layout.addWidget(new_project_btn)

        # Open Project button
        open_project_btn = QPushButton("Open Project...")
        open_project_btn.setStyleSheet(secondary_button_style)
        open_project_btn.clicked.connect(self._on_open_project)
        actions_layout.addWidget(open_project_btn)

        # Open Selected button (for recent projects)
        self._open_selected_btn = QPushButton("Open Selected")
        self._open_selected_btn.setStyleSheet(secondary_button_style)
        self._open_selected_btn.setEnabled(False)
        self._open_selected_btn.clicked.connect(self._on_open_selected)
        actions_layout.addWidget(self._open_selected_btn)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        actions_layout.addWidget(separator)

        # Tips section - use default text color
        tips_label = QLabel(
            "<b>Tip:</b> Double-click a recent project to open it directly."
        )
        tips_label.setWordWrap(True)
        actions_layout.addWidget(tips_label)

        actions_layout.addStretch()

        layout.addWidget(actions_widget, stretch=1)

    def _setup_footer(self, layout: QVBoxLayout) -> None:
        """Set up the footer with the checkbox."""
        footer_layout = QHBoxLayout()

        self._show_on_startup_checkbox = QCheckBox("Show this screen on startup")
        self._show_on_startup_checkbox.setChecked(get_settings().show_welcome_on_startup)
        self._show_on_startup_checkbox.stateChanged.connect(self._on_checkbox_changed)

        footer_layout.addWidget(self._show_on_startup_checkbox)
        footer_layout.addStretch()

        # Close button - use native styling
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        footer_layout.addWidget(close_btn)

        layout.addLayout(footer_layout)

    def _populate_recent_files(self) -> None:
        """Populate the recent files list."""
        self._recent_list.clear()
        recent_files = get_settings().recent_files

        if not recent_files:
            # Show placeholder
            placeholder = QListWidgetItem("No recent projects")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(Qt.GlobalColor.gray)
            self._recent_list.addItem(placeholder)
            return

        for file_path in recent_files:
            path = Path(file_path)
            if path.exists():
                item = QListWidgetItem()
                item.setText(path.stem)
                item.setToolTip(str(path))
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self._recent_list.addItem(item)
            else:
                # Show missing files with indicator
                item = QListWidgetItem()
                item.setText(f"{path.stem} (not found)")
                item.setToolTip(f"File not found: {path}")
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                item.setForeground(Qt.GlobalColor.gray)
                self._recent_list.addItem(item)

    def _on_selection_changed(self) -> None:
        """Handle selection change in recent list."""
        selected_items = self._recent_list.selectedItems()
        if selected_items:
            item = selected_items[0]
            file_path = item.data(Qt.ItemDataRole.UserRole)
            if file_path and Path(file_path).exists():
                self._selected_file = file_path
                self._open_selected_btn.setEnabled(True)
            else:
                self._selected_file = None
                self._open_selected_btn.setEnabled(False)
        else:
            self._selected_file = None
            self._open_selected_btn.setEnabled(False)

    def _on_recent_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on a recent project."""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if file_path and Path(file_path).exists():
            self.recent_project_selected.emit(file_path)
            self.accept()

    def _on_new_project(self) -> None:
        """Handle New Project button click."""
        self.new_project_requested.emit()
        self.accept()

    def _on_open_project(self) -> None:
        """Handle Open Project button click."""
        self.open_project_requested.emit()
        self.accept()

    def _on_open_selected(self) -> None:
        """Handle Open Selected button click."""
        if self._selected_file:
            self.recent_project_selected.emit(self._selected_file)
            self.accept()

    def _on_clear_recent(self) -> None:
        """Handle Clear Recent button click."""
        get_settings().clear_recent_files()
        self._populate_recent_files()
        self._open_selected_btn.setEnabled(False)
        self._selected_file = None

    def _on_checkbox_changed(self, state: int) -> None:
        """Handle checkbox state change."""
        get_settings().show_welcome_on_startup = state == Qt.CheckState.Checked.value

    @property
    def selected_file(self) -> str | None:
        """Get the selected file path, if any."""
        return self._selected_file
