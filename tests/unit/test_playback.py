"""Year and day playback of the shared sim clock (Phase 17 L5.1, #389, ADR-070)."""

from __future__ import annotations

from datetime import date, time

import pytest

from open_garden_planner.core.playback import (
    DAY_STEP_MINUTES,
    DEFAULT_SPEED,
    SPEEDS,
    STEP_MS,
    YEAR_STEP_DAYS,
    PlaybackMode,
    next_step,
)
from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE

DAY, YEAR = PlaybackMode.DAY, PlaybackMode.YEAR


def test_normal_day_playback_is_phase_14s_animate() -> None:
    """FR-SUN-04's Animate: 10 minutes every 200 ms — the default speed keeps it."""
    assert (STEP_MS, DEFAULT_SPEED, DAY_STEP_MINUTES[DEFAULT_SPEED]) == (200, "normal", 10)
    step = next_step(DAY, "normal", date(2026, 6, 21), time(12, 0))
    assert (step.plan_date, step.time_of_day) == (date(2026, 6, 21), time(12, 10))


@pytest.mark.parametrize("speed", SPEEDS)
def test_a_day_step_never_changes_the_plan_date(speed: str) -> None:
    """The day wraps at midnight onto the SAME date: nothing keyed on the date (plant
    presence, growth) changes while a day plays."""
    day = date(2026, 3, 29)                 # a spring-forward day in Europe
    moment = time(23, 55)
    for _ in range(400):
        step = next_step(DAY, speed, day, moment)
        assert step.plan_date == day
        moment = step.time_of_day
    assert moment.second == 0 and moment.microsecond == 0


def test_a_day_wraps_at_midnight() -> None:
    step = next_step(DAY, "fast", date(2026, 6, 21), time(23, 50))
    assert step == next_step(DAY, "fast", date(2026, 6, 21), time(23, 50))
    assert (step.plan_date, step.time_of_day) == (date(2026, 6, 21), time(0, 20))


@pytest.mark.parametrize("speed", SPEEDS)
def test_a_year_step_keeps_the_time_and_moves_the_date(speed: str) -> None:
    step = next_step(YEAR, speed, date(2026, 5, 1), time(14, 30))
    assert step.time_of_day == time(14, 30)
    assert (step.plan_date - date(2026, 5, 1)).days == YEAR_STEP_DAYS[speed]


@pytest.mark.parametrize(("year", "speed"), [(2026, "fast"), (2028, "fast"), (2028, "normal"),
                                             (2027, "slow")])
def test_a_year_wraps_into_the_same_year(year: int, speed: str) -> None:
    """The seasons play inside the plan's year: the step after the last days of a
    year is in the first days of the SAME year — leap years included."""
    day = date(year, 12, 31)
    step = next_step(YEAR, speed, day, time(12, 0))
    assert step.plan_date.year == year
    gone = YEAR_STEP_DAYS[speed]
    assert (step.plan_date - date(year, 1, 1)).days == (day.toordinal() + gone) - date(year + 1, 1, 1).toordinal()


def test_a_whole_year_of_steps_visits_every_season_and_stays_in_the_year() -> None:
    day, seen = date(2027, 1, 1), set()
    for _ in range(365 // YEAR_STEP_DAYS["normal"] + 2):
        day = next_step(YEAR, "normal", day, time(12, 0)).plan_date
        assert day.year == 2027
        seen.add(day.month)
    assert seen == set(range(1, 13))


@pytest.mark.parametrize("day", [MIN_PLAN_DATE, MAX_PLAN_DATE])
def test_playback_never_leaves_the_clocks_range(day: date) -> None:
    for mode in PlaybackMode:
        for speed in SPEEDS:
            step = next_step(mode, speed, day, time(23, 59))
            assert MIN_PLAN_DATE <= step.plan_date <= MAX_PLAN_DATE


def test_an_unknown_speed_is_refused() -> None:
    with pytest.raises(ValueError, match="speed"):
        next_step(DAY, "warp", date(2026, 1, 1), time(0, 0))


def test_speeds_grow() -> None:
    assert [DAY_STEP_MINUTES[s] for s in SPEEDS] == sorted(DAY_STEP_MINUTES.values())
    assert [YEAR_STEP_DAYS[s] for s in SPEEDS] == sorted(YEAR_STEP_DAYS.values())
    assert set(DAY_STEP_MINUTES) == set(YEAR_STEP_DAYS) == set(SPEEDS)
