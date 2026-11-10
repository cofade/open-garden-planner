"""Measurements of a rendered 3D frame — plain numpy, no Qt, no app (Phase 17 L1.4).

The instruments of ``scripts/render_beauty_board.py`` and of the looks' render
tier. Each one turns PIXELS into a number an artifact or a truth gate is judged
by; none of them renders, loads a plan or imports the app — the caller hands over
frames as ``(h, w, 3+)`` sRGB arrays and the geometry as plain numbers. That is
what lets ``tests/unit/test_board_probes.py`` check every instrument on synthetic
frames, with a positive control for each, in the GPU-less run.

Ported from the L0 spike's ``probes.py`` (frame statistics, the isolated-dark-pixel
count, the pixel bearing) and extended for what L1.4's gates ask: a PERSPECTIVE
camera (``Pinhole``: our own projection and its inverse, independent of the
engine's), the shadow IoU on a uniform ground grid seen through that camera, the
luminance step across the horizon, and the orientation of a top-down frame.

Frames: sRGB codes, row 0 on top. Scene: x = East, y = North, z = up, centimetres.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]
Mask = NDArray[np.bool_]
Polygon = Sequence[tuple[float, float]]

# ── frame statistics (the board's per-shot numbers) ──────────────────────────

#: An isolated dark pixel: luma under 40 while the mean of its eight neighbours is
#: over 110 — a near-black dot on a lit surface. ``sharpnessAmount`` 0.08 overshot
#: every thin lit/dark edge into them: 1,500-3,100 per daytime frame at 1280x720.
SPECKLE_MAX_LUMA, SPECKLE_MIN_NEIGHBOURS = 40.0, 110.0
#: A channel at or above this is clipped.
CLIPPED_CODE = 254


def luma(rgb: Any) -> Array:
    """Rec. 709 luma of an ``(..., 3+)`` array of sRGB codes."""
    values = np.asarray(rgb, dtype=np.float64)
    return np.asarray(0.2126 * values[..., 0] + 0.7152 * values[..., 1] + 0.0722 * values[..., 2])


def isolated_dark_pixels(rgb: Any) -> int:
    """Pixels darker than ``SPECKLE_MAX_LUMA`` in lit surroundings."""
    values = luma(rgb)
    height, width = values.shape
    padded = np.pad(values, 1, mode="edge")
    around = sum(padded[1 + dy:1 + dy + height, 1 + dx:1 + dx + width]
                 for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)) / 8.0
    return int(((values < SPECKLE_MAX_LUMA) & (around > SPECKLE_MIN_NEIGHBOURS)).sum())


def luminance(rgb: Any) -> Array:
    """Relative LUMINANCE (linear light, 0..1) of an ``(..., 3+)`` array of sRGB codes:
    every channel through the sRGB curve first, then the Rec. 709 weights. Luma is
    the weighted sum of the CODES; a frame at a quarter of the luminance has well
    over half the luma."""
    codes = np.asarray(rgb, dtype=np.float64)[..., :3] / 255.0
    linear = np.where(codes <= 0.04045, codes / 12.92, ((codes + 0.055) / 1.055) ** 2.4)
    return np.asarray(0.2126 * linear[..., 0] + 0.7152 * linear[..., 1] + 0.0722 * linear[..., 2])


def ground_luminance(rgb: Any, camera: Pinhole, margin_rows: int = 3) -> float:
    """The mean LUMINANCE of the rows below the horizon (from ``margin_rows`` under the
    camera's horizon row down): the garden and the meadow without the sky. L7 (#391): a
    sky whose light sits toward a low sun brightens a frame that faces it while the
    garden itself darkens; the mood order is judged on this."""
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    rows, cols = frame.shape[:2]
    first = int(math.ceil(camera.scaled((cols, rows)).horizon_row())) + margin_rows
    first = min(max(first, 0), rows - 1)
    return round(float(luminance(frame[first:]).mean()), 5)


def frame_stats(rgb: Any) -> dict[str, Any]:
    """A board frame's own numbers: isolated dark pixels, the share of pixels with a
    clipped channel (per cent), the mean luma (codes) and the mean luminance (linear)."""
    values = np.asarray(rgb, dtype=np.float64)[..., :3]
    return {"isolated_dark_px": isolated_dark_pixels(values),
            "clipped_pct": round(float((values.max(axis=2) >= CLIPPED_CODE).mean()) * 100.0, 3),
            "mean_luma": round(float(luma(values).mean()), 2),
            "mean_luminance": round(float(luminance(values).mean()), 5)}


# ── our own camera ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Pinhole:
    """A perspective camera as plain arithmetic: ``eye`` looking at ``target`` with the
    world's up, a VERTICAL field of view, an image of ``size`` = (width, height) pixels.

    Independent of the engine: it knows nothing but the shot's own numbers, so a
    mirrored or swapped engine mapping cannot agree with it.
    """

    eye: tuple[float, float, float]
    target: tuple[float, float, float]
    fov_deg: float
    size: tuple[int, int]

    def _basis(self) -> tuple[Array, Array, Array, Array]:
        eye = np.asarray(self.eye, dtype=np.float64)
        forward = np.asarray(self.target, dtype=np.float64) - eye
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
        right /= np.linalg.norm(right)
        return eye, forward, right, np.cross(right, forward)

    @property
    def _focal(self) -> float:
        """Pixels per unit of tan(angle): half the height over tan(half the fov)."""
        return (self.size[1] / 2.0) / math.tan(math.radians(self.fov_deg) / 2.0)

    def project(self, points: Any) -> tuple[Array, Array, Mask]:
        """Scene points ``(n, 3)`` -> pixel ``x``, ``y`` (continuous; pixel (i, j) covers
        [i, i+1) x [j, j+1)) and whether each lies in front of the camera."""
        eye, forward, right, up = self._basis()
        offsets = np.atleast_2d(np.asarray(points, dtype=np.float64)) - eye
        depth = offsets @ forward
        safe = np.where(depth > 1e-6, depth, 1.0)
        x = self.size[0] / 2.0 + (offsets @ right) / safe * self._focal
        y = self.size[1] / 2.0 - (offsets @ up) / safe * self._focal
        return x, y, depth > 1e-6

    def rays(self, x: Any, y: Any) -> Array:
        """World directions (not normalised) through pixel positions ``x``, ``y``."""
        _eye, forward, right, up = self._basis()
        cam_x = (np.asarray(x, dtype=np.float64) - self.size[0] / 2.0) / self._focal
        cam_y = (self.size[1] / 2.0 - np.asarray(y, dtype=np.float64)) / self._focal
        return np.asarray(forward + cam_x[..., None] * right + cam_y[..., None] * up)

    def bearing_deg(self, x: float, y: float) -> float:
        """Compass bearing (clockwise from north) of the direction through a pixel."""
        ray = self.rays(np.array(x), np.array(y))
        return float(math.degrees(math.atan2(ray[0], ray[1])) % 360.0)

    def elevation_deg(self, x: float, y: float) -> float:
        """Elevation above the horizon of the direction through a pixel."""
        ray = self.rays(np.array(x), np.array(y))
        return float(math.degrees(math.atan2(ray[2], math.hypot(ray[0], ray[1]))))

    def horizon_row(self) -> float:
        """The image row of the geometric horizon straight ahead (elevation 0)."""
        _eye, forward, _right, _up = self._basis()
        pitch = math.atan2(forward[2], math.hypot(forward[0], forward[1]))
        return self.size[1] / 2.0 + math.tan(pitch) * self._focal

    def scaled(self, size: tuple[int, int]) -> Pinhole:
        """The same camera for an image of another size (a grab is in DEVICE pixels)."""
        return Pinhole(self.eye, self.target, self.fov_deg, size)


def polygon_mask(xs: Any, ys: Any, polygon: Polygon) -> Mask:
    """Which of the points ``(xs, ys)`` lie inside ``polygon`` (even-odd rule)."""
    x = np.asarray(xs, dtype=np.float64)
    y = np.asarray(ys, dtype=np.float64)
    inside = np.zeros(x.shape, dtype=bool)
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if y1 == y2:
            continue
        crosses = (y1 > y) != (y2 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            at = (x2 - x1) * (y - y1) / (y2 - y1) + x1
        inside ^= crosses & (x < at)
    return inside


def polygons_mask(xs: Any, ys: Any, polygons: Sequence[Polygon]) -> Mask:
    """Even-odd union of several polygons — what the 2D shadow overlay paints."""
    mask = np.zeros(np.asarray(xs).shape, dtype=bool)
    for polygon in polygons:
        mask ^= polygon_mask(xs, ys, polygon)
    return mask


def convex_hull(points: Any) -> list[tuple[float, float]]:
    """The convex hull of 2D points, counter-clockwise (Andrew's monotone chain)."""
    ordered = sorted({(float(x), float(y)) for x, y in np.asarray(points, dtype=np.float64)})
    if len(ordered) < 3:
        return ordered

    def turn(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in ordered:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


# ── gate G2: the shadow of a box, seen in perspective ────────────────────────


def box_silhouette(camera: Pinhole, footprint: Polygon, height: float) -> list[tuple[float, float]]:
    """The image-space outline of a prism over ``footprint`` (a convex one: its
    silhouette is the hull of its projected corners)."""
    corners = [(x, y, z) for x, y in footprint for z in (0.0, height)]
    px, py, _front = camera.project(corners)
    return convex_hull(np.column_stack([px, py]))


def shadow_iou(rgb: Any, camera: Pinhole, footprint: Polygon, height: float,
               analytic: Sequence[Polygon], *, region: tuple[float, float, float, float],
               lit_reference: tuple[float, float, float, float], step_cm: float = 2.0,
               margin_px: float = 2.0) -> dict[str, Any]:
    """IoU of the shadow a frame shows against the analytic 2D shadow — on a uniform
    GROUND grid (``step_cm``), so that the number is an area ratio like the 2D one.

    ``rgb``: the perspective frame. ``camera``: the shot (``size`` is replaced by the
    frame's own). ``footprint`` / ``height``: the box caster. ``analytic``: the 2D
    shadow polygons (``core.shadow_geometry.compute_scene_shadows``). ``region``:
    (east0, north0, east1, north1) of ground to judge. ``lit_reference``: a patch of
    ground the sun certainly reaches.

    A ground point counts when the camera sees it: inside the frame and not behind
    the caster (its pixel outside the caster's silhouette, grown by ``margin_px``),
    and not under the caster. "Shadow" is darker than halfway between the lit
    ground and the darkest ground in the region — measured from the frame, not from
    the answer.
    """
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    rows, cols = frame.shape[:2]
    view = camera.scaled((cols, rows))
    values = luma(frame)

    def sample(east0: float, north0: float, east1: float, north1: float
               ) -> tuple[Array, Array, Array, Mask]:
        east = np.arange(east0 + step_cm / 2.0, east1, step_cm)
        north = np.arange(north0 + step_cm / 2.0, north1, step_cm)
        xs, ys = np.meshgrid(east, north)
        px, py, front = view.project(np.column_stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)]))
        col, row = np.floor(px).astype(np.int64), np.floor(py).astype(np.int64)
        seen = front & (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
        picked = np.full(xs.size, np.nan)
        picked[seen] = values[row[seen], col[seen]]
        outline = box_silhouette(view, footprint, height)
        centre = np.mean(np.asarray(outline), axis=0)
        grown = [(x + (x - centre[0]) / max(math.hypot(x - centre[0], y - centre[1]), 1e-9) * margin_px,
                  y + (y - centre[1]) / max(math.hypot(x - centre[0], y - centre[1]), 1e-9) * margin_px)
                 for x, y in outline]
        hidden = polygon_mask(px, py, grown)
        return xs, ys, picked.reshape(xs.shape), (seen & ~hidden).reshape(xs.shape)

    xs, ys, seen_luma, visible = sample(*region)
    visible &= ~polygon_mask(xs, ys, footprint)
    _lx, _ly, lit_luma, lit_seen = sample(*lit_reference)
    if not lit_seen.any() or not visible.any():
        return {"iou": 0.0, "measured_cells": 0, "analytic_cells": 0, "visible_cells": 0,
                "lit_luma": None, "threshold": None}
    lit = float(np.median(lit_luma[lit_seen]))
    dark = float(np.percentile(seen_luma[visible], 2.0))
    threshold = (lit + dark) / 2.0
    measured = visible & (seen_luma < threshold)
    expected = visible & polygons_mask(xs, ys, analytic)
    union = int((measured | expected).sum())
    both = int((measured & expected).sum())
    out: dict[str, Any] = {
        "iou": round(both / union, 4) if union else 0.0,
        "measured_cells": int(measured.sum()), "analytic_cells": int(expected.sum()),
        "visible_cells": int(visible.sum()), "lit_luma": round(lit, 1), "dark_luma": round(dark, 1),
        "threshold": round(threshold, 1), "step_cm": step_cm}
    for name, mask in (("centroid_measured_cm", measured), ("centroid_analytic_cm", expected)):
        out[name] = ([round(float(xs[mask].mean()), 1), round(float(ys[mask].mean()), 1)]
                     if mask.any() else None)
    return out


# ── gate G4: where the sky draws its sun ─────────────────────────────────────


def _largest_blob(mask: Any, *, compact_only: bool = False) -> tuple[Any, int]:
    """The largest 4-connected component of a boolean mask, and its pixel count.

    A sun disc is one compact plateau. The centroid of every white pixel in the sky
    merges two separate blobs into a point between them (a false sun at 180° from two
    blobs at 160° and 200°); the component is what makes "plateau" true. With
    ``compact_only`` a component must also be at most 4:1 in bounding box and at least
    40 % filled — a clipped white band is not a disc, and taking the largest component
    first would let it hide the real one."""
    white = np.asarray(mask, dtype=bool)
    seen = np.zeros_like(white, dtype=bool)
    best = np.zeros_like(white, dtype=bool)
    best_count = 0
    rows, cols = white.shape
    for row, col in zip(*np.nonzero(white), strict=False):
        if seen[row, col]:
            continue
        stack = [(int(row), int(col))]
        seen[row, col] = True
        cells: list[tuple[int, int]] = []
        while stack:
            current_row, current_col = stack.pop()
            cells.append((current_row, current_col))
            for delta_row, delta_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                next_row, next_col = current_row + delta_row, current_col + delta_col
                if (0 <= next_row < rows and 0 <= next_col < cols
                        and white[next_row, next_col] and not seen[next_row, next_col]):
                    seen[next_row, next_col] = True
                    stack.append((next_row, next_col))
        if compact_only:
            cell_rows = [cell[0] for cell in cells]
            cell_cols = [cell[1] for cell in cells]
            height = max(cell_rows) - min(cell_rows) + 1
            width = max(cell_cols) - min(cell_cols) + 1
            if (max(width, height) > 4 * max(1, min(width, height))
                    or len(cells) < 0.4 * width * height):
                continue
        if len(cells) > best_count:
            best_count = len(cells)
            best = np.zeros_like(white, dtype=bool)
            for cell_row, cell_col in cells:
                best[cell_row, cell_col] = True
    return best, best_count


def sun_disc(rgb: Any, camera: Pinhole) -> dict[str, Any]:
    """The compass bearing and the elevation of the sky's sun disc in a frame that
    looks at the sky.

    A disc at a low sun can be dimmer than the warm horizon band around it, so the
    finder first looks for the disc's own signature — the largest 4-connected plateau
    of at least 20 pixels with every channel at least 250 — and takes its centroid
    (#717; worst measured error 0.13°). A compactness test (bounding box at most 4:1,
    at least 40 % filled) keeps a thin white streak from reading as a disc. When no
    such plateau exists it falls back to the peak of "bright AND warm" above the
    horizon. ``found`` is False when nothing stands out (contrast of the peak over the
    median at most 40) — a sky without a disc, a night sky.
    """
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    rows, cols = frame.shape[:2]
    view = camera.scaled((cols, rows))
    band = max(1, min(rows, int(math.floor(view.horizon_row()))))
    sky = frame[:band]
    score = luma(sky) + 0.8 * (sky[:, :, 0] - sky[:, :, 2])
    median = float(np.median(score))
    white = np.all(sky >= 250.0, axis=2)
    plateau, count = _largest_blob(white, compact_only=True)
    if count >= 20:
        plateau_rows, plateau_cols = np.nonzero(plateau)
        contrast = float(np.median(score[plateau_rows, plateau_cols])) - median
        if contrast > 40.0:
            x, y = float(plateau_cols.mean()) + 0.5, float(plateau_rows.mean()) + 0.5
            return {"found": True, "contrast": round(contrast, 1),
                    "pixel": [round(x, 1), round(y, 1)], "plateau_px": count,
                    "bearing_deg": round(view.bearing_deg(x, y), 2),
                    "elevation_deg": round(view.elevation_deg(x, y), 2)}
    row, col = np.unravel_index(int(np.argmax(score)), score.shape)
    contrast = float(score[row, col] - median)
    if contrast <= 40.0:
        return {"found": False, "contrast": round(contrast, 1)}
    # the warm peak is a plateau too: take the centre of everything within 2 % of it
    peak = score >= score[row, col] - 0.02 * abs(float(score[row, col]))
    peak_rows, peak_cols = np.nonzero(peak)
    x, y = float(peak_cols.mean()) + 0.5, float(peak_rows.mean()) + 0.5
    return {"found": True, "contrast": round(contrast, 1), "pixel": [round(x, 1), round(y, 1)],
            "bearing_deg": round(view.bearing_deg(x, y), 2),
            "elevation_deg": round(view.elevation_deg(x, y), 2)}


def sun_dip(rgb: Any, camera: Pinhole, sun_azimuth_deg: float, *,
            sun_elevation_deg: float | None = None, near_deg: float = 10.0,
            away_deg: tuple[float, float] = (15.0, 45.0),
            near_elevation_deg: float = 1.5) -> dict[str, Any]:
    """The darkest sky pixel near the sun's bearing against the same WORLD ELEVATION
    away from it.

    The set-sun gate's instrument (#695): a black disc or a dark halo shows as the
    darkest pixel within ``near_deg`` of ``sun_azimuth_deg`` against the median luma
    ``away_deg`` to either side AT THE SAME WORLD ELEVATION; a sky that matches itself
    stays near 0. (An image row is not a world elevation with a pitched pinhole camera:
    off-axis pixels in one row sit higher in the sky, which read a false 20-luma dip.)
    A mean would drown a small disc in the glow around it — a 36-pixel black disc left
    the row mean 16 luma above the away rows. The statistic is the band's 2nd percentile,
    not its minimum: one stray dark pixel read −155 luma against a 10-luma bound whose
    legitimate baseline is 6–8, while a disc covering a fifth of the band still reads 0.
    ``dip_luma`` is the most negative difference and ``elevation_deg`` its 0.25-degree
    band. With
    ``sun_elevation_deg``, only bands within ``near_elevation_deg`` of the sun's own
    elevation count: under partial cloud an isolated cumulus elsewhere in the sky is
    legitimately dark (it read a 48-luma "dip" 6.6° above a 0.4° sun), but the disc's
    own rows are where a black sun hides. Used on a sky-only frame (``ground=None``),
    so a sun below the geometric horizon is still measured. ``measured`` is False when
    no band had both a near and an away sample: a gate must fail closed, not read that
    as a clean sky.
    """
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    rows, cols = frame.shape[:2]
    view = camera.scaled((cols, rows))
    xs, ys = np.meshgrid(np.arange(cols) + 0.5, np.arange(rows) + 0.5)
    rays = view.rays(xs, ys)
    rays /= np.linalg.norm(rays, axis=2, keepdims=True)
    bearing = (np.degrees(np.arctan2(rays[..., 0], rays[..., 1])) + 360.0) % 360.0
    off = np.abs(((bearing - sun_azimuth_deg + 180.0) % 360.0) - 180.0)
    near = off <= near_deg
    away = (off >= away_deg[0]) & (off <= away_deg[1])
    lum = luma(frame)
    elevation = np.degrees(np.arcsin(np.clip(rays[..., 2], -1.0, 1.0)))
    band_deg = 0.25
    bands = np.floor(elevation / band_deg).astype(np.int64)
    reference: dict[int, float] = {}
    for band in np.unique(bands[away]):
        values = lum[away & (bands == band)]
        if values.size >= 10:
            reference[int(band)] = float(np.median(values))
    centre_band = (None if sun_elevation_deg is None
                   else int(np.floor(sun_elevation_deg / band_deg)))
    dip, at_band = 0.0, None
    for band in np.unique(bands[near]):
        if int(band) not in reference:
            continue
        if centre_band is not None and abs(int(band) - centre_band) * band_deg > near_elevation_deg:
            continue
        values = lum[near & (bands == band)]
        if values.size < 3:
            continue
        delta = float(np.percentile(values, 2.0) - reference[int(band)])
        if at_band is None or delta < dip:
            dip, at_band = delta, int(band)
    out: dict[str, Any] = {"dip_luma": round(dip, 2), "band": at_band,
                           "measured": at_band is not None}
    if at_band is not None:
        out["elevation_deg"] = round((at_band + 0.5) * band_deg, 2)
    return out


def bearing_error_deg(measured: float, expected: float) -> float:
    """Signed difference of two compass bearings, in (-180, 180]."""
    return ((measured - expected + 180.0) % 360.0) - 180.0


# ── gate G5: fog meets sky ───────────────────────────────────────────────────


def outer_row_step(rgb: Any) -> dict[str, float | int]:
    """Largest adjacent-row luma change in either outer 18% band (#618).

    Average each side separately before comparing rows, so a cliff on one side
    cannot disappear by cancelling a cliff of the opposite sign on the other.
    """
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    width = max(1, int(math.ceil(frame.shape[1] * 0.18)))
    # The two-pixel postprocessing border samples outside the viewport. It is not
    # a world-space horizon/ground row and is reported separately from the gate.
    border = min(2, max(0, (frame.shape[0] - 2) // 2))
    valid = frame[border:frame.shape[0] - border]
    bands = (luma(valid[:, :width]).mean(axis=1), luma(valid[:, -width:]).mean(axis=1))
    steps = [float(np.abs(np.diff(band)).max()) if len(band) > 1 else 0.0 for band in bands]
    two_rows = [float(np.abs(band[2:] - band[:-2]).max()) if len(band) > 2 else 0.0 for band in bands]
    full_bands = (luma(frame[:, :width]).mean(axis=1), luma(frame[:, -width:]).mean(axis=1))
    full_deltas = [np.abs(np.diff(band)) for band in full_bands]
    full_step = max((float(delta.max()) for delta in full_deltas if len(delta)), default=0.0)
    border_step = max((float(value) for delta in full_deltas
                       for value in np.concatenate((delta[:border], delta[-border:]))),
                      default=0.0) if border else 0.0
    return {"step": round(max(steps), 3), "left_step": round(steps[0], 3),
            "right_step": round(steps[1], 3), "two_row_step": round(max(two_rows), 3),
            "full_step": round(full_step, 3), "border_step": round(border_step, 3),
            "columns_per_side": width, "rows_excluded_each_edge": border}


def horizon_step(rgb: Any, camera: Pinhole, *, reach_deg: float = 0.4, line_deg: float = 0.25,
                 step_deg: float = 0.15, columns: tuple[float, float] = (0.0, 1.0)) -> dict[str, Any]:
    """How the fogged ground meets the sky at the geometric horizon — three numbers
    of the row-mean luma within ``reach_deg`` of the horizon. (0.4 degrees: from eye
    height the fog is complete beyond 160 m, which is 0.59 degrees under the horizon.
    Further down the meadow shows through the fog — at night it is brighter than the
    sky — and that is the fog's own depth curve, not how fog meets sky.)

    ``step``   the largest change across ``step_deg`` of elevation (at least one row,
               so the number does not grow with the frame's size): a CLIFF where the
               meadow meets the sky (the low preset without fog: 84.5 luma in one row);
    ``dip``    how far the darkest row lies under BOTH the rows ``line_deg`` above
               and below it: a thin dark line (the sky's ground hemisphere reaching
               its dark end within a texel: 9-10 luma);
    ``ridge``  the same for a thin BRIGHT line (a fog brighter than the sky it meets).

    ``sky_luma`` / ``ground_luma``: the means just above and below, for the record.
    ``delta_e``: CIE76 colour difference between the sky from 0.4° above the horizon
    down to it and the ground 0.6° to 2° under it — the HUE seam that the luma rows
    cannot see (a grey-blue horizon over a lime meadow: ΔE 59.6 at noon for a luma
    difference of 7.5). Reported, not gated.
    ``columns``: the share of the image width to use (to keep a sun disc out).
    """
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    rows, cols = frame.shape[:2]
    view = camera.scaled((cols, rows))
    horizon = view.horizon_row()
    per_degree = math.tan(math.radians(1.0)) * view._focal
    left, right = int(columns[0] * cols), max(int(columns[1] * cols), int(columns[0] * cols) + 1)
    row_luma = luma(frame[:, left:right]).mean(axis=1)
    apart = max(2, int(round(line_deg * per_degree)))
    first = max(int(math.floor(horizon - reach_deg * per_degree)), apart)
    last = min(int(math.ceil(horizon + reach_deg * per_degree)), rows - 1 - apart)
    if last <= first:
        return {"step": 0.0, "dip": 0.0, "ridge": 0.0, "horizon_row": round(horizon, 1),
                "rows_per_degree": round(per_degree, 2), "judged_rows": 0}
    near = row_luma[first:last + 1]
    above, below = row_luma[first - apart:last + 1 - apart], row_luma[first + apart:last + 1 + apart]
    span = max(1, int(round(step_deg * per_degree)))
    step = float(np.abs(near[span:] - near[:-span]).max()) if near.size > span else 0.0
    dip = max(0.0, float((np.minimum(above, below) - near).max()))
    ridge = max(0.0, float((near - np.maximum(above, below)).max()))
    row_rgb = frame[:, left:right].mean(axis=1)
    sky_rows = row_rgb[max(0, int(math.floor(horizon - 0.4 * per_degree))):max(1, int(math.floor(horizon)))]
    ground_rows = row_rgb[min(rows - 1, int(math.ceil(horizon + 0.6 * per_degree))):
                          min(rows, int(math.ceil(horizon + 2.0 * per_degree)) + 1)]
    delta_e = (delta_e76(sky_rows.mean(axis=0), ground_rows.mean(axis=0))
               if len(sky_rows) and len(ground_rows) else None)
    return {"step": round(step, 2), "dip": round(dip, 2), "ridge": round(ridge, 2),
            "delta_e": None if delta_e is None else round(delta_e, 1),
            "sky_luma": round(float(row_luma[first - apart:first].mean()), 2),
            "ground_luma": round(float(row_luma[last + 1:last + 1 + apart].mean()), 2),
            "horizon_row": round(horizon, 1), "rows_per_degree": round(per_degree, 2),
            "judged_rows": int(near.size)}


def srgb_to_lab(rgb: Any) -> Array:
    """CIE L*a*b* (D65) of sRGB codes ``(..., 3)``."""
    codes = np.asarray(rgb, dtype=np.float64)[..., :3] / 255.0
    linear = np.where(codes <= 0.04045, codes / 12.92, ((codes + 0.055) / 1.055) ** 2.4)
    matrix = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]])
    xyz = linear @ matrix.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6.0 / 29.0) ** 3, np.cbrt(xyz), xyz / (3.0 * (6.0 / 29.0) ** 2) + 4.0 / 29.0)
    return np.stack([116.0 * f[..., 1] - 16.0, 500.0 * (f[..., 0] - f[..., 1]),
                     200.0 * (f[..., 1] - f[..., 2])], axis=-1)


