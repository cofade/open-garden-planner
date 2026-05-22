"""Unit tests for ViewportItem (Phase 13 Package B — US-B7)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QRectF

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem
from open_garden_planner.ui.paper_space.viewport_item import ViewportItem


@pytest.fixture()
def source_scene(qtbot: object) -> CanvasScene:  # noqa: ARG001
    return CanvasScene(width_cm=1000, height_cm=800)


class TestScale:
    def test_scale_factor_is_paper_per_model(self, source_scene: CanvasScene) -> None:
        # 10 cm paper for 1000 cm model -> 0.01 scale (1:100).
        vp = ViewportItem(
            source_scene=source_scene,
            source_rect=QRectF(0, 0, 1000, 800),
            paper_rect=QRectF(0, 0, 10, 8),
        )
        assert abs(vp.scale_factor - 0.01) < 1e-9

    def test_set_scale_resizes_source_rect_around_centre(
        self, source_scene: CanvasScene
    ) -> None:
        vp = ViewportItem(
            source_scene=source_scene,
            source_rect=QRectF(100, 100, 200, 200),
            paper_rect=QRectF(0, 0, 10, 10),
        )
        original_centre_x = vp.source_rect.x() + vp.source_rect.width() / 2.0
        vp.set_scale(0.02)  # 1:50 → source rect halves
        sr = vp.source_rect
        new_centre_x = sr.x() + sr.width() / 2.0
        assert abs(new_centre_x - original_centre_x) < 1e-9
        # 10 paper cm / 0.02 = 500 model cm.
        assert abs(sr.width() - 500.0) < 1e-9


class TestCacheInvalidation:
    def test_changing_source_rect_invalidates_cache(
        self, source_scene: CanvasScene
    ) -> None:
        vp = ViewportItem(
            source_scene=source_scene,
            source_rect=QRectF(0, 0, 100, 100),
            paper_rect=QRectF(0, 0, 5, 5),
        )
        # Trigger one paint to populate the cache.
        vp._cached_pixmap = vp._build_pixmap()
        assert vp._cached_pixmap is not None

        vp.source_rect = QRectF(50, 50, 100, 100)
        assert vp._cached_pixmap is None

    def test_source_scene_change_invalidates_cache(
        self, source_scene: CanvasScene
    ) -> None:
        vp = ViewportItem(
            source_scene=source_scene,
            source_rect=QRectF(0, 0, 1000, 800),
            paper_rect=QRectF(0, 0, 10, 8),
        )
        vp._cached_pixmap = vp._build_pixmap()
        assert vp._cached_pixmap is not None

        # Adding an item emits scene.changed → cache should drop.
        source_scene.addItem(CircleItem(500, 400, 50))
        # The signal is queued in Qt; pump events so the handler runs.
        from PyQt6.QtCore import QCoreApplication

        QCoreApplication.processEvents()
        assert vp._cached_pixmap is None


class TestSerialization:
    def test_round_trip(self, source_scene: CanvasScene) -> None:
        vp = ViewportItem(
            source_scene=source_scene,
            source_rect=QRectF(100, 200, 800, 600),
            paper_rect=QRectF(0, 0, 20, 15),
        )
        vp.setPos(3.0, 4.0)

        data = vp.to_dict()
        restored = ViewportItem.from_dict(source_scene, data)
        assert restored.source_rect == QRectF(100, 200, 800, 600)
        assert restored.rect() == QRectF(0, 0, 20, 15)
        assert restored.pos().x() == 3.0
        assert restored.pos().y() == 4.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
