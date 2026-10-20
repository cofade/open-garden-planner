"""Buildings: HOUSE, GARAGE_SHED, TOOL_SHED (Phase 17 L1.6).

Two parts each: ``walls`` (kind ``vc``, ``tinted`` — a building's walls take
the item's own fill colour, as the shipped 3D view always extruded it) and
``roof`` (kind ``roof`` — its own material in the engine, ``ogp-lush-cinematic``
§4), the tiles in the colour of the 2D roof.

- **HOUSE** takes its ridge from ``params["ridge"]`` — the LIVE ridge item's end
  points in the house's own frame (ADR-046: the ridge is recomputed by the
  canvas, this module only consumes it and never derives one). A HOUSE without a
  usable ridge (a rectangle typed HOUSE, a stale link, a ridge without length,
  a ridge whose line misses the building, a house too low for a roof slab) is a
  plain block up to its height: honest about what the plan holds.
- **The plain block is ``common.plain_block``**: ALL of the record's regions
  with their holes cut out — never ``footprints[0]`` alone. A gable roof needs a
  usable ridge AND one plain outline (``common.has_one_plain_ring``: one ring, no
  hole, not ``params["outline_resolved"]``); a record whose ground is anything
  else is that block too. A HOUSE drawn crossing itself comes without a ridge
  from the snapshot — and gets no roof here even if one is handed in: the flag
  decides, not the missing param.
- **GARAGE_SHED / TOOL_SHED** have no ridge item; theirs runs along the long
  axis of the footprint's local bounding box (``roofs.bounding_box_ridge``).
"""

from __future__ import annotations

import math
from typing import Final

from ..build import BuilderRegistry
from ..mesh import MeshPart
from ..record import PARAM_RIDGE, ParamValue, Record
from . import palette
from .common import BuiltBuilder, corner_count, footprint_of, has_one_plain_ring, plain_block
from .roofs import RoofStyle, bounding_box_ridge, gable_roof

HOUSE_ROOF: Final = RoofStyle(
    tile=palette.ROOF_TILE, cap=palette.ROOF_TILE_CAP, timber=palette.TIMBER,
    overhang_cm=30.0, pitch_deg=38.0,
)
SHED_ROOF: Final = RoofStyle(
    tile=palette.SHINGLE, cap=palette.SHINGLE_CAP, timber=palette.TIMBER,
    overhang_cm=20.0, pitch_deg=25.0,
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


def _block(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A building without a roof to show: ALL of its regions, holes cut out, up to
    its height (``common.plain_block``)."""
    return plain_block(record, height_cm, name="walls")


def _roofed(record: Record, height_cm: float, ridge: Ridge | None,
            style: RoofStyle) -> tuple[MeshPart, ...]:
    """Walls and a gable roof — on ONE plain outline (not a resolved one), and only
    with a ridge whose line the roof can be hung on; in every other case the block
    of the record's regions."""
    if ridge is None or not has_one_plain_ring(record):
        return _block(record, height_cm)
    built = gable_roof(footprint_of(record), ridge, height_cm, style)
    if built is None:
        return _block(record, height_cm)
    return (MeshPart(built.walls, "vc", tinted=True, name="walls"),
            MeshPart(built.roof, "roof", name="roof"))


def _house(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    return _roofed(record, height_cm, ridge_of(record.params.get(PARAM_RIDGE)), HOUSE_ROOF)


def _shed(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    ridge = bounding_box_ridge(footprint_of(record)) if has_one_plain_ring(record) else None
    return _roofed(record, height_cm, ridge, SHED_ROOF)


build_house: Final = BuiltBuilder(_house, "house")
build_shed: Final = BuiltBuilder(_shed, "shed")


def triangle_budget(record: Record) -> int:
    """The most triangles a building may have: 80 + 30 per corner of its ground."""
    return 80 + 30 * corner_count(record)


def register(registry: BuilderRegistry) -> None:
    registry.register("HOUSE", build_house)
    registry.register_many(("GARAGE_SHED", "TOOL_SHED"), build_shed)
