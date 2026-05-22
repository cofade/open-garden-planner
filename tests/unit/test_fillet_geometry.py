"""Unit tests for fillet corner geometry (Phase 13 Package B — US-B3)."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.cad_geometry import fillet_corner


def _approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


class TestFilletCornerRightAngle:
    """Reference case: right-angle corner at the origin, edges along ±X / +Y."""

    def test_right_angle_returns_arc_with_expected_geometry(self) -> None:
        """Edges P_prev=(100,0) → P_corner=(0,0) → P_next=(0,100), r=20.

        With α = 45°: tangent_in at (20, 0), tangent_out at (0, 20),
        arc center on the bisector at distance 20*sqrt(2)/sqrt(2) = 20*sqrt(2)
        — i.e. center = (20*sqrt(2)*cos(45°), 20*sqrt(2)*sin(45°)) = (20, 20).
        The arc subtends 90° (π - 2*45° = π/2).
        """
        result = fillet_corner(
            QPointF(100, 0), QPointF(0, 0), QPointF(0, 100), 20.0
        )
        assert result is not None
        tin, tout, center, _start_deg, span_deg = result
        assert _approx(tin.x(), 20.0)
        assert _approx(tin.y(), 0.0)
        assert _approx(tout.x(), 0.0)
        assert _approx(tout.y(), 20.0)
        assert _approx(center.x(), 20.0)
        assert _approx(center.y(), 20.0)
        # Sweep magnitude is 90° (the minor arc).
        assert _approx(abs(span_deg), 90.0)

    def test_tangent_points_at_correct_distance_along_edges(self) -> None:
        """tangent_in and tangent_out are at distance r/tan(α) from the corner."""
        result = fillet_corner(
            QPointF(100, 0), QPointF(0, 0), QPointF(0, 100), 30.0
        )
        assert result is not None
        tin, tout, _center, _, _ = result
        # α = 45°, tan(α) = 1, so edge_offset = r/tan(α) = 30
        assert _approx(math.hypot(tin.x(), tin.y()), 30.0)
        assert _approx(math.hypot(tout.x(), tout.y()), 30.0)

    def test_arc_center_equidistant_from_both_tangent_points(self) -> None:
        """The arc center is at distance r from both tangent points (it's the arc center)."""
        result = fillet_corner(
            QPointF(80, 0), QPointF(0, 0), QPointF(0, 80), 15.0
        )
        assert result is not None
        tin, tout, center, _, _ = result
        d_in = math.hypot(tin.x() - center.x(), tin.y() - center.y())
        d_out = math.hypot(tout.x() - center.x(), tout.y() - center.y())
        assert _approx(d_in, 15.0)
        assert _approx(d_out, 15.0)


class TestFilletCornerAngles:
    def test_acute_corner_produces_longer_sweep(self) -> None:
        """An acute corner (2α small) has a larger arc sweep (π - 2α large)."""
        # 60° corner — edges from corner at angles 0° and 60° (in math)
        cos60 = 0.5
        sin60 = math.sqrt(3) / 2
        p_prev = QPointF(100, 0)
        p_corner = QPointF(0, 0)
        p_next = QPointF(100 * cos60, 100 * sin60)
        result = fillet_corner(p_prev, p_corner, p_next, 10.0)
        assert result is not None
        _, _, _, _, span_deg = result
        # 2α = 60°, span = 180° - 60° = 120°.
        assert _approx(abs(span_deg), 120.0, tol=1e-4)

    def test_obtuse_corner_produces_shorter_sweep(self) -> None:
        """An obtuse corner (2α large) has a smaller arc sweep."""
        # 120° corner — edges from corner at 0° and 120°
        cos120 = -0.5
        sin120 = math.sqrt(3) / 2
        p_prev = QPointF(100, 0)
        p_corner = QPointF(0, 0)
        p_next = QPointF(100 * cos120, 100 * sin120)
        result = fillet_corner(p_prev, p_corner, p_next, 10.0)
        assert result is not None
        _, _, _, _, span_deg = result
        # 2α = 120°, span = 180° - 120° = 60°.
        assert _approx(abs(span_deg), 60.0, tol=1e-4)


class TestFilletCornerRejections:
    def test_collinear_corner_returns_none(self) -> None:
        """A 180° straight corner has no unique fillet — return None."""
        result = fillet_corner(
            QPointF(0, 0), QPointF(50, 0), QPointF(100, 0), 5.0
        )
        assert result is None

    def test_doubled_back_corner_returns_none(self) -> None:
        """A 0° doubled-back corner (edges overlap) is degenerate."""
        result = fillet_corner(
            QPointF(100, 0), QPointF(0, 0), QPointF(100, 0), 5.0
        )
        assert result is None

    def test_radius_too_large_returns_none(self) -> None:
        """Radius requires more cut-back than an adjacent edge allows."""
        # Right angle, edges 10 cm long; r=20 needs offset of 20 > 10.
        result = fillet_corner(
            QPointF(10, 0), QPointF(0, 0), QPointF(0, 10), 20.0
        )
        assert result is None

    def test_zero_or_negative_radius_returns_none(self) -> None:
        assert fillet_corner(
            QPointF(10, 0), QPointF(0, 0), QPointF(0, 10), 0.0
        ) is None
        assert fillet_corner(
            QPointF(10, 0), QPointF(0, 0), QPointF(0, 10), -5.0
        ) is None

    def test_zero_length_edge_returns_none(self) -> None:
        """If p_prev == p_corner the incoming edge is degenerate."""
        result = fillet_corner(
            QPointF(0, 0), QPointF(0, 0), QPointF(10, 10), 1.0
        )
        assert result is None


class TestFilletCornerArcContinuity:
    """Verify the arc is C¹-continuous: each tangent direction matches the edge."""

    def test_tangent_in_perpendicular_to_center_in(self) -> None:
        """At tangent_in, the line center→tangent_in is perpendicular to the edge."""
        result = fillet_corner(
            QPointF(100, 0), QPointF(0, 0), QPointF(0, 100), 25.0
        )
        assert result is not None
        tin, _, center, _, _ = result
        # Edge direction (from p_corner towards p_prev): (1, 0)
        edge_dx, edge_dy = 1.0, 0.0
        radial_dx = tin.x() - center.x()
        radial_dy = tin.y() - center.y()
        dot = edge_dx * radial_dx + edge_dy * radial_dy
        assert _approx(dot, 0.0, tol=1e-9)

    def test_tangent_out_perpendicular_to_center_out(self) -> None:
        """At tangent_out, the line center→tangent_out is perpendicular to that edge."""
        result = fillet_corner(
            QPointF(100, 0), QPointF(0, 0), QPointF(0, 100), 25.0
        )
        assert result is not None
        _, tout, center, _, _ = result
        edge_dx, edge_dy = 0.0, 1.0  # corner toward p_next
        radial_dx = tout.x() - center.x()
        radial_dy = tout.y() - center.y()
        dot = edge_dx * radial_dx + edge_dy * radial_dy
        assert _approx(dot, 0.0, tol=1e-9)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
