"""Unit tests for boolean shape operations (US-11.12)."""

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from open_garden_planner.core.commands import BooleanShapeCommand, CommandManager
from open_garden_planner.core.shape_boolean import (
    all_paths_connected,
    boolean_intersect,
    boolean_subtract,
    boolean_union,
    boolean_union_many,
    item_to_painter_path,
    path_has_hole,
    paths_overlap,
    paths_touch_or_overlap,
    union_path_many,
)
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
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
        # ``rect()``, not the shadow-inflated ``boundingRect()``: a boolean must
        # see the circle the user sees (and the ellipse branch's rect), or
        # every circle is 4 cm larger on each side (#550 review).
        rect = path.boundingRect()
        assert (rect.x(), rect.y(), rect.width(), rect.height()) == pytest.approx(
            (25, 25, 50, 50), rel=1e-6
        )
        assert item.boundingRect().width() > item.rect().width()

    def test_ellipse_item(self, scene, qtbot) -> None:  # noqa: ARG002
        item = EllipseItem(10, 20, 100, 50)
        scene.addItem(item)
        path = item_to_painter_path(item)
        assert path is not None
        assert not path.isEmpty()
        rect = path.boundingRect()
        assert (rect.x(), rect.y(), rect.width(), rect.height()) == pytest.approx(
            (10, 20, 100, 50), rel=1e-6
        )

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

    def test_union_of_three_paths_is_one_flat_result(self, qtbot) -> None:  # noqa: ARG002
        paths = [
            _rect_path(0, 0, 100, 100),
            _rect_path(100, 0, 100, 100),
            _rect_path(200, 0, 100, 100),
        ]
        result = boolean_union_many(paths)
        assert result is not None
        assert result.count() >= 4  # one flattened 300 x 100 band
        assert result.boundingRect().width() == pytest.approx(300.0, rel=1e-6)


class TestContactForUnion:
    """Union accepts contact; intersect/subtract require a real overlap (#550)."""

    def test_touching_rectangles_touch_but_do_not_overlap(self, qtbot) -> None:  # noqa: ARG002
        left = _rect_path(0, 0, 100, 100)
        right = _rect_path(100, 0, 100, 100)
        assert paths_touch_or_overlap(left, right)
        assert not paths_overlap(left, right)

    def test_a_gap_is_neither_touching_nor_overlapping(self, qtbot) -> None:  # noqa: ARG002
        left = _rect_path(0, 0, 100, 100)
        right = _rect_path(100.5, 0, 100, 100)
        assert not paths_touch_or_overlap(left, right)
        assert not paths_overlap(left, right)

    def test_a_middle_shape_connects_two_distant_ones(self, qtbot) -> None:  # noqa: ARG002
        left = _rect_path(0, 0, 100, 100)
        middle = _rect_path(100, 0, 100, 100)
        right = _rect_path(200, 0, 100, 100)
        assert all_paths_connected([left, middle, right])

    def test_a_disjoint_selection_is_not_connected(self, qtbot) -> None:  # noqa: ARG002
        left = _rect_path(0, 0, 100, 100)
        middle = _rect_path(100, 0, 100, 100)
        far = _rect_path(400, 0, 100, 100)
        assert not all_paths_connected([left, middle, far])

    def test_two_paths_are_trivially_connected(self, qtbot) -> None:  # noqa: ARG002
        assert all_paths_connected([_rect_path(0, 0, 10, 10)])

    def test_a_small_real_overlap_is_still_an_overlap(self, qtbot) -> None:  # noqa: ARG002
        left = _rect_path(0, 0, 10, 10)
        right = _rect_path(9.95, 0, 10, 10)  # 0.5 cm^2
        assert paths_overlap(left, right)

    def test_a_ring_keeps_its_hole_as_a_second_subpath(self, qtbot) -> None:  # noqa: ARG002
        paths = [
            _rect_path(0, 0, 300, 20),
            _rect_path(0, 180, 300, 20),
            _rect_path(0, 20, 20, 160),
            _rect_path(280, 20, 20, 160),
        ]
        assert all_paths_connected(paths)
        result = union_path_many(paths)
        assert result is not None
        assert path_has_hole(result)

    def test_corner_contact_is_not_a_hole(self, qtbot) -> None:  # noqa: ARG002
        first = _rect_path(0, 0, 100, 100)
        second = _rect_path(100, 100, 100, 100)
        assert paths_touch_or_overlap(first, second)
        result = union_path_many([first, second])
        assert result is not None
        assert not path_has_hole(result)

    def test_tangent_circles_are_not_a_hole(self, qtbot) -> None:  # noqa: ARG002
        left = QPainterPath()
        left.addEllipse(QRectF(0, 0, 100, 100))
        right = QPainterPath()
        right.addEllipse(QRectF(100, 0, 100, 100))
        assert paths_touch_or_overlap(left, right)
        result = union_path_many([left, right])
        assert result is not None
        assert not path_has_hole(result)


class TestPointContactIsMergedWithoutAConnector:
    def test_corner_rectangles_have_no_diagonal_and_both_are_filled(self, qtbot) -> None:  # noqa: ARG002
        result = boolean_union_many(
            [_rect_path(0, 0, 100, 100), _rect_path(100, 100, 100, 100)]
        )
        assert result is not None
        points = [
            (result.at(i).x(), result.at(i).y()) for i in range(result.count())
        ]
        connector = {((0.0, 0.0), (100.0, 100.0)), ((100.0, 100.0), (0.0, 0.0))}
        assert not any(
            (points[i], points[(i + 1) % len(points)]) in connector
            for i in range(len(points))
        )
        # A connector from the old flattening is a long diagonal
        # (100,0)->(200,100); the merged contour is axis-aligned apart from the
        # 0.01 cm bevel at the contact.
        for first, second in zip(points, points[1:] + points[:1], strict=True):
            dx = abs(second[0] - first[0])
            dy = abs(second[1] - first[1])
            assert dx < 1e-6 or dy < 1e-6 or (dx * dx + dy * dy) < 0.001
        path = QPainterPath()
        path.addPolygon(result)
        path.closeSubpath()
        assert path.contains(QPointF(50, 50))
        assert path.contains(QPointF(150, 150))

    def test_tangent_circles_fill_both_lobes(self, qtbot) -> None:  # noqa: ARG002
        left = QPainterPath()
        left.addEllipse(QRectF(0, 0, 100, 100))
        right = QPainterPath()
        right.addEllipse(QRectF(100, 0, 100, 100))
        result = boolean_union_many([left, right])
        assert result is not None
        path = QPainterPath()
        path.addPolygon(result)
        path.closeSubpath()
        assert path.contains(QPointF(50, 50))
        assert path.contains(QPointF(150, 50))

        # The application draws a PolygonItem, not a bare QPainterPath. Use a
        # cache-disabled item (the selected/export path) so #472's >256-vertex
        # interactive outline does not turn this into an outline-only probe.
        scene = QGraphicsScene()
        item = PolygonItem.from_polygon(result)
        item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        item.setBrush(QBrush(QColor(255, 0, 0)))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        scene.addItem(item)
        image = QImage(200, 100, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        try:
            scene.render(painter, QRectF(0, 0, 200, 100), QRectF(0, 0, 200, 100))
        finally:
            painter.end()
        for point in ((50, 50), (150, 50)):
            colour = image.pixelColor(*point)
            assert colour.red() > 0 and colour.alpha() > 0


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
