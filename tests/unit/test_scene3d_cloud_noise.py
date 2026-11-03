"""The atmosphere sky's cloud noise volume (Phase 17 L7, #391): a port of Qt's
skymaterial example's ``CloudNoiseTextureData`` (qtquick3d v6.12.0).

The oracle is a SCALAR transcription of the C++ — its loops, per voxel, in plain
Python ints and floats with explicit 32-bit wrapping — so the vectorised port is
checked against the example's own procedure, not against itself.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from open_garden_planner.core.scene3d import cloud_noise
from open_garden_planner.core.scene3d.cloud_noise import SIZE, cloud_noise_rgba, cloud_noise_rgba16f

_M32 = 0xFFFFFFFF


def _hash_cell(x: int, y: int, z: int, salt: int = 0) -> int:
    """``hashCell``, uint32_t arithmetic by hand."""
    h = ((x * 73856093) & _M32) ^ ((y * 19349663) & _M32) ^ ((z * 83492791) & _M32) ^ (salt & _M32)
    h ^= h >> 13
    h = (h * 0x5BD1E995) & _M32
    h ^= h >> 15
    return h


def _hash_float(x: int, y: int, z: int, salt: int = 0) -> float:
    return (_hash_cell(x, y, z, salt) & 0xFFFFFF) / float(0xFFFFFF)


def _wrap(v: int, period: int) -> int:
    r = v % period
    return r + period if r < 0 else r


def _value_noise(u: float, v: float, w: float, period: int) -> float:
    x, y, z = u * period, v * period, w * period
    x0, y0, z0 = (_wrap(math.floor(c), period) for c in (x, y, z))
    x1, y1, z1 = _wrap(x0 + 1, period), _wrap(y0 + 1, period), _wrap(z0 + 1, period)
    fx, fy, fz = x - math.floor(x), y - math.floor(y), z - math.floor(z)
    sx, sy, sz = (f * f * (3.0 - 2.0 * f) for f in (fx, fy, fz))

    def lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    n = _hash_float
    return lerp(lerp(lerp(n(x0, y0, z0), n(x1, y0, z0), sx), lerp(n(x0, y1, z0), n(x1, y1, z0), sx), sy),
                lerp(lerp(n(x0, y0, z1), n(x1, y0, z1), sx), lerp(n(x0, y1, z1), n(x1, y1, z1), sx), sy),
                sz)


def _perlin_fbm(u: float, v: float, w: float, base: int, octaves: int) -> float:
    value, amp, total, period = 0.0, 0.5, 0.0, base
    for _ in range(octaves):
        value += amp * _value_noise(u, v, w, period)
        total += amp
        period *= 2
        amp *= 0.5
    return value / total


def _worley(u: float, v: float, w: float, grid: int, salt: int) -> float:
    x, y, z = u * grid, v * grid, w * grid
    cx, cy, cz = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = x - cx, y - cy, z - cz
    best = 3.0
    for dz in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nx, ny, nz = _wrap(cx + dx, grid), _wrap(cy + dy, grid), _wrap(cz + dz, grid)
                px = _hash_float(nx, ny, nz, salt + 0xA1)
                py = _hash_float(nx, ny, nz, salt + 0xB2)
                pz = _hash_float(nx, ny, nz, salt + 0xC3)
                d = (dx + px - fx) ** 2 + (dy + py - fy) ** 2 + (dz + pz - fz) ** 2
                best = min(best, d)
    return min(math.sqrt(best) / 0.7, 1.0)


def _inv_worley_fbm(u: float, v: float, w: float, grid: int, salt: int) -> float:
    return (0.625 * (1.0 - _worley(u, v, w, grid, salt + 0x010))
            + 0.25 * (1.0 - _worley(u, v, w, grid * 2, salt + 0x020))
            + 0.125 * (1.0 - _worley(u, v, w, grid * 4, salt + 0x030)))


def _voxel(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """One voxel exactly as the C++ constructor's loop body computes it."""
    u, v, w = x / SIZE, y / SIZE, z / SIZE
    pfbm = abs(_perlin_fbm(u, v, w, 4, 4) * 2.0 - 1.0)
    wfbm = _inv_worley_fbm(u, v, w, 6, 0x100)
    r = wfbm + (pfbm - 0.0) / (1.0 - 0.0) * (1.0 - wfbm)
    g = _inv_worley_fbm(u, v, w, 6, 0x200)
    b = _inv_worley_fbm(u, v, w, 10, 0x300)
    a = _inv_worley_fbm(u, v, w, 16, 0x400)
    return tuple(min(max(c, 0.0), 1.0) for c in (r, g, b, a))  # type: ignore[return-value]


