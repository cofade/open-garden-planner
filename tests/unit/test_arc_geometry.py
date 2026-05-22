"""Unit tests for Phase 13 Package B — 3-point arc geometry (US-B2)."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.cad_geometry import arc_from_three_points


def _approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


class TestArcFromThreePoints:
    def test_collinear_returns_none(self) -> None:
        """Three collinear points produce no unique circle — caller falls back to a line."""
        p1 = QPointF(0, 0)
        p2 = QPointF(50, 0)
        p3 = QPointF(100, 0)
        assert arc_from_three_points(p1, p2, p3) is None

    def test_near_collinear_within_tolerance_returns_none(self) -> None:
        """A through-point offset by 0.001 cm from the chord is treated as collinear."""
        p1 = QPointF(0, 0)
        p2 = QPointF(50, 0.001)
        p3 = QPointF(100, 0)
        assert arc_from_three_points(p1, p2, p3) is None

    def test_just_outside_tolerance_returns_arc(self) -> None:
        """A clearly curved input produces an arc.

        Center sits on the perpendicular bisector of the chord, and on the
        OPPOSITE side of the chord from the through-point (geometry of a
        circle passing through three points: center is equidistant from
        all three, so it must be on the far side of the chord midpoint).
        """
        p1 = QPointF(0, 0)
        p2 = QPointF(50, 5)
        p3 = QPointF(100, 0)
        result = arc_from_three_points(p1, p2, p3)
        assert result is not None
        center, radius, _, _ = result
        # Center on the perpendicular bisector of the chord.
        assert _approx(center.x(), 50.0, tol=1e-4)
        # Opposite side of the chord from the through-point.
        assert center.y() < 0
        # Radius matches the known geometric solution for this triple.
        # chord = 100, sagitta = 5 -> radius = (chord^2/4 + sagitta^2)/(2*sagitta)
        expected = (100 * 100 / 4.0 + 5 * 5) / (2.0 * 5)
        assert _approx(radius, expected, tol=1e-4)

    def test_semicircle_through_top(self) -> None:
        """An arc through (-r, 0), (0, r), (r, 0) is a semicircle centered at origin."""
        p1 = QPointF(-100, 0)
        p2 = QPointF(0, 100)
        p3 = QPointF(100, 0)
        result = arc_from_three_points(p1, p2, p3)
        assert result is not None
        center, radius, start_deg, span_deg = result
        assert _approx(center.x(), 0.0, tol=1e-6)
        assert _approx(center.y(), 0.0, tol=1e-6)
        assert _approx(radius, 100.0, tol=1e-6)
        # start at p1: atan2(0, -100) = 180°
        assert _approx(abs(start_deg), 180.0, tol=1e-6)
        # Sweep is 180° (semicircle); sign depends on winding.
        assert _approx(abs(span_deg), 180.0, tol=1e-6)

    def test_arc_passes_through_all_three_points(self) -> None:
        """Every input point must lie on the resulting circle (radius * 2).

        Three arbitrary non-collinear points; verify each is equidistant
        from the returned center to within numerical tolerance.
        """
        cases = [
            (QPointF(0, 0), QPointF(30, 40), QPointF(60, 0)),
            (QPointF(10, 10), QPointF(25, 35), QPointF(80, 5)),
            (QPointF(-50, 0), QPointF(0, 30), QPointF(40, 0)),
        ]
        for p1, p2, p3 in cases:
            result = arc_from_three_points(p1, p2, p3)
            assert result is not None
            center, radius, _, _ = result
            for p in (p1, p2, p3):
                d = math.hypot(p.x() - center.x(), p.y() - center.y())
                assert _approx(d, radius, tol=1e-4), (
                    f"point ({p.x()}, {p.y()}) not on arc: distance {d} vs radius {radius}"
                )

    def test_through_point_selects_sweep_direction(self) -> None:
        """Swapping the through-point picks the opposite arc between the same endpoints."""
        p1 = QPointF(-100, 0)
        p3 = QPointF(100, 0)
        # Through-point above the chord -> arc bulges up.
        up = arc_from_three_points(p1, QPointF(0, 100), p3)
        # Through-point below the chord -> arc bulges down (opposite sweep).
        down = arc_from_three_points(p1, QPointF(0, -100), p3)
        assert up is not None
        assert down is not None
        # Spans have opposite signs.
        assert up[3] * down[3] < 0

    def test_span_is_never_zero(self) -> None:
        """A genuine arc has non-zero span."""
        result = arc_from_three_points(
            QPointF(0, 0), QPointF(50, 10), QPointF(100, 0)
        )
        assert result is not None
        _, _, _, span_deg = result
        assert abs(span_deg) > 1e-3

    def test_span_magnitude_in_range(self) -> None:
        """Span magnitude is strictly between 0 and 360 degrees (no overflow)."""
        result = arc_from_three_points(
            QPointF(0, 0), QPointF(50, 50), QPointF(100, 0)
        )
        assert result is not None
        _, _, _, span_deg = result
        assert 0 < abs(span_deg) < 360


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
