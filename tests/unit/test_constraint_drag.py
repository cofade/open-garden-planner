"""Tests for US-7.5: Constraint solver drag integration.

Tests the anchor-aware constraint solver and constraint propagation
during drag operations.
"""

import math
from uuid import uuid4

import pytest

from open_garden_planner.core.constraints import (
    AnchorRef,
    ConstraintGraph,
)
from open_garden_planner.core.measure_snapper import AnchorType


# --- Anchored solver tests ---


class TestSolveAnchored:
    """Tests for ConstraintGraph.solve_anchored() method."""

    def test_center_to_center_same_as_solve(self, qtbot) -> None:
        """With zero anchor offsets, solve_anchored should behave like solve."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )

        positions = {id_a: (0.0, 0.0), id_b: (200.0, 0.0)}
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
        }
        result = graph.solve_anchored(
            positions, anchor_offsets, pinned_items={id_a},
        )

        assert result.converged
        assert id_b in result.item_deltas
        # B should move from 200 to 100
        new_bx = 200.0 + result.item_deltas[id_b][0]
        assert abs(new_bx - 100.0) < 1.0

    def test_anchor_offset_changes_distance(self, qtbot) -> None:
        """Anchor offsets should affect the distance computation."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        # Constraint between right edge of A and left edge of B
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.EDGE_RIGHT, 0),
            AnchorRef(id_b, AnchorType.EDGE_LEFT, 0),
            50.0,  # Want 50cm between right edge of A and left edge of B
        )

        # Items are at 0 and 200; A is 100cm wide, B is 100cm wide
        # So right edge of A is at 50, left edge of B is at 150
        # Current distance = 100, want 50
        positions = {id_a: (0.0, 0.0), id_b: (200.0, 0.0)}
        anchor_offsets = {
            (id_a, AnchorType.EDGE_RIGHT, 0): (50.0, 0.0),  # Right edge is 50cm from center
            (id_b, AnchorType.EDGE_LEFT, 0): (-50.0, 0.0),  # Left edge is -50cm from center
        }
        result = graph.solve_anchored(
            positions, anchor_offsets, pinned_items={id_a},
        )

        # B should move so that its left edge is 50cm from A's right edge
        # A right edge at 50, so B left edge should be at 100
        # B left edge = B center - 50 = 100, so B center = 150
        new_bx = 200.0 + result.item_deltas[id_b][0]
        assert abs(new_bx - 150.0) < 2.0

    def test_pinned_item_stays_fixed(self, qtbot) -> None:
        """Pinned items should not appear in deltas."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )

        positions = {id_a: (0.0, 0.0), id_b: (200.0, 0.0)}
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
        }
        result = graph.solve_anchored(
            positions, anchor_offsets, pinned_items={id_a},
        )

        assert id_a not in result.item_deltas

    def test_chain_propagation_anchored(self, qtbot) -> None:
        """Chain A->B->C with A pinned should propagate to B and C."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )
        graph.add_constraint(
            AnchorRef(id_b, AnchorType.CENTER),
            AnchorRef(id_c, AnchorType.CENTER),
            100.0,
        )

        # A at origin (pinned), B too close, C too far
        positions = {id_a: (0.0, 0.0), id_b: (50.0, 0.0), id_c: (300.0, 0.0)}
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_c, AnchorType.CENTER, 0): (0.0, 0.0),
        }
        result = graph.solve_anchored(
            positions, anchor_offsets, pinned_items={id_a},
            max_iterations=15,
        )

        # B should move to ~100 from A
        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        new_bx = 50.0 + delta_b[0]
        assert abs(new_bx - 100.0) < 5.0

        # C should be ~100 from B's new position
        delta_c = result.item_deltas.get(id_c, (0.0, 0.0))
        new_cx = 300.0 + delta_c[0]
        assert abs(new_cx - new_bx - 100.0) < 10.0

    def test_already_satisfied_no_movement(self, qtbot) -> None:
        """Satisfied constraints should produce no deltas."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )

        positions = {id_a: (0.0, 0.0), id_b: (100.0, 0.0)}
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
        }
        result = graph.solve_anchored(positions, anchor_offsets)

        assert result.converged
        assert len(result.item_deltas) == 0

    def test_missing_anchor_offset_defaults_to_zero(self, qtbot) -> None:
        """Missing anchor offset should default to (0, 0)."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )

        positions = {id_a: (0.0, 0.0), id_b: (200.0, 0.0)}
        # Pass empty anchor_offsets — should default to zero
        result = graph.solve_anchored(
            positions, {}, pinned_items={id_a},
        )

        assert id_b in result.item_deltas
        new_bx = 200.0 + result.item_deltas[id_b][0]
        assert abs(new_bx - 100.0) < 1.0

    def test_diagonal_with_offsets(self, qtbot) -> None:
        """Anchored solver should work in diagonal directions with offsets."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CORNER, 0),
            AnchorRef(id_b, AnchorType.CORNER, 0),
            100.0,
        )

        positions = {id_a: (0.0, 0.0), id_b: (200.0, 200.0)}
        # Corners at item positions (no offset)
        anchor_offsets = {
            (id_a, AnchorType.CORNER, 0): (0.0, 0.0),
            (id_b, AnchorType.CORNER, 0): (0.0, 0.0),
        }
        result = graph.solve_anchored(
            positions, anchor_offsets, pinned_items={id_a},
        )

        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        new_bx = 200.0 + delta_b[0]
        new_by = 200.0 + delta_b[1]
        dist = math.sqrt(new_bx ** 2 + new_by ** 2)
        assert abs(dist - 100.0) < 1.0

    def test_both_pinned_no_movement(self, qtbot) -> None:
        """When both items are pinned, no movement should occur."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )

        positions = {id_a: (0.0, 0.0), id_b: (200.0, 0.0)}
        anchor_offsets = {}
        result = graph.solve_anchored(
            positions, anchor_offsets, pinned_items={id_a, id_b},
        )

        assert len(result.item_deltas) == 0

    def test_over_constrained_detection(self, qtbot) -> None:
        """Over-constrained items should be detected."""
        graph = ConstraintGraph()
        id_center = uuid4()
        id_1, id_2, id_3 = uuid4(), uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_center, AnchorType.CENTER),
            AnchorRef(id_1, AnchorType.CENTER),
            100.0,
        )
        graph.add_constraint(
            AnchorRef(id_center, AnchorType.CENTER),
            AnchorRef(id_2, AnchorType.CENTER),
            100.0,
        )
        graph.add_constraint(
            AnchorRef(id_center, AnchorType.CENTER),
            AnchorRef(id_3, AnchorType.CENTER),
            100.0,
        )

        positions = {
            id_center: (0.0, 0.0),
            id_1: (100.0, 0.0),
            id_2: (0.0, 100.0),
            id_3: (-100.0, 0.0),
        }
        result = graph.solve_anchored(positions, {})
        assert id_center in result.over_constrained_items


