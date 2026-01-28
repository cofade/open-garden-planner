"""Measurement tool for measuring distances between points."""

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import (
    QCursor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPen,
    QTransform,
)
from PyQt6.QtWidgets import QGraphicsTextItem

from open_garden_planner.core.tools.base_tool import BaseTool, ToolType


class MeasureTool(BaseTool):
    """Tool for measuring distances between two points.

    Click two points to measure the distance between them.
    The measurement is displayed but not persisted (temporary).
    """

    def __init__(self, view) -> None:
        """Initialize the measure tool.

        Args:
            view: The CanvasView this tool operates on
        """
        super().__init__(view)
        self._first_point: QPointF | None = None
        self._graphics_items: list = []  # Track all created items for cleanup

    @property
    def tool_type(self) -> ToolType:
        """Get the tool type."""
        return ToolType.MEASURE

    @property
    def display_name(self) -> str:
        """Get the display name for UI."""
        return "Measure"

    @property
    def shortcut(self) -> str:
        """Get the keyboard shortcut."""
        return "M"

    @property
    def cursor(self) -> QCursor:
        """Get the cursor for this tool."""
        return QCursor(Qt.CursorShape.CrossCursor)

    def activate(self) -> None:
        """Activate the tool."""
        super().activate()
        self._clear_measurement()

    def deactivate(self) -> None:
        """Deactivate the tool."""
        super().deactivate()
        self._clear_measurement()

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse press to set measurement points.

        Args:
            event: The mouse event
            scene_pos: Position in scene coordinates

        Returns:
            True if event was handled
        """
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        if self._first_point is None:
            # First point: start measurement
            self._first_point = scene_pos
            self._draw_start_point(scene_pos)
            return True
        else:
            # Second point: complete measurement
            self._draw_measurement(self._first_point, scene_pos)
            # Reset for next measurement
            self._first_point = None
            return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse move to show preview line.

        Args:
            _event: The mouse event (unused)
            scene_pos: Position in scene coordinates

        Returns:
            True if event was handled
        """
        if self._first_point is not None:
            # Update preview line
            self._draw_preview_line(self._first_point, scene_pos)
            return True
        return False

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        """Handle mouse release (not used for measure tool).

        Args:
            _event: The mouse event (unused)
            _scene_pos: Position in scene coordinates (unused)

        Returns:
            False (not handled)
        """
        return False

    def mouse_double_click(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        """Handle mouse double click (not used for measure tool).

        Args:
            _event: The mouse event (unused)
            _scene_pos: Position in scene coordinates (unused)

        Returns:
            False (not handled)
        """
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        """Handle key press for canceling measurement.

        Args:
            event: The key event

        Returns:
            True if event was handled
        """
        if event.key() == Qt.Key.Key_Escape:
            self._clear_measurement()
            return True
        return False

    def cancel(self) -> None:
        """Cancel the current measurement operation."""
        self._clear_measurement()

    def _draw_start_point(self, point: QPointF) -> None:
        """Draw a marker at the start point.

        Args:
            point: The start point in scene coordinates
        """
        scene = self._view.scene()
        if not scene:
            return

        # Clear previous measurement visuals
        self._clear_measurement_visuals()

        # Draw a small crosshair
        pen = QPen(Qt.GlobalColor.blue, 2)
        size = 15

        line_h = scene.addLine(
            point.x() - size, point.y(), point.x() + size, point.y(), pen
        )
        line_v = scene.addLine(
            point.x(), point.y() - size, point.x(), point.y() + size, pen
        )

        # Track items for cleanup
        self._graphics_items.extend([line_h, line_v])

    def _draw_preview_line(self, start: QPointF, end: QPointF) -> None:
        """Draw a preview line while measuring.

        Args:
            start: Start point in scene coordinates
            end: End point in scene coordinates
        """
        scene = self._view.scene()
        if not scene:
            return

        # Remove old preview (keep start point marker)
        self._clear_preview_items()

        # Draw preview line (dashed)
        pen = QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine)
        line_item = scene.addLine(QLineF(start, end), pen)
        line_item.setZValue(1000)  # On top
        self._graphics_items.append(line_item)

        # Show distance preview
        distance_cm = QLineF(start, end).length()
        distance_m = distance_cm / 100.0
        distance_text = f"{distance_m:.2f} m"

        text_item = self._create_text_item(distance_text, start, end)
        self._graphics_items.append(text_item)

    def _clear_preview_items(self) -> None:
        """Clear preview items (line and text) but keep start point marker."""
        scene = self._view.scene()
        if not scene:
            return

        # Remove all items except the first two (start point crosshair)
        items_to_remove = self._graphics_items[2:] if len(self._graphics_items) > 2 else []
        for item in items_to_remove:
            if item.scene():
                scene.removeItem(item)
        # Keep only the start point crosshair (first 2 items)
        self._graphics_items = self._graphics_items[:2]

    def _draw_measurement(self, start: QPointF, end: QPointF) -> None:
        """Draw the final measurement.

        Args:
            start: Start point in scene coordinates
            end: End point in scene coordinates
        """
        scene = self._view.scene()
        if not scene:
            return

        # Clear all previous items
        self._clear_measurement_visuals()

        # Draw final measurement line (solid)
        pen = QPen(Qt.GlobalColor.blue, 2)
        line_item = scene.addLine(QLineF(start, end), pen)
        line_item.setZValue(1000)
        self._graphics_items.append(line_item)

        # Draw end markers (crosshairs)
        size = 15
        for point in [start, end]:
            line_h = scene.addLine(
                point.x() - size, point.y(), point.x() + size, point.y(), pen
            )
            line_v = scene.addLine(
                point.x(), point.y() - size, point.x(), point.y() + size, pen
            )
            self._graphics_items.extend([line_h, line_v])

        # Show final distance
        distance_cm = QLineF(start, end).length()
        distance_m = distance_cm / 100.0
        distance_text = f"{distance_m:.2f} m"

        text_item = self._create_text_item(distance_text, start, end)
        self._graphics_items.append(text_item)

    def _create_text_item(
        self, text: str, start: QPointF, end: QPointF
    ) -> QGraphicsTextItem:
        """Create a text item with proper formatting and positioning.

        Args:
            text: The text to display
            start: Start point of measurement
            end: End point of measurement

        Returns:
            The created text item
        """
        scene = self._view.scene()
        if not scene:
            return QGraphicsTextItem()

        text_item = scene.addText(text)
        text_item.setDefaultTextColor(Qt.GlobalColor.blue)

        # Set larger font size (similar to menu text)
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        text_item.setFont(font)

        # Position text at midpoint
        mid_x = (start.x() + end.x()) / 2
        mid_y = (start.y() + end.y()) / 2
        text_item.setPos(mid_x + 20, mid_y + 30)  # Offset to the right and down

        # Counter-flip the text to make it readable (Y-axis is flipped in view)
        transform = QTransform()
        transform.scale(1, -1)  # Flip vertically to counter view's Y-flip
        text_item.setTransform(transform)

        text_item.setZValue(1001)

        return text_item

    def _clear_measurement(self) -> None:
        """Clear the current measurement."""
        self._clear_measurement_visuals()
        self._first_point = None

    def _clear_measurement_visuals(self) -> None:
        """Remove all measurement graphics items from the scene."""
        scene = self._view.scene()
        if not scene:
            return

        # Remove all graphics items
        for item in self._graphics_items:
            if item.scene():
                scene.removeItem(item)

        self._graphics_items.clear()
