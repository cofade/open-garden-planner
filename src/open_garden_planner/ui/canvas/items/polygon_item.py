"""Polygon item for the garden canvas."""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QBrush, QColor, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsSceneContextMenuEvent, QMenu

from .garden_item import GardenItemMixin


class PolygonItem(GardenItemMixin, QGraphicsPolygonItem):
    """A polygon shape on the garden canvas.

    Styled with light blue fill and steel blue stroke.
    Supports selection and movement.
    """

    # Default styling
    FILL_COLOR = QColor(173, 216, 230, 100)  # #ADD8E6 with alpha 100
    STROKE_COLOR = QColor(70, 130, 180)  # #4682B4
    STROKE_WIDTH = 2

    def __init__(self, vertices: list[QPointF]) -> None:
        """Initialize the polygon item.

        Args:
            vertices: List of vertices defining the polygon
        """
        GardenItemMixin.__init__(self)
        polygon = QPolygonF(vertices)
        QGraphicsPolygonItem.__init__(self, polygon)

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
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsMovable, True)

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
            # Delete this item and any other selected items
            scene = self.scene()
            for item in scene.selectedItems():
                scene.removeItem(item)

    @classmethod
    def from_polygon(cls, polygon: QPolygonF) -> "PolygonItem":
        """Create a PolygonItem from a QPolygonF.

        Args:
            polygon: The polygon geometry

        Returns:
            A new PolygonItem
        """
        vertices = [polygon.at(i) for i in range(polygon.count())]
        return cls(vertices)
