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

Base stacking (Phase 17 L1.6, ADR-037 addendum). A caster is a solid
``footprint x [base, base + h]`` — a plant on the soil of a raised bed starts at
the soil, not at the ground. Its ground shadow is

    S(F, b, h) = { p + t·d : p ∈ F, t ∈ [b / tan α, (b + h) / tan α] }

the footprint projected from the base, swept on to its projection from the top:
the ground shadow ``S(F, 0, h)`` translated by ``(b / tan α)·d``. The tip lies
``b / tan α`` further from the sun, and so does the near edge — what is below
the base is the shadow of whatever the caster stands on (its bed is a caster of
its own). ``base = 0`` takes the very same integer path as before L1.6: the
footprint is translated by ``round(b / tan α · d)`` first, and for b = 0 that
step does not run (pinned bit for bit by
``tests/integration/test_shadow_caster_golden.py``).

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
from collections.abc import Callable, Iterable, Sequence
from typing import NamedTuple

import pyclipper

Point = tuple[float, float]
Polygon = list[Point]


class ShadowCaster(NamedTuple):
    """One shadow-casting solid: ``footprint x [base_cm, base_cm + height_cm]``.

    The ONE caster shape of the sun & shade overlay, the hours-of-sun heatmap
    and (through the same base rule) the 3D records. ``footprint``: scene cm.
    ``height_cm``: the item's ``effective_height_cm``, measured from its own
    ground. ``base_cm``: how high that ground is — 0.0 for everything on the
    garden floor, the soil surface for a plant in a raised bed or container
    (``core.object_height.standing_base_cm``). Plain data: safe to hand to the
    heatmap worker thread.
    """

    footprint: Polygon
    height_cm: float
    base_cm: float = 0.0


#: What the shadow functions accept as a caster: a ``ShadowCaster`` or the
#: pre-L1.6 pair ``(footprint, height_cm)`` — a pair stands on the ground.
#: Nothing else: ``caster_fields`` refuses any other shape, so a third element
#: can only ever be a base when a ``ShadowCaster`` says so.
CasterLike = ShadowCaster | tuple[Sequence[Point], float | None]


def caster_fields(caster: CasterLike) -> tuple[Sequence[Point], float | None, float]:
    """``(footprint, height_cm, base_cm)`` of a caster — by TYPE, never by length.

    A ``ShadowCaster`` carries its base; an exact ``(footprint, height_cm)``
    tuple stands on the ground. Anything else — a list, a longer or shorter
    tuple, another named tuple — raises ``TypeError``: a caller that built a
    3-tuple for some other reason must not have its third element read as a
    height above ground.
    """
    if isinstance(caster, ShadowCaster):
        return caster.footprint, caster.height_cm, caster.base_cm
    if type(caster) is tuple and len(caster) == 2:
        return caster[0], caster[1], 0.0
    raise TypeError(
        "a shadow caster is a ShadowCaster or a (footprint, height_cm) tuple, "
        f"not {type(caster).__name__} of length {len(caster) if hasattr(caster, '__len__') else '?'}"
    )

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


def base_offset_cm(base_cm: float | None, elevation_deg: float) -> float:
    """How far along the shadow direction a raised caster's shadow STARTS:
    ``base / tan α``. 0.0 for a caster on the ground — and for a base that is
    no height above ground (None, negative, not finite)."""
    if base_cm is None or not math.isfinite(base_cm):
        return 0.0
    return shadow_length_cm(base_cm, elevation_deg) or 0.0


def shadow_polygon(
    footprint: Sequence[Point],
    height_cm: float | None,
    elevation_deg: float,
    azimuth_deg: float,
    base_cm: float = 0.0,
) -> list[Polygon]:
    """Ground shadow of one extruded footprint; [] when there is no shadow.

    ``base_cm`` lifts the solid: it occupies ``[base_cm, base_cm + height_cm]``
    and its shadow starts ``base_cm / tan α`` along the shadow direction
    (module docstring).
    """
    length = shadow_length_cm(height_cm, elevation_deg)
    if length is None:
        return []
    direction = shadow_direction_scene(azimuth_deg)
    paths = _caster_paths_int(footprint, length, direction,
                              base_offset_cm(base_cm, elevation_deg))
    return [_from_int(p) for p in _union_int(paths)]


def union_shadows(polygons: Iterable[Sequence[Point]]) -> list[Polygon]:
    """Union of already-computed shadow polygons (holes come out CW)."""
    int_paths = [_to_int(p) for p in polygons if len(p) >= 3]
    return [_from_int(p) for p in _union_int(int_paths)]


def clip_to_rect(
    polygons: Iterable[Sequence[Point]], width_cm: float, depth_cm: float
) -> list[Polygon]:
    """Shadow polygons cut at the rectangle (0, 0) — (width, depth): what the canvas
    shows of its overlay, which it clips to the canvas (Phase 17 L2.1: the 3D drape
    lays exactly that on the ground). Even-odd, like the overlay paints them (a
    union's holes stay sunny); outers come out CCW, holes CW. Nothing for an empty
    rectangle or no polygons."""
    paths = [_to_int(polygon) for polygon in polygons if len(polygon) >= 3]
    if not paths or width_cm <= 0 or depth_cm <= 0:
        return []
    w, d = round(width_cm * CLIPPER_SCALE), round(depth_cm * CLIPPER_SCALE)
    clipper = pyclipper.Pyclipper()
    clipper.AddPaths(paths, pyclipper.PT_SUBJECT, True)
    clipper.AddPath([(0, 0), (w, 0), (w, d), (0, d)], pyclipper.PT_CLIP, True)
    result = clipper.Execute(pyclipper.CT_INTERSECTION, pyclipper.PFT_EVENODD,
                             pyclipper.PFT_NONZERO)
    return [_from_int(path) for path in result]


