"""Unit tests for the pure task-generation engine (US-C2)."""
from __future__ import annotations

import datetime

from open_garden_planner.models.propagation import compute_propagation_plan
from open_garden_planner.models.succession import SuccessionEntry, SuccessionPlan
from open_garden_planner.models.task import ManualTask
from open_garden_planner.services.task_generator import (
    BedInput,
    PlanState,
    PlantRowInput,
    Task,
    classify_urgency,
    generate_all,
    generate_calendar_tasks,
    generate_frost_tasks,
    generate_manual_tasks,
    generate_propagation_tasks,
    generate_soil_amendment_tasks,
    generate_succession_tasks,
)
from open_garden_planner.services.weather_service import FrostAlert

TODAY = datetime.date(2026, 4, 20)
YEAR = 2026
# Last frost on this date makes the calendar windows below land near TODAY.
LAST_FROST = datetime.date(2026, 4, 24)


def _state(**overrides: object) -> PlanState:
    base = {
        "today": TODAY,
        "year": YEAR,
        "last_frost": LAST_FROST,
    }
    base.update(overrides)
    return PlanState(**base)  # type: ignore[arg-type]


class TestClassifyUrgency:
    def test_today(self) -> None:
        assert classify_urgency(TODAY, TODAY, TODAY) == "today"

    def test_overdue(self) -> None:
        end = TODAY - datetime.timedelta(days=3)
        assert classify_urgency(end, end, TODAY) == "overdue"

    def test_this_week(self) -> None:
        start = TODAY + datetime.timedelta(days=3)
        assert classify_urgency(start, start, TODAY) == "this_week"

    def test_upcoming(self) -> None:
        start = TODAY + datetime.timedelta(days=20)
        assert classify_urgency(start, start, TODAY) == "upcoming"

    def test_out_of_range_none(self) -> None:
        far = TODAY + datetime.timedelta(days=200)
        assert classify_urgency(far, far, TODAY) is None
        long_ago = TODAY - datetime.timedelta(days=200)
        assert classify_urgency(long_ago, long_ago, TODAY) is None


class TestCalendarTasks:
    def test_emits_actionable_windows(self) -> None:
        # transplant window straddles today (last_frost is 4 days out, weeks 0..1).
        row = PlantRowInput(
            display_name="Tomato",
            species_key="tomato",
            transplant_start=0,
            transplant_end=1,
        )
        tasks = generate_calendar_tasks(_state(plant_rows=(row,)))
        assert len(tasks) == 1
        t = tasks[0]
        assert t.task_id == "tomato:transplant:2026"
        assert t.source == "calendar"
        assert t.task_type == "transplant"
        assert t.title == "Tomato"
        assert t.start_date == LAST_FROST
        assert t.end_date == LAST_FROST + datetime.timedelta(weeks=1)
        assert t.dismissible is False

    def test_skipped_when_weeks_none(self) -> None:
        row = PlantRowInput(
            display_name="Tomato",
            species_key="tomato",
            transplant_start=0,
            transplant_end=None,  # incomplete window
        )
        assert generate_calendar_tasks(_state(plant_rows=(row,))) == []

    def test_skipped_when_urgency_none(self) -> None:
        # harvest window far in the future → classify_urgency None → skipped.
        row = PlantRowInput(
            display_name="Tomato",
            species_key="tomato",
            harvest_start=30,
            harvest_end=31,
        )
        assert generate_calendar_tasks(_state(plant_rows=(row,))) == []

    def test_skipped_when_no_last_frost(self) -> None:
        row = PlantRowInput(
            display_name="Tomato",
            species_key="tomato",
            transplant_start=0,
            transplant_end=1,
        )
        assert generate_calendar_tasks(_state(last_frost=None, plant_rows=(row,))) == []


