"""What a flower meadow costs against a lawn of the same area (#940).

A LAWN whose fill pattern is WILDFLOWER grows the lawn's blade count (the plan's share)
as taller blades, and a flower head of ``HEAD_TRIANGLES`` triangles on one blade in
``MEADOW_FLOWER_EVERY`` on average. Measured on the dev box (Windows 11, Python 3.11.9,
2026-11-18, a shared machine), a 15 x 10 m lawn and meadow, medians of 9:

==========  ======  =========  ===================  =====================
            parts   triangles  first build (ms)     a cut-out moved (ms)
==========  ======  =========  ===================  =====================
lawn        1       98,568     23-33                3.2-5.5
meadow      2       ~120,000   39-45                4.2-5.8
==========  ======  =========  ===================  =====================

Stated as RATIOS measured in one process, interleaved, so the machine's load cancels:
a first build at most 2.5 times the lawn's (measured 1.4-1.7), a rebuild from the
remembered sward (a flat item moved over it) at most 3 times (measured 1.0-1.4). The
triangle count is exact work, asserted in ``test_scene3d_l4_surfaces.py``.
"""

from __future__ import annotations

import statistics
import time

import pytest

from open_garden_planner.core.scene3d.builders import production_registry, surfaces
from tests.unit.scene3d_builder_cases import polygon_record, rectangle

RUNS = 9
FIRST_BUILD_RATIO = 2.5
REMEMBERED_RATIO = 3.0
CUT = ((-200.0, -150.0), (200.0, -150.0), (200.0, 150.0), (-200.0, 150.0))


def _record(pattern: str | None, cut: bool = False):  # noqa: ANN202 - a Record
    params: dict[str, object] = {"seed": "budget"}
    if pattern is not None:
        params["surface_pattern"] = pattern
    if cut:
        params["lawn_cutouts"] = (CUT,)
    return polygon_record("LAWN", rectangle(1500.0, 1000.0), None, params=params)


@pytest.mark.perf
def test_a_meadow_costs_a_bounded_multiple_of_a_lawn() -> None:
    registry = production_registry()
    first: dict[str | None, list[float]] = {None: [], surfaces.MEADOW_PATTERN: []}
    again: dict[str | None, list[float]] = {None: [], surfaces.MEADOW_PATTERN: []}
    for _ in range(RUNS):
        for pattern in first:   # interleaved: the machine's load is the same for both
            surfaces.clear_lawn_cache()
            started = time.perf_counter()
            registry.build(_record(pattern))
            first[pattern].append(time.perf_counter() - started)
            started = time.perf_counter()
            registry.build(_record(pattern, cut=True))   # the remembered sward, re-masked
            again[pattern].append(time.perf_counter() - started)
    surfaces.clear_lawn_cache()
    lawn, meadow = (statistics.median(first[key]) for key in first)
    assert meadow <= FIRST_BUILD_RATIO * lawn, (meadow * 1000.0, lawn * 1000.0)
    lawn, meadow = (statistics.median(again[key]) for key in again)
    assert meadow <= REMEMBERED_RATIO * lawn, (meadow * 1000.0, lawn * 1000.0)
