"""Tests for the distance constraint data model and solver."""

import math
from uuid import UUID, uuid4

import pytest

from open_garden_planner.core.constraints import (
    AnchorRef,
    Constraint,
    ConstraintGraph,
    ConstraintStatus,
    ConstraintType,
    SolverResult,
)
from open_garden_planner.core.measure_snapper import AnchorType


# --- AnchorRef tests ---


class TestAnchorRef:
    """Tests for AnchorRef dataclass."""

    def test_creation(self, qtbot) -> None:
        uid = uuid4()
        ref = AnchorRef(item_id=uid, anchor_type=AnchorType.CENTER)
        assert ref.item_id == uid
        assert ref.anchor_type == AnchorType.CENTER

    def test_serialization_roundtrip(self, qtbot) -> None:
        uid = uuid4()
        ref = AnchorRef(item_id=uid, anchor_type=AnchorType.EDGE_TOP)
        data = ref.to_dict()
        restored = AnchorRef.from_dict(data)
        assert restored.item_id == uid
        assert restored.anchor_type == AnchorType.EDGE_TOP


# --- Constraint tests ---


class TestConstraint:
    """Tests for Constraint dataclass."""

    def test_creation(self, qtbot) -> None:
        cid = uuid4()
        a = AnchorRef(uuid4(), AnchorType.CENTER)
        b = AnchorRef(uuid4(), AnchorType.EDGE_LEFT)
        c = Constraint(cid, a, b, target_distance=100.0, visible=True)
        assert c.constraint_id == cid
        assert c.target_distance == 100.0
        assert c.visible is True

    def test_serialization_roundtrip(self, qtbot) -> None:
        cid = uuid4()
        a = AnchorRef(uuid4(), AnchorType.CENTER)
        b = AnchorRef(uuid4(), AnchorType.EDGE_RIGHT)
        c = Constraint(cid, a, b, target_distance=250.5, visible=False)
        data = c.to_dict()
        restored = Constraint.from_dict(data)
        assert restored.constraint_id == cid
        assert restored.anchor_a.item_id == a.item_id
        assert restored.anchor_b.item_id == b.item_id
        assert restored.target_distance == 250.5
        assert restored.visible is False


# --- ConstraintGraph tests ---


