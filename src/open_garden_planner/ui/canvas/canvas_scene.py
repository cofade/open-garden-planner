"""Canvas scene for the garden planner.

The scene holds all the garden objects and manages their rendering.
Coordinates are in centimeters with Y-axis pointing down (Qt convention).
The view handles the Y-flip for display.
"""

from uuid import UUID

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
)

from open_garden_planner.models.layer import Layer, create_default_layers


class CanvasScene(QGraphicsScene):
    """Graphics scene for the garden canvas.

    The scene uses centimeters as the coordinate unit.
    Origin is at top-left (Qt convention), with Y increasing downward.
    The CanvasView flips the Y-axis for display (CAD convention).

    Signals:
        layers_changed: Emitted when layers are added, removed, or reordered
        active_layer_changed: Emitted when the active layer changes
    """

    # Default canvas colors (overridden by apply_theme_colors)
    CANVAS_COLOR = QColor("#f5f5dc")
    OUTSIDE_COLOR = QColor("#707070")

    # Signals
    layers_changed = pyqtSignal()
    active_layer_changed = pyqtSignal(object)  # Layer or None

    def __init__(
        self,
        width_cm: float = 5000.0,
        height_cm: float = 3000.0,
        parent: object = None,
    ) -> None:
        """Initialize the canvas scene.

        Args:
            width_cm: Width of the canvas in centimeters (default 50m)
            height_cm: Height of the canvas in centimeters (default 30m)
            parent: Parent object
        """
        super().__init__(parent)

        self._width_cm = width_cm
        self._height_cm = height_cm

        # Set scene rectangle (0,0 at top-left, dimensions in cm)
        # We use a larger rect to allow panning beyond canvas edges
        self._update_scene_rect()

        # Calibration mode state
        self._calibration_mode = False
        self._calibration_image = None
        self._calibration_points: list[QPointF] = []
        self._calibration_markers: list[QGraphicsLineItem] = []

        # Shadow state (painted shadows on garden items)
        self._shadows_enabled = True

        # Labels state
        self._labels_enabled = True

        # Construction geometry visibility state
        self._construction_visible = True

        # Layer management
        self._layers: list[Layer] = create_default_layers()
        self._active_layer: Layer | None = self._layers[0] if self._layers else None  # Default to first layer

        # Command manager reference (set by CanvasView after construction)
        self._command_manager = None

        # Constraint graph for distance constraints
        from open_garden_planner.core.constraints import ConstraintGraph

        self.constraint_graph = ConstraintGraph()

        # Dimension line manager for constraint visualization
        from open_garden_planner.ui.canvas.dimension_lines import DimensionLineManager

        self._dimension_line_manager = DimensionLineManager(self)

    def _update_scene_rect(self) -> None:
        """Update the scene rect with padding for panning."""
        # Add padding around canvas (50% of canvas size on each side)
        padding_x = self._width_cm * 0.5
        padding_y = self._height_cm * 0.5
        self.setSceneRect(QRectF(
            -padding_x,
            -padding_y,
            self._width_cm + 2 * padding_x,
            self._height_cm + 2 * padding_y
        ))

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the scene background.

        Fills the visible area with gray, then draws the canvas area in beige.
        """
        # First fill the entire visible rect with gray (outside canvas area)
        painter.fillRect(rect, QBrush(self.OUTSIDE_COLOR))

        # Then draw canvas area (beige rectangle) on top
        canvas_rect = QRectF(0, 0, self._width_cm, self._height_cm)
        painter.fillRect(canvas_rect, QBrush(self.CANVAS_COLOR))

    # Shadow management (painted shadows — no QGraphicsEffect overhead)

    @property
    def shadows_enabled(self) -> bool:
        """Whether painted shadows are shown on objects."""
        return self._shadows_enabled

    def set_shadows_enabled(self, enabled: bool) -> None:
        """Enable or disable painted shadows on all garden objects.

        Args:
            enabled: Whether shadows should be shown
        """
        self._shadows_enabled = enabled
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        for item in self.items():
            if isinstance(item, GardenItemMixin):
                item.shadows_enabled = enabled

    # Label management

    @property
    def labels_enabled(self) -> bool:
        """Whether labels are shown on objects."""
        return self._labels_enabled

    def set_labels_visible(self, visible: bool) -> None:
        """Enable or disable labels on all garden objects.

        Args:
            visible: Whether labels should be shown
        """
        self._labels_enabled = visible
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        for item in self.items():
            if isinstance(item, GardenItemMixin):
                item.set_global_labels_visible(visible)

    # Construction geometry visibility management

    @property
    def construction_visible(self) -> bool:
        """Whether construction geometry items are shown."""
        return self._construction_visible

    def set_construction_visible(self, visible: bool) -> None:
        """Show or hide all construction geometry items.

        Args:
            visible: Whether construction geometry should be shown.
        """
        self._construction_visible = visible
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        for item in self.items():
            if isinstance(item, (ConstructionLineItem, ConstructionCircleItem)):
                item.setVisible(visible)

    def addItem(self, item: QGraphicsItem) -> None:
        """Add an item to the scene, applying shadow and label state.

        Args:
            item: The graphics item to add
        """
        super().addItem(item)
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        if isinstance(item, (ConstructionLineItem, ConstructionCircleItem)):
            item.setVisible(self._construction_visible)
            return

        if isinstance(item, GardenItemMixin):
            item.shadows_enabled = self._shadows_enabled
            item.set_global_labels_visible(self._labels_enabled)

    # Constraint dimension line management

    @property
    def constraints_visible(self) -> bool:
        """Whether constraint dimension lines are shown."""
        return self._dimension_line_manager.visible

    def set_constraints_visible(self, visible: bool) -> None:
        """Show or hide constraint dimension lines.

        Args:
            visible: Whether dimension lines should be shown
        """
        self._dimension_line_manager.set_visible(visible)

    def reset_constraints(self) -> None:
        """Clear all constraints and their dimension-line visuals.

        Must be called BEFORE scene.clear() so the manager can remove its
        graphics items while the C++ objects are still alive.
        """
        from open_garden_planner.core.constraints import ConstraintGraph

        self._dimension_line_manager.clear()
        self.constraint_graph = ConstraintGraph()

    def update_dimension_lines(self) -> None:
        """Rebuild all dimension line visuals from the constraint graph."""
        self._dimension_line_manager.update_all()

    @property
    def dimension_line_manager(self):
        """Access the dimension line manager."""
        return self._dimension_line_manager

    def apply_theme_colors(self, colors: dict[str, str]) -> None:
        """Update canvas colors from the theme palette.

        Args:
            colors: Theme color dictionary from ThemeColors
        """
        self.CANVAS_COLOR = QColor(colors.get("canvas_background", "#f5f5dc"))
        self.OUTSIDE_COLOR = QColor(colors.get("canvas_outside", "#707070"))
        self.update()

    @property
    def width_cm(self) -> float:
        """Width of the canvas in centimeters."""
        return self._width_cm

    @property
    def height_cm(self) -> float:
        """Height of the canvas in centimeters."""
        return self._height_cm

    @property
    def canvas_rect(self) -> QRectF:
        """Get the actual canvas rectangle (not the scene rect with padding)."""
        return QRectF(0, 0, self._width_cm, self._height_cm)

    def get_command_manager(self):
        """Get the command manager for undo/redo operations."""
        return self._command_manager

    def resize_canvas(self, width_cm: float, height_cm: float) -> None:
        """Resize the canvas.

        Args:
            width_cm: New width in centimeters
            height_cm: New height in centimeters
        """
        self._width_cm = width_cm
        self._height_cm = height_cm
        self._update_scene_rect()
        self.update()  # Trigger redraw

    def start_image_calibration(self, image_item) -> None:
        """Start inline calibration mode for an image.

        Args:
            image_item: The BackgroundImageItem to calibrate
        """
        self._calibration_mode = True
        self._calibration_image = image_item
        self._calibration_points.clear()
        self._clear_calibration_markers()

        # Notify views that calibration started
        if self.views():
            self.views()[0].set_status_message(
                "Calibration: Click first point on the image"
            )

    def _clear_calibration_markers(self) -> None:
        """Remove calibration visual markers from the scene."""
        for marker in self._calibration_markers:
            self.removeItem(marker)
        self._calibration_markers.clear()

    def add_calibration_point(self, point: QPointF) -> None:
        """Add a calibration point.

        Args:
            point: The point in scene coordinates
        """
        if not self._calibration_mode or len(self._calibration_points) >= 2:
            return

        self._calibration_points.append(point)
        self._draw_calibration_marker(point)

        if len(self._calibration_points) == 1:
            # After first point, update status
            if self.views():
                self.views()[0].set_status_message(
                    "Calibration: Click second point on the image"
                )
        elif len(self._calibration_points) == 2:
            # After second point, draw line and show input
            self._draw_calibration_line()
            if self.views():
                self.views()[0].show_calibration_input(point)

    def _draw_calibration_marker(self, point: QPointF) -> None:
        """Draw a calibration crosshair marker at the given point.

        Args:
            point: The point in scene coordinates
        """
        pen = QPen(Qt.GlobalColor.red, 2)

        # Draw crosshair
        size = 15
        line_h = QGraphicsLineItem(point.x() - size, point.y(), point.x() + size, point.y())
        line_h.setPen(pen)
        self.addItem(line_h)
        self._calibration_markers.append(line_h)

        line_v = QGraphicsLineItem(point.x(), point.y() - size, point.x(), point.y() + size)
        line_v.setPen(pen)
        self.addItem(line_v)
        self._calibration_markers.append(line_v)


    def _draw_calibration_line(self) -> None:
        """Draw a line between the two calibration points."""
        if len(self._calibration_points) != 2:
            return

        pen = QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.DashLine)
        line = QGraphicsLineItem(QLineF(self._calibration_points[0], self._calibration_points[1]))
        line.setPen(pen)
        line.setZValue(999)
        self.addItem(line)
        self._calibration_markers.append(line)

    def finish_calibration(self, distance_cm: float) -> None:
        """Complete the calibration with the entered distance.

        Args:
            distance_cm: The real-world distance in centimeters
        """
        if not self._calibration_mode or len(self._calibration_points) != 2:
            return

        # Calculate pixel distance
        line = QLineF(self._calibration_points[0], self._calibration_points[1])
        pixel_distance = line.length()

        # Apply calibration to the image
        if self._calibration_image:
            self._calibration_image.calibrate(pixel_distance, distance_cm)

        # Clean up calibration mode
        self.cancel_calibration()

        # Notify view
        if self.views():
            self.views()[0].set_status_message("Calibration complete")

    def cancel_calibration(self) -> None:
        """Cancel calibration mode."""
        self._calibration_mode = False
        self._calibration_image = None
        self._calibration_points.clear()
        self._clear_calibration_markers()

        if self.views():
            self.views()[0].hide_calibration_input()
            self.views()[0].set_status_message("")

    @property
    def is_calibrating(self) -> bool:
        """Whether calibration mode is active."""
        return self._calibration_mode

    # Layer Management

    @property
    def layers(self) -> list[Layer]:
        """Get all layers."""
        return self._layers

    def set_layers(self, layers: list[Layer]) -> None:
        """Set the layers list.

        Args:
            layers: New list of layers
        """
        self._layers = layers
        # Set active layer to first layer if not set or invalid
        if not self._active_layer or self._active_layer not in self._layers:
            self._active_layer = self._layers[0] if self._layers else None
        self.layers_changed.emit()
        self._update_items_visibility()

    def add_layer(self, layer: Layer) -> None:
        """Add a new layer.

        Args:
            layer: Layer to add
        """
        self._layers.append(layer)
        self.layers_changed.emit()

    def remove_layer(self, layer_id: UUID) -> bool:
        """Remove a layer by ID.

        Args:
            layer_id: ID of layer to remove

        Returns:
            True if layer was removed, False if not found
        """
        for i, layer in enumerate(self._layers):
            if layer.id == layer_id:
                # Don't allow removing the last layer
                if len(self._layers) <= 1:
                    return False
                # Move items from this layer to another layer
                replacement_layer = self._layers[0] if i > 0 else self._layers[1]
                self._move_items_to_layer(layer_id, replacement_layer.id)
                # Remove the layer
                del self._layers[i]
                # Update active layer if needed
                if self._active_layer and self._active_layer.id == layer_id:
                    self._active_layer = replacement_layer
                    self.active_layer_changed.emit(self._active_layer)
                self.layers_changed.emit()
                return True
        return False

    def _move_items_to_layer(self, from_layer_id: UUID, to_layer_id: UUID) -> None:
        """Move all items from one layer to another.

        Args:
            from_layer_id: Source layer ID
            to_layer_id: Destination layer ID
        """
        for item in self.items():
            if hasattr(item, 'layer_id') and item.layer_id == from_layer_id:
                item.layer_id = to_layer_id

    def reorder_layers(self, new_order: list[Layer]) -> None:
        """Reorder layers.

        Args:
            new_order: New layer order (first in list = bottom, last = top)
        """
        self._layers = new_order
        # Update z_order values based on new position
        # Reverse order: first item in list gets highest z_order (on top)
        for i, layer in enumerate(self._layers):
            layer.z_order = len(self._layers) - 1 - i
        self.layers_changed.emit()
        self._update_items_z_order()

    def _update_items_z_order(self) -> None:
        """Update Z-order of all items based on layer order."""
        for item in self.items():
            if hasattr(item, 'layer_id') and item.layer_id:
                layer = self.get_layer_by_id(item.layer_id)
                if layer:
                    # Use z_order * 100 to leave room for ordering within layer
                    item.setZValue(layer.z_order * 100)

    def get_layer_by_id(self, layer_id: UUID) -> Layer | None:
        """Get a layer by its ID.

        Args:
            layer_id: Layer ID to find

        Returns:
            Layer if found, None otherwise
        """
        for layer in self._layers:
            if layer.id == layer_id:
                return layer
        return None

    @property
    def active_layer(self) -> Layer | None:
        """Get the active layer."""
        return self._active_layer

    def set_active_layer(self, layer: Layer | None) -> None:
        """Set the active layer.

        Args:
            layer: Layer to set as active
        """
        if layer != self._active_layer:
            self._active_layer = layer
            self.active_layer_changed.emit(layer)

    def _update_items_visibility(self) -> None:
        """Update visibility and interaction of all items based on layer state."""
        for item in self.items():
            if hasattr(item, 'layer_id') and item.layer_id:
                layer = self.get_layer_by_id(item.layer_id)
                if layer:
                    # Set visibility
                    item.setVisible(layer.visible)
                    # Set opacity
                    item.setOpacity(layer.opacity)
                    # Set selectability based on lock state
                    if hasattr(item, 'setFlag'):
                        from PyQt6.QtWidgets import QGraphicsItem
                        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not layer.locked)
                        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not layer.locked)

    def update_layer_visibility(self, layer_id: UUID, visible: bool) -> None:
        """Update visibility of a layer and its items.

        Args:
            layer_id: Layer ID
            visible: New visibility state
        """
        layer = self.get_layer_by_id(layer_id)
        if layer:
            layer.visible = visible
            self._update_items_visibility()
            self.layers_changed.emit()

    def update_layer_lock(self, layer_id: UUID, locked: bool) -> None:
        """Update lock state of a layer and its items.

        Args:
            layer_id: Layer ID
            locked: New lock state
        """
        layer = self.get_layer_by_id(layer_id)
        if layer:
            layer.locked = locked
            self._update_items_visibility()
            self.layers_changed.emit()

    def update_layer_opacity(self, layer_id: UUID, opacity: float) -> None:
        """Update opacity of a layer and its items.

        Args:
            layer_id: Layer ID
            opacity: New opacity (0.0 to 1.0)
        """
        layer = self.get_layer_by_id(layer_id)
        if layer:
            layer.opacity = max(0.0, min(1.0, opacity))
            self._update_items_visibility()
            self.layers_changed.emit()