def delta_e76(first: Any, second: Any) -> float:
    """CIE76 colour difference of two sRGB colours (codes)."""
    return float(np.linalg.norm(srgb_to_lab(first) - srgb_to_lab(second)))


# ── the plan rectangle meets the meadow ──────────────────────────────────────


#: The LINE along the plan's edge (``plan_edge_step``): the pixels within this many of
#: the edge's own pixel, against the median of a window this many either side (px).
EDGE_LINE_PX = 3
EDGE_LINE_WINDOW_PX = 12


def plan_edge_step(rgb: Any, camera: Pinhole, *, axis: str, at: float, along: Sequence[float],
                   reach: tuple[float, float] = (20.0, 220.0), step_cm: float = 10.0
                   ) -> dict[str, Any]:
    """The luma STEP where the plan rectangle meets the meadow along the edge line
    ``east = at`` (``axis="east"``) or ``north = at`` (``axis="north"``), the plan on
    the side of larger coordinates.

    At every station in ``along`` the ground is sampled on a line across the edge,
    ``reach`` cm into the plan and as far into the meadow, and each side is fitted
    with a straight line; the step is the plan's line minus the meadow's AT the edge.
    A smooth gradient across the view (the sky's sheen changes with the angle: here
    about 1.4 luma per metre) is not a step and does not count — two band means 2 m
    apart had read it as one (+4 luma for identical materials). ``step`` is the median
    over the stations.

    ``line`` is what the fits cannot see: a thin bright or dark line ON the edge (3D
    review of #388: ambient occlusion drew one, ±14 luma, along every plan edge while
    the meadow lay 5 cm under the plan, and the step read 0.45). At every station the
    pixels are read across the edge, ``EDGE_LINE_WINDOW_PX`` either side of the edge's
    own pixel; ``line`` is the largest difference from their median within
    ``EDGE_LINE_PX`` of it, the largest over the stations."""
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    rows, cols = frame.shape[:2]
    view = camera.scaled((cols, rows))
    values = luma(frame)
    offsets = np.arange(reach[0], reach[1] + 1e-9, step_cm)
    distances = np.concatenate([-offsets[::-1], offsets])
    steps: list[float] = []
    plan_at: list[float] = []
    meadow_at: list[float] = []
    lines: list[float] = []
    for station in along:
        across = at + distances
        if axis == "east":
            points = np.column_stack([across, np.full_like(across, station), np.zeros_like(across)])
        else:
            points = np.column_stack([np.full_like(across, station), across, np.zeros_like(across)])
        edge = np.array([[at, station, 0.0]] if axis == "east" else [[station, at, 0.0]])
        line = _edge_line(values, view, np.concatenate([edge, points[len(offsets):len(offsets) + 1]]))
        if line is not None:
            lines.append(line)
        px, py, front = view.project(points)
        col, row = np.floor(px).astype(np.int64), np.floor(py).astype(np.int64)
        seen = front & (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
        inside, outside = seen & (distances > 0), seen & (distances < 0)
        if inside.sum() < 3 or outside.sum() < 3:
            continue
        sampled = np.full(distances.shape, np.nan)
        sampled[seen] = values[row[seen], col[seen]]
        plan_line = np.polyfit(distances[inside], sampled[inside], 1)
        meadow_line = np.polyfit(distances[outside], sampled[outside], 1)
        plan_at.append(float(np.polyval(plan_line, 0.0)))
        meadow_at.append(float(np.polyval(meadow_line, 0.0)))
        steps.append(plan_at[-1] - meadow_at[-1])
    if not steps:
        return {"step": None, "stations": 0, "plan_luma": None, "meadow_luma": None,
                "line": None}
    return {"step": round(float(np.median(steps)), 2), "stations": len(steps),
            "plan_luma": round(float(np.median(plan_at)), 2),
            "meadow_luma": round(float(np.median(meadow_at)), 2),
            "line": round(max(lines), 2) if lines else None}


def _edge_line(values: Array, view: Pinhole, pair: Array) -> float | None:
    """``plan_edge_step``'s ``line`` at one station: ``pair`` is the point of the edge
    and a ground point across it, on the plan's side."""
    px, py, front = view.project(pair)
    if not front.all():
        return None
    middle = np.array([px[0], py[0]])
    direction = np.array([px[1] - px[0], py[1] - py[0]])
    length = float(np.hypot(*direction))
    if length < 1e-9:
        return None
    offsets = np.arange(-EDGE_LINE_WINDOW_PX, EDGE_LINE_WINDOW_PX + 1)
    cols = np.floor(middle[0] + offsets * direction[0] / length).astype(np.int64)
    rows = np.floor(middle[1] + offsets * direction[1] / length).astype(np.int64)
    height, width = values.shape[:2]
    if cols.min() < 0 or rows.min() < 0 or cols.max() >= width or rows.max() >= height:
        return None
    samples = values[rows, cols]
    near = np.abs(offsets) <= EDGE_LINE_PX
    return float(np.abs(samples[near] - np.median(samples)).max())


# ── a long shadow's edge: stair steps (#734) ─────────────────────────────────

#: The view-depth bins (m) a traced shadow edge is reported in. A cascade's texels grow
#: with the distance from the camera: one number over the whole edge hides the far
#: steps behind the clean near ones (PF-L3D-19 — bin by the world quantity).
EDGE_DEPTH_BINS_M = (0.0, 10.0, 20.0, 40.0, 80.0)
#: A station needs this much luma between the shadow's level and the lit level.
EDGE_MIN_CONTRAST = 6.0


def _bilinear(values: Array, px: Array, py: Array) -> Array:
    """``values`` (rows x cols) at continuous pixel positions (pixel (i, j) covers
    [i, i+1) x [j, j+1), its centre at +0.5), bilinearly."""
    rows, cols = values.shape
    x = np.clip(np.asarray(px, dtype=np.float64) - 0.5, 0.0, cols - 1.000001)
    y = np.clip(np.asarray(py, dtype=np.float64) - 0.5, 0.0, rows - 1.000001)
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0
    x1, y1 = np.minimum(x0 + 1, cols - 1), np.minimum(y0 + 1, rows - 1)
    return np.asarray(values[y0, x0] * (1 - fx) * (1 - fy) + values[y0, x1] * fx * (1 - fy)
                      + values[y1, x0] * (1 - fx) * fy + values[y1, x1] * fx * fy)


def shadow_edge_trace(rgb: Any, camera: Pinhole, start: tuple[float, float],
                      end: tuple[float, float], lit_side: tuple[float, float], *,
                      half_width_cm: float, spacing_px: float = 0.5, across: int = 241,
                      min_contrast: float = EDGE_MIN_CONTRAST) -> dict[str, Any]:
    """Where a STRAIGHT shadow edge on the ground (z = 0) lies, all along it.

    ``start`` / ``end``: (east, north) of the analytic edge; ``lit_side``: the unit
    (east, north) normal of it that points out of the shadow. Stations lie along the
    edge ``spacing_px`` apart ON SCREEN (a uniform step in centimetres would give the
    near end a few stations per step and the far end hundreds); at each the ground is
    read on a line across the edge, ``half_width_cm`` either side, ``across`` samples.

    The edge's position is the AREA estimator, not a threshold crossing: with the luma
    normalised between the shadow's level (the median of the inner 40 % on the shadow
    side) and the lit level (the outer 40 % on the lit side), ``f`` in [0, 1], a step
    at ``u*`` gives ``∫ f du = W - u*``. It is sub-pixel, has one answer per station
    even where noise crosses the threshold several times, and a blurred edge sits where
    the sharp one would. A station counts when its whole line is in front of the camera
    and inside the frame, and the two levels differ by ``min_contrast``.

    Returns per station: ``along_cm`` (from ``start``), ``offset_cm`` (+ = toward the lit
    side: the shadow reaches past the analytic line; - = it ends short), ``depth_cm`` (view depth of the
    station's point on the analytic line), ``px_per_cm`` (screen pixels per centimetre
    across the edge there) and ``valid``; and ``spacing_px``."""
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    rows, cols = frame.shape[:2]
    view = camera.scaled((cols, rows))
    values = luma(frame)
    eye, forward, _right, _up = view._basis()
    a, b = np.asarray(start, dtype=np.float64), np.asarray(end, dtype=np.float64)
    length = float(np.linalg.norm(b - a))
    direction = (b - a) / max(length, 1e-9)
    normal = np.asarray(lit_side, dtype=np.float64)
    normal = normal / max(float(np.linalg.norm(normal)), 1e-9)
    empty: dict[str, Any] = {key: np.zeros(0) for key in ("along_cm", "offset_cm", "depth_cm",
                                                         "px_per_cm")}
    empty["spacing_px"] = spacing_px
    # stations uniform on screen: a dense walk, then its screen arc length inverted
    dense = np.linspace(0.0, length, 8001)
    points = np.column_stack([a[0] + dense * direction[0], a[1] + dense * direction[1],
                              np.zeros_like(dense)])
    px, py, front = view.project(points)
    seen = front & (px >= 0) & (px < cols) & (py >= 0) & (py < rows)
    if seen.sum() < 2:
        return {**empty, "valid": np.zeros(0, dtype=bool)}
    first, last = np.flatnonzero(seen)[[0, -1]]
    dense, px, py = dense[first:last + 1], px[first:last + 1], py[first:last + 1]
    arc = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(px), np.diff(py)))])
    along = np.interp(np.arange(0.0, arc[-1], spacing_px), arc, dense)
    u = np.linspace(-half_width_cm, half_width_cm, across)
    east = a[0] + along[:, None] * direction[0] + u[None, :] * normal[0]
    north = a[1] + along[:, None] * direction[1] + u[None, :] * normal[1]
    grid = np.column_stack([east.ravel(), north.ravel(), np.zeros(east.size)])
    gx, gy, gfront = view.project(grid)
    gx, gy = gx.reshape(east.shape), gy.reshape(east.shape)
    inside = (gfront.reshape(east.shape) & (gx >= 0) & (gx < cols) & (gy >= 0) & (gy < rows)).all(axis=1)
    profile = _bilinear(values, gx, gy)
    inner = u <= -0.6 * half_width_cm
    outer = u >= 0.6 * half_width_cm
    dark = np.median(profile[:, inner], axis=1)
    lit = np.median(profile[:, outer], axis=1)
    contrast = lit - dark
    share = np.clip((profile - dark[:, None]) / np.where(contrast > 1e-9, contrast, 1.0)[:, None], 0.0, 1.0)
    offset = half_width_cm - np.trapezoid(share, u, axis=1)
    # the screen scale across the edge, and each station's view depth
    on_line = np.column_stack([a[0] + along * direction[0], a[1] + along * direction[1],
                               np.zeros_like(along)])
    ox, oy, _f = view.project(on_line)
    nx, ny, _f = view.project(on_line + np.array([normal[0], normal[1], 0.0]))
    tx, ty, _f = view.project(on_line + np.array([direction[0], direction[1], 0.0]))
    tangent = np.column_stack([tx - ox, ty - oy])
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1), 1e-12)[:, None]
    shift = np.column_stack([nx - ox, ny - oy])
    px_per_cm = np.abs(shift[:, 0] * tangent[:, 1] - shift[:, 1] * tangent[:, 0])
    depth = (on_line - eye) @ forward
    return {"along_cm": along, "offset_cm": offset, "depth_cm": depth, "px_per_cm": px_per_cm,
            "valid": inside & (contrast >= min_contrast), "spacing_px": spacing_px}


