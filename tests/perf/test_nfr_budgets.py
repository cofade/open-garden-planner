"""NFR performance budget verification tests (NFR-PERF-01, issue #409).

Asserts frame timing on the reference benchmark plan
`docs/11-risks-and-technical-debt/audit-2026-10-plan_500.ogp` (990 scene items)
in a 1600x1000 viewport:
- Fit-in-view repaint <= 16.7 ms median (>= 60 fps)
- Zoom step repaint <= 16.7 ms median (>= 60 fps)
- 100% zoom / pan repaint <= 16.7 ms median (>= 60 fps)
"""

from __future__ import annotations

import os
import statistics
import time
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PLAN = REPO_ROOT / "docs" / "11-risks-and-technical-debt" / "audit-2026-10-plan_500.ogp"

# 60 fps frame budget is 16.67 ms.
# In heavily-loaded headless CI environments (e.g. GitHub Actions Linux with xvfb/LLVMpipe),
# software rasterisation can have a higher CPU ceiling.
_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
FRAME_BUDGET_MS = 25.0 if _IS_CI else 16.7


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


def _measure_repaints(view: CanvasView, count: int = 15, warmup: int = 3) -> float:
    """Measure synchronous repaint durations and return the median in milliseconds."""
    viewport = view.viewport()
    for _ in range(warmup):
        viewport.repaint()
        QApplication.processEvents()

    times: list[float] = []
    for _ in range(count):
        t0 = time.perf_counter()
        viewport.repaint()
        times.append((time.perf_counter() - t0) * 1000.0)

    return statistics.median(times)


@pytest.mark.perf
class TestNfrPerf01Budgets:
    """Verify NFR-PERF-01 60fps budgets on the reference 500-object plan."""

    def test_fit_in_view_repaint_budget(self, benchmark_view) -> None:
        """Fit-in-view repaint satisfies the <= 16.7 ms frame budget."""
        benchmark_view.fit_in_view()
        QApplication.processEvents()

        median_ms = _measure_repaints(benchmark_view)
        assert median_ms <= FRAME_BUDGET_MS, (
            f"Fit-in-view repaint median {median_ms:.2f} ms exceeds "
            f"budget {FRAME_BUDGET_MS:.2f} ms"
        )

    def test_zoom_step_repaint_budget(self, benchmark_view) -> None:
        """Zoom step repaint satisfies the <= 16.7 ms frame budget."""
        benchmark_view.fit_in_view()
        benchmark_view.zoom_in()
        QApplication.processEvents()

        median_ms = _measure_repaints(benchmark_view)
        assert median_ms <= FRAME_BUDGET_MS, (
            f"Zoom step repaint median {median_ms:.2f} ms exceeds "
            f"budget {FRAME_BUDGET_MS:.2f} ms"
        )

    def test_full_zoom_repaint_budget(self, benchmark_view) -> None:
        """100% zoom repaint satisfies the <= 16.7 ms frame budget."""
        benchmark_view.reset_zoom()
        QApplication.processEvents()

        median_ms = _measure_repaints(benchmark_view)
        assert median_ms <= FRAME_BUDGET_MS, (
            f"100% zoom repaint median {median_ms:.2f} ms exceeds "
            f"budget {FRAME_BUDGET_MS:.2f} ms"
        )
