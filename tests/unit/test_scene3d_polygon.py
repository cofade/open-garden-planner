"""Plane polygons of the 3D pipeline: orientation, nesting, triangulation with holes.

Phase 17 L1.1, fix round 1 (#385). Qt-free. The defect this module exists for: a
closed fence's stroke is TWO rings — an outer and a hole — and the first contract
handed both to builders as "footprints". Extruded as two solids, 3.6 m² of fence
became an 80 m² slab, and every gate passed. So: outers and holes are told apart
by orientation, grouped, and a region is triangulated as outer MINUS holes.
"""

from __future__ import annotations

import math
import random

import pytest

from open_garden_planner.core import scene3d
from open_garden_planner.core.scene3d import (
    ccw,
    cw,
    group_rings,
    is_buildable_region,
    is_flat_ring,
    is_simple_ring,
    point_in_regions,
    point_in_ring,
    regions_area,
    ring_area,
    signed_area,
    triangulate_polygon,
    triangulate_region,
)
from open_garden_planner.core.scene3d import legacy as legacy_module
from open_garden_planner.core.scene3d import polygon as polygon_module
from open_garden_planner.core.scene3d.polygon import (
    HELD_VERTICES,
    MAX_ITEM_VERTICES,
    RegionTooLargeError,
    WorkBudget,
    cut_work,
    exceeds_work_bound,
    is_region_too_large,
    pay_for_region,
    region_cost,
    region_work,
    ring_keyed,
    segments_touch,
    stack_height,
    touching_pairs,
)
from open_garden_planner.core.shadow_geometry import polyline_footprint

