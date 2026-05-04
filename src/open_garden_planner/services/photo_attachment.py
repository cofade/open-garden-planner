"""Photo attachment helper (US-12.7, also reused by US-12.9).

Encodes user-supplied photos into a base64 JPEG string for embedding inside
.ogp record dicts. Resizes to ``max_edge_px`` (default 1024) preserving
aspect ratio and re-encodes at JPEG quality 85, keeping per-photo size in
the order of tens of KB regardless of camera resolution.

Pure utility — no Qt-widget state, no project-manager coupling.
"""
from __future__ import annotations

import base64
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QImage, QPixmap

DEFAULT_MAX_EDGE_PX = 1024
DEFAULT_JPEG_QUALITY = 85


class PhotoAttachmentError(ValueError):
    """Raised when a photo cannot be loaded or encoded."""


def encode_photo_to_base64(
    path: Path | str,
    max_edge_px: int = DEFAULT_MAX_EDGE_PX,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> str:
    """Load ``path``, downscale to ``max_edge_px`` max edge, re-encode JPEG, b64.

    Args:
        path: Image file path readable by ``QImage`` (PNG/JPEG/BMP/etc.).
        max_edge_px: Longest edge after resize. The shorter edge is scaled
            proportionally. Images already smaller are not upscaled.
        quality: JPEG quality 0–100; default 85 is a good size/quality balance.

    Returns:
        Base64-encoded JPEG string (no MIME prefix).

    Raises:
        PhotoAttachmentError: Path is unreadable or contents are not an image.
    """
    p = Path(path)
    image = QImage(str(p))
    if image.isNull():
        raise PhotoAttachmentError(f"Cannot load image: {p}")

    width, height = image.width(), image.height()
    longest = max(width, height)
    if longest > max_edge_px:
        mode = Qt.TransformationMode.SmoothTransformation
        if width >= height:
            scaled = image.scaledToWidth(max_edge_px, mode)
        else:
            scaled = image.scaledToHeight(max_edge_px, mode)
    else:
        scaled = image

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not scaled.save(buffer, "JPEG", quality):
        raise PhotoAttachmentError(f"Cannot encode JPEG: {p}")
    raw = bytes(buffer.data())
    buffer.close()

    return base64.b64encode(raw).decode("ascii")


def decode_photo_from_base64(b64: str) -> QPixmap:
    """Decode a base64 JPEG string back into a ``QPixmap`` for display.

    Returns an empty ``QPixmap`` on decode failure rather than raising — UI
    code can fall back to a placeholder without try/except clutter.
    """
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError):
        return QPixmap()
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(raw))
    return pixmap
