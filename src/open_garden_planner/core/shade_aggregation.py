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
    Polygon,
    compute_grouped_shadows,
    compute_scene_shadows,
)
from .sim_clock import SimInstant
from .solar import solar_position

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
    """

    item_id: str
    footprints: tuple[tuple[tuple[float, float], ...], ...]
    height_cm: float
    base_cm: float = 0.0


@dataclass(frozen=True)
class SunReceiver:
    """A plant whose direct sun is estimated, at the ground point under its centre.

    ``stands_on``: the id of the soil parent whose solid the plant stands in (the
    membership half of the base rule: linked to a visible bed, raised bed or
    container that has a height AND its centre inside it —
    ``ui/canvas/footprints.standing_parent``), else None. That parent is under
    the plant, not between it and the sun: it is left out for this receiver
    exactly like the receiver's own solid. Without it every plant in a raised
    bed reads 0 hours — the bed's footprint covers the point all day. Every
    OTHER caster shades the receiver as if it stood on the ground (a stated
    limit of the ground-level estimate).
    """

    item_id: str
    x_cm: float
    y_cm: float
    stands_on: str | None = None


@dataclass(frozen=True)
class SunExposureResult:
    """Ground heatmap plus sparse ground exposure excluding each receiver itself.

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
        """True when the per-sample masks were kept: ``minutes_through`` can answer."""
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
        if self.sample_shade is None:
            raise ValueError("this map kept no per-sample masks")
        shaded = np.unpackbits(self.sample_shade[index], axis=1, count=self.grid.cols)
        return shaded == 0

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
                total += np.where(self.sample_sunlit(index), float(self.step_minutes), 0.0)
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
) -> list[SunSample]:
    """Sun-up sample instants across the UTC civil day, at ``step_minutes``.

    Polar-safe by construction: midwinter at lat 70° yields an empty list
    (polar night), midsummer yields all samples (midnight sun).

    The gate is geometric α > 0 (sun up at all), NOT the shadow module's
    0.5° minimum — dropping the grazing dawn/dusk samples would silently
    undercount every cell's sun by ~10 min/day at Berlin's solstice.
    ``compute_heatmap`` clamps the elevation it feeds the shadow machinery
    instead (see there).
    """
    samples: list[SunSample] = []
    instant = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = instant + timedelta(days=1)
    step = timedelta(minutes=step_minutes)
    while instant < end:
        position = solar_position(lat_deg, lon_deg, instant)
        if position.elevation_deg > 0.0:
            samples.append(
                SunSample(instant, position.elevation_deg, position.azimuth_deg)
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
                            step_minutes=step_minutes, progress=progress, should_cancel=should_cancel)
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
                          progress=progress, should_cancel=should_cancel)


def _aggregate_day(
    casters: Sequence[CasterLike],
    lat_deg: float, lon_deg: float, day: date, grid: HeatmapGrid, rasterize: Rasterizer,
    *, identified: Sequence[IdentifiedCaster] = (), receivers: Sequence[SunReceiver] = (),
    step_minutes: int = SAMPLE_STEP_MINUTES,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> SunExposureResult | None:
    samples = daylight_samples(lat_deg, lon_deg, day, step_minutes)
    minutes = np.zeros((grid.rows, grid.cols), dtype=np.float32)
    valid = [receiver for receiver in receivers
             if math.isfinite(receiver.x_cm) and math.isfinite(receiver.y_cm)
             and 0 <= grid.cell_at(receiver.x_cm, receiver.y_cm)[0] < grid.rows
             and 0 <= grid.cell_at(receiver.x_cm, receiver.y_cm)[1] < grid.cols]
    points = np.asarray([grid.cell_center(*grid.cell_at(receiver.x_cm, receiver.y_cm))
                         for receiver in valid], dtype=float).reshape(-1, 2)
    # caster id -> the receivers it never shades: itself, and the plants standing
    # on its soil (``SunReceiver.stands_on``)
    spared: dict[str, list[int]] = {}
    for index, receiver in enumerate(valid):
        spared.setdefault(receiver.item_id, []).append(index)
        if receiver.stands_on is not None and receiver.stands_on != receiver.item_id:
            spared.setdefault(receiver.stands_on, []).append(index)
    exposure = np.zeros(len(valid), dtype=np.float32)
    total = len(samples)
    packed_cols = (grid.cols + 7) // 8
    keep_masks = total * grid.rows * packed_cols <= MAX_SAMPLE_SHADE_BYTES
    masks = np.zeros((total, grid.rows, packed_cols), dtype=np.uint8) if keep_masks else None
    for index, sample in enumerate(samples):
        if should_cancel is not None and should_cancel():
            return None
        owned_polygons: list[list[Polygon]] = []
        if identified:
            shadows = compute_grouped_shadows(
                [GroupedCaster(caster.footprints, caster.height_cm, caster.base_cm)
                 for caster in identified],
                max(sample.elevation_deg, MIN_SUN_ELEVATION_DEG), sample.azimuth_deg, should_cancel)
            if shadows is None:
                return None
            polygons, owned_polygons = shadows
        else:
            polygons = compute_scene_shadows(
                casters, max(sample.elevation_deg, MIN_SUN_ELEVATION_DEG), sample.azimuth_deg)
        if polygons:
            shaded = rasterize(polygons, grid)
            minutes += np.where(shaded, 0.0, float(step_minutes))
            if masks is not None:
                masks[index] = np.packbits(np.asarray(shaded, dtype=bool), axis=1)
        else:
            minutes += float(step_minutes)
        if len(valid):
            coverage = np.zeros(len(valid), dtype=np.int32)
            for caster, caster_polygons in zip(identified, owned_polygons, strict=True):
                if should_cancel is not None and should_cancel():
                    return None
                mask = points_in_polygons(caster_polygons, points)
                indices = spared.get(caster.item_id)
                if indices:
                    mask[indices] = False
                coverage += mask
            exposure += np.where(coverage == 0, float(step_minutes), 0.0)
        if progress is not None:
            progress(index + 1, total)
    if should_cancel is not None and should_cancel():
        return None
    return SunExposureResult(minutes, tuple((receiver.item_id, float(value))
                                           for receiver, value in zip(valid, exposure, strict=True)),
                             tuple(sample.dt_utc for sample in samples), masks)

