"""Boundary rules independent of Qt and the current wall date."""

from datetime import date

import pytest

from open_garden_planner.core.plan_timeline import (
    instance_date,
    month_number,
    month_start,
    plant_present,
    timeline_month_range,
)


@pytest.mark.parametrize("day,present", [
    (date(2024, 3, 31), False), (date(2024, 4, 1), True),
    (date(2027, 2, 28), True), (date(2027, 3, 1), False),
    (date(2030, 6, 1), False), (None, True),
])
def test_half_open_lifetime(day, present):
    metadata = {"plant_instance": {"planting_date": "2024-04-01", "removal_date": "2027-03-01"}}
    assert plant_present(metadata, day) is present


@pytest.mark.parametrize("value", [None, True, 20260401, "2026-02-30", "20260401", "2026-W01-1", {}, []])
def test_bad_dates_are_open_bounds(value):
    metadata = {"plant_instance": {"planting_date": value, "removal_date": value}}
    assert instance_date(metadata, "planting_date") is None
    assert plant_present(metadata, date(2026, 6, 1))


def test_scrubber_bounds_include_plantings_removals_current_and_clock_limits():
    records = [{"plant_instance": {"planting_date": "1982-02-28", "removal_date": "2090-12-01"}}]
    low, high = timeline_month_range(records, date(2026, 10, 19), date(2025, 6, 1))
    assert month_start(low) == date(1981, 2, 1)
    assert month_start(high) == date(2090, 12, 1)
    assert month_start(month_number(date(2024, 2, 29))) == date(2024, 2, 1)
    assert timeline_month_range([], date(2999, 12, 31), date(1971, 1, 1)) == (
        month_number(date(1971, 1, 1)), month_number(date(2999, 12, 31)))


def test_species_task_removal_keeps_another_living_instance(qtbot):
    from open_garden_planner.services.task_generator import (
        PlanState,
        PlantRowInput,
        generate_actionable_for_surface,
        generate_for_date_window,
    )

    removed = PlantRowInput("Lettuce", "lettuce", direct_sow_start=0, direct_sow_end=8,
                            removal_date=date(2026, 6, 1))
    state = PlanState(date(2026, 6, 2), 2026, date(2026, 5, 1), plant_rows=(removed,))
    assert generate_actionable_for_surface(state) == []
    from dataclasses import replace

    historical = generate_for_date_window(replace(state, actionable_only=False), date(2026, 5, 1), date(2026, 7, 1))
    assert historical and all(t.end_date < date(2026, 6, 1) for t in historical)
    living = replace(removed, removal_date=None)
    active = generate_actionable_for_surface(replace(state, plant_rows=(removed, living)))
    assert active and active[0].end_date > date(2026, 6, 2)
