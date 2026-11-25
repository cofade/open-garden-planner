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
- **One Model per mesh part and surface, one geometry OBJECT per Model lifetime.**
  ``add`` creates the Models, ``remove`` destroys them, ``replace_geometry`` keeps
  every Model a new piece of the same ``_reuse_key`` takes and loads the new buffers
  into that Model's own geometry object (``EngineScene.reload_part``, #531) — Qt
  Quick 3D keeps 15-20 kB of every Model it destroys, for good. A part made of several
  surfaces (``MeshPart.surface_runs``, #803) is drawn as one Model per surface
  (``mesh.surface_pieces``): a Model has one material. A geometry object is never
  handed to a second Model, nor a second geometry object to a live Model: the L0 spike
  measured a blank frame and 0/20 picks for the first, and ADR-069 withdrew the second
  (it drew nothing); loading into the object the Model already has draws (render tier:
  ``test_replace_geometry_changes_the_silhouette``, a forged tree regrown in place).
- **A move or a recolour uploads nothing.** ``update_transform`` re-poses,
  ``update_material`` re-colours (``materials.part_tint`` — the one rule a fill part
  changes: its picture carries the colour); ``geometry_uploads`` counts every buffer
  handed to the engine, and neither call changes it.
- **A fill part shows the item's own fill (#628 follow-up).** A part with
  ``MeshPart.fill_texture`` gets ``EngineScene.set_part_fill`` with the item's pattern
  and tint; the picture is one per (pattern, colour), shared, and the sink refcounts
  it (``release_fill`` with the last Model that shows it). A recolour swaps the
  picture and uploads no geometry.
- **A plant sways as a whole (#800).** Every part of an item with leaves gets the same
  ``PartSpec.sway`` (``core.scene3d.wind.sway_frame``: its height and reach from its own
  meshes, its phase from its id), so its leaves, wood and fruit move by one function;
  any other item gets none. A move re-poses and recomputes nothing.
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

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from open_garden_planner.core.scene3d import (
    EngineBuffers,
    EnginePose,
    GroundSpec,
    GroundTile,
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
    model_reuse_key,
    pattern_texture_name,
    scene_to_engine_points,
    scene_to_engine_vectors,
)
from open_garden_planner.core.scene3d.mesh import surface_pieces
from open_garden_planner.core.scene3d.selection import EMPTY_SELECTION, Selection
from open_garden_planner.core.scene3d.wind import NO_SWAY, SWAY_KINDS, sway_frame

from .materials import part_tint


@dataclass(frozen=True, slots=True)
class PartSpec:
    """Everything fixed for the lifetime of one engine Model."""

    item_id: str
    part_index: int        # index into the item's parts (a part without triangles has no Model)
    kind: str              # a ``core.scene3d.MATERIAL_KINDS`` member
    buffers: EngineBuffers
    casts_shadow: bool
    name: str = ""
    #: ``MeshPart.ground_detail`` (L4): relief on painted ground — never picked.
    ground_detail: bool = False
    #: ``MeshPart.surface`` (#803): what the part is made of — a key of
    #: ``core.scene3d.materials.SURFACES``; empty is ``DEFAULT_SURFACE``.
    surface: str = ""
    #: #800: the item's ``core.scene3d.wind.SwayFrame`` (height cm, canopy radius cm,
    #: phase 0..1) — the same for every part of one item; all 0: the part does not sway.
    sway: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class TilePlacement:
    """One baked ground tile (``core.scene3d.GroundTile``) in the ENGINE frame: where
    its quad lies, and its picture (L1.5)."""

    key: tuple[int, int]
    center: tuple[float, float, float]
    width_cm: float    # along engine x (East)
    depth_cm: float    # along engine z (North)
    width_px: int
    height_px: int
    #: RGBA8, row 0 on the NORTH edge — the very ``bytes`` object of the tile: an
    #: engine scene tells an unchanged tile by it and uploads nothing.
    pixels: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class GroundPlacement:
    """The plan rectangle in the ENGINE frame: its centre and its extents in cm —
    and the COMPLETE set of its baked tiles (none: bare ground)."""

    center: tuple[float, float, float]
    width_cm: float    # along engine x (East)
    depth_cm: float    # along engine z (North)
    tiles: tuple[TilePlacement, ...] = ()


class EngineScene(Protocol):
    """What the sink needs from the engine — plain data in, an opaque handle out."""

    def create_part(self, spec: PartSpec, pose: EnginePose, tint_rgba: Rgba) -> object:
        """Create one Model with fresh geometry; return the handle that names it."""

    def reload_part(self, handle: object, spec: PartSpec) -> None:
        """Load ``spec``'s buffers into the LIVE Model's own geometry object and take its
        index, name, shadow flag and sway (#531). Only for a Model of the same
        ``_reuse_key``: the scene checks kind and surface, and the CALLER guarantees ground
        detail and fill picture (what a Model is fixed to for life). The pose stays; the
        caller re-tints and re-fills."""

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

    def set_part_fill(self, handle: object, pattern: str | None, tint_rgba: Rgba) -> None:
        """Show the item's own fill on this Model (``MeshPart.fill_texture``):
        ``pattern``'s texture tinted with ``tint_rgba``, or that colour alone for
        ``None``/SOLID. The picture is cached per (pattern, colour); a recolour or
        a pattern change is this call, never a rebuild."""

    def release_fill(self, pattern: str | None, tint_rgba: Rgba) -> None:
        """No Model shows that fill any more: let its picture go (a no-op when the
        engine is gone or the picture was never made)."""

    def set_sun(self, travel: tuple[float, float, float] | None) -> None:
        """The unit vector the sunlight travels along, engine frame — or None: no sun."""

    def set_ground(self, ground: GroundPlacement | None) -> None:
        """Size and place the plan rectangle and show its tiles — or None: no plan
        ground. ``ground.tiles`` is the complete set: a tile the scene already
        shows (the same ``pixels``) is left alone, another is uploaded, one that is
        no longer named is dropped."""

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
    #: One per engine Model: (the piece of a part it draws, its handle). A part of one
    #: surface is one piece, a part of several one piece per surface (#803,
    #: ``mesh.surface_pieces``); a piece without triangles has no Model and no entry.
    handles: list[tuple[MeshPart, object]]


#: A fill picture the engine holds for a fill_texture part: its pattern (None for
#: SOLID) and the item's tint. The SAME key names the picture on both sides of
#: ``EngineScene.set_part_fill`` / ``release_fill``.
FillKey = tuple[str | None, Rgba]


def _fill_key(part: MeshPart, material: Material) -> FillKey | None:
    """The picture *part* shows for an item with *material*, or None (not a fill part)."""
    if not part.fill_texture:
        return None
    return (pattern_texture_name(material.pattern), material.tint_rgba)


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
        #: One entry per fill picture the engine holds (``_fill_key`` -> Models that
        #: show it): a picture is released with its last user, so recolouring a raised
        #: lawn does not leave a texture per colour behind.
        self._fills: dict[FillKey, int] = {}
        #: #531: Models that took new geometry in place (``replace_geometry``), and
        #: Models the sink destroyed one by one (``remove``, ``replace_geometry``'s
        #: leftovers; a ``clear()`` is counted by its caller). Qt Quick 3D keeps 15-20 kB
        #: of every destroyed Model for good, and its graphics state until a cache
        #: release: the instruments behind "a regrowth destroys no Model".
        self.models_reused = 0
        self.models_destroyed = 0
        #: Items that lost at least one Model: every ``remove``, every item a ``clear()``
        #: dropped, and a ``replace_geometry`` that destroyed one (one that only reloaded
        #: does not). What the workspace counts towards a cache release (ADR-060).
        self.items_retired = 0

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

    def fill_pictures(self) -> tuple[FillKey, ...]:
        """The fill pictures the engine holds right now — one per (pattern, tint) that
        at least one Model shows (#628 follow-up). A recolour replaces one; a remove
        of the last user drops one. The instrument behind "no picture per colour left
        behind"."""
        return tuple(self._fills)

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
        return len(self._items[item_id].handles)

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
        self.items_retired += sum(1 for held in self._items.values() if held.handles)
        try:
            self._scene.clear()  # the ONE owner of the Models destroys them all (and hides the ring)
            self._engine_unknown = False
        finally:  # the books are empty whatever the engine said: a second clear() is clean
            self._items.clear()
            self._sun = None
            self._ground = None
            self._selection = EMPTY_SELECTION
            self._open = False
            self._fills.clear()  # the engine's clear() let every picture go

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
        keys = self._fill_keys(held)
        if held.handles:
            self.items_retired += 1
        self._destroy(held)  # the Models first: no live Model may point at a released picture
        for key in keys:
            self._release(key)
        del self._items[item_id]

    def update_transform(self, item_id: str, transform: Transform) -> None:
        held = self._require_known("update_transform", item_id)
        held.transform = transform
        pose = engine_pose(transform)
        for _piece, handle in held.handles:
            self._scene.pose_part(handle, pose)

    def update_material(self, item_id: str, material: Material) -> None:
        held = self._require_known("update_material", item_id)
        previous = held.material
        held.material = material
        released: list[FillKey] = []
        for part, handle in held.handles:
            if part.tinted:
                self._scene.tint_part(handle, part_tint(part, material))
            if part.fill_texture:
                old_key, new_key = _fill_key(part, previous), _fill_key(part, material)
                if old_key != new_key:
                    if new_key is None:  # _fill_key always answers for a fill part
                        raise SinkProtocolError(
                            f"update_material(): fill part {part.name!r} has no fill key")
                    # in the books BEFORE a Model can show it; a failed set poisons the
                    # sync, whose reset() clears these books with the engine
                    self._acquire(new_key)
                    self._scene.set_part_fill(handle, *new_key)
                    if old_key is not None:
                        released.append(old_key)
        for key in released:  # after EVERY Model shows its new picture, not between two of them
            self._release(key)

    def replace_geometry(self, item_id: str, parts: Sequence[MeshPart]) -> None:
        """The item's new meshes, in the Models it has where they fit (#531).

        A new piece takes the first old Model of the same ``_reuse_key`` (kind, surface,
        ground detail, fill picture): the engine loads the new buffers into that Model's own geometry
        object (``EngineScene.reload_part``). Old Models nothing takes are destroyed
        first; pieces nothing old fits get new Models. Qt Quick 3D keeps 15-20 kB of
        every Model it destroys, so a regrowth that keeps its Models leaves nothing."""
        held = self._require_known("replace_geometry", item_id)
        checked = _checked(parts)
        old_keys = self._fill_keys(held)
        old_handles, held.handles = held.handles, []
        held.parts = checked
        pieces = list(self._pieces(item_id, held))
        spare: dict[tuple[str, str, bool, bool], list[object]] = {}
        for old_part, handle in old_handles:
            spare.setdefault(_reuse_key(old_part), []).append(handle)
        reuse: list[object | None] = []
        for part, _spec in pieces:
            free = spare.get(_reuse_key(part))
            reuse.append(free.pop(0) if free else None)
        # the Models nothing takes go first (a failure below is cleaned up by the
        # sync's reset: the scene owns every Model, clear() destroys them all)
        leftovers = [handle for handles in spare.values() for handle in handles]
        if leftovers:
            self.items_retired += 1
        for handle in leftovers:
            self._scene.destroy_part(handle)
            self.models_destroyed += 1
        pose = engine_pose(held.transform)
        for (part, spec), handle in zip(pieces, reuse, strict=True):
            tint = part_tint(part, held.material)
            if handle is None:
                handle = self._scene.create_part(spec, pose, tint)
            else:
                self._scene.reload_part(handle, spec)
                self._scene.tint_part(handle, tint)
                self.models_reused += 1
            held.handles.append((part, handle))
            self.geometry_uploads += 1
            key = _fill_key(part, held.material)
            if key is not None:
                self._acquire(key)  # in the books before a Model shows it
                self._scene.set_part_fill(handle, *key)
        for key in old_keys:  # after every Model shows its new picture
            self._release(key)

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
            width_cm=ground.width_cm, depth_cm=ground.depth_cm,
            tiles=tuple(_tile_placement(tile) for tile in ground.tiles)))

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

    def _pieces(self, item_id: str, held: _Held) -> Iterator[tuple[MeshPart, PartSpec]]:
        """Every engine Model *held*'s parts make: the piece and what is fixed for it —
        the ONE place a ``PartSpec`` is made (``_create`` and ``replace_geometry``)."""
        # #800: an item with leaves sways as a whole - every part takes the same frame
        frame = sway_frame(item_id, held.parts)
        for index, whole in enumerate(held.parts):
            sway = (frame.as_tuple() if frame.sways and whole.material_kind in SWAY_KINDS
                    else NO_SWAY.as_tuple())
            for part in surface_pieces(whole):  # one Model per surface (#803)
                buffers = engine_buffers(part.mesh)
                if buffers.is_empty:
                    continue
                yield part, PartSpec(item_id, index, part.material_kind, buffers,
                                     part.casts_shadow, part.name, part.ground_detail,
                                     surface=part.surface, sway=sway)

    def _create(self, item_id: str, held: _Held) -> None:
        pose = engine_pose(held.transform)
        for part, spec in self._pieces(item_id, held):
            handle = self._scene.create_part(spec, pose, part_tint(part, held.material))
            held.handles.append((part, handle))  # before the fill: clear() can destroy it
            self.geometry_uploads += 1
            key = _fill_key(part, held.material)
            if key is not None:
                self._scene.set_part_fill(handle, *key)
                self._acquire(key)

    def _fill_keys(self, held: _Held) -> list[FillKey]:
        """The fill pictures *held*'s Models show, in part order (released after the
        Models that show them are gone — a picture freed under a live Model is white)."""
        keys: list[FillKey] = []
        for part, _handle in held.handles:
            key = _fill_key(part, held.material)
            if key is not None:
                keys.append(key)
        return keys

    def _acquire(self, key: FillKey) -> None:
        self._fills[key] = self._fills.get(key, 0) + 1

    def _release(self, key: FillKey) -> None:
        count = self._fills.get(key, 0) - 1
        if count > 0:
            self._fills[key] = count
            return
        self._fills.pop(key, None)
        self._scene.release_fill(*key)

    def _destroy(self, held: _Held) -> None:
        handles, held.handles = held.handles, []
        for _piece, handle in handles:
            self._scene.destroy_part(handle)
            self.models_destroyed += 1

    def _require_open(self, op: str) -> None:
        if not self._open:
            raise SinkProtocolError(f"{op}() called outside begin()/commit()")

    def _require_known(self, op: str, item_id: str) -> _Held:
        self._require_open(op)
        held = self._items.get(item_id)
        if held is None:
            raise SinkProtocolError(f"{op}(): unknown item {item_id!r}")
        return held


def _reuse_key(part: MeshPart) -> tuple[str, str, bool, bool]:
    """What a Model is fixed to for life (#531): ``core.scene3d.model_reuse_key``.

    Kept as this module's private name because every call site here reads like the
    sink's own bookkeeping; the rule itself lives in the core so the recording
    double answers the same question (#1014)."""
    return model_reuse_key(part)


def _tile_placement(tile: GroundTile) -> TilePlacement:
    """A ground tile in the engine frame — the ONE place its rectangle is mapped."""
    center = scene_to_engine_points(np.array(
        [tile.east_cm + tile.width_cm / 2.0, tile.north_cm + tile.depth_cm / 2.0, 0.0],
        dtype=np.float64))
    return TilePlacement(
        key=tile.key, center=(float(center[0]), float(center[1]), float(center[2])),
        width_cm=tile.width_cm, depth_cm=tile.depth_cm,
        width_px=tile.width_px, height_px=tile.height_px, pixels=tile.pixels)


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
