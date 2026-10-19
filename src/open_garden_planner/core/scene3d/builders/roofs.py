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
    return GableRoof(walls, roof, tuple(runs_xy), slope, eave)
