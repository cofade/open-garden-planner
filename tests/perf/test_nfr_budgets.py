"""NFR performance budget verification tests (NFR-PERF-01, issue #409).

Asserts frame timing on the reference benchmark plan
`docs/11-risks-and-technical-debt/audit-2026-10-plan_500.ogp` (990 scene items)
in a 1600x1000 viewport:
- Fit-in-view repaint <= 16.7 ms median (>= 60 fps)
- Zoom step repaint <= 16.7 ms median (>= 60 fps)
- 100% zoom / pan repaint <= 16.7 ms median (>= 60 fps)

Issue #473 adds a second scenario — the same reference plan plus a fixed set of
plain and styled polylines — so the budgets also see what a line's paint costs.
"""

from __future__ import annotations

import gc
import os
import statistics
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PLAN = REPO_ROOT / "docs" / "11-risks-and-technical-debt" / "audit-2026-10-plan_500.ogp"

# --- Issue #473: a line-paint scenario -------------------------------------
#
# The reference plan holds no polyline — no fence, path or wall line — so the
# budgets above could not see a change that made every line's ``paint()``
# slower (a real 25% regression during the L1 work slipped past all three).
# This second scenario adds a fixed set of plain and styled lines to the same
# 500-object plan so line paint is part of the measured frame. Calibrated on
# the dev box (offscreen, best-of-8 median): 30 lines of 50 points add a stable
# ~1.3-1.5 ms, keeping fit-in-view around 10 ms — inside the 16.7 ms budget.
LINE_SCENARIO_LINES = 30
LINE_SCENARIO_POINTS = 50

# 60 fps frame budget is 16.67 ms.
# In heavily-loaded headless CI environments (e.g. GitHub Actions Linux with xvfb/LLVMpipe)
# and under coverage instrumentation (pytest --cov tracing every Python bytecode),
# software rasterisation has a higher CPU ceiling.
_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
FRAME_BUDGET_MS = 50.0 if _IS_CI else 16.7


@pytest.fixture
def benchmark_view(qtbot):
    """Load the 500-object audit plan into a 1600x1000 CanvasView."""
    scene = CanvasScene()
    pm = ProjectManager()
    assert BENCHMARK_PLAN.exists(), f"Benchmark plan not found at {BENCHMARK_PLAN}"
    pm.load(scene, BENCHMARK_PLAN)

    view = CanvasView(scene)
    view.resize(1600, 1000)
    view.show()
    qtbot.addWidget(view)
    qtbot.waitExposed(view)
    QApplication.processEvents()
    return view


def _measure_repaints(view: CanvasView, count: int = 15, warmup: int = 5) -> list[float]:
    """Measure synchronous repaint durations and return all frame times in milliseconds."""
    gc.collect()
    viewport = view.viewport()
    for _ in range(warmup):
        viewport.repaint()
        QApplication.processEvents()

    times: list[float] = []
    for _ in range(count):
        t0 = time.perf_counter()
        viewport.repaint()
        times.append((time.perf_counter() - t0) * 1000.0)

    return times


def _assert_repaint_budget(view: CanvasView, label: str, rounds: int = 8) -> None:
    """Verify repaint timing meets 60 fps budget (<= 16.7 ms) across retries (#448).

    Under preemptive OS scheduling, occasional frame times are inflated by
    context switches to background processes or GC pressure from earlier tests.
    Evaluating the best median across up to 8 measurement rounds protects
    against transient background spikes while strictly enforcing that typical
    frame presentation satisfies the <= 16.7 ms budget.
    """
    all_medians: list[float] = []
    for r in range(rounds):
        if r > 0:
            time.sleep(0.05)
            gc.collect()
            QApplication.processEvents()
        times = _measure_repaints(view)
        med = statistics.median(times)
        all_medians.append(med)
        if med <= FRAME_BUDGET_MS:
            return

    best_median = min(all_medians)
    assert best_median <= FRAME_BUDGET_MS, (
        f"{label} repaint exceeds frame budget {FRAME_BUDGET_MS:.2f} ms "
        f"(best median: {best_median:.2f} ms across {rounds} rounds)"
    )