def edge_staircase(trace: dict[str, Any], *, bins_m: Sequence[float] = EDGE_DEPTH_BINS_M,
                   keep: Any = None, min_stations: int = 40) -> list[dict[str, Any]]:
    """How far a traced shadow edge (``shadow_edge_trace``) strays from a straight line,
    per view-depth bin. ``keep``: an extra mask of the stations to judge (e.g. away from
    other casters' shadows).

    In each bin the offsets are detrended by a straight line along the edge (a constant
    offset is bias or a caster's own shape; a staircase is what is left). ``wobble_cm``
    / ``wobble_px``: the spread (95th minus 5th percentile) of what is left, in
    centimetres on the ground and in screen pixels across the edge — the size of the
    steps the eye sees. ``jump_px``: the 99th percentile of the change between stations
    one screen pixel apart (a soft edge that wanders is not a staircase; a riser is —
    and a riser can be one station pair in twenty).
    ``offset_cm``: the median offset (+: the shadow reaches past the line, -: short)."""
    valid = np.array(trace["valid"], dtype=bool)   # a copy: the trace is the caller's
    if keep is not None:
        valid &= np.asarray(keep, dtype=bool)
    along, offset = trace["along_cm"], trace["offset_cm"]
    depth_m, scale = trace["depth_cm"] / 100.0, trace["px_per_cm"]
    rows: list[dict[str, Any]] = []
    for low, high in zip(bins_m[:-1], bins_m[1:], strict=True):
        mask = valid & (depth_m >= low) & (depth_m < high)
        count = int(mask.sum())
        row: dict[str, Any] = {"depth_m": [low, high], "stations": count}
        if count < min_stations:
            rows.append(row)
            continue
        s, o, k = along[mask], offset[mask], scale[mask]
        fit = np.polyfit(s, o, 1)
        rest = o - np.polyval(fit, s)
        rest_px = rest * k
        # stations lie spacing_px apart on screen: compare those one pixel apart
        stride = max(1, int(round(1.0 / float(trace["spacing_px"]))))
        jumps = np.abs(np.diff(rest_px[::stride])) if count > stride else np.zeros(1)
        row.update({
            "offset_cm": round(float(np.median(o)), 2),
            "wobble_cm": round(float(np.percentile(rest, 95) - np.percentile(rest, 5)), 2),
            "wobble_px": round(float(np.percentile(rest_px, 95) - np.percentile(rest_px, 5)), 3),
            "jump_px": round(float(np.percentile(jumps, 99)), 3),
            "px_per_cm": round(float(np.median(k)), 4)})
        rows.append(row)
    return rows


