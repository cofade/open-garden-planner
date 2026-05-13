"""Integration tests for US-12.8 — succession planting.

Covers:
  * SuccessionEntry / SuccessionPlan serialisation round-trip
  * SuccessionPlan helpers: current_entry, next_entry, entries_sorted
  * compute_season_segments frost-relative date ranges
  * SetSuccessionPlanCommand execute / undo / redo via CommandManager
  * .ogp save/load round-trip preserves plans
  * Empty succession_plans key omitted from saved file
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from open_garden_planner.core import (
    CommandManager,
    ProjectManager,
    SetSuccessionPlanCommand,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.succession import (
    SuccessionEntry,
    SuccessionPlan,
    compute_season_segments,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture()
def project_manager(qtbot: object) -> ProjectManager:  # noqa: ARG001
    return ProjectManager()


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=1000, height_cm=800)


def _make_entry(
    common_name: str,
    start: str,
    end: str,
    species_key: str = "",
    scientific_name: str = "",
    notes: str = "",
) -> SuccessionEntry:
    return SuccessionEntry(
        common_name=common_name,
        species_key=species_key,
        scientific_name=scientific_name,
        start_date=start,
        end_date=end,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Data model — SuccessionEntry
# ---------------------------------------------------------------------------

class TestSuccessionEntry:
    def test_to_dict_from_dict_roundtrip(self) -> None:
        entry = SuccessionEntry(
            species_key="solanum_lycopersicum",
            common_name="Tomato",
            scientific_name="Solanum lycopersicum",
            start_date="2026-05-15",
            end_date="2026-08-30",
            notes="cherry variety",
        )
        d = entry.to_dict()
        restored = SuccessionEntry.from_dict(d)

        assert restored.id == entry.id
        assert restored.species_key == "solanum_lycopersicum"
        assert restored.common_name == "Tomato"
        assert restored.scientific_name == "Solanum lycopersicum"
        assert restored.start_date == "2026-05-15"
        assert restored.end_date == "2026-08-30"
        assert restored.notes == "cherry variety"

    def test_defaults_are_sensible(self) -> None:
        entry = SuccessionEntry()
        assert entry.id  # auto-generated UUID
        assert entry.species_key == ""
        assert entry.common_name == ""
        assert entry.scientific_name == ""
        assert entry.start_date == ""
        assert entry.end_date == ""
        assert entry.notes == ""

    def test_optional_fields_omitted_when_empty(self) -> None:
        entry = SuccessionEntry(common_name="Spinach", start_date="2026-03-01", end_date="2026-04-15")
        d = entry.to_dict()
        assert "scientific_name" not in d
        assert "notes" not in d

    def test_from_dict_forgiving_on_missing_keys(self) -> None:
        restored = SuccessionEntry.from_dict({"common_name": "Kale"})
        assert restored.common_name == "Kale"
        assert restored.start_date == ""
        assert restored.end_date == ""
        assert restored.id  # auto-generated when absent

    def test_unique_ids_auto_generated(self) -> None:
        a = SuccessionEntry()
        b = SuccessionEntry()
        assert a.id != b.id


# ---------------------------------------------------------------------------
# Data model — SuccessionPlan
# ---------------------------------------------------------------------------

class TestSuccessionPlan:
    def test_to_dict_from_dict_roundtrip(self) -> None:
        plan = SuccessionPlan(
            bed_id="bed-abc",
            year=2026,
            entries=[
                _make_entry("Spinach", "2026-03-01", "2026-04-20"),
                _make_entry("Beans", "2026-06-01", "2026-08-31"),
            ],
        )
        restored = SuccessionPlan.from_dict(plan.to_dict())
        assert restored.bed_id == "bed-abc"
        assert restored.year == 2026
        assert len(restored.entries) == 2
        assert restored.entries[0].common_name == "Spinach"
        assert restored.entries[1].common_name == "Beans"

    def test_entries_sorted_by_start_date(self) -> None:
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=2026,
            entries=[
                _make_entry("Kale", "2026-09-01", "2026-11-01"),
                _make_entry("Spinach", "2026-03-01", "2026-04-20"),
                _make_entry("Beans", "2026-06-01", "2026-08-31"),
            ],
        )
        sorted_entries = plan.entries_sorted()
        assert sorted_entries[0].common_name == "Spinach"
        assert sorted_entries[1].common_name == "Beans"
        assert sorted_entries[2].common_name == "Kale"

    def test_current_entry_today_within_range(self) -> None:
        today = datetime.date.today()
        yesterday = (today - datetime.timedelta(days=1)).isoformat()
        tomorrow = (today + datetime.timedelta(days=1)).isoformat()
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=today.year,
            entries=[_make_entry("Lettuce", yesterday, tomorrow)],
        )
        current = plan.current_entry(today)
        assert current is not None
        assert current.common_name == "Lettuce"

    def test_current_entry_returns_none_outside_range(self) -> None:
        today = datetime.date.today()
        past_start = (today - datetime.timedelta(days=30)).isoformat()
        past_end = (today - datetime.timedelta(days=10)).isoformat()
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=today.year,
            entries=[_make_entry("OldCrop", past_start, past_end)],
        )
        assert plan.current_entry(today) is None

    def test_next_entry_returns_first_future(self) -> None:
        today = datetime.date.today()
        soon = (today + datetime.timedelta(days=5)).isoformat()
        later = (today + datetime.timedelta(days=30)).isoformat()
        soon_end = (today + datetime.timedelta(days=20)).isoformat()
        later_end = (today + datetime.timedelta(days=60)).isoformat()
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=today.year,
            entries=[
                _make_entry("FarFuture", later, later_end),
                _make_entry("Soon", soon, soon_end),
            ],
        )
        nxt = plan.next_entry(today)
        assert nxt is not None
        assert nxt.common_name == "Soon"

    def test_next_entry_returns_none_when_all_past(self) -> None:
        today = datetime.date.today()
        past_start = (today - datetime.timedelta(days=30)).isoformat()
        past_end = (today - datetime.timedelta(days=10)).isoformat()
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=today.year,
            entries=[_make_entry("OldCrop", past_start, past_end)],
        )
        assert plan.next_entry(today) is None

    def test_entries_sorted_empty_dates_sort_last(self) -> None:
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=2026,
            entries=[
                _make_entry("NoDate", "", ""),
                _make_entry("Early", "2026-03-01", "2026-04-01"),
            ],
        )
        sorted_entries = plan.entries_sorted()
        assert sorted_entries[0].common_name == "Early"
        assert sorted_entries[1].common_name == "NoDate"

    def test_compute_season_segments_uses_frost_dates(self) -> None:
        segments = compute_season_segments("04-15", "10-01", 2026)
        last_frost = datetime.date(2026, 4, 15)
        fall_frost = datetime.date(2026, 10, 1)

        assert segments["early_spring"][0] == last_frost - datetime.timedelta(weeks=8)
        assert segments["early_spring"][1] == last_frost - datetime.timedelta(weeks=2)
        assert segments["late_spring"][0] == last_frost - datetime.timedelta(weeks=2)
        assert segments["late_spring"][1] == last_frost + datetime.timedelta(weeks=4)
        assert segments["summer"][0] == last_frost + datetime.timedelta(weeks=4)
        assert segments["summer"][1] == fall_frost - datetime.timedelta(weeks=4)
        assert segments["fall"][0] == fall_frost - datetime.timedelta(weeks=4)
        assert segments["fall"][1] == fall_frost + datetime.timedelta(weeks=2)

    def test_all_four_segments_present(self) -> None:
        segments = compute_season_segments("04-15", "10-01", 2026)
        assert set(segments.keys()) == {"early_spring", "late_spring", "summer", "fall"}


# ---------------------------------------------------------------------------
# Command: SetSuccessionPlanCommand
# ---------------------------------------------------------------------------

class TestSetSuccessionPlanCommand:
    def test_execute_stores_plan(self, project_manager: ProjectManager) -> None:
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=2026,
            entries=[_make_entry("Spinach", "2026-03-01", "2026-04-20")],
        )
        cmd = SetSuccessionPlanCommand(project_manager, "bed-1", plan)
        cmd.execute()
        stored = project_manager.succession_plans.get("bed-1")
        assert stored is not None
        restored = SuccessionPlan.from_dict(stored)
        assert restored.bed_id == "bed-1"
        assert len(restored.entries) == 1
        assert restored.entries[0].common_name == "Spinach"

    def test_undo_restores_prior_state(self, project_manager: ProjectManager) -> None:
        plan_a = SuccessionPlan(
            bed_id="bed-1",
            year=2026,
            entries=[_make_entry("Spinach", "2026-03-01", "2026-04-20")],
        )
        SetSuccessionPlanCommand(project_manager, "bed-1", plan_a).execute()

        plan_b = SuccessionPlan(
            bed_id="bed-1",
            year=2026,
            entries=[_make_entry("Lettuce", "2026-04-21", "2026-05-31")],
        )
        cmd_b = SetSuccessionPlanCommand(project_manager, "bed-1", plan_b)
        cmd_b.execute()
        assert SuccessionPlan.from_dict(
            project_manager.succession_plans["bed-1"]
        ).entries[0].common_name == "Lettuce"

        cmd_b.undo()
        assert SuccessionPlan.from_dict(
            project_manager.succession_plans["bed-1"]
        ).entries[0].common_name == "Spinach"

    def test_undo_when_no_prior_plan_removes_key(
        self, project_manager: ProjectManager
    ) -> None:
        plan = SuccessionPlan(
            bed_id="bed-new",
            year=2026,
            entries=[_make_entry("Beans", "2026-06-01", "2026-08-31")],
        )
        cmd = SetSuccessionPlanCommand(project_manager, "bed-new", plan)
        cmd.execute()
        assert "bed-new" in project_manager.succession_plans
        cmd.undo()
        assert "bed-new" not in project_manager.succession_plans

    def test_redo_reapplies_plan(self, project_manager: ProjectManager) -> None:
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=2026,
            entries=[_make_entry("Kale", "2026-09-01", "2026-11-01")],
        )
        cmd = SetSuccessionPlanCommand(project_manager, "bed-1", plan)
        cmd.execute()
        cmd.undo()
        assert "bed-1" not in project_manager.succession_plans
        cmd.execute()  # redo
        assert "bed-1" in project_manager.succession_plans
        assert SuccessionPlan.from_dict(
            project_manager.succession_plans["bed-1"]
        ).entries[0].common_name == "Kale"

    def test_command_description(self, project_manager: ProjectManager) -> None:
        plan = SuccessionPlan(bed_id="bed-1", year=2026)
        cmd = SetSuccessionPlanCommand(project_manager, "bed-1", plan)
        assert cmd.description == "Set succession plan"

    def test_none_plan_deletes_existing(self, project_manager: ProjectManager) -> None:
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=2026,
            entries=[_make_entry("Beans", "2026-06-01", "2026-08-31")],
        )
        SetSuccessionPlanCommand(project_manager, "bed-1", plan).execute()
        assert "bed-1" in project_manager.succession_plans

        delete_cmd = SetSuccessionPlanCommand(project_manager, "bed-1", None)
        delete_cmd.execute()
        assert "bed-1" not in project_manager.succession_plans

    def test_command_manager_undo_redo(self, project_manager: ProjectManager) -> None:
        cm = CommandManager()
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=2026,
            entries=[_make_entry("Spinach", "2026-03-01", "2026-04-20")],
        )
        cm.execute(SetSuccessionPlanCommand(project_manager, "bed-1", plan))
        assert "bed-1" in project_manager.succession_plans

        cm.undo()
        assert "bed-1" not in project_manager.succession_plans

        cm.redo()
        assert "bed-1" in project_manager.succession_plans


# ---------------------------------------------------------------------------
# .ogp save / load round-trip
# ---------------------------------------------------------------------------

class TestSuccessionIntegration:
    def test_plan_survives_save_load_roundtrip(
        self,
        project_manager: ProjectManager,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        bed = RectangleItem(100, 100, 200, 150, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        bed_id = str(bed.item_id)

        plan = SuccessionPlan(
            bed_id=bed_id,
            year=2026,
            entries=[
                _make_entry("Spinach", "2026-03-01", "2026-04-20"),
                _make_entry("Beans", "2026-06-01", "2026-08-31", notes="green variety"),
            ],
        )
        SetSuccessionPlanCommand(project_manager, bed_id, plan).execute()

        path = tmp_path / "test.ogp"
        project_manager.save(scene, path)

        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        assert "succession_plans" in raw
        assert bed_id in raw["succession_plans"]

        # Reload into fresh manager
        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2 = ProjectManager()
        pm2.load(scene2, path)

        stored = pm2.succession_plans.get(bed_id)
        assert stored is not None
        restored = SuccessionPlan.from_dict(stored)
        assert restored.year == 2026
        assert len(restored.entries) == 2
        names = [e.common_name for e in restored.entries_sorted()]
        assert names == ["Spinach", "Beans"]
        assert restored.entries_sorted()[1].notes == "green variety"

    def test_empty_succession_plan_omitted_from_file(
        self,
        project_manager: ProjectManager,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "empty.ogp"
        project_manager.save(scene, path)
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        assert "succession_plans" not in raw

    def test_multiple_beds_stored_independently(
        self,
        project_manager: ProjectManager,
        scene: CanvasScene,
        tmp_path: Path,
    ) -> None:
        bed_a = RectangleItem(100, 100, 200, 150, object_type=ObjectType.GARDEN_BED)
        bed_b = RectangleItem(400, 100, 200, 150, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed_a)
        scene.addItem(bed_b)

        plan_a = SuccessionPlan(
            bed_id=str(bed_a.item_id),
            year=2026,
            entries=[_make_entry("Spinach", "2026-03-01", "2026-04-20")],
        )
        plan_b = SuccessionPlan(
            bed_id=str(bed_b.item_id),
            year=2026,
            entries=[_make_entry("Tomato", "2026-05-15", "2026-09-30")],
        )
        SetSuccessionPlanCommand(project_manager, str(bed_a.item_id), plan_a).execute()
        SetSuccessionPlanCommand(project_manager, str(bed_b.item_id), plan_b).execute()

        path = tmp_path / "multi.ogp"
        project_manager.save(scene, path)
        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2 = ProjectManager()
        pm2.load(scene2, path)

        restored_a = SuccessionPlan.from_dict(pm2.succession_plans[str(bed_a.item_id)])
        restored_b = SuccessionPlan.from_dict(pm2.succession_plans[str(bed_b.item_id)])

        assert restored_a.entries[0].common_name == "Spinach"
        assert restored_b.entries[0].common_name == "Tomato"

    def test_orphaned_bed_id_handled_gracefully(
        self, project_manager: ProjectManager
    ) -> None:
        plan = SuccessionPlan(
            bed_id="ghost-bed-id",
            year=2026,
            entries=[_make_entry("Spinach", "2026-03-01", "2026-04-20")],
        )
        SetSuccessionPlanCommand(project_manager, "ghost-bed-id", plan).execute()
        # Accessing a plan for an orphaned (non-existent) bed id should not raise
        stored = project_manager.succession_plans.get("ghost-bed-id")
        assert stored is not None
        restored = SuccessionPlan.from_dict(stored)
        assert restored.bed_id == "ghost-bed-id"


# ---------------------------------------------------------------------------
# Pill row allocation (post-implementation bug fix)
# ---------------------------------------------------------------------------

class TestPillRowAllocation:
    """Overlapping entries in the season-band widget must stack on separate rows."""

    def test_non_overlapping_entries_stay_in_row_zero(self) -> None:
        from open_garden_planner.ui.dialogs.succession_plan_dialog import (
            _assign_pill_rows,
        )
        entries = [
            _make_entry("A", "2026-03-01", "2026-04-15"),
            _make_entry("B", "2026-04-20", "2026-06-01"),
            _make_entry("C", "2026-06-05", "2026-08-15"),
        ]
        placements = _assign_pill_rows(entries)
        assert all(row == 0 for _, row in placements)

    def test_overlapping_entries_get_new_rows(self) -> None:
        from open_garden_planner.ui.dialogs.succession_plan_dialog import (
            _assign_pill_rows,
        )
        # All three overlap with each other → three distinct rows
        entries = [
            _make_entry("A", "2026-03-01", "2026-06-01"),
            _make_entry("B", "2026-04-01", "2026-07-01"),
            _make_entry("C", "2026-05-01", "2026-08-01"),
        ]
        placements = _assign_pill_rows(entries)
        rows = {entry.common_name: row for entry, row in placements}
        assert rows["A"] == 0
        assert rows["B"] == 1
        assert rows["C"] == 2

    def test_first_fit_reuses_earlier_row_when_no_overlap(self) -> None:
        from open_garden_planner.ui.dialogs.succession_plan_dialog import (
            _assign_pill_rows,
        )
        # A (Mar-Apr) on row 0; B (Mar-May) overlaps A → row 1;
        # C (May-Jun) overlaps B but NOT A → should fit back into row 0.
        entries = [
            _make_entry("A", "2026-03-01", "2026-04-15"),
            _make_entry("B", "2026-03-10", "2026-05-10"),
            _make_entry("C", "2026-05-01", "2026-06-15"),
        ]
        placements = _assign_pill_rows(entries)
        rows = {entry.common_name: row for entry, row in placements}
        assert rows["A"] == 0
        assert rows["B"] == 1
        assert rows["C"] == 0  # fits back in row 0 since A ended before C starts


# ---------------------------------------------------------------------------
# Multi-line succession badge indicator (post-implementation bug fix)
# ---------------------------------------------------------------------------

class TestSuccessionBadgeIndicator:
    """The badge state on bed items must accept a list of (name, is_current) tuples."""

    def test_set_lines_stores_chronological_list(self, scene: CanvasScene) -> None:
        bed = RectangleItem(0, 0, 200, 150, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        bed.set_succession_indicator(
            [("Tomate", True), ("Gurke", False), ("Kürbis", False)]
        )
        assert bed._succession_lines == [
            ("Tomate", True),
            ("Gurke", False),
            ("Kürbis", False),
        ]

    def test_set_none_clears_lines(self, scene: CanvasScene) -> None:
        bed = RectangleItem(0, 0, 200, 150, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        bed.set_succession_indicator([("Tomate", True)])
        bed.set_succession_indicator(None)
        assert bed._succession_lines == []

    def test_idempotent_when_lines_unchanged(self, scene: CanvasScene) -> None:
        bed = RectangleItem(0, 0, 200, 150, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        bed.set_succession_indicator([("Tomate", True)])
        before = bed._succession_badge_item
        bed.set_succession_indicator([("Tomate", True)])
        assert bed._succession_badge_item is before  # no recreation
