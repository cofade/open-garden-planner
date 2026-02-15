"""Measurement tool for measuring distances between points."""

from PyQt6.QtCore import QCoreApplication, QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsTextItem

from open_garden_planner.core.measure_snapper import AnchorPoint, find_nearest_anchor
from open_garden_planner.core.tools.base_tool import BaseTool, ToolType

# Visual constants for the snap indicator
SNAP_INDICATOR_RADIUS = 8.0  # Scene units (cm)
SNAP_INDICATOR_COLOR = QColor(0, 180, 0, 200)  # Green
SNAP_INDICATOR_PEN_WIDTH = 2.5


class MeasureTool(BaseTool):
    """Tool for measuring distances between two points.

    Click two points to measure the distance between them.
    Snaps to object anchor points (centers and edge midpoints)
    when clicking near objects. The measurement is displayed
    but not persisted (temporary).
    """

    def __init__(self, view) -> None:
        """Initialize the measure tool.

        Args:
            view: The CanvasView this tool operates on
        """
        super().__init__(view)
        self._first_point: QPointF | None = None
        self._graphics_items: list = []  # Track all created items for cleanup
        self._snap_indicator: QGraphicsEllipseItem | None = None
        self._current_snap: AnchorPoint | None = None

    @property
    def tool_type(self) -> ToolType:
        """Get the tool type."""
        return ToolType.MEASURE

    @property
    def display_name(self) -> str:
        """Get the display name for UI."""
        return QCoreApplication.translate("MeasureTool", "Measure")

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
        self._remove_snap_indicator()

    def _snap_scene_pos(self, scene_pos: QPointF) -> QPointF:
        """Attempt to snap a scene position to the nearest object anchor.

        Updates the visual snap indicator accordingly.

        Args:
            scene_pos: Raw mouse position in scene coordinates.

        Returns:
            Snapped position if near an anchor, otherwise the original position.
        """
        scene = self._view.scene()
        if not scene:
            self._remove_snap_indicator()
            self._current_snap = None
            return scene_pos

        anchor = find_nearest_anchor(scene_pos, scene.items())
        if anchor is not None:
            self._current_snap = anchor
            self._show_snap_indicator(anchor.point)
            return anchor.point
        else:
            self._current_snap = None
            self._remove_snap_indicator()
            return scene_pos

    def _show_snap_indicator(self, point: QPointF) -> None:
        """Show a small circle at the snap point.

        Args:
            point: The anchor point in scene coordinates.
        """
        scene = self._view.scene()
        if not scene:
            return

        r = SNAP_INDICATOR_RADIUS
        rect = QRectF(point.x() - r, point.y() - r, r * 2, r * 2)

        if self._snap_indicator is not None and self._snap_indicator.scene():
            # Reposition existing indicator
            self._snap_indicator.setRect(rect)
        else:
            # Create new indicator
            pen = QPen(SNAP_INDICATOR_COLOR, SNAP_INDICATOR_PEN_WIDTH)
            self._snap_indicator = scene.addEllipse(rect, pen)
            self._snap_indicator.setZValue(1002)

    def _remove_snap_indicator(self) -> None:
        """Remove the snap indicator from the scene."""
        if self._snap_indicator is not None:
            scene = self._snap_indicator.scene()
            if scene:
                scene.removeItem(self._snap_indicator)
            self._snap_indicator = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse press to set measurement points.

        Snaps to object anchor points when near an object.

        Args:
            event: The mouse event
            scene_pos: Position in scene coordinates

        Returns:
            True if event was handled
        """
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Snap to nearest anchor if available
        snapped_pos = self._snap_scene_pos(scene_pos)
        # Remove indicator after click (it served its purpose)
        self._remove_snap_indicator()

        if self._first_point is None:
            # First point: start measurement
            self._first_point = snapped_pos
            self._draw_start_point(snapped_pos)
            return True
        else:
            # Second point: complete measurement
            self._draw_measurement(self._first_point, snapped_pos)
            # Reset for next measurement
            self._first_point = None
            return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse move to show preview line and snap indicator.

        Args:
            _event: The mouse event (unused)
            scene_pos: Position in scene coordinates

        Returns:
            True if event was handled
        """
        # Always try to snap and show indicator during mouse move
        snapped_pos = self._snap_scene_pos(scene_pos)

        if self._first_point is not None:
            # Update preview line using snapped position
            self._draw_preview_line(self._first_point, snapped_pos)
            return True
        return True  # Always handle to update snap indicator

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
        font.setPointSize(12)
        font.setBold(True)
        text_item.setFont(font)

        # Position text at midpoint
        mid_x = (start.x() + end.x()) / 2
        mid_y = (start.y() + end.y()) / 2

        # Center the text at the midpoint
        text_rect = text_item.boundingRect()
        text_item.setPos(mid_x - text_rect.width() / 2, mid_y - text_rect.height() / 2)

        # Make text zoom-independent (stays readable at all zoom levels)
        text_item.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations)

        text_item.setZValue(1001)

        return text_item

    def _clear_measurement(self) -> None:
        """Clear the current measurement."""
        self._clear_measurement_visuals()
        self._first_point = None
        self._remove_snap_indicator()

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
