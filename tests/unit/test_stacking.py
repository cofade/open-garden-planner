"""Unit tests for the Qt-free per-layer stacking core (issue #338).

No qtbot needed: `core/stacking.py` never imports PyQt6, and StackEntry is a
plain dataclass over UUIDs and (x, y, w, h) tuples.
"""

import uuid

import pytest

from open_garden_planner.core.stacking import (
    STACK_STEP,
    ArrangeMode,
    ArrangeOutcome,
    StackEntry,
    arrange,
    expand_block,
    normalize_order,
)


def uid(name: str) -> uuid.UUID:
    """Deterministic, readable UUID for a given name (stable across runs)."""
    return uuid.uuid5(uuid.NAMESPACE_OID, name)


def entry(
    name: str,
    parent: str | None = None,
    rect: tuple[float, float, float, float] = (0.0, 0.0, 10.0, 10.0),
) -> StackEntry:
    """Build a StackEntry by short name; `parent` is also a name."""
    return StackEntry(
        item_id=uid(name),
        parent_id=uid(parent) if parent is not None else None,
        rect=rect,
    )


def names(order: list[StackEntry]) -> list[str]:
    """Map a result order back to readable names for assertions.

    Relies on the fixed name->uuid5 mapping used by `entry()`/`uid()` in this
    module; only works for names actually used in the calling test.
    """
    reverse = {
        uid(n): n
        for n in [
            "lawn",
            "path",
            "bed",
            "A",
            "B",
            "C",
            "D",
            "plant1",
            "plant2",
            "ridge",
            "roof",
        ]
    }
    return [reverse[e.item_id] for e in order]


class TestNormalizeOrder:
    def test_idempotent(self) -> None:
        order = [entry("bed"), entry("plant1", parent="bed"), entry("lawn")]
        once = normalize_order(order)
        twice = normalize_order(once)
        assert once == twice

    def test_child_moved_above_parent(self) -> None:
        # Plant placed before its bed in the raw list -> normalize snaps it
        # to immediately above the bed.
        order = [entry("plant1", parent="bed"), entry("bed"), entry("lawn")]
        result = normalize_order(order)
        assert names(result) == ["bed", "plant1", "lawn"]

    def test_multiple_children_keep_relative_order(self) -> None:
        order = [
            entry("bed"),
            entry("lawn"),
            entry("plant2", parent="bed"),
            entry("plant1", parent="bed"),
        ]
        result = normalize_order(order)
        # Both plants move to sit right above bed, keeping their relative
        # (plant2 before plant1) order from the input.
        assert names(result) == ["bed", "plant2", "plant1", "lawn"]

    def test_parent_missing_from_list_is_left_alone(self) -> None:
        # parent_id references an id that simply isn't in `order` (e.g. bed
        # lives in a different layer) -> entry is treated as a normal
        # top-level item and stays where it is.
        order = [entry("plant1", parent="bed"), entry("lawn")]
        result = normalize_order(order)
        assert names(result) == ["plant1", "lawn"]

    def test_self_parent_is_ignored(self) -> None:
        # Defensive: an entry naming itself as parent must not vanish or loop.
        weird = StackEntry(item_id=uid("A"), parent_id=uid("A"), rect=(0, 0, 1, 1))
        order = [weird, entry("B")]
        result = normalize_order(order)
        assert [e.item_id for e in result] == [weird.item_id, uid("B")]


class TestExpandBlock:
    def test_selected_only_when_no_children(self) -> None:
        order = [entry("A"), entry("B"), entry("C")]
        block = expand_block(order, {uid("B")})
        assert block == {uid("B")}

    def test_selected_parent_pulls_in_children(self) -> None:
        order = [
            entry("lawn"),
            entry("bed"),
            entry("plant1", parent="bed"),
            entry("plant2", parent="bed"),
        ]
        block = expand_block(order, {uid("bed")})
        assert block == {uid("bed"), uid("plant1"), uid("plant2")}

    def test_selecting_only_a_child_does_not_pull_in_parent(self) -> None:
        order = [entry("bed"), entry("plant1", parent="bed")]
        block = expand_block(order, {uid("plant1")})
        assert block == {uid("plant1")}

    def test_ids_not_present_are_dropped(self) -> None:
        order = [entry("A"), entry("B")]
        block = expand_block(order, {uid("A"), uid("nowhere")})
        assert block == {uid("A")}


