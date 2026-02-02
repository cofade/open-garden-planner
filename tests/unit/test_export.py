"""Tests for export functionality."""

import csv
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem


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
        # Canvas: 5000cm x 2500cm, Output: 30cm wide
        # Output: 30cm x 15cm (maintains aspect ratio)
        # At 72 DPI: (30 / 2.54) * 72 = 850 pixels wide
        width_px, height_px = ExportService.calculate_image_size(5000, 2500, 30, 72)

        assert width_px == 850
        assert height_px == 425

    def test_calculate_image_size_150dpi(self, qtbot) -> None:
        """Test image size calculation at 150 DPI."""
        # Output: 30cm x 15cm at 150 DPI
        width_px, height_px = ExportService.calculate_image_size(5000, 2500, 30, 150)

        # (30 / 2.54) * 150 = 1771.6...
        assert width_px == 1771
        assert height_px == 885

    def test_calculate_image_size_300dpi(self, qtbot) -> None:
        """Test image size calculation at 300 DPI."""
        # Output: 30cm x 15cm at 300 DPI
        width_px, height_px = ExportService.calculate_image_size(5000, 2500, 30, 300)

        # (30 / 2.54) * 300 = 3543.3...
        assert width_px == 3543
        assert height_px == 1771

    def test_calculate_scale(self, qtbot) -> None:
        """Test scale calculation."""
        # 5000cm canvas → 30cm output = 1:166.67 scale
        scale = ExportService.calculate_scale(5000, 30)
        assert scale == pytest.approx(0.006, abs=0.001)

        # 1000cm canvas → 30cm output = 1:33.33 scale
        scale = ExportService.calculate_scale(1000, 30)
        assert scale == pytest.approx(0.03, abs=0.001)

    def test_export_to_png_creates_file(self, scene, tmp_path, qtbot) -> None:
        """Test that PNG export creates a file."""
        file_path = tmp_path / "test_export.png"

        ExportService.export_to_png(scene, file_path, dpi=72, output_width_cm=30)

        assert file_path.exists()
        assert file_path.stat().st_size > 0

    def test_export_to_png_with_content(self, scene_with_rect, tmp_path, qtbot) -> None:
        """Test PNG export with scene content."""
        file_path = tmp_path / "test_with_rect.png"

        ExportService.export_to_png(scene_with_rect, file_path, dpi=150, output_width_cm=30)

        assert file_path.exists()
        # File with content should be larger than empty
        assert file_path.stat().st_size > 1000

    def test_export_to_png_different_dpi(self, scene, tmp_path, qtbot) -> None:
        """Test that higher DPI produces larger images."""
        file_72 = tmp_path / "test_72.png"
        file_300 = tmp_path / "test_300.png"

        ExportService.export_to_png(scene, file_72, dpi=72, output_width_cm=30)
        ExportService.export_to_png(scene, file_300, dpi=300, output_width_cm=30)

        # 300 DPI file should be significantly larger
        assert file_300.stat().st_size > file_72.stat().st_size

    def test_export_to_svg_creates_file(self, scene, tmp_path, qtbot) -> None:
        """Test that SVG export creates a file."""
        file_path = tmp_path / "test_export.svg"

        ExportService.export_to_svg(scene, file_path, output_width_cm=30)

        assert file_path.exists()
        assert file_path.stat().st_size > 0

    def test_export_to_svg_with_content(self, scene_with_rect, tmp_path, qtbot) -> None:
        """Test SVG export with scene content."""
        file_path = tmp_path / "test_with_rect.svg"

        ExportService.export_to_svg(scene_with_rect, file_path, output_width_cm=30)

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
            output_width_cm=30,
            title="My Garden",
            description="Test garden plan"
        )

        content = file_path.read_text()
        assert "My Garden" in content
        assert "Test garden plan" in content

    def test_export_to_png_path_object(self, scene, tmp_path, qtbot) -> None:
        """Test export with Path object."""
        file_path = Path(tmp_path) / "test_path.png"

        ExportService.export_to_png(scene, file_path, dpi=72, output_width_cm=30)

        assert file_path.exists()

    def test_export_to_png_string_path(self, scene, tmp_path, qtbot) -> None:
        """Test export with string path."""
        file_path = str(tmp_path / "test_string.png")

        ExportService.export_to_png(scene, file_path, dpi=72, output_width_cm=30)

        assert Path(file_path).exists()


class TestExportPngDialog:
    """Tests for ExportPngDialog class."""

    def test_dialog_creation(self, qtbot) -> None:
        """Test dialog can be created."""
        from open_garden_planner.ui.dialogs.export_dialog import ExportPngDialog

        dialog = ExportPngDialog(1000, 500)
        qtbot.addWidget(dialog)

        assert dialog.selected_dpi == 150  # Default
        assert dialog.selected_output_width_cm == pytest.approx(29.7, abs=0.1)  # A4 landscape

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

    def test_dialog_size_selection(self, qtbot) -> None:
        """Test output size selection changes."""
        from open_garden_planner.ui.dialogs.export_dialog import ExportPngDialog

        dialog = ExportPngDialog(5000, 3000)
        qtbot.addWidget(dialog)

        # Select A3
        dialog._a3_radio.setChecked(True)
        dialog._on_size_changed(int(42.0 * 10))
        assert dialog.selected_output_width_cm == pytest.approx(42.0, abs=0.1)

        # Select Letter
        dialog._letter_radio.setChecked(True)
        dialog._on_size_changed(int(27.94 * 10))
        assert dialog.selected_output_width_cm == pytest.approx(27.94, abs=0.1)


