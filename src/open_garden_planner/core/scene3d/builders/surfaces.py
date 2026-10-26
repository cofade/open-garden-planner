"""Surfaces: paths, terraces, driveways, decks, ponds and lawns (Phase 17 L4.2 / L4.5, #388).

The ground bake paints these items flat (L1.5) — their texture, their colour,
their pattern, exactly as the canvas does. This module adds what a flat picture
cannot: RELIEF on top of it. Every part here is a ``ground_detail`` part
(``mesh.MeshPart``): the item stays painted under it (it is not a solid for the
ground bake), it is never picked (a click reaches the ground, as before L4) and
it casts no shadow (the plan gives a surface no height).

- **PATH**, by its style — where the 2D painter draws stones or planks, the 3D
  ones lie on the same spots (``walk_path`` is the painter's own walk):
  STEPPING_STONES — bevelled stones, 0.8 × 0.6 of the width, every 1.8 widths;
  WOODEN_BOARDWALK — planks across the path every 0.35 widths on two stringers;
  PAVED_PATH — a kerb along both edges; GRAVEL_PATH — a dark edging along both
  edges and scattered pebbles; DIRT_PATH and a plain line — nothing: they are
  flat. All in the line's own colour (``tinted``), the 2D painter's shading
  as weights.
- **TERRACE_PATIO, DRIVEWAY**: a kerb inside the outline. A decking or wood
  pattern (``params["surface_pattern"]``) makes it a DECK: boards with gaps
  across the outline. A terrace the user gave a HEIGHT is a raised deck or
  platform — a solid (its boards' top is the height) that casts a shadow.
- **POND_POOL**: water (the ``water`` material, in the item's colour) just above
  the painted ground, inside a stone coping that overlaps the edge.
- **LAWN**: grass blades — only drawn at the High and Ultra presets (the look's
  ``lawn_blades``; the engine hides them below) — in the lawn's colour, swaying
  with the wind, nowhere under a flat item painted ABOVE the lawn
  (``params["lawn_cutouts"]``, the snapshot's), so a path on a lawn stays clear.

Relief stays inside the footprint plus 10 cm (issue #388's truth gate) and low:
the tallest is a deck's boards, 6 cm.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from typing import Final, NamedTuple

import numpy as np
from numpy.typing import NDArray

from ..build import BuilderRegistry, default_builder, item_seed, prism_mesh
from ..mesh import Mesh, MeshPart
from ..polygon import cut_region
from ..record import (
    PARAM_LAWN_BLADES,
    PARAM_LAWN_CUTOUTS,
    PARAM_PATH_STYLE,
    PARAM_RADIUS_CM,
    PARAM_SEED,
    PARAM_SURFACE_PATTERN,
    SHAPE_CIRCLE,
    Record,
    Ring,
)
from . import palette
from .common import centre_line
from .kit import beam
from .primitives import F64, bevelled_boxes, flat_mesh, signed_area, sweep

#: The kinds this module builds.
KINDS: Final[tuple[str, ...]] = ("PATH", "TERRACE_PATIO", "DRIVEWAY", "POND_POOL", "LAWN")
#: The part name of a lawn's blades — the engine shows it at the presets whose look
#: says ``lawn_blades`` (High, Ultra).
LAWN_BLADES: Final = "lawn_blades"
#: Fill patterns that make a terrace a deck of boards.
DECK_PATTERNS: Final[frozenset[str]] = frozenset({"DECKING", "WOOD"})

#: A path narrower than this (cm) gets no relief: a line that thin is a 2D pattern, not
#: a path one walks on (plans from before L4 drew paths 5 to 10 cm wide).
MIN_RELIEF_WIDTH_CM: Final = 20.0
#: Relief heights (cm): a stone, a kerb, a board's top, the water's surface.
STONE_CM: Final = 4.0
KERB_CM: Final = 3.0
BOARD_TOP_CM: Final = 6.0
#: A terrace's deck boards: low, because the furniture on a deck stands on the plan's
#: ground (z 0) — at 6 cm a chair's legs sank into the boards (3D review of #388).
DECK_TOP_CM: Final = 2.5
WATER_CM: Final = 1.0
#: A pond's coping: how far it reaches over the water, out over the bank, and up (cm).
COPING_IN_CM: Final = 13.0
COPING_OUT_CM: Final = 7.0
COPING_UP_CM: Final = 7.0

#: Blades per square metre of lawn, and at most this many per lawn (a large lawn
#: gets a sparser sward rather than an unbounded mesh: 3 triangles a blade).
BLADES_PER_M2: Final = 220.0
MAX_BLADES: Final = 36_000
#: The jittered grid the blades' roots are drawn from lies over the lawn's BOUNDING
#: BOX: at most this many grid points, and at most ``MAX_SWARD_WORK`` point-in-ring
#: tests (points x the outline's edges), whatever the lawn's shape — a thin diagonal
#: strip kilometres long has a small area and a huge box, and gets a sparser sward
#: rather than billions of grid points.
MAX_SWARD_GRID: Final = 4 * MAX_BLADES
MAX_SWARD_WORK: Final = 400_000_000
#: The most stones, planks or pebbles one path gets: a path kilometres long gets
#: no relief rather than an unbounded mesh (the 2D pattern stays on the ground).
MAX_PATH_ELEMENTS: Final = 2_000
#: The most ROWS of deck boards one surface gets; beyond, each board is wider.
MAX_BOARDS: Final = 400
#: The most deck boards one surface gets in all (rows × the runs of each row): a deck
#: beyond it gets no boards — a kerb on the ground, the plain solid when raised (senior
#: review of #388: a comb-shaped deck of 402 vertices built 446,364 triangles in 14 s
#: on the GUI thread, one of 8,002 did not finish).
MAX_DECK_BOARDS: Final = 2_000
#: The most board rows a deck's scan looks at, over ALL its regions: with
#: ``MAX_RELIEF_VERTICES`` this bounds the WORK, not only the boards — a self-crossing
#: sawtooth of 601 regions narrower than a board scanned 400 rows each and built
#: nothing in 2.8 s (senior review of #388, round 2). Beyond it: a kerb or the solid.
MAX_DECK_ROWS: Final = 1_000
#: The most outline vertices a surface's relief is swept along (a kerb, a raised deck's
#: skirt, a pond's coping: 12-16 triangles a vertex): beyond it the surface keeps its
#: painted ground and no relief — a raised deck is its plain solid (senior review of
#: #388: a kerb of 768,000 triangles for an outline of 64,000 vertices).
MAX_RELIEF_VERTICES: Final = 4_096
#: A blade's height (cm), before its ±30 % variation.
BLADE_CM: Final = 7.0

Color = tuple[float, float, float, float]


def _shade(weight: float) -> Color:
    """A tinted part's vertex colour: a shading weight the sink multiplies with the
    item's tint (``palette.TINT`` is weight 1)."""
    return (weight, weight, weight, 1.0)


