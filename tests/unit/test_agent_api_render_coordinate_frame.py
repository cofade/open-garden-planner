"""Pins the D1.3 render tool's pixel frame against the scene coordinate frame.

Object positions are reported in cm, CAD Y-up (schema.py / ADR-002): a larger
scene y is further north. ``render_scene_region``'s ``y_flip=True`` (kept for
visual parity with the live CAD view and every existing PNG/PDF export) makes the
output PNG Y-up too (north at the top), so — because pixel rows count top-down —
a small scene-y lands near the BOTTOM of the image. This test pins the exact
correction formula documented on ``RenderMeta.px_per_cm`` so a future refactor
can't silently break agent visual grounding without a red test.
"""

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


def _render(scene: CanvasScene, w: int = 100, h: int = 80, *, y_flip: bool = True) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    painter = QPainter(img)
    try:
        render_scene_region(scene, painter, QRectF(0, 0, w, h), scene.canvas_rect, y_flip=y_flip)
    finally:
        painter.end()
    return img


def _marker_row_band(img: QImage, x: int, background: QColor) -> tuple[int, int]:
    """Rows in column ``x`` whose pixel differs from ``background`` — (min, max)."""
    rows = [r for r in range(img.height()) if img.pixelColor(x, r) != background]
    assert rows, "expected marker not found in scanned column"
    return min(rows), max(rows)


class TestRenderPixelFrameVsD12SceneFrame:
    def test_small_scene_y_lands_near_image_bottom(self, scene: CanvasScene) -> None:
        """A circle low in the scene (y=50cm, near the south edge) lands in the
        BOTTOM half of the Y-up render, NOT near pixel row 0 (the north/top)."""
        scene.addItem(CircleItem(500, 50, 30))
        img = _render(scene, w=100, h=80)
        background = img.pixelColor(0, 0)
        row_min, row_max = _marker_row_band(img, 50, background)
        row = (row_min + row_max) / 2
        assert row > img.height() * 0.5

    def test_correction_formula_holds(self, scene: CanvasScene) -> None:
        """pixel_y = image_height_px - (scene_y_cm - region_y_cm) * px_per_cm."""
        cy_cm = 750.0
        scene.addItem(CircleItem(500, cy_cm, 30))
        w, h = 100, 80
        img = _render(scene, w=w, h=h)
        background = img.pixelColor(0, 0)
        row_min, row_max = _marker_row_band(img, 50, background)
        actual_row = (row_min + row_max) / 2

        region_height_cm = scene.canvas_rect.height()
        px_per_cm = h / region_height_cm
        predicted_row = h - cy_cm * px_per_cm
        assert actual_row == pytest.approx(predicted_row, abs=2.0)

    def test_unflipped_render_aligns_directly_with_scene_frame(self, scene: CanvasScene) -> None:
        """Isolates y_flip as the sole source of the inversion (sanity cross-check)."""
        cy_cm = 750.0
        scene.addItem(CircleItem(500, cy_cm, 30))
        w, h = 100, 80
        img = _render(scene, w=w, h=h, y_flip=False)
        background = img.pixelColor(0, 0)
        row_min, row_max = _marker_row_band(img, 50, background)
        actual_row = (row_min + row_max) / 2

        region_height_cm = scene.canvas_rect.height()
        px_per_cm = h / region_height_cm
        predicted_row_direct = cy_cm * px_per_cm  # no inversion
        assert actual_row == pytest.approx(predicted_row_direct, abs=2.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
