"""#945 - the plan's own time zone, read from its garden location."""

from __future__ import annotations

from datetime import UTC, date, datetime

from open_garden_planner.core.plan_time import (
    LOCATION_TIMEZONE_KEY,
    plan_timezone,
    plan_timezone_name,
    plan_today,
    timezone_names,
)


class TestPlanTimezoneName:
    def test_a_named_zone_is_read_and_trimmed(self) -> None:
        assert plan_timezone_name({"timezone": " Europe/Berlin "}) == "Europe/Berlin"

    def test_no_location_or_no_key_means_the_computer_zone(self) -> None:
        assert plan_timezone_name(None) is None
        assert plan_timezone_name({}) is None
        assert plan_timezone_name({LOCATION_TIMEZONE_KEY: ""}) is None
        assert plan_timezone_name({LOCATION_TIMEZONE_KEY: "   "}) is None

    def test_a_non_string_is_ignored_rather_than_failing_the_plan(self) -> None:
        assert plan_timezone_name({"timezone": 2}) is None
        assert plan_timezone_name({"timezone": None}) is None


class TestPlanTimezone:
    def test_a_known_zone_resolves(self) -> None:
        zone = plan_timezone({"timezone": "Europe/Berlin"})
        assert zone is not None
        assert zone.key == "Europe/Berlin"

    def test_an_unknown_zone_falls_back_to_the_computer(self) -> None:
        assert plan_timezone({"timezone": "Mars/Olympus_Mons"}) is None

    def test_a_traversal_looking_name_is_not_resolved(self) -> None:
        assert plan_timezone({"timezone": "../../etc/passwd"}) is None

    def test_the_picker_offers_iana_names(self) -> None:
        names = timezone_names()
        assert "Europe/Berlin" in names
        assert list(names) == sorted(names)


class TestPlanToday:
    def test_the_garden_date_can_be_a_day_ahead_of_utc(self) -> None:
        # 23:30 UTC on 20 November is already 21 November in Tokyo.
        moment = datetime(2026, 11, 20, 23, 30, tzinfo=UTC)
        assert plan_today({"timezone": "Asia/Tokyo"}, now=moment) == date(2026, 11, 21)
        assert plan_today({"timezone": "America/New_York"}, now=moment) == date(
            2026, 11, 20
        )

    def test_no_zone_reads_the_computer(self) -> None:
        moment = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
        expected = moment.astimezone().date()
        assert plan_today({}, now=moment) == expected

    def test_the_garden_can_be_a_day_behind_utc(self) -> None:
        # 00:30 UTC on 1 January is still 31 December in Los Angeles.
        moment = datetime(2026, 1, 1, 0, 30, tzinfo=UTC)
        assert plan_today(
            {"timezone": "America/Los_Angeles"}, now=moment
        ) == date(2025, 12, 31)
