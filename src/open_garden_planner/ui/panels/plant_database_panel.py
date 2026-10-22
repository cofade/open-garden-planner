"""Plant database panel for displaying plant species metadata."""

import contextlib
from collections.abc import Callable
from datetime import date
from typing import cast

from PyQt6.QtCore import QDate, QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QShowEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE
from open_garden_planner.models.plant_data import (
    FlowerType,
    PermacultureLayer,
    PlantCycle,
    PlantFunction,
    PlantSpeciesData,
    PollinationType,
    SunRequirement,
    WaterNeeds,
)
from open_garden_planner.services import get_plant_library
from open_garden_planner.services.bundled_species_db import merge_calendar_data
from open_garden_planner.ui.canvas.items.garden_item import note_plan_changed
from open_garden_planner.ui.plant_species_assignment import (
    apply_species_to_item,
    confirm_apply_database_values,
    plant_source_label,
)
from open_garden_planner.ui.theme import set_text_role, theme_color


def _qt_date(day: date) -> QDate:
    return QDate(day.year, day.month, day.day)


class _PlanCalendar(QCalendarWidget):
    """Bound new calendar choices while the editor can display legacy dates."""

    def showEvent(self, event: QShowEvent | None) -> None:
        with QSignalBlocker(self):
            self.setDateRange(_qt_date(MIN_PLAN_DATE), _qt_date(MAX_PLAN_DATE))
        super().showEvent(event)


