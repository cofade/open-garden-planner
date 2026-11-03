"""The cloud noise volume of the atmosphere sky (Phase 17 L7, #391, ADR-048). Qt-free.

A numpy port of ``CloudNoiseTextureData`` from Qt's ``skymaterial`` example
(qtquick3d v6.12.0, ``examples/quick3d/skymaterial/cloudnoisetexturedata.cpp``,
Copyright (C) 2026 The Qt Company Ltd., BSD-3-Clause; provenance and licence text in
``ui/view3d/quick3d/qml/PROVENANCE.md`` and ``LICENSE-qt-skymaterial.txt``). The
recipe is Schneider's, "Real-time Volumetric Cloudscapes of Horizon Zero Dawn"
(GPU Pro 7): a ``SIZE``³ RGBA volume, tileable in all three axes —

- R: Perlin-Worley — a value-noise FBM folded (``|p·2 − 1|``) and remapped over an
  inverted Worley FBM: the clouds' base shape;
- G, B, A: inverted Worley FBM at three rising frequencies: the edges' detail.

The same hash, the same octaves, the same salts as the C++ — the volume is the
example's, computed in float64 instead of float32 (the texture is float16, so the two
differ by rounding at most). Deterministic: the same bytes on every run.

The C++ loops per voxel; this port vectorises per neighbour cell and uses that every
coordinate of a voxel depends on ONE axis (``u`` on x, ``v`` on y, ``w`` on z), so the
cell and the fraction are 64-element vectors and only the hash lookups are 3D.
"""

from __future__ import annotations

from functools import cache
from typing import Final

import numpy as np
from numpy.typing import NDArray

__all__ = ["SIZE", "cloud_noise_rgba", "cloud_noise_rgba16f"]

#: Voxels per axis (the example's ``kSize``).
SIZE: Final = 64

_MASK24: Final = 0xFFFFFF


def _hash(x: NDArray[np.int64], y: NDArray[np.int64], z: NDArray[np.int64],
          salt: int) -> NDArray[np.float64]:
    """``hashCellFloat``: the example's integer hash of a cell, as a float in [0, 1].

    uint32 arithmetic that wraps exactly as C++ ``uint32_t`` does: ``x·73856093 ^
    y·19349663 ^ z·83492791 ^ salt``, then ``h ^= h >> 13; h *= 0x5bd1e995;
    h ^= h >> 15``, then the low 24 bits over 0xFFFFFF.
    """
    with np.errstate(over="ignore"):
        h = ((x.astype(np.uint32) * np.uint32(73856093))
             ^ (y.astype(np.uint32) * np.uint32(19349663))
             ^ (z.astype(np.uint32) * np.uint32(83492791))
             ^ np.uint32(salt & 0xFFFFFFFF))
        h ^= h >> np.uint32(13)
        h *= np.uint32(0x5BD1E995)
        h ^= h >> np.uint32(15)
    result: NDArray[np.float64] = (h & np.uint32(_MASK24)).astype(np.float64) / float(_MASK24)
    return result


def _axis(size: int) -> NDArray[np.float64]:
    """The texel coordinates of one axis: ``i / size`` (the example's ``u``, ``v``, ``w``)."""
    return np.arange(size, dtype=np.float64) / float(size)


def _value_noise(period: int, size: int) -> NDArray[np.float64]:
    """``valueNoise3T``: tileable trilinear value noise over ``period`` cells, smoothstepped."""
    coordinate = _axis(size) * period
    low = np.floor(coordinate)
    fraction = coordinate - low
    smooth = fraction * fraction * (3.0 - 2.0 * fraction)
    c0 = np.mod(low.astype(np.int64), period)
    c1 = np.mod(c0 + 1, period)
    z0, y0, x0 = (c0[:, None, None], c0[None, :, None], c0[None, None, :])
    z1, y1, x1 = (c1[:, None, None], c1[None, :, None], c1[None, None, :])
    sz, sy, sx = (smooth[:, None, None], smooth[None, :, None], smooth[None, None, :])

    def lerp(a: NDArray[np.float64], b: NDArray[np.float64], t: NDArray[np.float64]
             ) -> NDArray[np.float64]:
        return a + (b - a) * t

    bottom = lerp(lerp(_hash(x0, y0, z0, 0), _hash(x1, y0, z0, 0), sx),
                  lerp(_hash(x0, y1, z0, 0), _hash(x1, y1, z0, 0), sx), sy)
    top = lerp(lerp(_hash(x0, y0, z1, 0), _hash(x1, y0, z1, 0), sx),
               lerp(_hash(x0, y1, z1, 0), _hash(x1, y1, z1, 0), sx), sy)
    return lerp(bottom, top, sz)


