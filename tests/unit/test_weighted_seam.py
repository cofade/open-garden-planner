"""#1007: a weighted region seam must not add or remove a sample of sun.

The seam cells are those whose centre lies on the boundary between two regions.
Qt classifies such a cell by the path that painted it, so painting each region on
its own can double-apply a shade (the darker transmittance wins) or miss it
altogether (the cell reads full sun). The aggregation now takes presence from the
union — the one path the solid sweep has always painted — and settles the value
of a seam cell by the even-odd rule at its centre.

The fake rasterizer below reproduces both painter failures on purpose, so the
test fails for any code that trusts the per-region masks at a seam.
"""

from __future__ import annotations

import numpy as np
import pytest

from open_garden_planner.core.shade_aggregation import (
    HeatmapGrid,
    _weighted_sun_factor,
)
from open_garden_planner.core.shadow_geometry import (
    WeightedShadowRegion,
    WeightedShadowsResult,
)

#: Two regions sharing the line x = 100: the west one is the darker, so a
#: double-painted cell on the east side reads darker than it is.
WEST = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
EAST = [(100.0, 0.0), (200.0, 0.0), (200.0, 100.0), (100.0, 100.0)]
UNION = [(0.0, 0.0), (200.0, 0.0), (200.0, 100.0), (0.0, 100.0)]

WEST_T = 0.25
EAST_T = 0.5


@pytest.fixture
def weighted() -> WeightedShadowsResult:
    return WeightedShadowsResult(
        [UNION],
        [WeightedShadowRegion([WEST], transmittance=WEST_T),
         WeightedShadowRegion([EAST], transmittance=EAST_T)],
        [],
    )


@pytest.fixture
def grid() -> HeatmapGrid:
    # wider than the union, so a stray region pixel can be outside it
    return HeatmapGrid.for_rect(0.0, 0.0, 250.0, 100.0, 10.0)


def _painter_failures(region: list[list[tuple[float, float]]], _grid: HeatmapGrid) -> np.ndarray:
    """The mask the fake painter returns: exactly the union, except that
    - the west region also paints the first east column (col 10), and
    - the east region misses its first two columns (cols 10 and 11),
    which is the double paint and the miss of the report."""
    mask = np.zeros((10, 25), dtype=bool)
    if region == [UNION]:
        mask[:, 0:20] = True
    elif region == [WEST]:
        mask[:, 0:11] = True          # one column too far
    elif region == [EAST]:
        mask[:, 12:20] = True         # two columns too few
    else:  # pragma: no cover - the test would otherwise silently pass
        raise AssertionError(f"unexpected region {region!r}")
    return mask


def test_a_seam_cell_takes_the_region_that_contains_its_centre(grid, weighted) -> None:
    factor = _weighted_sun_factor(weighted, grid, _painter_failures)

    # col 10 (centre x = 105) is in the EAST region; the west painter claimed it
    # too, so the min() would have given it WEST_T.
    assert factor[5, 10] == pytest.approx(EAST_T)
    # col 11 (centre x = 115) is in the EAST region; the painter missed it, so a
    # mask-trusting pass would have read full sun there.
    assert factor[5, 11] == pytest.approx(EAST_T)
    # well inside each region the painter's answer stands
    assert factor[5, 3] == pytest.approx(WEST_T)
    assert factor[5, 18] == pytest.approx(EAST_T)


def test_a_region_that_paints_outside_the_union_stays_sunny(grid, weighted) -> None:
    def stray(polygons, _grid):
        mask = _painter_failures(polygons, _grid)
        if polygons == [WEST]:
            mask[0, 24] = True        # a stray pixel far outside the union
        return mask

    factor = _weighted_sun_factor(weighted, grid, stray)
    # The union is the authority on presence: a per-region path cannot shade a
    # cell the solid sweep paints as open.
    assert grid.cols == 25
    assert factor[0, 24] == 1.0


def test_a_single_region_is_painted_once(grid) -> None:
    """#855's fast path: with one transmittance the region IS the union, so the
    map must not paint the union and then the same geometry again."""
    calls: list[list[list[tuple[float, float]]]] = []

    def counting(polygons, _grid):
        calls.append(polygons)
        mask = np.zeros((10, 25), dtype=bool)
        mask[:, 0:20] = True
        return mask

    weighted = WeightedShadowsResult(
        [UNION],
        [WeightedShadowRegion([UNION], transmittance=0.7)],
        [],
    )
    factor = _weighted_sun_factor(weighted, grid, counting)
    assert len(calls) == 1
    assert factor[5, 3] == pytest.approx(0.7)
    assert factor[5, 21] == 1.0


def test_a_porous_outer_edge_is_not_blackened_by_a_solid_elsewhere() -> None:
    """#1007 review: the ambiguous-cell fallback used the darkest transmittance on
    the PLAN, so a pergola's outer edge turned solid black because a house stood
    somewhere else. A painted cell keeps its own region's value; only a cell no
    region painted falls back to the darkest shade."""
    solid = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    pergola = [(200.0, 0.0), (300.0, 0.0), (300.0, 100.0), (200.0, 100.0)]
    union = [(0.0, 0.0), (300.0, 0.0), (300.0, 100.0), (0.0, 100.0)]
    weighted = WeightedShadowsResult(
        [union],
        [WeightedShadowRegion([solid], transmittance=0.0),
         WeightedShadowRegion([pergola], transmittance=0.7)],
        [],
    )
    grid = HeatmapGrid.for_rect(0.0, 0.0, 400.0, 100.0, 10.0)

    def painter(polygons, _grid):
        mask = np.zeros((grid.rows, grid.cols), dtype=bool)
        if polygons == [union]:
            mask[:, 0:31] = True          # the union covers the pergola through col 30
            mask[5, 35] = True            # and one cell no region paints
        elif polygons == [solid]:
            mask[:, 0:10] = True
            mask[6, 25:26] = True         # a stray solid paint inside the pergola
        elif polygons == [pergola]:
            mask[:, 20:31] = True         # col 30 is an outer edge the centre misses
        else:  # pragma: no cover
            raise AssertionError(polygons)
        return mask

    factor = _weighted_sun_factor(weighted, grid, painter)
    assert factor[5, 30] == pytest.approx(0.7)   # the pergola's outer edge: not 0.0
    assert factor[6, 25] == pytest.approx(0.7)   # a double paint: the geometry owns it
    assert factor[5, 35] == 0.0                  # union-only: the darkest shade
