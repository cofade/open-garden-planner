"""Cutaway and X-ray: what stands between the camera and the selection (Phase 17 L2.4, #386).

Qt-free: standard library and numpy. Two switches of one "Cutaway" mode:

- **Roofs off.** Every mesh part of material kind ``ROOF_KIND`` (the roof a
  building builder emits as a part of its own — ``builders/buildings.py``) is
  hidden by the engine; the walls stay. One switch, not a rebuild: no record, no
  mesh, no Model changes for it, and a building added while it is on is born
  without its roof showing.
- **Occluders fade.** ``occluders`` answers "which items does the view of the
  selection pass through?" from the camera's eye to sample points of each
  selected item — the centre and the corners of its bounding box, drawn in by
  ``SAMPLE_SHRINK`` so that a corner is a point OF the item and not of the air
  beside it. An item the engine holds no mesh for — a bed without a height, a
  lawn, a path: drawn into the ground — is looked at on its posed footprint,
  ``FLAT_TARGET_LIFT_CM`` above its ground plane: the centre and up to
  ``MAX_FLAT_TARGETS`` ring vertices drawn in by ``SAMPLE_SHRINK`` (without them
  Cutaway faded nothing for a selected bed — 3D review of #386). A segment is tested against every item's bounding box first and
  against the triangles of the boxes it meets only (``pick_oracle.cast_segment``,
  the pick oracle's own Möller–Trumbore — not a second ray test). The engine then
  draws those items at ``XRAY_OPACITY``.

The scene is the meshes the ENGINE holds for the records (``xray_scene(records,
parts_of)`` with the sink's books, as walk mode builds its world): what fades is
what is drawn in front, never a second build.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypeAlias

import numpy as np
from numpy.typing import NDArray

from .frame import pose_ring
from .mesh import MeshPart
from .pick_oracle import PartsOf, PickScene, cast_segment, pick_scene
from .record import Record

Vector: TypeAlias = tuple[float, float, float]
_F64: TypeAlias = NDArray[np.float64]

#: The material kind of a roof part — the parts "Cutaway" hides.
ROOF_KIND: Final = "roof"
#: How opaque an occluder is drawn while it fades (Cutaway on, something selected).
XRAY_OPACITY: Final = 0.22
#: A selected item's sample points are its bounding box's centre and corners, drawn
#: this share of the way towards the centre.
SAMPLE_SHRINK: Final = 0.15
#: At most this many selected items are looked through (a select-all of a large plan
#: would cast thousands of segments on the GUI thread for a picture nobody can read).
MAX_XRAY_ITEMS: Final = 16
#: A flat item (no mesh) is looked at this high above its ground plane, cm.
FLAT_TARGET_LIFT_CM: Final = 5.0
#: At most this many ring vertices of a flat item's footprint are sample points.
MAX_FLAT_TARGETS: Final = 8


@dataclass(frozen=True, slots=True, eq=False)
class XrayScene:
    """The pick scene of the records and each item's box: ``low`` / ``high``, one row
    per entry of ``pick.item_ids``, and the rows of its triangles in ``pick``;
    ``flat``: the sample points of each record the engine holds no mesh for."""

    pick: PickScene
    low: _F64
    high: _F64
    rows: tuple[NDArray[np.int64], ...]
    flat: Mapping[str, tuple[Vector, ...]]
    children: Mapping[str, tuple[str, ...]] = ()

    def index(self, item_id: str) -> int | None:
        try:
            return self.pick.item_ids.index(item_id)
        except ValueError:
            return None


def xray_scene(records: Mapping[str, Record], parts_of: PartsOf) -> XrayScene:
    """The X-ray scene of ``records``, built from ``parts_of`` (module docstring).

    Roof parts (``ROOF_KIND``) are left out: X-ray runs only in Cutaway, which cuts
    every roof, so a view through a cut roof passes through nothing — or a plant in a
    greenhouse would fade the whole building (senior review of #386)."""
    def uncut(record: Record) -> Sequence[MeshPart]:
        return tuple(part for part in parts_of(record) if part.material_kind != ROOF_KIND)

    pick = pick_scene(records, uncut)
    count = len(pick.item_ids)
    low = np.zeros((count, 3))
    high = np.zeros((count, 3))
    rows: list[NDArray[np.int64]] = []
    if pick.triangle_count:
        a = pick.corner
        b = a + pick.edge1
        c = a + pick.edge2
        tri_low = np.minimum(np.minimum(a, b), c)
        tri_high = np.maximum(np.maximum(a, b), c)
        order = np.argsort(pick.item, kind="stable")
        bounds = np.searchsorted(pick.item[order], np.arange(count + 1))
        for index in range(count):
            mine = order[bounds[index]:bounds[index + 1]]
            rows.append(mine)
            low[index] = tri_low[mine].min(axis=0)
            high[index] = tri_high[mine].max(axis=0)
    held = set(pick.item_ids)
    flat = {item_id: points for item_id, record in records.items()
            if item_id not in held and (points := flat_targets(record))}
    children: dict[str, list[str]] = {}
    for item_id, record in records.items():
        if record.parent_id:
            children.setdefault(record.parent_id, []).append(item_id)
    children_map = {k: tuple(v) for k, v in children.items()}
    return XrayScene(pick, low, high, tuple(rows), flat, children_map)


def flat_targets(record: Record) -> tuple[Vector, ...]:
    """The sample points of an item drawn into the ground (module docstring): per
    footprint ring its vertex centre and up to ``MAX_FLAT_TARGETS`` of its vertices,
    drawn in by ``SAMPLE_SHRINK``, posed, ``FLAT_TARGET_LIFT_CM`` above its base."""
    lift = record.transform.base_cm + FLAT_TARGET_LIFT_CM
    points: list[Vector] = []
    for outer, _holes in record.regions:
        ring = np.asarray(outer, dtype=np.float64).reshape(-1, 2)
        if not len(ring):
            continue
        center = ring.mean(axis=0)
        step = max(1, -(-len(ring) // MAX_FLAT_TARGETS))
        local = [center, *(vertex + (center - vertex) * SAMPLE_SHRINK for vertex in ring[::step])]
        for x, y in pose_ring(record.transform, ((float(p[0]), float(p[1])) for p in local)):
            points.append((x, y, lift))
    return tuple(points)


def target_points(scene: XrayScene, item_id: str) -> tuple[Vector, ...]:
    """The points of a selected item the view must reach (module docstring); none for
    an item the scene does not hold."""
    index = scene.index(item_id)
    if index is None:
        return tuple(scene.flat.get(item_id, ()))
    low, high = scene.low[index], scene.high[index]
    center = (low + high) / 2.0
    near_low = low + (center - low) * SAMPLE_SHRINK
    near_high = high - (high - center) * SAMPLE_SHRINK
    points = [center]
    for x in (near_low[0], near_high[0]):
        for y in (near_low[1], near_high[1]):
            for z in (near_low[2], near_high[2]):
                points.append(np.array([x, y, z]))
    return tuple((float(p[0]), float(p[1]), float(p[2])) for p in points)


def _boxes_met(scene: XrayScene, origin: _F64, end: _F64) -> NDArray[np.int64]:
    """Indices of the items whose bounding box the segment ``origin`` → ``end`` meets
    (the slab test, every box at once)."""
    direction = end - origin
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = (scene.low - origin) / direction
        t2 = (scene.high - origin) / direction
    near = np.where(np.isnan(t1), -np.inf, np.minimum(t1, t2))
    far = np.where(np.isnan(t2), np.inf, np.maximum(t1, t2))
    # an axis the segment runs parallel to: inside that slab (−inf, inf), outside empty
    parallel = direction == 0.0
    if parallel.any():
        inside = (origin >= scene.low) & (origin <= scene.high)
        near = np.where(parallel, np.where(inside, -np.inf, np.inf), near)
        far = np.where(parallel, np.where(inside, np.inf, -np.inf), far)
    enter = near.max(axis=1)
    leave = far.min(axis=1)
    return np.flatnonzero((enter <= leave) & (leave >= 0.0) & (enter <= 1.0))


def occluders(scene: XrayScene, eye: Sequence[float], selected: Collection[str]) -> frozenset[str]:
    """The items the view from ``eye`` passes through on its way to the selected items
    (module docstring): every item met by a segment from the eye to one of their
    sample points before it gets there, the selected items themselves excepted. At
    most ``MAX_XRAY_ITEMS`` selected items (in sorted order) are looked through."""
    wanted = sorted(item_id for item_id in set(selected)
                    if scene.index(item_id) is not None or item_id in scene.flat)
    if not wanted or not scene.pick.triangle_count:
        return frozenset()
    origin = np.asarray(eye, dtype=np.float64)
    keep = set(wanted)
    if getattr(scene, "children", None):
        for parent_id in wanted:
            if parent_id in scene.children:
                keep.update(scene.children[parent_id])
    found: set[str] = set()
    for item_id in wanted[:MAX_XRAY_ITEMS]:
        for point in target_points(scene, item_id):
            end = np.asarray(point, dtype=np.float64)
            met = [index for index in _boxes_met(scene, origin, end).tolist()
                   if scene.pick.item_ids[index] not in keep]
            if not met:
                continue
            rows = np.concatenate([scene.rows[index] for index in met])
            for hit in cast_segment(scene.pick, origin, end, rows=rows):
                if hit.item_id not in keep:
                    found.add(hit.item_id)
    return frozenset(found)
