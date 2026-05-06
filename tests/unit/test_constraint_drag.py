"""Tests for US-7.5: Constraint solver drag integration.

Tests the anchor-aware constraint solver and constraint propagation
during drag operations.
"""

import math
from uuid import uuid4

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

    def test_b_pinned_as_reference_only_a_moves(self, qtbot) -> None:
        """Pinning B as reference: only A moves to satisfy the distance.

        This mirrors the CAD convention applied by _execute_constraint_with_solve:
        anchor B's item_id is passed in extra_pinned (which becomes pinned_items
        in solve_anchored) so that B stays fixed and A moves the full correction.
        Scenario from issue #139: objects 10 m apart, target 8 m.
        """
        graph = ConstraintGraph()
        id_a, id_b = uuid4(), uuid4()
        graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            800.0,  # target: 8 m
        )
        positions = {id_a: (0.0, 0.0), id_b: (1000.0, 0.0)}  # 10 m apart
        anchor_offsets = {
            (id_a, AnchorType.CENTER, 0): (0.0, 0.0),
            (id_b, AnchorType.CENTER, 0): (0.0, 0.0),
        }

        # B is passed as pinned — simulates _compute_constraint_solve_moves(extra_pinned={id_b})
        result = graph.solve_anchored(positions, anchor_offsets, pinned_items={id_b})

        assert result.converged
        assert id_b not in result.item_deltas, "B (reference) must not move"
        assert id_a in result.item_deltas, "A must move to satisfy the constraint"
        new_ax = 0.0 + result.item_deltas[id_a][0]
        dist = abs(1000.0 - new_ax)
        assert abs(dist - 800.0) < 1.0, f"Constraint unsatisfied: dist={dist}, target=800"


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


# --- Issue #168: Polyline vertex drag isolation ---


class TestPolylineVertexDragIsolation:
    """Issue #168: dragging a polyline vertex must touch only that vertex.

    Regression coverage for the report that moving an unconstrained vertex
    on a fence with edge-length constraints elsewhere caused the entire
    polyline to "jump around wildly" on every pixel of motion.
    """

    def test_unconstrained_vertex_is_passthrough(self, qtbot) -> None:
        """If no constraint touches the moving vertex, projection is a no-op."""
        graph = ConstraintGraph()
        pid = uuid4()
        # Polyline v0..v4 along the X axis with an EDGE_LENGTH constraint
        # only between v2 and v3.
        graph.add_constraint(
            AnchorRef(pid, AnchorType.ENDPOINT, 2),
            AnchorRef(pid, AnchorType.ENDPOINT, 3),
            100.0,
        )

        item_positions = {pid: (0.0, 0.0)}
        anchor_offsets = {
            (pid, AnchorType.ENDPOINT, i): (i * 100.0, 0.0) for i in range(5)
        }
        deformable_vertices = {pid: [(i * 100.0, 0.0) for i in range(5)]}

        result = graph.project_to_feasible(
            moving_vertex=(pid, 0),
            desired_scene_pos=(5.0, 5.0),
            item_positions=item_positions,
            anchor_offsets=anchor_offsets,
            deformable_items={pid},
            deformable_vertices=deformable_vertices,
        )
        # Short-circuit: cursor passed through untouched.
        assert result == (5.0, 5.0)

    def test_constrained_vertex_projection_only_moves_target(self, qtbot) -> None:
        """Projecting the constrained vertex must keep neighbours stationary."""
        graph = ConstraintGraph()
        pid = uuid4()
        graph.add_constraint(
            AnchorRef(pid, AnchorType.ENDPOINT, 2),
            AnchorRef(pid, AnchorType.ENDPOINT, 3),
            100.0,
        )

        item_positions = {pid: (0.0, 0.0)}
        anchor_offsets = {
            (pid, AnchorType.ENDPOINT, i): (i * 100.0, 0.0) for i in range(5)
        }
        # Snapshot before projection so we can verify no other vertex moves.
        before = [(i * 100.0, 0.0) for i in range(5)]
        deformable_vertices = {pid: list(before)}

        # Drag v2 perpendicular to the chain — solver should snap onto the
        # circle of radius 100 around v3=(300,0).
        result = graph.project_to_feasible(
            moving_vertex=(pid, 2),
            desired_scene_pos=(200.0, 50.0),
            item_positions=item_positions,
            anchor_offsets=anchor_offsets,
            deformable_items={pid},
            deformable_vertices=deformable_vertices,
        )
        # Distance from v3=(300,0) must equal target 100 (within tol).
        d = math.hypot(result[0] - 300.0, result[1] - 0.0)
        assert abs(d - 100.0) < 1.0

        # All other vertices unchanged in the deformable_vertices state.
        verts = deformable_vertices[pid]
        for i in (0, 1, 3, 4):
            assert verts[i] == before[i], f"v{i} moved; should be pinned"

    def test_no_per_frame_drift_on_fully_constrained_vertex(self, qtbot) -> None:
        """Repeated near-stationary projections must not accumulate drift.

        Reproduces the post-merge manual test failure on PR #169: a fully
        constrained middle vertex (EDGE_LENGTH on both incident edges) was
        slipping ~0.2 cm per frame because newton_refine early-returned on
        its cm-scale tolerance, leaving ``vertex_pos[moving]`` at the cursor.
        Drives 100 frames of cursor sitting 0.3 cm off the original v_i and
        asserts the projected point stays on the constraint set throughout.
        """
        graph = ConstraintGraph()
        pid = uuid4()
        # Chain v0=(0,0), v1=(100,0), v2=(200,0), v3=(300,0), v4=(400,0)
        # with EDGE_LENGTH between every adjacent pair.
        for i in range(4):
            graph.add_constraint(
                AnchorRef(pid, AnchorType.ENDPOINT, i),
                AnchorRef(pid, AnchorType.ENDPOINT, i + 1),
                100.0,
            )

        item_positions = {pid: (0.0, 0.0)}
        anchor_offsets = {
            (pid, AnchorType.ENDPOINT, i): (i * 100.0, 0.0) for i in range(5)
        }
        original = [(i * 100.0, 0.0) for i in range(5)]

        # Simulate 100 mouse frames of cursor wobbling 0.3 cm off v2.
        for frame in range(100):
            # Cursor offset in tight 0.3 cm circle centred on v2.
            theta = (frame / 100.0) * 2.0 * math.pi
            cursor = (
                200.0 + 0.3 * math.cos(theta),
                0.0 + 0.3 * math.sin(theta),
            )
            deformable_vertices = {pid: list(original)}
            result = graph.project_to_feasible(
                moving_vertex=(pid, 2),
                desired_scene_pos=cursor,
                item_positions=item_positions,
                anchor_offsets=anchor_offsets,
                deformable_items={pid},
                deformable_vertices=deformable_vertices,
            )
            # Result must lie exactly on the v1=(100,0)/v3=(300,0) intersection
            # — i.e. v2's original position — within sub-mm precision.
            d_v1 = math.hypot(result[0] - 100.0, result[1])
            d_v3 = math.hypot(result[0] - 300.0, result[1])
            assert abs(d_v1 - 100.0) < 1e-2, (
                f"frame {frame}: |v2-v1|={d_v1:.6f} drifted from 100"
            )
            assert abs(d_v3 - 100.0) < 1e-2, (
                f"frame {frame}: |v2-v3|={d_v3:.6f} drifted from 100"
            )


