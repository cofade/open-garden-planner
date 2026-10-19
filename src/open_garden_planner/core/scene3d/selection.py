"""The selection ring — what is selected, as ONE mesh (Phase 17 L1.8, ADR-065).

Qt-free: standard library and numpy. Selection is in none of a record's three
signatures (ADR-064): selecting an item must never rebuild, re-pose or re-tint a
model. So the highlight is not a property of a model at all. It is one mesh of
its own — ``Selection.ring`` — that ``SceneSync`` hands the engine through one
additive ``EngineSink`` method (``set_selection``) and that the engine keeps in
ONE Model for the life of the scene: a selection change re-loads that Model's
vertex data and creates and destroys nothing.

THE RING of a record follows every outline of its footprint — each outer ring and
each hole (a closed fence gets a ring outside and one inside) — at the record's
standing base (``transform.base_cm``: the bed's soil for a plant on a bed),
``RING_LIFT_CM`` above it. It is in the SCENE frame: the record's transform is
applied here, so several selected items merge into one mesh, and a selected item
that moves takes the ring along in the transaction of the move (``SceneSync``
re-sends it; nothing else is re-sent).

THE BAND'S WIDTH IS THE SHADER'S, NOT THE MESH'S. A band in centimetres would be a
hair when the whole garden is framed and a plank in walk mode. So every outline
point carries THREE vertices at the SAME position, told apart by what the vertex
shader does with them (``qml/ring.vert``)::

    normal  = the level direction away from the solid (the corner's mitre), unit
    uv.x    = how many band widths to move along that direction (0, or the mitre's
              length: 1 on a straight run, more at a corner, at most MITRE_LIMIT)
    uv.y    = how many band widths to move UP (0 or 1)

    (0, 0)  the outline itself          ┐ a flat band on the ground, outside the
    (m, 0)  the band's outer edge       ┘ footprint — what is seen from above
    (m, 1)  one width above that edge   ─ a ribbon standing on the outer edge —
                                          what is seen from the side

and the shader turns one band width into ``RING_WIDTH_PX`` pixels at the vertex's
depth. Outside the footprint, always: the item's own solid stands on the
footprint and would hide a band laid inside it.

The colour is the canvas's selection blue (``SELECTION_RGB`` — a mirror of the
2D highlight pen and of ``SelectTool.ENCLOSING_COLOR``, pinned against both).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Final, TypeAlias

import numpy as np
from numpy.typing import NDArray

from .color import Rgba
from .frame import cos_sin
from .mesh import Mesh
from .record import Point, Record, Ring

_log = logging.getLogger(__name__)

#: How far above its standing base the ring starts (cm): clear of the surface.
RING_LIFT_CM: Final = 1.0
#: A corner's mitre is at most this many band widths long (a needle-sharp corner
#: would throw it metres away).
MITRE_LIMIT: Final = 2.5
#: The band's width on screen, logical pixels (``Garden.qml``: ``ringWidthPx``).
RING_WIDTH_PX: Final = 3.0
#: The canvas's selection colour, sRGB (module docstring).
SELECTION_RGB: Final[tuple[int, int, int]] = (0, 120, 215)
SELECTION_RGBA: Final[Rgba] = (*SELECTION_RGB, 255)
#: Two outline points closer than this (cm) are one corner.
_SAME_POINT_CM: Final = 1e-6

_F64: TypeAlias = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Selection:
    """What the engine is told about the selection (module docstring).

    ``ids``: the selected items that HAVE a record, sorted — an id the canvas has
    selected and the 3D scene does not hold (a text, an item on a hidden layer)
    is not in it and gets no ring. ``ring``: the merged ring mesh of all of them,
    scene frame; empty when ``ids`` is. Two selections are equal when the engine
    would draw the same.
    """

    ids: tuple[str, ...]
    ring: Mesh

    def __bool__(self) -> bool:
        return bool(self.ids)


EMPTY_SELECTION: Final = Selection((), Mesh.empty())


@lru_cache(maxsize=2048)
def _outline(ring: Ring) -> tuple[_F64, _F64, _F64] | None:
    """A closed ring (item-local) as ``(points, directions, mitres)``: its distinct
    corners, at each the unit direction away from what is on the LEFT of the ring's
    direction of travel — outwards for a counter-clockwise outer ring, into the
    hole for a clockwise hole ring: away from the solid both times — and the
    mitre's length in band widths. None for a ring without three distinct corners."""
    points = np.asarray(ring, dtype=np.float64).reshape(-1, 2)
    if len(points) < 3:
        return None
    apart = np.hypot(*(points - np.roll(points, 1, axis=0)).T) > _SAME_POINT_CM
    points = points[apart]  # a point that repeats the one before it (also last == first)
    if len(points) < 3:
        return None
    ahead = np.roll(points, -1, axis=0) - points
    ahead /= np.hypot(ahead[:, 0], ahead[:, 1])[:, None]
    after = np.stack([ahead[:, 1], -ahead[:, 0]], axis=1)     # right of travel, edge leaving
    before = np.roll(after, 1, axis=0)                        # … of the edge arriving
    mitre = before + after
    length = np.hypot(mitre[:, 0], mitre[:, 1])
    folded = length < 1e-9                                    # the outline doubles back
    mitre = np.where(folded[:, None], after, mitre / np.where(folded, 1.0, length)[:, None])
    cosine = np.einsum("ij,ij->i", mitre, after)
    reach = 1.0 / np.maximum(cosine, 1.0 / MITRE_LIMIT)
    for array in (points, mitre, reach):
        array.setflags(write=False)
    return points, mitre, reach


