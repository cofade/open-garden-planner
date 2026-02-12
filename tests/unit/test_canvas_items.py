"""Unit tests for canvas item classes."""

import uuid

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsRectItem

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    GardenItemMixin,
    PolygonItem,
    RectangleItem,
)


class TestGardenItemMixin:
    """Tests for the GardenItemMixin class."""

    def test_has_uuid(self) -> None:
        """Test mixin generates a UUID."""
        mixin = GardenItemMixin()
        assert mixin.item_id is not None
        assert isinstance(mixin.item_id, uuid.UUID)

    def test_unique_uuids(self) -> None:
        """Test each instance gets a unique UUID."""
        mixin1 = GardenItemMixin()
        mixin2 = GardenItemMixin()
        assert mixin1.item_id != mixin2.item_id

    def test_item_id_str(self) -> None:
        """Test item_id_str property."""
        mixin = GardenItemMixin()
        assert mixin.item_id_str == str(mixin.item_id)


class TestRectangleItem:
    """Tests for the RectangleItem class."""

    def test_creation(self) -> None:
        """Test RectangleItem can be created."""
        item = RectangleItem(0, 0, 100, 50)
        assert item is not None

    def test_inherits_qgraphicsrectitem(self) -> None:
        """Test RectangleItem inherits from QGraphicsRectItem."""
        item = RectangleItem(0, 0, 100, 50)
        assert isinstance(item, QGraphicsRectItem)

    def test_has_uuid(self) -> None:
        """Test RectangleItem has a UUID."""
        item = RectangleItem(0, 0, 100, 50)
        assert item.item_id is not None

    def test_geometry(self) -> None:
        """Test RectangleItem stores correct geometry."""
        item = RectangleItem(10, 20, 100, 50)
        rect = item.rect()
        assert rect.x() == 10
        assert rect.y() == 20
        assert rect.width() == 100
        assert rect.height() == 50

    def test_fill_color(self) -> None:
        """Test RectangleItem has correct fill color."""
        item = RectangleItem(0, 0, 100, 50)
        # #90EE90 fully opaque
        expected = QColor(144, 238, 144, 255)
        assert item.brush().color() == expected

    def test_stroke_color(self) -> None:
        """Test RectangleItem has correct stroke color."""
        item = RectangleItem(0, 0, 100, 50)
        # #228B22
        expected = QColor(34, 139, 34)
        assert item.pen().color() == expected

    def test_stroke_width(self) -> None:
        """Test RectangleItem has correct stroke width."""
        item = RectangleItem(0, 0, 100, 50)
        assert item.pen().widthF() == 2.0

    def test_is_selectable(self) -> None:
        """Test RectangleItem is selectable."""
        item = RectangleItem(0, 0, 100, 50)
        assert item.flags() & QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable

    def test_is_movable(self) -> None:
        """Test RectangleItem is movable."""
        item = RectangleItem(0, 0, 100, 50)
        assert item.flags() & QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable

    def test_from_rect(self) -> None:
        """Test creating RectangleItem from QRectF."""
        rect = QRectF(10, 20, 100, 50)
        item = RectangleItem.from_rect(rect)
        assert item.rect().x() == 10
        assert item.rect().y() == 20
        assert item.rect().width() == 100
        assert item.rect().height() == 50


