"""Polygon item for the garden canvas."""

import math
import uuid
from typing import Any

from PyQt6.QtCore import QCoreApplication, QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType, StrokeStyle, get_style, is_bed_type

from .garden_item import GardenItemMixin
from .resize_handle import ResizeHandlesMixin, RotationHandleMixin, VertexEditMixin


def _project_to_polygon_boundary(polygon: QPolygonF, point: QPointF) -> QPointF:
    """Find the closest point on a polygon's boundary to *point*.

    Iterates over every edge of *polygon*, projects *point* onto it, and
    returns the nearest result.  Coordinates are in whatever space the
    polygon vertices use (usually item-local).
    """
    best_pt = point
    best_dist_sq = float("inf")
    n = polygon.count()
    for i in range(n):
        v1 = polygon.at(i)
        v2 = polygon.at((i + 1) % n)
        ex = v2.x() - v1.x()
        ey = v2.y() - v1.y()
        len_sq = ex * ex + ey * ey
        if len_sq < 1e-10:
            proj = QPointF(v1)
        else:
            t = ((point.x() - v1.x()) * ex + (point.y() - v1.y()) * ey) / len_sq
            t = max(0.0, min(1.0, t))
            proj = QPointF(v1.x() + t * ex, v1.y() + t * ey)
        dx = proj.x() - point.x()
        dy = proj.y() - point.y()
        d2 = dx * dx + dy * dy
        if d2 < best_dist_sq:
            best_dist_sq = d2
            best_pt = proj
    return best_pt


def _split_path_by_line(
    path: QPainterPath, line: QLineF
) -> tuple[QPainterPath, QPainterPath]:
    """Split a QPainterPath into two halves along a line.

    Returns (left_half, right_half) where "left" is the side that the
    perpendicular points toward negative when walking from line.p1 to p2.

    Args:
        path: The path to split
        line: The dividing line (will be extended far beyond the path bounds)

    Returns:
        Tuple of (left_path, right_path)
    """
    bounds = path.boundingRect()
    ext = max(bounds.width(), bounds.height()) * 10.0 + 1000.0

    dx = line.dx()
    dy = line.dy()
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return path, QPainterPath()

    # Unit direction and unit perpendicular
    ux, uy = dx / length, dy / length
    px, py = -uy, ux  # left-perpendicular

    # Midpoint of the supplied line segment
    mid_x = (line.x1() + line.x2()) / 2.0
    mid_y = (line.y1() + line.y2()) / 2.0

    # Extended ridge endpoints
    e1 = QPointF(mid_x - ux * ext, mid_y - uy * ext)
    e2 = QPointF(mid_x + ux * ext, mid_y + uy * ext)

    # Left half-plane polygon (perpendicular direction is "left")
    left_rect = QPainterPath()
    left_rect.moveTo(e1)
    left_rect.lineTo(e2)
    left_rect.lineTo(QPointF(e2.x() + px * ext, e2.y() + py * ext))
    left_rect.lineTo(QPointF(e1.x() + px * ext, e1.y() + py * ext))
    left_rect.closeSubpath()

    # Right half-plane polygon
    right_rect = QPainterPath()
    right_rect.moveTo(e1)
    right_rect.lineTo(e2)
    right_rect.lineTo(QPointF(e2.x() - px * ext, e2.y() - py * ext))
    right_rect.lineTo(QPointF(e1.x() - px * ext, e1.y() - py * ext))
    right_rect.closeSubpath()

    return path.intersected(left_rect), path.intersected(right_rect)


