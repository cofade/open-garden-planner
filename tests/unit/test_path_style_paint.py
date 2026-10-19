"""The walk along a styled path, and its bound (Phase 17 L1.5, #385 — security add-on).

``PathStylePaint`` paints a path or fence style for two callers: the canvas item
(the whole line) and the 3D ground bake (one tile at a time). These tests are
about the WALK that places a style's elements — what it hands out, and what it
costs to find them. They count: elements handed out, steps charged, loop turns
taken. No clock is read.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from open_garden_planner.core.object_types import PathFenceStyle
from open_garden_planner.ui.canvas.items import path_style_paint
from open_garden_planner.ui.canvas.items.path_style_paint import (
    MAX_SPACING_CM,
    MIN_SPACING_CM,
    PathStylePaint,
    WalkBudget,
    segment_inside,
)

ZIGZAG = [QPointF(0.0, 0.0), QPointF(400.5, 30.25), QPointF(380.0, 300.0), QPointF(900.0, 310.75),
          QPointF(905.0, 20.0)]
Clip = tuple[float, float, float, float]


def pen(width: float = 30.0) -> QPen:
    made = QPen(QColor(120, 90, 60))
    made.setWidthF(width)
    return made


def legacy_walk(points: list[QPointF], spacing: float) -> list[tuple[int, float, float]]:
    """The walk as ``PolylineItem`` did it before it was shared: one running sum."""
    out: list[tuple[int, float, float]] = []
    remaining = 0.0
    for first, second in zip(points, points[1:], strict=False):
        dx, dy = second.x() - first.x(), second.y() - first.y()
        length = math.hypot(dx, dy)
        if length < 0.001:
            continue
        t = remaining
        while t <= length:
            out.append((len(out), first.x() + dx / length * t, first.y() + dy / length * t))
            t += spacing
        remaining = t - length
    return out


def walked(painter: PathStylePaint, spacing: float) -> list[tuple[int, float, float]]:
    return [(index, element[0].x(), element[0].y())
            for index, element in painter._walk_indexed(spacing)]


def inside(clip: Clip, x: float, y: float) -> bool:
    return clip[0] <= x <= clip[2] and clip[1] <= y <= clip[3]


class TestTheUnclippedWalkIsTheCanvass:
    @pytest.mark.parametrize("spacing", [4.0, 10.5, 54.00000000000001, 240.0, 5000.0])
    def test_every_element_at_the_old_place_with_the_old_index(self, spacing: float) -> None:
        assert walked(PathStylePaint(ZIGZAG, pen()), spacing) == legacy_walk(ZIGZAG, spacing)

    def test_the_plain_walk_is_the_indexed_one_without_its_indices(self) -> None:
        painter = PathStylePaint(ZIGZAG, pen())
        assert [(e[0].x(), e[0].y()) for e in painter._walk_path(10.5)] == [
            (x, y) for _i, x, y in legacy_walk(ZIGZAG, 10.5)]


CLIPS: list[Clip] = [(-50.0, -50.0, 200.0, 200.0), (350.0, 0.0, 420.0, 320.0),
                     (600.0, 250.0, 2000.0, 2000.0), (-1e6, -1e6, 1e6, 1e6), (5000.0, 5000.0, 6000.0, 6000.0)]


class TestTheClippedWalk:
    @pytest.mark.parametrize("clip", CLIPS)
    @pytest.mark.parametrize("spacing", [4.0, 10.5, 54.00000000000001])
    def test_it_hands_out_exactly_the_elements_inside_with_their_global_indices(
            self, clip: Clip, spacing: float) -> None:
        """With steps to spare the clipped walk IS the canvas's walk — the same
        floats — less what lies outside: nothing added, nothing renumbered."""
        budget = WalkBudget(10**6, 10**6)
        got = walked(PathStylePaint(ZIGZAG, pen(), clip=clip, budget=budget), spacing)
        assert got == [e for e in legacy_walk(ZIGZAG, spacing) if inside(clip, e[1], e[2])]
        assert budget.elements_spent == len(got) and not budget.truncated

    @pytest.mark.parametrize("clip", CLIPS)
    @pytest.mark.parametrize("spacing", [4.0, 10.5, 54.00000000000001])
    def test_without_steps_it_finds_the_same_elements_by_arithmetic(
            self, clip: Clip, spacing: float) -> None:
        """No exact step allowed: every segment is entered by multiplication. The
        same elements, the same indices, the same places to within a nanometre."""
        budget = WalkBudget(10**6, 0)
        got = walked(PathStylePaint(ZIGZAG, pen(), clip=clip, budget=budget), spacing)
        expected = [e for e in legacy_walk(ZIGZAG, spacing) if inside(clip, e[1], e[2])]
        assert budget.steps_spent == 0
        assert [index for index, _x, _y in got] == [index for index, _x, _y in expected]
        for (_i, x, y), (_j, ex, ey) in zip(got, expected, strict=True):
            assert math.hypot(x - ex, y - ey) < 1e-7

    def test_the_steps_walked_are_charged_not_the_elements_handed_out(self) -> None:
        """The finding: a segment that clips the window by a hair is walked from its
        start. Every one of those steps is paid for BEFORE it is taken — and when
        the window's budget does not cover them, none is taken."""
        line = [QPointF(0.0, 0.0), QPointF(64_000.0, 0.0)]  # 16,001 dots at 4 cm
        clip: Clip = (63_990.0, -5.0, 64_100.0, 5.0)        # … 3 of them inside
        rich = WalkBudget(10**6, 10**6)
        assert len(walked(PathStylePaint(line, pen(), clip=clip, budget=rich), 4.0)) == 3
        assert rich.steps_spent == 16_001 and rich.elements_spent == 3
        poor = WalkBudget(10**6, 16_000)
        assert len(walked(PathStylePaint(line, pen(), clip=clip, budget=poor), 4.0)) == 3
        assert poor.steps_spent == 0 and poor.elements_spent == 3

    def test_one_budget_bounds_all_the_paths_of_a_window(self) -> None:
        """256 paths that each clip one window by a hair: the exact walk is taken
        while the window's steps last and not once more — whatever the number of
        paths. (It was an allowance per path: 256 x 16,001 steps for one tile.)"""
        clip: Clip = (63_990.0, -5.0, 64_100.0, 300.0)
        budget = WalkBudget(16_384, 16_384)
        handed_out = 0
        for k in range(256):
            line = [QPointF(0.0, float(k)), QPointF(64_000.0, float(k))]
            handed_out += len(walked(PathStylePaint(line, pen(), clip=clip, budget=budget), 4.0))
        assert handed_out == 256 * 3
        assert budget.steps_spent == 16_001  # ONE path's exact walk; the rest by arithmetic
        assert budget.steps == 383 and budget.elements_spent == 768

    def test_the_loop_turns_of_a_walk_are_bounded_by_the_budget_and_the_vertices(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Counted at the source: every element handed out or stepped over in the
        exact walk makes one ``QPointF`` or one comparison — here the points made
        are counted, for a line of 19 km."""
        made = []
        real = path_style_paint.QPointF

        def counting(*args: Any) -> Any:
            made.append(1)
            return real(*args)

        line = [real(-950_000.0, 0.0), real(950_000.0, 0.0)]
        clip: Clip = (0.0, -50.0, 512.0, 50.0)
        budget = WalkBudget(16_384, 16_384)
        painter = PathStylePaint(line, pen(), clip=clip, budget=budget)
        monkeypatch.setattr(path_style_paint, "QPointF", counting)
        got = walked(painter, 4.0)
        assert len(got) == 129 == len(made)  # the dots of 512 cm, and not one point more
        assert budget.steps_spent == 0  # 475,001 steps were never affordable: arithmetic

    def test_zero_is_a_budget(self) -> None:
        """A spent budget means "no more elements", never "no bound"."""
        clip: Clip = (-1e6, -1e6, 1e6, 1e6)
        spent = WalkBudget(0, 0)
        painter = PathStylePaint(ZIGZAG, pen(), clip=clip, budget=spent)
        assert walked(painter, 10.5) == [] and spent.truncated and spent.elements_spent == 0
        exactly = len(legacy_walk(ZIGZAG, 10.5))
        shared = WalkBudget(exactly, 10**6)  # spent to the last element by the first path
        assert len(walked(PathStylePaint(ZIGZAG, pen(), clip=clip, budget=shared), 10.5)) == exactly
        assert shared.elements == 0 and not shared.truncated
        assert walked(PathStylePaint(ZIGZAG, pen(), clip=clip, budget=shared), 10.5) == []
        assert shared.truncated and shared.elements_spent == exactly

    def test_dashes_are_charged_all_or_none_and_zero_is_a_budget(self) -> None:
        """The dashes of dashed pens (the ground bake charges them): a stroke is
        covered whole or not at all, and a budget without dashes covers none."""
        budget = WalkBudget(10, 10, 100)
        assert budget.take_dashes(60) and budget.dashes == 40 and not budget.truncated
        assert not budget.take_dashes(41)  # not covered: nothing charged, and it says so
        assert budget.dashes == 40 and budget.dashes_spent == 60 and budget.truncated
        assert budget.take_dashes(40) and budget.dashes == 0
        assert not budget.take_dashes(1)
        none = WalkBudget(10, 10)  # as the walks' own callers make it
        assert none.dashes == 0 and not none.take_dashes(1) and none.truncated
        with pytest.raises(ValueError, match="not negative"):
            WalkBudget(1, 1, -1)

    def test_a_clip_and_a_budget_come_together(self) -> None:
        with pytest.raises(ValueError, match="needs a budget"):
            PathStylePaint(ZIGZAG, pen(), clip=(0.0, 0.0, 1.0, 1.0))
        with pytest.raises(ValueError, match="needs a budget"):
            PathStylePaint(ZIGZAG, pen(), budget=WalkBudget(1, 1))
        with pytest.raises(ValueError, match="not negative"):
            WalkBudget(-1, 0)


class TestSpacingsNoStyleDrawsAt:
    @pytest.mark.parametrize("spacing", [0.0, -4.0, 1e-300, 5e-324, MIN_SPACING_CM / 2, float("nan"),
                                         float("inf"), 1e300, MAX_SPACING_CM * 2])
    def test_no_elements_no_loop_no_overflow(self, spacing: float) -> None:
        """Zero and a negative spacing never returned; a denormal one made an
        integer no float can hold. None of them is a pattern: no elements."""
        assert walked(PathStylePaint(ZIGZAG, pen()), spacing) == []
        budget = WalkBudget(100, 100)
        clip: Clip = (-1e6, -1e6, 1e6, 1e6)
        assert walked(PathStylePaint(ZIGZAG, pen(), clip=clip, budget=budget), spacing) == []
        assert budget.elements_spent == 0 and budget.steps_spent == 0

    def test_the_floor_is_below_every_preset_pen(self) -> None:
        assert MIN_SPACING_CM == 0.05 and MAX_SPACING_CM == 1e7
        assert len(walked(PathStylePaint(ZIGZAG, pen()), MIN_SPACING_CM * 100)) > 100

    @pytest.mark.parametrize("width", [0.0, 1e-300, 5e-324, 1e-3, float("inf")])
    @pytest.mark.parametrize("style", [s for s in PathFenceStyle if s is not PathFenceStyle.NONE],
                             ids=lambda s: s.name)
    def test_every_style_returns_for_a_pen_width_that_is_no_width(
            self, qtbot: Any, style: PathFenceStyle, width: float) -> None:
        """Through the painters themselves — on the canvas's path (no clip) too."""
        image = QImage(64, 64, QImage.Format.Format_RGBA8888_Premultiplied)
        image.fill(QColor(255, 255, 255))
        painter = QPainter(image)
        try:
            assert PathStylePaint([QPointF(5.0, 5.0), QPointF(60.0, 50.0)], pen(width)).paint(
                painter, style) is True
        finally:
            painter.end()


class TestSegmentInside:
    @pytest.mark.parametrize(("start", "direction", "length", "expected"), [
        ((0.0, 5.0), (1.0, 0.0), 100.0, (10.0, 20.0)),     # crosses
        ((12.0, 5.0), (1.0, 0.0), 5.0, (0.0, 5.0)),        # inside
        ((0.0, 50.0), (1.0, 0.0), 100.0, None),            # beside, parallel
        ((0.0, 0.0), (0.0, 1.0), 100.0, None),             # beside, the other axis
        ((30.0, 5.0), (-1.0, 0.0), 100.0, (10.0, 20.0)),   # backwards
        ((0.0, 5.0), (1.0, 0.0), 8.0, None),               # stops short
    ])
    def test_the_part_of_a_segment_inside_a_box(
            self, start: tuple[float, float], direction: tuple[float, float], length: float,
            expected: tuple[float, float] | None) -> None:
        assert segment_inside(*start, *direction, length, (10.0, 0.0, 20.0, 10.0)) == expected
