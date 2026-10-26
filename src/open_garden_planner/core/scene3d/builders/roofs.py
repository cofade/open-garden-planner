"""A gable roof and the walls under it, from a ridge line (Phase 17 L1.6).

The roof is two planes through the ridge LINE:

    z_top(p) = top − cap_rise − slope · |d(p)|        d = signed distance to the line

over the footprint grown by the overhang. That is the model the 2D canvas
already paints — ``PolygonItem._paint_with_ridge`` splits the house along the
infinite line through its ridge and lays the tiles down-slope on either side —
so 2D and 3D agree for any footprint (convex or not) and any ridge chord,
including one the user dragged off-centre.

Truth:

- **the top is the height**: the ridge tile's apex line is at exactly ``top_cm``
  (ADR-037: a building's height is its ridge height) and lies ON the ridge line;
- **ridge = live ridge**: that line runs through the record's ridge ends on to
  the roof's edge — the overhang measured square to the wall it crosses, so
  ``overhang / cos θ`` beyond a ridge end whose wall the ridge meets at θ, and
  exactly the overhang where it meets the wall squarely;
- **faces**: every face stores its winding normal, and its winding is forced to
  the side the face looks at (``flat_mesh(outward=…)``).

The plan holds a ridge HEIGHT but no pitch: the slope is the style's, flattened
where it would push the eaves under ``eave_floor_cm`` (a door still fits).
Ported from the spike's ``gable_house_parts``, which handled convex footprints
at scene positions and left the slab's edges open.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from ..mesh import Mesh
from .palette import TINT, PaletteColor
from .primitives import (
    F64,
    ccw_ring,
    flat_mesh,
    offset_ring,
    polygon_triangles,
    split_triangles_by_line,
)

#: A ridge shorter than this (cm) has no direction.
MIN_RIDGE_CM = 1.0
_ON_LINE = 1e-7


@dataclass(frozen=True, slots=True)
class RoofStyle:
    """What the plan does not hold about a roof (module docstring)."""

    tile: PaletteColor
    cap: PaletteColor
    timber: PaletteColor
    overhang_cm: float = 30.0
    pitch_deg: float = 38.0
    slab_cm: float = 12.0
    cap_rise_cm: float = 5.0
    cap_half_width_cm: float = 9.0
    eave_floor_cm: float = 220.0
    eave_floor_share: float = 0.75


@dataclass(frozen=True, slots=True)
class GableRoof:
    """The two meshes of a roofed building, and what the gates measure."""

    walls: Mesh
    roof: Mesh
    #: (start, end) of each stretch of the ridge tile's apex line, item-local xy.
    ridge_runs: tuple[tuple[tuple[float, float], tuple[float, float]], ...]
    slope: float
    eave_cm: float
    #: The top of the walls over plan points (..., 2) -> heights (...): the slab's
    #: underside where it meets them — what a window or a door must stay under
    #: (L4.1 facade). Every roof style sets it.
    wall_top: Callable[[F64], F64] | None = None


def _crossings(ring: F64, origin: F64, along: F64, normal: F64) -> list[float]:
    """Where the line through ``origin`` crosses the ring: sorted positions along it."""
    distance = (ring - origin) @ normal
    following = np.roll(distance, -1)
    points_after = np.roll(ring, -1, axis=0)
    hits: list[float] = []
    for index in range(len(ring)):  # a footprint's edges
        here, there = float(distance[index]), float(following[index])
        if (here > _ON_LINE and there < -_ON_LINE) or (here < -_ON_LINE and there > _ON_LINE):
            point = ring[index] + (points_after[index] - ring[index]) * (here / (here - there))
            hits.append(float((point - origin) @ along))
        elif abs(here) <= _ON_LINE:  # a vertex on the line counts once, at its own edge start
            before = float(distance[index - 1])
            after = there
            if (before > _ON_LINE and after < -_ON_LINE) or (before < -_ON_LINE and after > _ON_LINE):
                hits.append(float((ring[index] - origin) @ along))
    return sorted(hits)


def _inside(ring: F64, point: F64) -> bool:
    """Even-odd point-in-polygon."""
    x, y = float(point[0]), float(point[1])
    following = np.roll(ring, -1, axis=0)
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, following, strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def _split_edges(ring: F64, origin: F64, normal: F64) -> tuple[F64, F64]:
    """The ring's edges as (starts, ends), each edge cut where it crosses the line —
    so every piece lies on one side of the ridge."""
    distance = (ring - origin) @ normal
    starts: list[F64] = []
    ends: list[F64] = []
    count = len(ring)
    for index in range(count):
        here, there = ring[index], ring[(index + 1) % count]
        d_here, d_there = float(distance[index]), float(distance[(index + 1) % count])
        if (d_here > _ON_LINE and d_there < -_ON_LINE) or (d_here < -_ON_LINE and d_there > _ON_LINE):
            middle = here + (there - here) * (d_here / (d_here - d_there))
            starts += [here, middle]
            ends += [middle, there]
        else:
            starts.append(here)
            ends.append(there)
    return np.stack(starts), np.stack(ends)


def bounding_box_ridge(footprint: ArrayLike) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """A ridge for a building the plan gives none (sheds): the long axis of the
    footprint's bounding box, through its centre, from edge to edge.

    The box is the one aligned with the footprint's LONGEST EDGE, in the
    item-local frame — so the ridge is parallel to the building's own long walls
    however the footprint lies in its frame (a rectangle item's is axis-aligned;
    a polygon drawn at an angle is not). The spike took the scene-frame bounding
    box, which gave a turned shed a ridge askew to its walls.
    """
    ring = ccw_ring(footprint)
    if len(ring) < 3:
        return None
    edge = np.roll(ring, -1, axis=0) - ring
    length = np.linalg.norm(edge, axis=1)
    longest = int(length.argmax())
    along = edge[longest] / length[longest]
    across = np.array([-along[1], along[0]])
    u, v = ring @ along, ring @ across
    if float(u.max() - u.min()) >= float(v.max() - v.min()):
        middle = (float(v.min()) + float(v.max())) / 2.0
        ends = [along * float(u.min()) + across * middle, along * float(u.max()) + across * middle]
    else:
        middle = (float(u.min()) + float(u.max())) / 2.0
        ends = [along * middle + across * float(v.min()), along * middle + across * float(v.max())]
    start, end = sorted(((float(x) + 0.0, float(y) + 0.0) for x, y in ends))
    return start, end


def gable_roof(footprint: ArrayLike, ridge: tuple[tuple[float, float], tuple[float, float]],
               top_cm: float, style: RoofStyle) -> GableRoof | None:
    """Walls and roof of a building whose ridge tile tops out at ``top_cm``.

    Returns None when there is nothing to build a roof from — a footprint with
    fewer than three corners, a ridge without a direction or one whose line
    misses the building, a building too low for a slab — so the caller can fall
    back to a plain block.
    """
    ring = ccw_ring(footprint)
    start = np.asarray(ridge[0], dtype=np.float64)
    end = np.asarray(ridge[1], dtype=np.float64)
    length = float(np.linalg.norm(end - start))
    if len(ring) < 3 or length < MIN_RIDGE_CM or not np.isfinite(start + end).all():
        return None
    along = (end - start) / length
    normal = np.array([-along[1], along[0]])  # to the left of the ridge
    crease = top_cm - style.cap_rise_cm  # where the two slab tops meet
    apex = crease - style.slab_cm  # the walls' peak under the ridge
    if apex <= 1.0:
        return None

    def distance(points: F64) -> F64:
        away: F64 = np.abs((points - start) @ normal)
        return away

    reach = float(distance(ring).max())
    if reach <= 1e-6:
        return None
    slope = math.tan(math.radians(style.pitch_deg))
    eave = apex - slope * reach
    floor = min(style.eave_floor_cm, style.eave_floor_share * apex)
    if eave < floor:
        eave = floor
        slope = (apex - floor) / reach

    outline = offset_ring(ring, style.overhang_cm)
    runs = _crossings(outline, start, along, normal)
    ridge_runs = [(runs[i], runs[i + 1]) for i in range(0, len(runs) - 1, 2)
                  if _inside(outline, start + along * ((runs[i] + runs[i + 1]) / 2.0))]
    if not ridge_runs:
        return None

    def lifted(points: F64, drop: float) -> F64:
        """Plan points (…, 2) onto the roof plane, ``drop`` cm below the slab's top."""
        z = crease - drop - slope * distance(points.reshape(-1, 2)).reshape(points.shape[:-1])
        return np.concatenate([points, z[..., None]], axis=-1)

    # ── roof: tiles, underside, fascia, ridge tile ───────────────────────────
    left, right = split_triangles_by_line(polygon_triangles(outline), start, normal)
    slab = np.concatenate([left, right])
    up, down = (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)
    edge_start, edge_end = _split_edges(outline, start, normal)
    edge = edge_end - edge_start
    fascia_out = np.concatenate([np.stack([edge[:, 1], -edge[:, 0]], axis=1),
                                 np.zeros((len(edge), 1))], axis=1)
    fascia = np.stack([lifted(edge_start, style.slab_cm), lifted(edge_end, style.slab_cm),
                       lifted(edge_end, 0.0), lifted(edge_start, 0.0)], axis=1)
    half = style.cap_half_width_cm
    foot = crease - slope * half
    cap_triangles: list[F64] = []
    cap_out: list[tuple[float, float, float]] = []
    runs_xy: list[tuple[tuple[float, float], tuple[float, float]]] = []
    # where each of the ridge tile's two foot lines crosses the roof's edge: the tile
    # is cut flush with the edge, also where the ridge meets it at an angle
    foot_hits = {side: _crossings(outline, start + side * half * normal, along, normal)
                 for side in (1.0, -1.0)}
    for run_start, run_end in ridge_runs:
        p0, p1 = start + along * run_start, start + along * run_end
        runs_xy.append(((float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1]))))
        apex0, apex1 = np.array([*p0, top_cm]), np.array([*p1, top_cm])
        feet: dict[float, tuple[F64, F64]] = {}
        for side in (1.0, -1.0):
            hits = foot_hits[side]
            s0 = min(hits, key=lambda s: abs(s - run_start)) if hits else run_start
            s1 = min(hits, key=lambda s: abs(s - run_end)) if hits else run_end
            base = start + side * half * normal
            foot0, foot1 = np.array([*(base + along * s0), foot]), np.array([*(base + along * s1), foot])
            feet[side] = (foot0, foot1)
            cap_triangles += [np.stack([foot0, foot1, apex1]), np.stack([foot0, apex1, apex0])]
            cap_out += [(side * normal[0], side * normal[1], 1.0)] * 2
        for index, apex_point, facing in ((0, apex0, -1.0), (1, apex1, 1.0)):
            cap_triangles.append(np.stack([feet[1.0][index], apex_point, feet[-1.0][index]]))
            cap_out.append((facing * along[0], facing * along[1], 0.0))
    roof = Mesh.merge([
        flat_mesh(lifted(slab, 0.0), style.tile.linear, outward=up),
        flat_mesh(lifted(slab, style.slab_cm), style.timber.linear, outward=down),
        flat_mesh(fascia[:, [0, 1, 2, 0, 2, 3]].reshape(-1, 3, 3), style.timber.linear,
                  outward=np.repeat(fascia_out, 2, axis=0)),
        flat_mesh(np.stack(cap_triangles), style.cap.linear, outward=np.asarray(cap_out)),
    ])

    # ── walls: one trapezoid per footprint edge, up to the slab's underside ──
    wall_start, wall_end = _split_edges(ring, start, normal)
    wall = wall_end - wall_start
    wall_out = np.concatenate([np.stack([wall[:, 1], -wall[:, 0]], axis=1),
                               np.zeros((len(wall), 1))], axis=1)
    ground_start = np.concatenate([wall_start, np.zeros((len(wall), 1))], axis=1)
    ground_end = np.concatenate([wall_end, np.zeros((len(wall), 1))], axis=1)
    quads = np.stack([ground_start, ground_end, lifted(wall_end, style.slab_cm),
                      lifted(wall_start, style.slab_cm)], axis=1)
    walls = flat_mesh(quads[:, [0, 1, 2, 0, 2, 3]].reshape(-1, 3, 3), TINT,
                      outward=np.repeat(wall_out, 2, axis=0))

    def wall_top(points: F64) -> F64:
        plan = np.asarray(points, dtype=np.float64)
        under: F64 = crease - style.slab_cm - slope * distance(plan.reshape(-1, 2))
        return under.reshape(plan.shape[:-1])

    return GableRoof(walls, roof, tuple(runs_xy), slope, eave, wall_top)


