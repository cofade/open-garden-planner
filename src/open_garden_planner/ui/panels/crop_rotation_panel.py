"""Crop rotation recommendation panel (US-10.6).

Shows planting history and rotation recommendations for the selected bed/area.
Displays suggested nutrient demand level and families to avoid.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services.crop_rotation_service import (
    CropRotationService,
    RotationRecommendation,
    RotationStatus,
)

# Status colors
_STATUS_COLORS = {
    RotationStatus.GOOD: "#2e7d32",       # Green
    RotationStatus.SUBOPTIMAL: "#f57f17",  # Amber
    RotationStatus.VIOLATION: "#c62828",   # Red
    RotationStatus.UNKNOWN: "#757575",     # Grey
}

_STATUS_ICONS = {
    RotationStatus.GOOD: "\u2705",       # Green check
    RotationStatus.SUBOPTIMAL: "\u26a0",  # Warning triangle
    RotationStatus.VIOLATION: "\u274c",   # Red X
    RotationStatus.UNKNOWN: "\u2753",     # Question mark
}

# Nutrient demand display labels
_DEMAND_LABELS = {
    "heavy": "Heavy Feeder",
    "medium": "Medium Feeder",
    "light": "Light Feeder",
    "fixer": "Green Manure / N-Fixer",
}


class CropRotationPanel(QWidget):
    """Sidebar panel showing crop rotation history and recommendations.

    Args:
        rotation_service: Shared CropRotationService instance.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        rotation_service: CropRotationService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = rotation_service
        self._current_area_id: str | None = None
        self._cached_item: object | None = None
        self._project_manager: Any = None
        self._setup_ui()
        self.update_for_bed(None, None)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_project_manager(self, pm: Any) -> None:
        """Attach the project manager for saving rotation records."""
        self._project_manager = pm

    def update_for_bed(self, item: object | None, area_id: str | None) -> None:
        """Rebuild the panel for a bed/area item (or None to clear)."""
        self._current_area_id = area_id
        self._cached_item = item
        self._history_list.clear()

        if item is None or area_id is None:
            self._status_label.setText(self.tr("No bed selected"))
            self._status_label.setStyleSheet("font-style: italic; color: #757575;")
            self._recommendation_label.setText("")
            self._avoid_label.setText("")
            self._suggest_label.setText("")
            self._add_record_btn.setEnabled(False)
            return

        self._add_record_btn.setEnabled(True)
        rec = self._service.get_recommendation(area_id)
        self._display_recommendation(rec, item)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Status header
        self._status_label = QLabel(self.tr("No bed selected"))
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("font-style: italic;")
        layout.addWidget(self._status_label)

        # Recommendation text
        self._recommendation_label = QLabel()
        self._recommendation_label.setWordWrap(True)
        self._recommendation_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._recommendation_label)

        # Suggested demand
        self._suggest_label = QLabel()
        self._suggest_label.setWordWrap(True)
        self._suggest_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(self._suggest_label)

        # Families to avoid
        self._avoid_label = QLabel()
        self._avoid_label.setWordWrap(True)
        self._avoid_label.setStyleSheet("color: #c62828; font-size: 11px;")
        layout.addWidget(self._avoid_label)

        # History header
        history_header = QLabel(self.tr("Planting History"))
        history_header.setStyleSheet("font-weight: bold; margin-top: 6px;")
        layout.addWidget(history_header)

        # History list
        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(140)
        self._history_list.setAlternatingRowColors(True)
        layout.addWidget(self._history_list)

        # Add record button
        btn_layout = QHBoxLayout()
        self._add_record_btn = QPushButton(self.tr("Add Planting Record..."))
        self._add_record_btn.setEnabled(False)
        self._add_record_btn.clicked.connect(self._on_add_record)
        btn_layout.addWidget(self._add_record_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _display_recommendation(
        self, rec: RotationRecommendation, item: object
    ) -> None:
        """Populate the panel with recommendation data."""
        color = _STATUS_COLORS.get(rec.status, "#757575")
        icon = _STATUS_ICONS.get(rec.status, "")

        # Bed name
        bed_name = getattr(item, "name", "") or self.tr("Unnamed Bed")
        status_text = {
            RotationStatus.GOOD: self.tr("Good Rotation"),
            RotationStatus.SUBOPTIMAL: self.tr("Suboptimal Rotation"),
            RotationStatus.VIOLATION: self.tr("Rotation Violation"),
            RotationStatus.UNKNOWN: self.tr("No History"),
        }.get(rec.status, "")

        self._status_label.setText(f"{icon} {bed_name}: {status_text}")
        self._status_label.setStyleSheet(
            f"font-weight: bold; color: {color}; font-size: 12px;"
        )

        # Recommendation reason
        self._recommendation_label.setText(rec.reason)

        # Suggested demand
        demand_label = _DEMAND_LABELS.get(rec.suggested_demand, rec.suggested_demand)
        self._suggest_label.setText(
            self.tr("Next: %1").replace("%1", demand_label)
        )

        # Families to avoid
        if rec.avoid_families:
            families_str = ", ".join(rec.avoid_families)
            self._avoid_label.setText(
                self.tr("Avoid: %1").replace("%1", families_str)
            )
        else:
            self._avoid_label.setText("")

        # History list
        self._history_list.clear()
        for record in rec.last_records:
            demand_short = _DEMAND_LABELS.get(
                record.nutrient_demand, record.nutrient_demand
            )
            text = (
                f"{record.year} {record.season}: "
                f"{record.common_name or record.species_name}"
            )
            if record.family:
                text += f" ({record.family})"
            if demand_short:
                text += f" \u2014 {demand_short}"

            entry = QListWidgetItem(text)
            entry.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._history_list.addItem(entry)

        if self._history_list.count() == 0:
            placeholder = QListWidgetItem(self.tr("(no records yet)"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(self.palette().placeholderText())
            self._history_list.addItem(placeholder)

    def _on_add_record(self) -> None:
        """Open a dialog to add a planting record for the current bed."""
        if not self._current_area_id:
            return

        from open_garden_planner.ui.dialogs.add_planting_record_dialog import (
            AddPlantingRecordDialog,
        )

        dialog = AddPlantingRecordDialog(self._current_area_id, parent=self)
        if dialog.exec():
            record = dialog.get_record()
            if record is not None:
                self._service.history.add_record(record)
                self._save_history()
                # Refresh panel
                self.update_for_bed(self._cached_item, self._current_area_id)

    def _save_history(self) -> None:
        """Persist the rotation history to the project file."""
        if self._project_manager is not None:
            self._project_manager.set_crop_rotation(
                self._service.history.to_dict()
            )
