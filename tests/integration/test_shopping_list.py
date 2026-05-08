"""Integration tests for US-12.6 — Shopping List.

Covers:
  * Dialog populates with category groups from a synthetic scene.
  * Editing the price cell mutates the item, updates the grand total, and
    persists to ``ProjectManager.shopping_list_prices``.
  * Saving and reloading the project file round-trips entered prices.
  * CSV export round-trips the row count.
  * Amendment Plan dialog's "Add to Shopping List" button calls the
    callback handed to it.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.shopping_list import ShoppingListCategory
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.services.shopping_list_service import ShoppingListService
from open_garden_planner.services.soil_service import GLOBAL_TARGET_ID, SoilService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.dialogs.amendment_plan_dialog import AmendmentPlanDialog
from open_garden_planner.ui.dialogs.shopping_list_dialog import (
    _COL_PRICE,
    ShoppingListDialog,
)


def _add_plant(scene: CanvasScene, common_name: str, source_id: str) -> CircleItem:
    plant = CircleItem(
        center_x=100, center_y=100, radius=20,
        object_type=ObjectType.PERENNIAL,
        name=common_name,
    )
    plant.metadata["plant_species"] = {
        "common_name": common_name,
        "source_id": source_id,
    }
    plant.metadata["plant_instance"] = {"current_spread_cm": 30.0}
    scene.addItem(plant)
    return plant


# ── Dialog population ─────────────────────────────────────────────────────────


class TestDialogPopulation:
    def test_dialog_renders_three_category_groups(self, qtbot) -> None:
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        _add_plant(scene, "Tomato", "solanum_lycopersicum")
        # Materials: a deficient bed.
        bed = RectangleItem(0, 0, 200, 100,
                            object_type=ObjectType.GARDEN_BED, name="Bed A")
        scene.addItem(bed)

        pm = ProjectManager()
        soil_service = MagicMock()
        soil_service.get_effective_record.return_value = SoilTestRecord(
            date="2026-04-01", ph=5.8, n_level=3, p_level=3, k_level=3,
        )

        svc = ShoppingListService(scene, soil_service, pm)
        dialog = ShoppingListDialog(service=svc)
        qtbot.addWidget(dialog)

        # Three category headers + at least one row each (1 plant, 1 seed gap, 1 material).
        assert dialog._table.rowCount() >= 6
        # Items collected internally span all three categories.
        cats = {i.category for i in dialog._items}
        assert cats == {
            ShoppingListCategory.PLANTS,
            ShoppingListCategory.SEEDS,
            ShoppingListCategory.MATERIALS,
        }

    def test_empty_state_when_nothing_to_buy(self, qtbot) -> None:
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        pm = ProjectManager()
        soil_service = MagicMock()
        soil_service.get_effective_record.return_value = None
        svc = ShoppingListService(scene, soil_service, pm)
        dialog = ShoppingListDialog(service=svc)
        qtbot.addWidget(dialog)
        # No items collected and the export buttons are disabled.
        assert dialog._items == []
        assert dialog._table.rowCount() == 0
        assert not dialog._csv_button.isEnabled()
        assert not dialog._pdf_button.isEnabled()


# ── Price editing & persistence ───────────────────────────────────────────────


class TestPriceEditing:
    def test_editing_price_cell_persists_to_project_manager(self, qtbot) -> None:
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        _add_plant(scene, "Tomato", "solanum_lycopersicum")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        dialog = ShoppingListDialog(service=svc)
        qtbot.addWidget(dialog)

        # First data row is the plant (header row 0 is the "Plants" group).
        plant_row = 1
        cell = dialog._table.item(plant_row, _COL_PRICE)
        assert cell is not None
        cell.setText("4.00")

        # Service updates item + persists to ProjectManager.
        plant_item = dialog._row_items[plant_row]
        assert plant_item is not None
        assert plant_item.price_each == 4.00
        assert pm.shopping_list_prices.get(plant_item.id) == 4.00
        assert pm.is_dirty
        # Grand-total label populated.
        assert "4.00" in dialog._grand_total_label.text()

    def test_invalid_price_is_ignored_and_resets(self, qtbot) -> None:
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        _add_plant(scene, "Tomato", "solanum_lycopersicum")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        dialog = ShoppingListDialog(service=svc)
        qtbot.addWidget(dialog)

        cell = dialog._table.item(1, _COL_PRICE)
        assert cell is not None
        cell.setText("not-a-number")
        plant_item = dialog._row_items[1]
        assert plant_item is not None
        assert plant_item.price_each is None
        assert pm.shopping_list_prices == {}

    def test_negative_price_resets_cell_and_status(self, qtbot) -> None:
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        _add_plant(scene, "Tomato", "solanum_lycopersicum")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        dialog = ShoppingListDialog(service=svc)
        qtbot.addWidget(dialog)

        cell = dialog._table.item(1, _COL_PRICE)
        assert cell is not None
        cell.setText("-5")
        plant_item = dialog._row_items[1]
        assert plant_item is not None
        assert plant_item.price_each is None
        # Cell text is refreshed to empty (not left displaying "-5").
        assert dialog._table.item(1, _COL_PRICE).text() == ""
        assert "Invalid" in dialog._status_label.text()

    def test_comma_decimal_is_accepted(self, qtbot) -> None:
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        _add_plant(scene, "Tomato", "solanum_lycopersicum")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        dialog = ShoppingListDialog(service=svc)
        qtbot.addWidget(dialog)

        cell = dialog._table.item(1, _COL_PRICE)
        assert cell is not None
        cell.setText("2,50")
        plant_item = dialog._row_items[1]
        assert plant_item is not None
        assert plant_item.price_each == 2.50

    def test_zero_price_round_trips_in_dialog(self, qtbot) -> None:
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        _add_plant(scene, "Tomato", "solanum_lycopersicum")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        dialog = ShoppingListDialog(service=svc)
        qtbot.addWidget(dialog)

        cell = dialog._table.item(1, _COL_PRICE)
        assert cell is not None
        cell.setText("0")
        plant_item = dialog._row_items[1]
        assert plant_item is not None
        assert plant_item.price_each == 0.0
        assert pm.shopping_list_prices.get(plant_item.id) == 0.0


# ── PDF pagination ────────────────────────────────────────────────────────────


class TestPdfPagination:
    def test_grand_total_only_on_final_page(self, tmp_path: Path) -> None:
        from open_garden_planner.models.shopping_list import (
            ShoppingListCategory as Cat,
        )
        from open_garden_planner.models.shopping_list import (
            ShoppingListItem,
        )
        from open_garden_planner.services.pdf_report_service import (
            _shopping_list_fits,
        )
        from PyQt6.QtCore import QRectF

        # 200 priced items — guaranteed to overflow A4 portrait.
        items = [
            ShoppingListItem(
                id=f"x:{i}", category=Cat.PLANTS, name=f"Plant {i}",
                quantity=1.0, unit="x", price_each=1.0,
            )
            for i in range(200)
        ]
        # Probe helper directly: a small page rect can't fit 200 rows.
        small_rect = QRectF(0, 0, 595, 842)  # A4 portrait points
        assert not _shopping_list_fits(items, small_rect)
        # Single-item slice fits.
        assert _shopping_list_fits(items[:1], small_rect)

        # End-to-end PDF render runs to completion without infinite loop.
        out = tmp_path / "shopping_paginated.pdf"
        from open_garden_planner.services.pdf_report_service import PdfReportService
        PdfReportService.export_shopping_list_to_pdf(items, out)
        assert out.exists() and out.stat().st_size > 0



# ── Project save/load round-trip ──────────────────────────────────────────────


class TestProjectRoundTrip:
    def test_prices_round_trip_through_save_load(self, tmp_path: Path) -> None:
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        _add_plant(scene, "Tomato", "solanum_lycopersicum")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)

        items = svc.build()
        plant = next(i for i in items if i.category is ShoppingListCategory.PLANTS)
        svc.update_price(plant, 3.25)

        save_path = tmp_path / "garden.ogp"
        pm.save(scene, save_path)

        # Verify the on-disk JSON includes prices.
        on_disk = json.loads(save_path.read_text(encoding="utf-8"))
        assert on_disk["shopping_list_prices"][plant.id] == 3.25

        # Fresh manager + fresh scene — prices come back.
        pm2 = ProjectManager()
        scene2 = CanvasScene(width_cm=5000, height_cm=3000)
        pm2.load(scene2, save_path)
        assert pm2.shopping_list_prices.get(plant.id) == 3.25


# ── CSV export ────────────────────────────────────────────────────────────────


class TestCsvExport:
    def test_export_round_trips_rows(self, tmp_path: Path, qtbot) -> None:  # noqa: ARG002
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        _add_plant(scene, "Tomato", "solanum_lycopersicum")
        _add_plant(scene, "Basil", "ocimum_basilicum")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        items = svc.build()

        from open_garden_planner.services.export_service import ExportService
        out = tmp_path / "shopping.csv"
        n = ExportService.export_shopping_list_to_csv(items, out)
        assert n == len(items)

        with open(out, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == len(items)
        names = {r["name"] for r in rows}
        assert "Tomato" in names
        assert "Basil" in names


# ── Amendment Plan handoff ────────────────────────────────────────────────────


class TestAmendmentPlanHandoff:
    def test_add_to_shopping_list_triggers_callback(self, qtbot) -> None:
        QApplication.instance() or QApplication([])
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        bed = RectangleItem(0, 0, 200, 100,
                            object_type=ObjectType.GARDEN_BED, name="Bed A")
        scene.addItem(bed)

        pm = ProjectManager()
        # Use real SoilService backed by ProjectManager so global record is found.
        pm.set_soil_test_history(GLOBAL_TARGET_ID,
                                 _make_global_history())
        soil_service = SoilService(pm)

        called = []
        dialog = AmendmentPlanDialog(
            canvas_scene=scene,
            soil_service=soil_service,
            on_add_to_shopping_list=lambda: called.append(True),
        )
        qtbot.addWidget(dialog)
        assert dialog._aggregated  # has at least one substance
        dialog._on_add_to_shopping_list_clicked()
        assert called == [True]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_global_history():  # type: ignore[no-untyped-def]
    from open_garden_planner.models.soil_test import SoilTestHistory
    history = SoilTestHistory(target_id=GLOBAL_TARGET_ID)
    history.records.append(
        SoilTestRecord(date="2026-04-01", ph=5.8, n_level=3, p_level=3, k_level=3)
    )
    return history