SQUARE = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))
L_SHAPE = ((0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (50.0, 50.0), (50.0, 100.0), (0.0, 100.0))
BOW_TIE = ((0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 300.0))
LOPSIDED_BOW_TIE = ((0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 200.0))
PENTAGRAM = ((0.0, 100.0), (58.8, -80.9), (-95.1, 30.9), (95.1, 30.9), (-58.8, -80.9))


def rect(x0: float, y0: float, x1: float, y1: float, *, clockwise: bool = False):
    ring = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    return ring[::-1] if clockwise else ring


def tri_area(points, triangle) -> float:
    a, b, c = (points[i] for i in triangle)
    return ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2.0


def assert_triangulates(outer, holes, *, flat_corners: bool = False) -> None:
    """The three facts of a correct triangulation of outer-minus-holes: every
    triangle counter-clockwise, their areas summing to the region's, and no
    triangle's centroid in a hole or outside the outer ring. ``flat_corners``:
    the region may have three vertices of different rings on one line, and an
    ear without an area yields no triangle — so there may be fewer."""
    points, triangles = triangulate_region(outer, holes)
    assert points == tuple(outer) + tuple(p for hole in holes for p in hole)
    areas = [tri_area(points, t) for t in triangles]
    assert all(area > 0.0 for area in areas), min(areas)
    expected = signed_area(outer) + sum(signed_area(h) for h in holes)
    assert sum(areas) == pytest.approx(expected, rel=1e-9)
    for triangle in triangles:
        cx = sum(points[i][0] for i in triangle) / 3.0
        cy = sum(points[i][1] for i in triangle) / 3.0
        assert point_in_regions(cx, cy, ((tuple(outer), tuple(holes)),)), (cx, cy)
    # outer + holes joined by one bridge each: n + 2h vertices on the merged ring
    full = len(points) + 2 * len(holes) - 2
    assert len(triangles) <= full if flat_corners else len(triangles) == full
    assert min(areas) > 1e-9  # no triangle that is nothing


# ── orientation ───────────────────────────────────────────────────────────────


class TestOrientation:
    def test_signed_area_is_positive_counter_clockwise(self) -> None:
        assert signed_area(SQUARE) == 10000.0
        assert signed_area(SQUARE[::-1]) == -10000.0
        assert signed_area(L_SHAPE) == 7500.0
        assert ring_area(SQUARE) == signed_area(SQUARE)
        assert signed_area(BOW_TIE) == 0.0  # two lobes of opposite sense cancel

    def test_ccw_and_cw_reverse_only_when_needed(self) -> None:
        assert ccw(SQUARE) is SQUARE and ccw(SQUARE[::-1]) == SQUARE
        assert cw(SQUARE) == SQUARE[::-1] and cw(SQUARE[::-1]) == SQUARE[::-1]

    def test_point_in_ring_and_regions(self) -> None:
        assert point_in_ring(50.0, 50.0, SQUARE) and not point_in_ring(150.0, 50.0, SQUARE)
        assert point_in_ring(25.0, 75.0, L_SHAPE) and not point_in_ring(75.0, 75.0, L_SHAPE)
        hole = rect(40.0, 40.0, 60.0, 60.0, clockwise=True)
        regions = ((SQUARE, (hole,)),)
        assert point_in_regions(10.0, 10.0, regions)
        assert not point_in_regions(50.0, 50.0, regions)  # in the hole
        assert not point_in_regions(500.0, 50.0, regions)


class TestSimple:
    @pytest.mark.parametrize("ring", [SQUARE, SQUARE[::-1], L_SHAPE, rect(-5.0, -5.0, 5.0, 5.0)])
    def test_simple_rings(self, ring) -> None:
        assert is_simple_ring(tuple(ring))

    @pytest.mark.parametrize(
        "ring",
        [BOW_TIE, LOPSIDED_BOW_TIE, PENTAGRAM,
         ((0.0, 0.0), (1.0, 1.0)),  # two points
         ((0.0, 0.0), (10.0, 0.0), (20.0, 0.0)),  # no area
         ((0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (0.0, 10.0)),  # a repeated vertex
         ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (5.0, 0.0), (0.0, 10.0))],  # touches its own edge
        ids=["bow-tie", "lopsided bow-tie", "pentagram", "two points", "collinear",
             "repeated vertex", "touching"],
    )
    def test_rings_that_are_not_simple(self, ring) -> None:
        assert not is_simple_ring(tuple(ring))

    def test_a_lopsided_bow_tie_has_an_area_and_a_valid_looking_orientation(self) -> None:
        """Why orientation alone is not enough: this ring crosses itself and still
        has a non-zero signed area, so a sign check waves it through."""
        assert signed_area(LOPSIDED_BOW_TIE) != 0.0
        assert not is_simple_ring(LOPSIDED_BOW_TIE)

    def test_flat_is_not_the_same_as_no_net_area(self) -> None:
        """A symmetric bow-tie has a signed area of exactly zero and still covers
        ground. "Skip the rings without area" would drop it silently; only a ring
        whose corners all lie on one line is skipped."""
        assert signed_area(BOW_TIE) == 0.0 and not is_flat_ring(BOW_TIE)
        assert is_flat_ring(()) and is_flat_ring(((0.0, 0.0), (1.0, 1.0)))
        assert is_flat_ring(((0.0, 0.0), (10.0, 0.0), (20.0, 0.0)))
        assert is_flat_ring(((5.0, 5.0), (5.0, 5.0), (5.0, 5.0)))  # one point, three times
        assert is_flat_ring(((0.0, 0.0), (30.0, 40.0), (15.0, 20.0), (60.0, 80.0)))
        assert not is_flat_ring(SQUARE) and not is_flat_ring(SQUARE[::-1])
        assert not is_flat_ring(LOPSIDED_BOW_TIE) and not is_flat_ring(PENTAGRAM)


def _wobbly(n: int, rng: random.Random, *, tangle: bool) -> tuple[tuple[float, float], ...]:
    """A star-shaped ring of ``n`` vertices (simple by construction); ``tangle``
    swaps two of its vertices, which makes two pairs of edges cross."""
    radii = [300.0 + rng.uniform(-80.0, 80.0) for _ in range(n)]
    ring = [(r * math.cos(2.0 * math.pi * k / n), r * math.sin(2.0 * math.pi * k / n))
            for k, r in enumerate(radii)]
    if tangle:
        i = rng.randrange(n)
        j = (i + rng.randrange(2, n - 2)) % n
        ring[i], ring[j] = ring[j], ring[i]
    return tuple(ring)


class TestSimpleRingAtScale:
    """The simplicity test is quadratic and runs on every edit of a ring. From
    ``SIMPLE_RING_NUMPY_FROM`` vertices on it runs on numpy — and must say exactly
    what the plain loop says."""

    @pytest.mark.parametrize("n", [5, 31, 32, 33, 100, 257, 600])
    def test_both_implementations_agree(self, n: int) -> None:
        rng = random.Random(385 + n)
        verdicts = set()
        for case in range(12):
            ring = _wobbly(n, rng, tangle=case % 2 == 1)
            loop = polygon_module._edges_touch_loop(ring)
            assert polygon_module._edges_touch_numpy(ring) is loop, (n, case)
            assert is_simple_ring(ring) is (not loop)
            verdicts.add(loop)
        assert verdicts == {True, False}  # both answers were exercised

    @pytest.mark.parametrize("n", [40, 300])
    def test_touching_without_crossing_is_seen_at_scale(self, n: int) -> None:
        """The cases only the ``== 0`` branches catch: a vertex lying exactly on
        another edge, and a vertex repeated elsewhere on the ring."""
        base = [(float(k), 0.0) for k in range(n // 2)]  # a comb's back, then its teeth
        top = [(float(k), 50.0 + (k % 3)) for k in reversed(range(n // 2))]
        ring = tuple(base + top)
        assert is_simple_ring(ring)
        on_an_edge = list(ring)
        on_an_edge[-1] = (2.5, 0.0)  # the last vertex now sits on the edge (2, 0)-(3, 0)
        assert not is_simple_ring(tuple(on_an_edge))
        assert polygon_module._edges_touch_numpy(tuple(on_an_edge))
        assert polygon_module._edges_touch_loop(tuple(on_an_edge))
        repeated = list(ring)
        repeated[-1] = ring[3]  # a vertex visited twice
        assert not is_simple_ring(tuple(repeated))

    def test_a_crossing_in_the_last_block_of_rows_is_found(self) -> None:
        """The array version works through the edges in blocks; a ring longer than
        two blocks whose only crossing lies among its last edges must still be seen."""
        n = 2 * polygon_module._SIMPLE_RING_ROWS + 100
        ring = _wobbly(n, random.Random(1), tangle=False)
        assert is_simple_ring(ring)
        crossed = list(ring)
        crossed[n - 40], crossed[n - 10] = crossed[n - 10], crossed[n - 40]
        assert polygon_module._edges_touch_loop(tuple(crossed))
        assert not is_simple_ring(tuple(crossed))

    def test_small_rings_take_the_loop_and_large_ones_the_arrays(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        used: list[str] = []
        loop, arrays = polygon_module._edges_touch_loop, polygon_module._edges_touch_numpy
        monkeypatch.setattr(polygon_module, "_edges_touch_loop",
                            lambda ring: used.append("loop") or loop(ring))
        monkeypatch.setattr(polygon_module, "_edges_touch_numpy",
                            lambda ring, work=None: used.append("arrays") or arrays(ring, work))
        threshold = polygon_module.SIMPLE_RING_NUMPY_FROM
        rng = random.Random(7)
        assert is_simple_ring(_wobbly(threshold - 1, rng, tangle=False))
        assert is_simple_ring(_wobbly(threshold, rng, tangle=False))
        assert used == ["loop", "arrays"]


# ── nesting ───────────────────────────────────────────────────────────────────


class TestGroupRings:
    def test_a_ring_alone_is_a_region_without_holes(self) -> None:
        assert group_rings([SQUARE]) == ((SQUARE, ()),)

    def test_a_clockwise_ring_inside_becomes_the_hole(self) -> None:
        hole = rect(40.0, 40.0, 60.0, 60.0, clockwise=True)
        assert group_rings([hole, SQUARE]) == ((SQUARE, (hole,)),)

    def test_a_hole_joins_the_smallest_outer_around_it(self) -> None:
        """An island inside a hole: outer A, hole in A, island B in that hole, a
        hole in B. B's hole belongs to B although A contains it too."""
        a = rect(0.0, 0.0, 100.0, 100.0)
        hole_a = rect(10.0, 10.0, 90.0, 90.0, clockwise=True)
        b = rect(30.0, 30.0, 70.0, 70.0)
        hole_b = rect(40.0, 40.0, 60.0, 60.0, clockwise=True)
        assert group_rings([a, hole_a, b, hole_b]) == ((a, (hole_a,)), (b, (hole_b,)))
        assert regions_area(group_rings([a, hole_a, b, hole_b])) == 10000 - 6400 + 1600 - 400

    def test_degenerate_rings_are_dropped_and_an_orphan_hole_is_an_error(self) -> None:
        assert group_rings([((0.0, 0.0), (1.0, 1.0)), ((0.0, 0.0), (5.0, 0.0), (9.0, 0.0))]) == ()
        with pytest.raises(ValueError, match="no outer ring"):
            group_rings([rect(0.0, 0.0, 5.0, 5.0, clockwise=True)])

    @pytest.mark.parametrize(
        ("label", "path", "outers", "holes"),
        [("closed loop", [(0, 0), (1000, 0), (1000, 800), (0, 800), (0, 0)], 1, 1),
         ("2 cm gap", [(0, 2), (0, 800), (1000, 800), (1000, 0), (0, 0)], 1, 1),
         ("open U", [(0, 800), (0, 0), (1000, 0), (1000, 800)], 1, 0),
         ("crossing", [(100, 100), (400, 400), (400, 100), (100, 400)], 1, 1),
         ("two crossings", [(0, 0), (300, 300), (600, 0), (600, 300), (300, 0), (0, 300), (0, 0)],
          1, 3)],
    )
    def test_what_pyclipper_returns_for_a_stroke(self, label, path, outers, holes) -> None:
        """The premise, measured: outers come back counter-clockwise, holes clockwise."""
        rings = [tuple(r) for r in polyline_footprint([(float(x), float(y)) for x, y in path], 10.0)]
        regions = group_rings(rings)
        assert len(regions) == outers, label
        assert sum(len(h) for _o, h in regions) == holes, label
        assert len(rings) == outers + holes

    # ── fix round 2 (P1): who owns a hole is not decided on a boundary point ───

    def test_a_hole_is_not_given_to_an_island_that_touches_it(self) -> None:
        """The re-review's case. Outer A, a hole H in it whose FIRST vertex is
        (20, 50), an island B inside H touching it exactly there. Ownership used
        to be decided by "which outer contains ``hole[0]``" — a point on B's
        boundary, where the point test may answer either way: H went to B, the
        island it surrounds (measured at 123a435, in every order of the rings)."""
        a = rect(0.0, 0.0, 100.0, 100.0)
        h = ((20.0, 50.0), (50.0, 80.0), (80.0, 50.0), (50.0, 20.0))
        b = ((20.0, 50.0), (40.0, 45.0), (40.0, 55.0))
        assert ring_area(h) < 0.0 < ring_area(b)
        for rings in ([a, h, b], [b, h, a], [h, b, a], [b, a, h]):
            assert dict(group_rings(rings)) == {a: (h,), b: ()}

    def test_a_hole_whose_every_vertex_lies_on_its_outer_ring(self) -> None:
        """A diamond cut out of a square, corner to edge: no vertex of the hole is
        inside anything, and it is still that square's hole — whichever vertex it
        starts with. (The point test answers "inside" for a point on the square's
        left or bottom edge and "outside" on its top or right one: the old rule,
        "ask about ``hole[0]``", lost this hole for two of the four starts.)"""
        a = rect(0.0, 0.0, 100.0, 100.0)
        diamond = ((0.0, 50.0), (50.0, 100.0), (100.0, 50.0), (50.0, 0.0))
        assert ring_area(diamond) < 0.0
        other = rect(200.0, 0.0, 300.0, 100.0)
        on_the_boundary = [point_in_ring(x, y, a) for x, y in diamond]
        assert True in on_the_boundary and False in on_the_boundary  # the premise
        for start in range(4):
            hole = diamond[start:] + diamond[:start]
            assert group_rings([other, hole, a]) == ((other, ()), (a, (hole,))), start

    def test_the_owner_must_be_larger_than_the_hole(self) -> None:
        """An island contains points of the hole around it; it is smaller than
        that hole and so can never own it — and a hole in nothing still raises."""
        hole = rect(0.0, 0.0, 100.0, 100.0, clockwise=True)
        island = rect(25.0, 25.0, 45.0, 45.0)
        x, y = polygon_module._point_inside(hole)
        assert point_in_ring(x, y, island)  # it sits exactly where the hole's inside point is taken
        with pytest.raises(ValueError, match="no outer ring"):
            group_rings([hole, island])
        around = rect(-10.0, -10.0, 110.0, 110.0)
        assert group_rings([hole, island, around]) == ((island, ()), (around, (hole,)))

    @pytest.mark.parametrize("seed", range(40))
    def test_point_inside_is_strictly_inside(self, seed: int) -> None:
        rng = random.Random(seed)
        ring = _wobbly(rng.randrange(3, 40), rng, tangle=False)
        if seed % 2:
            ring = ring[::-1]
        shift = rng.randrange(len(ring))
        ring = ring[shift:] + ring[:shift]
        x, y = polygon_module._point_inside(ring)
        assert point_in_ring(x, y, ring)
        assert _distance_to_ring(x, y, ring) > 1e-6

    @pytest.mark.parametrize(
        "ring",
        [L_SHAPE, L_SHAPE[::-1], SQUARE[::-1],
         # the corner's triangle holds other vertices: a notch reaching into it
         ((0.0, 0.0), (100.0, 0.0), (10.0, 10.0), (0.0, 100.0)),
         ((0.0, 0.0), (100.0, 0.0), (20.0, 5.0), (10.0, 10.0), (5.0, 20.0), (0.0, 100.0)),
         ((100.0, 100.0), (100.0, 300.0), (300.0, 300.0), (300.0, 260.0), (140.0, 260.0),
          (140.0, 140.0), (300.0, 140.0), (300.0, 100.0)),
         # a vertex on the line between the corner's neighbours
         ((0.0, 0.0), (100.0, 0.0), (50.0, 50.0), (0.0, 100.0))],
        ids=["L", "L clockwise", "square clockwise", "a notch", "a notch of three", "a C",
             "a vertex on the chord"],
    )
    def test_point_inside_of_awkward_rings(self, ring) -> None:
        x, y = polygon_module._point_inside(tuple(ring))
        assert point_in_ring(x, y, ring) and _distance_to_ring(x, y, ring) > 1e-6


def _distance_to_ring(x: float, y: float, ring) -> float:
    best = math.inf
    for i in range(len(ring)):
        (ax, ay), (bx, by) = ring[i - 1], ring[i]
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return best


def review_ladder(rungs: int, width: float = 6.0):
    """The ladder of the re-review, drawn as ONE stroke: two rails 100 cm apart
    and a rung every 40 cm. → its region ``(outer, holes)``; ``rungs - 2`` holes
    from 6 rungs on (the first cells merge with the rails' ends)."""
    path = [(0.0, 0.0)]
    for k in range(rungs):
        x = 40.0 * k
        path += ([(x, 100.0), (x + 40.0, 100.0), (x + 40.0, 0.0), (x, 0.0)] if k % 2 == 0 else
                 [(x + 40.0, 0.0), (x + 40.0, 100.0), (x, 100.0)])
    path = [*dict.fromkeys(path), (0.0, 0.0)]
    rings = [tuple((round(x, 7), round(y, 7)) for x, y in ring)
             for ring in polyline_footprint(path, width)]
    ((outer, holes),) = group_rings(rings)
    return outer, holes


# ── triangulation ─────────────────────────────────────────────────────────────


class TestTriangulateRegion:
    def test_without_holes_it_is_the_qt3d_ear_clipper(self) -> None:
        points, triangles = triangulate_region(L_SHAPE)
        assert points == L_SHAPE and triangles == triangulate_polygon(L_SHAPE)
        assert len(triangles) == 4

    def test_the_moved_function_is_one_object_everywhere(self) -> None:
        """``triangulate_polygon`` left ``legacy.py`` (it outlives it); every old
        import path still reaches the same function."""
        assert legacy_module.triangulate_polygon is polygon_module.triangulate_polygon
        assert scene3d.triangulate_polygon is polygon_module.triangulate_polygon
        assert legacy_module.sun_direction_scene is scene3d.frame.sun_direction_scene

    def test_a_frame(self) -> None:
        assert_triangulates(SQUARE, (rect(40.0, 40.0, 60.0, 60.0, clockwise=True),))

    def test_the_closed_fence(self) -> None:
        rings = [tuple(r) for r in polyline_footprint(
            [(0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0), (0.0, 800.0), (0.0, 0.0)], 10.0)]
        ((outer, holes),) = group_rings(rings)
        assert_triangulates(outer, holes)
        _points, triangles = triangulate_region(outer, holes)
        cap = sum(tri_area(_points, t) for t in triangles)
        assert cap == pytest.approx(35962.0, abs=1.0)  # the stroke — not 1,600,162

    def test_several_holes_and_a_concave_outer(self) -> None:
        outer = ((0.0, 0.0), (300.0, 0.0), (300.0, 100.0), (200.0, 100.0), (200.0, 200.0),
                 (300.0, 200.0), (300.0, 300.0), (0.0, 300.0))
        holes = (rect(20.0, 20.0, 80.0, 80.0, clockwise=True),
                 rect(120.0, 20.0, 180.0, 80.0, clockwise=True),
                 rect(20.0, 220.0, 180.0, 280.0, clockwise=True),
                 rect(60.0, 120.0, 140.0, 180.0, clockwise=True))
        assert_triangulates(outer, holes)

    def test_a_hole_that_only_sees_another_hole(self) -> None:
        """The inner hole is boxed in by a C-shaped hole: its only neighbours are
        that hole's vertices, so it can be bridged only after the C is."""
        outer = rect(0.0, 0.0, 400.0, 400.0)
        c_hole = ((100.0, 100.0), (100.0, 300.0), (300.0, 300.0), (300.0, 260.0), (140.0, 260.0),
                  (140.0, 140.0), (300.0, 140.0), (300.0, 100.0))
        assert signed_area(c_hole) < 0
        inner = rect(170.0, 170.0, 230.0, 230.0, clockwise=True)
        assert_triangulates(outer, (inner, c_hole))
        assert_triangulates(outer, (c_hole, inner))

    def test_a_stroke_that_crosses_itself_twice(self) -> None:
        """Two triangles and the diamond between them: three holes in one outer."""
        rings = [tuple(r) for r in polyline_footprint(
            [(0.0, 0.0), (300.0, 300.0), (600.0, 0.0), (600.0, 300.0), (300.0, 0.0), (0.0, 300.0),
             (0.0, 0.0)], 10.0)]
        ((outer, holes),) = group_rings(rings)
        assert len(holes) == 3
        assert_triangulates(outer, holes)

    @pytest.mark.parametrize("seed", range(12))
    def test_random_stars_with_random_holes(self, seed: int) -> None:
        rng = random.Random(seed)
        count = rng.randrange(5, 14)
        outer = tuple(
            (r * math.cos(a), r * math.sin(a))
            for a, r in ((2 * math.pi * k / count, rng.uniform(600.0, 1000.0)) for k in range(count))
        )
        assert is_simple_ring(outer) and signed_area(outer) > 0
        holes = []
        for k in range(rng.randrange(1, 5)):  # small convex holes on a ring of radius 300
            angle = 2 * math.pi * k / 4 + rng.uniform(-0.2, 0.2)
            cx, cy = 300.0 * math.cos(angle), 300.0 * math.sin(angle)
            sides = rng.randrange(3, 8)
            radius = rng.uniform(40.0, 110.0)
            holes.append(tuple(
                (cx + radius * math.cos(-2 * math.pi * j / sides), cy + radius * math.sin(-2 * math.pi * j / sides))
                for j in range(sides)
            ))
        assert all(signed_area(h) < 0 for h in holes)
        assert_triangulates(outer, tuple(holes))

    def test_rings_that_touch_are_refused_not_guessed(self) -> None:
        """A hole lying ON the outer ring has no bridge that touches nothing: the
        function raises rather than return a cap it cannot vouch for."""
        outer = rect(0.0, 0.0, 100.0, 100.0)
        hole = rect(0.0, 0.0, 100.0, 100.0, clockwise=True)  # the same square
        with pytest.raises(ValueError):
            triangulate_region(outer, (hole,))


# ── fix round 2: the cost of many holes, and the one predicate ────────────────


class TestManyHoles:
    """Review round 2, P2-4. A ladder drawn as one stroke: 20 holes took 24 ms in
    the first version and 58 holes 2.6 s — on every geometry tick of that item
    (and a closed fence along a traced outline of 400 vertices 12.6 s). The
    bridge of a hole is now found in one pass over the edges."""

    @pytest.mark.parametrize("rungs", [4, 20, 60])
    def test_a_ladder_triangulates(self, rungs: int) -> None:
        outer, holes = review_ladder(rungs)
        assert len(holes) >= rungs - 2
        assert_triangulates(outer, holes, flat_corners=True)

    def test_an_ear_without_an_area_yields_no_triangle(self) -> None:
        """Found by this round's own test of the ladder. Its long diagonal is
        crossed by every rung, so vertices of the outer ring and of several holes
        lie on ONE line — the diagonal's edge. Ears along it have a doubled area
        of 1e-14 cm² (noise around an exact zero): counter-clockwise by luck,
        nothing in fact, and in the engine's float32 thirteen of them came out
        wound DOWNWARDS (``Mesh.validate`` refused the fence). They are clipped
        and yield no triangle."""
        outer, holes = review_ladder(20)
        points, triangles = triangulate_region(outer, holes)
        full = len(points) + 2 * len(holes) - 2
        assert (full, len(triangles)) == (239, 226)  # 13 ears without an area
        areas = [tri_area(points, t) for t in triangles]
        assert min(areas) > 0.009 and sum(areas) == pytest.approx(
            regions_area(((outer, holes),)), rel=1e-12)
        assert polygon_module._FLAT_CORNER == 4e-15

    def test_the_work_per_hole_is_one_pass_not_a_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The cliff, pinned as a COUNT (a clock would be a flake on a loaded
        box): each hole tests ONE block of nearby boundary vertices against the
        edges. Measured: 58 blocks for 58 holes, 94 for 94."""
        blocks = 0
        touch = polygon_module._touch

        def counting(*args):
            nonlocal blocks
            blocks += 1
            return touch(*args)

        monkeypatch.setattr(polygon_module, "_touch", counting)
        for rungs in (60, 100):
            outer, holes = review_ladder(rungs)
            blocks = 0
            triangulate_region(outer, holes)
            assert len(holes) <= blocks <= 2 * len(holes), (rungs, len(holes), blocks)

    def test_beyond_the_bound_it_refuses_instead_of_freezing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``triangulate_region`` on its own is bounded like ``cut_region``."""
        outer, holes = review_ladder(20)
        assert (len(holes), len(outer) + sum(len(h) for h in holes)) == (20, 201)
        floor = polygon_module._triangulation_floor(len(outer), [len(h) for h in holes])
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", floor - 1)
        with monkeypatch.context() as patch:
            # refused from the sizes, BEFORE the first bridge: without that check the work
            # would stop only when the budget ran out, twenty bridges later
            patch.setattr(polygon_module, "_bridge_position", never("a bridge was looked for"))
            with pytest.raises(RegionTooLargeError, match="201 vertices with 20 holes is beyond"):
                triangulate_region(outer, holes)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", 10 * floor)
        assert len(triangulate_region(outer, holes)[1]) == 226

    def test_a_closed_fence_along_a_traced_outline(self) -> None:
        """One hole, many vertices: 400 path vertices → 1,201 ring vertices. The
        first version took 12.6 s for this region; it is cut and proven here."""
        rng = random.Random(400)
        path = list(_wobbly(400, rng, tangle=False))
        rings = [tuple((round(x, 7), round(y, 7)) for x, y in ring)
                 for ring in polyline_footprint([*path, path[0]], 4.0)]
        ((outer, holes),) = group_rings(rings)
        assert len(holes) == 1 and len(outer) + len(holes[0]) > 800
        vertices, triangles = polygon_module.cut_region(outer, holes)
        assert len(triangles) == len(vertices)  # n + 2h - 2 with one hole
        assert sum(tri_area(vertices, t) for t in triangles) == pytest.approx(
            regions_area(((outer, holes),)), rel=1e-9)


class TestLargeRingsWithoutHoles:
    """Fix round 2. The predicate asks for the cap's triangulation in the snapshot,
    so a traced outline under edit pays the ear clipper on every tick. The plain
    loop needs 272 ms for 1,000 vertices; the array clipper 30 ms."""

    def test_small_rings_take_the_shared_clipper_and_large_ones_the_arrays(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        used: list[str] = []
        shared, arrays = polygon_module.triangulate_polygon, polygon_module._ear_clip
        monkeypatch.setattr(polygon_module, "triangulate_polygon",
                            lambda ring: used.append("shared") or shared(ring))
        monkeypatch.setattr(polygon_module, "_ear_clip", lambda points, loop, work:
                            used.append("arrays") or arrays(points, loop, work))
        threshold = polygon_module.ARRAY_EAR_CLIP_FROM
        assert threshold == 256
        rng = random.Random(11)
        below, at = _wobbly(threshold - 1, rng, tangle=False), _wobbly(threshold, rng, tangle=False)
        assert triangulate_region(below)[1] == shared(below)  # the Qt 3D view's triangles, exactly
        assert len(triangulate_region(at)[1]) == threshold - 2
        assert used == ["shared", "arrays"]
        used.clear()
        triangulate_region(at[::-1])  # clockwise: only the shared clipper takes either winding
        assert used == ["shared"]

    @pytest.mark.parametrize("n", [256, 400, 1000])
    def test_a_large_ring_is_cut_correctly(self, n: int) -> None:
        ring = _wobbly(n, random.Random(n), tangle=False)
        vertices, triangles = polygon_module.cut_region(ring)  # … and proven
        assert vertices == ring and len(triangles) == n - 2
        areas = [tri_area(vertices, t) for t in triangles]
        assert min(areas) > 0.0 and sum(areas) == pytest.approx(signed_area(ring), rel=1e-9)
        assert sorted({i for t in triangles for i in t}) == list(range(n))  # every vertex is used
        assert is_buildable_region(ring)

    def test_a_ring_the_array_clipper_cannot_finish_is_not_handed_to_the_plain_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Round 2 let the shared clipper try such a ring — the plain loop, which
        needs 272 ms for 1,000 vertices and has no bound at all. A large ring is
        cut by the counted clipper or not at all."""
        def gives_up(_points, _loop, _work):
            raise ValueError("no ear")

        def never(_ring):
            raise AssertionError("the plain loop was asked to cut a large ring")

        ring = _wobbly(300, random.Random(3), tangle=False)
        monkeypatch.setattr(polygon_module, "_ear_clip", gives_up)
        monkeypatch.setattr(polygon_module, "triangulate_polygon", never)
        with pytest.raises(ValueError, match="no ear"):
            triangulate_region(ring)

    def test_a_large_ring_with_collinear_runs(self) -> None:
        """A rectangle with a vertex every centimetre along each side: 400 vertices,
        396 of them on a straight line between their neighbours."""
        ring = tuple([(float(x), 0.0) for x in range(100)] + [(100.0, float(y)) for y in range(100)]
                     + [(float(100 - x), 100.0) for x in range(100)]
                     + [(0.0, float(100 - y)) for y in range(100)])
        assert len(ring) == 400 and is_simple_ring(ring)
        vertices, triangles = polygon_module.cut_region(ring)
        assert sum(tri_area(vertices, t) for t in triangles) == pytest.approx(10000.0, rel=1e-12)
        assert min(tri_area(vertices, t) for t in triangles) > 0.0


def comb(teeth: int):
    """The ear clipper's worst case: every tooth has to wait for its neighbour."""
    points = [(0.0, 0.0)]
    x = 0.0
    for _ in range(teeth):
        points += [(x, 200.0), (x + 5.0, 200.0), (x + 5.0, 10.0), (x + 10.0, 10.0)]
        x += 10.0
    points += [(x, 200.0), (x + 5.0, 200.0), (x + 5.0, 0.0)]
    return ccw(tuple(points))


def hidden_bridges(dense: int, small: int):
    """The bridge search's worst case: small holes whose NEAREST boundary
    vertices all look at them and cannot be reached. A long thin wall stands
    between them and a hole whose near side is ``dense`` vertices: every one of
    those passes the corner test, and every bridge to one crosses the wall."""
    height = 700.0
    outer = ((-400.0, -50.0), (400.0, -50.0), (400.0, height + 50.0), (-400.0, height + 50.0))
    wall = ((0.5, 0.0), (0.5, height), (1.0, height), (1.0, 0.0))
    near_side = [(2.0 + (0.3 if k % 2 else 0.0), height * k / dense) for k in range(dense + 1)]
    crowd = (*near_side, (3.0, height), (3.0, 0.0))
    holes = [wall, crowd]
    for k in range(small):
        y = height * (k + 0.5) / small
        holes.append(((-3.0, y), (-6.0, y - 1.0), (-6.0, y + 1.0)))
    assert all(signed_area(hole) < 0.0 for hole in holes)
    return outer, tuple(holes)


@pytest.fixture
def fresh_verdicts():
    """A test that moves the bound must not read — or leave behind — a verdict
    reached under another one."""
    polygon_module._examined.cache_clear()
    yield
    polygon_module._examined.cache_clear()


class TestTheWorkBound:
    """Review round 3, P2-1. Round 2 bounded the SIZE of a region with holes — and
    judged it after the quadratic simplicity test, so saying no cost more than
    saying yes (2,700 traced points: 2.59 s to refuse), left rings without holes
    unbounded (a comb of 5,004 vertices: 1.5 s per tick), and was no bound on
    work at all (7,187 vertices and 61 holes, inside both limits: 4.0 s).

    Now ONE bound, on work, for every region; counted, so that it is the same on
    every machine — and these tests can pin it without a clock."""

    def test_the_size_is_judged_before_anything_that_costs(
        self, monkeypatch: pytest.MonkeyPatch, fresh_verdicts: None
    ) -> None:
        def never(*_args):
            raise AssertionError("work was done on a region that is refused for its size")

        outer, holes = review_ladder(20)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", region_work(outer, holes) - 1)
        monkeypatch.setattr(polygon_module, "_is_simple", never)
        monkeypatch.setattr(polygon_module, "_triangulate", never)
        assert exceeds_work_bound(outer, holes)
        with pytest.raises(RegionTooLargeError, match="201 vertices with 20 holes is beyond"):
            polygon_module.cut_region(outer, holes)
        assert not is_buildable_region(outer, holes) and is_region_too_large(outer, holes)
        assert issubclass(RegionTooLargeError, ValueError)  # … like every other refusal
        # … and the cut itself asks first, whoever calls it: its own check, not the caller's
        # (the first mutation run of this round removed it and nothing noticed)
        with pytest.raises(RegionTooLargeError, match="201 vertices with 20 holes is beyond"):
            cut_work(outer, holes)

    def test_region_work_reads_sizes_only(self) -> None:
        """Asking costs nothing: no coordinate is looked at — rings of the same
        SIZES have the same floor, whatever they hold."""
        outer, holes = review_ladder(20)
        blanks = tuple(((0.0, 0.0),) * len(hole) for hole in holes)
        assert region_work(outer, holes) == region_work(((0.0, 0.0),) * len(outer), blanks)
        # the price list, once by hand: a region, its simplicity test, its ears
        assert region_work(SQUARE) == 3_000 + 250 * 16 + 200 * 16 == cut_work(SQUARE)

    @pytest.mark.parametrize(
        ("label", "region"),
        [("a square", (SQUARE, ())), ("an L", (L_SHAPE, ())),
         ("a frame", (SQUARE, (rect(40.0, 40.0, 60.0, 60.0, clockwise=True),))),
         ("a traced ring of 255", (_wobbly(255, random.Random(1), tangle=False), ())),
         ("a traced ring of 256", (_wobbly(256, random.Random(2), tangle=False), ())),
         ("a traced ring of 900", (_wobbly(900, random.Random(3), tangle=False), ())),
         ("a comb of 80 teeth", (comb(80), ())),
         ("a ladder of 20 rungs", review_ladder(20)), ("a ladder of 60 rungs", review_ladder(60)),
         ("hidden bridges", hidden_bridges(200, 10))],
    )
    def test_the_floor_is_a_floor(self, label: str, region) -> None:
        """``region_work`` promises the LEAST a cut can cost. Were it ever more
        than the cut, a region the cutter can cut would be refused unseen."""
        outer, holes = region
        floor, spent = region_work(outer, holes), cut_work(outer, holes)
        assert 0 < floor <= spent, label
        assert spent == cut_work(outer, holes)  # a count: the same every time

    def test_what_the_awkward_shapes_cost_beyond_their_floor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Why the work is counted WHILE a region is cut and not only read off its
        size: the shape decides what the ears and the bridges cost."""
        teeth = comb(80)
        easy = _wobbly(len(teeth), random.Random(5), tangle=False)
        assert region_work(teeth) == region_work(easy)  # the same size: the same promise …
        assert cut_work(teeth) > 3 * cut_work(easy)  # … and more than three times the work
        outer, holes = hidden_bridges(200, 10)
        blocks = 0
        touch = polygon_module._touch

        def counting(*args):
            nonlocal blocks
            blocks += 1
            return touch(*args)

        monkeypatch.setattr(polygon_module, "_touch", counting)
        assert cut_work(outer, holes) > 1.4 * region_work(outer, holes)
        assert blocks > 4 * len(holes)  # a bridge that is found at the first try takes one
        assert polygon_module.is_buildable_region(outer, holes)  # awkward, and cut correctly

    @pytest.mark.parametrize("which", ["ears", "bridges"])
    def test_a_cut_that_outgrows_its_floor_is_stopped_on_the_way(
        self, monkeypatch: pytest.MonkeyPatch, fresh_verdicts: None, which: str
    ) -> None:
        outer, holes = (comb(80), ()) if which == "ears" else hidden_bridges(200, 10)
        floor, spent = region_work(outer, holes), cut_work(outer, holes)
        payments = 0
        pay = polygon_module.WorkBudget.spend

        def counting(self, units):
            nonlocal payments
            payments += 1
            pay(self, units)

        monkeypatch.setattr(polygon_module.WorkBudget, "spend", counting)
        cut_work(outer, holes)
        whole, payments = payments, 0
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", floor + (spent - floor) // 4)
        assert not exceeds_work_bound(outer, holes)  # its size alone does not give it away
        with pytest.raises(RegionTooLargeError):
            polygon_module.cut_region(outer, holes)
        assert 0 < payments < whole  # it stopped on the way: the rest of the work was never done
        assert is_region_too_large(outer, holes) and not is_buildable_region(outer, holes)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", spent)
        polygon_module._examined.cache_clear()
        assert is_buildable_region(outer, holes)  # exactly at the bound it is cut

    @pytest.mark.parametrize("vertices", [200, 300])
    def test_a_ring_without_holes_is_bounded_too(
        self, monkeypatch: pytest.MonkeyPatch, fresh_verdicts: None, vertices: int
    ) -> None:
        """Round 2: "a region without holes has no limit here". Below
        ``ARRAY_EAR_CLIP_FROM`` (the shared clipper) and above it (the counted one)."""
        ring = _wobbly(vertices, random.Random(vertices), tangle=False)
        spent = cut_work(ring)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", spent - 1)
        with pytest.raises(RegionTooLargeError):
            polygon_module.cut_region(ring)
        with pytest.raises(RegionTooLargeError):
            cut_work(ring)
        assert is_region_too_large(ring)

    def test_a_refusal_is_remembered_and_the_two_kinds_are_told_apart(
        self, monkeypatch: pytest.MonkeyPatch, fresh_verdicts: None
    ) -> None:
        cuts = 0
        real = polygon_module._cut

        def counting(outer, holes, work):
            nonlocal cuts
            cuts += 1
            return real(outer, holes, work)

        monkeypatch.setattr(polygon_module, "_cut", counting)
        bow = LOPSIDED_BOW_TIE[::-1]
        for _ in range(3):
            assert not is_buildable_region(bow) and not is_region_too_large(bow)  # its SHAPE
        assert cuts == 1
        teeth = comb(80)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", region_work(teeth) + 1)
        for _ in range(3):
            assert is_region_too_large(teeth) and not is_buildable_region(teeth)
        assert cuts == 2  # what such a refusal costs — up to the whole bound — is paid once

    def test_few_and_many_vertices_near_an_ear_are_judged_alike(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ear test has two bodies — written out for a handful of vertices,
        on arrays for many. They must cut the same triangles."""
        regions = [review_ladder(20), (comb(70), ()), hidden_bridges(100, 6),
                   (_wobbly(300, random.Random(9), tangle=False), ())]
        monkeypatch.setattr(polygon_module, "_FEW_NEAR", 10**9)
        one_by_one = [triangulate_region(outer, holes)[1] for outer, holes in regions]
        monkeypatch.setattr(polygon_module, "_FEW_NEAR", -1)
        on_arrays = [triangulate_region(outer, holes)[1] for outer, holes in regions]
        assert one_by_one == on_arrays and all(len(triangles) > 60 for triangles in one_by_one)

    def test_a_large_outer_ring_is_asked_on_arrays_and_answers_the_same(self) -> None:
        """``group_rings`` asks an outer ring once per hole. From 32 vertices the
        ring answers on arrays — the same answer, also for a point level with a
        vertex, where the plain test's own rule decides."""
        rng = random.Random(77)
        for n in (5, 31, 32, 200):
            ring = _wobbly(n, rng, tangle=False)
            holds = polygon_module._ring_holds(ring)
            points = [(rng.uniform(-450.0, 450.0), rng.uniform(-450.0, 450.0)) for _ in range(300)]
            points += [(x + dx, y) for x, y in ring[:20] for dx in (-1.0, 0.0, 1.0)]  # level with a vertex
            assert [holds(x, y) for x, y in points] == [point_in_ring(x, y, ring) for x, y in points]
            assert any(holds(x, y) for x, y in points) and not all(holds(x, y) for x, y in points)
        outer, holes = review_ladder(60)
        assert len(outer) >= 32
        assert group_rings([*holes, outer]) == ((outer, holes),)


class TestBuildable:
    """THE predicate: a region may be handed to a builder exactly when the default
    builder's own triangulation cuts it and the cut is proven."""

    HOLE = rect(40.0, 40.0, 60.0, 60.0, clockwise=True)

    def test_what_is_buildable(self) -> None:
        assert is_buildable_region(SQUARE)
        assert is_buildable_region(SQUARE, (self.HOLE,))
        assert is_buildable_region(L_SHAPE, ())
        outer, holes = review_ladder(20)
        assert is_buildable_region(outer, holes)

    @pytest.mark.parametrize(
        ("label", "outer", "holes"),
        [("a clockwise outer ring", SQUARE[::-1], ()),
         ("an outer ring that crosses itself", LOPSIDED_BOW_TIE[::-1], ()),
         ("an outer ring without area", ((0.0, 0.0), (10.0, 0.0), (20.0, 0.0)), ()),
         ("a counter-clockwise hole", SQUARE, (rect(40.0, 40.0, 60.0, 60.0),)),
         ("a hole that crosses itself", rect(0.0, 0.0, 400.0, 400.0),
          (((100.0, 100.0), (300.0, 300.0), (300.0, 100.0), (100.0, 250.0)),)),
         ("a hole on the outer ring", SQUARE, (SQUARE[::-1],)),
         ("a hole that reaches outside", SQUARE, (rect(50.0, 40.0, 150.0, 60.0, clockwise=True),)),
         ("a hole outside", SQUARE, (rect(200.0, 40.0, 250.0, 60.0, clockwise=True),)),
         ("two holes that overlap", SQUARE, (rect(20.0, 20.0, 60.0, 60.0, clockwise=True),
                                             rect(40.0, 40.0, 80.0, 80.0, clockwise=True))),
         ("two holes that touch in a point", SQUARE, (rect(20.0, 20.0, 50.0, 50.0, clockwise=True),
                                                      rect(50.0, 50.0, 80.0, 80.0, clockwise=True)))],
    )
    def test_what_is_not(self, label: str, outer, holes) -> None:
        assert not is_buildable_region(tuple(outer), tuple(holes)), label
        with pytest.raises(ValueError):
            polygon_module.cut_region(tuple(outer), tuple(holes))

    def test_touching_is_not_refused_for_its_own_sake(self) -> None:
        """The predicate is "it can be cut and the cut is proven", not "the rings
        keep their distance": a hole that touches the outer ring in one point is a
        region with a pinch, and it is cut correctly."""
        diamond = ((0.0, 50.0), (50.0, 80.0), (80.0, 50.0), (50.0, 20.0))
        assert is_buildable_region(SQUARE, (diamond,))
        assert_triangulates(SQUARE, (diamond,), flat_corners=True)

    def test_cut_region_is_the_triangulation_with_the_proof(self) -> None:
        vertices, triangles = polygon_module.cut_region(SQUARE, (self.HOLE,))
        points, plain = triangulate_region(SQUARE, (self.HOLE,))
        assert vertices == points and triangles == tuple(plain)
        assert isinstance(triangles, tuple)  # cached: nobody can edit what the next caller gets
        assert sum(tri_area(vertices, t) for t in triangles) == 10000.0 - 400.0

    def test_a_wrong_triangulation_does_not_get_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The proof is not decoration: a triangulation that forgets the hole, or
        winds a triangle downwards, is refused whatever produced it."""
        polygon_module._examined.cache_clear()
        filled = (tuple(SQUARE) + tuple(self.HOLE), [(0, 1, 2), (0, 2, 3)])  # covers the hole too
        monkeypatch.setattr(polygon_module, "_triangulate", lambda *_a: filled)
        with pytest.raises(ValueError, match="covers 10000.0 cm"):
            polygon_module.cut_region(SQUARE, (self.HOLE,))
        flipped = (tuple(SQUARE), [(0, 1, 2), (0, 3, 2), (0, 2, 3), (0, 2, 3)])  # the sum is right
        monkeypatch.setattr(polygon_module, "_triangulate", lambda *_a: flipped)
        with pytest.raises(ValueError, match="smallest triangle -5000.0"):
            polygon_module.cut_region(SQUARE)
        with pytest.raises(ValueError, match="smallest triangle -5000.0"):
            polygon_module.cut_region(SQUARE)  # a refusal is remembered WITH its words
        polygon_module._examined.cache_clear()

    def test_both_answers_are_remembered(self) -> None:
        """The snapshot asks on every tick; a region that cannot be built must not
        be tried again each time."""
        outer = tuple((x + 0.125, y) for x, y in SQUARE)  # a region no other test has asked about
        reaching_out = (tuple((x + 0.125, y) for x, y in rect(50.0, 40.0, 150.0, 60.0, clockwise=True)),)
        before = polygon_module._examined.cache_info()
        assert not is_buildable_region(outer, reaching_out)
        assert not is_buildable_region(outer, reaching_out)
        assert is_buildable_region(outer) and is_buildable_region(outer)
        after = polygon_module._examined.cache_info()
        assert (after.misses - before.misses, after.hits - before.hits) == (2, 2)

    def test_the_default_builder_builds_exactly_what_the_predicate_accepts(self) -> None:
        from open_garden_planner.core.scene3d import prism_mesh

        outer, holes = review_ladder(20)
        mesh = prism_mesh((outer,), 120.0, (holes,))
        mesh.validate()
        assert mesh.vertex_count
        overlapping = (rect(20.0, 20.0, 60.0, 60.0, clockwise=True),
                       rect(40.0, 40.0, 80.0, 80.0, clockwise=True))
        assert not is_buildable_region(SQUARE, overlapping)
        with pytest.raises(ValueError):
            prism_mesh((SQUARE,), 120.0, (overlapping,))


# ── fix round 3, the security finding: bound the input before the work, and the sum ──


def never(what: str):
    def called(*_args, **_kwargs):
        raise AssertionError(f"{what} — on something that is refused for its size")
    return called


class TestWhatIsRemembered:
    """``lru_cache`` bounds the number of answers. An answer about a traced outline
    is a thousand times an answer about a rectangle, so 2,048 of them were a
    gigabyte — and a ring of a million vertices was hashed, and kept, like any
    other. ``ring_keyed`` bounds the VERTICES held."""

    @staticmethod
    def ring(n: int, at: float = 0.0):
        return tuple((at + float(k), float(k * k % 7)) for k in range(n))

    def test_it_holds_vertices_not_answers(self) -> None:
        calls = []

        @ring_keyed(1_000)
        def length(ring) -> int:
            calls.append(len(ring))
            return len(ring)

        a, b, c = self.ring(300), self.ring(300, 1.0), self.ring(300, 2.0)
        assert [length(a), length(b), length(c), length(a), length(b), length(c)] == [300] * 6
        assert calls == [300, 300, 300]  # 924 vertices and three entries: all three are held
        assert length.cache_info() == (3, 3, 1_000, 3 * 308, 3)
        length(a)  # … a is now the most recently asked
        length(self.ring(300, 3.0))  # 1,232 > 1,000: the least recently asked go, down to 750
        info = length.cache_info()
        assert info.vertices <= 750 and info.entries == 2
        calls.clear()
        length(a)
        assert calls == []  # a was asked last before the new one came: it stayed
        length(b)
        assert calls == [300]  # b went

    def test_many_small_answers_are_bounded_too(self) -> None:
        @ring_keyed(1_000)
        def length(ring) -> int:
            return len(ring)

        for k in range(5_000):
            length(((float(k), 0.0), (1.0, 0.0), (0.0, 1.0)))
        info = length.cache_info()
        assert info.vertices <= 1_000 and info.entries <= 1_000 // (3 + 8)

    def test_what_the_answer_holds_counts(self) -> None:
        @ring_keyed(1_000, holds=len)
        def doubled(ring):
            return ring + ring

        doubled(self.ring(100))
        assert doubled.cache_info().vertices == 8 + 100 + 200

    def test_a_ring_beyond_the_cap_is_answered_and_never_kept(self) -> None:
        hashed = []

        class Watched(tuple):
            def __hash__(self) -> int:
                hashed.append(len(self))
                return super().__hash__()

        huge = Watched(self.ring(MAX_ITEM_VERTICES + 1))
        before = ring_area.cache_info()
        assert ring_area(huge) == polygon_module._signed_area(huge)
        assert ring_area.cache_info() == before and hashed == []  # not looked up, not hashed, not held
        at_the_cap = Watched(self.ring(MAX_ITEM_VERTICES))
        ring_area(at_the_cap)
        assert hashed and ring_area.cache_info().entries == before.entries + 1
        ring_area.cache_clear()

    def test_an_answer_worked_out_elsewhere_can_be_kept(self) -> None:
        @ring_keyed(1_000)
        def length(ring) -> int:
            raise AssertionError("it was computed")

        assert length.known(SQUARE) is None
        length.remember((SQUARE,), 4)
        assert length.known(SQUARE) == 4 == length(SQUARE)
        assert length.cache_info()[:2] == (2, 1) and length.cache_info().entries == 1
        huge = self.ring(MAX_ITEM_VERTICES + 1)
        length.remember((huge,), 0)  # too large to be a key: not kept …
        assert length.known(huge) is None and length.cache_info().entries == 1

    def test_the_real_ones_are_bounded_by_vertices(self) -> None:
        from open_garden_planner.core.scene3d import record as record_module

        assert HELD_VERTICES == 262_144 and MAX_ITEM_VERTICES == 16_384
        for function in (ring_area, polygon_module._examined, record_module._ring_facts):
            assert function.cache_info().max_vertices == HELD_VERTICES, function.__name__
        assert not hasattr(is_simple_ring, "cache_info")  # its one caller is remembered; it is not

    def test_an_exception_is_not_remembered_and_keywords_are_not_keys(self) -> None:
        calls = []

        @ring_keyed(1_000)
        def picky(ring, strict=False) -> int:
            calls.append(strict)
            if not ring:
                raise ValueError("empty")
            return len(ring)

        for _ in range(2):
            with pytest.raises(ValueError):
                picky(())
        assert picky(SQUARE, strict=True) == 4 == picky(SQUARE, strict=True)
        assert calls == [False, False, True, True] and picky.cache_info().entries == 0

    def test_a_region_beyond_the_bound_is_never_a_key(
        self, monkeypatch: pytest.MonkeyPatch, fresh_verdicts: None
    ) -> None:
        """Sized up from the LENGTHS of its rings — before it is hashed."""
        outer, holes = review_ladder(20)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", region_work(outer, holes) - 1)
        assert is_region_too_large(outer, holes) and not is_buildable_region(outer, holes)
        assert region_cost(outer, holes) == 0  # refused from its size alone: nothing was spent
        assert polygon_module._examined.cache_info().entries == 0
        huge = self.ring(100_000)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", 150_000_000)
        monkeypatch.setattr(polygon_module, "_is_simple", never("the simplicity test ran"))
        assert is_region_too_large(huge) and not is_buildable_region(huge)
        assert polygon_module._examined.cache_info().entries == 0


class TestTouchingPairs:
    """What the clipper's work on an outline depends on, counted before the
    clipper sees the outline."""

    @staticmethod
    def brute(points, closed: bool) -> int:
        n = len(points) if closed else len(points) - 1
        count = 0
        for i in range(n):
            for j in range(i + 2, n):
                if closed and i == 0 and j == n - 1:
                    continue
                if segments_touch(points[i], points[(i + 1) % len(points)],
                                  points[j], points[(j + 1) % len(points)]):
                    count += 1
        return count

    @pytest.mark.parametrize(
        ("label", "points", "closed", "touching"),
        [("a square", SQUARE, True, 0), ("a bow-tie", BOW_TIE, True, 1), ("a pentagram", PENTAGRAM, True, 5),
         ("an open path", ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (20.0, 10.0)), False, 0),
         ("a path that crosses itself", ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (5.0, 10.0), (5.0, -5.0)), False, 1),
         ("a path closed on its start", (*SQUARE, SQUARE[0]), False, 1),
         ("a path walked there and back", ((0.0, 0.0), (10.0, 0.0), (0.0, 0.0), (10.0, 0.0)), False, 1),
         ("two points", ((0.0, 0.0), (10.0, 0.0)), False, 0), ("nothing", (), True, 0)],
    )
    def test_what_touches(self, label: str, points, closed: bool, touching: int) -> None:
        near, found = touching_pairs(points, WorkBudget(), closed=closed)
        assert found == touching == self.brute(points, closed), label
        assert near >= found

    def test_it_counts_what_the_plain_loop_counts(self) -> None:
        rng = random.Random(11)
        for n in (5, 31, 64, 700):
            for closed in (True, False):
                points = tuple((rng.uniform(0.0, 100.0), rng.uniform(0.0, 100.0)) for _ in range(n))
                _near, touching = touching_pairs(points, WorkBudget(budget=10**12), closed=closed)
                assert touching == self.brute(points, closed), (n, closed)
                assert touching > 0 or n == 5

    def test_the_reach_widens_what_is_near_and_nothing_else(self) -> None:
        rungs = tuple((float(x), float(y)) for k in range(40) for x, y in ((k * 10, 0), (k * 10, 100))[::1 if k % 2 else -1])
        plain = touching_pairs(rungs, WorkBudget(), closed=False)
        wide = touching_pairs(rungs, WorkBudget(), closed=False, reach=12.0)
        assert plain == (0, 0)  # the rungs stand 10 apart and never touch
        assert wide[1] == 0 and wide[0] > 70  # … but strokes 24 wide would overlap their neighbours

    def test_the_count_is_paid_for_before_it_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        points = tuple((float(k), float(k * k % 13)) for k in range(200))
        monkeypatch.setattr(polygon_module.np, "asarray", never("an array was built"))
        with pytest.raises(RegionTooLargeError):
            touching_pairs(points, WorkBudget(budget=3 * 200 * 200 - 1), closed=True)

    def test_the_near_pairs_are_paid_for_before_they_are_tested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rng = random.Random(3)
        scribble = tuple((rng.uniform(0.0, 100.0), rng.uniform(0.0, 100.0)) for _ in range(120))
        whole = WorkBudget(budget=10**12)
        near, touching = touching_pairs(scribble, whole, closed=False)
        assert near > 2_000 and whole.spent == 3 * 119 * 119 + 350 * near
        monkeypatch.setattr(polygon_module, "_touch", never("the pairs were tested"))
        with pytest.raises(RegionTooLargeError):
            touching_pairs(scribble, WorkBudget(budget=3 * 119 * 119 + 100), closed=False)

    def test_all_of_them_before_the_first_is_tested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A path of 1,100 segments is counted in three blocks. With one unit less
        than ALL its near pairs cost, not one pair is tested — a path whose near
        pairs alone are beyond the budget is refused on the count (testing them
        block by block as they were paid took as long as the bound itself)."""
        rng = random.Random(5)
        scribble = tuple((rng.uniform(0.0, 100.0), rng.uniform(0.0, 100.0)) for _ in range(1_101))
        whole = WorkBudget(budget=10**12)
        tested = []
        real = polygon_module._touch
        monkeypatch.setattr(polygon_module, "_touch", lambda *args: (tested.append(len(args[0])), real(*args))[1])
        near, _touching = touching_pairs(scribble, whole, closed=False)
        assert len(tested) == 3 and sum(tested) == near  # three blocks, every near pair once
        tested.clear()
        with pytest.raises(RegionTooLargeError):
            touching_pairs(scribble, WorkBudget(budget=whole.spent - 1), closed=False)
        assert tested == []


class TestStackHeight:
    """A sweep line carries every edge it crosses: teeth that stand side by side
    cost the clipper their number squared without crossing anything (measured:
    4,000 points, 1.6 s standing, 4 ms lying down)."""

    def test_standing_and_lying(self) -> None:
        teeth = [(k * 30.0, 1000.0 + k if k % 2 else -float(k)) for k in range(400)]
        assert stack_height([teeth], closed=False) == 399
        assert stack_height([[(y, x) for x, y in teeth]], closed=False) == 2
        assert stack_height([SQUARE], closed=True) == 3  # a line along an edge meets it and both sides
        assert stack_height([SQUARE], closed=False) == 2
        assert stack_height([], closed=True) == 0 == stack_height([((1.0, 1.0),)], closed=True)

    def test_several_rings_and_the_reach(self) -> None:
        low, high = rect(0.0, 0.0, 10.0, 10.0), rect(0.0, 20.0, 10.0, 30.0)
        assert stack_height([low, high], closed=True) == 3
        assert stack_height([low, high], closed=True, reach=5.0) == 6  # widened by 5 they meet
        assert stack_height([[(0, 0), (5, 9), (9, 0)]], closed=True) == 3  # integers, as the clipper holds them


class TestSortingRingsIsPaidFor:
    """``group_rings`` asks every outer ring about every hole: holes x outers.
    Nothing bounded that product — 2,000 small holes in 2,000 small outer rings
    took 3.8 s."""

    @staticmethod
    def frames(count: int) -> list:
        rings = []
        for k in range(count):
            x, y = (k % 100) * 100.0, (k // 100) * 100.0
            rings += [rect(x, y, x + 80.0, y + 80.0), rect(x + 20.0, y + 20.0, x + 60.0, y + 60.0, clockwise=True)]
        return rings

    def test_the_product_is_the_price_and_it_is_paid_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rings = self.frames(50)
        work = WorkBudget(budget=10**12)
        regions = group_rings(rings, work)
        assert len(regions) == 50 and all(len(holes) == 1 for _outer, holes in regions)
        assert work.spent == 50 * 50 * 120 * (4 + 2) + 700 * 50 * 4  # holes x outers, and a point per hole
        monkeypatch.setattr(polygon_module, "_point_inside", never("a hole was looked at"))
        monkeypatch.setattr(polygon_module, "_ring_holds", never("an outer ring was asked"))
        with pytest.raises(RegionTooLargeError):
            group_rings(rings, WorkBudget(budget=work.spent - 1))

    def test_two_thousand_frames_are_refused_unasked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rings = self.frames(2_000)
        monkeypatch.setattr(polygon_module, "_ring_holds", never("an outer ring was asked"))
        with pytest.raises(RegionTooLargeError):  # 2,000 x 2,000 x 720 units: twenty times the bound
            group_rings(rings)  # … also without a budget handed in: it has one of its own

    def test_rings_without_holes_cost_nothing_to_sort(self) -> None:
        work = WorkBudget()
        assert len(group_rings([rect(k * 10.0, 0.0, k * 10.0 + 5.0, 5.0) for k in range(3_000)], work)) == 3_000
        assert work.spent == 0

    def test_a_large_outer_ring_is_priced_as_it_is_asked(self) -> None:
        outer, holes = review_ladder(60)
        work = WorkBudget()
        assert group_rings([*holes, outer], work) == ((outer, holes),)
        assert work.spent == len(holes) * (12_000 + 3 * len(outer)) + 700 * sum(len(hole) for hole in holes)


class TestTheSimplicityTestHasABound:
    def test_beyond_the_bound_it_refuses_instead_of_running(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ring = _wobbly(400, random.Random(8), tangle=False)
        assert is_simple_ring(ring)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", 3 * 400 * 400 - 1)
        monkeypatch.setattr(polygon_module, "_touch", never("the pairs were tested"))
        with pytest.raises(RegionTooLargeError, match="simplicity test of a ring of 400 vertices"):
            is_simple_ring(ring)

    def test_a_scribbled_ring_pays_for_the_pairs_it_makes_the_test_look_at(
        self, monkeypatch: pytest.MonkeyPatch, fresh_verdicts: None
    ) -> None:
        """The square of the edges was the whole price of the test — right for an
        outline, whose edges are near a few others each. Of a ring scribbled across
        a plan half of ALL pairs are near, and each costs a hundred times a unit of
        the square: 3,500 such vertices took half a second, three times the bound,
        for 37 M units. Now the near pairs are paid for, all of them before one is
        tested — and a ring that cannot pay is refused on the count."""
        rng = random.Random(21)
        scribble = ccw(tuple((rng.uniform(0.0, 2000.0), rng.uniform(0.0, 2000.0)) for _ in range(600)))
        whole = WorkBudget(budget=10**12)
        near, touching = touching_pairs(scribble, whole, closed=True)
        assert touching > 20_000 and near > 60_000
        assert whole.spent == 3 * 600 * 600 + 350 * near > 20 * polygon_module._simplicity_work(600)
        assert region_cost(scribble) == 3_000 + whole.spent  # what the verdict "not simple" cost
        assert not is_buildable_region(scribble) and not is_region_too_large(scribble)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", whole.spent // 2)
        monkeypatch.setattr(polygon_module, "_touch", never("the pairs were tested"))
        with pytest.raises(RegionTooLargeError):
            is_simple_ring(scribble)
        polygon_module._examined.cache_clear()
        assert is_region_too_large(scribble)  # … through the cut as well

    def test_with_the_real_bound_that_is_about_seven_thousand_vertices(self) -> None:
        assert polygon_module._simplicity_work(7_071) <= polygon_module.MAX_REGION_WORK
        assert polygon_module._simplicity_work(7_072) > polygon_module.MAX_REGION_WORK


class TestWhatARegionCost:
    """``region_cost``: what a caller pays per region when it judges several
    against ONE budget — the same number whether the answer was remembered."""

    def test_it_is_the_work_of_the_cut(self, fresh_verdicts: None) -> None:
        outer, holes = review_ladder(20)
        assert region_cost(outer, holes) == cut_work(outer, holes) >= region_work(outer, holes)
        assert region_cost(outer, holes) == cut_work(outer, holes)  # remembered: the same again
        assert region_cost(SQUARE) == region_work(SQUARE)

    def test_a_region_that_cannot_be_built_cost_what_was_spent_finding_out(self, fresh_verdicts: None) -> None:
        bow = LOPSIDED_BOW_TIE[::-1]
        assert not is_buildable_region(bow)
        assert region_cost(bow) == 3_000 + 250 * 16  # the region and its simplicity test; no ear was cut

    def test_the_budget_says_what_was_spent(self) -> None:
        work = WorkBudget("a test", budget=100)
        work.spend(60)
        assert (work.spent, work.left) == (60, 40)
        with pytest.raises(RegionTooLargeError, match="a test is beyond"):
            work.spend(41)
        with pytest.raises(RegionTooLargeError, match="a test is beyond"):
            WorkBudget("a test").refuse()


class TestPayingForARegion:
    """``pay_for_region``: the predicate, asked out of ONE budget — the caller's.
    The bound of fix round 3 was a bound per region; an item is many regions."""

    def test_it_costs_what_the_cut_costs_fresh_or_remembered(self, fresh_verdicts: None) -> None:
        outer, holes = review_ladder(20)
        cost = cut_work(outer, holes)
        first, again = WorkBudget(), WorkBudget()
        assert pay_for_region(outer, holes, first) and pay_for_region(outer, holes, again)
        assert first.spent == again.spent == cost  # the total does not depend on what is remembered
        assert is_buildable_region(outer, holes) and region_cost(outer, holes) == cost
        assert polygon_module._examined.cache_info().entries == 1  # ONE memory, the predicate's own

    def test_a_shape_that_cannot_be_built_is_false_and_paid_for(self, fresh_verdicts: None) -> None:
        bow = LOPSIDED_BOW_TIE[::-1]
        work = WorkBudget()
        assert not pay_for_region(bow, (), work)
        assert work.spent == 3_000 + 250 * 16 and not is_buildable_region(bow)

    def test_the_least_it_can_cost_must_be_left_before_it_is_hashed_or_cut(
        self, monkeypatch: pytest.MonkeyPatch, fresh_verdicts: None
    ) -> None:
        outer, holes = review_ladder(20)
        monkeypatch.setattr(polygon_module, "_cut", never("the region was cut"))
        work = WorkBudget(budget=region_work(outer, holes) - 1)
        with pytest.raises(RegionTooLargeError):
            pay_for_region(outer, holes, work)
        assert work.spent == 0
        assert polygon_module._examined.cache_info() == (0, 0, HELD_VERTICES, 0, 0)  # not even looked up

    def test_it_is_cut_out_of_what_is_left(self, monkeypatch: pytest.MonkeyPatch, fresh_verdicts: None) -> None:
        """Not out of a bound of its own: with less left than its cut takes, the
        cut stops on the way — and "this caller could not afford it" is no fact
        about the region, so nothing is remembered."""
        teeth = comb(80)
        floor, cost = region_work(teeth), cut_work(teeth)
        payments = 0
        pay = polygon_module.WorkBudget.spend

        def counting(self, units):
            nonlocal payments
            payments += 1
            pay(self, units)

        monkeypatch.setattr(polygon_module.WorkBudget, "spend", counting)
        cut_work(teeth)
        whole, payments = payments, 0
        work = WorkBudget(budget=(floor + cost) // 2)
        with pytest.raises(RegionTooLargeError):
            pay_for_region(teeth, (), work)
        assert 0 < payments < whole  # it stopped on the way
        assert 0 < work.spent - work.budget < 50_000  # … at the first payment beyond what was there
        assert polygon_module._examined.cache_info().entries == 0
        assert is_buildable_region(teeth) and not is_region_too_large(teeth)  # by itself it is cut
        enough = WorkBudget(budget=cost)
        assert pay_for_region(teeth, (), enough) and enough.left == 0

    def test_a_region_beyond_the_bound_by_itself_is_refused_and_that_is_remembered(
        self, monkeypatch: pytest.MonkeyPatch, fresh_verdicts: None
    ) -> None:
        teeth = comb(80)
        monkeypatch.setattr(polygon_module, "MAX_REGION_WORK", (region_work(teeth) + cut_work(teeth)) // 2)
        cuts = 0
        real = polygon_module._cut

        def counting(outer, holes, work):
            nonlocal cuts
            cuts += 1
            return real(outer, holes, work)

        monkeypatch.setattr(polygon_module, "_cut", counting)
        for _ in range(2):
            with pytest.raises(RegionTooLargeError):
                pay_for_region(teeth, (), WorkBudget(budget=10**12))  # however much the caller has
        assert cuts == 1 and is_region_too_large(teeth)

    def test_the_sum_is_what_is_bounded(self, fresh_verdicts: None) -> None:
        squares = [rect(k * 10.0, 0.0, k * 10.0 + 5.0, 5.0) for k in range(10)]
        each = region_work(squares[0])
        work = WorkBudget(budget=5 * each + each // 2)
        paid = 0
        with pytest.raises(RegionTooLargeError):
            for square in squares:
                assert pay_for_region(square, (), work)
                paid += 1
        assert paid == 5 and work.spent == 5 * each  # ten squares that each fit; five and a half paid for


# ── fix round 4 ──────────────────────────────────────────────────────────────


class TestWhatASnapshotAsksForIsNeverDropped:
    """Review of fix round 3, P1-A. A memory that drops the least recently asked
    answer when it is full recomputes the WHOLE plan on every tick once the plan
    is larger than the memory: a snapshot asks in the same order each time, so
    every answer is the oldest when its turn comes. What a snapshot asks for is
    LIVE now — for that snapshot and the next — and only the rest is bounded."""

    @staticmethod
    def memory(cap: int = 1_000):
        calls: list[int] = []

        @ring_keyed(cap)
        def length(ring) -> int:
            calls.append(len(ring))
            return len(ring)

        return length, calls

    @staticmethod
    def rings(count: int, size: int = 300):
        return [tuple((float(k), float(j)) for k in range(size)) for j in range(count)]

    def test_a_plan_above_the_cap_is_answered_from_memory_tick_after_tick(self) -> None:
        length, calls = self.memory()
        plan = self.rings(10)  # 3,080 vertices: three times the cap
        for tick in range(4):
            with polygon_module.snapshot_generation():
                assert [length(ring) for ring in plan] == [300] * 10
            assert len(calls) == 10, tick  # computed in the first tick, and never again
        assert length.cache_info().vertices == 10 * 308 and length.cache_info().entries == 10

    def test_what_the_plan_no_longer_asks_for_is_stale_two_snapshots_later(self) -> None:
        length, calls = self.memory()
        plan = self.rings(10)
        with polygon_module.snapshot_generation():
            for ring in plan:
                length(ring)
        with polygon_module.snapshot_generation():  # eight items are deleted: two are asked
            length(plan[0]), length(plan[1])
        assert length.cache_info().entries == 10  # asked by the snapshot before: still live
        with polygon_module.snapshot_generation():
            length(plan[0]), length(plan[1])
        info = length.cache_info()  # the eight are stale: 2,464 vertices of them, 750 are kept
        assert info.entries == 4 and info.vertices - 2 * 308 <= 750
        assert len(calls) == 10

    def test_a_memory_the_snapshot_did_not_ask_is_settled_too(self) -> None:
        length, _calls = self.memory()
        with polygon_module.snapshot_generation():
            for ring in self.rings(10):
                length(ring)
        with polygon_module.snapshot_generation():
            pass
        assert length.cache_info().entries == 10
        with polygon_module.snapshot_generation():
            pass  # nothing asks: the plan's last outline is gone — and the memory is settled all the same
        assert length.cache_info().vertices <= 750

    def test_outside_a_snapshot_nothing_is_live(self) -> None:
        """A builder's own rings, a script's loop: asked for outside any snapshot,
        an answer is stale from the start — plain least-recently-asked, by vertices."""
        length, calls = self.memory()
        for ring in self.rings(50):
            length(ring)
        assert length.cache_info().vertices <= 1_000 and len(calls) == 50
        plan = self.rings(3)
        with polygon_module.snapshot_generation():
            for ring in plan:
                length(ring)
        for ring in self.rings(50, size=200):  # … and it never pushes out what a snapshot asked for
            length(ring)
        calls.clear()
        assert [length(ring) for ring in plan] == [300] * 3 and calls == []
        length(plan[0])  # asked outside a snapshot, a live answer stays live — and gets no younger
        with polygon_module.snapshot_generation():
            pass
        with polygon_module.snapshot_generation():
            pass
        assert length.cache_info().vertices <= 1_000  # the three are stale now, like the rest

    def test_a_snapshot_inside_a_snapshot_is_still_a_snapshot(self) -> None:
        assert not polygon_module._snapshotting
        with polygon_module.snapshot_generation() as outer:
            with polygon_module.snapshot_generation() as inner:
                assert inner == outer + 1 and polygon_module._snapshotting
            assert polygon_module._snapshotting
        assert not polygon_module._snapshotting

    def test_clearing_forgets_what_was_live(self) -> None:
        length, calls = self.memory()
        with polygon_module.snapshot_generation():
            for ring in self.rings(10):
                length(ring)
        length.cache_clear()
        assert length.cache_info() == (0, 0, 1_000, 0, 0)
        for ring in self.rings(50):
            length(ring)
        assert length.cache_info().vertices <= 1_000  # nothing of the old plan is counted as live


class TestConvexByArithmetic:
    """Review of fix round 3, P2-1. A circle's, an ellipse's, a rectangle's ring is
    convex by construction; asking the cut predicate of it triangulated a 24-gon
    per new radius. ``is_convex_ring`` is arithmetic on its corners."""

    @pytest.mark.parametrize(
        ("label", "ring", "convex"),
        [("a square", SQUARE, True),
         ("a square, clockwise", SQUARE[::-1], False),
         ("an L (a corner that turns right)", L_SHAPE, False),
         ("a bow-tie", BOW_TIE, False),
         ("a point on an edge (a corner that does not turn)",
          ((0.0, 0.0), (50.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)), False),
         ("a vertex placed twice", ((0.0, 0.0), (100.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)), False),
         ("a triangle", ((0.0, 0.0), (10.0, 0.0), (0.0, 10.0)), True),
         ("a bed of 120 m by 5 mm (a sliver for its reach: the cut decides)",
          ((-6000.0, -0.25), (6000.0, -0.25), (6000.0, 0.25), (-6000.0, 0.25)), False),
         ("a bed of 20 cm by 5 mm (small: floats cannot blur it)",
          ((-10.0, -0.25), (10.0, -0.25), (10.0, 0.25), (-10.0, 0.25)), True),
         ("a spike that turns back on itself", ((0.0, 0.0), (10.0, 0.0), (5.0, 0.0)), False),
         ("two points", ((0.0, 0.0), (10.0, 0.0)), False), ("nothing", (), False)],
    )
    def test_what_is_convex(self, label: str, ring, convex: bool) -> None:
        assert polygon_module.is_convex_ring(ring) is convex, label
        if convex:
            assert is_buildable_region(ring)

    def test_a_sliver_the_cut_cannot_prove_is_not_called_convex(self) -> None:
        """Found by the sweep below: 120 m by 2 µm, turned. Every corner turns left
        — and the cut's proof fails on it, its two sums of areas a few 1e-9 apart.
        Called convex, it would be a record the default builder cannot build."""
        ring = ((4984.7008522, 3327.8602089), (4984.7007352, 3327.8603842),
                (-4984.7008522, -3327.8602089), (-4984.7007352, -3327.8603842))
        assert not is_buildable_region(ring)
        assert not polygon_module.is_convex_ring(ring)

    def test_convex_by_arithmetic_implies_buildable_by_the_cut(self) -> None:
        """The promise "every region of every record satisfies ``is_buildable_region``"
        must survive not asking it: over 2,000 circles, ellipses and rectangles from a
        tenth of a micrometre to ten kilometres, turned, on the record grid."""
        from open_garden_planner.core.scene3d import quantize_cm

        rng = random.Random(2026)
        convex = degenerate_but_cut = 0
        for k in range(2_000):
            a, b = (10.0 ** rng.uniform(-7.0, 6.0) for _ in range(2))
            if k % 3 == 0:
                a = b  # a circle
            turn = rng.uniform(0.0, 2.0 * math.pi) if k % 2 else 0.0
            corners = ([(a * math.cos(2.0 * math.pi * j / 24), b * math.sin(2.0 * math.pi * j / 24))
                        for j in range(24)] if k % 3 != 2 else [(-a, -b), (a, -b), (a, b), (-a, b)])
            ring = tuple((quantize_cm(x * math.cos(turn) - y * math.sin(turn)),
                          quantize_cm(x * math.sin(turn) + y * math.cos(turn))) for x, y in corners)
            if polygon_module.is_convex_ring(ring):
                convex += 1
                assert is_buildable_region(ring), (k, a, b, turn)
            elif signed_area(ring) > 0.0 and is_buildable_region(ring):
                degenerate_but_cut += 1  # squeezed to a few grid steps: the cut still decides, as before
        assert convex > 1_200 and degenerate_but_cut > 0

    def test_it_reads_plain_pairs_of_any_kind(self) -> None:
        assert polygon_module.is_convex_ring([[0, 0], [4, 0], [4, 3], [0, 3]])


class TestTheStackWithoutLevelSegments:
    """Review of fix round 3, P2-3: the clipper's sweep does not CARRY a level
    edge, it walks along it. For a path that is inflated the level segments are
    left out of the stack (``flat=False``)."""

    def test_a_level_line_has_no_stack(self) -> None:
        line = [(200.0 * k, 0.0) for k in range(1_000)]
        assert stack_height([line], closed=False, reach=7.0) == 999  # counted: every segment
        assert stack_height([line], closed=False, reach=7.0, flat=False) == 0
        assert stack_height([[(y, x) for x, y in line]], closed=False, reach=7.0, flat=False) == 2

    def test_only_the_level_segments_are_left_out(self) -> None:
        stairs = [(50.0 * (k // 2 + k % 2), 0.001 * (k // 2)) for k in range(1_000)]  # a level run, a rise, …
        assert stack_height([stairs], closed=False, reach=7.0) == 999
        assert stack_height([stairs], closed=False, reach=7.0, flat=False) == 499  # the rises
        teeth = [(k * 30.0, 1000.0 + k if k % 2 else -float(k)) for k in range(400)]
        assert stack_height([teeth], closed=False, flat=False) == stack_height([teeth], closed=False) == 399
        assert stack_height([SQUARE], closed=True, flat=False) == 2  # its two upright sides
        assert stack_height([[(0.0, 0.0), (5.0, 0.0)]], closed=False, flat=False) == 0


class TestWhatIsNoNumberIsNotConvex:
    """Review of fix round 4, P2-1: every ``<=`` is False for NaN, so a ring with
    a coordinate that is no number turned "left" at every corner and was called
    convex — by a function whose promise is "implies buildable". (The snapshot
    asks for finiteness first; the promise is the function's own.)"""

    SQUARE = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"])
    @pytest.mark.parametrize("vertex", range(4))
    @pytest.mark.parametrize("axis", [0, 1], ids=["x", "y"])
    def test_a_coordinate_that_is_no_number(self, bad: float, vertex: int, axis: int) -> None:
        from open_garden_planner.core.scene3d.polygon import is_convex_ring

        assert is_convex_ring(self.SQUARE)
        ring = [list(point) for point in self.SQUARE]
        ring[vertex][axis] = bad
        assert is_convex_ring([tuple(point) for point in ring]) is False

    def test_all_of_them(self) -> None:
        from open_garden_planner.core.scene3d.polygon import is_convex_ring

        nan = float("nan")
        assert is_convex_ring(((nan, nan),) * 4) is False
        assert is_convex_ring(((nan, 0.0), (nan, 1.0), (nan, 2.0))) is False


class TestForgettingEveryRing:
    """``clear_ring_memories``: every answer of every ``ring_keyed`` function,
    live and stale — what ``ui.view3d.snapshot.clear_outline_cache`` is made of."""

    def test_live_and_stale_answers_are_gone(self) -> None:
        from open_garden_planner.core.scene3d import polygon

        calls: list[int] = []

        @polygon.ring_keyed(max_vertices=100)
        def length(ring: tuple[tuple[float, float], ...]) -> int:
            calls.append(len(ring))
            return len(ring)

        live = tuple((float(k), 0.0) for k in range(300))  # three times the cap: only a snapshot keeps it
        stale = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))
        length(stale)
        with polygon.snapshot_generation():
            length(live)
        assert length.cache_info().entries == 2 and length.cache_info().vertices > 300
        polygon.clear_ring_memories()
        assert length.cache_info().entries == 0 == length.cache_info().vertices
        assert polygon.ring_area.cache_info().entries == 0 == polygon._examined.cache_info().entries
        calls.clear()
        with polygon.snapshot_generation():
            assert length(live) == 300
        assert calls == [300]  # asked again: it was forgotten, although it was live
        polygon.clear_ring_memories()
        polygon.clear_ring_memories()  # nothing held: nothing happens
