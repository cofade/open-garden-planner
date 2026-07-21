"""Rendering helpers for the hours-of-sun heatmap (US-E4 redesign).

Qt-free (pattern: ``core/shadow_geometry`` ↔ ``ui/canvas/sun_heatmap``): turns the
aggregated per-cell ``minutes`` grid from ``core/shade_aggregation`` into the
inputs a smooth, contoured overlay needs — a continuous **cool→warm colour ramp**
(deep indigo in deep shade → amber/pale-yellow in full sun; darker = fewer sun
hours) and **iso-contours** (topographic "height lines") at chosen minute
thresholds. Both are pure numpy so this module stays headless and unit-testable;
the ``QImage`` / ``QGraphicsItem`` assembly lives in ``ui/canvas/sun_heatmap``.

Grid convention is ``shade_aggregation``'s: ``grid[r, c]`` is the sun-minutes of
the cell whose centre is scene ``(x0 + (c+0.5)*cell, y0 + (r+0.5)*cell)``; row 0
is the SOUTH edge (scene +y = North, ADR-002). ``iso_segments`` returns points in
**grid coordinates** ``(col, row)`` (floats); the display layer maps them to
scene cm with that same +0.5 cell-centre offset — no Y-flip here (§8.20).
"""

from __future__ import annotations

import numpy as np

#: Cool→warm ramp control stops as ``(fraction, r, g, b, a)`` with fraction in
#: [0, 1] = fewest→most sun. Alpha DECREASES with sun hours: deep shade is the
#: most opaque (the map paints the problem), full sun is barely tinted so a good
#: spot shows the garden through. Single source of truth for every heatmap tint.
_SUN_RAMP_STOPS: tuple[tuple[float, int, int, int, int], ...] = (
    (0.00, 39, 46, 92, 180),   # deep indigo — deep shade, most opaque
    (0.30, 54, 96, 150, 140),  # blue / teal
    (0.55, 70, 141, 96, 110),  # green
    (0.80, 214, 179, 90, 74),  # warm yellow
    (1.00, 250, 233, 181, 32),  # pale amber — full sun, nearly transparent
)


def build_sun_lut(n: int = 256) -> np.ndarray:
    """An ``(n, 4)`` uint8 **RGBA** lookup table, index 0..n-1 = fewest→most sun.

    Each channel is linearly interpolated between ``_SUN_RAMP_STOPS``. Callers
    index it with ``sun_fraction`` scaled to ``[0, n-1]``.
    """
    stops = _SUN_RAMP_STOPS
    fracs = np.array([s[0] for s in stops], dtype=np.float64)
    channels = np.array([s[1:] for s in stops], dtype=np.float64)  # (k, 4)
    xs = np.linspace(0.0, 1.0, n)
    lut = np.empty((n, 4), dtype=np.uint8)
    for ch in range(4):
        lut[:, ch] = np.clip(
            np.round(np.interp(xs, fracs, channels[:, ch])), 0, 255
        ).astype(np.uint8)
    return lut


def sun_fraction(minutes: np.ndarray, daylight_minutes: float) -> np.ndarray:
    """Normalize a sun-minutes grid to ``[0, 1]`` against the day's daylight.

    ``daylight_minutes`` is the full daylight duration for the shown date, so a
    cell sunny all day maps to 1.0 and the ramp uses full contrast. Guards
    ``daylight_minutes <= 0`` (polar night) as all-shade (zeros).
    """
    if daylight_minutes <= 0:
        return np.zeros(minutes.shape, dtype=np.float32)
    return np.clip(minutes / daylight_minutes, 0.0, 1.0).astype(np.float32)


def smooth_field(grid: np.ndarray, passes: int = 2) -> np.ndarray:
    """Edge-padded 3-wide separable box blur, ``passes`` times (≈ Gaussian).

    Softens the hard 0→high shadow boundaries BEFORE contouring, so the
    marching-squares iso-lines read as smooth topographic curves instead of
    grid-aligned staircases. Contour-only: the ramp fill and the toy-case gates
    keep using the raw minutes.
    """
    out = grid.astype(np.float32, copy=True)
    for _ in range(max(0, passes)):
        padded = np.pad(out, ((1, 1), (0, 0)), mode="edge")
        out = (padded[:-2, :] + padded[1:-1, :] + padded[2:, :]) / 3.0
        padded = np.pad(out, ((0, 0), (1, 1)), mode="edge")
        out = (padded[:, :-2] + padded[:, 1:-1] + padded[:, 2:]) / 3.0
    return out


def _edge_point(
    v_a: float,
    v_b: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    threshold: float,
) -> tuple[float, float]:
    """Linear crossing of ``threshold`` on the segment a→b (grid coords)."""
    denom = v_b - v_a
    t = 0.5 if denom == 0 else (threshold - v_a) / denom
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return (ax + t * (bx - ax), ay + t * (by - ay))


Segment = tuple[tuple[float, float], tuple[float, float]]


def iso_segments(grid: np.ndarray, threshold: float) -> list[Segment]:
    """Marching-squares iso-line of ``threshold`` over ``grid``.

    Returns line segments as ``((x1, y1), (x2, y2))`` pairs in **grid**
    coordinates ``(col, row)`` (cell centres at integer indices). Only cells
    whose 2x2 corner block straddles the threshold are visited (found
    vectorized), so cost scales with the contour length, not the grid area.
    Saddle cells (all four edges cross) are split into two segments with a
    fixed, consistent resolution.
    """
    rows, cols = grid.shape
    if rows < 2 or cols < 2:
        return []
    above = grid >= threshold
    tl, tr = above[:-1, :-1], above[:-1, 1:]
    bl, br = above[1:, :-1], above[1:, 1:]
    mixed = ~((tl == tr) & (tl == bl) & (tl == br))
    rr, cc = np.nonzero(mixed)
    g = grid
    segments: list[Segment] = []
    for r, c in zip(rr.tolist(), cc.tolist(), strict=True):
        v_tl, v_tr = g[r, c], g[r, c + 1]
        v_bl, v_br = g[r + 1, c], g[r + 1, c + 1]
        a_tl, a_tr = above[r, c], above[r, c + 1]
        a_bl, a_br = above[r + 1, c], above[r + 1, c + 1]
        top = (
            _edge_point(v_tl, v_tr, c, r, c + 1, r, threshold)
            if a_tl != a_tr
            else None
        )
        right = (
            _edge_point(v_tr, v_br, c + 1, r, c + 1, r + 1, threshold)
            if a_tr != a_br
            else None
        )
        bottom = (
            _edge_point(v_bl, v_br, c, r + 1, c + 1, r + 1, threshold)
            if a_bl != a_br
            else None
        )
        left = (
            _edge_point(v_tl, v_bl, c, r, c, r + 1, threshold)
            if a_tl != a_bl
            else None
        )
        pts = [p for p in (top, right, bottom, left) if p is not None]
        if len(pts) == 2:
            segments.append((pts[0], pts[1]))
        elif len(pts) == 4:  # saddle
            segments.append((top, left))  # type: ignore[arg-type]
            segments.append((right, bottom))  # type: ignore[arg-type]
    return segments


def hour_levels(max_minutes: float) -> list[int]:
    """Whole-hour minute thresholds (60, 120, …) strictly below ``max_minutes``.

    A level equal to the maximum has no cell above it, so it yields no contour;
    excluding it avoids empty passes.
    """
    top = int(max_minutes // 60)
    if top * 60 >= max_minutes:
        top -= 1
    return [h * 60 for h in range(1, top + 1)]
