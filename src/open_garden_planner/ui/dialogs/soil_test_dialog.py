"""Soil test entry dialog (US-12.10a).

Right-click a bed → "Add soil test…" or Garden → "Set default soil test…"
to open this dialog. On accept, ``result_record()`` returns a populated
``SoilTestRecord`` ready to be wrapped in an ``AddSoilTestCommand``.

Two entry modes:
  * Kit  — categorical Rapitest labels (Depleted/Deficient/...)
  * Lab  — numeric ppm input for each macronutrient

The categorical levels are always populated; in Lab mode the dialog also
records the raw ppm values on the record for later use by the amendment
calculator (US-12.10c). pH and notes apply to both modes.
"""
from __future__ import annotations

from datetime import date as _date
from typing import Any

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.amendment import AmendmentRecommendation
from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.widgets import SoilSparklineWidget

# Categorical labels for Rapitest scale. Index = stored level value.
# N/P share the 0–4 scale (Depleted/Deficient/Adequate/Sufficient/Surplus).
# K shares the same labels but no K0 — represented by skipping index 0 in the combo.
# Ca/Mg/S use Low/Medium/High (0–2).
_NPK_LABELS_KEY = ("Depleted", "Deficient", "Adequate", "Sufficient", "Surplus")
_SECONDARY_LABELS_KEY = ("Low", "Medium", "High")


