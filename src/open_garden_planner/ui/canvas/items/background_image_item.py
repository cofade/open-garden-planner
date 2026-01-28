"""Background image item for the canvas.

Displays an imported image (satellite photo, etc.) that can be calibrated
to real-world scale.
"""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsSceneContextMenuEvent,
    QInputDialog,
    QMenu,
)


class BackgroundImageItem(QGraphicsPixmapItem):
    """A background image that can be scaled and positioned.

    The image is rendered behind all other items and can be calibrated
    to match real-world dimensions.
    """

    def __init__(
        self,
        image_path: str,
        parent: QGraphicsItem | None = None,
    ) -> None:
        """Initialize the background image item.

        Args:
            image_path: Path to the image file
            parent: Parent graphics item
        """
        super().__init__(parent)

        self._image_path = image_path
        self._opacity = 1.0
        self._locked = False
        self._scale_factor = 1.0  # pixels per cm after calibration

        # Load the image
        self._original_pixmap = QPixmap(image_path)
        if self._original_pixmap.isNull():
            raise ValueError(f"Failed to load image: {image_path}")

        # Flip vertically to compensate for view's Y-flip transform (CAD convention)
        from PyQt6.QtGui import QTransform
        flip_transform = QTransform().scale(1, -1)
        flipped_pixmap = self._original_pixmap.transformed(flip_transform)
        self.setPixmap(flipped_pixmap)

        # Set up item properties
        self.setZValue(-1000)  # Behind all other items
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        # Transform origin at center for easier manipulation
        self.setTransformOriginPoint(self.boundingRect().center())

        # Enable clipping to canvas bounds
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, True)

    def shape(self):
        """Return the shape for clipping to canvas bounds."""
        from PyQt6.QtGui import QPainterPath

        path = QPainterPath()
        if self.scene():
            # Get canvas bounds from scene
            from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
            if isinstance(self.scene(), CanvasScene):
                canvas_rect = self.scene().canvas_rect
                # Convert to item coordinates
                item_rect = self.mapRectFromScene(canvas_rect)
                path.addRect(item_rect)
                return path

        # Default: entire pixmap
        path.addRect(self.boundingRect())
        return path

    @property
    def image_path(self) -> str:
        """Path to the original image file."""
        return self._image_path

    @property
    def opacity(self) -> float:
        """Image opacity (0.0 to 1.0)."""
        return self._opacity

    @opacity.setter
    def opacity(self, value: float) -> None:
        """Set image opacity."""
        self._opacity = max(0.0, min(1.0, value))
        self.setOpacity(self._opacity)
        self.update()

    @property
    def locked(self) -> bool:
        """Whether the image is locked (cannot be moved)."""
        return self._locked

    @locked.setter
    def locked(self, value: bool) -> None:
        """Set locked state."""
        self._locked = value
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not value)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not value)

    @property
    def scale_factor(self) -> float:
        """Scale factor: pixels per centimeter."""
        return self._scale_factor

    def calibrate(self, pixels: float, centimeters: float) -> None:
        """Calibrate the image scale based on a known distance.

        Args:
            pixels: Distance in image pixels
            centimeters: Real-world distance in centimeters
        """
        if centimeters <= 0 or pixels <= 0:
            return

        # Calculate new scale: how many pixels per cm
        self._scale_factor = pixels / centimeters

        # Apply scale transform so 1 scene unit = 1 cm
        scale = 1.0 / self._scale_factor
        self.setScale(scale)

    def image_size_pixels(self) -> tuple[int, int]:
        """Get original image size in pixels."""
        return self._original_pixmap.width(), self._original_pixmap.height()

    def image_size_cm(self) -> tuple[float, float]:
        """Get image size in centimeters (after calibration)."""
        w, h = self.image_size_pixels()
        return w / self._scale_factor, h / self._scale_factor

    def to_dict(self) -> dict:
        """Serialize the item to a dictionary for saving."""
        return {
            "type": "background_image",
            "image_path": self._image_path,
            "position": {"x": self.pos().x(), "y": self.pos().y()},
            "opacity": self._opacity,
            "locked": self._locked,
            "scale_factor": self._scale_factor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackgroundImageItem":
        """Create an item from a dictionary."""
        item = cls(data["image_path"])
        item.setPos(QPointF(data["position"]["x"], data["position"]["y"]))
        item.opacity = data.get("opacity", 1.0)
        item.locked = data.get("locked", False)
        item._scale_factor = data.get("scale_factor", 1.0)
        # Apply saved scale
        scale = 1.0 / item._scale_factor
        item.setScale(scale)
        return item

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show context menu for background image options."""
        menu = QMenu()

        # Calibrate action
        calibrate_action = menu.addAction("Calibrate Scale...")
        calibrate_action.triggered.connect(self._show_calibration_dialog)

        menu.addSeparator()

        # Opacity action
        opacity_action = menu.addAction(f"Set Opacity ({int(self._opacity * 100)}%)...")
        opacity_action.triggered.connect(self._show_opacity_dialog)

        # Lock/Unlock action
        lock_text = "Unlock Image" if self._locked else "Lock Image"
        lock_action = menu.addAction(lock_text)
        lock_action.triggered.connect(self._toggle_lock)

        menu.addSeparator()

        # Remove action
        remove_action = menu.addAction("Remove Image")
        remove_action.triggered.connect(self._remove_self)

        menu.exec(event.screenPos())

    def _show_calibration_dialog(self) -> None:
        """Start inline calibration mode."""
        if self.scene():
            # Import here to avoid circular dependency
            from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
            if isinstance(self.scene(), CanvasScene):
                self.scene().start_image_calibration(self)

    def _show_opacity_dialog(self) -> None:
        """Show dialog to set opacity."""
        value, ok = QInputDialog.getInt(
            None,
            "Set Image Opacity",
            "Opacity (0-100%):",
            int(self._opacity * 100),
            0,
            100,
            5,
        )
        if ok:
            self.opacity = value / 100.0

    def _toggle_lock(self) -> None:
        """Toggle lock state."""
        self.locked = not self._locked

    def _remove_self(self) -> None:
        """Remove this image from the scene."""
        if self.scene():
            self.scene().removeItem(self)
