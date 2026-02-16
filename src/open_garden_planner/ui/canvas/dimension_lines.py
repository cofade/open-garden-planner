"""Dimension line visualization for distance constraints.

FreeCAD-style dimension annotations with witness lines, arrowheads,
and distance text that update in real-time as objects move.
"""

from __future__ import annotations

import math
from uuid import UUID

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from open_garden_planner.core.constraints import Constraint, ConstraintGraph
from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
from open_garden_planner.ui.canvas.items import GardenItemMixin

# Colors
COLOR_SATISFIED = QColor(0, 120, 200)  # Blue
COLOR_VIOLATED = QColor(220, 40, 40)  # Red

# Geometry constants
WITNESS_LINE_OFFSET = 15.0  # Perpendicular offset from dimension line (in cm)
WITNESS_LINE_GAP = 3.0  # Gap between anchor and start of witness line
WITNESS_LINE_EXTEND = 5.0  # Extension beyond dimension line
ARROW_LENGTH = 8.0  # Arrow head length in cm
ARROW_WIDTH = 3.5  # Arrow head half-width in cm
DIMENSION_LINE_Z = 900  # Z-value for dimension lines (below handles)


class DimensionLineGroup:
    """Visual representation of a single distance constraint.

    Contains witness lines, dimension line, arrowheads, and distance text.
    """

    def __init__(self, constraint_id: UUID) -> None:
        self.constraint_id = constraint_id
        self.items: list[QGraphicsItem] = []

    def remove_from_scene(self, scene: QGraphicsScene) -> None:
        """Remove all graphics items from the scene."""
        for item in self.items:
            if item.scene() is scene:
                scene.removeItem(item)
        self.items.clear()


