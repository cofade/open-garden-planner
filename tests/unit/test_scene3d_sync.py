"""EngineSink protocol, RecordingSink and SceneSync (Phase 17 L1.1, #385).

Qt-free. The pipeline's promise is "the engine receives only what changed": a
move is ONE ``update_transform`` and no builder call. Pinned here on hand-built
records, and on real canvas items in ``tests/integration/test_scene3d_pipeline.py``.
The invariant that makes diffs safe — incremental == full rebuild — is asserted
after every step.

Recovery (fix round 1) is tested THROUGH THE PROTOCOL: no test below reaches
into a sink to repair it. ``SceneSync.reset()`` calls ``EngineSink.clear()`` and
that is all the help a sink gets.
"""

from __future__ import annotations

import dataclasses
import logging
import random

import pytest

from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    BuildFailure,
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

    def test_the_protocol_has_eleven_methods_and_clear_is_one(self) -> None:
        """Ten since L1.1; ``set_selection`` since L1.8 — the one ADDITIVE seam of the
        selection ring (``tests/unit/test_scene3d_selection.py``)."""
        methods = sorted(name for name in vars(EngineSink)
                         if not name.startswith("_") and callable(getattr(EngineSink, name)))
        assert methods == ["add", "begin", "clear", "commit", "remove", "replace_geometry",
                           "set_ground", "set_selection", "set_sun", "update_material",
                           "update_transform"]

        class NineMethods:  # an engine written against the first contract
            def begin(self) -> None: ...
            def commit(self) -> None: ...
            def add(self, item_id, parts, transform, material) -> None: ...
            def remove(self, item_id) -> None: ...
            def update_transform(self, item_id, transform) -> None: ...
            def update_material(self, item_id, material) -> None: ...
            def replace_geometry(self, item_id, parts) -> None: ...
            def set_sun(self, sun) -> None: ...
            def set_ground(self, ground) -> None: ...

        assert not isinstance(NineMethods(), EngineSink)

    def test_clear_holds_nothing_afterwards(self) -> None:
        sink = RecordingSink()
        sink.begin()
        sink.add("a", default_builder(record()), T0, M0)
        sink.set_sun(SunState(30.0, 180.0))
        sink.set_ground(GroundSpec(100.0, 100.0))
        sink.commit()
        sink.clear()
        assert sink.state() == RecordingSink().state()
        assert sink.item_ids() == () and sink.sun is None and sink.ground is None
        assert sink.ops()[-1] == ("clear", None)  # recorded like any call
        assert sink.transactions == 1  # a clear is not a transaction

    def test_clear_is_legal_at_any_time(self) -> None:
        sink = RecordingSink()
        sink.clear()  # on an empty sink, outside a transaction
        sink.clear()  # twice
        sink.begin()
        sink.add("a", (), T0, M0)
        sink.clear()  # inside a transaction: it aborts it
        assert not sink.in_transaction and sink.item_ids() == ()
        with pytest.raises(SinkProtocolError, match="outside begin"):
            sink.commit()  # the transaction is gone, not merely emptied
        sink.begin()  # … and a new one opens cleanly
        sink.add("a", (), T0, M0)
        sink.commit()
        assert sink.item_ids() == ("a",)

    def test_reset_is_clear_plus_an_empty_log(self) -> None:
        """``reset()`` is this double's convenience, kept for callers written
        before ``clear()`` joined the protocol. It is not a protocol method."""
        sink = RecordingSink()
        sink.begin()
        sink.add("a", (), T0, M0)
        sink.reset()
        assert sink.calls == [] and sink.transactions == 0
        assert sink.state() == RecordingSink().state() and not sink.in_transaction
        assert "reset" not in vars(EngineSink)

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
        assert sink_of(sync).item("c").parts == ()  # no height: in the engine's books, no solid
        assert sink_of(sync).item("a").parts  # the default solid: sides + cap (#627)

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
    for step in range(120):
        sun = SunState(float(rng.randrange(5, 60)), float(rng.randrange(360))) if step % 3 else None
        sync.apply(records, sun=sun)
        fresh = SceneSync(RecordingSink(), validate=True)
        fresh.apply(records, sun=sync.sun)
        assert sink_of(sync).state() == sink_of(fresh).state() == sync.expected_state()
        assert sync.records == fresh.records and list(sync.records) == list(records)
        assert not sink_of(sync).in_transaction
        if step in (40, 80):  # recovery in the middle of a history changes nothing either
            sync.reset()
        records = _mutate(rng, records, counter)