class TestPlantListExport:
    """Tests for plant list CSV export."""

    @pytest.fixture
    def scene_with_plants(self, qtbot) -> CanvasScene:
        """Create a scene with plant objects."""
        scene = CanvasScene(width_cm=1000, height_cm=500)

        # Add tree with full metadata
        tree = CircleItem(0, 0, 150, object_type=ObjectType.TREE)
        tree.name = "Apple Tree"
        tree.setPos(QPointF(100, 200))
        tree.metadata["plant_instance"] = {
            "variety_cultivar": "Honeycrisp",
            "planting_date": "2023-04-15",
            "current_spread_cm": 150.0,
            "current_height_cm": 300.0,
            "notes": "Grafted on dwarf rootstock",
        }
        tree.metadata["plant_species"] = {
            "scientific_name": "Malus domestica",
            "common_name": "Apple",
            "family": "Rosaceae",
            "genus": "Malus",
            "cycle": "perennial",
            "sun_requirement": "full_sun",
            "water_needs": "medium",
            "edible": True,
            "edible_parts": ["fruit", "flower"],
            "data_source": "custom",
        }
        scene.addItem(tree)

        # Add shrub with minimal metadata
        shrub = CircleItem(0, 0, 80, object_type=ObjectType.SHRUB)
        shrub.name = "Rose Bush"
        shrub.setPos(QPointF(300, 400))
        shrub.metadata["plant_instance"] = {
            "variety_cultivar": "Knockout",
        }
        scene.addItem(shrub)

        # Add perennial with no metadata
        perennial = CircleItem(0, 0, 50, object_type=ObjectType.PERENNIAL)
        perennial.setPos(QPointF(500, 100))
        scene.addItem(perennial)

        return scene

    def test_export_csv_empty_scene(self, tmp_path, qtbot) -> None:
        """Test CSV export with no plants."""
        scene = CanvasScene(width_cm=1000, height_cm=500)
        file_path = tmp_path / "plants_empty.csv"

        count = ExportService.export_plant_list_to_csv(scene, file_path)

        assert count == 0
        assert file_path.exists()

        # Verify header exists
        with open(file_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert "name" in header
            assert "scientific_name" in header

    def test_export_csv_with_plants(self, scene_with_plants, tmp_path, qtbot) -> None:
        """Test CSV export with plant objects."""
        file_path = tmp_path / "plants.csv"

        count = ExportService.export_plant_list_to_csv(scene_with_plants, file_path)

        assert count == 3
        assert file_path.exists()

        # Read and verify CSV content
        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 3

        # Find the apple tree row
        apple = next(row for row in rows if row["name"] == "Apple Tree")
        assert apple["type"] == "Tree"
        assert apple["variety_cultivar"] == "Honeycrisp"
        assert apple["planting_date"] == "2023-04-15"
        assert float(apple["current_spread_cm"]) == 150.0
        assert float(apple["current_height_cm"]) == 300.0
        assert apple["scientific_name"] == "Malus domestica"
        assert apple["common_name"] == "Apple"
        assert apple["edible"] == "True"
        assert "fruit" in apple["edible_parts"]

        # Find the rose bush row
        rose = next(row for row in rows if row["name"] == "Rose Bush")
        assert rose["type"] == "Shrub"
        assert rose["variety_cultivar"] == "Knockout"

    def test_export_csv_without_species_data(self, scene_with_plants, tmp_path, qtbot) -> None:
        """Test CSV export excluding species-level data."""
        file_path = tmp_path / "plants_minimal.csv"

        count = ExportService.export_plant_list_to_csv(
            scene_with_plants, file_path, include_species_data=False
        )

        assert count == 3
        assert file_path.exists()

        # Read and verify CSV content
        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames

        # Verify species columns are not included
        assert "scientific_name" not in header
        assert "common_name" not in header

        # Verify instance columns are included
        assert "name" in header
        assert "variety_cultivar" in header
        assert "planting_date" in header

    def test_export_csv_position_data(self, scene_with_plants, tmp_path, qtbot) -> None:
        """Test CSV export includes position data."""
        file_path = tmp_path / "plants_positions.csv"

        ExportService.export_plant_list_to_csv(scene_with_plants, file_path)

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Check apple tree position
        apple = next(row for row in rows if row["name"] == "Apple Tree")
        assert float(apple["position_x_cm"]) == pytest.approx(100.0, abs=0.1)
        assert float(apple["position_y_cm"]) == pytest.approx(200.0, abs=0.1)

    def test_export_csv_path_object(self, scene_with_plants, tmp_path, qtbot) -> None:
        """Test CSV export with Path object."""
        file_path = Path(tmp_path) / "plants_path.csv"

        count = ExportService.export_plant_list_to_csv(scene_with_plants, file_path)

        assert count == 3
        assert file_path.exists()

    def test_export_csv_string_path(self, scene_with_plants, tmp_path, qtbot) -> None:
        """Test CSV export with string path."""
        file_path = str(tmp_path / "plants_string.csv")

        count = ExportService.export_plant_list_to_csv(scene_with_plants, file_path)

        assert count == 3
        assert Path(file_path).exists()
