"""Unit tests for construction geometry items and tools."""

import uuid

import pytest
from PyQt6.QtCore import QPointF, Qt

from open_garden_planner.ui.canvas.items.construction_item import (
    ConstructionCircleItem,
    ConstructionLineItem,
)


class TestConstructionLineItem:
    """Tests for ConstructionLineItem."""

    def test_creation(self, qtbot) -> None:  # noqa: ARG002
        """Test ConstructionLineItem can be created."""
        item = ConstructionLineItem(QPointF(0, 0), QPointF(100, 100))
        assert item is not None

    def test_is_construction_flag(self, qtbot) -> None:  # noqa: ARG002
        """Test is_construction attribute is True."""
        item = ConstructionLineItem(QPointF(0, 0), QPointF(50, 50))
        assert item.is_construction is True

    def test_has_uuid(self, qtbot) -> None:  # noqa: ARG002
        """Test item has a unique UUID."""
        item = ConstructionLineItem(QPointF(0, 0), QPointF(10, 10))
        assert isinstance(item.item_id, uuid.UUID)

    def test_unique_ids(self, qtbot) -> None:  # noqa: ARG002
        """Test two items have different UUIDs."""
        item1 = ConstructionLineItem(QPointF(0, 0), QPointF(10, 10))
        item2 = ConstructionLineItem(QPointF(0, 0), QPointF(10, 10))
        assert item1.item_id != item2.item_id

    def test_dashed_pen(self, qtbot) -> None:  # noqa: ARG002
        """Test pen is dashed."""
        item = ConstructionLineItem(QPointF(0, 0), QPointF(100, 0))
        assert item.pen().style() == Qt.PenStyle.DashLine

    def test_selectable_flag(self, qtbot) -> None:  # noqa: ARG002
        """Test item is selectable."""
        from PyQt6.QtWidgets import QGraphicsItem
        item = ConstructionLineItem(QPointF(0, 0), QPointF(10, 10))
        assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable

    def test_serialization(self, qtbot) -> None:  # noqa: ARG002
        """Test to_dict produces correct structure."""
        item = ConstructionLineItem(QPointF(10, 20), QPointF(30, 40))
        data = item.to_dict()
        assert data["type"] == "construction_line"
        assert "item_id" in data
        assert data["x1"] == pytest.approx(10.0)
        assert data["y1"] == pytest.approx(20.0)
        assert data["x2"] == pytest.approx(30.0)
        assert data["y2"] == pytest.approx(40.0)

    def test_deserialization(self, qtbot) -> None:  # noqa: ARG002
        """Test from_dict creates equivalent item."""
        original = ConstructionLineItem(QPointF(5, 15), QPointF(25, 35))
        data = original.to_dict()
        restored = ConstructionLineItem.from_dict(data)
        assert restored.item_id == original.item_id
        restored_data = restored.to_dict()
        assert restored_data["x1"] == pytest.approx(data["x1"])
        assert restored_data["y1"] == pytest.approx(data["y1"])
        assert restored_data["x2"] == pytest.approx(data["x2"])
        assert restored_data["y2"] == pytest.approx(data["y2"])


class TestConstructionCircleItem:
    """Tests for ConstructionCircleItem."""

    def test_creation(self, qtbot) -> None:  # noqa: ARG002
        """Test ConstructionCircleItem can be created."""
        item = ConstructionCircleItem(100, 100, 50)
        assert item is not None

    def test_is_construction_flag(self, qtbot) -> None:  # noqa: ARG002
        """Test is_construction attribute is True."""
        item = ConstructionCircleItem(0, 0, 30)
        assert item.is_construction is True

    def test_has_uuid(self, qtbot) -> None:  # noqa: ARG002
        """Test item has a unique UUID."""
        item = ConstructionCircleItem(0, 0, 20)
        assert isinstance(item.item_id, uuid.UUID)

    def test_dashed_pen(self, qtbot) -> None:  # noqa: ARG002
        """Test pen is dashed."""
        item = ConstructionCircleItem(0, 0, 30)
        assert item.pen().style() == Qt.PenStyle.DashLine

    def test_no_fill(self, qtbot) -> None:  # noqa: ARG002
        """Test circle has no fill brush."""
        item = ConstructionCircleItem(0, 0, 30)
        assert item.brush().style() == Qt.BrushStyle.NoBrush

    def test_radius(self, qtbot) -> None:  # noqa: ARG002
        """Test radius property returns correct value."""
        item = ConstructionCircleItem(0, 0, 42.5)
        assert item.radius == pytest.approx(42.5)

    def test_serialization(self, qtbot) -> None:  # noqa: ARG002
        """Test to_dict produces correct structure."""
        item = ConstructionCircleItem(10, 20, 15)
        data = item.to_dict()
        assert data["type"] == "construction_circle"
        assert "item_id" in data
        assert data["center_x"] == pytest.approx(10.0)
        assert data["center_y"] == pytest.approx(20.0)
        assert data["radius"] == pytest.approx(15.0)

    def test_deserialization(self, qtbot) -> None:  # noqa: ARG002
        """Test from_dict creates equivalent item."""
        original = ConstructionCircleItem(50, 60, 25)
        data = original.to_dict()
        restored = ConstructionCircleItem.from_dict(data)
        assert restored.item_id == original.item_id
        restored_data = restored.to_dict()
        assert restored_data["center_x"] == pytest.approx(data["center_x"])
        assert restored_data["center_y"] == pytest.approx(data["center_y"])
        assert restored_data["radius"] == pytest.approx(data["radius"])
