"""The contrast arithmetic every canvas label relies on (#793, ``core.legibility``)."""

from __future__ import annotations

import pytest

from open_garden_planner.core.legibility import (
    DARK_HALO,
    INK_CONTRAST_TARGET,
    LIGHT_HALO,
    MIN_TEXT_CONTRAST,
    contrast_ratio,
    halo_for,
    legible_ink,
    relative_luminance,
)


def test_the_stated_minimum_is_wcag_aa_and_inks_are_given_more() -> None:
    assert MIN_TEXT_CONTRAST == 4.5
    assert INK_CONTRAST_TARGET == 7.0


def test_luminance_and_contrast_match_the_wcag_reference_values() -> None:
    assert relative_luminance((0, 0, 0)) == 0.0
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0)
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert contrast_ratio((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0)
    assert contrast_ratio((120, 120, 120), (120, 120, 120)) == pytest.approx(1.0)
    # the WCAG worked example: #777777 on white is 4.48:1, just under AA
    assert contrast_ratio((119, 119, 119), (255, 255, 255)) == pytest.approx(4.48, abs=0.01)


def test_a_dark_ink_gets_the_light_halo_and_a_light_ink_the_dark_one() -> None:
    assert halo_for((0, 0, 0)) == LIGHT_HALO
    assert halo_for((40, 56, 40)) == LIGHT_HALO
    assert halo_for((255, 255, 255)) == DARK_HALO
    assert halo_for((240, 235, 200)) == DARK_HALO
    assert halo_for((255, 255, 0)) == DARK_HALO


def test_the_constraint_colours_all_keep_the_light_halo() -> None:
    """One look for every dimension label: a mid-tone ink is darkened, not edged in black."""
    for ink in [(0, 120, 200), (220, 40, 40), (120, 0, 180), (200, 100, 0), (140, 0, 180),
                (0, 160, 200), (20, 160, 100), (180, 130, 0)]:
        assert halo_for(ink) == LIGHT_HALO, ink


def test_an_ink_that_already_contrasts_is_left_alone() -> None:
    assert legible_ink((0, 0, 0), LIGHT_HALO) == (0, 0, 0)
    assert legible_ink((40, 56, 40), LIGHT_HALO) == (40, 56, 40)     # the scale bar: 12.6:1
    assert legible_ink((60, 60, 60), LIGHT_HALO) == (60, 60, 60)     # the area label: 10.4:1
    assert legible_ink((0, 120, 200), LIGHT_HALO, MIN_TEXT_CONTRAST) == (0, 120, 200)


@pytest.mark.parametrize(
    "ink",
    [
        (200, 100, 0),    # angle / equal constraint orange: 3.98:1 on white
        (20, 160, 100),   # parallel green: 3.36:1
        (180, 130, 0),    # fix-in-place gold: 3.42:1
        (0, 160, 200),    # coincident teal: 3.06:1
        (0, 120, 200),    # distance blue: 4.64:1 as colours, 3.5:1 as painted
        (220, 40, 40),    # violated red: 4.79:1
        (119, 119, 119),  # WCAG's own near miss: 4.48:1
    ],
)
def test_a_weak_ink_is_moved_until_it_reaches_the_target(ink) -> None:
    halo = halo_for(ink)
    assert halo == LIGHT_HALO
    assert contrast_ratio(ink, halo) < INK_CONTRAST_TARGET
    result = legible_ink(ink, halo)
    assert contrast_ratio(result, halo) >= INK_CONTRAST_TARGET
    assert result != ink
    # darkened, hue kept: no channel grows, and the strongest stays the strongest
    assert all(new <= old for new, old in zip(result, ink, strict=True))
    assert result.index(max(result)) == ink.index(max(ink))
    # and no further than it has to: still a colour, not black
    assert contrast_ratio(result, halo) < INK_CONTRAST_TARGET * 1.25


@pytest.mark.parametrize("red", range(0, 256, 51))
@pytest.mark.parametrize("green", range(0, 256, 51))
@pytest.mark.parametrize("blue", range(0, 256, 51))
def test_every_colour_ends_up_readable_on_its_halo(red: int, green: int, blue: int) -> None:
    ink = (red, green, blue)
    halo = halo_for(ink)
    assert contrast_ratio(legible_ink(ink, halo), halo) >= INK_CONTRAST_TARGET
