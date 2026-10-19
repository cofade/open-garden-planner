"""``Quick3DSink`` — the ``EngineSink`` of the Qt Quick 3D renderer (L1.2). Engine-free.

``SceneSync`` (``core/scene3d``) calls the sink methods; the sink keeps the
books and tells an ``EngineScene`` what to do. ``Quick3DHost`` implements
``EngineScene`` with real ``Model`` objects; a list-backed double implements it
in ``tests/unit/test_quick3d_adapter.py`` — which is why this module imports no
Qt at all and every line of it runs in the GPU-less test tier.

What the sink guarantees:

- **Frame mapping exactly once.** A part's mesh becomes engine-frame bytes in
  ``core.scene3d.engine_buffers``; a record's transform becomes a Model pose in
  ``core.scene3d.engine_pose``; the sun and the ground are mapped here. What
  the host is handed is in the engine frame already; the host maps only what it
  is asked itself (a camera placement, a pick result), with the same
  ``core/scene3d/frame.py`` functions, and the QML converts nothing.
- **One teardown, and one owner.** The engine scene OWNS every Model; the sink
  holds handles as names. ``clear()`` — the tenth ``EngineSink`` method — asks
  the scene to drop everything (``EngineScene.clear``) and empties the sink's
  books whether or not that succeeds. It is legal at any time: inside a
  transaction, also one an engine error broke half way; twice in a row; and
  when the engine is gone (the host was closed, or Qt destroyed its window with
  the main window) — then there is nothing left to destroy and it simply
  forgets. ``SceneSync.reset()`` calls it — the recovery after a sink failure —
  and the next ``apply`` re-sends everything; ``attach`` points the emptied
  sink at a fresh engine scene.
- **One sink per engine scene.** A scene that already holds Models belongs to
  somebody else: the constructor and ``attach`` refuse it
  (``SinkProtocolError``). Two sinks on one scene would draw both sinks' items,
  and the first ``clear()`` would destroy the other one's Models.
- **One Model per mesh part, one geometry per Model lifetime.** ``add`` creates
  the Models, ``remove`` destroys them, ``replace_geometry`` destroys and
  creates. A geometry object is never handed to a second Model: the L0 spike
  measured a blank frame and 0/20 picks for that (``ogp-3d-renderer`` §2).
- **A move or a recolour uploads nothing.** ``update_transform`` re-poses,
  ``update_material`` re-tints (``materials.part_tint``); ``geometry_uploads``
  counts every buffer handed to the engine, and neither call changes it.
- **Errors are loud.** A protocol breach raises ``SinkProtocolError`` before the
  engine is touched; an engine error propagates (``SceneSync`` poisons itself).
- **The selection ring is one mesh in one Model that is never destroyed (L1.8).**
  ``set_selection`` maps the ring to the engine frame (``engine_buffers`` — the
  same single mapping as every mesh) and hands the bytes to
  ``EngineScene.set_selection_ring``; an empty selection hides the ring. No
  Model is created or destroyed by it, ``geometry_uploads`` does not move
  (``ring_uploads`` counts), and the scene's ``clear()`` hides the ring with
  everything else.

GUI thread only, like everything that touches the scene.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from open_garden_planner.core.scene3d import (
    EngineBuffers,
    EnginePose,
    GroundSpec,
    Material,
    MeshPart,
    Rgba,
    SinkItem,
    SinkProtocolError,
    SinkState,
    SunState,
    Transform,
    engine_buffers,
    engine_pose,
    scene_to_engine_points,
    scene_to_engine_vectors,
)
from open_garden_planner.core.scene3d.selection import EMPTY_SELECTION, Selection

from .materials import part_tint


@dataclass(frozen=True, slots=True)
class PartSpec:
    """Everything fixed for the lifetime of one engine Model."""

    item_id: str
    part_index: int        # index into the item's parts (a part without triangles has no Model)
    kind: str              # a ``core.scene3d.MATERIAL_KINDS`` member
    buffers: EngineBuffers
    casts_shadow: bool


@dataclass(frozen=True, slots=True)
class GroundPlacement:
    """The plan rectangle in the ENGINE frame: its centre and its extents in cm."""

    center: tuple[float, float, float]
    width_cm: float    # along engine x (East)
    depth_cm: float    # along engine z (North)


class EngineScene(Protocol):
    """What the sink needs from the engine — plain data in, an opaque handle out."""

    def create_part(self, spec: PartSpec, pose: EnginePose, tint_rgba: Rgba) -> object:
        """Create one Model with fresh geometry; return the handle that names it."""

    def destroy_part(self, handle: object) -> None:
        """Destroy the Model (and its geometry) for good. A no-op when the engine is gone."""

    def clear(self) -> None:
        """Destroy every Model, no sun, no plan ground, no selection ring (hidden — its
        one Model stays). A no-op when the engine is gone
        — it must not raise then: a sync whose engine died still has to be reset. A
        LIVE engine that cannot destroy a Model finishes the rest, keeps that Model
        in its own books and raises: the next ``clear()`` tries again."""

    def part_count(self) -> int:
        """How many Models the engine holds (raises when the engine is gone)."""

    def pose_part(self, handle: object, pose: EnginePose) -> None:
        """Move / turn the Model."""

    def tint_part(self, handle: object, tint_rgba: Rgba) -> None:
        """Set the Model's tint (sRGB, 8 bit)."""

    def set_sun(self, travel: tuple[float, float, float] | None) -> None:
        """The unit vector the sunlight travels along, engine frame — or None: no sun."""

    def set_ground(self, ground: GroundPlacement | None) -> None:
        """Size and place the plan rectangle — or None: no plan ground."""

    def request_frame(self) -> None:
        """A transaction closed: show the new state."""

    def set_selection_ring(self, ring: EngineBuffers | None) -> None:
        """Draw this mesh (engine frame) as the selection ring, in the ONE Model the
        scene keeps for it — or None: hide the ring. Creates and destroys no Model.
        ``clear()`` hides it with everything else."""


