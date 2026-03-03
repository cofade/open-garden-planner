"""Seed inventory table model and packet edit dialog — US-9.3.

SeedTableModel: shared table model used by SeedInventoryView (tab).
SeedPacketEditDialog: add/edit form for a single seed packet.
"""
from __future__ import annotations

import datetime
from typing import Any

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.seed_inventory import (
    SeedInventoryStore,
    SeedPacket,
    SeedViabilityDB,
    ViabilityStatus,
)

# ── Viability colours — separate palettes for light and dark mode ───────────────

_STATUS_BG_LIGHT: dict[ViabilityStatus, QColor] = {
    ViabilityStatus.GOOD:    QColor(210, 240, 210),
    ViabilityStatus.REDUCED: QColor(255, 243, 200),
    ViabilityStatus.EXPIRED: QColor(255, 220, 220),
    ViabilityStatus.UNKNOWN: QColor(230, 230, 230),
}
_STATUS_BG_DARK: dict[ViabilityStatus, QColor] = {
    ViabilityStatus.GOOD:    QColor(20,  60,  20),
    ViabilityStatus.REDUCED: QColor(65,  45,   0),
    ViabilityStatus.EXPIRED: QColor(75,  18,  18),
    ViabilityStatus.UNKNOWN: QColor(45,  45,  45),
}
_STATUS_FG_LIGHT: dict[ViabilityStatus, QColor] = {
    ViabilityStatus.GOOD:    QColor(25, 120,  25),
    ViabilityStatus.REDUCED: QColor(155,  90,   0),
    ViabilityStatus.EXPIRED: QColor(175,  25,  25),
    ViabilityStatus.UNKNOWN: QColor(100, 100, 100),
}
_STATUS_FG_DARK: dict[ViabilityStatus, QColor] = {
    ViabilityStatus.GOOD:    QColor(100, 220, 100),
    ViabilityStatus.REDUCED: QColor(240, 180,  50),
    ViabilityStatus.EXPIRED: QColor(240,  80,  80),
    ViabilityStatus.UNKNOWN: QColor(160, 160, 160),
}


