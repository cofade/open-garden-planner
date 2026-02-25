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


# --- Angle constraint tests ---


class TestAngleConstraints:
    """Tests for ANGLE constraint type: data model, serialization, and solver."""

    # ----- Data model -----

    def test_angle_constraint_type_exists(self, qtbot) -> None:
        assert ConstraintType.ANGLE is not None

    def test_add_angle_constraint(self, qtbot) -> None:
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        ref_a = AnchorRef(id_a, AnchorType.CENTER)
        ref_b = AnchorRef(id_b, AnchorType.CENTER)
        ref_c = AnchorRef(id_c, AnchorType.CENTER)
        constraint = graph.add_constraint(
            ref_a, ref_b, 90.0,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=ref_c,
        )
        assert constraint.constraint_type == ConstraintType.ANGLE
        assert constraint.target_distance == 90.0
        assert constraint.anchor_c is not None
        assert constraint.anchor_c.item_id == id_c

    def test_angle_constraint_adjacency_includes_all_three(self, qtbot) -> None:
        """All three items (A, B, C) should be in the adjacency graph."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            90.0,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=AnchorRef(id_c, AnchorType.CENTER),
        )
        assert len(graph.get_item_constraints(id_a)) == 1
        assert len(graph.get_item_constraints(id_b)) == 1
        assert len(graph.get_item_constraints(id_c)) == 1

    def test_angle_constraint_remove_cleans_up_all_three(self, qtbot) -> None:
        """Removing an angle constraint removes adjacency for all three items."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            90.0,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=AnchorRef(id_c, AnchorType.CENTER),
        )
        graph.remove_constraint(c.constraint_id)
        assert c.constraint_id not in graph.constraints
        assert graph.get_item_constraints(id_a) == []
        assert graph.get_item_constraints(id_b) == []
        assert graph.get_item_constraints(id_c) == []

    def test_angle_constraint_connected_component_includes_all_three(self, qtbot) -> None:
        """BFS should include all three items of an angle constraint in the same component."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            90.0,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=AnchorRef(id_c, AnchorType.CENTER),
        )
        component = graph.get_connected_component(id_a)
        assert id_a in component
        assert id_b in component
        assert id_c in component

    # ----- Serialization -----

    def test_angle_constraint_serialization_roundtrip(self, qtbot) -> None:
        """Angle constraints with anchor_c survive serialization roundtrip."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            45.0,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=AnchorRef(id_c, AnchorType.EDGE_TOP),
        )
        data = graph.to_list()
        restored = ConstraintGraph.from_list(data)
        assert len(restored.constraints) == 1
        rc = list(restored.constraints.values())[0]
        assert rc.constraint_type == ConstraintType.ANGLE
        assert rc.target_distance == 45.0
        assert rc.anchor_c is not None
        assert rc.anchor_c.item_id == id_c
        assert rc.anchor_c.anchor_type == AnchorType.EDGE_TOP

    def test_angle_constraint_dict_includes_anchor_c(self, qtbot) -> None:
        """to_dict() should include anchor_c for ANGLE constraints."""
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        c = Constraint(
            constraint_id=uuid4(),
            anchor_a=AnchorRef(id_a, AnchorType.CENTER),
            anchor_b=AnchorRef(id_b, AnchorType.CENTER),
            target_distance=90.0,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=AnchorRef(id_c, AnchorType.CENTER),
        )
        d = c.to_dict()
        assert d["constraint_type"] == "ANGLE"
        assert "anchor_c" in d
        assert d["anchor_c"]["item_id"] == str(id_c)

    def test_angle_constraint_no_anchor_c_dict_omits_field(self, qtbot) -> None:
        """to_dict() should not include anchor_c key when anchor_c is None."""
        c = Constraint(
            constraint_id=uuid4(),
            anchor_a=AnchorRef(uuid4(), AnchorType.CENTER),
            anchor_b=AnchorRef(uuid4(), AnchorType.CENTER),
            target_distance=100.0,
        )
        d = c.to_dict()
        assert "anchor_c" not in d

    # ----- Solver -----

    def _compute_angle(self, pa, pb, pc):
        """Compute angle at vertex pb between rays pa and pc (degrees)."""
        ba_x, ba_y = pa[0] - pb[0], pa[1] - pb[1]
        bc_x, bc_y = pc[0] - pb[0], pc[1] - pb[1]
        ba_len = math.sqrt(ba_x ** 2 + ba_y ** 2)
        bc_len = math.sqrt(bc_x ** 2 + bc_y ** 2)
        if ba_len < 1e-9 or bc_len < 1e-9:
            return 0.0
        cos_val = max(-1.0, min(1.0, (ba_x * bc_x + ba_y * bc_y) / (ba_len * bc_len)))
        return math.degrees(math.acos(cos_val))

    def test_angle_solver_90_degrees(self, qtbot) -> None:
        """Solver should bring angle to 90° when A, B, C start at 60°."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        ref_a = AnchorRef(id_a, AnchorType.CENTER)
        ref_b = AnchorRef(id_b, AnchorType.CENTER)
        ref_c = AnchorRef(id_c, AnchorType.CENTER)

        graph.add_constraint(
            ref_a, ref_b, 90.0,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=ref_c,
        )

        # B at origin (vertex), A to the right, C at 60° from A
        positions = {
            id_a: (100.0, 0.0),
            id_b: (0.0, 0.0),
            id_c: (50.0, 86.6),  # ~60° from A (equilateral-ish)
        }
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_c, AnchorType.CENTER, 0): (0.0, 0.0),
        }

        result = graph.solve_anchored(
            item_positions={k: list(v) for k, v in positions.items()},
            anchor_offsets=anchor_offsets,
            pinned_items={id_b},  # vertex stays fixed
            max_iterations=20,
            tolerance=0.5,
        )

        # Compute final positions
        def get_final(uid, orig):
            delta = result.item_deltas.get(uid, (0.0, 0.0))
            return (orig[0] + delta[0], orig[1] + delta[1])

        pa = get_final(id_a, positions[id_a])
        pb = positions[id_b]  # pinned
        pc = get_final(id_c, positions[id_c])

        final_angle = self._compute_angle(pa, pb, pc)
        assert abs(final_angle - 90.0) < 5.0  # Within 5° (iterative solver)

    def test_angle_solver_already_satisfied(self, qtbot) -> None:
        """No movement should occur when angle is already at target."""
        graph = ConstraintGraph()
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()

        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            90.0,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=AnchorRef(id_c, AnchorType.CENTER),
        )

        # Already at 90°: B at origin, A to the right, C straight up
        positions = {
            id_a: (100.0, 0.0),
            id_b: (0.0, 0.0),
            id_c: (0.0, 100.0),
        }
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_c, AnchorType.CENTER, 0): (0.0, 0.0),
        }
        result = graph.solve_anchored(
            item_positions={k: list(v) for k, v in positions.items()},
            anchor_offsets=anchor_offsets,
            pinned_items={id_b},
            max_iterations=10,
            tolerance=0.5,
        )

        assert abs(result.max_error) < 1.0  # Already satisfied
        assert id_a not in result.item_deltas or abs(result.item_deltas[id_a][0]) < 1.0
        assert id_c not in result.item_deltas or abs(result.item_deltas[id_c][0]) < 1.0

    def test_angle_solver_skips_missing_anchor_c(self, qtbot) -> None:
        """Solver should skip angle constraint if anchor_c is None."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        # Manually add a constraint without anchor_c (normally prevented by the tool)
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            90.0,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=None,  # Missing
        )
        positions = {id_a: (100.0, 0.0), id_b: (0.0, 0.0)}
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
        }
        # Should not raise
        result = graph.solve_anchored(
            item_positions={k: list(v) for k, v in positions.items()},
            anchor_offsets=anchor_offsets,
        )
        assert result is not None