def ground_line_luma(rgb: Any, camera: Pinhole, start: tuple[float, float],
                     end: tuple[float, float], *, step_cm: float = 1.0) -> Array:
    """The luma under a ground line ``start`` -> ``end``, every ``step_cm``, where the
    camera sees it (bilinear; points off the frame or behind the camera are left out)."""
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    rows, cols = frame.shape[:2]
    view = camera.scaled((cols, rows))
    a, b = np.asarray(start, dtype=np.float64), np.asarray(end, dtype=np.float64)
    length = float(np.linalg.norm(b - a))
    along = np.arange(0.0, length, step_cm)
    points = a[None, :] + along[:, None] * ((b - a) / max(length, 1e-9))[None, :]
    px, py, front = view.project(np.column_stack([points, np.zeros(len(points))]))
    seen = front & (px >= 1) & (px < cols - 1) & (py >= 1) & (py < rows - 1)
    return _bilinear(luma(frame), px[seen], py[seen])


def lit_share(base: Array, shadow: Array, lit: Array) -> float | None:
    """The share of ``base`` samples brighter than halfway between the medians of
    ``shadow`` and ``lit`` — e.g. how much of a line just behind a caster's foot the
    sun reaches where its shadow should lie (a shadow map's lit teeth under a caster)."""
    if not len(base) or not len(shadow) or not len(lit):
        return None
    threshold = (float(np.median(shadow)) + float(np.median(lit))) / 2.0
    return round(float((np.asarray(base) > threshold).mean()), 4)


