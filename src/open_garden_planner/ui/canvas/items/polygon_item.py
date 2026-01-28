"""Polygon item for the garden canvas."""

from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QBrush, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core.object_types import ObjectType, get_style

from .garden_item import GardenItemMixin


class PolygonItem(GardenItemMixin, QGraphicsPolygonItem):
    """A polygon shape on the garden canvas.

    Supports property object types with appropriate styling.
    Supports selection and movement.
    """

    def __init__(
        self,
        vertices: list[QPointF],
        object_type: ObjectType = ObjectType.GENERIC_POLYGON,
        name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the polygon item.

        Args:
            vertices: List of vertices defining the polygon
            object_type: Type of property object
            name: Optional name/label for the object
            metadata: Optional metadata dictionary
        """
        GardenItemMixin.__init__(self, object_type=object_type, name=name, metadata=metadata)
        polygon = QPolygonF(vertices)
        QGraphicsPolygonItem.__init__(self, polygon)

        self._setup_styling()
        self._setup_flags()

    def _setup_styling(self) -> None:
        """Configure visual appearance based on object type."""
        style = get_style(self.object_type) if self.object_type else get_style(ObjectType.GENERIC_POLYGON)

        pen = QPen(style.stroke_color)
        pen.setWidthF(style.stroke_width)
        self.setPen(pen)

        brush = QBrush(style.fill_color)
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