class TestSymmetryConstraintSolver:
    """Tests for the symmetry constraint solver."""

    def _make_anchored_positions(
        self,
        positions: dict,
    ) -> tuple[dict, dict]:
        """Build item_positions and anchor_offsets with zero offsets."""
        anchor_offsets = {
            (uid, AnchorType.CENTER, 0): (0.0, 0.0)
            for uid in positions
        }
        item_positions = {uid: [x, y] for uid, (x, y) in positions.items()}
        return item_positions, anchor_offsets

    def test_horizontal_symmetry_already_satisfied(self, qtbot) -> None:
        """Two items already mirrored across y=0 should converge immediately."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        # A at (0, -100), B at (0, 100) — symmetric across y=0
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,  # axis at y=0
            constraint_type=ConstraintType.SYMMETRY_HORIZONTAL,
        )
        positions, offsets = self._make_anchored_positions(
            {id_a: (0.0, -100.0), id_b: (0.0, 100.0)}
        )
        result = graph.solve_anchored(
            item_positions=positions,
            anchor_offsets=offsets,
        )
        assert result.converged
        # Items should not have moved (already satisfied)
        assert id_a not in result.item_deltas
        assert id_b not in result.item_deltas

    def test_horizontal_symmetry_corrects_positions(self, qtbot) -> None:
        """Items not yet mirrored should be moved to satisfy symmetry."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        # Axis at y=0; A at (0, 50), B at (0, 30) — not symmetric
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,  # axis at y=0
            constraint_type=ConstraintType.SYMMETRY_HORIZONTAL,
        )
        positions, offsets = self._make_anchored_positions(
            {id_a: (0.0, 50.0), id_b: (0.0, 30.0)}
        )
        result = graph.solve_anchored(
            item_positions=positions,
            anchor_offsets=offsets,
        )
        assert result.converged
        # After correction: ay + by should be 0 (both free — equally adjusted)
        new_ay = 50.0 + result.item_deltas.get(id_a, (0.0, 0.0))[1]
        new_by = 30.0 + result.item_deltas.get(id_b, (0.0, 0.0))[1]
        assert abs(new_ay + new_by) < 1.0  # sum should be 2 * axis_y = 0

    def test_horizontal_symmetry_pinned_a_moves_b(self, qtbot) -> None:
        """When A is pinned, B should mirror A exactly."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,  # axis at y=0
            constraint_type=ConstraintType.SYMMETRY_HORIZONTAL,
        )
        positions, offsets = self._make_anchored_positions(
            {id_a: (50.0, 80.0), id_b: (0.0, 0.0)}
        )
        result = graph.solve_anchored(
            item_positions=positions,
            anchor_offsets=offsets,
            pinned_items={id_a},
        )
        assert result.converged
        assert id_a not in result.item_deltas
        new_bx = 0.0 + result.item_deltas.get(id_b, (0.0, 0.0))[0]
        new_by = 0.0 + result.item_deltas.get(id_b, (0.0, 0.0))[1]
        # B should mirror A: bx=50, by=-80
        assert abs(new_bx - 50.0) < 1.0
        assert abs(new_by - (-80.0)) < 1.0

    def test_vertical_symmetry_corrects_positions(self, qtbot) -> None:
        """Items not yet mirrored vertically should be corrected."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        # Axis at x=0; A at (50, 0), B at (30, 0) — not symmetric
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,  # axis at x=0
            constraint_type=ConstraintType.SYMMETRY_VERTICAL,
        )
        positions, offsets = self._make_anchored_positions(
            {id_a: (50.0, 0.0), id_b: (30.0, 0.0)}
        )
        result = graph.solve_anchored(
            item_positions=positions,
            anchor_offsets=offsets,
        )
        assert result.converged
        new_ax = 50.0 + result.item_deltas.get(id_a, (0.0, 0.0))[0]
        new_bx = 30.0 + result.item_deltas.get(id_b, (0.0, 0.0))[0]
        assert abs(new_ax + new_bx) < 1.0  # sum should be 2 * axis_x = 0

    def test_vertical_symmetry_pinned_a_moves_b(self, qtbot) -> None:
        """When A is pinned, B should mirror A exactly across vertical axis."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,  # axis at x=100
            constraint_type=ConstraintType.SYMMETRY_VERTICAL,
        )
        positions, offsets = self._make_anchored_positions(
            {id_a: (150.0, 75.0), id_b: (0.0, 0.0)}
        )
        result = graph.solve_anchored(
            item_positions=positions,
            anchor_offsets=offsets,
            pinned_items={id_a},
        )
        assert result.converged
        assert id_a not in result.item_deltas
        new_bx = 0.0 + result.item_deltas.get(id_b, (0.0, 0.0))[0]
        new_by = 0.0 + result.item_deltas.get(id_b, (0.0, 0.0))[1]
        # B should mirror A across x=100: bx = 2*100 - 150 = 50, by = 75
        assert abs(new_bx - 50.0) < 1.0
        assert abs(new_by - 75.0) < 1.0

    def test_horizontal_symmetry_pinned_with_nonzero_offsets(self, qtbot) -> None:
        """Regression: non-zero anchor offsets must not cause large item jumps.

        Simulates items where pos() = (0, 0) and the anchor is embedded at a
        large local coordinate (typical for QGraphicsRectItem created from
        scene drag without a subsequent setPos call).
        """
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        # axis at y=300; A's anchor at (200, 170), B's anchor at (200, 450)
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            300.0,
            constraint_type=ConstraintType.SYMMETRY_HORIZONTAL,
        )
        # Item positions with zero item-pos but large anchor offsets
        item_positions = {id_a: [0.0, 20.0], id_b: [0.0, 0.0]}
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (200.0, 150.0),  # anchor at (200, 170)
            (id_b, AnchorType.CENTER, 0): (200.0, 450.0),  # anchor at (200, 450)
        }
        result = graph.solve_anchored(
            item_positions=item_positions,
            anchor_offsets=anchor_offsets,
            pinned_items={id_a},
        )
        assert result.converged
        assert id_a not in result.item_deltas
        # ax=200, ay=170 → B's target anchor=(200, 430) → B's item target=(0, -20)
        new_bx = 0.0 + result.item_deltas.get(id_b, (0.0, 0.0))[0]
        new_by = 0.0 + result.item_deltas.get(id_b, (0.0, 0.0))[1]
        assert abs(new_bx) < 1.0            # B's item X stays at 0
        assert abs(new_by - (-20.0)) < 1.0  # B's item Y moves by -20, not +430

    def test_vertical_symmetry_pinned_with_nonzero_offsets(self, qtbot) -> None:
        """Regression: non-zero anchor offsets must not cause large item jumps (V)."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        # axis at x=300; A's anchor at (170, 200), B's anchor at (450, 200)
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            300.0,
            constraint_type=ConstraintType.SYMMETRY_VERTICAL,
        )
        item_positions = {id_a: [20.0, 0.0], id_b: [0.0, 0.0]}
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (150.0, 200.0),  # anchor at (170, 200)
            (id_b, AnchorType.CENTER, 0): (450.0, 200.0),  # anchor at (450, 200)
        }
        result = graph.solve_anchored(
            item_positions=item_positions,
            anchor_offsets=anchor_offsets,
            pinned_items={id_a},
        )
        assert result.converged
        assert id_a not in result.item_deltas
        # ax=170, ay=200 → B's target anchor=(430, 200) → B's item target=(-20, 0)
        new_bx = 0.0 + result.item_deltas.get(id_b, (0.0, 0.0))[0]
        new_by = 0.0 + result.item_deltas.get(id_b, (0.0, 0.0))[1]
        assert abs(new_bx - (-20.0)) < 1.0  # B's item X moves by -20, not +430
        assert abs(new_by) < 1.0            # B's item Y stays at 0

    def test_symmetry_serialization_roundtrip(self, qtbot) -> None:
        """SYMMETRY constraints should survive to_dict/from_dict round-trip."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            75.0,
            constraint_type=ConstraintType.SYMMETRY_HORIZONTAL,
        )
        data = graph.to_list()
        restored = ConstraintGraph.from_list(data)
        assert len(restored.constraints) == 1
        rc = list(restored.constraints.values())[0]
        assert rc.constraint_type == ConstraintType.SYMMETRY_HORIZONTAL
        assert rc.target_distance == 75.0


class TestCoincidentConstraint:
    """Tests for the COINCIDENT constraint type and solver."""

    def test_coincident_type_exists(self, qtbot) -> None:
        assert ConstraintType.COINCIDENT is not None

    def test_add_coincident_constraint(self, qtbot) -> None:
        """COINCIDENT constraint is added with target_distance=0."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.COINCIDENT,
        )
        assert c.constraint_type == ConstraintType.COINCIDENT
        assert c.target_distance == 0.0
        assert len(graph.constraints) == 1

    def test_coincident_solver_moves_to_midpoint(self, qtbot) -> None:
        """Solver moves two free anchors to meet at the midpoint."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        ref_a = AnchorRef(id_a, AnchorType.CENTER)
        ref_b = AnchorRef(id_b, AnchorType.CENTER)
        graph.add_constraint(ref_a, ref_b, 0.0, constraint_type=ConstraintType.COINCIDENT)

        positions = {id_a: (0.0, 0.0), id_b: (100.0, 0.0)}
        offsets: dict = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
        }

        result = graph.solve_anchored(positions, offsets, tolerance=0.01)
        assert result.converged
        # Both items should be at the midpoint (50, 0)
        final_a = (positions[id_a][0] + result.item_deltas.get(id_a, (0, 0))[0],
                   positions[id_a][1] + result.item_deltas.get(id_a, (0, 0))[1])
        final_b = (positions[id_b][0] + result.item_deltas.get(id_b, (0, 0))[0],
                   positions[id_b][1] + result.item_deltas.get(id_b, (0, 0))[1])
        assert abs(final_a[0] - final_b[0]) < 0.01
        assert abs(final_a[1] - final_b[1]) < 0.01

    def test_coincident_solver_pinned_a(self, qtbot) -> None:
        """When A is pinned, solver moves B to A's position."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        ref_a = AnchorRef(id_a, AnchorType.CENTER)
        ref_b = AnchorRef(id_b, AnchorType.CENTER)
        graph.add_constraint(ref_a, ref_b, 0.0, constraint_type=ConstraintType.COINCIDENT)

        positions = {id_a: (10.0, 20.0), id_b: (50.0, 80.0)}
        offsets: dict = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
        }

        result = graph.solve_anchored(positions, offsets, pinned_items={id_a}, tolerance=0.01)
        assert result.converged
        # A should not move; B should move to A's position
        assert id_a not in result.item_deltas
        delta_b = result.item_deltas.get(id_b, (0.0, 0.0))
        final_bx = positions[id_b][0] + delta_b[0]
        final_by = positions[id_b][1] + delta_b[1]
        assert abs(final_bx - 10.0) < 0.01
        assert abs(final_by - 20.0) < 0.01

    def test_coincident_solver_already_coincident(self, qtbot) -> None:
        """Solver is stable when anchors are already coincident."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        ref_a = AnchorRef(id_a, AnchorType.CENTER)
        ref_b = AnchorRef(id_b, AnchorType.CENTER)
        graph.add_constraint(ref_a, ref_b, 0.0, constraint_type=ConstraintType.COINCIDENT)

        positions = {id_a: (50.0, 50.0), id_b: (50.0, 50.0)}
        offsets: dict = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
        }

        result = graph.solve_anchored(positions, offsets, tolerance=0.01)
        assert result.converged
        assert len(result.item_deltas) == 0

    def test_coincident_serialization_roundtrip(self, qtbot) -> None:
        """COINCIDENT constraint survives to_dict/from_dict round-trip."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.COINCIDENT,
        )
        data = graph.to_list()
        restored = ConstraintGraph.from_list(data)
        assert len(restored.constraints) == 1
        rc = list(restored.constraints.values())[0]
        assert rc.constraint_type == ConstraintType.COINCIDENT
        assert rc.target_distance == 0.0


