"""A repaint with the sun-shadow overlay on costs what one with it off costs (#784).

Scenario: the bundled family-garden example in a 1453 x 898 viewport at fit —
the plan and size the 2D visual survey measured. Before #784 a repaint with the
overlay on cost 114 ms against 8 ms with it off (13 times), because the overlay
was painted on every frame; and with the plan's 17 MB of item caches in a 10 MB
``QPixmapCache``, items were painted again too. Now the overlay is a cached
picture and the cache has room: measured 1.0-1.1 times.

The bound is a RATIO of two medians taken alternately in the same process, never
milliseconds: this machine's absolute timings drift by half with no code change
(#509), a ratio of interleaved measurements does not.
"""

from __future__ import annotations

import gc
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    STATE_ACTIVE,
    SunShadowController,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_GARDEN = (
    REPO_ROOT / "src" / "open_garden_planner" / "resources" / "examples" / "family-garden.ogp"
)
BERLIN = {"latitude": 52.52, "longitude": 13.405}

#: A repaint with the overlay on may cost this many times one with it off.
#: Measured 1.0-1.1 with the fix and 11-18 without; 2 leaves room for a busy
#: machine and none for an overlay that is painted on every frame.
OVERLAY_REPAINT_RATIO = 2.0


def _median_repaint_ms(view: CanvasView, count: int = 11, warmup: int = 3) -> float:
    gc.collect()
    viewport = view.viewport()
    for _ in range(warmup):
        viewport.repaint()
        QApplication.processEvents()
    times: list[float] = []
    for _ in range(count):
        started = time.perf_counter()
        viewport.repaint()
        times.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(times)


@pytest.mark.perf
def test_overlay_repaint_ratio(qtbot) -> None:
    scene = CanvasScene()
    ProjectManager().load(scene, FAMILY_GARDEN)
    view = CanvasView(scene)
    view.resize(1453, 898)
    view.show()
    qtbot.addWidget(view)
    qtbot.waitExposed(view)
    view.fit_in_view()
    QApplication.processEvents()

    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(datetime(2026, 6, 21, 10, 0, tzinfo=UTC))

    ratios: list[float] = []
    readings: list[tuple[float, float]] = []
    for _ in range(7):  # on and off alternately: drift hits both arms alike
        controller.set_enabled(True)
        assert controller.state == STATE_ACTIVE
        QApplication.processEvents()
        with_overlay = _median_repaint_ms(view)
        controller.set_enabled(False)
        QApplication.processEvents()
        without = _median_repaint_ms(view)
        readings.append((with_overlay, without))
        ratios.append(with_overlay / max(without, 1e-6))
    ratio = statistics.median(ratios)
    print("[OVERLAY-PERF] on/off ms per round: "
          + " ".join(f"{a:.1f}/{b:.1f}" for a, b in readings)
          + f" | ratio median {ratio:.2f} min {min(ratios):.2f} max {max(ratios):.2f}")
    assert ratio <= OVERLAY_REPAINT_RATIO, (
        f"a repaint with the sun overlay on costs {ratio:.1f} times one with it off "
        f"(bound {OVERLAY_REPAINT_RATIO}); rounds on/off ms: {readings}"
    )
