"""Unit tests for ShoppingListService (US-12.6)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.shopping_list import (
    ShoppingListCategory,
    ShoppingListItem,
)
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.services.shopping_list_service import (
    ShoppingListService,
    aggregate_amendments,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_scene() -> CanvasScene:
    return CanvasScene(width_cm=5000, height_cm=3000)


def _add_plant(scene: CanvasScene, *, common_name: str, source_id: str | None = None,
               object_type: ObjectType = ObjectType.PERENNIAL,
               spread: float | None = 30.0) -> CircleItem:
    plant = CircleItem(
        center_x=100, center_y=100, radius=20,
        object_type=object_type,
        name=common_name,
    )
    species: dict = {"common_name": common_name}
    if source_id:
        species["source_id"] = source_id
    instance: dict = {}
    if spread is not None:
        instance["current_spread_cm"] = spread
    plant.metadata["plant_species"] = species
    plant.metadata["plant_instance"] = instance
    scene.addItem(plant)
    return plant


# ── ShoppingListItem model ────────────────────────────────────────────────────


class TestShoppingListItem:
    def test_total_cost_none_when_no_price(self) -> None:
        item = ShoppingListItem(
            id="x", category=ShoppingListCategory.PLANTS,
            name="Tomato", quantity=3.0, unit="plants",
        )
        assert item.total_cost is None

    def test_total_cost_multiplies(self) -> None:
        item = ShoppingListItem(
            id="x", category=ShoppingListCategory.PLANTS,
            name="Tomato", quantity=3.0, unit="plants",
            price_each=2.5,
        )
        assert item.total_cost == pytest.approx(7.5)

    def test_export_row_contains_all_fields(self) -> None:
        item = ShoppingListItem(
            id="x", category=ShoppingListCategory.MATERIALS,
            name="Compost", quantity=10.0, unit="kg", price_each=5.0,
            notes="Bed 1",
        )
        row = item.to_export_row()
        assert row["category"] == "materials"
        assert row["price_each"] == 5.0
        assert row["total_cost"] == pytest.approx(50.0)
        assert row["notes"] == "Bed 1"


# ── Plant aggregation ─────────────────────────────────────────────────────────


class TestPlantAggregation:
    def test_groups_plants_by_species_id(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        for _ in range(3):
            _add_plant(scene, common_name="Tomato", source_id="solanum_lycopersicum")
        _add_plant(scene, common_name="Basil", source_id="ocimum_basilicum")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)

        plants = [i for i in svc.build() if i.category is ShoppingListCategory.PLANTS]
        names = {i.name: i.quantity for i in plants}
        assert names == {"Tomato": 3.0, "Basil": 1.0}

    def test_falls_back_to_scientific_name(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        plant = CircleItem(
            center_x=50, center_y=50, radius=20,
            object_type=ObjectType.SHRUB, name="rose",
        )
        plant.metadata["plant_species"] = {"scientific_name": "Rosa rugosa"}
        scene.addItem(plant)
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)

        plants = [i for i in svc.build() if i.category is ShoppingListCategory.PLANTS]
        assert len(plants) == 1
        assert plants[0].name == "Rosa rugosa"

    def test_size_descriptor_averages_spread(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        _add_plant(scene, common_name="Tomato", source_id="t", spread=20.0)
        _add_plant(scene, common_name="Tomato", source_id="t", spread=40.0)
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)

        plants = [i for i in svc.build() if i.category is ShoppingListCategory.PLANTS]
        assert plants[0].size_descriptor == "~30 cm spread"

    def test_non_plant_items_ignored(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        bed = RectangleItem(0, 0, 200, 100, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        soil_service = MagicMock()
        soil_service.get_effective_record.return_value = None
        pm = ProjectManager()
        svc = ShoppingListService(scene, soil_service, pm)
        plants = [i for i in svc.build() if i.category is ShoppingListCategory.PLANTS]
        assert plants == []


# ── Seed gap aggregation ──────────────────────────────────────────────────────


class TestSeedGaps:
    def test_species_with_no_packet_becomes_gap(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        _add_plant(scene, common_name="Tomato", source_id="solanum_lycopersicum")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        seeds = [i for i in svc.build() if i.category is ShoppingListCategory.SEEDS]
        assert len(seeds) == 1
        assert seeds[0].name == "Tomato"
        assert seeds[0].unit == "packet"

    def test_species_with_inventory_packet_no_gap(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        _add_plant(scene, common_name="Tomato", source_id="solanum_lycopersicum")
        pm = ProjectManager()
        pm.set_seed_inventory([
            {"species_id": "solanum_lycopersicum", "species_name": "Tomato", "quantity": 10}
        ])
        svc = ShoppingListService(scene, MagicMock(), pm)
        seeds = [i for i in svc.build() if i.category is ShoppingListCategory.SEEDS]
        assert seeds == []


# ── Materials (amendments) ────────────────────────────────────────────────────


class TestMaterialsAggregation:
    def test_aggregates_amendments_across_beds(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        # Two beds, both deficient with the same low pH so one amendment will
        # apply to both → aggregated quantity sums.
        bed1 = RectangleItem(0, 0, 200, 100, object_type=ObjectType.GARDEN_BED, name="Bed A")
        bed2 = RectangleItem(0, 0, 200, 100, object_type=ObjectType.GARDEN_BED, name="Bed B")
        scene.addItem(bed1)
        scene.addItem(bed2)

        record = SoilTestRecord(date="2026-04-01", ph=5.8, n_level=3, p_level=3, k_level=3)
        soil_service = MagicMock()
        soil_service.get_effective_record.return_value = record

        agg = aggregate_amendments(scene, soil_service)
        assert len(agg) == 1
        assert "Bed A" in agg[0].bed_names
        assert "Bed B" in agg[0].bed_names
        assert agg[0].total_g > 0

        pm = ProjectManager()
        svc = ShoppingListService(scene, soil_service, pm)
        materials = [i for i in svc.build() if i.category is ShoppingListCategory.MATERIALS]
        assert len(materials) == 1
        assert materials[0].unit == "g"


# ── Price persistence ─────────────────────────────────────────────────────────


class TestPricePersistence:
    def test_update_price_writes_to_project_manager(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        _add_plant(scene, common_name="Tomato", source_id="t")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)

        items = svc.build()
        plant = next(i for i in items if i.category is ShoppingListCategory.PLANTS)
        svc.update_price(plant, 2.50)

        assert pm.shopping_list_prices == {plant.id: 2.50}
        # Rebuilding picks up the saved price.
        rebuilt = svc.build()
        plant2 = next(i for i in rebuilt if i.id == plant.id)
        assert plant2.price_each == pytest.approx(2.50)

    def test_clearing_price_removes_entry(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        _add_plant(scene, common_name="Tomato", source_id="t")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        plant = next(i for i in svc.build() if i.category is ShoppingListCategory.PLANTS)
        svc.update_price(plant, 2.50)
        svc.update_price(plant, None)
        assert pm.shopping_list_prices == {}

    def test_zero_price_is_persisted_as_real_value(self, qtbot) -> None:  # noqa: ARG002
        """Zero is a valid price (free); only None clears the entry."""
        scene = _make_scene()
        _add_plant(scene, common_name="Tomato", source_id="t")
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        plant = next(i for i in svc.build() if i.category is ShoppingListCategory.PLANTS)
        svc.update_price(plant, 0.0)
        assert pm.shopping_list_prices == {plant.id: 0.0}
        rebuilt = next(i for i in svc.build() if i.id == plant.id)
        assert rebuilt.price_each == 0.0
        assert rebuilt.total_cost == 0.0


# ── Edge cases & robustness ───────────────────────────────────────────────────


class TestEdgeCases:
    def test_plant_with_empty_metadata_does_not_crash(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        plant = CircleItem(
            center_x=50, center_y=50, radius=20,
            object_type=ObjectType.PERENNIAL, name="orphan",
        )
        # plant_species absent → service falls back to item.name then "Unknown plant"
        scene.addItem(plant)
        pm = ProjectManager()
        svc = ShoppingListService(scene, MagicMock(), pm)
        plants = [i for i in svc.build() if i.category is ShoppingListCategory.PLANTS]
        assert len(plants) == 1
        assert plants[0].name == "orphan"

    def test_seed_packet_with_no_keys_is_skipped(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        _add_plant(scene, common_name="Tomato", source_id="t")
        pm = ProjectManager()
        pm.set_seed_inventory([
            {"quantity": 10},  # neither species_id nor species_name
        ])
        svc = ShoppingListService(scene, MagicMock(), pm)
        seeds = [i for i in svc.build() if i.category is ShoppingListCategory.SEEDS]
        assert len(seeds) == 1  # gap still present

    def test_seed_gap_match_is_case_insensitive(self, qtbot) -> None:  # noqa: ARG002
        scene = _make_scene()
        plant = CircleItem(
            center_x=50, center_y=50, radius=20,
            object_type=ObjectType.PERENNIAL, name="Tomato",
        )
        plant.metadata["plant_species"] = {
            "scientific_name": "Solanum lycopersicum",
        }
        scene.addItem(plant)
        pm = ProjectManager()
        pm.set_seed_inventory([
            {"species_id": "  solanum LYCOPERSICUM ", "quantity": 10},
        ])
        svc = ShoppingListService(scene, MagicMock(), pm)
        seeds = [i for i in svc.build() if i.category is ShoppingListCategory.SEEDS]
        assert seeds == []
