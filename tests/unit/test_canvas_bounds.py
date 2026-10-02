"""Unit tests for the shared canvas-clamp math (issue #380).

The same rule now backs the GUI drag clamp and the agent write clamp, so these
tests pin the behaviour both depend on, edge choice included.
"""

from __future__ import annotations

import pytest

from open_garden_planner.core.canvas_bounds import (
    clamp_delta_within_canvas,
    clamp_shift_within_canvas,
    rect_intersects_canvas,
)

W, H = 1000.0, 800.0


class TestClampShiftWithinCanvas:
    def test_inside_returns_zero(self) -> None:
        assert clamp_shift_within_canvas([(100, 100, 200, 200)], W, H) == (0.0, 0.0)

    def test_left_overflow_shifts_right(self) -> None:
        assert clamp_shift_within_canvas([(-50, 100, 50, 200)], W, H) == (50.0, 0.0)

    def test_top_overflow_shifts_down(self) -> None:
        assert clamp_shift_within_canvas([(100, -30, 200, 70)], W, H) == (0.0, 30.0)

    def test_right_overflow_shifts_left(self) -> None:
        assert clamp_shift_within_canvas([(950, 100, 1100, 200)], W, H) == (-100.0, 0.0)

    def test_bottom_overflow_shifts_up(self) -> None:
        assert clamp_shift_within_canvas([(100, 750, 200, 900)], W, H) == (0.0, -100.0)

    def test_corner_overflow_shifts_both(self) -> None:
        assert clamp_shift_within_canvas([(-50, -50, 50, 50)], W, H) == (50.0, 50.0)

    def test_left_wins_over_right_for_oversized_rect(self) -> None:
        """An oversized rect aligns its left edge to 0 — same as the GUI."""
        rect = (-100, 0, W + 200, H)
        assert clamp_shift_within_canvas([rect], W, H) == (100.0, 0.0)

    def test_union_of_two_rects(self) -> None:
        rects = [(100, 100, 200, 200), (-40, 300, 60, 400)]
        assert clamp_shift_within_canvas(rects, W, H) == (40.0, 0.0)

    def test_empty_returns_zero(self) -> None:
        assert clamp_shift_within_canvas([], W, H) == (0.0, 0.0)


class TestClampDeltaWithinCanvas:
    def test_small_move_inside_is_unchanged(self) -> None:
        assert clamp_delta_within_canvas([(100, 100, 200, 200)], 10, 10, W, H) == (
            10.0,
            10.0,
        )

    def test_move_past_left_edge_is_restricted(self) -> None:
        # rect left=100; a -200 dx would put it at -100, so max is -100.
        assert clamp_delta_within_canvas([(100, 100, 200, 200)], -200, 0, W, H) == (
            -100.0,
            0.0,
        )

    def test_move_past_right_edge_is_restricted(self) -> None:
        # rect right=900; a +200 dx would exceed W=1000, so max is +100.
        assert clamp_delta_within_canvas([(800, 100, 900, 200)], 200, 0, W, H) == (
            100.0,
            0.0,
        )

    def test_move_past_top_and_bottom(self) -> None:
        assert clamp_delta_within_canvas([(100, 100, 200, 200)], 0, -300, W, H) == (
            0.0,
            -100.0,
        )
        assert clamp_delta_within_canvas([(100, 600, 200, 700)], 0, 300, W, H) == (
            0.0,
            100.0,
        )

    def test_empty_returns_delta(self) -> None:
        assert clamp_delta_within_canvas([], 12, -7, W, H) == (12.0, -7.0)


class TestRectIntersectsCanvas:
    def test_inside(self) -> None:
        assert rect_intersects_canvas((100, 100, 200, 200), W, H)

    def test_partial_overlap(self) -> None:
        assert rect_intersects_canvas((-50, 100, 50, 200), W, H)

    def test_fully_left_is_outside(self) -> None:
        assert not rect_intersects_canvas((-200, 100, -10, 200), W, H)

    def test_fully_above_is_outside(self) -> None:
        assert not rect_intersects_canvas((100, -200, 200, -10), W, H)

    def test_fully_right_is_outside(self) -> None:
        assert not rect_intersects_canvas((1100, 100, 1200, 200), W, H)

    def test_fully_below_is_outside(self) -> None:
        assert not rect_intersects_canvas((100, 900, 200, 1000), W, H)

    @pytest.mark.parametrize("cw,ch", [(0.0, 800.0), (1000.0, 0.0)])
    def test_degenerate_canvas_never_flags(self, cw: float, ch: float) -> None:
        assert rect_intersects_canvas((5000, 5000, 5100, 5100), cw, ch)


class TestGuiAgentParity:
    """The GUI drag clamp and the agent clamp must produce the same shift (#380).

    Both now call ``core.canvas_bounds``; this test proves the GUI's
    ``_clamp_items_to_canvas`` result equals the shared function's, so a future
    change to one path cannot silently diverge from the other.
    """

    def test_gui_drag_clamp_matches_shared_math(self, qtbot: object) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
        from open_garden_planner.ui.canvas.canvas_view import CanvasView
        from open_garden_planner.ui.canvas.items import RectangleItem

        scene = CanvasScene(width_cm=1000, height_cm=800)
        view = CanvasView(scene)
        qtbot.addWidget(view)  # type: ignore[attr-defined]

        bed = RectangleItem(-50, 100, 200, 100, object_type=ObjectType.RAISED_BED)
        scene.addItem(bed)

        rect = bed.sceneBoundingRect()
        before = (rect.left(), rect.top())
        expected_dx, expected_dy = clamp_shift_within_canvas(
            [(rect.left(), rect.top(), rect.right(), rect.bottom())], 1000.0, 800.0
        )
        view._clamp_items_to_canvas([bed])

        after = bed.sceneBoundingRect()
        assert abs(after.left() - (before[0] + expected_dx)) < 0.01
        assert abs(after.top() - (before[1] + expected_dy)) < 0.01

