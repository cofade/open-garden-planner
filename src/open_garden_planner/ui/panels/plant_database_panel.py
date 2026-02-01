"""Plant database panel for displaying plant species metadata."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGraphicsItem,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import (
    PlantCycle,
    PlantSpeciesData,
    SunRequirement,
    WaterNeeds,
)


class EditableField(QWidget):
    """A field that shows a label and allows inline editing on double-click."""

    value_changed = pyqtSignal()

    def __init__(
        self,
        field_type: str = "text",
        enum_class: type | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the editable field.

        Args:
            field_type: Type of field - "text", "enum", "number", "bool"
            enum_class: Enum class for enum fields
            parent: Parent widget
        """
        super().__init__(parent)
        self.field_type = field_type
        self.enum_class = enum_class
        self._value: str | int | float | bool | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Common style for consistent sizing
        common_style = "font-weight: bold; padding: 0px; margin: 0px;"

        # Display label
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setStyleSheet(common_style)
        self.label.mouseDoubleClickEvent = lambda _: self._start_editing()
        layout.addWidget(self.label)

        # Edit widgets (hidden by default)
        if field_type == "text":
            self.edit_widget = QLineEdit()
            self.edit_widget.setStyleSheet(common_style)
            self.edit_widget.editingFinished.connect(self._finish_editing)
            self.edit_widget.returnPressed.connect(self._finish_editing)
        elif field_type == "enum":
            self.edit_widget = QComboBox()
            self.edit_widget.setStyleSheet(common_style)
            if enum_class:
                for item in enum_class:
                    self.edit_widget.addItem(
                        item.value.replace("_", " ").title(), item.value
                    )
            self.edit_widget.currentIndexChanged.connect(self._finish_editing)
        elif field_type == "number":
            self.edit_widget = QLineEdit()
            self.edit_widget.setStyleSheet(common_style)
            self.edit_widget.editingFinished.connect(self._finish_editing)
            self.edit_widget.returnPressed.connect(self._finish_editing)
        elif field_type == "bool":
            self.edit_widget = QCheckBox()
            self.edit_widget.setStyleSheet(common_style)
            self.edit_widget.stateChanged.connect(self._finish_editing)
        else:
            self.edit_widget = QLineEdit()
            self.edit_widget.setStyleSheet(common_style)
            self.edit_widget.editingFinished.connect(self._finish_editing)

        self.edit_widget.hide()
        layout.addWidget(self.edit_widget)

    def set_value(self, value: str | int | float | bool | None) -> None:
        """Set the field value."""
        self._value = value
        if value is None or value == "":
            self.label.setText("N/A")
        else:
            self.label.setText(str(value))

    def get_value(self) -> str | int | float | bool | None:
        """Get the field value."""
        return self._value

    def _start_editing(self) -> None:
        """Start inline editing."""
        self.label.hide()

        if self.field_type == "text":
            self.edit_widget.setText(self._value or "")
            self.edit_widget.selectAll()
        elif self.field_type == "enum":
            # Find and select current value
            index = self.edit_widget.findData(self._value)
            if index >= 0:
                self.edit_widget.setCurrentIndex(index)
        elif self.field_type == "number":
            self.edit_widget.setText(str(self._value) if self._value else "")
            self.edit_widget.selectAll()
        elif self.field_type == "bool":
            self.edit_widget.setChecked(bool(self._value))

        self.edit_widget.show()
        self.edit_widget.setFocus()

    def _finish_editing(self) -> None:
        """Finish inline editing."""
        old_value = self._value

        if self.field_type == "text":
            self._value = self.edit_widget.text().strip() or None
        elif self.field_type == "enum":
            self._value = self.edit_widget.currentData()
        elif self.field_type == "number":
            text = self.edit_widget.text().strip()
            try:
                self._value = float(text) if text else None
            except ValueError:
                self._value = old_value  # Keep old value if invalid
        elif self.field_type == "bool":
            self._value = self.edit_widget.isChecked()

        self.edit_widget.hide()
        self.set_value(self._value)
        self.label.show()

        # Emit signal if value changed
        if self._value != old_value:
            self.value_changed.emit()


