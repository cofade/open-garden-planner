"""Unit tests for the Qt-free 3D scene core (US-E6, #261).

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
    FLAT_THICKNESS_CM,
    extrude_footprint,
    records_from_raw,
    sun_direction_scene,
    to_engine_frame,
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


class TestExtrusion:
    def test_square_prism_vertex_counts(self) -> None:
        positions, normals = extrude_footprint(SQUARE, 250.0)
        # 4 side quads × 6 verts + 2 cap triangles × 3 verts = 30 vertices.
        assert len(positions) == 30 * 3
        assert len(normals) == len(positions)

    def test_heights_and_normals(self) -> None:
        positions, normals = extrude_footprint(SQUARE, 250.0)
        zs = positions[2::3]
        assert min(zs) == 0.0
        assert max(zs) == 250.0
        # Cap normals point up; side normals are horizontal unit vectors.
        cap_normals = normals[-18:]
        assert cap_normals[2::3] == [1.0] * 6
        for i in range(0, len(normals) - 18, 3):
            nx, ny, nz = normals[i], normals[i + 1], normals[i + 2]
            assert nz == 0.0
            assert math.hypot(nx, ny) == pytest.approx(1.0)

    def test_side_normals_point_outward(self) -> None:
        positions, normals = extrude_footprint(SQUARE, 100.0)
        # For each side vertex, moving along its normal must leave the
        # footprint's bounding box center behind (outward test).
        cx, cy = 50.0, 50.0
        for i in range(0, len(positions) - 18, 3):
            px, py = positions[i], positions[i + 1]
            nx, ny = normals[i], normals[i + 1]
            assert (px + nx - cx) ** 2 + (py + ny - cy) ** 2 > (
                px - cx
            ) ** 2 + (py - cy) ** 2

    def test_concave_l_shape_prism(self) -> None:
        """Exercise the concave extrusion path (per-edge side quads +
        ear-clipped cap) end-to-end, not just triangulate_polygon alone."""
        positions, normals = extrude_footprint(L_SHAPE, 200.0)
        # 6 side quads × 6 verts + 4 cap triangles × 3 verts = 48 vertices.
        assert len(positions) == 48 * 3
        assert len(normals) == len(positions)
        zs = positions[2::3]
        assert min(zs) == 0.0
        assert max(zs) == 200.0
        # Top cap = last 4 triangles (12 verts); their normals point up.
        cap_normals = normals[-12 * 3:]
        assert cap_normals[2::3] == [1.0] * 12
        # Every side normal is a horizontal unit vector.
        side_n = normals[: -12 * 3]
        for i in range(0, len(side_n), 3):
            nx, ny, nz = side_n[i], side_n[i + 1], side_n[i + 2]
            assert nz == 0.0
            assert math.hypot(nx, ny) == pytest.approx(1.0)

    def test_degenerate_inputs(self) -> None:
        assert extrude_footprint([(0.0, 0.0), (1.0, 0.0)], 100.0) == ([], [])
        assert extrude_footprint(SQUARE, 0.0) == ([], [])


class TestRecords:
    def test_heights_map_to_kinds(self) -> None:
        records = records_from_raw(
            [
                {"footprint": SQUARE, "height_cm": 450.0, "name": "house",
                 "color_rgba": (200, 100, 50, 255)},
                {"footprint": SQUARE, "height_cm": None, "name": "lawn"},
                {"footprint": [(0, 0), (1, 1)], "height_cm": 100.0,
                 "name": "degenerate"},
            ]
        )
        assert len(records) == 2  # degenerate dropped
        assert records[0].kind == "extruded"
        assert records[0].height_cm == 450.0
        assert records[0].color_rgba == (200, 100, 50, 255)
        assert records[1].kind == "flat"
        assert records[1].height_cm == FLAT_THICKNESS_CM


class TestDecalStacking:
    def test_decals_lift_and_step_extruded_on_ground(self) -> None:
        from open_garden_planner.core.scene3d import (
            DECAL_LIFT_CM,
            DECAL_STACK_STEP_CM,
        )

        records = records_from_raw(
            [
                {"footprint": SQUARE, "height_cm": None, "name": "lawn",
                 "color_rgba": (0, 128, 0, 255)},       # bottom decal
                {"footprint": SQUARE, "height_cm": None, "name": "path",
                 "color_rgba": (128, 128, 128, 255)},   # next decal up
                {"footprint": SQUARE, "height_cm": 300.0, "name": "wall",
                 "color_rgba": (200, 200, 200, 255)},   # extruded object
            ]
        )
        assert records[0].base_cm == pytest.approx(DECAL_LIFT_CM)
        assert records[1].base_cm == pytest.approx(
            DECAL_LIFT_CM + DECAL_STACK_STEP_CM
        )
        assert records[2].base_cm == 0.0  # extruded sits on the ground

    def test_lift_is_capped_for_many_decals(self) -> None:
        from open_garden_planner.core.scene3d import DECAL_MAX_LIFT_CM

        records = records_from_raw(
            [{"footprint": SQUARE, "height_cm": None, "name": f"d{i}"}
             for i in range(40)]
        )
        assert all(r.base_cm <= DECAL_MAX_LIFT_CM for r in records)
        assert records[-1].base_cm == pytest.approx(DECAL_MAX_LIFT_CM)

    def test_base_cm_lifts_the_geometry(self) -> None:
        positions, _ = extrude_footprint(SQUARE, 2.0, base_cm=5.0)
        zs = positions[2::3]
        assert min(zs) == pytest.approx(5.0)
        assert max(zs) == pytest.approx(7.0)


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
        assert to_engine_frame(1.0, 2.0, 3.0) == (1.0, 3.0, -2.0)
        # North (0,1,0) maps to −z; up stays y — one flip, applied once.
        assert to_engine_frame(0.0, 1.0, 0.0) == (0.0, 0.0, -1.0)
