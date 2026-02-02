"""Tests for export functionality."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import RectangleItem


class TestExportService:
    """Tests for ExportService class."""

    @pytest.fixture
    def scene(self, qtbot) -> CanvasScene:
        """Create a canvas scene for testing."""
        return CanvasScene(width_cm=1000, height_cm=500)

    @pytest.fixture
    def scene_with_rect(self, scene) -> CanvasScene:
        """Create a scene with a rectangle."""
        rect = RectangleItem(100, 100, 200, 150)
        scene.addItem(rect)
        return scene

    def test_calculate_image_size_72dpi(self, qtbot) -> None:
        """Test image size calculation at 72 DPI."""
        # 100cm = ~39.37 inches
        # At 72 DPI: ~2835 pixels
        width_px, height_px = ExportService.calculate_image_size(100, 50, 72)

        # 100 / 2.54 * 72 = 2834.6...
        assert width_px == 2834
        assert height_px == 1417

    def test_calculate_image_size_150dpi(self, qtbot) -> None:
        """Test image size calculation at 150 DPI."""
        width_px, height_px = ExportService.calculate_image_size(100, 50, 150)

        # 100 / 2.54 * 150 = 5905.5...
        assert width_px == 5905
        assert height_px == 2952

    def test_calculate_image_size_300dpi(self, qtbot) -> None:
        """Test image size calculation at 300 DPI."""
        width_px, height_px = ExportService.calculate_image_size(100, 50, 300)

        # 100 / 2.54 * 300 = 11811.02...
        assert width_px == 11811
        assert height_px == 5905

    def test_estimate_file_size(self, qtbot) -> None:
        """Test file size estimation."""
        # 1000x1000 = 1M pixels
        # 4 bytes per pixel (ARGB32) = 4MB raw
        # With 40% compression = 1.6MB
        size_mb = ExportService.estimate_file_size_mb(1000, 1000)
        assert 1.0 < size_mb < 2.0

    def test_export_to_png_creates_file(self, scene, tmp_path, qtbot) -> None:
        """Test that PNG export creates a file."""
        file_path = tmp_path / "test_export.png"

        ExportService.export_to_png(scene, file_path, dpi=72)

        assert file_path.exists()
        assert file_path.stat().st_size > 0

    def test_export_to_png_with_content(self, scene_with_rect, tmp_path, qtbot) -> None:
        """Test PNG export with scene content."""
        file_path = tmp_path / "test_with_rect.png"

        ExportService.export_to_png(scene_with_rect, file_path, dpi=150)

        assert file_path.exists()
        # File with content should be larger than empty
        assert file_path.stat().st_size > 1000

    def test_export_to_png_different_dpi(self, scene, tmp_path, qtbot) -> None:
        """Test that higher DPI produces larger images."""
        file_72 = tmp_path / "test_72.png"
        file_300 = tmp_path / "test_300.png"

        ExportService.export_to_png(scene, file_72, dpi=72)
        ExportService.export_to_png(scene, file_300, dpi=300)

        # 300 DPI file should be significantly larger
        assert file_300.stat().st_size > file_72.stat().st_size

    def test_export_to_svg_creates_file(self, scene, tmp_path, qtbot) -> None:
        """Test that SVG export creates a file."""
        file_path = tmp_path / "test_export.svg"

        ExportService.export_to_svg(scene, file_path)

        assert file_path.exists()
        assert file_path.stat().st_size > 0

    def test_export_to_svg_with_content(self, scene_with_rect, tmp_path, qtbot) -> None:
        """Test SVG export with scene content."""
        file_path = tmp_path / "test_with_rect.svg"

        ExportService.export_to_svg(scene_with_rect, file_path)

        assert file_path.exists()

        # Verify it's valid SVG
        content = file_path.read_text()
        assert "<?xml" in content or "<svg" in content

    def test_export_to_svg_with_metadata(self, scene, tmp_path, qtbot) -> None:
        """Test SVG export includes metadata."""
        file_path = tmp_path / "test_metadata.svg"

        ExportService.export_to_svg(
            scene,
            file_path,
            title="My Garden",
            description="Test garden plan"
        )

        content = file_path.read_text()
        assert "My Garden" in content
        assert "Test garden plan" in content

    def test_export_to_png_path_object(self, scene, tmp_path, qtbot) -> None:
        """Test export with Path object."""
        file_path = Path(tmp_path) / "test_path.png"

        ExportService.export_to_png(scene, file_path, dpi=72)

        assert file_path.exists()

    def test_export_to_png_string_path(self, scene, tmp_path, qtbot) -> None:
        """Test export with string path."""
        file_path = str(tmp_path / "test_string.png")

        ExportService.export_to_png(scene, file_path, dpi=72)

        assert Path(file_path).exists()


class TestExportPngDialog:
    """Tests for ExportPngDialog class."""

    def test_dialog_creation(self, qtbot) -> None:
        """Test dialog can be created."""
        from open_garden_planner.ui.dialogs.export_dialog import ExportPngDialog

        dialog = ExportPngDialog(1000, 500)
        qtbot.addWidget(dialog)

        assert dialog.selected_dpi == 150  # Default

    def test_dialog_dpi_selection(self, qtbot) -> None:
        """Test DPI selection changes."""
        from open_garden_planner.ui.dialogs.export_dialog import ExportPngDialog

        dialog = ExportPngDialog(1000, 500)
        qtbot.addWidget(dialog)

        # Select 72 DPI
        dialog._dpi_72_radio.setChecked(True)
        dialog._on_dpi_changed(72)
        assert dialog.selected_dpi == 72

        # Select 300 DPI
        dialog._dpi_300_radio.setChecked(True)
        dialog._on_dpi_changed(300)
        assert dialog.selected_dpi == 300
