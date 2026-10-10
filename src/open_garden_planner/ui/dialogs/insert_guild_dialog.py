"""Template selection, authoring and preflighted transient guild preview."""

from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.guild_commands import (
    InsertGuildCommand,
    guild_plant_layers_editable,
    prepare_guild,
)
from open_garden_planner.core.object_types import is_plant_type
from open_garden_planner.models.guild import GuildTemplate
from open_garden_planner.services.guild_library import GuildLibrary
from open_garden_planner.services.species_catalog import offline_catalog
from open_garden_planner.ui.dialogs.guild_template_editor import GuildTemplateEditor
from open_garden_planner.ui.guild_errors import guild_error_message
from open_garden_planner.ui.widgets.trait_filters import trait_label


class InsertGuildDialog(QDialog):
    def __init__(self, scene: Any, *, auto_assign: bool = False, library: GuildLibrary | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self.auto_assign = auto_assign
        self.library = library or GuildLibrary()
        self.catalog = offline_catalog()
        self.command: InsertGuildCommand | None = None
        self._preview: list[QGraphicsEllipseItem] = []
        self.role_choices: dict[str, QComboBox] = {}
        self.setWindowTitle(self.tr("Insert guild…"))
        self.resize(650, 550)
        layout = QVBoxLayout(self)
        self.template_combo = QComboBox()
        layout.addWidget(self.template_combo)
        actions = QHBoxLayout()
        for label, callback in ((self.tr("New"), lambda: self.edit_template("new")),
                                (self.tr("Duplicate"), lambda: self.edit_template("duplicate")),
                                (self.tr("Edit"), lambda: self.edit_template("edit")),
                                (self.tr("Reload"), self.reload)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.name_edit = QLineEdit()
        self.centre_combo = QComboBox()
        self.existing_combo = QComboBox()
        form = QFormLayout()
        form.addRow(self.tr("Instance name:"), self.name_edit)
        form.addRow(self.tr("Centre species:"), self.centre_combo)
        form.addRow(self.tr("Existing centre:"), self.existing_combo)
        self.x_spin, self.y_spin = QDoubleSpinBox(), QDoubleSpinBox()
        for spin, size in ((self.x_spin, scene.width_cm), (self.y_spin, scene.height_cm)):
            spin.setRange(0, size)
            spin.setDecimals(2)
            spin.setSuffix(self.tr(" cm"))
            spin.setValue(size / 2)
            spin.valueChanged.connect(self.clear_preview)
        form.addRow(self.tr("Centre X:"), self.x_spin)
        form.addRow(self.tr("Centre Y:"), self.y_spin)
        layout.addLayout(form)
        self.roles_form = QFormLayout()
        layout.addLayout(self.roles_form)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        self.file_errors = QLabel()
        self.file_errors.setWordWrap(True)
        layout.addWidget(self.file_errors)
        preview = QPushButton(self.tr("Preview placement"))
        preview.clicked.connect(self.preview)
        layout.addWidget(preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.insert)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.template_combo.currentIndexChanged.connect(self._template_changed)
        self.existing_combo.currentIndexChanged.connect(self._centre_changed)
        self.centre_combo.currentIndexChanged.connect(self.clear_preview)
        self.reload()

    @property
    def template(self) -> GuildTemplate | None:
        return self.library.templates.get(self.template_combo.currentData())

    def reload(self) -> None:
        identity = self.template_combo.currentData()
        self.library.reload()
        self.catalog = offline_catalog()
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        from open_garden_planner.app.settings import active_language

        for template in self.library.templates.values():
            self.template_combo.addItem(template.name_de if active_language() == "de" and template.name_de else template.name, template.id)
        index = self.template_combo.findData(identity)
        if index >= 0:
            self.template_combo.setCurrentIndex(index)
        self.template_combo.blockSignals(False)
        self.file_errors.setText("\n".join(self.tr("{filename}: {reason} — repair the JSON file and Reload.").format(
            filename=filename, reason=guild_error_message(self.library.error_objects[filename])) for filename, _reason in self.library.errors))
        self._template_changed()

    def _template_changed(self) -> None:
        self.clear_preview()
        template = self.template
        while self.roles_form.rowCount():
            self.roles_form.removeRow(0)
        self.role_choices = {}
        self.centre_combo.clear()
        self.existing_combo.clear()
        self.existing_combo.addItem(self.tr("Create a new centre"), None)
        if template is None:
            return
        from open_garden_planner.app.settings import active_language

        self.name_edit.setText(template.name_de if active_language() == "de" and template.name_de else template.name)
        self.description.setText(template.description_de if active_language() == "de" and template.description_de else template.description)
        function_centre = template.centre.removeprefix("function:") if template.centre.startswith("function:") else None
        keys = [key for key, species in self.catalog.items() if function_centre in species.get("functions", [])] if function_centre else [template.centre]
        for key in keys:
            self.centre_combo.addItem(self.catalog.get(key, {}).get("common_name", self.tr("Unresolved: {key}").format(key=key)), key)
        for item in self.scene.items():
            if not hasattr(item, "object_type") or not is_plant_type(item.object_type) or item.metadata.get("guild") is not None or not guild_plant_layers_editable(self.scene, item):
                continue
            species = item.metadata.get("plant_species") or {}
            eligible = function_centre in species.get("functions", []) if function_centre else species.get("scientific_name", "").casefold() == self.catalog.get(template.centre, {}).get("scientific_name", "").casefold()
            if eligible:
                self.existing_combo.addItem(getattr(item, "name", "") or species.get("common_name", ""), str(item.item_id))
        for role in template.roles:
            combo = QComboBox()
            ordered = list(role.suggested_species) + [key for key, species in self.catalog.items()
                if key not in role.suggested_species and role.function in species.get("functions", [])]
            for key in ordered:
                species = self.catalog.get(key)
                combo.addItem(species.get("common_name", key) if species else self.tr("Unresolved: {key}").format(key=key), key)
            self.roles_form.addRow(trait_label(role.function), combo)
            self.role_choices[role.function] = combo
            combo.currentIndexChanged.connect(self.clear_preview)
        self.error_label.clear()

    def _centre_changed(self) -> None:
        new = self.existing_combo.currentData() is None
        self.centre_combo.setEnabled(new)
        self.x_spin.setEnabled(new)
        self.y_spin.setEnabled(new)
        self.clear_preview()

    def prepare(self) -> InsertGuildCommand:
        from uuid import UUID

        identity = self.existing_combo.currentData()
        existing = self.scene.find_item_by_id(UUID(identity)) if identity else None
        if identity and existing is None:
            raise ValueError("Existing centre is no longer in the plan")
        choices = {function: combo.currentData() for function, combo in self.role_choices.items()}
        choices["centre"] = self.centre_combo.currentData()
        template = self.template
        if template is None:
            raise ValueError(self.tr("Select a valid guild template"))
        return prepare_guild(self.scene, template, self.catalog, self.name_edit.text(),
                             QPointF(self.x_spin.value(), self.y_spin.value()), selections=choices,
                             existing_centre=existing, auto_assign=self.auto_assign)

    def preview(self) -> None:
        self.clear_preview()
        try:
            command = self.prepare()
            for item in command.items:
                marker = QGraphicsEllipseItem(item.mapRectToScene(item.rect()))
                marker.setPen(QPen(QColor("#559f62"), 2))
                marker.setZValue(1001)
                self.scene.addItem(marker)
                self._preview.append(marker)
            self.error_label.clear()
        except Exception as error:
            self.error_label.setText(self.tr("Guild cannot be placed: {error}").format(error=guild_error_message(error)))

    def clear_preview(self) -> None:
        for marker in self._preview:
            if marker.scene() is not None:
                self.scene.removeItem(marker)
        self._preview = []

    def insert(self) -> None:
        try:
            self.command = self.prepare()
        except Exception as error:
            self.error_label.setText(self.tr("Guild cannot be placed: {error}").format(error=guild_error_message(error)))
            return
        self.accept()

    def edit_template(self, mode: str) -> None:
        template = None if mode == "new" else self.template
        if mode != "new" and template is None:
            return
        editor = GuildTemplateEditor(self.library, template, duplicate=mode == "duplicate",
                                     readonly=mode == "edit" and template is not None and template.id not in self.library.user_paths, parent=self)
        if editor.exec():
            self.reload()
            self.template_combo.setCurrentIndex(self.template_combo.findData(editor.saved_template.id if editor.saved_template is not None else ""))

    def done(self, result: int) -> None:  # noqa: N802
        self.clear_preview()
        super().done(result)
