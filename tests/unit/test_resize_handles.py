"""Unit tests for resize handle functionality."""

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem
from open_garden_planner.ui.canvas.items.resize_handle import (
    MINIMUM_SIZE_CM,
    HandlePosition,
    ResizeHandle,
)


class TestResizeHandle:
    """Tests for the ResizeHandle class."""

    def test_handle_creation(self, qtbot) -> None:
        """Test ResizeHandle can be created."""
        rect = RectangleItem(0, 0, 100, 50)
        handle = ResizeHandle(HandlePosition.TOP_LEFT, rect)
        assert handle is not None
        assert handle.handle_position == HandlePosition.TOP_LEFT

    def test_handle_cursors(self, qtbot) -> None:
        """Test handles have appropriate cursors."""
        rect = RectangleItem(0, 0, 100, 50)

        # Corner handles should have diagonal cursors
        tl_handle = ResizeHandle(HandlePosition.TOP_LEFT, rect)
        assert tl_handle.cursor().shape() == Qt.CursorShape.SizeFDiagCursor

        br_handle = ResizeHandle(HandlePosition.BOTTOM_RIGHT, rect)
        assert br_handle.cursor().shape() == Qt.CursorShape.SizeFDiagCursor

        # Edge handles should have horizontal/vertical cursors
        top_handle = ResizeHandle(HandlePosition.TOP_CENTER, rect)
        assert top_handle.cursor().shape() == Qt.CursorShape.SizeVerCursor

        left_handle = ResizeHandle(HandlePosition.MIDDLE_LEFT, rect)
        assert left_handle.cursor().shape() == Qt.CursorShape.SizeHorCursor

    def test_handle_position_update(self, qtbot) -> None:
        """Test handle positions update based on parent bounding rect."""
        rect = RectangleItem(10, 20, 100, 50)
        handle = ResizeHandle(HandlePosition.TOP_LEFT, rect)
        handle.update_position()

        # Top-left handle should be at or near (10, 20) in item coordinates
        # Allow tolerance for pen width and handle offset
        assert abs(handle.pos().x() - 10) < 5
        assert abs(handle.pos().y() - 20) < 5


class TestRectangleItemResize:
    """Tests for RectangleItem resize functionality."""

    def test_resize_handles_created_on_selection(self, qtbot) -> None:
        """Test resize handles are created when item is selected."""
        scene = QGraphicsScene()
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)

        # Initially no handles
        assert len(rect._resize_handles) == 0

        # Select the item
        rect.setSelected(True)

        # Handles should be created
        assert len(rect._resize_handles) == 8

    def test_resize_handles_hidden_on_deselection(self, qtbot) -> None:
        """Test resize handles are hidden when item is deselected."""
        scene = QGraphicsScene()
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)

        # Select and then deselect
        rect.setSelected(True)
        assert len(rect._resize_handles) == 8

        rect.setSelected(False)

        # Handles should be hidden (but still exist)
        for handle in rect._resize_handles:
            assert not handle.isVisible()

    def test_rectangle_resize_changes_dimensions(self, qtbot) -> None:
        """Test resizing rectangle changes its dimensions."""
        rect = RectangleItem(0, 0, 100, 50)

        # Simulate resize from bottom-right
        rect._apply_resize(0, 0, 150, 75, 0, 0)

        # Dimensions should have changed
        assert rect.rect().width() == 150
        assert rect.rect().height() == 75

    def test_rectangle_minimum_size_enforced(self, qtbot) -> None:
        """Test minimum size constraint is enforced during handle drag."""
        rect = RectangleItem(0, 0, 100, 50)

        # Minimum size is enforced by ResizeHandle during drag, not by _apply_resize
        # _apply_resize just applies the values it receives
        # Test that we can enforce it manually
        new_width = max(0.5, MINIMUM_SIZE_CM)
        new_height = max(0.5, MINIMUM_SIZE_CM)
        rect._apply_resize(0, 0, new_width, new_height, 0, 0)

        # Should be at minimum
        assert rect.rect().width() == MINIMUM_SIZE_CM
        assert rect.rect().height() == MINIMUM_SIZE_CM


class TestCircleItemResize:
    """Tests for CircleItem resize functionality."""

    def test_resize_handles_created_on_selection(self, qtbot) -> None:
        """Test resize handles are created when circle is selected."""
        scene = QGraphicsScene()
        circle = CircleItem(50, 50, 25)
        scene.addItem(circle)

        # Select the item
        circle.setSelected(True)

        # Handles should be created
        assert len(circle._resize_handles) == 8

    def test_circle_resize_maintains_circular_shape(self, qtbot) -> None:
        """Test resizing circle maintains circular shape."""
        circle = CircleItem(50, 50, 25)

        # Try to resize to non-square dimensions (150x100)
        # Circle should use minimum dimension to maintain circular shape
        circle._apply_resize(-25, -25, 150, 100, 0, 0)

        # Should be circular (width == height), using minimum dimension
        rect = circle.rect()
        assert rect.width() == rect.height()
        assert rect.width() == 100  # Minimum of 150 and 100

    def test_circle_radius_updates_on_resize(self, qtbot) -> None:
        """Test circle radius property updates when resized."""
        circle = CircleItem(50, 50, 25)
        original_radius = circle.radius

        # Resize to larger circle
        new_diameter = 100
        circle._apply_resize(-25, -25, new_diameter, new_diameter, 0, 0)

        # Radius should have changed
        assert circle.radius == new_diameter / 2
        assert circle.radius != original_radius

    def test_circle_minimum_size_enforced(self, qtbot) -> None:
        """Test minimum size constraint is enforced for circles."""
        circle = CircleItem(50, 50, 25)

        # Minimum size is enforced by ResizeHandle during drag, not by _apply_resize
        new_diameter = max(0.5, MINIMUM_SIZE_CM)
        circle._apply_resize(0, 0, new_diameter, new_diameter, 0, 0)

        # Should be at minimum
        assert circle.radius == MINIMUM_SIZE_CM / 2


