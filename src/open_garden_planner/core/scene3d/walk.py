"""Walking through the garden — the walker, its world, its motion (Phase 17 L1.8, ADR-065).

Qt-free: standard library and numpy, plain immutable data and pure functions. The
UI layer (``ui/view3d/walk_mode.py``) keeps ONE ``WalkState``, feeds it time and
key state through ``advance``, and hands ``eye_scene`` / ``look_target_scene`` to
the engine. Nothing in here knows a window, a scene or a clock.

THE WALKER is a vertical cylinder of radius ``WALKER_RADIUS_CM`` (shoulders 45 cm:
a 20 cm gap blocks it, a 60 cm garden gate lets it through) standing on the flat
ground at height 0. Its eye is at one of ``EYE_HEIGHTS_CM``. It moves at
``WALK_SPEED_CM_S`` (``RUN_FACTOR`` times that when running), horizontally: where
it LOOKS never changes its pace or lifts it off the ground.

THE WORLD (``build_world``) is made from the same records the 3D view shows:

- A record is SOLID when its kind is one of ``WALK_SOLID_KINDS`` — the built world
  (walls, fences, houses, sheds, beds, containers, hedges) and the greenhouse — and
  the top of the solid the view shows for it is more than ``STEP_HEIGHT_CM`` above
  the walker's ground (``solid_height_cm``: the plan's height, else the kind's
  nominal one, exactly as the builders decide). Everything else is ground: flat
  items, low edgings, furniture — and every PLANT that is not a hedge. Walking
  through a tree is the stated v0 limit, not an oversight.
- A solid blocks over its FOOTPRINT — outer rings minus holes, so the courtyard
  inside a closed wall is free ground for whoever can get in — and over whatever
  its SHOWN mesh adds to that between the step height and ``HEADROOM_CM``. That
  second half is not decoration: the plan holds no thickness for a line, so a wall
  drawn with a 5 cm stroke is built 30 cm thick, and a walker stopped by the
  stroke alone would stand inside the masonry and look through it. The mesh comes
  from the caller (``parts_of`` — the registry's own builder), so what blocks is
  what is drawn. A builder that raises leaves the footprint.
- The plan rectangle is the world's edge: the walker's circle never leaves it.

MOTION. ``advance(state, command, dt, world)`` moves in TICKS of ``TICK_S`` — not
in frames — so the path does not depend on the frame rate: two runs that get the
same commands over the same times take the same ticks. One tick moves the
walker by at most ``WALK_SPEED_CM_S * RUN_FACTOR * TICK_S`` = 2.3 cm, a tenth of its radius: it cannot
step over the thinnest wall. Each tick is "move, then be pushed out of what the
circle entered, along the normal" — which IS sliding: the part of the step along
a wall is kept whole. A corner pushes from two sides in turn; if a position is
still not free after ``MAX_PUSHES`` the tick is refused and the walker stays where
it was (a valid place), so a narrow gap stops it and never traps it.

The time that does not fill a tick is kept in ``carry_s``; what a view shows is
``state.shown`` — the position one resolved partial step ahead — so a view that
refreshes faster than the walker ticks does not judder. ``shown`` is a free
position like every other. When the command's velocity changes, the carried time
is settled with the velocity it was accumulated under.

No head bob and no smoothing of any kind: reduced motion has nothing to switch off.

NOT here: stairs and slopes (the ground is flat at 0), plants as obstacles,
doors. The shipped Qt 3D walkthrough's helper (``core/walk_camera.py``) went
with it (L1.10); this module shares no code with it on purpose.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypeAlias

import numpy as np
from numpy.typing import NDArray

from .builders import BUILT_WORLD_KINDS
from .builders.common import nominal_height_cm
from .frame import cos_sin, pose_points
from .mesh import MeshPart
from .record import Point, Record

_log = logging.getLogger(__name__)

#: Half the shoulder width (45 cm).
WALKER_RADIUS_CM: Final = 22.5
#: Eye heights offered: an adult, a smaller adult, a child.
EYE_HEIGHTS_CM: Final = (165.0, 150.0, 110.0)
WALK_SPEED_CM_S: Final = 140.0
#: Shift: this many times the walking speed.
RUN_FACTOR: Final = 2.0
#: A solid whose top is at most this far above the walker's ground is stepped over.
STEP_HEIGHT_CM: Final = 25.0
#: What a shown solid holds above this height does not block (eaves, a pergola's
#: beams): one number for every eye height — a child is not let under what stops
#: an adult.
HEADROOM_CM: Final = 200.0
#: The walker advances in ticks of this length, whatever the frame rate.
TICK_S: Final = 1.0 / 120.0
#: One call advances by at most this much time: a stalled frame does not teleport.
MAX_ADVANCE_S: Final = 0.25
#: The view tilts at most this far up or down.
PITCH_LIMIT_DEG: Final = 80.0
#: The walk camera's vertical field of view, and its near plane — the engine's
#: (``Garden.qml``, ``clipNear``; pinned against it by a test).
WALK_FOV_DEG: Final = 60.0
NEAR_PLANE_CM: Final = 5.0
#: How far ahead of the eye the point lies that the camera is aimed at.
LOOK_DISTANCE_CM: Final = 100.0
#: The kinds that can block: the built world, and the greenhouse (a plain prism
#: until Package L4 gives it a builder of its own).
WALK_SOLID_KINDS: Final[frozenset[str]] = BUILT_WORLD_KINDS | {"GREENHOUSE"}
#: A tick tries this many pushes before it is refused.
MAX_PUSHES: Final = 8
#: The grid that finds the segments near the walker: cells at least this wide (and
#: never more than ``_MAX_CELLS_PER_SIDE`` of them along a side, however large the plan).
_CELL_CM: Final = 64.0
_MAX_CELLS_PER_SIDE: Final = 1024
#: Two outline points closer than this are one (mesh edges are de-duplicated on it).
_SNAP_CM: Final = 1e-3
#: A circle "touches" from this far inside its radius on: below it is float noise.
_CONTACT_CM: Final = 1e-9
#: ``nearest_free`` looks at no more candidate spots than this.
_MAX_START_TRIES: Final = 20_000

PartsOf: TypeAlias = Callable[[Record], Sequence[MeshPart]]
_F64: TypeAlias = NDArray[np.float64]
_I32: TypeAlias = NDArray[np.int32]


def near_plane_reach_cm(aspect: float, fov_deg: float = WALK_FOV_DEG) -> float:
    """How far from the eye the farthest corner of the near plane lies, for a view
    ``aspect`` times as wide as high. Below ``WALKER_RADIUS_CM`` the camera cannot
    cut into a solid the walker touches."""
    half_height = NEAR_PLANE_CM * math.tan(math.radians(fov_deg) / 2.0)
    return math.sqrt(NEAR_PLANE_CM ** 2 + half_height ** 2 * (1.0 + aspect * aspect))


# ── what is solid ────────────────────────────────────────────────────────────


def solid_height_cm(record: Record) -> float | None:
    """The height of the solid the 3D view SHOWS for ``record`` — None when it shows
    none, or when the kind never blocks. The plan's height; for a built-world kind
    without one, the kind's nominal height (``builders.common.nominal_height_cm`` —
    the builders' own rule: an item the plan gives no height is still drawn)."""
    if record.kind not in WALK_SOLID_KINDS:
        return None
    if record.height_cm is not None:
        return record.height_cm
    return nominal_height_cm(record.kind) if record.kind in BUILT_WORLD_KINDS else None