# ── reset ─────────────────────────────────────────────────────────────────────


class TestReset:
    def test_reset_on_a_healthy_sync_clears_the_sink_and_the_next_apply_readds_all(
        self, sync, builder
    ) -> None:
        records = scene(record("a"), record("b"))
        sun, ground = SunState(30.0, 180.0), GroundSpec(2400.0, 1600.0)
        sync.apply(records, sun=sun, ground=ground)
        sink_of(sync).clear_calls()
        builder.calls.clear()

        sync.reset()

        assert sink_of(sync).ops() == [("clear", None)]  # the one call recovery makes
        assert sink_of(sync).state() == RecordingSink().state()
        assert dict(sync.records) == {} and sync.failures == {} and not sync.poisoned
        assert sync.sun is None and sync.ground is None
        assert sync.expected_state() == RecordingSink().state()

        assert sync.apply(records, sun=sun, ground=ground) == SceneDiff(added=("a", "b"))
        assert builder.calls == ["a", "b"]
        assert sink_of(sync).ops() == [("clear", None), ("begin", None), ("add", "a"), ("add", "b"),
                                       ("set_ground", None), ("set_sun", None), ("commit", None)]
        assert sink_of(sync).state() == sync.expected_state()

    def test_reset_forgets_the_sun_and_ground_it_deduplicates_against(self, sync) -> None:
        """The engine forgot them (``clear()``), so "same as last time" must not
        swallow the next one — what a reset that forgot only the records would do."""
        sun, ground = SunState(30.0, 180.0), GroundSpec(2400.0, 1600.0)
        assert sync.set_sun(sun) is True and sync.set_ground(ground) is True
        assert sync.set_sun(sun) is False and sync.set_ground(ground) is False
        sync.reset()
        assert sync.set_sun(sun) is True and sync.set_ground(ground) is True
        assert (sink_of(sync).sun, sink_of(sync).ground) == (sun, ground)

    def test_reset_forgets_build_failures(self, sync, builder) -> None:
        builder.fail_for = {"HOUSE"}
        sync.apply(scene(record("h", kind="HOUSE")))
        assert "h" in sync.failures
        sync.reset()
        assert sync.failures == {}
        builder.fail_for = set()
        sync.apply(scene(record("h", kind="HOUSE")))  # same geometry: built again, now fine
        assert sync.failures == {} and sink_of(sync).item("h").parts

    def test_reset_on_an_empty_sync(self, sync) -> None:
        sync.reset()
        sync.reset()
        assert sink_of(sync).ops() == [("clear", None), ("clear", None)]
        assert sync.apply({}).is_empty

    def test_a_new_engine_needs_a_new_sync_or_nothing_at_all(self, builder) -> None:
        """The other way to start over — the one L1.3 uses when the 3D view is
        rebuilt: a new sink gets a new ``SceneSync``. And a new PLAN needs neither:
        a plain ``apply`` of its snapshot removes what is gone and adds what is new."""
        registry = BuilderRegistry(default=builder)
        sync = SceneSync(RecordingSink(), registry)
        old_plan = scene(record("a"), record("b"))
        sync.apply(old_plan)
        new_plan = scene(record("x"), record("y"), record("z"))
        assert sync.apply(new_plan) == SceneDiff(added=("x", "y", "z"), removed=("a", "b"))
        assert sink_of(sync).state() == sync.expected_state()
        rebuilt = SceneSync(RecordingSink(), registry)
        assert rebuilt.apply(new_plan) == SceneDiff(added=("x", "y", "z"))
        assert sink_of(rebuilt).state() == sink_of(sync).state()


# ── a builder that raises ─────────────────────────────────────────────────────


