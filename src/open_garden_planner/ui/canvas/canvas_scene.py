"""Canvas scene for the garden planner.

The scene holds all the garden objects and manages their rendering.
Coordinates are in centimeters with Y-axis pointing down (Qt convention).
The view handles the Y-flip for display.
"""

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsScene, QGraphicsTextItem


class CanvasScene(QGraphicsScene):
    """Graphics scene for the garden canvas.

    The scene uses centimeters as the coordinate unit.
    Origin is at top-left (Qt convention), with Y increasing downward.
    The CanvasView flips the Y-axis for display (CAD convention).
    """

    # Canvas background color (beige/cream)
    CANVAS_COLOR = QColor("#f5f5dc")

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
        self._calibration_markers: list[QGraphicsLineItem | QGraphicsTextItem] = []

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

    # Background color for area outside canvas (darker for clear contrast)
    OUTSIDE_COLOR = QColor("#707070")  # Medium-dark gray

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the scene background.

        Fills the visible area with gray, then draws the canvas area in beige.
        """
        # First fill the entire visible rect with gray (outside canvas area)
        painter.fillRect(rect, QBrush(self.OUTSIDE_COLOR))

        # Then draw canvas area (beige rectangle) on top
        canvas_rect = QRectF(0, 0, self._width_cm, self._height_cm)
        painter.fillRect(canvas_rect, QBrush(self.CANVAS_COLOR))

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
        self._draw_calibration_marker(point, len(self._calibration_points))

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

    def _draw_calibration_marker(self, point: QPointF, number: int) -> None:
        """Draw a calibration marker at the given point.

        Args:
            point: The point in scene coordinates
            number: The point number (1 or 2)
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

        # Draw number label
        text = QGraphicsTextItem(str(number))
        text.setDefaultTextColor(Qt.GlobalColor.red)
        text.setPos(point.x() + 20, point.y() - 20)
        text.setZValue(1000)  # On top of everything
        self.addItem(text)
        self._calibration_markers.append(text)

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
