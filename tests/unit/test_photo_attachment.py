"""Unit tests for the photo attachment helper (US-12.7, reused by US-12.9)."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest
from PyQt6.QtGui import QImage, qRgb

from open_garden_planner.services.photo_attachment import (
    PhotoAttachmentError,
    decode_photo_from_base64,
    encode_photo_to_base64,
)


def _write_png(path: Path, width: int, height: int) -> None:
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(qRgb(120, 200, 120))
    assert img.save(str(path), "PNG"), f"failed to save {path}"


class TestEncodePhotoToBase64:
    def test_oversized_image_is_resized_to_max_edge(
        self, tmp_path: Path, qtbot: object  # noqa: ARG002 — Qt init
    ) -> None:
        src = tmp_path / "big.png"
        _write_png(src, 2000, 1500)
        b64 = encode_photo_to_base64(src, max_edge_px=1024)
        pix = decode_photo_from_base64(b64)
        # Longest edge should be exactly 1024; aspect preserved.
        assert max(pix.width(), pix.height()) == 1024
        # Aspect ratio (4:3) preserved within ±1 px rounding.
        assert abs(pix.width() / pix.height() - 2000 / 1500) < 0.02

    def test_smaller_image_is_not_upscaled(
        self, tmp_path: Path, qtbot: object  # noqa: ARG002
    ) -> None:
        src = tmp_path / "small.png"
        _write_png(src, 800, 600)
        b64 = encode_photo_to_base64(src, max_edge_px=1024)
        pix = decode_photo_from_base64(b64)
        assert pix.width() == 800
        assert pix.height() == 600

    def test_unreadable_file_raises(
        self, tmp_path: Path, qtbot: object  # noqa: ARG002
    ) -> None:
        bogus = tmp_path / "not_an_image.txt"
        bogus.write_text("not an image")
        with pytest.raises(PhotoAttachmentError):
            encode_photo_to_base64(bogus)

    def test_round_trip_produces_valid_base64(
        self, tmp_path: Path, qtbot: object  # noqa: ARG002
    ) -> None:
        src = tmp_path / "rt.png"
        _write_png(src, 100, 100)
        b64 = encode_photo_to_base64(src)
        # Must be ascii and decodable
        raw = base64.b64decode(b64, validate=True)
        # JPEG SOI marker
        assert raw.startswith(b"\xff\xd8")


class TestDecodePhotoFromBase64:
    def test_invalid_base64_returns_empty_pixmap(
        self, qtbot: object  # noqa: ARG002
    ) -> None:
        pix = decode_photo_from_base64("not-base64!!!")
        assert pix.isNull()

    def test_valid_base64_non_image_returns_empty_pixmap(
        self, qtbot: object  # noqa: ARG002
    ) -> None:
        """Well-formed base64 whose payload is not an image must not crash;
        ``QPixmap.loadFromData`` returns False and we surface an empty pixmap."""
        garbage_b64 = base64.b64encode(b"this is plain text, not JPEG bytes").decode(
            "ascii"
        )
        pix = decode_photo_from_base64(garbage_b64)
        assert pix.isNull()
