"""Garden-wide Harvest dashboard tab (US-C1, epic #188).

Aggregates every plant/bed harvest record into per-species, per-year totals and
renders them in a table, with a CSV export. The aggregation itself is delegated
to the pure, Qt-free :mod:`open_garden_planner.services.harvest_aggregation`;
this view only snapshots ``project_manager.harvest_logs`` and renders the rows.

Double-clicking a species row navigates to (and selects) that species on the
canvas, reusing the Tasks tab's ``navigate_to_species`` contract.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.app.paths import default_save_path
from open_garden_planner.services.harvest_aggregation import aggregate_by_species_year

# Refresh debounce — coalesce edit bursts to at most one regeneration/second.
_REFRESH_DEBOUNCE_MS = 1000


class HarvestView(QWidget):
    """The Harvest dashboard tab."""

    #: Switch to the canvas and select all items of this species key.
    navigate_to_species = pyqtSignal(str)

    def __init__(
        self,
        canvas_scene: Any,
        project_manager: Any,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene = canvas_scene
        self._pm = project_manager

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_REFRESH_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)

        self._build_ui()
        self.refresh()

    # ── setup ────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel(self.tr("Harvest"))
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self._export_btn = QPushButton(self.tr("Export CSV…"))
        self._export_btn.clicked.connect(self._on_export_csv)
        header.addWidget(self._export_btn)
        layout.addLayout(header)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            [
                self.tr("Species"),
                self.tr("Year"),
                self.tr("Total"),
                self.tr("Unit"),
                self.tr("Entries"),
            ]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.itemDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table)

        self._empty_label = QLabel(
            self.tr("No harvests logged yet. Right-click a plant → “Log Harvest…”.")
        )
        self._empty_label.setStyleSheet("color: #7f8c8d;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(self._status_label)

    # ── refresh ────────────────────────────────────────────────────────────────
    def schedule_refresh(self) -> None:
        """Coalesce refresh requests to at most one per second."""
        self._refresh_timer.start()

    def _on_refresh_timer(self) -> None:
        """Debounced refresh — skip the rebuild while the tab is hidden."""
        if not self.isVisible():
            return
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the harvest table from current project state."""
        rows = aggregate_by_species_year(self._pm.harvest_logs)
        self._table.setRowCount(0)
        for agg in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)

            species_item = QTableWidgetItem(agg.species_name)
            # Stash the real species key (empty for unkeyed targets) so a
            # double-click only navigates when there is a species to select.
            nav_key = "" if agg.species_key.startswith("target:") else agg.species_key
            species_item.setData(Qt.ItemDataRole.UserRole, nav_key)
            self._table.setItem(r, 0, species_item)

            year_item = QTableWidgetItem(str(agg.year))
            year_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(r, 1, year_item)

            total_item = QTableWidgetItem(f"{agg.total_quantity:g}")
            total_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(r, 2, total_item)

            self._table.setItem(r, 3, QTableWidgetItem(agg.unit))

            count_item = QTableWidgetItem(str(agg.entry_count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(r, 4, count_item)

        has_rows = self._table.rowCount() > 0
        self._table.setVisible(has_rows)
        self._empty_label.setVisible(not has_rows)
        self._export_btn.setEnabled(has_rows)

    # ── interactions ───────────────────────────────────────────────────────────
    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        species_item = self._table.item(item.row(), 0)
        if species_item is None:
            return
        key = species_item.data(Qt.ItemDataRole.UserRole)
        if key:
            self.navigate_to_species.emit(str(key))

    def _on_export_csv(self) -> None:
        from open_garden_planner.services.export_service import (  # noqa: PLC0415
            ExportService,
        )

        cur = getattr(self._pm, "current_file", None)
        path, _filter = QFileDialog.getSaveFileName(
            self,
            self.tr("Export Harvest Totals as CSV"),
            default_save_path("harvest.csv", cur),
            self.tr("CSV files (*.csv)"),
        )
        if not path:
            return
        try:
            count = ExportService.export_harvest_to_csv(self._pm.harvest_logs, path)
        except ValueError as exc:
            QMessageBox.critical(self, self.tr("Export failed"), str(exc))
            return
        self._status_label.setText(
            self.tr("Wrote {count} rows to {name}").format(
                count=count, name=Path(path).name
            )
        )


__all__ = ["HarvestView"]