def edge_swim(traces: Sequence[dict[str, Any]], *, grid_cm: float = 2.0, smooth_cm: float = 0.0,
              bins_m: Sequence[float] = EDGE_DEPTH_BINS_M) -> list[dict[str, Any]]:
    """How a shadow edge CRAWLS between the frames of a camera move, the sun held still.

    ``traces``: ``shadow_edge_trace`` of the same edge in consecutive frames. The true
    edge does not move in the world, so each trace's offsets are put on one world grid
    along the edge (``grid_cm``) and consecutive frames compared where both saw it. Per
    view-depth bin of the later frame: ``swim_cm`` / ``swim_px``, the 95th percentile of
    the change (in pixels with that frame's scale), and ``pairs`` compared.
    ``smooth_cm``: the offsets are first averaged along the edge over this length. Qt's
    filter turns its samples by a per-PIXEL noise, so a moving camera re-dithers a soft
    edge everywhere; a shadow map's texels that move with the camera shift whole stretches
    of it. Averaged over a few centimetres the dither cancels and a crawl stays."""
    if len(traces) < 2:
        return []
    top = max(float(np.max(t["along_cm"])) for t in traces if len(t["along_cm"]))
    grid = np.arange(0.0, top, grid_cm)

    def on_grid(trace: dict[str, Any]) -> tuple[Array, Array, Array]:
        valid = np.asarray(trace["valid"], dtype=bool)
        along = trace["along_cm"][valid]
        if len(along) < 2:
            nothing = np.full(len(grid), np.nan)
            return nothing, nothing, nothing
        inside = (grid >= along[0]) & (grid <= along[-1])
        values = [np.where(inside, np.interp(grid, along, trace[key][valid]), np.nan)
                  for key in ("offset_cm", "px_per_cm", "depth_cm")]
        # a gap in the valid stations wider than two grid steps is not interpolated across
        gaps = np.interp(grid, along[1:], np.diff(along), left=np.inf, right=np.inf) > 2 * grid_cm
        values = [np.where(gaps, np.nan, value) for value in values]
        width = int(round(smooth_cm / grid_cm))
        if width > 1:   # a running mean that leaves a window touching a gap undefined
            kernel = np.ones(width) / width
            values[0] = np.convolve(values[0], kernel, mode="same")
        return values[0], values[1], values[2]

    sampled = [on_grid(trace) for trace in traces]
    changes_cm: list[Array] = []
    changes_px: list[Array] = []
    depths: list[Array] = []
    for (o0, _k0, _d0), (o1, k1, d1) in zip(sampled[:-1], sampled[1:], strict=True):
        both = np.isfinite(o0) & np.isfinite(o1)
        changes_cm.append(np.abs(o1[both] - o0[both]))
        changes_px.append(np.abs(o1[both] - o0[both]) * k1[both])
        depths.append(d1[both] / 100.0)
    change_cm, change_px, depth = (np.concatenate(changes_cm), np.concatenate(changes_px),
                                   np.concatenate(depths))
    rows: list[dict[str, Any]] = []
    for low, high in zip(bins_m[:-1], bins_m[1:], strict=True):
        mask = (depth >= low) & (depth < high)
        row: dict[str, Any] = {"depth_m": [low, high], "pairs": int(mask.sum())}
        if mask.sum() >= 40:
            row.update({"swim_cm": round(float(np.percentile(change_cm[mask], 95)), 3),
                        "swim_px": round(float(np.percentile(change_px[mask], 95)), 3)})
        rows.append(row)
    return rows


