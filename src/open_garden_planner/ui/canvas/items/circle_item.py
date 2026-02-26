"""Circle item for the garden canvas."""

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
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
from open_garden_planner.core.furniture_renderer import is_furniture_type, render_furniture_pixmap
from open_garden_planner.core.object_types import ObjectType, StrokeStyle, get_style
from open_garden_planner.core.plant_renderer import (
    PlantCategory,
    is_plant_type,
    render_plant_pixmap,
)

from .garden_item import GardenItemMixin
from .resize_handle import (
    AnnotationLabel,
    ResizeHandlesMixin,
    RotationHandleMixin,
    _format_coordinate,
    _format_edge_length,
)


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


class CircleItem(RotationHandleMixin, ResizeHandlesMixin, GardenItemMixin, QGraphicsEllipseItem):
    """A circle shape on the garden canvas.

    Supports property object types with appropriate styling.
    Supports selection, movement, resizing, and rotation.
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
        self._plant_category: PlantCategory | None = None
        self._plant_species: str = ""

        # Initialize resize and rotation handles
        self.init_resize_handles()
        self.init_rotation_handle()

        self._diameter_label: AnnotationLabel | None = None
        self._center_label: AnnotationLabel | None = None

        self._setup_styling()
        self._setup_flags()
        self.initialize_label()

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type."""
        style = get_style(self.object_type) if self.object_type else get_style(ObjectType.GENERIC_CIRCLE)

        # Plant and furniture types use SVG rendering — hide pen and brush
        if is_plant_type(self.object_type) or is_furniture_type(self.object_type):
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
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    @property
    def plant_category(self) -> PlantCategory | None:
        """Plant category for SVG shape selection."""
        return self._plant_category

    @plant_category.setter
    def plant_category(self, value: PlantCategory | None) -> None:
        """Set the plant category and trigger repaint."""
        self._plant_category = value
        self.update()

    @property
    def plant_species(self) -> str:
        """Plant species name for SVG lookup."""
        return self._plant_species

    @plant_species.setter
    def plant_species(self, value: str) -> None:
        """Set the plant species and trigger repaint."""
        self._plant_species = value
        self.update()

    # Scale factor to fill the circle area (SVGs have organic internal padding)
    _PLANT_FILL_SCALE = 1.15

    def boundingRect(self) -> QRectF:
        """Return bounding rect, expanded for plant SVG overflow and shadow."""
        base = super().boundingRect()
        if is_plant_type(self.object_type):
            rect = self.rect()
            overflow = rect.width() * (self._PLANT_FILL_SCALE - 1.0) / 2.0
            base = base.adjusted(-overflow, -overflow, overflow, overflow)
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
        """Paint the circle item.

        For plant types (TREE, SHRUB, PERENNIAL), renders an illustrated
        SVG plant shape instead of a flat colored ellipse. The SVG is
        scaled up slightly so its organic edges touch/fill the circle
        boundary rather than floating inside it.

        For non-plant circles, delegates to the default ellipse painting.
        """
        # Draw painted shadow before the item itself
        if self._shadows_enabled:
            rect = self.rect()
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.SHADOW_COLOR)
            shadow_rect = rect.translated(self.SHADOW_OFFSET_X, self.SHADOW_OFFSET_Y)
            painter.drawEllipse(shadow_rect)
            painter.restore()

        if is_plant_type(self.object_type):
            rect = self.rect()
            diameter = rect.width()

            # Render at a larger size so organic shapes fill the circle
            render_diameter = diameter * self._PLANT_FILL_SCALE

            pixmap = render_plant_pixmap(
                object_type=self.object_type,
                diameter=render_diameter,
                item_id=str(self._item_id),
                species=self._plant_species,
                category=self._plant_category,
                tint_color=self.fill_color,
            )

            if pixmap is not None:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                # Center the scaled-up pixmap over the circle area
                overflow = diameter * (self._PLANT_FILL_SCALE - 1.0) / 2.0
                draw_rect = QRectF(
                    rect.x() - overflow,
                    rect.y() - overflow,
                    render_diameter,
                    render_diameter,
                )
                painter.drawPixmap(draw_rect.toAlignedRect(), pixmap)

                # Draw selection highlight
                if self.isSelected():
                    pen = QPen(QColor(0, 120, 215, 180))
                    pen.setWidthF(2.0)
                    pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(rect)
                return

        if is_furniture_type(self.object_type):
            rect = self.rect()
            diameter = rect.width()
            pixmap = render_furniture_pixmap(
                object_type=self.object_type,
                width=diameter,
                height=diameter,
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
                    painter.drawEllipse(rect)
                return

        # Fall back to standard ellipse painting for non-plant/furniture circles
        super().paint(painter, option, widget)

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

        Shows/hides resize and rotation handles based on selection state.
        """
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value:  # Being selected
                self.show_resize_handles()
                self.show_rotation_handle()
                self._show_circle_annotations()
            else:  # Being deselected
                self.hide_resize_handles()
                self.hide_rotation_handle()
                self._hide_circle_annotations()
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._update_circle_annotations()

        return super().itemChange(change, value)

    def _show_circle_annotations(self) -> None:
        """Show diameter and center coordinate annotations."""
        rect = self.rect()
        diameter_cm = rect.width()
        center_item = QPointF(rect.x() + rect.width() / 2, rect.y() + rect.height() / 2)
        center_scene = self.mapToScene(center_item)

        # Center coordinate label
        if self._center_label is None:
            self._center_label = AnnotationLabel(self)
        self._center_label.set_text(_format_coordinate(center_scene.x(), center_scene.y()))
        self._center_label.setPos(center_item.x(), center_item.y())
        self._center_label.show()

        # Diameter label at the right edge midpoint
        right_mid = QPointF(rect.right(), rect.y() + rect.height() / 2)
        if self._diameter_label is None:
            self._diameter_label = AnnotationLabel(self)
        self._diameter_label.set_text(f"\u2300 {_format_edge_length(diameter_cm)}")
        self._diameter_label.setPos(right_mid.x(), right_mid.y())
        self._diameter_label.show()

    def _hide_circle_annotations(self) -> None:
        """Hide diameter and center coordinate annotations."""
        if self._center_label is not None:
            self._center_label.hide()
        if self._diameter_label is not None:
            self._diameter_label.hide()

    def _update_circle_annotations(self) -> None:
        """Update annotations after resize."""
        if self._center_label is None or not self._center_label.isVisible():
            return

        rect = self.rect()
        diameter_cm = rect.width()
        center_item = QPointF(rect.x() + rect.width() / 2, rect.y() + rect.height() / 2)
        center_scene = self.mapToScene(center_item)

        self._center_label.set_text(_format_coordinate(center_scene.x(), center_scene.y()))
        self._center_label.setPos(center_item.x(), center_item.y())

        right_mid = QPointF(rect.right(), rect.y() + rect.height() / 2)
        if self._diameter_label is not None:
            self._diameter_label.set_text(f"\u2300 {_format_edge_length(diameter_cm)}")
            self._diameter_label.setPos(right_mid.x(), right_mid.y())

    def _on_resize_start(self) -> None:
        """Called when a resize operation starts. Store initial geometry."""
        # Store the rect (not boundingRect) for accurate calculations
        self._resize_initial_rect = self.rect()
        self._resize_initial_pos = self.pos()

    def _apply_resize(
        self,
        _x: float,
        _y: float,
        width: float,
        height: float,
        pos_x: float,
        pos_y: float,
    ) -> None:
        """Apply a resize transformation to this circle.

        For circles, we maintain the circular shape by using the
        minimum of width/height to determine the new radius.

        Args:
            _x: New x position of rect (in item coords) - unused for circles
            _y: New y position of rect (in item coords) - unused for circles
            width: New width
            height: New height
            pos_x: New scene x position
            pos_y: New scene y position
        """
        # Get initial state (stored when resize started)
        if not hasattr(self, '_resize_initial_rect') or self._resize_initial_rect is None:
            self._resize_initial_rect = self.rect()
        if not hasattr(self, '_resize_initial_pos') or self._resize_initial_pos is None:
            self._resize_initial_pos = self.pos()

        init_rect = self._resize_initial_rect
        init_pos = self._resize_initial_pos

        # For circles, use the minimum dimension to maintain circular shape
        new_diameter = min(width, height)
        new_radius = new_diameter / 2.0

        # Determine which edges are fixed based on position change
        # If pos_x stayed the same, left edge is fixed (we're dragging right)
        # If pos_x changed, right edge is fixed (we're dragging left)
        left_edge_fixed = abs(pos_x - init_pos.x()) < 0.01
        top_edge_fixed = abs(pos_y - init_pos.y()) < 0.01

        # Calculate new position to keep the appropriate edges fixed
        if left_edge_fixed:  # Dragging right edge, keep left fixed
            # Calculate left edge position in scene coords
            left_edge_scene = init_pos.x() + init_rect.x()
            # Position circle so its left edge stays at this position
            new_pos_x = left_edge_scene
        else:  # Dragging left edge, keep right fixed
            # Calculate right edge position in scene coords
            right_edge_scene = init_pos.x() + init_rect.x() + init_rect.width()
            # Position circle so its right edge stays at this position
            new_pos_x = right_edge_scene - new_diameter

        if top_edge_fixed:  # Dragging bottom edge, keep top fixed
            # Calculate top edge position in scene coords
            top_edge_scene = init_pos.y() + init_rect.y()
            # Position circle so its top edge stays at this position
            new_pos_y = top_edge_scene
        else:  # Dragging top edge, keep bottom fixed
            # Calculate bottom edge position in scene coords
            bottom_edge_scene = init_pos.y() + init_rect.y() + init_rect.height()
            # Position circle so its bottom edge stays at this position
            new_pos_y = bottom_edge_scene - new_diameter

        # Set the rect at origin in item coordinates
        self.setRect(0, 0, new_diameter, new_diameter)

        # Update internal center and radius (in item coordinates)
        self._center = QPointF(new_radius, new_radius)
        self._radius = new_radius

        # Update position
        self.setPos(new_pos_x, new_pos_y)

        # Update dimension display with actual circular dimensions
        if hasattr(self, '_dimension_display') and self._dimension_display is not None:
            # Use the actual constrained diameter (not the requested width/height)
            # Get handle position for display positioning (approximate from center)
            display_pos = self.scenePos() + QPointF(new_diameter, new_diameter)
            self._dimension_display.update_dimensions(
                new_diameter,
                new_diameter,
                display_pos,
            )

        # Update resize handles
        self.update_resize_handles()

        # Update label position
        self._position_label()

        # Update annotations
        self._update_circle_annotations()

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

        # Collect EQUAL-constraint partner resize undo data
        from open_garden_planner.core.tools.constraint_tool import (
            _build_equal_resize_fn,  # noqa: PLC0415
        )
        partner_resizes = []
        for p_item, old_size, apply_fn, p_anchor_type in getattr(self, '_equal_partner_pre_states', []):
            new_size, _ = _build_equal_resize_fn(p_item, p_anchor_type)
            if new_size is not None and old_size != new_size:
                partner_resizes.append((p_item, old_size, new_size, apply_fn))

        command = ResizeItemCommand(
            self,
            old_geometry,
            new_geometry,
            apply_geometry,
            partner_resizes=partner_resizes or None,
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
            if isinstance(item, CircleItem):
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

        # Duplicate action
        duplicate_action = menu.addAction("Duplicate")

        # Linear array action
        linear_array_action = menu.addAction("Create Linear Array...")

        # Grid array action
        grid_array_action = menu.addAction("Create Grid Array...")

        # Circular array action
        circular_array_action = menu.addAction("Create Circular Array...")

        # Execute menu and handle result
        action = menu.exec(event.screenPos())

        if action == delete_action:
            self.scene().removeItem(self)
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
