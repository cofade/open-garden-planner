"""Ellipse item for the garden canvas."""

import uuid
from typing import Any

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType, StrokeStyle, get_style

from .garden_item import GardenItemMixin
from .resize_handle import ResizeHandlesMixin, RotationHandleMixin


class EllipseItem(RotationHandleMixin, ResizeHandlesMixin, GardenItemMixin, QGraphicsEllipseItem):
    """An ellipse shape on the garden canvas.

    Stored as a bounding QRectF (same as QGraphicsEllipseItem). Semi-axes are
    rect().width()/2 and rect().height()/2. Rotation is handled via rotation_angle.
    """

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        object_type: ObjectType = ObjectType.GENERIC_ELLIPSE,
        name: str = "",
        metadata: dict[str, Any] | None = None,
        fill_pattern: FillPattern | None = None,
        stroke_style: StrokeStyle | None = None,
        layer_id: uuid.UUID | None = None,
    ) -> None:
        style = get_style(object_type)
        if fill_pattern is None:
            fill_pattern = style.fill_pattern
        if stroke_style is None:
            stroke_style = style.stroke_style

        GardenItemMixin.__init__(
            self, object_type=object_type, name=name, metadata=metadata,
            fill_pattern=fill_pattern, fill_color=style.fill_color,
            stroke_color=style.stroke_color, stroke_width=style.stroke_width,
            stroke_style=stroke_style, layer_id=layer_id,
        )
        QGraphicsEllipseItem.__init__(self, x, y, width, height)

        self.init_resize_handles()
        self.init_rotation_handle()

        self._setup_styling()
        self._setup_flags()
        self.initialize_label()

    def _setup_styling(self) -> None:
        style = get_style(self.object_type) if self.object_type else get_style(ObjectType.GENERIC_ELLIPSE)
        stroke_color = self.stroke_color if self.stroke_color is not None else style.stroke_color
        stroke_width = self.stroke_width if self.stroke_width is not None else style.stroke_width
        stroke_style = self.stroke_style if self.stroke_style is not None else style.stroke_style

        pen = QPen(stroke_color)
        pen.setWidthF(stroke_width)
        pen.setStyle(stroke_style.to_qt_pen_style())
        self.setPen(pen)

        pattern = self.fill_pattern if self.fill_pattern is not None else style.fill_pattern
        color = self.fill_color if self.fill_color is not None else style.fill_color
        self.setBrush(create_pattern_brush(pattern, color))

    def _setup_flags(self) -> None:
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsFocusable, True)

    def boundingRect(self) -> QRectF:
        base = super().boundingRect()
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
        if self._shadows_enabled:
            rect = self.rect()
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.SHADOW_COLOR)
            painter.drawEllipse(rect.translated(self.SHADOW_OFFSET_X, self.SHADOW_OFFSET_Y))
            painter.restore()
        super().paint(painter, option, widget)

        # F9: soil-mismatch border for bed-typed ellipses (US-12.10d).
        from open_garden_planner.core.object_types import is_bed_type
        if is_bed_type(self.object_type):
            self._draw_soil_mismatch_border(painter)

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: Any,
    ) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value:
                self.show_resize_handles()
                self.show_rotation_handle()
            else:
                self.hide_resize_handles()
                self.hide_rotation_handle()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
            self.remove_rotation_handle()
        elif change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged,
        ):
            self._update_area_label()
        return super().itemChange(change, value)

    def _compute_area_cm2(self) -> float | None:
        import math
        r = self.rect()
        return math.pi * (r.width() / 2.0) * (r.height() / 2.0)

    def _apply_resize(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        pos_x: float,
        pos_y: float,
    ) -> None:
        self.setRect(x, y, width, height)
        self.setPos(pos_x, pos_y)
        self.update_resize_handles()
        self._position_label()
        self._update_area_label()

    def _on_resize_end(
        self,
        initial_rect: QRectF | None,
        initial_pos: QPointF | None,
    ) -> None:
        if initial_rect is None or initial_pos is None:
            return

        scene = self.scene()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        current_rect = self.rect()
        current_pos = self.pos()

        if initial_rect == current_rect and initial_pos == current_pos:
            return

        from open_garden_planner.core.commands import ResizeItemCommand

        def apply_geometry(item: QGraphicsItem, geom: dict[str, Any]) -> None:
            if isinstance(item, EllipseItem):
                item.setRect(geom['rect_x'], geom['rect_y'], geom['width'], geom['height'])
                item.setPos(geom['pos_x'], geom['pos_y'])
                item.update_resize_handles()
                item._position_label()

        old_geometry = {
            'rect_x': initial_rect.x(), 'rect_y': initial_rect.y(),
            'width': initial_rect.width(), 'height': initial_rect.height(),
            'pos_x': initial_pos.x(), 'pos_y': initial_pos.y(),
        }
        new_geometry = {
            'rect_x': current_rect.x(), 'rect_y': current_rect.y(),
            'width': current_rect.width(), 'height': current_rect.height(),
            'pos_x': current_pos.x(), 'pos_y': current_pos.y(),
        }

        command = ResizeItemCommand(self, old_geometry, new_geometry, apply_geometry)
        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def _on_rotation_end(self, initial_angle: float) -> None:
        scene = self.scene()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        current_angle = self.rotation_angle
        if abs(initial_angle - current_angle) < 0.01:
            return

        from open_garden_planner.core.commands import RotateItemCommand

        def apply_rotation(item: QGraphicsItem, angle: float) -> None:
            if isinstance(item, EllipseItem):
                item._apply_rotation(angle)

        command = RotateItemCommand(self, initial_angle, current_angle, apply_rotation)
        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_label_edit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        if not self.isSelected():
            self.scene().clearSelection()
            self.setSelected(True)

        _ = QCoreApplication.translate
        menu = QMenu()

        edit_label_action = menu.addAction(_("EllipseItem", "Edit Label"))

        # US-12.10a: Add soil test entry for bed-typed ellipses
        from open_garden_planner.core.object_types import is_bed_type
        add_soil_test_action = None
        if is_bed_type(self.object_type):
            menu.addSeparator()
            add_soil_test_action = menu.addAction(_("EllipseItem", "Add soil test…"))

        menu.addSeparator()

        move_layer_menu = self._build_move_to_layer_menu(menu)

        from open_garden_planner.core.object_types import get_valid_types_for_shape
        change_type_menu = self._build_change_type_menu(menu, get_valid_types_for_shape("ellipse"))

        # Show Area toggle
        show_area_action = menu.addAction(_("EllipseItem", "Show Area"))
        show_area_action.setCheckable(True)
        show_area_action.setChecked(self._area_label_visible)

        menu.addSeparator()

        delete_action = menu.addAction(_("EllipseItem", "Delete"))

        menu.addSeparator()

        duplicate_action = menu.addAction(_("EllipseItem", "Duplicate"))
        linear_array_action = menu.addAction(_("EllipseItem", "Create Linear Array..."))
        grid_array_action = menu.addAction(_("EllipseItem", "Create Grid Array..."))
        circular_array_action = menu.addAction(_("EllipseItem", "Create Circular Array..."))

        boolean_union_action = None
        boolean_intersect_action = None
        boolean_subtract_action = None
        array_along_path_action = None
        selected = self.scene().selectedItems()
        if len(selected) == 2:
            from open_garden_planner.ui.canvas.items.circle_item import CircleItem
            from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
            from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
            from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

            shape_types = (PolygonItem, RectangleItem, CircleItem, EllipseItem)
            if all(isinstance(s, shape_types) for s in selected):
                menu.addSeparator()
                bool_menu = menu.addMenu(_("EllipseItem", "Boolean"))
                boolean_union_action = bool_menu.addAction(_("EllipseItem", "Union"))
                boolean_intersect_action = bool_menu.addAction(_("EllipseItem", "Intersect"))
                boolean_subtract_action = bool_menu.addAction(_("EllipseItem", "Subtract"))
            if any(isinstance(s, PolylineItem) for s in selected):
                array_along_path_action = menu.addAction(
                    _("EllipseItem", "Array Along Path...")
                )

        action = menu.exec(event.screenPos())

        if action == edit_label_action:
            self.start_label_edit()
        elif action == add_soil_test_action and add_soil_test_action is not None:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views and hasattr(views[0], "request_soil_test"):
                    views[0].request_soil_test(str(self.item_id), self.name)
        elif action == show_area_action:
            self.area_label_visible = not self._area_label_visible
        elif action == delete_action:
            scene = self.scene()
            for item in scene.selectedItems():
                scene.removeItem(item)
        elif action == duplicate_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views and hasattr(views[0], "duplicate_selected"):
                    views[0].duplicate_selected()
        elif action == linear_array_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views and hasattr(views[0], "create_linear_array"):
                    views[0].create_linear_array()
        elif action == grid_array_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views and hasattr(views[0], "create_grid_array"):
                    views[0].create_grid_array()
        elif action == circular_array_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views and hasattr(views[0], "create_circular_array"):
                    views[0].create_circular_array()
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