class TestArrangeModes:
    def test_bring_to_front(self) -> None:
        order = [entry("A"), entry("B"), entry("C")]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.BRING_TO_FRONT)
        assert outcome is ArrangeOutcome.CHANGED
        assert names(result) == ["B", "C", "A"]

    def test_send_to_back(self) -> None:
        order = [entry("A"), entry("B"), entry("C")]
        result, outcome = arrange(order, {uid("C")}, ArrangeMode.SEND_TO_BACK)
        assert outcome is ArrangeOutcome.CHANGED
        assert names(result) == ["C", "A", "B"]

    def test_bring_forward_steps_past_overlap(self) -> None:
        # All three overlap at the origin rect.
        order = [entry("A"), entry("B"), entry("C")]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.BRING_FORWARD)
        assert outcome is ArrangeOutcome.CHANGED
        assert names(result) == ["B", "A", "C"]

    def test_send_backward_steps_past_overlap(self) -> None:
        order = [entry("A"), entry("B"), entry("C")]
        result, outcome = arrange(order, {uid("C")}, ArrangeMode.SEND_BACKWARD)
        assert outcome is ArrangeOutcome.CHANGED
        assert names(result) == ["A", "C", "B"]


class TestOverlapStepping:
    def test_forward_skips_non_overlapping_items(self) -> None:
        # A overlaps only C's rect; B does not overlap A at all -> forward
        # jumps straight past B to swap with C.
        order = [
            entry("A", rect=(0, 0, 10, 10)),
            entry("B", rect=(100, 100, 10, 10)),
            entry("C", rect=(5, 5, 10, 10)),
        ]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.BRING_FORWARD)
        assert outcome is ArrangeOutcome.CHANGED
        assert names(result) == ["B", "C", "A"]

    def test_forward_no_overlap_above_is_noop(self) -> None:
        order = [
            entry("A", rect=(0, 0, 10, 10)),
            entry("B", rect=(100, 100, 10, 10)),
        ]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.BRING_FORWARD)
        assert result is None
        assert outcome is ArrangeOutcome.NO_OVERLAP_ABOVE

    def test_backward_no_overlap_below_is_noop(self) -> None:
        order = [
            entry("A", rect=(100, 100, 10, 10)),
            entry("B", rect=(0, 0, 10, 10)),
        ]
        result, outcome = arrange(order, {uid("B")}, ArrangeMode.SEND_BACKWARD)
        assert result is None
        assert outcome is ArrangeOutcome.NO_OVERLAP_BELOW

    def test_touching_edges_do_not_count_as_overlap(self) -> None:
        # B's left edge exactly meets A's right edge -> zero-area overlap,
        # documented as NOT intersecting.
        order = [
            entry("A", rect=(0, 0, 10, 10)),
            entry("B", rect=(10, 0, 10, 10)),
        ]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.BRING_FORWARD)
        assert result is None
        assert outcome is ArrangeOutcome.NO_OVERLAP_ABOVE

    def test_overlapping_rects_do_intersect(self) -> None:
        order = [
            entry("A", rect=(0, 0, 10, 10)),
            entry("B", rect=(9, 0, 10, 10)),
        ]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.BRING_FORWARD)
        assert outcome is ArrangeOutcome.CHANGED
        assert names(result) == ["B", "A"]


class TestEveryOutcomeValue:
    def test_nothing_selected(self) -> None:
        order = [entry("A"), entry("B")]
        result, outcome = arrange(order, set(), ArrangeMode.BRING_TO_FRONT)
        assert result is None
        assert outcome is ArrangeOutcome.NOTHING_SELECTED

    def test_nothing_selected_when_ids_foreign(self) -> None:
        order = [entry("A"), entry("B")]
        result, outcome = arrange(order, {uid("nowhere")}, ArrangeMode.SEND_TO_BACK)
        assert result is None
        assert outcome is ArrangeOutcome.NOTHING_SELECTED

    def test_already_at_front(self) -> None:
        order = [entry("A"), entry("B"), entry("C")]
        result, outcome = arrange(order, {uid("C")}, ArrangeMode.BRING_TO_FRONT)
        assert result is None
        assert outcome is ArrangeOutcome.ALREADY_AT_FRONT

    def test_already_at_back(self) -> None:
        order = [entry("A"), entry("B"), entry("C")]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.SEND_TO_BACK)
        assert result is None
        assert outcome is ArrangeOutcome.ALREADY_AT_BACK

    def test_no_overlap_above(self) -> None:
        order = [
            entry("A", rect=(0, 0, 10, 10)),
            entry("B", rect=(100, 100, 10, 10)),
        ]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.BRING_FORWARD)
        assert result is None
        assert outcome is ArrangeOutcome.NO_OVERLAP_ABOVE

    def test_no_overlap_below(self) -> None:
        order = [
            entry("A", rect=(100, 100, 10, 10)),
            entry("B", rect=(0, 0, 10, 10)),
        ]
        result, outcome = arrange(order, {uid("B")}, ArrangeMode.SEND_BACKWARD)
        assert result is None
        assert outcome is ArrangeOutcome.NO_OVERLAP_BELOW

    def test_changed(self) -> None:
        order = [entry("A"), entry("B")]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.BRING_TO_FRONT)
        assert outcome is ArrangeOutcome.CHANGED
        assert result is not None

    def test_bring_forward_already_at_front_when_topmost(self) -> None:
        order = [entry("A"), entry("B")]
        result, outcome = arrange(order, {uid("B")}, ArrangeMode.BRING_FORWARD)
        assert result is None
        assert outcome is ArrangeOutcome.ALREADY_AT_FRONT

    def test_send_backward_already_at_back_when_bottommost(self) -> None:
        order = [entry("A"), entry("B")]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.SEND_BACKWARD)
        assert result is None
        assert outcome is ArrangeOutcome.ALREADY_AT_BACK


