"""Unit tests for boolean shape operations (US-11.12)."""

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath, QPolygonF
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.commands import BooleanShapeCommand, CommandManager
from open_garden_planner.core.shape_boolean import (
    boolean_intersect,
    boolean_subtract,
    boolean_union,
    item_to_painter_path,
)
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


def _rect_path(x: float, y: float, w: float, h: float) -> QPainterPath:
    """Create a QPainterPath rectangle for testing."""
    p = QPainterPath()
    p.addRect(QRectF(x, y, w, h))
    return p


class TestItemToPainterPath:
    """Tests for item_to_painter_path conversion."""

    @pytest.fixture()
    def scene(self, qtbot) -> QGraphicsScene:  # noqa: ARG002
        return QGraphicsScene()

    def test_polygon_item(self, scene, qtbot) -> None:  # noqa: ARG002
        vertices = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)]
        item = PolygonItem(vertices)
        scene.addItem(item)
        path = item_to_painter_path(item)
        assert path is not None
        assert not path.isEmpty()

    def test_rectangle_item(self, scene, qtbot) -> None:  # noqa: ARG002
        item = RectangleItem(0, 0, 100, 50)
        scene.addItem(item)
        path = item_to_painter_path(item)
        assert path is not None
        assert not path.isEmpty()

    def test_circle_item(self, scene, qtbot) -> None:  # noqa: ARG002
        item = CircleItem(50, 50, 25)
        scene.addItem(item)
        path = item_to_painter_path(item)
        assert path is not None
        assert not path.isEmpty()

    def test_unsupported_item_returns_none(self, scene, qtbot) -> None:  # noqa: ARG002
        from PyQt6.QtWidgets import QGraphicsRectItem

        item = QGraphicsRectItem(0, 0, 10, 10)
        scene.addItem(item)
        assert item_to_painter_path(item) is None


class TestBooleanOperations:
    """Tests for boolean union/intersect/subtract."""

    def test_union_overlapping_rects(self, qtbot) -> None:  # noqa: ARG002
        a = _rect_path(0, 0, 100, 100)
        b = _rect_path(50, 0, 100, 100)
        result = boolean_union(a, b)
        assert result is not None
        assert result.count() >= 4

    def test_intersect_overlapping_rects(self, qtbot) -> None:  # noqa: ARG002
        a = _rect_path(0, 0, 100, 100)
        b = _rect_path(50, 0, 100, 100)
        result = boolean_intersect(a, b)
        assert result is not None
        assert result.count() >= 4

    def test_subtract_overlapping_rects(self, qtbot) -> None:  # noqa: ARG002
        a = _rect_path(0, 0, 100, 100)
        b = _rect_path(50, 0, 100, 100)
        result = boolean_subtract(a, b)
        assert result is not None
        assert result.count() >= 4

    def test_intersect_non_overlapping_returns_none(self, qtbot) -> None:  # noqa: ARG002
        a = _rect_path(0, 0, 50, 50)
        b = _rect_path(200, 200, 50, 50)
        result = boolean_intersect(a, b)
        assert result is None

    def test_union_non_overlapping_returns_polygon(self, qtbot) -> None:  # noqa: ARG002
        a = _rect_path(0, 0, 50, 50)
        b = _rect_path(200, 200, 50, 50)
        result = boolean_union(a, b)
        # Union of non-overlapping shapes still produces a valid polygon
        assert result is not None


class TestBooleanShapeCommand:
    """Tests for BooleanShapeCommand undo/redo."""

    @pytest.fixture()
    def scene(self, qtbot) -> QGraphicsScene:  # noqa: ARG002
        return QGraphicsScene()

    @pytest.fixture()
    def manager(self, qtbot) -> CommandManager:  # noqa: ARG002
        return CommandManager()

    def test_execute_replaces_items(self, scene, manager, qtbot) -> None:  # noqa: ARG002
        item_a = PolygonItem(
            [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)]
        )
        item_b = PolygonItem(
            [QPointF(50, 0), QPointF(150, 0), QPointF(150, 100), QPointF(50, 100)]
        )
        result = PolygonItem(
            [QPointF(0, 0), QPointF(150, 0), QPointF(150, 100), QPointF(0, 100)]
        )
        scene.addItem(item_a)
        scene.addItem(item_b)

        cmd = BooleanShapeCommand(scene, item_a, item_b, result, "union")
        manager.execute(cmd)

        assert item_a.scene() is None
        assert item_b.scene() is None
        assert result.scene() is scene

    def test_undo_restores_originals(self, scene, manager, qtbot) -> None:  # noqa: ARG002
        item_a = PolygonItem(
            [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)]
        )
        item_b = PolygonItem(
            [QPointF(50, 0), QPointF(150, 0), QPointF(150, 100), QPointF(50, 100)]
        )
        result = PolygonItem(
            [QPointF(0, 0), QPointF(150, 0), QPointF(150, 100), QPointF(0, 100)]
        )
        scene.addItem(item_a)
        scene.addItem(item_b)

        cmd = BooleanShapeCommand(scene, item_a, item_b, result, "union")
        manager.execute(cmd)
        manager.undo()

        assert item_a.scene() is scene
        assert item_b.scene() is scene
        assert result.scene() is None

    def test_redo_reapplies(self, scene, manager, qtbot) -> None:  # noqa: ARG002
        item_a = PolygonItem(
            [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)]
        )
        item_b = PolygonItem(
            [QPointF(50, 0), QPointF(150, 0), QPointF(150, 100), QPointF(50, 100)]
        )
        result = PolygonItem(
            [QPointF(0, 0), QPointF(150, 0), QPointF(150, 100), QPointF(0, 100)]
        )
        scene.addItem(item_a)
        scene.addItem(item_b)

        cmd = BooleanShapeCommand(scene, item_a, item_b, result, "union")
        manager.execute(cmd)
        manager.undo()
        manager.redo()

        assert item_a.scene() is None
        assert item_b.scene() is None
        assert result.scene() is scene

    def test_description(self, qtbot) -> None:  # noqa: ARG002
        from PyQt6.QtWidgets import QGraphicsRectItem

        cmd = BooleanShapeCommand(
            QGraphicsScene(),
            QGraphicsRectItem(),
            QGraphicsRectItem(),
            QGraphicsRectItem(),
            "intersect",
        )
        assert "intersect" in cmd.description
