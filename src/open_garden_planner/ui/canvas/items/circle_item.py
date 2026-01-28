"""Circle item for the garden canvas."""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsSceneContextMenuEvent, QMenu

from .garden_item import GardenItemMixin


class CircleItem(GardenItemMixin, QGraphicsEllipseItem):
    """A circle shape on the garden canvas.

    Styled with green fill and darker green stroke.
    Supports selection and movement.
    """

    # Default styling
    FILL_COLOR = QColor(144, 238, 144, 100)  # #90EE90 with alpha 100
    STROKE_COLOR = QColor(34, 139, 34)  # #228B22
    STROKE_WIDTH = 2

    def __init__(
        self,
        center_x: float,
        center_y: float,
        radius: float,
    ) -> None:
        """Initialize the circle item.

        Args:
            center_x: X coordinate of center
            center_y: Y coordinate of center
            radius: Radius of circle
        """
        GardenItemMixin.__init__(self)
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
        """Configure visual appearance."""
        pen = QPen(self.STROKE_COLOR)
        pen.setWidthF(self.STROKE_WIDTH)
        self.setPen(pen)

        brush = QBrush(self.FILL_COLOR)
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
