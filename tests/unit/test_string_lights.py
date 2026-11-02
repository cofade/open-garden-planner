"""``core/string_lights.layout`` — a string of lights is a line (Phase 17 L5.4, #389;
ADR-070's owner addendum). Qt-free."""

from __future__ import annotations

import math

import pytest

from open_garden_planner.core.string_lights import (
    BULB_SPACING_CM,
    MAX_BULBS,
    MAX_POSTS,
    MERGE_CM,
    bulb_count,
    layout,
)


def test_a_post_at_every_point_and_a_span_between_each_two() -> None:
    lay = layout([(0.0, 0.0), (300.0, 0.0), (300.0, 400.0)])
    assert lay.posts == ((0.0, 0.0), (300.0, 0.0), (300.0, 400.0))
    assert [(s.a, s.b, s.length_cm) for s in lay.spans] == [(0, 1, 300.0), (1, 2, 400.0)]
    assert len(lay.bulbs) == round(700.0 / BULB_SPACING_CM)


def test_the_bulbs_are_evenly_spaced_along_the_wire() -> None:
    lay = layout([(0.0, 0.0), (120.0, 0.0), (120.0, 330.0)])
    starts = [0.0, 120.0]
    walked = [starts[b.span] + b.share * lay.spans[b.span].length_cm for b in lay.bulbs]
    step = lay.length_cm / len(lay.bulbs)
    assert walked == pytest.approx([(k + 0.5) * step for k in range(len(lay.bulbs))])
    assert all(0.0 <= b.share <= 1.0 for b in lay.bulbs)


@pytest.mark.parametrize(("length", "count"), [
    (0.0, 0), (-5.0, 0), (math.inf, 0), (math.nan, 0),
    (1.0, 1), (40.0, 1), (100.0, 2), (440.0, 11), (60_000.0, MAX_BULBS),
])
def test_how_many_bulbs(length: float, count: int) -> None:
    assert bulb_count(length) == count


def test_near_duplicates_are_one_post_and_non_finite_points_are_dropped() -> None:
    lay = layout([(0.0, 0.0), (0.4, 0.3), (math.nan, 5.0), (200.0, 0.0), (math.inf, 1.0),
                  (200.0 + MERGE_CM / 2.0, 0.0)])
    assert lay.posts == ((0.0, 0.0), (200.0, 0.0))


def test_a_closed_line_does_not_repeat_its_first_post_and_spans_back_to_it() -> None:
    lay = layout([(0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 0.0)])
    assert len(lay.posts) == 3
    assert (lay.spans[-1].a, lay.spans[-1].b) == (2, 0)
    assert lay.length_cm == pytest.approx(400.0 + 300.0 + 500.0)


@pytest.mark.parametrize("points", [[], [(1.0, 2.0)], [(1.0, 2.0), (1.2, 2.1)],
                                    [(math.nan, math.nan)] * 4], ids=["none", "one", "merged", "nan"])
def test_no_wire_without_two_posts(points) -> None:
    lay = layout(points)
    assert len(lay.posts) <= 1 and not lay.spans and not lay.bulbs


def test_a_line_of_twenty_thousand_points_stands_on_max_posts() -> None:
    """A crafted plan can hold a line of any length (security review of #389): the posts
    are thinned to ``MAX_POSTS``, evenly, the first and last kept — which bounds the
    canvas's picture and the 3D model; the bulbs are capped as always."""
    points = [(float(i) * 10.0, 30.0 * (i % 2)) for i in range(20_000)]
    lay = layout(points)
    assert len(lay.posts) == MAX_POSTS and len(lay.spans) == MAX_POSTS - 1
    assert lay.posts[0] == points[0] and lay.posts[-1] == points[-1]
    assert len(lay.bulbs) == MAX_BULBS
    xs = [x for x, _y in lay.posts]
    assert xs == sorted(xs), "thinned in order"
