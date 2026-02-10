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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import (
    FlowerType,
    PlantCycle,
    PlantSpeciesData,
    PollinationType,
    SunRequirement,
    WaterNeeds,
)
from open_garden_planner.services import get_plant_library


class ClickableDateEdit(QDateEdit):
    """A QDateEdit with a visible dropdown arrow for calendar popup.

    Uses the standard Qt approach with a dropdown button to open the calendar.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the date edit."""
        super().__init__(parent)
        self.setCalendarPopup(True)
        self._min_date = QDate(1900, 1, 1)
        self.setMinimumDate(self._min_date)

        # Make the line edit read-only
        line_edit = self.lineEdit()
        line_edit.setReadOnly(True)
        line_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Set cursor to indicate clickability
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Initialize to today's date
        self.setDate(QDate.currentDate())


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
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(8)

        # Button row at top
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)

        # Search button
        self.search_button = QPushButton(self.tr("Search"))
        self.search_button.setToolTip(self.tr("Search for plant species in online databases"))
        button_layout.addWidget(self.search_button)

        # Create custom plant button
        self.create_custom_button = QPushButton(self.tr("Create Custom"))
        self.create_custom_button.setToolTip(self.tr("Create a custom plant species entry"))
        self.create_custom_button.clicked.connect(self._on_create_custom_plant)
        button_layout.addWidget(self.create_custom_button)

        # Load from custom library button
        self.load_custom_button = QPushButton(self.tr("Load Custom"))
        self.load_custom_button.setToolTip(self.tr("Load a plant from your custom library"))
        self.load_custom_button.clicked.connect(self._on_load_custom_plant)
        button_layout.addWidget(self.load_custom_button)

        layout.addLayout(button_layout)

        # Scrollable area for plant info
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Container for plant info
        self.info_widget = QWidget()
        self.info_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.info_layout = QVBoxLayout(self.info_widget)
        self.info_layout.setContentsMargins(2, 4, 2, 4)
        self.info_layout.setSpacing(4)

        # Info labels
        self.no_selection_label = QLabel(self.tr("Select a plant to view details"))
        self.no_selection_label.setWordWrap(True)
        self.no_selection_label.setStyleSheet("color: palette(mid); font-style: italic;")
        self.info_layout.addWidget(self.no_selection_label)

        # Form layout for plant details (hidden initially)
        self.details_form = QFormLayout()
        self.details_form.setSpacing(4)
        self.details_form.setContentsMargins(0, 0, 0, 0)
        # Make form fields expand to fill available width
        self.details_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self.details_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_layout.addLayout(self.details_form)

        # Editable fields
        self._create_editable_fields()

        self.info_layout.addStretch()

        scroll.setWidget(self.info_widget)
        layout.addWidget(scroll)

        # Initially hide details
        self._hide_details()

    def _create_editable_fields(self) -> None:
        """Create editable fields for displaying plant information.

        Fields are ordered logically for gardeners:
        1. Basic identity (common/scientific/family/variety)
        2. Plant characteristics (cycle)
        3. Care requirements (sun/water)
        4. Growth information (heights/spread)
        5. Edibility
        6. Hardiness
        7. Planting info
        8. Notes
        """
        # === BASIC IDENTITY ===

        # Common name
        self.common_edit = QLineEdit()
        self.common_edit.setPlaceholderText(self.tr("Enter common name..."))
        self.common_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.common_edit.editingFinished.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Common Name:"), self.common_edit)

        # Scientific name
        self.scientific_edit = QLineEdit()
        self.scientific_edit.setPlaceholderText(self.tr("Enter scientific name..."))
        self.scientific_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.scientific_edit.editingFinished.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Scientific Name:"), self.scientific_edit)

        # Family
        self.family_edit = QLineEdit()
        self.family_edit.setPlaceholderText(self.tr("Enter plant family..."))
        self.family_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.family_edit.editingFinished.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Family:"), self.family_edit)

        # Variety/Cultivar (instance-specific)
        self.variety_edit = QLineEdit()
        self.variety_edit.setPlaceholderText(self.tr("Enter variety or cultivar..."))
        self.variety_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.variety_edit.editingFinished.connect(self._on_instance_field_changed)
        self.details_form.addRow(self.tr("Variety:"), self.variety_edit)

        # === PLANT CHARACTERISTICS ===

        # Cycle (annual/perennial)
        self.cycle_combo = QComboBox()
        for item in PlantCycle:
            # Skip "unknown" - don't show it as an option
            if item != PlantCycle.UNKNOWN:
                self.cycle_combo.addItem(item.value.replace("_", " ").title(), item.value)
        self.cycle_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cycle_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Cycle:"), self.cycle_combo)

        # === REPRODUCTIVE CHARACTERISTICS ===

        # Flower Type (sexual system)
        self.flower_type_combo = QComboBox()
        flower_type_labels = {
            FlowerType.HERMAPHRODITE: "Hermaphrodite (perfect flowers)",
            FlowerType.MONOECIOUS: "Monoecious (separate ♂/♀ flowers)",
            FlowerType.DIOECIOUS_MALE: "Dioecious Male (♂ only)",
            FlowerType.DIOECIOUS_FEMALE: "Dioecious Female (♀ only)",
        }
        for item in FlowerType:
            if item != FlowerType.UNKNOWN:
                label = flower_type_labels.get(item, item.value.replace("_", " ").title())
                self.flower_type_combo.addItem(label, item.value)
        self.flower_type_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.flower_type_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Flower Type:"), self.flower_type_combo)

        # Pollination Type (self-fertility)
        self.pollination_combo = QComboBox()
        pollination_labels = {
            PollinationType.SELF_FERTILE: "Self-fertile (no partner needed)",
            PollinationType.PARTIALLY_SELF_FERTILE: "Partially self-fertile",
            PollinationType.SELF_STERILE: "Self-sterile (needs partner)",
            PollinationType.TRIPLOID: "Triploid (sterile pollen)",
        }
        for item in PollinationType:
            if item != PollinationType.UNKNOWN:
                label = pollination_labels.get(item, item.value.replace("_", " ").title())
                self.pollination_combo.addItem(label, item.value)
        self.pollination_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pollination_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Pollination:"), self.pollination_combo)

        # === CARE REQUIREMENTS ===

        # Sun requirements
        self.sun_combo = QComboBox()
        for item in SunRequirement:
            # Skip "unknown" - don't show it as an option
            if item != SunRequirement.UNKNOWN:
                self.sun_combo.addItem(item.value.replace("_", " ").title(), item.value)
        self.sun_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sun_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Sun:"), self.sun_combo)

        # Water needs
        self.water_combo = QComboBox()
        for item in WaterNeeds:
            # Skip "unknown" - don't show it as an option
            if item != WaterNeeds.UNKNOWN:
                self.water_combo.addItem(item.value.replace("_", " ").title(), item.value)
        self.water_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.water_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Water:"), self.water_combo)

        # === GROWTH INFORMATION ===

        # Max Height
        self.max_height_spin = QDoubleSpinBox()
        self.max_height_spin.setRange(0, 10000)
        self.max_height_spin.setSingleStep(10)
        self.max_height_spin.setDecimals(0)
        self.max_height_spin.setSuffix(" cm")
        self.max_height_spin.setSpecialValueText("")  # Empty when 0
        self.max_height_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.max_height_spin.valueChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Max Height:"), self.max_height_spin)

        # Max Spread
        self.max_spread_spin = QDoubleSpinBox()
        self.max_spread_spin.setRange(0, 10000)
        self.max_spread_spin.setSingleStep(10)
        self.max_spread_spin.setDecimals(0)
        self.max_spread_spin.setSuffix(" cm")
        self.max_spread_spin.setSpecialValueText("")  # Empty when 0
        self.max_spread_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.max_spread_spin.valueChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Max Spread:"), self.max_spread_spin)

        # Current Height (instance-specific)
        self.current_height_spin = QDoubleSpinBox()
        self.current_height_spin.setRange(0, 10000)
        self.current_height_spin.setSingleStep(10)
        self.current_height_spin.setDecimals(0)
        self.current_height_spin.setSuffix(" cm")
        self.current_height_spin.setSpecialValueText("")  # Empty when 0
        self.current_height_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.current_height_spin.valueChanged.connect(self._on_current_height_changed)
        self.details_form.addRow(self.tr("Current Height:"), self.current_height_spin)

        # Current Spread (instance-specific)
        self.current_spread_spin = QDoubleSpinBox()
        self.current_spread_spin.setRange(0, 10000)
        self.current_spread_spin.setSingleStep(10)
        self.current_spread_spin.setDecimals(0)
        self.current_spread_spin.setSuffix(" cm")
        self.current_spread_spin.setSpecialValueText("")  # Empty when 0
        self.current_spread_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.current_spread_spin.valueChanged.connect(self._on_current_spread_changed)
        self.details_form.addRow(self.tr("Current Spread:"), self.current_spread_spin)

        # === EDIBILITY ===

        # Edible (simple checkbox)
        self.edible_checkbox = QCheckBox()
        self.edible_checkbox.stateChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Edible:"), self.edible_checkbox)

        # Edible parts
        self.edible_parts_edit = QLineEdit()
        self.edible_parts_edit.setPlaceholderText(self.tr("e.g., fruit, leaves, roots..."))
        self.edible_parts_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.edible_parts_edit.editingFinished.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Edible Parts:"), self.edible_parts_edit)

        # === HARDINESS ===

        # Hardiness zones (min/max on same row)
        hardiness_layout = QHBoxLayout()
        hardiness_layout.setSpacing(4)

        # Min zone
        min_label = QLabel(self.tr("Min:"))
        hardiness_layout.addWidget(min_label)

        self.hardiness_min_spin = QDoubleSpinBox()
        self.hardiness_min_spin.setRange(0, 13)
        self.hardiness_min_spin.setSingleStep(1)
        self.hardiness_min_spin.setDecimals(0)
        self.hardiness_min_spin.setSpecialValueText("")
        self.hardiness_min_spin.setMinimumWidth(60)  # Ensure arrows are visible
        self.hardiness_min_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.hardiness_min_spin.valueChanged.connect(self._on_field_changed)
        hardiness_layout.addWidget(self.hardiness_min_spin, 1)  # stretch factor 1

        # Max zone
        max_label = QLabel(self.tr("Max:"))
        hardiness_layout.addWidget(max_label)

        self.hardiness_max_spin = QDoubleSpinBox()
        self.hardiness_max_spin.setRange(0, 13)
        self.hardiness_max_spin.setSingleStep(1)
        self.hardiness_max_spin.setDecimals(0)
        self.hardiness_max_spin.setSpecialValueText("")
        self.hardiness_max_spin.setMinimumWidth(60)  # Ensure arrows are visible
        self.hardiness_max_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.hardiness_max_spin.valueChanged.connect(self._on_field_changed)
        hardiness_layout.addWidget(self.hardiness_max_spin, 1)  # stretch factor 1

        self.details_form.addRow(self.tr("Hardiness:"), hardiness_layout)

        # === PLANTING INFO ===

        # Planting Date with age display (instance-specific)
        planting_layout = QHBoxLayout()
        planting_layout.setSpacing(4)

        self.planting_date_edit = ClickableDateEdit()
        self.planting_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.planting_date_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Date is already initialized to minimum date in __init__, shows as empty
        self.planting_date_edit.dateChanged.connect(self._on_planting_date_changed)
        planting_layout.addWidget(self.planting_date_edit, 1)

        # Age label (calculated from planting date)
        self.age_label = QLabel("")
        self.age_label.setStyleSheet("color: palette(mid); font-style: italic;")
        planting_layout.addWidget(self.age_label)

        self.details_form.addRow(self.tr("Planted:"), planting_layout)

        # === NOTES ===

        # Notes (instance-specific)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(self.tr("Notes about this plant..."))
        self.notes_edit.setMaximumHeight(60)
        self.notes_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.notes_edit.textChanged.connect(self._on_notes_changed)
        self.details_form.addRow(self.tr("Notes:"), self.notes_edit)

        # === CUSTOM FIELDS ===

        # Custom fields container
        self.custom_fields_widget = QWidget()
        self.custom_fields_layout = QVBoxLayout(self.custom_fields_widget)
        self.custom_fields_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_fields_layout.setSpacing(4)

        # Add custom field button
        add_field_btn = QPushButton(self.tr("+ Add Field"))
        add_field_btn.setToolTip(self.tr("Add a custom metadata field"))
        add_field_btn.clicked.connect(self._on_add_custom_field)
        self.custom_fields_layout.addWidget(add_field_btn)

        self.details_form.addRow(self.tr("Custom:"), self.custom_fields_widget)

    def _on_field_changed(self) -> None:
        """Handle field value changes - update plant metadata."""
        if not self._current_plant_item or not self._current_plant_data:
            return

        # Update the PlantSpeciesData object
        self._current_plant_data.common_name = self.common_edit.text().strip() or ""
        self._current_plant_data.scientific_name = (
            self.scientific_edit.text().strip() or "Unknown"
        )
        self._current_plant_data.family = self.family_edit.text().strip() or ""

        # Enums from combo boxes
        cycle_val = self.cycle_combo.currentData()
        if cycle_val:
            self._current_plant_data.cycle = PlantCycle(cycle_val)

        flower_type_val = self.flower_type_combo.currentData()
        if flower_type_val:
            self._current_plant_data.flower_type = FlowerType(flower_type_val)

        pollination_val = self.pollination_combo.currentData()
        if pollination_val:
            self._current_plant_data.pollination_type = PollinationType(pollination_val)

        sun_val = self.sun_combo.currentData()
        if sun_val:
            self._current_plant_data.sun_requirement = SunRequirement(sun_val)

        water_val = self.water_combo.currentData()
        if water_val:
            self._current_plant_data.water_needs = WaterNeeds(water_val)

        # Numbers from spinboxes
        max_height = self.max_height_spin.value()
        self._current_plant_data.max_height_cm = max_height if max_height > 0 else None

        max_spread = self.max_spread_spin.value()
        self._current_plant_data.max_spread_cm = max_spread if max_spread > 0 else None

        hardiness_min = self.hardiness_min_spin.value()
        self._current_plant_data.hardiness_zone_min = (
            int(hardiness_min) if hardiness_min > 0 else None
        )

        hardiness_max = self.hardiness_max_spin.value()
        self._current_plant_data.hardiness_zone_max = (
            int(hardiness_max) if hardiness_max > 0 else None
        )

        # Boolean from checkbox
        self._current_plant_data.edible = self.edible_checkbox.isChecked()

        # Edible parts (comma-separated list)
        edible_parts_str = self.edible_parts_edit.text().strip()
        if edible_parts_str:
            self._current_plant_data.edible_parts = [
                p.strip() for p in edible_parts_str.split(",") if p.strip()
            ]
        else:
            self._current_plant_data.edible_parts = []

        # Save back to item metadata and custom library
        if hasattr(self._current_plant_item, "metadata"):
            if not self._current_plant_item.metadata:
                self._current_plant_item.metadata = {}

            library = get_plant_library()

            if self._current_plant_data.data_source == "custom":
                # Already a custom plant - update it in the library
                plant_id = self._current_plant_data.source_id
                if plant_id:
                    library.update_plant(plant_id, self._current_plant_data)
            else:
                # API-sourced plant being modified - convert to custom
                self._current_plant_data.data_source = "custom"
                plant_id = library.add_plant(self._current_plant_data)
                self._current_plant_data.source_id = plant_id

            # Save updated data to item metadata
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

    def _on_instance_field_changed(self) -> None:
        """Handle variety field change."""
        if not self._current_plant_item:
            return
        variety = self.variety_edit.text().strip() or None
        self._update_instance_metadata("variety_cultivar", variety)

    def _on_planting_date_changed(self) -> None:
        """Handle planting date change."""
        if not self._current_plant_item:
            return
        d = self.planting_date_edit.date()
        # Save the selected date
        value = d.toPyDate().isoformat()
        self._update_instance_metadata("planting_date", value)
        # Update age display
        self._update_age_label(d.toPyDate())

    def _update_age_label(self, planting_date: date | None) -> None:
        """Update the age label based on planting date.

        Args:
            planting_date: The planting date to calculate age from
        """
        if not planting_date:
            self.age_label.setText("")
            return

        today = date.today()
        if planting_date > today:
            self.age_label.setText(self.tr("(future)"))
            return

        # Calculate age
        delta = today - planting_date
        days = delta.days

        if days < 30:
            self.age_label.setText(self.tr("({days} days)").format(days=days))
        elif days < 365:
            months = days // 30
            self.age_label.setText(self.tr("({months} mo)").format(months=months))
        else:
            years = days // 365
            remaining_months = (days % 365) // 30
            if remaining_months > 0:
                self.age_label.setText(self.tr("({years}y {remaining_months}mo)").format(years=years, remaining_months=remaining_months))
            else:
                self.age_label.setText(self.tr("({years}y)").format(years=years))

    def _on_current_height_changed(self) -> None:
        """Handle current height change."""
        if not self._current_plant_item:
            return
        val = self.current_height_spin.value()
        self._update_instance_metadata("current_height_cm", val if val > 0 else None)

    def _on_current_spread_changed(self) -> None:
        """Handle current spread change."""
        if not self._current_plant_item:
            return
        val = self.current_spread_spin.value()
        self._update_instance_metadata("current_spread_cm", val if val > 0 else None)

    def _on_notes_changed(self) -> None:
        """Handle notes change."""
        if not self._current_plant_item:
            return
        self._update_instance_metadata("notes", self.notes_edit.toPlainText() or None)

    def _on_add_custom_field(self) -> None:
        """Add a new custom field."""
        if not self._current_plant_item:
            return

        # Create a new custom field row
        self._add_custom_field_row("", "")

    def _add_custom_field_row(self, key: str, value: str) -> QWidget:
        """Add a custom field row widget.

        Args:
            key: Field name
            value: Field value

        Returns:
            The created row widget
        """
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        # Key input
        key_edit = QLineEdit()
        key_edit.setPlaceholderText(self.tr("Field name"))
        key_edit.setText(key)
        key_edit.setMaximumWidth(100)
        key_edit.editingFinished.connect(lambda: self._on_custom_field_changed())
        row_layout.addWidget(key_edit)

        # Value input
        value_edit = QLineEdit()
        value_edit.setPlaceholderText(self.tr("Value"))
        value_edit.setText(value)
        value_edit.editingFinished.connect(lambda: self._on_custom_field_changed())
        row_layout.addWidget(value_edit, 1)

        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedWidth(24)
        remove_btn.setToolTip(self.tr("Remove this field"))
        remove_btn.clicked.connect(lambda: self._on_remove_custom_field(row_widget))
        row_layout.addWidget(remove_btn)

        # Store references for later retrieval
        row_widget.key_edit = key_edit
        row_widget.value_edit = value_edit

        # Insert before the "Add Field" button
        insert_index = self.custom_fields_layout.count() - 1
        self.custom_fields_layout.insertWidget(insert_index, row_widget)

        return row_widget

    def _on_remove_custom_field(self, row_widget: QWidget) -> None:
        """Remove a custom field row.

        Args:
            row_widget: The row widget to remove
        """
        self.custom_fields_layout.removeWidget(row_widget)
        row_widget.deleteLater()
        self._on_custom_field_changed()

    def _on_custom_field_changed(self) -> None:
        """Handle custom field changes - update metadata."""
        if not self._current_plant_item:
            return

        # Collect all custom fields
        custom_fields = {}
        for i in range(self.custom_fields_layout.count() - 1):  # -1 to skip Add button
            item = self.custom_fields_layout.itemAt(i)
            if item and item.widget():
                row_widget = item.widget()
                if hasattr(row_widget, "key_edit") and hasattr(row_widget, "value_edit"):
                    key = row_widget.key_edit.text().strip()
                    value = row_widget.value_edit.text().strip()
                    if key:  # Only save if key is not empty
                        custom_fields[key] = value

        self._update_instance_metadata("custom_fields", custom_fields if custom_fields else None)

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
        self.no_selection_label.setText(self.tr("Select a plant to view details"))
        self.no_selection_label.setVisible(True)

        # Hide all form widgets
        for i in range(self.details_form.rowCount()):
            label_item = self.details_form.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.details_form.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(False)
            if field_item:
                # Could be a widget or a layout
                if field_item.widget():
                    field_item.widget().setVisible(False)
                elif field_item.layout():
                    # Hide all widgets in the layout (e.g., hardiness min/max)
                    layout = field_item.layout()
                    for j in range(layout.count()):
                        widget = layout.itemAt(j).widget()
                        if widget:
                            widget.setVisible(False)

        # Clear the info tooltip
        parent_widget = self.parent()
        while parent_widget:
            if hasattr(parent_widget, "set_info_tooltip"):
                parent_widget.set_info_tooltip("")
                break
            parent_widget = parent_widget.parent()

    def _show_no_metadata(self) -> None:
        """Show message that selected plant has no metadata."""
        # Keep the plant item reference so Create Custom can use it
        # self._current_plant_item is set by set_selected_items
        self._current_plant_data = None
        self.no_selection_label.setText(
            self.tr(
                "No species data.\n\n"
                "Click 'Search' to find species online,\n"
                "or 'Create Custom' to define your own."
            )
        )
        self.no_selection_label.setVisible(True)

        # Hide all form widgets
        for i in range(self.details_form.rowCount()):
            label_item = self.details_form.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.details_form.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(False)
            if field_item:
                # Could be a widget or a layout
                if field_item.widget():
                    field_item.widget().setVisible(False)
                elif field_item.layout():
                    # Hide all widgets in the layout (e.g., hardiness min/max)
                    layout = field_item.layout()
                    for j in range(layout.count()):
                        widget = layout.itemAt(j).widget()
                        if widget:
                            widget.setVisible(False)

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
            if field_item:
                # Could be a widget or a layout
                if field_item.widget():
                    field_item.widget().setVisible(True)
                elif field_item.layout():
                    # Show all widgets in the layout (e.g., hardiness min/max)
                    layout = field_item.layout()
                    for j in range(layout.count()):
                        widget = layout.itemAt(j).widget()
                        if widget:
                            widget.setVisible(True)

        # Scroll to top to show basic identity fields
        # Find the scroll area parent
        scroll_parent = self.info_widget.parent()
        if scroll_parent and hasattr(scroll_parent, 'ensureVisible'):
            scroll_parent.ensureVisible(0, 0)

        # === BASIC IDENTITY ===

        self.common_edit.setText(plant_data.common_name or "")
        self.scientific_edit.setText(plant_data.scientific_name or "")
        self.family_edit.setText(plant_data.family or "")

        # === PLANT CHARACTERISTICS ===

        # Cycle - set combo box selection (block signals to avoid triggering changes)
        self.cycle_combo.blockSignals(True)
        cycle_index = self.cycle_combo.findData(plant_data.cycle.value)
        if cycle_index >= 0:
            self.cycle_combo.setCurrentIndex(cycle_index)
        else:
            # If unknown or not found, default to first item
            self.cycle_combo.setCurrentIndex(0)
        self.cycle_combo.blockSignals(False)

        # === REPRODUCTIVE CHARACTERISTICS ===

        # Flower Type
        self.flower_type_combo.blockSignals(True)
        flower_type_index = self.flower_type_combo.findData(plant_data.flower_type.value)
        if flower_type_index >= 0:
            self.flower_type_combo.setCurrentIndex(flower_type_index)
        else:
            self.flower_type_combo.setCurrentIndex(0)
        self.flower_type_combo.blockSignals(False)

        # Pollination Type
        self.pollination_combo.blockSignals(True)
        pollination_index = self.pollination_combo.findData(plant_data.pollination_type.value)
        if pollination_index >= 0:
            self.pollination_combo.setCurrentIndex(pollination_index)
        else:
            self.pollination_combo.setCurrentIndex(0)
        self.pollination_combo.blockSignals(False)

        # === CARE REQUIREMENTS ===

        # Sun
        self.sun_combo.blockSignals(True)
        sun_index = self.sun_combo.findData(plant_data.sun_requirement.value)
        if sun_index >= 0:
            self.sun_combo.setCurrentIndex(sun_index)
        else:
            # If unknown or not found, default to first item
            self.sun_combo.setCurrentIndex(0)
        self.sun_combo.blockSignals(False)

        # Water
        self.water_combo.blockSignals(True)
        water_index = self.water_combo.findData(plant_data.water_needs.value)
        if water_index >= 0:
            self.water_combo.setCurrentIndex(water_index)
        else:
            # If unknown or not found, default to first item
            self.water_combo.setCurrentIndex(0)
        self.water_combo.blockSignals(False)

        # === GROWTH INFORMATION ===

        # Max Height
        self.max_height_spin.blockSignals(True)
        self.max_height_spin.setValue(plant_data.max_height_cm or 0)
        self.max_height_spin.blockSignals(False)

        # Max Spread
        self.max_spread_spin.blockSignals(True)
        self.max_spread_spin.setValue(plant_data.max_spread_cm or 0)
        self.max_spread_spin.blockSignals(False)

        # === EDIBILITY ===

        # Edible checkbox
        self.edible_checkbox.blockSignals(True)
        self.edible_checkbox.setChecked(plant_data.edible)
        self.edible_checkbox.blockSignals(False)

        # Edible parts
        if plant_data.edible_parts:
            parts_text = ", ".join(plant_data.edible_parts)
            self.edible_parts_edit.setText(parts_text)
        else:
            self.edible_parts_edit.setText("")

        # === HARDINESS ===

        # Hardiness zones
        self.hardiness_min_spin.blockSignals(True)
        self.hardiness_min_spin.setValue(plant_data.hardiness_zone_min or 0)
        self.hardiness_min_spin.blockSignals(False)

        self.hardiness_max_spin.blockSignals(True)
        self.hardiness_max_spin.setValue(plant_data.hardiness_zone_max or 0)
        self.hardiness_max_spin.blockSignals(False)

        # === PLANT INSTANCE FIELDS ===

        # Get instance data from item metadata
        instance_data = {}
        if hasattr(plant_item, "metadata") and plant_item.metadata:
            instance_data = plant_item.metadata.get("plant_instance", {})

        # Variety
        self.variety_edit.setText(instance_data.get("variety_cultivar") or "")

        # Planting date
        planting_date_str = instance_data.get("planting_date")
        planting_date_val = None
        self.planting_date_edit.blockSignals(True)
        if planting_date_str:
            try:
                planting_date_val = date.fromisoformat(planting_date_str)
                self.planting_date_edit.setDate(QDate(planting_date_val))
            except (ValueError, TypeError):
                # If invalid date, default to today
                self.planting_date_edit.setDate(QDate.currentDate())
        else:
            # No date saved - default to today
            self.planting_date_edit.setDate(QDate.currentDate())
        self.planting_date_edit.blockSignals(False)

        # Update age label
        self._update_age_label(planting_date_val)

        # Current height
        current_height = instance_data.get("current_height_cm")
        self.current_height_spin.blockSignals(True)
        self.current_height_spin.setValue(float(current_height) if current_height else 0)
        self.current_height_spin.blockSignals(False)

        # Current spread
        current_spread = instance_data.get("current_spread_cm")
        self.current_spread_spin.blockSignals(True)
        self.current_spread_spin.setValue(float(current_spread) if current_spread else 0)
        self.current_spread_spin.blockSignals(False)

        # Notes
        self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText(instance_data.get("notes") or "")
        self.notes_edit.blockSignals(False)

        # === CUSTOM FIELDS ===

        # Clear existing custom field rows
        while self.custom_fields_layout.count() > 1:  # Keep the Add button
            item = self.custom_fields_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # Load custom fields from instance data
        custom_fields = instance_data.get("custom_fields", {})
        if custom_fields:
            for key, value in custom_fields.items():
                self._add_custom_field_row(key, str(value) if value else "")

        # === SOURCE INFO ===
        # Set source info as tooltip on the panel header (via parent)
        source_text = self.tr("Data Source: {source}").format(source=plant_data.data_source.title())
        if plant_data.source_id:
            source_text += f" (ID: {plant_data.source_id})"

        # Find the CollapsiblePanel parent and set the info tooltip
        parent_widget = self.parent()
        while parent_widget:
            if hasattr(parent_widget, "set_info_tooltip"):
                parent_widget.set_info_tooltip(source_text)
                break
            parent_widget = parent_widget.parent()

    def _on_load_custom_plant(self) -> None:
        """Handle Load Custom Plant button click."""
        # Check if we have a selected plant item
        if not self._current_plant_item:
            QMessageBox.information(
                self,
                self.tr("No Plant Selected"),
                self.tr("Please select a plant object (tree, shrub, or perennial) first."),
            )
            return

        # Get custom plants from library
        library = get_plant_library()
        plants = library.get_all_plants()

        if not plants:
            QMessageBox.information(
                self,
                self.tr("No Custom Plants"),
                self.tr(
                    "Your custom plant library is empty.\n\n"
                    "Use 'Create Custom' to add plants, or use the Plants menu "
                    "to manage your custom plant library."
                ),
            )
            return

        # Show selection dialog
        from open_garden_planner.ui.dialogs.custom_plants_dialog import CustomPlantsDialog

        dialog = CustomPlantsDialog(self)
        dialog.setWindowTitle(self.tr("Select Custom Plant"))
        if dialog.exec() and dialog.selected_plant:
            # Assign selected plant to the item
            plant_item = self._current_plant_item
            if not hasattr(plant_item, "metadata") or plant_item.metadata is None:
                plant_item.metadata = {}
            plant_item.metadata["plant_species"] = dialog.selected_plant.to_dict()

            # Show the plant data for editing
            self._show_plant_data(dialog.selected_plant, plant_item)

            # Mark project as dirty
            scene = plant_item.scene()
            if scene and hasattr(scene, "views"):
                for view in scene.views():
                    if hasattr(view, "window"):
                        window = view.window()
                        if hasattr(window, "_project_manager"):
                            window._project_manager.mark_dirty()
                            break

    def _on_create_custom_plant(self) -> None:
        """Handle Create Custom Plant button click."""
        # Check if we have a selected plant item
        if not self._current_plant_item:
            QMessageBox.information(
                self,
                self.tr("No Plant Selected"),
                self.tr("Please select a plant object (tree, shrub, or perennial) first."),
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
