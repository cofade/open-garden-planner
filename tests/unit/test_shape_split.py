"""Unit tests for the two-point shape split geometry (#664)."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath, QPolygonF

from open_garden_planner.core.shape_boolean import (
    _polygon_area,
    item_to_local_painter_path,
    item_to_painter_path,
)
from open_garden_planner.core.shape_split import (
    MIN_AXIS_LENGTH_CM,
    split_item_into_local_polygons,
    split_path,
)
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem


def _rect_path(x: float, y: float, width: float, height: float) -> QPainterPath:
    path = QPainterPath()
    path.addRect(QRectF(x, y, width, height))
    return path


def _total_area(polygons: list[QPolygonF]) -> float:
    return sum(_polygon_area(polygon) for polygon in polygons)


def test_a_vertical_axis_splits_a_rectangle_into_two_areas(qtbot) -> None:
    path = _rect_path(0, 0, 200, 100)
    pieces = split_path(path, QPointF(80, -50), QPointF(80, 150))

    assert len(pieces) == 2
    assert _total_area(pieces) == pytest.approx(20000.0, rel=1e-6)
    assert all(piece.count() >= 3 for piece in pieces)


def test_a_concave_shape_can_produce_more_than_two_pieces(qtbot) -> None:
    # A U: two arms on a base. A horizontal cut above the base separates the
    # two arms and leaves the base, so the documented "more than two" case is
    # real, not hypothetical.
    u_shape = QPolygonF(
        [
            QPointF(0, 0),
            QPointF(300, 0),
            QPointF(300, 300),
            QPointF(200, 300),
            QPointF(200, 100),
            QPointF(100, 100),
            QPointF(100, 300),
            QPointF(0, 300),
        ]
    )
    path = QPainterPath()
    path.addPolygon(u_shape)
    path.closeSubpath()

    pieces = split_path(path, QPointF(-10, 150), QPointF(310, 150))

    assert len(pieces) == 3
    assert _total_area(pieces) == pytest.approx(_polygon_area(u_shape), rel=1e-6)


def test_degenerate_and_tangent_axes_are_refused(qtbot) -> None:
    path = _rect_path(0, 0, 100, 100)

    assert split_path(path, QPointF(50, 50), QPointF(50, 50)) == []
    assert split_path(QPainterPath(), QPointF(0, 0), QPointF(10, 10)) == []
    # Along an edge: one side is empty, so the cut cannot make two pieces.
    assert split_path(path, QPointF(0, 0), QPointF(100, 0)) == []
    # Entirely outside the shape.
    assert split_path(path, QPointF(200, 0), QPointF(200, 100)) == []


def test_a_rotated_source_keeps_its_local_frame_and_area(qtbot) -> None:
    source = RectangleItem(100, 100, 200, 100)
    source._apply_rotation(37)
    original = item_to_painter_path(source)
    assert original is not None

    pieces = split_item_into_local_polygons(
        source, QPointF(200, -500), QPointF(200, 500)
    )

    assert len(pieces) == 2
    scene_area = 0.0
    for polygon in pieces:
        scene_polygon = source.mapToScene(polygon)
        scene_path = QPainterPath()
        scene_path.addPolygon(scene_polygon)
        scene_path.closeSubpath()
        scene_area += _polygon_area(scene_path.toFillPolygon())
        # The piece is in the source's LOCAL frame (0..200 x 0..100 before
        # rotation), not in scene coordinates.
        assert polygon.boundingRect().width() <= 200.0 + 1e-6
    assert scene_area == pytest.approx(20000.0, rel=1e-6)


def test_a_circle_becomes_polygons_with_the_same_area(qtbot) -> None:
    source = CircleItem(0, 0, 50)
    pieces = split_item_into_local_polygons(
        source, QPointF(0, -100), QPointF(0, 100)
    )

    assert len(pieces) == 2
    assert _total_area(pieces) == pytest.approx(math.pi * 50 * 50, rel=0.01)


def test_a_rectangle_item_converts_to_its_local_path(qtbot) -> None:
    source = RectangleItem(10, 20, 300, 100)
    local = item_to_local_painter_path(source)
    scene = item_to_painter_path(source)

    assert local is not None and scene is not None
    assert local.boundingRect() == QRectF(10, 20, 300, 100)
    assert _polygon_area(local.toFillPolygon()) == pytest.approx(30000.0)
    assert _polygon_area(scene.toFillPolygon()) == pytest.approx(30000.0)


def test_axis_length_floor_is_a_real_constant() -> None:
    assert MIN_AXIS_LENGTH_CM > 0.0
