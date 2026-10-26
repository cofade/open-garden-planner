"""Build budget of the plant silhouettes (Phase 17 L1.7, #385, gate G7).

Every plant of the two bench plans goes through the real pipeline —
``snapshot_records`` → ``SceneSync`` → ``RecordingSink`` with the plant builder
registered — and five things are pinned:

- **a first build** (nothing remembered: the shape cache is cleared before each
  run) of all plants of a plan, at two dates;
- **one daily scrub tick**: the plan date moves on by one day and the pipeline
  applies the new records. This is what a date slider costs per step, and what
  the workspace story (L1.3) schedules against. Two ways: *warm* — the scrub as
  it happens, the cache holding what earlier days built (a plant that grew is
  the remembered shape scaled; it is rebuilt only when its proportion crossed a
  ``PROPORTION_STEP``) — and *cold* — the cache cleared before the tick, so
  every plant that grew is rebuilt from nothing (the cost before the cache
  existed, and of the first tick after an eviction);
- **a scrub beyond the cache's cap**: with a cap that holds half the plants that
  grow, a warm tick rebuilds about that half — the overflow — and not every
  plant (which is what a plain least-recently-used cache does at its cap: a
  cliff, one plant past it);
- **triangles**: no plant over ``TRIANGLE_BUDGET``, and the plan totals;
- **a date change regrows only what grew**: scrubbing June → December reaches
  the sink as one ``replace_geometry`` per plant whose height or canopy changed
  and nothing else — a plant that did not grow is not rebuilt.

Measured on the dev box (Windows 11, Python 3.12.9, 2026-10-11) with every core
busy — other agents' test runs shared the machine, CPU load 96 % — medians, in
milliseconds and in REFERENCE UNITS (``reference_ms``: a fixed numpy workload
timed at the same moment, 108–135 ms then):

===============  ======  =====================  ================  ================
plan             plants  first build            daily tick, warm  daily tick, cold
===============  ======  =====================  ================  ================
``bench_small``  61      221–236 ms, 2.0        6.5 ms, 0.053     142 ms, 1.05
``bench_large``  320     1,210–1,222 ms, 10.8   15.2 ms, 0.134    342 ms, 3.17
===============  ======  =====================  ================  ================

Per tick 31 of ``bench_small``'s and 80 of ``bench_large``'s plants change size;
warm, 0.5 and 0.9 of them are rebuilt (their proportion crossed a step) and the
others scaled. The warm tick's 95th percentile was 15 ms and 25 ms.

On a quiet machine every number is lower — by about 3.5: the builder before the
shape cache read 329–333 ms for a first build of ``bench_large`` on a quiet
machine, and this one costs the same per first build to within 12 % (compared
in one process, interleaved). No quiet reading of THIS builder exists; that is
why the budgets are stated in reference units — work done at the same moment —
and not in milliseconds: about TWICE the units measured. A tripwire for a
builder that starts looping in Python or a cache that stops hitting, in
whatever hour it runs — not a frame budget. What does not depend on the machine
at all is asserted as well: the COUNTS — exactly where they are exact (a first
build builds every plant once; a cold tick builds every plant that changed),
and as a bound where they are not (warm, at most 10 % of the plants that
changed are rebuilt: measured 1.6 % and 1.1 %) — and the warm : cold ratio.
Timing conventions otherwise as in
``test_scene3d_snapshot_budget.py`` (a median; × 3 on CI runners; × 10 under a
line tracer, where a timing measures the tracer).
"""

from __future__ import annotations

