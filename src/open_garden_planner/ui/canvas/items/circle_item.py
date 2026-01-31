"""Circle item for the garden canvas."""

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
)

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType, StrokeStyle, get_style

from .garden_item import GardenItemMixin
from .resize_handle import ResizeHandlesMixin


def _show_properties_dialog(item: QGraphicsEllipseItem) -> None:
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


class CircleItem(ResizeHandlesMixin, GardenItemMixin, QGraphicsEllipseItem):
    """A circle shape on the garden canvas.

    Supports property object types with appropriate styling.
    Supports selection, movement, and resizing.
    """

    def __init__(
        self,
        center_x: float,
        center_y: float,
        radius: float,
        object_type: ObjectType = ObjectType.GENERIC_CIRCLE,
        name: str = "",
        metadata: dict[str, Any] | None = None,
        fill_pattern: FillPattern | None = None,
        stroke_style: StrokeStyle | None = None,
        layer_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize the circle item.

        Args:
            center_x: X coordinate of center
            center_y: Y coordinate of center
            radius: Radius of circle
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
        # QGraphicsEllipseItem uses bounding rect (top-left corner + width/height)
        # Convert center+radius to rect coordinates
        x = center_x - radius
        y = center_y - radius
        diameter = radius * 2
        QGraphicsEllipseItem.__init__(self, x, y, diameter, diameter)

        self._center = QPointF(center_x, center_y)
        self._radius = radius

        # Initialize resize handles
        self.init_resize_handles()

        self._setup_styling()
        self._setup_flags()
        self.initialize_label()

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type."""
        style = get_style(self.object_type) if self.object_type else get_style(ObjectType.GENERIC_CIRCLE)

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
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    @property
    def center(self) -> QPointF:
        """Get circle center point."""
        return self._center

    @property
    def radius(self) -> float:
        """Get circle radius."""
        return self._radius

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: Any,
    ) -> Any:
        """Handle item state changes.

        Shows/hides resize handles based on selection state.
        """
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value:  # Being selected
                self.show_resize_handles()
            else:  # Being deselected
                self.hide_resize_handles()

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
        """Apply a resize transformation to this circle.

        For circles, we maintain the circular shape by using the
        minimum of width/height to determine the new radius.

        Args:
            x: New x position of rect (in item coords)
            y: New y position of rect (in item coords)
            width: New width
            height: New height
            pos_x: New scene x position
            pos_y: New scene y position
        """
        # For circles, use the minimum dimension to maintain circular shape
        new_diameter = min(width, height)
        new_radius = new_diameter / 2.0

        # Calculate the center offset from the original bounding rect
        original_rect = self.rect()
        original_center_x = original_rect.x() + original_rect.width() / 2.0
        original_center_y = original_rect.y() + original_rect.height() / 2.0

        # Calculate new center based on resize direction
        # Use the center of the requested resize rect
        new_center_x = x + width / 2.0
        new_center_y = y + height / 2.0

        # Update the ellipse rect (centered on new center)
        new_x = new_center_x - new_radius
        new_y = new_center_y - new_radius
        self.setRect(new_x, new_y, new_diameter, new_diameter)

        # Update internal center and radius
        self._center = QPointF(new_center_x, new_center_y)
        self._radius = new_radius

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
            if isinstance(item, CircleItem):
                item.setRect(
                    geom['rect_x'],
                    geom['rect_y'],
                    geom['diameter'],
                    geom['diameter'],
                )
                item._center = QPointF(geom['center_x'], geom['center_y'])
                item._radius = geom['radius']
                item.setPos(geom['pos_x'], geom['pos_y'])
                item.update_resize_handles()
                item._position_label()

        old_geometry = {
            'rect_x': initial_rect.x(),
            'rect_y': initial_rect.y(),
            'diameter': initial_rect.width(),  # Circles have equal width/height
            'center_x': initial_rect.x() + initial_rect.width() / 2.0,
            'center_y': initial_rect.y() + initial_rect.height() / 2.0,
            'radius': initial_rect.width() / 2.0,
            'pos_x': initial_pos.x(),
            'pos_y': initial_pos.y(),
        }

        new_geometry = {
            'rect_x': current_rect.x(),
            'rect_y': current_rect.y(),
            'diameter': current_rect.width(),
            'center_x': self._center.x(),
            'center_y': self._center.y(),
            'radius': self._radius,
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

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle double-click to edit label inline."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_label_edit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show context menu on right-click."""
        # Select this item if not already selected
        if not self.isSelected():
            self.scene().clearSelection()
            self.setSelected(True)

        menu = QMenu()

        # Delete action
        delete_action = menu.addAction("Delete")

        menu.addSeparator()

        # Placeholder actions
        duplicate_action = menu.addAction("Duplicate")
        duplicate_action.setEnabled(False)  # Placeholder

        # Execute menu and handle result
        action = menu.exec(event.screenPos())

        if action == delete_action:
            self.scene().removeItem(self)

    def to_dict(self) -> dict:
        """Serialize the item to a dictionary for saving."""
        return {
            "type": "circle",
            "id": self.item_id,
            "center": {"x": self._center.x(), "y": self._center.y()},
            "radius": self._radius,
            "position": {"x": self.pos().x(), "y": self.pos().y()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CircleItem":
        """Create a circle from a dictionary."""
        center = data["center"]
        item = cls(center["x"], center["y"], data["radius"])
        item.setPos(data["position"]["x"], data["position"]["y"])
        return item
