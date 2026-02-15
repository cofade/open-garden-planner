"""Circle drawing tool."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QLineF, QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem

from open_garden_planner.core.object_types import ObjectType

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class CircleTool(BaseTool):
    """Tool for drawing circles by clicking center then rim.

    Usage:
        - First click: Set center point
        - Second click: Set radius (rim point)
        - Press Escape to cancel
    """

    tool_type = ToolType.CIRCLE
    display_name = QT_TR_NOOP("Circle")
    shortcut = "C"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(
        self,
        view: "CanvasView",
        object_type: ObjectType = ObjectType.GENERIC_CIRCLE,
    ) -> None:
        """Initialize the circle tool.

        Args:
            view: The canvas view
            object_type: Type of property object to create
        """
        super().__init__(view)
        self._object_type = object_type
        self._center_point: QPointF | None = None
        self._preview_circle: QGraphicsEllipseItem | None = None
        self._preview_line: QGraphicsLineItem | None = None
        self._is_drawing = False
        self._plant_category: object | None = None
        self._plant_species: str = ""

    def activate(self) -> None:
        """Called when this tool becomes the active tool.

        Clears any stale plant info from a previous gallery selection
        so that re-activating via toolbar defaults to category-based rendering.
        """
        super().activate()
        self._plant_category = None
        self._plant_species = ""

    def set_plant_info(
        self, category: object | None = None, species: str = ""
    ) -> None:
        """Set plant category/species for the next item created.

        Args:
            category: PlantCategory enum value (or None)
            species: Species name string
        """
        self._plant_category = category
        self._plant_species = species

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle click for center or rim point."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Snap the position to grid if enabled
        snapped_pos = self._view.snap_point(scene_pos)

        if not self._is_drawing:
            # First click: set center
            self._center_point = snapped_pos
            self._is_drawing = True

            # Create preview circle (starts with zero radius)
            self._preview_circle = QGraphicsEllipseItem()
            self._preview_circle.setPen(
                QPen(QColor(0, 100, 255), 1, Qt.PenStyle.DashLine)
            )
            self._preview_circle.setBrush(QBrush(QColor(100, 100, 255, 50)))
            self._view.scene().addItem(self._preview_circle)

            # Create preview line from center to rim
            self._preview_line = QGraphicsLineItem()
            self._preview_line.setPen(
                QPen(QColor(100, 100, 100), 1, Qt.PenStyle.DashLine)
            )
            self._view.scene().addItem(self._preview_line)

            return True
        else:
            # Second click: finalize circle (use snapped position)
            self._finalize_circle(snapped_pos)
            return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Update preview circle while selecting rim point."""
        if not self._is_drawing or not self._preview_circle or not self._center_point:
            return False

        # Snap the position to grid if enabled
        snapped_pos = self._view.snap_point(scene_pos)

        # Calculate radius from center to current mouse position
        radius = QLineF(self._center_point, snapped_pos).length()

        # Update preview circle
        top_left_x = self._center_point.x() - radius
        top_left_y = self._center_point.y() - radius
        diameter = radius * 2
        self._preview_circle.setRect(top_left_x, top_left_y, diameter, diameter)

        # Update preview line
        if self._preview_line:
            self._preview_line.setLine(
                self._center_point.x(),
                self._center_point.y(),
                snapped_pos.x(),
                snapped_pos.y(),
            )

        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        """No-op for circle tool (uses click, not drag)."""
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        """Handle Escape to cancel drawing."""
        if event.key() == Qt.Key.Key_Escape and self._is_drawing:
            self.cancel()
            return True
        return False

    def _finalize_circle(self, rim_pos: QPointF) -> None:
        """Create final circle item."""
        if not self._center_point:
            return

        # Calculate radius
        radius = QLineF(self._center_point, rim_pos).length()

        # Remove preview items
        self._cleanup_preview()

        # Create final circle if it has a meaningful radius
        if radius > 1:  # Minimum radius in cm
            from open_garden_planner.ui.canvas.items import CircleItem
            # Get active layer from scene
            scene = self._view.scene()
            layer_id = scene.active_layer.id if hasattr(scene, 'active_layer') and scene.active_layer else None
            item = CircleItem(
                self._center_point.x(),
                self._center_point.y(),
                radius,
                object_type=self._object_type,
                layer_id=layer_id,
            )
            # Set plant category/species if provided by gallery selection
            if self._plant_category is not None:
                item.plant_category = self._plant_category
            if self._plant_species:
                item.plant_species = self._plant_species
            self._view.add_item(item, "circle")

        self._reset_state()

    def _cleanup_preview(self) -> None:
        """Remove preview items from scene."""
        if self._preview_circle:
            self._view.scene().removeItem(self._preview_circle)
            self._preview_circle = None
        if self._preview_line:
            self._view.scene().removeItem(self._preview_line)
            self._preview_line = None

    def _reset_state(self) -> None:
        """Reset tool state for next circle."""
        self._center_point = None
        self._is_drawing = False

    def cancel(self) -> None:
        """Cancel the current circle drawing operation."""
        self._cleanup_preview()
        self._reset_state()
