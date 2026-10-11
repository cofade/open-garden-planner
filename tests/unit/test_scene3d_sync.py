"""EngineSink protocol, RecordingSink and SceneSync (Phase 17 L1.1, #385).

Qt-free. The pipeline's promise is "the engine receives only what changed": a
move is ONE ``update_transform`` and no builder call. Pinned here on hand-built
records, and on real canvas items in ``tests/integration/test_scene3d_pipeline.py``.
The invariant that makes diffs safe — incremental == full rebuild — is asserted
after every step.
"""

from __future__ import annotations

import dataclasses
import logging
import random

import pytest

from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    EngineSink,
    GroundSpec,
    Material,
    MeshPart,
    Params,
    Record,
    RecordingSink,
    SceneDiff,
    SceneSync,
    SinkProtocolError,
    SunState,
    SyncStateError,
    Transform,
    default_builder,
    prism_mesh,
    verify_builder,
)
from open_garden_planner.core.solar import SolarPosition

SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))
T0 = Transform(100.0, 200.0, 30.0)
M0 = Material("RAISED_BED", fill_rgba=(120, 80, 40, 255))


def record(item_id: str = "a", **changes: object) -> Record:
    base = Record(item_id=item_id, kind="RAISED_BED", shape="rectangle", footprints=(SQUARE,),
                  transform=T0, material=M0, height_cm=40.0, params=Params({"seed": item_id}),
                  name=item_id.upper())
    return dataclasses.replace(base, **changes) if changes else base


def scene(*records: Record) -> dict[str, Record]:
    return {r.item_id: r for r in records}