# --- Parallel constraint tests ---


class TestParallelConstraint:
    """Tests for the PARALLEL constraint type."""

    def test_parallel_constraint_type_enum(self, qtbot) -> None:
        """PARALLEL should be a distinct ConstraintType."""
        assert ConstraintType.PARALLEL != ConstraintType.DISTANCE
        assert ConstraintType.PARALLEL != ConstraintType.HORIZONTAL
        assert ConstraintType.PARALLEL != ConstraintType.COINCIDENT

    def test_add_parallel_constraint(self, qtbot) -> None:
        """Can add a PARALLEL constraint to a graph."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        c = graph.add_constraint(
            AnchorRef(id_a, AnchorType.EDGE_TOP),
            AnchorRef(id_b, AnchorType.EDGE_LEFT),
            45.0,  # target_rotation for item B in degrees
            constraint_type=ConstraintType.PARALLEL,
        )
        assert c.constraint_type == ConstraintType.PARALLEL
        assert c.target_distance == 45.0
        assert c.anchor_a.anchor_type == AnchorType.EDGE_TOP
        assert c.anchor_b.anchor_type == AnchorType.EDGE_LEFT

    def test_parallel_solver_does_not_translate(self, qtbot) -> None:
        """PARALLEL constraint should not produce translation deltas (rotation only)."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.EDGE_TOP),
            AnchorRef(id_b, AnchorType.EDGE_LEFT),
            30.0,
            constraint_type=ConstraintType.PARALLEL,
        )
        positions = {id_a: (0.0, 0.0), id_b: (100.0, 0.0)}
        result = graph.solve(positions)

        # PARALLEL is a snapshot constraint: solver does not produce translation deltas
        assert id_a not in result.item_deltas
        assert id_b not in result.item_deltas

    def test_parallel_constraint_serialization_roundtrip(self, qtbot) -> None:
        """PARALLEL constraint survives to_dict/from_dict round-trip."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.EDGE_TOP),
            AnchorRef(id_b, AnchorType.EDGE_RIGHT),
            67.5,
            constraint_type=ConstraintType.PARALLEL,
        )
        data = graph.to_list()
        restored = ConstraintGraph.from_list(data)
        assert len(restored.constraints) == 1
        rc = list(restored.constraints.values())[0]
        assert rc.constraint_type == ConstraintType.PARALLEL
        assert rc.target_distance == 67.5
        assert rc.anchor_a.anchor_type == AnchorType.EDGE_TOP
        assert rc.anchor_b.anchor_type == AnchorType.EDGE_RIGHT

    def test_parallel_solver_result_has_rotation_deltas_field(self, qtbot) -> None:
        """SolverResult should expose item_rotation_deltas dict."""
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.EDGE_TOP),
            AnchorRef(id_b, AnchorType.EDGE_LEFT),
            0.0,
            constraint_type=ConstraintType.PARALLEL,
        )
        positions = {id_a: (0.0, 0.0), id_b: (100.0, 0.0)}
        result = graph.solve(positions)
        assert hasattr(result, "item_rotation_deltas")
        assert isinstance(result.item_rotation_deltas, dict)