class TestPolygonItem:
    """Tests for the PolygonItem class."""

    @pytest.fixture
    def triangle_vertices(self):
        """Create triangle vertices."""
        return [
            QPointF(0, 0),
            QPointF(100, 0),
            QPointF(50, 86.6),  # Equilateral triangle
        ]

    def test_creation(self, triangle_vertices) -> None:
        """Test PolygonItem can be created."""
        item = PolygonItem(triangle_vertices)
        assert item is not None

    def test_inherits_qgraphicspolygonitem(self, triangle_vertices) -> None:
        """Test PolygonItem inherits from QGraphicsPolygonItem."""
        item = PolygonItem(triangle_vertices)
        assert isinstance(item, QGraphicsPolygonItem)

    def test_has_uuid(self, triangle_vertices) -> None:
        """Test PolygonItem has a UUID."""
        item = PolygonItem(triangle_vertices)
        assert item.item_id is not None

    def test_polygon_vertex_count(self, triangle_vertices) -> None:
        """Test PolygonItem stores correct number of vertices."""
        item = PolygonItem(triangle_vertices)
        assert item.polygon().count() == 3

    def test_fill_color(self, triangle_vertices) -> None:
        """Test PolygonItem has correct fill color."""
        item = PolygonItem(triangle_vertices)
        # #ADD8E6 fully opaque
        expected = QColor(173, 216, 230, 255)
        assert item.brush().color() == expected

    def test_stroke_color(self, triangle_vertices) -> None:
        """Test PolygonItem has correct stroke color."""
        item = PolygonItem(triangle_vertices)
        # #4682B4
        expected = QColor(70, 130, 180)
        assert item.pen().color() == expected

    def test_stroke_width(self, triangle_vertices) -> None:
        """Test PolygonItem has correct stroke width."""
        item = PolygonItem(triangle_vertices)
        assert item.pen().widthF() == 2.0

    def test_is_selectable(self, triangle_vertices) -> None:
        """Test PolygonItem is selectable."""
        item = PolygonItem(triangle_vertices)
        assert item.flags() & QGraphicsPolygonItem.GraphicsItemFlag.ItemIsSelectable

    def test_is_movable(self, triangle_vertices) -> None:
        """Test PolygonItem is movable."""
        item = PolygonItem(triangle_vertices)
        assert item.flags() & QGraphicsPolygonItem.GraphicsItemFlag.ItemIsMovable

    def test_is_focusable(self, triangle_vertices) -> None:
        """Test PolygonItem is focusable (for vertex edit mode key handling)."""
        item = PolygonItem(triangle_vertices)
        assert item.flags() & QGraphicsPolygonItem.GraphicsItemFlag.ItemIsFocusable


class TestPolygonVertexEditing:
    """Tests for polygon vertex editing functionality."""

    @pytest.fixture
    def square_vertices(self):
        """Create square vertices."""
        return [
            QPointF(0, 0),
            QPointF(100, 0),
            QPointF(100, 100),
            QPointF(0, 100),
        ]

    @pytest.fixture
    def triangle_vertices(self):
        """Create triangle vertices (minimum valid polygon)."""
        return [
            QPointF(0, 0),
            QPointF(100, 0),
            QPointF(50, 86.6),
        ]

    def test_vertex_edit_mode_initially_false(self, square_vertices) -> None:
        """Test polygon starts not in vertex edit mode."""
        item = PolygonItem(square_vertices)
        assert not item.is_vertex_edit_mode

    def test_enter_vertex_edit_mode(self, square_vertices) -> None:
        """Test entering vertex edit mode."""
        item = PolygonItem(square_vertices)
        item.enter_vertex_edit_mode()
        assert item.is_vertex_edit_mode

    def test_exit_vertex_edit_mode(self, square_vertices) -> None:
        """Test exiting vertex edit mode."""
        item = PolygonItem(square_vertices)
        item.enter_vertex_edit_mode()
        assert item.is_vertex_edit_mode
        item.exit_vertex_edit_mode()
        assert not item.is_vertex_edit_mode

    def test_get_vertex_count(self, square_vertices) -> None:
        """Test getting vertex count."""
        item = PolygonItem(square_vertices)
        assert item._get_vertex_count() == 4

    def test_get_vertex_position(self, square_vertices) -> None:
        """Test getting vertex position."""
        item = PolygonItem(square_vertices)
        pos = item._get_vertex_position(0)
        assert pos.x() == 0
        assert pos.y() == 0

        pos = item._get_vertex_position(2)
        assert pos.x() == 100
        assert pos.y() == 100

    def test_move_vertex_to(self, square_vertices) -> None:
        """Test moving a vertex."""
        item = PolygonItem(square_vertices)
        new_pos = QPointF(50, 50)
        item._move_vertex_to(0, new_pos)

        pos = item._get_vertex_position(0)
        assert pos.x() == 50
        assert pos.y() == 50

        # Other vertices should be unchanged
        pos1 = item._get_vertex_position(1)
        assert pos1.x() == 100
        assert pos1.y() == 0

    def test_insert_vertex(self, square_vertices) -> None:
        """Test inserting a vertex."""
        item = PolygonItem(square_vertices)
        assert item._get_vertex_count() == 4

        new_pos = QPointF(50, 0)
        item._insert_vertex(1, new_pos)

        assert item._get_vertex_count() == 5
        # Check the inserted vertex
        pos = item._get_vertex_position(1)
        assert pos.x() == 50
        assert pos.y() == 0
        # Original vertex 1 should now be at index 2
        pos = item._get_vertex_position(2)
        assert pos.x() == 100
        assert pos.y() == 0

    def test_remove_vertex(self, square_vertices) -> None:
        """Test removing a vertex."""
        item = PolygonItem(square_vertices)
        assert item._get_vertex_count() == 4

        item._remove_vertex(1)

        assert item._get_vertex_count() == 3
        # Vertex 2 should now be at index 1
        pos = item._get_vertex_position(1)
        assert pos.x() == 100
        assert pos.y() == 100

    def test_cannot_remove_below_minimum_vertices(self, triangle_vertices) -> None:
        """Test that minimum 3 vertices are enforced."""
        item = PolygonItem(triangle_vertices)
        assert item._get_vertex_count() == 3

        # _delete_vertex checks minimum, _remove_vertex is raw operation
        # The public API (_delete_vertex) should prevent going below 3
        item._delete_vertex(0)

        # Should still have 3 vertices (delete was prevented)
        assert item._get_vertex_count() == 3