# ── hip, shed and flat roofs (Phase 17 L4.1, #388) ───────────────────────────
#
# Three more ways to cover the same walls, chosen by the item's ``roof_style``
# (``core/roof_style``). The truth rules are the gable's: the roof's TOP is the
# building's height (the plan's height is the ridge's, ADR-037); the slope is the
# style's or the user's pitch, flattened where it would push the eaves under the
# eave floor; every face stores its winding normal.


def _walls_under(ring: F64, top_at: Callable[[F64], F64]) -> Mesh:
    """One quad per footprint edge, from the ground up to ``top_at`` (a plane, so
    each quad is planar), facing out of a counter-clockwise ring."""
    start, end = ring, np.roll(ring, -1, axis=0)
    edge = end - start
    out = np.concatenate([np.stack([edge[:, 1], -edge[:, 0]], axis=1), np.zeros((len(edge), 1))], axis=1)
    ground = np.zeros((len(edge), 1))
    quads = np.stack([np.concatenate([start, ground], axis=1), np.concatenate([end, ground], axis=1),
                      np.concatenate([end, top_at(end)[:, None]], axis=1),
                      np.concatenate([start, top_at(start)[:, None]], axis=1)], axis=1)
    return flat_mesh(quads[:, [0, 1, 2, 0, 2, 3]].reshape(-1, 3, 3), TINT,
                     outward=np.repeat(out, 2, axis=0))