class DimensionLineManager:
    """Manages dimension line graphics for all constraints in a scene.

    Creates, updates, and removes FreeCAD-style dimension annotations
    that visualize distance constraints between objects.
    """

    def __init__(self, scene: QGraphicsScene) -> None:
        self._scene = scene
        self._groups: dict[UUID, DimensionLineGroup] = {}
        self._visible = True

    @property
    def visible(self) -> bool:
        return self._visible

    def set_visible(self, visible: bool) -> None:
        """Show or hide all dimension lines."""
        self._visible = visible
        for group in self._groups.values():
            for item in group.items:
                item.setVisible(visible)
        if visible:
            self.update_all()

    def update_all(self) -> None:
        """Rebuild all dimension lines from the constraint graph."""
        if not hasattr(self._scene, "constraint_graph"):
            return

        graph: ConstraintGraph = self._scene.constraint_graph

        # Remove groups for constraints that no longer exist
        existing_ids = set(graph.constraints.keys())
        stale_ids = set(self._groups.keys()) - existing_ids
        for cid in stale_ids:
            self._remove_group(cid)

        # Update or create groups for current constraints
        for _cid, constraint in graph.constraints.items():
            self._update_constraint(constraint)

    def update_constraint(self, constraint_id: UUID) -> None:
        """Update dimension line for a single constraint."""
        if not hasattr(self._scene, "constraint_graph"):
            return
        graph: ConstraintGraph = self._scene.constraint_graph
        constraint = graph.constraints.get(constraint_id)
        if constraint is None:
            self._remove_group(constraint_id)
        else:
            self._update_constraint(constraint)

    def remove_constraint(self, constraint_id: UUID) -> None:
        """Remove dimension line for a constraint."""
        self._remove_group(constraint_id)

    def clear(self) -> None:
        """Remove all dimension lines."""
        for group in list(self._groups.values()):
            group.remove_from_scene(self._scene)
        self._groups.clear()

    def _remove_group(self, constraint_id: UUID) -> None:
        """Remove a dimension line group."""
        group = self._groups.pop(constraint_id, None)
        if group:
            group.remove_from_scene(self._scene)

    def _update_constraint(self, constraint: Constraint) -> None:
        """Update or create the dimension line for a constraint."""
        # Remove old visuals
        self._remove_group(constraint.constraint_id)

        if not constraint.visible or not self._visible:
            return

        # Resolve anchor positions
        pos_a = self._resolve_anchor_position(
            constraint.anchor_a.item_id, constraint.anchor_a.anchor_type
        )
        pos_b = self._resolve_anchor_position(
            constraint.anchor_b.item_id, constraint.anchor_b.anchor_type
        )
        if pos_a is None or pos_b is None:
            return

        # Calculate constraint status (satisfied vs violated)
        current_dist = QLineF(pos_a, pos_b).length()
        error = abs(current_dist - constraint.target_distance)
        satisfied = error < 1.0  # 1cm tolerance
        color = COLOR_SATISFIED if satisfied else COLOR_VIOLATED

        # Build the dimension line group
        group = DimensionLineGroup(constraint.constraint_id)
        self._build_dimension_line(group, pos_a, pos_b, constraint.target_distance, color)
        self._groups[constraint.constraint_id] = group

    def _resolve_anchor_position(
        self, item_id: UUID, anchor_type: AnchorType
    ) -> QPointF | None:
        """Get the scene position of an anchor on a garden item."""
        for item in self._scene.items():
            if not isinstance(item, GardenItemMixin):
                continue
            if item.item_id != item_id:
                continue
            anchors = get_anchor_points(item)
            for anchor in anchors:
                if anchor.anchor_type == anchor_type:
                    return anchor.point
            # Fallback to center if specific anchor type not found
            for anchor in anchors:
                if anchor.anchor_type == AnchorType.CENTER:
                    return anchor.point
            return None
        return None

    def _build_dimension_line(
        self,
        group: DimensionLineGroup,
        pos_a: QPointF,
        pos_b: QPointF,
        target_distance: float,
        color: QColor,
    ) -> None:
        """Build the full dimension annotation between two points."""
        dx = pos_b.x() - pos_a.x()
        dy = pos_b.y() - pos_a.y()
        length = math.sqrt(dx * dx + dy * dy)

        if length < 1e-6:
            return

        # Direction vector and perpendicular
        nx = dx / length
        ny = dy / length
        px = -ny  # Perpendicular (left side)
        py = nx

        # Offset the dimension line perpendicular to the constraint direction
        offset = WITNESS_LINE_OFFSET
        dim_a = QPointF(pos_a.x() + px * offset, pos_a.y() + py * offset)
        dim_b = QPointF(pos_b.x() + px * offset, pos_b.y() + py * offset)

        pen = QPen(color, 1.5)
        pen.setCosmetic(True)

        witness_pen = QPen(color, 1.0)
        witness_pen.setCosmetic(True)

        # Witness line A: from anchor to beyond dimension line
        w_a_start = QPointF(
            pos_a.x() + px * WITNESS_LINE_GAP,
            pos_a.y() + py * WITNESS_LINE_GAP,
        )
        w_a_end = QPointF(
            pos_a.x() + px * (offset + WITNESS_LINE_EXTEND),
            pos_a.y() + py * (offset + WITNESS_LINE_EXTEND),
        )
        witness_a = self._scene.addLine(QLineF(w_a_start, w_a_end), witness_pen)
        witness_a.setZValue(DIMENSION_LINE_Z)
        group.items.append(witness_a)

        # Witness line B
        w_b_start = QPointF(
            pos_b.x() + px * WITNESS_LINE_GAP,
            pos_b.y() + py * WITNESS_LINE_GAP,
        )
        w_b_end = QPointF(
            pos_b.x() + px * (offset + WITNESS_LINE_EXTEND),
            pos_b.y() + py * (offset + WITNESS_LINE_EXTEND),
        )
        witness_b = self._scene.addLine(QLineF(w_b_start, w_b_end), witness_pen)
        witness_b.setZValue(DIMENSION_LINE_Z)
        group.items.append(witness_b)

        # Main dimension line (between witness lines)
        dim_line = self._scene.addLine(QLineF(dim_a, dim_b), pen)
        dim_line.setZValue(DIMENSION_LINE_Z)
        group.items.append(dim_line)

        # Arrowheads
        self._add_arrowhead(group, dim_a, nx, ny, color)
        self._add_arrowhead(group, dim_b, -nx, -ny, color)

        # Distance text
        dist_m = target_distance / 100.0
        text_str = f"{dist_m:.2f} m"
        text_item = QGraphicsSimpleTextItem(text_str)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(color))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text_item.setZValue(DIMENSION_LINE_Z + 1)

        # Position text at midpoint of dimension line
        mid = QPointF(
            (dim_a.x() + dim_b.x()) / 2,
            (dim_a.y() + dim_b.y()) / 2,
        )
        text_item.setPos(mid)
        self._scene.addItem(text_item)
        group.items.append(text_item)

    def _add_arrowhead(
        self,
        group: DimensionLineGroup,
        tip: QPointF,
        dir_x: float,
        dir_y: float,
        color: QColor,
    ) -> None:
        """Add a triangular arrowhead at the given position."""
        # Perpendicular to direction
        perp_x = -dir_y
        perp_y = dir_x

        base = QPointF(
            tip.x() + dir_x * ARROW_LENGTH,
            tip.y() + dir_y * ARROW_LENGTH,
        )
        left = QPointF(
            base.x() + perp_x * ARROW_WIDTH,
            base.y() + perp_y * ARROW_WIDTH,
        )
        right = QPointF(
            base.x() - perp_x * ARROW_WIDTH,
            base.y() - perp_y * ARROW_WIDTH,
        )

        polygon = QPolygonF([tip, left, right])
        arrow = QGraphicsPolygonItem(polygon)
        arrow.setPen(QPen(Qt.PenStyle.NoPen))
        arrow.setBrush(QBrush(color))
        arrow.setZValue(DIMENSION_LINE_Z)
        self._scene.addItem(arrow)
        group.items.append(arrow)

    def get_constraint_at(self, scene_pos: QPointF, threshold: float = 10.0) -> UUID | None:
        """Find a constraint whose dimension line is near the given position.

        Used for double-click to edit.

        Args:
            scene_pos: Position in scene coordinates.
            threshold: Maximum distance in cm.

        Returns:
            Constraint UUID if found, None otherwise.
        """
        if not hasattr(self._scene, "constraint_graph"):
            return None

        graph: ConstraintGraph = self._scene.constraint_graph
        best_id: UUID | None = None
        best_dist = threshold

        for cid, constraint in graph.constraints.items():
            pos_a = self._resolve_anchor_position(
                constraint.anchor_a.item_id, constraint.anchor_a.anchor_type
            )
            pos_b = self._resolve_anchor_position(
                constraint.anchor_b.item_id, constraint.anchor_b.anchor_type
            )
            if pos_a is None or pos_b is None:
                continue

            # Check distance from point to the dimension line segment
            # (offset perpendicular from anchor line)
            dx = pos_b.x() - pos_a.x()
            dy = pos_b.y() - pos_a.y()
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1e-6:
                continue

            nx = dx / length
            ny = dy / length
            px = -ny
            py = nx
            offset = WITNESS_LINE_OFFSET

            dim_a = QPointF(pos_a.x() + px * offset, pos_a.y() + py * offset)
            dim_b = QPointF(pos_b.x() + px * offset, pos_b.y() + py * offset)

            dist = _point_to_segment_distance(scene_pos, dim_a, dim_b)
            if dist < best_dist:
                best_dist = dist
                best_id = cid

        return best_id


def _point_to_segment_distance(
    point: QPointF, seg_a: QPointF, seg_b: QPointF
) -> float:
    """Calculate minimum distance from a point to a line segment."""
    dx = seg_b.x() - seg_a.x()
    dy = seg_b.y() - seg_a.y()
    length_sq = dx * dx + dy * dy

    if length_sq < 1e-12:
        # Degenerate segment
        ddx = point.x() - seg_a.x()
        ddy = point.y() - seg_a.y()
        return math.sqrt(ddx * ddx + ddy * ddy)

    # Project point onto segment
    t = max(0.0, min(1.0, (
        (point.x() - seg_a.x()) * dx + (point.y() - seg_a.y()) * dy
    ) / length_sq))

    proj_x = seg_a.x() + t * dx
    proj_y = seg_a.y() + t * dy

    ddx = point.x() - proj_x
    ddy = point.y() - proj_y
    return math.sqrt(ddx * ddx + ddy * ddy)