def _relief(meshes: list[Mesh], name: str, kind: str = "vc", *, tinted: bool = True) -> tuple[MeshPart, ...]:
    mesh = Mesh.merge(meshes)
    if not mesh.vertex_count:
        return ()
    return (MeshPart(mesh, kind, casts_shadow=False, tinted=tinted, name=name, ground_detail=True),)


# ── the 2D painter's walk ────────────────────────────────────────────────────


def walk_path(path: F64, spacing: float) -> tuple[F64, F64]:
    """``PathStylePaint._walk_path`` in numpy: the points every ``spacing`` along a
    polyline — each segment starting where the last one's spacing left off — and the
    unit direction of the segment each lies on. ``(points (n, 2), directions (n, 2))``."""
    points: list[F64] = []
    directions: list[F64] = []
    if len(path) < 2 or not spacing > 0.05:
        return np.zeros((0, 2)), np.zeros((0, 2))
    remaining = 0.0
    for start, end in zip(path[:-1], path[1:], strict=True):
        edge = end - start
        length = float(np.linalg.norm(edge))
        if length < 0.001:
            continue
        along = edge / length
        steps = np.arange(remaining, length + 1e-12, spacing)
        steps = steps[steps <= length]
        points.append(start + steps[:, None] * along)
        directions.append(np.broadcast_to(along, (len(steps), 2)))
        last = steps[-1] if len(steps) else remaining - spacing
        remaining = last + spacing - length
    if not points:
        return np.zeros((0, 2)), np.zeros((0, 2))
    return np.concatenate(points), np.concatenate(directions)


def _closed(record: Record) -> tuple[F64, bool]:
    line, closed = centre_line(record)
    return np.asarray(line, dtype=np.float64), closed


def _offset_line(line: F64, closed: bool, offset: float) -> F64:
    """``line`` moved ``offset`` cm to the left of travel, its joints kept inside the
    path's own outline. The outline (``shadow_geometry.polyline_footprint``) squares
    a bend off at half the path's width from the joint; a MITRED offset line reaches
    ``offset / cos(turn / 2)`` there (3D review of #388: a gravel edging 18.6 cm past
    the path). So on the outside of a bend the two segments' offset ends are joined
    by a chord — no point further than ``|offset|`` from the joint — and on the inside
    the two offset lines meet where they cross (the two ends where they do not)."""
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
    out: list[F64] = [] if closed else [starts[0] + left[0] * offset]
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


def _rails(line: F64, closed: bool, offsets: tuple[float, ...], width: float, height: float,
           color: Color) -> list[Mesh]:
    """Low rails swept along the line at each lateral ``offset`` (left of travel), each
    along its own offset line (``_offset_line``: inside the path's outline)."""
    meshes = []
    half = width / 2.0
    cut = min(0.6, 0.3 * half, 0.3 * height)
    profile = [(-half, 0.0), (half, 0.0), (half, height - cut), (half - cut, height),
               (-half + cut, height), (-half, height - cut)]
    for offset in offsets:
        rail = _offset_line(line, closed, offset)
        if len(rail) >= 2:
            meshes.append(sweep(profile, rail, color, closed=closed))
    return meshes


