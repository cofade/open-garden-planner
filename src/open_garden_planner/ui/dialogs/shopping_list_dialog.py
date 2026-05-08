"""Shopping list dialog (US-12.6).

Garden → Shopping List… opens this modal. It groups items into Plants /
Seeds / Materials in one editable table, lets the user enter prices that
persist with the project, and exposes CSV / PDF / clipboard export.

The Materials category mirrors ``AmendmentPlanDialog`` totals — that dialog
now feeds into here via its "Add to Shopping List" button.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.app.settings import get_settings
from open_garden_planner.models.shopping_list import (
    ShoppingListCategory,
    ShoppingListItem,
)
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.pdf_report_service import PdfReportService
from open_garden_planner.ui.theme import ThemeColors

if TYPE_CHECKING:
    from open_garden_planner.services.shopping_list_service import ShoppingListService


# Column indexes — kept central so cell handlers stay readable.
# Column 0 is the "Have" checkbox: ticked rows stay visible (dimmed) but are
# excluded from CSV / PDF / clipboard exports and from the grand total.
_COL_HAVE = 0
_COL_ITEM = 1
_COL_QUANTITY = 2
_COL_UNIT = 3
_COL_SIZE = 4
_COL_PRICE = 5
_COL_TOTAL = 6
_COL_NOTES = 7


class ShoppingListDialog(QDialog):
    """Modal dialog displaying the shopping list with editable prices."""

    def __init__(
        self,
        service: ShoppingListService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Shopping List"))
        self.setModal(True)
        self.resize(820, 520)

        self._service = service
        self._items: list[ShoppingListItem] = []
        # Map row index → ShoppingListItem (None for category header rows).
        self._row_items: list[ShoppingListItem | None] = []
        self._suppress_changes = False
        # Translated once so we don't re-look up the same string per row.
        self._have_tooltip = self.tr(
            "Tick if you already have this item — excludes it from totals and exports."
        )

        self._setup_ui()
        self._populate_table()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            self.tr(
                "Items needed to realise the current plan. Enter prices to "
                "estimate the total cost — prices are saved with the project."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._table = QTableWidget(0, 8, self)
        self._table.setHorizontalHeaderLabels([
            self.tr("Have"),
            self.tr("Item"),
            self.tr("Quantity"),
            self.tr("Unit"),
            self.tr("Size"),
            self.tr("Price"),
            self.tr("Total"),
            self.tr("Notes"),
        ])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(_COL_HAVE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_ITEM, QHeaderView.ResizeMode.Stretch)
        for col in (_COL_QUANTITY, _COL_UNIT, _COL_SIZE, _COL_PRICE, _COL_TOTAL):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_NOTES, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table)

        self._empty_label = QLabel(
            self.tr("Shopping list is empty — place plants or run a soil test first.")
        )
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        self._grand_total_label = QLabel("")
        font = self._grand_total_label.font()
        font.setBold(True)
        self._grand_total_label.setFont(font)
        self._grand_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._grand_total_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)

        self._copy_button = QPushButton(self.tr("Copy to clipboard"))
        self._copy_button.clicked.connect(self._on_copy_clicked)
        button_box.addButton(self._copy_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._csv_button = QPushButton(self.tr("Export CSV…"))
        self._csv_button.clicked.connect(self._on_export_csv)
        button_box.addButton(self._csv_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._pdf_button = QPushButton(self.tr("Export PDF…"))
        self._pdf_button.clicked.connect(self._on_export_pdf)
        button_box.addButton(self._pdf_button, QDialogButtonBox.ButtonRole.ActionRole)

        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    # ── Population ────────────────────────────────────────────────────────────

    def _populate_table(self) -> None:
        self._items = self._service.build()
        # Group items per category preserving the build order.
        groups: dict[ShoppingListCategory, list[ShoppingListItem]] = {
            ShoppingListCategory.PLANTS: [],
            ShoppingListCategory.SEEDS: [],
            ShoppingListCategory.MATERIALS: [],
        }
        for item in self._items:
            groups[item.category].append(item)

        self._suppress_changes = True
        try:
            self._table.setRowCount(0)
            self._row_items = []
            row = 0
            any_rendered = False
            for category, label in (
                (ShoppingListCategory.PLANTS, self.tr("Plants")),
                (ShoppingListCategory.SEEDS, self.tr("Seeds")),
                (ShoppingListCategory.MATERIALS, self.tr("Materials")),
            ):
                items = groups[category]
                if not items:
                    continue
                any_rendered = True
                self._table.insertRow(row)
                self._set_category_header(row, label)
                self._row_items.append(None)
                row += 1
                for item in items:
                    self._table.insertRow(row)
                    self._set_data_row(row, item)
                    self._row_items.append(item)
                    row += 1

            self._empty_label.setVisible(not any_rendered)
            self._csv_button.setEnabled(any_rendered)
            self._pdf_button.setEnabled(any_rendered)
            self._copy_button.setEnabled(any_rendered)
        finally:
            self._suppress_changes = False
        self._update_grand_total()

    def _set_category_header(self, row: int, label: str) -> None:
        cell = QTableWidgetItem(label)
        font = QFont()
        font.setBold(True)
        cell.setFont(font)
        # Pull from the active palette so dark mode gets a readable sage stripe
        # instead of the light-pastel green that washes out on dark surfaces.
        colors = ThemeColors.get_colors(get_settings().theme_mode)
        cell.setBackground(QBrush(QColor(colors["section_header"])))
        cell.setForeground(QBrush(QColor(colors["text_primary"])))
        cell.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._table.setItem(row, 0, cell)
        self._table.setSpan(row, 0, 1, self._table.columnCount())

    def _set_data_row(self, row: int, item: ShoppingListItem) -> None:
        pm = self._service.project_manager
        excluded = pm.is_shopping_item_excluded(item.id)

        have_cell = QTableWidgetItem("")
        have_cell.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        )
        have_cell.setCheckState(
            Qt.CheckState.Checked if excluded else Qt.CheckState.Unchecked
        )
        have_cell.setToolTip(self._have_tooltip)

        name_cell = QTableWidgetItem(item.name)
        name_cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        qty_cell = QTableWidgetItem(f"{item.quantity:g}")
        qty_cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        unit_cell = QTableWidgetItem(item.unit)
        unit_cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        size_cell = QTableWidgetItem(item.size_descriptor)
        size_cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        price_cell = QTableWidgetItem(
            "" if item.price_each is None else f"{item.price_each:.2f}"
        )
        price_cell.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

        total_cell = QTableWidgetItem(self._format_total(item))
        total_cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        notes_cell = QTableWidgetItem(item.notes)
        notes_cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        self._table.setItem(row, _COL_HAVE, have_cell)
        self._table.setItem(row, _COL_ITEM, name_cell)
        self._table.setItem(row, _COL_QUANTITY, qty_cell)
        self._table.setItem(row, _COL_UNIT, unit_cell)
        self._table.setItem(row, _COL_SIZE, size_cell)
        self._table.setItem(row, _COL_PRICE, price_cell)
        self._table.setItem(row, _COL_TOTAL, total_cell)
        self._table.setItem(row, _COL_NOTES, notes_cell)

        if excluded:
            self._apply_excluded_style(row)

    @staticmethod
    def _format_total(item: ShoppingListItem) -> str:
        return "" if item.total_cost is None else f"{item.total_cost:.2f}"

    # ── Editing ───────────────────────────────────────────────────────────────

    def _on_item_changed(self, cell: QTableWidgetItem) -> None:
        if self._suppress_changes:
            return
        column = cell.column()
        row = cell.row()
        if row >= len(self._row_items):
            return
        item = self._row_items[row]
        if item is None:
            return
        if column == _COL_HAVE:
            self._on_have_toggled(row, item, cell)
            return
        if column != _COL_PRICE:
            return
        text = cell.text().strip().replace(",", ".")
        new_price: float | None
        if text == "":
            new_price = None
        else:
            try:
                new_price = float(text)
            except ValueError:
                self._status_label.setText(self.tr("Invalid price — ignored."))
                self._refresh_price_cell(row, item)
                return
            if new_price < 0:
                self._status_label.setText(self.tr("Invalid price — ignored."))
                self._service.update_price(item, None)
                self._refresh_price_cell(row, item)
                self._refresh_total_cell(row, item)
                self._update_grand_total()
                return
        self._service.update_price(item, new_price)
        self._refresh_total_cell(row, item)
        self._update_grand_total()

    def _on_have_toggled(
        self, row: int, item: ShoppingListItem, cell: QTableWidgetItem
    ) -> None:
        excluded = cell.checkState() == Qt.CheckState.Checked
        pm = self._service.project_manager
        pm.set_shopping_item_excluded(item.id, excluded)
        if excluded:
            self._apply_excluded_style(row)
        else:
            self._clear_excluded_style(row)
        self._update_grand_total()

    def _apply_excluded_style(self, row: int) -> None:
        """Dim every cell in ``row`` and strike through the Item cell."""
        self._suppress_changes = True
        try:
            colors = ThemeColors.get_colors(get_settings().theme_mode)
            faded = QBrush(QColor(colors["text_secondary"]))
            for col in (
                _COL_ITEM,
                _COL_QUANTITY,
                _COL_UNIT,
                _COL_SIZE,
                _COL_PRICE,
                _COL_TOTAL,
                _COL_NOTES,
            ):
                cell = self._table.item(row, col)
                if cell is not None:
                    cell.setForeground(faded)
            name_cell = self._table.item(row, _COL_ITEM)
            if name_cell is not None:
                font = name_cell.font()
                font.setStrikeOut(True)
                name_cell.setFont(font)
        finally:
            self._suppress_changes = False

    def _clear_excluded_style(self, row: int) -> None:
        """Restore default look for a row that was previously dimmed.

        Use the palette's ``text_primary`` brush rather than a default-
        constructed ``QBrush`` (which has ``Qt.NoBrush`` style and can leak
        through stylesheet selection rules to the wrong colour).
        """
        self._suppress_changes = True
        try:
            colors = ThemeColors.get_colors(get_settings().theme_mode)
            default_brush = QBrush(QColor(colors["text_primary"]))
            for col in (
                _COL_ITEM,
                _COL_QUANTITY,
                _COL_UNIT,
                _COL_SIZE,
                _COL_PRICE,
                _COL_TOTAL,
                _COL_NOTES,
            ):
                cell = self._table.item(row, col)
                if cell is not None:
                    cell.setForeground(default_brush)
            name_cell = self._table.item(row, _COL_ITEM)
            if name_cell is not None:
                font = name_cell.font()
                font.setStrikeOut(False)
                name_cell.setFont(font)
        finally:
            self._suppress_changes = False

    def _refresh_price_cell(self, row: int, item: ShoppingListItem) -> None:
        self._suppress_changes = True
        try:
            cell = self._table.item(row, _COL_PRICE)
            if cell is not None:
                cell.setText(
                    "" if item.price_each is None else f"{item.price_each:.2f}"
                )
        finally:
            self._suppress_changes = False

    def _refresh_total_cell(self, row: int, item: ShoppingListItem) -> None:
        self._suppress_changes = True
        try:
            cell = self._table.item(row, _COL_TOTAL)
            if cell is not None:
                cell.setText(self._format_total(item))
        finally:
            self._suppress_changes = False

    def _update_grand_total(self) -> None:
        priced = [
            i for i in self._exportable_items() if i.total_cost is not None
        ]
        if not priced:
            self._grand_total_label.setText("")
            return
        total = sum(i.total_cost or 0.0 for i in priced)
        self._grand_total_label.setText(
            self.tr("Grand total: {amount:.2f}").format(amount=total)
        )

    def _exportable_items(self) -> list[ShoppingListItem]:
        """Return only items the user hasn't ticked as already-owned."""
        pm = self._service.project_manager
        return [i for i in self._items if not pm.is_shopping_item_excluded(i.id)]

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_copy_clicked(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(self._build_clipboard_text())
        self._status_label.setText(self.tr("Shopping list copied to clipboard."))

    def _build_clipboard_text(self) -> str:
        headers = [
            self.tr("Category"),
            self.tr("Item"),
            self.tr("Quantity"),
            self.tr("Unit"),
            self.tr("Size"),
            self.tr("Price"),
            self.tr("Total"),
            self.tr("Notes"),
        ]
        lines = ["\t".join(headers)]
        for item in self._exportable_items():
            lines.append("\t".join([
                item.category.value,
                item.name,
                f"{item.quantity:g}",
                item.unit,
                item.size_descriptor,
                "" if item.price_each is None else f"{item.price_each:.2f}",
                self._format_total(item),
                item.notes,
            ]))
        return "\n".join(lines)

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export Shopping List as CSV"),
            "shopping_list.csv",
            self.tr("CSV files (*.csv)"),
        )
        if not path:
            return
        try:
            count = ExportService.export_shopping_list_to_csv(
                self._exportable_items(), path
            )
        except ValueError as exc:
            QMessageBox.critical(self, self.tr("Export failed"), str(exc))
            return
        self._status_label.setText(
            self.tr("Wrote {count} rows to {path}").format(count=count, path=Path(path).name)
        )

    def _on_export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export Shopping List as PDF"),
            "shopping_list.pdf",
            self.tr("PDF files (*.pdf)"),
        )
        if not path:
            return
        try:
            PdfReportService.export_shopping_list_to_pdf(
                self._exportable_items(), path
            )
        except (RuntimeError, OSError) as exc:
            QMessageBox.critical(self, self.tr("Export failed"), str(exc))
            return
        self._status_label.setText(
            self.tr("Wrote PDF to {path}").format(path=Path(path).name)
        )


__all__ = ["ShoppingListDialog"]
