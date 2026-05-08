"""Cross-bed amendment plan dialog (US-12.10c).

Garden → Amendment Plan… opens this dialog. It walks every bed in the scene,
computes amendment recommendations for each from its effective soil test,
groups results by substance, and shows totals in a single shopping-list view.

Aggregation logic now lives in
:mod:`open_garden_planner.services.shopping_list_service` so the totals
shown here match the Materials category in the US-12.6 Shopping List dialog.
The "Add to Shopping List" button hands off to that dialog when wired by the
caller; otherwise it falls back to copying a plain-text dump to the clipboard.
"""
from __future__ import annotations

from collections.abc import Callable
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

from open_garden_planner.services.shopping_list_service import (
    AggregatedAmendment,
    aggregate_amendments,
)
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.dialogs.soil_test_dialog import _amendment_display_lang

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


class AmendmentPlanDialog(QDialog):
    """Modal dialog showing the cross-bed amendment plan."""

    def __init__(
        self,
        parent: QWidget | None = None,
        canvas_scene: CanvasScene | None = None,
        soil_service: SoilService | None = None,
        on_add_to_shopping_list: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Amendment Plan"))
        self.setModal(True)
        self.resize(600, 400)

        self._canvas_scene = canvas_scene
        self._soil_service = soil_service
        self._on_add_to_shopping_list = on_add_to_shopping_list
        self._aggregated: list[AggregatedAmendment] = []

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

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)

        self._add_to_list_button = QPushButton(self.tr("Add to Shopping List"))
        self._add_to_list_button.clicked.connect(self._on_add_to_shopping_list_clicked)
        button_box.addButton(
            self._add_to_list_button, QDialogButtonBox.ButtonRole.ActionRole
        )

        self._copy_button = QPushButton(self.tr("Copy to clipboard"))
        self._copy_button.clicked.connect(self._on_copy_clicked)
        button_box.addButton(
            self._copy_button, QDialogButtonBox.ButtonRole.ActionRole
        )

        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    def _populate_table(self) -> None:
        """Compute aggregations from the scene and populate the table."""
        if self._canvas_scene is None or self._soil_service is None:
            self._aggregated = []
        else:
            self._aggregated = aggregate_amendments(
                self._canvas_scene, self._soil_service
            )
        self._table.setRowCount(len(self._aggregated))
        if not self._aggregated:
            self._empty_label.setVisible(True)
            self._copy_button.setEnabled(False)
            self._add_to_list_button.setEnabled(False)
            return
        self._empty_label.setVisible(False)
        self._copy_button.setEnabled(True)
        self._add_to_list_button.setEnabled(True)
        lang = _amendment_display_lang()
        for row, agg in enumerate(self._aggregated):
            self._table.setItem(
                row, 0, QTableWidgetItem(agg.amendment.display_name(lang))
            )
            self._table.setItem(
                row, 1, QTableWidgetItem(_format_quantity(agg.total_g))
            )
            self._table.setItem(
                row, 2, QTableWidgetItem(", ".join(agg.bed_names))
            )

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_copy_clicked(self) -> None:
        """Copy the plan as plain text to the system clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(self._build_clipboard_text())
        self._status_label.setText(self.tr("Amendment plan copied to clipboard."))

    def _on_add_to_shopping_list_clicked(self) -> None:
        """Hand off to the Shopping List dialog when wired by the host."""
        if self._on_add_to_shopping_list is None:
            self._status_label.setText(self.tr("Shopping list not available."))
            return
        self.accept()
        self._on_add_to_shopping_list()

    def _build_clipboard_text(self) -> str:
        """Render the aggregations as a tab-separated table for paste-into-spreadsheet."""
        lang = _amendment_display_lang()
        # Header row matches the visible column titles (kept in sync with _setup_ui).
        lines = [
            "\t".join(
                (self.tr("Substance"), self.tr("Total"), self.tr("Beds"))
            )
        ]
        for agg in self._aggregated:
            lines.append(
                "\t".join(
                    (
                        agg.amendment.display_name(lang),
                        _format_quantity(agg.total_g),
                        ", ".join(agg.bed_names),
                    )
                )
            )
        return "\n".join(lines)


def _format_quantity(grams: float) -> str:
    """Format a gram quantity. ≥1000 g shown in kg; else g."""
    if grams >= 1000.0:
        return f"{grams / 1000.0:.2f} kg"
    return f"{grams:.0f} g"


__all__ = ["AmendmentPlanDialog"]
