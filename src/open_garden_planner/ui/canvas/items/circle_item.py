"""Circle item for the garden canvas."""

from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QBrush, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core.object_types import ObjectType, get_style

from .garden_item import GardenItemMixin


class CircleItem(GardenItemMixin, QGraphicsEllipseItem):
    """A circle shape on the garden canvas.

    Supports property object types with appropriate styling.
    Supports selection and movement.
    """

    def __init__(
        self,
        center_x: float,
        center_y: float,
        radius: float,
        object_type: ObjectType = ObjectType.GENERIC_CIRCLE,
        name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the circle item.

        Args:
            center_x: X coordinate of center
            center_y: Y coordinate of center
            radius: Radius of circle
            object_type: Type of property object
            name: Optional name/label for the object
            metadata: Optional metadata dictionary
        """
        GardenItemMixin.__init__(self, object_type=object_type, name=name, metadata=metadata)
        # QGraphicsEllipseItem uses bounding rect (top-left corner + width/height)
        # Convert center+radius to rect coordinates
        x = center_x - radius
        y = center_y - radius
        diameter = radius * 2
        QGraphicsEllipseItem.__init__(self, x, y, diameter, diameter)

        self._center = QPointF(center_x, center_y)
        self._radius = radius

        self._setup_styling()
        self._setup_flags()

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type."""
        style = get_style(self.object_type) if self.object_type else get_style(ObjectType.GENERIC_CIRCLE)

        pen = QPen(style.stroke_color)
        pen.setWidthF(style.stroke_width)
        self.setPen(pen)

        brush = QBrush(style.fill_color)
        self.setBrush(brush)

    def _setup_flags(self) -> None:
        """Configure item interaction flags."""
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)

    @property
    def center(self) -> QPointF:
        """Get circle center point."""
        return self._center

    @property
    def radius(self) -> float:
        """Get circle radius."""
        return self._radius

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
        properties_action.setEnabled(False)  # Placeholder

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
