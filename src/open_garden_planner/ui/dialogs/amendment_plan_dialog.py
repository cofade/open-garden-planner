"""Cross-bed amendment plan dialog (US-12.10c).

Garden → Amendment Plan… opens this dialog. It walks every bed in the scene,
computes amendment recommendations for each from its effective soil test,
groups results by substance, and shows totals in a single shopping-list view.

The "Copy to clipboard" button writes plain text — a stand-in for the real
shopping-list integration that lands with US-12.6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.measurements import calculate_area_and_perimeter
from open_garden_planner.core.object_types import is_bed_type
from open_garden_planner.models.amendment import Amendment
from open_garden_planner.services.soil_service import SoilService

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


@dataclass
class _AggregatedAmendment:
    """Sum of one substance across all beds in the plan."""

    amendment: Amendment
    total_g: float = 0.0
    bed_names: list[str] = field(default_factory=list)


class AmendmentPlanDialog(QDialog):
    """Modal dialog showing the cross-bed amendment plan."""

    def __init__(
        self,
        parent: QWidget | None = None,
        canvas_scene: CanvasScene | None = None,
        soil_service: SoilService | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Amendment Plan"))
        self.setModal(True)
        self.resize(600, 400)

        self._canvas_scene = canvas_scene
        self._soil_service = soil_service
        self._aggregated: list[_AggregatedAmendment] = []

        self._setup_ui()
        self._populate_table()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._intro_label = QLabel(
            self.tr(
                "Recommended soil amendments aggregated across all beds with a "
                "deficient soil test. Quantities are totals — purchase rounded up "
                "and consult local extension advice before bulk application."
            )
        )
        self._intro_label.setWordWrap(True)
        layout.addWidget(self._intro_label)

        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels([
            self.tr("Substance"),
            self.tr("Total"),
            self.tr("Beds"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        self._empty_label = QLabel(self.tr("No deficient beds found."))
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        self._copy_button = QPushButton(self.tr("Copy to clipboard"))
        self._copy_button.clicked.connect(self._on_copy_clicked)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.addButton(
            self._copy_button, QDialogButtonBox.ButtonRole.ActionRole
        )
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    def _populate_table(self) -> None:
        """Compute aggregations from the scene and populate the table."""
        self._aggregated = self._aggregate_recommendations()
        self._table.setRowCount(len(self._aggregated))
        if not self._aggregated:
            self._empty_label.setVisible(True)
            self._copy_button.setEnabled(False)
            return
        self._empty_label.setVisible(False)
        self._copy_button.setEnabled(True)
        for row, agg in enumerate(self._aggregated):
            self._table.setItem(
                row, 0, QTableWidgetItem(agg.amendment.name)
            )
            self._table.setItem(
                row, 1, QTableWidgetItem(_format_quantity(agg.total_g))
            )
            self._table.setItem(
                row, 2, QTableWidgetItem(", ".join(agg.bed_names))
            )

    def _aggregate_recommendations(self) -> list[_AggregatedAmendment]:
        """Walk all beds and group amendment recommendations by substance."""
        if self._canvas_scene is None or self._soil_service is None:
            return []
        by_id: dict[str, _AggregatedAmendment] = {}
        for item in self._canvas_scene.items():
            object_type = getattr(item, "object_type", None)
            if not is_bed_type(object_type):
                continue
            target_id = str(getattr(item, "item_id", ""))
            if not target_id:
                continue
            area = _bed_area_m2(item)
            if area <= 0.0:
                continue
            record = self._soil_service.get_effective_record(target_id)
            recs = SoilService.calculate_amendments(
                record, bed_area_m2=area
            )
            if not recs:
                continue
            bed_name = str(getattr(item, "name", "") or self.tr("Bed"))
            for rec in recs:
                slot = by_id.setdefault(
                    rec.amendment.id, _AggregatedAmendment(amendment=rec.amendment)
                )
                slot.total_g += rec.quantity_g
                if bed_name not in slot.bed_names:
                    slot.bed_names.append(bed_name)
        return sorted(by_id.values(), key=lambda a: -a.total_g)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_copy_clicked(self) -> None:
        """Copy the plan as plain text to the system clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(self._build_clipboard_text())
        self._status_label.setText(self.tr("Amendment plan copied to clipboard."))

    def _build_clipboard_text(self) -> str:
        """Render the aggregations as a plain-text shopping list."""
        lines = [self.tr("Amendment Plan")]
        for agg in self._aggregated:
            beds = ", ".join(agg.bed_names)
            lines.append(
                f"- {agg.amendment.name}: {_format_quantity(agg.total_g)} ({beds})"
            )
        return "\n".join(lines)


def _bed_area_m2(item: object) -> float:
    """Return bed area in m², or 0.0 if the item type isn't supported."""
    result = calculate_area_and_perimeter(item)  # type: ignore[arg-type]
    if result is None:
        return 0.0
    area_cm2, _ = result
    return area_cm2 / 10_000.0


def _format_quantity(grams: float) -> str:
    """Format a gram quantity. ≥1000 g shown in kg; else g."""
    if grams >= 1000.0:
        return f"{grams / 1000.0:.2f} kg"
    return f"{grams:.0f} g"


__all__ = ["AmendmentPlanDialog"]
