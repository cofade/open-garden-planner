"""A caster's footprint set is ONE region — the shadow of a loop is its stroke (#444).

A fence or wall drawn as a closed loop comes back from the offset as an outer ring
and a hole. The sweep took every ring as a solid, so the hole was cast as a slab the
size of the enclosed garden: a 10 m x 8 m loop at a 60° sun drew **88.8 m²** where its
stroke's prism gives **17.5 m²** (ADR-056 addendum, issue #444). A self-crossing
outline had the same shape of defect: swept as one ring it lost a lobe (**80,000 cm²**
where the two lobes' prisms give **129,282 cm²**).

``core.shadow_geometry.shadow_region`` repairs both once per walk — the hole is cut
open by a zero-width slit, the self-crossing outline is split into its lobes — so the
sweep only ever sees simple rings. The numbers below are the issue's own before/after
table; the ray oracle is the independent answer (``points_in_polygons`` along the
shadow direction), and it is what makes the bridge's "zero width" claim a measurement
rather than a hope.

The fixture ``tests/fixtures/shadows/shadow_golden.json`` is NOT regenerated: nothing
on the ground in the bench plans is a loop or a self-crossing outline (measured: 0 of
87 and 0 of 379 casters), so every case it pins is a simple ring and
``shadow_region`` returns those point for point.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.shade_aggregation import points_in_polygons
from open_garden_planner.core.shadow_geometry import (
    ShadowCaster,
    compute_scene_shadows,
    polyline_footprint,
    shadow_region,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.footprints import item_footprints
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    SunShadowController,
    SunShadowOverlayItem,
    collect_identified_casters,
    collect_shadow_casters,
)

#: A 10 m x 8 m loop, the issue's reproduction: the centre line closes on itself.
LOOP = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0), (0.0, 800.0), (0.0, 0.0)]
#: A 10 cm stroke, 1.2 m high, at the issue's sun (60° elevation, due south).
STROKE_CM = 10.0
HEIGHT_CM = 120.0
ELEVATION_DEG = 60.0
AZIMUTH_DEG = 180.0
#: What the loop's shadow measures — its stroke's prism. The four-piece reference of
#: the issue (the stroke cut into triangles) gives 174,564 cm², 38 cm² more, because
#: its rectangles have square corners while the offset ring's corners are chamfered by
#: 38 cm² in total; the ray oracle below settles it in the sweep's favour.
LOOP_SHADOW_CM2 = 174_526.0
#: What it measured before #444: both rings swept as solids, i.e. the garden as a slab.
LOOP_SHADOW_BEFORE_CM2 = 888_037.0
#: The bow-tie of the issue: two lobes, 30,000 cm² each.
BOW_TIE = [(0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 300.0)]
BOW_TIE_SHADOW_CM2 = 129_282.0
BOW_TIE_SHADOW_BEFORE_CM2 = 80_000.0
BERLIN = {"latitude": 52.52, "longitude": 13.405}


def signed_area(polygons: Any) -> float:
    """Shoelace area of a polygon set (holes come out negative)."""
    total = 0.0
    for polygon in polygons:
        count = len(polygon)
        for index in range(count):
            x1, y1 = polygon[index]
            x2, y2 = polygon[(index + 1) % count]
            total += x1 * y2 - x2 * y1
    return total / 2.0


def swept(rings: Any, height: float = HEIGHT_CM) -> float:
    return signed_area(compute_scene_shadows(
        [ShadowCaster(list(ring), height) for ring in rings], ELEVATION_DEG, AZIMUTH_DEG))


def test_the_closed_loop_is_an_outer_ring_and_a_hole() -> None:
    """The shape the offset hands out: two rings, the hole negative — nothing here changes."""
    rings = polyline_footprint(LOOP, STROKE_CM)
    assert len(rings) == 2
    assert signed_area([rings[0]]) == pytest.approx(818_062.1, abs=1.0)
    assert signed_area([rings[1]]) == pytest.approx(-782_100.0, abs=1.0)
    # the stroke itself: outer minus hole, 10 cm wide round a 10 m x 8 m loop
    assert signed_area(rings) == pytest.approx(35_962.1, abs=1.0)


def test_the_region_is_one_simple_ring_of_the_same_ground() -> None:
    """``shadow_region`` bridges the hole: one ring, the stroke's own area."""
    rings = polyline_footprint(LOOP, STROKE_CM)
    region = shadow_region(rings)
    assert len(region) == 1
    assert signed_area(region) == pytest.approx(signed_area(rings), abs=1.0)
    # the bridge is a slit, not a cut-out: the 9 + 4 vertices plus the slit's pair
    assert len(region[0]) == 16


def test_the_shadow_of_the_loop_is_its_stroke() -> None:
    """The before/after of the issue, both measured: 88.8 m² -> 17.5 m²."""
    rings = polyline_footprint(LOOP, STROKE_CM)
    assert swept(rings) == pytest.approx(LOOP_SHADOW_BEFORE_CM2, abs=50.0)
    assert swept(shadow_region(rings)) == pytest.approx(LOOP_SHADOW_CM2, abs=50.0)


def _true_sweep(region: list[list[tuple[float, float]]], xs: np.ndarray, ys: np.ndarray,
                steps: int = 120) -> np.ndarray:
    """The shadow's ground truth: a point is shaded when SOME point between it and the
    sun's footprint of it is in the region — no polygons, no rounding."""
    length = HEIGHT_CM / math.tan(math.radians(ELEVATION_DEG))
    azimuth = math.radians(AZIMUTH_DEG)
    direction = np.array([-math.sin(azimuth), -math.cos(azimuth)]) * length
    xx, yy = np.meshgrid(xs, ys)
    points = np.stack([xx.ravel(), yy.ravel()], axis=1)
    mask = np.zeros(len(points), dtype=bool)
    for step in np.linspace(0.0, 1.0, steps):
        mask |= points_in_polygons(region, points - direction * step)
    return mask.reshape(len(ys), len(xs))