class TestPropagationTasks:
    def test_prick_out_and_harden_off(self) -> None:
        # Sow window so prick_out (sow+21d) and harden_off (transplant-10d..) land
        # in the actionable range around TODAY.
        plan = compute_propagation_plan(
            species_key="tomato",
            sow_start=TODAY - datetime.timedelta(days=21),  # prick_out == TODAY
            sow_end=TODAY - datetime.timedelta(days=18),
            transplant_date=TODAY + datetime.timedelta(days=5),  # harden_off active now
        )
        row = PlantRowInput(display_name="Tomato", species_key="tomato")
        tasks = generate_propagation_tasks(
            _state(plant_rows=(row,), prop_plans={"tomato": plan})
        )
        types = {t.task_type for t in tasks}
        assert "prick_out" in types
        assert "harden_off" in types
        for t in tasks:
            assert t.source == "propagation"
            assert t.species_key == "tomato"
            assert t.dismissible is False
            assert t.task_id == f"tomato:{t.task_type}:2026"

    def test_no_plan_no_tasks(self) -> None:
        row = PlantRowInput(display_name="Tomato", species_key="tomato")
        assert generate_propagation_tasks(_state(plant_rows=(row,))) == []


class TestSuccessionTasks:
    def test_sow_and_clear(self) -> None:
        sow = TODAY + datetime.timedelta(days=3)
        clear = TODAY + datetime.timedelta(days=5)
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=YEAR,
            entries=[
                SuccessionEntry(
                    id="e1",
                    species_key="lettuce",
                    common_name="Lettuce",
                    start_date=sow.isoformat(),
                    end_date=clear.isoformat(),
                )
            ],
        )
        tasks = generate_succession_tasks(
            _state(succession_plans={"bed-1": plan.to_dict()})
        )
        by_type = {t.task_type: t for t in tasks}
        assert set(by_type) == {"succession_sow", "succession_clear"}
        sow_task = by_type["succession_sow"]
        assert sow_task.task_id == "succession:sow:bed-1:e1"
        assert sow_task.source == "succession"
        assert sow_task.title == "Lettuce"
        assert sow_task.bed_id == "bed-1"
        assert sow_task.species_key == "lettuce"
        assert sow_task.start_date == sow
        clear_task = by_type["succession_clear"]
        assert clear_task.task_id == "succession:clear:bed-1:e1"
        assert clear_task.start_date == clear

    def test_far_future_entry_skipped(self) -> None:
        far = TODAY + datetime.timedelta(days=200)
        plan = SuccessionPlan(
            bed_id="bed-1",
            year=YEAR,
            entries=[
                SuccessionEntry(
                    id="e1",
                    common_name="Kale",
                    start_date=far.isoformat(),
                    end_date=far.isoformat(),
                )
            ],
        )
        assert generate_succession_tasks(
            _state(succession_plans={"bed-1": plan.to_dict()})
        ) == []


class TestSoilAmendmentTasks:
    def test_one_per_rec(self) -> None:
        bed = BedInput(
            bed_id="bed-1",
            name="North Bed",
            amendment_recs=(
                ("Garden lime", "Raises pH 5.8 -> 6.5"),
                ("Blood meal", "Raises N level 1 -> 3"),
            ),
        )
        tasks = generate_soil_amendment_tasks(_state(beds=(bed,)))
        assert len(tasks) == 2
        first = tasks[0]
        assert first.task_id == "soil_amendment:bed-1:Garden lime"
        assert first.source == "soil"
        assert first.task_type == "soil_amendment"
        assert first.title == "Garden lime — North Bed"
        assert first.notes == "Raises pH 5.8 -> 6.5"
        assert first.bed_id == "bed-1"
        assert first.start_date == TODAY
        assert first.end_date == TODAY
        assert first.dismissible is True
        assert tasks[1].task_id == "soil_amendment:bed-1:Blood meal"

    def test_no_recs_no_tasks(self) -> None:
        bed = BedInput(bed_id="bed-1", name="North Bed")
        assert generate_soil_amendment_tasks(_state(beds=(bed,))) == []


