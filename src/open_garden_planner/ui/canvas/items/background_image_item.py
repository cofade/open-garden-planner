"""Background image item for the canvas.

Displays an imported image (satellite photo, etc.) that can be calibrated
to real-world scale.
"""

import base64

from PyQt6.QtCore import QBuffer, QByteArray, QCoreApplication, QIODevice, QPointF
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
        *,
        _pixmap_data: bytes | None = None,
        geo_metadata: dict | None = None,
    ) -> None:
        """Initialize the background image item.

        Args:
            image_path: Path to the image file (used as display hint when _pixmap_data is given)
            parent: Parent graphics item
            _pixmap_data: Raw PNG bytes to load from (internal use by from_dict only).
                When provided, image_path is stored as a hint only and the file need not exist.
            geo_metadata: Optional geo-referencing data from a satellite fetch.
                When provided, ``_scale_factor`` is derived from ``meters_per_pixel``
                so the image lands on the canvas with a true real-world scale,
                bypassing the manual calibration step. See
                ``services/google_maps_service.py``.
        """
        super().__init__(parent)

        self._image_path = image_path
        self._opacity = 1.0
        self._locked = False
        self._scale_factor = 1.0  # pixels per cm after calibration
        self._geo_metadata: dict | None = geo_metadata

        # Load the image — either from embedded bytes or from disk path
        if _pixmap_data is not None:
            self._original_pixmap = QPixmap()
            self._original_pixmap.loadFromData(QByteArray(_pixmap_data))
            if self._original_pixmap.isNull():
                raise ValueError("Failed to load image from embedded data")
        else:
            self._original_pixmap = QPixmap(image_path)
            if self._original_pixmap.isNull():
                raise ValueError(f"Failed to load image: {image_path}")

        # Derive the scale from geo metadata so the satellite image is true-to-life.
        # 1 cm = 0.01 m → px_per_cm = 0.01 / meters_per_pixel.
        if geo_metadata is not None:
            mpp = geo_metadata.get("meters_per_pixel")
            if mpp is not None and mpp > 0:
                self._scale_factor = 0.01 / float(mpp)

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

        # Apply geo-derived scale so the image lands at true size on the canvas.
        if self._scale_factor != 1.0:
            self.setScale(1.0 / self._scale_factor)

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

    @property
    def geo_metadata(self) -> dict | None:
        """Geo-referencing data if the image was loaded from a satellite fetch."""
        return self._geo_metadata

    def to_dict(self) -> dict:
        """Serialize the item to a dictionary for saving.

        The original pixmap is embedded as a base64-encoded PNG so that the
        project file is self-contained and portable across machines.
        ``image_path`` is kept as a human-readable hint only — it is not used
        when loading if ``image_data`` is present.
        """
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        self._original_pixmap.save(buf, "PNG")
        image_data_b64 = base64.b64encode(bytes(buf.data())).decode("ascii")
        buf.close()
        data: dict = {
            "type": "background_image",
            "image_path": self._image_path,
            "image_data": image_data_b64,
            "position": {"x": self.pos().x(), "y": self.pos().y()},
            "opacity": self._opacity,
            "locked": self._locked,
            "scale_factor": self._scale_factor,
        }
        if self._geo_metadata is not None:
            data["geo_metadata"] = self._geo_metadata
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "BackgroundImageItem":
        """Create an item from a dictionary.

        Prefers ``image_data`` (base64 PNG, portable) when present; falls back
        to ``image_path`` for legacy project files that pre-date embedding.
        Honors a saved ``geo_metadata`` block (present for satellite imports);
        older projects without one keep loading unchanged.
        """
        image_path = data.get("image_path", "")
        geo_metadata = data.get("geo_metadata")
        if "image_data" in data:
            pixmap_bytes = base64.b64decode(data["image_data"])
            item = cls(
                image_path,
                _pixmap_data=pixmap_bytes,
                geo_metadata=geo_metadata,
            )
        else:
            item = cls(image_path, geo_metadata=geo_metadata)
        item.setPos(QPointF(data["position"]["x"], data["position"]["y"]))
        item.opacity = data.get("opacity", 1.0)
        item.locked = data.get("locked", False)
        # The saved scale_factor wins over the geo-derived default — the user
        # may have manually re-calibrated since import.
        item._scale_factor = data.get("scale_factor", item._scale_factor)
        item.setScale(1.0 / item._scale_factor)
        return item

    @classmethod
    def from_fetch_result(
        cls,
        image_path: str,
        png_bytes: bytes,
        *,
        meters_per_pixel: float,
        bbox_nw: tuple[float, float],
        bbox_se: tuple[float, float],
        zoom: int,
        source: str = "google_static_maps",
        fetched_at: str = "",
    ) -> "BackgroundImageItem":
        """Convenience factory for satellite imports.

        The caller (``application._on_load_satellite_background``) builds the
        PNG bytes from the PIL image and passes the geo data through; the
        item ends up with a correct real-world scale automatically.
        """
        center_lat = (bbox_nw[0] + bbox_se[0]) / 2.0
        center_lng = (bbox_nw[1] + bbox_se[1]) / 2.0
        geo_metadata = {
            "center": [center_lat, center_lng],
            "bbox_nw": list(bbox_nw),
            "bbox_se": list(bbox_se),
            "zoom": zoom,
            "meters_per_pixel": meters_per_pixel,
            "source": source,
            "fetched_at": fetched_at,
        }
        return cls(image_path, _pixmap_data=png_bytes, geo_metadata=geo_metadata)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show context menu for background image options."""
        _ = QCoreApplication.translate
        menu = QMenu()

        # Calibrate action
        calibrate_action = menu.addAction(_("BackgroundImageItem", "Calibrate Scale..."))
        calibrate_action.triggered.connect(self._show_calibration_dialog)

        menu.addSeparator()

        # Opacity action — embed the current value in the translated string at runtime
        opacity_label = _("BackgroundImageItem", "Set Opacity ({pct}%)...").format(
            pct=int(self._opacity * 100)
        )
        opacity_action = menu.addAction(opacity_label)
        opacity_action.triggered.connect(self._show_opacity_dialog)

        # Lock/Unlock action
        lock_text = (
            _("BackgroundImageItem", "Unlock Image")
            if self._locked
            else _("BackgroundImageItem", "Lock Image")
        )
        lock_action = menu.addAction(lock_text)
        lock_action.triggered.connect(self._toggle_lock)

        menu.addSeparator()

        # Remove action
        remove_action = menu.addAction(_("BackgroundImageItem", "Remove Image"))
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
