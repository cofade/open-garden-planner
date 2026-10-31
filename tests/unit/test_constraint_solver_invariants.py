"""Geometric solver oracles, independent of convergence flags (#457)."""

import copy
import math
from uuid import uuid4

import pytest

from open_garden_planner.core.constraint_solver_newton import newton_refine
from open_garden_planner.core.constraints import (
    AnchorRef,
    Constraint,
    ConstraintGraph,
    ConstraintType,
)
from open_garden_planner.core.measure_snapper import AnchorType


def constraint(a, b, kind, target=0.0, c=None):
    return Constraint(uuid4(), AnchorRef(a, AnchorType.CENTER), AnchorRef(b, AnchorType.CENTER),
                      target, constraint_type=kind,
                      anchor_c=AnchorRef(c, AnchorType.CENTER) if c else None)


def refine(positions, constraints, pins, offsets=None, **kwargs):
    return newton_refine(positions, {}, offsets or {}, set(), {}, constraints, pins, **kwargs)


@pytest.mark.parametrize("kind", [ConstraintType.HORIZONTAL, ConstraintType.VERTICAL,
                                  ConstraintType.SYMMETRY_HORIZONTAL, ConstraintType.SYMMETRY_VERTICAL])
def test_newton_alignment_and_symmetry_have_correct_geometry(kind, qtbot):
    a, b = uuid4(), uuid4()
    positions = {a: [10.0, 20.0], b: [80.0, 110.0]}
    expected = {
        ConstraintType.HORIZONTAL: (10.0, 110.0),
        ConstraintType.VERTICAL: (80.0, 20.0),
        ConstraintType.SYMMETRY_HORIZONTAL: (80.0, -50.0),
        ConstraintType.SYMMETRY_VERTICAL: (-20.0, 110.0),
    }[kind]
    converged, error = refine(positions, [constraint(a, b, kind, 30.0)], {b}, tol=1e-6)
    assert converged
    assert error <= 1e-6
    assert positions[a] == pytest.approx(expected, abs=1e-6)
    assert positions[b] == [80.0, 110.0]


@pytest.mark.parametrize("kind", [ConstraintType.HORIZONTAL_DISTANCE, ConstraintType.VERTICAL_DISTANCE])
@pytest.mark.parametrize("sign", [-1, 1])
def test_newton_axis_distance_preserves_side_and_free_coordinate(kind, sign, qtbot):
    a, b = uuid4(), uuid4()
    initial = [sign * 140.0, sign * 160.0]
    positions = {a: initial.copy(), b: [10.0, 20.0]}
    converged, error = refine(positions, [constraint(a, b, kind, 75.0)], {b}, tol=1e-6)
    axis = 0 if kind == ConstraintType.HORIZONTAL_DISTANCE else 1
    assert abs(positions[a][axis] - positions[b][axis]) == pytest.approx(75, abs=1e-6)
    assert positions[a][axis] == pytest.approx(positions[b][axis] + sign * 75, abs=1e-6)
    assert positions[a][1-axis] == initial[1-axis]
    assert positions[b] == [10.0, 20.0]
    assert converged and error <= 1e-6


@pytest.mark.parametrize("all_pinned", [False, True])
def test_newton_infeasible_reports_actual_residual_and_keeps_pins(all_pinned, qtbot):
    a, b = uuid4(), uuid4()
    positions = {a: [150.0, 0.0], b: [0.0, 0.0]}
    before = copy.deepcopy(positions)
    constraints = [constraint(a, b, ConstraintType.DISTANCE, distance) for distance in (100, 200)]
    pins = {a, b} if all_pinned else {b}
    converged, error = refine(positions, constraints, pins, tol=0.01)
    residual = max(abs(math.dist(positions[a], positions[b]) - distance) for distance in (100, 200))
    assert residual >= 50.0 - 1e-6  # Triangle inequality: cannot satisfy both radii.
    assert not converged
    assert error == pytest.approx(residual, abs=1e-6)
    assert positions[b] == before[b]
    if all_pinned:
        assert positions == before


