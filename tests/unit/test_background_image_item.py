"""Unit tests for BackgroundImageItem."""

import base64
import logging
from pathlib import Path

import pytest
from PyQt6.QtCore import QBuffer, QIODevice, QPointF, QSize
from PyQt6.QtGui import QColor, QImage, QImageReader, QPixmap
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.ui.canvas.items import BackgroundImageItem
from open_garden_planner.ui.canvas.items import background_image_item as bg_module


@pytest.fixture
def test_image_path(tmp_path: Path) -> Path:
    """Create a test image file.

    Args:
        tmp_path: Temporary directory provided by pytest

    Returns:
        Path to a test PNG image
    """
    # Create a simple test image (100x100 pixels, white)
    pixmap = QPixmap(100, 100)
    pixmap.fill()  # Fill with white

    image_path = tmp_path / "test_image.png"
    pixmap.save(str(image_path))
    return image_path


class TestBackgroundImageItem:
    """Tests for BackgroundImageItem class."""

    def test_creation(self, qtbot, test_image_path: Path) -> None:
        """Test basic background image creation."""
        item = BackgroundImageItem(str(test_image_path))

        assert item.image_path == str(test_image_path)
        assert not item.pixmap().isNull()
        assert item.zValue() == -1000  # Behind all other items
        assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable

    def test_invalid_image_path(self, qtbot) -> None:
        """Test that invalid image path raises ValueError."""
        with pytest.raises(ValueError, match="Failed to load image"):
            BackgroundImageItem("/nonexistent/path/to/image.png")

    def test_default_properties(self, qtbot, test_image_path: Path) -> None:
        """Test default property values."""
        item = BackgroundImageItem(str(test_image_path))

        assert item.opacity == 1.0
        assert not item.locked
        assert item.scale_factor == 1.0

    def test_opacity_property(self, qtbot, test_image_path: Path) -> None:
        """Test opacity property getter and setter."""
        item = BackgroundImageItem(str(test_image_path))

        # Set valid opacity
        item.opacity = 0.5
        assert item.opacity == 0.5
        assert item.opacity == pytest.approx(0.5)  # Check the property value

        # Set opacity out of range (should clamp)
        item.opacity = 1.5
        assert item.opacity == 1.0

        item.opacity = -0.5
        assert item.opacity == 0.0

    def test_locked_property(self, qtbot, test_image_path: Path) -> None:
        """Test locked property getter and setter."""
        item = BackgroundImageItem(str(test_image_path))

        # Initially not locked
        assert not item.locked
        assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable

        # Lock the item — movable is disabled but selectable stays on for right-click access
        item.locked = True
        assert item.locked
        assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable

        # Unlock the item
        item.locked = False
        assert not item.locked
        assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable

    def test_calibration(self, qtbot, test_image_path: Path) -> None:
        """Test image calibration."""
        item = BackgroundImageItem(str(test_image_path))

        # Calibrate: 100 pixels = 500 cm
        item.calibrate(pixels=100, centimeters=500)

        # Scale factor should be 100/500 = 0.2 pixels per cm
        assert item.scale_factor == pytest.approx(0.2)

        # The item's scale should be 1/scale_factor = 5.0
        assert item.scale() == pytest.approx(5.0)

    def test_calibration_with_zero_values(self, qtbot, test_image_path: Path) -> None:
        """Test that calibration with zero or negative values is ignored."""
        item = BackgroundImageItem(str(test_image_path))

        initial_scale_factor = item.scale_factor

        # These should not change the scale factor
        item.calibrate(pixels=0, centimeters=100)
        assert item.scale_factor == initial_scale_factor

        item.calibrate(pixels=100, centimeters=0)
        assert item.scale_factor == initial_scale_factor

        item.calibrate(pixels=-100, centimeters=100)
        assert item.scale_factor == initial_scale_factor

    def test_image_size_pixels(self, qtbot, test_image_path: Path) -> None:
        """Test getting image size in pixels."""
        item = BackgroundImageItem(str(test_image_path))

        width, height = item.image_size_pixels()
        assert width == 100
        assert height == 100

    def test_image_size_cm(self, qtbot, test_image_path: Path) -> None:
        """Test getting image size in centimeters."""
        item = BackgroundImageItem(str(test_image_path))

        # Before calibration, scale_factor is 1.0
        width, height = item.image_size_cm()
        assert width == pytest.approx(100.0)  # 100 pixels / 1.0 = 100 cm
        assert height == pytest.approx(100.0)

        # After calibration: 100 pixels = 200 cm
        item.calibrate(pixels=100, centimeters=200)
        width, height = item.image_size_cm()
        assert width == pytest.approx(200.0)  # 100 pixels / 0.5 = 200 cm
        assert height == pytest.approx(200.0)

    def test_to_dict(self, qtbot, test_image_path: Path) -> None:
        """Test serialization to dictionary.

        Verifies that image data is embedded as base64 (portable) and that all
        other fields are preserved correctly.
        """
        import base64

        item = BackgroundImageItem(str(test_image_path))
        item.setPos(QPointF(100, 200))
        item.opacity = 0.7
        item.locked = True
        item.calibrate(pixels=100, centimeters=500)

        data = item.to_dict()

        assert data["type"] == "background_image"
        # image_path is kept as a human-readable hint
        assert data["image_path"] == str(test_image_path)
        # image_data must be present and must be valid base64-encoded bytes
        assert "image_data" in data
        assert isinstance(data["image_data"], str)
        decoded = base64.b64decode(data["image_data"])
        assert len(decoded) > 0
        assert data["position"]["x"] == pytest.approx(100.0)
        assert data["position"]["y"] == pytest.approx(200.0)
        assert data["opacity"] == pytest.approx(0.7)
        assert data["locked"] is True
        assert data["scale_factor"] == pytest.approx(0.2)

    def test_from_dict_with_image_data(self, qtbot, test_image_path: Path) -> None:
        """Test deserialization from a dict that contains embedded image_data.

        The source file path need not be valid — the image is loaded from
        the base64-encoded PNG bytes.
        """
        # Generate base64 payload from the fixture image
        source = BackgroundImageItem(str(test_image_path))
        embedded_data = source.to_dict()["image_data"]

        data = {
            "type": "background_image",
            "image_path": "/nonexistent/path/photo.png",  # intentionally invalid
            "image_data": embedded_data,
            "position": {"x": 150.0, "y": 250.0},
            "opacity": 0.8,
            "locked": True,
            "scale_factor": 0.3,
        }

        item = BackgroundImageItem.from_dict(data)

        assert item.image_path == "/nonexistent/path/photo.png"
        assert not item.pixmap().isNull()
        assert item.pos().x() == pytest.approx(150.0)
        assert item.pos().y() == pytest.approx(250.0)
        assert item.opacity == pytest.approx(0.8)
        assert item.locked is True
        assert item.scale_factor == pytest.approx(0.3)
        assert item.scale() == pytest.approx(1.0 / 0.3)

    def test_from_dict_legacy_path_only(self, qtbot, test_image_path: Path) -> None:
        """Test backward-compat: old project files with only image_path still load."""
        data = {
            "type": "background_image",
            "image_path": str(test_image_path),  # valid path, no image_data
            "position": {"x": 150.0, "y": 250.0},
            "opacity": 0.8,
            "locked": True,
            "scale_factor": 0.3,
        }

        item = BackgroundImageItem.from_dict(data)

        assert item.image_path == str(test_image_path)
        assert not item.pixmap().isNull()
        assert item.pos().x() == pytest.approx(150.0)
        assert item.pos().y() == pytest.approx(250.0)
        assert item.opacity == pytest.approx(0.8)
        assert item.locked is True
        assert item.scale_factor == pytest.approx(0.3)
        assert item.scale() == pytest.approx(1.0 / 0.3)

    def test_round_trip_serialization(self, qtbot, test_image_path: Path) -> None:
        """Test that serialization and deserialization preserve all data."""
        original = BackgroundImageItem(str(test_image_path))
        original.setPos(QPointF(50, 75))
        original.opacity = 0.6
        original.locked = False
        original.calibrate(pixels=100, centimeters=400)

        data = original.to_dict()
        restored = BackgroundImageItem.from_dict(data)

        assert restored.image_path == original.image_path
        assert restored.pos() == original.pos()
        assert restored.opacity == pytest.approx(original.opacity)
        assert restored.locked == original.locked
        assert restored.scale_factor == pytest.approx(original.scale_factor)
        assert restored.scale() == pytest.approx(original.scale())

    def test_portable_load_without_source_file(
        self, qtbot, test_image_path: Path
    ) -> None:
        """Portable round-trip: image loads correctly even after the source file is deleted."""
        original = BackgroundImageItem(str(test_image_path))
        original.opacity = 0.5
        original.calibrate(pixels=100, centimeters=200)
        data = original.to_dict()

        # Delete the source file — simulates opening the project on another PC
        test_image_path.unlink()
        assert not test_image_path.exists()

        # Must succeed without the original file
        restored = BackgroundImageItem.from_dict(data)

        assert not restored.pixmap().isNull()
        assert restored.opacity == pytest.approx(0.5)
        assert restored.scale_factor == pytest.approx(0.5)


