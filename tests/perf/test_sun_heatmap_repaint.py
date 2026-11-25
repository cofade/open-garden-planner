"""A repaint with the hours-of-sun map on costs little more than one with it off (#852).

The map's contour lines and hour labels are static between two map computations.
Before #852 every hour line was its own ``QGraphicsPathItem`` stroking thousands
of two-point segments on every repaint: with the map shown a family-garden
repaint cost 3.3-4.0 times one with it hidden (8.3 ms against 2.5 ms). The lines
now live in one device-cached layer and the note clip is built only where a note
can reach, so the measured ratio is ~1.3.

The bound is a RATIO of two medians taken alternately in the same process, never
milliseconds: absolute timings drift by half with no code change (#509).
"""

from __future__ import annotations

import gc
import statistics
import time
from datetime import date
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_GARDEN = (
    REPO_ROOT / "src" / "open_garden_planner" / "resources" / "examples" / "family-garden.ogp"
)
BERLIN = {"latitude": 52.52, "longitude": 13.405}
SUMMER = date(2026, 6, 21)

#: A repaint with the map on may cost this many times one with it hidden.
#: Measured 1.3-1.5 with the cached layer and 3.3-4.0 without; 2.0 leaves room
#: for a busy machine and none for per-repaint contour stroking.
HEATMAP_REPAINT_RATIO = 2.0


def _median_repaint_ms(view: CanvasView, count: int = 11, warmup: int = 3) -> float:
    gc.collect()
    viewport = view.viewport()
    for _ in range(warmup):
        viewport.update()
        viewport.repaint()
        QApplication.processEvents()
    times: list[float] = []
    for _ in range(count):
        viewport.update()
        QApplication.processEvents()
        started = time.perf_counter()
        viewport.repaint()
        times.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(times)


@pytest.mark.perf
def test_heatmap_repaint_ratio(qtbot) -> None:
    scene = CanvasScene()
    ProjectManager().load(scene, FAMILY_GARDEN)
    view = CanvasView(scene)
    view.resize(1453, 898)
    view.show()
    qtbot.addWidget(view)
    qtbot.waitExposed(view)
    view.fit_in_view()
    QApplication.processEvents()

    controller = SunHeatmapController(scene, lambda: BERLIN)
    with qtbot.waitSignal(controller.finished, timeout=120000) as blocker:
        assert controller.run_for_day(SUMMER)
    assert blocker.args == [True]
    QApplication.processEvents()
    overlay = controller._ensure_overlay()
    assert overlay is not None
    map_items = [item for item in controller._contour_items if item is not overlay]
    assert map_items, "the map must have contours and labels for this test to mean anything"

    ratios: list[float] = []
    readings: list[tuple[float, float]] = []
    for _ in range(7):  # on and off alternately: drift hits both arms alike
        overlay.setVisible(True)
        for item in map_items:
            item.setVisible(True)
        QApplication.processEvents()
        shown = _median_repaint_ms(view)
        overlay.setVisible(False)
        for item in map_items:
            item.setVisible(False)
        QApplication.processEvents()
        hidden = _median_repaint_ms(view)
        readings.append((shown, hidden))
        ratios.append(shown / max(hidden, 1e-6))
    ratio = statistics.median(ratios)
    print("[HEATMAP-PERF] on/off ms per round: "
          + " ".join(f"{a:.1f}/{b:.1f}" for a, b in readings)
          + f" | ratio median {ratio:.2f} min {min(ratios):.2f} max {max(ratios):.2f}")
    assert ratio <= HEATMAP_REPAINT_RATIO, (
        f"a repaint with the hours-of-sun map on costs {ratio:.1f} times one with it "
        f"hidden (bound {HEATMAP_REPAINT_RATIO}); rounds on/off ms: {readings}"
    )