def _trimmed(line: F64, distance: float) -> F64:
    """An open polyline shortened by ``distance`` at both ends (no points when it is
    not longer than twice that)."""
    lengths = np.linalg.norm(np.diff(line, axis=0), axis=1)
    total = float(lengths.sum())
    if total <= 2.0 * distance:
        return line[:0]
    reach = np.concatenate([[0.0], np.cumsum(lengths)])

    def at(where: float) -> F64:
        index = min(int(np.searchsorted(reach, where, side="right")) - 1, len(lengths) - 1)
        share = (where - reach[index]) / lengths[index] if lengths[index] > 0.0 else 0.0
        return np.asarray(line[index] + (line[index + 1] - line[index]) * share)

    inner = [line[k] for k in range(len(line)) if distance < reach[k] < total - distance]
    return np.asarray([at(distance), *inner, at(total - distance)])


def _on_ground(points: F64, record: Record, margin: float) -> np.ndarray:
    """Which ``points`` lie on the record's ground — inside a region, or within
    ``margin`` cm of one's outline."""
    on = np.zeros(len(points), dtype=bool)
    for outer, holes in record.regions:
        inside = _inside(points, np.asarray(outer, dtype=np.float64))
        for hole in holes:
            inside &= ~_inside(points, np.asarray(hole, dtype=np.float64))
        on |= inside
    if on.all():
        return on
    for outer, holes in record.regions:
        for ring in (outer, *holes):
            closed = np.asarray((*ring, ring[0]), dtype=np.float64)
            start, end = closed[:-1], closed[1:]
            edge = end - start
            length2 = np.maximum((edge * edge).sum(axis=1), 1e-12)
            rest = points[~on]
            t = np.clip(((rest[:, None, :] - start[None]) * edge[None]).sum(axis=2) / length2, 0.0, 1.0)
            gap = np.linalg.norm(rest[:, None, :] - (start[None] + t[:, :, None] * edge[None]), axis=2)
            near = np.zeros(len(points), dtype=bool)
            near[np.flatnonzero(~on)] = gap.min(axis=1) <= margin
            on |= near
    return on


