"""UI tests for the Linear Array dialog (US-7.14)."""

# ruff: noqa: ARG002
import pytest
from PyQt6.QtWidgets import QDialogButtonBox

from open_garden_planner.ui.dialogs import LinearArrayDialog


class TestLinearArrayDialog:
    """Tests for the LinearArrayDialog."""

    def test_dialog_creation(self, qtbot) -> None:
        """Test that dialog can be created."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_dialog_title(self, qtbot) -> None:
        """Test dialog has correct title."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Create Linear Array"

    def test_dialog_is_modal(self, qtbot) -> None:
        """Test dialog is modal."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.isModal()

    def test_default_count(self, qtbot) -> None:
        """Test default count is 3."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.count == 3

    def test_default_spacing(self, qtbot) -> None:
        """Test default spacing is 100 cm."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.spacing_cm == 100.0

    def test_default_angle(self, qtbot) -> None:
        """Test default angle is 0 degrees."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.angle_deg == 0.0

    def test_default_constraints_off(self, qtbot) -> None:
        """Test auto-create constraints is off by default."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert not dialog.create_constraints

    def test_count_range(self, qtbot) -> None:
        """Test count spinbox range."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog._count_spin.minimum() == 2
        assert dialog._count_spin.maximum() == 100

    def test_spacing_range(self, qtbot) -> None:
        """Test spacing spinbox range."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog._spacing_spin.minimum() == 1.0
        assert dialog._spacing_spin.maximum() == 100000.0

    def test_spacing_suffix(self, qtbot) -> None:
        """Test spacing spinbox has cm suffix."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog._spacing_spin.suffix() == " cm"

    def test_angle_suffix(self, qtbot) -> None:
        """Test angle spinbox has degree suffix."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog._angle_spin.suffix() == "°"

    def test_set_count(self, qtbot) -> None:
        """Test setting count."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        dialog._count_spin.setValue(5)
        assert dialog.count == 5

    def test_set_spacing(self, qtbot) -> None:
        """Test setting spacing."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        dialog._spacing_spin.setValue(250.0)
        assert dialog.spacing_cm == 250.0

    def test_set_angle(self, qtbot) -> None:
        """Test setting direction angle."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        dialog._angle_spin.setValue(90.0)
        assert dialog.angle_deg == 90.0

    def test_enable_constraints(self, qtbot) -> None:
        """Test enabling auto-create constraints."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        dialog._constraints_check.setChecked(True)
        assert dialog.create_constraints

    def test_has_ok_button(self, qtbot) -> None:
        """Test dialog has OK button."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box is not None
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button is not None

    def test_has_cancel_button(self, qtbot) -> None:
        """Test dialog has Cancel button."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box is not None
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        assert cancel_button is not None

    def test_cancel_rejects_dialog(self, qtbot) -> None:
        """Test clicking Cancel rejects the dialog."""
        dialog = LinearArrayDialog()
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)

        with qtbot.waitSignal(dialog.rejected, timeout=1000):
            cancel_button.click()
