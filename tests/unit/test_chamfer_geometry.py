"""Unit tests for chamfer corner geometry (Phase 13 Package B — US-B3)."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.cad_geometry import chamfer_corner


def _approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


class TestChamferCornerBasic:
    def test_right_angle_distance(self) -> None:
        """Right-angle corner, d=15 → cut points at (15,0) and (0,15)."""
        result = chamfer_corner(
            QPointF(100, 0), QPointF(0, 0), QPointF(0, 100), 15.0
        )
        assert result is not None
        cut_in, cut_out = result
        assert _approx(cut_in.x(), 15.0)
        assert _approx(cut_in.y(), 0.0)
        assert _approx(cut_out.x(), 0.0)
        assert _approx(cut_out.y(), 15.0)

    def test_acute_corner(self) -> None:
        """60° corner: cut points at distance d along each edge."""
        cos60 = 0.5
        sin60 = math.sqrt(3) / 2
        result = chamfer_corner(
            QPointF(100, 0),
            QPointF(0, 0),
            QPointF(100 * cos60, 100 * sin60),
            20.0,
        )
        assert result is not None
        cut_in, cut_out = result
        assert _approx(math.hypot(cut_in.x(), cut_in.y()), 20.0)
        assert _approx(math.hypot(cut_out.x(), cut_out.y()), 20.0)

    def test_cut_points_lie_on_their_edges(self) -> None:
        """cut_in must be on the prev edge; cut_out on the next edge."""
        result = chamfer_corner(
            QPointF(80, 0), QPointF(0, 0), QPointF(0, 60), 10.0
        )
        assert result is not None
        cut_in, cut_out = result
        # cut_in is along the +x edge from the corner: y must be ~0.
        assert _approx(cut_in.y(), 0.0)
        # cut_out is along the +y edge: x must be ~0.
        assert _approx(cut_out.x(), 0.0)


class TestChamferCornerRejections:
    def test_zero_or_negative_distance(self) -> None:
        assert chamfer_corner(
            QPointF(10, 0), QPointF(0, 0), QPointF(0, 10), 0.0
        ) is None
        assert chamfer_corner(
            QPointF(10, 0), QPointF(0, 0), QPointF(0, 10), -3.0
        ) is None

    def test_distance_longer_than_edge(self) -> None:
        """Edges 10 cm; chamfer distance 15 cm is impossible."""
        result = chamfer_corner(
            QPointF(10, 0), QPointF(0, 0), QPointF(0, 10), 15.0
        )
        assert result is None

    def test_zero_length_edge_returns_none(self) -> None:
        result = chamfer_corner(
            QPointF(0, 0), QPointF(0, 0), QPointF(10, 10), 1.0
        )
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