class TestRectangleVertexEditing:
    """Tests for rectangle vertex editing functionality."""

    def test_vertex_edit_mode_initially_false(self) -> None:
        """Test rectangle starts not in vertex edit mode."""
        item = RectangleItem(0, 0, 100, 50)
        assert not item.is_vertex_edit_mode

    def test_enter_vertex_edit_mode(self) -> None:
        """Test entering vertex edit mode."""
        item = RectangleItem(0, 0, 100, 50)
        item.enter_vertex_edit_mode()
        assert item.is_vertex_edit_mode

    def test_exit_vertex_edit_mode(self) -> None:
        """Test exiting vertex edit mode."""
        item = RectangleItem(0, 0, 100, 50)
        item.enter_vertex_edit_mode()
        assert item.is_vertex_edit_mode
        item.exit_vertex_edit_mode()
        assert not item.is_vertex_edit_mode

    def test_is_focusable(self) -> None:
        """Test RectangleItem is focusable (for vertex edit mode key handling)."""
        item = RectangleItem(0, 0, 100, 50)
        assert item.flags() & QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable


class TestCircleItem:
    """Tests for the CircleItem class."""

    def test_creation(self) -> None:
        """Test CircleItem can be created."""
        item = CircleItem(50, 50, 25)
        assert item is not None

    def test_inherits_qgraphicsellipseitem(self) -> None:
        """Test CircleItem inherits from QGraphicsEllipseItem."""
        item = CircleItem(50, 50, 25)
        assert isinstance(item, QGraphicsEllipseItem)

    def test_has_uuid(self) -> None:
        """Test CircleItem has a UUID."""
        item = CircleItem(50, 50, 25)
        assert item.item_id is not None

    def test_center_property(self) -> None:
        """Test CircleItem stores correct center."""
        item = CircleItem(100, 150, 25)
        assert item.center.x() == 100
        assert item.center.y() == 150

    def test_radius_property(self) -> None:
        """Test CircleItem stores correct radius."""
        item = CircleItem(50, 50, 30)
        assert item.radius == 30

    def test_bounding_rect(self) -> None:
        """Test CircleItem has correct bounding rectangle."""
        # Center at (50, 50), radius 25 -> rect from (25, 25) with size 50x50
        item = CircleItem(50, 50, 25)
        rect = item.rect()
        assert rect.x() == 25
        assert rect.y() == 25
        assert rect.width() == 50
        assert rect.height() == 50

    def test_fill_color(self) -> None:
        """Test CircleItem has correct fill color."""
        item = CircleItem(50, 50, 25)
        # Light pink (#FFB6C1) fully opaque
        expected = QColor(255, 182, 193, 255)
        assert item.brush().color() == expected

    def test_stroke_color(self) -> None:
        """Test CircleItem has correct stroke color."""
        item = CircleItem(50, 50, 25)
        # Pale violet red (#DB7093)
        expected = QColor(219, 112, 147)
        assert item.pen().color() == expected

    def test_stroke_width(self) -> None:
        """Test CircleItem has correct stroke width."""
        item = CircleItem(50, 50, 25)
        assert item.pen().widthF() == 2.0

    def test_is_selectable(self) -> None:
        """Test CircleItem is selectable."""
        item = CircleItem(50, 50, 25)
        assert item.flags() & QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable

    def test_is_movable(self) -> None:
        """Test CircleItem is movable."""
        item = CircleItem(50, 50, 25)
        assert item.flags() & QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable

    def test_to_dict(self) -> None:
        """Test CircleItem serialization."""
        item = CircleItem(100, 150, 25)
        item.setPos(10, 20)
        data = item.to_dict()
        assert data["type"] == "circle"
        assert data["center"]["x"] == 100
        assert data["center"]["y"] == 150
        assert data["radius"] == 25
        assert data["position"]["x"] == 10
        assert data["position"]["y"] == 20
        assert "id" in data

    def test_from_dict(self) -> None:
        """Test CircleItem deserialization."""
        data = {
            "type": "circle",
            "id": "test-id",
            "center": {"x": 100, "y": 150},
            "radius": 25,
            "position": {"x": 10, "y": 20},
        }
        item = CircleItem.from_dict(data)
        assert item.center.x() == 100
        assert item.center.y() == 150
        assert item.radius == 25
        assert item.pos().x() == 10
        assert item.pos().y() == 20