def _longest_run(mask: Any) -> tuple[int, int] | None:
    """[first, last) of the longest run of True in a 1-D mask (None: no True)."""
    flags = np.concatenate([[False], np.asarray(mask, dtype=bool), [False]])
    edges = np.flatnonzero(np.diff(flags.astype(np.int8)))
    if not len(edges):
        return None
    starts, stops = edges[0::2], edges[1::2]
    best = int(np.argmax(stops - starts))
    return int(starts[best]), int(stops[best])


def shadow_streaks(rgb: Any, camera: Pinhole, start: tuple[float, float], end: tuple[float, float],
                   *, period_cm: float, lit_luma: float, step_cm: float = 1.0,
                   min_period_px: float = 8.0) -> dict[str, Any]:
    """How a porous caster's shadow STREAKS along a ground line ``start`` -> ``end``.

    The luma is read every ``step_cm`` along the line and box-filtered over one
    ``period_cm`` (a picket fence's pitch along the line): a pattern that repeats with
    the caster's own period — the true picket stripes, sharp or soft — averages to a
    constant, and what is left is the low-frequency beat a shadow map makes when its
    texels alias the slits (some slits leak a whole texel of light, others none).
    Judged only where one period spans ``min_period_px`` on screen (the longest such
    run of the line): further out the PIXELS alias the true stripes into a moiré of
    their own — the anti-aliasing's business, not the shadow map's.
    ``streak``: the spread (95th minus 5th percentile) of the filtered luma, as a share
    of the contrast between ``lit_luma`` and the line's median luma (``contrast``)."""
    frame = np.asarray(rgb, dtype=np.float64)[..., :3]
    rows, cols = frame.shape[:2]
    view = camera.scaled((cols, rows))
    a, b = np.asarray(start, dtype=np.float64), np.asarray(end, dtype=np.float64)
    length = float(np.linalg.norm(b - a))
    along = np.arange(0.0, length, step_cm)
    points = a[None, :] + along[:, None] * ((b - a) / max(length, 1e-9))[None, :]
    px, py, front = view.project(np.column_stack([points, np.zeros(len(points))]))
    window = max(1, int(round(period_cm / step_cm)))
    spacing = np.hypot(np.gradient(px), np.gradient(py)) if len(px) > 1 else np.zeros(len(px))
    seen = (front & (px >= 1) & (px < cols - 1) & (py >= 1) & (py < rows - 1)
            & (spacing * window >= min_period_px))
    run = _longest_run(seen)
    if run is None or run[1] - run[0] < 3 * window:
        return {"samples": 0 if run is None else run[1] - run[0], "streak": None,
                "mean_luma": None}
    first, last = run
    values = _bilinear(luma(frame), px[first:last], py[first:last])
    smoothed = np.convolve(values, np.ones(window) / window, mode="valid")
    level = float(np.median(values))
    contrast = max(lit_luma - level, 1e-6)
    return {"samples": int(len(values)),
            "streak": round(float(np.percentile(smoothed, 95) - np.percentile(smoothed, 5)) / contrast, 4),
            "mean_luma": round(float(values.mean()), 2), "lit_luma": round(lit_luma, 2),
            "contrast": round(contrast, 2)}


