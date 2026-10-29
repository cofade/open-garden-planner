"""Buildings: HOUSE, GARAGE_SHED, TOOL_SHED (Phase 17 L1.6; roofs and facades L4.1).

Three parts each: ``walls`` (kind ``vc``), ``roof`` (kind ``roof`` — its own
material in the engine, ``ogp-lush-cinematic`` §4), the tiles in the colour of
the 2D roof, and ``facade`` (L4.1: windows and a door, ``facade``). A shed's
walls are ``tinted``: they take the item's own fill colour, as the shipped 3D
view always extruded it. A HOUSE's walls are rendered sandstone
(``HOUSE_WALL``): its 2D fill is drawn as roof tiles — the roof seen from above —
and defaults to the roof's terracotta (owner, L4 manual pass), which on the walls
made the house one terracotta block.

**The roof** (L4.1, ``core/roof_style``): the item's ``params["roof_style"]``
picks it — ``gable`` (two planes through a ridge line), ``hip`` (every eave
slopes; a convex footprint only, else a gable), ``shed`` (one plane, rising
toward the item's own +y: an unrotated building's roof falls to the south) or
``flat`` (a concrete slab with a dark edge). Without a style the roof is AUTOMATIC:
a gable along the plan's ridge where there is one, a flat roof on a house
without one. ``params["roof_pitch_deg"]`` / ``["roof_overhang_cm"]`` replace the
style's own pitch and overhang. In EVERY style the roof's top is the building's
height (ADR-037: the height is the ridge's).

- **HOUSE** takes its ridge from ``params["ridge"]`` — the LIVE ridge item's end
  points in the house's own frame (ADR-046: the ridge is recomputed by the
  canvas, this module only consumes it and never derives one). A gable chosen
  for a house without a usable ridge runs along its footprint's long axis
  (``roofs.bounding_box_ridge``).
- **GARAGE_SHED** has no ridge item; its ridge runs along the long axis of the
  footprint's local bounding box. **TOOL_SHED** is drawn as a sprite whose ridge
  runs along the sprite's height — the item's local y — whatever the
  rectangle's proportions, so its 3D ridge does too (a polygon tool shed, which
  shows no sprite, takes the long axis).
- **The plain block is ``common.plain_block``**: ALL of the record's regions
  with their holes cut out — never ``footprints[0]`` alone. A roof needs ONE
  plain outline (``common.has_one_plain_ring``: one ring, no hole, not
  ``params["outline_resolved"]``); a record whose ground is anything else is that
  block (``BuiltBuilder`` sees to it), and so is a building whose roof cannot be
  built (too low for a slab).
"""

from __future__ import annotations

import dataclasses
import math
from typing import Final

import numpy as np

from ...roof_style import (
    FLAT,
    GABLE,
    HIP,
    SHED,
    roof_overhang_cm,
    roof_pitch_deg,
    roof_style,
)
from ..build import BuilderRegistry, cap_mesh
from ..mesh import Mesh, MeshPart
from ..record import (
    PARAM_DOOR_WALL,
    PARAM_RIDGE,
    SHAPE_RECTANGLE,
    ParamValue,
    Record,
)
from . import palette
from .common import BuiltBuilder, corner_count, footprint_of, has_one_plain_ring, plain_block
from .facade import facade
from .roofs import (
    GableRoof,
    RoofStyle,
    bounding_box_ridge,
    eave_floor,
    flat_roof,
    gable_roof,
    hip_roof,
    shed_roof,
)

#: An overhang never takes a pitched roof's lowest edge — the underside at the
#: overhang's outline — below this share of the walls' eave floor. The overhang
#: continues down the slope past the walls: at the panel's own extremes (pitch 60°,
#: overhang 150 cm) a 60 x 100 cm tool shed's eaves went 91.5 cm into the ground. The
#: OVERHANG is shortened; the style and the pitch the user chose are kept. A roof
#: without an overhang ends at its walls and is kept as it is.
EDGE_FLOOR_SHARE: Final = 0.5
#: The overhang's search (``_kept_up``): at most this many roofs beyond the ends of the
#: range. ``scripts/measure_roof_overhang.py`` measures how close to the longest
#: overhang that holds it lands, and how many roofs it builds.
OVERHANG_TRIES: Final = 5
#: … and done once even the larger of its two estimates (within the bracket) says less
#: than this share of the overhang found (or a centimetre) is left to gain.
OVERHANG_GAIN_SHARE: Final = 0.025
#: Where no overhang builds no roof — maybe an exact coincidence: the ridge on an edge of
#: the outline (an L drawn on a grid) — the search tries this much overhang instead.
OVERHANG_NUDGE_CM: Final = 0.5