def _perlin_fbm(base_period: int, octaves: int, size: int) -> NDArray[np.float64]:
    """``perlinFbm3T``: ``octaves`` of value noise, the period doubling, the weight halving."""
    value = np.zeros((size, size, size))
    amplitude, total, period = 0.5, 0.0, base_period
    for _ in range(octaves):
        value += amplitude * _value_noise(period, size)
        total += amplitude
        period *= 2
        amplitude *= 0.5
    return value / total


def _cell_table(grid: int, salt: int) -> NDArray[np.float64]:
    """``_hash`` of every cell of a ``grid``³ lattice, shape ``(grid, grid, grid)``
    indexed ``[z, y, x]``: each cell's hash once, gathered per voxel by ``_worley``."""
    cells = np.arange(grid, dtype=np.int64)
    return _hash(cells[None, None, :], cells[None, :, None], cells[:, None, None], salt)


def _worley(grid: int, salt: int, size: int) -> NDArray[np.float64]:
    """``worley3T``: distance to the nearest of one jittered point per cell (F1), wrapping
    over ``grid`` cells, scaled by 1/0.7 and capped at 1."""
    coordinate = _axis(size) * grid
    cell = np.floor(coordinate).astype(np.int64)
    fraction = coordinate - cell
    jitter_x, jitter_y, jitter_z = (_cell_table(grid, salt + offset) for offset in (0xA1, 0xB2, 0xC3))
    nearest = np.full((size, size, size), 3.0)
    for dz in (-1, 0, 1):
        nz = np.mod(cell + dz, grid)
        for dy in (-1, 0, 1):
            ny = np.mod(cell + dy, grid)
            for dx in (-1, 0, 1):
                nx = np.mod(cell + dx, grid)
                voxels = np.ix_(nz, ny, nx)
                ox = (dx - fraction)[None, None, :] + jitter_x[voxels]
                oy = (dy - fraction)[None, :, None] + jitter_y[voxels]
                oz = (dz - fraction)[:, None, None] + jitter_z[voxels]
                np.minimum(nearest, ox * ox + oy * oy + oz * oz, out=nearest)
    result: NDArray[np.float64] = np.minimum(np.sqrt(nearest) / 0.7, 1.0)
    return result


def _inverted_worley_fbm(grid: int, salt: int, size: int) -> NDArray[np.float64]:
    """``invWorleyFbm``: three inverted Worley octaves at grid, 2·grid, 4·grid, weighted
    0.625 / 0.25 / 0.125 — high in a cell's middle (the cloud), low between cells."""
    return (0.625 * (1.0 - _worley(grid, salt + 0x010, size))
            + 0.25 * (1.0 - _worley(grid * 2, salt + 0x020, size))
            + 0.125 * (1.0 - _worley(grid * 4, salt + 0x030, size)))


@cache
def cloud_noise_rgba(size: int = SIZE) -> NDArray[np.float64]:
    """The volume as float64, shape ``(size, size, size, 4)`` indexed ``[z, y, x, channel]``
    — the example's memory order (one z slice after another, rows of x). Read-only."""
    perlin = _perlin_fbm(4, 4, size)
    folded = np.abs(perlin * 2.0 - 1.0)
    base = _inverted_worley_fbm(6, 0x100, size)
    red = base + folded * (1.0 - base)        # remap(folded, 0, 1, base, 1)
    volume = np.stack((red,
                       _inverted_worley_fbm(6, 0x200, size),
                       _inverted_worley_fbm(10, 0x300, size),
                       _inverted_worley_fbm(16, 0x400, size)), axis=-1)
    volume = np.clip(volume, 0.0, 1.0)
    volume.setflags(write=False)
    return volume


@cache
def cloud_noise_rgba16f(size: int = SIZE) -> bytes:
    """The volume as the bytes of an RGBA16F 3D texture (``QQuick3DTextureData``: width
    = height = depth = ``size``), little-endian half floats."""
    return cloud_noise_rgba(size).astype("<f2").tobytes()