def _fascia(outline: F64, top_at: Callable[[F64], F64], slab: float, color: ArrayLike) -> Mesh:
    """The slab's edge round ``outline``: one quad per edge from the underside to the top."""
    start, end = outline, np.roll(outline, -1, axis=0)
    edge = end - start
    out = np.concatenate([np.stack([edge[:, 1], -edge[:, 0]], axis=1), np.zeros((len(edge), 1))], axis=1)

    def at(points: F64, drop: float) -> F64:
        return np.concatenate([points, (top_at(points) - drop)[:, None]], axis=1)

    quads = np.stack([at(start, slab), at(end, slab), at(end, 0.0), at(start, 0.0)], axis=1)
    return flat_mesh(quads[:, [0, 1, 2, 0, 2, 3]].reshape(-1, 3, 3), color,
                     outward=np.repeat(out, 2, axis=0))


def _slab(triangles: F64, top_at: Callable[[F64], F64], slab: float, tile: ArrayLike,
          under: ArrayLike) -> Mesh:
    """Plan triangles (t, 3, 2) lifted onto the roof's top (``tile``, facing up) and,
    ``slab`` lower, onto its underside (``under``, facing down)."""
    flat = np.asarray(triangles, dtype=np.float64).reshape(-1, 2)
    top = np.concatenate([flat, top_at(flat)[:, None]], axis=1).reshape(-1, 3, 3)
    bottom = top - np.array([0.0, 0.0, slab])
    return Mesh.merge([flat_mesh(top, tile, outward=(0.0, 0.0, 1.0)),
                       flat_mesh(bottom, under, outward=(0.0, 0.0, -1.0))])


