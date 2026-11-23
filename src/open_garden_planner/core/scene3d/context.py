"""What one record needs to know about the others (Phase 17 L4, #388). Qt-free.

A builder reads ONE record (``build``: the seam). Two L4 looks depend on other
items, so the snapshot writes what they need into the record's own params, in
the record's own frame, once every record exists (``with_context``):

- **A building's door** faces the nearest PATH — a garage's the nearest
  DRIVEWAY first: ``params["door_wall"]`` is the index of the building's wall
  that faces the point of that item nearest to the building's centre
  (``builders.facade.door_wall_index``). Only the wall: a house moved along its
  path keeps the param, and so its mesh.
- **A lawn's blades** grow nowhere under a flat item painted ABOVE it — a path,
  a terrace, a bed drawn on the lawn — nor inside an enclosed building on it
  (``ENCLOSED_KINDS``: a greenhouse's floor is seen through its glass):
  ``params["lawn_cutouts"]`` holds the outer outlines of every such record
  (painted on the ground, no height, not a plant, later in paint order; or
  enclosed) whose box meets the lawn's, in the lawn's frame — a pond's grown by its
  coping (``POND_CLEARANCE_CM``), an open gravel or dirt path's the rounded stroke the
  canvas paints (``ROUND_PATH_STYLES``), a stepping-stone path's each painted stone —
  the path itself is not a continuous surface, so grass grows and a rake runs between
  its stones (#998). At most
  ``MAX_CUTOUTS`` outlines and ``MAX_CUTOUT_VERTICES`` vertices, the largest
  first: beyond that, the smallest items let blades through.
- **How many blades a lawn grows** is the PLAN's to say: ``params["lawn_blades"]``
  shares ``MAX_PLAN_BLADES`` among the plan's lawns by area (each lawn its own
  density and ``surfaces.MAX_BLADES`` at most; what a capped or small lawn cannot
  use goes to the others), so a plan of many lawns — or of 2,000 stacked ones —
  grows a bounded meadow. A lawn with a height is a plain solid that grows no blades:
  it takes neither param.

Because these params are GEOMETRY, an edit that changes them rebuilds the house
whose door turns to another wall and the lawn a flat item crosses — and only
those. The ground bake paints neither param (``record.BUILD_ONLY_PARAMS``).
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import replace
from typing import Final

import numpy as np
from numpy.typing import NDArray

from ..shadow_geometry import grown_polygon, polyline_round_outline
from .builders import OBJECT_KINDS, hedges
from .builders.common import centre_line
from .builders.facade import door_wall_index
from .builders.surfaces import (
    BLADES_PER_M2,
    COPING_OUT_CM,
    MOSS_BLADES_PER_M2,
    is_moss,
    is_sand,
    pond_regions,
    walk_path,
)
from .builders.surfaces import MAX_BLADES as MAX_LAWN_BLADES
from .frame import cos_sin, pose_ring
from .polygon import group_rings, ring_area
from .record import (
    PARAM_DOOR_WALL,
    PARAM_HEDGE_LEAVES,
    PARAM_LAWN_BLADES,
    PARAM_LAWN_CUTOUTS,
    PARAM_PATH_STYLE,
    Record,
    Transform,
)

#: The kinds that get a door, and the kinds their door looks for, in order.
DOOR_TARGETS: Final[dict[str, tuple[str, ...]]] = {
    "HOUSE": ("PATH",),
    "TOOL_SHED": ("PATH",),
    "GARAGE_SHED": ("DRIVEWAY", "PATH"),
}
#: Kinds that never cut a lawn: plants stand in it, and a second lawn grows its own.
_NOT_A_CUTOUT: Final = frozenset({"TREE", "SHRUB", "PERENNIAL", "LAWN"})
#: The objects whose build covers their footprint at the ground — a pot, a pit, a box.
#: They cut a lawn whatever their height and their place in the paint order, as an
#: enclosed building does: a cold frame's soil and a fire pit's ash bed lie a few cm up,
#: under a blade's 7 cm. Every other object is built on legs, posts, a pole or ropes and
#: the lawn grows under it; a cut-out left a bald patch there (a pergola 12 m², a
#: parasol 6 m²).
GROUND_COVERING_KINDS: Final = frozenset({
    "COLD_FRAME", "COMPOST_BIN", "FIRE_PIT", "HOT_TUB", "PLANTER_POT", "RAIN_BARREL", "SANDBOX"})
#: Enclosed buildings cut a lawn whatever their place in the paint order: their
#: inside is seen — through a greenhouse's glass, into a house with its roof off
#: (Cutaway) — and no grass grows on a floor.
ENCLOSED_KINDS: Final = frozenset({"HOUSE", "GARAGE_SHED", "TOOL_SHED", "GREENHOUSE"})
#: The params this pass writes — what one record takes from the OTHERS. A drag changes
#: them at every step (a lawn's cut-outs are the other items' outlines in its frame);
#: the 3D controller applies a change of these alone at most once per
#: ``sync_controller.CONTEXT_REBUILD_MIN_MS``.
CONTEXT_PARAMS: Final = frozenset({
    PARAM_DOOR_WALL, PARAM_LAWN_CUTOUTS, PARAM_LAWN_BLADES, PARAM_HEDGE_LEAVES,
})
#: Path styles the canvas paints with round caps and joins (``path_style_paint``): their
#: cut-out is that rounded stroke, half a width past each end — blades grew through the
#: painted round ends of the square-ended outline (3D review of #388).
ROUND_PATH_STYLES: Final = frozenset({"GRAVEL_PATH", "DIRT_PATH"})
#: A pond's cut-out reaches past its outline by its coping and a little more: blades
#: grew through the coping's overhang (3D review of #388).
POND_CLEARANCE_CM: Final = COPING_OUT_CM + 2.0
MAX_CUTOUTS: Final = 96
MAX_CUTOUT_VERTICES: Final = 6000
#: The most lawn blades a whole plan grows (3 triangles a blade); a lawn's own
#: density and cap are ``builders.surfaces``' ``BLADES_PER_M2`` and ``MAX_BLADES``.
MAX_PLAN_BLADES: Final = 60_000
#: The most hedge leaves a whole plan grows (#954), shared by the hedges and hedge
#: fences by their own demand; a plan's long runs stay at their per-metre density
#: until this bound is reached.
MAX_PLAN_HEDGE_LEAVES: Final = hedges.MAX_PLAN_HEDGE_LEAVES

_F64 = NDArray[np.float64]


def context_params_for(record: Record) -> frozenset[str]:
    """The context a record consumes, including an absent value of that context."""
    if record.kind in DOOR_TARGETS:
        return frozenset({PARAM_DOOR_WALL})
    if record.kind == "LAWN" and record.height_cm is None:
        return frozenset({PARAM_LAWN_BLADES, PARAM_LAWN_CUTOUTS})
    if hedges.is_hedge_record(record):
        return frozenset({PARAM_HEDGE_LEAVES})
    return frozenset()


def without_lawn_blades(records: Mapping[str, Record]) -> dict[str, Record]:
    """A Low/Medium presentation: no blade synthesis or upload; ground paint stays."""
    return {item_id: replace(record, params=record.params.merged({PARAM_LAWN_BLADES: 0}))
            if PARAM_LAWN_BLADES in context_params_for(record) else record
            for item_id, record in records.items()}


def _local(transform: Transform, x: float, y: float) -> tuple[float, float]:
    """A scene point in an item's local frame: ``R(−θ)·(p − T)``."""
    c, s = cos_sin(transform.rotation_deg)
    dx, dy = x - transform.east_cm, y - transform.north_cm
    return (c * dx + s * dy, -s * dx + c * dy)


