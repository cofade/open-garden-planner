"""200 solid plant casters/receivers in the same explicit day calculation."""

import os
import time
from datetime import date

import pytest

from open_garden_planner.core.shade_aggregation import (
    HeatmapGrid,
    IdentifiedCaster,
    SunReceiver,
    compute_sun_exposure,
)
from open_garden_planner.ui.canvas.sun_heatmap import rasterize_polygons_qimage
from tests.unit.test_sparse_sun_exposure import circle


# The marker is what moves this test out of the parallel default run and onto a
# quiet runner of its own (`addopts` carries `-m 'not perf'`, CI runs it in a
# separate step). It is a wall-clock budget, so it belongs to that group in exactly
# the way test_nfr_budgets.py's classes do — it previously had no marker at all,
# which left it running beside eight workers while every other budget test had been
# moved out (#509).
@pytest.mark.perf
def test_two_hundred_receivers_budget(qtbot):
    casters, receivers = [], []
    for i in range(200):
        x, y = 75 + (i % 20) * 150, 75 + (i // 20) * 150
        casters.append(IdentifiedCaster(str(i), (circle(x, y, 30),), 180))
        receivers.append(SunReceiver(str(i), x, y))
    started = time.perf_counter()
    result = compute_sun_exposure(casters, receivers, 52.52, 13.405, date(2026, 6, 21),
                                  HeatmapGrid.for_rect(0, 0, 3000, 2000), rasterize_polygons_qimage)
    elapsed = time.perf_counter() - started
    print(f"[SUN-PERF] 200 casters/receivers: {elapsed:.3f}s")
    assert result is not None and len(result.receiver_minutes) == 200
    assert elapsed < (30 if os.environ.get("CI") else 10)