def is_solid(record: Record) -> bool:
    """True when the walker cannot pass over ``record`` (module docstring)."""
    height = solid_height_cm(record)
    return height is not None and record.transform.base_cm + height > STEP_HEIGHT_CM


# ── the world ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False)
class _Region:
    """One posed footprint region — outer ring and holes as one edge list — for the
    even-odd inside test. ``rise`` is ``y2 - y1`` with 1 where an edge is level."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float
    x1: _F64
    y1: _F64
    x2: _F64
    y2: _F64
    rise: _F64


@dataclass(frozen=True, slots=True, eq=False)
class WalkWorld:
    """Where a walker can and cannot be: plain read-only data (module docstring).

    ``segments``: every obstacle outline segment, ``(n, 4)`` rows of ``x1, y1, x2,
    y2`` in the SCENE frame (cm) — the posed footprint rings of the solids and the
    plan-view edges of their shown meshes. ``solid_ids``: the records that block,
    in paint order. The rest is the index ``advance`` reads.
    """

    width_cm: float
    depth_cm: float
    segments: _F64
    solid_ids: tuple[str, ...]
    regions: tuple[_Region, ...]
    cell_cm: float
    columns: int
    rows: int
    _ax: _F64
    _ay: _F64
    _dx: _F64
    _dy: _F64
    _inverse_length2: _F64
    _starts: _I32
    _items: _I32

    @property
    def has_ground(self) -> bool:
        """False for a plan too small to hold the walker's circle at all."""
        return (self.width_cm >= 2.0 * WALKER_RADIUS_CM
                and self.depth_cm >= 2.0 * WALKER_RADIUS_CM)


