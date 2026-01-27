"""Unit tests for canvas item classes."""

import uuid

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsRectItem

from open_garden_planner.ui.canvas.items import (
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
        # #90EE90 with alpha 100
        expected = QColor(144, 238, 144, 100)
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
        # #ADD8E6 with alpha 100
        expected = QColor(173, 216, 230, 100)
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