# --- Delete cascade tests ---


class TestDeleteCascade:
    """Tests for constraint removal when items are deleted."""

    def test_remove_item_removes_constraints(self, qtbot) -> None:
        """Removing an item should remove all its constraints."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        c1 = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )
        c2 = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_c, AnchorType.CENTER),
            200.0,
        )

        removed = graph.remove_item_constraints(id_a)
        assert len(removed) == 2
        assert c1.constraint_id in removed
        assert c2.constraint_id in removed
        assert len(graph.constraints) == 0

    def test_remove_middle_item_preserves_other_constraints(self, qtbot) -> None:
        """Removing a middle item in A-B-C should only remove B's constraints."""
        graph = ConstraintGraph()
        id_a, id_b, id_c, id_d = uuid4(), uuid4(), uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )
        graph.add_constraint(
            AnchorRef(id_b, AnchorType.CENTER),
            AnchorRef(id_c, AnchorType.CENTER),
            100.0,
        )
        c_unrelated = graph.add_constraint(
            AnchorRef(id_c, AnchorType.CENTER),
            AnchorRef(id_d, AnchorType.CENTER),
            100.0,
        )

        graph.remove_item_constraints(id_b)
        # Only the C-D constraint should remain
        assert len(graph.constraints) == 1
        assert c_unrelated.constraint_id in graph.constraints


# --- Serialization with constraints roundtrip ---


class TestConstraintSaveLoad:
    """Tests for constraints in project save/load."""

    def test_constraint_graph_roundtrip(self, qtbot) -> None:
        """Constraint graph should survive serialization roundtrip."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.EDGE_TOP),
            123.45,
            visible=True,
        )

        data = graph.to_list()
        restored = ConstraintGraph.from_list(data)

        assert len(restored.constraints) == 1
        rc = list(restored.constraints.values())[0]
        assert rc.constraint_id == c.constraint_id
        assert rc.target_distance == 123.45
        assert rc.anchor_a.anchor_type == AnchorType.CENTER
        assert rc.anchor_b.anchor_type == AnchorType.EDGE_TOP

    def test_anchor_index_preserved(self, qtbot) -> None:
        """Anchor index should be preserved through serialization."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CORNER, 3),
            AnchorRef(id_b, AnchorType.ENDPOINT, 2),
            50.0,
        )

        data = graph.to_list()
        restored = ConstraintGraph.from_list(data)

        rc = list(restored.constraints.values())[0]
        assert rc.anchor_a.anchor_index == 3
        assert rc.anchor_b.anchor_index == 2