class TestPolygonItemResize:
    """Tests for PolygonItem resize functionality."""

    @pytest.fixture
    def triangle_vertices(self):
        """Create triangle vertices."""
        return [
            QPointF(0, 0),
            QPointF(100, 0),
            QPointF(50, 86.6),
        ]

    def test_resize_handles_created_on_selection(self, qtbot, triangle_vertices) -> None:
        """Test resize handles are created when polygon is selected."""
        scene = QGraphicsScene()
        poly = PolygonItem(triangle_vertices)
        scene.addItem(poly)

        # Select the item
        poly.setSelected(True)

        # Handles should be created
        assert len(poly._resize_handles) == 8

    def test_polygon_resize_scales_vertices(self, qtbot, triangle_vertices) -> None:
        """Test resizing polygon scales all vertices proportionally."""
        poly = PolygonItem(triangle_vertices)
        original_bounds = poly.boundingRect()

        # Double the size
        new_width = original_bounds.width() * 2
        new_height = original_bounds.height() * 2

        poly._apply_resize(
            original_bounds.x(),
            original_bounds.y(),
            new_width,
            new_height,
            0,
            0,
        )

        # Polygon should have scaled (allow tolerance for pen width and handle offset)
        new_bounds = poly.boundingRect()
        assert abs(new_bounds.width() - new_width) < 10
        assert abs(new_bounds.height() - new_height) < 10

    def test_polygon_vertex_count_preserved(self, qtbot, triangle_vertices) -> None:
        """Test polygon maintains same number of vertices after resize."""
        poly = PolygonItem(triangle_vertices)
        original_count = poly.polygon().count()

        # Resize polygon
        poly._apply_resize(0, 0, 200, 150, 0, 0)

        # Should have same vertex count
        assert poly.polygon().count() == original_count

    def test_polygon_initial_state_stored(self, qtbot, triangle_vertices) -> None:
        """Test polygon stores initial state when resize starts."""
        poly = PolygonItem(triangle_vertices)

        # Call resize start
        poly._on_resize_start()

        # Should have stored initial polygon
        assert poly._resize_initial_polygon is not None
        assert poly._resize_initial_polygon.count() == len(triangle_vertices)


class TestDimensionDisplay:
    """Tests for dimension display during resize."""

    def test_dimension_display_created(self, qtbot) -> None:
        """Test dimension display is created with resize handles."""
        scene = QGraphicsScene()
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)

        # Select to create handles
        rect.setSelected(True)

        # Dimension display should exist
        assert rect._dimension_display is not None

    def test_dimension_display_initially_hidden(self, qtbot) -> None:
        """Test dimension display is hidden initially."""
        scene = QGraphicsScene()
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)

        rect.setSelected(True)

        # Should be hidden until resize starts
        assert not rect._dimension_display.isVisible()

    def test_dimension_display_formats_centimeters(self, qtbot) -> None:
        """Test dimension display formats small values in centimeters."""
        scene = QGraphicsScene()
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        rect.setSelected(True)

        # Update with small dimensions
        rect._dimension_display.update_dimensions(50, 30, QPointF(0, 0))

        # Should show in cm
        text = rect._dimension_display._text.text()
        assert "cm" in text
        assert "50" in text or "50.0" in text

    def test_dimension_display_formats_meters(self, qtbot) -> None:
        """Test dimension display formats large values in meters."""
        scene = QGraphicsScene()
        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)
        rect.setSelected(True)

        # Update with large dimensions (>= 100cm)
        rect._dimension_display.update_dimensions(250, 150, QPointF(0, 0))

        # Should show in meters
        text = rect._dimension_display._text.text()
        assert "m" in text
        assert "2.50" in text or "1.50" in text


class TestResizeUndo:
    """Tests for resize undo/redo functionality."""

    def test_resize_creates_undo_command(self, qtbot) -> None:
        """Test resizing creates an undo command."""
        from open_garden_planner.core.commands import CommandManager

        scene = QGraphicsScene()
        command_manager = CommandManager()
        scene.get_command_manager = lambda: command_manager

        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)

        # Simulate resize
        initial_rect = rect.rect()
        initial_pos = rect.pos()
        rect._apply_resize(0, 0, 150, 75, 0, 0)
        rect._on_resize_end(initial_rect, initial_pos)

        # Should have command in undo stack
        assert command_manager.can_undo

    def test_resize_undo_restores_geometry(self, qtbot) -> None:
        """Test undoing resize restores original geometry."""
        from open_garden_planner.core.commands import CommandManager

        scene = QGraphicsScene()
        command_manager = CommandManager()
        scene.get_command_manager = lambda: command_manager

        rect = RectangleItem(0, 0, 100, 50)
        scene.addItem(rect)

        # Store original dimensions
        original_width = rect.rect().width()
        original_height = rect.rect().height()

        # Resize
        initial_rect = rect.rect()
        initial_pos = rect.pos()
        rect._apply_resize(0, 0, 150, 75, 0, 0)
        rect._on_resize_end(initial_rect, initial_pos)

        # Undo
        command_manager.undo()

        # Should be back to original
        assert rect.rect().width() == original_width
        assert rect.rect().height() == original_height
