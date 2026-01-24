"""UI tests for the canvas widget."""

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


class TestCanvasScene:
    """Tests for the CanvasScene class."""

    def test_creation(self, qtbot) -> None:
        """Test basic scene creation."""
        scene = CanvasScene()
        assert scene is not None

    def test_default_size(self, qtbot) -> None:
        """Test default scene size in centimeters."""
        scene = CanvasScene(width_cm=1000, height_cm=800)
        rect = scene.sceneRect()
        assert rect.width() == 1000
        assert rect.height() == 800

    def test_scene_uses_cm_coordinates(self, qtbot) -> None:
        """Test that scene coordinates are in centimeters."""
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        rect = scene.sceneRect()
        # Scene rect should be in cm
        assert rect.left() == 0
        assert rect.top() == 0
        assert rect.right() == 5000
        assert rect.bottom() == 3000


class TestCanvasView:
    """Tests for the CanvasView class."""

    def test_creation(self, qtbot) -> None:
        """Test basic view creation."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        assert view is not None

    def test_default_zoom(self, qtbot) -> None:
        """Test that default zoom is 100%."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        assert view.zoom_factor == 1.0

    def test_zoom_in(self, qtbot) -> None:
        """Test zoom in functionality."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        initial_zoom = view.zoom_factor
        view.zoom_in()
        assert view.zoom_factor > initial_zoom

    def test_zoom_out(self, qtbot) -> None:
        """Test zoom out functionality."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        view.zoom_in()  # First zoom in
        zoomed_in = view.zoom_factor
        view.zoom_out()
        assert view.zoom_factor < zoomed_in

    def test_zoom_limits(self, qtbot) -> None:
        """Test that zoom has min/max limits."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Zoom out many times
        for _ in range(50):
            view.zoom_out()
        assert view.zoom_factor >= view.min_zoom

        # Zoom in many times
        for _ in range(50):
            view.zoom_in()
        assert view.zoom_factor <= view.max_zoom

    def test_set_zoom(self, qtbot) -> None:
        """Test setting zoom to specific value."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        view.set_zoom(2.0)
        assert view.zoom_factor == pytest.approx(2.0, rel=0.01)

    def test_reset_zoom(self, qtbot) -> None:
        """Test resetting zoom to 100%."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        view.zoom_in()
        view.zoom_in()
        view.reset_zoom()
        assert view.zoom_factor == pytest.approx(1.0, rel=0.01)

    def test_zoom_percent(self, qtbot) -> None:
        """Test zoom percentage property."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        view.set_zoom(1.5)
        assert view.zoom_percent == pytest.approx(150.0, rel=1)

    def test_scene_to_canvas_coords(self, qtbot) -> None:
        """Test coordinate conversion from scene to canvas (Y-flip)."""
        scene = CanvasScene(width_cm=1000, height_cm=800)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # In canvas coords (Y-up), point at bottom-left is (0, 0)
        # In scene coords (Y-down), this is (0, height)
        canvas_point = view.scene_to_canvas(QPointF(0, 800))
        assert canvas_point.x() == pytest.approx(0, abs=0.1)
        assert canvas_point.y() == pytest.approx(0, abs=0.1)

    def test_canvas_to_scene_coords(self, qtbot) -> None:
        """Test coordinate conversion from canvas to scene (Y-flip)."""
        scene = CanvasScene(width_cm=1000, height_cm=800)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Canvas point (0, 0) is bottom-left
        # Scene point should be (0, height)
        scene_point = view.canvas_to_scene(QPointF(0, 0))
        assert scene_point.x() == pytest.approx(0, abs=0.1)
        assert scene_point.y() == pytest.approx(800, abs=0.1)

    def test_grid_visible_default(self, qtbot) -> None:
        """Test that grid is hidden by default."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        assert view.grid_visible is False

    def test_toggle_grid(self, qtbot) -> None:
        """Test toggling grid visibility."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        view.set_grid_visible(True)
        assert view.grid_visible is True

        view.set_grid_visible(False)
        assert view.grid_visible is False

    def test_snap_enabled_default(self, qtbot) -> None:
        """Test that snap is enabled by default."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        assert view.snap_enabled is True

    def test_toggle_snap(self, qtbot) -> None:
        """Test toggling snap."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        view.set_snap_enabled(False)
        assert view.snap_enabled is False

        view.set_snap_enabled(True)
        assert view.snap_enabled is True

    def test_grid_size_default(self, qtbot) -> None:
        """Test default grid size."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        # Default grid size should be 50cm
        assert view.grid_size == 50.0

    def test_set_grid_size(self, qtbot) -> None:
        """Test setting grid size."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        view.set_grid_size(100.0)
        assert view.grid_size == 100.0
