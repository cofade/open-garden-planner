"""DragConstraints: one responsibility extracted from CanvasView."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.core import (
    AddConstraintCommand,
)

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

_log = logging.getLogger(__name__)


class DragConstraints:
    """Uses the original host for state, translation context and command ownership."""

    def __init__(self, host: CanvasView) -> None:
        self._host = host

    def _enforce_fixed_positions(self) -> None:
        """Revert any FIXED-constrained items to their pinned (target) position.

        Called immediately after super().mouseMoveEvent() so that Qt's own drag
        logic cannot move items that have a FIXED constraint.
        """
        host = self._host
        if not host._drag_start_positions:
            return

        from open_garden_planner.core.constraints import ConstraintType
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        graph = host._canvas_scene.constraint_graph
        for c in graph.constraints.values():
            if c.constraint_type != ConstraintType.FIXED:
                continue
            if c.target_x is None or c.target_y is None:
                continue
            item_id = c.anchor_a.item_id
            for scene_item in cast("CanvasScene", host.scene()).items():
                if (
                    isinstance(scene_item, GardenItemMixin)
                    and scene_item.item_id == item_id
                ):
                    from PyQt6.QtCore import QPointF as _QPointF

                    scene_item.setPos(_QPointF(c.target_x, c.target_y))
                    break


    def _enforce_point_on_edge_positions(self) -> None:
        """Project POINT_ON_EDGE-constrained anchors back onto their edge during drag.

        Called immediately after _enforce_fixed_positions so that Qt's drag
        cannot pull an anchor off its constrained edge line.  The anchor slides
        freely along the edge but its perpendicular displacement is zeroed out.
        """
        host = self._host
        if not host._drag_start_positions:
            return

        from open_garden_planner.core.constraints import ConstraintType
        from open_garden_planner.core.measure_snapper import get_anchor_points
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        graph = host._canvas_scene.constraint_graph

        import math as _math

        for c in graph.constraints.values():
            if c.constraint_type not in (
                ConstraintType.POINT_ON_EDGE,
                ConstraintType.POINT_ON_CIRCLE,
            ):
                continue

            # Only enforce when anchor_a's item is being dragged
            item_a = None
            for scene_item in cast("CanvasScene", host.scene()).items():
                if (
                    isinstance(scene_item, GardenItemMixin)
                    and scene_item.item_id == c.anchor_a.item_id
                ):
                    item_a = scene_item
                    break
            if item_a is None or item_a not in host._drag_start_positions:
                continue

            # Get anchor_a's current scene position (post-drag)
            anchor_a_scene = None
            for anchor in get_anchor_points(item_a):
                if (
                    anchor.anchor_type == c.anchor_a.anchor_type
                    and anchor.anchor_index == c.anchor_a.anchor_index
                ):
                    anchor_a_scene = anchor.point
                    break
            if anchor_a_scene is None:
                continue

            # Get item_b (the edge/circle owner)
            item_b = None
            for scene_item in cast("CanvasScene", host.scene()).items():
                if (
                    isinstance(scene_item, GardenItemMixin)
                    and scene_item.item_id == c.anchor_b.item_id
                ):
                    item_b = scene_item
                    break
            if item_b is None:
                continue

            # Resolve anchor_b position (always needed)
            pos_b = None
            for anchor in get_anchor_points(item_b):
                if (
                    anchor.anchor_type == c.anchor_b.anchor_type
                    and anchor.anchor_index == c.anchor_b.anchor_index
                ):
                    pos_b = anchor.point
                    break
            if pos_b is None:
                continue

            if c.constraint_type == ConstraintType.POINT_ON_CIRCLE:
                # Project anchor_a radially onto circle centred at pos_b with radius = target_distance
                radius = c.target_distance
                adx = anchor_a_scene.x() - pos_b.x()
                ady = anchor_a_scene.y() - pos_b.y()
                a_dist = _math.sqrt(adx * adx + ady * ady)
                if a_dist < 1e-9:
                    proj_x, proj_y = pos_b.x() + radius, pos_b.y()
                else:
                    proj_x = pos_b.x() + (adx / a_dist) * radius
                    proj_y = pos_b.y() + (ady / a_dist) * radius
            else:
                # POINT_ON_EDGE: project onto infinite line through pos_b → pos_c
                if c.anchor_c is None:
                    continue
                pos_c = None
                for anchor in get_anchor_points(item_b):
                    if (
                        anchor.anchor_type == c.anchor_c.anchor_type
                        and anchor.anchor_index == c.anchor_c.anchor_index
                    ):
                        pos_c = anchor.point
                        break
                if pos_c is None:
                    continue
                edx = pos_c.x() - pos_b.x()
                edy = pos_c.y() - pos_b.y()
                line_len_sq = edx * edx + edy * edy
                if line_len_sq < 1e-12:
                    continue
                t = (
                    (anchor_a_scene.x() - pos_b.x()) * edx
                    + (anchor_a_scene.y() - pos_b.y()) * edy
                ) / line_len_sq
                proj_x = pos_b.x() + t * edx
                proj_y = pos_b.y() + t * edy

            # Reposition item_a so its constrained anchor lands exactly on the projection
            local_x = anchor_a_scene.x() - item_a.pos().x()
            local_y = anchor_a_scene.y() - item_a.pos().y()
            item_a.setPos(QPointF(proj_x - local_x, proj_y - local_y))


    def _compute_constraint_propagation(
        self,
        moved_items: list[QGraphicsItem],
        delta: QPointF,
    ) -> list[tuple[QGraphicsItem, QPointF]]:
        """Compute constraint propagation deltas for non-selected items.

        Simulates moving the given items by delta, runs the constraint solver,
        and returns per-item deltas for connected (non-moved) items.

        Args:
            moved_items: Items being moved by the user.
            delta: The movement applied to moved items.

        Returns:
            List of (item, delta) tuples for constraint-propagated items.
            Empty list if no propagation needed.
        """
        host = self._host
        from open_garden_planner.core.measure_snapper import get_anchor_points
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        graph = host._canvas_scene.constraint_graph

        dragged_ids: set[Any] = set()
        for item in moved_items:
            if isinstance(item, GardenItemMixin):
                dragged_ids.add(item.item_id)

        if not dragged_ids:
            return []

        connected_ids: set[Any] = set()
        for did in dragged_ids:
            connected_ids.update(graph.get_connected_component(did))

        propagated_ids = connected_ids - dragged_ids
        if not propagated_ids:
            return []

        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        # Build item lookup (garden items + construction items in connected component)
        item_map: dict[Any, Any] = {}
        construction_ids: set[Any] = set()
        for item in cast("CanvasScene", host.scene()).items():
            if isinstance(item, GardenItemMixin) and item.item_id in connected_ids:
                item_map[item.item_id] = item
            elif (
                isinstance(item, (ConstructionLineItem, ConstructionCircleItem))
                and item.item_id in connected_ids
            ):
                item_map[item.item_id] = item
                construction_ids.add(item.item_id)

        # Build positions (with delta applied to moved items)
        item_positions: dict[Any, Any] = {}
        anchor_offsets: dict[Any, Any] = {}

        for uid, gitem in item_map.items():
            pos = gitem.pos()
            if uid in dragged_ids:
                item_positions[uid] = (pos.x() + delta.x(), pos.y() + delta.y())
            else:
                item_positions[uid] = (pos.x(), pos.y())

            anchors = get_anchor_points(gitem)
            for anchor in anchors:
                key = (uid, anchor.anchor_type, anchor.anchor_index)
                anchor_offsets[key] = (
                    anchor.point.x() - pos.x(),
                    anchor.point.y() - pos.y(),
                )

        deformable_items, deformable_vertices = host._gather_deformable_info(item_map)

        # Construction items are always pinned (they are fixed guides)
        result = graph.solve_anchored(
            item_positions=item_positions,
            anchor_offsets=anchor_offsets,
            pinned_items=dragged_ids | construction_ids,
            max_iterations=20,
            tolerance=1.0,
            deformable_items=deformable_items,
            deformable_vertices=deformable_vertices,
        )

        propagated_deltas: list[tuple[QGraphicsItem, QPointF]] = []
        for uid, (pdx, pdy) in result.item_deltas.items():
            if uid in construction_ids:
                continue
            gitem = item_map.get(uid)
            if gitem is not None:
                propagated_deltas.append((gitem, QPointF(pdx, pdy)))

        return propagated_deltas


    def _propagate_constraints_during_drag(self) -> None:
        """Run the constraint solver to propagate drag to connected items.

        Called during mouseMoveEvent after the dragged items have been
        repositioned by Qt. Pins the dragged items and moves connected
        items to satisfy distance constraints.
        """
        host = self._host
        if not host._drag_start_positions:
            return

        graph = host._canvas_scene.constraint_graph
        if not graph.constraints:
            return

        from open_garden_planner.core.measure_snapper import get_anchor_points
        from open_garden_planner.ui.canvas.items import GardenItemMixin
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        selected = cast("CanvasScene", host.scene()).selectedItems()
        if not selected:
            return

        # Collect item IDs of dragged items (garden + construction)
        dragged_ids: set[Any] = set()
        for item in selected:
            if isinstance(
                item, (GardenItemMixin, ConstructionLineItem, ConstructionCircleItem)
            ):
                dragged_ids.add(item.item_id)

        if not dragged_ids:
            return

        # Find all items in connected components of dragged items
        connected_ids: set[Any] = set()
        for did in dragged_ids:
            connected_ids.update(graph.get_connected_component(did))

        # Identify all construction items in scene (needed for soft_dragged logic below)
        scene_construction_ids: set[Any] = set()
        for scene_item in cast("CanvasScene", host.scene()).items():
            if isinstance(scene_item, (ConstructionLineItem, ConstructionCircleItem)):
                scene_construction_ids.add(scene_item.item_id)

        # Collect FIXED item IDs — they act as pinned anchors just like construction items
        from open_garden_planner.core.constraints import ConstraintType

        fixed_ids: set[Any] = {
            c.anchor_a.item_id
            for c in graph.constraints.values()
            if c.constraint_type == ConstraintType.FIXED
        }
        # Items that are always pinned (construction geometry + FIXED items)
        pinned_reference_ids = scene_construction_ids | fixed_ids

        # "Soft-dragged": dragged garden items whose ALL constraints are exclusively
        # to pinned reference items (construction or FIXED). These are NOT pinned in
        # the solver — the solver enforces the constraint by snapping them to the
        # correct position each frame (the cursor acts as a "desired" position, not a
        # hard pin). This makes constraints bidirectional and lets items orbit around
        # fixed partners.
        soft_dragged: set[Any] = set()
        for uid in dragged_ids:
            if uid in scene_construction_ids:
                continue  # Construction items are always hard-pinned
            item_constraints = graph.get_item_constraints(uid)
            if not item_constraints:
                continue
            if all(
                (
                    c.anchor_a.item_id
                    if c.anchor_b.item_id == uid
                    else c.anchor_b.item_id
                )
                in pinned_reference_ids
                for c in item_constraints
            ):
                soft_dragged.add(uid)

        # truly_dragged: follow the cursor and pull their constraint partners
        truly_dragged = dragged_ids - soft_dragged

        # propagated_ids: items the solver may move (soft_dragged included)
        propagated_ids = connected_ids - truly_dragged
        if not propagated_ids:
            return

        # Build item lookup by UUID (garden + construction items)
        item_map: dict[Any, Any] = {}
        construction_ids: set[Any] = set()
        for item in cast("CanvasScene", host.scene()).items():
            if isinstance(item, GardenItemMixin) and item.item_id in connected_ids:
                item_map[item.item_id] = item
                if item.item_id in fixed_ids:
                    # FIXED garden items are treated as pinned anchors like construction items
                    construction_ids.add(item.item_id)
            elif (
                isinstance(item, (ConstructionLineItem, ConstructionCircleItem))
                and item.item_id in connected_ids
            ):
                item_map[item.item_id] = item
                construction_ids.add(item.item_id)

        # Record start positions of propagated garden items (only once per drag).
        # soft_dragged items are excluded — their "start" is the cursor position
        # (reset by Qt each frame), so recording a stale start would be wrong.
        for uid in propagated_ids:
            if uid in soft_dragged:
                continue
            gitem = item_map.get(uid)
            if gitem and gitem not in host._constraint_propagated_starts:
                host._constraint_propagated_starts[gitem] = gitem.pos()

        # Items participating in a TANGENT constraint must NOT be reverted to
        # their drag-start position each frame: tangency to a circle has two
        # solutions (one per side), so the solver needs the *previous frame's*
        # position as a warm start to track continuously. Reverting to the
        # original drawn position makes a large circle drag re-project the
        # contact onto the wrong side, flipping the line through the centre and
        # trapping it on the opposite tangent. Other constraint types have no
        # such ambiguity, so they keep the clean-delta revert.
        tangent_item_ids: set[Any] = set()
        for c in graph.constraints.values():
            if c.constraint_type == ConstraintType.TANGENT:
                tangent_item_ids.add(c.anchor_a.item_id)
                tangent_item_ids.add(c.anchor_b.item_id)
                if c.anchor_c is not None:
                    tangent_item_ids.add(c.anchor_c.item_id)

        # Revert non-soft propagated garden items to start positions so the solver
        # computes deltas from a clean state each frame
        for gitem, start_pos in host._constraint_propagated_starts.items():
            if (
                isinstance(gitem, GardenItemMixin)
                and gitem.item_id in propagated_ids
                and gitem.item_id not in soft_dragged
                and gitem.item_id not in tangent_item_ids
            ):
                gitem.setPos(start_pos)

        # Build item positions and anchor offsets
        item_positions: dict[Any, Any] = {}
        anchor_offsets: dict[Any, Any] = {}

        for uid, gitem in item_map.items():
            pos = gitem.pos()
            item_positions[uid] = (pos.x(), pos.y())

            anchors = get_anchor_points(gitem)
            for anchor in anchors:
                key = (uid, anchor.anchor_type, anchor.anchor_index)
                anchor_offsets[key] = (
                    anchor.point.x() - pos.x(),
                    anchor.point.y() - pos.y(),
                )

        deformable_items, deformable_vertices = host._gather_deformable_info(item_map)

        # Run solver: truly_dragged and construction items are pinned.
        # soft_dragged items are FREE so the solver enforces construction constraints.
        result = graph.solve_anchored(
            item_positions=item_positions,
            anchor_offsets=anchor_offsets,
            pinned_items=truly_dragged | construction_ids,
            max_iterations=20,
            tolerance=1.0,
            deformable_items=deformable_items,
            deformable_vertices=deformable_vertices,
        )

        # Apply deltas (skip construction items — always pinned)
        for uid, (dx, dy) in result.item_deltas.items():
            if uid in construction_ids:
                continue
            gitem = item_map.get(uid)
            if gitem is not None:
                gitem.moveBy(dx, dy)

        # Apply vertex deltas for deformable items
        for (uid, vi), (vdx, vdy) in result.vertex_deltas.items():
            if uid in construction_ids:
                continue
            gitem = item_map.get(uid)
            if gitem is None or not hasattr(gitem, "_move_vertex_to"):
                continue
            old_local = host._get_vertex_local(gitem, vi)
            if old_local is None:
                continue
            old_scene = gitem.mapToScene(old_local)
            new_scene = QPointF(old_scene.x() + vdx, old_scene.y() + vdy)
            new_local = gitem.mapFromScene(new_scene)
            gitem._move_vertex_to(vi, new_local)


    def _enforce_after_vertex_drag(self) -> None:
        """Re-enforce constraints after a polygon vertex drag.

        Runs the ANGLE constraint solver and re-aligns any intra-object PARALLEL
        constraints, then bundles everything (original drag + all corrections) into
        a single MultiVertexMoveCommand so Ctrl+Z reverts in one step.
        """
        host = self._host
        from PyQt6.QtCore import QPointF

        from open_garden_planner.core.commands import MultiVertexMoveCommand

        deferred = getattr(host, '_deferred_vertex_move', None)
        if deferred is None:
            return
        host._deferred_vertex_move = None

        item, vertex_index, old_pos, new_pos = deferred

        # Snapshot ALL current vertex positions (post-drag, pre-correction).
        # Works for both PolygonItem (polygon().at(i)) and PolylineItem (._points).
        snapshots: dict[int, QPointF] = {
            i: QPointF(p) for i, p in enumerate(host._iter_item_vertices(item))
        }

        # Run the solver. We deliberately do NOT pin the moving item: for a
        # deformable item the solver only varies its per-vertex DOFs (no
        # item-translation DOF), and vertex_corrections is the channel that
        # rebalances neighbour vertices to satisfy the constraint the drag
        # just disturbed. _item_moves is intentionally discarded for the
        # moving item below.
        _item_moves, vertex_corrections = host._compute_constraint_solve_moves()
        for gitem, idx, _old_local, new_local in vertex_corrections:
            if hasattr(gitem, '_move_vertex_to'):
                gitem._move_vertex_to(idx, new_local)

        # Re-enforce intra-object PARALLEL constraints.
        host._reenforce_parallel_after_vertex_move(item, vertex_index)

        # Collect ALL vertex changes (original drag + solver + PARALLEL re-alignment).
        all_moves: list[Any] = [(item, vertex_index, old_pos, new_pos)]
        for i, new_v in enumerate(host._iter_item_vertices(item)):
            if i == vertex_index:
                continue
            old_v = snapshots.get(i)
            if old_v is not None and (
                abs(new_v.x() - old_v.x()) > 0.01 or abs(new_v.y() - old_v.y()) > 0.01
            ):
                all_moves.append((item, i, old_v, QPointF(new_v)))

        cmd = MultiVertexMoveCommand(all_moves)
        host.command_manager.register_applied(cmd)

        host._canvas_scene.update_dimension_lines()


    def _reenforce_parallel_after_vertex_move(self, item: Any, vertex_index: int) -> None:  # noqa: ARG002
        """Re-align the target edge of every intra-object PARALLEL constraint on *item*."""
        host = self._host
        import math as _m

        from PyQt6.QtCore import QPointF

        from open_garden_planner.core.constraints import ConstraintType

        uid = getattr(item, 'item_id', None)
        if uid is None or not (hasattr(item, 'polygon') and callable(item.polygon)):
            return

        graph = host._canvas_scene.constraint_graph
        pg = item.polygon()
        n = pg.count()
        if n < 4:
            return

        def _scene(i: int) -> QPointF:
            return cast(QPointF, item.mapToScene(pg.at(i)))

        for cid in list(graph._adjacency.get(uid, set())):
            c = graph._constraints.get(cid)
            if c is None or c.constraint_type != ConstraintType.PARALLEL:
                continue
            if c.anchor_a.item_id != uid or c.anchor_b.item_id != uid:
                continue  # inter-object — skip

            i_a = c.anchor_a.anchor_index  # reference edge start vertex
            i_b = c.anchor_b.anchor_index  # target edge start vertex

            p_a1, p_a2 = _scene(i_a), _scene((i_a + 1) % n)
            p_b1, p_b2 = _scene(i_b), _scene((i_b + 1) % n)

            da_x = p_a2.x() - p_a1.x()
            da_y = p_a2.y() - p_a1.y()
            db_x = p_b2.x() - p_b1.x()
            db_y = p_b2.y() - p_b1.y()
            if _m.hypot(da_x, da_y) < 1e-9 or _m.hypot(db_x, db_y) < 1e-9:
                continue

            delta = _m.atan2(da_y, da_x) - _m.atan2(db_y, db_x)
            while delta > _m.pi / 2:
                delta -= _m.pi
            while delta <= -_m.pi / 2:
                delta += _m.pi

            if abs(delta) < 1e-6:
                continue

            cos_d, sin_d = _m.cos(delta), _m.sin(delta)
            rel_x = p_b2.x() - p_b1.x()
            rel_y = p_b2.y() - p_b1.y()
            new_b2_scene = QPointF(
                p_b1.x() + cos_d * rel_x - sin_d * rel_y,
                p_b1.y() + sin_d * rel_x + cos_d * rel_y,
            )
            item._move_vertex_to((i_b + 1) % n, item.mapFromScene(new_b2_scene))


    @staticmethod
    def _gather_deformable_info(
        item_map: dict[Any, Any],
    ) -> tuple[set[Any], dict[Any, list[tuple[float, float]]]]:
        """Build deformable_items set and deformable_vertices dict from item_map.

        Returns:
            (deformable_items, deformable_vertices) for items that support
            per-vertex deformation (PolygonItem, PolylineItem).
        """
        from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem

        deformable_items: set[Any] = set()
        deformable_vertices: dict[Any, Any] = {}

        for uid, item in item_map.items():
            if isinstance(item, PolygonItem):
                deformable_items.add(uid)
                polygon = item.polygon()
                verts = []
                for i in range(polygon.count()):
                    sp = item.mapToScene(polygon.at(i))
                    verts.append((sp.x(), sp.y()))
                deformable_vertices[uid] = verts
            elif isinstance(item, PolylineItem):
                deformable_items.add(uid)
                verts = []
                for pt in item.points:
                    sp = item.mapToScene(pt)
                    verts.append((sp.x(), sp.y()))
                deformable_vertices[uid] = verts

        return deformable_items, deformable_vertices


    def _compute_edge_length_constraint_moves(
        self, command: AddConstraintCommand
    ) -> tuple[list[tuple[QGraphicsItem, QPointF, QPointF]], list[tuple[QGraphicsItem, int, QPointF, QPointF]]]:
        """Compute direct endpoint movement for a newly created edge-length constraint."""
        host = self._host
        from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem

        scene = cast("CanvasScene", host.scene())
        anchor_a = command._anchor_a
        anchor_b = command._anchor_b
        target_distance = command._target_distance

        item = next(
            (
                candidate
                for candidate in scene.items()
                if hasattr(candidate, "item_id")
                and candidate.item_id == anchor_a.item_id
            ),
            None,
        )
        if item is None:
            return [], []

        if isinstance(item, PolygonItem):
            polygon = item.polygon()
            if not (0 <= anchor_a.anchor_index < polygon.count()):
                return [], []
            if not (0 <= anchor_b.anchor_index < polygon.count()):
                return [], []
        elif isinstance(item, PolylineItem):
            points = item.points
            if not (0 <= anchor_a.anchor_index < len(points)):
                return [], []
            if not (0 <= anchor_b.anchor_index < len(points)):
                return [], []
        else:
            return host._compute_constraint_solve_moves(extra_pinned={anchor_b.item_id})

        old_local = host._get_vertex_local(item, anchor_a.anchor_index)
        ref_local = host._get_vertex_local(item, anchor_b.anchor_index)
        if old_local is None or ref_local is None:
            return [], []

        old_scene = item.mapToScene(old_local)
        ref_scene = item.mapToScene(ref_local)
        dx = old_scene.x() - ref_scene.x()
        dy = old_scene.y() - ref_scene.y()
        current_dist = (dx * dx + dy * dy) ** 0.5
        if current_dist < 1e-9:
            direction = QPointF(1.0, 0.0)
        else:
            direction = QPointF(dx / current_dist, dy / current_dist)

        new_scene = QPointF(
            ref_scene.x() + direction.x() * target_distance,
            ref_scene.y() + direction.y() * target_distance,
        )
        new_local = item.mapFromScene(new_scene)

        # Direct single-endpoint move. If the moved vertex participates in any
        # OTHER constraint, the direct move will violate it — run the hybrid
        # solver to propagate. Apply the move, solve, then collect the final
        # deltas before restoring the pre-move state (the caller re-applies via
        # the command).
        moved_vertex_idx = anchor_a.anchor_index
        has_other_touching = any(
            c
            for c in host._canvas_scene.constraint_graph.constraints.values()
            if (
                c.anchor_a.item_id == anchor_a.item_id
                and c.anchor_a.anchor_index == moved_vertex_idx
            )
            or (
                c.anchor_b.item_id == anchor_a.item_id
                and c.anchor_b.anchor_index == moved_vertex_idx
            )
        )
        if not has_other_touching or len(host._canvas_scene.constraint_graph.constraints) <= 1:
            return [], [(item, moved_vertex_idx, QPointF(old_local), new_local)]

        # Apply the direct move temporarily, solve, capture final vertex positions.
        original_polygon = None
        original_points = None
        if isinstance(item, PolygonItem):
            from PyQt6.QtGui import QPolygonF
            original_polygon = QPolygonF(item.polygon())
            item._move_vertex_to(moved_vertex_idx, new_local)
        elif isinstance(item, PolylineItem):
            original_points = list(item.points)
            item._move_vertex_to(moved_vertex_idx, new_local)

        try:
            # For intra-object self-constraints (common on polygon edges), pinning
            # anchor_b would pin the entire polygon, making vertex moves impossible.
            # Only pin the reference when it is a *different* item.
            intra_object = anchor_a.item_id == anchor_b.item_id
            extra_pinned = None if intra_object else {anchor_b.item_id}
            _item_moves, vertex_moves = host._compute_constraint_solve_moves(
                extra_pinned=extra_pinned
            )
        finally:
            if original_polygon is not None and isinstance(item, PolygonItem):
                item.setPolygon(original_polygon)
                # The polyline branch below restores through `_move_vertex_to`,
                # which re-derives a ROOF_RIDGE (ADR-046); a bare `setPolygon`
                # does not, so a HOUSE whose solve raised would keep a ridge
                # computed for the temporary trial geometry. Restoring the
                # polygon must restore the derived ridge with it.
                item._update_ridge_on_boundary()
            elif original_points is not None and isinstance(item, PolylineItem):
                for i, pt in enumerate(original_points):
                    item._move_vertex_to(i, pt)

        # Merge the primary endpoint move with any solver-produced vertex moves.
        # Solver vertex_moves are tuples (item, idx, old_local, new_local).
        final_vertex_moves: list[Any] = []
        moved_indices: set[Any] = set()
        for m_item, m_idx, m_old_local, m_new_local in vertex_moves:
            if m_item is item and m_idx == moved_vertex_idx:
                # Use the solver's result for the primary vertex too.
                final_vertex_moves.append(
                    (item, moved_vertex_idx, QPointF(old_local), m_new_local)
                )
                moved_indices.add(moved_vertex_idx)
            else:
                final_vertex_moves.append(
                    (m_item, m_idx, m_old_local, m_new_local)
                )
                if m_item is item:
                    moved_indices.add(m_idx)
        if moved_vertex_idx not in moved_indices:
            final_vertex_moves.append(
                (item, moved_vertex_idx, QPointF(old_local), new_local)
            )
        return [], final_vertex_moves


    def _compute_constraint_solve_moves(
        self,
        extra_pinned: set[Any] | None = None,
    ) -> tuple[list[tuple[QGraphicsItem, QPointF, QPointF]], list[tuple[QGraphicsItem, int, QPointF, QPointF]]]:
        """Run the constraint solver and return position changes.

        Should be called while the constraint graph already has the desired
        target distances set.  Returns a list of (item, old_pos, new_pos) for
        every item that would move by more than 0.01 cm.

        Args:
            extra_pinned: Additional item IDs to treat as pinned (immovable)
                during this solve pass, beyond the always-pinned construction
                items.  Used to implement the CAD convention that item B (the
                reference anchor) stays fixed while item A moves to satisfy the
                new constraint.
        """
        host = self._host
        from open_garden_planner.core.measure_snapper import get_anchor_points
        from open_garden_planner.ui.canvas.items import GardenItemMixin
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        graph = host._canvas_scene.constraint_graph
        if not graph.constraints:
            return [], []

        constrained_ids: set[Any] = set()
        for c in graph.constraints.values():
            constrained_ids.add(c.anchor_a.item_id)
            constrained_ids.add(c.anchor_b.item_id)
            if c.anchor_c is not None:
                constrained_ids.add(c.anchor_c.item_id)

        item_map: dict[Any, Any] = {}
        item_positions: dict[Any, Any] = {}
        anchor_offsets: dict[Any, Any] = {}
        construction_ids: set[Any] = set()

        for item in cast("CanvasScene", host.scene()).items():
            is_garden = isinstance(item, GardenItemMixin)
            is_construction = isinstance(
                item, (ConstructionLineItem, ConstructionCircleItem)
            )
            if (is_garden or is_construction) and cast(Any, item).item_id in constrained_ids:
                uid = cast(Any, item).item_id
                item_map[uid] = item
                pos = item.pos()
                item_positions[uid] = (pos.x(), pos.y())
                for anchor in get_anchor_points(item):
                    key = (uid, anchor.anchor_type, anchor.anchor_index)
                    anchor_offsets[key] = (
                        anchor.point.x() - pos.x(),
                        anchor.point.y() - pos.y(),
                    )
                if is_construction:
                    construction_ids.add(uid)

        if not item_positions:
            return [], []

        deformable_items, deformable_vertices = host._gather_deformable_info(item_map)

        # Construction items are always pinned — only garden items move.
        # extra_pinned allows callers to additionally pin a reference item so
        # that only the other item moves (CAD convention: A moves, B stays).
        result = graph.solve_anchored(
            item_positions=item_positions,
            anchor_offsets=anchor_offsets,
            pinned_items=construction_ids | (extra_pinned or set()),
            max_iterations=20,
            tolerance=1.0,
            deformable_items=deformable_items,
            deformable_vertices=deformable_vertices,
        )

        moves: list[Any] = []
        for uid, (pdx, pdy) in result.item_deltas.items():
            if uid in construction_ids:
                continue
            gitem = item_map.get(uid)
            if gitem is not None and (abs(pdx) > 0.01 or abs(pdy) > 0.01):
                old_pos = gitem.pos()
                moves.append(
                    (gitem, old_pos, QPointF(old_pos.x() + pdx, old_pos.y() + pdy))
                )

        vertex_moves: list[Any] = []
        for (uid, vi), (vdx, vdy) in result.vertex_deltas.items():
            if uid in construction_ids:
                continue
            gitem = item_map.get(uid)
            if gitem is None:
                continue
            if abs(vdx) < 0.01 and abs(vdy) < 0.01:
                continue
            # Get current vertex in item-local coords
            old_local = host._get_vertex_local(gitem, vi)
            if old_local is None:
                continue
            # Compute new local pos: map scene delta to local coords
            old_scene = gitem.mapToScene(old_local)
            new_scene = QPointF(old_scene.x() + vdx, old_scene.y() + vdy)
            new_local = gitem.mapFromScene(new_scene)
            vertex_moves.append((gitem, vi, QPointF(old_local), new_local))

        return moves, vertex_moves


