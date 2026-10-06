"""#414 — one frost-date rule: what the dialog accepts is what the parser reads.

Before #414 there were independent notions of a frost date (four: the generators, the location dialog,
the succession model, and the Phase 17 spike; see ADR-049): the generator's
parser, the calendar view's duplicate parser, and the location dialog's regex.
They disagreed in both directions — the dialog accepted ``02-30`` and ``04-31``,
which the parsers then turned into "no frost date", so the dialog saved a plan
whose every task surface came up empty.

Qt-free except for the dialog test itself, which is what matters here: the
dialog must delegate to the same validator the generators use.
"""

from __future__ import annotations

import datetime

import pytest

from open_garden_planner.core.frost_dates import (
    NON_LEAP_SUBSTITUTE_MONTH_DAY,
    is_valid_frost_date,
    parse_frost,
)

# The six dates a real calendar never has. The old dialog regex accepted all six.
IMPOSSIBLE = ["02-30", "02-31", "04-31", "06-31", "09-31", "11-31"]

REAL_DATES = ["01-01", "02-28", "02-29", "03-15", "04-09", "09-20", "10-31", "12-31"]


class TestValidator:
    @pytest.mark.parametrize("value", IMPOSSIBLE)
    def test_impossible_dates_are_rejected(self, value: str) -> None:
        assert is_valid_frost_date(value) is False

    @pytest.mark.parametrize("value", REAL_DATES)
    def test_real_dates_are_accepted(self, value: str) -> None:
        assert is_valid_frost_date(value) is True

    @pytest.mark.parametrize("value", ["", None])
    def test_absent_is_valid_and_means_unset(self, value) -> None:
        assert is_valid_frost_date(value) is True

    @pytest.mark.parametrize("value", ["bad", "13-01", "1-1", "04-9", "2026-04-09", "-1-01"])
    def test_malformed_is_rejected(self, value: str) -> None:
        assert is_valid_frost_date(value) is False


class TestParser:
    def test_every_accepted_date_parses_in_a_leap_year(self) -> None:
        """No accepted value may reach the parser and become None.

        This is the exact defect: the dialog accepted it, the parser returned
        None, and the plan silently had no frost anchor.
        """
        for value in [*REAL_DATES, *IMPOSSIBLE]:
            if not is_valid_frost_date(value):
                continue
            assert parse_frost(value, 2028) is not None, (
                f"{value} passes validation but does not parse — the dialog and "
                "the parser disagree, which is #414"
            )

    def test_29_february_is_a_real_stored_value(self) -> None:
        assert is_valid_frost_date("02-29") is True
        assert parse_frost("02-29", 2028) == datetime.date(2028, 2, 29)

    def test_29_february_substitutes_one_march_in_a_non_leap_year(self) -> None:
        """The owner decision: a 29-Feb plan must not lose its whole surface."""
        assert parse_frost("02-29", 2027) == datetime.date(2027, *NON_LEAP_SUBSTITUTE_MONTH_DAY)
        assert parse_frost("02-29", 2026) == datetime.date(2026, *NON_LEAP_SUBSTITUTE_MONTH_DAY)

    @pytest.mark.parametrize("year", [2024, 2025, 2026, 2027, 2028, 2029])
    def test_a_29_february_frost_always_yields_a_date(self, year: int) -> None:
        """Never None in any year — the condition that emptied whole surfaces."""
        assert parse_frost("02-29", year) is not None

    @pytest.mark.parametrize("value", IMPOSSIBLE)
    def test_impossible_dates_still_parse_to_none(self, value: str) -> None:
        """Rejected at the boundary, and defensively None if one slips through."""
        assert parse_frost(value, 2028) is None