class TestGardenBedItem:
    """Tests for garden bed items (PolygonItem with ObjectType.GARDEN_BED)."""

    @pytest.fixture
    def bed_vertices(self):
        """Create garden bed vertices (rectangular bed)."""
        return [
            QPointF(0, 0),
            QPointF(200, 0),
            QPointF(200, 100),
            QPointF(0, 100),
        ]

    def test_garden_bed_creation(self, bed_vertices) -> None:
        """Test garden bed can be created."""
        item = PolygonItem(bed_vertices, object_type=ObjectType.GARDEN_BED)
        assert item is not None
        assert item.object_type == ObjectType.GARDEN_BED

    def test_garden_bed_fill_color(self, bed_vertices) -> None:
        """Test garden bed has correct brown soil fill color."""
        item = PolygonItem(bed_vertices, object_type=ObjectType.GARDEN_BED)
        # Brown soil color (139, 90, 43) fully opaque
        expected = QColor(139, 90, 43, 255)
        assert item.fill_color == expected

    def test_garden_bed_stroke_color(self, bed_vertices) -> None:
        """Test garden bed has correct forest green stroke color."""
        item = PolygonItem(bed_vertices, object_type=ObjectType.GARDEN_BED)
        # Forest green (#228B22)
        expected = QColor(34, 139, 34)
        assert item.pen().color() == expected

    def test_garden_bed_fill_pattern(self, bed_vertices) -> None:
        """Test garden bed has soil fill pattern."""
        item = PolygonItem(bed_vertices, object_type=ObjectType.GARDEN_BED)
        assert item.fill_pattern == FillPattern.SOIL

    def test_garden_bed_metadata(self, bed_vertices) -> None:
        """Test garden bed can store metadata."""
        metadata = {
            "soil_type": "loam",
            "is_raised": True,
            "height_cm": 30,
        }
        item = PolygonItem(
            bed_vertices,
            object_type=ObjectType.GARDEN_BED,
            name="Vegetable Bed",
            metadata=metadata,
        )
        assert item.name == "Vegetable Bed"
        assert item.metadata["soil_type"] == "loam"
        assert item.metadata["is_raised"] is True
        assert item.metadata["height_cm"] == 30

    def test_garden_bed_is_selectable(self, bed_vertices) -> None:
        """Test garden bed is selectable."""
        item = PolygonItem(bed_vertices, object_type=ObjectType.GARDEN_BED)
        assert item.flags() & QGraphicsPolygonItem.GraphicsItemFlag.ItemIsSelectable

    def test_garden_bed_is_movable(self, bed_vertices) -> None:
        """Test garden bed is movable."""
        item = PolygonItem(bed_vertices, object_type=ObjectType.GARDEN_BED)
        assert item.flags() & QGraphicsPolygonItem.GraphicsItemFlag.ItemIsMovable
