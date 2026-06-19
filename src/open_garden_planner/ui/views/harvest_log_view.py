"""Garden-wide Harvest Log tab (US-C1, issue #188).

Shows per-crop, per-year yield totals aggregated from the project's harvest
logs, refreshed whenever ``harvest_logs_changed`` fires, with a CSV export
button. Crop names and the per-target CSV labels are resolved from the live
canvas scene.
"""
from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import (
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
from open_garden_planner.services.harvest_aggregation import aggregate_yields, all_years


def display_name_map(scene: Any) -> dict[str, str]:
    """Map each scene item's UUID string to a human label for harvest crops.

    Prefers the item's ``name``; falls back to the bound species' common name,
    then to a generic ``Plant`` label. Kept module-level so the export path can
    reuse the exact same resolution as the table.
    """
    names: dict[str, str] = {}
    if scene is None:
        return names
    for item in scene.items():
        item_id = getattr(item, "item_id", None)
        if item_id is None:
            continue
        label = (getattr(item, "name", "") or "").strip()
        if not label:
            metadata = getattr(item, "metadata", None) or {}
            species = metadata.get("plant_species") if isinstance(metadata, dict) else None
            if isinstance(species, dict):
                label = (species.get("common_name") or "").strip()
        names[str(item_id)] = label or "Plant"
    return names


class HarvestLogView(QWidget):
    """Dashboard tab presenting garden-wide yield totals (US-C1)."""

    def __init__(self, canvas_scene: Any, project_manager: Any) -> None:
        super().__init__()
        self._canvas_scene = canvas_scene
        self._project_manager = project_manager
        self._setup_ui()
        project_manager.harvest_logs_changed.connect(lambda _logs: self.refresh())
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header_row = QHBoxLayout()
        title = QLabel(self.tr("Harvest Yields"))
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_row.addWidget(title)
        header_row.addStretch(1)
        self._export_btn = QPushButton(self.tr("Export CSV…"))
        self._export_btn.clicked.connect(self._on_export_csv)
        header_row.addWidget(self._export_btn)
        layout.addLayout(header_row)

        self._empty_label = QLabel(self.tr("No harvests logged yet."))
        self._empty_label.setProperty("secondary", True)
        layout.addWidget(self._empty_label)

        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

    def refresh(self) -> None:
        """Rebuild the totals table from the current harvest logs."""
        logs = self._project_manager.harvest_logs
        rows = aggregate_yields(logs, display_name_map(self._canvas_scene))
        years = all_years(rows)

        self._empty_label.setVisible(not rows)
        self._table.setVisible(bool(rows))

        # Columns: Crop, Unit, <one per year>, Total
        headers = [self.tr("Crop"), self.tr("Unit")]
        headers += [str(y) for y in years]
        headers.append(self.tr("Total"))
        self._table.clear()
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(row.species))
            self._table.setItem(r, 1, QTableWidgetItem(row.unit))
            for c, year in enumerate(years, start=2):
                value = row.totals_by_year.get(year)
                text = f"{value:g}" if value is not None else ""
                self._table.setItem(r, c, QTableWidgetItem(text))
            self._table.setItem(
                r, len(headers) - 1, QTableWidgetItem(f"{row.total:g}")
            )

        header = self._table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _on_export_csv(self) -> None:
        from open_garden_planner.services.export_service import (  # noqa: PLC0415
            ExportService,
        )

        logs = self._project_manager.harvest_logs
        if not logs:
            QMessageBox.information(
                self,
                self.tr("Export Harvest Log"),
                self.tr("There are no harvests to export."),
            )
            return
        current_file = getattr(self._project_manager, "current_file", None)
        default_path = default_save_path("harvest_log.csv", current_file)
        path_str, _filter = QFileDialog.getSaveFileName(
            self, self.tr("Export Harvest Log"), default_path, self.tr("CSV files (*.csv)")
        )
        if not path_str:
            return
        try:
            count = ExportService.export_harvest_log_to_csv(
                logs, display_name_map(self._canvas_scene), path_str
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                self.tr("Export failed"),
                self.tr("Could not export harvest log: {err}").format(err=str(exc)),
            )
            return
        QMessageBox.information(
            self,
            self.tr("Export Harvest Log"),
            self.tr("Exported {count} harvest entries.").format(count=count),
        )


__all__ = ["HarvestLogView", "display_name_map"]
