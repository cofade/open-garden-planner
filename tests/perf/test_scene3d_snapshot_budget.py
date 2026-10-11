"""Snapshot budget of the 3D pipeline (Phase 17 L1.1, #385, gate G5).

``snapshot_records`` runs on the GUI thread after every edit, before any 3D
work, so it has a budget of its own: median ≤ 15 ms on
``tests/fixtures/plans/bench_small.ogp`` (99 records) and ≤ 60 ms on
``bench_large.ogp`` (425 records). Measured on the dev box (Windows 11,
2026-10-11, 30 runs each, idle machine): 2.1 ms / 8.6 ms median and 3.0 /
10.6 ms max on Python 3.12.9, 2.0 / 9.1 ms median on 3.11.9 — a seventh of the
budget. Under coverage's branch tracer: 8.2 / 39.3 ms median (4-4.6x), still
inside it. What dominates is not the 3D code: ~40 % is the shared height and
canopy resolvers (``effective_height_cm``, ``plant_canopy_radius_cm`` →
``core/growth_model``), which the 2D shadow overlay pays as well.

Conventions of ``tests/perf/test_nfr_budgets.py``: the ``perf`` marker, a median
(another pytest run may share the machine), and the same x3 allowance on CI
runners (their coverage job traces every line).
"""

from __future__ import annotations

import os
import statistics
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
_CI_FACTOR = 3.0 if _IS_CI else 1.0
#: plan → (records, median budget in ms)
BUDGETS = {"bench_small.ogp": (99, 15.0), "bench_large.ogp": (425, 60.0)}


@pytest.fixture(params=sorted(BUDGETS))
def plan(request: pytest.FixtureRequest, qtbot) -> tuple[CanvasScene, int, float]:  # noqa: ARG001
    records, budget_ms = BUDGETS[request.param]
    scene = CanvasScene()
    ProjectManager().load(scene, PLANS / request.param)
    return scene, records, budget_ms * _CI_FACTOR


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