def _is_dark_palette() -> bool:
    """Return True when the application is running with a dark palette."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().window().color().lightness() < 128


def _status_bg(status: ViabilityStatus) -> QColor:
    table = _STATUS_BG_DARK if _is_dark_palette() else _STATUS_BG_LIGHT
    return table.get(status, QColor(128, 128, 128))


def _status_fg(status: ViabilityStatus) -> QColor:
    table = _STATUS_FG_DARK if _is_dark_palette() else _STATUS_FG_LIGHT
    return table.get(status, QColor(200, 200, 200))

# Column indices
_COL_NAME = 0
_COL_VARIETY = 1
_COL_YEAR = 2
_COL_QUANTITY = 3
_COL_VIABILITY = 4
_COL_MANUFACTURER = 5
_COL_NOTES = 6
_NUM_COLS = 7


# ── Table model ─────────────────────────────────────────────────────────────────

class SeedTableModel(QAbstractTableModel):
    """Table model backed by a list of SeedPacket objects."""

    # Default (English) viability labels — overridden via set_viability_labels()
    _DEFAULT_VIA_LABELS: dict[ViabilityStatus, str] = {
        ViabilityStatus.GOOD:    "✓ Good",
        ViabilityStatus.REDUCED: "~ Reduced",
        ViabilityStatus.EXPIRED: "✗ Expired",
        ViabilityStatus.UNKNOWN: "? Unknown",
    }

    def __init__(self, store: SeedInventoryStore, viability_db: SeedViabilityDB) -> None:
        super().__init__()
        self._store = store
        self._db = viability_db
        self._packets: list[SeedPacket] = []
        self._current_year = datetime.date.today().year
        self._viability_labels: dict[ViabilityStatus, str] = dict(self._DEFAULT_VIA_LABELS)
        self._reload()

    def _reload(self) -> None:
        self.beginResetModel()
        self._packets = self._store.all()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: ARG002, B008
        return len(self._packets)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: ARG002, B008
        return _NUM_COLS

    def packet_at(self, row: int) -> SeedPacket | None:
        if 0 <= row < len(self._packets):
            return self._packets[row]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row >= len(self._packets):
            return None
        packet = self._packets[row]
        status = packet.viability_status(self._current_year, self._db)

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_data(packet, col, status)

        if role == Qt.ItemDataRole.BackgroundRole:
            return QBrush(_status_bg(status))

        if role == Qt.ItemDataRole.ForegroundRole and col == _COL_VIABILITY:
            return QBrush(_status_fg(status))

        if role == Qt.ItemDataRole.FontRole and col == _COL_VIABILITY:
            f = QFont()
            f.setBold(True)
            return f

        if role == Qt.ItemDataRole.UserRole:
            return packet.id

        return None

    def _display_data(self, p: SeedPacket, col: int, status: ViabilityStatus) -> str:
        if col == _COL_NAME:
            return p.species_name
        if col == _COL_VARIETY:
            return p.variety
        if col == _COL_YEAR:
            return str(p.purchase_year)
        if col == _COL_QUANTITY:
            if p.quantity == 0.0:
                return ""
            qty = int(p.quantity) if p.quantity == int(p.quantity) else p.quantity
            return f"{qty} {p.quantity_unit}"
        if col == _COL_VIABILITY:
            return self._viability_labels.get(status, "")
        if col == _COL_MANUFACTURER:
            return p.manufacturer
        if col == _COL_NOTES:
            return p.notes
        return ""

    def _col_header(self, col: int) -> str:
        headers = {
            _COL_NAME: "Species",
            _COL_VARIETY: "Variety",
            _COL_YEAR: "Year",
            _COL_QUANTITY: "Quantity",
            _COL_VIABILITY: "Viability",
            _COL_MANUFACTURER: "Manufacturer",
            _COL_NOTES: "Notes",
        }
        return headers.get(col, "")

    def set_headers(self, headers: list[str]) -> None:
        """Update column headers with translated strings."""
        self._translated_headers = headers
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, _NUM_COLS - 1)

    def set_viability_labels(self, labels: dict[ViabilityStatus, str]) -> None:
        """Update the viability display labels (for translation support)."""
        self._viability_labels = labels
        if self._packets:
            self.dataChanged.emit(
                self.index(0, _COL_VIABILITY),
                self.index(len(self._packets) - 1, _COL_VIABILITY),
            )

    def headerData(  # type: ignore[override]
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if hasattr(self, "_translated_headers") and section < len(self._translated_headers):
                return self._translated_headers[section]
            return self._col_header(section)
        return str(section + 1)


# ── Edit dialog ─────────────────────────────────────────────────────────────────

class SeedPacketEditDialog(QDialog):
    """Form dialog for creating or editing a single SeedPacket."""

    def __init__(
        self,
        packet: SeedPacket | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._packet = packet
        is_new = packet is None
        self.setWindowTitle(self.tr("Add Seed Packet") if is_new else self.tr("Edit Seed Packet"))
        self.setMinimumWidth(480)
        self._build_ui()
        if packet is not None:
            self._populate(packet)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Basic info ────────────────────────────────────────────────────────
        basic_group = QGroupBox(self.tr("Basic Information"))
        basic_form = QFormLayout(basic_group)
        basic_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(self.tr("e.g. Tomato"))
        basic_form.addRow(self.tr("Species name:"), self._name_edit)

        self._variety_edit = QLineEdit()
        self._variety_edit.setPlaceholderText(self.tr("e.g. Cherry Red"))
        basic_form.addRow(self.tr("Variety / cultivar:"), self._variety_edit)

        self._year_spin = QSpinBox()
        self._year_spin.setRange(1950, 2100)
        self._year_spin.setValue(datetime.date.today().year)
        basic_form.addRow(self.tr("Purchase / harvest year:"), self._year_spin)

        qty_row = QHBoxLayout()
        self._qty_spin = QDoubleSpinBox()
        self._qty_spin.setRange(0, 99999)
        self._qty_spin.setDecimals(1)
        self._qty_spin.setSingleStep(1)
        qty_row.addWidget(self._qty_spin)
        self._unit_combo = QComboBox()
        self._unit_combo.addItem(self.tr("seeds"), "seeds")
        self._unit_combo.addItem(self.tr("grams"), "grams")
        qty_row.addWidget(self._unit_combo)
        basic_form.addRow(self.tr("Quantity:"), qty_row)

        self._manufacturer_edit = QLineEdit()
        basic_form.addRow(self.tr("Manufacturer / source:"), self._manufacturer_edit)

        self._batch_edit = QLineEdit()
        basic_form.addRow(self.tr("Batch / lot number:"), self._batch_edit)

        layout.addWidget(basic_group)

        # ── Germination ───────────────────────────────────────────────────────
        germ_group = QGroupBox(self.tr("Germination"))
        germ_form = QFormLayout(germ_group)
        germ_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        temp_row = QHBoxLayout()
        self._temp_min = self._make_temp_spin()
        self._temp_opt = self._make_temp_spin()
        self._temp_max = self._make_temp_spin()
        temp_row.addWidget(QLabel(self.tr("Min:")))
        temp_row.addWidget(self._temp_min)
        temp_row.addWidget(QLabel(self.tr("Opt:")))
        temp_row.addWidget(self._temp_opt)
        temp_row.addWidget(QLabel(self.tr("Max:")))
        temp_row.addWidget(self._temp_max)
        germ_form.addRow(self.tr("Temp. range (°C):"), temp_row)

        days_row = QHBoxLayout()
        self._days_min = self._make_days_spin()
        self._days_max = self._make_days_spin()
        days_row.addWidget(QLabel(self.tr("Min:")))
        days_row.addWidget(self._days_min)
        days_row.addWidget(QLabel(self.tr("Max:")))
        days_row.addWidget(self._days_max)
        germ_form.addRow(self.tr("Germination days:"), days_row)

        self._light_combo = QComboBox()
        self._light_combo.addItem(self.tr("Indifferent"), None)
        self._light_combo.addItem(self.tr("Light germinator"), True)
        self._light_combo.addItem(self.tr("Dark germinator"), False)
        germ_form.addRow(self.tr("Light requirement:"), self._light_combo)

        layout.addWidget(germ_group)

        # ── Pre-treatment ─────────────────────────────────────────────────────
        pre_group = QGroupBox(self.tr("Pre-treatment"))
        pre_form = QFormLayout(pre_group)
        pre_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._cold_strat_cb = QCheckBox(self.tr("Cold stratification required"))
        pre_form.addRow("", self._cold_strat_cb)

        self._strat_days_spin = QSpinBox()
        self._strat_days_spin.setRange(1, 365)
        self._strat_days_spin.setValue(30)
        self._strat_days_spin.setEnabled(False)
        self._cold_strat_cb.toggled.connect(self._strat_days_spin.setEnabled)
        pre_form.addRow(self.tr("Stratification days:"), self._strat_days_spin)

        self._pretreat_edit = QLineEdit()
        self._pretreat_edit.setPlaceholderText(self.tr("e.g. scarify, soak 24h"))
        pre_form.addRow(self.tr("Other pre-treatment:"), self._pretreat_edit)

        layout.addWidget(pre_group)

        # ── Viability override ────────────────────────────────────────────────
        via_group = QGroupBox(self.tr("Viability Override"))
        via_form = QFormLayout(via_group)
        via_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        override_row = QHBoxLayout()
        self._override_cb = QCheckBox(self.tr("Override database shelf life"))
        override_row.addWidget(self._override_cb)
        self._override_spin = QSpinBox()
        self._override_spin.setRange(1, 50)
        self._override_spin.setValue(3)
        self._override_spin.setSuffix(self.tr(" years"))
        self._override_spin.setEnabled(False)
        self._override_cb.toggled.connect(self._override_spin.setEnabled)
        override_row.addWidget(self._override_spin)
        override_row.addStretch()
        via_form.addRow("", override_row)
        via_form.addRow(
            QLabel(self.tr("(Use this if you've tested germination and know the actual shelf life)"))
        )

        layout.addWidget(via_group)

        # ── Notes ─────────────────────────────────────────────────────────────
        notes_group = QGroupBox(self.tr("Notes"))
        notes_layout = QVBoxLayout(notes_group)
        self._notes_edit = QTextEdit()
        self._notes_edit.setMaximumHeight(80)
        notes_layout.addWidget(self._notes_edit)
        layout.addWidget(notes_group)

        # ── Dialog buttons ────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _make_temp_spin() -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(-20, 60)
        sb.setDecimals(1)
        sb.setSuffix("°")
        sb.setSpecialValueText("—")
        sb.setValue(sb.minimum())
        sb.setFixedWidth(70)
        return sb

    @staticmethod
    def _make_days_spin() -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(0, 365)
        sb.setSpecialValueText("—")
        sb.setValue(0)
        sb.setFixedWidth(60)
        return sb

    def _populate(self, p: SeedPacket) -> None:
        self._name_edit.setText(p.species_name)
        self._variety_edit.setText(p.variety)
        self._year_spin.setValue(p.purchase_year)
        self._qty_spin.setValue(p.quantity)
        idx = self._unit_combo.findData(p.quantity_unit)
        if idx >= 0:
            self._unit_combo.setCurrentIndex(idx)
        self._manufacturer_edit.setText(p.manufacturer)
        self._batch_edit.setText(p.batch_number)

        if p.germination_temp_min_c is not None:
            self._temp_min.setValue(p.germination_temp_min_c)
        if p.germination_temp_opt_c is not None:
            self._temp_opt.setValue(p.germination_temp_opt_c)
        if p.germination_temp_max_c is not None:
            self._temp_max.setValue(p.germination_temp_max_c)
        if p.germination_days_min is not None:
            self._days_min.setValue(p.germination_days_min)
        if p.germination_days_max is not None:
            self._days_max.setValue(p.germination_days_max)

        if p.light_germinator is not None:
            idx = self._light_combo.findData(p.light_germinator)
            if idx >= 0:
                self._light_combo.setCurrentIndex(idx)

        self._cold_strat_cb.setChecked(p.cold_stratification)
        if p.stratification_days is not None:
            self._strat_days_spin.setValue(p.stratification_days)
        self._pretreat_edit.setText(p.pre_treatment)

        if p.viability_shelf_life_override is not None:
            self._override_cb.setChecked(True)
            self._override_spin.setValue(p.viability_shelf_life_override)

        self._notes_edit.setPlainText(p.notes)

    def _on_accept(self) -> None:
        if not self._name_edit.text().strip():
            QMessageBox.warning(
                self,
                self.tr("Missing Information"),
                self.tr("Please enter a species name."),
            )
            return
        self.accept()

    def get_packet(self) -> SeedPacket:
        """Build and return a SeedPacket from the form values."""
        def _temp(sb: QDoubleSpinBox) -> float | None:
            return None if sb.value() == sb.minimum() else sb.value()

        def _days(sb: QSpinBox) -> int | None:
            return None if sb.value() == 0 else sb.value()

        existing_id = self._packet.id if self._packet else None
        import uuid
        packet_id = existing_id or str(uuid.uuid4())

        return SeedPacket(
            id=packet_id,
            species_name=self._name_edit.text().strip(),
            variety=self._variety_edit.text().strip(),
            purchase_year=self._year_spin.value(),
            quantity=self._qty_spin.value(),
            quantity_unit=self._unit_combo.currentData() or "seeds",
            manufacturer=self._manufacturer_edit.text().strip(),
            batch_number=self._batch_edit.text().strip(),
            germination_temp_min_c=_temp(self._temp_min),
            germination_temp_opt_c=_temp(self._temp_opt),
            germination_temp_max_c=_temp(self._temp_max),
            germination_days_min=_days(self._days_min),
            germination_days_max=_days(self._days_max),
            light_germinator=self._light_combo.currentData(),
            cold_stratification=self._cold_strat_cb.isChecked(),
            stratification_days=(
                self._strat_days_spin.value() if self._cold_strat_cb.isChecked() else None
            ),
            pre_treatment=self._pretreat_edit.text().strip(),
            notes=self._notes_edit.toPlainText().strip(),
            viability_shelf_life_override=(
                self._override_spin.value() if self._override_cb.isChecked() else None
            ),
        )
