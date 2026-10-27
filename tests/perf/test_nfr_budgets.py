"""NFR performance budget verification tests (NFR-PERF-01, issue #409).

Asserts frame timing on the reference benchmark plan
`tests/fixtures/plans/audit-2026-10-plan_500.ogp` (990 scene items)
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
from PyQt6.QtWidgets import QApplication, QGraphicsItem

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PLAN = REPO_ROOT / "tests" / "fixtures" / "plans" / "audit-2026-10-plan_500.ogp"

# --- Issue #473: a line-paint scenario -------------------------------------
#
# The reference plan holds no polyline — no fence, path or wall line — so the
# budgets above could not see a change that made every line's ``paint()``
# slower (a real 25% regression during the L1 work slipped past all three).
# This second scenario adds a fixed set of plain and styled lines to the same
# 500-object plan, with their item cache DISABLED so ``paint()`` runs on every
# measured frame (a cached line is never repainted — the defect this issue is
# about). Calibrated on the dev box (offscreen): 10 short plain fences and 1
# short styled gravel path add a stable ~5 ms. Styled paths walk the whole line
# each repaint (the unbounded cost tracked as #450), so an absolute per-frame
# budget for the line scenario is left to that issue; this scenario pins that
# line paint is *measured*.
LINE_SCENARIO_PLAIN = 10
LINE_SCENARIO_STYLED = 1
LINE_SCENARIO_POINTS = 8

# 60 fps frame budget is 16.67 ms.
# In heavily-loaded headless CI environments (e.g. GitHub Actions Linux with xvfb/LLVMpipe)
# and under coverage instrumentation (pytest --cov tracing every Python bytecode),
# software rasterisation has a higher CPU ceiling.
_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
FRAME_BUDGET_MS = 50.0 if _IS_CI else 16.7

# The per-command containment scan (#629) runs after EVERY executed/undone/redone command,
# so it must cost a fraction of a frame. Measured on the dev box: 0.9 ms on the reference
# plan (200 plants, none linked) and 2.8 ms for 300 unlinked plants in 30 beds. The bound is
# loose on purpose - it is there to catch the 330 ms shape-rebuild regression, not to time
# the machine (#448: viewport/machine timing drifts).
RESTACK_BUDGET_MS = 50.0 if _IS_CI else 12.0


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
    ``paint()`` cost is part of every measured frame. The scenario lines
    **disable their `DeviceCoordinateCache`**: every canvas item enables it by
    default, and the measurement warms the cache before timing, so a cached
    line is never repainted and a slower ``PolylineItem.paint()`` is invisible —
    the defect this issue is about.
    """
    for i in range(LINE_SCENARIO_PLAIN):
        points = [
            QPointF(300 + i * 120 + j * 30, 400 + (j % 2) * 400)
            for j in range(LINE_SCENARIO_POINTS)
        ]
        item = PolylineItem(points, object_type=ObjectType.FENCE)
        item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        scene.addItem(item)
    for i in range(LINE_SCENARIO_STYLED):
        points = [
            QPointF(1600 + i * 120 + j * 30, 500 + (j % 2) * 400)
            for j in range(LINE_SCENARIO_POINTS)
        ]
        item = PolylineItem(
            points,
            object_type=ObjectType.PATH,
            # a style that walks its elements along the line: gravel did until L4's
            # owner pass made it a texture (two fills, no walk)
            path_fence_style=PathFenceStyle.STEPPING_STONES,
        )
        item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
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


