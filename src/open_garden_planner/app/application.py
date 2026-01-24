"""Main application window."""

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMenu,
    QWidget,
)


class GardenPlannerApp(QMainWindow):
    """Main application window for Open Garden Planner.

    Provides the main window with menu bar, status bar, and central widget area.
    """

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()

        self.setWindowTitle("Open Garden Planner")
        self.setMinimumSize(800, 600)
        self.resize(1200, 800)

        # Set up UI components
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_central_widget()

    def _setup_menu_bar(self) -> None:
        """Set up the menu bar with File, Edit, View, Help menus."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        self._setup_file_menu(file_menu)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        self._setup_edit_menu(edit_menu)

        # View menu
        view_menu = menubar.addMenu("&View")
        self._setup_view_menu(view_menu)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        self._setup_help_menu(help_menu)

    def _setup_file_menu(self, menu: QMenu) -> None:
        """Set up the File menu actions."""
        # New Project
        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.setStatusTip("Create a new garden project")
        new_action.triggered.connect(self._on_new_project)
        menu.addAction(new_action)

        # Open Project
        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.setStatusTip("Open an existing project")
        open_action.triggered.connect(self._on_open_project)
        menu.addAction(open_action)

        menu.addSeparator()

        # Save
        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.setStatusTip("Save the current project")
        save_action.triggered.connect(self._on_save)
        menu.addAction(save_action)

        # Save As
        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.setStatusTip("Save the project with a new name")
        save_as_action.triggered.connect(self._on_save_as)
        menu.addAction(save_as_action)

        menu.addSeparator()

        # Export submenu
        export_menu = menu.addMenu("&Export")

        export_png = QAction("Export as &PNG...", self)
        export_png.setStatusTip("Export the plan as a PNG image")
        export_menu.addAction(export_png)

        export_svg = QAction("Export as &SVG...", self)
        export_svg.setStatusTip("Export the plan as an SVG vector file")
        export_menu.addAction(export_svg)

        menu.addSeparator()

        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)

    def _setup_edit_menu(self, menu: QMenu) -> None:
        """Set up the Edit menu actions."""
        # Undo
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.setStatusTip("Undo the last action")
        undo_action.triggered.connect(self._on_undo)
        menu.addAction(undo_action)

        # Redo
        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        redo_action.setStatusTip("Redo the last undone action")
        redo_action.triggered.connect(self._on_redo)
        menu.addAction(redo_action)

        menu.addSeparator()

        # Cut
        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence("Ctrl+X"))
        cut_action.setStatusTip("Cut selected objects")
        menu.addAction(cut_action)

        # Copy
        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence("Ctrl+C"))
        copy_action.setStatusTip("Copy selected objects")
        menu.addAction(copy_action)

        # Paste
        paste_action = QAction("&Paste", self)
        paste_action.setShortcut(QKeySequence("Ctrl+V"))
        paste_action.setStatusTip("Paste objects from clipboard")
        menu.addAction(paste_action)

        # Delete
        delete_action = QAction("&Delete", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.setStatusTip("Delete selected objects")
        menu.addAction(delete_action)

        menu.addSeparator()

        # Select All
        select_all_action = QAction("Select &All", self)
        select_all_action.setShortcut(QKeySequence("Ctrl+A"))
        select_all_action.setStatusTip("Select all objects")
        menu.addAction(select_all_action)

    def _setup_view_menu(self, menu: QMenu) -> None:
        """Set up the View menu actions."""
        # Zoom In
        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl++"))
        zoom_in_action.setStatusTip("Zoom in on the canvas")
        menu.addAction(zoom_in_action)

        # Zoom Out
        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.setStatusTip("Zoom out on the canvas")
        menu.addAction(zoom_out_action)

        # Fit to Window
        fit_action = QAction("&Fit to Window", self)
        fit_action.setShortcut(QKeySequence("Ctrl+0"))
        fit_action.setStatusTip("Fit the entire canvas in the window")
        menu.addAction(fit_action)

        menu.addSeparator()

        # Toggle Grid
        self.grid_action = QAction("Show &Grid", self)
        self.grid_action.setShortcut(QKeySequence("G"))
        self.grid_action.setCheckable(True)
        self.grid_action.setChecked(False)
        self.grid_action.setStatusTip("Toggle grid visibility")
        menu.addAction(self.grid_action)

        # Toggle Snap
        self.snap_action = QAction("&Snap to Grid", self)
        self.snap_action.setShortcut(QKeySequence("S"))
        self.snap_action.setCheckable(True)
        self.snap_action.setChecked(True)
        self.snap_action.setStatusTip("Toggle snap to grid")
        menu.addAction(self.snap_action)

    def _setup_help_menu(self, menu: QMenu) -> None:
        """Set up the Help menu actions."""
        # About
        about_action = QAction("&About Open Garden Planner", self)
        about_action.setStatusTip("About this application")
        about_action.triggered.connect(self._on_about)
        menu.addAction(about_action)

        # About Qt
        about_qt_action = QAction("About &Qt", self)
        about_qt_action.triggered.connect(QApplication.aboutQt)
        menu.addAction(about_qt_action)

    def _setup_status_bar(self) -> None:
        """Set up the status bar with coordinate and zoom display."""
        status_bar = self.statusBar()

        # Coordinate label (left side, permanent)
        self.coord_label = QLabel("X: 0.00 cm  Y: 0.00 cm")
        self.coord_label.setMinimumWidth(200)
        status_bar.addPermanentWidget(self.coord_label)

        # Zoom label
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(60)
        status_bar.addPermanentWidget(self.zoom_label)

        # Selection info label
        self.selection_label = QLabel("No selection")
        self.selection_label.setMinimumWidth(150)
        status_bar.addPermanentWidget(self.selection_label)

        # Tool label
        self.tool_label = QLabel("Select")
        self.tool_label.setMinimumWidth(80)
        status_bar.addPermanentWidget(self.tool_label)

        # Show ready message
        status_bar.showMessage("Ready")

    def _setup_central_widget(self) -> None:
        """Set up the central widget area (placeholder for now)."""
        # Placeholder - will be replaced with splitter containing canvas and panels
        central = QWidget()
        self.setCentralWidget(central)

    # Slot methods for menu actions

    def _on_new_project(self) -> None:
        """Handle New Project action."""
        self.statusBar().showMessage("New Project... (not implemented yet)")

    def _on_open_project(self) -> None:
        """Handle Open Project action."""
        self.statusBar().showMessage("Open Project... (not implemented yet)")

    def _on_save(self) -> None:
        """Handle Save action."""
        self.statusBar().showMessage("Save... (not implemented yet)")

    def _on_save_as(self) -> None:
        """Handle Save As action."""
        self.statusBar().showMessage("Save As... (not implemented yet)")

    def _on_undo(self) -> None:
        """Handle Undo action."""
        self.statusBar().showMessage("Undo (not implemented yet)")

    def _on_redo(self) -> None:
        """Handle Redo action."""
        self.statusBar().showMessage("Redo (not implemented yet)")

    def _on_about(self) -> None:
        """Handle About action."""
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "About Open Garden Planner",
            "<h3>Open Garden Planner</h3>"
            "<p>Version 0.1.0</p>"
            "<p>Precision garden planning for passionate gardeners.</p>"
            "<p>Free and open source under GPLv3.</p>"
            "<p><a href='https://github.com/cofade/open-garden-planner'>"
            "github.com/cofade/open-garden-planner</a></p>",
        )

    # Public methods for updating status bar

    def update_coordinates(self, x: float, y: float) -> None:
        """Update the coordinate display in the status bar.

        Args:
            x: X coordinate in centimeters
            y: Y coordinate in centimeters
        """
        self.coord_label.setText(f"X: {x:.2f} cm  Y: {y:.2f} cm")

    def update_zoom(self, zoom_percent: float) -> None:
        """Update the zoom display in the status bar.

        Args:
            zoom_percent: Zoom level as percentage (100 = 100%)
        """
        self.zoom_label.setText(f"{zoom_percent:.0f}%")

    def update_selection(self, count: int) -> None:
        """Update the selection info in the status bar.

        Args:
            count: Number of selected objects
        """
        if count == 0:
            self.selection_label.setText("No selection")
        elif count == 1:
            self.selection_label.setText("1 object selected")
        else:
            self.selection_label.setText(f"{count} objects selected")

    def update_tool(self, tool_name: str) -> None:
        """Update the current tool display in the status bar.

        Args:
            tool_name: Name of the active tool
        """
        self.tool_label.setText(tool_name)