def _frozen(array: NDArray[np.generic]) -> None:
    array.setflags(write=False)


def _ring_segments(ring: _F64) -> _F64:
    return np.hstack([ring, np.roll(ring, -1, axis=0)])


def _posed_ring(record: Record, ring: Sequence[Point]) -> _F64:
    c, s = cos_sin(record.transform.rotation_deg)
    local = np.asarray(ring, dtype=np.float64).reshape(-1, 2)
    posed = np.empty_like(local)
    posed[:, 0] = record.transform.east_cm + c * local[:, 0] - s * local[:, 1]
    posed[:, 1] = record.transform.north_cm + s * local[:, 0] + c * local[:, 1]
    return posed


def _region(rings: Sequence[_F64]) -> _Region:
    edges = np.concatenate([_ring_segments(ring) for ring in rings])
    rise = edges[:, 3] - edges[:, 1]
    region = _Region(
        float(edges[:, (0, 2)].min()), float(edges[:, (1, 3)].min()),
        float(edges[:, (0, 2)].max()), float(edges[:, (1, 3)].max()),
        edges[:, 0].copy(), edges[:, 1].copy(), edges[:, 2].copy(), edges[:, 3].copy(),
        np.where(rise != 0.0, rise, 1.0))
    for array in (region.x1, region.y1, region.x2, region.y2, region.rise):
        _frozen(array)
    return region


def _mesh_segments(record: Record, parts: Sequence[MeshPart]) -> list[_F64]:
    """The plan-view edges of every triangle of ``parts`` that reaches into the
    walker's height: above the step, below the headroom (heights above the
    WALKER's ground — the mesh is item-local, the record's base lifts it)."""
    low = STEP_HEIGHT_CM - record.transform.base_cm
    high = HEADROOM_CM - record.transform.base_cm
    found: list[_F64] = []
    for part in parts:
        mesh = part.mesh
        if not mesh.triangle_count:
            continue
        triangles = mesh.indices.astype(np.int64)
        heights = mesh.positions[:, 2].astype(np.float64)[triangles]
        keep = (heights.max(axis=1) > low) & (heights.min(axis=1) < high)
        if not keep.any():
            continue
        plan = pose_points(record.transform, mesh.positions)[:, :2]
        a, b, c = (plan[triangles[keep, corner]] for corner in range(3))
        found.append(np.concatenate([np.hstack([a, b]), np.hstack([b, c]), np.hstack([c, a])]))
    return found


def _unique_segments(segments: _F64) -> _F64:
    """``segments`` without the ones that have no length and without repeats (either
    way round), on the ``_SNAP_CM`` grid — a mesh names every inner edge twice."""
    if not len(segments):
        return np.zeros((0, 4))
    snapped = np.round(segments / _SNAP_CM).astype(np.int64)
    flip = (snapped[:, 0] > snapped[:, 2]) | (
        (snapped[:, 0] == snapped[:, 2]) & (snapped[:, 1] > snapped[:, 3]))
    ordered = np.where(flip[:, None], segments[:, (2, 3, 0, 1)], segments)
    keys = np.where(flip[:, None], snapped[:, (2, 3, 0, 1)], snapped)
    has_length = (keys[:, 0] != keys[:, 2]) | (keys[:, 1] != keys[:, 3])
    ordered, keys = ordered[has_length], keys[has_length]
    if not len(keys):
        return np.zeros((0, 4))
    _values, first = np.unique(keys, axis=0, return_index=True)
    return np.ascontiguousarray(ordered[np.sort(first)])


