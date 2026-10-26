"""Buildings: HOUSE, GARAGE_SHED, TOOL_SHED (Phase 17 L1.6; roofs and facades L4.1).

Three parts each: ``walls`` (kind ``vc``, ``tinted`` — a building's walls take
the item's own fill colour, as the shipped 3D view always extruded it),
``roof`` (kind ``roof`` — its own material in the engine, ``ogp-lush-cinematic``
§4), the tiles in the colour of the 2D roof, and ``facade`` (L4.1: windows and a
door, ``facade``).

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

from ...roof_style import (
    FLAT,
    GABLE,
    HIP,
    MAX_OVERHANG_CM,
    MAX_PITCH_DEG,
    MIN_PITCH_DEG,
    ROOF_STYLES,
    SHED,
)
from ..build import BuilderRegistry
from ..mesh import MeshPart
from ..record import (
    PARAM_DOOR_WALL,
    PARAM_RIDGE,
    PARAM_ROOF_OVERHANG,
    PARAM_ROOF_PITCH,
    PARAM_ROOF_STYLE,
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

#: A pitched roof's lowest edge — the underside at its overhang's outline — stays at
#: least this share of the walls' eave floor above the ground. The overhang continues
#: down the slope past the walls, and at the panel's own extremes (pitch 60°, overhang
#: 150 cm) a 60 x 100 cm tool shed's eaves went 91.5 cm into the ground (senior review
#: of #388). The OVERHANG is shortened to the longest that keeps the edge up — the
#: style and the pitch the user chose are kept.
EDGE_FLOOR_SHARE: Final = 0.5
#: Halvings of the overhang's search (150 cm to within 0.15 cm).
OVERHANG_STEPS: Final = 10

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


def _number(value: ParamValue | None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value)


def chosen_style(record: Record) -> str | None:
    """The roof style the record asks for, or None for automatic."""
    value = record.params.get(PARAM_ROOF_STYLE)
    return value if isinstance(value, str) and value in ROOF_STYLES else None


def style_for(record: Record, base: RoofStyle) -> RoofStyle:
    """``base`` with the record's own pitch and overhang, clamped (``core/roof_style``)."""
    pitch = _number(record.params.get(PARAM_ROOF_PITCH))
    overhang = _number(record.params.get(PARAM_ROOF_OVERHANG))
    style = base
    if pitch is not None and pitch > 0.0:
        style = dataclasses.replace(style, pitch_deg=min(MAX_PITCH_DEG, max(MIN_PITCH_DEG, pitch)))
    if overhang is not None:
        style = dataclasses.replace(style, overhang_cm=min(MAX_OVERHANG_CM, max(0.0, overhang)))
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
    """The ``chosen`` pitched roof with the longest overhang (up to the style's) whose
    lowest edge stays ``EDGE_FLOOR_SHARE`` of the eave floor above the ground. A hip
    whose eaves the overhang would sink is built with a shorter overhang, not turned
    into a gable; None only when no overhang gives this style a roof."""
    floor = EDGE_FLOOR_SHARE * eave_floor(style, height_cm)

    def up(built: GableRoof | None) -> bool:
        return built is not None and float(built.roof.positions[:, 2].min()) >= floor - 1e-6

    built = _pitched(record, chosen, height_cm, style)
    if up(built) or style.overhang_cm <= 0.0:
        return built
    best = _pitched(record, chosen, height_cm, dataclasses.replace(style, overhang_cm=0.0))
    if best is None:
        return built   # this style builds no roof here at all: the caller falls back
    low, high = 0.0, style.overhang_cm
    for _step in range(OVERHANG_STEPS):
        middle = (low + high) / 2.0
        trial = _pitched(record, chosen, height_cm, dataclasses.replace(style, overhang_cm=middle))
        if up(trial):
            best, low = trial, middle
        else:
            high = middle
    return best


def _block(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A building without a roof to show: ALL of its regions, holes cut out, up to
    its height (``common.plain_block``)."""
    return plain_block(record, height_cm, name="walls")


def _building(record: Record, height_cm: float, base: RoofStyle) -> tuple[MeshPart, ...]:
    if not has_one_plain_ring(record):  # checked here too: never a roof on footprints[0]
        return _block(record, height_cm)
    built = _roof(record, height_cm, base)
    if built is None or built.wall_top is None:
        return _block(record, height_cm)
    front = facade(record.kind, footprint_of(record), built.wall_top, door_wall_of(record))
    return (MeshPart(built.walls, "vc", tinted=True, name="walls"),
            MeshPart(built.roof, "roof", name="roof"),
            MeshPart(front, "vc", name="facade"))


def _house(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    return _building(record, height_cm, HOUSE_ROOF)


def _shed(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    return _building(record, height_cm, SHED_ROOF)


build_house: Final = BuiltBuilder(_house, "house")
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