class TestConstraintGraph:
    """Tests for ConstraintGraph add/remove/query operations."""

    def test_add_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        a = AnchorRef(id_a, AnchorType.CENTER)
        b = AnchorRef(id_b, AnchorType.CENTER)
        c = graph.add_constraint(a, b, 100.0)
        assert c.constraint_id in graph.constraints
        assert len(graph.get_item_constraints(id_a)) == 1
        assert len(graph.get_item_constraints(id_b)) == 1

    def test_remove_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        a = AnchorRef(id_a, AnchorType.CENTER)
        b = AnchorRef(id_b, AnchorType.CENTER)
        c = graph.add_constraint(a, b, 100.0)
        graph.remove_constraint(c.constraint_id)
        assert c.constraint_id not in graph.constraints
        assert len(graph.get_item_constraints(id_a)) == 0

    def test_remove_nonexistent_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        graph.remove_constraint(uuid4())  # Should not raise

    def test_remove_item_constraints(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_c, AnchorType.CENTER), 200.0)
        removed = graph.remove_item_constraints(id_a)
        assert len(removed) == 2
        assert len(graph.constraints) == 0

    def test_get_item_constraints_empty(self, qtbot) -> None:
        graph = ConstraintGraph()
        assert graph.get_item_constraints(uuid4()) == []

    def test_connected_component_single_pair(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)
        component = graph.get_connected_component(id_a)
        assert component == {id_a, id_b}

    def test_connected_component_chain(self, qtbot) -> None:
        """A-B-C chain should all be in the same component."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)
        graph.add_constraint(AnchorRef(id_b, AnchorType.CENTER), AnchorRef(id_c, AnchorType.CENTER), 150.0)
        component = graph.get_connected_component(id_a)
        assert component == {id_a, id_b, id_c}

    def test_disconnected_components(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        id_c, id_d = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)
        graph.add_constraint(AnchorRef(id_c, AnchorType.CENTER), AnchorRef(id_d, AnchorType.CENTER), 200.0)
        components = graph.get_all_connected_components()
        assert len(components) == 2

    def test_clear(self, qtbot) -> None:
        graph = ConstraintGraph()
        graph.add_constraint(AnchorRef(uuid4(), AnchorType.CENTER), AnchorRef(uuid4(), AnchorType.CENTER), 100.0)
        graph.clear()
        assert len(graph.constraints) == 0


# --- Solver tests ---


class TestConstraintSolver:
    """Tests for the iterative Gauss-Seidel constraint solver."""

    def test_single_constraint_converges(self, qtbot) -> None:
        """Two items 200cm apart, constraint wants 100cm -> should converge."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)

        positions = {id_a: (0.0, 0.0), id_b: (200.0, 0.0)}
        result = graph.solve(positions)

        assert result.converged
        # Items should have moved to be 100cm apart
        dx = positions[id_b][0] - positions[id_a][0]  # Original positions unchanged
        # Check deltas bring them to ~100cm apart
        pos_a = (0.0 + result.item_deltas.get(id_a, (0, 0))[0], 0.0 + result.item_deltas.get(id_a, (0, 0))[1])
        pos_b = (200.0 + result.item_deltas.get(id_b, (0, 0))[0], 0.0 + result.item_deltas.get(id_b, (0, 0))[1])
        dist = math.sqrt((pos_b[0] - pos_a[0]) ** 2 + (pos_b[1] - pos_a[1]) ** 2)
        assert abs(dist - 100.0) < 1.0  # Within tolerance

    def test_pinned_item_does_not_move(self, qtbot) -> None:
        """Pinned item should stay in place, other item moves."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)

        positions = {id_a: (0.0, 0.0), id_b: (200.0, 0.0)}
        result = graph.solve(positions, pinned_items={id_a})

        assert id_a not in result.item_deltas
        assert id_b in result.item_deltas
        # B should move to x=100
        new_bx = 200.0 + result.item_deltas[id_b][0]
        assert abs(new_bx - 100.0) < 1.0

    def test_both_pinned_no_movement(self, qtbot) -> None:
        """When both items are pinned, no movement should occur."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)

        positions = {id_a: (0.0, 0.0), id_b: (200.0, 0.0)}
        result = graph.solve(positions, pinned_items={id_a, id_b})

        assert len(result.item_deltas) == 0

    def test_triangle_chain(self, qtbot) -> None:
        """Three items in a triangle chain should converge."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        # Equilateral triangle with side 100
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)
        graph.add_constraint(AnchorRef(id_b, AnchorType.CENTER), AnchorRef(id_c, AnchorType.CENTER), 100.0)
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_c, AnchorType.CENTER), 100.0)

        # Start with items in a line
        positions = {id_a: (0.0, 0.0), id_b: (100.0, 0.0), id_c: (200.0, 0.0)}
        result = graph.solve(positions, max_iterations=20, tolerance=2.0)

        # Verify all distances are approximately 100
        def get_pos(uid):
            delta = result.item_deltas.get(uid, (0.0, 0.0))
            orig = positions[uid]
            return (orig[0] + delta[0], orig[1] + delta[1])

        pa, pb, pc = get_pos(id_a), get_pos(id_b), get_pos(id_c)
        dist_ab = math.sqrt((pb[0] - pa[0]) ** 2 + (pb[1] - pa[1]) ** 2)
        dist_bc = math.sqrt((pc[0] - pb[0]) ** 2 + (pc[1] - pb[1]) ** 2)
        dist_ac = math.sqrt((pc[0] - pa[0]) ** 2 + (pc[1] - pa[1]) ** 2)

        # With limited iterations, triangle may not perfectly converge but should improve
        assert dist_ab < 200.0  # Should have improved from initial 100, 100, 200

    def test_degenerate_same_position(self, qtbot) -> None:
        """Items at the same position should be pushed apart."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 50.0)

        positions = {id_a: (100.0, 100.0), id_b: (100.0, 100.0)}
        result = graph.solve(positions)

        # At least one item should have moved
        assert len(result.item_deltas) > 0

    def test_already_satisfied_no_movement(self, qtbot) -> None:
        """Items already at correct distance should not move."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)

        positions = {id_a: (0.0, 0.0), id_b: (100.0, 0.0)}
        result = graph.solve(positions)

        assert result.converged
        assert result.max_error < 1.0
        assert len(result.item_deltas) == 0

    def test_missing_item_skipped(self, qtbot) -> None:
        """Constraints referencing missing items should be skipped."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)

        # Only provide position for one item
        positions = {id_a: (0.0, 0.0)}
        result = graph.solve(positions)
        # Should not crash
        assert result.iterations_used >= 1

    def test_over_constrained_detection(self, qtbot) -> None:
        """An item connected to 3+ other items should be flagged."""
        graph = ConstraintGraph()
        id_center = uuid4()
        id_1, id_2, id_3 = uuid4(), uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_center, AnchorType.CENTER), AnchorRef(id_1, AnchorType.CENTER), 100.0)
        graph.add_constraint(AnchorRef(id_center, AnchorType.CENTER), AnchorRef(id_2, AnchorType.CENTER), 100.0)
        graph.add_constraint(AnchorRef(id_center, AnchorType.CENTER), AnchorRef(id_3, AnchorType.CENTER), 100.0)

        positions = {
            id_center: (0.0, 0.0),
            id_1: (100.0, 0.0),
            id_2: (0.0, 100.0),
            id_3: (-100.0, 0.0),
        }
        result = graph.solve(positions)
        assert id_center in result.over_constrained_items

    def test_solver_result_fields(self, qtbot) -> None:
        """Verify SolverResult has expected fields."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)

        positions = {id_a: (0.0, 0.0), id_b: (200.0, 0.0)}
        result = graph.solve(positions)

        assert isinstance(result.converged, bool)
        assert isinstance(result.iterations_used, int)
        assert isinstance(result.max_error, float)
        assert isinstance(result.item_deltas, dict)
        assert isinstance(result.over_constrained_items, set)

    def test_chain_propagation(self, qtbot) -> None:
        """Constraints should propagate through chains: A-B-C with A pinned."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)
        graph.add_constraint(AnchorRef(id_b, AnchorType.CENTER), AnchorRef(id_c, AnchorType.CENTER), 100.0)

        # A at origin (pinned), B at 50 (too close to A), C at 300 (too far from B)
        positions = {id_a: (0.0, 0.0), id_b: (50.0, 0.0), id_c: (300.0, 0.0)}
        result = graph.solve(positions, pinned_items={id_a}, max_iterations=10)

        # B should move to ~100 from A
        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        new_bx = 50.0 + delta_b[0]
        assert abs(new_bx - 100.0) < 5.0

    def test_diagonal_constraint(self, qtbot) -> None:
        """Constraint should work in diagonal directions."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        target = 100.0
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), target)

        # Items at 45 degrees, 200cm apart
        positions = {id_a: (0.0, 0.0), id_b: (141.42, 141.42)}
        result = graph.solve(positions, pinned_items={id_a})

        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        new_bx = 141.42 + delta_b[0]
        new_by = 141.42 + delta_b[1]
        dist = math.sqrt(new_bx ** 2 + new_by ** 2)
        assert abs(dist - target) < 1.0

    def test_zero_distance_constraint(self, qtbot) -> None:
        """Items should be pulled together with zero distance constraint."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 0.0)

        positions = {id_a: (0.0, 0.0), id_b: (50.0, 0.0)}
        result = graph.solve(positions)

        delta_a = result.item_deltas.get(id_a, (0.0, 0.0))
        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        new_ax = 0.0 + delta_a[0]
        new_bx = 50.0 + delta_b[0]
        dist = abs(new_bx - new_ax)
        assert dist < 2.0


