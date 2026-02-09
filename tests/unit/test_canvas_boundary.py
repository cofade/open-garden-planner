"""Tests for canvas boundary enforcement during object movement."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsRectItem

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView


class TestCanvasBoundaryClamping:
    """Tests for _clamp_items_to_canvas and _clamp_delta_to_canvas."""

    @pytest.fixture
    def scene(self, qtbot) -> CanvasScene:
        """Create a canvas scene."""
        return CanvasScene(width_cm=1000, height_cm=1000)

    @pytest.fixture
    def view(self, qtbot, scene) -> CanvasView:
        """Create a canvas view."""
        return CanvasView(scene)

    def _make_rect(
        self, scene: CanvasScene, x: float, y: float, w: float, h: float
    ) -> QGraphicsRectItem:
        """Create a rect item at the given position and add to scene."""
        item = QGraphicsRectItem(0, 0, w, h)
        item.setPos(x, y)
        item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        scene.addItem(item)
        return item

    def test_clamp_delta_no_overflow(self, view, scene) -> None:
        """Delta is unchanged if movement stays inside canvas."""
        item = self._make_rect(scene, 100, 100, 50, 50)
        delta = QPointF(10, 10)
        clamped = view._clamp_delta_to_canvas([item], delta)
        assert abs(clamped.x() - 10) < 0.01
        assert abs(clamped.y() - 10) < 0.01

    def test_clamp_delta_right_overflow(self, view, scene) -> None:
        """Delta is reduced if it would push item past right edge."""
        # Item right edge at 950+50=1000 (at the boundary already)
        item = self._make_rect(scene, 950, 100, 50, 50)
        delta = QPointF(100, 0)
        clamped = view._clamp_delta_to_canvas([item], delta)
        # sceneBoundingRect includes pen margin, so right edge is slightly beyond 1000.
        # The clamped dx should prevent going further right.
        assert clamped.x() <= 0.5  # At most a tiny float rounding

    def test_clamp_delta_left_overflow(self, view, scene) -> None:
        """Delta is reduced if it would push item past left edge."""
        item = self._make_rect(scene, 10, 100, 50, 50)
        delta = QPointF(-100, 0)
        clamped = view._clamp_delta_to_canvas([item], delta)
        # Should not push left edge below 0 (canvas left)
        result_left = item.sceneBoundingRect().left() + clamped.x()
        assert result_left >= -0.5  # Allow for pen margin

    def test_clamp_delta_top_overflow(self, view, scene) -> None:
        """Delta is reduced if it would push item past top edge."""
        item = self._make_rect(scene, 100, 5, 50, 50)
        delta = QPointF(0, -100)
        clamped = view._clamp_delta_to_canvas([item], delta)
        result_top = item.sceneBoundingRect().top() + clamped.y()
        assert result_top >= -0.5

    def test_clamp_delta_bottom_overflow(self, view, scene) -> None:
        """Delta is reduced if it would push item past bottom edge."""
        item = self._make_rect(scene, 100, 950, 50, 50)
        delta = QPointF(0, 100)
        clamped = view._clamp_delta_to_canvas([item], delta)
        assert clamped.y() <= 0.5

    def test_clamp_items_pushes_back(self, view, scene) -> None:
        """Items pushed outside the canvas are moved back in."""
        item = self._make_rect(scene, -50, -50, 50, 50)
        view._clamp_items_to_canvas([item])
        rect = item.sceneBoundingRect()
        canvas = scene.canvas_rect
        assert rect.left() >= canvas.left() - 0.5
        assert rect.top() >= canvas.top() - 0.5

    def test_clamp_items_already_inside(self, view, scene) -> None:
        """Items already inside the canvas are not moved."""
        item = self._make_rect(scene, 100, 100, 50, 50)
        original_pos = item.pos()
        view._clamp_items_to_canvas([item])
        assert item.pos() == original_pos

    def test_clamp_multiple_items(self, view, scene) -> None:
        """Multiple items are clamped together as a group."""
        item1 = self._make_rect(scene, 100, 100, 50, 50)
        item2 = self._make_rect(scene, 200, 200, 50, 50)
        # Move both far to the right (outside canvas)
        item1.setPos(980, 100)
        item2.setPos(1080, 200)
        view._clamp_items_to_canvas([item1, item2])
        # The combined right edge should be within canvas
        combined_right = max(
            item1.sceneBoundingRect().right(),
            item2.sceneBoundingRect().right(),
        )
        assert combined_right <= scene.canvas_rect.right() + 0.5