#: A house's walls (module docstring): the sprites' sandstone, close to the tan the
#: walls took from the former default fill (210, 180, 140), so an untouched house
#: drawn before L4 keeps the walls it had. A house given another fill (white, brick)
#: loses that colour on its 3D walls: the fill is its roof seen from above.
HOUSE_WALL: Final = palette.SANDSTONE

HOUSE_ROOF: Final = RoofStyle(
    tile=palette.ROOF_TILE, cap=palette.ROOF_TILE_CAP, timber=palette.TIMBER,
    overhang_cm=30.0, pitch_deg=38.0,
)
SHED_ROOF: Final = RoofStyle(
    tile=palette.SHINGLE, cap=palette.SHINGLE_CAP, timber=palette.TIMBER,
    overhang_cm=20.0, pitch_deg=25.0,
)
#: A flat roof: a light concrete slab with a dark edge (the sprites' concrete and stone).
FLAT_ROOF: Final = RoofStyle(
    tile=palette.CONCRETE_LIGHT, cap=palette.CONCRETE, timber=palette.STONE_DARK,
    overhang_cm=15.0, pitch_deg=0.0, slab_cm=20.0,
)

Ridge = tuple[tuple[float, float], tuple[float, float]]


def ridge_of(value: ParamValue | None) -> Ridge | None:
    """``params["ridge"]`` as two finite points, or None for anything else."""
    if not isinstance(value, tuple) or len(value) != 2:
        return None
    points: list[tuple[float, float]] = []
    for point in value:
        if not isinstance(point, tuple) or len(point) != 2:
            return None
        x, y = point
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int | float) \
                or not isinstance(y, int | float) or not math.isfinite(x + y):
            return None
        points.append((float(x), float(y)))
    return points[0], points[1]


def chosen_style(record: Record) -> str | None:
    """The roof style the record asks for, or None for automatic."""
    return roof_style(record.params)


def style_for(record: Record, base: RoofStyle) -> RoofStyle:
    """``base`` with the record's own pitch and overhang, clamped (``core/roof_style``)."""
    pitch = roof_pitch_deg(record.params)
    overhang = roof_overhang_cm(record.params)
    style = base
    if pitch is not None:
        style = dataclasses.replace(style, pitch_deg=pitch)
    if overhang is not None:
        style = dataclasses.replace(style, overhang_cm=overhang)
    return style


def door_wall_of(record: Record) -> int | None:
    """``params["door_wall"]`` as an int, or None."""
    value = record.params.get(PARAM_DOOR_WALL)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _ridge(record: Record) -> Ridge | None:
    """The ridge a gable hangs on: a HOUSE's live ridge item; a tool shed's sprite
    ridge (local y); else the long axis of the footprint's box."""
    footprint = footprint_of(record)
    if record.kind == "HOUSE":
        ridge = ridge_of(record.params.get(PARAM_RIDGE))
        if ridge is not None:
            return ridge
    if record.kind == "TOOL_SHED" and record.shape == SHAPE_RECTANGLE:
        ys = [y for _x, y in footprint]
        xs = [x for x, _y in footprint]
        middle = (min(xs) + max(xs)) / 2.0
        return (middle, min(ys)), (middle, max(ys))
    return bounding_box_ridge(footprint)


def _roof(record: Record, height_cm: float, base: RoofStyle) -> GableRoof | None:
    """The roof the record asks for (module docstring), or None when none can be built."""
    footprint = footprint_of(record)
    style = style_for(record, base)
    chosen = chosen_style(record)
    has_ridge = record.kind != "HOUSE" or ridge_of(record.params.get(PARAM_RIDGE)) is not None
    if chosen is None:
        chosen = GABLE if has_ridge else FLAT
    if chosen == FLAT:
        return flat_roof(footprint, height_cm, style_for(record, FLAT_ROOF))
    built = _kept_up(record, chosen, height_cm, style)
    if built is None and chosen == HIP:
        built = _kept_up(record, GABLE, height_cm, style)  # not convex: the gable, along its ridge
    return built


