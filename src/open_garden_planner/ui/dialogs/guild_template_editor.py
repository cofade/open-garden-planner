"""User-file guild authoring; no plan mutation or history entry."""

from typing import Any, cast
from uuid import uuid4

from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.guild import GuildTemplate
from open_garden_planner.models.plant_data import PlantFunction
from open_garden_planner.services.guild_library import GuildLibrary
from open_garden_planner.services.species_catalog import offline_catalog
from open_garden_planner.ui.guild_errors import guild_error_message
from open_garden_planner.ui.widgets.trait_filters import trait_label


class RadiusEditor(QWidget):
    """Choose a spacing-derived radius or an explicit distance."""

    def __init__(self, value: float | str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox()
        self.mode.addItem(self.tr("Canopy edge"), "canopy_edge")
        self.mode.addItem(self.tr("Distance (cm)"), "distance")
        self.distance = QDoubleSpinBox()
        self.distance.setRange(0.1, 1000000)
        self.distance.setValue(float(value) if value != "canopy_edge" else 100)
        self.mode.setCurrentIndex(0 if value == "canopy_edge" else 1)
        self.distance.setEnabled(self.mode.currentIndex() == 1)
        self.mode.currentIndexChanged.connect(lambda index: self.distance.setEnabled(index == 1))
        layout.addWidget(self.mode)
        layout.addWidget(self.distance)

    def value(self) -> float | str:
        return "canopy_edge" if self.mode.currentIndex() == 0 else self.distance.value()


class GuildTemplateEditor(QDialog):
    def __init__(self, library: GuildLibrary, template: GuildTemplate | None = None, *, duplicate: bool = False,
                 readonly: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.catalog = offline_catalog()
        self.original = template
        self.duplicate = duplicate
        self.readonly = readonly
        self.saved_template: GuildTemplate | None = None
        self.setWindowTitle(self.tr("Guild template editor"))
        self.resize(850, 650)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.id_edit = QLineEdit(template.id if template and not duplicate else "guild-" + uuid4().hex[:12])
        self.id_edit.setEnabled(template is None or duplicate)
        self.name_edit = QLineEdit(template.name if template else "")
        self.name_de_edit = QLineEdit(template.name_de if template else "")
        self.description_edit = QPlainTextEdit(template.description if template else "")
        self.description_de_edit = QPlainTextEdit(template.description_de if template else "")
        self.description_edit.setMaximumHeight(65)
        self.description_de_edit.setMaximumHeight(65)
        self.centre_combo = QComboBox()
        for key, record in self.catalog.items():
            self.centre_combo.addItem(record.get("common_name", key) + " — " + key, key)
        for function in PlantFunction:
            self.centre_combo.addItem(self.tr("Function: {function}").format(function=trait_label(function.value)),
                                      "function:" + function.value)
        if template:
            index = self.centre_combo.findData(template.centre)
            if index < 0:
                self.centre_combo.addItem(self.tr("Unresolved: {key}").format(key=template.centre), template.centre)
                index = self.centre_combo.count() - 1
            self.centre_combo.setCurrentIndex(index)
        self.license_edit = QLineEdit(template.license if template else "CC-BY-SA-4.0")
        self.attribution_edit = QLineEdit(template.attribution if template else "")
        self.sources_edit = QPlainTextEdit("\n".join(template.sources) if template else "")
        self.sources_edit.setMaximumHeight(55)
        for label, widget in ((self.tr("ID:"), self.id_edit), (self.tr("Name:"), self.name_edit),
                               (self.tr("German name:"), self.name_de_edit),
                               (self.tr("Description:"), self.description_edit),
                               (self.tr("German description:"), self.description_de_edit),
                               (self.tr("Centre:"), self.centre_combo), (self.tr("License:"), self.license_edit),
                               (self.tr("Attribution:"), self.attribution_edit), (self.tr("Sources (one per line):"), self.sources_edit)):
            form.addRow(label, widget)
        layout.addLayout(form)
        self.roles_table = QTableWidget(0, 4)
        self.roles_table.setHorizontalHeaderLabels([self.tr("Function"), self.tr("Minimum"),
                                                    self.tr("Radius"), self.tr("Suggested species (keys, ordered)")])
        header = self.roles_table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        layout.addWidget(self.roles_table)
        actions = QHBoxLayout()
        add = QPushButton(self.tr("Add role"))
        remove = QPushButton(self.tr("Remove role"))
        add.clicked.connect(lambda: self.add_role())
        remove.clicked.connect(lambda: self.roles_table.removeRow(self.roles_table.currentRow()))
        actions.addWidget(add)
        actions.addWidget(remove)
        layout.addLayout(actions)
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        layout.addWidget(self.validation_label)
        for role in template.roles if template else []:
            self.add_role(role.to_dict())
        self.roles_table.setColumnWidth(0, 180)
        self.roles_table.setColumnWidth(1, 75)
        self.roles_table.setColumnWidth(2, 250)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if readonly:
            for readonly_widget in (self.roles_table, self.name_edit, self.name_de_edit, self.description_edit,
                           self.description_de_edit, self.centre_combo, self.license_edit, self.attribution_edit,
                           self.sources_edit, add, remove):
                readonly_widget.setEnabled(False)
            save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
            if save_button is not None:
                save_button.setEnabled(False)
            self.validation_label.setText(self.tr("Bundled template is read-only. Use Duplicate to create a user template."))

    def add_role(self, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        row = self.roles_table.rowCount()
        self.roles_table.insertRow(row)
        function = QComboBox()
        for value in PlantFunction:
            function.addItem(trait_label(value.value), value.value)
        function.setCurrentIndex(max(0, function.findData(data.get("function", "nitrogen_fixer"))))
        count = QSpinBox()
        count.setRange(1, 199)
        count.setValue(data.get("count_min", 1))
        radius = RadiusEditor(data.get("ring_radius_cm", "canopy_edge"))
        species = QLineEdit(", ".join(data.get("suggested_species", [])))
        species.setCompleter(QCompleter(sorted(self.catalog), species))
        species.setToolTip(self.tr("Use canonical species keys separated by commas. Suggestions must record the selected function."))
        for column, widget in enumerate((function, count, radius, species)):
            self.roles_table.setCellWidget(row, column, widget)
        species.textChanged.connect(self._show_eligibility)
        function.currentIndexChanged.connect(self._show_eligibility)

    def _show_eligibility(self, *_args: Any) -> None:
        invalid: list[str] = []
        for row in range(self.roles_table.rowCount()):
            function = cast(QComboBox, self.roles_table.cellWidget(row, 0)).currentData()
            keys = [s.strip() for s in cast(QLineEdit, self.roles_table.cellWidget(row, 3)).text().split(",") if s.strip()]
            invalid.extend(key for key in keys if key not in self.catalog or function not in self.catalog[key].get("functions", []))
        self.validation_label.setText(self.tr("Unresolved or function-ineligible species: {keys}").format(keys=", ".join(invalid)) if invalid
                                      else self.tr("All suggested species are resolved and function-eligible."))

    def definition(self) -> GuildTemplate:
        roles = []
        for row in range(self.roles_table.rowCount()):
            radius = cast(RadiusEditor, self.roles_table.cellWidget(row, 2)).value()
            roles.append({"function": cast(QComboBox, self.roles_table.cellWidget(row, 0)).currentData(),
                          "count_min": cast(QSpinBox, self.roles_table.cellWidget(row, 1)).value(),
                          "ring_radius_cm": radius,
                          "suggested_species": [s.strip() for s in cast(QLineEdit, self.roles_table.cellWidget(row, 3)).text().split(",") if s.strip()]})
        version = self.original.version + 1 if self.original and not self.duplicate else 1
        return GuildTemplate.from_dict({"id": self.id_edit.text().strip(), "version": version,
            "name": self.name_edit.text().strip(), "name_de": self.name_de_edit.text().strip(),
            "description": self.description_edit.toPlainText(), "description_de": self.description_de_edit.toPlainText(),
            "centre": self.centre_combo.currentData(), "roles": roles, "license": self.license_edit.text(),
            "attribution": self.attribution_edit.text(), "sources": self.sources_edit.toPlainText().splitlines()})

    def save(self) -> None:
        if self.readonly:
            return
        try:
            template = self.definition()
            if (self.original is None or self.duplicate) and template.id in self.library.templates:
                raise ValueError(self.tr("Choose a new ID; this template already exists."))
            if not template.centre.startswith("function:") and template.centre not in self.catalog:
                raise ValueError(self.tr("Centre species is unresolved"))
            for role in template.roles:
                if not role.suggested_species or any(s not in self.catalog or role.function not in self.catalog[s].get("functions", []) for s in role.suggested_species):
                    raise ValueError(self.tr("Replace unresolved or function-ineligible suggested species"))
            self.library.save(template)
            self.saved_template = template
        except Exception as error:
            self.validation_label.setText(self.tr("Template could not be saved: {error}").format(error=guild_error_message(error)))
            return
        self.accept()
