"""``core/string_lights.layout`` — a string of lights is a line (Phase 17 L5.4, #389;
ADR-070's owner addendum). Qt-free."""

from __future__ import annotations

import math

import pytest

from open_garden_planner.core.string_lights import (
    BULB_SPACING_CM,
    MAX_BULBS_PER_STRING,
    MAX_POSTS,
    MERGE_CM,
    MIN_POST_GAP_CM,
    OTHER_POST_CLEAR_CM,
    POST_CLEAR_CM,
    bulb_count,
    layout,
)


def _filleted(points: tuple[tuple[float, float], ...], radius: float) -> list[tuple[float, float]]:
    """The three-point corner at ``points[1]`` replaced by the sampled arc #709 is about."""
    from PyQt6.QtCore import QPointF

    from open_garden_planner.core.cad_geometry import fillet_corner, sample_arc_points

    previous, corner, following = (QPointF(*point) for point in points)
    result = fillet_corner(previous, corner, following, radius)
    assert result is not None
    tangent_in, tangent_out, centre, start, span = result
    arc = sample_arc_points(centre, radius, start, span)
    return [(previous.x(), previous.y()), (tangent_in.x(), tangent_in.y()),
            *((point.x(), point.y()) for point in arc),
            (tangent_out.x(), tangent_out.y()), (following.x(), following.y())]


def _clear_of_every_post(lay) -> None:
    """Every bulb clears every post square (``POST_CLEAR_CM`` plus its ball, #709)."""
    from open_garden_planner.core.scene3d.builders.lights import BULB_RADIUS_CM, STRING_POST_CM

    reach = (STRING_POST_CM / 2.0) * math.sqrt(2.0) + BULB_RADIUS_CM + 0.5
    for bulb in lay.bulbs:
        x, y = lay.bulb_xy(bulb)
        for px, py in lay.posts:
            assert math.hypot(x - px, y - py) >= reach, (bulb, (px, py), (x, y))


@pytest.mark.parametrize("radius", [25.0, 100.0])
def test_a_filleted_string_is_not_a_wall_of_posts(radius: float) -> None:
    """#709: a filleted L used to stand 21 (r 25) / 41 (r 100) posts in a 39 / 157 cm
    arc. Posts now follow the line at least ``MIN_POST_GAP_CM`` apart, so the arc is a
    few straight chords and the bulbs keep clear of every post."""
    lay = layout(_filleted(((0.0, 0.0), (400.0, 0.0), (400.0, 400.0)), radius))
    assert lay.posts
    assert len(lay.posts) <= math.ceil(lay.length_cm / MIN_POST_GAP_CM) + 2
    # the span is the CHORD between two posts: a 40 cm chord at r 100 is ~2 cm shorter
    # than its arc, the sagitta the issue accepts
    assert all(span.length_cm >= MIN_POST_GAP_CM - 2.5 for span in lay.spans), (
        [round(span.length_cm, 2) for span in lay.spans])
    _clear_of_every_post(lay)


def test_a_dense_line_stands_its_posts_at_least_the_gap_apart() -> None:
    """A polyline drawn with a point every centimetre (a freehand curve, a file) is not
    a post every centimetre: the first and the drawn last point stay, the rest follow."""
    lay = layout([(float(index), 0.0) for index in range(1000)])
    assert len(lay.posts) == 25
    assert lay.posts[0] == (0.0, 0.0) and lay.posts[-1] == (999.0, 0.0)
    positions = [x for x, _y in lay.posts]
    assert all(b - a >= MIN_POST_GAP_CM - 1e-9 for a, b in zip(positions, positions[1:],
                                                              strict=False))


def test_a_closed_dense_loop_keeps_the_closing_span_too() -> None:
    """The closing span is a span like any other: no post lands a few centimetres before
    the first, or the first post would stand in a crowd at the loop's seam."""
    radius = 300.0
    points = [(radius * math.cos(2.0 * math.pi * index / 360.0),
               radius * math.sin(2.0 * math.pi * index / 360.0)) for index in range(361)]
    lay = layout(points)
    assert lay.is_closed
    assert 40 <= len(lay.posts) <= math.ceil(lay.length_cm / MIN_POST_GAP_CM)
    assert all(span.length_cm >= MIN_POST_GAP_CM - 0.1 for span in lay.spans)


