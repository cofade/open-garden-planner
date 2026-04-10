"""UI tests for ExportPngDialog."""

# ruff: noqa: ARG002

import pytest
from PyQt6.QtCore import Qt

from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.dialogs.export_dialog import ExportPngDialog


class TestExportPngDialog:
    """Tests for ExportPngDialog widget state and user interaction."""

    @pytest.fixture()
    def dialog(self, qtbot):
        dlg = ExportPngDialog(canvas_width_cm=5000, canvas_height_cm=3000)
        qtbot.addWidget(dlg)
        return dlg

    # --- Creation & defaults ---

    def test_dialog_creates_without_error(self, qtbot) -> None:
        """Dialog can be instantiated for any canvas size."""
        dlg = ExportPngDialog(canvas_width_cm=1000, canvas_height_cm=800)
        qtbot.addWidget(dlg)
        assert dlg is not None

    def test_default_dpi_is_print(self, dialog) -> None:
        """Default DPI is 150 (DPI_PRINT) for balanced quality."""
        assert dialog.selected_dpi == ExportService.DPI_PRINT

    def test_default_size_is_a4_landscape(self, dialog) -> None:
        """Default output width matches A4 landscape width."""
        assert dialog.selected_output_width_cm == pytest.approx(
            ExportService.PAPER_A4_LANDSCAPE_WIDTH_CM
        )

    def test_a4_radio_is_checked_by_default(self, dialog) -> None:
        """A4 Landscape radio button is pre-selected."""
        assert dialog._a4_radio.isChecked()

    def test_dpi_150_radio_is_checked_by_default(self, dialog) -> None:
        """150 DPI radio button is pre-selected."""
        assert dialog._dpi_150_radio.isChecked()

    # --- Format selection ---

    def test_select_a3_updates_output_width(self, dialog, qtbot) -> None:
        """Clicking A3 radio updates selected_output_width_cm."""
        qtbot.mouseClick(dialog._a3_radio, Qt.MouseButton.LeftButton)  # Qt.MouseButton.LeftButton = 1
        assert dialog.selected_output_width_cm == pytest.approx(
            ExportService.PAPER_A3_LANDSCAPE_WIDTH_CM
        )

    def test_select_72_dpi_updates_dpi(self, dialog, qtbot) -> None:
        """Selecting 72 DPI via the internal handler updates selected_dpi."""
        dialog._on_dpi_changed(ExportService.DPI_SCREEN)
        assert dialog.selected_dpi == ExportService.DPI_SCREEN

    def test_select_300_dpi_updates_dpi(self, dialog, qtbot) -> None:
        """Selecting 300 DPI via the internal handler updates selected_dpi."""
        dialog._on_dpi_changed(ExportService.DPI_HIGH)
        assert dialog.selected_dpi == ExportService.DPI_HIGH

    def test_selecting_a3_unchecks_a4(self, dialog, qtbot) -> None:
        """Selecting A3 radio deselects A4 (mutual exclusion)."""
        qtbot.mouseClick(dialog._a3_radio, Qt.MouseButton.LeftButton)
        assert not dialog._a4_radio.isChecked()
        assert dialog._a3_radio.isChecked()