def _pitched(record: Record, chosen: str, height_cm: float, style: RoofStyle) -> GableRoof | None:
    footprint = footprint_of(record)
    if chosen == HIP:
        return hip_roof(footprint, height_cm, style)
    if chosen == SHED:
        return shed_roof(footprint, height_cm, style)
    ridge = _ridge(record)
    return gable_roof(footprint, ridge, height_cm, style) if ridge is not None else None


def _kept_up(record: Record, chosen: str, height_cm: float, style: RoofStyle) -> GableRoof | None:
    """The ``chosen`` pitched roof with nearly the longest overhang (up to the style's)
    whose lowest edge stays ``EDGE_FLOOR_SHARE`` of the eave floor above the ground. A
    hip whose eaves the overhang would sink is built with a shorter overhang, not
    turned into a gable. A building too low for that floor even without an overhang
    keeps its roof without one. None when the style builds no roof at either end of the
    overhang's range (the short one also tried ``OVERHANG_NUDGE_CM`` in)."""
    floor = EDGE_FLOOR_SHARE * eave_floor(style, height_cm)

    def build(overhang_cm: float) -> GableRoof | None:
        return _pitched(record, chosen, height_cm, dataclasses.replace(style, overhang_cm=overhang_cm))

    def above(built: GableRoof) -> float:
        """How far the roof's lowest edge is above the floor."""
        return float(built.roof.positions[:, 2].min()) - floor

    high = style.overhang_cm
    built = build(high)
    if (built is not None and above(built) >= -1e-6) or high <= 0.0:
        return built
    # A builder returns None on an exact coincidence — an offset edge on the ridge line (a
    # U's courtyard at 100 cm), the ridge on an edge of the outline (an L drawn on a grid,
    # at no overhang) — and a hair beside it builds: the short end is tried there too.
    low = 0.0
    best = build(low)
    if best is None and high > 2.0 * OVERHANG_NUDGE_CM:
        low = OVERHANG_NUDGE_CM
        best = build(low)
    if best is None:
        return None   # no roof at the short end: the caller falls back
    at_low = above(best)
    if at_low < -1e-6:
        # Too low for the floor without an overhang — only a gable 18-22 cm tall: it holds
        # its eaves to 0.75 x (top - ridge cap - slab), lower than ``eave_floor``. (The
        # loop would return the same roof — its estimates are negative; said here.)
        return best
    at_high = None if built is None else above(built)
    held: tuple[float, float] | None = None   # the roof that held before ``low``
    sank = False
    for _try in range(OVERHANG_TRIES):
        # Two estimates of how much more overhang still holds. The chord to the roof that
        # sank, and a line from the last roof that held: through the two last that held,
        # or at first at the roof's own ``slope`` — the edge's fall per cm of overhang for
        # a hip and for a gable square to its ridge; a gable with an oblique ridge falls
        # faster at its far corner, a shed's edge twice as fast until its slope clamp and
        # slower after it. Neither is sure to be short of the root: a guess is the nearer
        # of the two, 1 % short (so never on the long end itself, maybe a coincidence),
        # and after a guess sank the next goes at most halfway. Only a roof that holds is
        # kept. The search stops when even the larger estimate (within the bracket) is
        # under a centimetre or ``OVERHANG_GAIN_SHARE`` of the overhang found.
        estimates = [high - low]
        if at_high is not None and at_low - at_high > 1e-6:
            estimates.append((high - low) * at_low / (at_low - at_high))
        slope = (held[1] - at_low) / (low - held[0]) if held is not None and held[1] > at_low else best.slope
        estimates.append(at_low / max(slope, 1e-6))
        if min(high - low, max(estimates[1:])) < max(1.0, OVERHANG_GAIN_SHARE * low):
            break
        gain = 0.99 * min(estimates)
        if sank:
            gain = min(gain, (high - low) / 2.0)
        trial = build(low + gain)
        if trial is not None and above(trial) >= -1e-6:
            held = (low, at_low)
            best, low, at_low, sank = trial, low + gain, above(trial), False
        else:
            high, at_high, sank = low + gain, None if trial is None else above(trial), True
    return best


