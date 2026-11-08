"""Polygon item for the garden canvas."""

import math
import uuid
from typing import Any

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
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
from open_garden_planner.ui.canvas.roof_ridge_link import ridge_points_local

from .garden_item import GardenItemMixin, is_interactive_paint
from .greenhouse_paint import paint_greenhouse
from .resize_handle import ResizeHandlesMixin, RotationHandleMixin, VertexEditMixin
from .roof_paint import paint_roof_with_ridge

# --- Issue #472: bound what a crafted plan can cost the 2D canvas -----------
#
# A polygon's fill cost is NOT a function of vertex count alone. Measured (512x512
# antialiased painter, the issue's full-height comb), the cost of one paint is:
#
#   vertices    full-detail fill        outline, item's 2.0 pen   outline, cosmetic 1px
#      256          38 ms                        35 ms                  2 ms
#     1024         322 ms                       319 ms                  4 ms
#     4096        1449 ms                       640 ms                 20 ms
#    16384        5580 ms                      2547 ms                 69 ms
#
# Two consequences drive this bound:
#   * a reflex-heavy fill is quadratic in vertices, so the full-detail budget must
#     sit below the counts the bug report measured (1,024 -> 10.5 s on its box);
#   * Qt strokes a WIDE solid pen by building a fill, so "draw the outline"
#     is only cheap with a COSMETIC (hairline) pen. Reusing the item's own pen
#     would leave the degraded frame quadratic (319 ms at 1,024 above).
#
# At or below MAX_FULL_DETAIL_VERTICES an unselected polygon paints exactly as
# before. Above it, an INTERACTIVE paint draws the exact outline with a cosmetic
# 1-px pen and no fill: that is linear with a small constant and independent of
# the item's pen width, so the window stays responsive. "Interactive" is decided
# by the item's CACHE MODE, not by Qt's ``widget`` argument — every cached paint
# receives widget=0, and unselected canvas items are cached, so a widget-based
# test would never fire (see the guard in ``paint``). Every export, report,
# print and agent render path disables caches first
# (``ExportService._disable_item_caches``), so those are never degraded and a
# saved PDF/PNG is unchanged; a selected item always paints exactly so editing
# and validation see the truth. A polygon whose outline is large but CONVEX
# would fill cheaply;
# distinguishing it needs an O(n) pass per paint, so the bound deliberately errs
# toward the outline for every large polygon (see ADR-057).
MAX_FULL_DETAIL_VERTICES = 256

# Hard ceiling at load for untrusted plan files (issue #472): a polygon above
# this is refused rather than built, so a crafted ``.ogp`` cannot stall the
# loader or exhaust memory. At this ceiling the degraded 2D outline is measured
# at ~69 ms, not minutes, and no legible garden outline comes near it.
MAX_POLYGON_VERTICES = 16_384


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
                item._update_label()

        # Apply layer change — consolidated onto MoveToLayerCommand (issue
        # #338); z is derived from the scene's normalized stacking order,
        # not set directly here.
        if hasattr(item, 'layer_id'):
            new_layer_id = dialog.get_layer_id()
            if new_layer_id is not None and new_layer_id != item.layer_id:
                from open_garden_planner.core.commands import MoveToLayerCommand

                scene = item.scene()
                if scene is not None:
                    target_layer = (
                        scene.get_layer_by_id(new_layer_id)
                        if hasattr(scene, 'get_layer_by_id')
                        else None
                    )
                    layer_name = target_layer.name if target_layer else str(new_layer_id)
                    cmd = MoveToLayerCommand([item], new_layer_id, scene, layer_name)
                    command_manager = getattr(scene, '_command_manager', None)
                    if command_manager:
                        command_manager.execute(cmd)
                    else:
                        cmd.execute()
                else:
                    item.layer_id = new_layer_id

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
            brush = create_pattern_brush(
                style.fill_pattern, style.fill_color, getattr(item, "fill_transform", None)
            )
            item.setBrush(brush)

        # Apply custom fill color and pattern (overrides type default)
        fill_color = dialog.get_fill_color()
        fill_pattern = dialog.get_fill_pattern()
        # Store the pattern and base color
        if hasattr(item, 'fill_pattern'):
            item.fill_pattern = fill_pattern
        if hasattr(item, 'fill_color'):
            item.fill_color = fill_color
        brush = create_pattern_brush(
            fill_pattern, fill_color, getattr(item, "fill_transform", None)
        )
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