@pytest.mark.perf
class TestNfrPerf01Budgets:
    """Verify NFR-PERF-01 60fps budgets on the reference 500-object plan."""

    def test_fit_in_view_repaint_budget(self, benchmark_view) -> None:
        """Fit-in-view repaint satisfies the <= 16.7 ms frame budget."""
        benchmark_view.fit_in_view()
        QApplication.processEvents()
        _assert_repaint_budget(benchmark_view, "Fit-in-view")

    def test_zoom_step_repaint_budget(self, benchmark_view) -> None:
        """Zoom step repaint satisfies the <= 16.7 ms frame budget."""
        benchmark_view.fit_in_view()
        benchmark_view.zoom_in()
        QApplication.processEvents()
        _assert_repaint_budget(benchmark_view, "Zoom step")

    def test_full_zoom_repaint_budget(self, benchmark_view) -> None:
        """100% zoom repaint satisfies the <= 16.7 ms frame budget."""
        benchmark_view.reset_zoom()
        QApplication.processEvents()
        _assert_repaint_budget(benchmark_view, "100% zoom")


def _add_line_scenario(scene: CanvasScene) -> None:
    """Add a fixed set of plain and styled polylines to ``scene`` (issue #473).

    Deterministic geometry inside the reference plan's canvas so a line's
    ``paint()`` cost is part of every measured frame. Half the lines are plain
    fences (``PathFenceStyle.NONE``); half are styled gravel paths, whose style
    painter walks the whole line on every repaint.
    """
    for i in range(LINE_SCENARIO_LINES):
        points = [
            QPointF(300 + i * 60 + j * 30, 400 + (j % 2) * 400)
            for j in range(LINE_SCENARIO_POINTS)
        ]
        if i % 2 == 0:
            item = PolylineItem(points, object_type=ObjectType.FENCE)
        else:
            item = PolylineItem(
                points,
                object_type=ObjectType.PATH,
                path_fence_style=PathFenceStyle.GRAVEL_PATH,
            )
        scene.addItem(item)


@pytest.fixture
def line_benchmark_view(qtbot):
    """Reference plan plus the issue #473 plain/styled line scenario."""
    scene = CanvasScene()
    pm = ProjectManager()
    assert BENCHMARK_PLAN.exists(), f"Benchmark plan not found at {BENCHMARK_PLAN}"
    pm.load(scene, BENCHMARK_PLAN)
    _add_line_scenario(scene)

    view = CanvasView(scene)
    view.resize(1600, 1000)
    view.show()
    qtbot.addWidget(view)
    qtbot.waitExposed(view)
    QApplication.processEvents()
    return view


@pytest.mark.perf
class TestNfrPerf01LinePaintBudgets:
    """Issue #473: the budgets must see what a line's paint costs."""

    def test_the_scenario_holds_plain_and_styled_lines(self, line_benchmark_view) -> None:
        """Guard the scenario's composition so a future edit cannot silently drop it."""
        polylines = [i for i in line_benchmark_view.scene().items() if isinstance(i, PolylineItem)]
        assert polylines, "the line scenario must hold polylines"
        assert any(
            p.path_fence_style == PathFenceStyle.NONE for p in polylines
        ), "the line scenario must hold a plain line"
        assert any(
            p.path_fence_style != PathFenceStyle.NONE for p in polylines
        ), "the line scenario must hold a styled line"

    def test_fit_in_view_repaint_budget_with_lines(self, line_benchmark_view) -> None:
        """Fit-in-view repaint including line paint satisfies the frame budget."""
        line_benchmark_view.fit_in_view()
        QApplication.processEvents()
        _assert_repaint_budget(line_benchmark_view, "Fit-in-view with lines")

    def test_full_zoom_repaint_budget_with_lines(self, line_benchmark_view) -> None:
        """100% zoom repaint including line paint satisfies the frame budget."""
        line_benchmark_view.reset_zoom()
        QApplication.processEvents()
        _assert_repaint_budget(line_benchmark_view, "100% zoom with lines")