def _write_png(path: Path, width: int, height: int) -> Path:
    """Write a solid-colour PNG of the given pixel size."""
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(QColor(120, 140, 110))
    assert image.save(str(path), "PNG")
    return path


def _png_bytes(width: int, height: int) -> bytes:
    """Return a solid-colour PNG of the given pixel size as bytes."""
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(QColor(110, 130, 150))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    payload = bytes(buffer.data())
    buffer.close()
    return payload


class TestDecodeAllocationBudget:
    """#659: backgrounds larger than Qt's 256 MB default decode budget.

    A 2000 x 2000 RGBA image is 16 MB decoded, so lowering the process budget to
    4 MB puts it over the limit exactly as the 256 MB default does to the
    reported 9000 x 8000 site plan -- without allocating 275 MiB per copy in CI.
    """

    def test_an_image_above_the_process_limit_loads(self, qtbot, tmp_path: Path) -> None:
        path = _write_png(tmp_path / "site_plan.png", 2000, 2000)
        previous = QImageReader.allocationLimit()
        QImageReader.setAllocationLimit(4)
        try:
            assert QPixmap(str(path)).isNull(), "precondition: plain Qt refuses this image"
            item = BackgroundImageItem(str(path))
        finally:
            QImageReader.setAllocationLimit(previous)

        assert item.image_size_pixels() == (2000, 2000)
        assert not item.pixmap().isNull()

    def test_an_embedded_image_above_the_process_limit_loads(
        self, qtbot, tmp_path: Path
    ) -> None:
        payload = _png_bytes(2000, 2000)
        previous = QImageReader.allocationLimit()
        QImageReader.setAllocationLimit(4)
        try:
            item = BackgroundImageItem(str(tmp_path / "bg.png"), _pixmap_data=payload)
        finally:
            QImageReader.setAllocationLimit(previous)

        assert item.image_size_pixels() == (2000, 2000)

    def test_the_limit_is_restored_after_loading(self, qtbot, test_image_path: Path) -> None:
        previous = QImageReader.allocationLimit()
        BackgroundImageItem(str(test_image_path))
        assert QImageReader.allocationLimit() == previous

    def test_a_larger_existing_budget_is_left_alone(
        self, qtbot, test_image_path: Path
    ) -> None:
        previous = QImageReader.allocationLimit()
        larger = previous + 1024
        QImageReader.setAllocationLimit(larger)
        try:
            BackgroundImageItem(str(test_image_path))
            assert QImageReader.allocationLimit() == larger
        finally:
            QImageReader.setAllocationLimit(previous)

    def test_a_disabled_budget_is_not_narrowed(
        self, qtbot, test_image_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """0 means "no allocation limit"; raising it to 512 would narrow it.

        Observed *inside* the decode window, because a wrong raise is restored
        afterwards and would otherwise be invisible.
        """
        seen: list[int] = []
        real_check = bg_module._check_image_size

        def spy(size: QSize) -> None:
            seen.append(QImageReader.allocationLimit())
            real_check(size)

        monkeypatch.setattr(bg_module, "_check_image_size", spy)
        previous = QImageReader.allocationLimit()
        QImageReader.setAllocationLimit(0)
        try:
            BackgroundImageItem(str(test_image_path))
            assert seen == [0], "a disabled decode budget must stay disabled"
            assert QImageReader.allocationLimit() == 0
        finally:
            QImageReader.setAllocationLimit(previous)

    def test_the_limit_is_restored_after_a_refusal(
        self, qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bg_module, "MAX_BACKGROUND_PIXELS", 1_000_000)
        previous = QImageReader.allocationLimit()
        with pytest.raises(ValueError, match="limited to 1.0 megapixels"):
            BackgroundImageItem(str(_write_png(tmp_path / "huge.png", 2000, 2000)))
        assert QImageReader.allocationLimit() == previous

    def test_an_oversized_file_is_refused_before_decoding(
        self, qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bg_module, "MAX_BACKGROUND_PIXELS", 1_000_000)
        with pytest.raises(ValueError, match="4.0 megapixels"):
            BackgroundImageItem(str(_write_png(tmp_path / "huge.png", 2000, 2000)))

    def test_the_refusal_reports_the_memory_of_both_copies(
        self, qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 4 MP at RGBA8 is 16 MB per copy; the item holds the original and the
        # flipped copy, so the message must not report a single copy as the cost.
        monkeypatch.setattr(bg_module, "MAX_BACKGROUND_PIXELS", 1_000_000)
        with pytest.raises(ValueError, match="needs about 32 MB"):
            BackgroundImageItem(str(_write_png(tmp_path / "huge.png", 2000, 2000)))

    def test_an_oversized_embedded_image_is_refused(
        self, qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bg_module, "MAX_BACKGROUND_PIXELS", 1_000_000)
        with pytest.raises(ValueError, match="4.0 megapixels"):
            BackgroundImageItem(
                str(tmp_path / "bg.png"), _pixmap_data=_png_bytes(2000, 2000)
            )

    def test_an_oversized_file_is_refused_without_decoding_it(
        self, qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The header probe must run before the pixmap is allocated.

        A decode-first implementation would allocate 16 MB here (800 MB for a
        200 MP file) before refusing; the stub makes that ordering observable.
        """
        monkeypatch.setattr(bg_module, "MAX_BACKGROUND_PIXELS", 1_000_000)

        class NoDecode:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("the image was decoded before its size was checked")

        monkeypatch.setattr(bg_module, "QPixmap", NoDecode)
        with pytest.raises(ValueError, match="megapixels"):
            BackgroundImageItem(str(_write_png(tmp_path / "huge.png", 2000, 2000)))

    def test_an_oversized_embedded_image_is_refused_without_decoding_it(
        self, qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bg_module, "MAX_BACKGROUND_PIXELS", 1_000_000)

        class NoDecode:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("the image was decoded before its size was checked")

        monkeypatch.setattr(bg_module, "QPixmap", NoDecode)
        with pytest.raises(ValueError, match="megapixels"):
            BackgroundImageItem(
                str(tmp_path / "bg.png"), _pixmap_data=_png_bytes(2000, 2000)
            )


class TestEncodedPngCache:
    """#660: an unchanged background is encoded once, not once per snapshot."""

    def test_a_snapshot_payload_is_reused_not_re_encoded(
        self, qtbot, test_image_path: Path
    ) -> None:
        item = BackgroundImageItem(str(test_image_path))

        # A re-encode returns a fresh string object; reuse means the same object.
        assert item.to_dict()["image_data"] is item.to_dict()["image_data"]

    def test_to_dict_encodes_the_png_once(
        self, qtbot, test_image_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[int] = []
        real_encode = bg_module._encode_png_base64

        def counting_encode(pixmap: QPixmap) -> str:
            calls.append(pixmap.cacheKey())
            return real_encode(pixmap)

        monkeypatch.setattr(bg_module, "_encode_png_base64", counting_encode)
        item = BackgroundImageItem(str(test_image_path))

        payloads = [item.to_dict()["image_data"] for _ in range(3)]

        assert len(calls) == 1, "three snapshots must encode the background once"
        assert payloads[0] == payloads[1] == payloads[2]
        # Independent of the helper name: a re-encode returns a fresh string object.
        assert payloads[0] is payloads[1] is payloads[2]

    def test_replacing_the_image_invalidates_the_cache(
        self, qtbot, test_image_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[int] = []
        real_encode = bg_module._encode_png_base64

        def counting_encode(pixmap: QPixmap) -> str:
            calls.append(pixmap.cacheKey())
            return real_encode(pixmap)

        monkeypatch.setattr(bg_module, "_encode_png_base64", counting_encode)
        item = BackgroundImageItem(str(test_image_path))
        first_payload = item.to_dict()["image_data"]

        # The seam a future "replace image" action will use: the item serializes
        # _original_pixmap, so replacing the image replaces that pixmap.
        replacement = QPixmap(90, 70)
        replacement.fill(QColor(20, 200, 40))
        item._original_pixmap = replacement
        second_payload = item.to_dict()["image_data"]

        assert len(calls) == 2, "a changed pixmap must be re-encoded"
        assert second_payload != first_payload

    def test_a_placeholder_is_never_encoded(
        self, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[int] = []

        def counting_encode(pixmap: QPixmap) -> str:
            calls.append(pixmap.cacheKey())
            return "unused"

        monkeypatch.setattr(bg_module, "_encode_png_base64", counting_encode)
        data = {
            "type": "background_image",
            "image_path": "/missing.png",
            "position": {"x": 0.0, "y": 0.0},
        }
        item = BackgroundImageItem("/missing.png", _placeholder=True, _raw_dict=data)

        assert item.to_dict() == {**data, "position": {"x": 0.0, "y": 0.0}}
        assert calls == []

    def test_an_unencodable_pixmap_raises_instead_of_writing_nothing(
        self, qtbot
    ) -> None:
        # A null pixmap cannot be saved; an empty image_data would reload as a
        # placeholder, so the failure must not be silent.
        with pytest.raises(RuntimeError, match="Failed to encode"):
            bg_module._encode_png_base64(QPixmap())

    def test_a_refused_embedded_image_logs_why_it_became_a_placeholder(
        self, qtbot, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A plan over the cap degrades to a placeholder; the log must say why."""
        monkeypatch.setattr(bg_module, "MAX_BACKGROUND_PIXELS", 1_000_000)
        data = {
            "type": "background_image",
            "image_path": "site_plan.png",
            "image_data": base64.b64encode(_png_bytes(2000, 2000)).decode("ascii"),
            "position": {"x": 0.0, "y": 0.0},
        }

        with caplog.at_level(logging.WARNING, logger=bg_module.__name__):
            item = BackgroundImageItem.from_dict(data)

        assert item.is_placeholder is True
        messages = [record.getMessage() for record in caplog.records]
        assert any("could not be decoded" in message for message in messages)
        assert any("megapixels" in message for message in messages)


