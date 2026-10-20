"""Build budget of the built world (Phase 17 L1.6, #385, gate G7).

Every built-world item of the two bench plans — buildings, fences, walls, beds,
containers, hedges — through ``SceneSync`` (production registry) into a
``RecordingSink``: how long the builders take and how many triangles they make.

Measured on the dev box (Windows 11, Python 3.12.9, 2026-10-11, 30 runs each;
INFORMATION, not assertions — the look pass will move the triangle counts):

==================  =====  =========  ======================  ===========
plan                items  triangles  median build (ms)       budget (ms)
==================  =====  =========  ======================  ===========
bench_small.ogp     15     16,874     9.8 idle / 18.4 loaded  40
bench_large.ogp     28     22,482     18.7 idle / 23.6 loaded  60
==================  =====  =========  ======================  ===========

("loaded": a second test run and a renderer sharing the machine.) Where the time
goes: a hedge at its 6,000-leaf cap (12,010 triangles) ~4 ms, a 24 m picket
fence ~1.5 ms, a raised bed ~0.4 ms (24 of them on bench_large), a house ~1 ms.

Three tripwires, each for a different failure:

- **time** (``perf`` marker, a median; x3 on a CI runner, x10 under a line
  tracer, as ``test_scene3d_snapshot_budget.py``): 40 / 60 ms — about twice the
  loaded medians. Review round 1 put these back from 60 / 90: the wider numbers
  had been chosen although the loaded medians were under the old ones, and with
  the CI factor a per-vertex Python loop would have passed them.
- **calls** (no clock, so it is the same on any machine): a builder makes a few
  hundred Python-level calls per item WHATEVER the item's size — 404 for a fence
  of 5 m and of 50 m. A loop over vertices shows up as calls that grow with the
  mesh. This replaces a test that compared the budget table with a copy of
  itself.
- **triangles**: each item within its family's stated budget
  (``builders.triangle_budget``) and each plan within a total; the structure —
  which kinds, how many items, which of them have a solid at all — is exact, the
  counts are ceilings.
"""

from __future__ import annotations

import collections
import statistics
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from open_garden_planner.core import ProjectManager, scene3d
from open_garden_planner.core.scene3d import Record, RecordingSink, SceneSync
from open_garden_planner.core.scene3d.builders import (
    BUILT_WORLD_KINDS,
    production_registry,
    triangle_budget,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.view3d.snapshot import snapshot_records
from tests.perf.test_scene3d_snapshot_budget import _IS_CI, budget_factor, traced
from tests.unit.scene3d_builder_cases import line_record, polygon_record, rectangle

PLANS = Path(__file__).resolve().parents[1] / "fixtures" / "plans"
AT = date(2026, 6, 21)
RUNS = 30
WARMUP = 3

#: plan → median build budget in ms (gate G7)
BUILD_BUDGET_MS: dict[str, float] = {"bench_small.ogp": 40.0, "bench_large.ogp": 60.0}
#: plan → the most triangles its whole built world may have
PLAN_TRIANGLE_BUDGET: dict[str, int] = {"bench_small.ogp": 25_000, "bench_large.ogp": 35_000}
#: plan → kind → how many items of it the plan holds (the fixtures' own content)
ITEMS: dict[str, dict[str, int]] = {
    "bench_small.ogp": {"CONTAINER_ROUND": 3, "FENCE": 2, "GARAGE_SHED": 1, "GARDEN_BED": 3,
                        "HEDGE_POLYGON": 1, "HOUSE": 1, "RAISED_BED": 3, "WALL": 1},
    "bench_large.ogp": {"FENCE": 1, "GARAGE_SHED": 1, "HEDGE_POLYGON": 1, "HOUSE": 1,
                        "RAISED_BED": 24},
}
#: A builder makes at most this many Python-level calls for one item of the bench
#: plans (measured: 302 … 1,483; a turned pot is the most). Not a function of size.
CALLS_PER_ITEM = 3_000
_SCENE3D = str(Path(scene3d.__file__).parent)


def built_world(plan: str) -> dict[str, Record]:
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / plan)
    return {item_id: record for item_id, record in snapshot_records(scene, AT).items()
            if record.kind in BUILT_WORLD_KINDS}


