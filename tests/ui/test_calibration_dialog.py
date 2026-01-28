"""Tests for the calibration dialog."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPixmap

from open_garden_planner.ui.dialogs import CalibrationDialog


@pytest.fixture
def test_pixmap() -> QPixmap:
    """Create a test pixmap for calibration.

    Returns:
        A 200x200 white pixmap
    """
    pixmap = QPixmap(200, 200)
    pixmap.fill()
    return pixmap


class TestCalibrationDialog:
    """Tests for CalibrationDialog class."""

    def test_creation(self, qtbot, test_pixmap: QPixmap) -> None:
        """Test basic dialog creation."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        assert dialog.windowTitle() == "Calibrate Background Image"
        assert dialog.isModal()

    def test_initial_state(self, qtbot, test_pixmap: QPixmap) -> None:
        """Test initial state of the dialog."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        # Initially, no points are selected
        assert len(dialog._points) == 0
        assert dialog._pixel_distance == 0.0

        # Distance input should be disabled initially
        assert not dialog._distance_input.isEnabled()

        # OK button should be disabled initially
        assert not dialog._ok_button.isEnabled()

        # Reset button should be disabled initially
        assert not dialog._reset_button.isEnabled()

    def test_first_point_click(self, qtbot, test_pixmap: QPixmap) -> None:
        """Test clicking the first calibration point."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        # Simulate clicking first point
        point1 = QPointF(50, 50)
        dialog._on_point_clicked(point1)

        assert len(dialog._points) == 1
        assert dialog._points[0] == point1
        assert dialog._reset_button.isEnabled()
        assert not dialog._distance_input.isEnabled()
        assert not dialog._ok_button.isEnabled()

    def test_second_point_click(self, qtbot, test_pixmap: QPixmap) -> None:
        """Test clicking the second calibration point."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        # Click two points
        point1 = QPointF(50, 50)
        point2 = QPointF(150, 50)
        dialog._on_point_clicked(point1)
        dialog._on_point_clicked(point2)

        assert len(dialog._points) == 2
        assert dialog._points[0] == point1
        assert dialog._points[1] == point2

        # Pixel distance should be calculated (100 pixels horizontally)
        assert dialog._pixel_distance == pytest.approx(100.0)

        # Distance input should be enabled
        assert dialog._distance_input.isEnabled()
        assert dialog._ok_button.isEnabled()

    def test_reset_points(self, qtbot, test_pixmap: QPixmap) -> None:
        """Test resetting calibration points."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        # Click two points
        dialog._on_point_clicked(QPointF(50, 50))
        dialog._on_point_clicked(QPointF(150, 50))
        assert len(dialog._points) == 2

        # Reset
        dialog._reset_points()

        assert len(dialog._points) == 0
        assert dialog._pixel_distance == 0.0
        assert not dialog._distance_input.isEnabled()
        assert not dialog._ok_button.isEnabled()
        assert not dialog._reset_button.isEnabled()
        assert dialog._distance_input.text() == ""

    def test_get_calibration_data_valid(
        self, qtbot, test_pixmap: QPixmap
    ) -> None:
        """Test getting valid calibration data."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        # Click two points and enter distance
        dialog._on_point_clicked(QPointF(0, 0))
        dialog._on_point_clicked(QPointF(100, 0))
        dialog._distance_input.setText("500")

        data = dialog.get_calibration_data()
        assert data is not None
        pixels, centimeters = data
        assert pixels == pytest.approx(100.0)
        assert centimeters == pytest.approx(500.0)

    def test_get_calibration_data_invalid_no_points(
        self, qtbot, test_pixmap: QPixmap
    ) -> None:
        """Test getting calibration data with no points."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        data = dialog.get_calibration_data()
        assert data is None

    def test_get_calibration_data_invalid_one_point(
        self, qtbot, test_pixmap: QPixmap
    ) -> None:
        """Test getting calibration data with only one point."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        dialog._on_point_clicked(QPointF(50, 50))

        data = dialog.get_calibration_data()
        assert data is None

    def test_get_calibration_data_invalid_text(
        self, qtbot, test_pixmap: QPixmap
    ) -> None:
        """Test getting calibration data with invalid distance text."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        dialog._on_point_clicked(QPointF(0, 0))
        dialog._on_point_clicked(QPointF(100, 0))
        dialog._distance_input.setText("invalid")

        data = dialog.get_calibration_data()
        assert data is None

    def test_get_calibration_data_zero_distance(
        self, qtbot, test_pixmap: QPixmap
    ) -> None:
        """Test getting calibration data with zero distance."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        dialog._on_point_clicked(QPointF(0, 0))
        dialog._on_point_clicked(QPointF(100, 0))
        dialog._distance_input.setText("0")

        data = dialog.get_calibration_data()
        assert data is None

    def test_get_calibration_data_negative_distance(
        self, qtbot, test_pixmap: QPixmap
    ) -> None:
        """Test getting calibration data with negative distance."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        dialog._on_point_clicked(QPointF(0, 0))
        dialog._on_point_clicked(QPointF(100, 0))
        dialog._distance_input.setText("-100")

        data = dialog.get_calibration_data()
        assert data is None

    def test_diagonal_distance_calculation(
        self, qtbot, test_pixmap: QPixmap
    ) -> None:
        """Test pixel distance calculation for diagonal line."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        # Click two points diagonally (3-4-5 triangle)
        dialog._on_point_clicked(QPointF(0, 0))
        dialog._on_point_clicked(QPointF(30, 40))

        # Distance should be 50 (3-4-5 right triangle)
        assert dialog._pixel_distance == pytest.approx(50.0)

    def test_markers_drawn_after_clicks(
        self, qtbot, test_pixmap: QPixmap
    ) -> None:
        """Test that visual markers are drawn after clicking points."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        initial_item_count = len(dialog._scene.items())

        # Click first point
        dialog._on_point_clicked(QPointF(50, 50))

        # Should have added marker items (crosshair lines and text)
        assert len(dialog._scene.items()) > initial_item_count

        # Click second point
        dialog._on_point_clicked(QPointF(150, 150))

        # Should have added more items (second marker + line)
        assert len(dialog._scene.items()) > initial_item_count + 1

    def test_image_displayed_in_scene(
        self, qtbot, test_pixmap: QPixmap
    ) -> None:
        """Test that the image is displayed in the scene."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        # Scene should contain the pixmap item
        items = dialog._scene.items()
        assert len(items) >= 1
        assert dialog._pixmap_item in items

    def test_third_click_ignored(self, qtbot, test_pixmap: QPixmap) -> None:
        """Test that clicking a third point is ignored."""
        dialog = CalibrationDialog(test_pixmap)
        qtbot.addWidget(dialog)

        # Click three points
        dialog._on_point_clicked(QPointF(0, 0))
        dialog._on_point_clicked(QPointF(100, 0))
        dialog._on_point_clicked(QPointF(200, 0))

        # Should only have two points
        assert len(dialog._points) == 2
