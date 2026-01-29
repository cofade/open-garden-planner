"""Polygon item for the garden canvas."""

from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import ObjectType, get_style

from .garden_item import GardenItemMixin


def _show_properties_dialog(item: QGraphicsPolygonItem) -> None:
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
        fill_pattern: FillPattern | None = None,
    ) -> None:
        """Initialize the polygon item.

        Args:
            vertices: List of vertices defining the polygon
            object_type: Type of property object
            name: Optional name/label for the object
            metadata: Optional metadata dictionary
            fill_pattern: Fill pattern (defaults to pattern from object type)
        """
        # Get default pattern and color from object type if not provided
        style = get_style(object_type)
        if fill_pattern is None:
            fill_pattern = style.fill_pattern

        GardenItemMixin.__init__(
            self, object_type=object_type, name=name, metadata=metadata,
            fill_pattern=fill_pattern, fill_color=style.fill_color
        )
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

        # Use stored fill_pattern and color if available, otherwise use style defaults
        pattern = self.fill_pattern if self.fill_pattern is not None else style.fill_pattern
        color = self.fill_color if self.fill_color is not None else style.fill_color
        brush = create_pattern_brush(pattern, color)
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
    def from_polygon(cls, polygon: QPolygonF) -> "PolygonItem":
        """Create a PolygonItem from a QPolygonF.

        Args:
            polygon: The polygon geometry

        Returns:
            A new PolygonItem
        """
        vertices = [polygon.at(i) for i in range(polygon.count())]
        return cls(vertices)