class TestBuilderFailure:
    """The rule (ADR-059): a failing builder is CONTAINED. Every builder runs
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
        assert sink_of(sync).item("a").parts and len(sink_of(sync).item("a").parts) == len(sink_of(sync).item("b").parts)
        failure = sync.failures["h"]
        assert failure == BuildFailure("h", "HOUSE", "RuntimeError", "cannot build HOUSE")
        assert "cannot build HOUSE" in caplog.text and "'h'" in caplog.text
        (logged,) = [r for r in caplog.records if "'h'" in r.getMessage()]
        assert isinstance(logged.exc_info[1], RuntimeError)  # the exception itself: to the log, only
        assert not sink_of(sync).in_transaction and not sync.poisoned

    def test_a_failure_is_plain_data_and_keeps_nothing_alive(self, builder) -> None:
        """Review round 3, P2-11 — the lesson of ``SkippedItem``, here. The failure
        used to hold the exception; its traceback holds the frame of ``apply``,
        and that frame the records, every mesh built in that call and the sink."""
        import gc
        import weakref

        class Marked(RuntimeError):
            """An exception a weak reference can watch."""

        def failing(rec: Record) -> tuple[MeshPart, ...]:
            raise raised[0]

        raised = [Marked("cannot build this")]
        gone = weakref.ref(raised[0])
        registry = BuilderRegistry()
        registry.register("HOUSE", failing)
        logging.getLogger("open_garden_planner.core.scene3d.sync").disabled = True  # pytest keeps log records
        try:
            sync = SceneSync(RecordingSink(), registry)
            sync.apply(scene(record("h", kind="HOUSE")))
        finally:
            logging.getLogger("open_garden_planner.core.scene3d.sync").disabled = False
        failure = sync.failures["h"]
        assert dataclasses.fields(failure)[2].name == "error_type"
        assert all(isinstance(getattr(failure, f.name), str) for f in dataclasses.fields(failure))
        assert (failure.error_type, failure.error_message) == ("Marked", "cannot build this")
        raised.clear()
        gc.collect()
        assert gone() is None  # the failure is still held; the exception is not

    def test_the_old_error_attribute_still_reads(self, builder) -> None:
        """``failure.error`` was the exception. Code written then — an engine's
        diagnostics formats ``type(failure.error).__name__`` and ``str(failure.error)``
        — keeps working on a stand-in: the same class NAME, the same text, no
        traceback. It is not the original class any more."""
        builder.fail_for = {"HOUSE"}
        sync = SceneSync(RecordingSink(), BuilderRegistry(default=builder))
        sync.apply(scene(record("h", kind="HOUSE")))
        error = sync.failures["h"].error
        assert f"{type(error).__name__}: {error}" == "RuntimeError: cannot build HOUSE"
        assert isinstance(error, Exception) and error.__traceback__ is None
        assert not isinstance(error, RuntimeError)  # test error_type, not isinstance
        assert type(sync.failures["h"].error) is type(error)  # one class per name, not one per call

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
        assert sync.failures == {} and sink_of(sync).item("h").parts

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
        assert sync.failures["h"].error_type == "BuilderContractError"
        assert "tuple of MeshPart" in sync.failures["h"].error_message
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
        assert "flat face" in strict.failures["h"].error_message
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

    def test_a_footprint_that_crosses_itself_gets_no_solid_not_a_wrong_one(self) -> None:
        """The default builder refuses a bow-tie instead of emitting a mesh that
        fails ``validate()`` (review P2-6). ``validate=False`` — the production
        setting — so nothing but the builder's own refusal stands in the way."""
        # crosses itself, and still has a positive signed area — so the record's
        # own orientation check cannot refuse it; the builder has to
        lopsided = ((0.0, 200.0), (400.0, 0.0), (400.0, 300.0), (0.0, 0.0))
        sync = SceneSync(RecordingSink())
        sync.apply(scene(record("a"), record("h", kind="HOUSE", footprints=(lopsided,))))
        failure = sync.failures["h"]
        assert isinstance(failure, BuildFailure) and failure.error_type == "ValueError"
        assert "not a simple polygon" in failure.error_message
        assert sink_of(sync).item("h").parts == ()
        assert sink_of(sync).item("a").parts  # sides + cap (#627)
        for item in sink_of(sync).state().items.values():
            for part in item.parts:
                part.validate()