# ── aliasing of thin repeated geometry (picket fences) ───────────────────────

#: A fence pixel this dark (luma) is one the anti-aliasing let alias to near-black.
MOIRE_DARK_LUMA = 40.0


def downsample(rgb: Any, factor: int) -> Array:
    """Box-filter an ``(h·f, w·f, 3+)`` frame down by ``factor`` in LINEAR light, back to
    sRGB codes — the reference a supersampled render gives."""
    codes = np.asarray(rgb, dtype=np.float64)[..., :3] / 255.0
    linear = np.where(codes <= 0.04045, codes / 12.92, ((codes + 0.055) / 1.055) ** 2.4)
    rows, cols = linear.shape[0] // factor, linear.shape[1] // factor
    blocks = linear[:rows * factor, :cols * factor].reshape(rows, factor, cols, factor, 3).mean(axis=(1, 3))
    encoded = np.where(blocks <= 0.0031308, blocks * 12.92, 1.055 * np.power(blocks, 1.0 / 2.4) - 0.055)
    return np.asarray(encoded * 255.0)


def thin_geometry_moire(with_it: Any, without_it: Any, reference: Any = None, *,
                        changed: float = 12.0) -> dict[str, Any]:
    """How a frame that shows thin repeated geometry (``with_it``) aliases. Its pixels
    are those that differ from the same frame WITHOUT it (``without_it``) by more than
    ``changed`` in a channel (the pickets and their shadow).

    ``alias_error``: the mean absolute luma difference over those pixels against
    ``reference`` — the same view rendered at a multiple of the size and box-filtered
    down (``downsample``): what the frame would show with every picket resolved. An
    aliased fence is a moiré of dark slits and bands where the reference is a smooth
    texture; the number does not depend on how dark the pickets are by themselves.
    Also reported: the share darker than ``MOIRE_DARK_LUMA`` and the mean absolute
    Laplacian of the luma (both include the fences' own shaded sides)."""
    a = np.asarray(with_it, dtype=np.float64)[..., :3]
    b = np.asarray(without_it, dtype=np.float64)[..., :3]
    mask = np.abs(a - b).max(axis=2) > changed
    count = int(mask.sum())
    if not count:
        return {"pixels": 0, "dark_share": 0.0, "laplacian": 0.0, "alias_error": None}
    values = luma(a)
    padded = np.pad(values, 1, mode="edge")
    laplacian = np.abs(4.0 * values - padded[:-2, 1:-1] - padded[2:, 1:-1]
                       - padded[1:-1, :-2] - padded[1:-1, 2:])
    error = None
    if reference is not None:
        ref = np.asarray(reference, dtype=np.float64)[..., :3]
        if ref.shape == a.shape:
            error = round(float(np.abs(values - luma(ref))[mask].mean()), 2)
    return {"pixels": count,
            "dark_share": round(float((values[mask] < MOIRE_DARK_LUMA).mean()), 4),
            "laplacian": round(float(laplacian[mask].mean()), 2), "alias_error": error}


