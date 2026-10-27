"""A caster's footprint set is ONE region — the shadow of a loop is its stroke (#444).

A fence or wall drawn as a closed loop comes back from the offset as an outer ring
and a hole. The sweep took every ring as a solid, so the hole was cast as a slab the
size of the enclosed garden: a 10 m x 8 m loop at a 60° sun drew **88.8 m²** where its
stroke's prism gives **17.5 m²** (ADR-037 addendum "one caster's ring set is one REGION", issue #444). A self-crossing
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
#: 38 cm² in total (the outer ring's printed area is 818,062.1, not the rectangles'
#: 818,100). The ray oracle below cannot adjudicate that difference — its grid cell is
#: 400 cm² — and does not need to: it settles the REPAIR, and the ring's own outline
#: settles the rest.
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


def test_the_repair_keeps_the_ground_when_it_is_asked_again() -> None:
    """A region handed back in describes the same ground (idempotent in coverage).

    It is not necessarily the same vertex list: a bridged ring touches itself at the
    slit's two ends, so a second pass may decompose it differently — which is why the
    walk always starts from the item's own rings, never from a repaired region.
    """
    for rings in (polyline_footprint(LOOP, STROKE_CM), [BOW_TIE]):
        once = shadow_region(rings)
        twice = shadow_region(once)
        assert sum(signed_area([piece]) for piece in twice) == pytest.approx(
            sum(signed_area([piece]) for piece in once), abs=1.0)
        xs = np.arange(-250.0, 1251.0, 5.0)
        ys = np.arange(-250.0, 1151.0, 5.0)
        xx, yy = np.meshgrid(xs, ys)
        points = np.stack([xx.ravel(), yy.ravel()], axis=1)
        assert (points_in_polygons(once, points) == points_in_polygons(twice, points)).all()


def test_a_self_crossing_outline_is_shaded_as_its_lobes() -> None:
    """A bow-tie is two lobes, not one: 129,282 cm² where one ring gave 80,000."""
    assert swept([BOW_TIE], height=300.0) == pytest.approx(BOW_TIE_SHADOW_BEFORE_CM2, abs=1.0)
    region = shadow_region([BOW_TIE])
    assert len(region) == 2
    assert [signed_area([piece]) for piece in region] == pytest.approx([30_000.0, 30_000.0],
                                                                       abs=1.0)
    assert swept(region, height=300.0) == pytest.approx(BOW_TIE_SHADOW_CM2, abs=1.0)


def _pentagram(cx: float, cy: float, radius: float) -> list[tuple[float, float]]:
    return [(cx + radius * math.cos(math.radians(-90 + 144 * k)),
             cy + radius * math.sin(math.radians(-90 + 144 * k))) for k in range(5)]


def test_a_clockwise_or_mirrored_crossing_outline_is_split_too(qtbot: Any) -> None:
    """A crossing outline is its lobes whatever way it is wound (#444 review).

    The first per-ring split asked the RING's winding whether it was a hole, so a
    clockwise or mirrored star was left unsplit and drew 334,617 cm² instead of
    321,565. The app's own mirror tool flips the winding, which makes this reachable
    without a hand-edited file; the star is mirrored here through
    ``core.mirror_geometry.build_mirrored_item`` — the production path.
    """
    from open_garden_planner.core.mirror_geometry import build_mirrored_item

    star = _pentagram(500.0, 500.0, 400.0)
    clockwise = list(reversed(star))
    assert signed_area([clockwise]) < 0.0 < signed_area([star])
    for ring in (clockwise, star):
        region = shadow_region([ring])
        assert len(region) >= 2, "a crossing outline is split, whichever way it winds"
        # the same ground as the counter-clockwise star: the five lobes of the star
        assert sum(abs(signed_area([piece])) for piece in region) == pytest.approx(
            124_108.3, abs=5.0)
        assert swept(region, height=300.0) == pytest.approx(321_564.7, abs=50.0)

    scene = CanvasScene(1000.0, 1000.0)
    drawn = PolygonItem([QPointF(x, y) for x, y in star], object_type=ObjectType.HOUSE)
    drawn.metadata[METADATA_KEY] = 300.0
    scene.addItem(drawn)
    mirrored = build_mirrored_item(drawn, QPointF(500.0, 0.0), QPointF(500.0, 1000.0))
    scene.addItem(mirrored)
    assert item_footprints(mirrored)[0] != item_footprints(drawn)[0]
    for item in (drawn, mirrored):
        (caster,) = [c for c in collect_identified_casters(scene)
                     if c.item_id == str(item.item_id)]
        assert len(caster.footprints) == 5, caster.item_id
        assert swept([list(footprint) for footprint in caster.footprints],
                     height=caster.height_cm) == pytest.approx(321_564.7, abs=100.0)


def test_a_pentagram_is_split_even_though_its_lobes_are_smaller_than_its_print() -> None:
    """A self-crossing ring whose decomposition is an OUTER PLUS A HOLE (#444 review).

    The first cut of the detection compared the decomposition's total area with the
    ring's printed area and demanded it be larger — true for a bow-tie, false for a
    pentagram: printed 235,114 cm², five lobes 124,108, and the even-odd fill of the
    outline is an outer with a pentagonal hole. Measured: swept as one ring 334,617
    cm² where its five lobes' prisms give 321,565.
    """
    star = _pentagram(500.0, 500.0, 400.0)
    region = shadow_region([star])
    assert len(region) == 5
    assert sum(abs(signed_area([lobe])) for lobe in region) == pytest.approx(
        124_108.3, abs=5.0)
    assert swept([star], height=300.0) == pytest.approx(334_617.3, abs=50.0)
    assert swept(region, height=300.0) == pytest.approx(321_564.7, abs=50.0)


def test_a_hole_belongs_to_the_innermost_outer_that_contains_it() -> None:
    """An island inside a hole keeps its own hole (#444 review).

    Attaching every negative ring to the FIRST outer that contains it made the
    island's hole a hole of the outermost ring, and the bridged ring crossed itself.
    The region's ground is the same either way — outer minus hole, plus island minus
    its hole — and each piece is now its own simple ring.
    """
    outer = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0), (0.0, 800.0)]
    hole = [(20.0, 20.0), (20.0, 780.0), (980.0, 780.0), (980.0, 20.0)]
    island = [(300.0, 300.0), (700.0, 300.0), (700.0, 500.0), (300.0, 500.0)]
    island_hole = [(310.0, 310.0), (310.0, 490.0), (690.0, 490.0), (690.0, 310.0)]
    rings = [outer, hole, island, island_hole]
    region = shadow_region(rings)
    assert len(region) == 2
    # The PIECES, not their sum: attaching the island's hole to the outermost ring
    # (the pre-review rule) gives [2,000, 80,000] — the same total ground, but a
    # bridged ring that crosses itself, so the sweep differs from the true sweep.
    assert sorted(abs(signed_area([piece])) for piece in region) == pytest.approx(
        [11_600.0, 70_400.0], abs=1.0)
    expected = (signed_area([outer]) + signed_area([hole])
                + signed_area([island]) + signed_area([island_hole]))
    assert sum(signed_area([piece]) for piece in region) == pytest.approx(expected, abs=1.0)
    xs = np.arange(-50.0, 1051.0, 25.0)
    ys = np.arange(-50.0, 851.0, 25.0)
    truth = _true_sweep(region, xs, ys)
    xx, yy = np.meshgrid(xs, ys)
    points = np.stack([xx.ravel(), yy.ravel()], axis=1)
    now = points_in_polygons(
        compute_scene_shadows([ShadowCaster(r, HEIGHT_CM) for r in region],
                              ELEVATION_DEG, AZIMUTH_DEG),
        points).reshape(truth.shape)
    assert truth.sum() > 100
    assert not (now & ~truth).any() and not (~now & truth).any()


def test_an_outline_above_the_vertex_bound_pays_no_simplify_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound that keeps a crafted plan off the walk's hot path (#444 review).

    ``SimplifyPolygons`` costs 257 ms on the loader's 16,384-vertex ceiling — per walk.
    Above ``MAX_REGION_VERTICES`` the self-crossing test is skipped and the ring is
    swept as it was before this repair; the monkeypatch proves no call is made at all.
    """
    import open_garden_planner.core.shadow_geometry as geometry

    ring = [(500.0 + 400.0 * math.cos(2 * math.pi * i / 16_384),
             500.0 + 400.0 * math.sin(2 * math.pi * i / 16_384)) for i in range(16_384)]
    assert len(ring) > geometry.MAX_REGION_VERTICES

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("SimplifyPolygons ran on a ring above the vertex bound")

    monkeypatch.setattr(geometry.pyclipper, "SimplifyPolygons", refuse)
    assert shadow_region([ring]) == [ring]


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


def test_a_pinched_outline_keeps_its_ground_whichever_way_it_winds(qtbot: Any) -> None:
    """A self-TOUCHING ring is not a crossing one, and its winding must not matter.

    Two 200 x 200 lobes sharing the vertex (300, 300) decompose into two rings that
    add up to the ring's own area. The first cut reversed those pieces for a negative
    ring ("a pinched hole stays a hole"), and the grouping then read the SHARED vertex
    as inside its sibling — one lobe was lost (2,200 cm² against 5,000). The pieces are
    now grouped by a majority of strictly interior vertices, so a lone reversed solid
    comes back as two solid lobes and a pinched hole stays a hole.
    """
    pinched = [(100.0, 100.0), (300.0, 300.0), (100.0, 500.0),
               (500.0, 500.0), (300.0, 300.0), (500.0, 100.0)]
    assert signed_area([pinched]) != 0.0
    xs = np.arange(0.0, 601.0, 5.0)
    ys = np.arange(0.0, 601.0, 5.0)
    for ring in (pinched, list(reversed(pinched))):
        region = shadow_region([ring])
        assert len(region) == 2, "a pinched outline is its two lobes"
        assert sum(abs(signed_area([piece])) for piece in region) == pytest.approx(
            80_000.0, abs=1.0)
        truth = _true_sweep(region, xs, ys)
        xx, yy = np.meshgrid(xs, ys)
        points = np.stack([xx.ravel(), yy.ravel()], axis=1)
        now = points_in_polygons(
            compute_scene_shadows([ShadowCaster(r, HEIGHT_CM) for r in region],
                                  ELEVATION_DEG, AZIMUTH_DEG),
            points).reshape(truth.shape)
        assert truth.sum() > 500
        # the oracle steps t in 120 slices, so the cusp where the two lobes' sweeps
        # meet cost a handful of cells (measured 27 of 5,282); one lost lobe would
        # disagree on more than half of them
        assert int((now & ~truth).sum() + (~now & truth).sum()) <= truth.sum() // 100

    # . and through the production mirror tool, which is what flips the winding
    from open_garden_planner.core.mirror_geometry import build_mirrored_item

    scene = CanvasScene(1000.0, 1000.0)
    drawn = PolygonItem([QPointF(x, y) for x, y in pinched], object_type=ObjectType.HOUSE)
    drawn.metadata[METADATA_KEY] = 120.0
    scene.addItem(drawn)
    mirrored = build_mirrored_item(drawn, QPointF(700.0, 0.0), QPointF(700.0, 1000.0))
    scene.addItem(mirrored)
    for item in (drawn, mirrored):
        (caster,) = [c for c in collect_identified_casters(scene)
                     if c.item_id == str(item.item_id)]
        assert len(caster.footprints) == 2, caster.item_id


def test_only_a_polygon_s_own_outline_can_cross_itself(qtbot: Any) -> None:
    """The premise of the walk's cheap gate, measured on every shape the extractor knows.

    ``_shadow_footprints`` skips the repair for a single ring from a circle, ellipse,
    rectangle or offset polyline, so each of those must hand out ONE positively wound
    ring — and ``footprints_can_self_cross`` must be True exactly for the one shape
    whose vertices are the user's own order. Every ``OUTLINE_SHAPES`` value is walked,
    so a shape added later fails here until it answers for itself; a crossing CENTRE
    LINE is pinned as the multi-ring case the walk always repairs.
    """
    from open_garden_planner.ui.canvas.footprints import (
        OUTLINE_CIRCLE,
        OUTLINE_ELLIPSE,
        OUTLINE_POLYGON,
        OUTLINE_POLYLINE,
        OUTLINE_RECTANGLE,
        OUTLINE_SHAPES,
        footprints_can_self_cross,
        item_outline,
    )
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    shapes = {
        OUTLINE_CIRCLE: CircleItem(100.0, 100.0, 30.0, object_type=ObjectType.PERENNIAL),
        OUTLINE_ELLIPSE: EllipseItem(500.0, 100.0, 80.0, 40.0, object_type=ObjectType.LAWN),
        OUTLINE_RECTANGLE: RectangleItem(700.0, 100.0, 100.0, 60.0,
                                         object_type=ObjectType.RAISED_BED),
        OUTLINE_POLYLINE: PolylineItem([QPointF(100.0, 500.0), QPointF(300.0, 500.0)],
                                       object_type=ObjectType.FENCE),
        OUTLINE_POLYGON: PolygonItem([QPointF(x, y) for x, y in BOW_TIE],
                                     object_type=ObjectType.HOUSE),
    }
    assert set(shapes) == set(OUTLINE_SHAPES), "a footprint shape is not covered here"
    for shape, item in shapes.items():
        assert item_outline(item) is not None and item_outline(item).shape == shape  # type: ignore[union-attr]
        assert footprints_can_self_cross(item) is (shape == OUTLINE_POLYGON), shape
        rings = item_footprints(item)
        if shape == OUTLINE_POLYGON:
            assert len(rings) == 1  # the user's own order: repaired by the walk
            continue
        assert len(rings) == 1 and signed_area(rings) > 0.0, shape

    crossing = PolylineItem(
        [QPointF(100.0, 700.0), QPointF(300.0, 900.0), QPointF(300.0, 700.0),
         QPointF(100.0, 900.0), QPointF(100.0, 700.0)], object_type=ObjectType.FENCE)
    raw = item_footprints(crossing)
    assert len(raw) > 1, "a crossing centre line is the multi-ring case"
    region = shadow_region(raw)
    assert len(region) == 1, "the repair collapses the stroke to one simple ring"
    assert signed_area(region) == pytest.approx(signed_area(raw), abs=5.0)