# --- Issue #168 + #167: Constraint anchor index shift on vertex add/delete ---


class TestConstraintIndexShift:
    """Inserting / deleting vertices must keep constraint anchor indices valid."""

    def test_shift_on_insert(self, qtbot) -> None:
        """An inserted vertex shifts later anchor indices up by one."""
        graph = ConstraintGraph()
        pid = uuid4()
        graph.add_constraint(
            AnchorRef(pid, AnchorType.ENDPOINT, 2),
            AnchorRef(pid, AnchorType.ENDPOINT, 3),
            100.0,
        )

        # Insert a vertex at index 1 — both anchored vertices shift to 3 and 4.
        graph.shift_vertex_indices(pid, threshold=1, delta=+1)
        c = next(iter(graph.constraints.values()))
        assert c.anchor_a.anchor_index == 3
        assert c.anchor_b.anchor_index == 4

    def test_delete_drops_referencing_constraints_then_shifts(self, qtbot) -> None:
        """Deleting a vertex drops constraints on it, shifts higher down."""
        graph = ConstraintGraph()
        pid = uuid4()
        # v2-v3 constraint and v3-v4 constraint (both touch v3).
        graph.add_constraint(
            AnchorRef(pid, AnchorType.ENDPOINT, 2),
            AnchorRef(pid, AnchorType.ENDPOINT, 3),
            100.0,
        )
        graph.add_constraint(
            AnchorRef(pid, AnchorType.ENDPOINT, 3),
            AnchorRef(pid, AnchorType.ENDPOINT, 4),
            100.0,
        )

        # Delete v3: both constraints reference it directly, so both go away.
        removed = graph.remove_vertex_constraints(pid, vertex_index=3)
        assert len(removed) == 2
        assert len(graph.constraints) == 0

    def test_shift_on_delete_only_higher_indices(self, qtbot) -> None:
        """A constraint anchored at v4 shifts to v3 when v0 is deleted."""
        graph = ConstraintGraph()
        pid = uuid4()
        graph.add_constraint(
            AnchorRef(pid, AnchorType.ENDPOINT, 3),
            AnchorRef(pid, AnchorType.ENDPOINT, 4),
            100.0,
        )

        # Simulate deletion of v0: shift indices >= 1 down by one.
        graph.shift_vertex_indices(pid, threshold=1, delta=-1)
        c = next(iter(graph.constraints.values()))
        assert c.anchor_a.anchor_index == 2
        assert c.anchor_b.anchor_index == 3
