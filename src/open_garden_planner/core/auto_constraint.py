"""Auto-emit geometric constraints from snap engagements (Phase 13 follow-up).

When a drawing tool commits a vertex at a snapped point, the snap kind +
source item describe an *intent* that should usually outlive the click
— e.g. "I want this vertex to stay on that edge", "I want this edge to
remain perpendicular to that one". This module turns that intent into a
real constraint stored in the project's `ConstraintGraph`.

Coverage today (PR #191 manual-test follow-up):

| Snap kind     | Source item          | Emits                      |
| ------------- | -------------------- | -------------------------- |
| NEAREST       | line-like outline    | POINT_ON_EDGE              |
| NEAREST       | circle / arc         | POINT_ON_CIRCLE            |
| PERPENDICULAR | line-like edge       | PERPENDICULAR (item-level) |
| TANGENT       | circle / arc         | *no-op* — see follow-up    |

The TANGENT case is intentionally a no-op: `ConstraintType.TANGENT`
does not exist yet and the constraint solver has no tangent math. A
follow-up US (US-B8 in the roadmap) adds the constraint type, Jacobian,
and UI before this entry can be filled in.

Drawing tools call `emit_for_polyline(view, item, snap_contexts)` (or
the equivalent for their own item kind) immediately after creating the
final item; constraints land in the project graph as a side effect.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

    from open_garden_planner.core.snap.provider import SnapCandidate
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


def emit_for_polyline(
    view: CanvasView,
    polyline_item: QGraphicsItem,
    snap_contexts: list[SnapCandidate | None],
) -> int:
    """Emit auto-constraints for each snapped vertex of a freshly placed polyline.

    Returns the number of constraints actually added (TANGENT and
    unrecognised kinds are skipped silently).
    """
    from open_garden_planner.core.constraints import (
        AnchorRef,
        ConstraintType,
    )
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.core.snap.provider import SnapCandidateKind

    graph = _constraint_graph(view)
    if graph is None or not snap_contexts:
        return 0

    polyline_id = getattr(polyline_item, "item_id", None)
    if polyline_id is None:
        return 0

    added = 0
    for vertex_idx, snap in enumerate(snap_contexts):
        if snap is None or snap.item is None:
            continue
        source_id = getattr(snap.item, "item_id", None)
        if source_id is None or source_id == polyline_id:
            continue

        vertex_anchor = AnchorRef(
            item_id=polyline_id,
            anchor_type=AnchorType.ENDPOINT,
            anchor_index=vertex_idx,
        )

        if snap.kind == SnapCandidateKind.NEAREST:
            ctype, source_anchor = _nearest_constraint_for(snap.item, source_id)
            if ctype is None or source_anchor is None:
                continue
            graph.add_constraint(
                vertex_anchor,
                source_anchor,
                target_distance=0.0,
                constraint_type=ctype,
            )
            added += 1
        elif snap.kind == SnapCandidateKind.PERPENDICULAR:
            # Item-level perpendicular: keep the polyline's edge ending
            # at `vertex_idx` perpendicular to the source item's edge
            # nearest to the snap point. Encoded with the polyline as
            # anchor_a (any vertex on its endpoint anchor — the solver
            # treats this as item-level), source as anchor_b.
            source_anchor = AnchorRef(
                item_id=source_id,
                anchor_type=AnchorType.CENTER,
                anchor_index=0,
            )
            graph.add_constraint(
                vertex_anchor,
                source_anchor,
                target_distance=90.0,
                constraint_type=ConstraintType.PERPENDICULAR,
            )
            added += 1
        # TANGENT: deliberate no-op — see module docstring.

    return added


def _nearest_constraint_for(
    source_item: object, source_id: object
) -> tuple[object, object] | tuple[None, None]:
    """Pick POINT_ON_EDGE vs POINT_ON_CIRCLE based on the source item kind."""
    from open_garden_planner.core.constraints import (
        AnchorRef,
        ConstraintType,
    )
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.ui.canvas.items import (
        ArcItem,
        CircleItem,
        EllipseItem,
        PolygonItem,
        PolylineItem,
        RectangleItem,
    )

    if isinstance(source_item, (CircleItem, EllipseItem, ArcItem)):
        return ConstraintType.POINT_ON_CIRCLE, AnchorRef(
            item_id=source_id,
            anchor_type=AnchorType.CENTER,
            anchor_index=0,
        )
    if isinstance(source_item, (PolygonItem, PolylineItem, RectangleItem)):
        return ConstraintType.POINT_ON_EDGE, AnchorRef(
            item_id=source_id,
            anchor_type=AnchorType.CENTER,
            anchor_index=0,
        )
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