def _path(record: Record) -> tuple[MeshPart, ...]:
    if record.height_cm is not None:  # a path the user gave a height: the plain prism, as before L4
        return default_builder(record)
    style = record.params.get(PARAM_PATH_STYLE)
    width = record.path_width_cm
    if not isinstance(style, str) or width is None or not width >= MIN_RELIEF_WIDTH_CM:
        return ()
    line, closed = _closed(record)
    if len(line) < 2:
        return ()
    # the 2D walk goes round a loop and on; the GROUND (``polyline_footprint``: the
    # stroke with butt ends) is open at a loop's first point too — a square notch
    # there — so the relief that follows the outline treats every path as open
    walked = np.concatenate([line, line[:1]]) if closed else line
    if style == "STEPPING_STONES":
        points, along = walk_path(walked, width * 1.8)
        if not len(points) or len(points) > MAX_PATH_ELEMENTS:
            return ()
        jitter = 0.88 + 0.12 * ((np.arange(len(points)) * 7919) % 13) / 12.0
        # the 2D painter draws a stone wherever its walk lands, also half over a
        # path's end or over the outside of a tight bend; in 3D a stone stays on the
        # path (the truth gate: nothing beyond the footprint plus 10 cm) — slid by
        # half its length along the path where that puts it there, else left out
        across = np.stack([-along[:, 1], along[:, 0]], axis=1)

        def fits(centres: F64) -> np.ndarray:
            corners = [centres + along * (sx * 0.4 * width) + across * (sy * 0.3 * width)
                       for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
            return np.asarray(np.all([_on_ground(corner, record, 9.0) for corner in corners], axis=0),
                              dtype=bool)

        points = points.copy()
        keep = fits(points)
        for shift in (0.4 * width, -0.4 * width):
            if keep.all():
                break
            moved = points + along * shift
            slid = ~keep & fits(moved)
            points[slid] = moved[slid]
            keep |= slid
        if not keep.any():
            return ()
        angles = np.degrees(np.arctan2(along[keep, 1], along[keep, 0]))
        colors = np.stack([jitter[keep], jitter[keep], jitter[keep], np.ones(int(keep.sum()))], axis=1)
        stones = bevelled_boxes(points[keep], (0.8 * width, 0.6 * width), 0.0,
                                min(STONE_CM, 0.08 * width), min(2.0, 0.1 * width), angles, colors)
        return _relief([stones], "stones")
    if style == "WOODEN_BOARDWALK":
        # a plank is 0.3 widths along the path: the first and the last stand half a
        # plank in from an open path's ends (3D review of #388: centred on the end,
        # it reached 15 cm past it)
        planked = _trimmed(walked, 0.15 * width)
        if len(planked) < 2:
            return ()
        points, along = walk_path(planked, width * 0.35)
        if not len(points) or len(points) > MAX_PATH_ELEMENTS:
            return ()
        angles = np.degrees(np.arctan2(along[:, 1], along[:, 0]))
        shade = np.where(np.arange(len(points)) % 2 == 0, 1.0, 0.92)
        colors = np.stack([shade, shade, shade, np.ones(len(points))], axis=1)
        top = min(BOARD_TOP_CM - 1.0, 0.08 * width)
        planks = bevelled_boxes(points, (0.3 * width, width), top - min(2.5, 0.5 * top), top,
                                0.4, angles, colors)
        stringers = _rails(walked, False, (-0.35 * width, 0.35 * width), min(6.0, 0.08 * width),
                           top - min(2.5, 0.5 * top), _shade(0.7))
        return _relief([planks, *stringers], "boardwalk")
    if style == "PAVED_PATH":
        kerb = min(5.0, 0.06 * width)
        return _relief(_rails(walked, False, (-width / 2.0 + kerb / 2.0, width / 2.0 - kerb / 2.0), kerb,
                              min(KERB_CM, 0.05 * width), _shade(0.74)), "kerb")
    if style == "GRAVEL_PATH":
        edge = min(2.5, 0.04 * width)
        meshes = _rails(walked, False, (-width / 2.0 + edge / 2.0, width / 2.0 - edge / 2.0), edge,
                        min(KERB_CM, 0.05 * width), _shade(0.55))
        points, along = walk_path(walked, 25.0)
        if 0 < len(points) <= MAX_PATH_ELEMENTS:
            index = np.arange(len(points))
            lateral = (((index * 7) % 5) - 2) / 2.0 * 0.4 * width  # the 2D stipple's own offsets
            normal = np.stack([-along[:, 1], along[:, 0]], axis=1)
            centres = points + normal * lateral[:, None]
            size = np.asarray(2.5 + 1.5 * (index % 3) / 2.0, dtype=np.float64)
            shades = (1.0, 0.84, 0.93)
            meshes.append(_pebbles(centres, size, np.asarray([shades[i % 3] for i in index])))
        return _relief(meshes, "gravel")
    return ()


def _pebbles(centres: F64, radius: F64, shade: F64) -> Mesh:
    """Low squashed octahedra (8 triangles each) at ``centres``."""
    count = len(centres)
    if not count:
        return Mesh.empty()
    r = np.broadcast_to(np.asarray(radius, dtype=np.float64), (count,))
    height = 0.45 * r
    ring = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0], [0.0, -1.0]])
    rim = centres[:, None, :] + ring[None, :, :] * r[:, None, None]
    rim3 = np.concatenate([rim, np.broadcast_to((0.2 * height)[:, None, None], (count, 4, 1))], axis=2)
    top = np.concatenate([centres, height[:, None]], axis=1)
    bottom = np.concatenate([centres, np.zeros((count, 1))], axis=1)
    triangles = []
    for k in range(4):
        a, b = rim3[:, k], rim3[:, (k + 1) % 4]
        triangles.append(np.stack([a, b, top], axis=1))
        triangles.append(np.stack([b, a, bottom], axis=1))
    tri = np.stack(triangles, axis=1).reshape(-1, 3, 3)
    colors = np.repeat(np.stack([shade, shade, shade, np.ones(count)], axis=1), 8, axis=0)
    centre = np.repeat(np.concatenate([centres, (0.5 * height)[:, None]], axis=1), 8, axis=0)
    return flat_mesh(tri, colors, outward=tri.mean(axis=1) - centre)


# ── terraces, driveways, decks ───────────────────────────────────────────────


def _outline_vertices(regions: tuple[tuple[Ring, tuple[Ring, ...]], ...]) -> int:
    return sum(len(outer) + sum(len(hole) for hole in holes) for outer, holes in regions)


def _kerbs(record: Record, height: float, width: float, color: Color) -> list[Mesh]:
    """A kerb just inside every ring of the record's ground (left of travel round a
    counter-clockwise outer ring, and round a clockwise hole: inside the region). None
    beyond ``MAX_RELIEF_VERTICES``."""
    if _outline_vertices(record.regions) > MAX_RELIEF_VERTICES:
        return []
    meshes = []
    for outer, holes in record.regions:
        for ring in (outer, *holes):
            points = np.asarray(ring, dtype=np.float64)
            if len(points) < 3:
                continue
            cut = min(0.8, 0.3 * width, 0.3 * height)
            profile = [(0.3 + width, 0.0), (0.3 + width, height - cut), (0.3 + width - cut, height),
                       (0.3 + cut, height), (0.3, height - cut), (0.3, 0.0)]
            meshes.append(sweep(profile, points, color, closed=True))
    return meshes


