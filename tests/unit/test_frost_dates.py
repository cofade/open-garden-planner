"""#414 — one frost-date rule: what the dialog accepts is what the parser reads.

Before #414 there were three independent notions of a frost date: the generator's
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

from open_garden_planner.services.frost_dates import (
    NON_LEAP_SUBSTITUTE_MM_DD,
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
        assert parse_frost("02-29", 2027) == datetime.date(2027, *NON_LEAP_SUBSTITUTE_MM_DD)
        assert parse_frost("02-29", 2026) == datetime.date(2026, *NON_LEAP_SUBSTITUTE_MM_DD)

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
