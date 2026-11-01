"""Background image item for the canvas.

Displays an imported image (satellite photo, etc.) that can be calibrated
to real-world scale.

Large site plans
----------------
Qt refuses to decode an image whose *decoded* size exceeds its process-wide
allocation limit (256 MB by default), so a 9000 x 8000 RGBA PNG — a 294 kB
file — fails to load even on a machine with plenty of memory (#659).
:data:`DECODE_ALLOCATION_LIMIT_MB` raises that limit for the duration of one
background decode only. The item then keeps the pixmap twice (the original for
serialization plus the vertically flipped copy it paints), which is why
:data:`MAX_BACKGROUND_PIXELS` bounds the accepted size rather than the decoded
bytes alone.

The embedded PNG is encoded once and reused (#660): a project snapshot is taken
on every Agent API read and every autosave, and re-encoding a 72-megapixel
background costs about 1.2 s of main-thread time per read for unchanged bytes.
"""

import base64
import logging
import math
from collections.abc import Iterator
from contextlib import contextmanager

from PyQt6.QtCore import (
    QBuffer,
    QByteArray,
    QCoreApplication,
    QIODevice,
    QPointF,
    QSize,
    Qt,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImageReader,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsSceneContextMenuEvent,
    QInputDialog,
    QMenu,
)

from open_garden_planner.core.plan_io import PlanValidationError, finite_number

logger = logging.getLogger(__name__)

# Decoded-size allowance for ONE background decode, in MB. Qt's default is 256,
# which rejects any image over ~67 megapixels at RGBA8 — below a real site plan
# (the reported case is 9917 x 7009: 278 MB, 265 MiB, decoded). #659.
DECODE_ALLOCATION_LIMIT_MB = 512

# Accepted pixel count of a background. The item holds the decoded pixmap twice
# (original + flipped copy), so this caps one copy at ~458 MiB and a loaded
# background at ~916 MiB. The largest real site plan seen is 69.5 MP. A 16-bit
# source over ~67 MP can still exceed the decoder budget above; that failure is
# reported by the generic load message rather than this cap.
MAX_BACKGROUND_PIXELS = 120_000_000


@contextmanager
def _decode_budget(limit_mb: int = DECODE_ALLOCATION_LIMIT_MB) -> Iterator[None]:
    """Permit a decoded image up to ``limit_mb`` MB for the duration of the block.

    ``QImageReader.setAllocationLimit`` is a process-wide static, not a per-reader
    setting, so the previous value is restored in ``finally``. A raise that leaked
    would let every later decode in the application allocate more than it should.
    Zero means *disabled*; Qt ignores a negative argument and ``allocationLimit()``
    never returns one, so 0 is the only sentinel to special-case. A budget that is
    already disabled or already larger is left untouched rather than narrowed.
    Every caller runs on the GUI thread — the import action, plan load and the
    satellite import — so the widened window is not observable by another decode.
    """
    previous = QImageReader.allocationLimit()
    raised = 0 < previous < limit_mb
    if raised:
        QImageReader.setAllocationLimit(limit_mb)
    try:
        yield
    finally:
        if raised:
            QImageReader.setAllocationLimit(previous)


def _check_image_size(size: QSize) -> None:
    """Refuse a background larger than :data:`MAX_BACKGROUND_PIXELS`.

    The probe reads the image header only, so an oversized file is refused
    before the decoder allocates anything. A format that cannot report its size
    is left to the decoder's own allocation limit (the outer backstop).
    """
    if not size.isValid():
        return
    pixels = size.width() * size.height()
    if pixels <= MAX_BACKGROUND_PIXELS:
        return
    # Round the measured size UP: a 120.05 MP image formatted with one decimal
    # would otherwise read "120.0 megapixels ... limited to 120", i.e. refused
    # for exceeding a limit it appears to equal. The limit takes the same
    # rounding so the two figures cannot disagree if the constant ever changes.
    def megapixels(px: int) -> float:
        return math.ceil(px / 100_000) / 10

    raise ValueError(
        QCoreApplication.translate(
            "BackgroundImageItem",
            "This image is {megapixels} megapixels and needs about {megabytes} MB "
            "of memory. Background images are limited to {limit} megapixels.",
        ).format(
            megapixels=f"{megapixels(pixels):.1f}",
            # The item keeps the decoded pixmap twice (original + flipped copy);
            # reporting one copy would understate the cost of what is being refused.
            megabytes=pixels * 8 // 1_000_000,
            limit=f"{megapixels(MAX_BACKGROUND_PIXELS):.1f}",
        )
    )