def _floor(style: RoofStyle, top_cm: float) -> float:
    """The lowest the walls may end under a pitched roof: a door still fits."""
    return min(style.eave_floor_cm, style.eave_floor_share * (top_cm - style.slab_cm))


def eave_floor(style: RoofStyle, top_cm: float) -> float:
    """The lowest the walls may end under a pitched roof of ``style`` topping out at
    ``top_cm`` (what the gable and the hip hold their eaves to)."""
    return _floor(style, top_cm)


def is_convex(footprint: ArrayLike) -> bool:
    """True for a convex counter-clockwise outline (collinear corners allowed)."""
    ring = ccw_ring(footprint)
    if len(ring) < 3:
        return False
    edge = np.roll(ring, -1, axis=0) - ring
    following = np.roll(edge, -1, axis=0)
    turn = edge[:, 0] * following[:, 1] - edge[:, 1] * following[:, 0]
    scale = np.linalg.norm(edge, axis=1) * np.linalg.norm(following, axis=1)
    return bool((turn >= -1e-9 * np.maximum(scale, 1e-12)).all())


def _clip(polygon: F64, normal: F64, bound: float) -> F64:
    """The part of a convex polygon where ``point · normal <= bound``."""
    if len(polygon) == 0:
        return polygon
    value = polygon @ normal - bound
    kept: list[F64] = []
    for index in range(len(polygon)):
        here, there = polygon[index], polygon[(index + 1) % len(polygon)]
        a, b = float(value[index]), float(value[(index + 1) % len(polygon)])
        if a <= 1e-9:
            kept.append(here)
        if (a < -1e-9 and b > 1e-9) or (a > 1e-9 and b < -1e-9):
            kept.append(here + (there - here) * (a / (a - b)))
    return np.asarray(kept, dtype=np.float64).reshape(-1, 2)


