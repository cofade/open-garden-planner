"""Issue #1005: the Plant Grid's arithmetic is Qt-free and unit-tested."""

from __future__ import annotations

import pytest

from open_garden_planner.core.plant_grid import (
    HANDLE_DIRECTIONS,
    MIN_SPAN_CM,
    cell_centers,
    first_cell_center,
    handle_positions,
    resize_edges,
    snap_cell_span,
)


class TestCellCenters:
    @pytest.mark.parametrize(("rows", "columns", "width", "height"), [
        (1, 1, 100.0, 100.0),
        (2, 3, 300.0, 200.0),
        (4, 5, 111.0, 87.0),
    ])
    def test_row_major_centres_inside_the_rectangle(
        self, rows: int, columns: int, width: float, height: float,
    ) -> None:
        centers = cell_centers(rows, columns, width, height)
        assert len(centers) == rows * columns
        assert centers == sorted(centers, key=lambda p: (round(p[1], 6), p[0]))
        for x, y in centers:
            assert -width / 2 - 1e-9 <= x <= width / 2 + 1e-9
            assert -height / 2 - 1e-9 <= y <= height / 2 + 1e-9

    def test_the_first_centre_and_the_steps(self) -> None:
        centers = cell_centers(2, 3, 300.0, 200.0)
        assert first_cell_center(2, 3, 300.0, 200.0) == pytest.approx((-100.0, -50.0))
        assert centers[0] == pytest.approx((-100.0, -50.0))
        assert centers[1] == pytest.approx((0.0, -50.0))
        assert centers[2] == pytest.approx((100.0, -50.0))
        assert centers[3] == pytest.approx((-100.0, 50.0))

class TestResizeEdges:
    @pytest.mark.parametrize(("direction", "position", "expected"), [
        (-1, -100.0, (-100.0, 50.0)),
        (1, 100.0, (-50.0, 100.0)),
        (0, 0.0, (-50.0, 50.0)),
    ])
    def test_the_dragged_edge_moves_and_the_other_stays(
        self, direction: int, position: float, expected: tuple[float, float],
    ) -> None:
        assert resize_edges(100.0, direction, position) == pytest.approx(expected)

    def test_the_moving_edge_cannot_cross_the_minimum_span(self) -> None:
        low, high = resize_edges(100.0, 1, -100.0)
        assert high - low == pytest.approx(MIN_SPAN_CM)
        low, high = resize_edges(100.0, -1, 100.0)
        assert high - low == pytest.approx(MIN_SPAN_CM)

    def test_a_custom_minimum_span_is_honoured(self) -> None:
        low, high = resize_edges(100.0, 1, -100.0, min_span=10.0)
        assert high - low == pytest.approx(10.0)


class TestSnapCellSpan:
    @pytest.mark.parametrize(("span", "cells", "expected"), [
        (401.0, 3, 402.0),
        (400.0, 3, 399.0),
        (100.0, 4, 100.0),
        (2.0, 3, 3.0),
        (0.5, 20, 20.0),
    ])
    def test_it_rounds_to_whole_centimetre_cells(
        self, span: float, cells: int, expected: float,
    ) -> None:
        assert snap_cell_span(span, cells) == pytest.approx(expected)

    def test_a_zero_or_negative_cell_count_is_a_no_op(self) -> None:
        assert snap_cell_span(50.0, 0) == 50.0


class TestHandlePositions:
    def test_every_directional_handle_and_the_three_special_ones(self) -> None:
        handles = handle_positions(
            200.0, 100.0, rows=2, columns=2, diameter=40.0, rotation_offset=10.0,
        )
        assert set(handles) == {*HANDLE_DIRECTIONS, "rotate", "move", "diameter"}
        assert handles["move"] == (0.0, 0.0)
        assert handles[(-1, -1)] == pytest.approx((-100.0, -50.0))
        assert handles[(1, 1)] == pytest.approx((100.0, 50.0))
        assert handles[(0, -1)] == pytest.approx((0.0, -50.0))
        assert handles["rotate"] == pytest.approx((0.0, -60.0))
        first_x, first_y = first_cell_center(2, 2, 200.0, 100.0)
        assert handles["diameter"] == pytest.approx((first_x + 20.0, first_y))

    def test_handle_positions_are_listed_in_painting_order(self) -> None:
        handles = handle_positions(
            10.0, 10.0, rows=1, columns=1, diameter=4.0, rotation_offset=1.0,
        )
        directional = [key for key in handles if isinstance(key, tuple)]
        assert tuple(directional) == HANDLE_DIRECTIONS
