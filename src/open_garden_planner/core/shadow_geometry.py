"""Analytic 2D shadow geometry for the sun/shade overlay (US-E3, #258).

Deliberately Qt-free (pattern: ``core/solar``, ``core/object_height``): all
inputs and outputs are plain float tuples in SCENE CENTIMETERS, so the whole
module is unit-testable headless and reusable by the hours-of-sun heatmap
(US-E4) and the 3D view's ground shadows (US-E6).

Coordinate frame (the campaign's central trap — ADR-002, §8.20,
``ogp-qt-cad-reference`` §1): scene coordinates ARE the CAD coordinates —
+x = East, +y = North. A solar azimuth ``Az`` (compass bearing, clockwise
from north) puts the sun's horizontal direction at ``(sin Az, cos Az)``;
the shadow extends OPPOSITE the sun, so the scene-space shadow direction is
``(-sin Az, -cos Az)``. There is NO further Y-flip anywhere in this module —
pixel-facing surfaces (render/export) apply their own flip; re-flipping here
is exactly the mirrored-shadow bug the campaign fences.

Geometry: an extruded footprint of height ``h`` with the sun at elevation
``α`` casts a ground shadow of length ``L = h / tan α`` — the filled
footprint swept along ``D = L·(-sin Az, -cos Az)`` (a Minkowski sum of the
footprint with the segment [(0,0) → D]). pyclipper computes the sweep and
the cross-item union on an integer grid (``CLIPPER_SCALE``, the
``offset_tool`` precedent — pyclipper is integer-only).

``pyclipper.MinkowskiSum`` was probed on 2026-07-19 (pyclipper >= 1.3):
``MinkowskiSum([[0,0],[100,50]], [[0,0],[400,0],[400,300],[0,300]], True)``
returns the swept-boundary annulus (outer hull + CW hole) as integer
polygons. The union of that annulus with the footprint and the translated
footprint (all CCW, PFT_NONZERO) is the exact filled sweep for convex AND
concave footprints; a translate-in-N-steps fallback covers builds where the
binding misbehaves (visually identical at garden scale).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import pyclipper

Point = tuple[float, float]
Polygon = list[Point]

# Integer grid for pyclipper: 1 unit = 1/1000 cm (offset_tool precedent).
CLIPPER_SCALE = 1000

# Below this geometric solar elevation the sun is treated as down: shadow
# lengths explode toward infinity near the horizon (tan α → 0) and a
# hundreds-of-meters shadow polygon is visual noise, not information.
MIN_SUN_ELEVATION_DEG = 0.5

# Sweep displacements shorter than this render identically to the bare
# footprint (sun near zenith), so the sweep is skipped.
_MIN_SWEEP_CM = 0.01

# Fallback sweep resolution when MinkowskiSum is unavailable.
_FALLBACK_SWEEP_STEPS = 8


def shadow_length_cm(height_cm: float | None, elevation_deg: float) -> float | None:
    """Ground shadow length ``L = h / tan α`` in cm, or None for no shadow.

    Returns None when the object has no height or the geometric sun
    elevation is below ``MIN_SUN_ELEVATION_DEG`` (night / grazing sun).
    """
    if height_cm is None or height_cm <= 0:
        return None
    if elevation_deg < MIN_SUN_ELEVATION_DEG:
        return None
    return height_cm / math.tan(math.radians(elevation_deg))


def shadow_direction_scene(azimuth_deg: float) -> Point:
    """Unit shadow direction in scene coordinates (+x = East, +y = North).

    ``(-sin Az, -cos Az)`` — opposite the sun's compass bearing. Scene +y is
    already North (ADR-002); do NOT re-flip the y component downstream.
    """
    az = math.radians(azimuth_deg)
    return (-math.sin(az), -math.cos(az))


def circle_footprint(
    cx: float, cy: float, radius_cm: float, segments: int = 24
) -> Polygon:
    """Polygonalized circle footprint (CCW), e.g. a tree canopy."""
    if radius_cm <= 0 or segments < 3:
        return []
    step = 2.0 * math.pi / segments
    return [
        (cx + radius_cm * math.cos(i * step), cy + radius_cm * math.sin(i * step))
        for i in range(segments)
    ]


def polyline_footprint(points: Sequence[Point], width_cm: float) -> list[Polygon]:
    """Closed footprint polygon(s) of an open polyline (fence/wall stroke).

    Inflates the centerline by half the stroke width with square joins and
    butt ends — a fence occupies its drawn stroke, no more.
    """
    if len(points) < 2 or width_cm <= 0:
        return []
    pco = pyclipper.PyclipperOffset()
    pco.AddPath(_to_int(points), pyclipper.JT_SQUARE, pyclipper.ET_OPENBUTT)
    result = pco.Execute(round(width_cm / 2.0 * CLIPPER_SCALE))
    return [_from_int(path) for path in result]


def shadow_polygon(
    footprint: Sequence[Point],
    height_cm: float | None,
    elevation_deg: float,
    azimuth_deg: float,
) -> list[Polygon]:
    """Ground shadow of one extruded footprint; [] when there is no shadow."""
    length = shadow_length_cm(height_cm, elevation_deg)
    if length is None:
        return []
    direction = shadow_direction_scene(azimuth_deg)
    paths = _caster_paths_int(footprint, length, direction)
    return [_from_int(p) for p in _union_int(paths)]


def union_shadows(polygons: Iterable[Sequence[Point]]) -> list[Polygon]:
    """Union of already-computed shadow polygons (holes come out CW)."""
    int_paths = [_to_int(p) for p in polygons if len(p) >= 3]
    return [_from_int(p) for p in _union_int(int_paths)]


def compute_scene_shadows(
    casters: Iterable[tuple[Sequence[Point], float | None]],
    elevation_deg: float,
    azimuth_deg: float,
) -> list[Polygon]:
    """Unioned ground shadows for ``(footprint, height_cm)`` casters.

    The whole pipeline stays on the integer grid until the single final
    union — one scale-out pass, one Execute — which is what keeps a
    200-item recompute in the low milliseconds (US-E3 perf gate).
    Output outers are CCW, enclosed holes CW (paint with odd-even fill).
    """
    if shadow_length_cm(1.0, elevation_deg) is None:
        return []
    direction = shadow_direction_scene(azimuth_deg)
    all_paths: list[list[tuple[int, int]]] = []
    for footprint, height_cm in casters:
        length = shadow_length_cm(height_cm, elevation_deg)
        if length is None:
            continue
        all_paths.extend(_caster_paths_int(footprint, length, direction))
    return [_from_int(p) for p in _union_int(all_paths)]


# ── integer-grid internals ────────────────────────────────────────


def _to_int(points: Sequence[Point]) -> list[tuple[int, int]]:
    return [
        (round(x * CLIPPER_SCALE), round(y * CLIPPER_SCALE)) for x, y in points
    ]


def _from_int(path: Sequence[Sequence[int]]) -> Polygon:
    return [(x / CLIPPER_SCALE, y / CLIPPER_SCALE) for x, y in path]


def _caster_paths_int(
    footprint: Sequence[Point], length_cm: float, direction: Point
) -> list[list[tuple[int, int]]]:
    """Integer paths whose nonzero union is the swept (filled) shadow."""
    int_fp = _to_int(footprint)
    if len(int_fp) < 3:
        return []
    if not pyclipper.Orientation(int_fp):
        int_fp = list(reversed(int_fp))  # normalize CCW for stable winding
    dx = round(direction[0] * length_cm * CLIPPER_SCALE)
    dy = round(direction[1] * length_cm * CLIPPER_SCALE)
    if abs(dx) < _MIN_SWEEP_CM * CLIPPER_SCALE and abs(dy) < _MIN_SWEEP_CM * CLIPPER_SCALE:
        return [int_fp]
    translated = [(x + dx, y + dy) for x, y in int_fp]
    return [int_fp, translated, *_swept_boundary_int(int_fp, dx, dy)]


def _swept_boundary_int(
    int_fp: list[tuple[int, int]], dx: int, dy: int
) -> list[list[tuple[int, int]]]:
    """Boundary sweep of the footprint along (dx, dy), integer grid.

    Primary: ``pyclipper.MinkowskiSum`` (probed — module docstring).
    Fallback: intermediate translated copies — their union with footprint +
    end copy fills the sweep to well under a millimeter at garden scale.
    """
    try:
        swept = pyclipper.MinkowskiSum([(0, 0), (dx, dy)], int_fp, True)
    except (pyclipper.ClipperException, TypeError, ValueError, OverflowError):
        # pragma: no cover — defensive: binding-specific failure; the
        # staircase fallback below keeps shadows correct (tip/direction
        # exact, a few % of edge-notch area).
        swept = None
    if swept:
        return list(swept)
    return [
        [(x + dx * i // _FALLBACK_SWEEP_STEPS, y + dy * i // _FALLBACK_SWEEP_STEPS) for x, y in int_fp]
        for i in range(1, _FALLBACK_SWEEP_STEPS)
    ]


def _union_int(
    paths: list[list[tuple[int, int]]],
) -> list[list[tuple[int, int]]]:
    paths = [p for p in paths if len(p) >= 3]
    if not paths:
        return []
    clipper = pyclipper.Pyclipper()
    clipper.AddPaths(paths, pyclipper.PT_SUBJECT, True)
    return clipper.Execute(
        pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO
    )
