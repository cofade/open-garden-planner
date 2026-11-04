"""The pipeline's gates over the committed edge-case plan (L1.1 fix rounds 1 to 3, #385).

``tests/fixtures/plans/scene3d_edge_cases.ogp`` (``scripts/make_scene3d_edge_plan.py``)
is the third committed plan. The two bench plans hold no stroke that closes on
itself, no turned house, no ellipse and no concave polygon — which is how a
closed fence could become an 80 m² slab with every gate green. Here the same
gates run over exactly those shapes, loaded through the real ``ProjectManager``:

- G8 — 100 snapshots of the untouched plan are identical;
- G7 — every mesh of the default builder validates, tops out at the resolved
  height, and its cap covers the footprint's AREA (the check the defect needed);
- G4 — ``transform ∘ local rings`` reproduces ``item_footprints``, holes included;
- the first ``SceneSync.apply`` adds every record once, the next says nothing.

Fix round 2 added three items the review asked for — a ladder drawn as one
stroke (four holes in one outer ring), a fence whose ends stop too far apart to
close, and a HOUSE whose outline crosses itself around a pocket — and the same
gates run over them. For the crossed house G4 reads differently, because its
record is deliberately NOT the drawn ring: every vertex of its rings lies on the
drawn outline, and the ground they cover is what the outline fills.

Fix round 3 added a fence whose two butt ends meet corner to corner — the stroke
the clipper hands out as ONE ring that touches itself, and the one live path of
the snapshot that no test had run.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import (
    Mesh,
    Record,
    RecordingSink,
    SceneDiff,
    SceneSync,
    default_builder,
    diff,
    is_buildable_region,
    is_simple_ring,
    pose_ring,
    signed_area,
    verify_builder,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.footprints import item_footprints
from open_garden_planner.ui.view3d.snapshot import SkippedItem, snapshot_records
from tests.integration.test_scene3d_snapshot import (
    JUNE,
    _assert_walls_face_away_from_the_solid,
    _boundary_distance,
    _cap_area,
    _ring_deviation,
    _rings_of,
    _signed_area_sum,
    _strip_deviation,
    _winding_area,
)

REPO = Path(__file__).resolve().parents[2]
PLAN = REPO / "tests" / "fixtures" / "plans" / "scene3d_edge_cases.ogp"
BENCH_PLANS = ("bench_small.ogp", "bench_large.ogp")


Snapshot = dict[str, Record]


@pytest.fixture
def plan(qtbot) -> tuple[CanvasScene, Snapshot, dict[str, Any]]:  # noqa: ARG001
    scene = CanvasScene()
    ProjectManager().load(scene, PLAN)
    items = {str(i.item_id): i for i in scene.items()
             if getattr(i, "object_type", None) is not None and hasattr(i, "item_id")}
    skipped: list[SkippedItem] = []
    snapshot = snapshot_records(scene, JUNE, skipped=skipped)
    assert skipped == []  # nothing in this plan is malformed
    return scene, snapshot, items


def _by_name(snapshot: Snapshot, name: str):
    (record,) = [r for r in snapshot.values() if r.name == name]
    return record


def test_generator_reproduces_the_committed_fixture(qtbot, tmp_path) -> None:  # noqa: ARG001
    """Regenerating writes the same plan (modulo the save timestamp) — and leaves
    the two bench plans exactly as they are.

    "The same plan" is ``same_plan``: this fixture has turned items, so a few of
    its numbers went through ``cos`` / ``sin`` and may differ in their last bit
    on another platform (the committed file was generated on Windows). Every
    platform runs this one comparison — the generating one too: "bit for bit on
    this machine" would assert the machine, not the plan."""
    import open_garden_planner.app.settings as app_settings

    spec = importlib.util.spec_from_file_location(
        "make_scene3d_edge_plan", REPO / "scripts" / "make_scene3d_edge_plan.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    store = (app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME)
    spec.loader.exec_module(module)
    after = (app_settings.ORGANIZATION_NAME, app_settings.APPLICATION_NAME)
    assert after == store  # importing the generator must not retarget this process's settings
    fresh = tmp_path / module.NAME
    module.bench._save(module.build_edge_cases(), fresh)
    regenerated, committed = module.bench._normalised(fresh), module.bench._normalised(PLAN)
    assert module.same_plan(regenerated, committed), (
        "scene3d_edge_cases.ogp is stale — rerun scripts/make_scene3d_edge_plan.py")
    for name, build in zip(BENCH_PLANS, (module.bench.build_small, module.bench.build_large),
                           strict=True):
        again = tmp_path / name
        module.bench._save(build(), again)
        assert module.bench._normalised(again) == module.bench._normalised(PLAN.parent / name), name


def test_same_plan_forgives_the_last_bit_and_nothing_else(qtbot) -> None:  # noqa: ARG001
    """The comparison the regeneration test stands on, turned against itself: a
    float moved by one bit is the same plan; a float moved by a micrometre, a
    changed string, a missing key, a reordered list, ``True`` for ``1`` are not."""
    import json
    import math

    spec = importlib.util.spec_from_file_location(
        "make_scene3d_edge_plan", REPO / "scripts" / "make_scene3d_edge_plan.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = json.loads(PLAN.read_text(encoding="utf-8"))
    assert module.same_plan(committed, copy.deepcopy(committed))

    def first_float(node, path=()):
        if isinstance(node, float):
            return path
        children = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
        for key, child in children:
            found = first_float(child, (*path, key))
            if found is not None:
                return found
        return None

    def changed(path, change):
        plan = copy.deepcopy(committed)
        node = plan
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = change(node[path[-1]])
        return plan

    where = first_float(committed["objects"])
    assert where is not None
    where = ("objects", *where)
    assert module.same_plan(changed(where, lambda x: math.nextafter(x, math.inf)), committed)
    assert not module.same_plan(changed(where, lambda x: x + 1e-4), committed)  # a micrometre
    assert not module.same_plan(changed(("objects", 0, "object_type"), lambda _x: "SHED"), committed)
    assert not module.same_plan(changed(("objects",), lambda items: items[1:]), committed)
    assert not module.same_plan(changed(("objects",), lambda items: items[::-1]), committed)
    assert not module.same_plan({"a": True}, {"a": 1}) and not module.same_plan({"a": 1}, {"b": 1})
    assert module.same_plan({"a": 2}, {"a": 2.0})  # 2 and 2.0 are one number in JSON


def test_what_the_plan_contains(plan) -> None:
    """The cases, by name — so a regenerated plan cannot quietly lose one."""
    _scene, snapshot, items = plan
    assert len(items) == 17 and len(snapshot) == 15  # every item but the two roof ridges
    kinds = sorted(record.kind for record in snapshot.values())
    assert kinds == ["CONTAINER_ROUND", "FENCE", "FENCE", "FENCE", "FENCE", "FENCE", "FENCE",
                     "HEDGE_POLYGON", "HOUSE", "HOUSE", "PERENNIAL", "PERENNIAL", "PERENNIAL",
                     "POND_POOL", "RAISED_BED"]
    assert sum(1 for i in items.values() if i.object_type is ObjectType.ROOF_RIDGE) == 2

    house = _by_name(snapshot, "House")
    assert house.transform.rotation_deg == 25.0 and house.shape == "polygon"
    assert "outline_resolved" not in house.params
    (start, end) = house.params["ridge"]  # type: ignore[misc]
    assert start == pytest.approx((-450.0, 0.0), abs=1e-6) and end == pytest.approx((450.0, 0.0), abs=1e-6)

    # fix round 2: a house whose outline crosses itself around a pocket. It HAS a
    # ridge item in the plan; its record says "resolved" and hands no ridge on.
    crossed = _by_name(snapshot, "Crossed house")
    (crossed_item,) = [i for i in items.values() if getattr(i, "name", "") == "Crossed house"]
    assert crossed_item.metadata.get("ridge_item_id") in items
    assert crossed.params["outline_resolved"] is True and "ridge" not in crossed.params
    assert sorted(len(ring) for ring in crossed.footprints) == [3, 4, 13] and crossed.holes == ()
    assert len(item_footprints(crossed_item, JUNE)) == 1  # 2D: the ring as drawn, 7 vertices

    pond = _by_name(snapshot, "Pond")
    assert pond.shape == "ellipse" and pond.transform.rotation_deg == 40.0

    closed, nearly, open_u = (_by_name(snapshot, name) for name in
                              ("Closed fence", "Nearly closed fence", "Open U fence"))
    assert [len(r.footprints) for r in (closed, nearly, open_u)] == [1, 1, 1]
    assert [sum(len(g) for g in r.holes) for r in (closed, nearly, open_u)] == [1, 1, 0]
    assert closed.path_width_cm == nearly.path_width_cm == open_u.path_width_cm == 10.0
    # 36 m, 35.98 m and 26 m of fence, 10 cm wide — not the 80 m² they enclose
    assert closed.plan_area_cm2 == pytest.approx(36000.0, rel=5e-3)
    assert nearly.plan_area_cm2 == pytest.approx(35980.0, rel=5e-3)
    assert open_u.plan_area_cm2 == pytest.approx(26000.0, rel=5e-3)

    # fix round 2: a multi-hole stroke, and the gap a stroke does NOT close
    ladder, gap = _by_name(snapshot, "Ladder fence"), _by_name(snapshot, "Fence with a gap")
    assert len(ladder.footprints) == 1 and [len(group) for group in ladder.holes] == [4]
    assert all(len(hole) == 4 for hole in ladder.holes[0])  # four cells, 140 cm x 140 cm each
    assert sorted(-signed_area(hole) for hole in ladder.holes[0]) == pytest.approx([140.0 * 140.0] * 4)
    # two rails of 6 m and five rungs of 1.5 m, 10 cm wide, less what the joints share
    assert ladder.plan_area_cm2 == pytest.approx(610.0 * 160.0 - 4 * 140.0 * 140.0, rel=2e-3)
    # the ends stop 6 cm apart at a corner: over half the stroke's width, so it stays OPEN …
    assert len(gap.footprints) == 1 and gap.holes == ()
    assert gap.path[0] == pytest.approx((gap.path[-1][0], gap.path[-1][1] + 6.0))
    # … where 2 cm (the nearly closed fence) closes: the strokes of the two sides overlap
    assert nearly.path[0] == pytest.approx((nearly.path[-1][0], nearly.path[-1][1] + 2.0))
    assert ladder.path_width_cm == gap.path_width_cm == 10.0

    # fix round 3: the two butt ends meet corner to corner — one point, 10 cm above the start
    meets = _by_name(snapshot, "Fence that meets itself")
    assert meets.path[0] == pytest.approx((meets.path[-1][0], meets.path[-1][1] + 10.0))
    assert [len(ring) for ring in meets.footprints] == [20] and meets.holes == ()
    assert "outline_resolved" not in meets.params and meets.path_width_cm == 10.0
    # 1,010 cm of fence, 10 cm wide, less the mitres — and less the hair it is drawn in by
    assert 10082.842 - 5.0 < meets.plan_area_cm2 < 10082.842 - 3.0
    assert {(0.002, 149.998), (-0.002, 150.002)} <= set(meets.footprints[0])  # the ends, apart

    bed = _by_name(snapshot, "Turned raised bed")
    assert bed.transform.rotation_deg == 30.0
    children = [r for r in snapshot.values() if r.parent_id == bed.item_id]
    assert sorted(str(r.params["species_name"]) for r in children) == ["Basil", "Tomato"]
    pot = _by_name(snapshot, "Pot")
    (herb,) = [r for r in snapshot.values() if r.parent_id == pot.item_id]
    assert herb.params["species_name"] == "Rosemary" and pot.params["radius_cm"] == 30.0

    hedge = _by_name(snapshot, "L-shaped hedge")
    assert len(hedge.footprints[0]) == 6 and hedge.holes == ()
    assert hedge.plan_area_cm2 == pytest.approx(900.0 * 300.0 + 400.0 * 400.0)  # concave: not its hull


def test_g8_the_untouched_plan_snapshots_identically_100_times(plan) -> None:
    scene, first, _items = plan
    for _ in range(100):
        again = snapshot_records(scene, JUNE)
        assert again == first and list(again) == list(first)
        assert diff(first, again).is_empty and diff(again, first).is_empty


def test_g7_every_mesh_validates_reaches_its_height_and_covers_its_footprint(plan) -> None:
    _scene, snapshot, _items = plan
    solids = 0
    for record in snapshot.values():
        assert all(is_simple_ring(ring) and signed_area(ring) > 0.0 for ring in record.footprints)
        # the contract's promise, as the one predicate states it — for every region of every record
        assert all(is_buildable_region(outer, holes) for outer, holes in record.regions), record.name
        parts = verify_builder(default_builder, record, plan_margin_cm=0.0)  # nothing outside at all
        assert bool(parts) is (record.height_cm is not None), record.name
        for part in parts:
            part.validate()
            assert float(part.mesh.bounds()[1][2]) == pytest.approx(record.height_cm, rel=1e-6)
        # #627: the solid is the tinted sides and the fill cap - the union's UP
        # triangles are the cap (a ground pond's water is its own part)
        if parts:
            cap = Mesh.merge([part.mesh for part in parts])
            assert _cap_area(cap) == pytest.approx(record.plan_area_cm2, rel=1e-6), record.name
            _assert_walls_face_away_from_the_solid(
                Mesh.merge([part.mesh for part in parts if not part.fill_texture]), record)
            solids += 1
    assert solids >= 12  # two houses, six fences, bed, pot, hedge, plants with a height


def test_g4_transform_and_local_rings_reproduce_the_2d_footprints(plan) -> None:
    _scene, snapshot, items = plan
    worst_exact = worst_strip = 0.0
    resolved = touched = 0
    for item_id, record in snapshot.items():
        expected = item_footprints(items[item_id], JUNE)
        posed = _rings_of(record)
        if record.params.get("outline_resolved"):
            # NOT the drawn ring, on purpose: its rings run along the drawn outline
            # (to the clipper's grid and the hair by which touching parts are drawn
            # apart), and they cover the ground the outline fills — by a raster of
            # its winding number, no clipper involved
            (drawn,) = expected
            assert max(_boundary_distance(list(ring), list(drawn)) for ring in posed) <= 3e-3
            low_x, low_y = min(x for x, _y in drawn), min(y for _x, y in drawn)
            moved = [(x - low_x, y - low_y) for x, y in drawn]
            assert record.plan_area_cm2 == pytest.approx(_winding_area(moved, step=0.25), rel=2e-3)
            resolved += 1
            continue
        assert len(posed) == len(expected), record.name  # every ring: outers AND holes
        if record.shape == "polyline":
            if record.name == "Fence that meets itself":
                # the 2D ring touches itself where the ends meet; the record's is that ring
                # drawn in by 0.002 cm — the same boundary to within the hair and the grid
                (ring,), (drawn,) = expected, posed
                assert not is_simple_ring(tuple(ring)) and is_simple_ring(tuple(drawn))
                touched += 1
            worst_strip = max(worst_strip, _strip_deviation(posed, expected))
            centre_line = [(p.x(), p.y()) for p in
                           (items[item_id].mapToScene(q) for q in items[item_id].points)]
            worst_exact = max(worst_exact, _ring_deviation(
                pose_ring(record.transform, record.path), centre_line))
            # the stroke's area, read even-odd from the 2D rings, is the record's
            assert record.plan_area_cm2 == pytest.approx(_signed_area_sum(expected), rel=5e-4)
        else:
            worst_exact = max(worst_exact, max(
                _ring_deviation(ring, scene_ring)
                for ring, scene_ring in zip(posed, expected, strict=True)))
    assert worst_exact <= 1e-6, worst_exact
    assert worst_strip <= 3e-3, worst_strip
    assert resolved == 1  # the crossed house, and nothing else
    assert touched == 1  # the fence that meets itself


def test_the_pipeline_adds_every_record_once_then_says_nothing(plan) -> None:
    scene, snapshot, _items = plan
    sink = RecordingSink()
    sync = SceneSync(sink, validate=True)
    result = sync.apply(snapshot)
    assert result == SceneDiff(added=tuple(snapshot)) and sync.failures == {}
    assert sink.ops() == [("begin", None), *[("add", i) for i in snapshot], ("commit", None)]
    sink.clear_calls()
    for _ in range(3):
        assert sync.apply(snapshot_records(scene, JUNE)).is_empty
    assert sink.calls == [] and sink.state() == sync.expected_state()


def test_turning_the_house_in_the_loaded_plan_is_one_transform_entry(plan) -> None:
    """The loaded house and its loaded ridge item, turned by the app's own rule."""
    scene, before, items = plan
    (house,) = [i for i in items.values() if getattr(i, "name", "") == "House"]
    house._apply_rotation(205.0)
    after = snapshot_records(scene, JUNE)
    assert diff(before, after) == SceneDiff(transform=(str(house.item_id),))
    assert after[str(house.item_id)].transform.rotation_deg == 205.0


@pytest.mark.parametrize("name", ["Crossed house", "Ladder fence", "Fence with a gap",
                                  "Fence that meets itself"])
def test_moving_or_turning_a_round_2_item_is_one_transform_entry(plan, name: str) -> None:
    """A resolved outline and a stroke with four holes are still item-local
    geometry: a move or a turn of the loaded item changes its pose and nothing else."""
    scene, before, items = plan
    (item,) = [i for i in items.values() if getattr(i, "name", "") == name]
    item_id = str(item.item_id)
    item.moveBy(37.5, -21.25)
    moved = snapshot_records(scene, JUNE)
    assert diff(before, moved) == SceneDiff(transform=(item_id,))
    item._apply_rotation(33.0)
    turned = snapshot_records(scene, JUNE)
    assert diff(moved, turned) == SceneDiff(transform=(item_id,))
    assert turned[item_id].footprints == before[item_id].footprints
    assert turned[item_id].holes == before[item_id].holes