def _pieces(segments: _F64, longest_cm: float) -> _F64:
    """``segments`` cut into pieces no longer than ``longest_cm`` (so that each lies
    in at most two grid cells along an axis)."""
    if not len(segments):
        return segments
    lengths = np.hypot(segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1])
    counts = np.maximum(np.ceil(lengths / longest_cm), 1.0).astype(np.int64)
    if int(counts.max()) == 1:
        return segments
    rows = np.repeat(np.arange(len(segments)), counts)
    first = np.cumsum(counts) - counts
    step = np.arange(len(rows)) - first[rows]
    whole = counts[rows].astype(np.float64)
    start, end = (step / whole)[:, None], ((step + 1) / whole)[:, None]
    a, b = segments[rows, :2], segments[rows, 2:]
    return np.hstack([a + (b - a) * start, a + (b - a) * end])


def _indexed(width_cm: float, depth_cm: float, segments: _F64, regions: Sequence[_Region],
             solid_ids: Sequence[str]) -> WalkWorld:
    cell = max(_CELL_CM, max(width_cm, depth_cm) / _MAX_CELLS_PER_SIDE,
               2.0 * WALKER_RADIUS_CM + 1.0)
    columns = max(1, math.ceil(width_cm / cell))
    rows = max(1, math.ceil(depth_cm / cell))
    pieces = _pieces(segments, cell)
    ax, ay = pieces[:, 0].copy(), pieces[:, 1].copy()
    dx, dy = pieces[:, 2] - pieces[:, 0], pieces[:, 3] - pieces[:, 1]
    length2 = dx * dx + dy * dy
    inverse = 1.0 / np.where(length2 > 0.0, length2, 1.0)
    if len(pieces):
        low_x = np.clip(np.floor(np.minimum(pieces[:, 0], pieces[:, 2]) / cell), 0, columns - 1)
        high_x = np.clip(np.floor(np.maximum(pieces[:, 0], pieces[:, 2]) / cell), 0, columns - 1)
        low_y = np.clip(np.floor(np.minimum(pieces[:, 1], pieces[:, 3]) / cell), 0, rows - 1)
        high_y = np.clip(np.floor(np.maximum(pieces[:, 1], pieces[:, 3]) / cell), 0, rows - 1)
        index = np.arange(len(pieces), dtype=np.int64)
        pairs = np.concatenate([
            np.stack([(row * columns + column).astype(np.int64), index], axis=1)
            for column, row in ((low_x, low_y), (high_x, low_y), (low_x, high_y), (high_x, high_y))])
        pairs = np.unique(pairs, axis=0)  # sorted by cell, then by piece
        items = pairs[:, 1].astype(np.int32)
        starts = np.searchsorted(pairs[:, 0], np.arange(columns * rows + 1)).astype(np.int32)
    else:
        items = np.zeros(0, np.int32)
        starts = np.zeros(columns * rows + 1, np.int32)
    kept = np.ascontiguousarray(segments, dtype=np.float64)
    for array in (kept, ax, ay, dx, dy, inverse, starts, items):
        _frozen(array)
    return WalkWorld(float(width_cm), float(depth_cm), kept, tuple(solid_ids), tuple(regions),
                     cell, columns, rows, ax, ay, dx, dy, inverse, starts, items)


