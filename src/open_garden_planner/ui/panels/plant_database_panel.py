"""Plant database panel for displaying plant species metadata."""

from datetime import date

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
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
from open_garden_planner.services import get_plant_library


class ClickableDateEdit(QDateEdit):
    """A QDateEdit that opens calendar on click, is read-only, and defaults to current month."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the date edit."""
        super().__init__(parent)
        self.setCalendarPopup(True)
        # Make the line edit read-only so users can only select via calendar
        self.lineEdit().setReadOnly(True)
        # Style to indicate it's clickable
        self.setStyleSheet("QDateEdit { background-color: palette(base); }")

    def mousePressEvent(self, event) -> None:
        """Open calendar popup on any click."""
        if event.button() == Qt.MouseButton.LeftButton:
            # If we're showing special value (no date set), show today's month
            if self.date() == self.minimumDate():
                calendar = self.calendarWidget()
                if calendar:
                    calendar.setSelectedDate(QDate.currentDate())
            # Always show the calendar popup on left click
            calendar = self.calendarWidget()
            if calendar:
                # Position calendar below the widget
                self.setFocus()
                calendar.show()
                calendar.setFocus()
        super().mousePressEvent(event)


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
        elif self.field_type == "enum":
            # Format enum values consistently with combobox display
            self.label.setText(str(value).replace("_", " ").title())
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

        # Button row at top
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)

        # Search button
        self.search_button = QPushButton("Search")
        self.search_button.setToolTip("Search for plant species in online databases")
        button_layout.addWidget(self.search_button)

        # Create custom plant button
        self.create_custom_button = QPushButton("Create Custom")
        self.create_custom_button.setToolTip("Create a custom plant species entry")
        self.create_custom_button.clicked.connect(self._on_create_custom_plant)
        button_layout.addWidget(self.create_custom_button)

        layout.addLayout(button_layout)

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

        # Cycle (annual/perennial) - direct dropdown
        self.cycle_combo = QComboBox()
        for item in PlantCycle:
            self.cycle_combo.addItem(item.value.replace("_", " ").title(), item.value)
        self.cycle_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow("Cycle:", self.cycle_combo)

        # Sun requirements - direct dropdown
        self.sun_combo = QComboBox()
        for item in SunRequirement:
            self.sun_combo.addItem(item.value.replace("_", " ").title(), item.value)
        self.sun_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow("Sun:", self.sun_combo)

        # Water needs - direct dropdown
        self.water_combo = QComboBox()
        for item in WaterNeeds:
            self.water_combo.addItem(item.value.replace("_", " ").title(), item.value)
        self.water_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow("Water:", self.water_combo)

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

        # Variety/Cultivar
        self.variety_field = EditableField("text")
        self.variety_field.value_changed.connect(self._on_instance_field_changed)
        self.details_form.addRow("Variety:", self.variety_field)

        # Planting Date
        self.planting_date_edit = ClickableDateEdit()
        self.planting_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.planting_date_edit.setSpecialValueText("Not set")
        self.planting_date_edit.setMinimumDate(self.planting_date_edit.minimumDate())
        self.planting_date_edit.dateChanged.connect(self._on_planting_date_changed)
        self.details_form.addRow("Planted:", self.planting_date_edit)

        # Current Height
        self.current_height_spin = QDoubleSpinBox()
        self.current_height_spin.setRange(0, 10000)
        self.current_height_spin.setSingleStep(10)
        self.current_height_spin.setDecimals(0)
        self.current_height_spin.setSuffix(" cm")
        self.current_height_spin.setSpecialValueText("Unknown")
        self.current_height_spin.valueChanged.connect(self._on_current_height_changed)
        self.details_form.addRow("Current Height:", self.current_height_spin)

        # Notes
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Notes about this plant...")
        self.notes_edit.setMaximumHeight(60)
        self.notes_edit.textChanged.connect(self._on_notes_changed)
        self.details_form.addRow("Notes:", self.notes_edit)

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

        # Enums from combo boxes
        cycle_val = self.cycle_combo.currentData()
        if cycle_val:
            self._current_plant_data.cycle = PlantCycle(cycle_val)

        sun_val = self.sun_combo.currentData()
        if sun_val:
            self._current_plant_data.sun_requirement = SunRequirement(sun_val)

        water_val = self.water_combo.currentData()
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

            # If this is a custom plant, update the library
            if self._current_plant_data.data_source == "custom":
                library = get_plant_library()
                plant_id = self._current_plant_data.source_id
                if plant_id:
                    library.update_plant(plant_id, self._current_plant_data)

            # Mark project as dirty
            scene = self._current_plant_item.scene()
            if scene and hasattr(scene, "views"):
                for view in scene.views():
                    if hasattr(view, "window"):
                        window = view.window()
                        if hasattr(window, "_project_manager"):
                            window._project_manager.mark_dirty()
                            break

    def _on_instance_field_changed(self) -> None:
        """Handle variety field change."""
        if not self._current_plant_item:
            return
        self._update_instance_metadata("variety_cultivar", self.variety_field.get_value())

    def _on_planting_date_changed(self) -> None:
        """Handle planting date change."""
        if not self._current_plant_item:
            return
        d = self.planting_date_edit.date()
        value = d.toPyDate().isoformat() if d != self.planting_date_edit.minimumDate() else None
        self._update_instance_metadata("planting_date", value)

    def _on_current_height_changed(self) -> None:
        """Handle current height change."""
        if not self._current_plant_item:
            return
        val = self.current_height_spin.value()
        self._update_instance_metadata("current_height_cm", val if val > 0 else None)

    def _on_notes_changed(self) -> None:
        """Handle notes change."""
        if not self._current_plant_item:
            return
        self._update_instance_metadata("notes", self.notes_edit.toPlainText() or None)

    def _update_instance_metadata(self, key: str, value) -> None:
        """Update plant instance metadata and mark project dirty.

        Args:
            key: The metadata key to update
            value: The new value (None to remove)
        """
        if not self._current_plant_item:
            return

        # Ensure metadata exists
        if not hasattr(self._current_plant_item, "metadata") or self._current_plant_item.metadata is None:
            self._current_plant_item.metadata = {}

        # Get or create plant_instance dict
        if "plant_instance" not in self._current_plant_item.metadata:
            self._current_plant_item.metadata["plant_instance"] = {}

        # Update value
        if value is None or value == "":
            self._current_plant_item.metadata["plant_instance"].pop(key, None)
        else:
            self._current_plant_item.metadata["plant_instance"][key] = value

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

        # Store current plant item for Create Custom functionality
        self._current_plant_item = item

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
        # Keep the plant item reference so Create Custom can use it
        # self._current_plant_item is set by set_selected_items
        self._current_plant_data = None
        self.no_selection_label.setText(
            "No species data.\n\n"
            "Click 'Search' to find species online,\n"
            "or 'Create Custom' to define your own."
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

        # Enums - set combo box selections (block signals to avoid triggering changes)
        self.cycle_combo.blockSignals(True)
        cycle_index = self.cycle_combo.findData(plant_data.cycle.value)
        if cycle_index >= 0:
            self.cycle_combo.setCurrentIndex(cycle_index)
        self.cycle_combo.blockSignals(False)

        self.sun_combo.blockSignals(True)
        sun_index = self.sun_combo.findData(plant_data.sun_requirement.value)
        if sun_index >= 0:
            self.sun_combo.setCurrentIndex(sun_index)
        self.sun_combo.blockSignals(False)

        self.water_combo.blockSignals(True)
        water_index = self.water_combo.findData(plant_data.water_needs.value)
        if water_index >= 0:
            self.water_combo.setCurrentIndex(water_index)
        self.water_combo.blockSignals(False)

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

        # --- Plant Instance Fields ---
        # Get instance data from item metadata
        instance_data = {}
        if hasattr(plant_item, "metadata") and plant_item.metadata:
            instance_data = plant_item.metadata.get("plant_instance", {})

        # Variety
        self.variety_field.set_value(instance_data.get("variety_cultivar") or None)

        # Planting date
        planting_date_str = instance_data.get("planting_date")
        if planting_date_str:
            try:
                planting_date_val = date.fromisoformat(planting_date_str)
                self.planting_date_edit.setDate(planting_date_val)
            except (ValueError, TypeError):
                self.planting_date_edit.setDate(self.planting_date_edit.minimumDate())
        else:
            self.planting_date_edit.setDate(self.planting_date_edit.minimumDate())

        # Current height
        current_height = instance_data.get("current_height_cm")
        self.current_height_spin.setValue(float(current_height) if current_height else 0)

        # Notes
        self.notes_edit.setPlainText(instance_data.get("notes") or "")

    def _on_create_custom_plant(self) -> None:
        """Handle Create Custom Plant button click."""
        # Check if we have a selected plant item
        if not self._current_plant_item:
            QMessageBox.information(
                self,
                "No Plant Selected",
                "Please select a plant object (tree, shrub, or perennial) first.",
            )
            return

        # Create a new custom plant species
        custom_plant = PlantSpeciesData(
            scientific_name="Custom Species",
            common_name="My Custom Plant",
            data_source="custom",
        )

        # Store the current plant item reference
        plant_item = self._current_plant_item

        # Assign to the selected plant item
        if not hasattr(plant_item, "metadata") or plant_item.metadata is None:
            plant_item.metadata = {}
        plant_item.metadata["plant_species"] = custom_plant.to_dict()

        # Add to the custom plant library
        library = get_plant_library()
        plant_id = library.add_plant(custom_plant)

        # Update the source_id in the item's metadata
        plant_item.metadata["plant_species"]["source_id"] = plant_id

        # Show the plant data for editing
        self._show_plant_data(custom_plant, plant_item)

        # Mark project as dirty
        scene = plant_item.scene()
        if scene and hasattr(scene, "views"):
            for view in scene.views():
                if hasattr(view, "window"):
                    window = view.window()
                    if hasattr(window, "_project_manager"):
                        window._project_manager.mark_dirty()
                        break

    def _save_to_custom_library(self) -> None:
        """Save the current plant data to the custom library."""
        if not self._current_plant_data or not self._current_plant_item:
            return

        library = get_plant_library()

        # Check if this is already a custom plant
        if self._current_plant_data.data_source == "custom":
            # Update existing custom plant
            plant_id = self._current_plant_data.source_id
            if plant_id:
                library.update_plant(plant_id, self._current_plant_data)
        else:
            # Add as new custom plant (copy from API source)
            self._current_plant_data.data_source = "custom"
            plant_id = library.add_plant(self._current_plant_data)

            # Update the item's metadata with new source info
            if hasattr(self._current_plant_item, "metadata"):
                self._current_plant_item.metadata["plant_species"] = (
                    self._current_plant_data.to_dict()
                )
