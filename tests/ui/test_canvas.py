"""UI tests for the canvas widget."""

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem


class TestCanvasScene:
    """Tests for the CanvasScene class."""

    def test_creation(self, qtbot) -> None:
        """Test basic scene creation."""
        scene = CanvasScene()
        assert scene is not None

    def test_default_size(self, qtbot) -> None:
        """Test default canvas size in centimeters."""
        scene = CanvasScene(width_cm=1000, height_cm=800)
        # Use canvas_rect which gives the actual canvas area (not padded scene rect)
        rect = scene.canvas_rect
        assert rect.width() == 1000
        assert rect.height() == 800

    def test_scene_uses_cm_coordinates(self, qtbot) -> None:
        """Test that canvas coordinates are in centimeters."""
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        # Use canvas_rect which gives the actual canvas area
        rect = scene.canvas_rect
        # Canvas rect should be in cm with origin at (0,0)
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


class TestCopyPaste:
    """Tests for copy/paste functionality."""

    def test_copy_selected_items(self, qtbot) -> None:
        """Test copying selected items to clipboard."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Create and add a rectangle
        rect = RectangleItem(100, 200, 300, 400, object_type=ObjectType.GENERIC_RECTANGLE)
        scene.addItem(rect)
        rect.setSelected(True)

        # Copy
        view.copy_selected()

        # Clipboard should have one item
        assert len(view._clipboard) == 1
        assert view._clipboard[0]["type"] == "rectangle"

    def test_copy_empty_selection(self, qtbot) -> None:
        """Test copying with no selection does nothing."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Copy with no selection
        view.copy_selected()

        # Clipboard should be empty
        assert len(view._clipboard) == 0

    def test_paste_items(self, qtbot) -> None:
        """Test pasting items from clipboard."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Create, add, and copy a rectangle
        rect = RectangleItem(100, 200, 300, 400, object_type=ObjectType.GENERIC_RECTANGLE)
        scene.addItem(rect)
        rect.setSelected(True)
        view.copy_selected()

        # Initial count
        initial_count = len([item for item in scene.items() if isinstance(item, RectangleItem)])

        # Paste
        view.paste()

        # Should have one more rectangle
        final_count = len([item for item in scene.items() if isinstance(item, RectangleItem)])
        assert final_count == initial_count + 1

        # New item should be offset
        items = [item for item in scene.items() if isinstance(item, RectangleItem)]
        assert len(items) == 2

    def test_paste_multiple_times(self, qtbot) -> None:
        """Test pasting the same items multiple times."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Create, add, and copy a rectangle
        rect = RectangleItem(100, 200, 300, 400, object_type=ObjectType.GENERIC_RECTANGLE)
        scene.addItem(rect)
        rect.setSelected(True)
        view.copy_selected()

        # Paste twice
        view.paste()
        view.paste()

        # Should have 3 rectangles total
        items = [item for item in scene.items() if isinstance(item, RectangleItem)]
        assert len(items) == 3

    def test_paste_empty_clipboard(self, qtbot) -> None:
        """Test pasting with empty clipboard does nothing."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        initial_count = len(scene.items())

        # Paste with empty clipboard
        view.paste()

        # No new items
        assert len(scene.items()) == initial_count

    def test_cut_selected_items(self, qtbot) -> None:
        """Test cutting selected items."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Create and add a rectangle
        rect = RectangleItem(100, 200, 300, 400, object_type=ObjectType.GENERIC_RECTANGLE)
        scene.addItem(rect)
        rect.setSelected(True)

        # Cut
        view.cut_selected()

        # Clipboard should have the item
        assert len(view._clipboard) == 1

        # Rectangle should be removed from scene
        items = [item for item in scene.items() if isinstance(item, RectangleItem)]
        assert len(items) == 0

    def test_cut_and_paste(self, qtbot) -> None:
        """Test cutting and pasting items."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Create and add a rectangle
        rect = RectangleItem(100, 200, 300, 400, object_type=ObjectType.GENERIC_RECTANGLE)
        scene.addItem(rect)
        rect.setSelected(True)

        # Cut
        view.cut_selected()

        # Should have no rectangles
        items = [item for item in scene.items() if isinstance(item, RectangleItem)]
        assert len(items) == 0

        # Paste
        view.paste()

        # Should have one rectangle again
        items = [item for item in scene.items() if isinstance(item, RectangleItem)]
        assert len(items) == 1

    def test_copy_multiple_items(self, qtbot) -> None:
        """Test copying multiple selected items."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Create and add multiple shapes
        rect = RectangleItem(100, 200, 300, 400, object_type=ObjectType.GENERIC_RECTANGLE)
        circle = CircleItem(500, 500, 100, object_type=ObjectType.GENERIC_CIRCLE)
        polygon = PolygonItem(
            [QPointF(700, 700), QPointF(800, 700), QPointF(750, 800)],
            object_type=ObjectType.GENERIC_POLYGON
        )

        scene.addItem(rect)
        scene.addItem(circle)
        scene.addItem(polygon)

        rect.setSelected(True)
        circle.setSelected(True)
        polygon.setSelected(True)

        # Copy
        view.copy_selected()

        # Clipboard should have 3 items
        assert len(view._clipboard) == 3

    def test_paste_multiple_items(self, qtbot) -> None:
        """Test pasting multiple items at once."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Create and add multiple shapes
        rect = RectangleItem(100, 200, 300, 400, object_type=ObjectType.GENERIC_RECTANGLE)
        circle = CircleItem(500, 500, 100, object_type=ObjectType.GENERIC_CIRCLE)

        scene.addItem(rect)
        scene.addItem(circle)

        rect.setSelected(True)
        circle.setSelected(True)

        # Copy
        view.copy_selected()

        # Paste
        view.paste()

        # Should have 4 items total (2 original + 2 pasted)
        items = [item for item in scene.items()
                 if isinstance(item, (RectangleItem, CircleItem))]
        assert len(items) == 4

    def test_paste_with_undo(self, qtbot) -> None:
        """Test that paste can be undone."""
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)

        # Create, add, and copy a rectangle
        rect = RectangleItem(100, 200, 300, 400, object_type=ObjectType.GENERIC_RECTANGLE)
        scene.addItem(rect)
        rect.setSelected(True)
        view.copy_selected()

        # Paste
        view.paste()
        assert len([item for item in scene.items() if isinstance(item, RectangleItem)]) == 2

        # Undo
        view.command_manager.undo()
        assert len([item for item in scene.items() if isinstance(item, RectangleItem)]) == 1

        # Redo
        view.command_manager.redo()
        assert len([item for item in scene.items() if isinstance(item, RectangleItem)]) == 2