class SoilTestDialog(QDialog):
    """Modal dialog for entering a single soil test record."""

    def __init__(
        self,
        parent: QWidget | None = None,
        target_id: str = "",
        target_name: str = "",
        existing_latest: SoilTestRecord | None = None,
        existing_history: SoilTestHistory | None = None,
        bed_area_m2: float = 0.0,
        edit_mode: bool = False,
        project_manager: Any | None = None,
        command_manager: Any | None = None,
    ) -> None:
        """Initialise the dialog.

        Args:
            parent: Parent widget for centring/modal behaviour.
            target_id: Bed UUID string or the literal ``"global"`` (informational).
            target_name: Human-readable name of the bed (used in the title); empty
                or ``"global"`` is displayed as the default-soil-test title.
            existing_latest: Optional record to pre-populate the form (e.g. when
                editing or re-opening for an existing target). In edit_mode this
                is the record being edited; its ``id`` is preserved on save.
            existing_history: Optional full history used to render the History
                tab (sparklines + past-tests list, US-12.10e). When ``None`` or
                empty the History tab shows placeholders. Ignored in edit_mode.
            bed_area_m2: Bed area in square metres. When > 0 the inline
                "Amendments for this bed" section is shown (US-12.10c). The
                global default test passes 0 to keep the section hidden.
            edit_mode: When True, the dialog is editing an existing record:
                History tab is hidden, the title reads "Edit Soil Test", and
                ``result_record()`` preserves ``existing_latest.id`` instead of
                generating a new uuid.
            project_manager: Optional ``ProjectManager`` — used by Edit/Delete
                buttons in the History tab to run undoable commands.
            command_manager: Optional command manager used to execute the Edit
                and Delete commands (issue #171).
        """
        super().__init__(parent)
        self._target_id = target_id
        self._bed_area_m2 = bed_area_m2
        self._edit_mode = edit_mode
        self._edit_record_id = existing_latest.id if (edit_mode and existing_latest) else None
        self._project_manager = project_manager
        self._command_manager = command_manager
        self._existing_history = existing_history

        if edit_mode:
            self.setWindowTitle(self.tr("Edit Soil Test"))
        elif not target_name or target_id == "global":
            self.setWindowTitle(self.tr("Default Soil Test"))
        else:
            self.setWindowTitle(self.tr("Soil Test — {name}").format(name=target_name))
        self.setModal(True)
        self.setMinimumWidth(450)

        self._setup_ui(existing_history)
        if existing_latest is not None:
            self._populate(existing_latest)
        self._refresh_amendments()

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self, existing_history: SoilTestHistory | None) -> None:
        layout = QVBoxLayout(self)

        if self._edit_mode:
            # Edit mode: no tabs, just the entry form.
            layout.addWidget(self._build_entry_tab())
        else:
            self._tabs = QTabWidget()
            self._tabs.addTab(self._build_entry_tab(), self.tr("Entry"))
            self._tabs.addTab(
                self._build_history_tab(existing_history), self.tr("History")
            )
            layout.addWidget(self._tabs)

        # OK / Cancel — at dialog level, outside the tabs.
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _build_entry_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        # Date row
        meta_form = QFormLayout()
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        today = _date.today()
        self._date_edit.setDate(QDate(today.year, today.month, today.day))
        meta_form.addRow(self.tr("Date"), self._date_edit)

        # Mode toggle (Kit categorical vs Lab ppm)
        self._mode_combo = QComboBox()
        self._mode_combo.addItem(self.tr("Kit (categorical)"), userData="kit")
        self._mode_combo.addItem(self.tr("Lab (ppm)"), userData="lab")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        meta_form.addRow(self.tr("Mode"), self._mode_combo)
        layout.addLayout(meta_form)

        # pH (shared between both modes)
        ph_form = QFormLayout()
        self._ph_spin = QDoubleSpinBox()
        self._ph_spin.setRange(0.0, 14.0)
        self._ph_spin.setDecimals(1)
        self._ph_spin.setSingleStep(0.1)
        self._ph_spin.setSpecialValueText(self.tr("—"))  # 0.0 = "not entered"
        self._ph_spin.setValue(0.0)
        ph_form.addRow(self.tr("pH (0–14)"), self._ph_spin)
        layout.addLayout(ph_form)

        # Stacked: index 0 = Kit (categorical combos), index 1 = Lab (ppm spins)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_kit_panel())
        self._stack.addWidget(self._build_lab_panel())
        layout.addWidget(self._stack)

        # Amendments for this bed (US-12.10c) — hidden when bed_area_m2 == 0.
        self._amendments_box = self._build_amendments_panel()
        if self._bed_area_m2 > 0.0:
            layout.addWidget(self._amendments_box)
        else:
            self._amendments_box.setVisible(False)

        # Wire any field that affects the recommendation list.
        self._ph_spin.valueChanged.connect(self._refresh_amendments)
        for combo in (
            self._n_combo, self._p_combo, self._k_combo,
            self._ca_combo, self._mg_combo, self._s_combo,
        ):
            combo.currentIndexChanged.connect(self._refresh_amendments)

        # Notes
        notes_label = QLabel(self.tr("Notes"))
        layout.addWidget(notes_label)
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setFixedHeight(80)
        layout.addWidget(self._notes_edit)

        return page

    def _build_history_tab(self, history: SoilTestHistory | None) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel(self.tr("Past tests")))

        # Container that we rebuild on edit/delete (issue #171).
        self._history_records_container = QWidget()
        self._history_records_layout = QVBoxLayout(self._history_records_container)
        self._history_records_layout.setContentsMargins(0, 0, 0, 0)
        self._history_records_layout.setSpacing(2)
        layout.addWidget(self._history_records_container)

        layout.addWidget(QLabel(self.tr("Trends")))
        self._sparklines: dict[str, SoilSparklineWidget] = {}
        for param, label in (
            ("ph", self.tr("pH")),
            ("n", self.tr("Nitrogen (N)")),
            ("p", self.tr("Phosphorus (P)")),
            ("k", self.tr("Potassium (K)")),
        ):
            row = QFormLayout()
            widget = SoilSparklineWidget(param)
            self._sparklines[param] = widget
            row.addRow(label, widget)
            layout.addLayout(row)

        layout.addStretch(1)
        scroll.setWidget(page)

        self._refresh_history_view(history)
        return scroll

    def _refresh_history_view(self, history: SoilTestHistory | None) -> None:
        """Rebuild the past-tests rows + sparklines from ``history`` (issue #171)."""
        # Clear existing rows
        while self._history_records_layout.count():
            item = self._history_records_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        records = list(history.records) if history is not None else []
        records_desc = sorted(records, key=lambda r: r.date, reverse=True)

        if not records_desc:
            self._history_records_layout.addWidget(
                QLabel(self.tr("No past tests yet"))
            )
        else:
            for rec in records_desc:
                self._history_records_layout.addWidget(self._build_history_row(rec))

        # Sparklines re-feed
        for widget in self._sparklines.values():
            widget.set_data(records)

        # Cache the latest history reference so edit/delete handlers can replay
        # off the current state instead of the original constructor arg.
        self._existing_history = history

    def _build_history_row(self, rec: SoilTestRecord) -> QWidget:
        """One row in the past-tests list: text + Edit + Delete buttons."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        label = QLabel(self._format_history_row(rec))
        label.setSizePolicy(
            label.sizePolicy().horizontalPolicy(),
            label.sizePolicy().verticalPolicy(),
        )
        h.addWidget(label, 1)

        # Edit/Delete only available when wired with a project + command manager.
        if self._project_manager is not None and self._command_manager is not None:
            edit_btn = QPushButton(self.tr("Edit"))
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, r=rec: self._on_edit_record(r))
            h.addWidget(edit_btn)

            del_btn = QPushButton(self.tr("Delete"))
            del_btn.setFixedWidth(60)
            del_btn.clicked.connect(lambda _, r=rec: self._on_delete_record(r))
            h.addWidget(del_btn)

        return row

    def _on_edit_record(self, rec: SoilTestRecord) -> None:
        """Open a sub-dialog in edit mode for ``rec`` (issue #171)."""
        sub = SoilTestDialog(
            parent=self,
            target_id=self._target_id,
            target_name="",
            existing_latest=rec,
            existing_history=None,
            bed_area_m2=self._bed_area_m2,
            edit_mode=True,
        )
        if sub.exec() != QDialog.DialogCode.Accepted:
            return
        from open_garden_planner.core import EditSoilTestCommand  # noqa: PLC0415

        new_record = sub.result_record()
        cmd = EditSoilTestCommand(self._project_manager, self._target_id, new_record)
        self._command_manager.execute(cmd)
        self._reload_history_after_change()

    def _on_delete_record(self, rec: SoilTestRecord) -> None:
        """Delete ``rec`` after a confirmation prompt (issue #171)."""
        prompt = self.tr("Delete the soil test from {date}?").format(
            date=rec.date or "?"
        )
        reply = QMessageBox.question(
            self,
            self.tr("Delete soil test"),
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from open_garden_planner.core import DeleteSoilTestCommand  # noqa: PLC0415

        cmd = DeleteSoilTestCommand(self._project_manager, self._target_id, rec.id)
        self._command_manager.execute(cmd)
        self._reload_history_after_change()

    def _reload_history_after_change(self) -> None:
        """Reload history from the project manager after edit/delete (issue #171).

        Also notify the parent application so it can refresh canvas overlays
        (mismatch borders, badges) — necessary because the user may then cancel
        the outer dialog without ever pressing OK.
        """
        if self._project_manager is None:
            return
        from open_garden_planner.models.soil_test import SoilTestHistory  # noqa: PLC0415

        raw = self._project_manager.soil_tests.get(self._target_id)
        history = SoilTestHistory.from_dict(raw) if raw else SoilTestHistory(
            target_id=self._target_id
        )
        self._refresh_history_view(history)
        # Best-effort canvas refresh — the parent (Application) usually owns a
        # canvas_view with refresh_soil_mismatches / refresh_soil_badges hooks.
        parent = self.parent()
        canvas_view = getattr(parent, "canvas_view", None)
        if canvas_view is not None:
            for refresh in ("refresh_soil_mismatches", "refresh_soil_badges"):
                fn = getattr(canvas_view, refresh, None)
                if callable(fn):
                    fn()
            calendar_view = getattr(parent, "calendar_view", None)
            if calendar_view is not None and hasattr(calendar_view, "refresh"):
                calendar_view.refresh()

    def _format_history_row(self, rec: SoilTestRecord) -> str:
        ph = f"{rec.ph:.1f}" if rec.ph is not None else self.tr("(no pH)")
        n = str(rec.n_level) if rec.n_level is not None else "—"
        p = str(rec.p_level) if rec.p_level is not None else "—"
        k = str(rec.k_level) if rec.k_level is not None else "—"
        return self.tr("{date} — pH {ph}, N{n} P{p} K{k}").format(
            date=rec.date or "?", ph=ph, n=n, p=p, k=k
        )

    def _build_kit_panel(self) -> QWidget:
        """Build the Kit-mode panel: categorical comboboxes for N/P/K and Ca/Mg/S."""
        panel = QGroupBox(self.tr("Kit (categorical)"))
        form = QFormLayout(panel)

        # NPK: 0–4 (K starts at 1 — represented by selecting "Deficient" minimum)
        self._n_combo = self._make_level_combo(_NPK_LABELS_KEY, allow_none=True)
        self._p_combo = self._make_level_combo(_NPK_LABELS_KEY, allow_none=True)
        self._k_combo = self._make_level_combo(_NPK_LABELS_KEY, allow_none=True, skip_first=True)
        form.addRow(self.tr("Nitrogen (N)"), self._n_combo)
        form.addRow(self.tr("Phosphorus (P)"), self._p_combo)
        form.addRow(self.tr("Potassium (K)"), self._k_combo)

        # Secondary nutrients (Ca/Mg/S): 0–2 Low/Medium/High
        self._ca_combo = self._make_level_combo(_SECONDARY_LABELS_KEY, allow_none=True)
        self._mg_combo = self._make_level_combo(_SECONDARY_LABELS_KEY, allow_none=True)
        self._s_combo = self._make_level_combo(_SECONDARY_LABELS_KEY, allow_none=True)
        form.addRow(self.tr("Calcium (Ca)"), self._ca_combo)
        form.addRow(self.tr("Magnesium (Mg)"), self._mg_combo)
        form.addRow(self.tr("Sulfur (S)"), self._s_combo)

        return panel

    def _build_lab_panel(self) -> QWidget:
        """Build the Lab-mode panel: numeric ppm spinboxes for each nutrient."""
        panel = QGroupBox(self.tr("Lab (ppm)"))
        form = QFormLayout(panel)

        self._n_ppm_spin = self._make_ppm_spin()
        self._p_ppm_spin = self._make_ppm_spin()
        self._k_ppm_spin = self._make_ppm_spin()
        self._ca_ppm_spin = self._make_ppm_spin()
        self._mg_ppm_spin = self._make_ppm_spin()
        self._s_ppm_spin = self._make_ppm_spin()
        form.addRow(self.tr("Nitrogen (N)"), self._n_ppm_spin)
        form.addRow(self.tr("Phosphorus (P)"), self._p_ppm_spin)
        form.addRow(self.tr("Potassium (K)"), self._k_ppm_spin)
        form.addRow(self.tr("Calcium (Ca)"), self._ca_ppm_spin)
        form.addRow(self.tr("Magnesium (Mg)"), self._mg_ppm_spin)
        form.addRow(self.tr("Sulfur (S)"), self._s_ppm_spin)

        return panel

    def _make_level_combo(
        self, labels: tuple[str, ...], *, allow_none: bool, skip_first: bool = False
    ) -> QComboBox:
        """Build a combobox whose ``userData`` is the integer level (or None).

        When ``skip_first`` is true the first label is omitted (used for K which
        has no K0 entry on the Rapitest kit).
        """
        combo = QComboBox()
        if allow_none:
            combo.addItem(self.tr("—"), userData=None)
        start = 1 if skip_first else 0
        for idx in range(start, len(labels)):
            combo.addItem(self.tr(labels[idx]), userData=idx)
        return combo

    def _build_amendments_panel(self) -> QGroupBox:
        """Build the inline 'Amendments for this bed' section (US-12.10c).

        Contains target spinboxes (pH, N, P, K) plus a list widget that
        recomputes from the form's current values whenever any field changes.
        """
        panel = QGroupBox(self.tr("Amendments for this bed"))
        layout = QVBoxLayout(panel)

        targets_form = QFormLayout()
        self._target_ph_spin = QDoubleSpinBox()
        self._target_ph_spin.setRange(4.0, 9.0)
        self._target_ph_spin.setDecimals(1)
        self._target_ph_spin.setSingleStep(0.1)
        self._target_ph_spin.setValue(6.5)
        self._target_ph_spin.valueChanged.connect(self._refresh_amendments)
        targets_form.addRow(self.tr("Target pH"), self._target_ph_spin)

        self._target_n_spin = self._make_target_level_spin()
        self._target_p_spin = self._make_target_level_spin()
        self._target_k_spin = self._make_target_level_spin()
        targets_form.addRow(self.tr("Target N"), self._target_n_spin)
        targets_form.addRow(self.tr("Target P"), self._target_p_spin)
        targets_form.addRow(self.tr("Target K"), self._target_k_spin)
        layout.addLayout(targets_form)

        self._amendments_list = QListWidget()
        self._amendments_list.setMinimumHeight(80)
        layout.addWidget(self._amendments_list)
        return panel

    def _make_target_level_spin(self) -> QSpinBox:
        """Build a 0–4 target spinbox (Rapitest scale) defaulted to 3 (Sufficient)."""
        spin = QSpinBox()
        spin.setRange(0, 4)
        spin.setValue(3)
        spin.valueChanged.connect(self._refresh_amendments)
        return spin

    @staticmethod
    def _make_ppm_spin() -> QDoubleSpinBox:
        """Build a ppm spinbox. 0.0 with special-value text means 'not entered'."""
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100000.0)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setSuffix(" ppm")
        spin.setSpecialValueText("—")
        spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        return spin

    # ── Behaviour ────────────────────────────────────────────────────────────

    def _on_mode_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    def _refresh_amendments(self) -> None:
        """Recompute and re-render the inline amendments list."""
        if self._bed_area_m2 <= 0.0:
            return
        record = self.result_record()
        recs = SoilService.calculate_amendments(
            record,
            target_ph=self._target_ph_spin.value(),
            target_n=self._target_n_spin.value(),
            target_p=self._target_p_spin.value(),
            target_k=self._target_k_spin.value(),
            bed_area_m2=self._bed_area_m2,
        )
        self._amendments_list.clear()
        if not recs:
            self._amendments_list.addItem(
                QListWidgetItem(self.tr("No deficiencies — soil is adequate."))
            )
            return
        for rec in recs:
            self._amendments_list.addItem(
                QListWidgetItem(format_amendment_line(rec, dialog=self))
            )

    def _populate(self, record: SoilTestRecord) -> None:
        """Pre-populate fields from an existing record."""
        if record.date:
            try:
                yyyy, mm, dd = (int(p) for p in record.date.split("-"))
                self._date_edit.setDate(QDate(yyyy, mm, dd))
            except (ValueError, TypeError):
                pass
        if record.ph is not None:
            self._ph_spin.setValue(record.ph)
        self._set_combo_value(self._n_combo, record.n_level)
        self._set_combo_value(self._p_combo, record.p_level)
        self._set_combo_value(self._k_combo, record.k_level)
        self._set_combo_value(self._ca_combo, record.ca_level)
        self._set_combo_value(self._mg_combo, record.mg_level)
        self._set_combo_value(self._s_combo, record.s_level)
        if record.n_ppm is not None:
            self._n_ppm_spin.setValue(record.n_ppm)
        if record.p_ppm is not None:
            self._p_ppm_spin.setValue(record.p_ppm)
        if record.k_ppm is not None:
            self._k_ppm_spin.setValue(record.k_ppm)
        if record.ca_ppm is not None:
            self._ca_ppm_spin.setValue(record.ca_ppm)
        if record.mg_ppm is not None:
            self._mg_ppm_spin.setValue(record.mg_ppm)
        if record.s_ppm is not None:
            self._s_ppm_spin.setValue(record.s_ppm)
        if record.notes:
            self._notes_edit.setPlainText(record.notes)
        # If any ppm value is set, default to Lab mode
        if any(
            getattr(record, k) is not None
            for k in ("n_ppm", "p_ppm", "k_ppm", "ca_ppm", "mg_ppm", "s_ppm")
        ):
            self._mode_combo.setCurrentIndex(1)

    @staticmethod
    def _set_combo_value(combo: QComboBox, level: int | None) -> None:
        """Select the combo entry whose userData matches ``level``."""
        for idx in range(combo.count()):
            if combo.itemData(idx) == level:
                combo.setCurrentIndex(idx)
                return

    # ── Public API ───────────────────────────────────────────────────────────

    def result_record(self) -> SoilTestRecord:
        """Return a ``SoilTestRecord`` populated from the dialog fields.

        In edit mode the existing record id is preserved so EditSoilTestCommand
        can update the record in place rather than appending a new one.
        """
        qd = self._date_edit.date()
        date_iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        ph = self._ph_spin.value()
        # 0.0 is the "not entered" sentinel (special-value text active)
        ph_value: float | None = ph if ph > 0.0 else None
        kwargs: dict[str, Any] = {
            "date": date_iso,
            "ph": ph_value,
            "n_level": self._n_combo.currentData(),
            "p_level": self._p_combo.currentData(),
            "k_level": self._k_combo.currentData(),
            "ca_level": self._ca_combo.currentData(),
            "mg_level": self._mg_combo.currentData(),
            "s_level": self._s_combo.currentData(),
            "n_ppm": self._ppm_value(self._n_ppm_spin),
            "p_ppm": self._ppm_value(self._p_ppm_spin),
            "k_ppm": self._ppm_value(self._k_ppm_spin),
            "ca_ppm": self._ppm_value(self._ca_ppm_spin),
            "mg_ppm": self._ppm_value(self._mg_ppm_spin),
            "s_ppm": self._ppm_value(self._s_ppm_spin),
            "notes": self._notes_edit.toPlainText().strip(),
        }
        if self._edit_record_id is not None:
            kwargs["id"] = self._edit_record_id
        return SoilTestRecord(**kwargs)

    @staticmethod
    def _ppm_value(spin: QDoubleSpinBox) -> float | None:
        """Return the ppm value, or None when the field is at the 'not entered' sentinel."""
        v = spin.value()
        return v if v > 0.0 else None

    # ── Test helpers ─────────────────────────────────────────────────────────

    def set_values(
        self,
        *,
        date: str | None = None,
        ph: float | None = None,
        n_level: int | None = None,
        p_level: int | None = None,
        k_level: int | None = None,
        ca_level: int | None = None,
        mg_level: int | None = None,
        s_level: int | None = None,
        notes: str | None = None,
    ) -> None:
        """Programmatic field-setter for tests."""
        if date is not None:
            try:
                yyyy, mm, dd = (int(p) for p in date.split("-"))
                self._date_edit.setDate(QDate(yyyy, mm, dd))
            except (ValueError, TypeError):
                pass
        if ph is not None:
            self._ph_spin.setValue(ph)
        if n_level is not None:
            self._set_combo_value(self._n_combo, n_level)
        if p_level is not None:
            self._set_combo_value(self._p_combo, p_level)
        if k_level is not None:
            self._set_combo_value(self._k_combo, k_level)
        if ca_level is not None:
            self._set_combo_value(self._ca_combo, ca_level)
        if mg_level is not None:
            self._set_combo_value(self._mg_combo, mg_level)
        if s_level is not None:
            self._set_combo_value(self._s_combo, s_level)
        if notes is not None:
            self._notes_edit.setPlainText(notes)


def format_amendment_line(
    rec: AmendmentRecommendation, dialog: QWidget | None = None
) -> str:
    """Render one ``AmendmentRecommendation`` as a localisable display string.

    ``dialog`` is used purely for ``self.tr`` lookup so the format strings get
    extracted with the dialog's translation context. Falls back to the
    English defaults from ``rec.rationale_en`` if no dialog is supplied.
    """
    name = rec.amendment.name
    qty = _format_quantity(rec.quantity_g)
    if dialog is None:
        return f"{name}: {qty} — {rec.rationale_en}"
    if rec.target_kind == "ph":
        if rec.target_value > rec.current_value:
            rationale = dialog.tr("Raises pH {cur:.1f} → {tgt:.1f}").format(
                cur=rec.current_value, tgt=rec.target_value
            )
        else:
            rationale = dialog.tr("Lowers pH {cur:.1f} → {tgt:.1f}").format(
                cur=rec.current_value, tgt=rec.target_value
            )
    else:
        nutrient = rec.target_kind.upper()
        rationale = dialog.tr("Raises {nutrient} level {cur} → {tgt}").format(
            nutrient=nutrient, cur=int(rec.current_value), tgt=int(rec.target_value)
        )
    return f"{name}: {qty} — {rationale}"


def _format_quantity(grams: float) -> str:
    """Format a gram quantity. ≥1000 g shown in kg; else g."""
    if grams >= 1000.0:
        return f"{grams / 1000.0:.2f} kg"
    return f"{grams:.0f} g"


__all__: list[str] = ["SoilTestDialog", "format_amendment_line"]
