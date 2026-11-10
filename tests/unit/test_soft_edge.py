"""The arithmetic of the shadow feather: a falloff, not bands (#793).

``core.soft_edge`` turns the raster of a shade into how dark the ground beside
it is. These tests are Qt-free; the painted result is measured in
``tests/integration/test_shadow_feather.py``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from open_garden_planner.core.soft_edge import (
    BLUR_PASSES,
    FEATHER_REACH_CM,
    MAX_BLUR_RADIUS,
    MAX_WEIGHT,
    MIN_CELL_PX,
    MIN_REACH_PX,
    blur_full_scale,
    box_blur,
    box_sums,
    falloff_lut,
    feather_grid,
    feather_weight,
)


def _half_plane(cells: int, angle_deg: float, cell_cm: float) -> tuple[np.ndarray, np.ndarray]:
    """Coverage bytes of a half plane through the field's centre, and each
    cell centre's distance outside it in centimetres (negative: inside)."""
    turn = math.radians(angle_deg)
    normal = (math.cos(turn), math.sin(turn))
    fine = 8
    axis = (np.arange(cells * fine) + 0.5) / fine - cells / 2
    x, y = np.meshgrid(axis, axis)
    inside = (x * normal[0] + y * normal[1]) <= 0
    coverage = inside.reshape(cells, fine, cells, fine).mean(axis=(1, 3))
    centre = (np.arange(cells) + 0.5) - cells / 2
    cx, cy = np.meshgrid(centre, centre)
    return (
        (coverage * 255 + 0.5).astype(np.uint8),
        (cx * normal[0] + cy * normal[1]) * cell_cm,
    )


class TestLattice:
    def test_no_falloff_where_it_would_be_under_a_pixel_and_a_half(self) -> None:
        assert feather_grid(MIN_REACH_PX / FEATHER_REACH_CM * 0.99) is None
        assert feather_grid(MIN_REACH_PX / FEATHER_REACH_CM * 1.01) is not None

    @pytest.mark.parametrize("scale", [0.0, -1.0, math.inf, math.nan])
    def test_a_scale_that_is_no_scale_has_no_lattice(self, scale: float) -> None:
        assert feather_grid(scale) is None

    @pytest.mark.parametrize("scale", [0.25, 0.47, 1.0, 1.18, 2.0, 3.0])
    def test_zoomed_out_a_cell_is_two_device_pixels(self, scale: float) -> None:
        grid = feather_grid(scale)
        assert grid is not None
        assert grid.cell_cm * scale == pytest.approx(MIN_CELL_PX)

    @pytest.mark.parametrize("scale", [4.0, 10.0, 50.0])
    def test_zoomed_in_the_reach_has_twelve_cells(self, scale: float) -> None:
        grid = feather_grid(scale)
        assert grid is not None
        assert grid.radius == MAX_BLUR_RADIUS
        assert FEATHER_REACH_CM / grid.cell_cm == pytest.approx(BLUR_PASSES * MAX_BLUR_RADIUS + 0.5)

    @pytest.mark.parametrize("scale", [0.22, 0.47, 1.0, 2.0, 3.4, 4.0, 10.0, 50.0])
    def test_the_blur_never_ends_before_the_falloff_does(self, scale: float) -> None:
        grid = feather_grid(scale)
        assert grid is not None
        assert (BLUR_PASSES * grid.radius + 0.5) * grid.cell_cm >= FEATHER_REACH_CM - 1e-9

    def test_a_coarser_lattice_still_spans_the_reach(self) -> None:
        grid = feather_grid(10.0)
        assert grid is not None
        coarse = grid.coarser(3.0)
        assert coarse.cell_cm == pytest.approx(3.0 * grid.cell_cm)
        assert (BLUR_PASSES * coarse.radius + 0.5) * coarse.cell_cm >= FEATHER_REACH_CM


class TestBoxSums:
    def test_a_full_field_sums_to_full_scale_in_its_middle(self) -> None:
        field = np.full((60, 60), 255, dtype=np.uint8)
        for radius in (1, 3, MAX_BLUR_RADIUS):
            sums = box_sums(field, radius)
            assert sums[30, 30] == blur_full_scale(radius)

    def test_outside_the_field_counts_as_nothing(self) -> None:
        field = np.full((40, 40), 255, dtype=np.uint8)
        blurred = box_blur(field, 2)
        assert blurred[0, 0] < 0.5 < blurred[20, 20] == pytest.approx(1.0)

    def test_the_sums_are_exact_although_the_running_sums_wrap(self) -> None:
        """A field this large takes the 32-bit running sums past 2**32."""
        rng = np.random.default_rng(7)
        field = rng.integers(0, 256, size=(700, 900), dtype=np.uint8)
        radius = MAX_BLUR_RADIUS
        width = 2 * radius + 1
        exact = field.astype(np.int64)
        for _ in range(BLUR_PASSES):
            for axis in (0, 1):
                pad = [(radius, radius), (0, 0)] if axis == 0 else [(0, 0), (radius, radius)]
                padded = np.pad(exact, pad)
                exact = sum(
                    padded[k: k + exact.shape[0], :] if axis == 0 else padded[:, k: k + exact.shape[1]]
                    for k in range(width)
                )
        assert np.array_equal(box_sums(field, radius).astype(np.int64), exact)

    def test_only_bytes_are_summed(self) -> None:
        with pytest.raises(TypeError):
            box_sums(np.zeros((4, 4), dtype=np.float32), 1)


