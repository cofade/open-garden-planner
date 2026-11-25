"""Hours-of-sun shade aggregation for the heatmap overlay (US-E4, #259).

Qt-free (pattern: ``core/solar``, ``core/shadow_geometry``): samples the
daylight period of one civil day at a fixed step, reuses the US-E3 shadow
machinery per sample, and accumulates per-grid-cell minutes of direct sun.
Rasterization of the per-sample shadow polygons is INJECTED as a callable —
the production rasterizer paints a ``QImage`` off the GUI thread
(``ui/canvas/sun_heatmap.py``, ADR-037 route 1); tests may inject a
point-in-polygon reference rasterizer. That keeps this module headless.

Grid convention: ``row r`` covers scene ``y ∈ [y0 + r·cell, y0 + (r+1)·cell)``
— row 0 is the SOUTH edge (scene +y = North, ADR-002). The display layer
keeps that convention so the Y-flip discipline of §8.20 holds end to end.

Horticultural bands (glossary §12.1): < 2 h = deep shade, 2–4 h = light
shade, 4–6 h = partial sun, ≥ 6 h = full sun.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import NamedTuple

import numpy as np

from .shadow_geometry import (
    MIN_SUN_ELEVATION_DEG,
    CasterLike,
    GroupedCaster,
    OpenFrame,
    Polygon,
    Triangle3D,
    WeightedShadowsResult,
    _clip_triangle_above_z,
    caster_transmittance,
    compute_grouped_shadows,
    compute_scene_shadows,
    compute_weighted_shadows,
)
from .sim_clock import SimInstant
from .solar import scene_azimuth, solar_position

#: Daylight sampling step. 15 min × ≤64 daylight samples covers the perf
#: budget; the toy-case gate allows one sample of slack.
SAMPLE_STEP_MINUTES = 15

#: Default heatmap resolution — 10 cm cells (60 000 cells for a 30 m × 20 m
#: garden, the stated performance target).
GRID_CELL_CM = 10.0

#: Band thresholds in minutes of direct sun: deep shade < 2 h ≤ light
#: shade < 4 h ≤ partial sun < 6 h ≤ full sun.
BAND_THRESHOLDS_MINUTES: tuple[int, int, int] = (120, 240, 360)


class SunSample(NamedTuple):
    """One daylight sample instant with the precomputed sun position."""

    dt_utc: datetime
    elevation_deg: float
    azimuth_deg: float


@dataclass(frozen=True)
class HeatmapGrid:
    """Cell grid over a scene-space rectangle (row 0 = south edge)."""

    x0_cm: float
    y0_cm: float
    cell_cm: float
    cols: int
    rows: int

    @classmethod
    def for_rect(
        cls,
        x0_cm: float,
        y0_cm: float,
        width_cm: float,
        height_cm: float,
        cell_cm: float = GRID_CELL_CM,
    ) -> HeatmapGrid:
        return cls(
            x0_cm=x0_cm,
            y0_cm=y0_cm,
            cell_cm=cell_cm,
            cols=max(1, math.ceil(width_cm / cell_cm)),
            rows=max(1, math.ceil(height_cm / cell_cm)),
        )

    def cell_center(self, row: int, col: int) -> tuple[float, float]:
        return (
            self.x0_cm + (col + 0.5) * self.cell_cm,
            self.y0_cm + (row + 0.5) * self.cell_cm,
        )

    def cell_at(self, x_cm: float, y_cm: float) -> tuple[int, int]:
        """(row, col) of the cell containing a scene point (no bounds check)."""
        return (
            int((y_cm - self.y0_cm) // self.cell_cm),
            int((x_cm - self.x0_cm) // self.cell_cm),
        )


#: A rasterizer turns one sample's shadow polygons into a boolean shade mask
#: of shape (rows, cols), True = shaded. Injected so the core stays Qt-free.
Rasterizer = Callable[[list[Polygon], HeatmapGrid], np.ndarray]


@dataclass(frozen=True)
class IdentifiedCaster:
    """All solid footprints belonging to one object (plain worker input).

    ``base_cm`` is where the object stands (Phase 17 L1.6, ADR-037 addendum): 0.0
    on the garden floor, the soil surface for a plant on raised soil. Its solid is
    ``footprint x [base_cm, base_cm + height_cm]`` everywhere it shades — the
    overlay, the heatmap grid and the per-plant estimates.

    ``holds_plants``: this solid is a SOIL container a plant can stand in
    (``core.object_height.is_solid_soil_parent`` — a bed, raised bed, container
    or wall planter with a resolved height), not a wall. A plant inside its
    outline is inside its soil, so the estimate must not count it as shade
    whether or not the plant is LINKED to it (#481, the ``spared`` map in
    ``_aggregate_day``).

    ``frame`` (#698): an OPEN FRAME's solid members (a pergola's timber, a trellis's
    lattice) in the frame's own coordinates (``core.shadow_geometry.OpenFrame``).
    The caster's shadow stays its prism's; the members weigh it for the sun of each
    sample (``open_frame_transmittance``). None for every other caster. The caster
    walk sets it; nothing else decides which kinds are open
    (``core.object_height.OPEN_FRAME_TYPE_NAMES``).
    """

    item_id: str
    footprints: tuple[tuple[tuple[float, float], ...], ...]
    height_cm: float
    base_cm: float = 0.0
    holds_plants: bool = False
    roof_triangles: tuple[Triangle3D, ...] = ()
    fence_style: str | None = None
    fence_points: tuple[tuple[float, float], ...] = ()
    fence_width_cm: float = 0.0
    transmittance: float | None = None
    frame: OpenFrame | None = None
    #: A living plant (#830): it does not shade the grid cells inside its own
    #: footprint, the same rule its own sun estimate uses (its own solid and the
    #: soil parent it stands in are left out). The map stays honest under a
    #: plant instead of showing a dark dot, and the cell at the plant's centre
    #: agrees with the plant's estimate.
    is_plant: bool = False


@dataclass(frozen=True)
class SunReceiver:
    """A plant whose direct sun is estimated, at its centre and soil elevation.

    ``stands_on``: the id of the soil parent whose solid the plant stands in (the
    membership half of the base rule: linked to a visible bed, raised bed or
    container that has a height AND its centre inside it —
    ``ui/canvas/footprints.standing_parent``), else None. That parent is under
    the plant, not between it and the sun: it is left out for this receiver
    exactly like the receiver's own solid. Without it every plant in a raised
    bed reads 0 hours — the bed's footprint covers the point all day.

    A soil solid the plant stands in WITHOUT that link is left out too (#481):
    ``_aggregate_day`` spares every caster whose ``holds_plants`` is set and
    whose outline contains this receiver's point.

    ``elevation_cm`` (issue #641): the soil elevation where the plant stands
    (``ui/canvas/footprints.item_base_cm``, 0.0 on ground). When evaluating an
    elevated receiver, shadow casting from obstacles is evaluated against the
    obstacle slice strictly above ``elevation_cm``, preventing false shade warnings
    for plants raised above fences, walls, or edgings.
    """

    item_id: str
    x_cm: float
    y_cm: float
    stands_on: str | None = None
    elevation_cm: float = 0.0


@dataclass(frozen=True)
class SunExposureResult:
    """Ground heatmap plus sparse soil-plane exposure excluding each receiver itself.

    ``samples`` / ``sample_shade`` (Phase 17 L2.2, #386): every daylight sample's
    instant and its shade mask — ``np.packbits`` of the rasterised mask along the
    columns, shape ``(len(samples), rows, ceil(cols / 8))``, True = shaded — so
    that a day sweep can show the map filling up sample by sample
    (``SunHoursMap.minutes_until``) without a second computation. Kept while the
    masks fit ``MAX_SAMPLE_SHADE_BYTES``; beyond it ``sample_shade`` is None and
    the map is only ever shown whole.
    """

    minutes: np.ndarray
    receiver_minutes: tuple[tuple[str, float], ...]
    samples: tuple[datetime, ...] = ()
    sample_shade: np.ndarray | None = None
    sample_transmittance: np.ndarray | None = None


#: The per-sample shade masks of one day are kept up to this size (bytes): 1 bit a
#: cell a sample — a 10 cm map of a 30 x 20 m garden over 64 samples is 480 kB, and
#: this bound is a map of eight million cells.
MAX_SAMPLE_SHADE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, eq=False)
class SunHoursMap:
    """A finished hours-of-sun map as plain data — what the canvas shows (L2.1, #386).

    The heatmap controller's public ``result()``: the day, the grid (row 0 = SOUTH),
    the minutes of direct sun per cell, the day's full daylight (the ramp's top),
    the sampling step and, when they were kept, the per-sample shade masks
    (``SunExposureResult``). Consumers read it; nobody recomputes it.
    """

    day: date
    grid: HeatmapGrid
    minutes: np.ndarray
    daylight_minutes: float
    step_minutes: int = SAMPLE_STEP_MINUTES
    samples: tuple[datetime, ...] = ()
    sample_shade: np.ndarray | None = None
    sample_transmittance: np.ndarray | None = None

    def minutes_at(self, x_cm: float, y_cm: float) -> float | None:
        """The minutes of the cell a scene point lies in — the cell the canvas draws
        there — or None outside the grid (and for a point that is not finite)."""
        if not (math.isfinite(x_cm) and math.isfinite(y_cm)):
            return None
        row, col = self.grid.cell_at(x_cm, y_cm)
        if not (0 <= row < self.grid.rows and 0 <= col < self.grid.cols):
            return None
        return float(self.minutes[row, col])

    @property
    def progressive(self) -> bool:
        """True when the per-sample masks or transmittances were kept: ``minutes_through`` can answer."""
        if self.sample_transmittance is not None and len(self.samples) == len(self.sample_transmittance):
            return True
        return self.sample_shade is not None and len(self.samples) == len(self.sample_shade)

    def sample_minutes_of_day(self, tz: tzinfo | None) -> tuple[int, ...]:
        """Each sample's wall minute of the day in ``tz`` (the clock's zone).

        The map samples a UTC civil day (``daylight_samples``) — one whole diurnal arc,
        but, far from Greenwich, not the LOCAL day: in Sydney it runs from 10:00 one
        day to 10:00 the next. A day sweep goes through the local day, so it takes
        the samples by their time of day, not by their instant: at local sunset every
        daylight sample is in, and the sweep ends on the whole map."""
        return tuple(SimInstant.from_datetime(sample, tz).minute_of_day for sample in self.samples)

    def sample_sunlit(self, index: int) -> np.ndarray:
        """Sample ``index``'s sunlit cells, ``(rows, cols)`` bool (True = in the sun)."""
        if self.sample_transmittance is not None:
            sunlit_f: np.ndarray = self.sample_transmittance[index] > 0.0
            return sunlit_f
        if self.sample_shade is None:
            raise ValueError("this map kept no per-sample masks")
        shaded = np.unpackbits(self.sample_shade[index], axis=1, count=self.grid.cols)
        sunlit: np.ndarray = shaded == 0
        return sunlit

    def sample_sun_factor(self, index: int) -> np.ndarray:
        """Sample ``index``'s sunlight transmittance factor ``(rows, cols)`` float32 in ``[0, 1]`` (#440)."""
        if self.sample_transmittance is not None:
            return np.asarray(self.sample_transmittance[index], dtype=np.float32)
        return np.where(self.sample_sunlit(index), 1.0, 0.0).astype(np.float32)

    def minutes_through(self, minute_of_day: int, tz: tzinfo | None) -> np.ndarray | None:
        """The minutes of direct sun each cell collected from the morning up to the wall
        time ``minute_of_day`` in ``tz`` (inclusive) — the map half-way through a day
        sweep. None when the masks were not kept. Through the last minute of the day it
        equals ``minutes`` (pinned)."""
        if not self.progressive:
            return None
        total = np.zeros((self.grid.rows, self.grid.cols), dtype=np.float32)
        for index, minute in enumerate(self.sample_minutes_of_day(tz)):
            if minute <= minute_of_day:
                total += float(self.step_minutes) * self.sample_sun_factor(index)
        return total


def points_in_polygons(polygons: Sequence[Sequence[tuple[float, float]]], points: np.ndarray) -> np.ndarray:
    """Vectorized version of the reference's even-odd rule, with bbox pruning.

    Polygons must be union output (including holes). Separate solids belonging
    to one caster are ORed by the caller, not XORed as if they were holes.
    """
    mask = np.zeros(len(points), dtype=bool)
    for polygon in polygons:
        if len(polygon) < 3:
            continue
        vertices = np.asarray(polygon, dtype=float)
        indices = np.flatnonzero(np.all((points >= vertices.min(axis=0)) & (points <= vertices.max(axis=0)), axis=1))
        if not len(indices):
            continue
        candidates = points[indices]
        x1, y1 = vertices[:, 0], vertices[:, 1]
        x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
        slopes = np.divide(x2 - x1, y2 - y1, out=np.zeros_like(x1), where=y2 != y1)
        y = candidates[:, 1, None]
        crosses = ((y1 > y) != (y2 > y)) & (x1 + (y - y1) * slopes > candidates[:, 0, None])
        mask[indices] ^= np.count_nonzero(crosses, axis=1) % 2 == 1
    return mask


def daylight_samples(
    lat_deg: float,
    lon_deg: float,
    day: date,
    step_minutes: int = SAMPLE_STEP_MINUTES,
    *,
    north_angle_deg: float = 0.0,
) -> list[SunSample]:
    """Sun-up sample instants across the UTC civil day, at ``step_minutes``.

    Polar-safe by construction: midwinter at lat 70° yields an empty list
    (polar night), midsummer yields all samples (midnight sun).

    The gate is geometric α > 0 (sun up at all), NOT the shadow module's
    0.5° minimum — dropping the grazing dawn/dusk samples would silently
    undercount every cell's sun by ~10 min/day at Berlin's solstice.
    ``compute_heatmap`` clamps the elevation it feeds the shadow machinery
    instead (see there).

    ``north_angle_deg`` is the plan's north orientation (#663): each sample's
    azimuth is mapped into the scene frame here, once, so every cell's
    receiver-side shading uses the same frame as the 2D shadow overlay.
    """
    samples: list[SunSample] = []
    instant = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = instant + timedelta(days=1)
    step = timedelta(minutes=step_minutes)
    while instant < end:
        position = solar_position(lat_deg, lon_deg, instant)
        if position.elevation_deg > 0.0:
            samples.append(
                SunSample(
                    instant,
                    position.elevation_deg,
                    scene_azimuth(position.azimuth_deg, north_angle_deg),
                )
            )
        instant += step
    return samples


def point_rasterizer_reference(
    polygons: list[Polygon], grid: HeatmapGrid
) -> np.ndarray:
    """Reference rasterizer: even-odd point-in-polygon per CELL CENTER.

    O(cells × vertices) — fine for tests and tiny grids, far too slow for
    production (that is the QImage rasterizer's job). Kept in the core so
    the integration suite can pin QImage-vs-reference equivalence.
    """
    mask = np.zeros((grid.rows, grid.cols), dtype=bool)
    for row in range(grid.rows):
        for col in range(grid.cols):
            x, y = grid.cell_center(row, col)
            inside = False
            for polygon in polygons:
                n = len(polygon)
                for i in range(n):
                    x1, y1 = polygon[i]
                    x2, y2 = polygon[(i + 1) % n]
                    if (y1 > y) != (y2 > y):
                        x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                        if x_cross > x:
                            inside = not inside
            mask[row, col] = inside
    return mask


def compute_heatmap(
    casters: Sequence[CasterLike],
    lat_deg: float,
    lon_deg: float,
    day: date,
    grid: HeatmapGrid,
    rasterize: Rasterizer,
    *,
    step_minutes: int = SAMPLE_STEP_MINUTES,
    north_angle_deg: float = 0.0,

    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> np.ndarray | None:
    """Minutes of direct sun per grid cell over one day; None if cancelled.

    For each daylight sample: shadow polygons via the US-E3 machinery →
    injected rasterizer → unshaded cells collect ``step_minutes``. Cells
    under no shadow all day accumulate the full daylight duration.
    ``casters`` are the overlay's own (``ShadowCaster``, base included — a
    plant in a raised bed casts from its soil here exactly as it does there).

    Grazing samples (0 < α < 0.5°) are counted as daylight but their
    shadows are computed at a clamped 0.5° elevation — the shadow module
    refuses true grazing angles (lengths explode), and at 0.5° a shadow is
    already ~115 m per meter of height, so "everything sunward-shadowed is
    shaded" holds while open cells still collect their dawn/dusk minutes
    (this keeps the winter toy case at exactly 0 and the summer one at the
    oracle's 540).
    """
    result = _aggregate_day(casters, lat_deg, lon_deg, day, grid, rasterize,
                            step_minutes=step_minutes, north_angle_deg=north_angle_deg,
                            progress=progress, should_cancel=should_cancel)
    return result.minutes if result is not None else None


def compute_sun_exposure(
    casters: Sequence[IdentifiedCaster],
    receivers: Sequence[SunReceiver],
    lat_deg: float,
    lon_deg: float,
    day: date,
    grid: HeatmapGrid,
    rasterize: Rasterizer,
    *,
    step_minutes: int = SAMPLE_STEP_MINUTES,
    north_angle_deg: float = 0.0,
    include_sample_masks: bool = False,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> SunExposureResult | None:
    """One explicit day run, preserving the ordinary grid and excluding self at receivers.

    Receivers use heatmap cell centres. Out-of-grid receivers are omitted,
    never returned as zero sun. No leaf-height or transparent-canopy model.
    """
    # The grid and the receivers both come from the identified casters' grouped
    # sweeps (base included); the anonymous list is only for a caller without ids.
    return _aggregate_day((), lat_deg, lon_deg, day, grid, rasterize,
                          identified=casters, receivers=receivers, step_minutes=step_minutes,
                          north_angle_deg=north_angle_deg,
                          include_sample_masks=include_sample_masks,
                          progress=progress, should_cancel=should_cancel)


def _slice_roof_triangles_for_elevation(
    roof_triangles: tuple[Triangle3D, ...],
    base_cm: float,
    elev_cm: float,
) -> tuple[Triangle3D, ...]:
    """Slice 3D roof/wall triangles at ``z >= elev_cm`` and shift down by ``elev_cm`` (#440)."""
    if not roof_triangles or elev_cm <= 0.0:
        return roof_triangles
    sliced: list[Triangle3D] = []
    for tri in roof_triangles:
        clipped = _clip_triangle_above_z(tri, base_cm, elev_cm)
        if len(clipped) < 3:
            continue
        shifted = [(x, y, max(0.0, z - elev_cm)) for x, y, z in clipped]
        sliced.append((shifted[0], shifted[1], shifted[2]))
        if len(shifted) == 4:
            sliced.append((shifted[0], shifted[2], shifted[3]))
    return tuple(sliced)


def _slice_frame_for_elevation(
    frame: OpenFrame | None,
    base_cm: float,
    elev_cm: float,
) -> OpenFrame | None:
    """An open frame's members above a raised receiver's plane, z from the SLICE's own
    base (#698) — the frame's half of the slice ``_aggregate_day`` makes of a caster.

    A frame standing at or above the plane is the same frame: the slice's base is
    ``base_cm - elev_cm`` and its members are measured from it as before. One standing
    below is cut at the plane (the slice's base is the plane itself). None stays None:
    not an open frame. A frame left without triangles is an open frame with no member
    above the plane, which shades nothing there.
    """
    if frame is None or elev_cm <= 0.0 or base_cm >= elev_cm:
        return frame
    from open_garden_planner.core.shadow_geometry import slice_open_frame_for_elevation

    return slice_open_frame_for_elevation(frame, base_cm, elev_cm)


def _weighted_sun_factor(
    weighted: WeightedShadowsResult,
    grid: HeatmapGrid,
    rasterize: Rasterizer,
) -> np.ndarray:
    """The sunlight fraction of every grid cell for one sample of a weighted sweep.

    Each weighted region is painted on its own, because one path over all of
    them would let odd-even filling cancel where two regions meet. A cell whose
    centre lies exactly on a seam between regions is then classified by the
    painter, not by the geometry: the two paths can both claim it (the darker
    transmittance wins) or neither can (the cell reads as full sun) — the
    one-sample seam #1007 reports. Presence is therefore taken from the union,
    the one path the solid sweep has always painted, so a per-region pass can
    neither add nor remove a cell against it. Inside the union, a seam cell's
    fraction is settled by the even-odd point-in-polygon rule at its centre:
    the darkest region that contains the centre owns the cell.
    """
    regions = [region for region in weighted.weighted_regions if region.polygons]
    if not regions:
        return np.ones((grid.rows, grid.cols), dtype=np.float32)
    if len(regions) == 1:
        # One transmittance over the whole shade: there is no seam to settle, and
        # the region IS the union — paint it once instead of painting the union
        # and then the same polygons again (#855's first-open-frame cost).
        region = regions[0]
        shaded = np.asarray(rasterize(region.polygons, grid), dtype=bool)
        return np.where(shaded, np.float32(region.transmittance), np.float32(1.0))
    factor = np.ones((grid.rows, grid.cols), dtype=np.float32)
    # The union is the "single region" of the same shade: the presence it paints
    # is the answer the solid path gave before #440, and a per-region path must
    # not add or remove a cell against it (#1007). Each region is clipped to it.
    union = (
        np.asarray(rasterize(weighted.union_polygons, grid), dtype=bool)
        if weighted.union_polygons
        else np.zeros((grid.rows, grid.cols), dtype=bool)
    )
    # Region ids let us find the cells that sit on a seam without a second
    # geometric pass: an id that differs from any neighbour's is a boundary
    # cell, and the painter's classification of it is the ambiguous one.
    ids = np.zeros((grid.rows, grid.cols), dtype=np.int16)
    overlap = np.zeros((grid.rows, grid.cols), dtype=bool)
    for index, region in enumerate(regions):
        shaded = np.asarray(rasterize(region.polygons, grid), dtype=bool) & union
        overlap |= shaded & (ids != 0)      # two regions' paths claimed this cell
        factor = np.where(
            shaded, np.minimum(factor, np.float32(region.transmittance)), factor
        )
        ids[shaded] = index + 1
    # Edge replication: the map's border is not a region seam.
    padded = np.pad(ids, 1, mode="edge")
    seam = np.zeros(ids.shape, dtype=bool)
    for dr in (0, 1, 2):
        for dc in (0, 1, 2):
            if dr == 1 and dc == 1:
                continue
            seam |= padded[dr:dr + ids.shape[0], dc:dc + ids.shape[1]] != ids
    # … and the two painter failures a neighbour comparison cannot see: a cell
    # two paths claimed, and a union cell no region path painted (an isolated
    # sliver). Both are decided by the geometry below.
    seam |= overlap | (union & (ids == 0))
    if not seam.any():
        return factor
    rows, cols = np.nonzero(seam)
    inside = union[rows, cols]
    if not inside.any():
        return factor
    rows, cols = rows[inside], cols[inside]
    points = np.asarray(
        [grid.cell_center(int(row), int(col)) for row, col in zip(rows, cols, strict=True)],
        dtype=float,
    )
    # Start from what the raster gave the cell: for an outer boundary cell that
    # is its own region's transmittance — NOT the darkest transmittance on the
    # plan, which would turn a pergola's edge black because a house exists (#1007
    # review). Only a cell no region painted falls back to the darkest shade.
    resolved = factor[rows, cols].copy()
    ids_here = ids[rows, cols]
    claimed = np.zeros(len(points), dtype=bool)
    # darkest first: a point on two regions' shared edge takes the darker shade,
    # as the min() above would have given it
    for region in sorted(regions, key=lambda candidate: candidate.transmittance):
        inside_region = points_in_polygons(region.polygons, points) & ~claimed
        if inside_region.any():
            resolved[inside_region] = np.float32(region.transmittance)
            claimed |= inside_region
    unresolved = (ids_here == 0) & ~claimed
    if unresolved.any():
        resolved[unresolved] = np.float32(
            min(region.transmittance for region in regions)
        )
    factor[rows, cols] = resolved
    return factor


def _footprint_centroid(
    footprints: tuple[tuple[tuple[float, float], ...], ...]
) -> tuple[float, float]:
    """The mean of a caster's footprint vertices: inside for a plant's ring."""
    xs = [x for ring in footprints for x, _y in ring]
    ys = [y for ring in footprints for _x, y in ring]
    if not xs:
        return (0.0, 0.0)
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _plant_shade_spares(
    identified: Sequence[IdentifiedCaster], grid: HeatmapGrid
) -> tuple[np.ndarray, np.ndarray] | None:
    """The grid cells inside a plant's own footprint, and the casters it is spared.

    #830 (owner decision): a plant does not shade the cells inside its own
    footprint, and neither does the soil solid it stands in — the rule the plant's
    own estimate already follows (``SunReceiver``'s own solid and soil parent).
    Returns ``(flat_cell_indices, spared)`` where ``spared[row, caster]`` is true
    for the plant that owns that cell and every ``holds_plants`` caster whose
    outline contains the plant's centre; ``None`` with no plant in the plan.

    The membership is static for a run (casters do not move between samples), so
    it is answered once, on cell centres, with the caster walk's own footprints.
    """
    plants = [index for index, caster in enumerate(identified) if caster.is_plant]
    if not plants:
        return None
    cell_spares: dict[int, set[int]] = {}
    for index in plants:
        plant = identified[index]
        spared: set[int] = {index}
        centre = np.asarray([_footprint_centroid(plant.footprints)], dtype=float)
        for other_index, other in enumerate(identified):
            if (
                other_index != index
                and other.holds_plants
                and other.frame is None      # a framed glasshouse still shades (#830)
                and other.footprints
                and points_in_polygons(other.footprints, centre)[0]
            ):
                spared.add(other_index)
        xs = [x for ring in plant.footprints for x, _y in ring]
        ys = [y for ring in plant.footprints for _x, y in ring]
        if not xs:
            continue
        col0 = max(0, grid.cell_at(min(xs), min(ys))[1])
        col1 = min(grid.cols - 1, grid.cell_at(max(xs), max(ys))[1])
        row0 = max(0, grid.cell_at(min(xs), min(ys))[0])
        row1 = min(grid.rows - 1, grid.cell_at(max(xs), max(ys))[0])
        if col0 > col1 or row0 > row1:
            continue
        local = np.asarray(
            [[grid.cell_center(row, col) for col in range(col0, col1 + 1)]
             for row in range(row0, row1 + 1)],
            dtype=float,
        ).reshape(-1, 2)
        inside = points_in_polygons(plant.footprints, local)
        for offset in np.flatnonzero(inside):
            row = row0 + int(offset) // (col1 - col0 + 1)
            col = col0 + int(offset) % (col1 - col0 + 1)
            cell_spares.setdefault(row * grid.cols + col, set()).update(spared)
    if not cell_spares:
        return None
    cells = np.asarray(sorted(cell_spares), dtype=np.intp)
    matrix = np.zeros((len(cells), len(identified)), dtype=bool)
    for row, flat in enumerate(cells):
        for caster_index in cell_spares[int(flat)]:
            matrix[row, caster_index] = True
    return cells, matrix


def _plant_cell_factors(
    identified: Sequence[IdentifiedCaster],
    owned_polygons: Sequence[list[Polygon]],
    spared: np.ndarray,
    points: np.ndarray,
    elevation_deg: float,
    azimuth_deg: float,
) -> np.ndarray:
    """The sunlight fraction of plant-owned cells, caster by caster, sparing each
    cell's own plant and soil parent — the product the plant estimate computes."""
    factor = np.ones(len(points), dtype=np.float32)
    for index, (caster, owned) in enumerate(
        zip(identified, owned_polygons, strict=True)
    ):
        if not owned:
            continue
        through = caster_transmittance(caster, elevation_deg, azimuth_deg)
        if through >= 1.0:
            continue
        covered = points_in_polygons(owned, points) & ~spared[:, index]
        if covered.any():
            factor[covered] *= np.float32(through)
    return factor


def _aggregate_day(
    casters: Sequence[CasterLike],
    lat_deg: float, lon_deg: float, day: date, grid: HeatmapGrid, rasterize: Rasterizer,
    *, identified: Sequence[IdentifiedCaster] = (), receivers: Sequence[SunReceiver] = (),
    step_minutes: int = SAMPLE_STEP_MINUTES,
    north_angle_deg: float = 0.0,
    include_sample_masks: bool = False,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> SunExposureResult | None:
    samples = daylight_samples(
        lat_deg, lon_deg, day, step_minutes, north_angle_deg=north_angle_deg
    )
    minutes = np.zeros((grid.rows, grid.cols), dtype=np.float32)
    valid = [receiver for receiver in receivers
             if math.isfinite(receiver.x_cm) and math.isfinite(receiver.y_cm)
             and math.isfinite(receiver.elevation_cm)
             and 0 <= grid.cell_at(receiver.x_cm, receiver.y_cm)[0] < grid.rows
             and 0 <= grid.cell_at(receiver.x_cm, receiver.y_cm)[1] < grid.cols]
    points = np.asarray([grid.cell_center(*grid.cell_at(receiver.x_cm, receiver.y_cm))
                         for receiver in valid], dtype=float).reshape(-1, 2)
    # The map cell each receiver stands in; the first receiver in a cell owns it
    # (overlapping plants in one 10 cm cell cannot each show their own value).
    receiver_cell_first: dict[int, int] = {}
    for receiver_index, receiver in enumerate(valid):
        row, col = grid.cell_at(receiver.x_cm, receiver.y_cm)
        receiver_cell_first.setdefault(row * grid.cols + col, receiver_index)
    # caster id -> the receivers it never shades: itself, the plants standing
    # on its soil (``SunReceiver.stands_on``), and — #481 — every plant whose
    # point lies inside a soil container's own outline, linked or not. The
    # containment test is static for a run (casters do not move between
    # samples), so it is answered once here, on the same points the estimate
    # reports, with the caster walk's own footprints.
    spared: dict[str, list[int]] = {}
    for index, receiver in enumerate(valid):
        spared.setdefault(receiver.item_id, []).append(index)
        if receiver.stands_on is not None and receiver.stands_on != receiver.item_id:
            spared.setdefault(receiver.stands_on, []).append(index)
    if len(valid) and any(caster.holds_plants for caster in identified):
        for caster in identified:
            if not caster.holds_plants or caster.frame is not None:
                # #830: a framed glasshouse is not a solid around the plant - its
                # frame must still shade it. Only a soil solid is spared.
                continue
            inside = np.flatnonzero(points_in_polygons(caster.footprints, points))
            if len(inside):
                spared.setdefault(caster.item_id, []).extend(int(index) for index in inside)
    # Share a sweep only at identical elevations. Rounding can remove an obstacle
    # whose top is above the real receiver but below the rounded elevation.
    elevations: dict[float, list[int]] = {}
    for idx, receiver in enumerate(valid):
        elev = receiver.elevation_cm
        key = max(0.0, elev)
        elevations.setdefault(key, []).append(idx)

    # Slice and index once per distinct elevation, outside the daylight loop.
    receiver_groups = []
    for elev, indices in elevations.items():
        if should_cancel is not None and should_cancel():
            return None
        group_indices = np.asarray(indices, dtype=int)
        slice_casters: list[tuple[IdentifiedCaster, GroupedCaster]] = []
        for caster in identified:
            if elev == 0.0:
                slice_casters.append((caster, GroupedCaster(
                    caster.footprints,
                    caster.height_cm,
                    caster.base_cm,
                    caster.roof_triangles,
                    caster.fence_style,
                    caster.fence_points,
                    caster.fence_width_cm,
                    caster.transmittance,
                    caster.frame,
                )))
                continue
            top_cm = caster.base_cm + caster.height_cm
            if top_cm > elev:
                eff_base = max(0.0, caster.base_cm - elev)
                eff_height = top_cm - max(caster.base_cm, elev)
                sliced_roof = _slice_roof_triangles_for_elevation(
                    caster.roof_triangles, caster.base_cm, elev
                )
                slice_casters.append((caster, GroupedCaster(
                    caster.footprints,
                    eff_height,
                    0.0 if sliced_roof else eff_base,
                    sliced_roof,
                    caster.fence_style,
                    caster.fence_points,
                    caster.fence_width_cm,
                    caster.transmittance,
                    _slice_frame_for_elevation(caster.frame, caster.base_cm, elev),
                )))
        exclusions = {caster.item_id: np.isin(group_indices, spared.get(caster.item_id, []))
                      for caster, _ in slice_casters}
        receiver_groups.append((elev, group_indices, points[group_indices], slice_casters, exclusions))
    exposure = np.zeros(len(valid), dtype=np.float32)
    total = len(samples)
    has_porous = any(
        caster.fence_style is not None
        or caster.frame is not None
        or (caster.transmittance is not None and 0.0 < caster.transmittance < 1.0)
        for caster in identified
    )
    packed_cols = (grid.cols + 7) // 8
    keep_masks = (
        include_sample_masks
        and not has_porous
        and (total * grid.rows * packed_cols <= MAX_SAMPLE_SHADE_BYTES)
    )
    masks = np.zeros((total, grid.rows, packed_cols), dtype=np.uint8) if keep_masks else None
    keep_trans = (
        include_sample_masks
        and has_porous
        and (total * grid.rows * grid.cols * 4 <= MAX_SAMPLE_SHADE_BYTES)
    )
    sample_trans = (
        np.ones((total, grid.rows, grid.cols), dtype=np.float32) if keep_trans else None
    )
    ground_grouped = [
        GroupedCaster(
            caster.footprints,
            caster.height_cm,
            caster.base_cm,
            caster.roof_triangles,
            caster.fence_style,
            caster.fence_points,
            caster.fence_width_cm,
            caster.transmittance,
            caster.frame,
        )
        for caster in identified
    ]
    plant_data = _plant_shade_spares(identified, grid) if identified else None
    plant_cells = plant_data[0] if plant_data is not None else None
    plant_spared = plant_data[1] if plant_data is not None else None
    for index, sample in enumerate(samples):
        if should_cancel is not None and should_cancel():
            return None
        sample_elev = max(sample.elevation_deg, MIN_SUN_ELEVATION_DEG)
        owned_polygons: list[list[Polygon]] = []
        weighted: WeightedShadowsResult | None = None
        if has_porous and identified:
            # ONE sweep of the casters for a plan with a weighted shade (#698): the
            # weighted result holds every owner's own shadow too — the very polygons
            # the grouped sweep makes (pinned in ``tests/unit/test_open_frames.py``),
            # so that sweep is not run a second time beside it. An owner that lets
            # all the sun through has no shadow there, and shades no plant.
            weighted = compute_weighted_shadows(
                ground_grouped, sample_elev, sample.azimuth_deg, should_cancel
            )
            if weighted is None:
                return None
            polygons = weighted.union_polygons
            owned_polygons = [owned for owned, _through in weighted.owned_shadows]
        elif identified:
            shadows = compute_grouped_shadows(
                ground_grouped,
                sample_elev, sample.azimuth_deg, should_cancel)
            if shadows is None:
                return None
            polygons, owned_polygons = shadows
        else:
            polygons = compute_scene_shadows(
                casters, sample_elev, sample.azimuth_deg)
        if weighted is not None:
            sun_factor = _weighted_sun_factor(weighted, grid, rasterize)
        elif polygons:
            shaded = np.asarray(rasterize(polygons, grid), dtype=bool)
            sun_factor = np.where(shaded, 0.0, 1.0).astype(np.float32)
        else:
            sun_factor = np.ones((grid.rows, grid.cols), dtype=np.float32)
        if plant_cells is not None and owned_polygons:
            # #830: the cells inside a plant's own footprint are shaded without
            # that plant (and without the soil it stands in): the rule the plant's
            # own estimate already follows, so the map cannot disagree with it.
            plant_rows = plant_cells // grid.cols
            plant_cols = plant_cells % grid.cols
            cell_points = np.asarray(
                [grid.cell_center(int(row), int(col))
                 for row, col in zip(plant_rows, plant_cols, strict=True)],
                dtype=float,
            )
            sun_factor[plant_rows, plant_cols] = _plant_cell_factors(
                identified, owned_polygons, plant_spared, cell_points,
                sample_elev, sample.azimuth_deg,
            )
        if len(valid):
            rx_trans = np.ones(len(valid), dtype=np.float32)
            for elev, group_indices, group_points, slice_casters, exclusions in receiver_groups:
                if elev == 0.0:
                    group_owned = owned_polygons
                else:
                    elevated = compute_grouped_shadows(
                        [gc for _, gc in slice_casters],
                        sample_elev,
                        sample.azimuth_deg, should_cancel,
                    )
                    if elevated is None:
                        return None
                    _, group_owned = elevated
                for (caster, sliced), caster_polygons in zip(slice_casters, group_owned, strict=True):
                    if should_cancel is not None and should_cancel():
                        return None
                    if not caster_polygons:
                        continue
                    mask = points_in_polygons(caster_polygons, group_points)
                    mask[exclusions[caster.item_id]] = False
                    if np.any(mask):
                        # an open frame is weighed as the SLICE this plane's
                        # receivers see (#698); at ground level that is the caster
                        seen = sliced if sliced.frame is not None else caster
                        t_c = (
                            caster_transmittance(seen, sample_elev, sample.azimuth_deg)
                            if has_porous
                            else 0.0
                        )
                        rx_trans[group_indices[mask]] *= np.float32(t_c)

            exposure += float(step_minutes) * rx_trans
            # #830's contract: the map's cell at a plant's centre is the plant's
            # own estimate, so it takes the receiver's factor for this sample —
            # sliced at the plant's soil elevation, with its own solid and soil
            # parent spared (a raised bed's wall, a pergola above it and an
            # overstorey tree are all in that answer). The cell's other
            # footprint cells keep the ground-level rule above.
            if receiver_cell_first:
                flat_factor = sun_factor.reshape(-1)
                for flat_index, receiver_index in receiver_cell_first.items():
                    flat_factor[flat_index] = rx_trans[receiver_index]
        minutes += float(step_minutes) * sun_factor
        if sample_trans is not None:
            sample_trans[index] = sun_factor
        if masks is not None:
            masks[index] = np.packbits(sun_factor < 0.5, axis=1)
        if progress is not None:
            progress(index + 1, total)
    if should_cancel is not None and should_cancel():
        return None
    return SunExposureResult(
        minutes,
        tuple((receiver.item_id, float(value)) for receiver, value in zip(valid, exposure, strict=True)),
        tuple(sample.dt_utc for sample in samples),
        masks,
        sample_trans,
    )