@dataclass(slots=True)
class _Held:
    parts: tuple[MeshPart, ...]
    transform: Transform
    material: Material
    handles: list[object | None]  # one per part; None = that part has nothing to draw


class Quick3DSink:
    """An ``EngineSink`` that drives an ``EngineScene`` (module docstring)."""

    def __init__(self, scene: EngineScene) -> None:
        _require_empty("Quick3DSink()", scene)
        self._scene = scene
        self._items: dict[str, _Held] = {}
        self._sun: SunState | None = None
        self._ground: GroundSpec | None = None
        self._open = False
        self._engine_unknown = False  # the last clear() failed: see clear() and begin()
        self.transactions = 0
        #: Vertex/index buffers handed to the engine so far. A move or a recolour
        #: must leave it unchanged — the instrument behind that gate.
        self.geometry_uploads = 0
        self._selection: Selection = EMPTY_SELECTION
        #: Ring meshes handed to the engine so far (L1.8) — counted apart from the
        #: Models' buffers: the ring follows a selected item that moves.
        self.ring_uploads = 0

    # ── what the sink holds (the same questions ``RecordingSink`` answers) ────

    @property
    def scene(self) -> EngineScene:
        return self._scene

    @property
    def in_transaction(self) -> bool:
        return self._open

    @property
    def sun(self) -> SunState | None:
        return self._sun

    @property
    def ground(self) -> GroundSpec | None:
        return self._ground

    def item_ids(self) -> tuple[str, ...]:
        return tuple(self._items)

    def item(self, item_id: str) -> SinkItem:
        held = self._items[item_id]
        return SinkItem(held.parts, held.transform, held.material)

    def state(self) -> SinkState:
        """Comparable with ``RecordingSink.state()``: equal means the two were told the
        same scene. (What the ENGINE holds is ``Quick3DHost.engine_parts()``.)"""
        return SinkState({item_id: self.item(item_id) for item_id in self._items},
                         self._sun, self._ground, self._selection)

    @property
    def selection(self) -> Selection:
        """The selection ring the engine was last handed (the empty one: none)."""
        return self._selection

    def part_count(self, item_id: str) -> int:
        """Engine Models the item has (parts without triangles have none)."""
        return sum(handle is not None for handle in self._items[item_id].handles)

    def clear(self) -> None:
        """Tear the engine scene down: no item, no sun, no ground, no transaction.

        The tenth ``EngineSink`` method. Legal at any time: inside an open
        ``begin``/``commit`` (it aborts the transaction — also one an engine
        error broke half way; a ``commit()`` after it is a protocol error),
        outside one, and on a sink that is empty already. ``SceneSync.reset()``
        calls it; the next ``apply`` re-sends items, sun and ground. Every Model
        is destroyed together with its geometry — also one a failed call left
        behind without a handle in these books: the scene owns them all — so the
        items added afterwards get fresh ones (the re-attach rule,
        ``ogp-3d-renderer`` §2).

        Exception-safe and idempotent: the books are emptied in a ``finally``. An
        engine that is gone raises nothing; a LIVE engine that fails to clear
        propagates its error (the sync stays poisoned) and still holds, in ITS
        books, the Models it could not destroy — so the next ``clear()`` asks it
        again, and it tries them again. Until one succeeds the sink refuses
        ``begin()``: its books are empty and the engine is not, and nothing may be
        built on that.
        """
        self._engine_unknown = True
        try:
            self._scene.clear()  # the ONE owner of the Models destroys them all (and hides the ring)
            self._engine_unknown = False
        finally:  # the books are empty whatever the engine said: a second clear() is clean
            self._items.clear()
            self._sun = None
            self._ground = None
            self._selection = EMPTY_SELECTION
            self._open = False

    def attach(self, scene: EngineScene) -> None:
        """Point an EMPTY sink at another, EMPTY engine scene — a fresh host after the
        old one died. ``SinkProtocolError`` while the sink still holds anything
        (``clear()`` first — ``SceneSync.reset()`` does), and for a scene that
        already holds Models (it has an owner; module docstring)."""
        if self._items or self._open or self._sun is not None or self._ground is not None:
            raise SinkProtocolError("attach(): the sink is not empty — clear() it first")
        _require_empty("attach()", scene)
        self._scene = scene
        self._engine_unknown = False

    # ── EngineSink ───────────────────────────────────────────────────────────

    def begin(self) -> None:
        if self._open:
            raise SinkProtocolError("begin(): a transaction is already open")
        if self._engine_unknown:
            raise SinkProtocolError(
                "begin(): the last clear() failed, so the engine still holds Models these "
                "books do not know — clear() again (SceneSync.reset() does), or attach() a "
                "fresh host")
        self._open = True

    def commit(self) -> None:
        self._require_open("commit")
        self._open = False
        self.transactions += 1
        self._scene.request_frame()

    def add(self, item_id: str, parts: Sequence[MeshPart], transform: Transform,
            material: Material) -> None:
        self._require_open("add")
        if item_id in self._items:
            raise SinkProtocolError(f"add(): item {item_id!r} is already in the sink")
        held = _Held(_checked(parts), transform, material, [])
        self._items[item_id] = held  # before the engine is touched: clear() can clean up
        self._create(item_id, held)

    def remove(self, item_id: str) -> None:
        held = self._require_known("remove", item_id)
        self._destroy(held)
        del self._items[item_id]

    def update_transform(self, item_id: str, transform: Transform) -> None:
        held = self._require_known("update_transform", item_id)
        held.transform = transform
        pose = engine_pose(transform)
        for handle in held.handles:
            if handle is not None:
                self._scene.pose_part(handle, pose)

    def update_material(self, item_id: str, material: Material) -> None:
        held = self._require_known("update_material", item_id)
        held.material = material
        for part, handle in zip(held.parts, held.handles, strict=True):
            if handle is not None and part.tinted:
                self._scene.tint_part(handle, part_tint(part, material))

    def replace_geometry(self, item_id: str, parts: Sequence[MeshPart]) -> None:
        held = self._require_known("replace_geometry", item_id)
        checked = _checked(parts)
        self._destroy(held)
        held.parts = checked
        self._create(item_id, held)

    def set_sun(self, sun: SunState) -> None:
        self._require_open("set_sun")
        self._sun = sun
        if not sun.is_up:  # no SUNLIGHT from below the horizon (a night look's moon is the host's)
            self._scene.set_sun(None)
            return
        travel = scene_to_engine_vectors(np.array(sun.light_travel_scene, dtype=np.float64))
        self._scene.set_sun((float(travel[0]), float(travel[1]), float(travel[2])))

    def set_ground(self, ground: GroundSpec) -> None:
        self._require_open("set_ground")
        self._ground = ground
        center = scene_to_engine_points(
            np.array([ground.width_cm / 2.0, ground.depth_cm / 2.0, 0.0], dtype=np.float64))
        self._scene.set_ground(GroundPlacement(
            center=(float(center[0]), float(center[1]), float(center[2])),
            width_cm=ground.width_cm, depth_cm=ground.depth_cm))

    def set_selection(self, selection: Selection) -> None:
        self._require_open("set_selection")
        if not isinstance(selection, Selection):
            raise SinkProtocolError(f"set_selection() takes a Selection, got {selection!r:.80}")
        self._selection = selection
        buffers = engine_buffers(selection.ring) if selection else None
        if buffers is None or buffers.is_empty:
            self._scene.set_selection_ring(None)
            return
        self._scene.set_selection_ring(buffers)
        self.ring_uploads += 1

    # ── internals ────────────────────────────────────────────────────────────

    def _create(self, item_id: str, held: _Held) -> None:
        pose = engine_pose(held.transform)
        for index, part in enumerate(held.parts):
            buffers = engine_buffers(part.mesh)
            if buffers.is_empty:
                held.handles.append(None)
                continue
            spec = PartSpec(item_id, index, part.material_kind, buffers, part.casts_shadow)
            held.handles.append(self._scene.create_part(spec, pose, part_tint(part, held.material)))
            self.geometry_uploads += 1

    def _destroy(self, held: _Held) -> None:
        handles, held.handles = held.handles, []
        for handle in handles:
            if handle is not None:
                self._scene.destroy_part(handle)

    def _require_open(self, op: str) -> None:
        if not self._open:
            raise SinkProtocolError(f"{op}() called outside begin()/commit()")

    def _require_known(self, op: str, item_id: str) -> _Held:
        self._require_open(op)
        held = self._items.get(item_id)
        if held is None:
            raise SinkProtocolError(f"{op}(): unknown item {item_id!r}")
        return held


def _require_empty(call: str, scene: EngineScene) -> None:
    held = scene.part_count()
    if held:
        raise SinkProtocolError(
            f"{call}: the engine scene already holds {held} Model(s) — it belongs to another "
            "sink. One sink per scene: use a fresh host")


def _checked(parts: Sequence[MeshPart]) -> tuple[MeshPart, ...]:
    result = tuple(parts)
    if not all(isinstance(part, MeshPart) for part in result):
        raise SinkProtocolError(f"parts must be MeshPart objects, got {result!r:.120}")
    return result
