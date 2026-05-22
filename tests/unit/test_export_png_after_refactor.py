"""Regression check that PNG export still produces a valid image after refactor.

US-B7 moved the scene-region render into ``services/scene_rendering.py``
and ``ExportService.export_to_png`` now delegates to it. This file
exists to catch any regression that breaks the existing PNG export.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage

from open_garden_planner.services.export_service import ExportService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem, PolylineItem


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    s = CanvasScene(width_cm=1000, height_cm=800)
    s.addItem(CircleItem(500, 400, 80))
    s.addItem(PolylineItem(points=[QPointF(100, 100), QPointF(900, 100)]))
    return s


class TestExportPng:
    def test_export_writes_valid_image(self, scene: CanvasScene, tmp_path) -> None:
        out = tmp_path / "garden.png"
        ExportService.export_to_png(scene, out, dpi=72, output_width_cm=10.0)
        assert out.exists()
        image = QImage(str(out))
        assert not image.isNull()
        assert image.width() > 0
        assert image.height() > 0

    def test_export_at_high_dpi(self, scene: CanvasScene, tmp_path) -> None:
        out = tmp_path / "hi.png"
        ExportService.export_to_png(scene, out, dpi=300, output_width_cm=15.0)
        image = QImage(str(out))
        # 15 cm × 300 DPI / 2.54 = ~1771 px wide.
        assert image.width() > 1500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