class Counting:
    """A builder that counts its calls per item id (gate G2 counts invocations)."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_for: set[str] = set()

    def __call__(self, rec: Record) -> tuple[MeshPart, ...]:
        self.calls.append(rec.item_id)
        if rec.kind in self.fail_for:
            raise RuntimeError(f"cannot build {rec.kind}")
        return default_builder(rec)


@pytest.fixture
def builder() -> Counting:
    return Counting()


@pytest.fixture
def sync(builder: Counting) -> SceneSync:
    return SceneSync(RecordingSink(), BuilderRegistry(default=builder))


def sink_of(sync: SceneSync) -> RecordingSink:
    assert isinstance(sync.sink, RecordingSink)
    return sync.sink


# ── RecordingSink ─────────────────────────────────────────────────────────────


class TestRecordingSink:
    def test_is_an_engine_sink(self) -> None:
        assert isinstance(RecordingSink(), EngineSink)

    def test_records_every_call_in_order_and_answers_what_the_engine_holds(self) -> None:
        sink = RecordingSink()
        parts = default_builder(record())
        sun = SunState(59.29, 203.74)
        ground = GroundSpec(2400.0, 1600.0)
        sink.begin()
        sink.add("a", parts, T0, M0)
        sink.add("b", (), T0, M0)
        sink.update_transform("a", Transform(1.0, 2.0))
        sink.update_material("a", Material("X"))
        sink.replace_geometry("b", parts)
        sink.remove("a")
        sink.set_sun(sun)
        sink.set_ground(ground)
        sink.commit()
        assert sink.ops() == [
            ("begin", None), ("add", "a"), ("add", "b"), ("update_transform", "a"),
            ("update_material", "a"), ("replace_geometry", "b"), ("remove", "a"),
            ("set_sun", None), ("set_ground", None), ("commit", None),
        ]
        assert sink.calls[3].args == (Transform(1.0, 2.0),)
        assert sink.calls[1].args == (parts, T0, M0)
        assert sink.item_ids() == ("b",)
        assert sink.item("b").parts == parts and sink.item("b").transform == T0
        assert (sink.sun, sink.ground) == (sun, ground)
        assert sink.transactions == 1 and not sink.in_transaction
        state = sink.state()
        assert state.items == {"b": sink.item("b")} and state.sun == sun and state.ground == ground

    def test_state_is_a_snapshot_not_a_view(self) -> None:
        sink = RecordingSink()
        sink.begin()
        sink.add("a", (), T0, M0)
        sink.commit()
        before = sink.state()
        sink.begin()
        sink.remove("a")
        sink.commit()
        assert "a" in before.items and sink.state().items == {}

    def test_clear_calls_keeps_the_state(self) -> None:
        sink = RecordingSink()
        sink.begin()
        sink.add("a", (), T0, M0)
        sink.commit()
        sink.clear_calls()
        assert sink.calls == [] and sink.item_ids() == ("a",)

    @pytest.mark.parametrize(
        "call",
        [lambda s: s.add("a", (), T0, M0), lambda s: s.remove("a"),
         lambda s: s.update_transform("a", T0), lambda s: s.update_material("a", M0),
         lambda s: s.replace_geometry("a", ()), lambda s: s.set_sun(SunState(10.0, 90.0)),
         lambda s: s.set_ground(GroundSpec(1.0, 1.0)), lambda s: s.commit()],
        ids=["add", "remove", "update_transform", "update_material", "replace_geometry",
             "set_sun", "set_ground", "commit"],
    )
    def test_a_call_outside_begin_commit_raises(self, call) -> None:
        sink = RecordingSink()
        with pytest.raises(SinkProtocolError, match="outside begin"):
            call(sink)
        assert sink.calls == []  # a refused call is not recorded

    def test_nested_begin_raises(self) -> None:
        sink = RecordingSink()
        sink.begin()
        with pytest.raises(SinkProtocolError, match="already open"):
            sink.begin()

    def test_add_of_an_existing_id_raises(self) -> None:
        sink = RecordingSink()
        sink.begin()
        sink.add("a", (), T0, M0)
        with pytest.raises(SinkProtocolError, match="'a' is already"):
            sink.add("a", (), T0, M0)

    @pytest.mark.parametrize(
        "call",
        [lambda s: s.remove("ghost"), lambda s: s.update_transform("ghost", T0),
         lambda s: s.update_material("ghost", M0), lambda s: s.replace_geometry("ghost", ())],
        ids=["remove", "update_transform", "update_material", "replace_geometry"],
    )
    def test_touching_an_unknown_id_raises(self, call) -> None:
        sink = RecordingSink()
        sink.begin()
        with pytest.raises(SinkProtocolError, match="unknown item 'ghost'"):
            call(sink)

    def test_parts_must_be_mesh_parts(self) -> None:
        sink = RecordingSink()
        sink.begin()
        with pytest.raises(SinkProtocolError, match="MeshPart"):
            sink.add("a", (prism_mesh((SQUARE,), 1.0),), T0, M0)  # type: ignore[arg-type]
        sink.add("a", (), T0, M0)
        with pytest.raises(SinkProtocolError, match="MeshPart"):
            sink.replace_geometry("a", ["nope"])  # type: ignore[list-item]


class TestSunAndGround:
    def test_sun_state_is_plain_solar_data(self) -> None:
        sun = SunState(59.29, 203.74)
        e, n, up = sun.direction_scene
        assert (e, n, up) == pytest.approx((-0.2056, -0.4675, 0.8598), abs=1e-3)  # the US-E6 gate
        assert sun.light_travel_scene == (-e, -n, -up)  # light travels AWAY from the sun
        assert sun.is_up is True and SunState(-3.0, 10.0).is_up is False

    def test_sun_state_from_core_solar(self) -> None:
        from datetime import UTC, datetime

        from open_garden_planner.core.solar import solar_position

        position = solar_position(52.52, 13.405, datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        assert isinstance(position, SolarPosition)
        sun = SunState.from_solar_position(position)
        assert (sun.elevation_deg, sun.azimuth_deg) == (position.elevation_deg, position.azimuth_deg)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_non_finite_sun_is_refused(self, bad: float) -> None:
        with pytest.raises(ValueError):
            SunState(bad, 10.0)
        with pytest.raises(ValueError):
            SunState(10.0, bad)

    def test_ground_spec_is_the_plan_rectangle(self) -> None:
        ground = GroundSpec(2400.0, 1600.0)
        assert (ground.width_cm, ground.depth_cm) == (2400.0, 1600.0)
        with pytest.raises(ValueError):
            GroundSpec(0.0, 100.0)
        with pytest.raises(ValueError):
            GroundSpec(100.0, float("nan"))


# ── SceneSync: minimal calls ──────────────────────────────────────────────────


class TestMinimalCalls:
    def test_first_apply_adds_everything_in_one_transaction(self, sync, builder) -> None:
        result = sync.apply(scene(record("a"), record("b"), record("c", height_cm=None)))
        assert result == SceneDiff(added=("a", "b", "c"))
        assert sink_of(sync).ops() == [("begin", None), ("add", "a"), ("add", "b"), ("add", "c"),
                                       ("commit", None)]
        assert builder.calls == ["a", "b", "c"]
        assert sink_of(sync).item("c").parts == ()  # decoration: in the engine's books, no solid
        assert len(sink_of(sync).item("a").parts) == 1

    def test_unchanged_scene_makes_no_call_at_all(self, sync, builder) -> None:
        sync.apply(scene(record("a"), record("b")))
        sink_of(sync).clear_calls()
        builder.calls.clear()
        assert sync.apply(scene(record("a"), record("b"))).is_empty
        assert sink_of(sync).calls == [] and builder.calls == []
        assert sink_of(sync).transactions == 1

    def test_a_move_is_one_update_transform_and_no_builder_call(self, sync, builder) -> None:
        sync.apply(scene(record("a"), record("b")))
        sink_of(sync).clear_calls()
        builder.calls.clear()
        moved = Transform(555.0, 200.0, 30.0)
        result = sync.apply(scene(record("a", transform=moved), record("b")))
        assert result == SceneDiff(transform=("a",))
        assert sink_of(sync).ops() == [("begin", None), ("update_transform", "a"), ("commit", None)]
        assert sink_of(sync).calls[1].args == (moved,)
        assert builder.calls == []
        assert sync.build_count == 2  # the two adds — nothing since

    def test_a_recolour_is_one_update_material_and_no_builder_call(self, sync, builder) -> None:
        sync.apply(scene(record("a")))
        sink_of(sync).clear_calls()
        builder.calls.clear()
        green = Material("RAISED_BED", fill_rgba=(0, 200, 0, 255))
        assert sync.apply(scene(record("a", material=green))) == SceneDiff(material=("a",))
        assert sink_of(sync).ops() == [("begin", None), ("update_material", "a"), ("commit", None)]
        assert sink_of(sync).calls[1].args == (green,)
        assert builder.calls == []

    def test_a_geometry_change_rebuilds_that_item_only(self, sync, builder) -> None:
        sync.apply(scene(record("a"), record("b")))
        sink_of(sync).clear_calls()
        builder.calls.clear()
        assert sync.apply(scene(record("a"), record("b", height_cm=90.0))) == SceneDiff(geometry=("b",))
        assert sink_of(sync).ops() == [("begin", None), ("replace_geometry", "b"), ("commit", None)]
        assert builder.calls == ["b"]
        assert float(sink_of(sync).item("b").parts[0].mesh.bounds()[1][2]) == 90.0

    def test_all_three_at_once_are_three_calls_and_one_build(self, sync, builder) -> None:
        sync.apply(scene(record("a")))
        sink_of(sync).clear_calls()
        builder.calls.clear()
        changed = record("a", height_cm=1.0, transform=Transform(1.0, 1.0), material=Material("X"))
        sync.apply(scene(changed))
        assert sink_of(sync).ops() == [("begin", None), ("replace_geometry", "a"),
                                       ("update_transform", "a"), ("update_material", "a"),
                                       ("commit", None)]
        assert builder.calls == ["a"]

    def test_remove_and_add_in_one_transaction(self, sync, builder) -> None:
        sync.apply(scene(record("a"), record("b")))
        sink_of(sync).clear_calls()
        builder.calls.clear()
        assert sync.apply(scene(record("b"), record("c"))) == SceneDiff(added=("c",), removed=("a",))
        assert sink_of(sync).ops() == [("begin", None), ("remove", "a"), ("add", "c"), ("commit", None)]
        assert builder.calls == ["c"]

    def test_reorder_and_rename_reach_no_sink(self, sync, builder) -> None:
        sync.apply(scene(record("a"), record("b")))
        sink_of(sync).clear_calls()
        builder.calls.clear()
        result = sync.apply(scene(record("b"), record("a", name="Renamed")))
        assert result == SceneDiff(reordered=True)
        assert sink_of(sync).calls == [] and builder.calls == []
        assert list(sync.records) == ["b", "a"]  # … but the new order and name are kept
        assert sync.records["a"].name == "Renamed"

    def test_records_view_is_read_only_and_detached_from_the_input(self, sync) -> None:
        given = scene(record("a"))
        sync.apply(given)
        given["z"] = record("z")
        assert list(sync.records) == ["a"]
        with pytest.raises(TypeError):
            sync.records["q"] = record("q")  # type: ignore[index]


# ── the invariant: incremental == full rebuild ────────────────────────────────


def _mutate(rng: random.Random, records: dict[str, Record], counter: list[int]) -> dict[str, Record]:
    out = dict(records)
    op = rng.choice(["move", "rotate", "recolour", "height", "footprint", "add", "remove",
                     "reorder", "rename", "all", "nothing", "lose_height"])
    ids = list(out)
    if op == "add" or not ids:
        counter[0] += 1
        new_id = f"n{counter[0]}"
        out[new_id] = record(new_id, transform=Transform(rng.uniform(0, 900), rng.uniform(0, 900)))
        return out
    target = rng.choice(ids)
    rec = out[target]
    if op == "move":
        out[target] = dataclasses.replace(rec, transform=Transform(
            rng.uniform(0, 900), rng.uniform(0, 900), rec.transform.rotation_deg))
    elif op == "rotate":
        out[target] = dataclasses.replace(rec, transform=dataclasses.replace(
            rec.transform, rotation_deg=rng.choice([0.0, 17.0, 90.0, 213.5])))
    elif op == "recolour":
        out[target] = dataclasses.replace(rec, material=Material(
            "RAISED_BED", fill_rgba=(rng.randrange(256), rng.randrange(256), rng.randrange(256), 255)))
    elif op == "height":
        out[target] = dataclasses.replace(rec, height_cm=rng.choice([10.0, 40.0, 250.0]))
    elif op == "lose_height":
        out[target] = dataclasses.replace(rec, height_cm=None)
    elif op == "footprint":
        half = rng.choice([10.0, 25.0, 80.0])
        out[target] = dataclasses.replace(rec, footprints=(
            ((-half, -half), (half, -half), (half, half), (-half, half)),))
    elif op == "remove":
        del out[target]
    elif op == "reorder":
        rng.shuffle(ids)
        out = {i: out[i] for i in ids}
    elif op == "rename":
        out[target] = dataclasses.replace(rec, name=rec.name + "'")
    elif op == "all":
        out[target] = dataclasses.replace(
            rec, height_cm=77.0, transform=Transform(1.0, 2.0, 3.0), material=Material("Y"))
    return out


@pytest.mark.parametrize("seed", [1, 2, 3, 385])
def test_incremental_apply_always_equals_a_full_rebuild(seed: int) -> None:
    rng = random.Random(seed)
    sync = SceneSync(RecordingSink(), validate=True)
    records = scene(record("a"), record("b"), record("c"))
    counter = [0]
    for _step in range(120):
        sync.apply(records)
        fresh = SceneSync(RecordingSink(), validate=True)
        fresh.apply(records)
        assert sink_of(sync).state() == sink_of(fresh).state()
        assert sync.records == fresh.records and list(sync.records) == list(records)
        assert not sink_of(sync).in_transaction
        records = _mutate(rng, records, counter)


# ── reset ─────────────────────────────────────────────────────────────────────


class TestReset:
    def test_reset_forgets_everything_the_next_apply_readds_all(self, builder) -> None:
        registry = BuilderRegistry(default=builder)
        first = RecordingSink()
        sync = SceneSync(first, registry)
        records = scene(record("a"), record("b"))
        sync.apply(records)
        sync.set_sun(SunState(30.0, 180.0))
        # the engine was torn down: a new sink, and the sync must not assume anything
        torn_down = RecordingSink()
        sync = SceneSync(torn_down, registry)
        assert sync.apply(records) == SceneDiff(added=("a", "b"))
        assert torn_down.item_ids() == ("a", "b")

    def test_reset_on_the_same_sync(self, sync, builder) -> None:
        records = scene(record("a"), record("b"))
        sync.apply(records)
        sync.set_sun(SunState(30.0, 180.0))
        sink_of(sync).reset()  # the double's "engine torn down"
        sync.reset()
        assert dict(sync.records) == {} and sync.failures == {}
        builder.calls.clear()
        assert sync.apply(records) == SceneDiff(added=("a", "b"))
        assert builder.calls == ["a", "b"]
        assert sync.set_sun(SunState(30.0, 180.0)) is True  # resent: the engine forgot it


# ── a builder that raises ─────────────────────────────────────────────────────


class TestBuilderFailure:
    """The rule (ADR-054): a failing builder is CONTAINED. Every builder runs
    before the sink is touched, so the transaction is never half applied; the
    failing item gets no parts and is reported in ``failures``; everything else
    is applied; later applies are not poisoned."""

    def test_the_failing_item_gets_no_parts_and_the_rest_is_applied(self, sync, builder, caplog) -> None:
        builder.fail_for = {"HOUSE"}
        records = scene(record("a"), record("h", kind="HOUSE"), record("b"))
        with caplog.at_level(logging.ERROR, logger="open_garden_planner.core.scene3d.sync"):
            result = sync.apply(records)
        assert result == SceneDiff(added=("a", "h", "b"))
        assert sink_of(sync).ops() == [("begin", None), ("add", "a"), ("add", "h"), ("add", "b"),
                                       ("commit", None)]
        assert sink_of(sync).item("h").parts == ()
        assert len(sink_of(sync).item("a").parts) == len(sink_of(sync).item("b").parts) == 1
        failure = sync.failures["h"]
        assert (failure.item_id, failure.kind) == ("h", "HOUSE")
        assert isinstance(failure.error, RuntimeError) and "cannot build HOUSE" in str(failure.error)
        assert "cannot build HOUSE" in caplog.text and "'h'" in caplog.text
        assert not sink_of(sync).in_transaction and not sync.poisoned

    def test_a_failing_builder_is_not_rerun_until_the_geometry_changes(self, sync, builder) -> None:
        builder.fail_for = {"HOUSE"}
        sync.apply(scene(record("h", kind="HOUSE")))
        builder.calls.clear()
        sink_of(sync).clear_calls()
        # a move of the failing item: still one update_transform, still no build
        moved = record("h", kind="HOUSE", transform=Transform(9.0, 9.0))
        sync.apply(scene(moved))
        assert sink_of(sync).ops() == [("begin", None), ("update_transform", "h"), ("commit", None)]
        assert builder.calls == [] and "h" in sync.failures
        # its geometry changes while the builder is still broken: tried once more
        sync.apply(scene(dataclasses.replace(moved, height_cm=1.0)))
        assert builder.calls == ["h"] and "h" in sync.failures
        assert sink_of(sync).item("h").parts == ()

    def test_a_repaired_item_clears_its_failure(self, sync, builder) -> None:
        builder.fail_for = {"HOUSE"}
        sync.apply(scene(record("h", kind="HOUSE")))
        builder.fail_for = set()
        sync.apply(scene(record("h", kind="HOUSE", height_cm=300.0)))
        assert sync.failures == {} and len(sink_of(sync).item("h").parts) == 1

    def test_removing_the_item_clears_its_failure(self, sync, builder) -> None:
        builder.fail_for = {"HOUSE"}
        sync.apply(scene(record("h", kind="HOUSE"), record("a")))
        sync.apply(scene(record("a")))
        assert sync.failures == {}

    def test_incremental_still_equals_full_rebuild_with_a_failing_builder(self, builder) -> None:
        builder.fail_for = {"HOUSE"}
        registry = BuilderRegistry(default=builder)
        sync = SceneSync(RecordingSink(), registry)
        sync.apply(scene(record("a")))
        records = scene(record("a", height_cm=5.0), record("h", kind="HOUSE"))
        sync.apply(records)
        fresh = SceneSync(RecordingSink(), registry)
        fresh.apply(records)
        assert sink_of(sync).state() == sink_of(fresh).state()
        assert set(sync.failures) == set(fresh.failures) == {"h"}

    def test_a_wrong_return_type_is_a_failure_too(self) -> None:
        registry = BuilderRegistry()
        registry.register("HOUSE", lambda _rec: "not parts")  # type: ignore[arg-type,return-value]
        sync = SceneSync(RecordingSink(), registry)
        sync.apply(scene(record("h", kind="HOUSE")))
        assert "tuple of MeshPart" in str(sync.failures["h"].error)
        assert sink_of(sync).item("h").parts == ()

    def test_validate_turns_an_invalid_mesh_into_a_failure(self) -> None:
        def lit_from_below(rec: Record) -> tuple[MeshPart, ...]:
            mesh = prism_mesh(rec.footprints, 10.0)
            flipped = dataclasses.replace(mesh, normals=-mesh.normals)
            return (MeshPart(flipped),)

        registry = BuilderRegistry()
        registry.register("HOUSE", lit_from_below)
        strict = SceneSync(RecordingSink(), registry, validate=True)
        strict.apply(scene(record("h", kind="HOUSE")))
        assert "flat face" in str(strict.failures["h"].error)
        assert sink_of(strict).item("h").parts == ()
        lax = SceneSync(RecordingSink(), registry)  # production default: no per-build validation
        lax.apply(scene(record("h", kind="HOUSE")))
        assert lax.failures == {} and len(sink_of(lax).item("h").parts) == 1

    def test_an_interrupt_inside_a_builder_applies_nothing(self, builder) -> None:
        """KeyboardInterrupt is not a builder failure: it propagates — and because
        builders run before ``begin()``, the sink and the sync are untouched."""
        def interrupted(_rec: Record) -> tuple[MeshPart, ...]:
            raise KeyboardInterrupt

        registry = BuilderRegistry(default=builder)
        registry.register("HOUSE", interrupted)
        sync = SceneSync(RecordingSink(), registry)
        sync.apply(scene(record("a")))
        sink_of(sync).clear_calls()
        with pytest.raises(KeyboardInterrupt):
            sync.apply(scene(record("a", height_cm=7.0), record("h", kind="HOUSE")))
        assert sink_of(sync).calls == [] and not sync.poisoned
        assert sync.records == scene(record("a"))
        registry.register("HOUSE", builder, replace=True)
        sync.apply(scene(record("a", height_cm=7.0), record("h", kind="HOUSE")))  # works again
        assert sink_of(sync).item_ids() == ("a", "h")


# ── a sink that raises ────────────────────────────────────────────────────────


class FlakySink(RecordingSink):
    def __init__(self, fail_on: str) -> None:
        super().__init__()
        self.fail_on = fail_on

    def update_transform(self, item_id: str, transform: Transform) -> None:
        if self.fail_on == "update_transform":
            raise OSError("device lost")
        super().update_transform(item_id, transform)

    def commit(self) -> None:
        if self.fail_on == "commit":
            raise OSError("device lost")
        super().commit()


class TestSinkFailure:
    @pytest.mark.parametrize("fail_on", ["update_transform", "commit"])
    def test_a_sink_error_poisons_the_sync_until_reset(self, fail_on: str) -> None:
        """An engine that failed mid-transaction holds an unknown scene. The sync
        refuses to send it diffs against a state it may not have: every later
        ``apply`` raises until the owner tears the engine scene down and ``reset()``s."""
        sink = FlakySink(fail_on="")
        sync = SceneSync(sink)
        sync.apply(scene(record("a")))
        sink.fail_on = fail_on
        with pytest.raises(OSError, match="device lost"):
            sync.apply(scene(record("a", transform=Transform(5.0, 5.0))))
        assert sync.poisoned
        with pytest.raises(SyncStateError, match="reset"):
            sync.apply(scene(record("a")))
        with pytest.raises(SyncStateError):
            sync.set_sun(SunState(10.0, 10.0))
        sink.fail_on = ""
        sink.reset()
        sync.reset()
        assert not sync.poisoned
        assert sync.apply(scene(record("a"))) == SceneDiff(added=("a",))


# ── sun and ground pass-throughs ──────────────────────────────────────────────


class TestSunGroundPassThrough:
    def test_set_sun_is_sent_once_per_change(self, sync) -> None:
        assert sync.set_sun(SunState(30.0, 180.0)) is True
        assert sync.set_sun(SunState(30.0, 180.0)) is False
        assert sync.set_sun(SunState(31.0, 180.0)) is True
        assert sink_of(sync).ops() == [("begin", None), ("set_sun", None), ("commit", None),
                                       ("begin", None), ("set_sun", None), ("commit", None)]
        assert sink_of(sync).sun == SunState(31.0, 180.0)

    def test_set_ground_is_sent_once_per_change(self, sync) -> None:
        assert sync.set_ground(GroundSpec(2400.0, 1600.0)) is True
        assert sync.set_ground(GroundSpec(2400.0, 1600.0)) is False
        assert sink_of(sync).ground == GroundSpec(2400.0, 1600.0)
        assert sink_of(sync).ops() == [("begin", None), ("set_ground", None), ("commit", None)]


# ── the documented way to test a builder ──────────────────────────────────────


def test_the_documented_builder_workflow() -> None:
    """§8.26.1 "How to test a builder", as code. If this test has to change, the
    section's example has to change with it."""
    def build_house(rec: Record) -> tuple[MeshPart, ...]:
        assert rec.height_cm is not None
        walls = prism_mesh(rec.footprints, rec.height_cm * 0.6)
        roof = prism_mesh(rec.footprints, rec.height_cm)  # a stand-in: its top is the ridge
        return (MeshPart(walls, "vc", tinted=True, name="walls"),
                MeshPart(roof, "roof", name="roof"))

    house = record("h", kind="HOUSE", height_cm=450.0)
    records = scene(record("a"), house)
    house_id = "h"

    parts = verify_builder(build_house, house)  # the contract, one call
    assert [p.name for p in parts] == ["walls", "roof"]

    registry = BuilderRegistry()
    registry.register("HOUSE", build_house)
    sink = RecordingSink()
    sync = SceneSync(sink, registry, validate=True)
    sync.apply(records)
    assert sync.failures == {}
    assert sink.item(house_id).parts[1].material_kind == "roof"
    sink.clear_calls()
    moved_records = scene(record("a"), dataclasses.replace(house, transform=Transform(5.0, 6.0, 90.0)))
    sync.apply(moved_records)  # a move …
    assert sink.ops() == [("begin", None), ("update_transform", house_id), ("commit", None)]
    assert sync.build_count == len(records)  # … built nothing
