"""The 2D sun analysis, draped over the 3D ground (Phase 17 L2.1, #386). Qt-free.

ADR-048 put the rule in one sentence: the analysis stays with the 2D model, and it
is DRAPED onto the 3D ground. The engine's shadow maps are illustrative (measured
against the 2D model on a box caster, nothing more — a gable roof, a porous fence
and a crown on a trunk cast differently by design); what a gardener reads off the
3D ground is the 2D answer, laid on it. Two drapes, each ONE mesh:

- ``shadow_drape`` — the shadow overlay of the canvas: the very polygons
  ``SunShadowController`` paints (``drape_polygons()``: the union of every
  caster's shadow at the sim instant, the whole canvas at night), cut at the plan
  rectangle as the canvas cuts them, triangulated. Its vertex colour is a linear
  MULTIPLIER (``SHADE_MULTIPLIER``) the engine's ``"shade"`` layer multiplies the
  frame with: darker in every mood and tinted the way the canvas's shadow colour is
  (blue over green over red — ``sun_shadow_controller._SHADOW_COLOR``, pinned by a
  test). A colour BLENDED over the 3D ground cannot do that: an unlit overlay goes
  through the mood's exposure, and at night (exposure 2.4) the canvas's shadow
  colour turned the garden lighter (3D review of #386, PF-L3D-06). Nothing is
  computed a second time.
- ``sun_hours_drape`` — the hours-of-sun map: the heatmap's minutes grid
  (``core.shade_aggregation.SunHoursMap``) as a vertex-coloured mesh, one vertex
  per cell centre plus a clamped edge — what the canvas's ``SmoothTransformation``
  draws: a bilinear surface — coloured through the heatmap's own ramp
  (``core.heatmap_render.build_sun_lut``) in linear light.

Both are in the SCENE frame with the scene origin as their origin (they belong to no
item: no transform poses them), ``DRAPE_LIFT_CM`` above the ground, normals up. An
item standing on the ground hides the drape under it, as it hides the ground: the
drape is the analysis AT GROUND LEVEL, which is what both 2D maps are.

The probe of L2.1 — "a click on the ground reports sun minutes and band" — is
``SunHoursMap.minutes_at`` (the cell the canvas would name) and
``services.sun_mismatch_service.band_of``; this module only says where the drape
lies.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from typing import Final, TypeAlias

import numpy as np
from numpy.typing import NDArray

from ..shade_aggregation import HeatmapGrid, points_in_polygons
from ..shadow_geometry import clip_to_rect
from .color import srgb8_to_linear
from .mesh import Mesh
from .polygon import RegionTooLargeError, group_rings, triangulate_region

_log = logging.getLogger(__name__)

#: How far above the ground plane the drape lies (cm). The ground tiles lie at 0 and
#: the endless meadow at -5: at the workspace's near plane (5 cm) a 24-bit depth
#: buffer resolves about 0.3 cm at 50 m and 1.2 cm at 100 m, so 1.5 cm keeps the drape
#: off the ground's depth from every distance the orbit camera frames a garden at.
DRAPE_LIFT_CM: Final = 1.5
#: What the shade layer multiplies the frame under a shadow with, linear RGB: below 1
#: in every channel (a shadow only darkens) and ordered like the canvas's shadow
#: colour (30, 41, 66) - blue kept most, red least. Measured 2026-10-24 (D3D11, the
#: board's hero camera, the High look): the lit lawn under it reads 0.83 of its luma at
#: noon, 0.76 at golden hour, 0.74 at sunset, 0.78 on a December noon and 0.76 at night;
#: over the engine's own shadow 0.71-0.84. The over-blended canvas colour read
#: +17.6 / +24.1 luma at night (lighter) and -4.1 at golden hour.
SHADE_MULTIPLIER: Final[tuple[float, float, float]] = (0.60, 0.62, 0.95)
#: At most this many vertices in a sun-hours drape. Beyond it the map is averaged over
#: square blocks of cells for the drape alone (the probe reads the full map): a 10 cm
#: map of a 51 x 51 m garden still fits, and the mesh stays below 13 MB.
MAX_DRAPE_VERTICES: Final = 262_144
#: The raster step (cm) a shadow region falls back to when it cannot be triangulated.
FALLBACK_STEP_CM: Final = 5.0

_F64: TypeAlias = NDArray[np.float64]
Polygon: TypeAlias = Sequence[tuple[float, float]]


def _up_normals(count: int) -> NDArray[np.float64]:
    normals = np.zeros((count, 3))
    normals[:, 2] = 1.0
    return normals


def _raster_rings(rings: Sequence[Polygon], step_cm: float) -> tuple[_F64, NDArray[np.int64]]:
    """Rings as row runs of a ``step_cm`` raster, even-odd (a hole stays sunny, however
    the rings lie): one quad per run of covered cell centres. Exact to the step — the
    fallback for what the triangulator refuses."""
    xy = np.concatenate([np.asarray(ring, dtype=np.float64).reshape(-1, 2) for ring in rings])
    low, high = xy.min(axis=0), xy.max(axis=0)
    cols = max(1, math.ceil((high[0] - low[0]) / step_cm))
    rows = max(1, math.ceil((high[1] - low[1]) / step_cm))
    xs = low[0] + (np.arange(cols) + 0.5) * step_cm
    ys = low[1] + (np.arange(rows) + 0.5) * step_cm
    grid = np.stack(np.meshgrid(xs, ys), axis=-1).reshape(-1, 2)
    inside = points_in_polygons(rings, grid).reshape(rows, cols)
    quads: list[tuple[float, float, float, float]] = []
    for row in range(rows):
        line = np.concatenate([[False], inside[row], [False]])
        edges = np.flatnonzero(line[1:] != line[:-1])
        for start, stop in zip(edges[::2], edges[1::2], strict=True):
            y0 = low[1] + row * step_cm
            quads.append((low[0] + start * step_cm, y0, low[0] + stop * step_cm, y0 + step_cm))
    positions = np.zeros((4 * len(quads), 2))
    triangles = np.zeros((2 * len(quads), 3), dtype=np.int64)
    for index, (x0, y0, x1, y1) in enumerate(quads):
        positions[4 * index:4 * index + 4] = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        first = 4 * index
        triangles[2 * index] = (first, first + 1, first + 2)
        triangles[2 * index + 1] = (first, first + 2, first + 3)
    return positions, triangles


def shadow_drape(polygons: Sequence[Polygon], width_cm: float, depth_cm: float,
                 multiplier: tuple[float, float, float] = SHADE_MULTIPLIER) -> Mesh:
    """The shadow overlay's polygons as one flat mesh on the plan (module docstring).

    Every region is triangulated exactly (``polygon.triangulate_region``); one the
    triangulator refuses — a hole that touches its outer ring, a region beyond the
    work bound — is laid as row runs of a ``FALLBACK_STEP_CM`` raster instead and
    logged at DEBUG: the drape never loses a shadow it was given.
    """
    clipped = clip_to_rect(polygons, width_cm, depth_cm)
    if not clipped:
        return Mesh.empty()
    rings = [_as_ring(ring) for ring in clipped]
    pieces: list[tuple[_F64, NDArray[np.int64]]] = []
    try:
        regions = group_rings(rings)
    except (ValueError, RegionTooLargeError) as error:
        # rings that do not nest as outers and holes: the whole set as ONE even-odd
        # raster, so a sunny island inside a shadow stays sunny
        _log.debug("3D drape: the shadow rings were raster-cut whole (%s)", type(error).__name__)
        regions = ()
        pieces.append(_raster_rings(rings, FALLBACK_STEP_CM))
    for outer, holes in regions:
        try:
            points, tris = triangulate_region(outer, holes)
            pieces.append((np.asarray(points, dtype=np.float64).reshape(-1, 2),
                           np.asarray(tris, dtype=np.int64).reshape(-1, 3)))
        except (ValueError, RegionTooLargeError) as error:
            _log.debug("3D drape: a shadow region was raster-cut (%s)", type(error).__name__)
            pieces.append(_raster_rings([outer, *holes], FALLBACK_STEP_CM))
    positions: list[_F64] = []
    triangles: list[NDArray[np.int64]] = []
    count = 0
    for xy, indices in pieces:
        if not len(indices):
            continue
        positions.append(xy)
        triangles.append(indices + count)
        count += len(xy)
    if not count:
        return Mesh.empty()
    xy = np.concatenate(positions)
    full = np.zeros((count, 3))
    full[:, :2] = xy
    full[:, 2] = DRAPE_LIFT_CM
    colors = np.tile(np.asarray((*multiplier, 1.0), dtype=np.float64), (count, 1))
    return Mesh.from_arrays(full, _up_normals(count), colors, np.zeros((count, 2)),
                            np.concatenate(triangles))


def _as_ring(ring: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    return tuple((float(x), float(y)) for x, y in ring)



def _block_mean(values: NDArray[np.float64], factor: int) -> NDArray[np.float64]:
    """``values`` averaged over ``factor`` x ``factor`` blocks (partial blocks at the
    north and east edge average what they hold)."""
    rows, cols = values.shape
    out_rows, out_cols = math.ceil(rows / factor), math.ceil(cols / factor)
    padded = np.full((out_rows * factor, out_cols * factor), np.nan)
    padded[:rows, :cols] = values
    blocks = padded.reshape(out_rows, factor, out_cols, factor)
    means: NDArray[np.float64] = np.nanmean(blocks, axis=(1, 3))
    return means


def drape_factor(grid: HeatmapGrid, max_vertices: int = MAX_DRAPE_VERTICES) -> int:
    """How many cells a side one drape cell averages: 1 while ``(rows + 2) x (cols + 2)``
    vertices fit ``max_vertices``, else the smallest factor that fits."""
    factor = 1
    while (math.ceil(grid.rows / factor) + 2) * (math.ceil(grid.cols / factor) + 2) > max_vertices:
        factor += 1
    return factor


def sun_hours_drape(minutes: NDArray[np.floating], grid: HeatmapGrid, daylight_minutes: float,
                    lut: NDArray[np.uint8], *, max_vertices: int = MAX_DRAPE_VERTICES) -> Mesh:
    """An hours-of-sun map as one vertex-coloured mesh on the plan (module docstring).

    ``minutes``: the map's grid, row 0 = SOUTH (``core.shade_aggregation``) — so row
    ``r`` lies at scene north ``y0 + (r + 0.5) x cell``, and nothing here flips it.
    ``lut``: the heatmap's RGBA ramp (``heatmap_render.build_sun_lut``), indexed by
    the share of the day's daylight a cell had (``daylight_minutes``; 0: all shade).
    A vertex sits on every cell centre, and one more row and column of vertices on
    each edge repeat the edge cells: the surface reaches the grid's edge flat, as
    the canvas's smooth scaling draws it.
    """
    values = np.asarray(minutes, dtype=np.float64)
    if values.ndim != 2 or values.shape != (grid.rows, grid.cols):
        raise ValueError(f"minutes has shape {values.shape}, the grid {(grid.rows, grid.cols)}")
    factor = drape_factor(grid, max_vertices)
    cell = grid.cell_cm * factor
    if factor > 1:
        values = _block_mean(values, factor)
    rows, cols = values.shape
    # vertex coordinates: the grid's edge, every (block) cell centre, the far edge
    east_extent = grid.cols * grid.cell_cm
    north_extent = grid.rows * grid.cell_cm
    xs = np.concatenate([[0.0], (np.arange(cols) + 0.5) * cell, [east_extent]])
    ys = np.concatenate([[0.0], (np.arange(rows) + 0.5) * cell, [north_extent]])
    xs = np.minimum(xs, east_extent) + grid.x0_cm
    ys = np.minimum(ys, north_extent) + grid.y0_cm
    padded = np.pad(values, 1, mode="edge")
    share = (np.zeros_like(padded) if daylight_minutes <= 0.0
             else np.clip(padded / daylight_minutes, 0.0, 1.0))
    index = np.clip(np.round(share * (len(lut) - 1)).astype(np.intp), 0, len(lut) - 1)
    linear = _linear_lut(lut)[index].reshape(-1, 4)
    gx, gy = np.meshgrid(xs, ys)
    count = gx.size
    positions = np.zeros((count, 3))
    positions[:, 0] = gx.reshape(-1)
    positions[:, 1] = gy.reshape(-1)
    positions[:, 2] = DRAPE_LIFT_CM
    width = len(xs)
    here = (np.arange(len(ys) - 1)[:, None] * width + np.arange(width - 1)[None, :]).reshape(-1)
    east, north, both = here + 1, here + width, here + width + 1
    triangles = np.concatenate([np.stack([here, east, both], axis=1),
                                np.stack([here, both, north], axis=1)])
    return Mesh.from_arrays(positions, _up_normals(count), linear, np.zeros((count, 2)), triangles)


def _linear_lut(lut: NDArray[np.uint8]) -> NDArray[np.float64]:
    """The 8-bit sRGB ramp in linear light, alpha as 0..1 (``color.srgb8_to_linear``)."""
    return np.asarray([srgb8_to_linear((int(r), int(g), int(b), int(a))) for r, g, b, a in lut],
                      dtype=np.float64)