def polygon_resize_apply(item: QGraphicsItem, geom: dict[str, Any]) -> None:
    """Apply a resize geometry dict to a ``PolygonItem`` - the ONE apply path.

    ``ResizeItemCommand`` calls this for ``execute``, ``undo`` **and** ``redo``,
    so this is the path an undo of a HOUSE resize re-enters, and it must
    re-derive the linked roof ridge exactly as ``_apply_resize`` does for the
    live drag. Found by the #364 senior-review round: it did not, which left
    the polygon restored and the ridge still sized for the *resized* house -
    measured 300 cm of drift on a 300->600 cm resize, persisted into the
    ``.ogp`` because the ridge is itself a serialized item.

    Module-level rather than a closure inside ``_on_resize_end`` so a test can
    drive the production function instead of re-implementing it: a test that
    copies the apply logic passes while the real one stays broken.
    ``setPos`` fires the item-change ridge hook first; the recompute below
    overwrites it wholesale. ``_update_area_label`` is here so this path and
    ``_apply_resize`` (the live drag) do not disagree: ``setPos`` only fires
    ``itemChange`` when the position actually changes, so a resize that holds
    ``pos`` fixed would otherwise leave a stale area label. See ADR-046.
    """
    if not isinstance(item, PolygonItem):
        return
    vertices = [QPointF(v["x"], v["y"]) for v in geom["vertices"]]
    item.setPolygon(QPolygonF(vertices))
    item.setPos(geom["pos_x"], geom["pos_y"])
    item.update_resize_handles()
    item._position_label()
    item._update_area_label()
    # Derived state: a HOUSE's roof ridge is a function of the polygon, so
    # every polygon-apply path must re-derive it. Adding a new apply path
    # without this call silently rots the invariant.
    item._update_ridge_on_boundary()
    # A resize re-enters this path from undo/redo while the polygon may be in
    # vertex edit mode; the dense sample's candidate set and the handle
    # positions must follow the new vertices (#594, senior review).
    if getattr(item, "_is_vertex_edit_mode", False):
        item._update_vertex_handles()


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
        brush = create_pattern_brush(pattern, color, self.fill_transform)
        self.setBrush(brush)

    def _setup_flags(self) -> None:
        """Configure item interaction flags."""
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.enable_device_coordinate_cache()

    def boundingRect(self) -> QRectF:
        """Return bounding rect, expanded for shadow."""
        base = super().boundingRect()
        m = self._shadow_margin()
        if m > 0:
            base = base.adjusted(-m, -m, m, m)
        return base

    def _find_ridge(self) -> "QGraphicsItem | None":
        """Look up the associated roof ridge through the one validated lookup.

        ``linked_ridge`` checks the reverse ``owner_polygon_id``, so a copied
        or stale id can never make this house adopt (and then move/delete)
        another house's ridge.
        """
        from open_garden_planner.ui.canvas.roof_ridge_link import linked_ridge

        return linked_ridge(self)

    def _update_ridge_on_boundary(self) -> None:
        """Recompute the linked roof ridge from the current polygon (issue #364).

        Called after a vertex edit, resize, or rotation. The ridge is
        **derived** geometry, so it is recomputed here through
        :func:`~open_garden_planner.core.roof_ridge.compute_roof_ridge_endpoints`
        — the one canonical computation shared with creation — rather than
        adjusted from wherever it currently sits.

        Two properties follow from recomputing instead of projecting, and both
        were defects before (see ADR-046 and §11.4):

        * **It is self-healing and undo-safe.** An earlier version re-projected
          the ridge's *existing* endpoints onto the boundary, which is a
          membrane: once an endpoint landed on the wrong edge it had no way
          back to canonical, and because the write bypassed the command system
          an undo that restored the polygon left the ridge behind. Drift
          accumulated over repeated edit/undo cycles. Deriving the ridge purely
          from the polygon means restoring the polygon *is* restoring the
          ridge, with no extra undo bookkeeping.
        * **It is rotation- and scale-correct.** The canonical endpoints are
          computed in the polygon's LOCAL frame and mapped through this item's
          full transform, so a rotated house gets a ridge along its rotated
          long axis. The projection path kept the old orientation, so a house
          rotated 90 degrees kept a ridge at 0 degrees — 180 cm off — and
          ``_paint_with_ridge`` mirrors the roof texture along this line, so
          the roof itself was wrong too.

        A ridge endpoint dragged by hand (see ``PolylineItem._move_vertex_to``,
        which still constrains it to this outline) is therefore *not* sticky: the
        next polygon edit returns it to canonical. That is the recorded
        decision — the ridge and the roof texture derived from it must agree.
        """
        from open_garden_planner.ui.canvas.roof_ridge_link import update_linked_ridge

        # Shared with RectangleItem (a rectangle converted to HOUSE): one
        # derivation, one place that knows how any HOUSE outline maps its ridge.
        update_linked_ridge(self)

    def _paint_with_ridge(self, painter: QPainter, ridge: "QGraphicsItem") -> None:
        """Paint a HOUSE polygon with tiles mirrored on each side of its ridge.

        The shared implementation lives in ``roof_paint.paint_roof_with_ridge``
        so a rectangle converted into a HOUSE (#690) draws the identical roof;
        this method keeps the polygon's own outline and brush/cockpit wiring.
        """
        paint_roof_with_ridge(
            painter,
            self,
            self.polygon(),
            ridge,
            self.brush(),
            self.pen(),
            self.fill_transform,
        )

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
        poly = self.polygon()

        # Degraded paint for an over-budget outline (issue #472): interactive
        # painting only, an unselected item only. Draw the exact outline with a
        # COSMETIC 1-px pen and no fill. A cosmetic pen is essential: Qt strokes
        # a wide solid pen by building a fill, which would leave this path
        # quadratic (issue #472 measurement), whereas a cosmetic stroke is linear
        # with a small constant and independent of the item's own pen width.
        #
        # "Interactive" is `is_interactive_paint` (the item's cache mode), NOT
        # `widget is not None`: Qt passes widget=0 for every CACHED paint and
        # every unselected canvas item is DeviceCoordinateCache, so a
        # widget-based test selected the empty set and the first shipped version
        # of this degrade never ran in the app (measured: a cached 1,024-vertex
        # comb repainted at full detail, 44.7 ms; 16,384 at 589 ms). Every
        # export, report, print and agent render path disables the cache first,
        # so those stay full detail, while the interactive view degrades.
        # This degrade is the ONLY level-of-detail pass in the canvas — the #409
        # low-zoom flat fill was removed in #503, measured to buy nothing.
        degrade = (
            poly.count() > MAX_FULL_DETAIL_VERTICES
            and not self.isSelected()
            and is_interactive_paint(self, widget)
        )
        if degrade:
            outline_pen = QPen(self.pen())
            outline_pen.setCosmetic(True)
            outline_pen.setWidthF(1.0)
            outline_pen.setStyle(Qt.PenStyle.SolidLine)
            painter.save()
            painter.setPen(outline_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(poly)
            painter.restore()
            return

        if self._shadows_enabled:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.SHADOW_COLOR)
            shadow_poly = poly.translated(
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

        # A GREENHOUSE's aluminium glazing bars over its glass fill (#768); the
        # ridge is the plan's linked one in the item's own frame.
        if self.object_type == ObjectType.GREENHOUSE:
            paint_greenhouse(
                painter,
                poly,
                self.pen(),
                ridge_points_local(self, ridge),
            )

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
        self.handle_item_change(change, value)
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
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.is_vertex_edit_mode:
                self._update_annotations()
            # Re-derive instead of translating by a delta: a reparent (ungroup)
            # also changes the local pos, and a delta would move the ridge twice
            # (review round 4). The derivation is self-healing and exact.
            self._update_ridge_on_boundary()
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

    def _move_vertex_to(self, index: int, pos: QPointF) -> None:
        """Move a polygon vertex and keep the attached ridge on the boundary."""
        super()._move_vertex_to(index, pos)
        # Re-project ridge endpoints when the polygon shape changes
        self._update_ridge_on_boundary()

    def _after_vertex_topology_change(self) -> None:
        """Keep a HOUSE's linked roof ridge attached after add/delete/undo."""
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

        # The module-level apply path, shared with the tests so they drive the
        # production function rather than a copy of it.
        apply_geometry = polygon_resize_apply

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

        # Add to undo stack without executing (geometry already applied). A bed
        # resize also re-decides which plants it holds, in the SAME undo step (#443).
        from open_garden_planner.core.commands import register_applied_with_membership

        register_applied_with_membership(scene, command_manager, command, self)

        # Clear stored initial polygon
        self._resize_initial_polygon = None

    def _on_rotation_end(self, initial_angle: float) -> None:
        """Called when rotation operation completes. Registers undo command."""
        # One implementation for every item type (issue #485): the command also
        # carries the partner corrections the live solver applied during the
        # gesture, so undo/redo move the angle and the partner together.
        from open_garden_planner.ui.canvas.geometry_apply import (
            register_rotation_command,
        )

        register_rotation_command(self, initial_angle)

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
        self.normalize_context_menu_selection()

        _ = QCoreApplication.translate
        menu = QMenu()

        group_actions = self.build_group_context_menu(menu)
        if group_actions.offered:
            menu.addSeparator()

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
        from open_garden_planner.core.object_types import is_plant_parent_type
        from open_garden_planner.ui.canvas.items.garden_item import BedMenuActions
        bed_actions = BedMenuActions()
        if is_plant_parent_type(self.object_type):
            soil = is_bed_type(self.object_type)
            bed_actions = self.build_bed_context_menu(
                menu,
                grid_enabled=self._grid_enabled,
                supports_grid=soil,
                supports_soil=soil,
            )

        menu.addSeparator()

        # Move to Layer submenu (hidden when project has only one layer)
        move_layer_menu = self._build_move_to_layer_menu(menu)

        # Arrange submenu (Bring to Front / Forward / Send Backward / Back)
        arrange_menu = self._build_arrange_menu(menu)

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
        from .common_menu import build_repeat_actions

        repeat_actions = build_repeat_actions(menu, "PolygonItem")

        # Boolean operations (union supports two or more closed shapes; the
        # other operations stay a two-shape relation)
        boolean_union_action = None
        boolean_intersect_action = None
        boolean_subtract_action = None
        array_along_path_action = None
        selected = self.scene().selectedItems()
        if len(selected) >= 2:
            from open_garden_planner.ui.canvas.items.circle_item import CircleItem
            from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
            from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
            from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

            shape_types = (PolygonItem, RectangleItem, CircleItem, EllipseItem)
            if all(isinstance(s, shape_types) for s in selected):
                menu.addSeparator()
                bool_menu = menu.addMenu(_("PolygonItem", "Boolean"))
                boolean_union_action = bool_menu.addAction(_("PolygonItem", "Union"))
                if len(selected) == 2:
                    boolean_intersect_action = bool_menu.addAction(
                        _("PolygonItem", "Intersect")
                    )
                    boolean_subtract_action = bool_menu.addAction(
                        _("PolygonItem", "Subtract")
                    )
            if len(selected) == 2 and any(isinstance(s, PolylineItem) for s in selected):
                array_along_path_action = menu.addAction(
                    _("PolygonItem", "Array Along Path...")
                )

        # Execute menu and handle result
        menu.addSeparator()
        lock_action = self.build_lock_context_menu(menu)
        action = menu.exec(event.screenPos())

        if self.dispatch_group_action(action, group_actions):
            return
        if self.dispatch_lock_action(action, lock_action):
            return
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
            # Delete the selection through the view: it owns linked ridges,
            # constraints and journal-note pruning (round-5 review of #690).
            from .common_menu import dispatch_delete_selection

            dispatch_delete_selection(self.scene())
        elif repeat_actions.dispatch(action, self.scene()):
            return
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
        elif arrange_menu and action and action.parent() is arrange_menu:
            self._dispatch_arrange(action.data())
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