def build_world(records: Mapping[str, Record], width_cm: float, depth_cm: float, *,
                parts_of: PartsOf | None = None) -> WalkWorld:
    """The walker's world for ``records`` (bottom to top, as a snapshot gives them)
    on a plan of ``width_cm`` x ``depth_cm`` (module docstring).

    ``parts_of(record)``: the mesh parts the view shows for a record — hand it the
    registry's builder (``registry.builder_for(record.kind)``), so that what blocks
    is what is drawn. Called for solid records only. None: footprints alone. A
    ``parts_of`` that raises for a record is contained: that record blocks over its
    footprint, and one line goes to the log.
    """
    outlines: list[_F64] = []
    regions: list[_Region] = []
    solid_ids: list[str] = []
    for item_id, record in records.items():
        if not is_solid(record):
            continue
        solid_ids.append(item_id)
        for outer, holes in record.regions:
            rings = [_posed_ring(record, outer), *(_posed_ring(record, hole) for hole in holes)]
            regions.append(_region(rings))
            outlines.extend(_ring_segments(ring) for ring in rings)
        if parts_of is None:
            continue
        try:
            outlines.extend(_mesh_segments(record, parts_of(record)))
        except Exception as error:  # noqa: BLE001 - any builder defect: the footprint still blocks
            _log.warning("walk: no mesh for %s item %r (%s); it blocks over its footprint",
                         record.kind, item_id, type(error).__name__)
    segments = _unique_segments(np.concatenate(outlines)) if outlines else np.zeros((0, 4))
    return _indexed(width_cm, depth_cm, segments, regions, solid_ids)


# ── asking the world ─────────────────────────────────────────────────────────