def _posed_outline(record: Record, ring: Sequence[Point]) -> tuple[_F64, _F64, _F64] | None:
    """``_outline(ring)`` in the SCENE frame: turned and moved by the record's
    transform. The directions turn with it; the mitres do not change."""
    local = _outline(tuple(ring))
    if local is None:
        return None
    points, directions, reach = local
    c, s = cos_sin(record.transform.rotation_deg)
    turn = np.array([[c, s], [-s, c]])                        # row vectors: v @ turn
    posed = points @ turn + (record.transform.east_cm, record.transform.north_cm)
    return posed, directions @ turn, reach


def _ring_arrays(posed: _F64, directions: _F64, reach: _F64, height_cm: float,
                 first: int) -> tuple[_F64, _F64, _F64, NDArray[np.int64]]:
    """Positions, normals, uvs and triangles (indices from ``first``) of one ring."""
    count = len(posed)
    positions = np.empty((3 * count, 3))
    positions[:, :2] = np.tile(posed, (3, 1))
    positions[:, 2] = height_cm
    normals = np.zeros((3 * count, 3))
    normals[:, :2] = np.tile(directions, (3, 1))
    uvs = np.zeros((3 * count, 2))
    uvs[count:2 * count, 0] = reach
    uvs[2 * count:, 0] = reach
    uvs[2 * count:, 1] = 1.0
    here = np.arange(count)
    there = (here + 1) % count
    inner, outer, top = here, here + count, here + 2 * count
    inner_next, outer_next, top_next = there, there + count, there + 2 * count
    triangles = np.concatenate([
        np.stack([inner, outer, outer_next], axis=1), np.stack([inner, outer_next, inner_next], axis=1),
        np.stack([outer, top, top_next], axis=1), np.stack([outer, top_next, outer_next], axis=1),
    ]) + first
    return positions, normals, uvs, triangles


def selection_of(records: Mapping[str, Record], ids: Iterable[str]) -> Selection:
    """The selection for ``ids`` in ``records``: the ids that have a record, and the
    ring mesh around every outline of each (module docstring). Ids without a
    record are left out; so is a record whose outline cannot be ringed (logged) —
    one bad item never takes the others' rings with it."""
    wanted = sorted({str(item_id) for item_id in ids} & records.keys())
    if not wanted:
        return EMPTY_SELECTION
    kept: list[str] = []
    positions: list[_F64] = []
    normals: list[_F64] = []
    uvs: list[_F64] = []
    triangles: list[NDArray[np.int64]] = []
    count = 0
    for item_id in wanted:
        record = records[item_id]
        height = record.transform.base_cm + RING_LIFT_CM
        try:
            rings = [_posed_outline(record, ring)
                     for outer, holes in record.regions for ring in (outer, *holes)]
        except Exception as error:  # noqa: BLE001 - contained to this item
            _log.warning("3D selection: no ring for %s item %r (%s)", record.kind, item_id,
                         type(error).__name__)
            continue
        drawn = False
        for ring in rings:
            if ring is None:
                continue
            part = _ring_arrays(*ring, height, count)
            positions.append(part[0])
            normals.append(part[1])
            uvs.append(part[2])
            triangles.append(part[3])
            count += len(part[0])
            drawn = True
        if drawn:
            kept.append(item_id)
    if not kept:
        return EMPTY_SELECTION
    mesh = Mesh.from_arrays(np.concatenate(positions), np.concatenate(normals),
                            np.ones((count, 4)), np.concatenate(uvs), np.concatenate(triangles))
    return Selection(tuple(kept), mesh)