#: A hip roof is cut face by face against every other face (n² clips): an outline of
#: more corners — a drawn circle — gets a gable instead.
MAX_HIP_CORNERS = 64


def hip_roof(footprint: ArrayLike, top_cm: float, style: RoofStyle) -> GableRoof | None:
    """Walls and a hip roof over a CONVEX footprint: every edge of the eaves slopes
    up at the same pitch, so the roof is the lower envelope of one plane per edge —
    on a rectangle four faces meeting in a ridge, on a square a pyramid. Its apex
    (or ridge) is at ``top_cm``. None for a footprint that is not convex (a hip roof
    over an L needs a straight skeleton; the caller shows another roof)."""
    ring = ccw_ring(footprint)
    if len(ring) < 3 or len(ring) > MAX_HIP_CORNERS or not is_convex(ring):
        return None
    outline = offset_ring(ring, style.overhang_cm)
    edge = np.roll(outline, -1, axis=0) - outline
    edge /= np.maximum(np.linalg.norm(edge, axis=1, keepdims=True), 1e-12)
    inward = np.stack([-edge[:, 1], edge[:, 0]], axis=1)  # left of travel: the inside
    offsets = (outline * inward).sum(axis=1)
    count = len(outline)
    faces: list[tuple[int, F64]] = []
    for i in range(count):  # the part of the outline where edge i is the nearest
        face = outline.copy()
        for j in range(count):
            if j != i:
                face = _clip(face, inward[i] - inward[j], offsets[i] - offsets[j])  # d_i <= d_j
        if len(face) >= 3:
            faces.append((i, face))
    if not faces:
        return None
    reach = max(float((face @ inward[i] - offsets[i]).max()) for i, face in faces)
    slope = math.tan(math.radians(style.pitch_deg))
    floor = _floor(style, top_cm)
    if top_cm - style.slab_cm - slope * (reach - style.overhang_cm) < floor:
        slope = max(0.0, (top_cm - style.slab_cm - floor) / max(reach - style.overhang_cm, 1e-6))
    eave = top_cm - slope * reach  # the slab's top at the outline
    if eave - style.slab_cm <= 1.0:
        return None

    def top_at(points: F64) -> F64:
        plan = np.asarray(points, dtype=np.float64)
        nearest = (plan.reshape(-1, 2) @ inward.T - offsets[None, :]).min(axis=1)
        heights: F64 = eave + slope * np.maximum(nearest, 0.0)
        return heights.reshape(plan.shape[:-1])

    triangles = np.concatenate([np.stack([np.stack([face[0], face[k], face[k + 1]])
                                          for k in range(1, len(face) - 1)]) for _i, face in faces])
    roof = Mesh.merge([_slab(triangles, top_at, style.slab_cm, style.tile.linear, style.timber.linear),
                       _fascia(outline, top_at, style.slab_cm, style.timber.linear)])
    wall_z = eave + slope * style.overhang_cm - style.slab_cm

    def wall_top(points: F64) -> F64:
        heights: F64 = np.full(np.asarray(points).shape[:-1], wall_z)
        return heights

    return GableRoof(_walls_under(ring, wall_top), roof, (), slope, eave, wall_top)