def _segments(record: Record) -> _F64:
    """The record's lines in the scene, (m, 2, 2): a PATH's centre line, every
    other kind's outer outlines."""
    if record.path:
        line = np.asarray(pose_ring(record.transform, record.path), dtype=np.float64)
        return np.stack([line[:-1], line[1:]], axis=1) if len(line) >= 2 else np.zeros((0, 2, 2))
    pieces = []
    for ring in record.footprints:
        closed = np.asarray(pose_ring(record.transform, (*ring, ring[0])), dtype=np.float64)
        pieces.append(np.stack([closed[:-1], closed[1:]], axis=1))
    return np.concatenate(pieces) if pieces else np.zeros((0, 2, 2))


def _nearest(segments: _F64, x: float, y: float) -> tuple[float, float, float]:
    """``(distance, x, y)`` of the point of ``segments`` nearest to (x, y)."""
    start, end = segments[:, 0], segments[:, 1]
    edge = end - start
    length2 = np.maximum((edge * edge).sum(axis=1), 1e-12)
    point = np.array([x, y])
    t = np.clip(((point - start) * edge).sum(axis=1) / length2, 0.0, 1.0)
    near = start + t[:, None] * edge
    distance = np.linalg.norm(near - point, axis=1)
    best = int(distance.argmin())
    return float(distance[best]), float(near[best, 0]), float(near[best, 1])


