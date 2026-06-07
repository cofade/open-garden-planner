"""Unit tests for the TANGENT constraint solver math (issue #192, US-B8).

TANGENT means "the edge ``anchor_a→anchor_c`` is perpendicular to the radius
``anchor_b−anchor_a``" — residual ``(C−v1)·(v0−v1) == 0``. Paired with
POINT_ON_CIRCLE (which pins ``|v1−C| == radius``) it expresses a proper
line-tangent-to-circle with the contact welded at ``v1``. The pair is
non-degenerate (this residual's gradient is along the edge, orthogonal to
POINT_ON_CIRCLE's radial gradient), so it holds under drag without drifting.
These tests drive ``solve_anchored`` end-to-end.
"""

from __future__ import annotations

import math
from uuid import uuid4

from open_garden_planner.core.constraints import (
    AnchorRef,
    ConstraintGraph,
    ConstraintType,
)
from open_garden_planner.core.measure_snapper import AnchorType

_RADIUS = 50.0


def _radius_proj(
    center: tuple[float, float],
    v1: tuple[float, float],
    v0: tuple[float, float],
) -> float:
    """The TANGENT residual: radius·êdge. ~0 when the edge ⟂ the radius."""
    ex, ey = v0[0] - v1[0], v0[1] - v1[1]
    elen = math.hypot(ex, ey)
    return ((center[0] - v1[0]) * ex + (center[1] - v1[1]) * ey) / elen


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _solve_tangent(
    center_xy: tuple[float, float],
    v0: tuple[float, float],
    v1: tuple[float, float],
    *,
    with_point_on_circle: bool,
    pinned_circle: bool = True,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Build a TANGENT (± POINT_ON_CIRCLE) graph and return the final (v0, v1).

    The polyline has one distinct constrained vertex (v1), so it is rigid: the
    returned endpoints are the originals shifted by the item delta.
    """
    circle, poly = uuid4(), uuid4()
    graph = ConstraintGraph()
    a = AnchorRef(poly, AnchorType.ENDPOINT, 1)  # v1 (contact)
    b = AnchorRef(circle, AnchorType.CENTER, 0)  # centre
    c = AnchorRef(poly, AnchorType.ENDPOINT, 0)  # v0 (far vertex)
    if with_point_on_circle:
        graph.add_constraint(a, b, _RADIUS, constraint_type=ConstraintType.POINT_ON_CIRCLE)
    graph.add_constraint(
        a, b, _RADIUS, constraint_type=ConstraintType.TANGENT, anchor_c=c
    )
    item_positions = {circle: center_xy, poly: (0.0, 0.0)}
    anchor_offsets = {
        (circle, AnchorType.CENTER, 0): (0.0, 0.0),
        (poly, AnchorType.ENDPOINT, 0): v0,
        (poly, AnchorType.ENDPOINT, 1): v1,
    }
    result = graph.solve_anchored(
        item_positions,
        anchor_offsets,
        pinned_items={circle} if pinned_circle else set(),
        max_iterations=40,
        tolerance=0.1,
    )
    dx, dy = result.item_deltas.get(poly, (0.0, 0.0))
    return (v0[0] + dx, v0[1] + dy), (v1[0] + dx, v1[1] + dy)


class TestTangentConstraintSolver:
    def test_tangent_alone_makes_edge_perpendicular_to_radius(self, qtbot) -> None:
        """TANGENT alone drives the edge perpendicular to the radius (residual 0).

        It does NOT control the distance — that's POINT_ON_CIRCLE's job.
        """
        # Edge starts tilted (not perpendicular to the radius to the centre).
        v0_f, v1_f = _solve_tangent(
            (0.0, 0.0), (-150.0, 80.0), (0.0, 50.0), with_point_on_circle=False
        )
        assert abs(_radius_proj((0.0, 0.0), v1_f, v0_f)) < 1.0

    def test_point_on_circle_plus_tangent_is_proper_tangent(self, qtbot) -> None:
        """Both constraints → a true tangent: contact on the rim AND edge⟂radius."""
        # Start perturbed: contact off the rim and edge not perpendicular.
        v0_f, v1_f = _solve_tangent(
            (0.0, 0.0), (-150.0, 70.0), (5.0, 40.0), with_point_on_circle=True
        )
        assert abs(_dist((0.0, 0.0), v1_f) - _RADIUS) < 1.0  # contact welded to rim
        assert abs(_radius_proj((0.0, 0.0), v1_f, v0_f)) < 1.0  # tangent

    def test_combo_holds_when_circle_moves(self, qtbot) -> None:
        """Pinning the circle at a moved centre keeps the contact welded + tangent
        (the non-degenerate pair does not drift)."""
        # Drawn tangent: contact at top (0,50), far vertex left along y=50.
        # Now the circle centre sits at (-40, 25) instead of the origin.
        v0_f, v1_f = _solve_tangent(
            (-40.0, 25.0), (-150.0, 50.0), (0.0, 50.0), with_point_on_circle=True
        )
        c = (-40.0, 25.0)
        assert abs(_dist(c, v1_f) - _RADIUS) < 1.5  # still on the rim
        assert abs(_radius_proj(c, v1_f, v0_f)) < 1.5  # still tangent

    def test_serialization_round_trip(self, qtbot) -> None:
        """A TANGENT constraint round-trips through to_dict/from_dict."""
        from open_garden_planner.core.constraints import Constraint

        circle, poly = uuid4(), uuid4()
        graph = ConstraintGraph()
        graph.add_constraint(
            AnchorRef(poly, AnchorType.ENDPOINT, 1),
            AnchorRef(circle, AnchorType.CENTER, 0),
            _RADIUS,
            constraint_type=ConstraintType.TANGENT,
            anchor_c=AnchorRef(poly, AnchorType.ENDPOINT, 0),
        )
        original = next(iter(graph.constraints.values()))
        restored = Constraint.from_dict(original.to_dict())
        assert restored.constraint_type == ConstraintType.TANGENT
        assert restored.anchor_c is not None
        assert restored.anchor_c.item_id == poly
        assert restored.anchor_c.anchor_index == 0