def test_anchored_all_pinned_infeasible_is_not_success(qtbot):
    a, b = uuid4(), uuid4()
    graph = ConstraintGraph()
    graph.add_constraint(AnchorRef(a, AnchorType.CENTER), AnchorRef(b, AnchorType.CENTER), 200)
    positions = {a: (0.0, 0.0), b: (100.0, 0.0)}
    result = graph.solve_anchored(positions, {}, pinned_items={a, b}, tolerance=0.01)
    assert not result.converged
    assert result.max_error == pytest.approx(100.0)
    assert result.item_deltas == {}
    assert result.vertex_deltas == {}
    assert positions == {a: (0.0, 0.0), b: (100.0, 0.0)}


@pytest.mark.parametrize("use_newton", [False, True])
def test_nonzero_anchor_offsets_resolve_in_scene_frame(use_newton, qtbot):
    a, b = uuid4(), uuid4()
    offsets = {(a, AnchorType.CENTER, 0): (17.0, -23.0),
               (b, AnchorType.CENTER, 0): (-31.0, 47.0)}
    positions = {a: (200.0, 90.0), b: (-30.0, 50.0)}
    before = copy.deepcopy((positions, offsets))
    pair = constraint(a, b, ConstraintType.COINCIDENT)
    if use_newton:
        mutable = {uid: list(point) for uid, point in positions.items()}
        converged, error = refine(mutable, [pair], {b}, offsets, tol=1e-6)
        resolved = mutable
    else:
        graph = ConstraintGraph()
        graph.add_constraint(pair.anchor_a, pair.anchor_b, 0, constraint_type=pair.constraint_type)
        result = graph.solve_anchored(positions, offsets, pinned_items={b}, tolerance=1e-6)
        resolved = {uid: (point[0] + result.item_deltas.get(uid, (0, 0))[0],
                          point[1] + result.item_deltas.get(uid, (0, 0))[1])
                    for uid, point in positions.items()}
        converged, error = result.converged, result.max_error
    assert resolved[a] == pytest.approx((-78.0, 120.0), abs=1e-6)
    assert resolved[b] == pytest.approx(positions[b], abs=1e-6)
    assert converged and error <= 1e-6
    assert (positions, offsets) == before


@pytest.mark.parametrize("start", [(80.0, 10.0), (80.0, -10.0)])
def test_coupled_newton_residual_matches_geometry_and_decreases(start, qtbot):
    a, b, c = uuid4(), uuid4(), uuid4()
    positions = {a: list(start), b: [0.0, 0.0], c: [150.0, 0.0]}
    constraints = [constraint(a, uid, ConstraintType.DISTANCE, 100) for uid in (b, c)]
    initial = max(abs(math.dist(positions[a], positions[uid])-100) for uid in (b, c))
    converged, error = refine(positions, constraints, {b, c}, tol=0.01)
    residual = max(abs(math.dist(positions[a], positions[uid])-100) for uid in (b, c))
    assert converged
    assert residual <= 0.01
    assert residual < initial
    assert error == pytest.approx(residual, abs=1e-9)
    assert positions[b] == [0.0, 0.0] and positions[c] == [150.0, 0.0]
    assert positions[a][1] * start[1] > 0  # Nearest continuous circle-intersection branch.


def test_deformable_newton_changes_only_free_vertex(qtbot):
    a, b = uuid4(), uuid4()
    positions = {a: [0.0, 0.0], b: [30.0, 40.0]}
    vertices = {(a, 0): [10.0, 20.0], (a, 1): [200.0, 300.0]}
    pair = constraint(a, b, ConstraintType.COINCIDENT)
    pair.anchor_a = AnchorRef(a, AnchorType.CORNER, 0)
    converged, error = newton_refine(positions, vertices, {}, {a}, {a: [(a, 0)]}, [pair], {b}, tol=1e-6)
    assert vertices[(a, 0)] == pytest.approx([30, 40], abs=1e-6)
    assert vertices[(a, 1)] == [200.0, 300.0]
    assert positions == {a: [0.0, 0.0], b: [30.0, 40.0]}
    assert converged and error <= 1e-6