@pytest.fixture(params=sorted(BUILD_BUDGET_MS))
def plan(request: pytest.FixtureRequest, qtbot) -> tuple[str, dict[str, Record]]:  # noqa: ARG001
    return request.param, built_world(request.param)


def python_calls(function: Callable[[], object]) -> int:
    """How many calls (to Python and to C functions) the scene3d package makes while
    ``function`` runs. A profile hook, not a trace hook: it leaves coverage alone,
    and it counts events, so the answer does not depend on the machine."""
    count = 0

    def profiler(frame, event, _arg) -> None:  # noqa: ANN001
        nonlocal count
        if event in ("call", "c_call") and frame.f_code.co_filename.startswith(_SCENE3D):
            count += 1

    previous = sys.getprofile()
    sys.setprofile(profiler)
    try:
        function()
    finally:
        sys.setprofile(previous)
    return count


def calls_to_build(record: Record) -> int:
    registry = production_registry()
    sync = SceneSync(RecordingSink(), registry)
    made = python_calls(lambda: sync.apply({record.item_id: record}))
    assert not sync.failures
    return made


def test_triangles_per_kind(plan: tuple[str, dict[str, Record]]) -> None:
    name, records = plan
    sink = RecordingSink()
    sync = SceneSync(sink, production_registry(), validate=True)
    sync.apply(records)
    assert sync.failures == {}
    items: dict[str, int] = collections.Counter(record.kind for record in records.values())
    assert dict(items) == ITEMS[name]  # the structure: which kinds, how many of each
    total = 0
    for item_id, record in records.items():
        triangles = sum(part.mesh.triangle_count for part in sink.item(item_id).parts)
        budget = triangle_budget(record)
        assert budget is not None and triangles <= budget, (record.kind, triangles, budget)
        # … and the structure: an in-ground bed is ground, everything else has a solid
        assert (triangles == 0) == (record.kind == "GARDEN_BED"), record.kind
        total += triangles
    print(f"\n[G7] {name}: {len(records)} built-world items, {total} triangles "
          f"(plan budget {PLAN_TRIANGLE_BUDGET[name]})")
    assert total <= PLAN_TRIANGLE_BUDGET[name]


@pytest.mark.perf
def test_build_time_median(plan: tuple[str, dict[str, Record]]) -> None:
    name, records = plan
    budget_ms = BUILD_BUDGET_MS[name] * budget_factor(is_traced=traced(), is_ci=_IS_CI)
    registry = production_registry()

    def build_everything() -> None:
        sync = SceneSync(RecordingSink(), registry)
        sync.apply(records)
        assert sync.build_count == len(records) and not sync.failures

    for _ in range(WARMUP):
        build_everything()
    times = []
    for _ in range(RUNS):
        start = time.perf_counter()
        build_everything()
        times.append((time.perf_counter() - start) * 1000.0)
    median_ms = statistics.median(times)
    print(f"\n[G7] {name}: {len(records)} built-world items, median {median_ms:.2f} ms, "
          f"max {max(times):.2f} ms over {RUNS} runs (budget {budget_ms:.0f} ms)")
    assert median_ms <= budget_ms, (
        f"building {len(records)} built-world items of {name} took a median of {median_ms:.2f} ms "
        f"(max {max(times):.2f} ms), over the {budget_ms:.0f} ms budget"
    )


