"""Snapshot budget of the 3D pipeline (Phase 17 L1.1, #385, gate G5).

``snapshot_records`` runs on the GUI thread after every edit, before any 3D
work, so it has a budget of its own: median ≤ 15 ms on
``tests/fixtures/plans/bench_small.ogp`` (98 records) and ≤ 60 ms on
``bench_large.ogp`` (424 records). Measured on the dev box (Windows 11,
2026-10-11, 30 runs each, idle machine): 2.2 ms / 9.6 ms median and 4.1 /
10.8 ms max on Python 3.12.9, 2.3 / 9.6 ms median on 3.11.9 — about a sixth of
the budget. A third of it is not 3D code at all but the shared height and canopy
resolvers (``effective_height_cm`` 18 %, ``plant_canopy_radius_cm`` 16 % under
cProfile → ``core/growth_model``), which the 2D shadow overlay pays as well.

Conventions of ``tests/perf/test_nfr_budgets.py``: the ``perf`` marker, a median
(another pytest run may share the machine), and the same x3 allowance on CI
runners.

One addition, because this code is pure Python: **a timing taken under a line
tracer measures the tracer.** Under ``pytest --cov=open_garden_planner
--cov-branch`` — how CI's coverage job runs the suite — the same snapshot took
17 ms / 78 ms median here (8-9x; measured on the story's first version, when
the untraced medians were 2.1 / 8.6 ms), above the budget of the untraced
product. So
when a tracer is active the assertion is only a tripwire against a blow-up, at
ten times the budget; the gate itself is asserted by every untraced run (a
developer's ``pytest``, CI's test job).
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.scene3d import diff
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.view3d.snapshot import snapshot_records

PLANS = Path(__file__).resolve().parents[1] / "fixtures" / "plans"
AT = date(2026, 6, 21)
RUNS = 30
WARMUP = 3

_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
CI_FACTOR = 3.0
TRACE_FACTOR = 10.0
#: plan → (records, median budget in ms)
BUDGETS = {"bench_small.ogp": (98, 15.0), "bench_large.ogp": (424, 60.0)}


def traced() -> bool:
    """True when a line tracer is active (coverage, a debugger)."""
    if sys.gettrace() is not None:
        return True
    monitoring = getattr(sys, "monitoring", None)  # Python 3.12+: coverage's sysmon core
    return monitoring is not None and monitoring.get_tool(monitoring.COVERAGE_ID) is not None


def budget_factor(*, is_traced: bool, is_ci: bool) -> float:
    """What the budget is multiplied with: 1 for the product on a developer's
    machine, ``CI_FACTOR`` on a CI runner, ``TRACE_FACTOR`` under a tracer."""
    if is_traced:
        return TRACE_FACTOR
    return CI_FACTOR if is_ci else 1.0


@pytest.fixture(params=sorted(BUDGETS))
def plan(request: pytest.FixtureRequest, qtbot) -> tuple[CanvasScene, int, float]:  # noqa: ARG001
    records, budget_ms = BUDGETS[request.param]
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / request.param)
    return scene, records, budget_ms * budget_factor(is_traced=traced(), is_ci=_IS_CI)


def _timed(run, runs: int = RUNS) -> tuple[float, float]:
    """(median, max) wall time of ``run`` in milliseconds."""
    for _ in range(WARMUP):
        run()
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        run()
        times.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(times), max(times)


def test_a_tracer_is_what_widens_the_budget_and_it_is_detected(monkeypatch) -> None:
    """The logic around the gate — not its numbers, which a test can only repeat.

    ``traced()`` is what decides whether the timing below asserts the product's
    budget or only a tripwire, so both of its answers are exercised: with a trace
    function installed it says yes; with none (and no coverage tool on
    ``sys.monitoring``) it says no — and then nothing but a CI runner widens the
    budget, and a tracer on a CI runner is not widened twice.
    """
    monkeypatch.setattr(sys, "gettrace", lambda: (lambda *_args: None))
    assert traced()
    monkeypatch.setattr(sys, "gettrace", lambda: None)
    monitoring = getattr(sys, "monitoring", None)
    if monitoring is not None:  # Python 3.12+
        monkeypatch.setattr(monitoring, "get_tool", lambda _tool_id: None)
    assert not traced()
    if monitoring is not None:
        monkeypatch.setattr(monitoring, "get_tool", lambda _tool_id: "coverage")
        assert traced()

    local = budget_factor(is_traced=False, is_ci=False)
    on_ci = budget_factor(is_traced=False, is_ci=True)
    under_tracer = budget_factor(is_traced=True, is_ci=False)
    assert local == 1.0  # the product's budget, as the gate states it
    assert local < on_ci < under_tracer
    assert budget_factor(is_traced=True, is_ci=True) == under_tracer  # not multiplied


@pytest.mark.perf
class TestSnapshotBudget:
    def test_snapshot_records_median(self, plan: tuple[CanvasScene, int, float]) -> None:
        scene, records, budget_ms = plan
        assert len(snapshot_records(scene, AT)) == records
        median_ms, max_ms = _timed(lambda: snapshot_records(scene, AT))
        assert median_ms <= budget_ms, (
            f"snapshot_records median {median_ms:.2f} ms (max {max_ms:.2f} ms) over {RUNS} runs "
            f"exceeds the {budget_ms:.0f} ms budget for {records} records"
        )

    def test_a_tick_without_changes_fits_the_same_budget(
        self, plan: tuple[CanvasScene, int, float]
    ) -> None:
        """What every edit elsewhere in the app costs the 3D pipeline when nothing
        it shows changed: one snapshot plus one diff — and no sink call."""
        scene, _records, budget_ms = plan
        last = snapshot_records(scene, AT)

        def tick() -> None:
            assert diff(last, snapshot_records(scene, AT)).is_empty

        median_ms, max_ms = _timed(tick)
        assert median_ms <= budget_ms, (
            f"snapshot + diff median {median_ms:.2f} ms (max {max_ms:.2f} ms) exceeds "
            f"{budget_ms:.0f} ms"
        )

    def test_a_date_scrub_tick_fits_the_same_budget_and_cuts_nothing(
        self, plan: tuple[CanvasScene, int, float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scrubbing the sim date gives every DATED plant a new canopy on every tick
        (bench_large: 80 of its 424 records). After fix round 3 the snapshot cut a
        24-gon for each new radius, and this tick went from 12 ms to 33; a ring that
        is convex by construction is judged by arithmetic now. The op count is the
        gate — not one region is cut by the snapshot — and the budget the statement
        (a new date on every run, so nothing is answered from memory)."""
        from open_garden_planner.core.scene3d import polygon

        scene, records, budget_ms = plan
        cuts = []
        real = polygon._cut
        monkeypatch.setattr(polygon, "_cut", lambda *args: (cuts.append(1), real(*args))[1])
        day = date(2026, 3, 1)
        last = [snapshot_records(scene, day)]
        cuts.clear()  # the first snapshot cuts the plan's polygons and strokes, once
        changed: list[int] = []
        ticks = iter(range(1, 1_000))

        def tick() -> None:
            now = snapshot_records(scene, day + timedelta(days=3 * next(ticks)))
            changed.append(len(diff(last[0], now).geometry))
            last[0] = now

        median_ms, max_ms = _timed(tick)
        assert cuts == []
        if records == 424:
            assert statistics.median(changed) >= 40  # … and it IS a scrub: the plants change every tick
        assert median_ms <= budget_ms, (
            f"a date-scrub snapshot + diff: median {median_ms:.2f} ms (max {max_ms:.2f} ms) exceeds "
            f"{budget_ms:.0f} ms"
        )
