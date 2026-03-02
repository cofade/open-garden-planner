"""Seed Inventory Management Dialog — US-9.3.

Provides a QDialog for browsing, adding, editing, and deleting seed packets
stored in the global SeedInventoryStore.  A separate SeedPacketEditDialog
handles the add/edit form.
"""
from __future__ import annotations

import datetime
from typing import Any

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.seed_inventory import (
    SeedInventoryStore,
    SeedPacket,
    SeedViabilityDB,
    ViabilityStatus,
    get_seed_inventory,
    get_viability_db,
)

# ── Viability colours ───────────────────────────────────────────────────────────

_STATUS_COLORS: dict[ViabilityStatus, QColor] = {
    ViabilityStatus.GOOD:    QColor(210, 240, 210),   # light green
    ViabilityStatus.REDUCED: QColor(255, 243, 200),   # light amber
    ViabilityStatus.EXPIRED: QColor(255, 220, 220),   # light red
    ViabilityStatus.UNKNOWN: QColor(230, 230, 230),   # light grey
}

_STATUS_TEXT_COLORS: dict[ViabilityStatus, QColor] = {
    ViabilityStatus.GOOD:    QColor(30, 130, 30),
    ViabilityStatus.REDUCED: QColor(160, 100, 0),
    ViabilityStatus.EXPIRED: QColor(180, 30, 30),
    ViabilityStatus.UNKNOWN: QColor(100, 100, 100),
}

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

class _SeedTableModel(QAbstractTableModel):
    """Table model backed by a list of SeedPacket objects."""

    def __init__(self, store: SeedInventoryStore, viability_db: SeedViabilityDB) -> None:
        super().__init__()
        self._store = store
        self._db = viability_db
        self._packets: list[SeedPacket] = []
        self._current_year = datetime.date.today().year
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
            return QBrush(_STATUS_COLORS.get(status, QColor(255, 255, 255)))

        if role == Qt.ItemDataRole.ForegroundRole and col == _COL_VIABILITY:
            return QBrush(_STATUS_TEXT_COLORS.get(status, QColor(0, 0, 0)))

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
            labels = {
                ViabilityStatus.GOOD:    "✓ Good",
                ViabilityStatus.REDUCED: "~ Reduced",
                ViabilityStatus.EXPIRED: "✗ Expired",
                ViabilityStatus.UNKNOWN: "? Unknown",
            }
            return labels.get(status, "")
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


# ── Main dialog ─────────────────────────────────────────────────────────────────

