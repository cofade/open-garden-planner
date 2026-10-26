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
  canvas paints (``ROUND_PATH_STYLES``). At most
  ``MAX_CUTOUTS`` outlines and ``MAX_CUTOUT_VERTICES`` vertices, the largest
  first: beyond that, the smallest items let blades through.
- **How many blades a lawn grows** is the PLAN's to say: ``params["lawn_blades"]``
  shares ``MAX_PLAN_BLADES`` among the plan's lawns by area (each lawn its own
  density and ``surfaces.MAX_BLADES`` at most; what a capped or small lawn cannot
  use goes to the others), so a plan of many lawns — or of 2,000 stacked ones —
  grows a bounded meadow.

Because these params are GEOMETRY, an edit that changes them rebuilds the house
whose door turns to another wall and the lawn a flat item crosses — and only
those. The ground bake paints neither param (``record.BUILD_ONLY_PARAMS``).
"""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from dataclasses import replace
from typing import Final

import numpy as np
from numpy.typing import NDArray

from ..shadow_geometry import grown_polygon, polyline_round_outline
from .builders import OBJECT_KINDS
from .builders.common import centre_line
from .builders.facade import door_wall_index
from .builders.surfaces import BLADES_PER_M2, COPING_OUT_CM, pond_regions
from .builders.surfaces import MAX_BLADES as MAX_LAWN_BLADES
from .frame import cos_sin, pose_ring
from .polygon import group_rings, ring_area
from .record import (
    PARAM_DOOR_WALL,
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
#: The objects whose build covers their footprint at the ground — a pot, a pit, a box:
#: without a height (``object_height_estimate``) they still cut a lawn. Every other
#: object is built as a solid on legs, posts, a pole or ropes and the lawn grows under
#: it; a cut-out left a bald patch there (senior review of #388: a pergola 12 m²,
#: a parasol 6 m²). An object WITH a height is a solid and cuts nothing anyway.
GROUND_COVERING_KINDS: Final = frozenset({
    "COLD_FRAME", "COMPOST_BIN", "FIRE_PIT", "HOT_TUB", "PLANTER_POT", "RAIN_BARREL", "SANDBOX"})
#: Enclosed buildings cut a lawn whatever their place in the paint order: their
#: inside is seen — through a greenhouse's glass, into a house with its roof off
#: (Cutaway) — and no grass grows on a floor.
ENCLOSED_KINDS: Final = frozenset({"HOUSE", "GARAGE_SHED", "TOOL_SHED", "GREENHOUSE"})
#: The params this pass writes — what one record takes from the OTHERS. A drag changes
#: them at every step (a lawn's cut-outs are the other items' outlines in its frame);
#: the 3D controller applies a change of these alone at most once per
#: ``sync_controller.CONTEXT_REBUILD_MIN_MS`` (senior review of #388).
CONTEXT_PARAMS: Final = frozenset({PARAM_DOOR_WALL, PARAM_LAWN_CUTOUTS, PARAM_LAWN_BLADES})
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

_F64 = NDArray[np.float64]


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


def _blade_shares(areas: dict[int, float]) -> dict[int, int]:
    """The plan's blades shared out by area: each lawn gets its own density's count
    (``BLADES_PER_M2``, at most ``MAX_LAWN_BLADES``) where the budget allows, and what
    a lawn cannot use (a capped lawn, a small one) goes to the others — the lawns
    that want least per square metre are served first, each at most its area's share
    of what is left."""
    demand = {index: min(MAX_LAWN_BLADES, int(BLADES_PER_M2 * area / 10_000.0))
              for index, area in areas.items()}
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
    open gravel or dirt path the rounded stroke the canvas paints."""
    if record.kind == "POND_POOL":  # the outline its coping is built on (a round pond: round)
        return [_keyhole(grown, holes) for outer, holes in pond_regions(record)
                for grown in grown_polygon(outer, POND_CLEARANCE_CM)]
    width = record.path_width_cm
    if record.kind == "PATH" and record.params.get(PARAM_PATH_STYLE) in ROUND_PATH_STYLES and width:
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
    lawns = [index for index, item_id in enumerate(order)
             if records[item_id].kind == "LAWN" and records[item_id].footprints]
    if not lawns:
        return
    candidates = []  # every record that cuts a lawn it lies on: collected once
    for index, item_id in enumerate(order):
        other = records[item_id]
        enclosed = other.kind in ENCLOSED_KINDS
        if not other.footprints or (not enclosed and (
                other.kind in _NOT_A_CUTOUT or other.height_cm is not None or other.material.paint is None
                or (other.kind in OBJECT_KINDS and other.kind not in GROUND_COVERING_KINDS))):
            continue
        own = _cutout_rings(other)
        if not own:
            continue
        rings = [np.asarray(pose_ring(other.transform, ring), dtype=np.float64) for ring in own]
        candidates.append((len(order) if enclosed else index, own, rings, _box(rings)))
    shares = _blade_shares({index: sum(ring_area(ring) for ring in records[order[index]].footprints)
                            for index in lawns})
    for index in lawns:
        item_id = order[index]
        lawn = records[item_id]
        merged: dict[str, object] = {PARAM_LAWN_BLADES: shares[index]}
        lawn_rings = [np.asarray(pose_ring(lawn.transform, ring), dtype=np.float64) for ring in lawn.footprints]
        lx0, ly0, lx1, ly1 = _box(lawn_rings)
        found: list[tuple[float, tuple[tuple[float, float], ...]]] = []
        for other_index, own, rings, (ox0, oy0, ox1, oy1) in candidates:
            if other_index <= index:  # painted under the lawn: the lawn hides it
                continue
            if ox1 < lx0 or ox0 > lx1 or oy1 < ly0 or oy0 > ly1:
                continue
            for ring, scene_ring in zip(own, rings, strict=True):
                local = tuple((round(x, 1) + 0.0, round(y, 1) + 0.0)
                              for x, y in (_local(lawn.transform, float(px), float(py)) for px, py in scene_ring))
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
        records[item_id] = replace(lawn, params=lawn.params.merged(merged))  # type: ignore[arg-type]


def with_context(records: MutableMapping[str, Record]) -> None:
    """Write every record's context params (module docstring), in place: values
    are replaced, no key is added or removed."""
    _door_points(records)
    _lawn_cutouts(records)


__all__ = ["CONTEXT_PARAMS", "DOOR_TARGETS", "GROUND_COVERING_KINDS", "MAX_CUTOUTS", "MAX_CUTOUT_VERTICES", "MAX_PLAN_BLADES", "with_context"]