import os
import statistics
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.plant_art import PLANT_KINDS
from open_garden_planner.core.scene3d import BuilderRegistry, Record, RecordingSink, SceneSync, diff
from open_garden_planner.core.scene3d.builders.plants import (
    PART_PLACEHOLDER,
    TRIANGLE_BUDGET,
    clear_shape_cache,
    register,
    resize_shape_cache,
    shape_cache_info,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.view3d.snapshot import snapshot_records
from tests.perf.test_scene3d_snapshot_budget import budget_factor, traced

PLANS = Path(__file__).resolve().parents[1] / "fixtures" / "plans"
JUNE, DECEMBER = date(2026, 6, 21), date(2026, 12, 21)
#: The scrub that is timed: this many consecutive days from 1 May 2026 — spring,
#: when the bench plans' annuals grow fastest.
SCRUB_START, SCRUB_DAYS = date(2026, 5, 1), 30
_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
#: plan → (plants, plants that grow June → December, triangles in June,
#:         budgets in REFERENCE UNITS: first build, warm daily tick, cold daily tick)
BUDGETS = {
    "bench_small.ogp": (61, 29, 68_402, 4.0, 0.12, 2.2),
    "bench_large.ogp": (320, 80, 291_652, 22.0, 0.28, 6.5),
}
_REFERENCE = np.random.Generator(np.random.PCG64(0)).random((4000, 3))


def reference_ms() -> float:
    """One run of a fixed numpy workload of the kind a plant builder does —
    element-wise float64 on a few thousand vertices, 400 times over. The UNIT the
    time budgets are stated in: on a shared machine everything slows down
    together (on this box a first build of 369 plants took 916 ms of wall time
    and 828 ms of CPU time with every core busy: the process is not waiting, it
    is slower), so a bound in milliseconds is either too tight for the busy hour
    or says nothing in the quiet one. A bound in units of work done at the same
    moment says the same thing in both."""
    start = time.perf_counter()
    for _ in range(400):
        length = np.linalg.norm(_REFERENCE, axis=1, keepdims=True)
        turned = np.cross(_REFERENCE / length, _REFERENCE[::-1])
        float(np.hypot(turned[:, 0], turned[:, 1]).sum())
    return (time.perf_counter() - start) * 1000.0


def unit_ms() -> float:
    """The reference unit right now: the median of five runs."""
    return statistics.median(reference_ms() for _ in range(5))


def plant_registry() -> BuilderRegistry:
    registry = BuilderRegistry()
    register(registry)
    return registry


def plants_of(records: dict[str, Record]) -> dict[str, Record]:
    return {item_id: record for item_id, record in records.items() if record.kind in PLANT_KINDS}


def triangle_count(sink: RecordingSink) -> tuple[int, int]:
    """(all triangles, the largest plant's) of what the sink holds."""
    counts = [sum(part.mesh.triangle_count for part in sink.item(item_id).parts)
              for item_id in sink.item_ids()]
    return sum(counts), max(counts)


def factor() -> float:
    return budget_factor(is_traced=traced(), is_ci=_IS_CI)


@pytest.fixture(params=sorted(BUDGETS))
def plan(request: pytest.FixtureRequest, qtbot) -> tuple[CanvasScene, str]:  # noqa: ARG001
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / request.param)
    return scene, request.param


