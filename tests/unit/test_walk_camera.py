"""Unit tests for the Qt-free walk-camera math (US-E7, #262)."""

from __future__ import annotations

import math

import pytest

from open_garden_planner.core.walk_camera import (
    BOUNDS_MARGIN_CM,
    EYE_HEIGHT_CM,
    PITCH_LIMIT_DEG,
    clamp_walk_position,
    look_direction,
)


class TestClamp:
    def test_inside_positions_unchanged(self) -> None:
        assert clamp_walk_position(500.0, 300.0, 1000.0, 800.0) == (500.0, 300.0)

    def test_outside_clamps_to_bounds_plus_margin(self) -> None:
        east, north = clamp_walk_position(-9999.0, 99999.0, 1000.0, 800.0)
        assert east == -BOUNDS_MARGIN_CM
        assert north == 800.0 + BOUNDS_MARGIN_CM

    def test_margin_is_walkable(self) -> None:
        east, north = clamp_walk_position(-50.0, -50.0, 1000.0, 800.0)
        assert (east, north) == (-50.0, -50.0)

    def test_eye_height_constant(self) -> None:
        # One named constant, not configurable in the MVP (FR-SUN-07).
        assert EYE_HEIGHT_CM == 165.0


class TestLookDirection:
    def test_north_and_east(self) -> None:
        assert look_direction(0.0, 0.0) == pytest.approx((0.0, 1.0, 0.0))
        east_vec = look_direction(90.0, 0.0)
        assert east_vec[0] == pytest.approx(1.0)
        assert east_vec[1] == pytest.approx(0.0, abs=1e-12)

    def test_unit_length_everywhere(self) -> None:
        for yaw in (0.0, 37.0, 180.0, 271.5):
            for pitch in (-89.0, -45.0, 0.0, 45.0, 89.0):
                vec = look_direction(yaw, pitch)
                assert math.hypot(*vec) == pytest.approx(1.0)

    def test_pitch_clamped_no_gimbal_flip(self) -> None:
        # Beyond ±89° the vector must be identical to the limit — never
        # flipped over the zenith.
        assert look_direction(45.0, 200.0) == look_direction(45.0, PITCH_LIMIT_DEG)
        assert look_direction(45.0, -95.0) == look_direction(
            45.0, -PITCH_LIMIT_DEG
        )
        up = look_direction(0.0, 89.0)[2]
        assert up == pytest.approx(math.sin(math.radians(89.0)))

    def test_horizontal_component_never_vanishes(self) -> None:
        # At the pitch limit a sliver of horizontal direction survives, so
        # "forward" stays defined (stability at the limits).
        east, north, _up = look_direction(0.0, PITCH_LIMIT_DEG)
        assert math.hypot(east, north) > 0.01