class ClickableDateEdit(QDateEdit):
    """A QDateEdit with a visible dropdown arrow for calendar popup.

    Uses the standard Qt approach with a dropdown button to open the calendar.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the date edit."""
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setCalendarWidget(_PlanCalendar(self))
        self.setDateRange(_qt_date(MIN_PLAN_DATE), _qt_date(MAX_PLAN_DATE))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Make the line edit read-only
        line_edit = self.lineEdit()
        line_edit.setReadOnly(True)
        line_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Set cursor to indicate clickability
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Initialize to today's date
        self.setDate(QDate.currentDate())

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        # These are calendar selectors. Wheel gestures belong to the details
        # panel's scroll area, even when a date was the last focused control.
        if event is not None:
            event.ignore()

    def set_stored_date(self, day: date | None) -> None:
        """Display old metadata faithfully; only new writes have clock bounds."""
        minimum = QDate(1, 1, 1) if self.specialValueText() else _qt_date(MIN_PLAN_DATE)
        maximum = _qt_date(MAX_PLAN_DATE)
        selected = _qt_date(day) if day is not None else (
            minimum if self.specialValueText() else QDate.currentDate())
        self.setDateRange(min(minimum, selected), max(maximum, selected))
        self.setDate(selected)


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
        self._command_manager = None
        # True while applying model values to widgets or building a command:
        # widget signals fired here must not create a nested command.
        self._in_commit = False
        # True after an undo/redo (stack_changed): the next set_selected_items
        # must refresh even a focused editor (#560). Ordinary notifications
        # keep protecting uncommitted typing.
        self._history_pending = False
        # Debounced notes commit: textChanged fires per keystroke, but undo
        # carries one committed edit (#559). The timer coalesces a typing run.
        self._pending_notes_value: str | None = None
        self._notes_has_pending = False
        # Coalescing handle (#559): consecutive valueChanged ticks of one spin
        # drag merge into this pending command instead of one undo entry per
        # tick. Cleared on selection change, history, or a non-spin commit.
        self._last_spin_cmd = None
        from PyQt6.QtCore import QTimer as _QTimer

        self._notes_timer = _QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.setInterval(800)
        self._notes_timer.timeout.connect(self._flush_pending_notes)

        from open_garden_planner.models.plant_lists import get_plant_list_store  # noqa: PLC0415
        self._list_store = get_plant_list_store()
        self._list_store.changed.connect(self._update_favorite_button)

        self._setup_ui()

    def set_command_manager(self, command_manager) -> None:
        """Attach the shared undo stack; previous stack signals are detached."""
        try:
            if self._command_manager is not None:
                with contextlib.suppress(Exception):
                    self._command_manager.history_navigated.disconnect(
                        self._on_history_changed
                    )
        except Exception:
            pass
        self._command_manager = command_manager
        if command_manager is not None:
            with contextlib.suppress(Exception):
                command_manager.history_navigated.connect(self._on_history_changed)

    def _on_history_changed(self) -> None:
        """Mark the next refresh as history-driven (#560).

        Connected to ``history_navigated`` (undo/redo only), never to the
        every-commit ``stack_changed`` — an own commit must not masquerade as
        a history transition and clobber the focused editor.
        """
        self._history_pending = True
        self._last_spin_cmd = None

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(8)

        # === PROFILE HEADER (US-G2, issue #317) ===
        self._profile_header = QWidget()
        profile_layout = QHBoxLayout(self._profile_header)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setSpacing(8)

        # Thumbnail
        self._profile_thumbnail = QLabel()
        self._profile_thumbnail.setFixedSize(96, 96)
        self._profile_thumbnail.setStyleSheet(
            f"background-color: {theme_color('surface_alt')};"
            f" border: 1px solid {theme_color('border')};"
            " border-radius: 4px;"
        )
        self._profile_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_layout.addWidget(self._profile_thumbnail)

        # Text content
        profile_text = QVBoxLayout()
        profile_text.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(4)
        name_row.setContentsMargins(0, 0, 0, 0)

        self._profile_name = QLabel()
        self._profile_name.setWordWrap(True)
        self._profile_name.setStyleSheet("font-weight: bold; font-size: 14px;")
        name_row.addWidget(self._profile_name, 1)

        self._favorite_btn = QToolButton()
        self._favorite_btn.setText("☆")
        self._favorite_btn.setToolTip(self.tr("Add to Favorites"))
        self._favorite_btn.setStyleSheet(
            "font-size: 16px; border: none; background: transparent; padding: 2px;"
        )
        self._favorite_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._favorite_btn.clicked.connect(self._on_toggle_favorite)
        name_row.addWidget(self._favorite_btn)

        profile_text.addLayout(name_row)

        self._profile_scientific = QLabel()
        self._profile_scientific.setWordWrap(True)
        set_text_role(self._profile_scientific, "hint")
        profile_text.addWidget(self._profile_scientific)

        self._profile_description = QLabel()
        self._profile_description.setWordWrap(True)
        set_text_role(self._profile_description, "secondary")
        profile_text.addWidget(self._profile_description)

        self._profile_source = QLabel()
        self._profile_source.setWordWrap(True)
        set_text_role(self._profile_source, "hint")
        profile_text.addWidget(self._profile_source)

        # Links row
        self._profile_links = QLabel()
        self._profile_links.setWordWrap(True)
        set_text_role(self._profile_links, "hint")
        self._profile_links.setOpenExternalLinks(True)
        profile_text.addWidget(self._profile_links)

        profile_text.addStretch()
        profile_layout.addLayout(profile_text)
        layout.addWidget(self._profile_header)

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
        self.no_selection_label.setProperty("secondary", True)
        self.no_selection_label.setStyleSheet("font-style: italic;")
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
        from open_garden_planner.ui.widgets.trait_filters import trait_label

        self._trait_refreshers: list[tuple[QWidget, Callable[[PlantSpeciesData], None]]] = []
        self.layer_combo = QComboBox()
        for layer in (PermacultureLayer.UNKNOWN, *[v for v in PermacultureLayer if v != PermacultureLayer.UNKNOWN]):
            self.layer_combo.addItem(trait_label(layer.value), layer.value)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        self.details_form.addRow(self.tr("Food-forest layer:"), self.layer_combo)
        self.functions_list = QListWidget()
        self.functions_list.setMaximumHeight(130)
        for function in PlantFunction:
            row = QListWidgetItem(trait_label(function.value))
            row.setData(Qt.ItemDataRole.UserRole, function.value)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Unchecked)
            self.functions_list.addItem(row)
        self.functions_list.itemChanged.connect(self._on_functions_changed)
        self.details_form.addRow(self.tr("Recorded functions:"), self.functions_list)
        self._register_refresh(self.layer_combo, self._refresh_layer)
        self._register_refresh(self.functions_list, self._refresh_functions)
        self.guild_label = QLabel()
        self.guild_label.setWordWrap(True)
        self.details_form.addRow(self.tr("Guild:"), self.guild_label)

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
        cycle_labels = {
            PlantCycle.ANNUAL: self.tr("Annual"),
            PlantCycle.BIENNIAL: self.tr("Biennial"),
            PlantCycle.PERENNIAL: self.tr("Perennial"),
        }
        # Leading neutral entry so a species with no cycle data shows "—" rather
        # than being misrepresented as the first concrete option (#231).
        self.cycle_combo.addItem(self.tr("—"), PlantCycle.UNKNOWN.value)
        for item in PlantCycle:
            if item != PlantCycle.UNKNOWN:
                self.cycle_combo.addItem(cycle_labels.get(item, item.value), item.value)
        self.cycle_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cycle_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Cycle:"), self.cycle_combo)

        # === REPRODUCTIVE CHARACTERISTICS ===

        # Flower Type (sexual system)
        self.flower_type_combo = QComboBox()
        flower_type_labels = {
            FlowerType.HERMAPHRODITE: self.tr("Hermaphrodite (perfect flowers)"),
            FlowerType.MONOECIOUS: self.tr("Monoecious (separate \u2642/\u2640 flowers)"),
            FlowerType.DIOECIOUS_MALE: self.tr("Dioecious Male (\u2642 only)"),
            FlowerType.DIOECIOUS_FEMALE: self.tr("Dioecious Female (\u2640 only)"),
        }
        self.flower_type_combo.addItem(self.tr("—"), FlowerType.UNKNOWN.value)
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
            PollinationType.SELF_FERTILE: self.tr("Self-fertile (no partner needed)"),
            PollinationType.PARTIALLY_SELF_FERTILE: self.tr("Partially self-fertile"),
            PollinationType.SELF_STERILE: self.tr("Self-sterile (needs partner)"),
            PollinationType.TRIPLOID: self.tr("Triploid (sterile pollen)"),
        }
        self.pollination_combo.addItem(self.tr("—"), PollinationType.UNKNOWN.value)
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
        sun_labels = {
            SunRequirement.FULL_SUN: self.tr("Full Sun"),
            SunRequirement.PARTIAL_SUN: self.tr("Partial Sun"),
            SunRequirement.PARTIAL_SHADE: self.tr("Partial Shade"),
            SunRequirement.FULL_SHADE: self.tr("Full Shade"),
        }
        self.sun_combo.addItem(self.tr("—"), SunRequirement.UNKNOWN.value)
        for item in SunRequirement:
            if item != SunRequirement.UNKNOWN:
                self.sun_combo.addItem(sun_labels.get(item, item.value), item.value)
        self.sun_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sun_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Sun:"), self.sun_combo)

        # Water needs
        self.water_combo = QComboBox()
        water_labels = {
            WaterNeeds.LOW: self.tr("Low"),
            WaterNeeds.MEDIUM: self.tr("Medium"),
            WaterNeeds.HIGH: self.tr("High"),
        }
        self.water_combo.addItem(self.tr("—"), WaterNeeds.UNKNOWN.value)
        for item in WaterNeeds:
            if item != WaterNeeds.UNKNOWN:
                self.water_combo.addItem(water_labels.get(item, item.value), item.value)
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
        # A non-empty special-value text is required to engage Qt's placeholder:
        # the minimum (0) is the "unset" sentinel, shown as "—" not "0 cm" (#231).
        self.max_height_spin.setSpecialValueText(self.tr("—"))
        self.max_height_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.max_height_spin.valueChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Max Height:"), self.max_height_spin)

        # Max Spread
        self.max_spread_spin = QDoubleSpinBox()
        self.max_spread_spin.setRange(0, 10000)
        self.max_spread_spin.setSingleStep(10)
        self.max_spread_spin.setDecimals(0)
        self.max_spread_spin.setSuffix(" cm")
        self.max_spread_spin.setSpecialValueText(self.tr("—"))  # — when unset (#231)
        self.max_spread_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.max_spread_spin.valueChanged.connect(self._on_field_changed)
        self.details_form.addRow(self.tr("Max Spread:"), self.max_spread_spin)

        # Current Height (instance-specific)
        self.current_height_spin = QDoubleSpinBox()
        self.current_height_spin.setRange(0, 10000)
        self.current_height_spin.setSingleStep(10)
        self.current_height_spin.setDecimals(0)
        self.current_height_spin.setSuffix(" cm")
        self.current_height_spin.setSpecialValueText(self.tr("—"))  # — when unset (#231)
        self.current_height_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.current_height_spin.valueChanged.connect(self._on_current_height_changed)
        self.details_form.addRow(self.tr("Current Height:"), self.current_height_spin)

        # Current Spread (instance-specific)
        self.current_spread_spin = QDoubleSpinBox()
        self.current_spread_spin.setRange(0, 10000)
        self.current_spread_spin.setSingleStep(10)
        self.current_spread_spin.setDecimals(0)
        self.current_spread_spin.setSuffix(" cm")
        self.current_spread_spin.setSpecialValueText(self.tr("—"))  # — when unset (#231)
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
        self.hardiness_min_spin.setSpecialValueText(self.tr("—"))  # — when unset (#231)
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
        self.hardiness_max_spin.setSpecialValueText(self.tr("—"))  # — when unset (#231)
        self.hardiness_max_spin.setMinimumWidth(60)  # Ensure arrows are visible
        self.hardiness_max_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.hardiness_max_spin.valueChanged.connect(self._on_field_changed)
        hardiness_layout.addWidget(self.hardiness_max_spin, 1)  # stretch factor 1

        self.details_form.addRow(self.tr("Hardiness:"), hardiness_layout)

        # === SOIL REQUIREMENTS (US-12.10d) ===
        # pH window — used by SoilService.get_mismatched_plants to decide whether
        # the bed's soil pH is acceptable for this plant. Empty (0.0) = unknown.

        ph_layout = QHBoxLayout()
        ph_layout.setSpacing(4)
        ph_layout.addWidget(QLabel(self.tr("Min:")))
        self.ph_min_spin = QDoubleSpinBox()
        self.ph_min_spin.setRange(0.0, 14.0)
        self.ph_min_spin.setSingleStep(0.1)
        self.ph_min_spin.setDecimals(1)
        self.ph_min_spin.setSpecialValueText(self.tr("—"))  # — when 0.0 (= unknown) (#231)
        self.ph_min_spin.setMinimumWidth(60)
        self.ph_min_spin.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.ph_min_spin.valueChanged.connect(self._on_field_changed)
        ph_layout.addWidget(self.ph_min_spin, 1)

        ph_layout.addWidget(QLabel(self.tr("Max:")))
        self.ph_max_spin = QDoubleSpinBox()
        self.ph_max_spin.setRange(0.0, 14.0)
        self.ph_max_spin.setSingleStep(0.1)
        self.ph_max_spin.setDecimals(1)
        self.ph_max_spin.setSpecialValueText(self.tr("—"))  # — when unset (#231)
        self.ph_max_spin.setMinimumWidth(60)
        self.ph_max_spin.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.ph_max_spin.valueChanged.connect(self._on_field_changed)
        ph_layout.addWidget(self.ph_max_spin, 1)

        self.details_form.addRow(self.tr("pH range:"), ph_layout)

        # Per-nutrient demand (US-12.10d). Each combo's userData carries the
        # canonical string ("high"/"medium"/"low"/"fixer") or None for unknown.
        self.n_demand_combo = self._make_demand_combo()
        self.details_form.addRow(self.tr("N demand:"), self.n_demand_combo)
        self.p_demand_combo = self._make_demand_combo()
        self.details_form.addRow(self.tr("P demand:"), self.p_demand_combo)
        self.k_demand_combo = self._make_demand_combo()
        self.details_form.addRow(self.tr("K demand:"), self.k_demand_combo)

        # Legacy combined demand (US-10.5) — kept for crop rotation. When the
        # individual N/P/K demands are unset, get_mismatched_plants falls back
        # to this value via _effective_demand("heavy"→all-high, etc.).
        self.nutrient_demand_combo = QComboBox()
        for label_key, value in (
            (self.tr("—"), None),
            (self.tr("Heavy feeder"), "heavy"),
            (self.tr("Medium feeder"), "medium"),
            (self.tr("Light feeder"), "light"),
            (self.tr("Fixer (legume)"), "fixer"),
        ):
            self.nutrient_demand_combo.addItem(label_key, value)
        self.nutrient_demand_combo.currentIndexChanged.connect(self._on_field_changed)
        self.details_form.addRow(
            self.tr("Overall demand:"), self.nutrient_demand_combo
        )

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
        self.age_label.setProperty("secondary", True)
        self.age_label.setStyleSheet("font-style: italic;")
        planting_layout.addWidget(self.age_label)

        self.details_form.addRow(self.tr("Planted:"), planting_layout)

        removal_layout = QHBoxLayout()
        self.removal_date_edit = ClickableDateEdit()
        self.removal_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.removal_date_edit.setSpecialValueText(self.tr("Not removed"))
        self.removal_date_edit.set_stored_date(None)
        self.removal_date_edit.dateChanged.connect(self._on_removal_date_changed)
        removal_layout.addWidget(self.removal_date_edit, 1)
        self.clear_removal_button = QToolButton()
        self.clear_removal_button.setText(self.tr("Clear"))
        self.clear_removal_button.clicked.connect(
            lambda: self.removal_date_edit.setDate(self.removal_date_edit.minimumDate()))
        removal_layout.addWidget(self.clear_removal_button)
        self.details_form.addRow(self.tr("Removed on:"), removal_layout)

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

        # === SEED PACKET LINK (US-9.6) ===
        seed_link_widget = QWidget()
        seed_link_vbox = QVBoxLayout(seed_link_widget)
        seed_link_vbox.setContentsMargins(0, 0, 0, 0)
        seed_link_vbox.setSpacing(2)

        self.seed_packet_combo = QComboBox()
        self.seed_packet_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.seed_packet_combo.currentIndexChanged.connect(self._on_seed_packet_changed)
        seed_link_vbox.addWidget(self.seed_packet_combo)

        self.seed_packet_info_lbl = QLabel()
        self.seed_packet_info_lbl.setWordWrap(True)
        self.seed_packet_info_lbl.setStyleSheet("font-size: 8pt;")
        seed_link_vbox.addWidget(self.seed_packet_info_lbl)

        self.details_form.addRow(self.tr("Seed Packet:"), seed_link_widget)

    def _make_demand_combo(self) -> QComboBox:
        """Build a NPK-demand combobox (US-12.10d)."""
        combo = QComboBox()
        for label, value in (
            (self.tr("—"), None),
            (self.tr("High"), "high"),
            (self.tr("Medium"), "medium"),
            (self.tr("Low"), "low"),
            (self.tr("Fixer"), "fixer"),
        ):
            combo.addItem(label, value)
        combo.currentIndexChanged.connect(self._on_field_changed)
        return combo

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: object) -> None:
        """Select the combo entry whose userData matches ``value`` (None-safe)."""
        combo.blockSignals(True)
        for idx in range(combo.count()):
            if combo.itemData(idx) == value:
                combo.setCurrentIndex(idx)
                break
        else:
            combo.setCurrentIndex(0)  # Fall back to "—"
        combo.blockSignals(False)

    def _is_spin_gesture(self) -> bool:
        """True when the current commit comes from a spinbox tick (#559)."""
        try:
            from PyQt6.QtWidgets import QAbstractSpinBox as _Spin

            sender = self.sender()
            return isinstance(sender, _Spin)
        except Exception:
            return False

    def _push_or_merge_species_cmd(self, cmd) -> bool:
        """Execute ``cmd`` or merge it into a pending spin gesture.

        Returns True when merged (no new history entry).
        """
        mgr = self._command_manager
        if mgr is None:
            cmd.execute()
            return False
        cmd._cmd_kind = "species"
        pending = self._last_spin_cmd
        if (
            self._is_spin_gesture()
            and pending is not None
            and getattr(pending, "_cmd_kind", None) == "species"
            and mgr.peek_undo() is pending
            and getattr(pending, "_item", None) is cmd._item
        ):
            pending._new_species = cmd._new_species
            pending._new_radius = cmd._new_radius
            pending._new_spacing_override = cmd._new_spacing_override
            pending._apply(
                pending._new_species,
                pending._new_radius,
                pending._new_spacing_override,
            )
            note_plan_changed(cmd._item.scene())
            return True
        mgr.execute(cmd)
        from PyQt6.QtWidgets import QAbstractSpinBox as _Spin  # noqa: PLC0415

        self._last_spin_cmd = cmd if isinstance(self.sender(), _Spin) else None
        return False

    def _push_or_merge_instance_cmd(self, cmd) -> bool:
        """Execute ``cmd`` or merge it into a pending spin gesture."""
        mgr = self._command_manager
        if mgr is None:
            cmd.execute()
            return False
        cmd._cmd_kind = "instance"
        pending = self._last_spin_cmd
        if (
            self._is_spin_gesture()
            and pending is not None
            and getattr(pending, "_cmd_kind", None) == "instance"
            and mgr.peek_undo() is pending
            and getattr(pending, "_item", None) is cmd._item
        ):
            pending._new_instance = cmd._new_instance
            pending._apply(pending._new_instance)
            note_plan_changed(cmd._item.scene())
            return True
        mgr.execute(cmd)
        from PyQt6.QtWidgets import QAbstractSpinBox as _Spin  # noqa: PLC0415

        self._last_spin_cmd = cmd if isinstance(self.sender(), _Spin) else None
        return False

    def _on_field_changed(self) -> None:
        """Handle field value changes - one committed edit, one undo step (#559)."""
        if not self._current_plant_item or not self._current_plant_data:
            return
        if self._in_commit:
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

        # Soil requirements (US-12.10d)
        ph_min_val = self.ph_min_spin.value()
        self._current_plant_data.ph_min = ph_min_val if ph_min_val > 0.0 else None
        ph_max_val = self.ph_max_spin.value()
        self._current_plant_data.ph_max = ph_max_val if ph_max_val > 0.0 else None
        self._current_plant_data.n_demand = self.n_demand_combo.currentData()
        self._current_plant_data.p_demand = self.p_demand_combo.currentData()
        self._current_plant_data.k_demand = self.k_demand_combo.currentData()
        self._current_plant_data.nutrient_demand = (
            self.nutrient_demand_combo.currentData()
        )

        # Save back to item metadata and custom library. (metadata is a
        # read-only property backed by a dict that's always present, so there's
        # nothing to initialize — the old `metadata = {}` write here would have
        # raised AttributeError on an item with empty metadata.)
        if hasattr(self._current_plant_item, "metadata"):
            from open_garden_planner.core.commands import PlantSpeciesEditCommand

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
            # Library writes above are shared-library side effects and are
            # explicitly NOT part of undo (#559): undo restores the item's
            # metadata + footprint, never the library entry.

            # Save updated data to item metadata (merge local calendar DB data)
            # as ONE undoable command (#559), with footprint resize (#558).
            old_species = self._current_plant_item.metadata.get("plant_species")
            old_species = dict(old_species) if isinstance(old_species, dict) else None
            edited = self._current_plant_data.to_dict()
            new_species = merge_calendar_data(edited)
            # The bundled overlay must not silently discard what was just
            # edited: ``merge_calendar_data`` prioritises the bundled DB, and
            # ``family``/``nutrient_demand`` are both calendar fields AND form
            # fields. On this edit path the committed widget values win; the
            # overlay still fills every other calendar field (#559).
            for _key in ("family", "nutrient_demand"):
                new_species[_key] = edited.get(_key)
            if old_species is not None and old_species == new_species:
                # Check geometry-only change (max_spread edit that leaves the
                # dict equal cannot happen: max_spread is IN the dict).
                return
            old_radius, new_radius = self._species_resize_radii(
                self._current_plant_item, old_species, new_species
            )
            try:
                old_spacing = self._current_plant_item.spacing_radius_cm
            except Exception:
                old_spacing = None
            cmd = PlantSpeciesEditCommand(
                self._current_plant_item,
                old_species,
                new_species,
                old_radius=old_radius,
                new_radius=new_radius,
                old_spacing_override=old_spacing,
                new_spacing_override=old_spacing,
            )
            if self._command_manager is not None:
                self._push_or_merge_species_cmd(cmd)
            else:
                cmd.execute()

            # Repaint so the spacing circle reflects a live max_spread edit.
            if hasattr(self._current_plant_item, "prepareGeometryChange"):
                self._current_plant_item.prepareGeometryChange()
            if hasattr(self._current_plant_item, "update"):
                self._current_plant_item.update()
            # The 3D view follows the PLAN, not its repaints: the command moves
            # the plan revision via stack_changed; this nudge covers the
            # no-manager fallback and coalesces otherwise (ADR-060 decision 5).
            note_plan_changed(self._current_plant_item.scene())

            # Mark project as dirty + refresh soil-mismatch borders (US-12.10d)
            scene = self._current_plant_item.scene()
            if scene and hasattr(scene, "views"):
                for view in scene.views():
                    if hasattr(view, "window"):
                        window = view.window()
                        if hasattr(window, "_project_manager"):
                            window._project_manager.mark_dirty()
                    if hasattr(view, "refresh_soil_mismatches"):
                        view.refresh_soil_mismatches()

    def _species_resize_radii(
        self, item, old_species: dict | None, new_species: dict
    ) -> tuple[float | None, float | None]:
        """Compute (old_radius, new_radius) for a species-dict edit (#558).

        Precedence: an explicit spacing override, an explicit current/measured
        spread, or a custom footprint (drawn radius != old species size) wins
        and the edit resizes nothing. A cleared max_spread preserves geometry
        rather than collapsing it. Otherwise the footprint diameter follows
        max_spread_cm, preserving center + rotation pivot via
        set_radius_centered.

        When the old species has no max_spread there is no species size to
        conflict with, so the edit adopts the new size even if the drawn
        radius was hand-placed (undoable, and documented here rather than
        silently kept).
        """
        try:
            old_max = (old_species or {}).get("max_spread_cm")
            new_max = new_species.get("max_spread_cm")
        except Exception:
            return None, None
        if new_max == old_max:
            return None, None
        if new_max is None:
            return None, None
        try:
            new_max_f = float(new_max)
        except Exception:
            return None, None
        if not new_max_f > 0:
            return None, None
        try:
            if getattr(item, "spacing_radius_cm", None) is not None:
                return None, None
        except Exception:
            pass
        try:
            instance = getattr(item, "metadata", {}).get("plant_instance", {}) or {}
            if instance.get("current_spread_cm") is not None:
                return None, None
        except Exception:
            pass
        get_radius = getattr(item, "radius", None)
        current_r: float | None = None
        try:
            current_r = float(get_radius()) if callable(get_radius) else None
        except Exception:
            current_r = None
        if current_r is None:
            get_r = getattr(item, "_radius", None)
            try:
                current_r = float(get_r) if isinstance(get_r, (int, float)) else None
            except Exception:
                current_r = None
        if current_r is None or not hasattr(item, "set_radius_centered"):
            return None, None
        if old_max is not None:
            try:
                if abs(current_r - float(old_max) / 2.0) > 1.0:
                    return None, None
            except Exception:
                return None, None
        new_radius = new_max_f / 2.0
        if abs(new_radius - current_r) < 1e-6:
            return None, None
        return current_r, new_radius

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
        self._change_lifetime_date("planting_date", value)

    def _on_removal_date_changed(self) -> None:
        day = self.removal_date_edit.date()
        value = None if day == self.removal_date_edit.minimumDate() else day.toPyDate().isoformat()
        self._change_lifetime_date("removal_date", value)

    def _change_lifetime_date(self, field: str, value: str | None) -> None:
        if self._current_plant_item is None:
            return
        from open_garden_planner.ui.plant_lifetime import change_lifetime_date

        item = self._current_plant_item
        try:
            change_lifetime_date(item, field, value)
        except ValueError:
            QMessageBox.warning(self, self.tr("Invalid plant dates"),
                                self.tr("Choose dates between {min} and {max}. Removal must be after planting.").format(
                                    min=MIN_PLAN_DATE.isoformat(), max=MAX_PLAN_DATE.isoformat()))
        if self._current_plant_item is item:
            self._refresh_lifetime_dates(item)

    def _refresh_lifetime_dates(self, item: QGraphicsItem) -> None:
        from open_garden_planner.core.plan_timeline import instance_date

        removed = instance_date(getattr(item, "metadata", None), "removal_date")
        planted = instance_date(getattr(item, "metadata", None), "planting_date")
        self.planting_date_edit.blockSignals(True)
        self.planting_date_edit.set_stored_date(planted)
        self.planting_date_edit.blockSignals(False)
        self.removal_date_edit.blockSignals(True)
        self.removal_date_edit.set_stored_date(removed)
        self.removal_date_edit.blockSignals(False)
        self._update_age_label(planted)

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
        """Stage a notes edit; the debounce timer commits one undo step (#559)."""
        if not self._current_plant_item or self._in_commit:
            return
        try:
            self._pending_notes_value = self.notes_edit.toPlainText() or None
            self._notes_has_pending = True
            self._notes_timer.start()
        except Exception:
            pass

    def _flush_pending_notes(self) -> None:
        """Commit a staged notes edit as one undoable step, if changed."""
        with contextlib.suppress(Exception):
            self._notes_timer.stop()
        if not self._notes_has_pending:
            return
        self._notes_has_pending = False
        value = self._pending_notes_value
        self._pending_notes_value = None
        if not self._current_plant_item:
            return
        current = (self._current_plant_item.metadata.get("plant_instance", {}) or {}).get("notes")
        if value == current:
            return
        self._update_instance_metadata("notes", value)

    def _populate_seed_packet_combo(
        self, plant_data: PlantSpeciesData, instance_data: dict
    ) -> None:
        """Populate the seed packet combo box for the given plant."""
        from open_garden_planner.models.seed_inventory import get_seed_inventory

        self.seed_packet_combo.blockSignals(True)
        self.seed_packet_combo.clear()
        self.seed_packet_combo.addItem(self.tr("— No packet linked —"), None)

        store = get_seed_inventory()
        packets = store.all()
        species_lower = (plant_data.common_name or plant_data.scientific_name or "").lower()
        matching = [p for p in packets if species_lower and (
            species_lower in p.species_name.lower() or p.species_name.lower() in species_lower
        )]
        others = [p for p in packets if p not in matching]
        for p in matching + others:
            label = p.species_name
            if p.variety:
                label += f" ({p.variety})"
            label += f" [{p.purchase_year}]"
            self.seed_packet_combo.addItem(label, p.id)

        linked_id = instance_data.get("seed_packet_id")
        if linked_id:
            idx = self.seed_packet_combo.findData(linked_id)
            self.seed_packet_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.seed_packet_combo.setCurrentIndex(0)
        self.seed_packet_combo.blockSignals(False)

        packet = store.get(linked_id) if linked_id else None
        self._update_seed_packet_info(packet)

    def _on_seed_packet_changed(self) -> None:
        """Handle seed packet link change — save to plant instance metadata."""
        if not self._current_plant_item:
            return
        from open_garden_planner.models.seed_inventory import get_seed_inventory

        packet_id = self.seed_packet_combo.currentData()
        self._update_instance_metadata("seed_packet_id", packet_id)
        packet = get_seed_inventory().get(packet_id) if packet_id else None
        self._update_seed_packet_info(packet)

    def _update_seed_packet_info(self, packet) -> None:
        """Show germination info for the linked seed packet."""
        if packet is None:
            self.seed_packet_info_lbl.setText("")
            return
        parts = []
        if packet.germination_days_min is not None:
            days = str(packet.germination_days_min)
            if packet.germination_days_max and packet.germination_days_max != packet.germination_days_min:
                days += f"\u2013{packet.germination_days_max}"
            parts.append(self.tr("Germination: %1 days").replace("%1", days))
        if packet.germination_temp_opt_c is not None:
            parts.append(
                self.tr("Opt. temp: %1\u00b0C").replace("%1", str(int(packet.germination_temp_opt_c)))
            )
        if packet.cold_stratification:
            parts.append(self.tr("Cold stratification"))
        self.seed_packet_info_lbl.setText("  \u00b7  ".join(parts))

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
        """Update plant instance metadata as one undoable step (#559).

        Args:
            key: The metadata key to update
            value: The new value (None to remove)
        """
        if not self._current_plant_item:
            return
        if self._in_commit:
            return

        # metadata is a read-only property backed by a dict that always exists,
        # so there's nothing to initialize here.
        old_instance = self._current_plant_item.metadata.get("plant_instance", {}) or {}
        old_instance = dict(old_instance)
        new_instance = dict(old_instance)
        if value is None or value == "":
            new_instance.pop(key, None)
        else:
            new_instance[key] = value
        if new_instance == old_instance:
            return  # A no-op adds no history entry.

        from open_garden_planner.core.commands import PlantInstanceEditCommand

        cmd = PlantInstanceEditCommand(
            self._current_plant_item, old_instance, new_instance
        )
        if self._command_manager is not None:
            self._push_or_merge_instance_cmd(cmd)
        else:
            cmd.execute()

        # A metadata-only write repaints nothing, so QGraphicsScene.changed
        # never fires; the command moves the plan revision via stack_changed
        # (and this nudge covers the no-manager fallback). Derived overlays
        # subscribe to exactly those two, so without this the sun/shade shadow
        # keeps showing the OLD size after the user edits Current
        # height/spread (US-E8 reads both straight off this dict). See §11.4.
        self._current_plant_item.update()
        # … and what follows the PLAN rather than its repaints (the 3D view) is
        # told directly for the fallback path (ADR-060 decision 5).
        note_plan_changed(self._current_plant_item.scene())

        # Mark project as dirty
        scene = self._current_plant_item.scene()
        if scene and hasattr(scene, "views"):
            for view in scene.views():
                if hasattr(view, "window"):
                    window = view.window()
                    if hasattr(window, "_project_manager"):
                        window._project_manager.mark_dirty()
                        break

    def _register_refresh(self, widget: QWidget, refresher: Callable[[PlantSpeciesData], None]) -> None:
        self._trait_refreshers.append((widget, refresher))

    def _refresh_traits(self, data: PlantSpeciesData) -> None:
        for widget, refresher in self._trait_refreshers:
            previous = widget.blockSignals(True)
            try:
                refresher(data)
            finally:
                widget.blockSignals(previous)
        guild = getattr(self._current_plant_item, "metadata", {}).get("guild")
        if isinstance(guild, dict):
            from open_garden_planner.ui.widgets.trait_filters import trait_label

            role_value = guild.get("role")
            role = self.tr("Centre") if role_value == "centre" else trait_label(role_value) if isinstance(role_value, str) and role_value in {v.value for v in PlantFunction} else self.tr("Invalid role")
            name = guild.get("name") or guild.get("guild_id", "")
            scene = self._current_plant_item.scene() if self._current_plant_item is not None else None
            if scene is not None and guild.get("role") != "centre":
                from open_garden_planner.core.guild_commands import guild_members

                centre = next((plant for plant in guild_members(scene, guild.get("guild_id", "")) if plant.metadata["guild"].get("role") == "centre"), None)
                if centre is not None:
                    name = centre.metadata["guild"].get("name", name)
            self.guild_label.setText(self.tr("{name} — {role}").format(name=name, role=role))
        else:
            self.guild_label.setText(self.tr("No guild"))

    def _refresh_layer(self, data: PlantSpeciesData) -> None:
        self.layer_combo.setCurrentIndex(self.layer_combo.findData(data.permaculture_layer.value))

    def _refresh_functions(self, data: PlantSpeciesData) -> None:
        values = {f.value for f in data.functions}
        for i in range(self.functions_list.count()):
            row = cast(QListWidgetItem, self.functions_list.item(i))
            row.setCheckState(Qt.CheckState.Checked if row.data(Qt.ItemDataRole.UserRole) in values
                              else Qt.CheckState.Unchecked)

    def _on_layer_changed(self) -> None:
        from open_garden_planner.ui.plant_traits import change_trait

        if self._current_plant_item is not None:
            change_trait(self._current_plant_item, "permaculture_layer", self.layer_combo.currentData())

    def _on_functions_changed(self) -> None:
        from open_garden_planner.ui.plant_traits import change_trait

        if self._current_plant_item is not None:
            values = [cast(QListWidgetItem, self.functions_list.item(i)).data(Qt.ItemDataRole.UserRole)
                      for i in range(self.functions_list.count())
                      if cast(QListWidgetItem, self.functions_list.item(i)).checkState() == Qt.CheckState.Checked]
            change_trait(self._current_plant_item, "functions", values)

    def set_selected_items(self, items: list[QGraphicsItem]) -> None:
        """Update panel based on selected items.

        Args:
            items: List of selected graphics items
        """
        # A genuine selection change must not drop a coalesced notes edit for
        # the previous item: flush it as its own undo step before switching.
        # Same-item notifications (mid-typing) must NOT flush here.
        if (
            self._current_plant_item is not None
            and (len(items) != 1 or items[0] is not self._current_plant_item)
        ):
            with contextlib.suppress(Exception):
                self._flush_pending_notes()
            self._last_spin_cmd = None
        # Consume a history transition first (#560): it outranks both the
        # trait-only fast path and the focus guard below.
        history = self._history_pending
        self._history_pending = False
        # Defensive backstop (#206): this panel reuses persistent widgets and
        # re-pushes values via _show_plant_data on every call. If it is called
        # for the *same* item that is already displayed while one of its own
        # editable fields holds focus (e.g. a stray signal mid-edit), skip the
        # re-push so it cannot stomp the active edit / drop the caret — the sole
        # reason the unguarded sibling here was "safe only by luck" (issue #200).
        # A genuine selection change still falls through and updates the panel.
        if len(items) == 1 and items[0] is self._current_plant_item:
            self._refresh_lifetime_dates(items[0])
            species = getattr(items[0], "metadata", {}).get("plant_species")
            if isinstance(species, dict):
                data = PlantSpeciesData.from_dict(species)
                self._refresh_traits(data)
                # Trait-only commands must never reset scroll position or active edits.
                old = self._current_plant_data
                if old is not None:
                    before, after = old.to_dict(), data.to_dict()
                    for field in ("permaculture_layer", "functions"):
                        before.pop(field, None)
                        after.pop(field, None)
                    if before == after and not history:
                        self._current_plant_data = data
                        return
        if (
            len(items) == 1
            and items[0] is self._current_plant_item
            and self._holds_field_focus()
            and not history
        ):
            return
        # History transitions (#560) refresh even a focused editor, but never
        # lose a coalesced notes edit: flush it first as its own undo step.
        if history:
            with contextlib.suppress(Exception):
                self._flush_pending_notes()

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

        # Deserialize and display. Programmatic pushes must not create nested
        # commands: guard the whole push (P1-4). Every push path blocks its
        # own signals today, but a guard that never guards is worse than none.
        self._in_commit = True
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
        finally:
            self._in_commit = False

    def _holds_field_focus(self) -> bool:
        """True when one of this panel's editable input widgets currently has focus."""
        fw = QApplication.focusWidget()
        return (
            fw is not None
            and isinstance(fw, (QAbstractSpinBox, QLineEdit, QPlainTextEdit))
            and self.isAncestorOf(fw)
        )

    def _hide_details(self) -> None:
        """Hide plant details and show 'no selection' message."""
        self._current_plant_data = None
        self._current_plant_item = None
        self._update_favorite_button()
        self._clear_profile_header()
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

    def _clear_profile_header(self) -> None:
        """Remove species identity and attribution when no species is displayed."""
        for label in (
            self._profile_name, self._profile_scientific, self._profile_description,
            self._profile_source, self._profile_links, self._profile_thumbnail,
        ):
            label.clear()
        self._profile_header.hide()
        if hasattr(self, "_license_label"):
            self._license_label.clear()
            self._license_label.hide()
        self._favorite_btn.setToolTip("")

        # The collapsible panel's source hint belongs to the same identity.
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
        self._update_favorite_button()
        self._clear_profile_header()
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
        self._refresh_traits(plant_data)
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

        # Soil requirements (US-12.10d)
        self.ph_min_spin.blockSignals(True)
        self.ph_min_spin.setValue(plant_data.ph_min or 0.0)
        self.ph_min_spin.blockSignals(False)
        self.ph_max_spin.blockSignals(True)
        self.ph_max_spin.setValue(plant_data.ph_max or 0.0)
        self.ph_max_spin.blockSignals(False)
        self._set_combo_data(self.n_demand_combo, plant_data.n_demand)
        self._set_combo_data(self.p_demand_combo, plant_data.p_demand)
        self._set_combo_data(self.k_demand_combo, plant_data.k_demand)
        self._set_combo_data(self.nutrient_demand_combo, plant_data.nutrient_demand)

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
        self._refresh_lifetime_dates(plant_item)

        # Update age label
        self._update_age_label(planting_date_val)

        # Current height
        current_height = instance_data.get("current_height_cm")
        self.current_height_spin.blockSignals(True)
        self.current_height_spin.setValue(float(current_height) if current_height else 0)
        self.current_height_spin.blockSignals(False)

        # Current spread — honour the legacy current_diameter_cm alias, as
        # PlantInstance.from_dict, the CSV export and the growth model all
        # do; otherwise an old plan shows "—" here while its shadow is sized
        # from the aliased value.
        current_spread = instance_data.get("current_spread_cm") or instance_data.get(
            "current_diameter_cm"
        )
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

        # === SEED PACKET LINK (US-9.6) ===
        self._populate_seed_packet_combo(plant_data, instance_data)

        # === SOURCE INFO ===
        # Set source info as tooltip on the panel header (via parent)
        source_text = self.tr("Data Source: {source}").format(
            source=plant_source_label(plant_data.data_source)
        )
        if plant_data.source_id:
            source_text += self.tr(" (ID: {id})").format(id=plant_data.source_id)

        # Find the CollapsiblePanel parent and set the info tooltip
        parent_widget = self.parent()
        while parent_widget:
            if hasattr(parent_widget, "set_info_tooltip"):
                parent_widget.set_info_tooltip(source_text)
                break
            parent_widget = parent_widget.parent()

        # === SOURCE LICENCE LINE ===
        # Show licence/attribution line for API-sourced plants
        from open_garden_planner.ui.plant_species_assignment import plant_source_license
        license_text = plant_source_license(plant_data.data_source)
        if license_text:
            if not hasattr(self, "_license_label"):
                self._license_label = QLabel()
                self._license_label.setWordWrap(True)
                set_text_role(self._license_label, "hint")
                # Insert after the button row, before the scroll area
                self.layout().insertWidget(2, self._license_label)
            self._license_label.setText(license_text)
            self._license_label.setVisible(True)
        elif hasattr(self, "_license_label"):
            self._license_label.setVisible(False)

        # === PROFILE HEADER (US-G2, issue #317) ===
        self._update_profile_header(plant_data)

    def _update_profile_header(self, plant_data: PlantSpeciesData) -> None:
        """Update the profile header with plant data (US-G2, issue #317).

        Shows thumbnail, names, description, source, and external links.
        """
        from open_garden_planner.services.plant_api.thumbnail_loader import (
            get_cached_thumbnail,
        )

        # Name
        name_parts = []
        if plant_data.common_name:
            name_parts.append(plant_data.common_name)
        if plant_data.scientific_name:
            name_parts.append(f"({plant_data.scientific_name})")
        self._profile_name.setText(" ".join(name_parts) if name_parts else "—")

        # Scientific name (separate line for readability)
        self._profile_scientific.setText(plant_data.scientific_name or "")

        # Description (truncated to 3 lines)
        desc = plant_data.description or ""
        if len(desc) > 200:
            desc = desc[:200] + "…"
        self._profile_description.setText(desc)
        self._profile_description.setVisible(bool(plant_data.description))

        # Source + licence
        from open_garden_planner.ui.plant_species_assignment import (
            plant_source_label,
            plant_source_license,
        )
        source_label = plant_source_label(plant_data.data_source)
        license_text = plant_source_license(plant_data.data_source)
        source_parts = [source_label]
        if license_text:
            source_parts.append(license_text)
        self._profile_source.setText(" · ".join(source_parts))
        self._profile_source.setVisible(bool(source_label))

        # External links
        links = []
        sci_name = plant_data.scientific_name
        if sci_name:
            from urllib.parse import quote
            encoded_name = quote(sci_name)
            # Wikipedia
            from open_garden_planner.app.settings import get_settings
            settings = get_settings()
            lang = settings.language if hasattr(settings, "language") else "en"
            if lang == "de":
                links.append(
                    f"<a href='https://de.wikipedia.org/wiki/{encoded_name}'>Wikipedia</a>"
                )
            else:
                links.append(
                    f"<a href='https://en.wikipedia.org/wiki/{encoded_name}'>Wikipedia</a>"
                )
            # PFAF
            links.append(
                f"<a href='https://pfaf.org/user/Plant.aspx?LatinName={encoded_name}'>PFAF</a>"
            )
            # POWO
            links.append(
                f"<a href='https://powo.science.kew.org/results?q={encoded_name}'>POWO</a>"
            )
        # Provider's own page
        if plant_data.data_source == "permapeople" and plant_data.slug:
            links.append(
                f"<a href='https://permapeople.org/plants/{plant_data.slug}'>Permapeople</a>"
            )
        self._profile_links.setText(" · ".join(links) if links else "")
        self._profile_links.setVisible(bool(links))

        # Thumbnail
        thumb_url = plant_data.thumbnail_url or plant_data.image_url
        if thumb_url:
            cached = get_cached_thumbnail(thumb_url)
            if cached:
                from PyQt6.QtGui import QPixmap
                pixmap = QPixmap(str(cached))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        96, 96,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._profile_thumbnail.setPixmap(scaled)
                else:
                    self._profile_thumbnail.setText("🌱")
            else:
                # Show placeholder while loading
                self._profile_thumbnail.setText("🌱")
        else:
            self._profile_thumbnail.setText("🌱")

        # Show the header if there's any content
        has_content = bool(
            plant_data.common_name
            or plant_data.scientific_name
            or plant_data.description
            or thumb_url
        )
        self._profile_header.setVisible(has_content)

        # Update favorite button
        self._current_plant_data = plant_data
        self._update_favorite_button()

    def _on_toggle_favorite(self) -> None:
        """Toggle favorite status for currently displayed plant."""
        if self._current_plant_data:
            self._list_store.toggle_favorite(self._current_plant_data)
            self._update_favorite_button()

    def _update_favorite_button(self) -> None:
        """Update favorite button state from store."""
        if not self._current_plant_data:
            self._favorite_btn.setEnabled(False)
            self._favorite_btn.setText("☆")
            return
        self._favorite_btn.setEnabled(True)
        is_fav = self._list_store.is_favorite(self._current_plant_data)
        self._favorite_btn.setText("⭐" if is_fav else "☆")
        self._favorite_btn.setToolTip(
            self.tr("Remove from Favorites") if is_fav else self.tr("Add to Favorites")
        )

    def _apply_species_to_item(
        self, plant_item: QGraphicsItem, species_dict: dict
    ) -> None:
        """Assign a database species dict to a plant item (undoable + repaints).

        Thin wrapper over :func:`apply_species_to_item` that supplies this panel
        as the dialog parent. See issue #213.
        """
        apply_species_to_item(
            plant_item,
            species_dict,
            confirm=self._confirm_apply_database_values,
        )

    def _confirm_apply_database_values(self) -> bool:
        """Ask whether to overwrite a differing manual override with the DB value.

        Returns True to apply database values, False to keep the custom value.
        A separate method so tests can stub the user's choice.
        """
        return confirm_apply_database_values(self)

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
            # Assign selected plant to the item (undoable + repaints canvas)
            plant_item = self._current_plant_item
            self._apply_species_to_item(
                plant_item, merge_calendar_data(dialog.selected_plant.to_dict())
            )

            # Show the plant data for editing
            self._show_plant_data(dialog.selected_plant, plant_item)

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
            scientific_name=self.tr("Custom Species"),
            common_name=self.tr("My Custom Plant"),
            data_source="custom",
        )

        # Store the current plant item reference
        plant_item = self._current_plant_item

        # Build the species record, register it in the library, stamp source_id.
        species_dict = merge_calendar_data(custom_plant.to_dict())
        library = get_plant_library()
        plant_id = library.add_plant(custom_plant)
        species_dict["source_id"] = plant_id

        # Assign to the selected plant item (undoable + repaints canvas)
        self._apply_species_to_item(plant_item, species_dict)

        # Show the plant data for editing
        self._show_plant_data(custom_plant, plant_item)