def test_no_builder_makes_more_calls_than_a_few_hundred_per_item(
    plan: tuple[str, dict[str, Record]]
) -> None:
    """The clock-free tripwire, on the bench plans: every item is built with a bounded
    number of Python-level calls. bench_large's hedge has 24,000 vertices and its fence
    16,000 — a loop over either would make that many calls and more."""
    _name, records = plan
    for record in records.values():
        made = calls_to_build(record)
        assert made <= CALLS_PER_ITEM, (record.kind, made)


@pytest.mark.parametrize(("small", "large"), [
    (line_record("FENCE", ((0.0, 0.0), (500.0, 0.0)), 120.0, style="WOODEN_FENCE"),
     line_record("FENCE", ((0.0, 0.0), (5000.0, 0.0)), 120.0, style="WOODEN_FENCE")),
    (line_record("FENCE", ((0.0, 0.0), (500.0, 0.0)), 120.0, style="METAL_FENCE"),
     line_record("FENCE", ((0.0, 0.0), (5000.0, 0.0)), 120.0, style="METAL_FENCE")),
    (line_record("FENCE", ((0.0, 0.0), (500.0, 0.0)), 120.0, style="CHAIN_LINK"),
     line_record("FENCE", ((0.0, 0.0), (5000.0, 0.0)), 120.0, style="CHAIN_LINK")),
    (line_record("FENCE", ((0.0, 0.0), (200.0, 0.0)), 150.0, style="HEDGE_FENCE"),
     line_record("FENCE", ((0.0, 0.0), (2000.0, 0.0)), 150.0, style="HEDGE_FENCE")),
    (polygon_record("HEDGE_POLYGON", rectangle(200.0, 60.0), 150.0),
     polygon_record("HEDGE_POLYGON", rectangle(2000.0, 60.0), 150.0)),
    (line_record("WALL", tuple((300.0 * i, 40.0 * (i % 2)) for i in range(3)), 200.0),
     line_record("WALL", tuple((300.0 * i, 40.0 * (i % 2)) for i in range(31)), 200.0)),
], ids=["picket", "metal", "chain-link", "hedge-fence", "hedge", "wall-30-segments"])
def test_python_calls_do_not_grow_with_the_vertex_count(small: Record, large: Record) -> None:
    """Ten times the fence, the hedge or the wall: several times the vertices, the SAME
    number of Python-level calls. (A footprint's corners are another matter — a house
    is ear-clipped corner by corner — which is why no building is in this list.)"""
    registry = production_registry()
    vertices = [sum(part.mesh.vertex_count for part in registry.build(record))
                for record in (small, large)]
    assert vertices[1] >= 2 * vertices[0]  # the pair really differs in size
    assert calls_to_build(large) == calls_to_build(small)


def test_the_call_count_sees_a_loop_over_vertices() -> None:
    """The tripwire trips: a builder that walks its vertices in Python — here a wrapper
    that touches every vertex of the real hedge once — is caught by the call count,
    on any machine."""
    record = polygon_record("HEDGE_POLYGON", rectangle(2000.0, 60.0), 150.0)
    honest = production_registry()
    looping = production_registry()
    real = looping.builder_for("HEDGE_POLYGON")

    def per_vertex(item: Record):  # noqa: ANN202
        parts = real(item)
        for part in parts:
            for position in part.mesh.positions:
                abs(float(position[2]))  # one C call per vertex
        return parts

    # The profile hook only counts frames of the scene3d package, so the loop has to
    # live there to be seen — as a real builder's would. Give the wrapper that home.
    per_vertex.__code__ = per_vertex.__code__.replace(co_filename=str(Path(_SCENE3D) / "looping.py"))
    looping.register("HEDGE_POLYGON", per_vertex, replace=True)

    def build(registry) -> int:  # noqa: ANN001
        sync = SceneSync(RecordingSink(), registry)
        return python_calls(lambda: sync.apply({record.item_id: record}))

    clean, caught = build(honest), build(looping)
    assert clean <= CALLS_PER_ITEM < caught
    assert caught - clean >= 24_000  # one call for each of the hedge's vertices
