"""Rectangle item for the garden canvas."""

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.furniture_renderer import is_furniture_type, render_furniture_pixmap
from open_garden_planner.core.object_types import ObjectType, StrokeStyle, get_style

from .garden_item import GardenItemMixin
from .resize_handle import RectVertexEditMixin, ResizeHandlesMixin, RotationHandleMixin


def _show_properties_dialog(item: QGraphicsRectItem) -> None:
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


class RectangleItem(RectVertexEditMixin, RotationHandleMixin, ResizeHandlesMixin, GardenItemMixin, QGraphicsRectItem):
    """A rectangle shape on the garden canvas.

    Supports property object types with appropriate styling.
    Supports selection, movement, resizing, rotation, and vertex editing.
    """

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        object_type: ObjectType = ObjectType.GENERIC_RECTANGLE,
        name: str = "",
        metadata: dict[str, Any] | None = None,
        fill_pattern: FillPattern | None = None,
        stroke_style: StrokeStyle | None = None,
        layer_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize the rectangle item.

        Args:
            x: X coordinate of top-left corner
            y: Y coordinate of top-left corner
            width: Width of rectangle
            height: Height of rectangle
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
        QGraphicsRectItem.__init__(self, x, y, width, height)

        # Initialize resize, rotation, and vertex editing handles
        self.init_resize_handles()
        self.init_rotation_handle()
        self.init_rect_vertex_edit()

        self._setup_styling()
        self._setup_flags()
        self.initialize_label()

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type."""
        style = get_style(self.object_type) if self.object_type else get_style(ObjectType.GENERIC_RECTANGLE)

        # Furniture types use SVG rendering — hide pen and brush
        if is_furniture_type(self.object_type):
            self.setPen(QPen(Qt.PenStyle.NoPen))
            self.setBrush(QBrush())
            return

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
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable, True)

    def boundingRect(self) -> QRectF:
        """Return bounding rect, expanded for shadow."""
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
        """Paint the rectangle item.

        For furniture types, renders an illustrated SVG instead of a
        flat colored rectangle. For non-furniture rectangles, delegates
        to the default rectangle painting.
        """
        # Draw painted shadow before the item itself
        if self._shadows_enabled:
            rect = self.rect()
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.SHADOW_COLOR)
            shadow_rect = rect.translated(self.SHADOW_OFFSET_X, self.SHADOW_OFFSET_Y)
            painter.drawRect(shadow_rect)
            painter.restore()

        if is_furniture_type(self.object_type):
            rect = self.rect()
            pixmap = render_furniture_pixmap(
                object_type=self.object_type,
                width=rect.width(),
                height=rect.height(),
            )
            if pixmap is not None:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawPixmap(rect.toAlignedRect(), pixmap)

                # Draw selection highlight
                if self.isSelected():
                    pen = QPen(QColor(0, 120, 215, 180))
                    pen.setWidthF(2.0)
                    pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)
                return

        # Fall back to standard rectangle painting
        super().paint(painter, option, widget)

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: Any,
    ) -> Any:
        """Handle item state changes.

        Shows/hides resize and rotation handles based on selection state.
        Exits vertex edit mode when deselected.
        Updates annotations when position changes.
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
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.is_vertex_edit_mode:
            self._update_rect_annotations()

        return super().itemChange(change, value)

    def _apply_resize(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        pos_x: float,
        pos_y: float,
    ) -> None:
        """Apply a resize transformation to this rectangle.

        Args:
            x: New x position of rect (in item coords)
            y: New y position of rect (in item coords)
            width: New width
            height: New height
            pos_x: New scene x position
            pos_y: New scene y position
        """
        # Update the rectangle geometry
        self.setRect(x, y, width, height)

        # Update position
        self.setPos(pos_x, pos_y)

        # Update resize handles
        self.update_resize_handles()

        # Update label position
        self._position_label()

    def _on_resize_end(
        self,
        initial_rect: QRectF | None,
        initial_pos: QPointF | None,
    ) -> None:
        """Called when resize operation completes. Registers undo command."""
        if initial_rect is None or initial_pos is None:
            return

        scene = self.scene()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        # Get current geometry
        current_rect = self.rect()
        current_pos = self.pos()

        # Only register command if geometry actually changed
        if (initial_rect == current_rect and initial_pos == current_pos):
            return

        from open_garden_planner.core.commands import ResizeItemCommand

        def apply_geometry(item: QGraphicsItem, geom: dict[str, Any]) -> None:
            """Apply geometry to the item."""
            if isinstance(item, RectangleItem):
                item.setRect(
                    geom['rect_x'],
                    geom['rect_y'],
                    geom['width'],
                    geom['height'],
                )
                item.setPos(geom['pos_x'], geom['pos_y'])
                item.update_resize_handles()
                item._position_label()

        old_geometry = {
            'rect_x': initial_rect.x(),
            'rect_y': initial_rect.y(),
            'width': initial_rect.width(),
            'height': initial_rect.height(),
            'pos_x': initial_pos.x(),
            'pos_y': initial_pos.y(),
        }

        new_geometry = {
            'rect_x': current_rect.x(),
            'rect_y': current_rect.y(),
            'width': current_rect.width(),
            'height': current_rect.height(),
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
            if isinstance(item, RectangleItem):
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

        menu = QMenu()

        # Edit vertices action
        if self.is_vertex_edit_mode:
            exit_edit_action = menu.addAction("Exit Vertex Edit Mode")
            edit_vertices_action = None
        else:
            edit_vertices_action = menu.addAction("Edit Vertices")
            exit_edit_action = None

        # Edit label action
        edit_label_action = menu.addAction("Edit Label")

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction("Delete")

        menu.addSeparator()

        # Duplicate action
        duplicate_action = menu.addAction("Duplicate")

        # Linear array action
        linear_array_action = menu.addAction("Create Linear Array...")

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
            # Exit vertex edit mode
            self.exit_vertex_edit_mode()
        elif action == edit_label_action:
            # Edit the label
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

    @classmethod
    def from_rect(cls, rect: QRectF) -> "RectangleItem":
        """Create a RectangleItem from a QRectF.

        Args:
            rect: The rectangle geometry

        Returns:
            A new RectangleItem
        """
        return cls(rect.x(), rect.y(), rect.width(), rect.height())
