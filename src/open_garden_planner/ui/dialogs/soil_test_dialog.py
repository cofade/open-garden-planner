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

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.soil_test import SoilTestRecord

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
    ) -> None:
        """Initialise the dialog.

        Args:
            parent: Parent widget for centring/modal behaviour.
            target_id: Bed UUID string or the literal ``"global"`` (informational).
            target_name: Human-readable name of the bed (used in the title); empty
                or ``"global"`` is displayed as the default-soil-test title.
            existing_latest: Optional record to pre-populate the form (e.g. when
                editing or re-opening for an existing target).
        """
        super().__init__(parent)
        self._target_id = target_id

        if not target_name or target_id == "global":
            self.setWindowTitle(self.tr("Default Soil Test"))
        else:
            self.setWindowTitle(self.tr("Soil Test — {name}").format(name=target_name))
        self.setModal(True)
        self.setMinimumWidth(450)

        self._setup_ui()
        if existing_latest is not None:
            self._populate(existing_latest)

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

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

        # Notes
        notes_label = QLabel(self.tr("Notes"))
        layout.addWidget(notes_label)
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setFixedHeight(80)
        layout.addWidget(self._notes_edit)

        # OK / Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

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
        """Return a ``SoilTestRecord`` populated from the dialog fields."""
        qd = self._date_edit.date()
        date_iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        ph = self._ph_spin.value()
        # 0.0 is the "not entered" sentinel (special-value text active)
        ph_value: float | None = ph if ph > 0.0 else None
        return SoilTestRecord(
            date=date_iso,
            ph=ph_value,
            n_level=self._n_combo.currentData(),
            p_level=self._p_combo.currentData(),
            k_level=self._k_combo.currentData(),
            ca_level=self._ca_combo.currentData(),
            mg_level=self._mg_combo.currentData(),
            s_level=self._s_combo.currentData(),
            n_ppm=self._ppm_value(self._n_ppm_spin),
            p_ppm=self._ppm_value(self._p_ppm_spin),
            k_ppm=self._ppm_value(self._k_ppm_spin),
            ca_ppm=self._ppm_value(self._ca_ppm_spin),
            mg_ppm=self._ppm_value(self._mg_ppm_spin),
            s_ppm=self._ppm_value(self._s_ppm_spin),
            notes=self._notes_edit.toPlainText().strip(),
        )

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


__all__: list[str] = ["SoilTestDialog"]
