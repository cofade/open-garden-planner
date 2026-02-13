"""Polyline item for the garden canvas."""

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
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

from open_garden_planner.core.object_types import ObjectType, get_style

from .garden_item import GardenItemMixin
from .resize_handle import PolylineVertexEditMixin, RotationHandleMixin


class PolylineItem(PolylineVertexEditMixin, RotationHandleMixin, GardenItemMixin, QGraphicsPathItem):
    """A polyline (open path) on the garden canvas.

    Used for fences, walls, paths, and other linear features.
    Supports selection, movement, and rotation.
    """

    def __init__(
        self,
        points: list[QPointF],
        object_type: ObjectType = ObjectType.FENCE,
        name: str = "",
        layer_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize the polyline item.

        Args:
            points: List of points defining the polyline
            object_type: Type of property object
            name: Optional name/label for the object
            layer_id: Layer ID this item belongs to (optional)
        """
        GardenItemMixin.__init__(self, object_type=object_type, name=name, layer_id=layer_id)

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

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type."""
        style = get_style(self.object_type)

        pen = QPen(style.stroke_color)
        pen.setWidthF(style.stroke_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

        # Polylines typically don't have fill
        self.setBrush(QBrush(QColor(0, 0, 0, 0)))

    def _setup_flags(self) -> None:
        """Configure item interaction flags."""
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsFocusable, True)

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
        """Paint the polyline with an optional painted shadow."""
        if self._shadows_enabled:
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
        super().paint(painter, option, widget)

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

        return super().itemChange(change, value)

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
            if isinstance(item, PolylineItem):
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

        # Execute menu and handle result
        action = menu.exec(event.screenPos())

        if action == edit_vertices_action and edit_vertices_action is not None:
            self.enter_vertex_edit_mode()
            self.setFocus()
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
