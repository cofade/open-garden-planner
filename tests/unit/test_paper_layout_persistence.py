"""Persistence tests for paper-space layouts (Phase 13 Package B — US-B7)."""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QPointF, QRectF

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.paper_space.paper_space_scene import PaperSpaceScene


@pytest.fixture()
def canvas(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=5000, height_cm=3000)


class TestPaperSpaceSceneRoundTrip:
    def test_serialize_default_layout(self, canvas: CanvasScene) -> None:
        ps = PaperSpaceScene(canvas)
        data = ps.to_dict()
        # The default scene has one viewport + title block + scale bar.
        kinds = {entry["type"] for entry in data["items"]}
        assert kinds == {"viewport", "title_block", "scale_bar"}
        assert data["page_name"] == "A4"
        assert data["orientation"] == "landscape"

    def test_load_replaces_default_layout(self, canvas: CanvasScene) -> None:
        ps = PaperSpaceScene(canvas)
        ps.viewport.setPos(QPointF(0, 0))
        ps.viewport.set_paper_rect(QRectF(0, 0, 25, 15))
        ps.viewport.source_rect = QRectF(100, 100, 800, 600)
        saved = ps.to_dict()

        ps2 = PaperSpaceScene(canvas)
        ps2.load_from_dict(saved)
        assert ps2.viewport is not None
        assert ps2.viewport.rect() == QRectF(0, 0, 25, 15)
        assert ps2.viewport.source_rect == QRectF(100, 100, 800, 600)


class TestProjectFileIncludesPaperLayouts:
    def test_save_and_load_round_trip(
        self, canvas: CanvasScene, tmp_path
    ) -> None:
        ps = PaperSpaceScene(canvas)
        layouts_in = [ps.to_dict()]

        pm = ProjectManager()
        pm.set_paper_layouts(layouts_in)
        out_path = tmp_path / "layout.ogp"
        pm.save(canvas, out_path)

        # Reload into a fresh manager.
        pm2 = ProjectManager()
        canvas2 = CanvasScene(width_cm=5000, height_cm=3000)
        pm2.load(canvas2, out_path)
        assert len(pm2.paper_layouts) == 1
        assert pm2.paper_layouts[0]["page_name"] == "A4"

    def test_newer_file_version_is_rejected(
        self, canvas: CanvasScene, tmp_path
    ) -> None:
        """A 1.5 file on a 1.4 binary must fail loud rather than silently dropping data."""
        future = {
            "version": "1.5",
            "metadata": {"modified": "2030-01-01T00:00:00+00:00"},
            "canvas": {"width": 5000, "height": 3000},
            "layers": [],
            "objects": [],
            "paper_layouts": [],
            "some_future_key": "data we don't know how to handle",
        }
        out_path = tmp_path / "future.ogp"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(future, f)

        pm = ProjectManager()
        with pytest.raises(ValueError, match="newer version"):
            pm.load(canvas, out_path)

    def test_v1_3_file_loads_without_paper_layouts(
        self, canvas: CanvasScene, tmp_path
    ) -> None:
        """v1.3 files have no ``paper_layouts`` key — they must still load."""
        legacy = {
            "version": "1.3",
            "metadata": {"modified": "2025-01-01T00:00:00+00:00"},
            "canvas": {"width": 5000, "height": 3000},
            "layers": [],
            "objects": [],
        }
        out_path = tmp_path / "legacy.ogp"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(legacy, f)

        pm = ProjectManager()
        pm.load(canvas, out_path)
        assert pm.paper_layouts == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