class TestLocationDialogUsesTheSharedRule:
    def test_dialog_rejects_the_six_impossible_dates(self, qtbot) -> None:
        from open_garden_planner.ui.dialogs.location_dialog import LocationDialog

        dialog = LocationDialog()
        qtbot.addWidget(dialog)
        for value in IMPOSSIBLE:
            assert dialog._validate_frost_date(value) is False, value

    def test_dialog_accepts_29_february(self, qtbot) -> None:
        """02-29 must stay acceptable: the shared parser knows what to do with it."""
        from open_garden_planner.ui.dialogs.location_dialog import LocationDialog

        dialog = LocationDialog()
        qtbot.addWidget(dialog)
        assert dialog._validate_frost_date("02-29") is True
        assert dialog._validate_frost_date("04-09") is True
        assert dialog._validate_frost_date("") is True


class TestStoredValueSurvivesIntoTheAnchorYears:
    """Regression: the 02-29 substitution must not become sticky (#414 review).

    ``build_plan_state`` resolves the stored ``'02-29'`` for the requested year,
    so in a non-leap year ``state.last_frost`` is already the substituted
    1 March. Any anchor year re-derived from *that* value — including a leap one
    — would parse "03-01", making a 02-29 plan behave exactly like a 03-01 plan
    in every year. ADR-049 promises the non-leap anchor sits one day later, so the
    stored string has to travel on the state.
    """

    def test_plan_state_carries_the_stored_mmdd(self) -> None:
        from open_garden_planner.core.project import ProjectManager
        from open_garden_planner.services.task_generator import build_plan_state

        pm = ProjectManager()
        pm.set_location({"frost_dates": {"last_spring_frost": "02-29"}})
        state = build_plan_state(
            scene=None, project_manager=pm, today=datetime.date(2027, 6, 1), year=2027
        )
        assert state.last_frost == datetime.date(2027, 3, 1), "substituted for this year"
        assert state.last_frost_mmdd == "02-29", (
            "the STORED value must survive so a leap anchor can still use 29 February"
        )

    def test_a_leap_anchor_year_uses_the_real_29_february(self) -> None:
        from open_garden_planner.core.project import ProjectManager
        from open_garden_planner.services.task_generator import (
            build_plan_state,
            stored_frost_mmdd,
        )

        pm = ProjectManager()
        pm.set_location({"frost_dates": {"last_spring_frost": "02-29"}})
        state = build_plan_state(
            scene=None, project_manager=pm, today=datetime.date(2027, 6, 1), year=2027
        )
        assert stored_frost_mmdd(state) == "02-29"
        assert parse_frost(stored_frost_mmdd(state), 2028) == datetime.date(2028, 2, 29)

    def test_the_fallback_still_works_when_nothing_stored(self) -> None:
        from open_garden_planner.services.task_generator import (
            PlanState,
            stored_frost_mmdd,
        )

        state = PlanState(
            today=datetime.date(2026, 6, 1),
            year=2026,
            last_frost=datetime.date(2026, 4, 9),
        )
        assert stored_frost_mmdd(state) == "04-09"
        assert stored_frost_mmdd(
            PlanState(today=datetime.date(2026, 6, 1), year=2026)
        ) == ""


class TestSuccessionUsesTheSharedParser:
    """ADR-049 claims one parser for every reader; succession was the fourth."""

    def test_a_29_february_frost_resolves_in_the_season_segments(self) -> None:
        from open_garden_planner.models.succession import compute_season_segments

        segments = compute_season_segments("02-29", "10-15", 2027)
        early = segments["early_spring"][0]
        assert early == datetime.date(2027, 3, 1) - datetime.timedelta(weeks=8)

    def test_a_leap_year_uses_the_real_29_february(self) -> None:
        from open_garden_planner.models.succession import compute_season_segments

        segments = compute_season_segments("02-29", "10-15", 2028)
        assert segments["early_spring"][0] == (
            datetime.date(2028, 2, 29) - datetime.timedelta(weeks=8)
        )

    def test_an_impossible_frost_date_is_refused_loudly(self) -> None:
        """It used to fall back to month-only boundaries, silently disagreeing
        with the task windows for the same plan on the same day."""
        from open_garden_planner.models.succession import compute_season_segments

        with pytest.raises(ValueError):
            compute_season_segments("02-30", "10-15", 2027)