def _door_points(records: MutableMapping[str, Record]) -> None:
    by_kind: dict[str, list[_F64]] = {}
    for record in records.values():
        if record.kind in ("PATH", "DRIVEWAY"):
            segments = _segments(record)
            if len(segments):
                by_kind.setdefault(record.kind, []).append(segments)
    for item_id, record in records.items():
        targets = DOOR_TARGETS.get(record.kind)
        if targets is None:
            continue
        wall: int | None = None
        for kind in targets:
            if kind in by_kind and record.footprints:
                _d, x, y = _nearest(np.concatenate(by_kind[kind]), record.transform.east_cm,
                                    record.transform.north_cm)
                wall = door_wall_index(record.footprints[0], _local(record.transform, x, y))
                break
        if wall is not None:
            records[item_id] = replace(record, params=record.params.merged({PARAM_DOOR_WALL: wall}))


def _box(rings: list[_F64]) -> tuple[float, float, float, float]:
    every = np.concatenate(rings)
    low, high = every.min(axis=0), every.max(axis=0)
    return float(low[0]), float(low[1]), float(high[0]), float(high[1])


def _blade_shares(
    areas: dict[int, float],
    densities: dict[int, float] | None = None,
) -> dict[int, int]:
    """The plan's blades shared out by area: each lawn gets its own density's count
    (``BLADES_PER_M2`` for grass, ``MOSS_BLADES_PER_M2`` for moss, at most
    ``MAX_LAWN_BLADES``) where the budget allows, and what a lawn cannot use (a capped
    lawn, a small one) goes to the others — the lawns that want least per square metre
    are served first, each at most its area's share of what is left."""
    demand = {
        index: min(
            MAX_LAWN_BLADES,
            int((densities[index] if densities is not None else BLADES_PER_M2) * area / 10_000.0),
        )
        for index, area in areas.items()
    }
    budget = float(MAX_PLAN_BLADES)
    area_left = sum(areas.values())
    shares: dict[int, int] = {}
    for index in sorted(areas, key=lambda i: (demand[i] / areas[i] if areas[i] > 0.0 else 0.0, i)):
        fair = budget * areas[index] / area_left if area_left > 0.0 else 0.0
        shares[index] = min(demand[index], int(fair))
        budget -= shares[index]
        area_left -= areas[index]
    return shares