class GroupedCaster(NamedTuple):
    """All solid footprints of ONE owner with its height and its base — the caster
    shape of ``compute_grouped_shadows``. ``base_cm`` as in ``ShadowCaster``."""

    footprints: Sequence[Sequence[Point]]
    height_cm: float
    base_cm: float = 0.0


def compute_grouped_shadows(
    casters: Iterable[GroupedCaster | tuple[Sequence[Sequence[Point]], float]],
    elevation_deg: float,
    azimuth_deg: float,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[Polygon], list[list[Polygon]]] | None:
    """Shared sweeps for the displayed union and sparse per-owner coverage.

    Keep paths on the existing integer grid. Union each owner's footprints
    before sparse sampling, so overlapping footprints count as one caster.
    A ``GroupedCaster`` carries its base — the same swept solid
    ``compute_scene_shadows`` makes of a ``ShadowCaster``; an exact
    ``(footprints, height_cm)`` pair stands on the ground. By TYPE, never by
    length (``caster_fields``).
    """
    direction = shadow_direction_scene(azimuth_deg)
    all_paths: list[list[tuple[int, int]]] = []
    owned = []
    for caster in casters:
        if should_cancel is not None and should_cancel():
            return None
        if isinstance(caster, GroupedCaster):
            footprints, height, base = caster.footprints, caster.height_cm, caster.base_cm
        elif type(caster) is tuple and len(caster) == 2:
            footprints, height, base = caster[0], caster[1], 0.0
        else:
            raise TypeError(
                "a grouped caster is a GroupedCaster or a (footprints, height_cm) tuple, "
                f"not {type(caster).__name__}")
        length = shadow_length_cm(height, elevation_deg)
        paths = []
        if length is not None:
            start = base_offset_cm(base, elevation_deg)
            for footprint in footprints:
                paths.extend(_caster_paths_int(footprint, length, direction, start))
        all_paths.extend(paths)
        owned.append([_from_int(p) for p in _union_int(paths)])
    return [_from_int(p) for p in _union_int(all_paths)], owned


def compute_scene_shadows(
    casters: Iterable[CasterLike],
    elevation_deg: float,
    azimuth_deg: float,
) -> list[Polygon]:
    """Unioned ground shadows of ``ShadowCaster``s (or ``(footprint, height_cm)``
    pairs, which stand on the ground).

    The whole pipeline stays on the integer grid until the single final
    union — one scale-out pass, one Execute — which is what keeps a
    200-item recompute in the low milliseconds (US-E3 perf gate).
    Output outers are CCW, enclosed holes CW (paint with odd-even fill).
    """
    if shadow_length_cm(1.0, elevation_deg) is None:
        return []
    direction = shadow_direction_scene(azimuth_deg)
    all_paths: list[list[tuple[int, int]]] = []
    for caster in casters:
        footprint, height_cm, base_cm = caster_fields(caster)
        length = shadow_length_cm(height_cm, elevation_deg)
        if length is None:
            continue
        all_paths.extend(_caster_paths_int(
            footprint, length, direction, base_offset_cm(base_cm, elevation_deg)))
    return [_from_int(p) for p in _union_int(all_paths)]


# ── integer-grid internals ────────────────────────────────────────


def _to_int(points: Sequence[Point]) -> list[tuple[int, int]]:
    return [
        (round(x * CLIPPER_SCALE), round(y * CLIPPER_SCALE)) for x, y in points
    ]


def _from_int(path: Sequence[Sequence[int]]) -> Polygon:
    return [(x / CLIPPER_SCALE, y / CLIPPER_SCALE) for x, y in path]


def _caster_paths_int(
    footprint: Sequence[Point], length_cm: float, direction: Point, start_cm: float = 0.0
) -> list[list[tuple[int, int]]]:
    """Integer paths whose nonzero union is the swept (filled) shadow.

    ``start_cm`` is a raised caster's base offset (``base / tan α``): the
    footprint is moved that far along ``direction`` before the sweep. For a
    caster on the ground the step is skipped, so its paths are what they were
    before base stacking existed.
    """
    int_fp = _to_int(footprint)
    if len(int_fp) < 3:
        return []
    if not pyclipper.Orientation(int_fp):
        int_fp = list(reversed(int_fp))  # normalize CCW for stable winding
    if start_cm > 0.0:
        ox = round(direction[0] * start_cm * CLIPPER_SCALE)
        oy = round(direction[1] * start_cm * CLIPPER_SCALE)
        int_fp = [(x + ox, y + oy) for x, y in int_fp]
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
        # Binding-specific failure — the staircase fallback below keeps
        # shadows correct (tip/direction exact, a few % of edge-notch area).
        # Exercised by the fallback-equivalence unit test.
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