class TestFalloff:
    @pytest.mark.parametrize("scale", [0.47, 1.0, 2.0, 4.0, 10.0])
    def test_beside_an_upright_edge_it_is_linear_from_the_shade_to_nothing(self, scale: float) -> None:
        grid = feather_grid(scale)
        assert grid is not None
        coverage, distance = _half_plane(96, 0.0, grid.cell_cm)
        weight = feather_weight(coverage, grid)
        middle = slice(24, 72)
        outside = distance[middle, middle] > 0
        wanted = np.clip(1.0 - distance / FEATHER_REACH_CM, 0.0, 1.0)
        error = np.abs(weight[middle, middle] - wanted[middle, middle])[outside]
        assert error.max() < 0.01

    @pytest.mark.parametrize("angle", [15.0, 30.0, 45.0, 60.0])
    def test_beside_a_slanted_edge_it_is_the_same_falloff(self, angle: float) -> None:
        grid = feather_grid(10.0)
        assert grid is not None
        coverage, distance = _half_plane(96, angle, grid.cell_cm)
        weight = feather_weight(coverage, grid)
        middle = slice(24, 72)
        outside = distance[middle, middle] > 0
        wanted = np.clip(1.0 - distance / FEATHER_REACH_CM, 0.0, 1.0)
        error = np.abs(weight[middle, middle] - wanted[middle, middle])[outside]
        assert error.max() < 0.09   # measured 0.079 at 45 degrees: wider there, never banded

    def test_it_is_nothing_beyond_the_reach(self) -> None:
        grid = feather_grid(10.0)
        assert grid is not None
        coverage, distance = _half_plane(96, 0.0, grid.cell_cm)
        weight = feather_weight(coverage, grid)
        assert not weight[distance > FEATHER_REACH_CM + grid.cell_cm].any()

    def test_it_goes_on_rising_inside_the_shade(self) -> None:
        """What the enlargement interpolates from just outside the edge."""
        grid = feather_grid(10.0)
        assert grid is not None
        lut = falloff_lut(grid)
        assert lut[0] == 0.0
        assert lut[len(lut) // 2] == pytest.approx(1.0, abs=0.01)
        assert lut[-1] == pytest.approx(MAX_WEIGHT)
        assert (np.diff(lut) >= 0).all()

    def test_beside_a_light_shade_it_starts_at_that_shades_tone(self) -> None:
        grid = feather_grid(10.0)
        assert grid is not None
        coverage, distance = _half_plane(96, 0.0, grid.cell_cm)
        light = (coverage.astype(np.float32) * 0.3 + 0.5).astype(np.uint8)
        solid = feather_weight(coverage, grid)
        weighted = feather_weight(coverage, grid, light)
        just_outside = (distance > 0.5) & (distance < 2.0)
        ratio = weighted[just_outside] / solid[just_outside]
        assert ratio == pytest.approx(0.3, abs=0.02)

    def test_two_shades_of_different_tone_each_keep_their_own_edge(self) -> None:
        """A solid's edge is not worn by the light shade beside it (#698)."""
        grid = feather_grid(10.0)
        assert grid is not None
        cells = 120
        coverage = np.zeros((cells, cells), dtype=np.uint8)
        strength = np.zeros((cells, cells), dtype=np.uint8)
        coverage[20:100, 20:50] = 255
        strength[20:100, 20:50] = 255             # solid, its edge at column 50
        coverage[20:100, 80:110] = 255
        strength[20:100, 80:110] = 64             # light, its edge at column 80
        weight = feather_weight(coverage, grid, strength)
        beside_solid = weight[60, 51]
        beside_light = weight[60, 78]
        assert beside_solid == pytest.approx(1.0 - 1.5 * grid.cell_cm / FEATHER_REACH_CM, abs=0.03)
        assert beside_light == pytest.approx(beside_solid * 64 / 255, abs=0.03)
