"""Tests for SeedInventoryDialog and SeedPacketEditDialog (US-9.3)."""
# ruff: noqa: ARG002
from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from open_garden_planner.models.seed_inventory import (
    SeedInventoryStore,
    SeedPacket,
    SeedViabilityDB,
    ViabilityStatus,
)
from open_garden_planner.ui.dialogs.seed_inventory_dialog import (
    SeedInventoryDialog,
    SeedPacketEditDialog,
    _SeedTableModel,
)

# ── Minimal viability DB fixture ────────────────────────────────────────────────

_MINI_DB_DATA = {
    "by_species": {"tomato": {"shelf_life_years": 5, "reduced_after_years": 4}},
    "by_family": {},
    "_default": {"shelf_life_years": 3, "reduced_after_years": 2},
}


@pytest.fixture
def db() -> SeedViabilityDB:
    return SeedViabilityDB.from_dict(_MINI_DB_DATA)


@pytest.fixture
def tmp_store(tmp_path: Path) -> SeedInventoryStore:
    store = SeedInventoryStore(tmp_path / "test_inventory.json")
    return store


# ── _SeedTableModel tests (no Qt event loop needed) ────────────────────────────

class TestSeedTableModel:
    def test_row_count_empty(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        model = _SeedTableModel(tmp_store, db)
        assert model.rowCount() == 0

    def test_row_count_after_add(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        tmp_store.add(SeedPacket(species_name="Tomato", purchase_year=2023))
        tmp_store.add(SeedPacket(species_name="Carrot", purchase_year=2024))
        model = _SeedTableModel(tmp_store, db)
        assert model.rowCount() == 2

    def test_column_count(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        model = _SeedTableModel(tmp_store, db)
        assert model.columnCount() == 7

    def test_packet_at_valid(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        p = SeedPacket(species_name="Basil", purchase_year=2024)
        tmp_store.add(p)
        model = _SeedTableModel(tmp_store, db)
        result = model.packet_at(0)
        assert result is not None
        assert result.species_name == "Basil"

    def test_packet_at_invalid(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        model = _SeedTableModel(tmp_store, db)
        assert model.packet_at(0) is None
        assert model.packet_at(-1) is None

    def test_display_data_name(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        from PyQt6.QtCore import Qt
        tmp_store.add(SeedPacket(species_name="Pepper", purchase_year=2024))
        model = _SeedTableModel(tmp_store, db)
        idx = model.index(0, 0)
        assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "Pepper"

    def test_display_data_year(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        from PyQt6.QtCore import Qt
        tmp_store.add(SeedPacket(species_name="Pea", purchase_year=2021))
        model = _SeedTableModel(tmp_store, db)
        idx = model.index(0, 2)  # Year column
        assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "2021"

    def test_display_quantity_with_unit(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        from PyQt6.QtCore import Qt
        tmp_store.add(SeedPacket(species_name="Bean", purchase_year=2024, quantity=50.0, quantity_unit="seeds"))
        model = _SeedTableModel(tmp_store, db)
        idx = model.index(0, 3)  # Quantity column
        assert model.data(idx, Qt.ItemDataRole.DisplayRole) == "50 seeds"

    def test_display_quantity_zero_is_empty(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        from PyQt6.QtCore import Qt
        tmp_store.add(SeedPacket(species_name="Bean", purchase_year=2024, quantity=0.0))
        model = _SeedTableModel(tmp_store, db)
        idx = model.index(0, 3)
        assert model.data(idx, Qt.ItemDataRole.DisplayRole) == ""

    def test_background_role_good(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        from PyQt6.QtCore import Qt
        tmp_store.add(SeedPacket(species_name="Tomato", purchase_year=2024))
        model = _SeedTableModel(tmp_store, db)
        model._current_year = 2024
        idx = model.index(0, 0)
        brush = model.data(idx, Qt.ItemDataRole.BackgroundRole)
        assert brush is not None

    def test_set_headers_updates_model(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        from PyQt6.QtCore import Qt
        model = _SeedTableModel(tmp_store, db)
        headers = ["A", "B", "C", "D", "E", "F", "G"]
        model.set_headers(headers)
        result = model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        assert result == "A"

    def test_reload_updates_rows(self, tmp_store: SeedInventoryStore, db: SeedViabilityDB) -> None:
        model = _SeedTableModel(tmp_store, db)
        assert model.rowCount() == 0
        tmp_store.add(SeedPacket(species_name="Kale", purchase_year=2025))
        model._reload()
        assert model.rowCount() == 1


# ── SeedPacketEditDialog tests ──────────────────────────────────────────────────

class TestSeedPacketEditDialog:
    def test_create_new_packet_defaults(self, qtbot) -> None:
        dlg = SeedPacketEditDialog()
        qtbot.addWidget(dlg)
        assert dlg._year_spin.value() == datetime.date.today().year
        assert dlg._qty_spin.value() == 0.0
        assert dlg._cold_strat_cb.isChecked() is False
        assert dlg._override_cb.isChecked() is False

    def test_get_packet_returns_correct_data(self, qtbot) -> None:
        dlg = SeedPacketEditDialog()
        qtbot.addWidget(dlg)
        dlg._name_edit.setText("Tomato")
        dlg._variety_edit.setText("Gardener's Delight")
        dlg._year_spin.setValue(2022)
        dlg._qty_spin.setValue(25)
        dlg._unit_combo.setCurrentIndex(0)  # seeds
        packet = dlg.get_packet()
        assert packet.species_name == "Tomato"
        assert packet.variety == "Gardener's Delight"
        assert packet.purchase_year == 2022
        assert packet.quantity == 25.0
        assert packet.quantity_unit == "seeds"

    def test_populate_existing_packet(self, qtbot) -> None:
        existing = SeedPacket(
            species_name="Carrot",
            variety="Nantes",
            purchase_year=2020,
            quantity=100.0,
            quantity_unit="seeds",
            manufacturer="Vilmorin",
            cold_stratification=True,
            stratification_days=28,
            viability_shelf_life_override=4,
            notes="Stored in fridge",
        )
        dlg = SeedPacketEditDialog(packet=existing)
        qtbot.addWidget(dlg)
        assert dlg._name_edit.text() == "Carrot"
        assert dlg._variety_edit.text() == "Nantes"
        assert dlg._year_spin.value() == 2020
        assert dlg._qty_spin.value() == 100.0
        assert dlg._manufacturer_edit.text() == "Vilmorin"
        assert dlg._cold_strat_cb.isChecked() is True
        assert dlg._strat_days_spin.value() == 28
        assert dlg._override_cb.isChecked() is True
        assert dlg._override_spin.value() == 4
        assert dlg._notes_edit.toPlainText() == "Stored in fridge"

    def test_get_packet_preserves_id(self, qtbot) -> None:
        existing = SeedPacket(species_name="Pea")
        dlg = SeedPacketEditDialog(packet=existing)
        qtbot.addWidget(dlg)
        dlg._name_edit.setText("Pea Updated")
        result = dlg.get_packet()
        assert result.id == existing.id

    def test_cold_strat_disables_days_spin(self, qtbot) -> None:
        dlg = SeedPacketEditDialog()
        qtbot.addWidget(dlg)
        assert dlg._strat_days_spin.isEnabled() is False
        dlg._cold_strat_cb.setChecked(True)
        assert dlg._strat_days_spin.isEnabled() is True

    def test_override_disables_spin_when_unchecked(self, qtbot) -> None:
        dlg = SeedPacketEditDialog()
        qtbot.addWidget(dlg)
        assert dlg._override_spin.isEnabled() is False
        dlg._override_cb.setChecked(True)
        assert dlg._override_spin.isEnabled() is True

    def test_get_packet_no_override_when_unchecked(self, qtbot) -> None:
        dlg = SeedPacketEditDialog()
        qtbot.addWidget(dlg)
        dlg._name_edit.setText("Lettuce")
        dlg._override_cb.setChecked(False)
        result = dlg.get_packet()
        assert result.viability_shelf_life_override is None

    def test_get_packet_stratification_none_when_unchecked(self, qtbot) -> None:
        dlg = SeedPacketEditDialog()
        qtbot.addWidget(dlg)
        dlg._name_edit.setText("Spinach")
        dlg._cold_strat_cb.setChecked(False)
        result = dlg.get_packet()
        assert result.stratification_days is None

    def test_light_combo_values(self, qtbot) -> None:
        dlg = SeedPacketEditDialog()
        qtbot.addWidget(dlg)
        # Default is Indifferent (None)
        assert dlg._light_combo.currentData() is None
        # Select light germinator
        dlg._light_combo.setCurrentIndex(1)
        assert dlg._light_combo.currentData() is True
        # Select dark germinator
        dlg._light_combo.setCurrentIndex(2)
        assert dlg._light_combo.currentData() is False

    def test_title_new_vs_edit(self, qtbot) -> None:
        dlg_new = SeedPacketEditDialog()
        qtbot.addWidget(dlg_new)
        assert "Add" in dlg_new.windowTitle()

        existing = SeedPacket(species_name="Basil")
        dlg_edit = SeedPacketEditDialog(packet=existing)
        qtbot.addWidget(dlg_edit)
        assert "Edit" in dlg_edit.windowTitle()


# ── SeedInventoryDialog tests ───────────────────────────────────────────────────

class TestSeedInventoryDialog:
    @pytest.fixture
    def dialog(self, qtbot, tmp_path):
        with (
            patch(
                "open_garden_planner.ui.dialogs.seed_inventory_dialog.get_seed_inventory",
            ) as mock_store_factory,
            patch(
                "open_garden_planner.ui.dialogs.seed_inventory_dialog.get_viability_db",
            ) as mock_db_factory,
        ):
            store = SeedInventoryStore(tmp_path / "inv.json")
            db = SeedViabilityDB.from_dict(_MINI_DB_DATA)
            mock_store_factory.return_value = store
            mock_db_factory.return_value = db
            dlg = SeedInventoryDialog()
            qtbot.addWidget(dlg)
            yield dlg, store, db

    def test_dialog_opens(self, dialog) -> None:
        dlg, store, db = dialog
        assert dlg.isVisible() is False  # not shown yet, just constructed

    def test_stats_label_shows_zero(self, dialog) -> None:
        dlg, store, db = dialog
        assert "0 packets" in dlg._stats_lbl.text()

    def test_table_empty_on_start(self, dialog) -> None:
        dlg, store, db = dialog
        assert dlg._model.rowCount() == 0

    def test_table_shows_packets(self, dialog) -> None:
        dlg, store, db = dialog
        store.add(SeedPacket(species_name="Tomato", purchase_year=2023))
        store.add(SeedPacket(species_name="Basil", purchase_year=2024))
        dlg._reload()
        assert dlg._model.rowCount() == 2

    def test_delete_button_disabled_on_start(self, dialog) -> None:
        dlg, store, db = dialog
        assert dlg._delete_btn.isEnabled() is False

    def test_edit_button_disabled_on_start(self, dialog) -> None:
        dlg, store, db = dialog
        assert dlg._edit_btn.isEnabled() is False

    def test_stats_label_counts_correctly(self, dialog) -> None:
        dlg, store, db = dialog
        # Add a good packet (bought this year)
        store.add(SeedPacket(species_name="Tomato", purchase_year=datetime.date.today().year))
        # Add an expired packet (bought 10 years ago)
        store.add(SeedPacket(species_name="Onion", purchase_year=datetime.date.today().year - 10))
        dlg._reload()
        text = dlg._stats_lbl.text()
        assert "2 packets" in text
        assert "1 expired" in text
