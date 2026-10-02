"""Crop rotation recommendation panel (US-10.6).

Shows planting history and rotation recommendations for the selected bed/area.
Displays suggested nutrient demand level and families to avoid.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication, Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services.crop_rotation_service import (
    CropRotationService,
    RotationRecommendation,
    RotationStatus,
)
from open_garden_planner.ui.icons import get_pixmap
from open_garden_planner.ui.theme import set_text_role, theme_color

# Status -> semantic theme token (resolved live so a theme switch re-tints)
_STATUS_TOKENS = {
    RotationStatus.GOOD: "success",
    RotationStatus.SUBOPTIMAL: "warning",
    RotationStatus.VIOLATION: "error",
    RotationStatus.UNKNOWN: "text_disabled",
}


def _status_color(status: RotationStatus) -> str:
    """Hex for a rotation status from the active theme palette."""
    return theme_color(_STATUS_TOKENS.get(status, "text_disabled"))

# provider icon per status (was an emoji ✅ ⚠ ❌ ❓ text prefix; #310)
_STATUS_ICONS = {
    RotationStatus.GOOD: "check",
    RotationStatus.SUBOPTIMAL: "warning",
    RotationStatus.VIOLATION: "cross",
    RotationStatus.UNKNOWN: "help",
}

# Keys for demand / season — translated at display time via _tr()
_DEMAND_KEYS = ("heavy", "medium", "light", "fixer")
_SEASON_KEYS = ("spring", "summer", "fall", "winter")


def _tr(source: str) -> str:
    """Translate a string in the CropRotationPanel context at display time."""
    return QCoreApplication.translate("CropRotationPanel", source)


def _demand_label(key: str) -> str:
    """Return the translated demand label for a nutrient-demand key."""
    labels = {
        "heavy": QT_TR_NOOP("Heavy Feeder"),
        "medium": QT_TR_NOOP("Medium Feeder"),
        "light": QT_TR_NOOP("Light Feeder"),
        "fixer": QT_TR_NOOP("Green Manure / N-Fixer"),
    }
    return _tr(labels.get(key, key))


def _season_label(key: str) -> str:
    """Return the translated season label."""
    labels = {
        "spring": QT_TR_NOOP("Spring"),
        "summer": QT_TR_NOOP("Summer"),
        "fall": QT_TR_NOOP("Fall"),
        "winter": QT_TR_NOOP("Winter"),
    }
    return _tr(labels.get(key, key))


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
        # A succession plan can change while the panel is open (the GUI plan
        # dialog, or an agent's set_succession_plan). Re-render on that signal so
        # the "Planned This Season" section never shows stale data (issue #378).
        changed = getattr(pm, "succession_plans_changed", None)
        if changed is not None and hasattr(changed, "connect"):
            changed.connect(self._on_succession_plans_changed)

    def _on_succession_plans_changed(self, _plans: object = None) -> None:
        """Re-render the current bed when its succession plan changes."""
        if self._current_area_id is not None:
            self.update_for_bed(self._cached_item, self._current_area_id)

    def apply_theme_colors(self, _colors: dict[str, str]) -> None:
        """Re-render on theme switch — the status colors are palette-driven."""
        self.update_for_bed(self._cached_item, self._current_area_id)

    def update_for_bed(self, item: object | None, area_id: str | None) -> None:
        """Rebuild the panel for a bed/area item (or None to clear)."""
        self._current_area_id = area_id
        self._cached_item = item
        self._history_list.clear()

        if item is None or area_id is None:
            self._current_status = None
            self._status_icon.hide()
            self._status_label.setText(self.tr("No bed selected"))
            self._status_label.setStyleSheet(
                f"font-style: italic; color: {theme_color('text_disabled')};"
            )
            self._recommendation_label.setText("")
            self._avoid_label.setText("")
            self._suggest_label.setText("")
            self._add_record_btn.setEnabled(False)
            self._edit_record_btn.setEnabled(False)
            self._delete_record_btn.setEnabled(False)
            self._hide_succession_plan()
            return

        self._add_record_btn.setEnabled(True)
        rec = self._service.get_recommendation(area_id)
        self._display_recommendation(rec, item)
        self._display_succession_plan(area_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Status header: themed status icon + text
        status_row = QHBoxLayout()
        status_row.setSpacing(4)
        self._status_icon = QLabel()
        self._status_icon.setFixedSize(18, 18)
        self._status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_icon.hide()
        status_row.addWidget(self._status_icon, 0, Qt.AlignmentFlag.AlignTop)
        self._status_label = QLabel(self.tr("No bed selected"))
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("font-style: italic;")
        status_row.addWidget(self._status_label, 1)
        layout.addLayout(status_row)
        self._current_status: RotationStatus | None = None

        # Recommendation text
        self._recommendation_label = QLabel()
        self._recommendation_label.setWordWrap(True)
        self._recommendation_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._recommendation_label)

        # Suggested demand
        self._suggest_label = QLabel()
        self._suggest_label.setWordWrap(True)
        self._suggest_label.setStyleSheet("font-weight: 600; font-size: 11px;")
        layout.addWidget(self._suggest_label)

        # Families to avoid
        self._avoid_label = QLabel()
        self._avoid_label.setWordWrap(True)
        set_text_role(self._avoid_label, color_role="error")
        self._avoid_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._avoid_label)

        # History header
        history_header = QLabel(self.tr("Planting History"))
        set_text_role(history_header, "h2")
        history_header.setStyleSheet("margin-top: 6px;")
        layout.addWidget(history_header)

        # History list
        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(140)
        self._history_list.setAlternatingRowColors(True)
        layout.addWidget(self._history_list)

        # Succession plan ("planned this season") — display-only, NOT history.
        # Kept visually and semantically separate from the rotation history
        # above: it is what is *planned*, not what was *grown* (issue #378).
        self._plan_header = QLabel(self.tr("Planned This Season"))
        set_text_role(self._plan_header, "h2")
        self._plan_header.setStyleSheet("margin-top: 6px;")
        layout.addWidget(self._plan_header)

        self._plan_note = QLabel(
            self.tr(
                "Planned crops are not planting history and do not affect the "
                "rotation advice above."
            )
        )
        self._plan_note.setWordWrap(True)
        set_text_role(self._plan_note, color_role="text_disabled")
        self._plan_note.setStyleSheet("font-size: 10px; font-style: italic;")
        layout.addWidget(self._plan_note)

        self._plan_list = QListWidget()
        self._plan_list.setMaximumHeight(120)
        layout.addWidget(self._plan_list)

        # Buttons: add / edit / delete
        btn_layout = QHBoxLayout()
        self._add_record_btn = QPushButton(self.tr("Add Planting Record..."))
        self._add_record_btn.setEnabled(False)
        self._add_record_btn.clicked.connect(self._on_add_record)
        btn_layout.addWidget(self._add_record_btn)

        self._edit_record_btn = QPushButton(self.tr("Edit"))
        self._edit_record_btn.setEnabled(False)
        self._edit_record_btn.setFixedWidth(50)
        self._edit_record_btn.clicked.connect(self._on_edit_record)
        btn_layout.addWidget(self._edit_record_btn)

        self._delete_record_btn = QPushButton(self.tr("Delete"))
        self._delete_record_btn.setEnabled(False)
        self._delete_record_btn.setFixedWidth(50)
        self._delete_record_btn.clicked.connect(self._on_delete_record)
        btn_layout.addWidget(self._delete_record_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Enable edit/delete when a history entry is selected
        self._history_list.currentItemChanged.connect(self._on_history_selection_changed)

    def refresh_theme_icons(self) -> None:
        """Theme-switch hook: (re-)tint the rotation status icon (#310)."""
        status = self._current_status
        if status is None:
            self._status_icon.hide()
            return
        pixmap = get_pixmap(_STATUS_ICONS.get(status, "help"), 16, color=_status_color(status))
        if pixmap is not None:
            self._status_icon.setPixmap(pixmap)
        self._status_icon.show()

    def _display_recommendation(
        self, rec: RotationRecommendation, item: object
    ) -> None:
        """Populate the panel with recommendation data."""
        color = _status_color(rec.status)
        self._current_status = rec.status
        self.refresh_theme_icons()

        # Bed name
        bed_name = getattr(item, "name", "") or self.tr("Unnamed Bed")
        status_text = {
            RotationStatus.GOOD: self.tr("Good Rotation"),
            RotationStatus.SUBOPTIMAL: self.tr("Suboptimal Rotation"),
            RotationStatus.VIOLATION: self.tr("Rotation Violation"),
            RotationStatus.UNKNOWN: self.tr("No History"),
        }.get(rec.status, "")

        self._status_label.setText(f"{bed_name}: {status_text}")
        self._status_label.setStyleSheet(
            f"font-weight: bold; color: {color}; font-size: 12px;"
        )

        # Recommendation reason (translate known service strings). When there is
        # no history but a succession plan exists, replace the bare
        # "every crop is suitable" wording with an unambiguous statement: the
        # advice cannot see the plan (issue #378). The plain reason stays when
        # no plan exists (regression).
        if rec.status is RotationStatus.UNKNOWN and self._has_succession_plan():
            self._recommendation_label.setText(
                self.tr(
                    "No planting history yet, so the rotation advice cannot see "
                    "this bed's planned crops. See the succession plan below."
                )
            )
        else:
            self._recommendation_label.setText(self._translate_reason(rec.reason))

        # Suggested demand
        demand_text = _demand_label(rec.suggested_demand)
        self._suggest_label.setText(
            self.tr("Next: %1").replace("%1", demand_text)
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
            demand_short = _demand_label(record.nutrient_demand)
            season_text = _season_label(record.season)
            text = (
                f"{record.year} {season_text}: "
                f"{record.common_name or record.species_name}"
            )
            if record.family:
                text += f" ({record.family})"
            if demand_short:
                text += f" \u2014 {demand_short}"

            entry = QListWidgetItem(text)
            entry.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            entry.setData(Qt.ItemDataRole.UserRole, record)
            self._history_list.addItem(entry)

        if self._history_list.count() == 0:
            placeholder = QListWidgetItem(self.tr("(no records yet)"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(self.palette().placeholderText())
            self._history_list.addItem(placeholder)

    def _on_history_selection_changed(self) -> None:
        """Enable/disable edit and delete buttons based on selection."""
        current = self._history_list.currentItem()
        has_record = (
            current is not None
            and current.data(Qt.ItemDataRole.UserRole) is not None
        )
        self._edit_record_btn.setEnabled(has_record)
        self._delete_record_btn.setEnabled(has_record)

    # ------------------------------------------------------------------
    # Succession plan section (issue #378) — display-only, never history
    # ------------------------------------------------------------------

    def _hide_succession_plan(self) -> None:
        """Hide the succession-plan section."""
        self._plan_list.clear()
        self._plan_header.hide()
        self._plan_note.hide()
        self._plan_list.hide()

    def _has_succession_plan(self) -> bool:
        """True when the current bed carries a succession plan."""
        pm = self._project_manager
        if pm is None or self._current_area_id is None:
            return False
        plans = getattr(pm, "succession_plans", None)
        if not isinstance(plans, dict):
            return False
        return bool(plans.get(self._current_area_id))

    def _display_succession_plan(self, area_id: str) -> None:
        """Show the bed's succession plan as 'planned this season', not history.

        Reads ``ProjectManager.succession_plans`` directly. It deliberately does
        NOT feed the plan into :class:`CropRotationService`: succession slots are
        *planned*, not *grown*, and counting them as history would change the
        service's cross-year cooldown semantics for every caller (issue #378
        option 2, rejected — see the ADR).
        """
        pm = self._project_manager
        plans = getattr(pm, "succession_plans", None) if pm is not None else None
        raw = plans.get(area_id) if isinstance(plans, dict) else None
        if not raw:
            self._hide_succession_plan()
            return

        from open_garden_planner.models.succession import SuccessionPlan

        try:
            plan = SuccessionPlan.from_dict(raw)
        except (AttributeError, TypeError, ValueError):
            self._hide_succession_plan()
            return

        self._plan_list.clear()
        for entry in plan.entries_sorted():
            label = entry.common_name or entry.scientific_name or entry.species_key
            family = self._resolve_family(entry.species_key, entry.scientific_name)
            text = f"{label} \u2014 {family}" if family else self.tr(
                "{name} \u2014 family unknown"
            ).replace("{name}", label)
            item = QListWidgetItem(text)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._plan_list.addItem(item)

        if self._plan_list.count() == 0:
            placeholder = QListWidgetItem(self.tr("(plan has no crop slots)"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(self.palette().placeholderText())
            self._plan_list.addItem(placeholder)

        self._plan_header.show()
        self._plan_note.show()
        self._plan_list.show()

    @staticmethod
    def _resolve_family(species_key: str, scientific_name: str) -> str:
        """Botanical family for a succession entry, or '' when unresolvable.

        The bundled DB is the only family source available to the panel; an
        API-imported species has no bundled record, so it degrades to '' and the
        row says "family unknown" rather than being dropped.
        """
        from open_garden_planner.services.bundled_species_db import (
            get_species_entry,
            lookup_species,
        )

        record = None
        if species_key:
            record = lookup_species(species_key)
        if record is None and scientific_name:
            record = get_species_entry(scientific_name)
        if record is None:
            return ""
        return str(record.get("family", "") or "")

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
                self.update_for_bed(self._cached_item, self._current_area_id)

    def _on_edit_record(self) -> None:
        """Edit the selected planting record."""
        current = self._history_list.currentItem()
        if current is None:
            return
        old_record = current.data(Qt.ItemDataRole.UserRole)
        if old_record is None:
            return

        from open_garden_planner.ui.dialogs.add_planting_record_dialog import (
            AddPlantingRecordDialog,
        )

        dialog = AddPlantingRecordDialog(
            self._current_area_id or "", parent=self, record=old_record
        )
        if dialog.exec():
            new_record = dialog.get_record()
            if new_record is not None:
                self._service.history.remove_record(old_record)
                self._service.history.add_record(new_record)
                self._save_history()
                self.update_for_bed(self._cached_item, self._current_area_id)

    def _on_delete_record(self) -> None:
        """Delete the selected planting record after confirmation."""
        current = self._history_list.currentItem()
        if current is None:
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        if record is None:
            return

        reply = QMessageBox.question(
            self,
            self.tr("Delete Record"),
            self.tr("Delete this planting record?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.history.remove_record(record)
            self._save_history()
            self.update_for_bed(self._cached_item, self._current_area_id)

    def _translate_reason(self, reason: str) -> str:
        """Translate known English reason strings from the service."""
        # Exact-match translations for known service reason strings
        known = {
            "No planting history \u2014 any crop is suitable.":
                self.tr("No planting history \u2014 any crop is suitable."),
            "Only one season recorded \u2014 rotation looks fine.":
                self.tr("Only one season recorded \u2014 rotation looks fine."),
            "Good rotation \u2014 diverse families and balanced demands.":
                self.tr("Good rotation \u2014 diverse families and balanced demands."),
        }
        if reason in known:
            return known[reason]

        # Pattern-based translations for dynamic strings
        import re

        # "After 'X' feeder, expected 'Y' but got 'Z'."
        m = re.match(
            r"After '(\w+)' feeder, expected '(\w+)' but got '(\w+)'\.", reason
        )
        if m:
            return self.tr(
                "After '%1' feeder, expected '%2' but got '%3'."
            ).replace("%1", _demand_label(m.group(1))).replace(
                "%2", _demand_label(m.group(2))
            ).replace("%3", _demand_label(m.group(3)))

        # "X planted in consecutive seasons — rotate to a different family."
        m = re.match(
            r"(.+?) planted in consecutive seasons", reason
        )
        if m:
            return self.tr(
                "%1 planted in consecutive seasons \u2014 rotate to a different family."
            ).replace("%1", m.group(1))

        # "X appears multiple times in the last N years."
        m = re.match(
            r"(.+?) appears multiple times in the last (\d+) years\.", reason
        )
        if m:
            return self.tr(
                "%1 appears multiple times in the last %2 years."
            ).replace("%1", m.group(1)).replace("%2", m.group(2))

        # Fallback: return untranslated
        return reason

    def _save_history(self) -> None:
        """Persist the rotation history to the project file."""
        if self._project_manager is not None:
            self._project_manager.set_crop_rotation(
                self._service.history.to_dict()
            )
