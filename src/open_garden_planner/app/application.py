"""Main application window."""

import contextlib
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core import (
    ProjectManager,
    calculate_area_and_perimeter,
    format_area,
    format_length,
)
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.panels import (
    DrawingToolsPanel,
    LayersPanel,
    PlantDatabasePanel,
    PlantSearchPanel,
    PropertiesPanel,
)
from open_garden_planner.ui.widgets import CollapsiblePanel


class GardenPlannerApp(QMainWindow):
    """Main application window for Open Garden Planner.

    Provides the main window with menu bar, status bar, and central widget area.
    """

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()

        self.setMinimumSize(800, 600)

        # Project manager for save/load
        self._project_manager = ProjectManager(self)
        self._project_manager.project_changed.connect(self._update_window_title)
        self._project_manager.dirty_changed.connect(self._update_window_title)

        # Set up UI components
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_central_widget()

        # Initial window title
        self._update_window_title()

        # Show maximized and fit canvas after window is fully displayed
        self.showMaximized()
        QTimer.singleShot(100, self.canvas_view.fit_in_view)

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

        # Plants menu
        plants_menu = menubar.addMenu("&Plants")
        self._setup_plants_menu(plants_menu)

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

        # Import Background Image
        import_image_action = QAction("&Import Background Image...", self)
        import_image_action.setStatusTip("Import a background image (satellite photo, etc.)")
        import_image_action.triggered.connect(self._on_import_background_image)
        menu.addAction(import_image_action)

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
        self._undo_action = QAction("&Undo", self)
        self._undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self._undo_action.setStatusTip("Undo the last action")
        self._undo_action.setEnabled(False)  # Disabled until there's something to undo
        self._undo_action.triggered.connect(self._on_undo)
        menu.addAction(self._undo_action)

        # Redo
        self._redo_action = QAction("&Redo", self)
        self._redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        self._redo_action.setStatusTip("Redo the last undone action")
        self._redo_action.setEnabled(False)  # Disabled until there's something to redo
        self._redo_action.triggered.connect(self._on_redo)
        menu.addAction(self._redo_action)

        menu.addSeparator()

        # Cut
        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence("Ctrl+X"))
        cut_action.setStatusTip("Cut selected objects")
        cut_action.triggered.connect(self._on_cut)
        menu.addAction(cut_action)

        # Copy
        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence("Ctrl+C"))
        copy_action.setStatusTip("Copy selected objects")
        copy_action.triggered.connect(self._on_copy)
        menu.addAction(copy_action)

        # Paste
        paste_action = QAction("&Paste", self)
        paste_action.setShortcut(QKeySequence("Ctrl+V"))
        paste_action.setStatusTip("Paste objects from clipboard")
        paste_action.triggered.connect(self._on_paste)
        menu.addAction(paste_action)

        # Delete
        self._delete_action = QAction("&Delete", self)
        self._delete_action.setShortcut(QKeySequence("Delete"))
        self._delete_action.setStatusTip("Delete selected objects")
        menu.addAction(self._delete_action)

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
        zoom_in_action.triggered.connect(self._on_zoom_in)
        menu.addAction(zoom_in_action)

        # Zoom Out
        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.setStatusTip("Zoom out on the canvas")
        zoom_out_action.triggered.connect(self._on_zoom_out)
        menu.addAction(zoom_out_action)

        # Fit to Window
        fit_action = QAction("&Fit to Window", self)
        fit_action.setShortcut(QKeySequence("Ctrl+0"))
        fit_action.setStatusTip("Fit the entire canvas in the window")
        fit_action.triggered.connect(self._on_fit_to_window)
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

    def _setup_plants_menu(self, menu: QMenu) -> None:
        """Set up the Plants menu actions."""
        # Search Plant Database
        search_action = QAction("&Search Plant Database", self)
        search_action.setShortcut(QKeySequence("Ctrl+K"))
        search_action.setStatusTip("Search for plant species in online databases")
        search_action.triggered.connect(self._on_search_plant_database)
        menu.addAction(search_action)

        menu.addSeparator()

        # Manage Custom Plants
        manage_custom_action = QAction("&Manage Custom Plants...", self)
        manage_custom_action.setStatusTip("View, edit, and delete your custom plant species")
        manage_custom_action.triggered.connect(self._on_manage_custom_plants)
        menu.addAction(manage_custom_action)

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
        """Set up the central widget area with canvas and sidebar panels."""
        # Create canvas scene and view
        self.canvas_scene = CanvasScene(width_cm=5000, height_cm=3000)
        self.canvas_view = CanvasView(self.canvas_scene)

        # Create sidebar panels
        self._setup_sidebar()

        # Create splitter for canvas and sidebar
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.canvas_view)
        splitter.addWidget(self.sidebar)
        splitter.setStretchFactor(0, 1)  # Canvas takes most space
        splitter.setStretchFactor(1, 0)  # Sidebar fixed width
        splitter.setHandleWidth(1)  # Minimal splitter handle
        # Set initial sizes: give sidebar 450px, canvas gets the rest
        splitter.setSizes([1000, 450])

        # Connect canvas signals to status bar updates
        self.canvas_view.coordinates_changed.connect(self.update_coordinates)
        self.canvas_view.zoom_changed.connect(self.update_zoom)

        # Connect view menu actions to canvas
        self.grid_action.triggered.connect(self._on_toggle_grid)
        self.snap_action.triggered.connect(self._on_toggle_snap)

        # Connect tool panel to canvas view
        self.drawing_tools_panel.tool_selected.connect(self._on_tool_selected)
        self.canvas_view.tool_changed.connect(self.update_tool)

        # Connect scene selection changes to status bar and panels
        self.canvas_scene.selectionChanged.connect(self._on_selection_changed)
        self.canvas_scene.selectionChanged.connect(self._update_properties_panel)
        self.canvas_scene.selectionChanged.connect(self._update_plant_database_panel)

        # Connect delete action to canvas
        self._delete_action.triggered.connect(self.canvas_view._delete_selected_items)

        # Connect undo/redo action enable state to command manager
        cmd_mgr = self.canvas_view.command_manager
        cmd_mgr.can_undo_changed.connect(self._undo_action.setEnabled)
        cmd_mgr.can_redo_changed.connect(self._redo_action.setEnabled)

        # Mark project dirty when commands are executed
        cmd_mgr.command_executed.connect(lambda _: self._project_manager.mark_dirty())

        # Set splitter as central widget
        self.setCentralWidget(splitter)

        # Initial zoom display
        self.update_zoom(self.canvas_view.zoom_percent)

        # Initial tool display
        self.update_tool("Select")

        # Initial selection display
        self.update_selection(0, [])

    def _setup_sidebar(self) -> None:
        """Set up the right sidebar with collapsible panels."""
        # Create sidebar container
        self.sidebar = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(4)

        # 1. Drawing Tools Panel (collapsible)
        self.drawing_tools_panel = DrawingToolsPanel()
        tools_panel = CollapsiblePanel("Drawing Tools", self.drawing_tools_panel, expanded=True)
        sidebar_layout.addWidget(tools_panel)

        # 2. Properties Panel (collapsible)
        self.properties_panel = PropertiesPanel(
            command_manager=self.canvas_view.command_manager
        )
        # Connect object type change to update plant details panel
        self.properties_panel.object_type_changed.connect(self._update_plant_database_panel)
        props_panel = CollapsiblePanel("Properties", self.properties_panel, expanded=True)
        sidebar_layout.addWidget(props_panel)

        # 3. Layers Panel (collapsible)
        self.layers_panel = LayersPanel()
        self.layers_panel.set_layers(self.canvas_scene.layers)

        # Connect layers panel signals to scene
        self.layers_panel.active_layer_changed.connect(self._on_active_layer_changed)
        self.layers_panel.layer_visibility_changed.connect(self.canvas_scene.update_layer_visibility)
        self.layers_panel.layer_lock_changed.connect(self.canvas_scene.update_layer_lock)
        self.layers_panel.layer_opacity_changed.connect(self.canvas_scene.update_layer_opacity)
        self.layers_panel.layers_reordered.connect(self._on_layers_reordered)
        self.layers_panel.layer_renamed.connect(self._on_layer_renamed)

        # Connect scene layer changes to panel
        self.canvas_scene.layers_changed.connect(lambda: self.layers_panel.set_layers(self.canvas_scene.layers))

        layers_panel = CollapsiblePanel("Layers", self.layers_panel, expanded=True)
        sidebar_layout.addWidget(layers_panel)

        # 4. Plant Search Panel (collapsible) - for finding plants in the project
        self.plant_search_panel = PlantSearchPanel()
        self.plant_search_panel.set_canvas_scene(self.canvas_scene)

        # Connect scene changes to refresh plant list
        self.canvas_scene.changed.connect(self._on_scene_changed_for_plant_search)

        plant_search_collapsible = CollapsiblePanel("Find Plants", self.plant_search_panel, expanded=False)
        sidebar_layout.addWidget(plant_search_collapsible)

        # 5. Plant Details Panel (collapsible) - only shown when a plant is selected
        self.plant_database_panel = PlantDatabasePanel()
        self.plant_database_panel.search_button.clicked.connect(self._on_search_plant_database)
        self.plant_details_collapsible = CollapsiblePanel("Plant Details", self.plant_database_panel, expanded=True)
        self.plant_details_collapsible.setVisible(False)  # Hidden by default
        sidebar_layout.addWidget(self.plant_details_collapsible)

        # Add stretch at the bottom to push panels to top
        sidebar_layout.addStretch()

    def _update_properties_panel(self) -> None:
        """Update properties panel with current selection."""
        try:
            selected_items = self.canvas_scene.selectedItems()
            self.properties_panel.set_selected_items(selected_items)
        except RuntimeError:
            # Canvas scene has been deleted (happens during app shutdown)
            pass

    def _update_plant_database_panel(self) -> None:
        """Update plant database panel with current selection."""
        from open_garden_planner.core.object_types import ObjectType

        try:
            selected_items = self.canvas_scene.selectedItems()

            # Check if exactly one plant item is selected
            show_panel = False
            if len(selected_items) == 1:
                item = selected_items[0]
                if hasattr(item, "object_type") and item.object_type in (
                    ObjectType.TREE,
                    ObjectType.SHRUB,
                    ObjectType.PERENNIAL,
                ):
                    show_panel = True

            # Show/hide the plant details collapsible panel
            self.plant_details_collapsible.setVisible(show_panel)

            # Update panel content
            self.plant_database_panel.set_selected_items(selected_items)
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    # Slot methods for menu actions

    def _on_new_project(self) -> None:
        """Handle New Project action."""
        if not self._confirm_discard_changes():
            return

        from open_garden_planner.ui.dialogs import NewProjectDialog

        dialog = NewProjectDialog(self)
        # Pre-fill with current canvas dimensions
        dialog.set_dimensions_cm(
            self.canvas_scene.width_cm,
            self.canvas_scene.height_cm
        )

        if dialog.exec():
            # User clicked OK - create new project with specified dimensions
            width_cm = dialog.width_cm
            height_cm = dialog.height_cm

            # Clear existing objects from scene
            self.canvas_scene.clear()

            # Resize the canvas
            self.canvas_scene.resize_canvas(width_cm, height_cm)

            # Reset layers to default
            from open_garden_planner.models.layer import create_default_layers
            self.canvas_scene.set_layers(create_default_layers())
            self.layers_panel.set_layers(self.canvas_scene.layers)

            # Fit the new canvas in view
            self.canvas_view.fit_in_view()

            # Clear undo history and reset project state
            self.canvas_view.command_manager.clear()
            self._project_manager.new_project()

            # Update status bar
            width_m = width_cm / 100.0
            height_m = height_cm / 100.0
            status_bar = self.statusBar()
            if status_bar:
                status_bar.showMessage(
                    f"New project created: {width_m:.1f}m x {height_m:.1f}m"
                )

    def _on_open_project(self) -> None:
        """Handle Open Project action."""
        if not self._confirm_discard_changes():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "Open Garden Planner (*.ogp);;All Files (*)",
        )
        if file_path:
            try:
                self._project_manager.load(self.canvas_scene, Path(file_path))
                self.canvas_view.command_manager.clear()
                self.canvas_view.fit_in_view()
                self.statusBar().showMessage(f"Opened: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

    def _on_save(self) -> None:
        """Handle Save action."""
        if self._project_manager.current_file:
            self._save_to_file(self._project_manager.current_file)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        """Handle Save As action."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            self._project_manager.project_name + ".ogp",
            "Open Garden Planner (*.ogp);;All Files (*)",
        )
        if file_path:
            self._save_to_file(Path(file_path))

    def _save_to_file(self, file_path: Path) -> None:
        """Save the project to a specific file."""
        try:
            self._project_manager.save(self.canvas_scene, file_path)
            self.statusBar().showMessage(f"Saved: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")

    def _confirm_discard_changes(self) -> bool:
        """Ask user to save if there are unsaved changes.

        Returns:
            True if it's OK to proceed (saved or discarded), False to cancel.
        """
        if not self._project_manager.is_dirty:
            return True

        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Do you want to save changes before proceeding?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

        if result == QMessageBox.StandardButton.Save:
            self._on_save()
            return not self._project_manager.is_dirty  # True if save succeeded
        return result == QMessageBox.StandardButton.Discard

    def _update_window_title(self, _: object = None) -> None:
        """Update the window title with project name and dirty indicator."""
        name = self._project_manager.project_name
        dirty = "*" if self._project_manager.is_dirty else ""
        self.setWindowTitle(f"{name}{dirty} - Open Garden Planner")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close - prompt to save if dirty."""
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()

    def _on_undo(self) -> None:
        """Handle Undo action."""
        cmd_mgr = self.canvas_view.command_manager
        if cmd_mgr.can_undo:
            desc = cmd_mgr.undo_description
            cmd_mgr.undo()
            self.statusBar().showMessage(f"Undo: {desc}")
        else:
            self.statusBar().showMessage("Nothing to undo")

    def _on_redo(self) -> None:
        """Handle Redo action."""
        cmd_mgr = self.canvas_view.command_manager
        if cmd_mgr.can_redo:
            desc = cmd_mgr.redo_description
            cmd_mgr.redo()
            self.statusBar().showMessage(f"Redo: {desc}")
        else:
            self.statusBar().showMessage("Nothing to redo")

    def _on_copy(self) -> None:
        """Handle Copy action."""
        self.canvas_view.copy_selected()

    def _on_cut(self) -> None:
        """Handle Cut action."""
        self.canvas_view.cut_selected()

    def _on_paste(self) -> None:
        """Handle Paste action."""
        self.canvas_view.paste()

    def _on_toggle_grid(self, checked: bool) -> None:
        """Handle toggle grid action."""
        self.canvas_view.set_grid_visible(checked)

    def _on_toggle_snap(self, checked: bool) -> None:
        """Handle toggle snap action."""
        self.canvas_view.set_snap_enabled(checked)

    def _on_zoom_in(self) -> None:
        """Handle zoom in action."""
        self.canvas_view.zoom_in()

    def _on_zoom_out(self) -> None:
        """Handle zoom out action."""
        self.canvas_view.zoom_out()

    def _on_fit_to_window(self) -> None:
        """Handle fit to window action."""
        self.canvas_view.fit_in_view()

    def _on_tool_selected(self, tool_type: ToolType) -> None:
        """Handle tool selection from toolbar.

        Args:
            tool_type: The selected tool type
        """
        self.canvas_view.set_active_tool(tool_type)

    def _on_active_layer_changed(self, layer_id) -> None:
        """Handle active layer change from layers panel.

        Args:
            layer_id: UUID of the newly active layer
        """
        try:
            layer = self.canvas_scene.get_layer_by_id(layer_id)
            if layer:
                self.canvas_scene.set_active_layer(layer)
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_layers_reordered(self, new_order) -> None:
        """Handle layer reordering from layers panel.

        Args:
            new_order: New list of layers in order
        """
        try:
            self.canvas_scene.reorder_layers(new_order)
            self._project_manager.mark_dirty()
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_layer_renamed(self, _layer_id, _new_name) -> None:
        """Handle layer rename from layers panel.

        Args:
            _layer_id: UUID of the renamed layer (unused)
            _new_name: New layer name (unused)
        """
        self._project_manager.mark_dirty()

    def _on_scene_changed_for_plant_search(self) -> None:
        """Handle scene changes to refresh plant search panel."""
        with contextlib.suppress(RuntimeError):
            self.plant_search_panel.refresh_plant_list()

    def _on_selection_changed(self) -> None:
        """Handle selection changes in the canvas scene."""
        # Guard against accessing deleted scene (can happen during shutdown or dialog execution)
        try:
            selected_items = self.canvas_scene.selectedItems()
            count = len(selected_items)
            self.update_selection(count, selected_items)
        except RuntimeError:
            # Scene has been deleted, ignore
            pass

    def _on_manage_custom_plants(self) -> None:
        """Handle Manage Custom Plants action."""
        from open_garden_planner.ui.dialogs import CustomPlantsDialog

        dialog = CustomPlantsDialog(self)
        dialog.exec()

    def _on_search_plant_database(self) -> None:
        """Handle Search Plant Database action."""
        from open_garden_planner.services import PlantAPIManager
        from open_garden_planner.ui.dialogs import PlantSearchDialog

        # Initialize API manager (will use .env credentials)
        api_manager = PlantAPIManager()

        dialog = PlantSearchDialog(api_manager, self)
        if dialog.exec():
            # User selected a plant species
            plant_data = dialog.selected_plant
            if plant_data:
                # Check if there's a selected plant item to update
                selected_items = self.canvas_scene.selectedItems()
                from open_garden_planner.core.object_types import ObjectType

                # Find a plant item in selection
                plant_item = None
                for item in selected_items:
                    if hasattr(item, 'object_type') and item.object_type in (
                        ObjectType.TREE,
                        ObjectType.SHRUB,
                        ObjectType.PERENNIAL,
                    ):
                        plant_item = item
                        break

                if plant_item:
                    # Update existing plant with species data
                    if not hasattr(plant_item, 'metadata') or plant_item.metadata is None:
                        plant_item.metadata = {}
                    plant_item.metadata['plant_species'] = plant_data.to_dict()

                    # Update the panel display
                    self._update_plant_database_panel()

                    # Mark project as dirty
                    self._project_manager.mark_dirty()

                    self.statusBar().showMessage(
                        f"Updated plant with species: {plant_data.common_name}", 3000
                    )
                else:
                    # No plant selected - show message
                    self.statusBar().showMessage(
                        "Select a plant object (tree, shrub, or perennial) to assign species data",
                        5000,
                    )

    def _on_about(self) -> None:
        """Handle About action."""
        from pathlib import Path

        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout

        # Create custom about dialog to show logo
        dialog = QDialog(self)
        dialog.setWindowTitle("About Open Garden Planner")
        dialog.setFixedSize(450, 280)

        layout = QHBoxLayout(dialog)

        # Logo on the left
        icon_path = Path(__file__).parent.parent / "resources" / "icons" / "OGP_logo.png"
        if icon_path.exists():
            logo_label = QLabel()
            pixmap = QPixmap(str(icon_path))
            scaled_pixmap = pixmap.scaled(
                128, 128, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            layout.addWidget(logo_label)

        # Text on the right
        text_layout = QVBoxLayout()
        text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_label = QLabel("<h2>Open Garden Planner</h2>")
        text_layout.addWidget(title_label)

        version_label = QLabel("<p>Version 0.1.0</p>")
        text_layout.addWidget(version_label)

        description_label = QLabel(
            "<p>Precision garden planning for passionate gardeners.</p>"
            "<p>Free and open source under GPLv3.</p>"
        )
        description_label.setWordWrap(True)
        text_layout.addWidget(description_label)

        link_label = QLabel(
            "<p><a href='https://github.com/cofade/open-garden-planner'>"
            "github.com/cofade/open-garden-planner</a></p>"
        )
        link_label.setOpenExternalLinks(True)
        text_layout.addWidget(link_label)

        text_layout.addStretch()
        layout.addLayout(text_layout)

        dialog.exec()

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

    def update_selection(self, count: int, selected_items: list | None = None) -> None:
        """Update the selection info in the status bar.

        Args:
            count: Number of selected objects
            selected_items: List of selected QGraphicsItems (optional)
        """
        if count == 0:
            self.selection_label.setText("No selection")
        elif count == 1:
            # For single selection, show area and perimeter if available
            if selected_items:
                item = selected_items[0]
                measurements = calculate_area_and_perimeter(item)
                if measurements:
                    area, perimeter = measurements
                    area_str = format_area(area)
                    length_str = format_length(perimeter)
                    self.selection_label.setText(
                        f"1 object | Area: {area_str} | Perimeter: {length_str}"
                    )
                else:
                    self.selection_label.setText("1 object selected")
            else:
                self.selection_label.setText("1 object selected")
        else:
            # For multiple selection, show total area and perimeter
            if selected_items:
                total_area = 0.0
                total_perimeter = 0.0
                measurable_count = 0

                for item in selected_items:
                    measurements = calculate_area_and_perimeter(item)
                    if measurements:
                        area, perimeter = measurements
                        total_area += area
                        total_perimeter += perimeter
                        measurable_count += 1

                if measurable_count > 0:
                    area_str = format_area(total_area)
                    length_str = format_length(total_perimeter)
                    self.selection_label.setText(
                        f"{count} objects | Total Area: {area_str} | Total Perimeter: {length_str}"
                    )
                else:
                    self.selection_label.setText(f"{count} objects selected")
            else:
                self.selection_label.setText(f"{count} objects selected")

    def update_tool(self, tool_name: str) -> None:
        """Update the current tool display in the status bar.

        Args:
            tool_name: Name of the active tool
        """
        self.tool_label.setText(tool_name)

    def _on_import_background_image(self) -> None:
        """Handle Import Background Image action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Background Image",
            "",
            "Images (*.png *.jpg *.jpeg *.tiff *.bmp);;All Files (*)",
        )
        if file_path:
            try:
                from open_garden_planner.ui.canvas.items import BackgroundImageItem

                image_item = BackgroundImageItem(file_path)
                self.canvas_scene.addItem(image_item)

                # Center the image on the canvas
                canvas_center = self.canvas_scene.canvas_rect.center()
                image_rect = image_item.boundingRect()
                image_item.setPos(
                    canvas_center.x() - image_rect.width() / 2,
                    canvas_center.y() - image_rect.height() / 2,
                )

                self._project_manager.mark_dirty()
                self.statusBar().showMessage(f"Imported: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import image:\n{e}")
