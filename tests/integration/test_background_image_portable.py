"""Integration tests: BackgroundImageItem portability across machines (issue #137).

Verifies that:
  - Background images are embedded as base64 in the saved .ogp project file.
  - A project reloads its background image correctly even after the original
    source file has been deleted (simulating "open on another PC").
  - Legacy project files (no image_data key) still load without crashing.
"""

# ruff: noqa: ARG002

import json
from pathlib import Path

import pytest
from PyQt6.QtGui import QPixmap

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.background_image_item import BackgroundImageItem


@pytest.fixture()
def png_image(tmp_path: Path) -> Path:
    """Create a small test PNG and return its path."""
    pixmap = QPixmap(64, 64)
    pixmap.fill()
    path = tmp_path / "test_bg.png"
    pixmap.save(str(path))
    return path


class TestBackgroundImagePortability:
    """End-to-end portability tests for background image embedding."""

    def test_saved_project_contains_image_data_key(
        self, qtbot, png_image: Path, tmp_path: Path
    ) -> None:
        """Saving a project with a background image must embed image_data in the JSON."""
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        scene.addItem(BackgroundImageItem(str(png_image)))

        project = ProjectManager()
        save_path = tmp_path / "test_project.ogp"
        project.save(scene, save_path)

        with open(save_path, encoding="utf-8") as f:
            saved = json.load(f)

        bg_items = [
            obj for obj in saved.get("objects", []) if obj.get("type") == "background_image"
        ]
        assert len(bg_items) == 1, "Expected exactly one background_image object in saved JSON"
        assert "image_data" in bg_items[0], (
            "background_image must have 'image_data' key for portability"
        )
        assert isinstance(bg_items[0]["image_data"], str)
        assert len(bg_items[0]["image_data"]) > 0

    def test_project_loads_background_image_without_source_file(
        self, qtbot, png_image: Path, tmp_path: Path
    ) -> None:
        """After deleting the source image, the project still loads the background image."""
        # Save with the source file present
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        bg_item = BackgroundImageItem(str(png_image))
        bg_item.opacity = 0.6
        bg_item.calibrate(pixels=64, centimeters=200)
        scene.addItem(bg_item)

        project = ProjectManager()
        save_path = tmp_path / "portable_test.ogp"
        project.save(scene, save_path)

        # Delete the source file — simulates opening on another PC
        png_image.unlink()
        assert not png_image.exists()

        # Load into a fresh scene
        fresh_scene = CanvasScene(width_cm=5000, height_cm=3000)
        fresh_project = ProjectManager()
        fresh_project.load(fresh_scene, save_path)

        bg_items = [
            item
            for item in fresh_scene.items()
            if isinstance(item, BackgroundImageItem)
        ]
        assert len(bg_items) == 1, "Background image should be present after loading"
        restored = bg_items[0]
        assert not restored.pixmap().isNull(), "Restored pixmap must not be null"
        assert restored.opacity == pytest.approx(0.6)
        assert restored.scale_factor == pytest.approx(64 / 200)

    def test_legacy_project_without_image_data_loads_gracefully(
        self, qtbot, tmp_path: Path
    ) -> None:
        """Legacy .ogp files that only have image_path (no image_data) load without crashing.

        The background image is silently dropped when the path is invalid — this is the
        existing behaviour for missing files and must be preserved for backward compatibility.
        """
        legacy_project = {
            "version": "1.0",
            "canvas": {"width_cm": 500, "height_cm": 300},
            "layers": [
                {"id": "00000000-0000-0000-0000-000000000001", "name": "Layer 1",
                 "visible": True, "locked": False, "opacity": 1.0, "z_order": 0}
            ],
            "objects": [
                {
                    "type": "background_image",
                    "image_path": "/nonexistent/path/on/disk.png",
                    # No 'image_data' key — this is the legacy format
                    "position": {"x": 0.0, "y": 0.0},
                    "opacity": 1.0,
                    "locked": False,
                    "scale_factor": 1.0,
                }
            ],
        }
        save_path = tmp_path / "legacy.ogp"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(legacy_project, f)

        scene = CanvasScene(width_cm=5000, height_cm=3000)
        project = ProjectManager()
        # Must not raise — the missing background image is silently ignored
        project.load(scene, save_path)

        bg_items = [
            item for item in scene.items() if isinstance(item, BackgroundImageItem)
        ]
        assert len(bg_items) == 0, (
            "Background image with invalid legacy path should be silently dropped, not crash"
        )