class SeedInventoryDialog(QDialog):
    """Dialog for managing the global seed packet inventory."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Seed Inventory"))
        self.setMinimumSize(900, 600)
        self.resize(1000, 650)

        self._store = get_seed_inventory()
        self._db = get_viability_db()
        self._model = _SeedTableModel(self._store, self._db)

        self._setup_ui()
        self._update_headers()
        self._update_stats()

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Title + stats bar
        top = QHBoxLayout()
        title_lbl = QLabel(self.tr("Seed Inventory"))
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        top.addWidget(title_lbl)
        top.addStretch()
        self._stats_lbl = QLabel()
        self._stats_lbl.setStyleSheet("color: palette(text); font-size: 9pt;")
        top.addWidget(self._stats_lbl)
        layout.addLayout(top)

        # Search + filter bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(self.tr("Search by name or variety…"))
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._search_edit, 2)

        filter_row.addWidget(QLabel(self.tr("Status:")))
        self._status_combo = QComboBox()
        self._status_combo.addItem(self.tr("All"), "all")
        self._status_combo.addItem(self.tr("Good"), "good")
        self._status_combo.addItem(self.tr("Reduced"), "reduced")
        self._status_combo.addItem(self.tr("Expired"), "expired")
        self._status_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._status_combo)

        filter_row.addWidget(QLabel(self.tr("Year:")))
        self._year_combo = QComboBox()
        self._year_combo.addItem(self.tr("All years"), "all")
        self._year_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._year_combo)

        layout.addLayout(filter_row)

        # Table view
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)  # search all columns

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(False)  # handled by viability colors
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._on_edit)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_VARIETY, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_YEAR, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_QUANTITY, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_VIABILITY, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_MANUFACTURER, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_NOTES, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._add_btn = QPushButton(self.tr("Add Packet"))
        self._add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(self._add_btn)

        self._edit_btn = QPushButton(self.tr("Edit"))
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(self._edit_btn)

        self._delete_btn = QPushButton(self.tr("Delete"))
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._delete_btn)

        btn_row.addStretch()

        close_btn = QPushButton(self.tr("Close"))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _update_headers(self) -> None:
        self._model.set_headers([
            self.tr("Species"),
            self.tr("Variety"),
            self.tr("Year"),
            self.tr("Quantity"),
            self.tr("Viability"),
            self.tr("Manufacturer"),
            self.tr("Notes"),
        ])

    def _update_stats(self) -> None:
        """Refresh the stats label and year filter combo."""
        packets = self._store.all()
        total = len(packets)
        year = datetime.date.today().year
        expired = sum(1 for p in packets if p.viability_status(year, self._db) == ViabilityStatus.EXPIRED)
        reduced = sum(1 for p in packets if p.viability_status(year, self._db) == ViabilityStatus.REDUCED)
        self._stats_lbl.setText(
            self.tr("%1 packets · %2 reduced · %3 expired")
            .replace("%1", str(total))
            .replace("%2", str(reduced))
            .replace("%3", str(expired))
        )
        # Rebuild year filter
        years = sorted({p.purchase_year for p in packets}, reverse=True)
        prev = self._year_combo.currentData()
        self._year_combo.blockSignals(True)
        self._year_combo.clear()
        self._year_combo.addItem(self.tr("All years"), "all")
        for yr in years:
            self._year_combo.addItem(str(yr), yr)
        # Restore selection
        idx = self._year_combo.findData(prev)
        if idx >= 0:
            self._year_combo.setCurrentIndex(idx)
        self._year_combo.blockSignals(False)

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _apply_filter(self) -> None:
        search_text = self._search_edit.text().strip()
        status_filter = self._status_combo.currentData()
        year_filter = self._year_combo.currentData()

        # Build a combined proxy: we need custom filtering for status+year
        # We'll use a custom filter function via QSortFilterProxyModel override
        # but since QSortFilterProxyModel doesn't support multi-column easily,
        # we implement it by using filterAcceptsRow on a subclass.
        # For simplicity, use the text filter from Qt and post-filter status/year
        # by rebuilding rows in the model directly.
        self._proxy.setFilterFixedString(search_text)
        self._proxy.setFilterKeyColumn(-1)

        # Status + year filtering: rebuild model data from store with pre-filter
        packets = self._store.all()
        year = datetime.date.today().year
        if status_filter and status_filter != "all":
            wanted = {
                "good": ViabilityStatus.GOOD,
                "reduced": ViabilityStatus.REDUCED,
                "expired": ViabilityStatus.EXPIRED,
            }.get(status_filter)
            if wanted:
                packets = [p for p in packets if p.viability_status(year, self._db) == wanted]
        if year_filter and year_filter != "all":
            packets = [p for p in packets if p.purchase_year == year_filter]

        self._model.beginResetModel()
        self._model._packets = packets
        self._model.endResetModel()

        # Re-apply text search on top
        self._proxy.setFilterFixedString(search_text)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        has_sel = bool(self._table.selectionModel().selectedRows())
        self._edit_btn.setEnabled(has_sel)
        self._delete_btn.setEnabled(has_sel)

    def _selected_packet(self) -> SeedPacket | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        src_index = self._proxy.mapToSource(rows[0])
        return self._model.packet_at(src_index.row())

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        dlg = SeedPacketEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            packet = dlg.get_packet()
            self._store.add(packet)
            self._store.save()
            self._reload()

    def _on_edit(self) -> None:
        packet = self._selected_packet()
        if packet is None:
            return
        dlg = SeedPacketEditDialog(packet=packet, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_packet()
            self._store.add(updated)
            self._store.save()
            self._reload()

    def _on_delete(self) -> None:
        packet = self._selected_packet()
        if packet is None:
            return
        name = packet.species_name or self.tr("this packet")
        answer = QMessageBox.question(
            self,
            self.tr("Delete Seed Packet"),
            self.tr("Delete '%1'? This cannot be undone.").replace("%1", name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._store.remove(packet.id)
            self._store.save()
            self._reload()

    def _reload(self) -> None:
        self._model._reload()
        self._update_stats()
        self._apply_filter()
        self._on_selection_changed()


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
