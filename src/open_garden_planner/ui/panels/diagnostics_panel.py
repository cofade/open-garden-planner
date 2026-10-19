"""Shared-record diagnostics UI and deferred identity-based object navigation."""

from dataclasses import asdict
from datetime import date
from typing import Any
from uuid import UUID

from PyQt6.QtCore import QCoreApplication, Qt, QTimer
from PyQt6.QtWidgets import QComboBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from open_garden_planner.models.plant_data import SunRequirement
from open_garden_planner.services.diagnostics import DiagnosticRecord
from open_garden_planner.ui.guild_errors import guild_error_details
from open_garden_planner.ui.sun_exposure_text import mismatch_message, unavailable_message
from open_garden_planner.ui.widgets.trait_filters import trait_label


class ObjectNavigator(QWidget):
    """No borrowed graphics items in sidebar rows; resolve at navigation time."""

    def __init__(self, scene: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self._pending_ids: list[str] = []
        self._navigation = QTimer(self)
        self._navigation.setSingleShot(True)
        self._navigation.timeout.connect(self._navigate)
        scene.document_replaced.connect(self._cancel_navigation)

    def _cancel_navigation(self) -> None:
        self._navigation.stop()
        self._pending_ids = []

    def select_ids(self, ids: list[str]) -> None:
        self._pending_ids = list(ids)
        self._navigation.start(0)

    def _navigate(self) -> None:
        try:
            items = []
            for identity in self._pending_ids:
                try:
                    item = self.scene.find_item_by_id(UUID(identity))
                except ValueError:
                    continue
                if item is not None:
                    while item.parentItem() is not None and hasattr(item.parentItem(), "item_id"):
                        item = item.parentItem()
                    items.append(item)
            if not items:
                return
            self.scene.clearSelection()
            for item in items:
                item.setSelected(True)
            if self.scene.views():
                self.scene.views()[0].ensureVisible(items[0])
        except RuntimeError:
            return


class DiagnosticsPanel(ObjectNavigator):
    def __init__(self, scene: Any, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.records: list[DiagnosticRecord] = []
        self._signature: list[dict[str, Any]] | None = None
        layout = QVBoxLayout(self)
        self.count_label = QLabel()
        layout.addWidget(self.count_label)
        self.kind_filter = QComboBox()
        self.kind_filter.addItem(self.tr("All kinds"), None)
        for key, label in (("companion_conflict", self.tr("Companion conflict")),
                           ("spacing_overlap", self.tr("Spacing overlap")),
                           ("capacity_overrun", self.tr("Container capacity")),
                           ("soil_mismatch", self.tr("Soil mismatch")),
                           ("crop_rotation", self.tr("Crop rotation")),
                           ("outside_canvas", self.tr("Outside canvas")),
                           ("guild_role_missing", self.tr("Missing guild role")),
                           ("guild_data_warning", self.tr("Guild data warning"))):
            self.kind_filter.addItem(label, key)
        self.kind_filter.addItem(self.tr("Sun requirement mismatch"), "sun_mismatch")
        self.kind_filter.addItem(self.tr("Sun evaluation"), "sun_evaluation")
        self.severity_filter = QComboBox()
        self.severity_filter.addItem(self.tr("All severities"), None)
        self.severity_filter.addItem(self.tr("Warning"), "warning")
        self.severity_filter.addItem(self.tr("Critical"), "critical")
        self.severity_filter.addItem(self.tr("Information"), "info")
        layout.addWidget(self.kind_filter)
        layout.addWidget(self.severity_filter)
        self.rows = QListWidget()
        self.rows.itemClicked.connect(lambda row: self.select_ids(row.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.rows)
        self.kind_filter.currentIndexChanged.connect(self._render)
        self.severity_filter.currentIndexChanged.connect(self._render)

    def set_records(self, records: list[DiagnosticRecord]) -> None:
        signature = [asdict(record) for record in records]
        if signature == self._signature:
            return
        self.records = records
        self._signature = signature
        self._render()

    def _message(self, record: DiagnosticRecord) -> str:
        details = record.details
        name = details.get("label", "")
        if record.kind in ("sun_mismatch", "sun_evaluation") and details.get("label_is_species"):
            name = QCoreApplication.translate("GalleryData", name)
        if record.kind == "sun_evaluation":
            return self.tr("{name}: {status}").format(name=name, status=unavailable_message(details["reason"]))
        if record.kind == "sun_mismatch":
            return mismatch_message(name, SunRequirement(details["required"]), details["hours"],
                                    date.fromisoformat(details["reference_date"]), details["direction"])
        if record.kind == "guild_role_missing":
            return self.tr("{name}: {function} — {present}/{required}").format(
                name=details["guild_name"], function=trait_label(details["function"]),
                present=details["present_count"], required=details["required_count"])
        if record.kind == "guild_data_warning":
            code = details.get("reason_code")
            reason = guild_error_details(code, details.get("reason_details", {})) if code else self.tr("Invalid saved membership or template")
            return self.tr("Guild data needs repair: {reason}").format(reason=reason)
        templates = {
            "companion_conflict": self.tr("{name}: antagonistic plant nearby"),
            "spacing_overlap": self.tr("{name}: spacing overlap"),
            "capacity_overrun": self.tr("{name}: container capacity exceeded"),
            "soil_mismatch": self.tr("{name}: soil requirements not met"),
            "crop_rotation": self.tr("{name}: crop rotation conflict"),
            "outside_canvas": self.tr("{name}: outside the canvas"),
        }
        return templates.get(record.kind, self.tr("{name}: diagnostic warning")).format(name=name)

    def _render(self) -> None:
        selected = self.rows.currentItem()
        selected_ids = selected.data(Qt.ItemDataRole.UserRole) if selected is not None else None
        scrollbar = self.rows.verticalScrollBar()
        scroll = scrollbar.value() if scrollbar is not None else 0
        self.rows.clear()
        visible = [record for record in self.records
                   if (self.kind_filter.currentData() in (None, record.kind))
                   and (self.severity_filter.currentData() in (None, record.severity))]
        self.count_label.setText(self.tr("{shown} of {total} diagnostics").format(shown=len(visible), total=len(self.records)))
        for record in visible:
            row = QListWidgetItem(self._message(record))
            row.setData(Qt.ItemDataRole.UserRole, record.item_ids)
            self.rows.addItem(row)
            if record.item_ids == selected_ids:
                self.rows.setCurrentItem(row)
        if scrollbar is not None:
            scrollbar.setValue(scroll)