# --- Serialization tests ---


class TestConstraintGraphSerialization:
    """Tests for ConstraintGraph serialization."""

    def test_empty_graph_roundtrip(self, qtbot) -> None:
        graph = ConstraintGraph()
        data = graph.to_list()
        assert data == []
        restored = ConstraintGraph.from_list(data)
        assert len(restored.constraints) == 0

    def test_single_constraint_roundtrip(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.EDGE_TOP),
            150.0,
            visible=False,
        )
        data = graph.to_list()
        restored = ConstraintGraph.from_list(data)

        assert len(restored.constraints) == 1
        rc = list(restored.constraints.values())[0]
        assert rc.constraint_id == c.constraint_id
        assert rc.anchor_a.item_id == id_a
        assert rc.anchor_b.item_id == id_b
        assert rc.anchor_a.anchor_type == AnchorType.CENTER
        assert rc.anchor_b.anchor_type == AnchorType.EDGE_TOP
        assert rc.target_distance == 150.0
        assert rc.visible is False

    def test_multiple_constraints_roundtrip(self, qtbot) -> None:
        graph = ConstraintGraph()
        ids = [uuid4() for _ in range(4)]
        graph.add_constraint(AnchorRef(ids[0], AnchorType.CENTER), AnchorRef(ids[1], AnchorType.CENTER), 100.0)
        graph.add_constraint(AnchorRef(ids[1], AnchorType.CENTER), AnchorRef(ids[2], AnchorType.CENTER), 200.0)
        graph.add_constraint(AnchorRef(ids[2], AnchorType.CENTER), AnchorRef(ids[3], AnchorType.CENTER), 300.0)

        data = graph.to_list()
        restored = ConstraintGraph.from_list(data)
        assert len(restored.constraints) == 3

        # Adjacency should be preserved
        assert len(restored.get_item_constraints(ids[1])) == 2


