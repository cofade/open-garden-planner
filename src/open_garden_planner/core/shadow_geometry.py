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

One caster is one REGION, not one ring (issue #444). A fence or wall stroke
that closes on itself is an outer ring plus a hole, and a self-crossing
outline is two lobes: both are repaired once per walk by ``shadow_region``,
which hands the sweep simple rings only. A hole swept as a solid would cast the
enclosed garden as a slab (88.8 m² instead of 17.5 m² for a 10 m x 8 m loop),
and a figure-eight swept as one ring loses a lobe.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from functools import lru_cache
from typing import Any, NamedTuple, cast

import pyclipper

Point = tuple[float, float]
Polygon = list[Point]
Point3D = tuple[float, float, float]
Triangle3D = tuple[Point3D, Point3D, Point3D]


class WeightedShadowRegion(NamedTuple):
    """A shadow region with analytical occlusion and open transmittance (#440).

    ``polygons``: outer (CCW) and hole (CW) rings bounding the region.
    ``occlusion``: shade weight ``1.0 - transmittance`` in ``(0.0, 1.0]`` (``1.0``
    for opaque casters).
    ``transmittance``: open sunlight fraction in ``[0.0, 1.0)`` (``0.0`` for opaque
    casters).
    """

    polygons: list[Polygon]
    occlusion: float = 1.0
    transmittance: float = 0.0


class WeightedShadowsResult(NamedTuple):
    """Result of ``compute_weighted_shadows`` (#440).

    ``union_polygons``: full outer/hole union of all active shadow casters.
    ``weighted_regions``: disjoint shadow regions with their ``occlusion`` and
    ``transmittance`` weights.
    ``owned_shadows``: per-caster ``(polygons, transmittance)`` in input order.
    """

    union_polygons: list[Polygon]
    weighted_regions: list[WeightedShadowRegion]
    owned_shadows: list[tuple[list[Polygon], float]]


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


def _offset_line(line: Any, closed: bool, offset: float) -> Any:
    """line moved offset cm to the left of travel, its joints kept inside the
    path's own outline. The outline squares a bend off at half the path's width
    from the joint; on the outside of a bend the two segments' offset ends are joined
    by a chord — no point further than |offset| from the joint — and on the inside
    the two offset lines meet where they cross (the two ends where they do not)."""
    import numpy as np

    points = np.asarray(line, dtype=np.float64)
    if closed and len(points) > 1 and np.allclose(points[0], points[-1]):
        points = points[:-1]
    keep = np.ones(len(points), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(points, axis=0), axis=1) > 1e-6
    points = points[keep]
    if len(points) < 2:
        return points
    starts = points if closed else points[:-1]
    ends = np.roll(points, -1, axis=0) if closed else points[1:]
    lengths = np.linalg.norm(ends - starts, axis=1)
    if closed and lengths[-1] <= 1e-6:
        starts, ends, lengths = starts[:-1], ends[:-1], lengths[:-1]
    along = (ends - starts) / np.maximum(lengths, 1e-12)[:, None]
    left = np.stack([-along[:, 1], along[:, 0]], axis=1)
    out: list[Any] = [] if closed else [starts[0] + left[0] * offset]
    for joint in (range(len(along)) if closed else range(1, len(along))):
        before, after = joint - 1, joint
        corner = starts[after]
        first, second = corner + left[before] * offset, corner + left[after] * offset
        turn = float(along[before, 0] * along[after, 1] - along[before, 1] * along[after, 0])
        if abs(turn) < 1e-9:
            out.append(first)
            continue
        if offset * turn > 0.0:  # the inside of the bend: where the two offset lines cross
            gap = second - first
            back = float(gap[0] * along[after, 1] - gap[1] * along[after, 0]) / turn
            crossing = first + along[before] * back
            forward = float(np.dot(crossing - second, along[after]))
            if -lengths[before] <= back <= 0.0 and 0.0 <= forward <= lengths[after]:
                out.append(crossing)
                continue
        out.extend((first, second))
    if not closed:
        out.append(ends[-1] + left[-1] * offset)
    return np.asarray(out)


def polyline_bevel_footprint(points: Sequence[Point], width_cm: float) -> list[Polygon]:
    """Closed footprint polygon(s) of an open polyline with bevelled joins and butt ends.

    Matches what 2D paints for a paved path (BevelJoin + FlatCap) and what 3D
    builds for paved path kerbs (_offset_line; issue #726).
    """
    if len(points) < 2 or width_cm <= 0:
        return []
    import numpy as np

    pts = np.asarray(points, dtype=np.float64)
    if len(pts) > 1 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    keep = np.ones(len(pts), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-6
    pts = pts[keep]
    if len(pts) < 2:
        return []

    half_w = width_cm / 2.0
    left = _offset_line(pts, False, -half_w)
    right = _offset_line(pts, False, half_w)
    if len(left) < 2 or len(right) < 2:
        return []
    ring = np.concatenate([left, right[::-1]])
    pco = pyclipper.Pyclipper()
    pco.AddPath(_to_int([tuple(p) for p in ring]), pyclipper.PT_SUBJECT, True)
    result = pco.Execute(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    return [_from_int(path) for path in result]


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


#: How far a rounded outline's arcs may stray from the true circle, cm.
ROUND_ARC_TOLERANCE_CM = 0.5


def polyline_round_outline(points: Sequence[Point], width_cm: float, *,
                           arc_tolerance_cm: float = ROUND_ARC_TOLERANCE_CM) -> list[Polygon]:
    """The ground an open polyline covers when it is stroked with round caps and round
    joins — what the canvas paints for a gravel or a dirt path (``path_style_paint``),
    half a width past each end. Not a caster: a fence's footprint is
    ``polyline_footprint``."""
    if len(points) < 2 or width_cm <= 0:
        return []
    pco = pyclipper.PyclipperOffset(arc_tolerance=arc_tolerance_cm * CLIPPER_SCALE)
    pco.AddPath(_to_int(points), pyclipper.JT_ROUND, pyclipper.ET_OPENROUND)
    result = pco.Execute(round(width_cm / 2.0 * CLIPPER_SCALE))
    return [_from_int(path) for path in result]


def grown_polygon(ring: Sequence[Point], distance_cm: float) -> list[Polygon]:
    """``ring`` grown outwards by ``distance_cm``, its corners rounded."""
    if len(ring) < 3 or distance_cm <= 0:
        return [list(ring)] if len(ring) >= 3 else []
    pco = pyclipper.PyclipperOffset(arc_tolerance=ROUND_ARC_TOLERANCE_CM * CLIPPER_SCALE)
    pco.AddPath(_to_int(ring), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    result = pco.Execute(round(distance_cm * CLIPPER_SCALE))
    return [_from_int(path) for path in result]


def base_offset_cm(base_cm: float | None, elevation_deg: float) -> float:
    """How far along the shadow direction a raised caster's shadow STARTS:
    ``base / tan α``. 0.0 for a caster on the ground — and for a base that is
    no height above ground (None, negative, not finite)."""
    if base_cm is None or not math.isfinite(base_cm):
        return 0.0
    return shadow_length_cm(base_cm, elevation_deg) or 0.0


#: How far a ring's printed area may differ from the area its own outline
#: encloses before the ring is treated as a self-crossing one — one grid step
#: of the 1/1000 cm grid, squared, with room for the integer rounding of a
#: long outline (issue #444).
_RING_AREA_SLACK = 0.5


def shadow_region(footprints: Iterable[Sequence[Point]]) -> list[Polygon]:
    """The ground ONE caster covers, as rings that are all simple (#444).

    ``footprints`` is a caster's whole set for one item — ``item_footprints``
    output, e.g. a fence's stroke: an outer ring and its hole. Two shapes the
    sweep cannot take as they come are repaired here, once, where the item is
    still known:

    - **A stroke that closes on itself** comes back from an offset as an outer
      ring and a hole ring. Swept as two solids the hole becomes a slab the
      size of the enclosed garden: a 10 m x 8 m loop at a 60° sun drew 88.8 m²
      instead of 17.5 m². The hole is cut open by a zero-width slit to the
      nearest boundary above it, so the item is ONE simple ring whose region is
      exactly the stroke's — the slit encloses no ground and the sweep of the
      region is unchanged (measured against a ray oracle: no cell differs).
    - **A self-crossing ring** (a polygon whose outline crosses itself) is
      split by ``SimplifyPolygons`` into its lobes, which are then swept as the
      separate solids they are: a bow-tie at a 60° sun drew 80,000 cm² where
      its two lobes' prisms give 129,282 cm².

    A ring that is already simple is returned **as it is** — the very same point
    list, whatever its winding: that is the case of everything on the ground in
    ``tests/fixtures/shadows/shadow_golden.json``, which stays bit-for-bit (the
    golden's stated rule). Roles come from the sign of the enclosed area —
    outers counter-clockwise, holes clockwise — which is what every
    ``pyclipper`` offset hands out. A ring that touches itself (a pinched
    outline) is rebuilt into its lobes; its ground is the same.

    The self-crossing test and split are per RING and bounded by
    ``MAX_REGION_VERTICES``: above it a ring is taken as it comes (measured, one
    ``SimplifyPolygons`` call over a 16,384-vertex ring costs 257 ms, and over a
    whole ring set of a crafted fence 2.4 s — per walk). The hole repair has no
    such bound: a stroke's rings are grouped by winding and bridged, which is
    linear in the ring and cheap next to that stroke's own sweep.

    Callers: the caster walk (``collect_identified_casters``; the overlay's
    ``collect_shadow_casters`` flattens it) asks this once per item per walk. The
    sweep functions themselves take simple rings — one item's ring
    set is not recoverable from a single ring, and a hole passed on its own
    would be cast as a solid.
    """
    rings = [list(footprint) for footprint in footprints if len(footprint) >= 3]
    if not rings:
        return []
    int_rings = [_to_int(ring) for ring in rings]
    if not _region_needs_repair(int_rings):
        return rings
    pieces: list[list[tuple[int, int]]] = []
    for ring in int_rings:
        # Per ring, never over the whole set: one SimplifyPolygons call over a crafted
        # fence's rings cost 2.4 s a walk. A ring above the bound is taken as it comes.
        if len(ring) > MAX_REGION_VERTICES:
            pieces.append(ring)
            continue
        lobes = pyclipper.SimplifyPolygons([ring], pyclipper.PFT_EVENODD)
        if len(lobes) == 1:
            pieces.append(ring)  # simple: unchanged, point for point, either winding
        elif abs(abs(sum(pyclipper.Area(lobe) for lobe in lobes))
                 - abs(pyclipper.Area(ring))) <= _RING_AREA_SLACK:
            # Self-TOUCHING, not crossing: the lobes add up to the ring's own ground,
            # so the ring's role survives — a pinched hole stays a hole.
            pieces.extend([list(reversed(lobe)) for lobe in lobes]
                          if pyclipper.Area(ring) < 0 else lobes)
        else:
            # Self-CROSSING: the lobes are the solid the outline draws, and they are
            # solid whichever way it was wound (a mirrored or clockwise star draws the
            # same ground as a counter-clockwise one).
            pieces.extend(lobes)
    regions: list[Polygon] = []
    for outer, holes in _group_holes_int(pieces):
        regions.append(_from_int(_bridge_holes_int(outer, holes) if holes else outer))
    return regions


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


class OpenFrame:
    """The solid members of an OPEN FRAME — a pergola's timber, a trellis's lattice, a
    swing's legs and beam — in the frame's OWN coordinates (#698).

    ``triangles``: the members as triangles, cm, z from the frame's own ground.
    ``footprint``: the outline its prism stands on, in the same coordinates — the
    item's footprint before it is turned and placed. ``rotation_deg``: how far the
    item is turned in the scene, counter-clockwise seen from above (north up).

    Kept in the frame's own coordinates on purpose: what a frame lets through
    depends on the sun's bearing RELATIVE to it, not on where it stands. Fifty
    garden lights along a path are one frame fifty times — the caster walk hands
    all of them the very same object, they are weighed once per sun position, and
    they get the very same number (so the overlay paints them as one region).

    Immutable, compared by value, hashed once: a frame can be a thousand
    triangles, and the transmittance cache looks one up for every caster and sun.
    Plain data — safe to hand to the heatmap worker thread.
    """

    __slots__ = ("triangles", "footprint", "rotation_deg", "_hash")

    triangles: tuple[Triangle3D, ...]
    footprint: tuple[Point, ...]
    rotation_deg: float
    _hash: int

    def __init__(self, triangles: Iterable[Triangle3D], footprint: Iterable[Point],
                 rotation_deg: float = 0.0) -> None:
        object.__setattr__(self, "triangles", tuple(triangles))
        object.__setattr__(self, "footprint", tuple(footprint))
        object.__setattr__(self, "rotation_deg", float(rotation_deg))
        object.__setattr__(self, "_hash",
                           hash((self.triangles, self.footprint, self.rotation_deg)))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("an OpenFrame is immutable")

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        return (isinstance(other, OpenFrame) and self._hash == other._hash
                and self.rotation_deg == other.rotation_deg
                and self.footprint == other.footprint and self.triangles == other.triangles)

    def __repr__(self) -> str:
        return (f"OpenFrame({len(self.triangles)} triangles, {len(self.footprint)} corners, "
                f"turned {self.rotation_deg:g} deg)")

    def with_triangles(self, triangles: Iterable[Triangle3D]) -> OpenFrame:
        """The same frame with other members — its slice above a raised receiver."""
        return OpenFrame(triangles, self.footprint, self.rotation_deg)


class GroupedCaster(NamedTuple):
    """All solid footprints of ONE owner with its height, base, and optional 3D
    roof or fence porosity metadata (#440) — the caster shape of
    ``compute_grouped_shadows`` and ``compute_weighted_shadows``.

    ``frame`` (#698): the solid members of an OPEN FRAME (a pergola, a trellis, a
    swing …). They do NOT replace the prism's shadow as ``roof_triangles`` do: they
    weigh it (``open_frame_transmittance``). None for every caster that is no open
    frame; a frame WITHOUT triangles is an open frame with nothing solid left (a
    slice above a raised receiver that holds none of its members), which lets all
    the sun through.
    """

    footprints: Sequence[Sequence[Point]]
    height_cm: float
    base_cm: float = 0.0
    roof_triangles: tuple[Triangle3D, ...] = ()
    fence_style: str | None = None
    fence_points: tuple[Point, ...] = ()
    fence_width_cm: float = 0.0
    transmittance: float | None = None
    frame: OpenFrame | None = None


def _path_area_cm2(paths: Iterable[Sequence[tuple[int, int]]]) -> float:
    """The ground a union's rings cover, cm² (holes are clockwise and subtract)."""
    return float(sum(pyclipper.Area(path) for path in paths)) / (CLIPPER_SCALE * CLIPPER_SCALE)


def _frame_shadow_area_cm2(
    triangles: Sequence[Triangle3D], elevation_deg: float, direction: Point
) -> float:
    """The ground a frame's members shade, cm²: every triangle moved along the sun ray
    onto the ground, united. One numpy projection and one clipper union.

    The triangles' z is taken as it comes — from the frame's own ground. A base under
    the frame moves its whole shadow ``base / tan α`` along the sun ray and changes no
    area, so it is not asked for.

    Only the triangles that face the sun are united. For every solid a builder makes
    — boxes, beams, rods, lathed posts, cloth laid with both faces — those cover the
    same ground as all of them, at half the clipper's work (measured: a trellis 2.8 ms
    with all, 0.7 ms with these). ``tests/unit/test_open_frames.py`` holds every
    open-frame kind to that, against all triangles united, over sizes and suns.
    """
    import numpy as np

    corners = np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)
    if not len(corners):
        return 0.0
    reach = np.maximum(corners[:, :, 2], 0.0) / math.tan(math.radians(elevation_deg))
    grid = np.rint(np.stack(
        [corners[:, :, 0] + reach * direction[0], corners[:, :, 1] + reach * direction[1]],
        axis=2) * CLIPPER_SCALE).astype(np.int64)
    doubled = ((grid[:, 1, 0] - grid[:, 0, 0]) * (grid[:, 2, 1] - grid[:, 0, 1])
               - (grid[:, 2, 0] - grid[:, 0, 0]) * (grid[:, 1, 1] - grid[:, 0, 1]))
    lit = grid[doubled > 0]
    if not len(lit):
        return 0.0
    return _path_area_cm2(_union_int(lit.tolist()))


@lru_cache(maxsize=4096)
def _open_frame_transmittance(
    frame: OpenFrame, height_cm: float, elevation_deg: float, azimuth_deg: float
) -> float:
    length = shadow_length_cm(height_cm, elevation_deg)
    if length is None:
        return 1.0
    # in the frame's own coordinates: the item turned counter-clockwise by t sees the
    # sun at the bearing it has in the scene plus t (a bearing runs clockwise)
    direction = shadow_direction_scene(azimuth_deg + frame.rotation_deg)
    prism_area = _path_area_cm2(_union_int(_caster_paths_int(frame.footprint, length, direction)))
    if prism_area <= 0.0:
        return 1.0
    frame_area = _frame_shadow_area_cm2(frame.triangles, elevation_deg, direction)
    return float(min(1.0, max(0.0, 1.0 - frame_area / prism_area)))


def open_frame_transmittance(
    frame: OpenFrame, height_cm: float, elevation_deg: float, azimuth_deg: float
) -> float:
    """The share of the sun an open frame lets through, in ``[0.0, 1.0]`` (#698).

    ``1 - A(frame) / A(prism)``: ``A(prism)`` is the ground shadow of the caster the
    2D model casts — the frame's footprint, ``height_cm`` high — and ``A(frame)`` the
    ground shadow of the frame's own solid members, both for this sun. The prism
    keeps its shape — it is where the shade can fall — and this number is how dark
    it is there: the frame's shade, spread evenly over the prism's. So the shade
    the 2D model reports, area times depth, is the frame's real shadow area, at
    every elevation and azimuth and for every size and turn of the item — nothing
    is tabulated.

    ``azimuth_deg`` is the sun's bearing in the SCENE; the frame's turn is the
    frame's own (``OpenFrame.rotation_deg``). A base under the caster moves the
    prism's shadow and the frame's alike and leaves the number as it is, so none
    is asked for. 1.0 (all the sun) for a frame with no members, a prism with no
    shadow, and a sun below ``MIN_SUN_ELEVATION_DEG``. Results are kept per frame,
    height and sun: the map asks the same sample for the grid and again for every
    plant it shades, and every identical frame on the plan shares the answer.
    """
    if elevation_deg < MIN_SUN_ELEVATION_DEG or not frame.triangles:
        return 1.0
    return _open_frame_transmittance(
        frame, float(height_cm), float(elevation_deg), float(azimuth_deg))


def caster_transmittance(
    caster: Any,
    elevation_deg: float,
    azimuth_deg: float,
) -> float:
    """Open sunlight transmittance in ``[0.0, 1.0]`` for a caster (#440).

    Returns ``0.0`` for opaque casters, ``caster.transmittance`` when explicitly
    provided, the open frame's for the sun of the moment when the caster carries a
    ``frame`` (#698, ``open_frame_transmittance``), or the angle-dependent
    structural fence transmittance when ``caster.fence_style`` is set.
    """
    explicit = getattr(caster, "transmittance", None)
    if explicit is not None:
        return float(min(1.0, max(0.0, float(explicit))))
    frame = getattr(caster, "frame", None)
    if frame is not None:
        return open_frame_transmittance(
            frame, float(getattr(caster, "height_cm", 0.0) or 0.0), elevation_deg, azimuth_deg)
    fence_style = getattr(caster, "fence_style", None)
    if isinstance(fence_style, str) and fence_style:
        from open_garden_planner.core.scene3d.builders.fences import fence_transmittance

        height_cm = float(getattr(caster, "height_cm", 0.0) or 0.0)
        stroke_cm = float(getattr(caster, "fence_width_cm", 0.0) or 3.0)
        points = getattr(caster, "fence_points", ()) or ()
        return fence_transmittance(
            fence_style, height_cm, stroke_cm, elevation_deg, azimuth_deg, points
        )
    return 0.0


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
    length (``caster_fields``). When ``roof_triangles`` is present on a
    ``GroupedCaster``, its 3D structural triangles are projected directly (#440).
    """
    direction = shadow_direction_scene(azimuth_deg)
    all_paths: list[list[tuple[int, int]]] = []
    owned = []
    for caster in casters:
        if should_cancel is not None and should_cancel():
            return None
        if isinstance(caster, GroupedCaster):
            footprints = caster.footprints
            height = caster.height_cm
            base = caster.base_cm
            roof_tris = caster.roof_triangles
        elif type(caster) is tuple and len(caster) == 2:
            footprints, height, base, roof_tris = caster[0], caster[1], 0.0, ()
        else:
            raise TypeError(
                "a grouped caster is a GroupedCaster or a (footprints, height_cm) tuple, "
                f"not {type(caster).__name__}")
        length = shadow_length_cm(height, elevation_deg)
        paths: list[list[tuple[int, int]]] = []
        if length is not None:
            if roof_tris:
                paths = _roof_caster_paths_int(
                    roof_tris, elevation_deg, direction, base_cm=base
                )
            else:
                start = base_offset_cm(base, elevation_deg)
                for footprint in footprints:
                    paths.extend(_caster_paths_int(footprint, length, direction, start))
        unioned = _union_int(paths)
        all_paths.extend(paths)
        owned.append([_from_int(p) for p in unioned])
    return [_from_int(p) for p in _union_int(all_paths)], owned


def compute_weighted_shadows(
    casters: Iterable[Any],
    elevation_deg: float,
    azimuth_deg: float,
    should_cancel: Callable[[], bool] | None = None,
    *,
    receiver_elev_cm: float = 0.0,
) -> WeightedShadowsResult | None:
    """Enriched analytical shadow projection with pitched roofs and fence porosity (#440).

    Accepts ``GroupedCaster``, ``IdentifiedCaster``, or ``(footprints, height_cm)``
    pairs. Each owner's shadow components are unioned first so overlapping parts of
    one object never double-count shade. When porous casters are present, overlapping
    regions are partitioned on the integer grid with multiplied transmittance
    ``T_total = prod(T_i)`` and ``occlusion = 1.0 - T_total``.
    """
    if elevation_deg < MIN_SUN_ELEVATION_DEG:
        return WeightedShadowsResult([], [], [])
    direction = shadow_direction_scene(azimuth_deg)
    all_paths: list[list[tuple[int, int]]] = []
    owner_int_paths: list[list[list[tuple[int, int]]]] = []
    owner_transmittances: list[float] = []
    owned_shadows: list[tuple[list[Polygon], float]] = []

    for caster in casters:
        if should_cancel is not None and should_cancel():
            return None
        if isinstance(caster, GroupedCaster) or hasattr(caster, "footprints"):
            footprints = caster.footprints
            height = caster.height_cm
            base = float(getattr(caster, "base_cm", 0.0) or 0.0)
            roof_tris = getattr(caster, "roof_triangles", ()) or ()
        elif type(caster) is tuple and len(caster) == 2:
            footprints, height, base, roof_tris = caster[0], caster[1], 0.0, ()
        else:
            raise TypeError(
                "a weighted caster must provide footprints and height_cm, "
                f"not {type(caster).__name__}"
            )
        trans = caster_transmittance(caster, elevation_deg, azimuth_deg)
        if trans >= 1.0 or height is None or height <= 0.0:
            owner_int_paths.append([])
            owner_transmittances.append(1.0)
            owned_shadows.append(([], 1.0))
            continue

        top = base + height
        if top <= receiver_elev_cm:
            owner_int_paths.append([])
            owner_transmittances.append(trans)
            owned_shadows.append(([], trans))
            continue

        paths: list[list[tuple[int, int]]] = []
        if roof_tris:
            paths = _roof_caster_paths_int(
                roof_tris,
                elevation_deg,
                direction,
                base_cm=base,
                receiver_elev_cm=receiver_elev_cm,
            )
        else:
            eff_base = max(base, receiver_elev_cm) - receiver_elev_cm
            eff_height = top - max(base, receiver_elev_cm)
            length = shadow_length_cm(eff_height, elevation_deg)
            if length is not None:
                start = base_offset_cm(eff_base, elevation_deg)
                for footprint in footprints:
                    paths.extend(_caster_paths_int(footprint, length, direction, start))

        all_paths.extend(paths)
        unioned = _union_int(paths)
        owner_int_paths.append(unioned)
        owner_transmittances.append(trans)
        owned_shadows.append(([_from_int(p) for p in unioned], trans))

    union_int = _union_int(all_paths)
    union_polygons = [_from_int(p) for p in union_int]
    if not union_int:
        return WeightedShadowsResult([], [], owned_shadows)

    has_porous = any(
        0.0 < t < 1.0 and bool(paths)
        for paths, t in zip(owner_int_paths, owner_transmittances, strict=True)
    )
    if not has_porous:
        return WeightedShadowsResult(
            union_polygons,
            [WeightedShadowRegion(union_polygons, occlusion=1.0, transmittance=0.0)],
            owned_shadows,
        )

    opaque_paths = [
        p
        for paths, t in zip(owner_int_paths, owner_transmittances, strict=True)
        if t <= 0.0
        for p in paths
    ]
    opaque_union = _union_int(opaque_paths)
    # The porous owners, each with the box its shadow lies in. A clip is asked only
    # where two boxes overlap, and a box is made once, not once per pair: fifty garden
    # lights along a path are fifty shades that never meet (#698; the pairwise loop
    # cost 0.8 s a sun position at 500 of them). The boxes are turned WITH THE SUN —
    # every shade is swept along the same direction, so a long shade's box is as
    # narrow as its caster, where an upright box round a slanting shade takes in the
    # neighbours it never touches.

    def box(paths: list[list[tuple[int, int]]]) -> tuple[float, float, float, float] | None:
        return _box_along(paths, direction)

    opaque_bbox = box(opaque_union)
    porous = [
        (paths, trans, box(paths))
        for paths, trans in zip(owner_int_paths, owner_transmittances, strict=True)
        if 0.0 < trans < 1.0 and paths
    ]
    meets_another = _boxes_meeting_another([box for _paths, _trans, box in porous])
    porous_regions: list[_PorousRegion] = []
    alone: list[tuple[list[list[tuple[int, int]]], float]] = []

    for (p_paths, p_trans, p_bbox), meets in zip(porous, meets_another, strict=True):
        rem = (_diff_int(p_paths, opaque_union)
               if opaque_union and _bboxes_overlap(p_bbox, opaque_bbox) else p_paths)
        if not rem:
            continue
        if not meets:
            # no other porous shade can reach it: it is its own region, as it is
            alone.append((rem, p_trans))
            continue
        rem_bbox = box(rem)
        next_regions: list[_PorousRegion] = []
        for region in porous_regions:
            r_paths, r_trans, r_bbox = region
            if not rem or not _bboxes_overlap(r_bbox, rem_bbox):
                next_regions.append(region)
                continue
            overlap = _intersect_int(r_paths, rem)
            if not overlap:
                next_regions.append(region)
                continue
            r_only = _diff_int(r_paths, rem)
            if r_only:
                next_regions.append((r_only, r_trans, box(r_only)))
            next_regions.append((overlap, r_trans * p_trans, box(overlap)))
            rem = _diff_int(rem, r_paths)
            rem_bbox = box(rem)
        if rem:
            next_regions.append((rem, p_trans, rem_bbox))
        porous_regions = next_regions

    weighted_regions: list[WeightedShadowRegion] = []
    if opaque_union:
        weighted_regions.append(
            WeightedShadowRegion(
                [_from_int(p) for p in opaque_union],
                occlusion=1.0,
                transmittance=0.0,
            )
        )
    grouped_by_trans: dict[float, list[list[tuple[int, int]]]] = {}
    for r_paths, r_trans in [*((paths, trans) for paths, trans, _box in porous_regions), *alone]:
        if not r_paths:
            continue
        key_t = round(r_trans, 6)
        grouped_by_trans.setdefault(key_t, []).extend(r_paths)
    for key_t, r_paths in sorted(grouped_by_trans.items(), key=lambda kv: kv[0]):
        merged = _union_int(r_paths)
        if merged:
            occ = round(min(1.0, max(0.0, 1.0 - key_t)), 6)
            weighted_regions.append(
                WeightedShadowRegion(
                    [_from_int(p) for p in merged],
                    occlusion=occ,
                    transmittance=key_t,
                )
            )
    return WeightedShadowsResult(union_polygons, weighted_regions, owned_shadows)


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
    return cast(
        list[list[tuple[int, int]]],
        clipper.Execute(
            pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO
        ),
    )


def _paths_bbox(
    paths: list[list[tuple[int, int]]],
) -> tuple[int, int, int, int] | None:
    if not paths:
        return None
    xs = [pt[0] for p in paths for pt in p]
    ys = [pt[1] for p in paths for pt in p]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _bboxes_overlap(
    a: tuple[float, float, float, float] | None,
    b: tuple[float, float, float, float] | None,
) -> bool:
    if a is None or b is None:
        return False
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _box_along(
    paths: Sequence[Sequence[tuple[int, int]]], direction: Point
) -> tuple[float, float, float, float] | None:
    """The box the paths lie in, in coordinates turned with the sun — ``u`` along
    ``direction`` (a unit vector), ``v`` across it — as ``(u0, v0, u1, v1)``, one grid
    unit wider on every side (the turn is float arithmetic: two shapes that overlap
    must never be told apart by a rounding). None for no paths."""
    dx, dy = direction
    along = [x * dx + y * dy for path in paths for x, y in path]
    if not along:
        return None
    across = [y * dx - x * dy for path in paths for x, y in path]
    return (min(along) - 1.0, min(across) - 1.0, max(along) + 1.0, max(across) + 1.0)


#: One region of ``compute_weighted_shadows``' porous partition: its paths, its
#: transmittance, and the box the paths lie in (``_box_along``; None for no paths).
_PorousRegion = tuple[list[list[tuple[int, int]]], float, tuple[float, float, float, float] | None]

#: Above this many boxes ``_boxes_meeting_another`` answers "every one may": its table
#: of pairs is n x n booleans (16 MB here), and a plan of four thousand porous casters
#: is a crafted one.
_MAX_BOX_PAIRS = 4000


def _boxes_meeting_another(
    boxes: Sequence[tuple[float, float, float, float] | None],
) -> list[bool]:
    """For each box: does it overlap ANOTHER box of the list (``_bboxes_overlap``'s
    rule: boxes that only touch do not)? One vectorised table instead of a Python loop
    over the pairs. A missing box meets none."""
    count = len(boxes)
    if count < 2:
        return [False] * count
    if count > _MAX_BOX_PAIRS:
        return [box is not None for box in boxes]
    import numpy as np

    present = np.array([box is not None for box in boxes])
    table = np.array([box if box is not None else (0.0, 0.0, 0.0, 0.0) for box in boxes],
                     dtype=np.float64)
    x0, y0, x1, y1 = table[:, 0], table[:, 1], table[:, 2], table[:, 3]
    apart = ((x1[:, None] <= x0[None, :]) | (x1[None, :] <= x0[:, None])
             | (y1[:, None] <= y0[None, :]) | (y1[None, :] <= y0[:, None]))
    meets = ~apart & present[:, None] & present[None, :]
    np.fill_diagonal(meets, False)
    return [bool(value) for value in meets.any(axis=1)]


def _intersect_int(
    subject: list[list[tuple[int, int]]],
    clip: list[list[tuple[int, int]]],
) -> list[list[tuple[int, int]]]:
    subject = [p for p in subject if len(p) >= 3]
    clip = [p for p in clip if len(p) >= 3]
    if not subject or not clip:
        return []
    if not _bboxes_overlap(_paths_bbox(subject), _paths_bbox(clip)):
        return []
    clipper = pyclipper.Pyclipper()
    clipper.AddPaths(subject, pyclipper.PT_SUBJECT, True)
    clipper.AddPaths(clip, pyclipper.PT_CLIP, True)
    return cast(
        list[list[tuple[int, int]]],
        clipper.Execute(
            pyclipper.CT_INTERSECTION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD
        ),
    )


def _diff_int(
    subject: list[list[tuple[int, int]]],
    clip: list[list[tuple[int, int]]],
) -> list[list[tuple[int, int]]]:
    subject = [p for p in subject if len(p) >= 3]
    clip = [p for p in clip if len(p) >= 3]
    if not subject:
        return []
    if not clip or not _bboxes_overlap(_paths_bbox(subject), _paths_bbox(clip)):
        return subject
    clipper = pyclipper.Pyclipper()
    clipper.AddPaths(subject, pyclipper.PT_SUBJECT, True)
    clipper.AddPaths(clip, pyclipper.PT_CLIP, True)
    return cast(
        list[list[tuple[int, int]]],
        clipper.Execute(
            pyclipper.CT_DIFFERENCE, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD
        ),
    )


def _clip_triangle_above_z(
    tri: Triangle3D,
    base_cm: float,
    z_plane: float,
) -> list[Point3D]:
    """Clip a 3D triangle (shifted by ``base_cm``) to the half-space ``z >= z_plane``."""
    verts: list[Point3D] = [
        (tri[0][0], tri[0][1], tri[0][2] + base_cm),
        (tri[1][0], tri[1][1], tri[1][2] + base_cm),
        (tri[2][0], tri[2][1], tri[2][2] + base_cm),
    ]
    if z_plane <= 0.0 and min(v[2] for v in verts) >= 0.0:
        return verts
    if max(v[2] for v in verts) <= z_plane + 1e-9:
        return []
    out: list[Point3D] = []
    for idx in range(3):
        a = verts[idx]
        b = verts[(idx + 1) % 3]
        a_in = a[2] >= z_plane - 1e-9
        b_in = b[2] >= z_plane - 1e-9
        if a_in and b_in:
            out.append(b)
        elif a_in and not b_in:
            denom = a[2] - b[2]
            t = (a[2] - z_plane) / denom if abs(denom) > 1e-12 else 0.0
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), z_plane))
        elif not a_in and b_in:
            denom = b[2] - a[2]
            t = (z_plane - a[2]) / denom if abs(denom) > 1e-12 else 0.0
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), z_plane))
            out.append(b)
    return out


def _roof_caster_paths_int(
    roof_triangles: Sequence[Triangle3D],
    elevation_deg: float,
    direction: Point,
    base_cm: float = 0.0,
    receiver_elev_cm: float = 0.0,
) -> list[list[tuple[int, int]]]:
    """Project 3D structural triangles (walls + pitched roof) onto ``z = receiver_elev_cm`` (#440)."""
    if elevation_deg < MIN_SUN_ELEVATION_DEG or not roof_triangles:
        return []
    tan_a = math.tan(math.radians(elevation_deg))
    dx, dy = direction
    paths: list[list[tuple[int, int]]] = []
    for tri in roof_triangles:
        clipped = _clip_triangle_above_z(tri, base_cm, receiver_elev_cm)
        if len(clipped) < 3:
            continue
        poly: list[tuple[int, int]] = []
        for vx, vy, vz in clipped:
            dz = max(0.0, vz - receiver_elev_cm)
            s = dz / tan_a
            poly.append(
                (round((vx + s * dx) * CLIPPER_SCALE), round((vy + s * dy) * CLIPPER_SCALE))
            )
        area = pyclipper.Area(poly)
        if abs(area) <= 0.0:
            continue
        if area < 0.0:
            poly.reverse()
        paths.append(poly)
    return paths


# ── one caster's ring set as simple rings (issue #444) ────────────

#: Above this many vertices a ring is swept as it comes: the self-crossing test is a
#: ``SimplifyPolygons`` call, and the loader accepts polygons up to
#: ``MAX_POLYGON_VERTICES`` (16 384) — measured, that call costs 0.12 ms at 256
#: vertices, 0.93 ms at 1 024, 20 ms at 4 096 and **257 ms at 16 384**, on every
#: walk (the overlay recompute and every sun snapshot). The bound is ADR-057's
#: painting bound, for the same class of crafted plan. Nothing regresses above it:
#: such a ring is swept exactly as it was before this repair existed, and a
#: user-drawn crossing outline stays far below it. The hole half of the repair has
#: no such bound: a stroke's rings are grouped by winding and bridged, which is
#: linear in the ring and cheap next to that stroke's own sweep (measured, a
#: crafted 8 192-point closed fence: 13.2 ms here against 64.5 ms in the offset
#: that built the rings, and 18.5 against 248.3 at 16 384 points).
MAX_REGION_VERTICES = 256


def _region_needs_repair(rings: list[list[tuple[int, int]]]) -> bool:
    """Is this ring set already one simple ring per piece?

    Two things need the repair: a ring set in which some ring encloses a NEGATIVE
    area (a hole — the stroke of a fence that closes on itself), and a ring whose
    own outline is not one simple ring (a self-crossing outline). A LONE ring is
    never a hole, whatever its winding: a solid drawn clockwise is a solid, and the
    sweep already normalises a ring's winding. Everything else is left alone, point
    for point — the rule ``tests/fixtures/shadows/shadow_golden.json`` pins for the
    ground.

    "Not one simple ring" is decided by the decomposition, not by an area
    difference: a self-crossing ring can decompose into an outer **plus a hole**
    whose total area is SMALLER than the ring's printed area (a pentagram: printed
    235,114 cm², five lobes 124,108 cm², a hole of 110,000 — the sign of a
    difference test is not fixed), so any decomposition into more than one ring
    means the outline crosses itself. Above ``MAX_REGION_VERTICES`` the test is
    skipped (see that constant).
    """
    for ring in rings:
        if len(ring) <= MAX_REGION_VERTICES:
            lobes = pyclipper.SimplifyPolygons([ring], pyclipper.PFT_EVENODD)
            if len(lobes) != 1:
                return True
            area = pyclipper.Area(ring)
            if abs(pyclipper.Area(lobes[0])) - abs(area) > _RING_AREA_SLACK:
                return True
    return len(rings) > 1 and any(pyclipper.Area(ring) < 0 for ring in rings)


def _group_holes_int(
    rings: list[list[tuple[int, int]]],
) -> list[tuple[list[tuple[int, int]], list[list[tuple[int, int]]]]]:
    """``[(outer, [its holes]), ...]`` — roles from the enclosed area's sign.

    A ring with a negative area is a hole and is attached to the SMALLEST outer
    ring that contains it — the innermost one, so an island in a hole (a hole
    inside an island inside a hole) keeps its own hole instead of lending it to
    the outermost ring, which would make a bridged ring cross itself. A negative
    ring that is inside NO outer is not a hole of this region at all — a caller
    passed it on its own — so it is kept as a piece of its own, reversed;
    dropping it would lose ground, and the region it describes is the same ring.
    """
    outers: list[list[tuple[int, int]]] = []
    holes: list[list[tuple[int, int]]] = []
    for ring in rings:
        if pyclipper.Area(ring) < 0:
            holes.append(ring)
        else:
            outers.append(ring)
    groups: list[tuple[list[tuple[int, int]], list[list[tuple[int, int]]]]] = [
        (outer, []) for outer in outers
    ]
    for hole in holes:
        innermost: tuple[list[tuple[int, int]], list[list[tuple[int, int]]]] | None = None
        for group in groups:
            if not _hole_is_inside(hole, group[0]):
                continue
            if innermost is None or abs(pyclipper.Area(group[0])) < abs(
                    pyclipper.Area(innermost[0])):
                innermost = group
        if innermost is None:
            groups.append((list(reversed(hole)), []))
        else:
            innermost[1].append(hole)
    return groups


def _hole_is_inside(hole: list[tuple[int, int]], outer: list[tuple[int, int]]) -> bool:
    """Is ``hole`` inside ``outer``? One vertex normally, a majority on a tie.

    An offset's hole lies strictly inside its outer, so the first vertex answers in
    one ``PointInPolygon`` call — a full scan would be O(vertices × vertices) and cost
    seconds on a crafted 16,384-point closed fence. A vertex exactly ON the outer's
    boundary (``-1``) is the interesting case: two pieces of one pinched outline share
    a vertex exactly, and treating that shared point as "inside" would make a hole of
    a sibling lobe. Then, and only then, a MAJORITY of the ring's vertices must be
    strictly inside (``== 1``), counted with an early exit.
    """
    first = int(pyclipper.PointInPolygon(hole[0], outer))
    if first != -1:
        return first == 1
    needed = len(hole) // 2 + 1
    inside = 0
    for index, point in enumerate(hole):
        if int(pyclipper.PointInPolygon(point, outer)) == 1:
            inside += 1
            if inside >= needed:
                return True
        elif inside + len(hole) - index - 1 < needed:
            return False
    return inside >= needed


#: X offsets tried, in grid steps, to place a bridge's vertical ray off a
#: vertex. 0 first (a straight bridge), then the nearest clear columns.
_BRIDGE_RAY_OFFSETS = (0, 1, -1, 2, -2, 3, -3, 4, -4)


def _bridge_holes_int(
    outer: list[tuple[int, int]], holes: list[list[tuple[int, int]]]
) -> list[tuple[int, int]]:
    """One simple ring: each hole cut open along a zero-width slit (#444).

    A vertical slit runs from the hole's topmost vertex to the nearest boundary
    above it, and the ring visits it down and up again. The slit encloses no
    area, so the ring's region is exactly ``outer - holes`` — the shadow of the
    stroke, not of a slab. The nearest boundary above a hole's topmost vertex is
    always there: the hole is strictly inside the outer ring. Holes are bridged
    from the highest down, so a lower hole's slit meets the boundary above it
    (the outer's or a higher hole's) and the result stays simple.
    """
    ring = list(outer)
    for hole in sorted(holes, key=lambda h: max(y for _x, y in h), reverse=True):
        v_index = max(range(len(hole)), key=lambda i: (hole[i][1], hole[i][0]))
        vx, vy = hole[v_index]
        bridge: tuple[int, tuple[int, int]] | None = None
        for offset in _BRIDGE_RAY_OFFSETS:
            ray_x = vx + offset
            best: tuple[int, tuple[int, int]] | None = None
            for index in range(len(ring)):
                a, b = ring[index], ring[(index + 1) % len(ring)]
                if a[0] == b[0]:  # vertical: a vertical ray cannot cross it
                    continue
                if min(a[0], b[0]) <= ray_x <= max(a[0], b[0]):
                    t = (ray_x - a[0]) / (b[0] - a[0])
                    y = a[1] + t * (b[1] - a[1])
                    if y > vy and (best is None or y < best[1][1]):
                        best = (index, (ray_x, round(y)))
            if best is not None:
                bridge = best
                break
        if bridge is None:  # pragma: no cover - malformed caller rings only
            # A malformed ring set (a "hole" with no boundary above it) keeps the
            # outer ring as it came - today's over-shading - rather than taking the
            # window down in a paint-adjacent recompute. The extractor's holes always
            # have a boundary above them; this is a hand-built set's fallback.
            return list(outer)
        index, cross = bridge
        v = (vx, vy)
        around_hole = hole[v_index + 1:] + hole[:v_index]
        ring = ring[:index + 1] + [cross, v] + around_hole + [v, cross] + ring[index + 1:]
    return ring