def test_the_vectorised_hash_wraps_like_uint32() -> None:
    """Large cell indices overflow 32 bits in the C++ multiply; the port must wrap."""
    for x, y, z, salt in ((0, 0, 0, 0), (63, 1, 17, 0x1A1), (40000, 70000, 123456, 0x4C3),
                          (64, 64, 64, 0xFFFFFFFF)):
        got = cloud_noise._hash(np.array([x]), np.array([y]), np.array([z]), salt)[0]
        assert got == _hash_float(x, y, z, salt)


@pytest.mark.parametrize("voxel", [(0, 0, 0), (63, 63, 63), (5, 40, 22), (31, 0, 63), (17, 9, 48)])
def test_voxels_match_the_examples_scalar_recipe(voxel: tuple[int, int, int]) -> None:
    x, y, z = voxel
    volume = cloud_noise_rgba()
    assert volume[z, y, x] == pytest.approx(_voxel(x, y, z), abs=1e-12)


def test_the_volume_is_rgba_64_cubed_in_the_examples_memory_order_and_read_only() -> None:
    volume = cloud_noise_rgba()
    assert volume.shape == (SIZE, SIZE, SIZE, 4) and SIZE == 64
    assert not volume.flags.writeable
    assert float(volume.min()) >= 0.0 and float(volume.max()) <= 1.0
    data = cloud_noise_rgba16f()
    assert len(data) == SIZE ** 3 * 4 * 2, "RGBA16F: two bytes a channel"
    halves = np.frombuffer(data, dtype="<f2").reshape(SIZE, SIZE, SIZE, 4)
    assert np.allclose(halves, volume, atol=1e-3), "z slices of y rows of x, as the C++ writes"


def test_the_volume_tiles_in_every_axis() -> None:
    """Tileable (the shader repeats it): the step across the wrap is like any other step."""
    volume = cloud_noise_rgba()
    for axis in range(3):
        inside = float(np.abs(np.diff(volume, axis=axis)).mean())
        across = float(np.abs(np.take(volume, 0, axis=axis) - np.take(volume, -1, axis=axis)).mean())
        assert across < 1.25 * inside, (axis, inside, across)


def test_the_channels_are_the_recipes_and_are_not_flat() -> None:
    """R (Perlin-Worley) is the brightest; G, B, A are finer and finer Worley FBM."""
    volume = cloud_noise_rgba()
    means = volume.reshape(-1, 4).mean(axis=0)
    assert means[0] > means[1] and all(0.15 < m < 0.6 for m in means), means
    stds = volume.reshape(-1, 4).std(axis=0)
    assert all(s > 0.05 for s in stds), stds
    # higher frequency: neighbouring voxels differ more
    steps = [float(np.abs(np.diff(volume[..., c], axis=2)).mean()) for c in (1, 2, 3)]
    assert steps[0] < steps[1] < steps[2], steps


def test_the_volume_is_deterministic() -> None:
    cloud_noise_rgba.cache_clear()
    cloud_noise_rgba16f.cache_clear()
    first = cloud_noise_rgba16f()
    cloud_noise_rgba.cache_clear()
    cloud_noise_rgba16f.cache_clear()
    assert cloud_noise_rgba16f() == first