def shed_roof(footprint: ArrayLike, top_cm: float, style: RoofStyle,
              high: tuple[float, float] = (0.0, 1.0)) -> GableRoof | None:
    """Walls and a mono-pitch (shed) roof: one plane rising toward ``high`` (a plan
    direction in the item's own frame), its high eave at ``top_cm``. Any outline."""
    ring = ccw_ring(footprint)
    if len(ring) < 3 or top_cm - style.slab_cm <= 1.0:
        return None
    up = np.asarray(high, dtype=np.float64)
    up /= max(float(np.linalg.norm(up)), 1e-12)
    outline = offset_ring(ring, style.overhang_cm)
    peak = float((outline @ up).max())
    span = peak - float((ring @ up).min())
    slope = math.tan(math.radians(style.pitch_deg))
    floor = _floor(style, top_cm)
    if top_cm - style.slab_cm - slope * span < floor:
        slope = max(0.0, (top_cm - style.slab_cm - floor) / max(span, 1e-6))

    def top_at(points: F64) -> F64:
        heights: F64 = top_cm - slope * (peak - np.asarray(points, dtype=np.float64) @ up)
        return heights

    def wall_top(points: F64) -> F64:
        under: F64 = top_at(points) - style.slab_cm
        return under

    roof = Mesh.merge([_slab(polygon_triangles(outline), top_at, style.slab_cm, style.tile.linear,
                             style.timber.linear),
                       _fascia(outline, top_at, style.slab_cm, style.timber.linear)])
    return GableRoof(_walls_under(ring, wall_top), roof, (), slope, top_cm - slope * span, wall_top)


def flat_roof(footprint: ArrayLike, top_cm: float, style: RoofStyle) -> GableRoof | None:
    """Walls and a flat roof slab whose top is ``top_cm``, overhanging by the style's
    overhang."""
    ring = ccw_ring(footprint)
    slab = min(style.slab_cm, 0.3 * top_cm)
    if len(ring) < 3 or top_cm - slab <= 1.0:
        return None
    outline = offset_ring(ring, style.overhang_cm)

    def top_at(points: F64) -> F64:
        heights: F64 = np.full(np.asarray(points).shape[:-1], top_cm)
        return heights

    def wall_top(points: F64) -> F64:
        heights: F64 = np.full(np.asarray(points).shape[:-1], top_cm - slab)
        return heights

    roof = Mesh.merge([_slab(polygon_triangles(outline), top_at, slab, style.tile.linear,
                             style.timber.linear),
                       _fascia(outline, top_at, slab, style.timber.linear)])
    return GableRoof(_walls_under(ring, wall_top), roof, (), 0.0, top_cm - slab, wall_top)