def _nearest(world: WalkWorld, x: float, y: float) -> tuple[float, float, float] | None:
    """The outline point nearest to (x, y) among the segments within the walker's
    radius of it — ``(qx, qy, distance)`` — or None when there is none that near."""
    cell = world.cell_cm
    column0 = min(max(int((x - WALKER_RADIUS_CM) // cell), 0), world.columns - 1)
    column1 = min(max(int((x + WALKER_RADIUS_CM) // cell), 0), world.columns - 1)
    row0 = min(max(int((y - WALKER_RADIUS_CM) // cell), 0), world.rows - 1)
    row1 = min(max(int((y + WALKER_RADIUS_CM) // cell), 0), world.rows - 1)
    starts, items = world._starts, world._items
    if column0 == column1 and row0 == row1:
        key = row0 * world.columns + column0
        near = items[starts[key]:starts[key + 1]]
    else:
        chunks = []
        for row in range(row0, row1 + 1):
            first = row * world.columns + column0
            last = row * world.columns + column1
            chunks.append(items[starts[first]:starts[last + 1]])  # the cells of a row are adjacent
        near = np.concatenate(chunks)
    if not near.size:
        return None
    ax, ay, dx, dy = world._ax[near], world._ay[near], world._dx[near], world._dy[near]
    along = np.clip(((x - ax) * dx + (y - ay) * dy) * world._inverse_length2[near], 0.0, 1.0)
    qx, qy = ax + along * dx, ay + along * dy
    distance2 = (x - qx) ** 2 + (y - qy) ** 2
    best = int(distance2.argmin())
    distance = math.sqrt(float(distance2[best]))
    if distance >= WALKER_RADIUS_CM - _CONTACT_CM:
        return None
    return float(qx[best]), float(qy[best]), distance


def _inside_a_footprint(world: WalkWorld, x: float, y: float) -> bool:
    for region in world.regions:
        if not (region.min_x <= x <= region.max_x and region.min_y <= y <= region.max_y):
            continue
        crosses = ((region.y1 > y) != (region.y2 > y)) & (
            x < (region.x2 - region.x1) * (y - region.y1) / region.rise + region.x1)
        if int(crosses.sum()) % 2:
            return True
    return False


def _in_bounds(world: WalkWorld, x: float, y: float) -> bool:
    return (WALKER_RADIUS_CM - _CONTACT_CM <= x <= world.width_cm - WALKER_RADIUS_CM + _CONTACT_CM
            and WALKER_RADIUS_CM - _CONTACT_CM <= y
            <= world.depth_cm - WALKER_RADIUS_CM + _CONTACT_CM)


def is_free(world: WalkWorld, x: float, y: float) -> bool:
    """True when the walker's circle centred on (x, y) lies inside the plan and
    touches no solid: not within its radius of any outline, not inside a footprint."""
    return (_in_bounds(world, x, y) and _nearest(world, x, y) is None
            and not _inside_a_footprint(world, x, y))


def _clamped(world: WalkWorld, x: float, y: float) -> Point:
    return (min(max(x, WALKER_RADIUS_CM), world.width_cm - WALKER_RADIUS_CM),
            min(max(y, WALKER_RADIUS_CM), world.depth_cm - WALKER_RADIUS_CM))


def nearest_free(world: WalkWorld, x: float, y: float) -> Point | None:
    """The free spot nearest to (x, y) — (x, y) itself (brought inside the plan) when
    that is free — or None when the plan holds no free ground within reach.

    "Nearest" to within one walker's radius: rings of that spacing are searched
    outwards, and of the free spots on the first ring that has any, each is drawn
    back towards (x, y) as far as it stays free; the closest wins. Deterministic.
    """
    if not world.has_ground or not (math.isfinite(x) and math.isfinite(y)):
        return None
    x, y = _clamped(world, x, y)
    if is_free(world, x, y):
        return (x, y)
    step = WALKER_RADIUS_CM
    limit = math.hypot(world.width_cm, world.depth_cm)
    tried = 0
    radius = step
    while radius <= limit and tried < _MAX_START_TRIES:
        count = max(8, int(2.0 * math.pi * radius / step))
        best: tuple[float, Point] | None = None
        for index in range(count):
            angle = 2.0 * math.pi * index / count
            spot = (x + radius * math.sin(angle), y + radius * math.cos(angle))
            if not _in_bounds(world, *spot):
                continue
            tried += 1
            if not is_free(world, *spot):
                continue
            near, far = 0.0, 1.0  # fractions of the way from (x, y): not free … free
            for _ in range(12):
                middle = (near + far) / 2.0
                if is_free(world, x + (spot[0] - x) * middle, y + (spot[1] - y) * middle):
                    far = middle
                else:
                    near = middle
            drawn = (x + (spot[0] - x) * far, y + (spot[1] - y) * far)
            reach = radius * far
            if best is None or reach < best[0]:
                best = (reach, drawn)
        if best is not None:
            return best[1]
        radius += step
    return None


# ── the walker ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WalkCommand:
    """What the walker is asked to do: ``forward`` (+1 ahead, −1 back) along its
    heading, ``strafe`` (+1 right, −1 left) across it, and whether it runs. A
    diagonal is not faster than a straight step."""

    forward: float = 0.0
    strafe: float = 0.0
    run: bool = False


@dataclass(frozen=True, slots=True)
class WalkState:
    """Where the walker is and where it looks — plain data.

    ``east`` / ``north``: its ground position at the last whole tick. ``yaw_deg``:
    the compass bearing it faces (0 = north, 90 = east); ``pitch_deg``: how far it
    looks up (+) or down (−). ``carry_s``: time not yet ticked. ``shown``: where a
    view puts it — one resolved partial step ahead (module docstring). ``drift``:
    the velocity the carried time was accumulated under.
    """

    east: float
    north: float
    yaw_deg: float
    pitch_deg: float = 0.0
    carry_s: float = 0.0
    shown: Point = (0.0, 0.0)
    drift: Point = (0.0, 0.0)


def start_state(world: WalkWorld, at: Point, yaw_deg: float) -> WalkState | None:
    """A walker at ``at`` — or at the nearest free spot when ``at`` is inside a solid
    or beyond the plan — facing ``yaw_deg``, looking level. None when the plan has
    no free ground to stand on."""
    spot = nearest_free(world, at[0], at[1])
    if spot is None:
        return None
    return WalkState(spot[0], spot[1], yaw_deg % 360.0, 0.0, 0.0, spot)


def turned(state: WalkState, yaw_delta_deg: float, pitch_delta_deg: float) -> WalkState:
    """The same walker looking elsewhere: yaw is free (kept within one turn), pitch
    stays inside ``±PITCH_LIMIT_DEG``. The position does not change."""
    pitch = min(max(state.pitch_deg + pitch_delta_deg, -PITCH_LIMIT_DEG), PITCH_LIMIT_DEG)
    return WalkState(state.east, state.north, (state.yaw_deg + yaw_delta_deg) % 360.0, pitch,
                     state.carry_s, state.shown, state.drift)


def eye_scene(state: WalkState, eye_height_cm: float) -> tuple[float, float, float]:
    """Where the camera is: above the SHOWN position, scene frame (E, N, up)."""
    return (state.shown[0], state.shown[1], eye_height_cm)


def look_target_scene(state: WalkState, eye_height_cm: float) -> tuple[float, float, float]:
    """The point the camera is aimed at: ``LOOK_DISTANCE_CM`` ahead of the eye."""
    c, s = cos_sin(state.yaw_deg)
    level = math.cos(math.radians(state.pitch_deg)) * LOOK_DISTANCE_CM
    return (state.shown[0] + s * level, state.shown[1] + c * level,
            eye_height_cm + math.sin(math.radians(state.pitch_deg)) * LOOK_DISTANCE_CM)


def _velocity(yaw_deg: float, command: WalkCommand) -> Point:
    forward, strafe = command.forward, command.strafe
    size = math.hypot(forward, strafe)
    if not size > 1e-9:  # also a NaN
        return (0.0, 0.0)
    speed = WALK_SPEED_CM_S * (RUN_FACTOR if command.run else 1.0) / size
    c, s = cos_sin(yaw_deg)
    # ahead = (sin, cos) of the bearing; to the right of it = (cos, −sin)
    return ((forward * s + strafe * c) * speed, (forward * c - strafe * s) * speed)


def _step(world: WalkWorld, x: float, y: float, dx: float, dy: float) -> Point:
    """One move from the free spot (x, y) by (dx, dy), resolved: the new free spot,
    or (x, y) when none is found in ``MAX_PUSHES``."""
    nx, ny = _clamped(world, x + dx, y + dy)
    for _ in range(MAX_PUSHES):
        hit = _nearest(world, nx, ny)
        if hit is None:
            return (nx, ny)
        qx, qy, distance = hit
        if distance > 1e-9:
            ux, uy = (nx - qx) / distance, (ny - qy) / distance
        else:  # exactly on an outline: back towards where it came from
            back = math.hypot(x - qx, y - qy)
            if back <= 1e-9:
                return (x, y)
            ux, uy = (x - qx) / back, (y - qy) / back
        nx, ny = _clamped(world, qx + ux * WALKER_RADIUS_CM, qy + uy * WALKER_RADIUS_CM)
    return (nx, ny) if _nearest(world, nx, ny) is None else (x, y)


def advance(state: WalkState, command: WalkCommand, dt_s: float, world: WalkWorld) -> WalkState:
    """``state`` after ``dt_s`` seconds of ``command`` in ``world`` (module docstring).

    A time that is not a positive number moves nothing; more than ``MAX_ADVANCE_S``
    counts as that. Pure and deterministic: the same arguments give the same state.
    """
    if not dt_s > 0.0 or not math.isfinite(dt_s):
        return state
    velocity = _velocity(state.yaw_deg, command)
    x, y, carry = state.east, state.north, state.carry_s
    if velocity != state.drift:
        # the carried time belongs to the old velocity: where it led is where we are
        x, y = state.shown
        carry = 0.0
    if velocity == (0.0, 0.0):
        if (x, y, carry) == (state.east, state.north, state.carry_s) and state.drift == velocity:
            return state
        return WalkState(x, y, state.yaw_deg, state.pitch_deg, 0.0, (x, y), velocity)
    total = carry + min(dt_s, MAX_ADVANCE_S)
    ticks = int(total / TICK_S + 1e-9)  # the same count whichever way the time was sliced
    step_x, step_y = velocity[0] * TICK_S, velocity[1] * TICK_S
    for _ in range(ticks):
        x, y = _step(world, x, y, step_x, step_y)
    carry = max(total - ticks * TICK_S, 0.0)
    shown = _step(world, x, y, velocity[0] * carry, velocity[1] * carry) if carry > 0.0 else (x, y)
    return WalkState(x, y, state.yaw_deg, state.pitch_deg, carry, shown, velocity)
