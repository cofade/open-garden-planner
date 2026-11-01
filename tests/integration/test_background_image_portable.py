"""Integration tests: BackgroundImageItem portability across machines (issue #137).

Verifies that:
  - Background images are embedded as base64 in the saved .ogp project file.
  - A project reloads its background image correctly even after the original
    source file has been deleted (simulating "open on another PC").
  - Legacy project files (no image_data key) still load without crashing.
"""


import base64
import json
from pathlib import Path

import pytest
from PyQt6.QtGui import QColor, QImage, QImageReader, QPixmap

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import background_image_item
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

    def test_google_maps_key_is_not_written_to_project_file(
        self, qtbot, tmp_path: Path
    ) -> None:
        """Per-user API credentials must stay outside portable .ogp files."""
        from open_garden_planner.app.settings import get_settings

        get_settings().google_maps_api_key = "SECRET_GOOGLE_MAPS_KEY"
        project = ProjectManager()
        save_path = tmp_path / "no_secrets.ogp"
        project.save(CanvasScene(width_cm=5000, height_cm=3000), save_path)

        saved_text = save_path.read_text(encoding="utf-8")
        assert "SECRET_GOOGLE_MAPS_KEY" not in saved_text
        assert "google_maps_key" not in saved_text

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
        # AUD-043 (#397): Missing legacy background image loads as placeholder
        # and survives re-save rather than being silently dropped.
        project.load(scene, save_path)

        bg_items = [
            item for item in scene.items() if isinstance(item, BackgroundImageItem)
        ]
        assert len(bg_items) == 1, (
            "Missing background image must load as placeholder, not be dropped"
        )
        assert bg_items[0].is_placeholder is True


def _write_png(path: Path, width: int, height: int) -> Path:
    """Write a solid-colour PNG of the given pixel size."""
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(QColor(120, 140, 110))
    assert image.save(str(path), "PNG")
    return path


class TestLargeBackgroundImages:
    """#659 / #660: site-plan-sized backgrounds import, reopen and read cheaply."""

    def test_a_background_above_the_process_decode_budget_reloads(
        self, qtbot, tmp_path: Path
    ) -> None:
        """A plan whose image exceeds the decode budget must not reopen as a placeholder.

        A 2000 x 2000 RGBA image is 16 MB decoded, so a 4 MB process budget puts
        it over the limit exactly as Qt's 256 MB default does to the reported
        9000 x 8000 site plan, without allocating 275 MiB per copy here (#659).
        """
        source = _write_png(tmp_path / "site_plan.png", 2000, 2000)
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        scene.addItem(BackgroundImageItem(str(source)))
        save_path = tmp_path / "large_background.ogp"
        ProjectManager().save(scene, save_path)
        source.unlink()  # portable file: the source path is only a hint

        previous = QImageReader.allocationLimit()
        QImageReader.setAllocationLimit(4)
        try:
            # Plain Qt refuses the embedded payload at this budget: without that
            # precondition the test would pass even if the limit were never in force.
            embedded = base64.b64decode(
                next(
                    obj["image_data"]
                    for obj in json.loads(save_path.read_text(encoding="utf-8"))["objects"]
                    if obj.get("type") == "background_image"
                )
            )
            assert QPixmap().loadFromData(embedded) is False, (
                "precondition: plain Qt refuses this payload at a 4 MB budget"
            )
            fresh_scene = CanvasScene(width_cm=5000, height_cm=3000)
            ProjectManager().load(fresh_scene, save_path)
        finally:
            QImageReader.setAllocationLimit(previous)

        bg_items = [
            item for item in fresh_scene.items() if isinstance(item, BackgroundImageItem)
        ]
        assert len(bg_items) == 1
        assert bg_items[0].is_placeholder is False, (
            "an image above the process decode budget must reload, not degrade"
        )
        assert bg_items[0].image_size_pixels() == (2000, 2000)

    def test_repeated_plan_reads_encode_the_background_once(
        self, qtbot, png_image: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every Agent API read takes a snapshot; the embedded PNG is encoded once."""
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        scene.addItem(BackgroundImageItem(str(png_image)))
        project = ProjectManager()

        calls: list[int] = []
        real_encode = background_image_item._encode_png_base64

        def counting_encode(pixmap: QPixmap) -> str:
            calls.append(pixmap.cacheKey())
            return real_encode(pixmap)

        monkeypatch.setattr(background_image_item, "_encode_png_base64", counting_encode)

        first = project.snapshot_dict(scene)
        second = project.snapshot_dict(scene)

        assert len(calls) == 1, "two plan reads must encode the background once"
        first_bg = [o for o in first["objects"] if o.get("type") == "background_image"][0]
        second_bg = [o for o in second["objects"] if o.get("type") == "background_image"][0]
        assert first_bg["image_data"] == second_bg["image_data"]
        assert first_bg["image_data"] is second_bg["image_data"], (
            "an unchanged background must not be re-encoded for each plan read"
        )
        # The snapshot still round-trips into a real item.
        restored = BackgroundImageItem.from_dict(first_bg)
        assert restored.is_placeholder is False
        assert not restored.pixmap().isNull()