def test_a_ray_oracle_agrees_over_the_loop() -> None:
    """The bridge costs no ground: the polygon answer and the ray answer agree on every
    cell of a 20 cm grid — and the old answer is off by a whole garden."""
    rings = polyline_footprint(LOOP, STROKE_CM)
    region = shadow_region(rings)
    xs = np.arange(-200.0, 1201.0, 20.0)
    ys = np.arange(-200.0, 1101.0, 20.0)
    truth = _true_sweep(region, xs, ys)
    xx, yy = np.meshgrid(xs, ys)
    points = np.stack([xx.ravel(), yy.ravel()], axis=1)
    now = points_in_polygons(
        compute_scene_shadows([ShadowCaster(r, HEIGHT_CM) for r in region],
                              ELEVATION_DEG, AZIMUTH_DEG),
        points).reshape(truth.shape)
    assert truth.sum() > 300 and now.sum() == truth.sum()
    assert not (now & ~truth).any() and not (~now & truth).any()
    # the same oracle on the swept rings: the enclosed garden counted as shade
    before = points_in_polygons(
        compute_scene_shadows([ShadowCaster(r, HEIGHT_CM) for r in rings],
                              ELEVATION_DEG, AZIMUTH_DEG),
        points).reshape(truth.shape)
    assert (before & ~truth).sum() > 1500


def test_a_simple_ring_is_handed_back_point_for_point() -> None:
    """The golden fixture's rule: nothing on the ground changes."""
    square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    clockwise = list(reversed(square))
    concave = [(0.0, 0.0), (300.0, 0.0), (300.0, 120.0), (120.0, 120.0), (120.0, 400.0),
               (0.0, 400.0)]
    for ring in (square, clockwise, concave):
        assert shadow_region([ring]) == [ring]
    assert shadow_region([square, concave]) == [square, concave]
    assert shadow_region([]) == []


def test_the_repair_is_idempotent() -> None:
    for rings in (polyline_footprint(LOOP, STROKE_CM), [BOW_TIE]):
        once = shadow_region(rings)
        assert shadow_region(once) == once


def test_a_self_crossing_outline_is_shaded_as_its_lobes() -> None:
    """A bow-tie is two lobes, not one: 129,282 cm² where one ring gave 80,000."""
    assert swept([BOW_TIE], height=300.0) == pytest.approx(BOW_TIE_SHADOW_BEFORE_CM2, abs=1.0)
    region = shadow_region([BOW_TIE])
    assert len(region) == 2
    assert [signed_area([piece]) for piece in region] == pytest.approx([30_000.0, 30_000.0],
                                                                       abs=1.0)
    assert swept(region, height=300.0) == pytest.approx(BOW_TIE_SHADOW_CM2, abs=1.0)


# ── through the real walk and the real overlay ───────────────────────


def _closed_fence_garden() -> tuple[CanvasScene, PolylineItem]:
    scene = CanvasScene(1500.0, 1200.0)
    fence = PolylineItem(
        [QPointF(100.0, 100.0), QPointF(1100.0, 100.0), QPointF(1100.0, 900.0),
         QPointF(100.0, 900.0), QPointF(100.0, 100.0)],
        object_type=ObjectType.FENCE, path_fence_style=PathFenceStyle.WOODEN_FENCE)
    fence.metadata[METADATA_KEY] = 120.0
    scene.addItem(fence)
    return scene, fence


def test_the_caster_walk_hands_out_one_ring_per_loop(qtbot: Any) -> None:
    """The region repair happens on the walk — the one place an item's rings are known."""
    scene, fence = _closed_fence_garden()
    raw = item_footprints(fence)
    assert len(raw) == 2  # the extraction itself is unchanged: outer + hole
    (caster,) = collect_identified_casters(scene)
    assert len(caster.footprints) == 1
    assert signed_area([list(caster.footprints[0])]) == pytest.approx(signed_area(raw), abs=5.0)
    # the overlay's flattening is the same walk: one ShadowCaster, not two
    assert len(collect_shadow_casters(scene)) == 1


def test_the_overlay_leaves_the_garden_inside_a_loop_in_the_sun(qtbot: Any) -> None:
    """End to end: the real overlay's painter path covers the stroke, not the garden."""
    scene, _fence = _closed_fence_garden()
    controller = SunShadowController(scene, lambda: BERLIN)
    controller.set_sim_datetime(datetime(2026, 6, 21, 10, 0, tzinfo=UTC))  # local solar noon
    controller.set_enabled(True)
    overlay = next(item for item in scene.items() if isinstance(item, SunShadowOverlayItem))
    path = overlay.path()
    assert not path.contains(QPointF(600.0, 500.0)), (
        "the garden inside a fence loop is not shaded by the fence")
    assert path.contains(QPointF(600.0, 130.0)), "the fence's own shadow is still drawn"
    controller.set_enabled(False)


def test_a_self_crossing_polygon_in_a_plan_keeps_its_lobes(qtbot: Any) -> None:
    """A polygon item whose outline crosses itself is swept as the lobes it draws."""
    scene = CanvasScene(1000.0, 1000.0)
    bow = PolygonItem([QPointF(x, y) for x, y in BOW_TIE], object_type=ObjectType.HOUSE)
    bow.metadata[METADATA_KEY] = 300.0
    scene.addItem(bow)
    (caster,) = collect_identified_casters(scene)
    assert len(caster.footprints) == 2
    assert swept([list(footprint) for footprint in caster.footprints],
                 height=caster.height_cm) == pytest.approx(BOW_TIE_SHADOW_CM2, abs=50.0)