def _region_edges(outer: Ring, holes: tuple[Ring, ...]) -> F64:
    """Every edge of a region's rings as ``(x1, y1, x2, y2)`` rows."""
    rings = [np.asarray(ring, dtype=np.float64) for ring in (outer, *holes) if len(ring) >= 3]
    return np.concatenate([np.column_stack([ring, np.roll(ring, -1, axis=0)]) for ring in rings]) \
        if rings else np.zeros((0, 4))


def _inside_at(edges: F64, at: float) -> list[tuple[float, float]]:
    """The x intervals of the line ``y = at`` inside the region (even-odd), in order."""
    crossing = (edges[:, 1] > at) != (edges[:, 3] > at)
    if not crossing.any():
        return []
    x1, y1, x2, y2 = edges[crossing].T
    hits = np.sort(x1 + (at - y1) * (x2 - x1) / (y2 - y1))
    return list(zip(hits[0::2].tolist(), hits[1::2].tolist(), strict=False))


def _overlap(first: list[tuple[float, float]], second: list[tuple[float, float]]
             ) -> list[tuple[float, float]]:
    """The intervals in both ordered lists, longer than 1 cm (one merge pass)."""
    out: list[tuple[float, float]] = []
    i = j = 0
    while i < len(first) and j < len(second):
        lo, hi = max(first[i][0], second[j][0]), min(first[i][1], second[j][1])
        if hi - lo > 1.0:
            out.append((lo, hi))
        if first[i][1] < second[j][1]:
            i += 1
        else:
            j += 1
    return out


def _board_runs(edges: F64, y: float, half: float) -> list[tuple[float, float]]:
    """Where a board centred on ``y`` (``half`` its half width) lies inside the region
    whose ``_region_edges`` are ``edges``: the x intervals inside along its centre line
    AND both of its edges."""
    runs = _inside_at(edges, y)
    for edge in (y - half + 0.01, y + half - 0.01):
        runs = _overlap(runs, _inside_at(edges, edge))
    return runs


def _deck(record: Record, top: float, solid: bool) -> list[Mesh] | None:
    """Boards across the outline (along its local x), their top at ``top``. A deck on the
    ground lies on it (its boards were 1.25 cm off it: 3D review of #388); a raised deck's
    boards are at most 3 cm thick, on its skirt. None for a deck that would need more
    than ``MAX_DECK_BOARDS`` boards: the board runs are found BEFORE a mesh is built."""
    if _outline_vertices(record.regions) > MAX_RELIEF_VERTICES:
        return None
    gap = 0.8
    thick = min(3.0, 0.5 * top) if solid else top
    boards: list[tuple[float, float, float, float, int]] = []   # x0, x1, y, width, row
    rows_scanned = 0
    for outer, holes in record.regions:
        xs, ys = [x for x, _y in outer], [y for _x, y in outer]
        if max(xs) - min(xs) < 1.0 or max(ys) - min(ys) < 1.0:
            continue   # narrower than a board run: no row can hold one
        edges = _region_edges(outer, holes)
        board = max(14.0, (max(ys) - min(ys)) / MAX_BOARDS - gap)
        y = min(ys) + board / 2.0 + 0.5
        row = 0
        while y + board / 2.0 <= max(ys) - 0.5:
            rows_scanned += 1
            if rows_scanned > MAX_DECK_ROWS:
                return None
            for x0, x1 in _board_runs(edges, y, board / 2.0):
                boards.append((x0, x1, y, board, row))
                if len(boards) > MAX_DECK_BOARDS:
                    return None
            y += board + gap
            row += 1
    meshes = [beam((x0 + 0.5, y, top - thick / 2.0), (x1 - 0.5, y, top - thick / 2.0), width, thick,
                   _shade(0.95 + 0.05 * (((row * 7) % 5) - 2) / 2.0), across=(0.0, 1.0, 0.0))
              for x0, x1, y, width, row in boards]
    if solid:  # a raised deck: a skirt round it, from the ground to under the boards
        meshes += _kerbs(record, max(top - thick, 0.5), 3.0, _shade(0.78))
    return meshes


def _surface(record: Record) -> tuple[MeshPart, ...]:
    pattern = record.params.get(PARAM_SURFACE_PATTERN)
    deck = isinstance(pattern, str) and pattern in DECK_PATTERNS
    if record.height_cm is not None:  # a raised terrace: a solid, its top the height
        top = record.height_cm
        boarded = _deck(record, top, solid=True) if deck else None
        meshes = boarded if boarded is not None else [prism_mesh(record.footprints, top, record.holes)]
        mesh = Mesh.merge(meshes)
        return (MeshPart(mesh, "vc", tinted=True, name="deck" if boarded is not None else "platform"),) \
            if mesh.vertex_count else ()
    boarded = _deck(record, DECK_TOP_CM, solid=False) if deck else None
    if boarded is not None:
        return _relief(boarded, "deck")
    return _relief(_kerbs(record, KERB_CM, 8.0, _shade(0.72)), "kerb")


