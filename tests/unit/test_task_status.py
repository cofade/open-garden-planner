"""Unit tests for per-task status resolution (US-C2)."""
from __future__ import annotations

import datetime

from open_garden_planner.services.task_status import (
    effective_status,
    is_visible_active,
)

TODAY = datetime.date(2026, 6, 20)


def _days(n: int) -> str:
    return (TODAY + datetime.timedelta(days=n)).isoformat()


class TestEffectiveStatus:
    def test_none_is_open(self) -> None:
        assert effective_status(None, TODAY) == "open"

    def test_empty_dict_is_open(self) -> None:
        assert effective_status({}, TODAY) == "open"

    def test_future_snooze_is_snoozed(self) -> None:
        assert effective_status({"snooze_until": _days(5)}, TODAY) == "snoozed"

    def test_past_snooze_falls_through_to_open(self) -> None:
        # snooze_until in the past → the task re-surfaces.
        assert effective_status({"snooze_until": _days(-1)}, TODAY) == "open"

    def test_snooze_today_is_not_snoozed(self) -> None:
        # Strictly greater than today is required to stay snoozed.
        assert effective_status({"snooze_until": TODAY.isoformat()}, TODAY) == "open"

    def test_dismissed(self) -> None:
        assert effective_status({"status": "dismissed"}, TODAY) == "dismissed"

    def test_done_within_7_days(self) -> None:
        assert effective_status(
            {"status": "done", "done_date": _days(-3)}, TODAY
        ) == "done"

    def test_done_exactly_7_days_is_still_done(self) -> None:
        # Boundary: > 7 archives, == 7 does not.
        assert effective_status(
            {"status": "done", "done_date": _days(-7)}, TODAY
        ) == "done"

    def test_done_more_than_7_days_archived(self) -> None:
        assert effective_status(
            {"status": "done", "done_date": _days(-8)}, TODAY
        ) == "archived"

    def test_done_without_done_date_is_archived(self) -> None:
        # Legacy task_completions folded on load carry no done_date → hidden.
        assert effective_status({"status": "done"}, TODAY) == "archived"

    def test_done_with_invalid_done_date_is_archived(self) -> None:
        assert effective_status(
            {"status": "done", "done_date": "not-a-date"}, TODAY
        ) == "archived"

    def test_unknown_status_is_open(self) -> None:
        assert effective_status({"status": "whatever"}, TODAY) == "open"

    def test_snooze_precedence_over_done(self) -> None:
        # An active future snooze wins even if status is done.
        state = {"status": "done", "done_date": _days(-30), "snooze_until": _days(5)}
        assert effective_status(state, TODAY) == "snoozed"


class TestIsVisibleActive:
    def test_open_and_done_are_visible(self) -> None:
        assert is_visible_active("open") is True
        assert is_visible_active("done") is True

    def test_others_are_hidden(self) -> None:
        assert is_visible_active("snoozed") is False
        assert is_visible_active("dismissed") is False
        assert is_visible_active("archived") is False
