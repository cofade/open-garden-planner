"""Canvas scene for the garden planner.

The scene holds all the garden objects and manages their rendering.
Coordinates are in centimeters with Y-axis pointing down (Qt convention).
The view handles the Y-flip for display.
"""

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QBrush, QColor, QPainter
from PyQt6.QtWidgets import QGraphicsScene


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

        Only draws the canvas area in beige; outside is handled by the view.
        """
        # Draw canvas area (beige rectangle)
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