@pytest.mark.parametrize("trial_target,compatible", [(100.0, True), (200.0, False)])
def test_feasibility_and_conflict_ids_preserve_graph_and_inputs(trial_target, compatible, qtbot):
    a, b, c, d = (uuid4() for _ in range(4))
    graph = ConstraintGraph()
    old = graph.add_constraint(AnchorRef(a, AnchorType.CENTER), AnchorRef(b, AnchorType.CENTER), 100)
    unrelated = graph.add_constraint(AnchorRef(c, AnchorType.CENTER), AnchorRef(d, AnchorType.CENTER), 0,
                                     constraint_type=ConstraintType.HORIZONTAL)
    positions = {a: (0.0, 0.0), b: (100.0, 0.0), c: (10.0, 80.0), d: (50.0, 80.0)}
    before = copy.deepcopy((graph.constraints, graph._adjacency, positions))
    trial = constraint(a, b, ConstraintType.DISTANCE, trial_target)
    assert graph.validate_constraint(trial.anchor_a, trial.anchor_b, trial_target,
                                     trial.constraint_type, positions, {}, tolerance=0.01) is compatible
    conflicts = graph.find_conflicting_constraints(trial, positions, {}, tolerance=0.01)
    assert set(conflicts) == (set() if compatible else {old.constraint_id})
    assert unrelated.constraint_id not in conflicts
    assert (graph.constraints, graph._adjacency, positions) == before


@pytest.mark.parametrize("method", ["validate", "conflicts"])
def test_trial_queries_clean_up_after_solver_exception(monkeypatch, method, qtbot):
    a, b = uuid4(), uuid4()
    graph = ConstraintGraph()
    pair = constraint(a, b, ConstraintType.DISTANCE, 100)
    before = copy.deepcopy((graph.constraints, graph._adjacency))
    positions = {a: (0.0, 0.0), b: (100.0, 0.0)}

    def fail(**kwargs):
        raise RuntimeError("solver probe failed")

    monkeypatch.setattr(graph, "solve_anchored", fail)
    with pytest.raises(RuntimeError, match="solver probe failed"):
        if method == "validate":
            graph.validate_constraint(
                pair.anchor_a, pair.anchor_b, 100, pair.constraint_type, positions, {}
            )
        else:
            graph.find_conflicting_constraints(pair, positions, {})
    assert (graph.constraints, graph._adjacency) == before


def test_a_trial_with_a_missing_anchor_is_infeasible(qtbot):
    """A graph we cannot even build is not "compatible" (#670 review, P2)."""
    a, b = uuid4(), uuid4()
    graph = ConstraintGraph()
    before = copy.deepcopy((graph.constraints, graph._adjacency))
    assert (
        graph.validate_constraint(
            AnchorRef(a, AnchorType.CENTER),
            AnchorRef(b, AnchorType.CENTER),
            100.0,
            ConstraintType.DISTANCE,
            {a: (0.0, 0.0)},  # b is missing
            {},
        )
        is False
    )
    assert (graph.constraints, graph._adjacency) == before


@pytest.mark.parametrize("desired", [(200.0, 70.0), (-80.0, 180.0)])
def test_projected_vertex_is_feasible_and_preserves_input(desired, qtbot):
    polygon, circle = uuid4(), uuid4()
    graph = ConstraintGraph()
    graph.add_constraint(AnchorRef(polygon, AnchorType.CORNER, 0), AnchorRef(circle, AnchorType.CENTER),
                         100, constraint_type=ConstraintType.POINT_ON_CIRCLE)
    positions = {polygon: (0.0, 0.0), circle: (30.0, 40.0)}
    vertices = {polygon: [(130.0, 40.0), (200.0, 300.0)]}
    before = copy.deepcopy((positions, vertices, graph.constraints))
    projected = graph.project_to_feasible((polygon, 0), desired, positions, {}, {polygon}, vertices)
    assert math.dist(projected, positions[circle]) == pytest.approx(100, abs=1e-4)
    assert math.dist(projected, desired) < math.dist(vertices[polygon][0], desired)
    assert (positions, vertices, graph.constraints) == before