# ── a registry that changes after the first apply ─────────────────────────────


class TestRegistryChange:
    """Review P2-1: a builder registered after the sync had built left the old
    geometry in the engine for good — incremental != full rebuild. The rule now:
    the next ``apply`` rebuilds every item whose builder is no longer the one
    that built it."""

    @staticmethod
    def tall(rec: Record) -> tuple[MeshPart, ...]:
        return (MeshPart(prism_mesh(rec.footprints, 999.0), name="tall"),)

    def test_a_late_registration_rebuilds_the_items_it_now_owns(self, builder) -> None:
        registry = BuilderRegistry(default=builder)
        sync = SceneSync(RecordingSink(), registry)
        records = scene(record("a"), record("h", kind="HOUSE"), record("b"))
        sync.apply(records)
        sink_of(sync).clear_calls()
        builder.calls.clear()

        registry.register("HOUSE", self.tall)
        result = sync.apply(records)

        assert result.is_empty  # no RECORD changed …
        assert sink_of(sync).ops() == [("begin", None), ("replace_geometry", "h"), ("commit", None)]
        assert builder.calls == []  # … and nobody else was rebuilt
        assert sink_of(sync).item("h").parts[0].name == "tall"
        assert sink_of(sync).state() == sync.expected_state()
        sink_of(sync).clear_calls()
        assert sync.apply(records).is_empty and sink_of(sync).calls == []  # once, not every time

    def test_a_replaced_builder_rebuilds_too(self) -> None:
        registry = BuilderRegistry()
        registry.register("HOUSE", default_builder)
        sync = SceneSync(RecordingSink(), registry)
        records = scene(record("h", kind="HOUSE"), record("a"))
        sync.apply(records)
        registry.register("HOUSE", self.tall, replace=True)
        sync.apply(scene(record("h", kind="HOUSE", transform=Transform(1.0, 2.0)), record("a")))
        assert sink_of(sync).ops()[-4:] == [("begin", None), ("replace_geometry", "h"),
                                            ("update_transform", "h"), ("commit", None)]
        assert sink_of(sync).state() == sync.expected_state()

    def test_a_geometry_change_under_a_new_builder_is_built_once(self) -> None:
        calls: list[str] = []

        def counting_tall(rec: Record) -> tuple[MeshPart, ...]:
            calls.append(rec.item_id)
            return self.tall(rec)

        registry = BuilderRegistry()
        sync = SceneSync(RecordingSink(), registry)
        sync.apply(scene(record("h", kind="HOUSE")))
        registry.register("HOUSE", counting_tall)
        sync.apply(scene(record("h", kind="HOUSE", height_cm=77.0)))
        assert calls == ["h"]
        assert sink_of(sync).ops().count(("replace_geometry", "h")) == 1

    def test_a_new_builder_gets_a_failing_item_another_try(self, builder) -> None:
        builder.fail_for = {"HOUSE"}
        registry = BuilderRegistry(default=builder)
        sync = SceneSync(RecordingSink(), registry)
        records = scene(record("h", kind="HOUSE"))
        sync.apply(records)
        assert "h" in sync.failures
        registry.register("HOUSE", self.tall)
        sync.apply(records)
        assert sync.failures == {} and sink_of(sync).item("h").parts[0].name == "tall"

    def test_a_removed_item_is_not_rebuilt(self, builder) -> None:
        registry = BuilderRegistry(default=builder)
        sync = SceneSync(RecordingSink(), registry)
        sync.apply(scene(record("h", kind="HOUSE"), record("a")))
        registry.register("HOUSE", self.tall)
        sync.apply(scene(record("a")))
        assert sink_of(sync).ops()[-3:] == [("begin", None), ("remove", "h"), ("commit", None)]

    # ── fix round 2, P2-5 / P2-6: the comparison is identity, and gated ────────

    def test_a_registry_that_hands_out_a_fresh_callable_does_not_rebuild_every_apply(self) -> None:
        """The re-review's measurement: such a registry rebuilt EVERY item on
        EVERY idle apply — identity never matched. ``SceneSync`` now looks for
        items to rebuild only when ``BuilderRegistry.version`` moved."""
        import functools

        class Fresh(BuilderRegistry):
            def builder_for(self, kind: str):
                return functools.partial(super().builder_for(kind))  # never the same object

        registry = Fresh()
        sync = SceneSync(RecordingSink(), registry)
        records = scene(record("a"), record("h", kind="HOUSE"), record("b"))
        sync.apply(records)
        assert sync.build_count == 3
        sink_of(sync).clear_calls()
        for _ in range(5):
            assert sync.apply(records).is_empty
        assert sync.build_count == 3 and sink_of(sync).calls == []
        # a registration is still seen — at the price such a registry asks for: all of them
        registry.register("HOUSE", self.tall)
        sync.apply(records)
        assert sink_of(sync).item("h").parts[0].name == "tall"
        assert sync.build_count == 6
        sink_of(sync).clear_calls()
        assert sync.apply(records).is_empty and sink_of(sync).calls == [] and sync.build_count == 6

    def test_an_idle_apply_does_not_ask_the_registry_about_every_item(self) -> None:
        asked: list[str] = []

        class Asked(BuilderRegistry):
            def builder_for(self, kind: str):
                asked.append(kind)
                return super().builder_for(kind)

        registry = Asked()
        sync = SceneSync(RecordingSink(), registry)
        records = scene(*(record(f"i{n}") for n in range(50)))
        sync.apply(records)
        assert len(asked) == 50  # once per built item
        asked.clear()
        sync.apply(records)
        sync.apply({**records, "i0": record("i0", transform=Transform(1.0, 2.0))})
        assert asked == []  # nothing registered: nothing to look for
        registry.register("HOUSE", self.tall)
        sync.apply(records)
        assert len(asked) == 50  # the one scan a registration costs
        asked.clear()
        sync.apply(records)
        assert asked == []

    def test_a_registry_without_a_version_is_compared_on_every_apply(self, builder) -> None:
        """Anything with ``builder_for`` will do as a registry (the old behaviour):
        without a ``version`` to go by, the items are compared each time."""
        class Bare:
            def __init__(self) -> None:
                self.current = builder

            def builder_for(self, _kind: str):
                return self.current

        registry = Bare()
        sync = SceneSync(RecordingSink(), registry)  # type: ignore[arg-type]
        records = scene(record("a"), record("b"))
        sync.apply(records)
        sync.apply(records)
        assert builder.calls == ["a", "b"]
        registry.current = self.tall
        sync.apply(records)
        assert [sink_of(sync).item(i).parts[0].name for i in "ab"] == ["tall", "tall"]
        sink_of(sync).clear_calls()
        sync.apply(records)
        assert sink_of(sync).calls == []

    def test_a_reset_forgets_which_registry_built_the_items(self, builder) -> None:
        registry = BuilderRegistry(default=builder)
        sync = SceneSync(RecordingSink(), registry)
        records = scene(record("a"))
        sync.apply(records)
        sync.reset()
        sync.apply(records)
        registry.register("RAISED_BED", self.tall)
        sync.apply(records)
        assert sink_of(sync).item("a").parts[0].name == "tall"
        assert sink_of(sync).state() == sync.expected_state()

    def test_many_items_regrown_in_one_tick_with_a_late_builder(self, builder) -> None:
        """P2-5: the scan asked ``item_id not in changes.geometry`` — a tuple — per
        held item (224 of 260 ms at 8,000 items). A set now; what it decides is
        unchanged: an item whose geometry changes anyway is built ONCE."""
        registry = BuilderRegistry(default=builder)
        sync = SceneSync(RecordingSink(), registry)
        count = 400
        records = scene(*(record(f"i{n}") for n in range(count)))
        sync.apply(records)
        builder.calls.clear()
        registry.register("NOTHING HERE", self.tall)  # the version moves, no item is affected
        grown = scene(*(record(f"i{n}", height_cm=41.0) for n in range(count)))
        sync.apply(grown)
        assert sorted(builder.calls) == sorted(grown)  # each once
        assert sink_of(sync).state() == sync.expected_state()