def test_a_self_crossing_line_keeps_every_bulb_off_every_post() -> None:
    """#709's other half: a bulb could meet a FOREIGN post where the line doubles back.
    It moves along its own span until it clears every post, not only its span's two."""
    lay = layout([(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0),
                  (0.0, 0.0), (400.0, 400.0)])
    _clear_of_every_post(lay)


def test_other_post_clearance_exceeds_post_diagonal_plus_bulb_radius() -> None:
    """``OTHER_POST_CLEAR_CM`` = POST_CLEAR_CM + the 3D bulb's 2.6 cm, pinned to the
    builder's own radius so either constant cannot drift silently (#709)."""
    from open_garden_planner.core.scene3d.builders.lights import BULB_RADIUS_CM

    assert pytest.approx(POST_CLEAR_CM + BULB_RADIUS_CM) == OTHER_POST_CLEAR_CM


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
    assert walked == pytest.approx([(k + 0.5) * step for k in range(len(lay.bulbs))],
                                   abs=POST_CLEAR_CM)
    assert all(0.0 <= b.share <= 1.0 for b in lay.bulbs)


@pytest.mark.parametrize("points", [
    [(0.0, 0.0), (210.0, 40.0), (420.0, 0.0)],                       # a symmetric V, 11 bulbs
    [(0.0, 0.0), (160.0, 40.0), (300.0, 0.0)],
    [(float(60 * i), 80.0 * (i % 2)) for i in range(30)],             # a zig-zag of 30 posts
    [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0), (0.0, 0.0)],  # a closed square
], ids=["v-odd", "v", "zigzag", "loop"])
def test_no_bulb_hangs_inside_a_post(points) -> None:
    """3D review of the line: an arc length on a post put a 2.6 cm ball inside the 4 cm
    post — the middle post of every symmetric string with an odd bulb count. Every bulb
    keeps clear of EVERY post (#709: a foreign post where the line doubles back)."""
    lay = layout(points)
    assert lay.bulbs
    _clear_of_every_post(lay)


@pytest.mark.parametrize("points", [
    [(0.0, 0.0), (20.0, 0.0), (40.0, 0.0), (300.0, 0.0)],             # own spans under 40
    [(0.0, 0.0), (5.0, 0.0), (15.0, 0.0), (300.0, 0.0)],              # a line shorter than the gap
], ids=["short-spans", "tiny-spans"])
def test_a_line_shorter_than_the_gap_cannot_clear_every_post(points) -> None:
    """A line with no room for a 40 cm span keeps its first and last point (the gap is a
    promise the geometry cannot keep); its bulbs still keep ``POST_CLEAR_CM`` from its
    own span's posts, as #707 pinned."""
    lay = layout(points)
    for bulb in lay.bulbs:
        span = lay.spans[bulb.span]
        x, y = lay.bulb_xy(bulb)
        for post in (span.a, span.b):
            px, py = lay.posts[post]
            assert math.hypot(x - px, y - py) >= min(POST_CLEAR_CM, span.length_cm / 2.0) - 1e-9


@pytest.mark.parametrize(("length", "count"), [
    (0.0, 0), (-5.0, 0), (math.inf, 0), (math.nan, 0),
    (1.0, 1), (40.0, 1), (100.0, 2), (440.0, 11), (60_000.0, MAX_BULBS_PER_STRING),
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
    assert len(lay.bulbs) == MAX_BULBS_PER_STRING
    xs = [x for x, _y in lay.posts]
    assert xs == sorted(xs), "thinned in order"


def test_post_clearance_exceeds_post_diagonal_plus_bulb_radius() -> None:
    """Issue #707: POST_CLEAR_CM = 6 is safe only while
    STRING_POST_CM / 2 * sqrt(2) + BULB_RADIUS_CM stays below it."""
    from open_garden_planner.core.scene3d.builders.lights import BULB_RADIUS_CM, STRING_POST_CM

    worst_post_reach = (STRING_POST_CM / 2.0) * math.sqrt(2.0) + BULB_RADIUS_CM
    assert worst_post_reach < POST_CLEAR_CM
