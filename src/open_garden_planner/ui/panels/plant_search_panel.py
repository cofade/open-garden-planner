"""Plant search panel for finding and filtering plants in the project."""

from uuid import UUID

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGraphicsItem,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import PlantSpeciesData


class PlantListItem(QWidget):
    """Custom widget for a plant list item."""

    def __init__(
        self,
        item_id: UUID,
        name: str,
        species: str,
        plant_type: ObjectType,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the plant list item.

        Args:
            item_id: The UUID of the graphics item
            name: Display name of the plant
            species: Scientific name of the plant
            plant_type: The plant type (TREE, SHRUB, PERENNIAL)
            parent: Parent widget
        """
        super().__init__(parent)
        self.item_id = item_id
        self._setup_ui(name, species, plant_type)

    def _setup_ui(self, name: str, species: str, plant_type: ObjectType) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Top row: type icon and name
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        # Type icon/label
        type_icons = {
            ObjectType.TREE: "🌳",
            ObjectType.SHRUB: "🌿",
            ObjectType.PERENNIAL: "🌸",
        }
        type_label = QLabel(type_icons.get(plant_type, "🌱"))
        type_label.setFixedWidth(20)
        top_row.addWidget(type_label)

        # Plant name
        name_label = QLabel(name or "Unnamed")
        name_label.setStyleSheet("font-weight: bold;")
        top_row.addWidget(name_label, 1)

        layout.addLayout(top_row)

        # Bottom row: scientific name
        if species:
            species_label = QLabel(species)
            species_label.setProperty("secondary", True)
            species_label.setStyleSheet("font-style: italic; padding-left: 24px;")
            layout.addWidget(species_label)


class PlantSearchPanel(QWidget):
    """Panel for searching and filtering plants in the current project.

    Allows users to:
    - Search plants by common name, scientific name, or family
    - Filter by plant type (Tree, Shrub, Perennial)
    - Click on a plant to select and pan to it on the canvas
    """

    plant_selected = pyqtSignal(UUID)  # Emitted when a plant is clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the plant search panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._all_plants: list[tuple[UUID, str, str, ObjectType, QGraphicsItem]] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Search input
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Search plants..."))
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)

        layout.addLayout(search_layout)

        # Filter checkboxes
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        self.tree_checkbox = QCheckBox(self.tr("🌳 Trees"))
        self.tree_checkbox.setChecked(True)
        self.tree_checkbox.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.tree_checkbox)

        self.shrub_checkbox = QCheckBox(self.tr("🌿 Shrubs"))
        self.shrub_checkbox.setChecked(True)
        self.shrub_checkbox.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.shrub_checkbox)

        self.perennial_checkbox = QCheckBox(self.tr("🌸 Perennials"))
        self.perennial_checkbox.setChecked(True)
        self.perennial_checkbox.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.perennial_checkbox)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Results count label
        self.results_label = QLabel(self.tr("No plants in project"))
        self.results_label.setStyleSheet("color: palette(text);")
        layout.addWidget(self.results_label)

        # Results list
        self.results_list = QListWidget()
        self.results_list.setAlternatingRowColors(True)
        self.results_list.itemClicked.connect(self._on_item_clicked)
        self.results_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.results_list)

    def set_canvas_scene(self, scene) -> None:
        """Set the canvas scene to query plants from.

        Args:
            scene: The CanvasScene instance
        """
        self._scene = scene
        self.refresh_plant_list()

    def refresh_plant_list(self) -> None:
        """Refresh the list of plants from the canvas scene."""
        self._all_plants = []

        if not hasattr(self, "_scene") or self._scene is None:
            self._update_results_display()
            return

        # Query all items from the scene
        for item in self._scene.items():
            if not hasattr(item, "object_type"):
                continue

            object_type = item.object_type
            if object_type not in (ObjectType.TREE, ObjectType.SHRUB, ObjectType.PERENNIAL):
                continue

            # Get plant data
            item_id = getattr(item, "item_id", None)
            if item_id is None:
                continue

            # Get name from item or plant metadata
            name = getattr(item, "name", None) or ""
            species = ""
            family = ""

            if hasattr(item, "metadata") and item.metadata:
                species_data = item.metadata.get("plant_species")
                if species_data:
                    if isinstance(species_data, dict):
                        name = name or species_data.get("common_name", "")
                        species = species_data.get("scientific_name", "")
                        family = species_data.get("family", "")
                    elif isinstance(species_data, PlantSpeciesData):
                        name = name or species_data.common_name or ""
                        species = species_data.scientific_name or ""
                        family = species_data.family or ""

            # Store plant info: (id, name, species, family, type, item)
            self._all_plants.append((item_id, name, species, family, object_type, item))

        # Sort alphabetically by name (case-insensitive)
        self._all_plants.sort(key=lambda p: (p[1] or "").lower())

        self._update_results_display()

    def _on_search_changed(self, _text: str) -> None:
        """Handle search text changes."""
        self._update_results_display()

    def _on_filter_changed(self) -> None:
        """Handle filter checkbox changes."""
        self._update_results_display()

    def _update_results_display(self) -> None:
        """Update the results list based on current search and filters."""
        self.results_list.clear()

        search_text = self.search_input.text().lower().strip()

        # Get enabled filters
        enabled_types = set()
        if self.tree_checkbox.isChecked():
            enabled_types.add(ObjectType.TREE)
        if self.shrub_checkbox.isChecked():
            enabled_types.add(ObjectType.SHRUB)
        if self.perennial_checkbox.isChecked():
            enabled_types.add(ObjectType.PERENNIAL)

        matching_count = 0

        for item_id, name, species, family, plant_type, graphics_item in self._all_plants:
            # Filter by type
            if plant_type not in enabled_types:
                continue

            # Filter by search text
            if search_text:
                searchable = f"{name} {species} {family}".lower()
                if search_text not in searchable:
                    continue

            # Add to results
            list_item = QListWidgetItem()
            widget = PlantListItem(item_id, name, species, plant_type)
            list_item.setSizeHint(widget.sizeHint())
            list_item.setData(Qt.ItemDataRole.UserRole, (item_id, graphics_item))

            self.results_list.addItem(list_item)
            self.results_list.setItemWidget(list_item, widget)
            matching_count += 1

        # Update results label
        total = len(self._all_plants)
        if total == 0:
            self.results_label.setText(self.tr("No plants in project"))
        elif matching_count == total:
            self.results_label.setText(self.tr("{count} plant(s) in project").format(count=total))
        else:
            self.results_label.setText(
                self.tr("Showing {shown} of {total} plants").format(
                    shown=matching_count, total=total
                )
            )

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle single click on a plant item - select it."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            item_id, graphics_item = data
            self._select_plant(graphics_item)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double click on a plant item - select and pan to it."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            item_id, graphics_item = data
            self._select_and_pan_to_plant(graphics_item)

    def _select_plant(self, graphics_item: QGraphicsItem) -> None:
        """Select a plant on the canvas.

        Args:
            graphics_item: The graphics item to select
        """
        if not hasattr(self, "_scene") or self._scene is None:
            return

        # Clear current selection and select this item
        self._scene.clearSelection()
        graphics_item.setSelected(True)

    def _select_and_pan_to_plant(self, graphics_item: QGraphicsItem) -> None:
        """Select a plant and pan the view to center on it.

        Args:
            graphics_item: The graphics item to select and pan to
        """
        if not hasattr(self, "_scene") or self._scene is None:
            return

        # Select the item
        self._select_plant(graphics_item)

        # Pan to center on the item
        views = self._scene.views()
        if views:
            view = views[0]
            # Get item center in scene coordinates
            item_center = graphics_item.sceneBoundingRect().center()
            view.centerOn(item_center)

            # Emit signal for any additional handling
            item_id = getattr(graphics_item, "item_id", None)
            if item_id:
                self.plant_selected.emit(item_id)