# ── a sink that raises ────────────────────────────────────────────────────────


class FlakySink(RecordingSink):
    """Fails on the named call. Nothing in it helps recovery: ``clear()`` is the
    inherited protocol method, and no test calls anything else on it to repair it."""

    def __init__(self, fail_on: str = "") -> None:
        super().__init__()
        self.fail_on = fail_on

    def _maybe_fail(self, op: str) -> None:
        if self.fail_on == op:
            raise OSError("device lost")

    def add(self, item_id, parts, transform, material) -> None:
        self._maybe_fail("add")
        super().add(item_id, parts, transform, material)

    def update_transform(self, item_id: str, transform: Transform) -> None:
        self._maybe_fail("update_transform")
        super().update_transform(item_id, transform)

    def set_sun(self, sun: SunState) -> None:
        self._maybe_fail("set_sun")
        super().set_sun(sun)

    def commit(self) -> None:
        self._maybe_fail("commit")
        super().commit()

    def clear(self) -> None:
        self._maybe_fail("clear")
        super().clear()


class DeafSink(RecordingSink):
    """A lenient sink: it accepts ``clear()`` and does nothing."""

    def clear(self) -> None:
        return None


def assert_recovered(sync: SceneSync, sink: RecordingSink, records: dict[str, Record]) -> None:
    """The recovery contract, checked from outside: after ``reset()`` and one
    ``apply``, the sink holds what a from-scratch apply puts into an empty one."""
    from_scratch = RecordingSink()
    SceneSync(from_scratch, sync.registry).apply(records, sun=sync.sun, ground=sync.ground)
    assert sink.state() == from_scratch.state()
    assert sink.state() == sync.expected_state()
    assert not sink.in_transaction and not sync.poisoned