def _load_pixmap_from_file(image_path: str) -> QPixmap:
    """Decode a background image from disk under the raised allocation budget."""
    with _decode_budget():
        _check_image_size(QImageReader(image_path).size())
        pixmap = QPixmap(image_path)
    if pixmap.isNull():
        raise ValueError(
            QCoreApplication.translate(
                "BackgroundImageItem", "Failed to load image: {path}"
            ).format(path=image_path)
        )
    return pixmap


def _load_pixmap_from_data(data: bytes) -> QPixmap:
    """Decode an embedded background image under the raised allocation budget."""
    payload = QByteArray(data)
    with _decode_budget():
        buffer = QBuffer()
        buffer.setData(payload)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        try:
            _check_image_size(QImageReader(buffer).size())
        finally:
            buffer.close()
        pixmap = QPixmap()
        loaded = pixmap.loadFromData(payload)
    if not loaded or pixmap.isNull():
        raise ValueError(
            QCoreApplication.translate(
                "BackgroundImageItem", "Failed to load image from embedded data"
            )
        )
    return pixmap


def _encode_png_base64(pixmap: QPixmap) -> str:
    """Encode a pixmap as a base64 PNG for embedding in the project file."""
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    saved = pixmap.save(buf, "PNG")
    encoded = base64.b64encode(bytes(buf.data())).decode("ascii")
    buf.close()
    if not saved:
        # Internal invariant, not user input: an unencodable pixmap must fail the
        # save loudly rather than write an empty image_data that reloads as a
        # placeholder (the data-loss shape AUD-043 exists to prevent). Translated
        # because the app's save-error dialog shows str(error) (application.py).
        raise RuntimeError(
            QCoreApplication.translate(
                "BackgroundImageItem",
                "Failed to encode the background image as PNG",
            )
        )
    return encoded


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
        _placeholder: bool = False,
        _raw_dict: dict | None = None,
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
            _placeholder: If True, renders a placeholder when the file is missing/undecodable.
            _raw_dict: Original serialized dictionary preserved for re-saving when in placeholder mode.
        """
        super().__init__(parent)

        self._image_path = image_path
        self._opacity = 1.0
        self._locked = False
        self._scale_factor = 1.0  # pixels per cm after calibration
        self._geo_metadata: dict | None = geo_metadata
        self._is_placeholder: bool = _placeholder
        self._raw_dict: dict | None = _raw_dict
        # Encoded-once cache for to_dict(); see _cached_png_base64 (#660).
        self._encoded_png_b64: str | None = None
        self._encoded_png_cache_key: int = 0

        if _placeholder:
            w = 300
            h = 200
            placeholder = QPixmap(w, h)
            placeholder.fill(QColor(240, 240, 240, 200))
            painter = QPainter(placeholder)
            pen = QPen(QColor(180, 50, 50), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(1, 1, w - 2, h - 2)
            painter.setPen(QColor(100, 100, 100))
            font = QFont("Arial", 9)
            painter.setFont(font)
            from pathlib import Path

            name_hint = Path(image_path).name if image_path else "embedded"
            hint_text = f"[Missing Image: {name_hint}]"
            painter.drawText(placeholder.rect(), Qt.AlignmentFlag.AlignCenter, hint_text)
            painter.end()

            self._original_pixmap = placeholder
        else:
            # Load the image — either from embedded bytes or from disk path
            if _pixmap_data is not None:
                self._original_pixmap = _load_pixmap_from_data(_pixmap_data)
            else:
                self._original_pixmap = _load_pixmap_from_file(image_path)

        # Derive the scale from geo metadata so the satellite image is true-to-life.
        # 1 cm = 0.01 m → px_per_cm = 0.01 / meters_per_pixel.
        # Gate on not _is_placeholder so missing images don't distort placeholder bounds (FIND-02).
        if not self._is_placeholder and geo_metadata is not None:
            mpp = geo_metadata.get("meters_per_pixel")
            if mpp is not None and mpp > 0:
                self._scale_factor = 0.01 / float(mpp)

        # Flip vertically to compensate for view's Y-flip transform (CAD convention)
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
        if not self._is_placeholder and self._scale_factor != 1.0:
            self._apply_checked_scale()

    def _apply_checked_scale(self) -> None:
        """Check decoded pixel extents before applying calibration to Qt."""
        factor = finite_number(self._scale_factor, "background.scale_factor")
        if factor <= 0:
            raise PlanValidationError("background.scale_factor", "positive")
        scale = finite_number(1.0 / factor, "background.scale")
        for dimension in (self.pixmap().width(), self.pixmap().height()):
            finite_number(dimension * scale, "background.scaled_extent")
        self.setScale(scale)

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

    @property
    def is_placeholder(self) -> bool:
        """Whether this item is a placeholder for a missing or undecodable image."""
        return self._is_placeholder

    def to_dict(self) -> dict:
        """Serialize the item to a dictionary for saving.

        The original pixmap is embedded as a base64-encoded PNG so that the
        project file is self-contained and portable across machines.
        ``image_path`` is kept as a human-readable hint only — it is not used
        when loading if ``image_data`` is present.
        If in placeholder mode, the original raw dictionary is preserved so that
        saving doesn't lose the missing image's metadata or image reference (AUD-043).

        The encoded payload is cached (#660): callers take a snapshot on every
        Agent API read and every autosave, and the bytes cannot change without
        the pixmap changing.
        """
        if getattr(self, "_is_placeholder", False) and getattr(self, "_raw_dict", None):
            res = self._raw_dict.copy()
            res["position"] = {"x": self.pos().x(), "y": self.pos().y()}
            return res

        data: dict = {
            "type": "background_image",
            "image_path": self._image_path,
            "image_data": self._cached_png_base64(),
            "position": {"x": self.pos().x(), "y": self.pos().y()},
            "opacity": self._opacity,
            "locked": self._locked,
            "scale_factor": self._scale_factor,
        }
        if self._geo_metadata is not None:
            data["geo_metadata"] = self._geo_metadata
        return data

    def _cached_png_base64(self) -> str:
        """Return the embedded base64 PNG, encoding at most once per revision.

        ``QPixmap.cacheKey()`` changes whenever the pixmap's contents change, so
        the cache can never outlive the pixels it was made from — including for
        a future "replace image" action. Called on the GUI thread only, like
        every other member of the item.
        """
        cache_key = self._original_pixmap.cacheKey()
        if self._encoded_png_b64 is None or self._encoded_png_cache_key != cache_key:
            self._encoded_png_b64 = _encode_png_base64(self._original_pixmap)
            self._encoded_png_cache_key = cache_key
        return self._encoded_png_b64

    @classmethod
    def from_dict(cls, data: dict) -> "BackgroundImageItem":
        """Create an item from a dictionary.

        Prefers ``image_data`` (base64 PNG, portable) when present; falls back
        to ``image_path`` for legacy project files that pre-date embedding.
        Honors a saved ``geo_metadata`` block (present for satellite imports);
        older projects without one keep loading unchanged.
        If image file loading or decoding fails, returns a placeholder item
        that preserves data on re-save (AUD-043). The refusal reason is logged:
        an image above the size cap otherwise degrades to a dashed
        "[Missing Image: ...]" box with nothing in the log to explain why.
        """
        image_path = data.get("image_path", "")
        geo_metadata = data.get("geo_metadata")
        item: BackgroundImageItem
        try:
            if "image_data" in data:
                pixmap_bytes = base64.b64decode(data["image_data"])
                item = cls(
                    image_path,
                    _pixmap_data=pixmap_bytes,
                    geo_metadata=geo_metadata,
                )
            else:
                item = cls(image_path, geo_metadata=geo_metadata)
        except PlanValidationError:
            raise
        except Exception as error:
            logger.warning(
                "Background image could not be decoded; loading a placeholder "
                "that keeps its data on re-save: path=%r reason=%s",
                image_path,
                error,
            )
            item = cls(
                image_path,
                geo_metadata=geo_metadata,
                _placeholder=True,
                _raw_dict=data,
            )

        pos = data.get("position", {})
        item.setPos(QPointF(float(pos.get("x", 0.0)), float(pos.get("y", 0.0))))
        item.opacity = data.get("opacity", 1.0)
        item.locked = data.get("locked", False)
        # The saved scale_factor wins over the geo-derived default — the user
        # may have manually re-calibrated since import.
        item._scale_factor = data.get("scale_factor", item._scale_factor)
        if not getattr(item, "_is_placeholder", False):
            item._apply_checked_scale()
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
        attribution: str = "",
        fetched_at: str = "",
    ) -> "BackgroundImageItem":
        """Convenience factory for satellite imports.

        The caller (``application._on_load_satellite_background``) builds the
        PNG bytes from the PIL image and passes the geo data through; the
        item ends up with a correct real-world scale automatically.

        ``source`` distinguishes the Static-API path from the JS-API view
        capture (issue #346); a non-empty ``attribution`` line (the Google
        copyright strip baked into captures) is persisted in
        ``geo_metadata`` so the provenance survives save/load.
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
        if attribution:
            # Additive key — older binaries ignore it, no FILE_VERSION bump.
            geo_metadata["attribution"] = attribution
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
