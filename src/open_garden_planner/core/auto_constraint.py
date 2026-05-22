"""Auto-emit geometric constraints from snap engagements (Phase 13 follow-up).

When a drawing tool commits a vertex at a snapped point, the snap kind +
source item describe an *intent* that should usually outlive the click
— e.g. "I want this vertex to stay on that edge". This module turns
that intent into a real constraint stored in the project's
`ConstraintGraph`.

Coverage today (PR #191 manual-test follow-up):

| Snap kind     | Source item          | Emits                          |
| ------------- | -------------------- | ------------------------------ |
| NEAREST       | line-like outline    | POINT_ON_EDGE                  |
| NEAREST       | circle / arc         | POINT_ON_CIRCLE                |

**Not yet emitted** (each tracked as its own follow-up issue):

- `MIDPOINT` snap → `COINCIDENT` with the midpoint anchor of the source
  item's nearest edge. (Issue #196)
- `PERPENDICULAR` snap → `PERPENDICULAR` constraint between the new
  edge ending at the vertex and the source's nearest edge. Requires
  edge-level identification beyond what AnchorRef currently exposes.
  (Issue #197)
- `TANGENT` snap → new `TANGENT` constraint type + solver math. (Issue
  #192, US-B8)

The earlier draft emitted PERPENDICULAR against the source item's
`CENTER` anchor as a placeholder. Manual testing showed that produced
constraints that referenced the wrong anchor *and* were never enforced
because they bypassed the undo command + dimension-line refresh. It is
removed pending #197.

Drawing tools call `emit_for_polyline(view, item, snap_contexts)` (or
the equivalent for their own item kind) immediately after creating the
final item; constraints land in the project graph via the standard
`AddConstraintCommand` so undo + dimension-line refresh fire.
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

    Returns the number of constraints actually added. Snap kinds that
    aren't yet supported (MIDPOINT, PERPENDICULAR, TANGENT) are skipped
    silently — see module docstring + follow-up issues.
    """
    from open_garden_planner.core.commands import AddConstraintCommand
    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.core.snap.provider import SnapCandidateKind

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
        if snap.kind != SnapCandidateKind.NEAREST:
            # MIDPOINT / PERPENDICULAR / TANGENT: deliberate no-op,
            # tracked in #196 / #197 / #192 — emitting them with the
            # wrong anchor shape produced phantom violated constraints
            # in earlier drafts.
            continue

        ctype, source_anchor = _nearest_constraint_for(snap.item, source_id)
        if ctype is None or source_anchor is None:
            continue

        vertex_anchor = AnchorRef(
            item_id=polyline_id,
            anchor_type=AnchorType.ENDPOINT,
            anchor_index=vertex_idx,
        )
        cmd = AddConstraintCommand(
            graph=graph,
            anchor_a=vertex_anchor,
            anchor_b=source_anchor,
            target_distance=0.0,
            constraint_type=ctype,
        )
        if cmd_manager is not None:
            cmd_manager.execute(cmd)
        else:
            cmd.execute()
        added += 1

    if added > 0 and hasattr(view, "update_dimension_lines"):
        view.update_dimension_lines()
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