class TestBlockContiguityAndRelativeOrder:
    def test_non_contiguous_selection_becomes_contiguous_at_front(self) -> None:
        order = [entry("A"), entry("B"), entry("C"), entry("D")]
        result, outcome = arrange(
            order, {uid("A"), uid("C")}, ArrangeMode.BRING_TO_FRONT
        )
        assert outcome is ArrangeOutcome.CHANGED
        # A and C keep their relative order (A before C) and land contiguous
        # at the top; B and D keep their relative order among themselves.
        assert names(result) == ["B", "D", "A", "C"]

    def test_non_contiguous_selection_becomes_contiguous_at_back(self) -> None:
        order = [entry("A"), entry("B"), entry("C"), entry("D")]
        result, outcome = arrange(
            order, {uid("B"), uid("D")}, ArrangeMode.SEND_TO_BACK
        )
        assert outcome is ArrangeOutcome.CHANGED
        assert names(result) == ["B", "D", "A", "C"]

    def test_bed_block_moves_together_preserving_children_order(self) -> None:
        order = [
            entry("bed"),
            entry("plant1", parent="bed"),
            entry("plant2", parent="bed"),
            entry("lawn"),
        ]
        result, outcome = arrange(order, {uid("bed")}, ArrangeMode.BRING_TO_FRONT)
        assert outcome is ArrangeOutcome.CHANGED
        assert names(result) == ["lawn", "bed", "plant1", "plant2"]


class TestPlantClamp:
    def test_lone_plant_send_to_back_stops_above_its_bed(self) -> None:
        order = [entry("bed"), entry("plant1", parent="bed"), entry("lawn")]
        result, outcome = arrange(
            order, {uid("plant1")}, ArrangeMode.SEND_TO_BACK
        )
        # Raw candidate would put plant1 below bed, but normalization snaps
        # it right back above the bed -> net result equals the input.
        assert result is None
        assert outcome is ArrangeOutcome.ALREADY_AT_BACK

    def test_lone_plant_send_backward_past_bed_collapses_to_noop(self) -> None:
        # plant1 overlaps its bed and there's nothing else between them ->
        # a raw "step backward" would place plant1 below bed, which
        # normalization immediately undoes.
        order = [
            entry("bed", rect=(0, 0, 10, 10)),
            entry("plant1", parent="bed", rect=(1, 1, 2, 2)),
            entry("lawn", rect=(50, 50, 5, 5)),
        ]
        result, outcome = arrange(
            order, {uid("plant1")}, ArrangeMode.SEND_BACKWARD
        )
        assert result is None
        assert outcome is ArrangeOutcome.ALREADY_AT_BACK

    def test_bed_block_bring_to_front_keeps_plant_clamped_above_bed(self) -> None:
        # bed+plant1 aren't at the front yet ("path" sits above them), so
        # Bring to Front is a real change -- and the clamp must still hold:
        # plant1 lands immediately above bed, never the other way round.
        order = [
            entry("lawn"),
            entry("bed"),
            entry("plant1", parent="bed"),
            entry("path"),
        ]
        result, outcome = arrange(order, {uid("bed")}, ArrangeMode.BRING_TO_FRONT)
        assert outcome is ArrangeOutcome.CHANGED
        assert names(result) == ["lawn", "path", "bed", "plant1"]
        result_names = names(result)
        assert result_names.index("bed") < result_names.index("plant1")


class TestNoOpCrossCheck:
    @pytest.mark.parametrize(
        "mode",
        [
            ArrangeMode.BRING_TO_FRONT,
            ArrangeMode.BRING_FORWARD,
            ArrangeMode.SEND_BACKWARD,
            ArrangeMode.SEND_TO_BACK,
        ],
    )
    def test_empty_selection_always_returns_none(self, mode: ArrangeMode) -> None:
        order = [entry("A"), entry("B")]
        result, outcome = arrange(order, set(), mode)
        assert result is None
        assert outcome is ArrangeOutcome.NOTHING_SELECTED

    def test_single_item_layer_front_is_noop(self) -> None:
        order = [entry("A")]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.BRING_TO_FRONT)
        assert result is None
        assert outcome is ArrangeOutcome.ALREADY_AT_FRONT

    def test_single_item_layer_back_is_noop(self) -> None:
        order = [entry("A")]
        result, outcome = arrange(order, {uid("A")}, ArrangeMode.SEND_TO_BACK)
        assert result is None
        assert outcome is ArrangeOutcome.ALREADY_AT_BACK


def test_stack_step_constant() -> None:
    assert STACK_STEP == 1024
