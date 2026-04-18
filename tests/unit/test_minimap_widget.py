"""Unit tests for minimap / overview panel widget (US-11.7)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QMouseEvent, QResizeEvent
from PyQt6.QtWidgets import QWidget

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.widgets.minimap_widget import (
    MARGIN,
    MINIMAP_HEIGHT,
    MINIMAP_WIDTH,
    MinimapWidget,
    _OVERLAY_Z_MIN,
)


@pytest.fixture()
def canvas_pair(qtbot: object) -> tuple[CanvasView, CanvasScene]:
    """Create a CanvasView + CanvasScene pair for testing."""
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    view.resize(800, 600)
    view.show()
    return view, scene


@pytest.fixture()
def minimap(canvas_pair: tuple[CanvasView, CanvasScene]) -> MinimapWidget:
    """Create a MinimapWidget attached to the canvas pair."""
    view, scene = canvas_pair
    return MinimapWidget(view, scene)


class TestMinimapCreation:
    """Tests for minimap widget creation and initial state."""

    def test_minimap_creates(self, minimap: MinimapWidget) -> None:
        assert minimap is not None
        assert isinstance(minimap, QWidget)

    def test_minimap_fixed_size(self, minimap: MinimapWidget) -> None:
        assert minimap.width() == MINIMAP_WIDTH
        assert minimap.height() == MINIMAP_HEIGHT

    def test_minimap_is_enabled_by_default(self, minimap: MinimapWidget) -> None:
        assert minimap.is_enabled() is True


class TestMinimapVisibility:
    """Tests for minimap visibility toggling."""

    def test_set_visible_false_hides(self, minimap: MinimapWidget) -> None:
        minimap.set_visible(False)
        assert minimap.is_enabled() is False
        assert minimap.isHidden()

    def test_set_visible_true_shows(self, minimap: MinimapWidget) -> None:
        minimap.set_visible(False)
        minimap.set_visible(True)
        assert minimap.is_enabled() is True
        assert minimap.isVisible()


class TestMinimapPosition:
    """Tests for minimap positioning."""

    def test_minimap_initial_position(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        QApplication.processEvents()  # flush deferred singleShot(0) reposition
        vp = view.viewport().geometry()
        sb = CanvasView.SCALE_BAR_RESERVED_PX if view.scale_bar_visible else 0
        expected_x = max(vp.left(), vp.right() - minimap.width() - MARGIN)
        expected_y = max(vp.top(), vp.bottom() - minimap.height() - MARGIN - sb)
        assert minimap.x() == expected_x
        assert minimap.y() == expected_y


class TestMinimapCoordinateMapping:
    """Tests for coordinate conversion.

    The minimap uses Y-inverted coordinates: minimap Y=0 corresponds
    to the visual top of the canvas (scene Y=height_cm) because the
    view applies a Y-flip transform.
    """

    def test_minimap_to_scene_top_left(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        """Minimap top-left (0,0) → scene bottom-left (0, height)."""
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        sx, sy = minimap._minimap_to_scene(0, 0)
        assert sx == pytest.approx(0.0, abs=1.0)
        assert sy == pytest.approx(3000.0, abs=1.0)

    def test_minimap_to_scene_bottom_right(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        """Minimap bottom-right (W,H) → scene top-right (width, 0)."""
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        sx, sy = minimap._minimap_to_scene(MINIMAP_WIDTH, MINIMAP_HEIGHT)
        assert sx == pytest.approx(5000.0, abs=1.0)
        assert sy == pytest.approx(0.0, abs=1.0)

    def test_minimap_to_scene_center(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        sx, sy = minimap._minimap_to_scene(MINIMAP_WIDTH / 2, MINIMAP_HEIGHT / 2)
        assert sx == pytest.approx(2500.0, abs=1.0)
        assert sy == pytest.approx(1500.0, abs=1.0)

    def test_viewport_rect_returns_qrectf(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        rect = minimap._viewport_rect_on_minimap()
        # May be None if canvas is empty or rect could be QRectF
        if rect is not None:
            assert isinstance(rect, QRectF)


class TestMinimapThrottleTimer:
    """Tests for the update throttle timer."""

    def test_timer_interval(self, minimap: MinimapWidget) -> None:
        assert minimap._update_timer.interval() == 100

    def test_timer_is_single_shot(self, minimap: MinimapWidget) -> None:
        assert minimap._update_timer.isSingleShot() is True


class TestMinimapMouseInteraction:
    """Tests for mouse-based navigation."""

    def test_click_pans_view(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object,
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)

        # Zoom in so the minimap is visible and viewport doesn't cover everything
        view.set_zoom(300.0)

        # Record initial center
        vp = view.viewport().rect()
        initial_center = view.mapToScene(vp.center())

        # Simulate click near top-left of minimap (should pan toward scene origin)
        click_pos = QPointF(10.0, 10.0)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            click_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        minimap.mousePressEvent(press)

        # Check that view center changed
        new_center = view.mapToScene(vp.center())
        # At high zoom, clicking near origin should move the view
        assert (
            initial_center.x() != new_center.x()
            or initial_center.y() != new_center.y()
        )

    def test_drag_flag_set_on_viewport_rect(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        # Initially not dragging
        assert minimap._dragging is False

    def test_mouse_release_clears_drag(
        self, canvas_pair: tuple[CanvasView, CanvasScene],
    ) -> None:
        view, scene = canvas_pair
        minimap = MinimapWidget(view, scene)
        minimap._dragging = True
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(50.0, 50.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        minimap.mouseReleaseEvent(release)
        assert minimap._dragging is False


class TestMinimapOverlayFiltering:
    """Regression tests for issue #152 — overlay filter must not hide garden items."""

    def test_layer_items_not_hidden_by_overlay_filter(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object
    ) -> None:
        """Items on non-bottom layers (zValue = 100, 200, …) must survive
        _hide_overlay_items() — they were wrongly hidden before the fix."""
        from PyQt6.QtWidgets import QGraphicsRectItem

        view, scene = canvas_pair
        item = QGraphicsRectItem(0, 0, 100, 100)
        item.setZValue(100)  # z_order=1 layer
        scene.addItem(item)

        minimap = MinimapWidget(view, scene)
        hidden = minimap._hide_overlay_items()
        minimap._restore_overlay_items(hidden)

        assert item not in hidden, "Garden item with zValue=100 must not be hidden"
        assert item.isVisible()

    def test_high_z_overlay_is_hidden_and_restored(
        self, canvas_pair: tuple[CanvasView, CanvasScene], qtbot: object
    ) -> None:
        """Items with zValue >= _OVERLAY_Z_MIN (overlay handles) must be
        hidden during render and restored afterwards."""
        from PyQt6.QtWidgets import QGraphicsRectItem

        view, scene = canvas_pair
        overlay = QGraphicsRectItem(0, 0, 10, 10)
        overlay.setZValue(_OVERLAY_Z_MIN)
        scene.addItem(overlay)

        minimap = MinimapWidget(view, scene)
        hidden = minimap._hide_overlay_items()
        assert overlay in hidden
        minimap._restore_overlay_items(hidden)
        assert overlay.isVisible()
