"""A soft edge as a smooth falloff: the arithmetic of the shadow feather (#793).

Qt-free, numpy only (the pattern of ``core/heatmap_render``). The sun-shadow
overlay's edge used to be four stacked strokes of 14, 9, 5 and 2.5 cm: four
flat bands, 1.25 to 2.5 cm wide, invisible at 100 % zoom and four visible
stripes from 200 % on — and the innermost one was darker than the shade it
edged. A falloff that is smooth at every zoom cannot be made of strokes (a
stroke has one tone); it is a *field*: how dark the ground is as a function of
its distance to the shade.

That distance is not computed. The shade is rasterised on a coarse lattice
(``FeatherGrid``), the raster is blurred with two box passes
(``box_blur``: a tent, isotropic enough — beside an edge at 45 degrees the
falloff is within 8 % of the shade's tone of the one beside an upright edge,
measured), and the blurred
coverage ``m`` is read as a distance: beside a straight edge ``m`` falls
monotonically from one half at the edge to nothing at the blur's reach, so
``falloff_lut`` maps it to the weight the falloff has at that distance —
linear from 1 at the edge to 0 at ``FEATHER_REACH_CM``. The painter enlarges
the field with bilinear filtering, which keeps it continuous (and, the falloff
being linear, exact between two cells); the lattice has twelve cells to the
reach when zoomed in and cells of two device pixels when zoomed out — finer
buys nothing the eye can see and is what the falloff costs.

Why linear from 1: the old stack averaged 0.51 of the shade's own tone over its
7 cm, and a linear ramp averages 0.5 — the edge keeps its visual weight. It
starts at exactly the shade's tone, so there is no ring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

import numpy as np

#: How far past the shade's edge the falloff reaches, centimetres of plan. The
#: stacked strokes it replaces reached half their widest width: 7 cm.
FEATHER_REACH_CM: Final = 7.0

#: The widest box of one blur pass, in lattice cells each side. Two passes
#: then reach 12.5 cells from an edge: the falloff is sampled twelve times, and
#: the bilinear enlargement of that is smooth to the eye at any zoom.
MAX_BLUR_RADIUS: Final = 6

#: How many box passes make the blur. Three are nearer a Gaussian and cost half
#: as much again; measured, they are no closer to the linear falloff.
BLUR_PASSES: Final = 2

#: A cell is at least this many device pixels wide. What a coarse lattice costs
#: is a falloff that starts a little under the shade's tone within half a cell
#: of the edge; under two pixels that is the edge's own anti-aliasing.
MIN_CELL_PX: Final = 2.0

#: A falloff shorter than this on the device is not drawn: under a pixel and a
#: half it is the anti-aliasing of the shade's own edge.
MIN_REACH_PX: Final = 1.5

#: The most cells one field may have. A larger one (a poster-size export of a
#: large plan) is computed on a coarser lattice: 16 MB of sums a field.
MAX_FIELD_CELLS: Final = 4_000_000

#: Entries of the coverage-to-weight table (coverage 0 to 1). Many: far from
#: the edge the coverage is tiny and the distance it stands for changes fast (a
#: coverage of 1/2000 is a twentieth of the reach from its end).
_LUT_SIZE: Final = 131072

#: The falloff is continued this far above the shade's tone INSIDE the shade:
#: the cells there are what the enlargement interpolates from just outside the
#: edge, and a table that stopped at 1 would start the falloff under the
#: shade's tone (by up to a quarter of a cell's share of the reach). The
#: painter cuts the shade out, so nothing of it shows.
MAX_WEIGHT: Final = 1.5


@dataclass(frozen=True)
class FeatherGrid:
    """The lattice a falloff is computed on.

    Attributes:
        cell_cm: The side of one cell, centimetres of plan. The lattice is
            anchored at the item's origin, so two partial paints of one
            picture compute the same cells.
        radius: Cells each side of one box pass (``BLUR_PASSES`` are made).
    """

    cell_cm: float
    radius: int

    @property
    def blur_cells(self) -> int:
        """How many cells the passes reach from a cell."""
        return BLUR_PASSES * self.radius

    def coarser(self, factor: float) -> FeatherGrid:
        """The same falloff on a lattice ``factor`` times coarser (>= 1)."""
        cell = self.cell_cm * max(1.0, factor)
        return FeatherGrid(cell, _radius_for(cell, FEATHER_REACH_CM))


def _radius_for(cell_cm: float, reach_cm: float) -> int:
    """The smallest box radius whose passes span ``reach_cm`` on cells of
    ``cell_cm``: the blur must not end before the falloff does."""
    cells = reach_cm / cell_cm
    # the passes reach ``passes * r`` cells from a cell's centre, and the cell
    # is half a cell wide beyond that
    radius = math.ceil((cells - 0.5) / BLUR_PASSES - 1e-9)
    return max(1, min(MAX_BLUR_RADIUS, radius))


def feather_grid(
    scale_px_per_cm: float, reach_cm: float = FEATHER_REACH_CM
) -> FeatherGrid | None:
    """The lattice for a painter that shows ``scale_px_per_cm`` device pixels a
    centimetre; ``None`` when the falloff is too short to show there.

    Zoomed in, a cell is a fixed share of the reach (so the falloff has the same
    number of samples at 400 % and at 5000 %); zoomed out, a cell is
    ``MIN_CELL_PX`` device pixels.
    """
    if not (math.isfinite(scale_px_per_cm) and scale_px_per_cm > 0.0):
        return None
    if reach_cm * scale_px_per_cm < MIN_REACH_PX:
        return None
    finest = reach_cm / (BLUR_PASSES * MAX_BLUR_RADIUS + 0.5)
    cell = max(finest, MIN_CELL_PX / scale_px_per_cm)
    return FeatherGrid(cell, _radius_for(cell, reach_cm))


def blur_full_scale(radius: int) -> int:
    """What ``box_sums`` returns for a cell in the middle of a full (255) field."""
    return 255 * (2 * radius + 1) ** (2 * BLUR_PASSES)


def box_sums(cells: np.ndarray, radius: int) -> np.ndarray:
    """``cells`` (bytes, 0 to 255) summed over ``BLUR_PASSES`` box passes of
    ``2 * radius + 1`` cells in both axes; what lies outside the field is zero.

    Exact integers: a cell of the result is ``blur_full_scale(radius)`` times
    the blurred value. The running sums are 32-bit and may wrap around; a
    difference of two of them is still exact, because no window's own sum
    reaches 2**32 (the largest is ``blur_full_scale(MAX_BLUR_RADIUS)``, 7.3e6).
    This is four times as fast as floating-point sums (measured), and the sums
    are most of what the falloff costs.
    """
    if cells.dtype != np.uint8:
        raise TypeError("box_sums takes bytes")
    out = cells.astype(np.uint32)
    if radius <= 0:
        return out
    width = 2 * radius + 1
    rows, columns = out.shape
    for _ in range(BLUR_PASSES):
        down = np.zeros((rows + width, columns), dtype=np.uint32)
        np.cumsum(out, axis=0, out=down[radius + 1: radius + 1 + rows])
        down[radius + 1 + rows:] = down[radius + rows]
        out = down[width:] - down[:-width]
        across = np.zeros((rows, columns + width), dtype=np.uint32)
        np.cumsum(out, axis=1, out=across[:, radius + 1: radius + 1 + columns])
        across[:, radius + 1 + columns:] = across[:, radius + columns: radius + columns + 1]
        out = across[:, width:] - across[:, :-width]
    return out


def box_blur(cells: np.ndarray, radius: int) -> np.ndarray:
    """``cells`` (bytes) blurred as ``box_sums`` sums them, as shares 0 to 1."""
    return box_sums(cells, radius).astype(np.float32) / np.float32(blur_full_scale(radius))


@lru_cache(maxsize=64)
def _falloff_lut(radius: int, cells_per_reach: float) -> np.ndarray:
    kernel = np.ones(1)
    box = np.full(2 * radius + 1, 1.0 / (2 * radius + 1))
    for _ in range(BLUR_PASSES):
        kernel = np.convolve(kernel, box)
    reach = BLUR_PASSES * radius
    centres = np.arange(-reach, reach + 1, dtype=np.float64)
    # blurred coverage of a cell whose centre lies ``d`` cells outside a
    # straight edge (the cell the edge crosses is covered in part)
    distances = np.linspace(0.0, reach + 0.5, 64 * reach + 33)
    covered = np.clip(0.5 - distances[:, None] - centres[None, :], 0.0, 1.0)
    coverage = covered @ kernel
    wanted = np.linspace(0.0, 1.0, _LUT_SIZE)
    # coverage falls with distance: reverse both for np.interp's rising x.
    # Inside the edge the picture is the mirror image: coverage 1 - m lies as
    # far inside as coverage m lies outside.
    outside = np.interp(np.minimum(wanted, 1.0 - wanted), coverage[::-1], distances[::-1])
    distance = np.where(wanted <= 0.5, outside, -outside)
    lut = np.clip(1.0 - distance / cells_per_reach, 0.0, MAX_WEIGHT).astype(np.float32)
    lut.setflags(write=False)
    return lut


def falloff_lut(grid: FeatherGrid, reach_cm: float = FEATHER_REACH_CM) -> np.ndarray:
    """The weight of the falloff for a blurred coverage of 0 to 1 (index 0 to
    the last): 1 at the edge (coverage one half), linear to 0 at ``reach_cm``
    outside it, and continued to ``MAX_WEIGHT`` inside it."""
    return _falloff_lut(grid.radius, round(reach_cm / grid.cell_cm, 4))


def feather_weight(
    coverage: np.ndarray,
    grid: FeatherGrid,
    strength: np.ndarray | None = None,
    reach_cm: float = FEATHER_REACH_CM,
) -> np.ndarray:
    """How dark each cell of the lattice is, as a share of a solid shade's tone:
    1 at the shade's edge, 0 from ``reach_cm`` outside it on.

    ``coverage`` is the share of each cell the shade covers, in bytes (255: all
    of it). ``strength`` is the shade's own tone per cell where it is not solid
    everywhere (a porous fence, an open frame: bytes, zero outside the shade);
    the falloff beside a light shade starts at that shade's tone, not at the
    solid one's. Inside the shade the falloff simply goes on rising, to
    ``MAX_WEIGHT`` (see there); the painter draws the shade itself and removes
    what this function says about its inside.
    """
    sums = box_sums(coverage, grid.radius)
    lut = falloff_lut(grid, reach_cm)
    per_entry = np.float32((_LUT_SIZE - 1) / blur_full_scale(grid.radius))
    shares = sums.astype(np.float32)
    index = np.minimum((shares * per_entry).astype(np.intp), _LUT_SIZE - 1)
    weight = lut[index]
    if strength is None:
        return weight
    tone = box_sums(strength, grid.radius).astype(np.float32) / np.maximum(shares, np.float32(1.0))
    return weight * np.minimum(tone, np.float32(1.0))


__all__ = [
    "BLUR_PASSES",
    "FEATHER_REACH_CM",
    "MAX_BLUR_RADIUS",
    "MAX_FIELD_CELLS",
    "MAX_WEIGHT",
    "MIN_CELL_PX",
    "MIN_REACH_PX",
    "FeatherGrid",
    "blur_full_scale",
    "box_blur",
    "box_sums",
    "falloff_lut",
    "feather_grid",
    "feather_weight",
]