# ── ponds ────────────────────────────────────────────────────────────────────


#: A round pond's water and coping are built from this many segments: the record's
#: 24-point ring showed its facets at 3-4 m (3D review of #388).
ROUND_POND_SEGMENTS: Final = 64


def pond_regions(record: Record) -> tuple[tuple[Ring, tuple[Ring, ...]], ...]:
    """The pond's regions — for a round pond (one plain circle) its circle of
    ``ROUND_POND_SEGMENTS`` points instead of the record's coarser ring."""
    radius = record.params.get(PARAM_RADIUS_CM)
    regions = record.regions
    if (record.shape == SHAPE_CIRCLE and isinstance(radius, int | float) and not isinstance(radius, bool)
            and 0.0 < radius < 1e6 and len(regions) == 1 and not regions[0][1]):
        turn = np.linspace(0.0, 2.0 * math.pi, ROUND_POND_SEGMENTS, endpoint=False)
        ring = tuple((float(radius * math.cos(a)), float(radius * math.sin(a))) for a in turn)
        return ((ring, ()),)
    return tuple(regions)


def _water_plan(record: Record) -> F64 | None:
    """The pond's regions (holes cut out) as plan triangles (t, 3, 2), or None."""
    triangles: list[F64] = []
    for outer, holes in pond_regions(record):
        try:
            vertices, faces = cut_region(tuple(outer), tuple(holes))
        except ValueError:
            continue
        points = np.asarray(vertices, dtype=np.float64)
        for face in faces:
            triangles.append(points[list(face)])
    return np.stack(triangles) if triangles else None


def _water(plan: F64, level: float) -> Mesh:
    return flat_mesh(np.concatenate([plan, np.full((len(plan), 3, 1), level)], axis=2),
                     _shade(0.9), outward=(0.0, 0.0, 1.0))


def _raised_pool(record: Record, height: float, plan: F64) -> tuple[MeshPart, ...]:
    """A pond the user gave a HEIGHT: a raised pool — a stone wall just inside its
    outline up to the height (a solid: it casts a shadow, as its 2D caster does) and
    the water a hand under the wall's top."""
    walls = []
    thick = min(18.0, 0.2 * min(np.ptp(np.asarray(record.footprints[0]), axis=0)))
    regions = pond_regions(record)
    # the water's work bound holds per REGION: a pond of many small regions passes it and
    # would sweep walls along all their vertices (security review of #388)
    if _outline_vertices(regions) > MAX_RELIEF_VERTICES:
        return default_builder(record)
    for outer, holes in regions:
        for ring in (outer, *holes):
            points = np.asarray(ring, dtype=np.float64)
            if len(points) < 3:
                continue
            cut = min(1.5, 0.2 * thick, 0.2 * height)
            profile = [(thick, 0.0), (thick, height - cut), (thick - cut, height), (cut, height),
                       (0.0, height - cut), (0.0, 0.0)]
            walls.append(sweep(profile, points, palette.STONE.linear, closed=True))
    water = _water(plan, max(0.5, height - min(6.0, 0.25 * height)))
    return (MeshPart(Mesh.merge(walls), "vc", name="walls"),
            MeshPart(water, "water", casts_shadow=False, tinted=True, name="water"))


def _pond(record: Record) -> tuple[MeshPart, ...]:
    plan = _water_plan(record)
    if plan is None:
        return ()
    if record.height_cm is not None:
        return _raised_pool(record, record.height_cm, plan)
    water = _water(plan, WATER_CM)
    coping = []
    regions = pond_regions(record)   # (the water's own work bound usually refuses first)
    for outer, holes in regions if _outline_vertices(regions) <= MAX_RELIEF_VERTICES else ():
        for ring in (outer, *holes):
            points = np.asarray(ring, dtype=np.float64)
            if len(points) < 3:
                continue
            up = COPING_UP_CM
            profile = [(COPING_IN_CM, 0.0), (COPING_IN_CM, 0.55 * up), (0.75 * COPING_IN_CM, 0.9 * up),
                       (0.3 * COPING_IN_CM, up), (-0.3 * COPING_OUT_CM, up), (-0.8 * COPING_OUT_CM, 0.8 * up),
                       (-COPING_OUT_CM, 0.4 * up), (-COPING_OUT_CM, 0.0)]
            coping.append(sweep(profile, points, palette.STONE.linear, closed=True))
    return (*_relief([water], "water", "water"),
            *_relief(coping, "coping", tinted=False))


# ── lawns ────────────────────────────────────────────────────────────────────


def _inside(points: F64, ring: F64) -> np.ndarray:
    """Even-odd point-in-polygon, vectorised over ``points``."""
    x, y = points[:, 0], points[:, 1]
    hit = np.zeros(len(points), dtype=bool)
    following = np.roll(ring, -1, axis=0)
    for (x1, y1), (x2, y2) in zip(ring, following, strict=True):
        if y1 == y2:
            continue
        crosses = (y1 > y) != (y2 > y)
        at = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        hit ^= crosses & (x < at)
    return hit