# ── north is up: the orientation of a top-down frame ─────────────────────────


def ncc(first: Any, second: Any) -> float:
    """Normalised cross-correlation of two arrays of one shape (0 for a flat one)."""
    a = np.asarray(first, dtype=np.float64)
    b = np.asarray(second, dtype=np.float64)
    a = a - a.mean()
    b = b - b.mean()
    scale = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum() / scale) if scale > 0.0 else 0.0


def orientation_scores(seen: Any, predicted: Any) -> dict[str, Any]:
    """Does a top-down frame show the plan the way OUR projection predicts it?

    ``seen``: what the frame shows (a mask or an image, h x w); ``predicted``: the
    same thing computed on the CPU from the records. The correlation with the
    prediction as it is must beat the correlation with each of its mirror images.
    """
    target = np.asarray(seen, dtype=np.float64)
    made = np.asarray(predicted, dtype=np.float64)
    scores = {"identity": ncc(target, made), "flip_v": ncc(target, made[::-1]),
              "flip_h": ncc(target, made[:, ::-1]), "flip_both": ncc(target, made[::-1, ::-1])}
    best = max(scores, key=lambda name: scores[name])
    return {"ncc": {name: round(value, 4) for name, value in scores.items()},
            "best": best, "ok": best == "identity"}
