"""Year and day playback of the shared sim clock (Phase 17 L5.1, #389, ADR-070). Qt-free.

The "Animate" control of the Plan & Sun toolbar plays the ONE sim clock
(``core/sim_clock.py``, ADR-053): it is a writer like any other — it hands the clock
a wall reading or a plan date, the clock notifies, and the shadow overlay, the
hours-of-sun map, the 3D light and the 3D growth follow on their own
subscriptions. This module is the arithmetic of one step, so that the rules are
pinned in the GPU-less tier and no view keeps a moment of its own.

Two modes:

- **Day** — the time of day advances by the speed's minutes per step and wraps at
  midnight onto the SAME plan date: a day plays again and again, and nothing that
  is keyed on the date (plant presence, growth) changes while it plays.
- **Year** — the plan date advances by the speed's days per step at the SAME time
  of day, and wraps from the last day of the year to the first of the same year:
  the seasons play again and again inside the year the plan date is in. A plan
  date never leaves the clock's range this way (``MIN_PLAN_DATE`` … ``MAX_PLAN_DATE``
  are whole years).

The step interval is the same for both (``STEP_MS``). A year step changes the plan
date, and the 3D view regrows at most once per ``DATE_REGROW_MIN_MS`` while the date
keeps changing (``ui/view3d/sync_controller.py``) — the light follows every step.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final

from .sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE

__all__ = ["DAY_STEP_MINUTES", "DEFAULT_SPEED", "SPEEDS", "STEP_MS", "YEAR_STEP_DAYS",
           "PlaybackMode", "PlaybackStep", "next_step"]


class PlaybackMode(enum.Enum):
    """What one step of the playback advances."""

    DAY = "day"
    YEAR = "year"


#: The speeds, slowest first.
SPEEDS: Final = ("slow", "normal", "fast")
DEFAULT_SPEED: Final = "normal"
#: One step every this many milliseconds, in both modes. 200 ms is the toolbar's
#: Animate of Phase 14 (FR-SUN-04), kept so that "normal" day playback is what it was.
STEP_MS: Final = 200
#: Minutes of wall time per step of the day playback — "normal" is Phase 14's 10
#: minutes (50 minutes a second: a day in 29 s); slow 25 minutes a second, fast 2.5 h.
DAY_STEP_MINUTES: Final = {"slow": 5, "normal": 10, "fast": 30}
#: Days per step of the year playback: 5, 10 and 35 days a second — a year in 73 s,
#: 37 s and 10 s. The 3D growth follows at most twice a second whatever the speed.
YEAR_STEP_DAYS: Final = {"slow": 1, "normal": 2, "fast": 7}


@dataclass(frozen=True, slots=True)
class PlaybackStep:
    """What a step asks the clock to become: a new time of day on the same date (day
    playback) or a new plan date at the same time (year playback) — never both."""

    plan_date: date
    time_of_day: time

    @property
    def wall(self) -> datetime:
        return datetime.combine(self.plan_date, self.time_of_day)


def _speed(speed: str) -> str:
    if speed not in SPEEDS:
        raise ValueError(f"unknown playback speed {speed!r}; choose from {list(SPEEDS)}")
    return speed


def next_step(mode: PlaybackMode, speed: str, plan_date: date, time_of_day: time) -> PlaybackStep:
    """The moment one step after ``plan_date`` / ``time_of_day`` (module docstring).

    Day: ``time_of_day`` + the speed's minutes, wrapped at midnight onto ``plan_date``
    (seconds dropped, as the toolbar's minute slider shows them). Year: ``plan_date``
    + the speed's days, wrapped into the same calendar year; ``time_of_day`` is kept.
    """
    speed = _speed(speed)
    if mode is PlaybackMode.DAY:
        minute = time_of_day.hour * 60 + time_of_day.minute + DAY_STEP_MINUTES[speed]
        minute %= 24 * 60
        return PlaybackStep(plan_date, time(minute // 60, minute % 60))
    if mode is not PlaybackMode.YEAR:
        raise ValueError(f"unknown playback mode {mode!r}")
    following = plan_date + timedelta(days=YEAR_STEP_DAYS[speed])
    if following.year != plan_date.year:
        # into the first days of the same year: the seasons play inside the plan's year
        following = date(plan_date.year, 1, 1) + (following - date(following.year, 1, 1))
    following = min(max(following, MIN_PLAN_DATE), MAX_PLAN_DATE)
    return PlaybackStep(following, time_of_day)
