"""Unit tests for the Qt-free 3D scene core (US-E6, #261; what survives of them since the
Qt 3D view's own contract — prisms, decal records, the scalar frame mapping — left with
that view in Phase 17 L1.10).

The light-direction gate from the issue: Berlin 2026-06-21 12:00 UTC →
sun vector (cos 59.29°·sin 203.74°, cos 59.29°·cos 203.74°, sin 59.29°) =
**(−0.2056, −0.4675, 0.8598)** (±0.001) in (E, N, up) — and its ground
projection must agree with the US-E3 shadow direction (the 2D overlay and
the 3D light can never disagree).
"""

from __future__ import annotations

import math

import pytest

from open_garden_planner.core.scene3d import (
    scene_to_engine_points,
    sun_direction_scene,
    triangulate_polygon,
)
from open_garden_planner.core.shadow_geometry import shadow_direction_scene
from open_garden_planner.core.solar import solar_position

SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
# Concave L-shape, area 3 * 50² = 7500.
L_SHAPE = [
    (0.0, 0.0), (100.0, 0.0), (100.0, 50.0),
    (50.0, 50.0), (50.0, 100.0), (0.0, 100.0),
]


def tri_area(a, b, c) -> float:
    return abs(
        (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    ) / 2.0


def triangulation_area(polygon) -> float:
    return sum(
        tri_area(polygon[i], polygon[j], polygon[k])
        for i, j, k in triangulate_polygon(polygon)
    )


class TestTriangulation:
    def test_square_two_triangles_full_area(self) -> None:
        triangles = triangulate_polygon(SQUARE)
        assert len(triangles) == 2
        assert triangulation_area(SQUARE) == pytest.approx(10000.0)

    def test_concave_l_shape(self) -> None:
        triangles = triangulate_polygon(L_SHAPE)
        assert len(triangles) == 4  # n−2 for a simple polygon
        assert triangulation_area(L_SHAPE) == pytest.approx(7500.0)

    def test_clockwise_input_normalized(self) -> None:
        assert triangulation_area(list(reversed(L_SHAPE))) == pytest.approx(7500.0)

    def test_degenerate_returns_empty(self) -> None:
        assert triangulate_polygon([(0.0, 0.0), (1.0, 1.0)]) == []


class TestSunLight:
    def test_berlin_june_noon_gate_vector(self) -> None:
        position = solar_position(
            52.52, 13.405, __import__("datetime").datetime(
                2026, 6, 21, 12, 0,
                tzinfo=__import__("datetime").UTC,
            ),
        )
        e, n, up = sun_direction_scene(
            position.elevation_deg, position.azimuth_deg
        )
        assert e == pytest.approx(-0.2056, abs=0.001)
        assert n == pytest.approx(-0.4675, abs=0.001)
        assert up == pytest.approx(0.8598, abs=0.001)

    def test_ground_projection_agrees_with_shadow_direction(self) -> None:
        """The 3D light and the 2D overlay can never disagree: the sun
        vector's ground projection is exactly opposite the shadow direction."""
        for azimuth in (51.3, 128.0, 203.74, 270.0):
            e, n, _up = sun_direction_scene(45.0, azimuth)
            dx, dy = shadow_direction_scene(azimuth)
            norm = math.hypot(e, n)
            assert e / norm == pytest.approx(-dx, abs=1e-9)
            assert n / norm == pytest.approx(-dy, abs=1e-9)

    def test_engine_frame_mapping(self) -> None:
        assert tuple(scene_to_engine_points([1.0, 2.0, 3.0])) == (1.0, 3.0, -2.0)
        # North (0,1,0) maps to −z; up stays y — one flip, applied once.
        assert tuple(scene_to_engine_points([0.0, 1.0, 0.0])) == (0.0, 0.0, -1.0)
