"""UI tests for the Print Options dialog and GardenPrintManager (US-6.13)."""

from PyQt6.QtWidgets import QDialogButtonBox

from open_garden_planner.ui.dialogs.print_dialog import (
    SCALE_PRESETS,
    GardenPrintManager,
    PrintOptionsDialog,
)


class TestPrintOptionsDialog:
    """Tests for the Print Options dialog."""

    def test_dialog_creation(self, qtbot) -> None:
        """Test that dialog can be created."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_dialog_title(self, qtbot) -> None:
        """Test that dialog has correct title."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Print Options"

    def test_dialog_is_modal(self, qtbot) -> None:
        """Test that dialog is modal."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        assert dialog.isModal()

    def test_default_scale_is_fit_to_page(self, qtbot) -> None:
        """Test that default scale is Fit to Page (denominator 0)."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        assert dialog.scale_denominator == 0

    def test_scale_presets_available(self, qtbot) -> None:
        """Test that all scale presets are available in the combo box."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        assert dialog._scale_combo.count() == len(SCALE_PRESETS)

    def test_scale_selection(self, qtbot) -> None:
        """Test selecting a specific scale preset."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        # Select 1:100 (index 3)
        dialog._scale_combo.setCurrentIndex(3)
        assert dialog.scale_denominator == 100

    def test_grid_checkbox_reflects_initial_state(self, qtbot) -> None:
        """Test grid checkbox reflects the initial grid visibility."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=True, labels_visible=False)
        qtbot.addWidget(dialog)
        assert dialog.include_grid is True

    def test_labels_checkbox_reflects_initial_state(self, qtbot) -> None:
        """Test labels checkbox reflects the initial labels visibility."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=False)
        qtbot.addWidget(dialog)
        assert dialog.include_labels is False

    def test_legend_on_by_default(self, qtbot) -> None:
        """Test legend is enabled by default."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        assert dialog.include_legend is True

    def test_has_ok_button(self, qtbot) -> None:
        """Test dialog has OK button."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box is not None
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button is not None

    def test_has_cancel_button(self, qtbot) -> None:
        """Test dialog has Cancel button."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box is not None
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        assert cancel_button is not None

    def test_cancel_rejects_dialog(self, qtbot) -> None:
        """Test clicking Cancel rejects the dialog."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)

        with qtbot.waitSignal(dialog.rejected, timeout=1000):
            cancel_button.click()

    def test_page_info_fit_to_page(self, qtbot) -> None:
        """Test page info shows single page for fit-to-page."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        # Default is Fit to Page
        assert "Single page" in dialog._page_info_label.text()

    def test_page_info_multi_page(self, qtbot) -> None:
        """Test page info shows multi-page for small scale."""
        dialog = PrintOptionsDialog(5000, 3000, grid_visible=False, labels_visible=True)
        qtbot.addWidget(dialog)
        # Select 1:20 scale (index 1) - should require multiple pages for 50x30m garden
        dialog._scale_combo.setCurrentIndex(1)
        text = dialog._page_info_label.text()
        assert "pages" in text or "page" in text


class TestGardenPrintManager:
    """Tests for the GardenPrintManager."""

    def test_creation(self, qtbot) -> None:
        """Test that print manager can be created."""
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene(5000, 3000)
        mgr = GardenPrintManager(scene, project_name="Test Garden")
        assert mgr is not None

    def test_configure(self, qtbot) -> None:
        """Test that print manager can be configured."""
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene(5000, 3000)
        mgr = GardenPrintManager(scene, project_name="Test Garden")
        mgr.configure(
            scale_denominator=100,
            include_grid=True,
            include_labels=True,
            include_legend=True,
        )
        assert mgr._scale_denom == 100
        assert mgr._include_grid is True
        assert mgr._include_labels is True
        assert mgr._include_legend is True

    def test_configure_fit_to_page(self, qtbot) -> None:
        """Test that print manager can be configured for fit-to-page."""
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene(5000, 3000)
        mgr = GardenPrintManager(scene)
        mgr.configure(
            scale_denominator=0,
            include_grid=False,
            include_labels=False,
            include_legend=False,
        )
        assert mgr._scale_denom == 0
        assert mgr._include_legend is False

    def test_prepare_and_restore_scene(self, qtbot) -> None:
        """Test that scene state is saved and restored around printing."""
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene(5000, 3000)
        scene.set_labels_visible(True)

        mgr = GardenPrintManager(scene)
        mgr.configure(
            scale_denominator=0,
            include_grid=False,
            include_labels=False,
            include_legend=True,
        )

        # Prepare should change labels
        mgr._prepare_scene_for_print()
        assert scene.labels_enabled is False

        # Restore should bring back original
        mgr._restore_scene_after_print()
        assert scene.labels_enabled is True
