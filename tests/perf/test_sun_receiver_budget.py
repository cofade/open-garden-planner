"""200 solid plant casters/receivers in the same explicit day calculation."""

import os
import time
from datetime import date

from open_garden_planner.core.shade_aggregation import (
    HeatmapGrid,
    IdentifiedCaster,
    SunReceiver,
    compute_sun_exposure,
)
from open_garden_planner.ui.canvas.sun_heatmap import rasterize_polygons_qimage
from tests.unit.test_sparse_sun_exposure import circle


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