class TestPlantBuildBudget:
    @pytest.mark.perf
    def test_a_first_build_of_every_plant_of_a_plan(self, plan: tuple[CanvasScene, str]) -> None:
        scene, name = plan
        plants, _grow, triangles, budget_units, _warm, _cold = BUDGETS[name]
        for at in (JUNE, DECEMBER):
            records = plants_of(snapshot_records(scene, at))
            assert len(records) == plants
            times, sink = [], RecordingSink()
            unit = unit_ms()
            for _ in range(5):
                clear_shape_cache()                       # nothing remembered: a first build
                sink = RecordingSink()
                sync = SceneSync(sink, plant_registry())
                start = time.perf_counter()
                sync.apply(records)
                times.append((time.perf_counter() - start) * 1000.0)
                assert sync.build_count == plants and not sync.failures
                assert shape_cache_info()[:2] == (0, plants)   # every plant was built, none reused
            unit = statistics.median([unit, unit_ms()])
            median_ms = statistics.median(times)
            total, largest = triangle_count(sink)
            print(f"\n{name} at {at}: {plants} plants, {total} triangles (largest {largest}), "
                  f"first build median {median_ms:.0f} ms (min {min(times):.0f}, max {max(times):.0f})"
                  f" = {median_ms / unit:.2f} units of {unit:.0f} ms")
            assert largest <= TRIANGLE_BUDGET and total <= plants * TRIANGLE_BUDGET
            if at == JUNE:
                assert total == triangles
            assert median_ms / unit <= budget_units * factor(), (
                f"{name}: a first build of {plants} plants took {median_ms:.0f} ms = "
                f"{median_ms / unit:.2f} reference units (median of 5), "
                f"budget {budget_units * factor():.1f}")

    @pytest.mark.perf
    def test_one_daily_scrub_tick(self, plan: tuple[CanvasScene, str]) -> None:
        """The plan date moves on by one day, ``SCRUB_DAYS`` times: what the pipeline
        does per tick (records in, sink calls out), warm and cold."""
        scene, name = plan
        plants, _grow, _triangles, _first, warm_budget, cold_budget = BUDGETS[name]
        days = [SCRUB_START + timedelta(days=n) for n in range(SCRUB_DAYS + 1)]
        snapshots = [plants_of(snapshot_records(scene, day)) for day in days]
        results: dict[str, tuple[float, float]] = {}
        for mode in ("warm", "cold"):
            unit = unit_ms()
            clear_shape_cache()
            sink = RecordingSink()
            sync = SceneSync(sink, plant_registry())
            sync.apply(snapshots[0])
            times, rebuilt, built_shapes = [], [], []
            for records in snapshots[1:]:
                if mode == "cold":
                    clear_shape_cache()
                misses_before = shape_cache_info()[1]
                builds_before = sync.build_count
                start = time.perf_counter()
                sync.apply(records)
                times.append((time.perf_counter() - start) * 1000.0)
                rebuilt.append(sync.build_count - builds_before)
                built_shapes.append(shape_cache_info()[1] - misses_before)
                assert not sync.failures
            unit = statistics.median([unit, unit_ms()])
            median_ms = statistics.median(times)
            p95_ms = sorted(times)[int(0.95 * (len(times) - 1))]
            results[mode] = (median_ms, p95_ms)
            print(f"\n{name}, daily tick {mode}: {statistics.mean(rebuilt):.1f} of {plants} plants "
                  f"change per tick, {statistics.mean(built_shapes):.1f} shapes built per tick — "
                  f"median {median_ms:.1f} ms, p95 {p95_ms:.1f} ms, max {max(times):.1f} ms"
                  f" = {median_ms / unit:.3f} units of {unit:.0f} ms")
            assert min(rebuilt) > 0                       # the scrub does make plants grow
            if mode == "cold":
                assert built_shapes == rebuilt            # every plant that grew was built anew
            else:
                # the cache's whole point: nearly every plant that grew was SCALED, not
                # rebuilt — only those whose proportion crossed a step (measured: 1.6 % and
                # 1.1 % of the plants that changed; the bound is not exact, it is roomy)
                assert sum(built_shapes) <= 0.10 * sum(rebuilt), (sum(built_shapes), sum(rebuilt))
            budget = (warm_budget if mode == "warm" else cold_budget) * factor()
            assert median_ms / unit <= budget, (
                f"{name}: a {mode} daily tick took {median_ms:.1f} ms = {median_ms / unit:.3f} "
                f"reference units (median of {SCRUB_DAYS}), budget {budget:.2f}")
        # and warm is what it is for: several times cheaper than cold
        assert results["warm"][0] <= 0.5 * results["cold"][0], results

    def test_beyond_the_cap_a_tick_rebuilds_the_overflow_not_everything(
        self, plan: tuple[CanvasScene, str]
    ) -> None:
        """More growing plants than the cache's cap holds: the scrub keeps as many
        shapes as fit and rebuilds the rest, tick after tick — it degrades by the
        overflow. A plain least-recently-used cache rebuilds EVERY growing plant on
        every tick from one plant past its cap (the scrub asks for them in the same
        order each time, so what it drops is what it needs next)."""
        scene, name = plan
        days = [SCRUB_START + timedelta(days=n) for n in range(13)]
        snapshots = [plants_of(snapshot_records(scene, day)) for day in days]

        def scrub() -> tuple[list[int], list[int]]:
            clear_shape_cache()
            sync = SceneSync(RecordingSink(), plant_registry())
            sync.apply(snapshots[0])
            changed, built = [], []
            for records in snapshots[1:]:
                misses, builds = shape_cache_info().misses, sync.build_count
                sync.apply(records)
                changed.append(sync.build_count - builds)
                built.append(shape_cache_info().misses - misses)
            return changed, built

        try:
            changed, built = scrub()                       # the cap far away: warm
            assert sum(built) <= 0.10 * sum(changed)
            info = shape_cache_info()
            growing = statistics.median(changed)
            cap = int(info.bytes / info.shapes * growing / 2.0)     # about half the growing plants
            resize_shape_cache(cap)
            changed, built = scrub()
            settled_changed, settled_built = sum(changed[3:]), sum(built[3:])   # past the warm-up
            print(f"\n{name}: {growing:.0f} plants grow per tick, a cap of {cap / 1e6:.1f} MB "
                  f"(about half of them): {settled_built / len(built[3:]):.1f} rebuilt per tick, "
                  f"{shape_cache_info().shapes} shapes held")
            assert shape_cache_info().bytes <= cap
            # the overflow, give or take the plants' different sizes — and not all of them
            assert 0.2 * settled_changed <= settled_built <= 0.8 * settled_changed, (changed, built)
        finally:
            resize_shape_cache()
            clear_shape_cache()

    def test_a_warm_tick_gives_what_a_cold_build_gives(self, plan: tuple[CanvasScene, str]) -> None:
        """Remembering changes how long a tick takes, never what the sink holds."""
        scene, _name = plan
        days = [SCRUB_START + timedelta(days=n) for n in (0, 1, 2, 9, 30)]
        clear_shape_cache()
        warm_sink = RecordingSink()
        warm = SceneSync(warm_sink, plant_registry(), validate=True)
        for day in days:
            records = plants_of(snapshot_records(scene, day))
            warm.apply(records)
            assert not warm.failures
            clear_shape_cache()
            cold_sink = RecordingSink()
            cold = SceneSync(cold_sink, plant_registry(), validate=True)
            cold.apply(records)
            # (the clear above also makes the next warm tick start cold — on purpose:
            # the two are compared tick by tick, in whatever state the cache is)
            assert warm_sink.state() == cold_sink.state()

    def test_every_bench_plant_is_a_valid_real_plant(self, plan: tuple[CanvasScene, str]) -> None:
        """With ``validate=True`` no builder fails, and no bench plant is a
        placeholder: every one has a species and so a height."""
        scene, name = plan
        for at in (JUNE, DECEMBER):
            sink = RecordingSink()
            sync = SceneSync(sink, plant_registry(), validate=True)
            sync.apply(plants_of(snapshot_records(scene, at)))
            assert not sync.failures, {k: str(v.error) for k, v in sync.failures.items()}
            assert len(sink.item_ids()) == BUDGETS[name][0]
            for item_id in sink.item_ids():
                held = sink.item(item_id)
                assert held.parts and all(p.name != PART_PLACEHOLDER for p in held.parts)
                top = max(float(p.mesh.positions[:, 2].max()) for p in held.parts)
                assert top == pytest.approx(sync.records[item_id].height_cm, rel=1e-5)

    def test_a_date_change_regrows_only_the_plants_that_grew(
        self, plan: tuple[CanvasScene, str]
    ) -> None:
        scene, name = plan
        plants, grow = BUDGETS[name][:2]
        june = plants_of(snapshot_records(scene, JUNE))
        december = plants_of(snapshot_records(scene, DECEMBER))
        grown = diff(june, december)
        assert len(grown.geometry) == grow
        assert not (grown.added or grown.removed or grown.transform or grown.material)
        sink = RecordingSink()
        sync = SceneSync(sink, plant_registry(), validate=True)
        sync.apply(june)
        assert sync.build_count == plants
        before = {item_id: sink.item(item_id).parts for item_id in sink.item_ids()}
        sink.clear_calls()
        sync.apply(december)
        assert sink.ops() == [("begin", None),
                              *(("replace_geometry", item_id) for item_id in grown.geometry),
                              ("commit", None)]
        assert sync.build_count == plants + grow          # one build per grown plant, no more
        for item_id in sink.item_ids():
            if item_id in grown.geometry:
                assert sink.item(item_id).parts != before[item_id]
                assert december[item_id].height_cm != june[item_id].height_cm or (
                    december[item_id].params["radius_cm"] != june[item_id].params["radius_cm"])
            else:
                assert sink.item(item_id).parts is before[item_id]   # not rebuilt, not re-sent
        sink.clear_calls()
        sync.apply(december)                                # the same date again: silence
        assert sink.ops() == [] and sync.build_count == plants + grow
