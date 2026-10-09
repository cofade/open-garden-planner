"""Phase 17 L1.0 (#385) — one simulation clock for every sun/growth surface.

Qt-free: no ``qtbot``, no QApplication. The L1.0 gate is "a time change never
fires ``date_changed``" — pinned here by sweeps over every minute of an ordinary
day and of both DST transition days, in the system zone (always) and in IANA
zones (where the platform has tz data — CI Linux does, a bare Windows venv does
not, so those cases skip there and run in CI).
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from open_garden_planner.core import sim_clock
from open_garden_planner.core.sim_clock import (
    MAX_PLAN_DATE,
    MIN_PLAN_DATE,
    Channel,
    SimChange,
    SimClock,
    SimInstant,
)

TOKYO_FIXED = timezone(timedelta(hours=9))
LA_FIXED = timezone(timedelta(hours=-7))

# The two 2026 transition days of the EU rule (last Sunday of March / October).
EU_SPRING_FORWARD = date(2026, 3, 29)
EU_FALL_BACK = date(2026, 10, 25)


def _zone(key: str) -> tzinfo:
    try:
        return ZoneInfo(key)
    except ZoneInfoNotFoundError:
        pytest.skip(f"no IANA tz data for {key} on this platform")


def _every_minute() -> list[time]:
    return [time(m // 60, m % 60) for m in range(24 * 60)]


class _Spy:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def __call__(self, value: object) -> None:
        self.calls.append(value)


# ── SimInstant ────────────────────────────────────────────────────────────────


class TestSimInstant:
    def test_naive_input_is_wall_time(self) -> None:
        instant = SimInstant.from_datetime(datetime(2026, 6, 21, 14, 5), TOKYO_FIXED)
        assert instant.plan_date == date(2026, 6, 21)
        assert instant.time_of_day == time(14, 5)
        assert instant.utc == datetime(2026, 6, 21, 5, 5, tzinfo=UTC)

    def test_aware_input_is_the_instant(self) -> None:
        moment = datetime(2026, 6, 21, 16, 0, tzinfo=UTC)
        instant = SimInstant.from_datetime(moment, TOKYO_FIXED)
        assert instant.utc == moment
        assert instant.wall == datetime(2026, 6, 22, 1, 0)

    def test_plan_date_is_the_local_day_not_the_utc_day(self) -> None:
        """The bug L1.0 fixes: the overlay grew plants for the UTC date, the
        heatmap for the toolbar's local date — a day apart after local midnight
        east of UTC (and before it west of UTC)."""
        east = SimInstant.from_datetime(datetime(2026, 6, 22, 1, 0), TOKYO_FIXED)
        assert east.plan_date == date(2026, 6, 22)
        assert east.utc.date() == date(2026, 6, 21)
        west = SimInstant.from_datetime(datetime(2026, 6, 21, 22, 0), LA_FIXED)
        assert west.plan_date == date(2026, 6, 21)
        assert west.utc.date() == date(2026, 6, 22)

    def test_microseconds_are_dropped_seconds_kept(self) -> None:
        instant = SimInstant.from_datetime(datetime(2026, 6, 21, 14, 5, 33, 999_999))
        assert instant.time_of_day == time(14, 5, 33)
        assert instant.minute_of_day == 14 * 60 + 5

    def test_local_is_aware_and_names_the_same_instant(self) -> None:
        instant = SimInstant.from_datetime(datetime(2026, 6, 21, 12, 0), TOKYO_FIXED)
        assert instant.local.tzinfo is not None
        assert instant.local == instant.utc
        assert instant.local.utcoffset() == timedelta(hours=9)

    def test_system_zone_round_trip(self) -> None:
        moment = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
        assert SimInstant.from_datetime(moment).utc == moment

    def test_aware_time_of_day_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="naive"):
            SimInstant(date(2026, 6, 21), time(12, 0, tzinfo=UTC))

    def test_datetime_as_plan_date_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="date"):
            SimInstant(datetime(2026, 6, 21, 12, 0), time(12, 0))  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "day",
        [date(1752, 9, 14), date(1960, 1, 1), date(1970, 12, 31), date(3000, 1, 1)],
    )
    def test_dates_outside_the_platform_safe_range_are_rejected(self, day: date) -> None:
        """Windows' system-zone conversion raises OSError outside 1970–3000;
        the clock refuses earlier, with a ValueError naming the range."""
        with pytest.raises(ValueError, match="supported range"):
            SimInstant(day, time(12, 0))
        with pytest.raises(ValueError, match="supported range"):
            SimInstant.from_datetime(datetime.combine(day, time(12, 0)))
        with pytest.raises(ValueError, match="supported range"):
            SimInstant.from_datetime(datetime.combine(day, time(12, 0), tzinfo=UTC))

    @pytest.mark.parametrize("tz", [None, TOKYO_FIXED, LA_FIXED], ids=["system", "+09:00", "-07:00"])
    @pytest.mark.parametrize("day", [MIN_PLAN_DATE, MAX_PLAN_DATE])
    def test_range_edges_convert_in_every_zone(self, day: date, tz: tzinfo | None) -> None:
        for t in (time(0, 0), time(23, 59)):
            instant = SimInstant(day, t, tz)
            assert SimInstant.from_datetime(instant.utc, tz) == instant

    @pytest.mark.parametrize(
        "tz",
        [None, TOKYO_FIXED, LA_FIXED, "Europe/Berlin", "America/New_York"],
        ids=["system", "+09:00", "-07:00", "Berlin", "New_York"],
    )
    def test_every_half_hour_of_a_year_round_trips_exactly(
        self, tz: tzinfo | str | None
    ) -> None:
        zone = _zone(tz) if isinstance(tz, str) else tz
        start = datetime(2026, 1, 1, tzinfo=UTC)
        for step in range(365 * 48):
            moment = start + timedelta(minutes=30 * step)
            assert SimInstant.from_datetime(moment, zone).utc == moment, moment

    def test_repeated_fall_back_hour_keeps_both_occurrences(self) -> None:
        berlin = _zone("Europe/Berlin")
        first = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # 02:30 CEST
        second = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)  # 02:30 CET
        a = SimInstant.from_datetime(first, berlin)
        b = SimInstant.from_datetime(second, berlin)
        assert a.wall == b.wall  # same wall clock reading …
        assert a != b  # … but different instants: fold is part of equality
        assert (a.utc, b.utc) == (first, second)


# ── SimClock ──────────────────────────────────────────────────────────────────


class TestSeed:
    def test_explicit_seed(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 14, 5, 33, 123), tz=TOKYO_FIXED)
        assert clock.plan_date == date(2026, 6, 21)
        assert clock.time_of_day == time(14, 5, 33)
        assert clock.tz is TOKYO_FIXED

    def test_default_seed_is_now_to_the_minute(self) -> None:
        before = datetime.now(UTC).replace(second=0, microsecond=0)
        clock = SimClock()
        after = datetime.now(UTC)
        assert clock.time_of_day.second == 0
        assert before <= clock.utc <= after

    def test_properties_agree(self) -> None:
        clock = SimClock(datetime(2026, 6, 22, 1, 0), tz=TOKYO_FIXED)
        assert clock.instant.plan_date == clock.plan_date
        assert clock.wall == datetime(2026, 6, 22, 1, 0)
        assert clock.utc == datetime(2026, 6, 21, 16, 0, tzinfo=UTC)
        assert clock.local == clock.utc


class TestTransitions:
    def test_time_change_fires_only_instant_changed(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))
        dates, instants = _Spy(), _Spy()
        clock.date_changed.connect(dates)
        clock.instant_changed.connect(instants)
        change = clock.set_time_of_day(time(15, 30))
        assert dates.calls == []
        assert instants.calls == [change]
        assert isinstance(change, SimChange)
        assert change.time_changed and not change.date_changed
        assert clock.plan_date == date(2026, 6, 21)

    def test_date_change_fires_date_changed_then_instant_changed(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))
        order: list[str] = []
        clock.date_changed.connect(lambda day: order.append(f"date {day}"))
        clock.instant_changed.connect(lambda _change: order.append("instant"))
        change = clock.set_date(date(2031, 6, 21))
        assert order == ["date 2031-06-21", "instant"]
        assert change is not None and change.date_changed and not change.time_changed
        assert clock.time_of_day == time(12, 0)

    def test_set_datetime_can_change_both(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))
        dates = _Spy()
        clock.date_changed.connect(dates)
        change = clock.set_datetime(datetime(2026, 12, 21, 9, 0))
        assert dates.calls == [date(2026, 12, 21)]
        assert change is not None and change.date_changed and change.time_changed

    def test_listeners_see_the_new_state(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))
        seen: list[tuple[date, time]] = []
        clock.date_changed.connect(
            lambda _day: seen.append((clock.plan_date, clock.time_of_day))
        )
        clock.set_datetime(datetime(2027, 1, 2, 8, 15))
        assert seen == [(date(2027, 1, 2), time(8, 15))]

    @pytest.mark.parametrize(
        "write",
        [
            lambda c: c.set_datetime(datetime(2026, 6, 21, 12, 0)),
            lambda c: c.set_date(date(2026, 6, 21)),
            lambda c: c.set_time_of_day(time(12, 0)),
            lambda c: c.set_time_of_day(time(12, 0, 0, 500)),  # sub-second only
        ],
        ids=["datetime", "date", "time", "microseconds"],
    )
    def test_no_op_write_emits_nothing_and_returns_none(self, write) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))
        spy = _Spy()
        clock.date_changed.connect(spy)
        clock.instant_changed.connect(spy)
        assert write(clock) is None
        assert spy.calls == []

    def test_set_date_rejects_a_datetime(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))
        with pytest.raises(TypeError, match="date"):
            clock.set_date(datetime(2026, 6, 22, 12, 0))  # type: ignore[arg-type]

    def test_out_of_range_write_changes_nothing(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))
        spy = _Spy()
        clock.instant_changed.connect(spy)
        with pytest.raises(ValueError, match="supported range"):
            clock.set_date(date(1960, 1, 1))
        assert clock.plan_date == date(2026, 6, 21)
        assert spy.calls == []

    def test_set_time_of_day_rejects_an_aware_time(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))
        with pytest.raises(ValueError, match="naive"):
            clock.set_time_of_day(time(12, 0, tzinfo=UTC))

    def test_switching_between_fold_occurrences_is_a_change(self) -> None:
        berlin = _zone("Europe/Berlin")
        clock = SimClock(datetime(2026, 10, 25, 0, 30, tzinfo=UTC), tz=berlin)
        dates = _Spy()
        clock.date_changed.connect(dates)
        change = clock.set_datetime(datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
        assert change is not None and change.time_changed
        assert dates.calls == []
        assert clock.utc == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)


class TestTimeChangeNeverFiresDateChanged:
    """The L1.0 gate, swept rather than sampled."""

    @staticmethod
    def _sweep(clock: SimClock, day: date) -> None:
        dates = _Spy()
        clock.date_changed.connect(dates)
        for t in _every_minute():
            clock.set_time_of_day(t)
            assert clock.plan_date == day, t
        # Wrap past midnight as the toolbar's animation does: 23:59 → 00:00 of
        # the SAME plan date, not the next one.
        clock.set_time_of_day(time(0, 0))
        assert dates.calls == []
        assert clock.plan_date == day

    @pytest.mark.parametrize(
        "day", [date(2026, 6, 21), EU_SPRING_FORWARD, EU_FALL_BACK]
    )
    def test_system_zone(self, day: date) -> None:
        self._sweep(SimClock(datetime.combine(day, time(12, 0))), day)

    @pytest.mark.parametrize("day", [EU_SPRING_FORWARD, EU_FALL_BACK])
    def test_berlin(self, day: date) -> None:
        berlin = _zone("Europe/Berlin")
        self._sweep(SimClock(datetime.combine(day, time(12, 0)), tz=berlin), day)

    @pytest.mark.parametrize("day", [date(2026, 3, 8), date(2026, 11, 1)])
    def test_new_york(self, day: date) -> None:
        new_york = _zone("America/New_York")
        self._sweep(SimClock(datetime.combine(day, time(12, 0)), tz=new_york), day)

    @pytest.mark.parametrize("tz", [TOKYO_FIXED, LA_FIXED], ids=["+09:00", "-07:00"])
    def test_fixed_offsets_far_from_utc(self, tz: tzinfo) -> None:
        day = date(2026, 6, 21)
        self._sweep(SimClock(datetime.combine(day, time(12, 0)), tz=tz), day)

    def test_skipped_spring_forward_hour_leaves_the_date_alone(self) -> None:
        berlin = _zone("Europe/Berlin")
        clock = SimClock(datetime(2026, 3, 29, 1, 50), tz=berlin)
        dates = _Spy()
        clock.date_changed.connect(dates)
        clock.set_time_of_day(time(2, 30))  # a wall time that does not exist
        assert clock.plan_date == EU_SPRING_FORWARD
        assert dates.calls == []
        assert clock.utc.date() == EU_SPRING_FORWARD


class TestReentrancyAndErrors:
    def test_write_from_a_listener_raises(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))
        clock.instant_changed.connect(lambda _c: clock.set_time_of_day(time(9, 0)))
        with pytest.raises(RuntimeError, match="notification"):
            clock.set_time_of_day(time(15, 0))

    def test_a_raising_listener_does_not_leave_the_clock_stuck(self) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0))

        def boom(_change: SimChange) -> None:
            raise LookupError("listener bug")

        clock.instant_changed.connect(boom)
        with pytest.raises(LookupError):
            clock.set_time_of_day(time(15, 0))
        assert clock.time_of_day == time(15, 0)  # state committed before emit
        clock.instant_changed.disconnect(boom)
        assert clock.set_time_of_day(time(16, 0)) is not None


# ── Channel ───────────────────────────────────────────────────────────────────


class TestChannel:
    def test_connect_is_idempotent(self) -> None:
        channel: Channel[int] = Channel()
        spy = _Spy()
        channel.connect(spy)
        channel.connect(spy)
        assert channel.receiver_count() == 1
        channel.emit(7)
        assert spy.calls == [7]

    def test_disconnect_stops_delivery(self) -> None:
        channel: Channel[int] = Channel()
        spy = _Spy()
        channel.connect(spy)
        channel.disconnect(spy)
        channel.emit(7)
        assert spy.calls == []
        assert channel.receiver_count() == 0

    def test_disconnecting_an_unknown_listener_raises(self) -> None:
        channel: Channel[int] = Channel()
        with pytest.raises(ValueError):
            channel.disconnect(_Spy())

    def test_bound_methods_compare_by_target(self) -> None:
        channel: Channel[int] = Channel()
        spy = _Spy()
        channel.connect(spy.__call__)
        channel.connect(spy.__call__)  # a fresh bound-method object, same target
        assert channel.receiver_count() == 1
        channel.disconnect(spy.__call__)
        assert channel.receiver_count() == 0

    def test_listener_disconnecting_itself_during_emit(self) -> None:
        channel: Channel[int] = Channel()
        later = _Spy()

        def once(value: int) -> None:
            channel.disconnect(once)

        channel.connect(once)
        channel.connect(later)
        channel.emit(1)  # delivery to `later` must not be skipped
        channel.emit(2)
        assert later.calls == [1, 2]


# ── Qt-free contract ─────────────────────────────────────────────────────────


def test_module_is_qt_free() -> None:
    """Epic #383: the sim clock is a Qt-free core (engine-independent, NO-GO
    insurance, headless tests). Only the standard library may be imported."""
    path = Path(sim_clock.__file__)
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported <= {
        "__future__",
        "collections.abc",
        "dataclasses",
        "datetime",
        "typing",
    }, imported