def _block(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A building without a roof to show: ALL of its regions, holes cut out, up to
    its height (``common.plain_block``)."""
    return plain_block(record, height_cm, name="walls")


def _floor(record: Record) -> Mesh:
    """A neutral interior floor (holzboden / palette.PLANK) inside the footprint at z = 0.5 cm.
    Seen in Cutaway mode when the roof and upper walls are removed (#589)."""
    cap = cap_mesh(record.footprints, 0.5, record.holes)
    if not len(cap.positions):
        return Mesh.empty()
    colors = np.broadcast_to(
        np.asarray(palette.PLANK.linear, dtype=np.float32),
        (len(cap.positions), 4),
    )
    return Mesh.from_arrays(cap.positions, cap.normals, colors, cap.uvs, cap.indices)


def _building(record: Record, height_cm: float, base: RoofStyle) -> tuple[MeshPart, ...]:
    """Walls in the item's fill colour (``tinted``), the roof and the facade — or the
    block, where no roof can be built."""
    if not has_one_plain_ring(record):  # checked here too: never a roof on footprints[0]
        return _block(record, height_cm)
    built = _roof(record, height_cm, base)
    if built is None or built.wall_top is None:
        return _block(record, height_cm)
    front = facade(record.kind, footprint_of(record), built.wall_top, door_wall_of(record))
    floor = _floor(record)
    return (MeshPart(built.walls, "vc", tinted=True, name="walls"),
            MeshPart(built.roof, "roof", name="roof"),
            MeshPart(front, "vc", name="facade"),
            MeshPart(floor, "vc", tinted=False, name="floor"))


def _house(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    return _building(record, height_cm, HOUSE_ROOF)


def _shed(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    return _building(record, height_cm, SHED_ROOF)


def _house_walls(parts: tuple[MeshPart, ...]) -> tuple[MeshPart, ...]:
    """A HOUSE's walls are ``HOUSE_WALL`` on EVERY route — under its roof, the block of
    a house whose roof cannot be built (``_block``) and ``BuiltBuilder``'s plain block of
    a house that is not one plain outline — never the item's fill (module docstring).
    A block's top is the roof seen from above, so it is roof tiles: the 2D plan's look at
    the default fill (3D review of the owner's second pass). Like the real roof, it does
    not follow another fill. Walls under a roof have no top.
    The rule of the kind, applied once to whatever was built: the tinted parts."""
    wall = np.asarray(HOUSE_WALL.linear, dtype=np.float32)
    tile = np.asarray(HOUSE_ROOF.tile.linear, dtype=np.float32)

    def recoloured(mesh: Mesh) -> Mesh:
        colour = np.where(mesh.normals[:, 2:3] > 0.99, tile, wall)
        return Mesh.from_arrays(mesh.positions, mesh.normals, mesh.colors * colour, mesh.uvs,
                                mesh.indices)

    return tuple(dataclasses.replace(part, tinted=False, mesh=recoloured(part.mesh))
                 if part.tinted else part for part in parts)


build_house: Final = BuiltBuilder(_house, "house", recolour=_house_walls)
build_shed: Final = BuiltBuilder(_shed, "shed")


def triangle_budget(record: Record) -> int:
    """The most triangles a building may have: 80 + 30 per corner of its ground for
    the walls and the roof (a hip roof: one face per corner), and the facade's —
    one window per 1.5 m of wall at most, 96 triangles each, two rows, a door."""
    corners = corner_count(record)
    perimeter = sum(
        math.dist(ring[i], ring[(i + 1) % len(ring)]) for ring in record.footprints for i in range(len(ring)))
    windows = 2 * (int(perimeter / 150.0) + corners)
    return 80 + 60 * corners + 96 * windows + 120


def register(registry: BuilderRegistry) -> None:
    registry.register("HOUSE", build_house)
    registry.register_many(("GARAGE_SHED", "TOOL_SHED"), build_shed)