def _show_properties_dialog(item: QGraphicsPolygonItem) -> None:
    """Show properties dialog for an item (imported locally to avoid circular import)."""
    from open_garden_planner.core.object_types import get_style
    from open_garden_planner.ui.dialogs import PropertiesDialog

    dialog = PropertiesDialog(item)
    if dialog.exec():
        # Apply name change
        if hasattr(item, 'name'):
            item.name = dialog.get_name()
            # Update the label if it exists
            if hasattr(item, '_update_label'):
                item._update_label()  # type: ignore[attr-defined]

        # Apply layer change
        if hasattr(item, 'layer_id'):
            new_layer_id = dialog.get_layer_id()
            if new_layer_id is not None:
                item.layer_id = new_layer_id
                # Update z-order based on new layer
                scene = item.scene()
                if scene and hasattr(scene, 'get_layer_by_id'):
                    layer = scene.get_layer_by_id(new_layer_id)
                    if layer:
                        item.setZValue(layer.z_order * 100)

        # Apply object type change (updates styling)
        new_object_type = dialog.get_object_type()
        if new_object_type and hasattr(item, 'object_type'):
            item.object_type = new_object_type
            # Update to default styling for new type
            style = get_style(new_object_type)
            pen = item.pen()
            pen.setColor(style.stroke_color)
            pen.setWidthF(style.stroke_width)
            pen.setStyle(style.stroke_style.to_qt_pen_style())
            item.setPen(pen)
            # Apply pattern brush and store pattern
            if hasattr(item, 'fill_pattern'):
                item.fill_pattern = style.fill_pattern
            brush = create_pattern_brush(style.fill_pattern, style.fill_color)
            item.setBrush(brush)

        # Apply custom fill color and pattern (overrides type default)
        fill_color = dialog.get_fill_color()
        fill_pattern = dialog.get_fill_pattern()
        # Store the pattern and base color
        if hasattr(item, 'fill_pattern'):
            item.fill_pattern = fill_pattern
        if hasattr(item, 'fill_color'):
            item.fill_color = fill_color
        brush = create_pattern_brush(fill_pattern, fill_color)
        item.setBrush(brush)

        # Apply custom stroke properties (overrides type default)
        stroke_color = dialog.get_stroke_color()
        stroke_width = dialog.get_stroke_width()
        stroke_style = dialog.get_stroke_style()
        # Store stroke properties
        if hasattr(item, 'stroke_color'):
            item.stroke_color = stroke_color
        if hasattr(item, 'stroke_width'):
            item.stroke_width = stroke_width
        if hasattr(item, 'stroke_style'):
            item.stroke_style = stroke_style
        pen = item.pen()
        pen.setColor(stroke_color)
        pen.setWidthF(stroke_width)
        pen.setStyle(stroke_style.to_qt_pen_style())
        item.setPen(pen)


