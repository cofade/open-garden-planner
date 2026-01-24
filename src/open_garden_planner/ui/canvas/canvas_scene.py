"""Canvas scene for the garden planner.

The scene holds all the garden objects and manages their rendering.
Coordinates are in centimeters with Y-axis pointing down (Qt convention).
The view handles the Y-flip for display.
"""

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsScene


class CanvasScene(QGraphicsScene):
    """Graphics scene for the garden canvas.

    The scene uses centimeters as the coordinate unit.
    Origin is at top-left (Qt convention), with Y increasing downward.
    The CanvasView flips the Y-axis for display (CAD convention).
    """

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
        self.setSceneRect(QRectF(0, 0, width_cm, height_cm))

        # Set background color
        self.setBackgroundBrush(QColor("#f5f5dc"))  # Beige/cream color

    @property
    def width_cm(self) -> float:
        """Width of the canvas in centimeters."""
        return self._width_cm

    @property
    def height_cm(self) -> float:
        """Height of the canvas in centimeters."""
        return self._height_cm

    def resize_canvas(self, width_cm: float, height_cm: float) -> None:
        """Resize the canvas.

        Args:
            width_cm: New width in centimeters
            height_cm: New height in centimeters
        """
        self._width_cm = width_cm
        self._height_cm = height_cm
        self.setSceneRect(QRectF(0, 0, width_cm, height_cm))
