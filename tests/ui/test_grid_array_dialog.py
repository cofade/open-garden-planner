"""UI tests for the Grid Array dialog (US-7.15)."""

# ruff: noqa: ARG002
import pytest
from PyQt6.QtWidgets import QDialogButtonBox

from open_garden_planner.ui.dialogs import GridArrayDialog


class TestGridArrayDialog:
    """Tests for the GridArrayDialog."""

    def test_dialog_creation(self, qtbot) -> None:
        """Test that dialog can be created."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_dialog_title(self, qtbot) -> None:
        """Test dialog has correct title."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Create Grid Array"

    def test_dialog_is_modal(self, qtbot) -> None:
        """Test dialog is modal."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.isModal()

    def test_default_rows(self, qtbot) -> None:
        """Test default row count is 3."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.rows == 3

    def test_default_cols(self, qtbot) -> None:
        """Test default column count is 3."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.cols == 3

    def test_default_row_spacing(self, qtbot) -> None:
        """Test default row spacing is 100 cm."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.row_spacing_cm == 100.0

    def test_default_col_spacing(self, qtbot) -> None:
        """Test default column spacing is 100 cm."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog.col_spacing_cm == 100.0

    def test_default_constraints_off(self, qtbot) -> None:
        """Test auto-create constraints is off by default."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert not dialog.create_constraints

    def test_rows_range(self, qtbot) -> None:
        """Test rows spinbox range."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog._rows_spin.minimum() == 1
        assert dialog._rows_spin.maximum() == 100

    def test_cols_range(self, qtbot) -> None:
        """Test columns spinbox range."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog._cols_spin.minimum() == 1
        assert dialog._cols_spin.maximum() == 100

    def test_row_spacing_suffix(self, qtbot) -> None:
        """Test row spacing spinbox has cm suffix."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog._row_spacing_spin.suffix() == " cm"

    def test_col_spacing_suffix(self, qtbot) -> None:
        """Test column spacing spinbox has cm suffix."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        assert dialog._col_spacing_spin.suffix() == " cm"

    def test_set_rows(self, qtbot) -> None:
        """Test setting row count."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        dialog._rows_spin.setValue(5)
        assert dialog.rows == 5

    def test_set_cols(self, qtbot) -> None:
        """Test setting column count."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        dialog._cols_spin.setValue(4)
        assert dialog.cols == 4

    def test_set_row_spacing(self, qtbot) -> None:
        """Test setting row spacing."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        dialog._row_spacing_spin.setValue(200.0)
        assert dialog.row_spacing_cm == 200.0

    def test_set_col_spacing(self, qtbot) -> None:
        """Test setting column spacing."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        dialog._col_spacing_spin.setValue(150.0)
        assert dialog.col_spacing_cm == 150.0

    def test_enable_constraints(self, qtbot) -> None:
        """Test enabling auto-create constraints."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        dialog._constraints_check.setChecked(True)
        assert dialog.create_constraints

    def test_has_ok_button(self, qtbot) -> None:
        """Test dialog has OK button."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box is not None
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button is not None

    def test_has_cancel_button(self, qtbot) -> None:
        """Test dialog has Cancel button."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box is not None
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        assert cancel_button is not None

    def test_cancel_rejects_dialog(self, qtbot) -> None:
        """Test clicking Cancel rejects the dialog."""
        dialog = GridArrayDialog()
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)

        with qtbot.waitSignal(dialog.rejected, timeout=1000):
            cancel_button.click()
