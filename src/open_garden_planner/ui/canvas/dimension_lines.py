"""Dimension line visualization for distance constraints.

FreeCAD-style dimension annotations with witness lines, arrowheads,
and distance text that update in real-time as objects move.
"""

from __future__ import annotations

import math
from uuid import UUID

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from open_garden_planner.core.constraints import Constraint, ConstraintGraph, ConstraintType
from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
from open_garden_planner.ui.canvas.items import GardenItemMixin

# Colors
COLOR_SATISFIED = QColor(0, 120, 200)     # Blue
COLOR_VIOLATED = QColor(220, 40, 40)      # Red
COLOR_ALIGN_SATISFIED = QColor(120, 0, 180)  # Purple for alignment
COLOR_ALIGN_VIOLATED = QColor(220, 40, 40)   # Red (same as distance violated)
COLOR_ANGLE_SATISFIED = QColor(200, 100, 0)  # Orange for angle constraints
COLOR_ANGLE_VIOLATED = QColor(220, 40, 40)   # Red
COLOR_SYMMETRY_SATISFIED = QColor(140, 0, 180)  # Purple for symmetry constraints
COLOR_SYMMETRY_VIOLATED = QColor(220, 40, 40)   # Red
COLOR_COINCIDENT_SATISFIED = QColor(0, 160, 200)  # Teal for coincident constraints
COLOR_COINCIDENT_VIOLATED = QColor(220, 40, 40)   # Red
COLOR_PARALLEL_SATISFIED = QColor(20, 160, 100)       # Green for parallel constraints
COLOR_PARALLEL_VIOLATED = QColor(220, 40, 40)         # Red
COLOR_PERPENDICULAR_SATISFIED = QColor(20, 120, 160)  # Blue-teal for perpendicular constraints
COLOR_PERPENDICULAR_VIOLATED = QColor(220, 40, 40)    # Red
COLOR_EQUAL_SATISFIED = QColor(200, 100, 0)           # Amber for equal-size constraints
COLOR_EQUAL_VIOLATED = QColor(220, 40, 40)            # Red
COLOR_FIXED = QColor(180, 130, 0)                     # Gold for fix-in-place constraints

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
            try:
                if item.scene() is scene:
                    scene.removeItem(item)
            except RuntimeError:
                pass  # C++ object already deleted (e.g. after scene.clear())
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
        """Update or create the visual for a constraint."""
        # Remove old visuals
        self._remove_group(constraint.constraint_id)

        if not constraint.visible or not self._visible:
            return

        # FIXED constraint — single-anchor visual (padlock badge at item center)
        if constraint.constraint_type == ConstraintType.FIXED:
            pos_a = self._resolve_anchor_position(
                constraint.anchor_a.item_id,
                constraint.anchor_a.anchor_type,
                constraint.anchor_a.anchor_index,
            )
            if pos_a is None:
                return
            group = DimensionLineGroup(constraint.constraint_id)
            self._build_fixed_marker(group, pos_a)
            self._groups[constraint.constraint_id] = group
            return

        # Resolve anchor positions
        pos_a = self._resolve_anchor_position(
            constraint.anchor_a.item_id,
            constraint.anchor_a.anchor_type,
            constraint.anchor_a.anchor_index,
        )
        pos_b = self._resolve_anchor_position(
            constraint.anchor_b.item_id,
            constraint.anchor_b.anchor_type,
            constraint.anchor_b.anchor_index,
        )
        if pos_a is None or pos_b is None:
            return

        group = DimensionLineGroup(constraint.constraint_id)

        if constraint.constraint_type == ConstraintType.HORIZONTAL:
            error = abs(pos_b.y() - pos_a.y())
            satisfied = error < 1.0
            color = COLOR_ALIGN_SATISFIED if satisfied else COLOR_ALIGN_VIOLATED
            self._build_alignment_indicator(group, pos_a, pos_b, "H", color)
        elif constraint.constraint_type == ConstraintType.VERTICAL:
            error = abs(pos_b.x() - pos_a.x())
            satisfied = error < 1.0
            color = COLOR_ALIGN_SATISFIED if satisfied else COLOR_ALIGN_VIOLATED
            self._build_alignment_indicator(group, pos_a, pos_b, "V", color)
        elif constraint.constraint_type in (
            ConstraintType.SYMMETRY_HORIZONTAL,
            ConstraintType.SYMMETRY_VERTICAL,
        ):
            axis_is_horizontal = constraint.constraint_type == ConstraintType.SYMMETRY_HORIZONTAL
            axis_val = constraint.target_distance
            if axis_is_horizontal:
                x_error = abs(pos_b.x() - pos_a.x())
                y_error = abs((pos_a.y() + pos_b.y()) / 2.0 - axis_val)
            else:
                y_error = abs(pos_b.y() - pos_a.y())
                x_error = abs((pos_a.x() + pos_b.x()) / 2.0 - axis_val)
            satisfied = x_error < 1.0 and y_error < 1.0
            color = COLOR_SYMMETRY_SATISFIED if satisfied else COLOR_SYMMETRY_VIOLATED
            self._build_symmetry_indicator(
                group, pos_a, pos_b, axis_val, axis_is_horizontal, color
            )
        elif constraint.constraint_type == ConstraintType.COINCIDENT:
            dx = pos_b.x() - pos_a.x()
            dy = pos_b.y() - pos_a.y()
            error = math.sqrt(dx * dx + dy * dy)
            satisfied = error < 0.1  # 1 mm tolerance (0.1 cm)
            color = COLOR_COINCIDENT_SATISFIED if satisfied else COLOR_COINCIDENT_VIOLATED
            # Use midpoint of the two anchors as the marker position
            mid = QPointF((pos_a.x() + pos_b.x()) / 2, (pos_a.y() + pos_b.y()) / 2)
            self._build_coincident_marker(group, pos_a, pos_b, mid, color)
        elif constraint.constraint_type == ConstraintType.PARALLEL:
            # Satisfaction: both edges have the same scene angle (±0.5°)
            alpha_a = self._compute_edge_angle_for_anchor(
                constraint.anchor_a.item_id,
                constraint.anchor_a.anchor_type,
                constraint.anchor_a.anchor_index,
            )
            alpha_b = self._compute_edge_angle_for_anchor(
                constraint.anchor_b.item_id,
                constraint.anchor_b.anchor_type,
                constraint.anchor_b.anchor_index,
            )
            if alpha_a is None or alpha_b is None:
                satisfied = False
            else:
                angle_error = abs((alpha_a - alpha_b + 90.0) % 180.0 - 90.0)
                satisfied = angle_error < 0.5
            color = COLOR_PARALLEL_SATISFIED if satisfied else COLOR_PARALLEL_VIOLATED
            self._build_parallel_marker(group, pos_a, pos_b, color)
        elif constraint.constraint_type == ConstraintType.PERPENDICULAR:
            # Satisfaction: the two edges differ by 90° in scene angle (±0.5°)
            alpha_a = self._compute_edge_angle_for_anchor(
                constraint.anchor_a.item_id,
                constraint.anchor_a.anchor_type,
                constraint.anchor_a.anchor_index,
            )
            alpha_b = self._compute_edge_angle_for_anchor(
                constraint.anchor_b.item_id,
                constraint.anchor_b.anchor_type,
                constraint.anchor_b.anchor_index,
            )
            if alpha_a is None or alpha_b is None:
                satisfied = False
            else:
                diff = abs(alpha_a - alpha_b) % 180.0
                satisfied = abs(diff - 90.0) < 0.5
            color = COLOR_PERPENDICULAR_SATISFIED if satisfied else COLOR_PERPENDICULAR_VIOLATED
            self._build_perpendicular_marker(group, pos_a, pos_b, color)
        elif constraint.constraint_type == ConstraintType.EQUAL:
            # Satisfaction: both anchors have the same dimension (within 1 mm)
            dim_a = self._compute_equal_dim_for_anchor(
                constraint.anchor_a.item_id,
                constraint.anchor_a.anchor_type,
                constraint.anchor_a.anchor_index,
            )
            dim_b = self._compute_equal_dim_for_anchor(
                constraint.anchor_b.item_id,
                constraint.anchor_b.anchor_type,
                constraint.anchor_b.anchor_index,
            )
            satisfied = False if dim_a is None or dim_b is None else abs(dim_a - dim_b) < 1.0
            color = COLOR_EQUAL_SATISFIED if satisfied else COLOR_EQUAL_VIOLATED
            self._build_equal_marker(group, pos_a, pos_b, color)
        elif constraint.constraint_type == ConstraintType.ANGLE:
            # ANGLE constraint: pos_b is the vertex, pos_a and pos_c are the ray endpoints.
            if constraint.anchor_c is None:
                return
            pos_c = self._resolve_anchor_position(
                constraint.anchor_c.item_id,
                constraint.anchor_c.anchor_type,
                constraint.anchor_c.anchor_index,
            )
            if pos_c is None:
                return
            # Compute current angle at vertex (pos_b) between rays to pos_a and pos_c
            ba_x, ba_y = pos_a.x() - pos_b.x(), pos_a.y() - pos_b.y()
            bc_x, bc_y = pos_c.x() - pos_b.x(), pos_c.y() - pos_b.y()
            ba_len = math.sqrt(ba_x * ba_x + ba_y * ba_y)
            bc_len = math.sqrt(bc_x * bc_x + bc_y * bc_y)
            if ba_len < 1e-6 or bc_len < 1e-6:
                return
            cos_val = max(-1.0, min(1.0, (ba_x * bc_x + ba_y * bc_y) / (ba_len * bc_len)))
            current_angle_deg = math.degrees(math.acos(cos_val))
            angle_error = abs(current_angle_deg - constraint.target_distance)
            satisfied = angle_error < 0.5  # 0.5° tolerance
            color = COLOR_ANGLE_SATISFIED if satisfied else COLOR_ANGLE_VIOLATED
            self._build_angle_arc(
                group, pos_a, pos_b, pos_c, constraint.target_distance, color
            )
        else:
            # DISTANCE constraint
            current_dist = QLineF(pos_a, pos_b).length()
            error = abs(current_dist - constraint.target_distance)
            satisfied = error < 1.0  # 1cm tolerance
            color = COLOR_SATISFIED if satisfied else COLOR_VIOLATED
            self._build_dimension_line(group, pos_a, pos_b, constraint.target_distance, color)

        self._groups[constraint.constraint_id] = group

    def _resolve_anchor_position(
        self, item_id: UUID, anchor_type: AnchorType, anchor_index: int = 0
    ) -> QPointF | None:
        """Get the scene position of an anchor on a garden or construction item."""
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        for item in self._scene.items():
            is_garden = isinstance(item, GardenItemMixin)
            is_construction = isinstance(item, (ConstructionLineItem, ConstructionCircleItem))
            if not (is_garden or is_construction):
                continue
            if item.item_id != item_id:
                continue
            anchors = get_anchor_points(item)
            # Match by both type and index to distinguish same-type anchors
            for anchor in anchors:
                if anchor.anchor_type == anchor_type and anchor.anchor_index == anchor_index:
                    return anchor.point
            # Fallback: match by type only (for CENTER and unique types)
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

    def _build_alignment_indicator(
        self,
        group: DimensionLineGroup,
        pos_a: QPointF,
        pos_b: QPointF,
        label: str,
        color: QColor,
    ) -> None:
        """Build a visual indicator for a horizontal or vertical alignment constraint.

        Draws a dashed line between the two anchor positions and a badge
        with the alignment type label (H or V).
        """
        pen = QPen(color, 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)

        line = self._scene.addLine(QLineF(pos_a, pos_b), pen)
        line.setZValue(DIMENSION_LINE_Z)
        group.items.append(line)

        # Small circles at each anchor endpoint
        for pos in (pos_a, pos_b):
            r = 4.0
            ellipse = self._scene.addEllipse(
                QRectF(pos.x() - r, pos.y() - r, r * 2, r * 2),
                QPen(color, 1.5),
                QBrush(color),
            )
            ellipse.setZValue(DIMENSION_LINE_Z)
            group.items.append(ellipse)

        # Label badge at midpoint
        mid = QPointF((pos_a.x() + pos_b.x()) / 2, (pos_a.y() + pos_b.y()) / 2)
        text_item = QGraphicsSimpleTextItem(label)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(color))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text_item.setZValue(DIMENSION_LINE_Z + 1)
        text_item.setPos(mid)
        self._scene.addItem(text_item)
        group.items.append(text_item)

    def _build_coincident_marker(
        self,
        group: DimensionLineGroup,
        pos_a: QPointF,
        pos_b: QPointF,
        marker_pos: QPointF,
        color: QColor,
    ) -> None:
        """Build a visual marker for a coincident constraint.

        Draws a dashed line between the two anchor positions (when not coincident)
        and a filled diamond at the merged point position.
        """
        pen = QPen(color, 1.5)
        pen.setCosmetic(True)

        # Dashed connector line (shows where the anchors came from)
        dx = pos_b.x() - pos_a.x()
        dy = pos_b.y() - pos_a.y()
        if math.sqrt(dx * dx + dy * dy) > 0.5:
            dash_pen = QPen(color, 1.5, Qt.PenStyle.DashLine)
            dash_pen.setCosmetic(True)
            line = self._scene.addLine(QLineF(pos_a, pos_b), dash_pen)
            line.setZValue(DIMENSION_LINE_Z)
            group.items.append(line)

        # Filled diamond at the marker position
        half = 6.0  # half-diagonal of the diamond in scene units (cm)
        diamond = QPolygonF([
            QPointF(marker_pos.x(), marker_pos.y() - half),  # top
            QPointF(marker_pos.x() + half, marker_pos.y()),  # right
            QPointF(marker_pos.x(), marker_pos.y() + half),  # bottom
            QPointF(marker_pos.x() - half, marker_pos.y()),  # left
        ])
        path = QPainterPath()
        path.addPolygon(diamond)
        path.closeSubpath()
        diamond_item = QGraphicsPathItem(path)
        diamond_item.setPen(QPen(color.darker(120), 1))
        diamond_item.setBrush(QBrush(color))
        diamond_item.setZValue(DIMENSION_LINE_Z + 1)
        self._scene.addItem(diamond_item)
        group.items.append(diamond_item)

        # "⦿" label offset from the marker
        text_item = QGraphicsSimpleTextItem("⦿")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(color))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text_item.setZValue(DIMENSION_LINE_Z + 1)
        text_item.setPos(QPointF(marker_pos.x() + half + 2, marker_pos.y() - half))
        self._scene.addItem(text_item)
        group.items.append(text_item)

    def _find_item_by_id(self, item_id: UUID):
        """Return the scene item with the given item_id, or None."""
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        for item in self._scene.items():
            is_garden = isinstance(item, GardenItemMixin)
            is_construction = isinstance(item, (ConstructionLineItem, ConstructionCircleItem))
            if (is_garden or is_construction) and item.item_id == item_id:
                return item
        return None

    def _compute_edge_angle_for_anchor(
        self, item_id: UUID, anchor_type: AnchorType, anchor_index: int
    ) -> float | None:
        """Compute the scene angle [0, 180°) of an edge anchor on the given item.

        Returns the angle in degrees, or None if not computable (wrong item type,
        missing anchor, etc.).
        """
        from open_garden_planner.ui.canvas.items import PolylineItem, RectangleItem
        from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

        item = self._find_item_by_id(item_id)
        if item is None:
            return None

        anchors = get_anchor_points(item)

        if isinstance(item, RectangleItem):
            corner_map = {
                AnchorType.EDGE_TOP:    (0, 1),
                AnchorType.EDGE_BOTTOM: (2, 3),
                AnchorType.EDGE_LEFT:   (0, 2),
                AnchorType.EDGE_RIGHT:  (1, 3),
            }
            if anchor_type not in corner_map:
                return None
            i0, i1 = corner_map[anchor_type]
            corners = {a.anchor_index: a.point for a in anchors if a.anchor_type == AnchorType.CORNER}
            if i0 not in corners or i1 not in corners:
                return None
            p1, p2 = corners[i0], corners[i1]
        elif isinstance(item, PolygonItem):
            polygon = item.polygon()
            n = polygon.count()
            if n < 2:
                return None
            i = anchor_index
            p1 = item.mapToScene(polygon.at(i))
            p2 = item.mapToScene(polygon.at((i + 1) % n))
        elif isinstance(item, PolylineItem):
            pts = item.points
            i = anchor_index
            if i < 0 or i + 1 >= len(pts):
                return None
            p1 = item.mapToScene(pts[i])
            p2 = item.mapToScene(pts[i + 1])
        else:
            return None

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return None
        return math.degrees(math.atan2(dy, dx)) % 180.0

    def _compute_equal_dim_for_anchor(
        self, item_id: UUID, anchor_type: AnchorType, anchor_index: int
    ) -> float | None:
        """Compute the 'size' dimension for an EQUAL constraint anchor on the given item.

        - CircleItem + any EDGE_* → radius
        - RectangleItem + EDGE_TOP/EDGE_BOTTOM → rect width
        - RectangleItem + EDGE_LEFT/EDGE_RIGHT → rect height
        - PolygonItem / PolylineItem + EDGE_* → segment length

        Returns the dimension in scene units (cm), or None if not computable.
        """
        from open_garden_planner.ui.canvas.items import PolylineItem, RectangleItem
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem
        from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

        item = self._find_item_by_id(item_id)
        if item is None:
            return None

        if isinstance(item, CircleItem):
            return item._radius

        if isinstance(item, RectangleItem):
            rect = item.rect()
            if anchor_type in (AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM):
                return abs(rect.width())
            if anchor_type in (AnchorType.EDGE_LEFT, AnchorType.EDGE_RIGHT):
                return abs(rect.height())
            return None

        if isinstance(item, PolygonItem):
            polygon = item.polygon()
            n = polygon.count()
            if n < 2:
                return None
            i = anchor_index
            p1 = item.mapToScene(polygon.at(i))
            p2 = item.mapToScene(polygon.at((i + 1) % n))
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            return math.sqrt(dx * dx + dy * dy)

        if isinstance(item, PolylineItem):
            pts = item.points
            i = anchor_index
            if i < 0 or i + 1 >= len(pts):
                return None
            p1 = item.mapToScene(pts[i])
            p2 = item.mapToScene(pts[i + 1])
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            return math.sqrt(dx * dx + dy * dy)

        return None

    def _build_equal_marker(
        self,
        group: DimensionLineGroup,
        pos_a: QPointF,
        pos_b: QPointF,
        color: QColor,
    ) -> None:
        """Draw "=" signs at each anchor and a dashed connector between them."""
        pen = QPen(color, 1.5)
        pen.setCosmetic(True)

        # Dashed connector
        dash_pen = QPen(color, 1.0, Qt.PenStyle.DashLine)
        dash_pen.setCosmetic(True)
        connector = self._scene.addLine(QLineF(pos_a, pos_b), dash_pen)
        connector.setZValue(DIMENSION_LINE_Z)
        group.items.append(connector)

        # Two horizontal bars ("=") at each anchor position
        for pos in (pos_a, pos_b):
            for offset in (-3.5, 3.5):
                bar = self._scene.addLine(
                    QLineF(pos.x() - 5, pos.y() + offset, pos.x() + 5, pos.y() + offset),
                    pen,
                )
                bar.setZValue(DIMENSION_LINE_Z + 1)
                group.items.append(bar)

        # "=" label at midpoint
        mid = QPointF((pos_a.x() + pos_b.x()) / 2, (pos_a.y() + pos_b.y()) / 2)
        text_item = QGraphicsSimpleTextItem("=")
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(color))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text_item.setZValue(DIMENSION_LINE_Z + 1)
        text_item.setPos(QPointF(mid.x() + 4, mid.y() - 8))
        self._scene.addItem(text_item)
        group.items.append(text_item)

    def _build_fixed_marker(
        self,
        group: DimensionLineGroup,
        pos: QPointF,
    ) -> None:
        """Draw a padlock badge (🔒) at the item's center anchor position.

        The lock symbol indicates the item is fixed in place and cannot be moved.
        """
        color = COLOR_FIXED

        # Small filled square as "body" of the padlock
        half = 6.0
        path = QPainterPath()
        path.addRect(QRectF(pos.x() - half, pos.y() - half / 2, half * 2, half * 1.5))
        body = QGraphicsPathItem(path)
        body.setPen(QPen(color.darker(120), 1.0))
        body.setBrush(QBrush(color))
        body.setZValue(DIMENSION_LINE_Z + 1)
        self._scene.addItem(body)
        group.items.append(body)

        # Arc above the body (shackle of the lock)
        arc_path = QPainterPath()
        arc_path.moveTo(pos.x() - half * 0.5, pos.y() - half / 2)
        arc_path.arcTo(
            QRectF(pos.x() - half * 0.5, pos.y() - half * 1.3, half, half),
            180, -180,
        )
        shackle = self._scene.addPath(arc_path, QPen(color.darker(120), 2.5))
        shackle.setZValue(DIMENSION_LINE_Z + 1)
        group.items.append(shackle)

        # "🔒" text label offset to the right
        text_item = QGraphicsSimpleTextItem("🔒")
        font = QFont()
        font.setPointSize(10)
        text_item.setFont(font)
        text_item.setBrush(QBrush(color))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text_item.setZValue(DIMENSION_LINE_Z + 1)
        text_item.setPos(QPointF(pos.x() + half + 2, pos.y() - half))
        self._scene.addItem(text_item)
        group.items.append(text_item)

    def _build_parallel_marker(
        self,
        group: DimensionLineGroup,
        pos_a: QPointF,
        pos_b: QPointF,
        color: QColor,
    ) -> None:
        """Draw two parallel hash marks (∥) at each edge midpoint and a dashed connector."""
        pen = QPen(color, 1.5)
        pen.setCosmetic(True)

        # Dashed connector line between the two edge midpoints
        dash_pen = QPen(color, 1.0, Qt.PenStyle.DashLine)
        dash_pen.setCosmetic(True)
        connector = self._scene.addLine(QLineF(pos_a, pos_b), dash_pen)
        connector.setZValue(DIMENSION_LINE_Z)
        group.items.append(connector)

        # Draw double-tick hash marks at each anchor position
        for pos in (pos_a, pos_b):
            for offset in (-4.0, 4.0):
                tick = self._scene.addLine(
                    QLineF(pos.x() - 5, pos.y() + offset, pos.x() + 5, pos.y() + offset),
                    pen,
                )
                tick.setZValue(DIMENSION_LINE_Z + 1)
                group.items.append(tick)

        # "∥" label near the midpoint
        mid = QPointF((pos_a.x() + pos_b.x()) / 2, (pos_a.y() + pos_b.y()) / 2)
        text_item = QGraphicsSimpleTextItem("\u2225")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(color))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text_item.setZValue(DIMENSION_LINE_Z + 1)
        text_item.setPos(QPointF(mid.x() + 4, mid.y() - 8))
        self._scene.addItem(text_item)
        group.items.append(text_item)

    def _build_perpendicular_marker(
        self,
        group: DimensionLineGroup,
        pos_a: QPointF,
        pos_b: QPointF,
        color: QColor,
    ) -> None:
        """Draw a right-angle symbol (⊾) at each edge midpoint and a dashed connector."""
        pen = QPen(color, 1.5)
        pen.setCosmetic(True)

        # Dashed connector line between the two edge midpoints
        dash_pen = QPen(color, 1.0, Qt.PenStyle.DashLine)
        dash_pen.setCosmetic(True)
        connector = self._scene.addLine(QLineF(pos_a, pos_b), dash_pen)
        connector.setZValue(DIMENSION_LINE_Z)
        group.items.append(connector)

        # Draw a small right-angle square marker at each anchor
        SZ = 5.0  # half-size of the right-angle square in scene units
        for pos in (pos_a, pos_b):
            path = QPainterPath()
            path.moveTo(pos.x() - SZ, pos.y())
            path.lineTo(pos.x() - SZ, pos.y() - SZ)
            path.lineTo(pos.x(), pos.y() - SZ)
            right_angle = self._scene.addPath(path, pen)
            right_angle.setZValue(DIMENSION_LINE_Z + 1)
            group.items.append(right_angle)

        # "⊾" label near the midpoint
        mid = QPointF((pos_a.x() + pos_b.x()) / 2, (pos_a.y() + pos_b.y()) / 2)
        text_item = QGraphicsSimpleTextItem("\u22be")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(color))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text_item.setZValue(DIMENSION_LINE_Z + 1)
        text_item.setPos(QPointF(mid.x() + 4, mid.y() - 8))
        self._scene.addItem(text_item)
        group.items.append(text_item)

    def _build_symmetry_indicator(
        self,
        group: DimensionLineGroup,
        pos_a: QPointF,
        pos_b: QPointF,
        axis_val: float,
        axis_is_horizontal: bool,
        color: QColor,
    ) -> None:
        """Build a visual indicator for a symmetry constraint.

        Draws a dashed axis line through the midpoint, small dots at each anchor,
        and a dashed connector between them with an "S" label.
        """
        pen_dash = QPen(color, 1.5, Qt.PenStyle.DashLine)
        pen_dash.setCosmetic(True)
        pen_solid = QPen(color, 1.5)
        pen_solid.setCosmetic(True)

        # Dashed connector line between the two anchors
        connector = self._scene.addLine(QLineF(pos_a, pos_b), pen_dash)
        connector.setZValue(DIMENSION_LINE_Z)
        group.items.append(connector)

        # Determine axis extent: span a bit beyond both anchors
        if axis_is_horizontal:
            # Horizontal axis at y = axis_val; extend left/right
            min_x = min(pos_a.x(), pos_b.x()) - 30.0
            max_x = max(pos_a.x(), pos_b.x()) + 30.0
            axis_start = QPointF(min_x, axis_val)
            axis_end = QPointF(max_x, axis_val)
        else:
            # Vertical axis at x = axis_val; extend up/down
            min_y = min(pos_a.y(), pos_b.y()) - 30.0
            max_y = max(pos_a.y(), pos_b.y()) + 30.0
            axis_start = QPointF(axis_val, min_y)
            axis_end = QPointF(axis_val, max_y)

        axis_line = self._scene.addLine(QLineF(axis_start, axis_end), pen_solid)
        axis_line.setZValue(DIMENSION_LINE_Z)
        group.items.append(axis_line)

        # Small triangular "mirror" tick marks on the axis
        TICK = 6.0
        if axis_is_horizontal:
            mid_x = (pos_a.x() + pos_b.x()) / 2.0
            tick_a = QPointF(mid_x - TICK, axis_val)
            tick_b = QPointF(mid_x + TICK, axis_val)
            # Two short perpendicular ticks above and below the axis line
            for side in (-1.0, 1.0):
                t = self._scene.addLine(
                    QLineF(
                        QPointF(mid_x, axis_val - TICK * side),
                        QPointF(mid_x, axis_val + TICK * side * 0.5),
                    ),
                    pen_solid,
                )
                t.setZValue(DIMENSION_LINE_Z)
                group.items.append(t)
            _ = tick_a, tick_b  # suppress unused warnings
        else:
            mid_y = (pos_a.y() + pos_b.y()) / 2.0
            for side in (-1.0, 1.0):
                t = self._scene.addLine(
                    QLineF(
                        QPointF(axis_val - TICK * side, mid_y),
                        QPointF(axis_val + TICK * side * 0.5, mid_y),
                    ),
                    pen_solid,
                )
                t.setZValue(DIMENSION_LINE_Z)
                group.items.append(t)

        # Small dots at each anchor
        for pos in (pos_a, pos_b):
            r = 3.5
            ellipse = self._scene.addEllipse(
                QRectF(pos.x() - r, pos.y() - r, r * 2, r * 2),
                QPen(color, 1.5),
                QBrush(color),
            )
            ellipse.setZValue(DIMENSION_LINE_Z)
            group.items.append(ellipse)

        # Label "S" at the axis midpoint
        if axis_is_horizontal:
            label_pos = QPointF((pos_a.x() + pos_b.x()) / 2.0 + 6.0, axis_val - 8.0)
        else:
            label_pos = QPointF(axis_val + 6.0, (pos_a.y() + pos_b.y()) / 2.0 - 8.0)

        text_item = QGraphicsSimpleTextItem("S")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(color))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text_item.setZValue(DIMENSION_LINE_Z + 1)
        text_item.setPos(label_pos)
        self._scene.addItem(text_item)
        group.items.append(text_item)

    def _build_angle_arc(
        self,
        group: DimensionLineGroup,
        pos_a: QPointF,
        pos_b: QPointF,
        pos_c: QPointF,
        target_angle_deg: float,
        color: QColor,
    ) -> None:
        """Build an angle arc annotation at the vertex (pos_b).

        Draws two short ray lines from B towards A and C, then an arc between
        them at a fixed radius, with the target angle label.
        """
        pen = QPen(color, 1.5)
        pen.setCosmetic(True)

        # Vectors from vertex to A and C
        ba_x, ba_y = pos_a.x() - pos_b.x(), pos_a.y() - pos_b.y()
        bc_x, bc_y = pos_c.x() - pos_b.x(), pos_c.y() - pos_b.y()
        ba_len = math.sqrt(ba_x * ba_x + ba_y * ba_y)
        bc_len = math.sqrt(bc_x * bc_x + bc_y * bc_y)

        if ba_len < 1e-6 or bc_len < 1e-6:
            return

        # Angles of the two rays from the vertex (in degrees, Qt convention: right=0, CW)
        angle_a = math.degrees(math.atan2(ba_y, ba_x))
        angle_c = math.degrees(math.atan2(bc_y, bc_x))

        # Arc radius in scene units (cosmetic — will appear ~20px regardless of zoom)
        arc_r = 25.0  # cm

        # Short tick lines along each ray at arc_r distance
        tick_end_a = QPointF(
            pos_b.x() + ba_x / ba_len * arc_r,
            pos_b.y() + ba_y / ba_len * arc_r,
        )
        tick_end_c = QPointF(
            pos_b.x() + bc_x / bc_len * arc_r,
            pos_b.y() + bc_y / bc_len * arc_r,
        )
        line_a = self._scene.addLine(QLineF(pos_b, tick_end_a), pen)
        line_a.setZValue(DIMENSION_LINE_Z)
        group.items.append(line_a)

        line_c = self._scene.addLine(QLineF(pos_b, tick_end_c), pen)
        line_c.setZValue(DIMENSION_LINE_Z)
        group.items.append(line_c)

        # Arc from angle_a to angle_c (choose the shorter arc)
        # QGraphicsEllipseItem draws arcs with spanAngle; Qt uses 1/16 degree units.
        # Normalize span to the interior angle (always <= 180°).
        span = angle_c - angle_a
        # Normalize to (-360, 360]
        span = span % 360.0
        if span > 180.0:
            span -= 360.0
        elif span < -180.0:
            span += 360.0

        # In Qt, the arc goes CCW from start_angle by span_angle
        # (positive span = CCW in Qt's Y-down coordinate system).
        path = QPainterPath()
        rect = QRectF(
            pos_b.x() - arc_r, pos_b.y() - arc_r, arc_r * 2, arc_r * 2
        )
        # arcTo: startAngle (CCW from 3 o'clock in Qt), spanAngle (positive = CCW)
        # Qt uses Y-down so atan2(y, x) maps directly.
        path.arcMoveTo(rect, -angle_a)
        path.arcTo(rect, -angle_a, span)

        arc_item = QGraphicsPathItem(path)
        arc_item.setPen(pen)
        arc_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        arc_item.setZValue(DIMENSION_LINE_Z)
        self._scene.addItem(arc_item)
        group.items.append(arc_item)

        # Angle label at the mid-arc point
        mid_angle_rad = math.radians(angle_a + span / 2.0)
        label_r = arc_r + 10.0  # place label slightly outside the arc
        label_pos = QPointF(
            pos_b.x() + math.cos(mid_angle_rad) * label_r,
            pos_b.y() + math.sin(mid_angle_rad) * label_r,
        )
        text_str = f"{target_angle_deg:.1f}°"
        text_item = QGraphicsSimpleTextItem(text_str)
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(color))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text_item.setZValue(DIMENSION_LINE_Z + 1)
        text_item.setPos(label_pos)
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
                constraint.anchor_a.item_id,
                constraint.anchor_a.anchor_type,
                constraint.anchor_a.anchor_index,
            )
            pos_b = self._resolve_anchor_position(
                constraint.anchor_b.item_id,
                constraint.anchor_b.anchor_type,
                constraint.anchor_b.anchor_index,
            )
            if pos_a is None or pos_b is None:
                continue

            # For alignment constraints check distance to the direct line;
            # for angle constraints check proximity to vertex (pos_b);
            # for distance constraints check the offset dimension line.
            if constraint.constraint_type in (ConstraintType.HORIZONTAL, ConstraintType.VERTICAL):
                dist = _point_to_segment_distance(scene_pos, pos_a, pos_b)
            elif constraint.constraint_type in (
                ConstraintType.SYMMETRY_HORIZONTAL,
                ConstraintType.SYMMETRY_VERTICAL,
                ConstraintType.COINCIDENT,
                ConstraintType.PARALLEL,
                ConstraintType.PERPENDICULAR,
            ):
                # Check proximity to the connector line between the two anchors
                dist = _point_to_segment_distance(scene_pos, pos_a, pos_b)
            elif constraint.constraint_type == ConstraintType.ANGLE:
                dx = scene_pos.x() - pos_b.x()
                dy = scene_pos.y() - pos_b.y()
                dist = math.sqrt(dx * dx + dy * dy)
            else:
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
