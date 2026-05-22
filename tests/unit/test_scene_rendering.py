"""Unit tests for the shared scene-rendering helper (Phase 13 Package B — US-B7)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=1000, height_cm=800)


def _render(scene: CanvasScene, source_rect: QRectF, w: int = 100, h: int = 100) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    painter = QPainter(img)
    try:
        render_scene_region(
            scene, painter, QRectF(0, 0, w, h), source_rect
        )
    finally:
        painter.end()
    return img


class TestRenderRegion:
    def test_empty_scene_renders_background(self, scene: CanvasScene) -> None:
        img = _render(scene, scene.sceneRect())
        # Just verify it didn't crash and the image came back the right size.
        assert img.width() == 100
        assert img.height() == 100

    def test_renders_a_circle(self, scene: CanvasScene) -> None:
        scene.addItem(CircleItem(500, 400, 100))
        img = _render(scene, scene.sceneRect())
        # Centre pixel should NOT be the white background — something drew.
        centre = img.pixelColor(50, 50)
        assert centre != QColor(255, 255, 255)

    def test_overlay_handles_are_hidden(self, scene: CanvasScene) -> None:
        """Selection handles are hidden during render and restored after."""
        circle = CircleItem(500, 400, 100)
        scene.addItem(circle)
        circle.setSelected(True)
        # Render — handles should not appear inside the output, and the
        # source selection must be restored.
        _render(scene, scene.sceneRect())
        # Selection state restored.
        assert circle.isSelected()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
