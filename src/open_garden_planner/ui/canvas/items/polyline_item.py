"""Polyline item for the garden canvas."""

import uuid
from typing import Any

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.item_look import (
    adopt_pen,
    apply_line_look,
    copy_visual_style,
    line_look_for_preset,
)
from open_garden_planner.core.object_types import (
    ObjectType,
    PathFenceStyle,
    get_style,
)

from .garden_item import GardenItemMixin
from .path_style_paint import STYLES_PAINTED, PathStylePaint, style_paint_reach
from .resize_handle import PolylineVertexEditMixin, RotationHandleMixin


class PolylineItem(PolylineVertexEditMixin, RotationHandleMixin, GardenItemMixin, QGraphicsPathItem):
    """A polyline (open path) on the garden canvas.

    Used for fences, walls, paths, and other linear features.
    Supports selection, movement, rotation, and style presets.
    """

    def __init__(
        self,
        points: list[QPointF],
        object_type: ObjectType = ObjectType.FENCE,
        name: str = "",
        layer_id: uuid.UUID | None = None,
        path_fence_style: PathFenceStyle = PathFenceStyle.NONE,
    ) -> None:
        """Initialize the polyline item.

        Args:
            points: List of points defining the polyline
            object_type: Type of property object
            name: Optional name/label for the object
            layer_id: Layer ID this item belongs to (optional)
            path_fence_style: Visual style preset for paths/fences
        """
        GardenItemMixin.__init__(self, object_type=object_type, name=name, layer_id=layer_id)

        self._path_fence_style = path_fence_style

        # Create path from points
        path = QPainterPath()
        if points:
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)

        QGraphicsPathItem.__init__(self, path)

        self._points = points.copy()

        # Initialize rotation handle and vertex editing
        self.init_rotation_handle()
        self.init_vertex_edit()

        self._setup_styling()
        self._setup_flags()
        self.initialize_label()

    @property
    def points(self) -> list[QPointF]:
        """Get the polyline points."""
        return self._points.copy()

    @property
    def point_count(self) -> int:
        """How many points the polyline has — without copying them (``points`` does)."""
        return len(self._points)

    def clone_with_points(self, new_points: list[QPointF]) -> "PolylineItem":
        """Return a new PolylineItem with identical styling but a different point list.

        Args:
            new_points: Replacement points in item-local coordinates.

        Returns:
            A new PolylineItem not yet added to any scene.
        """
        clone = PolylineItem(
            points=new_points,
            object_type=self.object_type,
            name=self.name,
            layer_id=self.layer_id,
            path_fence_style=self._path_fence_style,
        )
        copy_visual_style(self, clone)  # brush, pen and the stroke attributes
        return clone

    @property
    def path_fence_style(self) -> PathFenceStyle:
        """Get the path/fence style preset."""
        return self._path_fence_style

    @path_fence_style.setter
    def path_fence_style(self, value: PathFenceStyle) -> None:
        """Set the path/fence style preset and update visuals."""
        if value == self._path_fence_style:
            return
        if hasattr(self, 'prepareGeometryChange'):
            self.prepareGeometryChange()
        self._path_fence_style = value
        if hasattr(self, 'update'):
            self.update()

    def setPen(self, pen: QPen) -> None:
        """Notify while the old pen still determines our extra styled bounds."""
        self.prepareGeometryChange()
        super().setPen(pen)

    def apply_style_preset(self) -> None:
        """Apply visual properties from the current style preset.

        Updates stroke color and width from the preset defaults.
        """
        if self._path_fence_style == PathFenceStyle.NONE:
            return
        apply_line_look(self, line_look_for_preset(self, self._path_fence_style))

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type and style preset.

        Construction uses the stored stroke attributes, else the type defaults,
        and the line states the pen it ends up with. Type and preset history use
        ``apply_line_look`` to restore snapshots. A line used to state no
        stroke until it had been through a project file: undoing a width or dash
        edit, or a type change, on a freshly drawn line raised on the ``None``.
        """
        style = get_style(self.object_type)

        pen = QPen(self.stroke_color if self.stroke_color is not None else style.stroke_color)
        pen.setWidthF(self.stroke_width if self.stroke_width is not None else style.stroke_width)
        if self.stroke_style is not None:  # a line that states none is solid, whatever its type
            pen.setStyle(self.stroke_style.to_qt_pen_style())
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        adopt_pen(self, pen)  # the pen AND the stroke attributes (core.item_look)

        # Polylines typically don't have fill
        self.setBrush(QBrush(QColor(0, 0, 0, 0)))

        # Apply style preset if set
        if self._path_fence_style != PathFenceStyle.NONE:
            self.apply_style_preset()

    def _setup_flags(self) -> None:
        """Configure item interaction flags."""
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.enable_device_coordinate_cache()

    def _find_owner_polygon(self) -> "QGraphicsItem | None":
        """Look up the HOUSE polygon that owns this ridge via metadata."""
        pid = self.get_metadata("owner_polygon_id") if hasattr(self, "get_metadata") else None
        if not pid:
            return None
        scene = self.scene()
        if scene is None:
            return None
        for item in scene.items():
            if hasattr(item, "item_id") and str(item.item_id) == pid:
                return item
        return None

    def _move_vertex_to(self, index: int, pos: QPointF) -> None:
        """Move a vertex, constraining ROOF_RIDGE endpoints to the polygon boundary."""
        if self.object_type == ObjectType.ROOF_RIDGE:
            owner = self._find_owner_polygon()
            if owner is not None and hasattr(owner, "polygon"):
                from .polygon_item import _project_to_polygon_boundary

                # Convert new position from ridge-local → scene → polygon-local
                scene_pt = self.mapToScene(pos)
                local_pt = owner.mapFromScene(scene_pt)
                projected = _project_to_polygon_boundary(owner.polygon(), local_pt)
                # Convert back to ridge-local
                pos = self.mapFromScene(owner.mapToScene(projected))

        super()._move_vertex_to(index, pos)

    def boundingRect(self) -> QRectF:
        """Return bounding rect, expanded for shadow and style decorations."""
        base = super().boundingRect()
        # Extra margin for styled rendering (wider than stroke)
        style_margin = self.pen().widthF() / 2.0 + 2.0
        base = base.adjusted(-style_margin, -style_margin, style_margin, style_margin)
        if self._path_fence_style in STYLES_PAINTED:
            reach = style_paint_reach(self.pen().widthF())
            painted = self.path().controlPointRect().adjusted(-reach, -reach, reach, reach)
            base = base.united(painted)
        m = self._shadow_margin()
        if m > 0:
            base = base.adjusted(-m, -m, m, m)
        return base

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the polyline with style-specific rendering and optional shadow."""
        # Draw shadow first
        if self._shadows_enabled:
            self._paint_shadow(painter)

        # Roof ridge: custom cap rendering regardless of path_fence_style
        if self.object_type == ObjectType.ROOF_RIDGE:
            self._paint_roof_ridge(painter)
            return

        # Draw style-specific rendering — the painters are shared with the 3D ground
        # bake (path_style_paint.py): one implementation, two callers. A plain line
        # (and a style without a painter) is the base class's stroke, as it always
        # was: nothing is built for it.
        style = self._path_fence_style
        if style in STYLES_PAINTED:
            PathStylePaint(self._points, self.pen(), self.path()).paint(painter, style)
            self._paint_selection(painter, option)
        else:
            super().paint(painter, option, widget)

    def _paint_shadow(self, painter: QPainter) -> None:
        """Paint drop shadow for the polyline."""
        painter.save()
        shadow_pen = QPen(self.SHADOW_COLOR)
        shadow_pen.setWidthF(self.pen().widthF())
        shadow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        shadow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(shadow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        shadow_path = self.path().translated(
            self.SHADOW_OFFSET_X, self.SHADOW_OFFSET_Y,
        )
        painter.drawPath(shadow_path)
        painter.restore()

    def _paint_roof_ridge(self, painter: QPainter) -> None:
        """Paint a roof ridge cap with layered width and highlight."""
        import math as _math

        path = self.path()
        pts = self._points
        if len(pts) < 2:
            painter.setPen(self.pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Layer 1 – wide dark shadow base (ridge cap sides)
        pen_base = QPen(QColor(70, 45, 20))
        pen_base.setWidthF(8.0)
        pen_base.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_base.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen_base)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Layer 2 – main ridge body (terracotta)
        pen_body = QPen(QColor(155, 90, 52))
        pen_body.setWidthF(5.5)
        pen_body.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_body.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen_body)
        painter.drawPath(path)

        # Layer 3 – central highlight (peak of the ridge cap)
        pen_highlight = QPen(QColor(210, 150, 100))
        pen_highlight.setWidthF(1.8)
        pen_highlight.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_highlight)
        painter.drawPath(path)

        # Draw small semi-circular caps at each end segment
        for i in range(len(pts) - 1):
            seg_dx = pts[i + 1].x() - pts[i].x()
            seg_dy = pts[i + 1].y() - pts[i].y()
            seg_len = _math.sqrt(seg_dx * seg_dx + seg_dy * seg_dy)
            if seg_len < 1e-6:
                continue
            ux = seg_dx / seg_len
            uy = seg_dy / seg_len
            # Cap circles at each end point
            for end_pt in (pts[i], pts[i + 1]):
                r = 4.0
                painter.setPen(QPen(QColor(70, 45, 20), 1.0))
                painter.setBrush(QBrush(QColor(155, 90, 52)))
                painter.drawEllipse(end_pt, r, r)
                # Highlight on cap
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(210, 150, 100, 160)))
                painter.drawEllipse(
                    QPointF(end_pt.x() - ux * 0.5, end_pt.y() - uy * 0.5), r * 0.45, r * 0.45
                )

        painter.restore()

    def _paint_selection(self, painter: QPainter, option: QStyleOptionGraphicsItem) -> None:
        """Draw selection highlight if the item is selected."""
        from PyQt6.QtWidgets import QStyle
        if option.state & QStyle.StateFlag.State_Selected:
            painter.save()
            sel_pen = QPen(QColor(0, 120, 215), 1.0, Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
            painter.restore()

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: Any,
    ) -> Any:
        """Handle item state changes.

        Shows/hides rotation handle based on selection state.
        Exits vertex edit mode when deselected.
        Updates annotations when position changes.
        """
        self.handle_item_change(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value:  # Being selected
                if not self.is_vertex_edit_mode:
                    self.show_rotation_handle()
            else:  # Being deselected
                if self.is_vertex_edit_mode:
                    self.exit_vertex_edit_mode()
                self.hide_rotation_handle()
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.is_vertex_edit_mode:
            self._update_annotations()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
            self.remove_rotation_handle()

        return super().itemChange(change, value)

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

        # US-D2.2: the canonical rotate apply path (ui.canvas.geometry_apply),
        # shared with the Agent API's rotate_object. Every item class had an
        # identical private copy of this one-liner; a shared name means the
        # agent and the drag handles provably rotate the same way.
        from open_garden_planner.ui.canvas.geometry_apply import apply_rotation

        command = RotateItemCommand(
            self,
            initial_angle,
            current_angle,
            apply_rotation,
        )

        # Add to undo stack without executing (rotation already applied)
        command_manager.register_applied(command)

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
            exit_edit_action = menu.addAction(_("PolylineItem", "Exit Vertex Edit Mode"))
            edit_vertices_action = None
        else:
            edit_vertices_action = menu.addAction(_("PolylineItem", "Edit Vertices"))
            exit_edit_action = None

        # Edit label action
        edit_label_action = menu.addAction(_("PolylineItem", "Edit Label"))

        menu.addSeparator()

        # Move to Layer submenu (hidden when project has only one layer)
        move_layer_menu = self._build_move_to_layer_menu(menu)

        # Arrange submenu (Bring to Front / Forward / Send Backward / Back)
        arrange_menu = self._build_arrange_menu(menu)

        # Change Type submenu
        from open_garden_planner.core.object_types import get_valid_types_for_shape
        change_type_menu = self._build_change_type_menu(menu, get_valid_types_for_shape("polyline"))

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction(_("PolylineItem", "Delete"))

        menu.addSeparator()

        # Duplicate action
        duplicate_action = menu.addAction(_("PolylineItem", "Duplicate"))

        # Linear array action
        linear_array_action = menu.addAction(_("PolylineItem", "Create Linear Array..."))

        # Grid array action
        grid_array_action = menu.addAction(_("PolylineItem", "Create Grid Array..."))

        # Circular array action
        circular_array_action = menu.addAction(_("PolylineItem", "Create Circular Array..."))

        # Array along path (requires exactly 2 selected, one being a polyline)
        array_along_path_action = None
        selected = self.scene().selectedItems()
        if len(selected) == 2:
            array_along_path_action = menu.addAction(_("PolylineItem", "Array Along Path..."))

        # Execute menu and handle result
        action = menu.exec(event.screenPos())

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
            self.exit_vertex_edit_mode()
        elif action == edit_label_action:
            self.start_label_edit()
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