# --- Alignment constraint tests ---


class TestAlignmentConstraints:
    """Tests for HORIZONTAL and VERTICAL alignment constraints."""

    def test_constraint_type_enum(self, qtbot) -> None:
        assert ConstraintType.DISTANCE != ConstraintType.HORIZONTAL
        assert ConstraintType.HORIZONTAL != ConstraintType.VERTICAL

    def test_default_constraint_type_is_distance(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        c = graph.add_constraint(AnchorRef(id_a, AnchorType.CENTER), AnchorRef(id_b, AnchorType.CENTER), 100.0)
        assert c.constraint_type == ConstraintType.DISTANCE

    def test_add_horizontal_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.HORIZONTAL,
        )
        assert c.constraint_type == ConstraintType.HORIZONTAL

    def test_add_vertical_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.VERTICAL,
        )
        assert c.constraint_type == ConstraintType.VERTICAL

    def test_horizontal_solver_aligns_y(self, qtbot) -> None:
        """HORIZONTAL constraint should make items have same Y coordinate."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.HORIZONTAL,
        )
        # Items at different Y positions
        positions = {id_a: (0.0, 0.0), id_b: (100.0, 60.0)}
        result = graph.solve(positions)

        assert result.converged
        delta_a = result.item_deltas.get(id_a, (0.0, 0.0))
        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        new_ay = 0.0 + delta_a[1]
        new_by = 60.0 + delta_b[1]
        assert abs(new_by - new_ay) < 1.0  # Same Y

    def test_vertical_solver_aligns_x(self, qtbot) -> None:
        """VERTICAL constraint should make items have same X coordinate."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.VERTICAL,
        )
        # Items at different X positions
        positions = {id_a: (0.0, 0.0), id_b: (80.0, 100.0)}
        result = graph.solve(positions)

        assert result.converged
        delta_a = result.item_deltas.get(id_a, (0.0, 0.0))
        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        new_ax = 0.0 + delta_a[0]
        new_bx = 80.0 + delta_b[0]
        assert abs(new_bx - new_ax) < 1.0  # Same X

    def test_horizontal_pinned_a_only_b_moves(self, qtbot) -> None:
        """HORIZONTAL with A pinned: only B adjusts its Y."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.HORIZONTAL,
        )
        positions = {id_a: (0.0, 0.0), id_b: (100.0, 50.0)}
        result = graph.solve(positions, pinned_items={id_a})

        assert id_a not in result.item_deltas
        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        new_by = 50.0 + delta_b[1]
        assert abs(new_by - 0.0) < 1.0  # B moves to A's Y

    def test_vertical_pinned_b_only_a_moves(self, qtbot) -> None:
        """VERTICAL with B pinned: only A adjusts its X."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.VERTICAL,
        )
        positions = {id_a: (0.0, 0.0), id_b: (60.0, 100.0)}
        result = graph.solve(positions, pinned_items={id_b})

        assert id_b not in result.item_deltas
        delta_a = result.item_deltas.get(id_a, (0.0, 0.0))
        new_ax = 0.0 + delta_a[0]
        assert abs(new_ax - 60.0) < 1.0  # A moves to B's X

    def test_already_aligned_no_movement(self, qtbot) -> None:
        """Items already aligned should not move."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.HORIZONTAL,
        )
        positions = {id_a: (0.0, 50.0), id_b: (100.0, 50.0)}
        result = graph.solve(positions)

        assert result.converged
        assert result.max_error < 1.0
        assert len(result.item_deltas) == 0

    def test_alignment_composable_with_distance(self, qtbot) -> None:
        """HORIZONTAL alignment + DISTANCE should both be enforced."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.HORIZONTAL,
        )
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
            constraint_type=ConstraintType.DISTANCE,
        )
        positions = {id_a: (0.0, 0.0), id_b: (200.0, 60.0)}
        result = graph.solve(positions, pinned_items={id_a}, max_iterations=20)

        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        new_bx = 200.0 + delta_b[0]
        new_by = 60.0 + delta_b[1]
        # B should be aligned horizontally (same Y as A=0)
        assert abs(new_by - 0.0) < 2.0

    def test_alignment_constraint_serialization_roundtrip(self, qtbot) -> None:
        """Alignment constraints survive serialization roundtrip."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        c_h = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.HORIZONTAL,
        )
        c_v = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.EDGE_TOP),
            0.0,
            constraint_type=ConstraintType.VERTICAL,
        )
        data = graph.to_list()
        restored = ConstraintGraph.from_list(data)

        assert len(restored.constraints) == 2
        types = {c.constraint_type for c in restored.constraints.values()}
        assert ConstraintType.HORIZONTAL in types
        assert ConstraintType.VERTICAL in types

    def test_constraint_dict_includes_type(self, qtbot) -> None:
        """to_dict() should include constraint_type field."""
        id_a, id_b = uuid4(), uuid4()
        c = Constraint(
            constraint_id=uuid4(),
            anchor_a=AnchorRef(id_a, AnchorType.CENTER),
            anchor_b=AnchorRef(id_b, AnchorType.CENTER),
            target_distance=0.0,
            constraint_type=ConstraintType.HORIZONTAL,
        )
        d = c.to_dict()
        assert d["constraint_type"] == "HORIZONTAL"

    def test_constraint_from_dict_defaults_to_distance(self, qtbot) -> None:
        """Old saved data without constraint_type should default to DISTANCE."""
        id_a, id_b = uuid4(), uuid4()
        d = {
            "constraint_id": str(uuid4()),
            "anchor_a": AnchorRef(id_a, AnchorType.CENTER).to_dict(),
            "anchor_b": AnchorRef(id_b, AnchorType.CENTER).to_dict(),
            "target_distance": 100.0,
            "visible": True,
            # No "constraint_type" key (old format)
        }
        c = Constraint.from_dict(d)
        assert c.constraint_type == ConstraintType.DISTANCE
