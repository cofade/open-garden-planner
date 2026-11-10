"""The rule that wraps the main window's toolbar row (#796)."""

from __future__ import annotations

import pytest

from open_garden_planner.ui.widgets.toolbar_rows import rows_for_width

#: The three toolbars' measured size hints: core tools, constraints, categories + search.
MAIN, CONSTRAINTS, CATEGORIES = 192, 819, 656


@pytest.mark.parametrize(
    ("available", "expected"),
    [
        pytest.param(1920, [False, False, False], id="full-hd-one-row"),
        pytest.param(1667, [False, False, False], id="exactly-wide-enough"),
        pytest.param(1666, [False, False, True], id="one-pixel-short"),
        pytest.param(1280, [False, False, True], id="1280-categories-on-their-own-row"),
        pytest.param(1000, [False, True, True], id="every-toolbar-on-its-own-row"),
        pytest.param(100, [False, True, True], id="narrower-than-one-toolbar"),
    ],
)
def test_a_toolbar_that_does_not_fit_starts_a_row(available: int, expected: list[bool]) -> None:
    assert rows_for_width([MAIN, CONSTRAINTS, CATEGORIES], available) == expected


def test_the_first_toolbar_never_starts_a_row() -> None:
    assert rows_for_width([5000], 100) == [False]
    assert rows_for_width([], 100) == []


def test_a_hidden_toolbar_takes_no_room_and_starts_no_row() -> None:
    """The soil overlay's toolbar is in the row and hidden most of the time."""
    assert rows_for_width([MAIN, CONSTRAINTS, CATEGORIES, 0], 1667) == [False, False, False, False]
    assert rows_for_width([MAIN, CONSTRAINTS, 0, CATEGORIES], 1280) == [False, False, False, True]


def test_a_later_toolbar_joins_the_new_row_while_it_fits() -> None:
    """At 1280 the categories and the soil overlay share the second row."""
    assert rows_for_width([MAIN, CONSTRAINTS, CATEGORIES, 560], 1280) == [False, False, True, False]
    assert rows_for_width([MAIN, CONSTRAINTS, CATEGORIES, 560], 1920) == [False, False, False, True]
