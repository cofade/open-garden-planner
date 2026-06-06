"""Auto-emit geometric constraints from snap engagements (Phase 13 follow-up).

When a drawing tool commits a vertex at a snapped point, the snap kind +
source item describe an *intent* that should usually outlive the click
— e.g. "I want this vertex to stay on that edge". This module turns
that intent into a real constraint stored in the project's
`ConstraintGraph`.

Coverage (issues #196 + #192, PR "Make snap-constraints real"):

| Snap kind     | Source item          | Emits                              |
| ------------- | -------------------- | ---------------------------------- |
| NEAREST       | line-like outline    | POINT_ON_EDGE (named edge)         |
| NEAREST       | circle / arc         | POINT_ON_CIRCLE                    |
| MIDPOINT      | line-like outline    | COINCIDENT (vertex ↔ edge mid)     |
| PERPENDICULAR | line-like outline    | POINT_ON_EDGE (named edge)         |
| TANGENT       | circle / arc         | POINT_ON_CIRCLE + TANGENT          |

A tangent snap emits POINT_ON_CIRCLE (pins the contact's *radial* position —
distance == radius) plus TANGENT, where TANGENT means "the edge is
perpendicular to the radius at the contact" (residual `(C−v1)·(v0−v1) == 0`).
That residual's gradient is along the edge, **orthogonal** to POINT_ON_CIRCLE's
radial gradient, so the pair is full-rank (non-degenerate): the contact is
welded to the rim *and* the edge stays tangent, and the contact co-moves with
the circle. (A "perpendicular distance == radius" tangent would instead be
parallel to POINT_ON_CIRCLE and degenerate — it drifts. See ADR-024.)

The edge a snap projected onto is carried on `SnapCandidate.source_edge_index`
(populated by the nearest / midpoint / perpendicular providers). The emitter
turns that edge into a *named* constraint by resolving the edge's two endpoints
(POINT_ON_EDGE) or its midpoint (COINCIDENT) to concrete `AnchorRef`s — matched
against `get_anchor_points(source)` so the same anchors the drag solver tracks
are referenced, and the constraint is actually enforced (issue #197 reuses the
existing `CanvasView._propagate_constraints_during_drag` path).

`PERPENDICULAR` snap deliberately emits POINT_ON_EDGE (vertex rides the source
edge) rather than the rotation-only `ConstraintType.PERPENDICULAR`: the latter
rotates a whole item and is skipped by the position solver, so it would not
hold a single drawn edge at 90°. A true edge⟂edge residual is deferred.

Drawing tools call `emit_for_polyline(view, item, snap_contexts)` immediately
after creating the final item; constraints land in the project graph via the
standard `AddConstraintCommand` so undo + dimension-line refresh fire.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QLineF, QPointF

if TYPE_CHECKING:
    from uuid import UUID

    from PyQt6.QtWidgets import QGraphicsItem

    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.snap.provider import SnapCandidate
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

# Max distance (scene cm) between a recomputed edge anchor and a catalogued
# anchor for them to be considered the same point. Both derive from the same
# item geometry at emit time, so the gap is floating-point noise; the bound is
# generous only to stay robust to minor rounding.
_ANCHOR_MATCH_TOL = 0.5


def emit_for_polyline(
    view: CanvasView,
    polyline_item: QGraphicsItem,
    snap_contexts: list[SnapCandidate | None],
) -> int:
    """Emit auto-constraints for each snapped vertex of a freshly placed polyline.

    Returns the number of constraints actually added. Snaps that can't be
    expressed as a constraint (unsupported source type, missing edge index,
    no previous vertex for a tangent line) are skipped silently.
    """
    from open_garden_planner.core.commands import AddConstraintCommand

    graph = _constraint_graph(view)
    if graph is None or not snap_contexts:
        return 0
    polyline_id = getattr(polyline_item, "item_id", None)
    if polyline_id is None:
        return 0

    cmd_manager = getattr(view, "command_manager", None)
    added = 0
    for vertex_idx, snap in enumerate(snap_contexts):
        if snap is None or snap.item is None:
            continue
        source_id = getattr(snap.item, "item_id", None)
        if source_id is None or source_id == polyline_id:
            continue

        for ctype, anchor_a, anchor_b, anchor_c, target in _constraints_for_snap(
            snap, source_id, polyline_item, vertex_idx
        ):
            cmd = AddConstraintCommand(
                graph=graph,
                anchor_a=anchor_a,
                anchor_b=anchor_b,
                target_distance=target,
                constraint_type=ctype,
                anchor_c=anchor_c,
            )
            if cmd_manager is not None:
                cmd_manager.execute(cmd)
            else:
                cmd.execute()
            added += 1

    if added > 0:
        # Snap the geometry to satisfy the new constraints right away, then
        # refresh the dimension-line overlay so they're visible from creation.
        if hasattr(view, "apply_constraint_solver"):
            view.apply_constraint_solver()
        if hasattr(view, "update_dimension_lines"):
            view.update_dimension_lines()
    return added


def _constraints_for_snap(
    snap: SnapCandidate,
    source_id: UUID,
    polyline_item: QGraphicsItem,
    vertex_idx: int,
) -> list:
    """Map a snapped vertex to zero or more constraint specs.

    Each spec is ``(constraint_type, anchor_a, anchor_b, anchor_c,
    target_distance)``. A tangent snap yields a POINT_ON_CIRCLE + TANGENT pair
    (TANGENT = edge⊥radius; the pairing is non-degenerate — see the module
    docstring and ADR-024).
    """
    from open_garden_planner.core.constraints import AnchorRef, ConstraintType
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.core.snap.provider import SnapCandidateKind

    source = snap.item
    polyline_id = polyline_item.item_id  # type: ignore[attr-defined]
    vertex_anchor = AnchorRef(
        item_id=polyline_id,
        anchor_type=AnchorType.ENDPOINT,
        anchor_index=vertex_idx,
    )

    # Circle / arc sources: the snap relates to the circle, not a straight edge.
    center, radius = _circle_center_radius(source)
    if center is not None and radius is not None:
        center_anchor = AnchorRef(
            item_id=source_id, anchor_type=AnchorType.CENTER, anchor_index=0
        )
        if snap.kind == SnapCandidateKind.TANGENT:
            # Weld the contact AND keep the edge tangent with a NON-degenerate
            # pair: POINT_ON_CIRCLE pins the contact's radial position (distance
            # = radius); TANGENT here means "the edge is perpendicular to the
            # radius at the contact" (residual (C−v1)·(v0−v1)=0), whose gradient
            # is along the edge direction — orthogonal to POINT_ON_CIRCLE's
            # radial gradient. Orthogonal gradients ⇒ full-rank Jacobian, so the
            # solver holds both robustly and the contact co-moves with the
            # circle. (A "signed perpendicular distance = radius" tangent would
            # instead be parallel to POINT_ON_CIRCLE and degenerate.)
            #
            # The edge is the polyline segment ending at this vertex; it needs
            # the previous vertex as its other endpoint.
            if vertex_idx == 0:
                return []  # no edge yet → can't define perpendicularity
            prev_anchor = AnchorRef(
                item_id=polyline_id,
                anchor_type=AnchorType.ENDPOINT,
                anchor_index=vertex_idx - 1,
            )
            return [
                (
                    ConstraintType.POINT_ON_CIRCLE,
                    vertex_anchor,
                    center_anchor,
                    None,
                    radius,
                ),
                (
                    ConstraintType.TANGENT,
                    vertex_anchor,
                    center_anchor,
                    prev_anchor,
                    radius,  # stored for display; the perp residual ignores it
                ),
            ]
        if snap.kind in (
            SnapCandidateKind.NEAREST,
            SnapCandidateKind.PERPENDICULAR,
        ):
            return [
                (
                    ConstraintType.POINT_ON_CIRCLE,
                    vertex_anchor,
                    center_anchor,
                    None,
                    radius,
                )
            ]
        return []

    # Straight-edge sources need the edge index the snap projected onto.
    if snap.source_edge_index is None:
        return []
    edge = _edge_line(source, snap.source_edge_index)
    if edge is None:
        return []

    if snap.kind == SnapCandidateKind.MIDPOINT:
        mid = QPointF(
            (edge.x1() + edge.x2()) / 2.0, (edge.y1() + edge.y2()) / 2.0
        )
        mid_anchor = _match_anchor(source, source_id, mid, _EDGE_MID_TYPES)
        if mid_anchor is None:
            return []
        return [(ConstraintType.COINCIDENT, vertex_anchor, mid_anchor, None, 0.0)]

    if snap.kind in (SnapCandidateKind.NEAREST, SnapCandidateKind.PERPENDICULAR):
        a_end = _match_anchor(source, source_id, edge.p1(), _VERTEX_TYPES)
        b_end = _match_anchor(source, source_id, edge.p2(), _VERTEX_TYPES)
        if a_end is None or b_end is None:
            return []
        return [(ConstraintType.POINT_ON_EDGE, vertex_anchor, a_end, b_end, 0.0)]

    return []


def _edge_line(source_item: object, edge_index: int) -> QLineF | None:
    """Return the ``edge_index``-th straight edge of ``source_item`` (scene coords)."""
    from open_garden_planner.core.snap.geometry import item_edges

    edges = list(item_edges(source_item))  # type: ignore[arg-type]
    if 0 <= edge_index < len(edges):
        return edges[edge_index]
    return None


def _match_anchor(
    source_item: object,
    source_id: UUID,
    scene_point: QPointF,
    types: frozenset,
) -> AnchorRef | None:
    """Resolve ``scene_point`` to the nearest catalogued anchor of ``types``.

    Matching against ``get_anchor_points`` (rather than recomputing indices)
    guarantees we reference the exact ``(anchor_type, anchor_index)`` the drag
    solver builds offsets for, so the emitted constraint is enforceable.
    """
    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import get_anchor_points

    best: AnchorRef | None = None
    best_dsq = _ANCHOR_MATCH_TOL * _ANCHOR_MATCH_TOL
    for anchor in get_anchor_points(source_item):  # type: ignore[arg-type]
        if anchor.anchor_type not in types:
            continue
        dx = anchor.point.x() - scene_point.x()
        dy = anchor.point.y() - scene_point.y()
        dsq = dx * dx + dy * dy
        if dsq <= best_dsq:
            best_dsq = dsq
            best = AnchorRef(
                item_id=source_id,
                anchor_type=anchor.anchor_type,
                anchor_index=anchor.anchor_index,
            )
    return best


def _circle_center_radius(
    source_item: object,
) -> tuple[QPointF | None, float | None]:
    """Return (scene centre, radius) for a circle/arc source, else (None, None).

    EllipseItem is intentionally excluded — it is not a true circle, so
    POINT_ON_CIRCLE / TANGENT (which assume a constant radius) don't apply.
    """
    from open_garden_planner.ui.canvas.items import ArcItem, CircleItem
    from open_garden_planner.ui.canvas.items.construction_item import (
        ConstructionCircleItem,
    )

    if isinstance(source_item, ArcItem):
        return source_item.center, source_item.radius
    if isinstance(source_item, (CircleItem, ConstructionCircleItem)):
        rect = source_item.rect()
        local_center = QPointF(
            rect.x() + rect.width() / 2.0, rect.y() + rect.height() / 2.0
        )
        radius = rect.width() / 2.0
        if radius <= 0:
            return None, None
        return source_item.mapToScene(local_center), radius
    return None, None


def _constraint_graph(view: CanvasView) -> object | None:
    """Locate the project's ConstraintGraph via the canvas scene.

    The scene exposes it through `active_layer.constraint_graph` in
    current builds; fall back to `view.constraint_graph` if a future
    refactor moves it.
    """
    scene = view.scene()
    if hasattr(scene, "constraint_graph"):
        return scene.constraint_graph
    if hasattr(view, "constraint_graph"):
        return view.constraint_graph
    return None


def _lazy_anchor_type_sets() -> tuple[frozenset, frozenset]:
    """Build the AnchorType sets once the enum is importable."""
    from open_garden_planner.core.measure_snapper import AnchorType

    vertex = frozenset({AnchorType.CORNER, AnchorType.ENDPOINT})
    edge_mid = frozenset(
        {
            AnchorType.EDGE_TOP,
            AnchorType.EDGE_BOTTOM,
            AnchorType.EDGE_LEFT,
            AnchorType.EDGE_RIGHT,
        }
    )
    return vertex, edge_mid


_VERTEX_TYPES, _EDGE_MID_TYPES = _lazy_anchor_type_sets()