def _blades(footprints: tuple[Ring, ...], holes: tuple[tuple[Ring, ...], ...], seed: str,
            wanted: int | None) -> tuple[F64, ...]:
    """The blades of a lawn before any cut-out: roots on a jittered grid inside its
    regions, and each blade's height, heading, lean, width, shade and phase."""
    rings = [np.asarray(ring, dtype=np.float64) for ring in footprints]
    area = sum(abs(signed_area(ring)) for ring in rings)
    area -= sum(abs(signed_area(hole)) for group in holes for hole in group)
    count = int(min(MAX_BLADES, BLADES_PER_M2 * area / 10_000.0))
    if wanted is not None:  # the plan's share (``context``)
        count = min(count, max(0, wanted))
    if count < 1:
        return (np.zeros((0, 2)),) + (np.zeros(0),) * 6
    rng = np.random.Generator(np.random.PCG64(item_seed(seed, "lawn blades")))
    every = np.concatenate(rings)
    low, high = every.min(axis=0), every.max(axis=0)
    width, depth = float(high[0] - low[0]), float(high[1] - low[1])
    edges = len(every) + sum(len(hole) for group in holes for hole in group)
    grid_cap = max(1, min(MAX_SWARD_GRID, MAX_SWARD_WORK // max(edges, 1)))
    step = max(math.sqrt(area / count), math.sqrt(width * depth / grid_cap))
    while math.ceil(width / step) * math.ceil(depth / step) > grid_cap:  # a thin box
        step *= 1.25
    xs = np.arange(low[0] + step / 2.0, high[0], step)
    ys = np.arange(low[1] + step / 2.0, high[1], step)
    grid = np.stack(np.meshgrid(xs, ys), axis=-1).reshape(-1, 2)
    roots = grid + rng.uniform(-0.5, 0.5, grid.shape) * step
    keep = np.zeros(len(roots), dtype=bool)
    for index, ring in enumerate(rings):
        inside = _inside(roots, ring)
        for hole in (holes[index] if holes else ()):
            inside &= ~_inside(roots, np.asarray(hole, dtype=np.float64))
        keep |= inside
    roots = roots[keep]
    n = len(roots)
    return (roots, BLADE_CM * rng.uniform(0.7, 1.3, n), rng.uniform(0.0, 2.0 * math.pi, n),
            rng.uniform(0.1, 0.45, n), rng.uniform(0.8, 1.3, n), rng.uniform(0.92, 1.0, n), rng.random(n))


class _Sward(NamedTuple):
    """A lawn's blades as the engine gets them, before any cut-out: the roots
    ``(n, 2)`` and, per blade, its five vertices' positions, normals, colours and
    uvs (``(n, 5, 3|3|4|2)``, float32)."""

    roots: F64
    positions: NDArray[np.float32]
    normals: NDArray[np.float32]
    colors: NDArray[np.float32]
    uvs: NDArray[np.float32]

    @property
    def nbytes(self) -> int:
        return sum(int(array.nbytes) for array in self)


#: A blade's two triangles at its foot and one at its tip, over its five vertices.
_BLADE_CORNERS: Final = np.array([0, 1, 3, 0, 3, 2, 2, 3, 4])
_BLADE_FRACTIONS: Final = np.array([0.0, 0.0, 0.45, 0.45, 1.0])


def _grow(roots: F64, height: F64, heading: F64, lean: F64, width: F64, shade: F64,
          phase: F64) -> _Sward:
    """Every blade's vertices (``_Sward``)."""
    k = len(roots)
    direction = np.stack([np.cos(heading), np.sin(heading), np.zeros(k)], axis=1)
    side = np.stack([-np.sin(heading), np.cos(heading), np.zeros(k)], axis=1)
    base = np.concatenate([roots, np.full((k, 1), 0.3)], axis=1)
    rows = []
    for fraction, narrowing in ((0.0, 1.0), (0.45, 0.75), (1.0, 0.0)):
        centre = (base + direction * (lean * height * fraction * fraction)[:, None]
                  + np.array([0.0, 0.0, 1.0]) * (height * fraction)[:, None])
        half = (width * narrowing * 0.5)[:, None]
        rows.append((centre - side * half, centre + side * half))
    positions = np.stack([rows[0][0], rows[0][1], rows[1][0], rows[1][1], rows[2][0]], axis=1)
    normal = direction * 0.4 + np.array([0.0, 0.0, 1.0])
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    normals = np.repeat(normal[:, None, :], 5, axis=1)
    # near the lawn's own value, a little darker at the foot: at 0.62 + 0.38·f with a
    # shade of 0.82-1 the blades read as dark stubble on the painted lawn (142.5 luma
    # against 182.7, 3D review of #388)
    weight = (0.92 + 0.08 * _BLADE_FRACTIONS)[None, :] * shade[:, None]
    colors = np.stack([weight, weight, weight, np.ones_like(weight)], axis=-1)
    uvs = np.stack([np.broadcast_to(_BLADE_FRACTIONS, (k, 5)), np.repeat(phase[:, None], 5, axis=1)],
                   axis=-1)
    return _Sward(roots, *(np.ascontiguousarray(array, dtype=np.float32)
                           for array in (positions, normals, colors, uvs)))


#: The lawns' swards are remembered, keyed by the lawn's own geometry, seed and blade
#: share, so a path or terrace dragged across a lawn only re-masks its blades: on
#: bench_large a move rebuilt every blade in 28 ms (median of 15), measured
#: 2026-10-26 (#388). At most this many bytes; the least recently used goes first.
SWARD_CACHE_BYTES: Final = 64 * 1024 * 1024
_SWARDS: OrderedDict[tuple[object, ...], _Sward] = OrderedDict()
_SWARD_STATS: dict[str, int] = {"hits": 0, "misses": 0}


def _sward(footprints: tuple[Ring, ...], holes: tuple[tuple[Ring, ...], ...], seed: str,
           wanted: int | None) -> _Sward:
    """The lawn's blades before any cut-out, remembered (``SWARD_CACHE_BYTES``)."""
    key = (footprints, holes, seed, wanted)
    held = _SWARDS.get(key)
    if held is not None:
        _SWARDS.move_to_end(key)
        _SWARD_STATS["hits"] += 1
        return held
    _SWARD_STATS["misses"] += 1
    grown = _grow(*_blades(footprints, holes, seed, wanted))
    _SWARDS[key] = grown
    total = sum(sward.nbytes for sward in _SWARDS.values())
    while total > SWARD_CACHE_BYTES and len(_SWARDS) > 1:
        _key, dropped = _SWARDS.popitem(last=False)
        total -= dropped.nbytes
    return grown


def sward_cache_info() -> dict[str, int]:
    """How the sward memory has done: hits, misses, entries and bytes held."""
    return {**_SWARD_STATS, "entries": len(_SWARDS),
            "bytes": sum(sward.nbytes for sward in _SWARDS.values())}


def _cutouts(record: Record) -> list[F64]:
    value = record.params.get(PARAM_LAWN_CUTOUTS)
    if not isinstance(value, tuple):
        return []
    rings = []
    for ring in value:
        if isinstance(ring, tuple) and len(ring) >= 3:
            rings.append(np.asarray(ring, dtype=np.float64))
    return rings


def _lawn(record: Record) -> tuple[MeshPart, ...]:
    if record.height_cm is not None:  # a lawn the user gave a height: the plain prism, as before L4
        return default_builder(record)
    seed = str(record.params.get(PARAM_SEED, ""))
    wanted = record.params.get(PARAM_LAWN_BLADES)
    share = wanted if isinstance(wanted, int) and not isinstance(wanted, bool) else None
    sward = _sward(record.footprints, record.holes, seed, share)
    roots = sward.roots
    if not len(roots):
        return ()
    keep = np.ones(len(roots), dtype=bool)
    for ring in _cutouts(record):
        low, high = ring.min(axis=0) - BLADE_CM, ring.max(axis=0) + BLADE_CM
        near = keep & (roots[:, 0] >= low[0]) & (roots[:, 0] <= high[0]) \
            & (roots[:, 1] >= low[1]) & (roots[:, 1] <= high[1])
        if near.any():
            index = np.flatnonzero(near)
            keep[index[_inside(roots[index], ring)]] = False
    k = int(keep.sum())
    if not k:
        return ()
    arrays = sward[1:] if k == len(roots) else tuple(array[keep] for array in sward[1:])
    positions, normals, colors, uvs = arrays
    indices = (_BLADE_CORNERS[None, :] + (np.arange(k) * 5)[:, None]).reshape(-1)
    mesh = Mesh.from_arrays(positions, normals, colors, uvs, indices)
    return (MeshPart(mesh, "grass", casts_shadow=False, tinted=True, name=LAWN_BLADES,
                     ground_detail=True),)


def clear_lawn_cache() -> None:
    """Forget every lawn's blades (a plan was closed, the 3D view closed)."""
    _SWARDS.clear()
    _SWARD_STATS.update(hits=0, misses=0)


BUILDERS: Final = {
    "PATH": _path,
    "TERRACE_PATIO": _surface,
    "DRIVEWAY": _surface,
    "POND_POOL": _pond,
    "LAWN": _lawn,
}


def register(registry: BuilderRegistry) -> None:
    for kind, builder in BUILDERS.items():
        registry.register(kind, builder)


__all__ = ["BUILDERS", "DECK_PATTERNS", "KINDS", "LAWN_BLADES", "clear_lawn_cache", "pond_regions", "register",
           "sward_cache_info",
           "walk_path"]
