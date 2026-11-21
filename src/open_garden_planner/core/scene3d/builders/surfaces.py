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
  edges (the 2D painter's rim); DIRT_PATH and a plain line — nothing: they are
  flat. All in the line's own colour (``tinted``), the 2D painter's shading
  as weights. Gravel and earth are their TEXTURES, painted by the ground bake
  (L4 manual pass: the pebbles once scattered on a gravel path read as little
  tents on a lawn, not as gravel).
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
  A lawn whose fill pattern is WILDFLOWER (``params["surface_pattern"]``, written
  for that pattern only) is a flower MEADOW (#940): taller, looser blades, and on
  one in ``MEADOW_FLOWER_EVERY`` a flower head (``MEADOW_FLOWERS``) — a second,
  untinted part under the same name, so the same presets show it.

Relief stays inside the footprint plus 10 cm (issue #388's truth gate) and low —
the tallest is a deck's boards, 6 cm — except a meadow's: grass up to
``MEADOW_TOP_CM``. Relief is illustrative: the plan gives a surface no height, so
it casts no shadow and no height gate measures it.
"""

from __future__ import annotations

import functools
import math
import threading
from collections import OrderedDict
from typing import Final, NamedTuple

import numpy as np
from numpy.typing import NDArray

from ...plant_art import FLOWERS
from ...shadow_geometry import _offset_line, polyline_round_outline
from ..build import (
    BuilderRegistry,
    default_builder,
    item_seed,
    raised_surface,
    uv_origin_of,
)
from ..color import srgb_to_linear
from ..mesh import Mesh, MeshPart
from ..polygon import cut_region
from ..record import (
    PARAM_LAWN_CUTOUTS,
    PARAM_PATH_STYLE,
    PARAM_RADIUS_CM,
    PARAM_SEED,
    PARAM_SURFACE_PATTERN,
    PATTERN_TILE_CM,
    SHAPE_CIRCLE,
    SHAPE_POLYGON,
    Record,
    Ring,
    lawn_blade_share,
)
from . import palette
from .common import centre_line, surfaced
from .kit import MIN_DETAIL_DIMENSION_CM, beam
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
#: A formal pond/pool's coping: how far it reaches over the water, out over the bank, and up (cm).
COPING_IN_CM: Final = 13.0
COPING_OUT_CM: Final = 7.0
COPING_UP_CM: Final = 7.0
#: #961: a natural pond's low sloped bank (organic multi-vertex polygons): wider, lower
#: earth-and-stone shore than a formal pool's stone kerb, staying inside the 10 cm margin.
BANK_IN_CM: Final = 14.0
BANK_OUT_CM: Final = 7.0
BANK_UP_CM: Final = 3.5
#: #961: linear tint multiplier on a natural pond's water (earthy olive-green, darker than a formal pool's 0.9).
NATURAL_POND_WATER_WEIGHT: Final[tuple[float, float, float, float]] = (0.46, 0.58, 0.28, 1.0)
#: Subdivisions per convex corner when filleting a natural pond's outline (#961).
NATURAL_POND_CORNER_STEPS: Final = 4
#: Maximum inward corner cut (cm) so the ``BANK_OUT_CM`` sloped bank completely covers the
#: original 2D polygon corner underneath (no cobalt triangle peeking out, #961).
NATURAL_POND_MAX_CUT_CM: Final = BANK_OUT_CM - 1.5
#: A gravel path's edging: at most this wide (cm) and this share of the path's width,
#: in the line's colour times this — the rim the 2D painter draws
#: (``ui/canvas/items/path_style_paint.py`` holds the same three, a test both).
GRAVEL_EDGE_CM: Final = 2.5
GRAVEL_EDGE_SHARE: Final = 0.04
GRAVEL_EDGE_SHADE: Final = 0.55
#: A visible rim needs finer curves than a lawn cut-out (whose default is 0.5 cm).
GRAVEL_ARC_TOLERANCE_CM: Final = 0.01

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
#: The most stones or planks one path gets: a path kilometres long gets
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
#: nothing in 2.8 s (senior review of #388). Beyond it: a kerb or the solid.
MAX_DECK_ROWS: Final = 1_000
#: The most outline vertices a surface's relief is swept along (a kerb, a raised deck's
#: skirt, a pond's coping: 12-16 triangles a vertex): beyond it the surface keeps its
#: painted ground and no relief — a raised deck is its plain solid (senior review of
#: #388: a kerb of 768,000 triangles for an outline of 64,000 vertices).
MAX_RELIEF_VERTICES: Final = 4_096
#: A blade's height (cm), before its ±30 % variation.
BLADE_CM: Final = 7.0

#: #940: the fill pattern that makes a LAWN a flower meadow.
MEADOW_PATTERN: Final = "WILDFLOWER"
#: A meadow blade's height (cm) before its variation: x 0.65-1.3 a blade, and x 0.78-1.22
#: by the patch it grows in (``MEADOW_PATCH``) — 12 to 38 cm, a June hay meadow before the
#: first cut. A flower's stem stands x 1.15-1.55 of it, x 0.9-1.1 by its patch.
MEADOW_BLADE_CM: Final = 24.0
MEADOW_PATCH: Final = 0.22
#: A meadow blade's shading weight at its foot (its tip is 1), and how much darker a
#: patch of tall grass is (and lighter a short one): the sward's depth and mottle.
MEADOW_FOOT: Final = 0.68
MEADOW_PATCH_SHADE: Final = 0.1
#: The waves (cm) the meadow's patches of taller and shorter grass are summed from.
MEADOW_PATCH_WAVES_CM: Final = (170.0, 260.0, 410.0)
#: How far a meadow blade's tip leans out from its root, at most (cm): with a flower
#: head's radius the relief stays inside the footprint plus 10 cm (#388's gate).
MEADOW_REACH_CM: Final = 7.0
STEM_REACH_CM: Final = 3.0
#: One blade in this many is a flower's stem on average: 220 / 6 = 37 heads a square
#: metre at the full density. Where the flowers are rich (a field like the grass's
#: patches, ``MEADOW_RICHNESS_WAVES_CM``) up to 1 + ``MEADOW_RICHNESS`` times that.
MEADOW_FLOWER_EVERY: Final = 6
MEADOW_RICHNESS: Final = 0.85
MEADOW_RICHNESS_WAVES_CM: Final = (230.0, 370.0, 590.0)
#: A meadow's flowers: (``plant_art.recipes.FLOWERS`` key — the 2D sprites' petal and
#: centre colours, share, head radius in cm) — a Central European hay meadow in June:
#: ox-eye daisy, buttercup, knapweed and scabious, cranesbill, a few poppies; the radii
#: are the upper half of the real flowers' (a head under 2 px at 25 m reads as nothing).
MEADOW_FLOWERS: Final = (
    ("white", 0.34, (2.0, 2.8)),
    ("yellow", 0.30, (1.1, 1.5)),
    ("lilac", 0.16, (1.5, 2.1)),
    ("blue", 0.12, (1.4, 2.0)),
    ("red", 0.08, (2.6, 3.4)),
)
#: Each kind of flower grows in DRIFTS: its share is weighted by exp(``MEADOW_DRIFT`` x a
#: field of its own, ``MEADOW_DRIFT_WAVES_CM``), so a meadow seen from 25 m shows patches
#: of white, yellow and violet, where flowers spread evenly averaged into one tint.
MEADOW_DRIFT: Final = 2.0
MEADOW_DRIFT_WAVES_CM: Final = (180.0, 290.0, 460.0)
#: The highest a meadow's relief reaches (cm): the tallest stem and, over it, its head
#: (tilted, its rim can stand higher than the stem's tip) — 44 cm.
MEADOW_TOP_CM: Final = MEADOW_BLADE_CM * 1.55 * 1.1 + max(radius[1] for _key, _share, radius in MEADOW_FLOWERS)
#: How far a head is tilted off level, at most (the tangent: 0.6 is 31 degrees).
HEAD_TILT: Final = 0.6
#: A head is a flat polygon of ``HEAD_PETALS`` corners round its stem's tip, in its petal
#: colour, and an eye 0.15 cm over it (a triangle, ``HEAD_EYE`` of its radius) in its
#: centre colour. Every vertex of a head has ONE normal and each triangle one colour: a
#: head far off is a sliver under a pixel, and a varying the multisampled pixel
#: extrapolated across a centre-to-rim gradient came out negative or zero — pixels of
#: pure red, blue or black at the meadow's far edge.
HEAD_PETALS: Final = 5
HEAD_EYE: Final = 0.38
HEAD_TRIANGLES: Final = HEAD_PETALS - 2 + 1
HEAD_VERTICES: Final = HEAD_PETALS + 3

Color = tuple[float, float, float, float]


def _shade(weight: float) -> Color:
    """A tinted part's vertex colour: a shading weight the sink multiplies with the
    item's tint (``palette.TINT`` is weight 1)."""
    return (weight, weight, weight, 1.0)


#: What a tinted relief part is made of (#803), by its name; an untinted one (a pond's
#: coping) takes its palette entries' surfaces.
RELIEF_SURFACES: Final = {"stones": "stone", "boardwalk": "wood", "kerb": "concrete",
                          "gravel": "stone", "deck": "wood"}


def _relief(meshes: list[Mesh], name: str, kind: str = "vc", *, tinted: bool = True) -> tuple[MeshPart, ...]:
    mesh = Mesh.merge(meshes)
    if not mesh.vertex_count:
        return ()
    surface = RELIEF_SURFACES.get(name, "") if tinted and kind == "vc" else ""
    return (MeshPart(mesh, kind, casts_shadow=False, tinted=tinted, name=name, ground_detail=True,
                     surface=surface),)


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


# _offset_line imported from shadow_geometry


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


def _gravel_rim(line: F64, width: float, edge: float, height: float) -> list[Mesh]:
    """Bevelled edging along the ROUND stroke's boundary, including its end caps.

    A rail on each offset centreline cuts a chord across the gravel at an outer
    bend. Use the same round outline as the lawn cut-out, then sweep inward.
    The nominal square/butt analytical caster footprint is unchanged.
    """
    if len(line) > MAX_RELIEF_VERTICES:
        return []
    keep = np.ones(len(line), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(line, axis=0), axis=1) > 1e-3
    points = line[keep]
    if len(points) < 2:
        return []
    along = np.diff(points, axis=0)
    along /= np.linalg.norm(along, axis=1, keepdims=True)
    turns = np.abs(np.arctan2(
        along[:-1, 0] * along[1:, 1] - along[:-1, 1] * along[1:, 0],
        (along[:-1] * along[1:]).sum(axis=1),
    ))
    step = 2 * math.acos(1 - GRAVEL_ARC_TOLERANCE_CM / (width / 2))
    # Bound arc work BEFORE the clipper allocates its rounded answer. Beyond
    # the relief budget the accurate painted path remains, without 3D edging.
    if 4 * len(points) + math.ceil((math.tau + float(turns.sum())) / step) > MAX_RELIEF_VERTICES:
        return []
    rings = polyline_round_outline(
        [(float(x), float(y)) for x, y in points], width,
        arc_tolerance_cm=GRAVEL_ARC_TOLERANCE_CM,
    )
    if sum(len(ring) for ring in rings) > MAX_RELIEF_VERTICES:
        return []
    cut = min(0.6, 0.15 * edge, 0.3 * height)
    profile = [(0.0, 0.0), (edge, 0.0), (edge, height - cut), (edge - cut, height),
               (cut, height), (0.0, height - cut)]
    return [sweep(profile, np.asarray(ring, dtype=np.float64), _shade(GRAVEL_EDGE_SHADE), closed=True)
            for ring in rings]


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


@surfaced
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
        # the 2D rim's width and place (``path_style_paint.GRAVEL_EDGE_*``)
        edge = min(GRAVEL_EDGE_CM, GRAVEL_EDGE_SHARE * width)
        return _relief(_gravel_rim(walked, width, edge, min(KERB_CM, 0.05 * width)), "gravel")
    return ()


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


@surfaced
def _surface(record: Record) -> tuple[MeshPart, ...]:
    pattern = record.params.get(PARAM_SURFACE_PATTERN)
    deck = isinstance(pattern, str) and pattern in DECK_PATTERNS
    if record.height_cm is not None:  # a raised terrace: a solid, its top the height
        top = record.height_cm
        boarded = _deck(record, top, solid=True) if deck else None
        if boarded is not None:
            mesh = Mesh.merge(boarded)
            return (MeshPart(mesh, "vc", tinted=True, name="deck", surface="wood"),) \
                if mesh.vertex_count else ()
        # not a deck: the platform shows the item's own fill - a raised driveway or
        # terrace keeps the texture the ground bake painted while it lay flat (#628),
        # on its TOP; its sides are the item's tint (no smear down the edge)
        return raised_surface(record, top, name="platform")
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


def is_natural_pond(record: Record) -> bool:
    """True when a ``POND_POOL`` is an organic multi-vertex ground pond rather than a
    formal rectangular, circular or raised pool (#961)."""
    return (record.height_cm is None
            and record.shape == SHAPE_POLYGON
            and bool(record.footprints)
            and all(len(ring) >= 5 for ring in record.footprints))


def _smooth_pond_ring(points: F64, steps: int = NATURAL_POND_CORNER_STEPS) -> F64:
    """Round each convex corner of a natural pond polygon with a quadratic Bézier fillet
    whose inward displacement stays within ``NATURAL_POND_MAX_CUT_CM`` (#961).

    Cutting only convex corners keeps the smoothed ring strictly inside the original
    footprint (never cutting across a concave reflex corner outside the plan), while
    clamping the inward cut below ``BANK_OUT_CM`` ensures the sloped bank completely
    covers the painted 2D polygon corner underneath with no blue triangles peeking out."""
    n = len(points)
    if n < 3 or steps < 1:
        return points
    ccw = signed_area(points) >= 0.0
    prev = np.roll(points, 1, axis=0)
    nxt = np.roll(points, -1, axis=0)
    e_in = points - prev
    e_out = nxt - points
    len_in = np.linalg.norm(e_in, axis=1)
    len_out = np.linalg.norm(e_out, axis=1)
    u_in = e_in / np.maximum(len_in, 1e-12)[:, None]
    u_out = e_out / np.maximum(len_out, 1e-12)[:, None]
    turn = u_in[:, 0] * u_out[:, 1] - u_in[:, 1] * u_out[:, 0]
    convex = turn > 1e-4 if ccw else turn < -1e-4
    # Exterior turn angle theta in (0, pi); midpoint inward cut of quadratic Bezier is
    # 0.5 * d * sin(theta / 2) = 0.5 * d * sqrt((1 - dot(u_in, u_out)) / 2).
    dots = np.clip((u_in * u_out).sum(axis=1), -1.0, 1.0)
    sin_half = np.sqrt(np.maximum(0.5 * (1.0 - dots), 0.0))
    ts = np.linspace(0.0, 1.0, steps + 1)
    out: list[F64] = []
    for i in range(n):
        if not convex[i] or len_in[i] < 1.0 or len_out[i] < 1.0 or sin_half[i] < 1e-3:
            out.append(points[i])
            continue
        max_d = min(0.42 * float(len_in[i]), 0.42 * float(len_out[i]),
                    2.0 * NATURAL_POND_MAX_CUT_CM / float(sin_half[i]))
        a = points[i] - max_d * u_in[i]
        b = points[i] + max_d * u_out[i]
        for t in ts:
            s = 1.0 - t
            out.append(s * s * a + 2.0 * s * t * points[i] + t * t * b)
    return np.asarray(out, dtype=np.float64)


def _natural_pond_regions(record: Record) -> tuple[tuple[Ring, tuple[Ring, ...]], ...]:
    """The regions of a natural pond smoothed within ``MAX_RELIEF_VERTICES``."""
    regions = pond_regions(record)
    total = _outline_vertices(regions)
    steps = 0
    for candidate in range(NATURAL_POND_CORNER_STEPS, 0, -1):
        if total * (candidate + 1) <= MAX_RELIEF_VERTICES:
            steps = candidate
            break
    if steps == 0:
        return regions

    def smooth(ring: Ring) -> Ring:
        pts = _smooth_pond_ring(np.asarray(ring, dtype=np.float64), steps)
        return tuple((float(x), float(y)) for x, y in pts)

    validated: list[tuple[Ring, tuple[Ring, ...]]] = []
    for outer, holes in regions:
        smoothed = (smooth(outer), tuple(smooth(h) for h in holes))
        try:
            cut_region(smoothed[0], smoothed[1])
        except ValueError:
            # #961: a pinched concave outline whose fillet crosses a reflex corner or hole
            # falls back to its original valid ring rather than silently dropping the pond.
            validated.append((outer, holes))
        else:
            validated.append(smoothed)
    return tuple(validated)


def _water_plan(regions: tuple[tuple[Ring, tuple[Ring, ...]], ...]) -> F64 | None:
    """The pond's regions (holes cut out) as plan triangles (t, 3, 2), or None."""
    triangles: list[F64] = []
    for outer, holes in regions:
        try:
            vertices, faces = cut_region(tuple(outer), tuple(holes))
        except ValueError:
            continue
        points = np.asarray(vertices, dtype=np.float64)
        for face in faces:
            triangles.append(points[list(face)])
    return np.stack(triangles) if triangles else None


def _water(plan: F64, level: float, uv_origin: tuple[float, float] = (0.0, 0.0),
           color: Color | None = None) -> Mesh:
    """The water surface at ``level``, with the plan's UVs (a raised pool shows its
    own water picture: one texel per vertex would sample a single texel, #627)."""
    triangles = np.concatenate([plan, np.full((len(plan), 3, 1), level)], axis=2)
    normalised = np.asarray(uv_origin, dtype=np.float64)
    uvs = (triangles[:, :, :2] + normalised) / PATTERN_TILE_CM
    return flat_mesh(triangles, _shade(0.9) if color is None else color,
                     outward=(0.0, 0.0, 1.0), vertex_uvs=uvs)


def _raised_pool(record: Record, height: float, plan: F64) -> tuple[MeshPart, ...]:
    """A pond the user gave a HEIGHT: a raised pool — a stone wall just inside its
    outline up to the height (a solid: it casts a shadow, as its 2D caster does) and
    the water a hand under the wall's top.

    The water shows the item's own FILL picture (``fill_texture``): the plan's
    water texture tinted with its colour, which the ``water.frag`` look samples as
    its albedo (and still lights and reflects like water). Without it a raised pond
    was the fill COLOUR alone — a flat blue slab the owner read as "the water
    became unreflective" (#627's manual pass): on the ground the same item keeps its
    picture, and the raised one must too.
    """
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
    water = _water(plan, max(0.5, height - min(6.0, 0.25 * height)), uv_origin_of(record))
    return (MeshPart(Mesh.merge(walls), "vc", name="walls"),
            MeshPart(water, "water", casts_shadow=False, fill_texture=True, name="water"))


@surfaced
def _pond(record: Record) -> tuple[MeshPart, ...]:
    points = np.asarray([point for ring in record.footprints for point in ring], dtype=np.float64)
    if len(points) and ((np.ptp(points, axis=0) < MIN_DETAIL_DIMENSION_CM).any()
                       or (record.height_cm is not None and record.height_cm < MIN_DETAIL_DIMENSION_CM)):
        return default_builder(record)
    natural = is_natural_pond(record)
    regions = _natural_pond_regions(record) if natural else pond_regions(record)
    plan = _water_plan(regions)
    if plan is None:
        return ()
    if record.height_cm is not None:
        return _raised_pool(record, record.height_cm, plan)
    water = _water(plan, WATER_CM, color=NATURAL_POND_WATER_WEIGHT if natural else None)
    coping = []
    # the water's work bound holds per region: this total cap is what bounds the coping
    # of a pond of many regions
    for outer, holes in regions if _outline_vertices(regions) <= MAX_RELIEF_VERTICES else ():
        for ring in (outer, *holes):
            pts = np.asarray(ring, dtype=np.float64)
            if len(pts) < 3:
                continue
            if natural:
                # #961: low sloped natural earth-and-stone bank instead of a grey kerb
                up = BANK_UP_CM
                profile = [
                    (BANK_IN_CM, 0.2),
                    (0.55 * BANK_IN_CM, WATER_CM + 0.4),
                    (0.15 * BANK_IN_CM, 0.85 * up),
                    (-0.25 * BANK_OUT_CM, up),
                    (-0.7 * BANK_OUT_CM, 0.45 * up),
                    (-BANK_OUT_CM, 0.0),
                ]
                colors = [
                    palette.SOIL.linear,
                    palette.STONE_DARK.linear,
                    palette.STONE_DARK.linear,
                    palette.SOIL.linear,
                    palette.SOIL.linear,
                ]
                coping.append(sweep(profile, pts, colors, closed=True, profile_closed=False))
            else:
                up = COPING_UP_CM
                profile = [(COPING_IN_CM, 0.0), (COPING_IN_CM, 0.55 * up), (0.75 * COPING_IN_CM, 0.9 * up),
                           (0.3 * COPING_IN_CM, up), (-0.3 * COPING_OUT_CM, up), (-0.8 * COPING_OUT_CM, 0.8 * up),
                           (-COPING_OUT_CM, 0.4 * up), (-COPING_OUT_CM, 0.0)]
                coping.append(sweep(profile, pts, palette.STONE.linear, closed=True))
    return (*_relief([water], "water", "water"),
            *_relief(coping, "coping", tinted=False))


# ── lawns ────────────────────────────────────────────────────────────────────


def _inside(points: F64, ring: F64) -> np.ndarray:
    """Exact even-odd mask in y-sorted batches, with bounded temporary arrays.

    A batch considers only edges crossing its y range. A 6,000-edge ring no
    longer visits every root once per edge; at most 65,536 pairs live at once.
    Horizontal edges and the strict endpoint convention match ray casting.
    """
    hit = np.zeros(len(points), dtype=bool)
    if not len(points) or len(ring) < 3:
        return hit
    following = np.roll(ring, -1, axis=0)
    vertical = following[:, 1] != ring[:, 1]
    start, end = ring[vertical], following[vertical]
    if len(start) <= 16:
        x, y = points[:, 0], points[:, 1]
        for first, last in zip(start, end, strict=True):
            crosses = (first[1] > y) != (last[1] > y)
            at = first[0] + (y - first[1]) * (last[0] - first[0]) / (last[1] - first[1])
            hit ^= crosses & (x < at)
        return hit
    low, high = np.minimum(start[:, 1], end[:, 1]), np.maximum(start[:, 1], end[:, 1])
    order = np.argsort(points[:, 1], kind="stable")
    batch_size = max(1, min(256, math.ceil(len(points) / 128)))
    for begin in range(0, len(points), batch_size):
        index = order[begin:begin + batch_size]
        x, y = points[index, 0, None], points[index, 1, None]
        near = (low <= float(y.max())) & (high > float(y.min()))
        a, b = start[near], end[near]
        edge_batch = max(1, 65536 // len(index))
        inside = np.zeros(len(index), dtype=bool)
        for edge in range(0, len(a), edge_batch):
            first, last = a[edge:edge + edge_batch], b[edge:edge + edge_batch]
            crosses = (first[:, 1] > y) != (last[:, 1] > y)
            at = first[:, 0] + (y - first[:, 1]) * (last[:, 0] - first[:, 0]) / (last[:, 1] - first[:, 1])
            inside ^= np.logical_xor.reduce(crosses & (x < at), axis=1)
        hit[index] = inside
    return hit


def _blades(footprints: tuple[Ring, ...], holes: tuple[tuple[Ring, ...], ...], seed: str,
            wanted: int | None) -> tuple[F64, ...]:
    """The blades of a lawn before any cut-out: roots on a jittered grid inside its
    regions, and each blade's height, heading, lean, width, shade and phase."""
    roots, rng = _rooted(footprints, holes, seed, wanted)
    if rng is None:
        return (np.zeros((0, 2)),) + (np.zeros(0),) * 6
    n = len(roots)
    return (roots, BLADE_CM * rng.uniform(0.7, 1.3, n), rng.uniform(0.0, 2.0 * math.pi, n),
            rng.uniform(0.1, 0.45, n), rng.uniform(0.8, 1.3, n), rng.uniform(0.92, 1.0, n), rng.random(n))


def _rooted(footprints: tuple[Ring, ...], holes: tuple[tuple[Ring, ...], ...], seed: str,
            wanted: int | None) -> tuple[F64, np.random.Generator | None]:
    """A sward's roots — a jittered grid inside its regions, the lawn's own count or the
    plan's share of it — and the generator each blade's own draws continue from (None:
    no blade)."""
    rings = [np.asarray(ring, dtype=np.float64) for ring in footprints]
    area = sum(abs(signed_area(ring)) for ring in rings)
    area -= sum(abs(signed_area(hole)) for group in holes for hole in group)
    count = int(min(MAX_BLADES, BLADES_PER_M2 * area / 10_000.0))
    if wanted is not None:  # the plan's share (``context``)
        count = min(count, max(0, wanted))
    if count < 1:
        return np.zeros((0, 2)), None
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
    return roots[keep], rng


class _Heads(NamedTuple):
    """A meadow's flower heads: the blade each one tops ``(m,)``, and its
    ``HEAD_VERTICES`` vertices' positions, normals, colours and uvs (float32)."""

    stem: NDArray[np.intp]
    positions: NDArray[np.float32]
    normals: NDArray[np.float32]
    colors: NDArray[np.float32]
    uvs: NDArray[np.float32]

    @property
    def nbytes(self) -> int:
        return sum(int(array.nbytes) for array in self)


class _Sward(NamedTuple):
    """A lawn's blades as the engine gets them, before any cut-out: the roots
    ``(n, 2)`` and, per blade, its five vertices' positions, normals, colours and
    uvs (``(n, 5, 3|3|4|2)``, float32); a meadow's flower heads too (``_Heads``)."""

    roots: F64
    positions: NDArray[np.float32]
    normals: NDArray[np.float32]
    colors: NDArray[np.float32]
    uvs: NDArray[np.float32]
    heads: _Heads | None = None

    @property
    def nbytes(self) -> int:
        arrays = (self.roots, self.positions, self.normals, self.colors, self.uvs)
        return (sum(int(array.nbytes) for array in arrays)
                + (self.heads.nbytes if self.heads is not None else 0))


#: A blade's two triangles at its foot and one at its tip, over its five vertices.
_BLADE_CORNERS: Final = np.array([0, 1, 3, 0, 3, 2, 2, 3, 4])
_BLADE_FRACTIONS: Final = np.array([0.0, 0.0, 0.45, 0.45, 1.0])
#: A head's polygon — a fan from its first corner — and its eye (the last three vertices).
_HEAD_CORNERS: Final = np.array([*((0, k, k + 1) for k in range(1, HEAD_PETALS - 1)),
                                 tuple(range(HEAD_PETALS, HEAD_VERTICES))]).reshape(-1)


def _blade_shapes(roots: F64, height: F64, heading: F64, lean: F64, width: F64) -> tuple[F64, F64]:
    """Every blade's five vertices and their one normal, ``((k, 5, 3), (k, 5, 3))``."""
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
    return positions, np.repeat(normal[:, None, :], 5, axis=1)


def _f32(*arrays: NDArray[np.floating]) -> tuple[NDArray[np.float32], ...]:
    return tuple(np.ascontiguousarray(array, dtype=np.float32) for array in arrays)


def _grow(roots: F64, height: F64, heading: F64, lean: F64, width: F64, shade: F64,
          phase: F64) -> _Sward:
    """Every blade's vertices (``_Sward``)."""
    k = len(roots)
    positions, normals = _blade_shapes(roots, height, heading, lean, width)
    # near the lawn's own value, a little darker at the foot: at 0.62 + 0.38·f with a
    # shade of 0.82-1 the blades read as dark stubble on the painted lawn (142.5 luma
    # against 182.7, 3D review of #388)
    weight = (0.92 + 0.08 * _BLADE_FRACTIONS)[None, :] * shade[:, None]
    colors = np.stack([weight, weight, weight, np.ones_like(weight)], axis=-1)
    uvs = np.stack([np.broadcast_to(_BLADE_FRACTIONS, (k, 5)), np.repeat(phase[:, None], 5, axis=1)],
                   axis=-1)
    blade_positions, blade_normals, blade_colors, blade_uvs = _f32(positions, normals, colors, uvs)
    return _Sward(roots, blade_positions, blade_normals, blade_colors, blade_uvs)


def _patches(points: F64, rng: np.random.Generator, waves_cm: tuple[float, ...] = MEADOW_PATCH_WAVES_CM) -> F64:
    """A smooth field over ``points`` in −1..1: plane waves of ``waves_cm``, each its own
    heading and phase, summed to unit variance and clipped at ±1 — a standard deviation
    of 0.73, a third of the points on a plateau at ±1 (measured). The meadow's patches of
    taller and shorter grass, where its flowers are rich, a kind of flower's drifts."""
    heading = rng.uniform(0.0, 2.0 * math.pi, len(waves_cm))
    phase = rng.uniform(0.0, 2.0 * math.pi, len(waves_cm))
    waves = np.stack([np.cos(heading), np.sin(heading)], axis=1) * (2.0 * math.pi / np.asarray(waves_cm))[:, None]
    field = np.sin(points @ waves.T + phase).sum(axis=1)
    return np.asarray(field / math.sqrt(len(waves_cm) / 2.0), dtype=np.float64).clip(-1.0, 1.0)


@functools.cache
def flower_colours() -> tuple[F64, F64]:
    """Each ``MEADOW_FLOWERS`` entry's petal and centre colour as the 2D sprites paint
    them (``FLOWERS``: petal, petal tip, centre), linear RGB ``(k, 3)``."""
    petals = np.asarray([srgb_to_linear(FLOWERS[key][0]) for key, _share, _radius in MEADOW_FLOWERS],
                        dtype=np.float64)
    centres = np.asarray([srgb_to_linear(FLOWERS[key][2]) for key, _share, _radius in MEADOW_FLOWERS],
                         dtype=np.float64)
    return petals, centres


def _meadow(roots: F64, rng: np.random.Generator) -> _Sward:
    """A meadow's blades and flower heads (``_Sward`` with ``heads``) on the roots of
    ``_rooted``, every draw from ``rng``."""
    n = len(roots)
    rich = 1.0 + MEADOW_RICHNESS * _patches(roots, rng, MEADOW_RICHNESS_WAVES_CM)
    stem = rng.random(n) * MEADOW_FLOWER_EVERY < rich
    patch = _patches(roots, rng)
    grass_cm = MEADOW_BLADE_CM * rng.uniform(0.65, 1.3, n) * (1.0 + MEADOW_PATCH * patch)
    stem_cm = MEADOW_BLADE_CM * rng.uniform(1.15, 1.55, n) * (1.0 + 0.1 * patch)
    height = np.where(stem, stem_cm, grass_cm)
    heading = rng.uniform(0.0, 2.0 * math.pi, n)
    reach = np.where(stem, np.minimum(rng.uniform(0.0, 0.1, n) * height, STEM_REACH_CM),
                     np.minimum(rng.uniform(0.1, 0.4, n) * height, MEADOW_REACH_CM))
    width = np.where(stem, rng.uniform(0.35, 0.5, n), rng.uniform(0.9, 1.5, n))
    shade = np.where(stem, rng.uniform(0.78, 0.88, n), rng.uniform(0.82, 1.04, n))
    dry = np.where(~stem & (rng.random(n) < 0.3), rng.uniform(0.3, 1.0, n), 0.0)
    phase = rng.random(n)
    positions, normals = _blade_shapes(roots, height, heading, reach / height, width)
    # a deep sward is darker at its foot, and darker where it grows tall (the patches: a
    # mottle seen from 25 m, where a lawn of the same colour is flat); some blades' tips
    # are drying (seed heads, straw): warmer, by the square of the height fraction
    shade = shade * (1.0 - MEADOW_PATCH_SHADE * patch)
    weight = (MEADOW_FOOT + (1.0 - MEADOW_FOOT) * _BLADE_FRACTIONS)[None, :] * shade[:, None]
    warm = dry[:, None] * _BLADE_FRACTIONS[None, :] ** 2
    colors = np.stack([weight * (1.0 + 0.8 * warm), weight * (1.0 + 0.05 * warm),
                       weight * (1.0 - 0.4 * warm), np.ones_like(weight)], axis=-1)
    # the wind's weight grows with the blade: w = uv.x² at its tip is √(h / BLADE_CM), so
    # a 24 cm blade sways 1.85 times a lawn blade's ``windStrength`` (grass.vert)
    sway = (height / BLADE_CM) ** 0.25
    uvs = np.stack([_BLADE_FRACTIONS[None, :] * sway[:, None], np.repeat(phase[:, None], 5, axis=1)],
                   axis=-1)
    vertices, shading, colours, weights = _f32(positions, normals, colors, uvs)
    return _Sward(roots, vertices, shading, colours, weights,
                  heads=_heads(np.flatnonzero(stem), roots, positions[:, 4], sway, phase, rng))


def _heads(stem: NDArray[np.intp], roots: F64, tips: F64, sway: F64, phase: F64,
           rng: np.random.Generator) -> _Heads:
    """A flower head on the tip of every stem: a tilted polygon in its petal colour and
    an eye in its centre colour (``HEAD_PETALS``); its kind drawn from
    ``MEADOW_FLOWERS``' shares, each weighted by its drifts at the stem's root."""
    m = len(stem)
    shares = np.asarray([share for _key, share, _radius in MEADOW_FLOWERS])
    at = roots[stem]
    weight = shares[None, :] * np.exp(MEADOW_DRIFT * np.stack(
        [_patches(at, rng, MEADOW_DRIFT_WAVES_CM) for _flower in MEADOW_FLOWERS], axis=1))
    reach = np.cumsum(weight, axis=1)
    kind = np.minimum((reach < rng.random(m)[:, None] * reach[:, -1:]).sum(axis=1), len(MEADOW_FLOWERS) - 1)
    low, high = (np.asarray([radius[i] for _key, _share, radius in MEADOW_FLOWERS]) for i in (0, 1))
    radius = low[kind] + (high[kind] - low[kind]) * rng.random(m)
    lean, tilt = rng.uniform(0.0, 2.0 * math.pi, m), rng.uniform(0.0, HEAD_TILT, m)
    spin = rng.uniform(0.0, 2.0 * math.pi, m)
    bright = rng.uniform(0.9, 1.05, m)
    up = np.stack([tilt * np.cos(lean), tilt * np.sin(lean), np.ones(m)], axis=1)
    up /= np.linalg.norm(up, axis=1, keepdims=True)
    across = np.stack([np.cos(spin), np.sin(spin), np.zeros(m)], axis=1)
    across -= up * (across * up).sum(axis=1, keepdims=True)
    across /= np.linalg.norm(across, axis=1, keepdims=True)
    along = np.cross(up, across)
    angle = 2.0 * math.pi * np.arange(HEAD_PETALS) / HEAD_PETALS
    out = (np.cos(angle)[None, :, None] * across[:, None, :]
           + np.sin(angle)[None, :, None] * along[:, None, :])          # (m, petals, 3)
    tip = tips[stem]
    rim = tip[:, None, :] + radius[:, None, None] * out
    # the eye: a triangle a little over the polygon's middle, turned against its corners
    eye_angle = 2.0 * math.pi * (np.arange(3) + 0.25) / 3.0
    eye_out = (np.cos(eye_angle)[None, :, None] * across[:, None, :]
               + np.sin(eye_angle)[None, :, None] * along[:, None, :])
    eye = (tip + up * 0.15)[:, None, :] + (HEAD_EYE * radius)[:, None, None] * eye_out
    positions = np.concatenate([rim, eye], axis=1)
    normals = np.repeat(up[:, None, :], HEAD_VERTICES, axis=1)
    petals, centres = flower_colours()
    colour = np.concatenate([np.repeat(petals[kind][:, None, :], HEAD_PETALS, axis=1),
                             np.repeat(centres[kind][:, None, :], 3, axis=1)], axis=1)
    colour *= bright[:, None, None]
    colors = np.concatenate([colour, np.ones((m, HEAD_VERTICES, 1))], axis=2)
    # every vertex sways with its stem's tip
    uvs = np.repeat(np.stack([sway[stem], phase[stem]], axis=1)[:, None, :], HEAD_VERTICES, axis=1)
    return _Heads(stem, *_f32(positions, normals, colors, uvs))


#: The lawns' swards are remembered, keyed by the lawn's own geometry, seed and blade
#: share, so a path or terrace dragged across a lawn only re-masks its blades: on
#: bench_large a move rebuilt every blade in 28 ms (median of 15), measured
#: 2026-10-26 (#388). At most this many bytes; the least recently used goes first.
SWARD_CACHE_BYTES: Final = 64 * 1024 * 1024
_SWARDS: OrderedDict[tuple[object, ...], _Sward] = OrderedDict()
_SWARD_STATS: dict[str, int] = {"hits": 0, "misses": 0}
#: #452: the geometry lane builds on a worker while the GUI thread may clear this
#: memory (a document change, closing the view). Every read and write of the two
#: dicts above is under this lock.
_SWARD_LOCK = threading.Lock()


def _sward(footprints: tuple[Ring, ...], holes: tuple[tuple[Ring, ...], ...], seed: str,
           wanted: int | None, meadow: bool = False) -> _Sward:
    """The lawn's blades before any cut-out — a meadow's with its flower heads —
    remembered (``SWARD_CACHE_BYTES``)."""
    key = (footprints, holes, seed, wanted, meadow)
    with _SWARD_LOCK:
        held = _SWARDS.get(key)
        if held is not None:
            _SWARDS.move_to_end(key)
            _SWARD_STATS["hits"] += 1
            return held
        _SWARD_STATS["misses"] += 1
    roots, rng = _rooted(footprints, holes, seed, wanted) if meadow else (None, None)
    if roots is not None and rng is not None:   # outside the lock: it is slow
        grown = _meadow(roots, rng)
    else:
        grown = _grow(*_blades(footprints, holes, seed, wanted))
    with _SWARD_LOCK:
        _SWARDS[key] = grown
        total = sum(sward.nbytes for sward in _SWARDS.values())
        while total > SWARD_CACHE_BYTES and len(_SWARDS) > 1:
            _key, dropped = _SWARDS.popitem(last=False)
            total -= dropped.nbytes
    return grown


def sward_cache_info() -> dict[str, int]:
    """How the sward memory has done: hits, misses, entries and bytes held."""
    with _SWARD_LOCK:
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


@surfaced
def _lawn(record: Record) -> tuple[MeshPart, ...]:
    # A lawn the user gave a height is a solid whose TOP keeps the fill (and its
    # sides the turf's tint) — and it still grows its sward: the blades are what
    # made the ground lawn read as grass, and without them the raised one became a
    # flat textured slab (#627's manual pass). The blades ride the new top.
    solid: tuple[MeshPart, ...] = ()
    lift = 0.0
    if record.height_cm is not None:
        solid = raised_surface(record, record.height_cm, name="lawn")
        lift = record.height_cm
    if lawn_blade_share(record.params) == 0:
        return solid  # Low/Medium: do not synthesize or cache even an empty sward
    seed = str(record.params.get(PARAM_SEED, ""))
    sward = _sward(record.footprints, record.holes, seed, lawn_blade_share(record.params),
                   is_meadow(record))
    roots = sward.roots
    if not len(roots):
        return solid
    keep = np.ones(len(roots), dtype=bool)
    for ring in _cutouts(record):
        low, high = ring.min(axis=0) - BLADE_CM, ring.max(axis=0) + BLADE_CM
        near = keep & (roots[:, 0] >= low[0]) & (roots[:, 0] <= high[0]) \
            & (roots[:, 1] >= low[1]) & (roots[:, 1] <= high[1])
        if near.any():
            index = np.flatnonzero(near)
            keep[index[_inside(roots[index], ring)]] = False
    if not keep.any():
        return solid
    blades = _relief_part(_kept((sward.positions, sward.normals, sward.colors, sward.uvs), keep),
                          _BLADE_CORNERS, lift, tinted=True)
    if sward.heads is None:
        return (*solid, blades)
    heads = sward.heads
    # a head goes with its stem; it carries its own colours (``MEADOW_FLOWERS``), so it is
    # not tinted — under the blades' NAME, which the engine shows from High (``Garden.qml``)
    flowers = _relief_part(_kept((heads.positions, heads.normals, heads.colors, heads.uvs), keep[heads.stem]),
                           _HEAD_CORNERS, lift, tinted=False)
    return (*solid, blades, *((flowers,) if flowers.mesh.triangle_count else ()))


def is_meadow(record: Record) -> bool:
    """A LAWN that is a flower meadow (#940): its fill pattern is ``MEADOW_PATTERN``."""
    return record.kind == "LAWN" and bool(record.params.get(PARAM_SURFACE_PATTERN) == MEADOW_PATTERN)


def _kept(arrays: tuple[NDArray[np.float32], ...], keep: NDArray[np.bool_]) -> tuple[NDArray[np.float32], ...]:
    return arrays if keep.all() else tuple(array[keep] for array in arrays)


def _relief_part(arrays: tuple[NDArray[np.float32], ...], corners: NDArray[np.int_], lift: float, *,
                 tinted: bool) -> MeshPart:
    """One ``lawn_blades`` part of ``(k, v, …)`` per-element vertex arrays, each element
    triangulated by ``corners``, risen by ``lift`` (a raised lawn's top)."""
    positions, normals, colors, uvs = arrays
    k, per = positions.shape[:2]
    if lift:
        positions = positions.copy()      # the cache's array is shared: never move it
        positions[:, :, 2] += lift
    indices = (corners[None, :] + (np.arange(k) * per)[:, None]).reshape(-1)
    mesh = Mesh.from_arrays(positions, normals, colors, uvs, indices)
    return MeshPart(mesh, "grass", casts_shadow=False, tinted=tinted, name=LAWN_BLADES, ground_detail=True)


def clear_lawn_cache() -> None:
    """Forget every lawn's blades (a plan was closed, the 3D view closed)."""
    with _SWARD_LOCK:
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


__all__ = ["BUILDERS", "DECK_PATTERNS", "KINDS", "LAWN_BLADES", "MEADOW_PATTERN", "clear_lawn_cache",
           "flower_colours", "is_meadow", "pond_regions", "register", "sward_cache_info", "walk_path"]
