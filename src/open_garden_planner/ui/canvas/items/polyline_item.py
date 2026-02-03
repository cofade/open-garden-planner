"""Polyline item for the garden canvas."""

import uuid

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core.object_types import ObjectType, get_style

from .garden_item import GardenItemMixin


class PolylineItem(GardenItemMixin, QGraphicsPathItem):
    """A polyline (open path) on the garden canvas.

    Used for fences, walls, paths, and other linear features.
    Supports selection and movement.
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
