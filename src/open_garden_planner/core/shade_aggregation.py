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
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

import numpy as np

from .shadow_geometry import (
    MIN_SUN_ELEVATION_DEG,
    Polygon,
    compute_scene_shadows,
)
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

#: Number of bands (``band_index`` returns 0..BAND_COUNT-1).
BAND_COUNT = 4


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


def band_index(sun_minutes: float) -> int:
    """0 = deep shade (<2 h) … 3 = full sun (≥6 h)."""
    index = 0
    for threshold in BAND_THRESHOLDS_MINUTES:
        if sun_minutes >= threshold:
            index += 1
    return index


def band_grid(sun_minutes: np.ndarray) -> np.ndarray:
    """Vectorized ``band_index`` — uint8 band per cell."""
    bands = np.zeros(sun_minutes.shape, dtype=np.uint8)
    for threshold in BAND_THRESHOLDS_MINUTES:
        bands += (sun_minutes >= threshold).astype(np.uint8)
    return bands


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
    casters: Sequence[tuple[Sequence[tuple[float, float]], float | None]],
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

    Grazing samples (0 < α < 0.5°) are counted as daylight but their
    shadows are computed at a clamped 0.5° elevation — the shadow module
    refuses true grazing angles (lengths explode), and at 0.5° a shadow is
    already ~115 m per meter of height, so "everything sunward-shadowed is
    shaded" holds while open cells still collect their dawn/dusk minutes
    (this keeps the winter toy case at exactly 0 and the summer one at the
    oracle's 540).
    """
    samples = daylight_samples(lat_deg, lon_deg, day, step_minutes)
    minutes = np.zeros((grid.rows, grid.cols), dtype=np.float32)
    total = len(samples)
    for index, sample in enumerate(samples):
        if should_cancel is not None and should_cancel():
            return None
        polygons = compute_scene_shadows(
            casters,
            max(sample.elevation_deg, MIN_SUN_ELEVATION_DEG),
            sample.azimuth_deg,
        )
        if polygons:
            shaded = rasterize(polygons, grid)
            minutes += np.where(shaded, 0.0, float(step_minutes))
        else:
            minutes += float(step_minutes)
        if progress is not None:
            progress(index + 1, total)
    return minutes

