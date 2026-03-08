"""Dialog for adding a planting record to the crop rotation history (US-10.6)."""

from __future__ import annotations

from datetime import date

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.crop_rotation import (
    NUTRIENT_DEMANDS,
    SEASONS,
    PlantingRecord,
)


class AddPlantingRecordDialog(QDialog):
    """Dialog to create a new PlantingRecord for a specific bed/area.

    Args:
        area_id: The UUID string of the bed/area this record belongs to.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        area_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._area_id = area_id
        self.setWindowTitle(self.tr("Add Planting Record"))
        self.setMinimumWidth(360)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        # Year
        self._year_spin = QSpinBox()
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(date.today().year)
        form.addRow(self.tr("Year:"), self._year_spin)

        # Season
        self._season_combo = QComboBox()
        season_labels = {
            "spring": self.tr("Spring"),
            "summer": self.tr("Summer"),
            "fall": self.tr("Fall"),
            "winter": self.tr("Winter"),
        }
        for key in SEASONS:
            self._season_combo.addItem(season_labels.get(key, key), key)
        form.addRow(self.tr("Season:"), self._season_combo)

        # Species / common name
        self._species_edit = QLineEdit()
        self._species_edit.setPlaceholderText(self.tr("e.g. Solanum lycopersicum"))
        form.addRow(self.tr("Species:"), self._species_edit)

        self._common_name_edit = QLineEdit()
        self._common_name_edit.setPlaceholderText(self.tr("e.g. Tomato"))
        form.addRow(self.tr("Common Name:"), self._common_name_edit)

        # Family
        self._family_edit = QLineEdit()
        self._family_edit.setPlaceholderText(self.tr("e.g. Solanaceae"))
        form.addRow(self.tr("Family:"), self._family_edit)

        # Nutrient demand
        self._demand_combo = QComboBox()
        demand_labels = {
            "heavy": self.tr("Heavy Feeder"),
            "medium": self.tr("Medium Feeder"),
            "light": self.tr("Light Feeder"),
            "fixer": self.tr("Green Manure / N-Fixer"),
        }
        for key in NUTRIENT_DEMANDS:
            self._demand_combo.addItem(demand_labels.get(key, key), key)
        form.addRow(self.tr("Nutrient Demand:"), self._demand_combo)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_record(self) -> PlantingRecord | None:
        """Build a PlantingRecord from the dialog fields.

        Returns:
            PlantingRecord if valid, None if species is empty.
        """
        species = self._species_edit.text().strip()
        common_name = self._common_name_edit.text().strip()
        if not species and not common_name:
            return None

        return PlantingRecord(
            year=self._year_spin.value(),
            season=self._season_combo.currentData(),
            species_name=species,
            common_name=common_name,
            family=self._family_edit.text().strip(),
            nutrient_demand=self._demand_combo.currentData(),
            area_id=self._area_id,
        )
