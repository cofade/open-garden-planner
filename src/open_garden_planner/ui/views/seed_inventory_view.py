"""Seed Inventory tab view — US-9.4.

A full-screen QWidget tab showing the seed packet inventory with summary
statistics, quick-add, and batch operations (mark as used, delete multiple).
Shares SeedTableModel and SeedPacketEditDialog with the seed inventory dialog.
"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import QSortFilterProxyModel, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.seed_inventory import (
    SeedPacket,
    ViabilityStatus,
    get_seed_inventory,
    get_viability_db,
)
from open_garden_planner.ui.dialogs.seed_inventory_dialog import (
    _COL_MANUFACTURER,
    _COL_NAME,
    _COL_NOTES,
    _COL_QUANTITY,
    _COL_VARIETY,
    _COL_VIABILITY,
    _COL_YEAR,
    SeedPacketEditDialog,
    SeedTableModel,
)


def _needs_reorder(packet: SeedPacket) -> bool:
    """Return True when a packet is out of stock (quantity == 0)."""
    return packet.quantity == 0.0


class SeedInventoryView(QWidget):
    """Full-screen seed inventory tab view (US-9.4)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = get_seed_inventory()
        self._db = get_viability_db()
        self._model = SeedTableModel(self._store, self._db)
        self._setup_ui()
        self._update_headers()
        self._update_stats()

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload from the store — call when this tab becomes active."""
        self._reload()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # Title + stats bar
        top_row = QHBoxLayout()
        top_row.setSpacing(16)
        title_lbl = QLabel(self.tr("Seed Inventory"))
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        top_row.addWidget(title_lbl)
        top_row.addStretch()
        self._stats_lbl = QLabel()
        self._stats_lbl.setStyleSheet("color: palette(text); font-size: 9pt;")
        top_row.addWidget(self._stats_lbl)
        layout.addLayout(top_row)

        # Search + filter + quick-add button
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

        filter_row.addStretch()

        self._add_btn = QPushButton(self.tr("+ Add Packet"))
        self._add_btn.clicked.connect(self._on_add)
        filter_row.addWidget(self._add_btn)

        layout.addLayout(filter_row)

        # Table view (multi-selection)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
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

        # Batch action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._edit_btn = QPushButton(self.tr("Edit"))
        self._edit_btn.setEnabled(False)
        self._edit_btn.setToolTip(self.tr("Edit the selected seed packet"))
        self._edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(self._edit_btn)

        self._mark_used_btn = QPushButton(self.tr("Mark as Used"))
        self._mark_used_btn.setEnabled(False)
        self._mark_used_btn.setToolTip(self.tr("Set quantity to 0 for selected packets"))
        self._mark_used_btn.clicked.connect(self._on_mark_used)
        btn_row.addWidget(self._mark_used_btn)

        self._delete_btn = QPushButton(self.tr("Delete Selected"))
        self._delete_btn.setEnabled(False)
        self._delete_btn.setToolTip(self.tr("Delete all selected seed packets"))
        self._delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._delete_btn)

        btn_row.addStretch()
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
        self._model.set_viability_labels({
            ViabilityStatus.GOOD:    "✓ " + self.tr("Good"),
            ViabilityStatus.REDUCED: "~ " + self.tr("Reduced"),
            ViabilityStatus.EXPIRED: "✗ " + self.tr("Expired"),
            ViabilityStatus.UNKNOWN: "? " + self.tr("Unknown"),
        })

    def _update_stats(self) -> None:
        """Refresh the stats label and year filter combo."""
        packets = self._store.all()
        total = len(packets)
        year = datetime.date.today().year
        expired = sum(1 for p in packets if p.viability_status(year, self._db) == ViabilityStatus.EXPIRED)
        reorder = sum(1 for p in packets if _needs_reorder(p))
        self._stats_lbl.setText(
            self.tr("%1 packets · %2 expired · %3 out of stock")
            .replace("%1", str(total))
            .replace("%2", str(expired))
            .replace("%3", str(reorder))
        )
        # Rebuild year filter
        years = sorted({p.purchase_year for p in packets}, reverse=True)
        prev = self._year_combo.currentData()
        self._year_combo.blockSignals(True)
        self._year_combo.clear()
        self._year_combo.addItem(self.tr("All years"), "all")
        for yr in years:
            self._year_combo.addItem(str(yr), yr)
        idx = self._year_combo.findData(prev)
        if idx >= 0:
            self._year_combo.setCurrentIndex(idx)
        self._year_combo.blockSignals(False)

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _apply_filter(self) -> None:
        search_text = self._search_edit.text().strip()
        status_filter = self._status_combo.currentData()
        year_filter = self._year_combo.currentData()

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
        self._proxy.setFilterFixedString(search_text)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        count = len(rows)
        self._edit_btn.setEnabled(count == 1)
        self._mark_used_btn.setEnabled(count > 0)
        self._delete_btn.setEnabled(count > 0)

    def _selected_packets(self) -> list[SeedPacket]:
        rows = self._table.selectionModel().selectedRows()
        result: list[SeedPacket] = []
        for proxy_index in rows:
            src_index = self._proxy.mapToSource(proxy_index)
            packet = self._model.packet_at(src_index.row())
            if packet is not None:
                result.append(packet)
        return result

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        dlg = SeedPacketEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            packet = dlg.get_packet()
            self._store.add(packet)
            self._store.save()
            self._reload()

    def _on_edit(self) -> None:
        packets = self._selected_packets()
        if len(packets) != 1:
            return
        dlg = SeedPacketEditDialog(packet=packets[0], parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_packet()
            self._store.add(updated)
            self._store.save()
            self._reload()

    def _on_mark_used(self) -> None:
        packets = self._selected_packets()
        if not packets:
            return
        names = ", ".join(p.species_name for p in packets[:3])
        if len(packets) > 3:
            names += self.tr(" and %1 more").replace("%1", str(len(packets) - 3))
        answer = QMessageBox.question(
            self,
            self.tr("Mark as Used"),
            self.tr("Set quantity to 0 for %1?").replace(
                "%1", names if len(packets) > 1 else (packets[0].species_name or self.tr("this packet"))
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        import dataclasses
        for packet in packets:
            updated = dataclasses.replace(packet, quantity=0.0)
            self._store.add(updated)
        self._store.save()
        self._reload()

    def _on_delete(self) -> None:
        packets = self._selected_packets()
        if not packets:
            return
        if len(packets) == 1:
            name = packets[0].species_name or self.tr("this packet")
            msg = self.tr("Delete '%1'? This cannot be undone.").replace("%1", name)
        else:
            msg = self.tr("Delete %1 seed packets? This cannot be undone.").replace(
                "%1", str(len(packets))
            )
        answer = QMessageBox.question(
            self,
            self.tr("Delete Seed Packets"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for packet in packets:
            self._store.remove(packet.id)
        self._store.save()
        self._reload()

    def _reload(self) -> None:
        self._model._reload()
        self._update_stats()
        self._apply_filter()
        self._on_selection_changed()
