"""Tests for US-6.4: Visual scale bar on canvas."""

import pytest

from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView


class TestScaleBarVisibility:
    """Tests for scale bar toggle."""

    def test_scale_bar_visible_by_default(self, qtbot) -> None:
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        assert view.scale_bar_visible is True

    def test_set_scale_bar_visible_false(self, qtbot) -> None:
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        view.set_scale_bar_visible(False)
        assert view.scale_bar_visible is False

    def test_set_scale_bar_visible_true(self, qtbot) -> None:
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        view.set_scale_bar_visible(False)
        view.set_scale_bar_visible(True)
        assert view.scale_bar_visible is True


class TestScaleBarDistanceFormat:
    """Tests for distance label formatting."""

    def test_format_centimeters(self, qtbot) -> None:
        assert CanvasView._format_distance(1) == "1 cm"
        assert CanvasView._format_distance(5) == "5 cm"
        assert CanvasView._format_distance(50) == "50 cm"

    def test_format_meters(self, qtbot) -> None:
        assert CanvasView._format_distance(100) == "1 m"
        assert CanvasView._format_distance(200) == "2 m"
        assert CanvasView._format_distance(500) == "5 m"
        assert CanvasView._format_distance(1000) == "10 m"

    def test_format_kilometers(self, qtbot) -> None:
        assert CanvasView._format_distance(100000) == "1 km"
        assert CanvasView._format_distance(500000) == "5 km"

    def test_format_no_trailing_zeros(self, qtbot) -> None:
        # %g format strips trailing zeros
        assert CanvasView._format_distance(100) == "1 m"
        assert CanvasView._format_distance(250) == "2.5 m"


class TestScaleBarDistancePicking:
    """Tests for the scale bar round distance selection."""

    def test_picks_from_nice_distances(self, qtbot) -> None:
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        # At default zoom (1.0), target ~150px => 150cm = 1.5m
        # Closest nice distance should be 100cm or 200cm
        dist = view._pick_scale_bar_distance()
        assert dist in CanvasView._SCALE_BAR_NICE_DISTANCES

    def test_zoomed_in_picks_smaller_distance(self, qtbot) -> None:
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        view.set_zoom(10.0)  # Very zoomed in
        dist = view._pick_scale_bar_distance()
        # At zoom=10, 150px = 15cm, so should pick small distance
        assert dist <= 50

    def test_zoomed_out_picks_larger_distance(self, qtbot) -> None:
        scene = CanvasScene()
        view = CanvasView(scene)
        qtbot.addWidget(view)
        view.set_zoom(0.05)  # Very zoomed out
        dist = view._pick_scale_bar_distance()
        # At zoom=0.05, 150px = 3000cm = 30m, should pick large distance
        assert dist >= 1000
