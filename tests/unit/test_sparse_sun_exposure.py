"""Independent point oracle, solid ownership, and the Berlin reference numbers."""

import math
from datetime import date

import numpy as np

from open_garden_planner.core.shade_aggregation import (
    HeatmapGrid,
    IdentifiedCaster,
    SunReceiver,
    compute_heatmap,
    compute_sun_exposure,
    point_rasterizer_reference,
    points_in_polygons,
)

DAY = date(2026, 6, 21)


def circle(x, y, radius):
    return tuple((x + radius * math.cos(i * math.tau / 32), y + radius * math.sin(i * math.tau / 32)) for i in range(32))


def test_sparse_matches_reference_with_holes_and_overlap():
    grid = HeatmapGrid(0, 0, 10, 8, 8)
    outer = [(0, 0), (80, 0), (80, 80), (0, 80)]
    hole = [(20, 20), (20, 60), (60, 60), (60, 20)]
    for polygons in ([outer], [outer, hole], [outer, outer]):
        points = np.array([grid.cell_center(r, c) for r in range(8) for c in range(8)])
        assert np.array_equal(points_in_polygons(polygons, points).reshape(8, 8), point_rasterizer_reference(polygons, grid))


def test_receiver_exclusion_and_multifootprint_union_preserve_raw_heatmap():
    grid = HeatmapGrid(0, 0, 10, 8, 8)
    footprint = ((20, 20), (60, 20), (60, 60), (20, 60))
    casters = [IdentifiedCaster("self", (footprint, footprint), 100), IdentifiedCaster("other", (footprint,), 100)]
    receivers = [SunReceiver("self", 45, 45), SunReceiver("outside", -1, 20), SunReceiver("nan", float("nan"), 0)]
    result = compute_sun_exposure(casters, receivers, 52.52, 13.405, DAY, grid, point_rasterizer_reference)
    assert dict(result.receiver_minutes) == {"self": 0}
    expected = compute_heatmap([(p, c.height_cm) for c in casters for p in c.footprints], 52.52, 13.405, DAY, grid, point_rasterizer_reference)
    assert np.array_equal(result.minutes, expected)
    alone = compute_sun_exposure(casters[:1], receivers, 52.52, 13.405, DAY, grid, point_rasterizer_reference)
    assert dict(alone.receiver_minutes) == {"self": 990}
    assert grid.cell_at(45, 15) == (1, 4)  # row zero is south


def test_berlin_reference_values():
    # These constants were measured before implementing the sparse path.
    casters = [IdentifiedCaster("tree", (circle(1200, 1200, 300),), 1000),
               IdentifiedCaster("north", (circle(1200, 1300, 30),), 180),
               IdentifiedCaster("south", (circle(1200, 400, 30),), 180)]
    grid = HeatmapGrid(0, 0, 10, 240, 240)
    receivers = [SunReceiver("north", 1200, 1300), SunReceiver("south", 1200, 400)]
    # Rasterization is irrelevant to sparse exposure; avoid a slow 57k-cell oracle.
    result = compute_sun_exposure(casters, receivers, 52.52, 13.405, DAY, grid,
                                  lambda _polygons, g: np.zeros((g.rows, g.cols), dtype=bool))
    assert dict(result.receiver_minutes) == {"north": 0, "south": 990}


def test_cancellation_inside_caster_loop():
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        return calls == 3
    caster = IdentifiedCaster("a", (circle(50, 50, 20),), 100)
    assert compute_sun_exposure([caster] * 20, [SunReceiver("r", 20, 20)], 52.52, 13.405, DAY,
                                HeatmapGrid(0, 0, 10, 10, 10), point_rasterizer_reference, should_cancel=cancel) is None
    assert calls == 3