class TestSinkFailure:
    @pytest.mark.parametrize("fail_on", ["add", "update_transform", "set_sun", "commit"])
    def test_recovery_goes_through_the_protocol(self, fail_on: str) -> None:
        """An engine that failed mid-transaction holds an unknown scene and an OPEN
        transaction. The sync refuses to send it diffs against a state it may not
        have — and ``reset()`` alone, through ``EngineSink.clear()``, puts both
        right. (The first contract could not say this: its ``reset()`` touched no
        sink, and the next ``begin()`` raised "a transaction is already open".)"""
        sink = FlakySink()
        sync = SceneSync(sink)
        sun, ground = SunState(30.0, 180.0), GroundSpec(2400.0, 1600.0)
        sync.apply(scene(record("a"), record("b")), sun=sun, ground=ground)
        after = scene(record("a", transform=Transform(5.0, 5.0)), record("c"))
        sink.fail_on = fail_on
        with pytest.raises(OSError, match="device lost"):
            sync.apply(after, sun=SunState(31.0, 181.0))
        assert sync.poisoned
        if fail_on != "commit":
            assert sink.in_transaction  # left open by the failure
        with pytest.raises(SyncStateError, match="reset"):
            sync.apply(after)
        with pytest.raises(SyncStateError):
            sync.set_sun(SunState(10.0, 10.0))
        with pytest.raises(SyncStateError):
            sync.set_ground(GroundSpec(1.0, 1.0))
        assert sync.records == scene(record("a"), record("b"))  # the failed apply was not booked

        sink.fail_on = ""  # the device is back; nothing else is done to the sink
        sync.reset()

        assert not sync.poisoned and not sink.in_transaction
        assert sync.apply(after, sun=sun, ground=ground) == SceneDiff(added=("a", "c"))
        assert_recovered(sync, sink, after)

    def test_a_failure_in_a_sun_only_transaction_recovers_the_same_way(self) -> None:
        sink = FlakySink()
        sync = SceneSync(sink)
        records = scene(record("a"))
        sync.apply(records)
        sink.fail_on = "set_sun"
        with pytest.raises(OSError):
            sync.set_sun(SunState(30.0, 180.0))
        assert sync.poisoned and sync.sun is None
        sink.fail_on = ""
        sync.reset()
        sync.apply(records, sun=SunState(30.0, 180.0))
        assert_recovered(sync, sink, records)

    def test_a_clear_that_raises_leaves_the_sync_poisoned(self) -> None:
        sink = FlakySink()
        sync = SceneSync(sink)
        sync.apply(scene(record("a")))
        sink.fail_on = "clear"
        with pytest.raises(OSError, match="device lost"):
            sync.reset()  # on a healthy sync: it is poisoned NOW
        assert sync.poisoned
        with pytest.raises(SyncStateError):
            sync.apply(scene(record("a")))
        with pytest.raises(OSError):
            sync.reset()  # still failing, still poisoned
        assert sync.poisoned
        sink.fail_on = ""
        sync.reset()
        assert not sync.poisoned
        sync.apply(scene(record("a")))
        assert_recovered(sync, sink, scene(record("a")))

    def test_a_sink_that_ignores_clear_is_caught_by_comparing_states(self) -> None:
        """The limit of what the sync can know: ``clear()`` returns nothing, so a
        sink that ignores it looks healthy from inside. Two things catch it — the
        strict double refuses the re-``add`` of an id it still holds, and, for a
        sink lenient about that too, ``sink.state() != sync.expected_state()``."""
        sink = DeafSink()
        sync = SceneSync(sink)
        sync.apply(scene(record("a"), record("b")))
        sync.reset()
        assert sink.state() != sync.expected_state()  # caught: the sink still holds a and b
        with pytest.raises(SinkProtocolError, match="'a' is already in the sink"):
            sync.apply(scene(record("a")))
        assert sync.poisoned

    def test_a_sink_that_ignores_clear_and_forgives_everything(self) -> None:
        class Forgiving(DeafSink):
            def add(self, item_id, parts, transform, material) -> None:
                if item_id in self._items:
                    del self._items[item_id]
                super().add(item_id, parts, transform, material)

        sink = Forgiving()
        sync = SceneSync(sink)
        sync.apply(scene(record("a"), record("b")))
        sync.reset()
        sync.apply(scene(record("a")))  # no error anywhere …
        assert not sync.poisoned
        assert sink.item_ids() == ("b", "a")  # … and a ghost of the old scene in the engine
        assert sink.state() != sync.expected_state()  # the comparison is what sees it


