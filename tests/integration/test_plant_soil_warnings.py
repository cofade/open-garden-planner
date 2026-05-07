"""Integration tests for US-12.10d — Plant-Soil Compatibility Warnings.

Covers:
  * Pure ``SoilService.get_mismatched_plants`` rules.
  * Legacy ``nutrient_demand`` fallback via ``_effective_demand``.
  * Severity level set on bed items via ``_update_soil_mismatches``.
  * Dashboard ``_inject_soil_mismatch_tasks`` card injection.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


# ---------------------------------------------------------------------------
# Helpers


def _make_spec(
    common_name: str = "Tomato",
    scientific_name: str = "Solanum lycopersicum",
    ph_min: float | None = 5.8,
    ph_max: float | None = 7.0,
    nutrient_demand: str | None = None,
    n_demand: str | None = None,
    p_demand: str | None = None,
    k_demand: str | None = None,
) -> PlantSpeciesData:
    return PlantSpeciesData(
        common_name=common_name,
        scientific_name=scientific_name,
        ph_min=ph_min,
        ph_max=ph_max,
        nutrient_demand=nutrient_demand,
        n_demand=n_demand,
        p_demand=p_demand,
        k_demand=k_demand,
    )


def _make_record(**kwargs) -> SoilTestRecord:
    defaults = {"date": "2026-05-01"}
    defaults.update(kwargs)
    return SoilTestRecord(**defaults)


# ---------------------------------------------------------------------------
# TestCalculatorRules — pure static method tests


class TestGetMismatchedPlants:
    def test_no_mismatch_returns_empty(self) -> None:
        record = _make_record(ph=6.5, n_level=3)
        spec = _make_spec(ph_min=6.0, ph_max=7.0, n_demand="high")
        assert SoilService.get_mismatched_plants(record, [spec]) == []

    def test_none_record_returns_empty(self) -> None:
        spec = _make_spec()
        assert SoilService.get_mismatched_plants(None, [spec]) == []

    def test_empty_specs_returns_empty(self) -> None:
        record = _make_record(ph=5.0)
        assert SoilService.get_mismatched_plants(record, []) == []

    def test_ph_low_triggers_mismatch(self) -> None:
        record = _make_record(ph=5.0)
        spec = _make_spec(ph_min=6.0, ph_max=7.0)
        result = SoilService.get_mismatched_plants(record, [spec])
        assert len(result) == 1
        returned_spec, reasons = result[0]
        assert returned_spec is spec
        assert any("pH" in r or "ph" in r.lower() for r in reasons)

    def test_ph_high_triggers_mismatch(self) -> None:
        record = _make_record(ph=8.0)
        spec = _make_spec(ph_min=5.8, ph_max=7.0)
        result = SoilService.get_mismatched_plants(record, [spec])
        assert len(result) == 1
        _, reasons = result[0]
        assert any("pH" in r or "ph" in r.lower() for r in reasons)

    def test_ph_within_tolerance_no_mismatch(self) -> None:
        # Tolerance is 0.05 (only float-rounding slack). pH 5.96 vs ph_min=6.0
        # is within tolerance → no mismatch. pH 5.9 vs ph_min=6.0 IS a mismatch
        # (test split into two cases below).
        record = _make_record(ph=5.96)
        spec = _make_spec(ph_min=6.0, ph_max=7.0)
        assert SoilService.get_mismatched_plants(record, [spec]) == []

    def test_ph_just_below_min_triggers_mismatch(self) -> None:
        # pH 5.7 with ph_min=5.8 → delta 0.1 → mismatch under tight tolerance.
        record = _make_record(ph=5.7)
        spec = _make_spec(ph_min=5.8, ph_max=7.0)
        result = SoilService.get_mismatched_plants(record, [spec])
        assert len(result) == 1
        _, reasons = result[0]
        assert any("pH" in r or "ph" in r.lower() for r in reasons)

    def test_n_deficient_with_explicit_high_demand(self) -> None:
        record = _make_record(n_level=1)
        spec = _make_spec(ph_min=None, ph_max=None, n_demand="high")
        result = SoilService.get_mismatched_plants(record, [spec])
        assert len(result) == 1
        _, reasons = result[0]
        assert any("N" in r for r in reasons)

    def test_legacy_nutrient_demand_heavy_maps_to_high(self) -> None:
        record = _make_record(n_level=1)
        spec = _make_spec(ph_min=None, ph_max=None, nutrient_demand="heavy")
        result = SoilService.get_mismatched_plants(record, [spec])
        assert len(result) == 1

    def test_legacy_nutrient_demand_medium_no_mismatch(self) -> None:
        record = _make_record(n_level=1)
        spec = _make_spec(ph_min=None, ph_max=None, nutrient_demand="medium")
        assert SoilService.get_mismatched_plants(record, [spec]) == []

    def test_multiple_parameters_all_returned(self) -> None:
        record = _make_record(ph=5.0, n_level=1)
        spec = _make_spec(ph_min=6.0, ph_max=7.0, n_demand="high")
        result = SoilService.get_mismatched_plants(record, [spec])
        assert len(result) == 1
        _, reasons = result[0]
        assert len(reasons) == 2  # one pH reason + one N reason


# ---------------------------------------------------------------------------
# TestSeverityLevel — mismatch level set on bed items via _update_soil_mismatches


class TestSeverityLevel:
    def _make_canvas(self, qtbot) -> tuple[CanvasView, RectangleItem]:
        """Return (view, bed_item) with a planted rectangle bed."""
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        bed = RectangleItem(
            x=0, y=0, width=200, height=100,
            object_type=ObjectType.GARDEN_BED,
            name="Bed 1",
        )
        scene.addItem(bed)
        return view, bed

    def _make_soil_service_mock(
        self, bed_item: RectangleItem, record: SoilTestRecord | None
    ) -> MagicMock:
        svc = MagicMock()
        svc.get_effective_record.return_value = record
        return svc

    def test_no_mismatch_level_is_none(self, qtbot) -> None:
        view, bed = self._make_canvas(qtbot)
        svc = self._make_soil_service_mock(bed, _make_record(ph=6.5, n_level=3))
        view.set_soil_service(svc)
        assert bed._soil_mismatch_level is None

    def test_one_mismatch_sets_warning(self, qtbot) -> None:
        view, bed = self._make_canvas(qtbot)
        scene = view._canvas_scene

        # Add a child plant item via metadata
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        plant = CircleItem(
            center_x=50,
            center_y=50,
            radius=20,
            object_type=ObjectType.TREE,
            name="Tomato",
        )
        plant.metadata["plant_species"] = {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "ph_min": 5.8,
            "ph_max": 7.0,
        }
        scene.addItem(plant)

        # Link plant to bed via _child_item_ids
        bed._child_item_ids = [plant._item_id]

        record = _make_record(ph=5.0)  # pH too low → 1 mismatch
        svc = self._make_soil_service_mock(bed, record)
        view.set_soil_service(svc)
        view.refresh_soil_mismatches()

        assert bed._soil_mismatch_level == "warning"

    def test_two_mismatches_sets_critical(self, qtbot) -> None:
        view, bed = self._make_canvas(qtbot)
        scene = view._canvas_scene

        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        plant = CircleItem(
            center_x=50, center_y=50, radius=20,
            object_type=ObjectType.TREE, name="Tomato",
        )
        plant.metadata["plant_species"] = {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "ph_min": 5.8,
            "ph_max": 7.0,
            "nutrient_demand": "heavy",
        }
        scene.addItem(plant)
        bed._child_item_ids = [plant._item_id]

        # pH too low + N deficient → 2 mismatches → critical
        record = _make_record(ph=5.0, n_level=1)
        svc = self._make_soil_service_mock(bed, record)
        view.set_soil_service(svc)
        view.refresh_soil_mismatches()

        assert bed._soil_mismatch_level == "critical"


# ---------------------------------------------------------------------------
# TestDashboardCards — _inject_soil_mismatch_tasks


class TestDashboardCards:
    def test_dashboard_shows_amber_card_for_mismatch(self, qtbot) -> None:
        from unittest.mock import patch

        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem
        from open_garden_planner.ui.views.planting_calendar_view import (
            PlantingCalendarView,
        )

        scene = CanvasScene(width_cm=5000, height_cm=3000)
        pm = MagicMock()
        pm.location = None
        pm.task_completions = set()

        view = PlantingCalendarView(canvas_scene=scene, project_manager=pm)
        qtbot.addWidget(view)

        # Add a bed + plant
        bed = RectangleItem(
            x=0, y=0, width=200, height=100,
            object_type=ObjectType.GARDEN_BED,
            name="Veggie Bed",
        )
        scene.addItem(bed)

        plant = CircleItem(
            center_x=50, center_y=50, radius=20,
            object_type=ObjectType.TREE, name="Tomato",
        )
        plant.metadata["plant_species"] = {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "ph_min": 5.8,
            "ph_max": 7.0,
        }
        scene.addItem(plant)
        bed._child_item_ids = [plant._item_id]

        svc = MagicMock()
        svc.get_effective_record.return_value = _make_record(ph=5.0)  # mismatch
        view.set_soil_service(svc)

        # Capture the task list passed to _dashboard.set_data
        captured: list = []
        original_set_data = view._dashboard.set_data

        def capturing_set_data(tasks):
            captured.extend(tasks)
            original_set_data(tasks)

        view._dashboard.set_data = capturing_set_data
        view._current_dashboard_tasks = []
        view._inject_soil_mismatch_tasks()

        # Should have produced a task mentioning the bed name
        assert any(
            "Veggie Bed" in t.display_name for t in captured
        ), f"Expected 'Veggie Bed' in task names; got: {[t.display_name for t in captured]}"


# ---------------------------------------------------------------------------
# TestRefreshOnReparent — issue #173: warning state must update when a plant
# moves into or out of a bed without waiting on the 500 ms debounce.


class TestRefreshOnReparent:
    """The bed soil-mismatch level must re-evaluate immediately when plant
    parenting changes via _update_plant_bed_relationships (drag-and-drop).
    """

    def _build_view_with_bed_and_plant(
        self, qtbot, plant_inside_bed: bool
    ):
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        bed = RectangleItem(
            x=0, y=0, width=400, height=400,
            object_type=ObjectType.GARDEN_BED,
            name="Bed 1",
        )
        scene.addItem(bed)

        # Plant centre depends on whether we want it inside the bed or outside.
        cx = 100 if plant_inside_bed else 800
        plant = CircleItem(
            center_x=cx, center_y=100, radius=20,
            object_type=ObjectType.TREE, name="Tomato",
        )
        plant.metadata["plant_species"] = {
            "common_name": "Tomato",
            "scientific_name": "Solanum lycopersicum",
            "ph_min": 6.0,
            "ph_max": 7.5,
        }
        scene.addItem(plant)
        return view, bed, plant

    def test_attach_via_command_sets_warning_immediately(self, qtbot) -> None:
        """Plant moved INTO a bed with hostile pH → warning must appear w/o debounce."""
        view, bed, plant = self._build_view_with_bed_and_plant(
            qtbot, plant_inside_bed=False
        )
        svc = MagicMock()
        svc.get_effective_record.return_value = _make_record(ph=4.0)  # very acidic
        view.set_soil_service(svc)
        # set_soil_service already calls _update_soil_mismatches synchronously.
        assert bed._soil_mismatch_level is None

        # Simulate the post-move parent re-evaluation: plant moves INTO bed.
        plant.setSelected(True)
        plant.setPos(plant.pos().x() - 800, plant.pos().y())  # center is in bed
        view._update_plant_bed_relationships()

        # Bug #173: this should be set without waiting 500 ms for the debounce.
        assert bed._soil_mismatch_level == "warning"

    def test_detach_via_command_clears_warning_immediately(self, qtbot) -> None:
        """Plant moved OUT of a bed → warning must clear w/o debounce."""
        view, bed, plant = self._build_view_with_bed_and_plant(
            qtbot, plant_inside_bed=True
        )
        # Pre-attach the plant (mimic state after a previous drop).
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)
        svc = MagicMock()
        svc.get_effective_record.return_value = _make_record(ph=4.0)
        view.set_soil_service(svc)
        assert bed._soil_mismatch_level == "warning"

        # Move plant outside the bed and re-evaluate.
        plant.setSelected(True)
        plant.setPos(plant.pos().x() + 800, plant.pos().y())
        view._update_plant_bed_relationships()

        # Bug #173: warning must clear immediately.
        assert bed._soil_mismatch_level is None

    def test_unlink_via_properties_panel_clears_warning_immediately(
        self, qtbot
    ) -> None:
        """Properties-panel "Unlink" calls SetParentBedCommand directly (not via
        _update_plant_bed_relationships). The fix must still cover this path
        because the command itself triggers the soil-mismatch refresh.
        """
        from open_garden_planner.core.commands import (
            CommandManager,
            SetParentBedCommand,
        )

        view, bed, plant = self._build_view_with_bed_and_plant(
            qtbot, plant_inside_bed=True
        )
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)
        svc = MagicMock()
        svc.get_effective_record.return_value = _make_record(ph=4.0)
        view.set_soil_service(svc)
        assert bed._soil_mismatch_level == "warning"

        # Mimic the properties-panel _do_unlink flow exactly.
        cmd = SetParentBedCommand(view._canvas_scene, plant, bed.item_id, None)
        CommandManager().execute(cmd)

        assert bed._soil_mismatch_level is None
