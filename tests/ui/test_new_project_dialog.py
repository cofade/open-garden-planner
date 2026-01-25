"""UI tests for the New Project dialog (US-1.1)."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialogButtonBox

from open_garden_planner.ui.dialogs import NewProjectDialog


class TestNewProjectDialog:
    """Tests for the New Project dialog."""

    def test_dialog_creation(self, qtbot) -> None:
        """Test that dialog can be created."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_dialog_title(self, qtbot) -> None:
        """Test that dialog has correct title."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "New Project"

    def test_dialog_is_modal(self, qtbot) -> None:
        """Test that dialog is modal."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        assert dialog.isModal()

    def test_default_width(self, qtbot) -> None:
        """Test default width is 50 meters."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        assert dialog.width_m == 50.0

    def test_default_height(self, qtbot) -> None:
        """Test default height is 30 meters."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        assert dialog.height_m == 30.0

    def test_width_cm_conversion(self, qtbot) -> None:
        """Test width is correctly converted to centimeters."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        dialog.width_spinbox.setValue(10.0)
        assert dialog.width_cm == 1000.0

    def test_height_cm_conversion(self, qtbot) -> None:
        """Test height is correctly converted to centimeters."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        dialog.height_spinbox.setValue(5.0)
        assert dialog.height_cm == 500.0

    def test_set_dimensions_m(self, qtbot) -> None:
        """Test setting dimensions in meters."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        dialog.set_dimensions_m(20.0, 15.0)
        assert dialog.width_m == 20.0
        assert dialog.height_m == 15.0

    def test_set_dimensions_cm(self, qtbot) -> None:
        """Test setting dimensions in centimeters."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        dialog.set_dimensions_cm(2500.0, 1500.0)
        assert dialog.width_m == 25.0
        assert dialog.height_m == 15.0

    def test_width_spinbox_range(self, qtbot) -> None:
        """Test width spinbox has correct range."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        assert dialog.width_spinbox.minimum() == 1.0
        assert dialog.width_spinbox.maximum() == 1000.0

    def test_height_spinbox_range(self, qtbot) -> None:
        """Test height spinbox has correct range."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        assert dialog.height_spinbox.minimum() == 1.0
        assert dialog.height_spinbox.maximum() == 1000.0

    def test_width_spinbox_suffix(self, qtbot) -> None:
        """Test width spinbox shows meters suffix."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        assert dialog.width_spinbox.suffix() == " m"

    def test_height_spinbox_suffix(self, qtbot) -> None:
        """Test height spinbox shows meters suffix."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        assert dialog.height_spinbox.suffix() == " m"

    def test_has_ok_button(self, qtbot) -> None:
        """Test dialog has OK button."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box is not None
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button is not None

    def test_has_cancel_button(self, qtbot) -> None:
        """Test dialog has Cancel button."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box is not None
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        assert cancel_button is not None

    def test_cancel_returns_rejected(self, qtbot) -> None:
        """Test clicking Cancel rejects the dialog."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)

        # Simulate cancel click
        with qtbot.waitSignal(dialog.rejected, timeout=1000):
            cancel_button.click()

    def test_custom_dimensions_preserved(self, qtbot) -> None:
        """Test that custom dimensions are preserved after setting."""
        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)

        # Set custom dimensions
        dialog.width_spinbox.setValue(75.5)
        dialog.height_spinbox.setValue(42.3)

        # Verify values
        assert dialog.width_m == 75.5
        assert dialog.height_m == 42.3
        assert dialog.width_cm == 7550.0
        assert dialog.height_cm == 4230.0