# ── sun and ground ────────────────────────────────────────────────────────────


class TestSunAndGroundCalls:
    def test_set_sun_is_sent_once_per_change(self, sync) -> None:
        assert sync.sun is None
        assert sync.set_sun(SunState(30.0, 180.0)) is True
        assert sync.set_sun(SunState(30.0, 180.0)) is False
        assert sync.set_sun(SunState(31.0, 180.0)) is True
        assert sink_of(sync).ops() == [("begin", None), ("set_sun", None), ("commit", None),
                                       ("begin", None), ("set_sun", None), ("commit", None)]
        assert sink_of(sync).sun == sync.sun == SunState(31.0, 180.0)

    def test_set_ground_is_sent_once_per_change(self, sync) -> None:
        assert sync.set_ground(GroundSpec(2400.0, 1600.0)) is True
        assert sync.set_ground(GroundSpec(2400.0, 1600.0)) is False
        assert sink_of(sync).ground == sync.ground == GroundSpec(2400.0, 1600.0)
        assert sink_of(sync).ops() == [("begin", None), ("set_ground", None), ("commit", None)]

    def test_a_clock_tick_is_one_transaction(self, sync, builder) -> None:
        """Review P2-2: a sim-date change moves the sun AND grows the plants. Sent
        as ``set_sun`` plus ``apply`` that was two commits — one frame with the new
        sun over the old plants. ``apply(records, sun=…)`` is one."""
        sync.apply(scene(record("a"), record("b")), sun=SunState(30.0, 180.0),
                   ground=GroundSpec(2400.0, 1600.0))
        assert sink_of(sync).transactions == 1
        sink_of(sync).clear_calls()
        grown = scene(record("a", height_cm=55.0), record("b"))
        result = sync.apply(grown, sun=SunState(41.0, 195.0))
        assert result == SceneDiff(geometry=("a",))
        assert sink_of(sync).ops() == [("begin", None), ("replace_geometry", "a"),
                                       ("set_sun", None), ("commit", None)]
        assert sink_of(sync).transactions == 2
        assert sink_of(sync).state() == sync.expected_state()

    def test_first_apply_carries_ground_and_sun(self, sync) -> None:
        sync.apply(scene(record("a")), sun=SunState(30.0, 180.0), ground=GroundSpec(10.0, 20.0))
        assert sink_of(sync).ops() == [("begin", None), ("add", "a"), ("set_ground", None),
                                       ("set_sun", None), ("commit", None)]
        assert (sync.sun, sync.ground) == (SunState(30.0, 180.0), GroundSpec(10.0, 20.0))

    def test_an_unchanged_sun_and_ground_send_nothing(self, sync) -> None:
        records = scene(record("a"))
        sun, ground = SunState(30.0, 180.0), GroundSpec(10.0, 20.0)
        sync.apply(records, sun=sun, ground=ground)
        sink_of(sync).clear_calls()
        assert sync.apply(records, sun=sun, ground=ground).is_empty
        assert sink_of(sync).calls == []
        assert sync.apply(records).is_empty  # None = leave them as they are
        assert sink_of(sync).calls == [] and (sync.sun, sync.ground) == (sun, ground)

    def test_a_sun_alone_opens_a_transaction_for_itself(self, sync) -> None:
        records = scene(record("a"))
        sync.apply(records)
        sink_of(sync).clear_calls()
        assert sync.apply(records, sun=SunState(12.0, 90.0)).is_empty
        assert sink_of(sync).ops() == [("begin", None), ("set_sun", None), ("commit", None)]

    def test_a_failed_transaction_books_neither_records_nor_sun(self) -> None:
        sink = FlakySink()
        sync = SceneSync(sink)
        sync.apply(scene(record("a")), sun=SunState(30.0, 180.0))
        sink.fail_on = "commit"
        with pytest.raises(OSError):
            sync.apply(scene(record("a"), record("b")), sun=SunState(40.0, 190.0))
        assert sync.sun == SunState(30.0, 180.0) and list(sync.records) == ["a"]

    def test_expected_state_is_the_from_scratch_reference(self, sync) -> None:
        assert sync.expected_state() == RecordingSink().state()
        records = scene(record("a"), record("b", height_cm=None))
        sync.apply(records, sun=SunState(30.0, 180.0), ground=GroundSpec(10.0, 20.0))
        expected = sync.expected_state()
        assert expected == sink_of(sync).state()
        assert set(expected.items) == {"a", "b"} and expected.items["b"].parts == ()
        assert (expected.sun, expected.ground) == (SunState(30.0, 180.0), GroundSpec(10.0, 20.0))
        calls = len(sink_of(sync).calls)
        sync.expected_state()
        assert len(sink_of(sync).calls) == calls  # it never touches the real sink

    def test_expected_state_between_a_registration_and_the_next_apply(self, builder) -> None:
        """Fix round 2, P2-8 — the precondition, shown. ``expected_state`` is built
        with the registry as it is NOW; a sink that honours the protocol still
        holds what the old builders made until ``apply`` has run."""
        registry = BuilderRegistry(default=builder)
        sync = SceneSync(RecordingSink(), registry)
        records = scene(record("h", kind="HOUSE"))
        sync.apply(records)
        assert sink_of(sync).state() == sync.expected_state()
        registry.register("HOUSE", TestRegistryChange.tall)
        assert sink_of(sync).state() != sync.expected_state()  # not a broken sink: a pending apply
        sync.apply(records)
        assert sink_of(sync).state() == sync.expected_state()

    def test_expected_state_does_not_log_old_failures_again(self, sync, builder, caplog) -> None:
        builder.fail_for = {"HOUSE"}
        with caplog.at_level(logging.ERROR, logger="open_garden_planner.core.scene3d.sync"):
            sync.apply(scene(record("h", kind="HOUSE")))
            assert len(caplog.records) == 1  # said once, when it happened
            caplog.clear()
            assert sync.expected_state().items["h"].parts == ()
        assert caplog.records == []


# ── the documented way to test a builder ──────────────────────────────────────


def test_the_documented_builder_workflow() -> None:
    """§8.29.1 "How to test a builder", as code. If this test has to change, the
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