class PlantDatabasePanel(QWidget):
    """Panel for displaying plant species information from the database.

    Shows botanical and growing information when a plant object is selected.
    Allows inline editing of all fields.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the plant database panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._current_plant_data: PlantSpeciesData | None = None
        self._current_plant_item: QGraphicsItem | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Search button at top
        self.search_button = QPushButton("Search Plant Database")
        self.search_button.setToolTip("Search for plant species in online databases")
        layout.addWidget(self.search_button)

        # Scrollable area for plant info
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Container for plant info
        self.info_widget = QWidget()
        self.info_layout = QVBoxLayout(self.info_widget)
        self.info_layout.setContentsMargins(4, 4, 4, 4)
        self.info_layout.setSpacing(4)

        # Info labels
        self.no_selection_label = QLabel("Select a plant to view details")
        self.no_selection_label.setWordWrap(True)
        self.no_selection_label.setStyleSheet("color: gray; font-style: italic;")
        self.info_layout.addWidget(self.no_selection_label)

        # Form layout for plant details (hidden initially)
        self.details_form = QFormLayout()
        self.details_form.setSpacing(4)
        self.info_layout.addLayout(self.details_form)

        # Editable fields
        self._create_editable_fields()

        self.info_layout.addStretch()

        scroll.setWidget(self.info_widget)
        layout.addWidget(scroll)

        # Initially hide details
        self._hide_details()

    def _create_editable_fields(self) -> None:
        """Create editable fields for displaying plant information."""
        # Scientific name
        self.scientific_field = EditableField("text")
        self.scientific_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Scientific:", self.scientific_field)

        # Common name
        self.common_field = EditableField("text")
        self.common_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Common:", self.common_field)

        # Family
        self.family_field = EditableField("text")
        self.family_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Family:", self.family_field)

        # Cycle (annual/perennial)
        self.cycle_field = EditableField("enum", PlantCycle)
        self.cycle_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Cycle:", self.cycle_field)

        # Sun requirements
        self.sun_field = EditableField("enum", SunRequirement)
        self.sun_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Sun:", self.sun_field)

        # Water needs
        self.water_field = EditableField("enum", WaterNeeds)
        self.water_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Water:", self.water_field)

        # Height (max)
        self.height_field = EditableField("number")
        self.height_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Max Height (cm):", self.height_field)

        # Hardiness zones
        self.hardiness_min_field = EditableField("number")
        self.hardiness_min_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Hardiness Min:", self.hardiness_min_field)

        self.hardiness_max_field = EditableField("number")
        self.hardiness_max_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Hardiness Max:", self.hardiness_max_field)

        # Edible
        self.edible_field = EditableField("bool")
        self.edible_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Edible:", self.edible_field)

        # Edible parts
        self.edible_parts_field = EditableField("text")
        self.edible_parts_field.value_changed.connect(self._on_field_changed)
        self.details_form.addRow("Edible Parts:", self.edible_parts_field)

        # Data source (read-only)
        self.source_label = QLabel()
        self.source_label.setStyleSheet("color: gray; font-size: 10pt;")
        self.details_form.addRow("Source:", self.source_label)

    def _on_field_changed(self) -> None:
        """Handle field value changes - update plant metadata."""
        if not self._current_plant_item or not self._current_plant_data:
            return

        # Update the PlantSpeciesData object
        self._current_plant_data.scientific_name = (
            self.scientific_field.get_value() or "Unknown"
        )
        self._current_plant_data.common_name = self.common_field.get_value() or ""
        self._current_plant_data.family = self.family_field.get_value() or ""

        # Enums
        cycle_val = self.cycle_field.get_value()
        if cycle_val:
            self._current_plant_data.cycle = PlantCycle(cycle_val)

        sun_val = self.sun_field.get_value()
        if sun_val:
            self._current_plant_data.sun_requirement = SunRequirement(sun_val)

        water_val = self.water_field.get_value()
        if water_val:
            self._current_plant_data.water_needs = WaterNeeds(water_val)

        # Numbers
        height_val = self.height_field.get_value()
        self._current_plant_data.max_height_cm = float(height_val) if height_val else None

        hardiness_min = self.hardiness_min_field.get_value()
        self._current_plant_data.hardiness_zone_min = (
            int(hardiness_min) if hardiness_min else None
        )

        hardiness_max = self.hardiness_max_field.get_value()
        self._current_plant_data.hardiness_zone_max = (
            int(hardiness_max) if hardiness_max else None
        )

        # Boolean
        self._current_plant_data.edible = bool(self.edible_field.get_value())

        # Edible parts (comma-separated list)
        edible_parts_str = self.edible_parts_field.get_value()
        if edible_parts_str:
            self._current_plant_data.edible_parts = [
                p.strip() for p in str(edible_parts_str).split(",") if p.strip()
            ]
        else:
            self._current_plant_data.edible_parts = []

        # Save back to item metadata
        if hasattr(self._current_plant_item, "metadata"):
            if not self._current_plant_item.metadata:
                self._current_plant_item.metadata = {}
            self._current_plant_item.metadata["plant_species"] = (
                self._current_plant_data.to_dict()
            )

            # Mark project as dirty
            scene = self._current_plant_item.scene()
            if scene and hasattr(scene, "views"):
                for view in scene.views():
                    if hasattr(view, "window"):
                        window = view.window()
                        if hasattr(window, "_project_manager"):
                            window._project_manager.mark_dirty()
                            break

    def set_selected_items(self, items: list[QGraphicsItem]) -> None:
        """Update panel based on selected items.

        Args:
            items: List of selected graphics items
        """
        # Check if exactly one plant item is selected
        if len(items) != 1:
            self._hide_details()
            return

        item = items[0]

        # Check if it's a plant type
        if not hasattr(item, "object_type"):
            self._hide_details()
            return

        object_type = item.object_type
        if object_type not in (ObjectType.TREE, ObjectType.SHRUB, ObjectType.PERENNIAL):
            self._hide_details()
            return

        # Check if it has plant metadata
        if not hasattr(item, "metadata") or not item.metadata:
            self._show_no_metadata()
            return

        # Try to load plant species data from metadata
        species_data = item.metadata.get("plant_species")
        if not species_data:
            self._show_no_metadata()
            return

        # Deserialize and display
        try:
            if isinstance(species_data, dict):
                plant_data = PlantSpeciesData.from_dict(species_data)
                self._show_plant_data(plant_data, item)
            elif isinstance(species_data, PlantSpeciesData):
                self._show_plant_data(species_data, item)
            else:
                self._show_no_metadata()
        except Exception:
            self._show_no_metadata()

    def _hide_details(self) -> None:
        """Hide plant details and show 'no selection' message."""
        self._current_plant_data = None
        self._current_plant_item = None
        self.no_selection_label.setText("Select a plant to view details")
        self.no_selection_label.setVisible(True)

        # Hide all form widgets
        for i in range(self.details_form.rowCount()):
            label_item = self.details_form.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.details_form.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(False)
            if field_item and field_item.widget():
                field_item.widget().setVisible(False)

    def _show_no_metadata(self) -> None:
        """Show message that selected plant has no metadata."""
        self._current_plant_data = None
        self._current_plant_item = None
        self.no_selection_label.setText(
            "No species data.\n\nClick 'Search Plant Database' to add species information."
        )
        self.no_selection_label.setVisible(True)

        # Hide all form widgets
        for i in range(self.details_form.rowCount()):
            label_item = self.details_form.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.details_form.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(False)
            if field_item and field_item.widget():
                field_item.widget().setVisible(False)

    def _show_plant_data(
        self, plant_data: PlantSpeciesData, plant_item: QGraphicsItem
    ) -> None:
        """Display plant species data.

        Args:
            plant_data: Plant species data to display
            plant_item: The graphics item this data belongs to
        """
        self._current_plant_data = plant_data
        self._current_plant_item = plant_item
        self.no_selection_label.setVisible(False)

        # Show all form widgets
        for i in range(self.details_form.rowCount()):
            label_item = self.details_form.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.details_form.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(True)
            if field_item and field_item.widget():
                field_item.widget().setVisible(True)

        # Update field values
        self.scientific_field.set_value(plant_data.scientific_name)
        self.common_field.set_value(plant_data.common_name or "N/A")
        self.family_field.set_value(plant_data.family or "N/A")

        # Enums
        self.cycle_field.set_value(plant_data.cycle.value)
        self.sun_field.set_value(plant_data.sun_requirement.value)
        self.water_field.set_value(plant_data.water_needs.value)

        # Height
        if plant_data.max_height_cm:
            self.height_field.set_value(
                f"{plant_data.max_height_cm:.0f} cm ({plant_data.max_height_cm/100:.1f} m)"
            )
            # Store raw value for editing
            self.height_field._value = plant_data.max_height_cm
        else:
            self.height_field.set_value(None)

        # Hardiness
        self.hardiness_min_field.set_value(
            plant_data.hardiness_zone_min if plant_data.hardiness_zone_min else None
        )
        self.hardiness_max_field.set_value(
            plant_data.hardiness_zone_max if plant_data.hardiness_zone_max else None
        )

        # Edible
        self.edible_field.set_value("Yes" if plant_data.edible else "No")
        self.edible_field._value = plant_data.edible

        # Edible parts
        if plant_data.edible_parts:
            parts_text = ", ".join(plant_data.edible_parts)
            self.edible_parts_field.set_value(parts_text)
        else:
            self.edible_parts_field.set_value(None)

        # Data source (read-only)
        source_text = f"{plant_data.data_source.title()}"
        if plant_data.source_id:
            source_text += f" (ID: {plant_data.source_id})"
        self.source_label.setText(source_text)
