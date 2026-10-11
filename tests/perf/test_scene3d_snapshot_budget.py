"""Snapshot budget of the 3D pipeline (Phase 17 L1.1, #385, gate G5).

``snapshot_records`` runs on the GUI thread after every edit, before any 3D
work, so it has a budget of its own: median ≤ 15 ms on
``tests/fixtures/plans/bench_small.ogp`` (99 records) and ≤ 60 ms on
``bench_large.ogp`` (425 records). Measured on the dev box (Windows 11,
2026-10-11, 30 runs each, idle machine): 2.1 ms / 8.6 ms median and 3.0 /
10.6 ms max on Python 3.12.9, 2.0 / 9.1 ms median on 3.11.9 — a seventh of the
budget. What dominates is not the 3D code: ~40 % is the shared height and
canopy resolvers (``effective_height_cm``, ``plant_canopy_radius_cm`` →
``core/growth_model``), which the 2D shadow overlay pays as well.

Conventions of ``tests/perf/test_nfr_budgets.py``: the ``perf`` marker, a median
(another pytest run may share the machine), and the same x3 allowance on CI
runners.

One addition, because this code is pure Python: **a timing taken under a line
tracer measures the tracer.** Under ``pytest --cov=open_garden_planner
--cov-branch`` — how CI's coverage job runs the suite — the same snapshot took
17 ms / 78 ms median here (8-9x), above the budget of the untraced product. So
when a tracer is active the assertion is only a tripwire against a blow-up, at
ten times the budget; the gate itself is asserted by every untraced run (a
developer's ``pytest``, CI's test job). ``budget_factor`` is pinned below so the
untraced local budget can never be relaxed by accident.
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from datetime import date
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
BUDGETS = {"bench_small.ogp": (99, 15.0), "bench_large.ogp": (425, 60.0)}


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


def test_the_untraced_local_budget_is_never_relaxed() -> None:
    """The gate is 15 / 60 ms. Only a CI runner or a tracer may widen it."""
    assert budget_factor(is_traced=False, is_ci=False) == 1.0
    assert budget_factor(is_traced=False, is_ci=True) == CI_FACTOR == 3.0
    assert budget_factor(is_traced=True, is_ci=False) == TRACE_FACTOR == 10.0
    assert budget_factor(is_traced=True, is_ci=True) == TRACE_FACTOR  # not multiplied
    assert BUDGETS == {"bench_small.ogp": (99, 15.0), "bench_large.ogp": (425, 60.0)}


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
