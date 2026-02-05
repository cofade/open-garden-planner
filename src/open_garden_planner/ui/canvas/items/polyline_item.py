"""Polyline item for the garden canvas."""

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsSceneContextMenuEvent,
    QMenu,
)

from open_garden_planner.core.object_types import ObjectType, get_style

from .garden_item import GardenItemMixin
from .resize_handle import RotationHandleMixin


class PolylineItem(RotationHandleMixin, GardenItemMixin, QGraphicsPathItem):
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

        # Initialize rotation handle
        self.init_rotation_handle()

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

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: Any,
    ) -> Any:
        """Handle item state changes.

        Shows/hides rotation handle based on selection state.
        """
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value:  # Being selected
                self.show_rotation_handle()
            else:  # Being deselected
                self.hide_rotation_handle()

        return super().itemChange(change, value)

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

        # Delete action
        delete_action = menu.addAction("Delete")

        menu.addSeparator()

        # Duplicate action
        duplicate_action = menu.addAction("Duplicate")

        # Execute menu and handle result
        action = menu.exec(event.screenPos())

        if action == delete_action:
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