def _best_median(view: CanvasView, rounds: int = 6) -> float:
    """Best-of-rounds median repaint time in ms (same idea as _assert_repaint_budget)."""
    best = float("inf")
    for r in range(rounds):
        if r > 0:
            time.sleep(0.05)
            gc.collect()
            QApplication.processEvents()
        best = min(best, statistics.median(_measure_repaints(view)))
    return best


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

    def test_the_scenario_lines_are_not_cached(self, line_benchmark_view) -> None:
        """The deterministic half of the issue #473 guard.

        A `DeviceCoordinateCache`d line is never repainted after the warm-up
        frame, so its `paint()` cost is invisible to the measurement. This pins
        that the scenario lines run their painter every frame.
        """
        lines = [i for i in line_benchmark_view.scene().items() if isinstance(i, PolylineItem)]
        assert lines, "the line scenario must hold polylines"
        assert all(
            p.cacheMode() == QGraphicsItem.CacheMode.NoCache for p in lines
        ), "scenario lines must disable DeviceCoordinateCache or line paint is not measured"

    @pytest.mark.perf
    def test_line_paint_cost_has_not_exploded(self, line_benchmark_view) -> None:
        """A same-view upper bound on what the scenario's lines cost per frame.

        Only an **upper** bound: the deterministic ``cacheMode`` guard above is
        the real issue-#473 detector ("does line ``paint()`` run every frame?"),
        and a *lower* bound on this delta was removed because viewport timing on
        a loaded machine swings by tens of milliseconds in both directions
        (measured −10 ms to +21 ms on the same view, which made the bound a
        coin flip rather than a signal). An absolute per-frame budget for the
        styled line stays with #450, which owns its whole-line style walk.
        """
        view = line_benchmark_view
        view.fit_in_view()
        QApplication.processEvents()
        lines = [i for i in view.scene().items() if isinstance(i, PolylineItem)]
        assert lines, "the scenario must hold lines to measure"

        with_lines = _best_median(view)
        for line in lines:
            line.setVisible(False)
        QApplication.processEvents()
        without_lines = _best_median(view)

        delta = with_lines - without_lines
        assert delta <= 40.0, (
            f"the scenario lines add {delta:.2f} ms to the frame ({with_lines:.2f} ms "
            f"-> {without_lines:.2f} ms); line paint cost has exploded"
        )


def _restack_scene(plants: int, beds: int, *, link: bool) -> CanvasScene:
    """A dense garden for the containment scan: ``plants`` in ``beds`` raised beds.

    Unlinked is the expensive case (a linked plant is answered by its link before any
    geometry) and it is what a paste or a bed drawn around standing plants produces.
    """
    scene = CanvasScene(4000.0, 4000.0)
    layer = scene.active_layer.id
    per_bed = max(1, plants // beds)
    for bed_index in range(beds):
        x = 100.0 + 120.0 * (bed_index % 6)
        y = 100.0 + 120.0 * (bed_index // 6)
        bed = PolygonItem(
            [QPointF(x, y), QPointF(x + 100.0, y), QPointF(x + 100.0, y + 100.0),
             QPointF(x, y + 100.0)],
            object_type=ObjectType.RAISED_BED, layer_id=layer,
        )
        scene.addItem(bed)
        for plant_index in range(per_bed):
            plant = CircleItem(
                15.0 + x + 18.0 * (plant_index % 5),
                15.0 + y + 18.0 * (plant_index // 5),
                4.0, object_type=ObjectType.PERENNIAL, layer_id=layer,
            )
            if link:
                plant.parent_bed_id = bed.item_id
            scene.addItem(plant)
    return scene


def _best_restack_ms(scene: CanvasScene, rounds: int = 7) -> float:
    best = float("inf")
    for _ in range(rounds):
        start = time.perf_counter()
        scene._restack_plant_containment()
        best = min(best, (time.perf_counter() - start) * 1000.0)
    return best


@pytest.mark.perf
class TestNfrPerf01ContainmentScanBudget:
    """The per-command plant-containment scan stays inside a slice of a frame (#629)."""

    @pytest.mark.perf
    def test_the_reference_plan_scan_stays_within_budget(self, benchmark_view) -> None:
        scene = benchmark_view.scene()
        best = _best_restack_ms(scene)
        assert best <= RESTACK_BUDGET_MS, (
            f"the containment scan costs {best:.2f} ms on the reference plan "
            f"(budget {RESTACK_BUDGET_MS} ms)"
        )

    @pytest.mark.perf
    @pytest.mark.parametrize("link", [True, False], ids=["linked", "unlinked"])
    def test_a_dense_garden_scan_stays_within_budget(self, qtbot, link: bool) -> None:
        """300 plants in 30 beds: the realistic per-command cost of the scan.

        Measured 0.9 ms linked and 2.6 ms unlinked on the dev box. This is a **budget**,
        not the shape-cache pin: a 4-vertex square rebuilds its path in microseconds, so
        this fixture cannot see a per-(plant, parent) rebuild at all — that property is
        counted deterministically in
        ``test_plant_above_parent_stacking.py::test_the_scan_builds_each_parent_shape_once``
        (mutation-verified: 100 builds against 5).
        """
        scene = _restack_scene(300, 30, link=link)
        try:
            best = _best_restack_ms(scene)
        finally:
            scene.clear()
        assert best <= RESTACK_BUDGET_MS, (
            f"the containment scan costs {best:.2f} ms for 300 {'linked' if link else 'unlinked'} "
            f"plants in 30 beds (budget {RESTACK_BUDGET_MS} ms)"
        )