def _cutout_rings(record: Record) -> list[tuple[tuple[float, float], ...]]:
    """The ground ``record`` keeps blades off, in its own frame, one ring a region (its
    holes joined in: ``_keyhole``): its outline — for a pond grown by its coping, for an
    open gravel or dirt path the rounded stroke the canvas paints, for a stepping-stone
    path each painted stone (the path is not a continuous surface)."""
    if record.kind == "POND_POOL":  # the outline its coping is built on (a round pond: round)
        return [_keyhole(grown, holes) for outer, holes in pond_regions(record)
                for grown in grown_polygon(outer, POND_CLEARANCE_CM)]
    width = record.path_width_cm
    style = record.params.get(PARAM_PATH_STYLE)
    if record.kind == "PATH" and style == "STEPPING_STONES" and width:
        line, closed = centre_line(record)
        if len(line) >= 2:
            walked = np.asarray(line, dtype=np.float64)
            if closed:  # the painter's walk goes round the loop and closes it (#998)
                walked = np.concatenate([walked, walked[:1]])
            points, along = walk_path(walked, width * 1.8)
            # #998: the 2D painter draws a stone wherever its walk lands, including one
            # centred on an open end; the path's footprint is not a surface there. Cut
            # each stone's own rounded rectangle (as its square envelope, 1 cm clear so
            # a 2.4 cm ridge's edge cannot graze the bevelled base) out of the lawn/rake.
            half_long, half_wide = 0.4 * width + 1.0, 0.3 * width + 1.0
            rings: list[tuple[tuple[float, float], ...]] = []
            for (x, y), (dx, dy) in zip(points, along, strict=True):
                rings.append(tuple(
                    (float(x + dx * sx * half_long - dy * sy * half_wide),
                     float(y + dy * sx * half_long + dx * sy * half_wide))
                    for sx, sy in ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))))
            if rings:
                return rings
    if record.kind == "PATH" and style in ROUND_PATH_STYLES and width:
        line, closed = centre_line(record)
        if not closed and len(line) >= 2:
            rounded = polyline_round_outline([(float(x), float(y)) for x, y in line], width)
            try:
                return [_keyhole(outer, holes) for outer, holes in group_rings([tuple(r) for r in rounded])]
            except ValueError:  # no regions: the outline below
                pass
    return [_keyhole(outer, holes) for outer, holes in record.regions]


def _keyhole(outer: Sequence[tuple[float, float]], holes: Sequence[Sequence[tuple[float, float]]]
             ) -> tuple[tuple[float, float], ...]:
    """ONE ring for a region with holes: each hole is joined to the ring by a doubled
    edge, there and back. An even-odd test of the one ring (the lawn's cut-out mask)
    counts the doubled edge twice or not at all, so the holes stay out of it — a
    loop of path round a bed, or a terrace round a pond, keeps the lawn inside it."""
    ring = [(float(x), float(y)) for x, y in outer]
    for hole in holes:
        inner = [(float(x), float(y)) for x, y in hole]
        if len(inner) < 3 or len(ring) < 3:
            continue
        reach = np.hypot(*(np.asarray(ring) - np.asarray(inner[0])).T)
        at = int(reach.argmin())
        ring = [*ring[:at + 1], *inner, inner[0], *ring[at:]]
    return tuple(ring)