class PolygonItem(VertexEditMixin, RotationHandleMixin, ResizeHandlesMixin, GardenItemMixin, QGraphicsPolygonItem):
    """A polygon shape on the garden canvas.

    Supports property object types with appropriate styling.
    Supports selection, movement, resizing, rotation, and vertex editing.
    """

    def __init__(
        self,
        vertices: list[QPointF],
        object_type: ObjectType = ObjectType.GENERIC_POLYGON,
        name: str = "",
        metadata: dict[str, Any] | None = None,
        fill_pattern: FillPattern | None = None,
        stroke_style: StrokeStyle | None = None,
        layer_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize the polygon item.

        Args:
            vertices: List of vertices defining the polygon
            object_type: Type of property object
            name: Optional name/label for the object
            metadata: Optional metadata dictionary
            fill_pattern: Fill pattern (defaults to pattern from object type)
            stroke_style: Stroke style (defaults to style from object type)
            layer_id: Layer ID this item belongs to (optional)
        """
        # Get default pattern and color from object type if not provided
        style = get_style(object_type)
        if fill_pattern is None:
            fill_pattern = style.fill_pattern
        if stroke_style is None:
            stroke_style = style.stroke_style

        GardenItemMixin.__init__(
            self, object_type=object_type, name=name, metadata=metadata,
            fill_pattern=fill_pattern, fill_color=style.fill_color,
            stroke_color=style.stroke_color, stroke_width=style.stroke_width,
            stroke_style=stroke_style, layer_id=layer_id
        )
        polygon = QPolygonF(vertices)
        QGraphicsPolygonItem.__init__(self, polygon)

        # Initialize resize, rotation, and vertex editing handles
        self.init_resize_handles()
        self.init_rotation_handle()
        self.init_vertex_edit()
        self._resize_initial_polygon: QPolygonF | None = None

        self._setup_styling()
        self._setup_flags()
        self.initialize_label()

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type."""
        style = get_style(self.object_type) if self.object_type else get_style(ObjectType.GENERIC_POLYGON)

        # Use stored stroke properties if available, otherwise use style defaults
        stroke_color = self.stroke_color if self.stroke_color is not None else style.stroke_color
        stroke_width = self.stroke_width if self.stroke_width is not None else style.stroke_width
        stroke_style = self.stroke_style if self.stroke_style is not None else style.stroke_style

        pen = QPen(stroke_color)
        pen.setWidthF(stroke_width)
        pen.setStyle(stroke_style.to_qt_pen_style())
        self.setPen(pen)

        # Use stored fill_pattern and color if available, otherwise use style defaults
        pattern = self.fill_pattern if self.fill_pattern is not None else style.fill_pattern
        color = self.fill_color if self.fill_color is not None else style.fill_color
        brush = create_pattern_brush(pattern, color)
        self.setBrush(brush)

    def _setup_flags(self) -> None:
        """Configure item interaction flags."""
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsFocusable, True)

    def boundingRect(self) -> QRectF:
        """Return bounding rect, expanded for shadow."""
        base = super().boundingRect()
        m = self._shadow_margin()
        if m > 0:
            base = base.adjusted(-m, -m, m, m)
        return base

    def _find_ridge(self) -> "QGraphicsItem | None":
        """Look up the associated roof ridge item in the scene by metadata ID."""
        rid = self.get_metadata("ridge_item_id")
        if not rid:
            return None
        scene = self.scene()
        if scene is None:
            return None
        for item in scene.items():
            if hasattr(item, "item_id") and str(item.item_id) == rid:
                return item
        return None

    def _update_ridge_on_boundary(self) -> None:
        """Re-project the ridge endpoints onto the current polygon boundary.

        Called after polygon resize, vertex edit, or rotation so that the
        ridge stays attached to the polygon's outer edge.
        """
        ridge = self._find_ridge()
        if ridge is None:
            return

        poly = self.polygon()
        if poly.count() < 3:
            return

        from open_garden_planner.ui.canvas.items import PolylineItem

        if not isinstance(ridge, PolylineItem):
            return

        pts = ridge.points  # scene-space (ridge pos is usually 0,0)
        if len(pts) < 2:
            return

        new_pts: list[QPointF] = []
        for pt in pts:
            # Convert ridge scene-coord → polygon item-local coord
            local = self.mapFromScene(ridge.mapToScene(pt))
            projected = _project_to_polygon_boundary(poly, local)
            # Convert back to ridge item-local coords
            scene_pt = self.mapToScene(projected)
            new_pts.append(ridge.mapFromScene(scene_pt))

        # Update ridge geometry directly
        ridge._points = new_pts
        ridge._rebuild_path()
        if hasattr(ridge, '_update_vertex_handles') and ridge.is_vertex_edit_mode:
            ridge._update_vertex_handles()
        if hasattr(ridge, '_position_label'):
            ridge._position_label()

    def _paint_with_ridge(self, painter: QPainter, ridge: "QGraphicsItem") -> None:
        """Paint HOUSE polygon with tile texture mirrored on each side of the ridge."""
        # Get ridge endpoints in item-local coordinates
        pts = ridge.points  # list[QPointF] in item-local coords of the ridge item
        if len(pts) < 2:
            return
        p1 = self.mapFromScene(ridge.mapToScene(pts[0]))
        p2 = self.mapFromScene(ridge.mapToScene(pts[-1]))

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-9:
            return
        mid_x = (p1.x() + p2.x()) / 2.0
        mid_y = (p1.y() + p2.y()) / 2.0
        angle_deg = math.degrees(math.atan2(dy, dx))

        # Build polygon QPainterPath
        poly = self.polygon()
        poly_path = QPainterPath()
        if poly.count() > 0:
            poly_path.moveTo(poly.at(0))
            for i in range(1, poly.count()):
                poly_path.lineTo(poly.at(i))
            poly_path.closeSubpath()

        # Build half-plane clipping paths along the ridge line
        left_path, right_path = _split_path_by_line(poly_path, QLineF(p1, p2))

        brush = self.brush()

        # Align tile rows perpendicular to ridge, tiling origin at ridge midpoint.
        # QBrush.setTransform(T) means: local point (x,y) samples texture at T^-1.(x,y).
        # We want texture to tile outward from the ridge on each side.
        normal_tx = QTransform()
        normal_tx.translate(mid_x, mid_y)
        normal_tx.rotate(angle_deg)
        normal_brush = QBrush(brush)
        normal_brush.setTransform(normal_tx)

        # Mirrored brush: flip the perpendicular axis so tiles mirror across the ridge
        mirrored_tx = QTransform()
        mirrored_tx.translate(mid_x, mid_y)
        mirrored_tx.rotate(angle_deg)
        mirrored_tx.scale(1.0, -1.0)
        mirrored_brush = QBrush(brush)
        mirrored_brush.setTransform(mirrored_tx)

        # Bounding rect for fill (clip handles actual shape)
        bounds = poly_path.boundingRect()
        ext = max(bounds.width(), bounds.height()) + 100.0
        fill_rect = QRectF(
            bounds.center().x() - ext,
            bounds.center().y() - ext,
            ext * 2.0,
            ext * 2.0,
        )

        # Paint right side (normal texture — tiles go "right" from ridge)
        painter.save()
        painter.setClipPath(right_path)
        painter.setBrush(normal_brush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(fill_rect)
        painter.restore()

        # Paint left side (mirrored texture — tiles go "left" from ridge)
        painter.save()
        painter.setClipPath(left_path)
        painter.setBrush(mirrored_brush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(fill_rect)
        painter.restore()

        # Draw outline on top
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(self.pen())
        painter.drawPath(poly_path)

    def _draw_grid_overlay(self, painter: QPainter) -> None:
        """Draw a square-foot grid overlay clipped to the polygon boundary."""
        spacing = self._grid_spacing
        if spacing <= 0:
            return
        poly = self.polygon()
        if poly.isEmpty():
            return

        # Build clip path from polygon
        clip_path = QPainterPath()
        clip_path.addPolygon(poly)
        clip_path.closeSubpath()

        painter.save()
        painter.setClipPath(clip_path, Qt.ClipOperation.IntersectClip)

        pen = QPen(QColor(255, 255, 255, 120))
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        br = poly.boundingRect()
        # Align grid lines to spacing multiples for consistent appearance
        x0 = math.floor(br.left() / spacing) * spacing
        y0 = math.floor(br.top() / spacing) * spacing

        # Vertical lines
        x = x0
        while x <= br.right():
            painter.drawLine(QPointF(x, br.top()), QPointF(x, br.bottom()))
            x += spacing

        # Horizontal lines
        y = y0
        while y <= br.bottom():
            painter.drawLine(QPointF(br.left(), y), QPointF(br.right(), y))
            y += spacing

        painter.restore()

    def grid_cell_count(self) -> int:
        """Return the approximate number of grid cells inside the polygon."""
        poly = self.polygon()
        if poly.isEmpty() or self._grid_spacing <= 0:
            return 0
        # Shoelace formula for polygon area
        n = poly.count()
        area = 0.0
        for i in range(n):
            p1 = poly.at(i)
            p2 = poly.at((i + 1) % n)
            area += p1.x() * p2.y() - p2.x() * p1.y()
        area = abs(area) / 2.0
        cell_area = self._grid_spacing ** 2
        return int(area / cell_area)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the polygon with an optional painted shadow."""
        if self._shadows_enabled:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.SHADOW_COLOR)
            shadow_poly = self.polygon().translated(
                self.SHADOW_OFFSET_X, self.SHADOW_OFFSET_Y,
            )
            painter.drawPolygon(shadow_poly)
            painter.restore()

        # For HOUSE polygons with a ridge: use mirrored tile rendering
        ridge = self._find_ridge()
        if ridge is not None and self.object_type == ObjectType.HOUSE:
            self._paint_with_ridge(painter, ridge)
        else:
            super().paint(painter, option, widget)

        # Draw square-foot grid overlay inside bed
        if self._grid_enabled and is_bed_type(self.object_type):
            self._draw_grid_overlay(painter)

        # Draw crop rotation status indicator (colored inner border on beds)
        if self._rotation_status is not None:
            _rotation_colors = {
                "good": QColor(46, 125, 50, 160),
                "suboptimal": QColor(245, 127, 23, 160),
                "violation": QColor(198, 40, 40, 160),
            }
            indicator_color = _rotation_colors.get(self._rotation_status)
            if indicator_color is not None:
                indicator_pen = QPen(indicator_color)
                indicator_pen.setWidthF(4.0)
                painter.setPen(indicator_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(self.polygon())

        # Draw soil mismatch border outside rotation border (US-12.10d)
        if is_bed_type(self.object_type):
            self._draw_soil_mismatch_border(painter)

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: Any,
    ) -> Any:
        """Handle item state changes.

        Shows/hides resize and rotation handles based on selection state.
        Exits vertex edit mode when deselected.
        Updates annotations when position changes.
        Moves the attached ridge when the polygon moves.
        """
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value:  # Being selected
                # Only show resize/rotation handles if not in vertex edit mode
                if not self.is_vertex_edit_mode:
                    self.show_resize_handles()
                    self.show_rotation_handle()
            else:  # Being deselected
                # Exit vertex edit mode when deselected
                if self.is_vertex_edit_mode:
                    self.exit_vertex_edit_mode()
                self.hide_resize_handles()
                self.hide_rotation_handle()
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Record old pos BEFORE it changes so we can compute the delta
            self._pre_move_pos = QPointF(self.pos())
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.is_vertex_edit_mode:
                self._update_annotations()
            # Move attached ridge by the same delta
            self._move_ridge_by_delta()
            self._update_area_label()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
            self.remove_rotation_handle()

        return super().itemChange(change, value)

    def _compute_area_cm2(self) -> float | None:
        poly = self.polygon()
        n = poly.count()
        if n < 3:
            return None
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += poly.at(i).x() * poly.at(j).y()
            area -= poly.at(j).x() * poly.at(i).y()
        return abs(area) / 2.0

    def _move_ridge_by_delta(self) -> None:
        """Translate the attached ridge by the same delta as this polygon moved."""
        old_pos = getattr(self, "_pre_move_pos", None)
        if old_pos is None:
            return
        new_pos = self.pos()
        dx = new_pos.x() - old_pos.x()
        dy = new_pos.y() - old_pos.y()
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return

        ridge = self._find_ridge()
        if ridge is None:
            return

        from open_garden_planner.ui.canvas.items import PolylineItem

        if not isinstance(ridge, PolylineItem):
            return

        # Shift every ridge point by the same delta (both are scene-space items)
        new_pts = [QPointF(pt.x() + dx, pt.y() + dy) for pt in ridge._points]
        ridge._points = new_pts
        ridge._rebuild_path()
        if hasattr(ridge, "_update_vertex_handles") and ridge.is_vertex_edit_mode:
            ridge._update_vertex_handles()
        if hasattr(ridge, "_position_label"):
            ridge._position_label()

    def _move_vertex_to(self, index: int, pos: QPointF) -> None:
        """Move a polygon vertex and keep the attached ridge on the boundary."""
        super()._move_vertex_to(index, pos)
        # Re-project ridge endpoints when the polygon shape changes
        self._update_ridge_on_boundary()

    def _apply_rotation(self, angle: float) -> None:
        """Apply rotation and keep the attached ridge on the boundary."""
        super()._apply_rotation(angle)
        self._update_ridge_on_boundary()

    def _on_resize_start(self) -> None:
        """Called when a resize operation starts. Store initial polygon."""
        super()._on_resize_start()
        self._resize_initial_polygon = QPolygonF(self.polygon())

    def _apply_resize(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        pos_x: float,
        pos_y: float,
    ) -> None:
        """Apply a resize transformation to this polygon.

        Scales polygon vertices proportionally based on bounding box change.

        Args:
            x: New x position of rect (in item coords)
            y: New y position of rect (in item coords)
            width: New width
            height: New height
            pos_x: New scene x position
            pos_y: New scene y position
        """
        # Get current polygon and bounding rect
        current_poly = self.polygon()
        old_rect = current_poly.boundingRect()

        # Calculate scale factors
        scale_x = width / old_rect.width() if old_rect.width() > 0 else 1.0
        scale_y = height / old_rect.height() if old_rect.height() > 0 else 1.0

        # Scale each vertex relative to the bounding rect's top-left
        new_vertices = []
        for i in range(current_poly.count()):
            old_point = current_poly.at(i)
            # Calculate relative position within bounding rect
            rel_x = old_point.x() - old_rect.x()
            rel_y = old_point.y() - old_rect.y()
            # Scale and reposition
            new_x = x + rel_x * scale_x
            new_y = y + rel_y * scale_y
            new_vertices.append(QPointF(new_x, new_y))

        # Update polygon
        self.setPolygon(QPolygonF(new_vertices))

        # Update position
        self.setPos(pos_x, pos_y)

        # Update resize handles
        self.update_resize_handles()

        # Update label position
        self._position_label()
        self._update_area_label()

        # Keep ridge endpoints on the polygon boundary
        self._update_ridge_on_boundary()

    def _on_resize_end(
        self,
        initial_rect: QRectF | None,
        initial_pos: QPointF | None,
    ) -> None:
        """Called when resize operation completes. Registers undo command."""
        if initial_rect is None or initial_pos is None or self._resize_initial_polygon is None:
            return

        scene = self.scene()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        # Get current geometry
        current_pos = self.pos()
        current_poly = self.polygon()

        # Only register command if geometry actually changed
        if (self._resize_initial_polygon == current_poly and initial_pos == current_pos):
            self._resize_initial_polygon = None
            return

        from open_garden_planner.core.commands import ResizeItemCommand

        def apply_geometry(item: QGraphicsItem, geom: dict[str, Any]) -> None:
            """Apply geometry to the item."""
            if isinstance(item, PolygonItem):
                # Reconstruct polygon from vertices
                vertices = [QPointF(v['x'], v['y']) for v in geom['vertices']]
                item.setPolygon(QPolygonF(vertices))
                item.setPos(geom['pos_x'], geom['pos_y'])
                item.update_resize_handles()
                item._position_label()

        # Convert polygon vertices to serializable format
        def polygon_to_vertices(poly: QPolygonF) -> list[dict[str, float]]:
            return [{'x': poly.at(i).x(), 'y': poly.at(i).y()} for i in range(poly.count())]

        old_geometry = {
            'vertices': polygon_to_vertices(self._resize_initial_polygon),
            'pos_x': initial_pos.x(),
            'pos_y': initial_pos.y(),
        }

        new_geometry = {
            'vertices': polygon_to_vertices(current_poly),
            'pos_x': current_pos.x(),
            'pos_y': current_pos.y(),
        }

        command = ResizeItemCommand(
            self,
            old_geometry,
            new_geometry,
            apply_geometry,
        )

        # Add to undo stack without executing (geometry already applied)
        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

        # Clear stored initial polygon
        self._resize_initial_polygon = None

    def _on_rotation_end(self, initial_angle: float) -> None:
        """Called when rotation operation completes. Registers undo command."""
        scene = self.scene()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        # Get current angle
        current_angle = self.rotation_angle

        # Only register command if angle actually changed
        if abs(initial_angle - current_angle) < 0.01:
            return

        from open_garden_planner.core.commands import RotateItemCommand

        def apply_rotation(item: QGraphicsItem, angle: float) -> None:
            """Apply rotation to the item."""
            if isinstance(item, PolygonItem):
                item._apply_rotation(angle)

        command = RotateItemCommand(
            self,
            initial_angle,
            current_angle,
            apply_rotation,
        )

        # Add to undo stack without executing (rotation already applied)
        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle double-click to enter vertex edit mode and start label edit."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.is_vertex_edit_mode:
                # Exit vertex edit mode on any other item first
                for item in self.scene().items():
                    if item is not self and hasattr(item, 'is_vertex_edit_mode') and item.is_vertex_edit_mode:
                        item.exit_vertex_edit_mode()
                self.enter_vertex_edit_mode()
            self.start_label_edit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key presses - Escape exits vertex edit mode."""
        if event.key() == Qt.Key.Key_Escape and self.is_vertex_edit_mode:
            self.exit_vertex_edit_mode()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show context menu on right-click."""
        # Select this item if not already selected
        if not self.isSelected():
            self.scene().clearSelection()
            self.setSelected(True)

        _ = QCoreApplication.translate
        menu = QMenu()

        # Edit vertices action
        if self.is_vertex_edit_mode:
            exit_edit_action = menu.addAction(_("PolygonItem", "Exit Vertex Edit Mode"))
            edit_vertices_action = None
        else:
            edit_vertices_action = menu.addAction(_("PolygonItem", "Edit Vertices"))
            exit_edit_action = None

        # Edit label action
        edit_label_action = menu.addAction(_("PolygonItem", "Edit Label"))

        # Bed-specific actions (grid toggle, soil test, pest log, succession)
        # are built centrally on GardenItemMixin — see ADR-017 / §8.12.
        from open_garden_planner.ui.canvas.items.garden_item import BedMenuActions
        bed_actions = BedMenuActions()
        if is_bed_type(self.object_type):
            bed_actions = self.build_bed_context_menu(
                menu, grid_enabled=self._grid_enabled, supports_grid=True
            )

        menu.addSeparator()

        # Move to Layer submenu (hidden when project has only one layer)
        move_layer_menu = self._build_move_to_layer_menu(menu)

        # Change Type submenu
        from open_garden_planner.core.object_types import get_valid_types_for_shape
        change_type_menu = self._build_change_type_menu(menu, get_valid_types_for_shape("polygon"))

        # Show Area toggle
        show_area_action = menu.addAction(_("PolygonItem", "Show Area"))
        show_area_action.setCheckable(True)
        show_area_action.setChecked(self._area_label_visible)

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction(_("PolygonItem", "Delete"))

        menu.addSeparator()

        # Duplicate action
        duplicate_action = menu.addAction(_("PolygonItem", "Duplicate"))

        # Linear array action
        linear_array_action = menu.addAction(_("PolygonItem", "Create Linear Array..."))

        # Grid array action
        grid_array_action = menu.addAction(_("PolygonItem", "Create Grid Array..."))

        # Circular array action
        circular_array_action = menu.addAction(_("PolygonItem", "Create Circular Array..."))

        # Boolean operations (requires exactly 2 selected closed shapes)
        boolean_union_action = None
        boolean_intersect_action = None
        boolean_subtract_action = None
        array_along_path_action = None
        selected = self.scene().selectedItems()
        if len(selected) == 2:
            from open_garden_planner.ui.canvas.items.circle_item import CircleItem
            from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
            from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

            shape_types = (PolygonItem, RectangleItem, CircleItem)
            if all(isinstance(s, shape_types) for s in selected):
                menu.addSeparator()
                bool_menu = menu.addMenu(_("PolygonItem", "Boolean"))
                boolean_union_action = bool_menu.addAction(_("PolygonItem", "Union"))
                boolean_intersect_action = bool_menu.addAction(_("PolygonItem", "Intersect"))
                boolean_subtract_action = bool_menu.addAction(_("PolygonItem", "Subtract"))
            if any(isinstance(s, PolylineItem) for s in selected):
                array_along_path_action = menu.addAction(
                    _("PolygonItem", "Array Along Path...")
                )

        # Execute menu and handle result
        action = menu.exec(event.screenPos())

        # Dispatch bed-specific actions via the shared mixin handler.
        if self.dispatch_bed_action(action, bed_actions):
            return

        if action == edit_vertices_action and edit_vertices_action is not None:
            # Enter vertex edit mode and switch to Select tool
            self.enter_vertex_edit_mode()
            self.setFocus()
            scene = self.scene()
            if scene:
                for v in scene.views():
                    if hasattr(v, "_tool_manager"):
                        from open_garden_planner.core.tools import ToolType
                        v._tool_manager.set_active_tool(ToolType.SELECT)
                        break
        elif action == exit_edit_action and exit_edit_action is not None:
            # Exit vertex edit mode
            self.exit_vertex_edit_mode()
        elif action == edit_label_action:
            # Edit the label
            self.start_label_edit()
        elif action == show_area_action:
            self.area_label_visible = not self._area_label_visible
        elif action == delete_action:
            # Delete this item and any other selected items
            scene = self.scene()
            for item in scene.selectedItems():
                scene.removeItem(item)
        elif action == duplicate_action:
            # Duplicate via canvas view
            scene = self.scene()
            if scene:
                views = scene.views()
                if views:
                    view = views[0]
                    if hasattr(view, "duplicate_selected"):
                        view.duplicate_selected()
        elif action == linear_array_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views:
                    view = views[0]
                    if hasattr(view, "create_linear_array"):
                        view.create_linear_array()
        elif action == grid_array_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views:
                    view = views[0]
                    if hasattr(view, "create_grid_array"):
                        view.create_grid_array()
        elif action == circular_array_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views:
                    view = views[0]
                    if hasattr(view, "create_circular_array"):
                        view.create_circular_array()
        elif action is not None and action in (
            boolean_union_action, boolean_intersect_action, boolean_subtract_action
        ):
            op_map = {
                boolean_union_action: "union",
                boolean_intersect_action: "intersect",
                boolean_subtract_action: "subtract",
            }
            scene = self.scene()
            if scene:
                for v in scene.views():
                    if hasattr(v, "boolean_operation"):
                        v.boolean_operation(op_map[action])
                        break
        elif action == array_along_path_action and array_along_path_action is not None:
            scene = self.scene()
            if scene:
                for v in scene.views():
                    if hasattr(v, "create_array_along_path"):
                        v.create_array_along_path()
                        break
        elif move_layer_menu and action and action.parent() is move_layer_menu:
            self._dispatch_move_to_layer(action.data())
        elif change_type_menu and action and action.parent() is change_type_menu:
            self._dispatch_change_type(action.data())

    @classmethod
    def from_polygon(cls, polygon: QPolygonF) -> "PolygonItem":
        """Create a PolygonItem from a QPolygonF.

        Args:
            polygon: The polygon geometry

        Returns:
            A new PolygonItem
        """
        vertices = [polygon.at(i) for i in range(polygon.count())]
        return cls(vertices)