class TestFrostTasks:
    def test_red_and_orange(self) -> None:
        alerts = (
            FrostAlert(
                date=(TODAY + datetime.timedelta(days=2)).isoformat(),
                min_temp=-1.0,
                severity="red",
                affected_plant_ids=["p1", "p2"],
            ),
            FrostAlert(
                date=(TODAY + datetime.timedelta(days=3)).isoformat(),
                min_temp=4.0,
                severity="orange",
                affected_plant_ids=["p3"],
            ),
        )
        tasks = generate_frost_tasks(_state(frost_alerts=alerts))
        assert len(tasks) == 2
        red = tasks[0]
        assert red.task_type == "frost_alert_red"
        assert red.source == "frost"
        assert red.item_ids == ("p1", "p2")
        assert red.task_id.startswith("frost:")
        assert tasks[1].task_type == "frost_alert_orange"
        assert tasks[1].item_ids == ("p3",)

    def test_empty_alerts_no_tasks(self) -> None:
        assert generate_frost_tasks(_state(frost_alerts=())) == []

    def test_far_future_alert_skipped(self) -> None:
        alert = FrostAlert(
            date=(TODAY + datetime.timedelta(days=200)).isoformat(),
            min_temp=-2.0,
            severity="red",
            affected_plant_ids=["p1"],
        )
        assert generate_frost_tasks(_state(frost_alerts=(alert,))) == []


class TestManualTasks:
    def test_dated_manual_task(self) -> None:
        manual = ManualTask(
            id="m1",
            date="2026-04-22",
            title="Sharpen the hoe",
            notes="garage shelf",
            bed_id="bed-2",
        )
        tasks = generate_manual_tasks(_state(manual_tasks=(manual,)))
        assert len(tasks) == 1
        t = tasks[0]
        assert t.task_id == "m1"
        assert t.source == "manual"
        assert t.task_type == "manual"
        assert t.title == "Sharpen the hoe"
        assert t.notes == "garage shelf"
        assert t.bed_id == "bed-2"
        assert t.start_date == datetime.date(2026, 4, 22)
        assert t.dismissible is True

    def test_far_future_manual_task_still_emitted(self) -> None:
        far = (TODAY + datetime.timedelta(days=400)).isoformat()
        manual = ManualTask(id="m1", date=far, title="Plan next-next season")
        tasks = generate_manual_tasks(_state(manual_tasks=(manual,)))
        assert len(tasks) == 1  # never filtered by urgency
        assert tasks[0].start_date == datetime.date.fromisoformat(far)

    def test_undated_manual_task_has_no_dates(self) -> None:
        manual = ManualTask(id="m1", title="Someday: build a greenhouse")
        tasks = generate_manual_tasks(_state(manual_tasks=(manual,)))
        assert len(tasks) == 1
        assert tasks[0].start_date is None
        assert tasks[0].end_date is None


class TestGenerateAll:
    def test_flat_maps_all_sources(self) -> None:
        row = PlantRowInput(
            display_name="Tomato",
            species_key="tomato",
            transplant_start=0,
            transplant_end=1,
        )
        manual = ManualTask(id="m1", date="2026-04-22", title="Hoe")
        bed = BedInput(
            bed_id="bed-1",
            name="North",
            amendment_recs=(("Lime", "Raises pH"),),
        )
        tasks = generate_all(
            _state(plant_rows=(row,), manual_tasks=(manual,), beds=(bed,))
        )
        sources = {t.source for t in tasks}
        assert {"calendar", "manual", "soil"} <= sources

    def test_dedups_by_task_id_keeping_first(self) -> None:
        # A manual task whose id collides with the calendar task's id.
        row = PlantRowInput(
            display_name="Tomato",
            species_key="tomato",
            transplant_start=0,
            transplant_end=1,
        )
        colliding = ManualTask(
            id="tomato:transplant:2026", date="2026-04-22", title="dup"
        )
        tasks = generate_all(_state(plant_rows=(row,), manual_tasks=(colliding,)))
        matches = [t for t in tasks if t.task_id == "tomato:transplant:2026"]
        assert len(matches) == 1
        # Calendar runs before manual, so the calendar task wins.
        assert matches[0].source == "calendar"

    def test_returns_task_instances(self) -> None:
        tasks = generate_all(_state())
        assert all(isinstance(t, Task) for t in tasks)
