"""Rectangle item for the garden canvas."""

from typing import Any

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QBrush, QPen
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core.object_types import ObjectType, get_style

from .garden_item import GardenItemMixin


def _show_properties_dialog(item: QGraphicsRectItem) -> None:
    """Show properties dialog for an item (imported locally to avoid circular import)."""
    from open_garden_planner.core.object_types import get_style
    from open_garden_planner.ui.dialogs import PropertiesDialog

    dialog = PropertiesDialog(item)
    if dialog.exec():
        # Apply name change
        if hasattr(item, 'name'):
            item.name = dialog.get_name()

        # Apply object type change (updates styling)
        new_object_type = dialog.get_object_type()
        if new_object_type and hasattr(item, 'object_type'):
            item.object_type = new_object_type
            # Update to default styling for new type
            style = get_style(new_object_type)
            pen = item.pen()
            pen.setColor(style.stroke_color)
            pen.setWidthF(style.stroke_width)
            item.setPen(pen)
            brush = item.brush()
            brush.setColor(style.fill_color)
            item.setBrush(brush)

        # Apply custom fill color (overrides type default)
        fill_color = dialog.get_fill_color()
        brush = item.brush()
        brush.setColor(fill_color)
        item.setBrush(brush)


class RectangleItem(GardenItemMixin, QGraphicsRectItem):
    """A rectangle shape on the garden canvas.

    Supports property object types with appropriate styling.
    Supports selection and movement.
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
        """
        GardenItemMixin.__init__(self, object_type=object_type, name=name, metadata=metadata)
        QGraphicsRectItem.__init__(self, x, y, width, height)

        self._setup_styling()
        self._setup_flags()

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type."""
        style = get_style(self.object_type) if self.object_type else get_style(ObjectType.GENERIC_RECTANGLE)

        pen = QPen(style.stroke_color)
        pen.setWidthF(style.stroke_width)
        self.setPen(pen)

        brush = QBrush(style.fill_color)
        self.setBrush(brush)

    def _setup_flags(self) -> None:
        """Configure item interaction flags."""
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)

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

        properties_action = menu.addAction("Properties...")

        # Execute menu and handle result
        action = menu.exec(event.screenPos())

        if action == delete_action:
            # Delete this item and any other selected items
            scene = self.scene()
            for item in scene.selectedItems():
                scene.removeItem(item)
        elif action == properties_action:
            _show_properties_dialog(self)

    @classmethod
    def from_rect(cls, rect: QRectF) -> "RectangleItem":
        """Create a RectangleItem from a QRectF.

        Args:
            rect: The rectangle geometry

        Returns:
            A new RectangleItem
        """
        return cls(rect.x(), rect.y(), rect.width(), rect.height())
