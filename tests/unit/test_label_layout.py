"""Which object labels are shown when room is short (#793, ``core.label_layout``)."""

from __future__ import annotations

import random

import pytest

from open_garden_planner.core.label_layout import (
    BADGE_MAX_OWNER_SHARE,
    LABEL_GAP_PX,
    LABEL_MIN_OWNER_PX,
    LabelCandidate,
    badge_has_room,
    place_labels,
)


def _box(x: float, y: float, w: float = 60.0, h: float = 16.0):
    return (x, y, x + w, y + h)


def _overlap(a, b, gap: float = 0.0) -> bool:
    return a[0] - gap < b[2] and b[0] - gap < a[2] and a[1] - gap < b[3] and b[1] - gap < a[3]


def test_labels_with_room_are_all_shown() -> None:
    candidates = [LabelCandidate(_box(i * 200.0, 0.0), 80.0) for i in range(5)]
    assert sorted(place_labels(candidates)) == [0, 1, 2, 3, 4]


def test_an_object_too_small_on_screen_gets_no_label() -> None:
    candidates = [
        LabelCandidate(_box(0.0, 0.0), LABEL_MIN_OWNER_PX - 0.1),
        LabelCandidate(_box(300.0, 0.0), LABEL_MIN_OWNER_PX),
    ]
    assert place_labels(candidates) == [1]


def test_the_selected_object_keeps_its_label_however_small_it_is() -> None:
    candidates = [LabelCandidate(_box(0.0, 0.0), 2.0, pinned=True)]
    assert place_labels(candidates) == [0]


def test_of_two_labels_in_one_place_the_larger_object_wins() -> None:
    candidates = [
        LabelCandidate(_box(0.0, 0.0), 40.0, tie="Chair"),
        LabelCandidate(_box(10.0, 4.0), 400.0, tie="Terrace"),
    ]
    assert place_labels(candidates) == [1]


def test_the_selected_object_wins_over_a_larger_one() -> None:
    candidates = [
        LabelCandidate(_box(0.0, 0.0), 40.0, pinned=True, tie="Chair"),
        LabelCandidate(_box(10.0, 4.0), 400.0, tie="Terrace"),
    ]
    assert place_labels(candidates) == [0]


def test_labels_keep_a_gap() -> None:
    touching = [
        LabelCandidate(_box(0.0, 0.0), 100.0, tie="a"),
        LabelCandidate(_box(60.0 + LABEL_GAP_PX - 0.5, 0.0), 100.0, tie="b"),
    ]
    assert place_labels(touching) == [0]
    apart = [
        LabelCandidate(_box(0.0, 0.0), 100.0, tie="a"),
        LabelCandidate(_box(60.0 + 2 * LABEL_GAP_PX + 0.5, 0.0), 100.0, tie="b"),
    ]
    assert sorted(place_labels(apart)) == [0, 1]


def test_the_name_is_placed_before_the_area_of_the_same_object() -> None:
    candidates = [
        LabelCandidate(_box(0.0, 0.0), 100.0, rank=1, tie="6.24 m2"),
        LabelCandidate(_box(0.0, 4.0), 100.0, rank=0, tie="Raised bed"),
    ]
    assert place_labels(candidates) == [1]


def test_the_labels_of_one_object_do_not_push_each_other_out() -> None:
    """A name and the area hung under it lie closer than the gap, by construction."""
    candidates = [
        LabelCandidate(_box(0.0, 13.0), 100.0, rank=1, tie="6.24 m2", owner="bed"),
        LabelCandidate(_box(0.0, 0.0), 100.0, rank=0, tie="Raised bed", owner="bed"),
    ]
    assert place_labels(candidates) == [1, 0]
    # ...but the same two rects of two different objects still exclude each other
    strangers = [
        LabelCandidate(_box(0.0, 13.0), 100.0, rank=1, tie="6.24 m2", owner="bed"),
        LabelCandidate(_box(0.0, 0.0), 100.0, rank=0, tie="Raised bed", owner="lawn"),
    ]
    assert place_labels(strangers) == [1]


def test_an_object_whose_name_has_no_room_shows_no_area_either() -> None:
    """The area hangs under the name; without the name it would hang under nothing."""
    candidates = [
        LabelCandidate(_box(0.0, 0.0), 400.0, tie="Terrace", owner="terrace"),
        LabelCandidate(_box(10.0, 4.0), 100.0, rank=0, tie="Raised bed", owner="bed"),
        LabelCandidate(_box(10.0, 40.0), 100.0, rank=1, tie="6.24 m2", owner="bed"),
    ]
    assert place_labels(candidates) == [0]


def test_the_answer_does_not_depend_on_the_order_given_or_on_a_shift_of_the_view() -> None:
    rng = random.Random(793)
    candidates = [
        LabelCandidate(
            _box(rng.uniform(0, 900), rng.uniform(0, 600), rng.uniform(30, 110)),
            rng.uniform(5, 300),
            tie=f"item {i}",
        )
        for i in range(120)
    ]
    shown = {candidates[i].tie for i in place_labels(candidates)}
    shuffled = candidates[:]
    rng.shuffle(shuffled)
    assert {shuffled[i].tie for i in place_labels(shuffled)} == shown
    # a pan moves every label by the same amount: nothing appears or disappears
    panned = [
        LabelCandidate(
            (c.rect[0] - 4321.5, c.rect[1] + 987.25, c.rect[2] - 4321.5, c.rect[3] + 987.25),
            c.owner_extent_px, c.pinned, c.rank, c.tie,
        )
        for c in candidates
    ]
    assert {panned[i].tie for i in place_labels(panned)} == shown


def test_no_two_shown_labels_overlap_in_a_crowd() -> None:
    rng = random.Random(7930)
    candidates = [
        LabelCandidate(
            _box(rng.uniform(0, 500), rng.uniform(0, 300), rng.uniform(30, 110)),
            rng.uniform(14, 300),
            tie=f"item {i}",
        )
        for i in range(400)
    ]
    shown = [candidates[i].rect for i in place_labels(candidates)]
    assert 5 < len(shown) < 400
    for i, first in enumerate(shown):
        for second in shown[i + 1:]:
            assert not _overlap(first, second, LABEL_GAP_PX - 1e-9)
    # and none was left out that had room: the layout is maximal
    for candidate in candidates:
        if candidate.rect in shown:
            continue
        assert any(_overlap(candidate.rect, other, LABEL_GAP_PX) for other in shown)


# A badge of constant size on its object (#836): a bed's succession tag.

@pytest.mark.parametrize(("badge", "owner", "room"), [
    ((77.0, 51.0), (429.0, 209.0), True),     # the raised-bed example, fitted to a window
    ((77.0, 51.0), (86.0, 42.0), False),      # zoomed out: taller than its bed
    ((77.0, 51.0), (60.0, 300.0), False),     # a narrow strip: wider than its bed
    ((77.0, 51.0), (160.0, 80.0), False),     # fits inside, but covers a third of it
    ((80.0, 50.0), (160.0, 100.0), True),     # exactly a quarter
    ((0.0, 0.0), (400.0, 200.0), False),      # nothing to draw
])
def test_a_badge_is_drawn_only_where_it_has_room_on_its_object(badge, owner, room) -> None:
    assert badge_has_room(*badge, *owner) is room


def test_the_room_a_badge_may_take_is_a_stated_share() -> None:
    assert BADGE_MAX_OWNER_SHARE == 0.25
    assert badge_has_room(100.0, 50.0, 200.0, 100.0, max_share=0.3)
    assert not badge_has_room(100.0, 61.0, 200.0, 100.0, max_share=0.3)
