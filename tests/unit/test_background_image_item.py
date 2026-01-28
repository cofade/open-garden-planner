"""Unit tests for BackgroundImageItem."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsItem

from open_garden_planner.ui.canvas.items import BackgroundImageItem


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

        # Lock the item
        item.locked = True
        assert item.locked
        assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

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
        """Test serialization to dictionary."""
        item = BackgroundImageItem(str(test_image_path))
        item.setPos(QPointF(100, 200))
        item.opacity = 0.7
        item.locked = True
        item.calibrate(pixels=100, centimeters=500)

        data = item.to_dict()

        assert data["type"] == "background_image"
        assert data["image_path"] == str(test_image_path)
        assert data["position"]["x"] == pytest.approx(100.0)
        assert data["position"]["y"] == pytest.approx(200.0)
        assert data["opacity"] == pytest.approx(0.7)
        assert data["locked"] is True
        assert data["scale_factor"] == pytest.approx(0.2)

    def test_from_dict(self, qtbot, test_image_path: Path) -> None:
        """Test deserialization from dictionary."""
        data = {
            "type": "background_image",
            "image_path": str(test_image_path),
            "position": {"x": 150.0, "y": 250.0},
            "opacity": 0.8,
            "locked": True,
            "scale_factor": 0.3,
        }

        item = BackgroundImageItem.from_dict(data)

        assert item.image_path == str(test_image_path)
        assert item.pos().x() == pytest.approx(150.0)
        assert item.pos().y() == pytest.approx(250.0)
        assert item.opacity == pytest.approx(0.8)
        assert item.locked is True
        assert item.scale_factor == pytest.approx(0.3)
        # Scale should be 1/0.3 ≈ 3.33
        assert item.scale() == pytest.approx(1.0 / 0.3)

    def test_round_trip_serialization(self, qtbot, test_image_path: Path) -> None:
        """Test that serialization and deserialization preserve data."""
        # Create an item with specific properties
        original = BackgroundImageItem(str(test_image_path))
        original.setPos(QPointF(50, 75))
        original.opacity = 0.6
        original.locked = False
        original.calibrate(pixels=100, centimeters=400)

        # Serialize and deserialize
        data = original.to_dict()
        restored = BackgroundImageItem.from_dict(data)

        # Verify all properties match
        assert restored.image_path == original.image_path
        assert restored.pos() == original.pos()
        assert restored.opacity == pytest.approx(original.opacity)
        assert restored.locked == original.locked
        assert restored.scale_factor == pytest.approx(original.scale_factor)
        assert restored.scale() == pytest.approx(original.scale())