def _lawn_cutouts(records: MutableMapping[str, Record]) -> None:
    order = list(records)
    lawns = [index for index, item_id in enumerate(order)   # a lawn with a height grows no blades
             if records[item_id].kind == "LAWN" and records[item_id].footprints
             and records[item_id].height_cm is None]
    # #960 review: a SAND court's rake stops at a flat item painted above it too (the
    # Japanese garden's moss islands lie on the court), so the same pass serves both.
    sands = [index for index, item_id in enumerate(order)
             if records[item_id].kind != "LAWN" and records[item_id].footprints
             and is_sand(records[item_id])]
    if not lawns and not sands:
        return
    lawn_set = set(lawns)
    candidates = []  # every record that cuts a ground surface it lies on: collected once
    for index, item_id in enumerate(order):
        other = records[item_id]
        enclosed = other.kind in ENCLOSED_KINDS or other.kind in GROUND_COVERING_KINDS
        if not other.footprints:
            continue
        if not enclosed:
            if other.kind in ("TREE", "SHRUB", "PERENNIAL"):
                continue
            if (other.height_cm is not None or other.material.paint is None
                    or other.kind in OBJECT_KINDS):
                continue
        own = _cutout_rings(other)
        if not own:
            continue
        rings = [np.asarray(pose_ring(other.transform, ring), dtype=np.float64) for ring in own]
        candidates.append((len(order) if enclosed else index, own, rings, _box(rings),
                           other.kind not in _NOT_A_CUTOUT))
    shares = _blade_shares(
        {index: sum(ring_area(ring) for ring in records[order[index]].footprints)
         for index in lawns},
        {index: MOSS_BLADES_PER_M2 if is_moss(records[order[index]]) else BLADES_PER_M2
         for index in lawns},
    )
    for index in [*lawns, *sands]:
        item_id = order[index]
        target = records[item_id]
        merged: dict[str, object] = {}
        if index in lawn_set:
            merged[PARAM_LAWN_BLADES] = shares[index]
        target_rings = [np.asarray(pose_ring(target.transform, ring), dtype=np.float64)
                        for ring in target.footprints]
        lx0, ly0, lx1, ly1 = _box(target_rings)
        found: list[tuple[float, tuple[tuple[float, float], ...]]] = []
        for other_index, own, rings, (ox0, oy0, ox1, oy1), cuts_lawn in candidates:
            if other_index <= index:  # painted under the target: the target hides it
                continue
            if index in lawn_set and not cuts_lawn:  # a second lawn is not a lawn cut-out
                continue
            if ox1 < lx0 or ox0 > lx1 or oy1 < ly0 or oy0 > ly1:
                continue
            for ring, scene_ring in zip(own, rings, strict=True):
                local = tuple((round(x, 1) + 0.0, round(y, 1) + 0.0)
                              for x, y in (_local(target.transform, float(px), float(py)) for px, py in scene_ring))
                found.append((ring_area(ring), local))
        if found:
            found.sort(key=lambda entry: -entry[0])
            kept: list[tuple[tuple[float, float], ...]] = []
            vertices = 0
            for _area, ring in found:
                if len(kept) >= MAX_CUTOUTS or vertices + len(ring) > MAX_CUTOUT_VERTICES:
                    break
                kept.append(ring)
                vertices += len(ring)
            merged[PARAM_LAWN_CUTOUTS] = tuple(kept)
        if merged:
            records[item_id] = replace(target, params=target.params.merged(merged))  # type: ignore[arg-type]


def _hedge_leaves(records: MutableMapping[str, Record]) -> None:
    """Share ``MAX_PLAN_HEDGE_LEAVES`` among the hedges by their own demand (#954)."""
    demand: dict[str, tuple[int, float]] = {}
    for item_id, record in records.items():
        measured = hedges.hedge_area_and_run(record)
        if measured is None:
            continue
        area, run = measured
        wanted = hedges.leaf_count(area, run_length_cm=run)
        demand[item_id] = (wanted, run)
    if not demand:
        return
    total = sum(wanted for wanted, _run in demand.values())
    if total <= MAX_PLAN_HEDGE_LEAVES:
        shares = {item_id: wanted for item_id, (wanted, _run) in demand.items()}
    else:
        shares = {}
        budget = float(MAX_PLAN_HEDGE_LEAVES)
        remaining = float(total)
        # each hedge's share is proportional to its own demand; the sorted order only
        # fixes how the integer remainders fall, so the same plan always shares alike
        for item_id in sorted(demand, key=lambda key: (demand[key][0], key)):
            wanted = demand[item_id][0]
            fair = budget * wanted / remaining if remaining > 0.0 else 0.0
            share = min(wanted, int(fair))
            shares[item_id] = share
            budget -= share
            remaining -= wanted
    for item_id, share in shares.items():
        record = records[item_id]
        records[item_id] = replace(
            record, params=record.params.merged({PARAM_HEDGE_LEAVES: int(share)}))


def with_context(records: MutableMapping[str, Record]) -> None:
    """Write every record's context params (module docstring), in place.

    Existing values are replaced. Since #954 a hedge gains ``hedge_leaves`` in the same
    step — its share of the plan's hedge budget — so this may add that one key; it
    never removes a key or changes any other param.
    """
    _door_points(records)
    _lawn_cutouts(records)
    _hedge_leaves(records)


__all__ = ["CONTEXT_PARAMS", "DOOR_TARGETS", "GROUND_COVERING_KINDS", "MAX_CUTOUTS",
           "MAX_CUTOUT_VERTICES", "MAX_PLAN_BLADES", "MAX_PLAN_HEDGE_LEAVES", "with_context"]
