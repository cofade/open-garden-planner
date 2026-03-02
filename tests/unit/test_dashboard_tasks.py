"""Unit tests for US-8.6: Dashboard / Today View task generation logic."""
from __future__ import annotations

import datetime
from dataclasses import dataclass

import pytest

from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.ui.views.planting_calendar_view import (
    _DashboardTask,
    _PlantRow,
    _classify_urgency,
    _generate_dashboard_tasks,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tomato_species() -> PlantSpeciesData:
    """Tomato with all calendar windows defined relative to last frost."""
    return PlantSpeciesData(
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        indoor_sow_start=-8,   # 8 weeks before last frost
        indoor_sow_end=-6,
        transplant_start=0,    # at last frost
        transplant_end=2,
        direct_sow_start=None,
        direct_sow_end=None,
        harvest_start=14,      # 14 weeks after last frost
        harvest_end=20,
    )


@pytest.fixture
def lettuce_species() -> PlantSpeciesData:
    """Lettuce with direct sow only."""
    return PlantSpeciesData(
        scientific_name="Lactuca sativa",
        common_name="Lettuce",
        direct_sow_start=-4,
        direct_sow_end=2,
        indoor_sow_start=None,
        indoor_sow_end=None,
        transplant_start=None,
        transplant_end=None,
        harvest_start=8,
        harvest_end=12,
    )


# ─── Tests for _classify_urgency ──────────────────────────────────────────────

class TestClassifyUrgency:
    def test_overdue_window_ended_yesterday(self) -> None:
        today = datetime.date(2026, 3, 10)
        start = datetime.date(2026, 2, 20)
        end = datetime.date(2026, 3, 9)
        assert _classify_urgency(start, end, today) == "overdue"

    def test_overdue_exactly_14_days_ago(self) -> None:
        today = datetime.date(2026, 3, 10)
        end = today - datetime.timedelta(days=14)
        start = end - datetime.timedelta(days=7)
        assert _classify_urgency(start, end, today) == "overdue"

    def test_not_overdue_15_days_ago(self) -> None:
        today = datetime.date(2026, 3, 10)
        end = today - datetime.timedelta(days=15)
        start = end - datetime.timedelta(days=7)
        assert _classify_urgency(start, end, today) is None

    def test_today_window_starts_today(self) -> None:
        today = datetime.date(2026, 3, 10)
        start = today
        end = today + datetime.timedelta(days=14)
        assert _classify_urgency(start, end, today) == "today"

    def test_today_window_active_started_earlier(self) -> None:
        today = datetime.date(2026, 3, 10)
        start = today - datetime.timedelta(days=3)
        end = today + datetime.timedelta(days=5)
        assert _classify_urgency(start, end, today) == "today"

    def test_today_window_ends_today(self) -> None:
        today = datetime.date(2026, 3, 10)
        start = today - datetime.timedelta(days=7)
        end = today
        assert _classify_urgency(start, end, today) == "today"

    def test_this_week_starts_tomorrow(self) -> None:
        today = datetime.date(2026, 3, 10)
        start = today + datetime.timedelta(days=1)
        end = start + datetime.timedelta(days=14)
        assert _classify_urgency(start, end, today) == "this_week"

    def test_this_week_starts_in_7_days(self) -> None:
        today = datetime.date(2026, 3, 10)
        start = today + datetime.timedelta(days=7)
        end = start + datetime.timedelta(days=14)
        assert _classify_urgency(start, end, today) == "this_week"

    def test_coming_up_starts_in_8_days(self) -> None:
        today = datetime.date(2026, 3, 10)
        start = today + datetime.timedelta(days=8)
        end = start + datetime.timedelta(days=14)
        assert _classify_urgency(start, end, today) == "coming_up"

    def test_coming_up_starts_in_30_days(self) -> None:
        today = datetime.date(2026, 3, 10)
        start = today + datetime.timedelta(days=30)
        end = start + datetime.timedelta(days=7)
        assert _classify_urgency(start, end, today) == "coming_up"

    def test_too_far_future_returns_none(self) -> None:
        today = datetime.date(2026, 3, 10)
        start = today + datetime.timedelta(days=31)
        end = start + datetime.timedelta(days=7)
        assert _classify_urgency(start, end, today) is None

    def test_too_old_returns_none(self) -> None:
        today = datetime.date(2026, 3, 10)
        end = today - datetime.timedelta(days=15)
        start = end - datetime.timedelta(days=7)
        assert _classify_urgency(start, end, today) is None


# ─── Tests for _generate_dashboard_tasks ──────────────────────────────────────

class TestGenerateDashboardTasks:
    def test_generates_indoor_sow_task(
        self, tomato_species: PlantSpeciesData
    ) -> None:
        # Last frost: Apr 15. Indoor sow: -8 to -6 weeks = ~Feb 18 – Mar 4
        # If today is Feb 28, window should be "today"
        last_frost = datetime.date(2026, 4, 15)
        today = datetime.date(2026, 2, 28)
        rows = [_PlantRow(display_name="Tomato", species=tomato_species)]
        tasks = _generate_dashboard_tasks(rows, last_frost, today, set())

        indoor_tasks = [t for t in tasks if t.task_type == "indoor_sow"]
        assert len(indoor_tasks) == 1
        t = indoor_tasks[0]
        assert t.display_name == "Tomato"
        assert t.urgency in ("today", "this_week", "coming_up", "overdue")
        assert t.task_id == f"Solanum lycopersicum:indoor_sow:{today.year}"
        assert t.species_key == "Solanum lycopersicum"

    def test_completed_task_excluded(
        self, tomato_species: PlantSpeciesData
    ) -> None:
        last_frost = datetime.date(2026, 4, 15)
        today = datetime.date(2026, 2, 28)
        rows = [_PlantRow(display_name="Tomato", species=tomato_species)]
        task_id = f"Solanum lycopersicum:indoor_sow:{today.year}"
        tasks = _generate_dashboard_tasks(rows, last_frost, today, {task_id})

        indoor_tasks = [t for t in tasks if t.task_type == "indoor_sow"]
        assert len(indoor_tasks) == 0

    def test_out_of_year_window_excluded(
        self, tomato_species: PlantSpeciesData
    ) -> None:
        # Move last frost to October so all windows spill into next year
        last_frost = datetime.date(2026, 10, 1)
        today = datetime.date(2026, 3, 1)
        rows = [_PlantRow(display_name="Tomato", species=tomato_species)]
        tasks = _generate_dashboard_tasks(rows, last_frost, today, set())
        # No tasks should fall within the 30-day window in early March
        assert all(t.task_type != "harvest" for t in tasks)

    def test_multiple_plants_generate_separate_tasks(
        self,
        tomato_species: PlantSpeciesData,
        lettuce_species: PlantSpeciesData,
    ) -> None:
        last_frost = datetime.date(2026, 4, 15)
        today = datetime.date(2026, 3, 1)
        rows = [
            _PlantRow(display_name="Tomato", species=tomato_species),
            _PlantRow(display_name="Lettuce", species=lettuce_species),
        ]
        tasks = _generate_dashboard_tasks(rows, last_frost, today, set())
        species_keys = {t.species_key for t in tasks}
        # Both plants should appear in tasks
        assert "Solanum lycopersicum" in species_keys
        assert "Lactuca sativa" in species_keys

    def test_no_tasks_when_no_rows(self) -> None:
        last_frost = datetime.date(2026, 4, 15)
        today = datetime.date(2026, 3, 1)
        tasks = _generate_dashboard_tasks([], last_frost, today, set())
        assert tasks == []

    def test_task_id_format(self, tomato_species: PlantSpeciesData) -> None:
        last_frost = datetime.date(2026, 4, 15)
        today = datetime.date(2026, 2, 20)
        rows = [_PlantRow(display_name="Tomato", species=tomato_species)]
        tasks = _generate_dashboard_tasks(rows, last_frost, today, set())
        for task in tasks:
            parts = task.task_id.split(":")
            assert len(parts) == 3
            assert parts[2] == str(today.year)

    def test_uses_scientific_name_as_species_key(
        self, tomato_species: PlantSpeciesData
    ) -> None:
        last_frost = datetime.date(2026, 4, 15)
        today = datetime.date(2026, 2, 20)
        rows = [_PlantRow(display_name="Tomato", species=tomato_species)]
        tasks = _generate_dashboard_tasks(rows, last_frost, today, set())
        assert all(t.species_key == "Solanum lycopersicum" for t in tasks)

    def test_falls_back_to_common_name_as_species_key(self) -> None:
        species = PlantSpeciesData(
            scientific_name=None,
            common_name="Carrot",
            direct_sow_start=-2,
            direct_sow_end=4,
        )
        last_frost = datetime.date(2026, 4, 15)
        today = datetime.date(2026, 4, 1)  # within direct sow window
        rows = [_PlantRow(display_name="Carrot", species=species)]
        tasks = _generate_dashboard_tasks(rows, last_frost, today, set())
        assert all(t.species_key == "Carrot" for t in tasks)
