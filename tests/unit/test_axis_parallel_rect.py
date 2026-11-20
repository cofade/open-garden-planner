"""#828: a straight piece of a rectangle is recognised as a rectangle."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from open_garden_planner.core.shape_split import axis_parallel_rect


def _polygon(*points: tuple[float, float]) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


class TestAxisParallelRect:
    def test_a_rectangle_returns_its_frame(self) -> None:
        polygon = _polygon((10, 20), (60, 20), (60, 50), (10, 50))
        assert axis_parallel_rect(polygon) == (10.0, 20.0, 50.0, 30.0)

    def test_a_closing_point_is_ignored(self) -> None:
        polygon = _polygon(
            (10, 20), (60, 20), (60, 50), (10, 50), (10, 20)
        )
        assert axis_parallel_rect(polygon) == (10.0, 20.0, 50.0, 30.0)

    def test_the_clipper_rounding_is_absorbed(self) -> None:
        polygon = _polygon(
            (10.0, 20.0),
            (60.004, 20.0),
            (60.0, 50.003),
            (10.0, 50.0),
        )
        assert axis_parallel_rect(polygon) == pytest.approx(
            (10.0, 20.0, 50.0, 30.0), abs=0.01
        )

    def test_a_triangle_is_not_a_rectangle(self) -> None:
        assert axis_parallel_rect(_polygon((0, 0), (10, 0), (0, 10))) is None

    def test_a_trapezoid_is_not_a_rectangle(self) -> None:
        assert axis_parallel_rect(
            _polygon((0, 0), (10, 0), (8, 10), (2, 10))
        ) is None

    def test_a_diagonal_piece_is_not_a_rectangle(self) -> None:
        assert axis_parallel_rect(
            _polygon((0, 0), (10, 0), (12, 10), (2, 10))
        ) is None

    def test_a_degenerate_piece_is_not_a_rectangle(self) -> None:
        assert axis_parallel_rect(_polygon((0, 0), (10, 0), (10, 0), (0, 0))) is None
        assert axis_parallel_rect(QPolygonF()) is None

    def test_the_tolerance_bound_is_pinned(self) -> None:
        just_inside = _polygon((0, 0), (10.0099, 0), (10, 10), (0, 10))
        just_outside = _polygon((0, 0), (10.0101, 0), (10, 10), (0, 10))
        assert axis_parallel_rect(just_inside) is not None
        assert axis_parallel_rect(just_outside) is None
