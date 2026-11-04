"""``Quick3DSink`` against a recording engine boundary (Phase 17 L1.2, #385).

The sink is pure bookkeeping: it enforces the ``EngineSink`` protocol, maps
frames once and tells an ``EngineScene`` what to create, pose, tint and
destroy. ``Quick3DHost`` implements that boundary with Qt Quick 3D (render
tier); here a list-backed double implements it, so every line of the adapter
runs in the default (GPU-less) run — and nothing in this file imports the
engine.

What the double cannot show — that a created part appears on screen where it
should — is the render tier's job (``tests/integration/test_quick3d_render.py``).
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest

from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    EngineBuffers,
    EnginePose,
    EngineSink,
    GroundSpec,
    Material,
    Mesh,
    MeshPart,
    Params,
    Record,
    RecordingSink,
    SceneSync,
    SinkProtocolError,
    SunState,
    SyncStateError,
    Transform,
    engine_buffers,
    engine_pose,
    prism_mesh,
)
from open_garden_planner.core.shadow_geometry import MIN_SUN_ELEVATION_DEG
from open_garden_planner.ui.view3d.quick3d.adapter import (
    GroundPlacement,
    PartSpec,
    Quick3DSink,
)
from open_garden_planner.ui.view3d.quick3d.materials import WHITE, part_tint

SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))
RED = Material("SHED", fill_rgba=(200, 30, 30, 255))
BLUE = Material("SHED", fill_rgba=(20, 40, 220, 128))


@dataclass
class FakePart:
    spec: PartSpec
    pose: EnginePose
    tint: tuple[int, int, int, int]
    alive: bool = True
    fill: tuple[str | None, tuple[int, int, int, int]] | None = None


class EngineGone(RuntimeError):
    """What a closed host raises (``HostStateError`` there) — for every call but the
    releases."""


@dataclass
class FakeScene:
    """A list-backed ``EngineScene``: records every call, holds what was created.

    It OWNS its parts, like the host: ``clear()`` destroys all of them. ``dead=True``
    makes it behave like a closed host — the releases (``destroy_part``, ``clear``)
    do nothing, every other call raises.
    """

    calls: list[tuple[Any, ...]] = field(default_factory=list)
    parts: list[FakePart] = field(default_factory=list)
    sun: Any = "unset"
    ground: Any = "unset"
    fail_on_create: int | None = None  # raise on the n-th create_part (1-based)
    fail_on_clear: bool = False        # a LIVE engine that cannot clear
    fail_once: str | None = None       # the next call of that name raises (then it works again)
    dead: bool = False                 # the engine is gone (closed host, destroyed window)
    created: int = 0

    def _alive(self, call: str = "") -> None:
        if self.dead:
            raise EngineGone("the engine is gone")
        if call and self.fail_once == call:
            self.fail_once = None
            raise RuntimeError(f"engine failed in {call}")

    def clear(self) -> None:
        self.calls.append(("clear",))
        if self.dead:
            return
        if self.fail_on_clear:
            raise RuntimeError("engine could not clear")
        for part in self.parts:
            part.alive = False
        self.parts.clear()
        self.sun = None
        self.ground = None
        self.ring = None  # hidden with everything else (the host's clear() does)

    def part_count(self) -> int:
        self._alive()  # asked of a dead engine it raises, like the host
        return len(self.parts)

    def create_part(self, spec: PartSpec, pose: EnginePose,
                    tint_rgba: tuple[int, int, int, int]) -> FakePart:
        self._alive("create_part")
        self.created += 1
        if self.fail_on_create == self.created:
            raise RuntimeError("engine refused the part")
        part = FakePart(spec, pose, tint_rgba)
        self.parts.append(part)
        self.calls.append(("create", spec.item_id, spec.kind))
        return part

    def destroy_part(self, handle: object) -> None:
        if self.dead:
            return
        assert isinstance(handle, FakePart) and handle.alive, "destroyed twice or unknown"
        handle.alive = False
        self.parts.remove(handle)
        self.calls.append(("destroy", handle.spec.item_id))

    def pose_part(self, handle: object, pose: EnginePose) -> None:
        self._alive("pose_part")
        assert isinstance(handle, FakePart) and handle.alive
        handle.pose = pose
        self.calls.append(("pose", handle.spec.item_id))

    def tint_part(self, handle: object, tint_rgba: tuple[int, int, int, int]) -> None:
        self._alive("tint_part")
        assert isinstance(handle, FakePart) and handle.alive
        handle.tint = tint_rgba
        self.calls.append(("tint", handle.spec.item_id))

    def set_part_fill(self, handle: object, pattern: str | None,
                      tint_rgba: tuple[int, int, int, int]) -> None:
        self._alive("set_part_fill")
        assert isinstance(handle, FakePart) and handle.alive
        handle.fill = (pattern, tint_rgba)
        self.calls.append(("fill", handle.spec.item_id, pattern))

    def release_fill(self, pattern: str | None, tint_rgba: tuple[int, int, int, int]) -> None:
        if self.dead:  # a release, like destroy_part: nothing to do on a gone engine
            return
        self._alive("release_fill")
        self.calls.append(("release_fill", pattern, tint_rgba))

    def set_sun(self, travel: tuple[float, float, float] | None) -> None:
        self._alive("set_sun")
        self.sun = travel
        self.calls.append(("sun",))

    def set_ground(self, ground: GroundPlacement | None) -> None:
        self._alive("set_ground")
        self.ground = ground
        self.calls.append(("ground",))

    def request_frame(self) -> None:
        self._alive("request_frame")
        self.calls.append(("frame",))

    #: The selection ring's bytes (L1.8) — None: hidden. Not a part: the scene keeps
    #: ONE ring Model, and ``clear()`` of the sink hides it.
    ring: Any = None

    def set_selection_ring(self, ring: Any) -> None:
        self._alive("set_selection_ring")
        self.ring = ring
        self.calls.append(("ring", None if ring is None else ring.vertex_count))

    def of(self, item_id: str) -> list[FakePart]:
        return [p for p in self.parts if p.spec.item_id == item_id]


def _prism(height: float = 100.0, *, tinted: bool = True, kind: str = "vc",
           casts: bool = True, name: str = "prism", fill: bool = False) -> MeshPart:
    return MeshPart(prism_mesh([SQUARE], height), kind, casts_shadow=casts, tinted=tinted,
                    name=name, fill_texture=fill)


@pytest.fixture()
def rig() -> tuple[Quick3DSink, FakeScene]:
    scene = FakeScene()
    return Quick3DSink(scene), scene


class TestProtocol:
    def test_it_is_an_engine_sink(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        assert isinstance(rig[0], EngineSink)

    @pytest.mark.parametrize("call", [
        lambda s: s.commit(),
        lambda s: s.add("a", (), Transform(), RED),
        lambda s: s.remove("a"),
        lambda s: s.update_transform("a", Transform()),
        lambda s: s.update_material("a", RED),
        lambda s: s.replace_geometry("a", ()),
        lambda s: s.set_sun(SunState(45.0, 180.0)),
        lambda s: s.set_ground(GroundSpec(100.0, 100.0)),
    ], ids=["commit", "add", "remove", "update_transform", "update_material",
            "replace_geometry", "set_sun", "set_ground"])
    def test_every_call_needs_an_open_transaction(self, rig: tuple[Quick3DSink, FakeScene],
                                                  call: Any) -> None:
        sink, scene = rig
        with pytest.raises(SinkProtocolError, match="outside begin"):
            call(sink)
        assert scene.calls == []

    def test_begin_does_not_nest(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, _ = rig
        sink.begin()
        with pytest.raises(SinkProtocolError, match="already open"):
            sink.begin()

    def test_add_refuses_a_known_id_and_the_others_an_unknown_one(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("a", (_prism(),), Transform(), RED)
        before = list(scene.calls)
        with pytest.raises(SinkProtocolError, match="already in the sink"):
            sink.add("a", (), Transform(), RED)
        for call in (lambda: sink.remove("b"), lambda: sink.update_transform("b", Transform()),
                     lambda: sink.update_material("b", RED),
                     lambda: sink.replace_geometry("b", ())):
            with pytest.raises(SinkProtocolError, match="unknown item 'b'"):
                call()
        assert scene.calls == before  # a refused call reaches the engine with nothing

    def test_parts_must_be_mesh_parts(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        with pytest.raises(SinkProtocolError, match="MeshPart"):
            sink.add("a", (prism_mesh([SQUARE], 10.0),), Transform(), RED)  # type: ignore[arg-type]
        assert scene.parts == [] and sink.item_ids() == ()

    def test_commit_asks_for_one_frame(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        assert scene.calls == []  # opening a transaction touches nothing
        sink.commit()
        assert scene.calls == [("frame",)] and sink.transactions == 1 and not sink.in_transaction


class TestAdd:
    def test_one_engine_part_per_mesh_part_with_the_mapped_bytes(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        walls, roof = _prism(250.0, name="walls"), _prism(80.0, kind="roof", name="roof",
                                                          tinted=False)
        transform = Transform(east_cm=300.0, north_cm=120.0, rotation_deg=17.0, base_cm=40.0)
        sink.begin()
        sink.add("house", (walls, roof), transform, RED)
        sink.commit()
        first, second = scene.of("house")
        assert (first.spec.kind, second.spec.kind) == ("vc", "roof")
        assert (first.spec.part_index, second.spec.part_index) == (0, 1)
        assert first.spec.buffers == engine_buffers(walls.mesh)   # the ONE frame mapping
        assert second.spec.buffers == engine_buffers(roof.mesh)
        assert first.spec.casts_shadow and second.spec.casts_shadow
        # the pose is frame.engine_pose: (E, base, −N), yaw = +rotation
        assert first.pose == second.pose == EnginePose((300.0, 40.0, -120.0), 17.0)
        assert sink.geometry_uploads == 2

    def test_a_tinted_part_gets_the_items_tint_an_untinted_one_white(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("a", (_prism(tinted=True), _prism(tinted=False)), Transform(), BLUE)
        tinted, plain = scene.of("a")
        assert tinted.tint == (20, 40, 220, 255)  # Material.tint_rgba: alpha forced opaque
        assert plain.tint == WHITE == (255, 255, 255, 255)

    def test_shadow_flag_and_kind_are_passed_through(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("pond", (_prism(2.0, kind="water", casts=False),), Transform(), RED)
        (part,) = scene.of("pond")
        assert part.spec.kind == "water" and part.spec.casts_shadow is False

    def test_an_item_without_parts_is_still_an_item(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("lawn", (), Transform(east_cm=5.0), RED)
        assert sink.item_ids() == ("lawn",) and scene.parts == []
        sink.update_transform("lawn", Transform(east_cm=6.0))   # addressable, nothing to pose
        sink.update_material("lawn", BLUE)
        assert scene.calls == [] and sink.item("lawn").transform.east_cm == 6.0

    def test_a_part_with_nothing_to_draw_creates_no_model(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        empty = MeshPart(Mesh.empty(), "vc", tinted=True)
        sink.begin()
        sink.add("a", (empty, _prism()), Transform(), RED)
        assert len(scene.of("a")) == 1 and scene.of("a")[0].spec.part_index == 1
        assert sink.geometry_uploads == 1
        assert len(sink.item("a").parts) == 2  # the sink still holds both parts
        sink.update_transform("a", Transform(east_cm=1.0))
        sink.update_material("a", BLUE)
        sink.remove("a")
        assert scene.parts == []


class TestUpdates:
    def test_update_transform_reposes_every_part_and_uploads_nothing(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("a", (_prism(), _prism(30.0)), Transform(), RED)
        uploads, parts = sink.geometry_uploads, list(scene.of("a"))
        scene.calls.clear()
        moved = Transform(east_cm=10.0, north_cm=-20.0, rotation_deg=90.0, base_cm=3.0)
        sink.update_transform("a", moved)
        assert scene.calls == [("pose", "a"), ("pose", "a")]
        assert all(p.pose == EnginePose((10.0, 3.0, 20.0), 90.0) for p in scene.of("a"))
        assert scene.of("a") == parts and sink.geometry_uploads == uploads  # same Models
        assert sink.item("a").transform == moved

    def test_update_material_retints_tinted_parts_only_and_uploads_nothing(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("a", (_prism(tinted=True), _prism(tinted=False)), Transform(), RED)
        uploads = sink.geometry_uploads
        scene.calls.clear()
        sink.update_material("a", BLUE)
        assert scene.calls == [("tint", "a")]  # ONE call: the untinted part is left alone
        tinted, plain = scene.of("a")
        assert tinted.tint == (20, 40, 220, 255) and plain.tint == WHITE
        assert sink.geometry_uploads == uploads
        assert sink.item("a").material == BLUE

    def test_replace_geometry_swaps_the_models_and_keeps_pose_and_tint(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        transform = Transform(east_cm=7.0, north_cm=8.0, rotation_deg=45.0)
        sink.begin()
        sink.add("a", (_prism(100.0),), transform, RED)
        (old,) = scene.of("a")
        taller = (_prism(300.0), _prism(20.0, kind="roof"))
        sink.replace_geometry("a", taller)
        new = scene.of("a")
        assert not old.alive and len(new) == 2 and old not in new  # fresh Models, never a reuse
        assert new[0].spec.buffers == engine_buffers(taller[0].mesh)
        assert all(p.pose == EnginePose((7.0, 0.0, -8.0), 45.0) for p in new)
        assert new[0].tint == (200, 30, 30, 255)
        assert sink.item("a").parts == taller and sink.geometry_uploads == 3

    def test_remove_destroys_every_part(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("a", (_prism(), _prism(5.0)), Transform(), RED)
        sink.add("b", (_prism(),), Transform(), RED)
        sink.remove("a")
        assert sink.item_ids() == ("b",) and [p.spec.item_id for p in scene.parts] == ["b"]

    def test_an_item_removed_and_added_again_gets_fresh_parts(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        """The geometry rule (``ogp-3d-renderer`` §2): one geometry per Model lifetime —
        a re-add never hands the engine a buffer object it saw before."""
        sink, scene = rig
        part = _prism()
        sink.begin()
        sink.add("a", (part,), Transform(), RED)
        (first,) = scene.of("a")
        sink.remove("a")
        sink.add("a", (part,), Transform(), RED)
        (second,) = scene.of("a")
        assert second is not first and not first.alive and second.alive
        assert second.spec.buffers == first.spec.buffers  # equal bytes, a new upload
        assert sink.geometry_uploads == 2


class TestTheItemsOwnFill:
    """``MeshPart.fill_texture`` (#628 follow-up): the raised object keeps its texture.

    The sink hands the Model the item's picture — its fill pattern tinted with the
    fill colour, or that colour alone for SOLID — and refcounts the picture, so a
    recolour or a plan edit does not leave one behind.
    """

    GRASS = Material("LAWN", fill_rgba=(90, 160, 60, 255), pattern="GRASS")
    SOIL = Material("GARDEN_BED", fill_rgba=(120, 80, 40, 255), pattern="SOIL")
    SOLID = Material("TERRACE_PATIO", fill_rgba=(150, 140, 130, 255), pattern="SOLID")

    def test_a_fill_part_gets_the_items_picture_and_no_tint(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("lawn", (_prism(fill=True, tinted=False),), Transform(), self.GRASS)
        (part,) = scene.of("lawn")
        assert part.fill == ("GRASS", (90, 160, 60, 255))
        assert part.tint == WHITE, "the picture carries the colour; nothing is tinted on top"
        assert sink.fill_pictures() == (("GRASS", (90, 160, 60, 255)),)

    def test_solid_fill_has_no_picture_and_the_flat_colour(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        """A raised generic shape with a SOLID fill: no texture exists, so the host
        paints the fill colour — the same flat look the 2D canvas gives it."""
        sink, scene = rig
        sink.begin()
        sink.add("terrace", (_prism(fill=True, tinted=False),), Transform(), self.SOLID)
        (part,) = scene.of("terrace")
        assert part.fill == (None, (150, 140, 130, 255))

    def test_a_recolour_swaps_the_picture_and_uploads_no_geometry(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("bed", (_prism(fill=True, tinted=False),), Transform(), self.SOIL)
        uploads, models = sink.geometry_uploads, list(scene.of("bed"))
        scene.calls.clear()
        sink.update_material("bed", self.GRASS)
        assert scene.of("bed") == models and sink.geometry_uploads == uploads
        assert scene.calls == [
            ("fill", "bed", "GRASS"),
            ("release_fill", "SOIL", (120, 80, 40, 255)),
        ]
        assert sink.fill_pictures() == (("GRASS", (90, 160, 60, 255)),)

    def test_one_picture_is_shared_and_released_with_its_last_user(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        """Two lawns of one colour are one picture; the first removal frees nothing."""
        sink, scene = rig
        sink.begin()
        sink.add("a", (_prism(fill=True, tinted=False),), Transform(), self.GRASS)
        sink.add("b", (_prism(fill=True, tinted=False),), Transform(), self.GRASS)
        assert sink.fill_pictures() == (("GRASS", (90, 160, 60, 255)),)
        scene.calls.clear()
        sink.remove("a")
        assert not [call for call in scene.calls if call[0] == "release_fill"]
        sink.remove("b")
        assert [call for call in scene.calls if call[0] == "release_fill"] == [
            ("release_fill", "GRASS", (90, 160, 60, 255)),
        ]
        assert sink.fill_pictures() == ()

    def test_a_clear_frees_every_picture_without_asking_one_by_one(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        """The host's clear() drops them all; the sink's books say so."""
        sink, scene = rig
        sink.begin()
        sink.add("a", (_prism(fill=True, tinted=False),), Transform(), self.GRASS)
        sink.commit()
        sink.clear()
        assert sink.fill_pictures() == () and scene.parts == []


class TestSunAndGround:
    def test_the_light_travels_away_from_the_sun_in_the_engine_frame(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sun = SunState(elevation_deg=35.0, azimuth_deg=225.0)  # in the south-west
        sink.begin()
        sink.set_sun(sun)
        east, north, up = sun.light_travel_scene
        assert scene.sun == pytest.approx((east, up, -north), abs=1e-12)
        assert scene.sun[0] > 0 and scene.sun[1] < 0 and scene.sun[2] < 0  # to NE, downwards
        assert math.hypot(*scene.sun) == pytest.approx(1.0, abs=1e-12)
        assert sink.sun == sun

    @pytest.mark.parametrize("elevation", [0.49, 0.0, -6.0, -90.0])
    def test_a_sun_that_is_down_switches_the_light_off(
            self, rig: tuple[Quick3DSink, FakeScene], elevation: float) -> None:
        """No light from below: the night rig is L1.4; until then, night is dark. "Down"
        is ``SunState.is_up`` — the 2D shadow overlay's threshold, not a second one."""
        sink, scene = rig
        sink.begin()
        sink.set_sun(SunState(elevation, 10.0))
        assert scene.sun is None and sink.sun == SunState(elevation, 10.0)

    def test_a_sun_at_the_threshold_still_shines(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.set_sun(SunState(MIN_SUN_ELEVATION_DEG, 90.0))  # due east, as low as "up" gets
        low = math.radians(MIN_SUN_ELEVATION_DEG)
        assert scene.sun == pytest.approx((-math.cos(low), -math.sin(low), 0.0), abs=1e-12)

    def test_ground_is_the_plan_rectangle_from_the_scene_origin(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.set_ground(GroundSpec(width_cm=2400.0, depth_cm=1600.0))
        assert scene.ground == GroundPlacement(center=(1200.0, 0.0, -800.0), width_cm=2400.0,
                                               depth_cm=1600.0)
        assert sink.ground == GroundSpec(2400.0, 1600.0)


class TestStateAndTeardown:
    def test_state_reads_like_a_recording_sink(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, _ = rig
        recording = RecordingSink()
        for target in (sink, recording):
            target.begin()
            target.add("a", (_prism(),), Transform(east_cm=1.0), RED)
            target.add("b", (), Transform(), BLUE)
            target.update_transform("a", Transform(east_cm=2.0))
            target.set_sun(SunState(30.0, 100.0))
            target.set_ground(GroundSpec(10.0, 20.0))
            target.commit()
        assert sink.state() == recording.state()
        assert sink.item("a") == recording.item("a")

    def test_clear_leaves_the_engine_holding_nothing(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.begin()
        sink.add("a", (_prism(), _prism(5.0)), Transform(), RED)
        sink.add("b", (_prism(),), Transform(), RED)
        sink.set_sun(SunState(30.0, 100.0))
        sink.set_ground(GroundSpec(10.0, 20.0))
        sink.clear()  # inside the open transaction: it aborts it
        assert scene.parts == [] and sink.item_ids() == ()
        assert scene.sun is None and scene.ground is None
        assert sink.sun is None and sink.ground is None and not sink.in_transaction
        assert sink.state() == RecordingSink().state()

    def test_clear_hands_the_teardown_to_the_one_owner_of_the_models(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        """One owner of Model lifetime (review P1-3): the sink does not destroy part by
        part and hope its handles are still good — it asks the engine scene, which
        holds every Model, to drop them all."""
        sink, scene = rig
        sink.begin()
        sink.add("a", (_prism(), _prism(5.0)), Transform(), RED)
        sink.commit()
        scene.calls.clear()
        sink.clear()
        assert scene.calls == [("clear",)]

    def test_clear_empties_the_books_even_when_the_engine_raises(self) -> None:
        """Exception-safe: a LIVE engine that fails to clear propagates its error (the
        sync stays poisoned) — and the sink is empty all the same, so the next
        ``clear()`` is clean instead of tripping over half-forgotten handles."""
        scene = FakeScene(fail_on_clear=True)
        sink = Quick3DSink(scene)
        sink.begin()
        sink.add("a", (_prism(),), Transform(), RED)
        sink.set_sun(SunState(30.0, 100.0))
        sink.set_ground(GroundSpec(10.0, 20.0))
        with pytest.raises(RuntimeError, match="could not clear"):
            sink.clear()
        assert sink.item_ids() == () and sink.sun is None and sink.ground is None
        assert not sink.in_transaction
        assert sink.state() == RecordingSink().state()
        scene.fail_on_clear = False
        sink.clear()  # asks the engine again, and this time it is clean
        assert scene.parts == [] and scene.calls[-1] == ("clear",)

    def test_nothing_is_built_on_an_engine_that_failed_to_clear(self) -> None:
        """Review round 2, P2-3: after a failed ``clear()`` the sink's books are empty and
        the engine still holds Models. A sink that went on would draw the new scene ON
        TOP of the leftovers while ``state()`` says everything is as told. ``begin()``
        refuses until a ``clear()`` went through — or a fresh, empty scene is attached."""
        scene = FakeScene(fail_on_clear=True)
        sink = Quick3DSink(scene)
        sink.begin()
        sink.add("a", (_prism(),), Transform(), RED)
        sink.commit()
        for _attempt in range(3):
            with pytest.raises(RuntimeError, match="could not clear"):
                sink.clear()
            assert len(scene.parts) == 1, "the engine still holds it"
            with pytest.raises(SinkProtocolError, match=r"the last clear\(\) failed"):
                sink.begin()
            assert not sink.in_transaction
        scene.fail_on_clear = False
        sink.clear()
        sink.begin()
        sink.add("a", (_prism(),), Transform(), RED)
        sink.commit()
        assert len(scene.parts) == 1

        scene.fail_on_clear = True
        with pytest.raises(RuntimeError):
            sink.clear()
        fresh = FakeScene()
        sink.attach(fresh)  # the other way out: an empty scene of its own
        sink.begin()
        sink.commit()
        assert fresh.calls[-1] == ("frame",)

    @pytest.mark.parametrize("in_transaction", [False, True])
    def test_clear_on_an_engine_that_is_gone_raises_nothing(self, in_transaction: bool) -> None:
        """The host was closed, or Qt destroyed its window with the main window: there is
        nothing left to destroy, and a sync whose engine died still has to be reset."""
        scene = FakeScene()
        sink = Quick3DSink(scene)
        sink.begin()
        sink.add("a", (_prism(), _prism(5.0)), Transform(), RED)
        sink.set_sun(SunState(30.0, 100.0))
        if not in_transaction:
            sink.commit()
        scene.dead = True
        sink.clear()
        sink.clear()  # idempotent
        assert sink.item_ids() == () and sink.sun is None and not sink.in_transaction
        with pytest.raises(EngineGone):  # everything else still says so, loudly
            sink.begin()
            sink.add("b", (_prism(),), Transform(), RED)

    def test_attach_points_an_empty_sink_at_a_fresh_engine(self) -> None:
        """The recovery after the engine died: clear, attach a new scene, send again."""
        old, new = FakeScene(), FakeScene()
        sink = Quick3DSink(old)
        sync = SceneSync(sink)
        record = Record(item_id="a", kind="SHED", shape="rectangle", footprints=(SQUARE,),
                        transform=Transform(), material=RED, height_cm=100.0,
                        params=Params({"seed": "a"}))
        sync.apply({"a": record})
        old.dead = True
        sink.clear()
        sync.reset()
        sink.attach(new)
        assert sink.scene is new
        sync.apply({"a": record})
        assert [p.spec.item_id for p in new.parts] == ["a", "a"] and len(old.parts) == 2  # old: untouched

    def test_attach_refuses_a_sink_that_still_holds_something(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        other = FakeScene()
        sink.begin()
        with pytest.raises(SinkProtocolError, match="not empty"):
            sink.attach(other)  # an open transaction
        sink.add("a", (_prism(),), Transform(), RED)
        sink.commit()
        with pytest.raises(SinkProtocolError, match="not empty"):
            sink.attach(other)  # an item
        assert sink.scene is scene
        sink.clear()
        sink.begin()
        sink.set_sun(SunState(30.0, 100.0))
        sink.commit()
        with pytest.raises(SinkProtocolError, match="not empty"):
            sink.attach(other)  # a sun
        sink.clear()
        sink.attach(other)
        assert sink.scene is other

    def test_one_sink_per_scene(self) -> None:
        """Review round 2, P2-4: ``attach()`` accepted a scene that already held Models.
        The engine then drew both sinks' items, and the next ``clear()`` of either
        destroyed the other's. A scene that holds Models has an owner: a second sink is
        refused at construction and at ``attach()`` — refused, not cleared: clearing
        would destroy what somebody else is showing."""
        scene = FakeScene()
        owner = Quick3DSink(scene)
        owner.begin()
        owner.add("a", (_prism(), _prism(5.0)), Transform(), RED)
        owner.commit()
        with pytest.raises(SinkProtocolError, match=r"Quick3DSink\(\): .*already holds 2 Model"):
            Quick3DSink(scene)
        other = Quick3DSink(FakeScene())
        with pytest.raises(SinkProtocolError, match=r"attach\(\): .*already holds 2 Model"):
            other.attach(scene)
        assert other.scene is not scene and len(scene.parts) == 2, "refused, and nothing destroyed"
        owner.clear()
        other.attach(scene)  # empty: free to take
        assert other.scene is scene

    def test_a_sink_cannot_be_given_an_engine_that_is_gone(self) -> None:
        with pytest.raises(EngineGone):
            Quick3DSink(FakeScene(dead=True))
        sink = Quick3DSink(FakeScene())
        with pytest.raises(EngineGone):
            sink.attach(FakeScene(dead=True))

    def test_clear_is_legal_at_any_time(self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        sink, scene = rig
        sink.clear()                      # on a sink that never held anything
        sink.clear()                      # twice
        sink.begin()
        sink.clear()                      # inside an empty transaction
        assert not sink.in_transaction
        sink.begin()
        sink.add("a", (_prism(),), Transform(), RED)
        sink.commit()
        sink.clear()                      # outside a transaction, with content
        assert scene.parts == [] and sink.item_ids() == ()

    def test_clear_then_the_same_items_again_gives_fresh_models(
            self, rig: tuple[Quick3DSink, FakeScene]) -> None:
        """What ``SceneSync.reset()`` does: clear, then re-send everything. No Model and
        no buffer object of the first round may come back (the re-attach trap)."""
        sink, scene = rig
        part = _prism()

        def send() -> None:
            sink.begin()
            sink.add("a", (part,), Transform(east_cm=3.0), RED)
            sink.set_sun(SunState(30.0, 100.0))
            sink.set_ground(GroundSpec(10.0, 20.0))
            sink.commit()

        send()
        first, state = scene.of("a")[0], sink.state()
        sink.clear()
        send()
        (second,) = scene.of("a")
        assert second is not first and not first.alive and second.alive
        assert sink.state() == state and sink.geometry_uploads == 2
        assert scene.sun is not None and scene.ground is not None

    def test_an_engine_error_propagates_and_clear_cleans_up(self) -> None:
        """A sink never swallows: ``SceneSync`` must see the error to poison itself, and
        ``clear()`` must then leave nothing half-built behind."""
        scene = FakeScene(fail_on_create=2)
        sink = Quick3DSink(scene)
        sink.begin()
        with pytest.raises(RuntimeError, match="engine refused"):
            sink.add("a", (_prism(), _prism(5.0), _prism(7.0)), Transform(), RED)
        assert len(scene.parts) == 1  # the first part was created before the failure
        sink.clear()
        assert scene.parts == [] and sink.item_ids() == () and not sink.in_transaction


class TestThroughSceneSync:
    def _record(self, item_id: str, east: float = 0.0, height: float | None = 100.0,
                colour: tuple[int, int, int, int] = (200, 30, 30, 255)) -> Record:
        return Record(item_id=item_id, kind="SHED", shape="rectangle", footprints=(SQUARE,),
                      transform=Transform(east_cm=east), material=Material("SHED", fill_rgba=colour),
                      height_cm=height, params=Params({"seed": item_id}))

    def test_a_scripted_session_keeps_the_sink_equal_to_the_recording_one(self) -> None:
        scene = FakeScene()
        quick, recording = Quick3DSink(scene), RecordingSink()
        syncs = (SceneSync(quick, validate=True), SceneSync(recording, validate=True))
        steps: list[dict[str, Record]] = [
            {"a": self._record("a"), "b": self._record("b", 300.0), "flat": self._record("flat", height=None)},
            {"a": self._record("a", east=50.0), "b": self._record("b", 300.0), "flat": self._record("flat", height=None)},
            {"a": self._record("a", east=50.0, colour=(1, 2, 3, 255)), "b": self._record("b", 300.0)},
            {"a": self._record("a", east=50.0, colour=(1, 2, 3, 255), height=250.0)},
            {},
            {"a": self._record("a"), "b": self._record("b", 300.0)},
        ]
        for records in steps:
            for sync in syncs:
                sync.apply(records)
            assert quick.state() == recording.state()
            # the engine boundary holds exactly one live part per drawable mesh part
            expected = sorted(item_id for item_id, held in recording.state().items.items()
                              for part in held.parts if part.mesh.vertex_count)
            assert sorted(p.spec.item_id for p in scene.parts) == expected
        assert quick.transactions == recording.transactions

    def test_a_move_reaches_the_engine_as_poses_only(self) -> None:
        scene = FakeScene()
        sync = SceneSync(Quick3DSink(scene))
        sync.apply({"a": self._record("a")})
        scene.calls.clear()
        sync.apply({"a": self._record("a", east=10.0)})
        assert scene.calls == [("pose", "a"), ("pose", "a"), ("frame",)]  # sides + cap

    def test_a_failing_engine_poisons_the_sync_until_it_is_cleared_and_reset(self) -> None:
        scene = FakeScene(fail_on_create=2)
        sink = Quick3DSink(scene)
        sync = SceneSync(sink)
        with pytest.raises(RuntimeError, match="engine refused"):
            sync.apply({"a": self._record("a"), "b": self._record("b")})
        assert sync.poisoned
        with pytest.raises(SyncStateError):
            sync.apply({})
        sync.reset()  # the recovery: it calls sink.clear() itself
        assert not sync.poisoned and scene.parts == [] and sink.item_ids() == ()
        scene.fail_on_create = None
        sync.apply({"a": self._record("a")})
        assert [p.spec.item_id for p in scene.parts] == ["a", "a"]  # sides + cap (#627)
        assert sink.state() == sync.expected_state()

    def _engine_matches(self, scene: FakeScene, sync: SceneSync) -> None:
        """What the ENGINE boundary holds, against the reference: one live part per
        drawable mesh part of ``expected_state()``, with its pose and tint."""
        expected = sync.expected_state()
        want = sorted((item_id, index, engine_pose(held.transform),
                       part_tint(part, held.material))
                      for item_id, held in expected.items.items()
                      for index, part in enumerate(held.parts) if part.mesh.vertex_count)
        have = sorted((p.spec.item_id, p.spec.part_index, p.pose, p.tint) for p in scene.parts)
        assert have == want
        nothing = (None, "unset")  # a fresh FakeScene was never told either
        assert (scene.sun not in nothing) == (expected.sun is not None and expected.sun.is_up)
        assert (scene.ground not in nothing) == (expected.ground is not None)

    @pytest.mark.parametrize(("call", "trigger"), [
        ("create_part", "add"), ("create_part", "replace"), ("pose_part", "move"),
        ("set_part_fill", "recolour"), ("release_fill", "recolour"),
        ("set_sun", "sun"), ("set_ground", "ground"),
        ("request_frame", "move"),
    ], ids=["add", "replace_geometry", "update_transform", "update_material",
            "release_fill", "set_sun", "set_ground", "commit"])
    def test_any_engine_call_failing_mid_transaction_is_recovered_by_reset(
            self, call: str, trigger: str) -> None:
        """The L1.1 recipe for a sink (its report, F.2): make ONE engine call fail in the
        middle of a transaction, ``sync.reset()``, ``sync.apply(...)`` — and what the
        sink holds is what one from-scratch apply would hold (``expected_state()``).
        For every engine call the sink makes, including the frame request of ``commit``.

        The transaction that fails changes TWO things, and the failing call is the
        second of its kind where that is possible — so there is something half done
        to clean up."""
        scene = FakeScene()
        sink = Quick3DSink(scene)
        sync = SceneSync(sink, validate=True)
        sun, ground = SunState(30.0, 100.0), GroundSpec(500.0, 400.0)
        before = {"a": self._record("a"), "b": self._record("b", 300.0)}
        sync.apply(before, sun=sun, ground=ground)
        self._engine_matches(scene, sync)

        after = dict(before)
        new_sun, new_ground = sun, ground
        if trigger == "add":
            after.update(c=self._record("c", 600.0), d=self._record("d", 900.0))
            scene.fail_on_create = scene.created + 2   # c is built, d fails
        elif trigger == "replace":
            after.update(a=self._record("a", height=250.0), b=self._record("b", 300.0, height=50.0))
            scene.fail_on_create = scene.created + 2   # a is rebuilt, b is destroyed and fails
        elif trigger == "move":
            after.update(a=self._record("a", east=40.0), b=self._record("b", 340.0))
        elif trigger == "recolour":
            # BOTH items: the old fill picture has two users, so it is released only
            # when the second one moves — the case a picture's lifetime rests on
            after.update(a=self._record("a", colour=(1, 2, 3, 255)),
                         b=self._record("b", 300.0, colour=(1, 2, 3, 255)))
        elif trigger == "sun":
            new_sun = SunState(55.0, 200.0)
        else:
            new_ground = GroundSpec(900.0, 700.0)
        if call != "create_part":
            scene.fail_once = call

        with pytest.raises(RuntimeError, match="engine"):
            sync.apply(after, sun=new_sun, ground=new_ground)
        assert sync.poisoned
        with pytest.raises(SyncStateError):
            sync.apply(after)
        if call != "request_frame":
            assert sink.in_transaction, "the failure left the transaction open"

        scene.fail_on_create = None
        sync.reset()
        assert not sync.poisoned and not sink.in_transaction
        assert scene.parts == [] and scene.sun is None and scene.ground is None
        assert sink.state() == RecordingSink().state()

        sync.apply(after, sun=new_sun, ground=new_ground)
        assert sink.state() == sync.expected_state()   # incremental == full rebuild
        self._engine_matches(scene, sync)

    def test_reset_on_an_engine_that_is_gone_succeeds_and_a_fresh_one_takes_over(self) -> None:
        """``reset()`` propagates what ``clear()`` raises and stays poisoned — so a sink
        whose ``clear()`` raised on a dead engine would poison the sync for good. It
        does not raise there; the sync comes back clean and drives a fresh engine."""
        old, new = FakeScene(), FakeScene()
        sink = Quick3DSink(old)
        sync = SceneSync(sink)
        records = {"a": self._record("a"), "b": self._record("b", 300.0)}
        sync.apply(records, sun=SunState(30.0, 100.0))
        old.dead = True
        with pytest.raises(EngineGone):
            sync.apply({"a": self._record("a", east=5.0), "b": self._record("b", 300.0)})
        assert sync.poisoned
        sync.reset()
        assert not sync.poisoned and sink.item_ids() == ()
        sink.attach(new)
        sync.apply(records, sun=SunState(30.0, 100.0))
        assert sink.state() == sync.expected_state()
        self._engine_matches(new, sync)

    def test_a_live_engine_that_cannot_clear_keeps_the_sync_poisoned(self) -> None:
        """The other half of the rule: when the engine is THERE and fails to clear, the
        error is not swallowed — ``reset()`` raises, the sync stays poisoned, and the
        next ``reset()`` asks again."""
        scene = FakeScene()
        sink = Quick3DSink(scene)
        sync = SceneSync(sink)
        sync.apply({"a": self._record("a")})
        scene.fail_on_clear = True
        with pytest.raises(RuntimeError, match="could not clear"):
            sync.reset()
        assert sync.poisoned
        scene.fail_on_clear = False
        sync.reset()
        sync.apply({"a": self._record("a")})
        assert not sync.poisoned and sink.state() == sync.expected_state()

    def test_the_default_registry_builds_what_the_sink_uploads(self) -> None:
        scene = FakeScene()
        sync = SceneSync(Quick3DSink(scene), BuilderRegistry(), validate=True)
        record = self._record("a", height=180.0)
        sync.apply({"a": record})
        sides, cap = scene.parts
        packed = np.frombuffer(sides.spec.buffers.vertex_data, "<f4").reshape(-1, 12)
        assert float(packed[:, 1].max()) == 180.0 and float(packed[:, 1].min()) == 0.0  # y = up
        cap_packed = np.frombuffer(cap.spec.buffers.vertex_data, "<f4").reshape(-1, 12)
        assert np.all(cap_packed[:, 1] == 180.0)  # the cap: the top face, nothing else
        for part in scene.parts:
            assert isinstance(part.spec.buffers, EngineBuffers)
        assert (sides.spec.name, cap.spec.name) == ("prism_sides", "prism")


def test_the_adapter_module_does_not_import_the_engine() -> None:
    """The sink is testable here BECAUSE it is engine-free: importing it must not pull
    Qt Quick in (the engine modules are ``geometry`` and ``host``). Checked in the
    module's own namespace — ``sys.modules`` of a shared test process proves nothing."""
    module = sys.modules["open_garden_planner.ui.view3d.quick3d.adapter"]
    names = {name for name, value in vars(module).items()
             if getattr(value, "__module__", "").startswith("PyQt6")}
    assert names == set()
