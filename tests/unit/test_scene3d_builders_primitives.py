"""Primitives of the built world (Phase 17 L1.6, #385 — part of gate G1). Qt-free.

Each primitive returns a mesh ``Mesh.validate()`` accepts: finite, unit normals,
and every flat face stores its WINDING normal (dot ≥ 0.99). On top of that this
file pins what ``validate`` cannot know — that the winding faces OUTWARD (a mesh
turned inside out validates just as well), exact tops, triangle counts, and the
plan geometry of mitres, offsets and splits.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.scene3d import (
    EMPTY_PARAMS,
    Material,
    Mesh,
    MeshPart,
    Record,
    Transform,
    normal_vs_winding,
    prism_mesh,
)
from open_garden_planner.core.scene3d.builders.common import (
    BuiltBuilder,
    fit_parts,
    fit_scale,
    nominal_height_cm,
    top_cm,
)
from open_garden_planner.core.scene3d.builders.primitives import (
    BEVEL_BEYOND,
    MITER_LIMIT,
    bevelled_boxes,
    boxes,
    ccw_ring,
    clean_path,
    flat_mesh,
    lathe,
    offset_ring,
    plank,
    polygon_cap,
    polygon_triangles,
    prism,
    signed_area,
    split_triangles_by_line,
    sweep,
    tubes,
)
from open_garden_planner.core.shadow_geometry import circle_footprint

#: What the L0 spike measured, frozen when L1.10 deleted it (its provenance field says how).
SPIKE = json.loads((Path(__file__).resolve().parents[1] / "data" / "l0_spike_reference.json")
                   .read_text(encoding="utf-8"))

SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
L_SHAPE = [(0.0, 0.0), (300.0, 0.0), (300.0, 120.0), (120.0, 120.0), (120.0, 400.0), (0.0, 400.0)]
RED = (1.0, 0.0, 0.0, 1.0)


def triangles_of(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    """(triangle corner positions (t, 3, 3), winding normals (t, 3)) of a mesh."""
    corners = mesh.positions.astype(np.float64)[mesh.indices]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    return corners, cross / np.linalg.norm(cross, axis=1, keepdims=True)


def assert_faces_look_away_from(mesh: Mesh, centre: tuple[float, float, float], *,
                                skip_below: float | None = None) -> None:
    """Every face of a CONVEX solid looks away from a point inside it."""
    corners, winding = triangles_of(mesh)
    outward = corners.mean(axis=1) - np.asarray(centre)
    dots = (winding * outward).sum(axis=1)
    if skip_below is not None:
        dots = dots[corners[:, :, 2].max(axis=1) > skip_below]
    assert float(dots.min()) > 0.0


def flat_dots(mesh: Mesh) -> np.ndarray:
    dots, flat = normal_vs_winding(mesh)
    return dots[flat]


class TestFlatMesh:
    def test_a_triangle_stores_its_winding_normal(self) -> None:
        mesh = flat_mesh([[(0, 0, 0), (1, 0, 0), (0, 1, 0)]], RED)
        mesh.validate()
        assert mesh.triangle_count == 1 and mesh.vertex_count == 3
        assert np.allclose(mesh.normals, [[0.0, 0.0, 1.0]] * 3)
        assert np.allclose(mesh.colors, [RED] * 3)

    def test_an_outward_hint_flips_a_face_wound_the_other_way(self) -> None:
        wrong = [[(0, 0, 0), (0, 1, 0), (1, 0, 0)]]  # wound to look down
        assert np.allclose(flat_mesh(wrong).normals[0], [0.0, 0.0, -1.0])
        fixed = flat_mesh(wrong, outward=(0.0, 0.0, 1.0))
        fixed.validate()
        assert np.allclose(fixed.normals, [[0.0, 0.0, 1.0]] * 3)
        assert float(flat_dots(fixed).min()) > 0.999  # … and the stored normal followed

    def test_degenerate_triangles_are_dropped(self) -> None:
        mesh = flat_mesh([[(0, 0, 0), (1, 0, 0), (2, 0, 0)], [(0, 0, 0), (1, 0, 0), (0, 1, 0)]])
        assert mesh.triangle_count == 1
        assert flat_mesh([[(0, 0, 0), (0, 0, 0), (0, 0, 0)]]).triangle_count == 0
        assert flat_mesh(np.zeros((0, 3, 3))).triangle_count == 0

    def test_per_triangle_colours_and_uvs(self) -> None:
        soup = [[(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 0, 5), (1, 0, 5), (0, 1, 5)]]
        mesh = flat_mesh(soup, [RED, (0.0, 1.0, 0.0, 1.0)], uvs=[(0.5, 0.25), (1.0, 0.0)])
        assert np.allclose(mesh.colors[:3], [RED] * 3) and np.allclose(mesh.colors[3:, 1], 1.0)
        assert np.allclose(mesh.uvs[:3], [(0.5, 0.25)] * 3) and np.allclose(mesh.uvs[3:], [(1.0, 0.0)] * 3)


class TestBoxes:
    @pytest.mark.parametrize("angle", [0.0, 30.0, 90.0, 213.5])
    def test_one_box(self, angle: float) -> None:
        mesh = boxes([(10.0, -5.0)], (40.0, 20.0), 3.0, 87.3, angle, RED)
        mesh.validate()
        assert mesh.triangle_count == 10
        low, high = mesh.bounds()
        assert float(low[2]) == 3.0 and float(high[2]) == float(np.float32(87.3))  # exact top
        assert_faces_look_away_from(mesh, (10.0, -5.0, 45.0))
        assert float(flat_dots(mesh).min()) > 0.999
        corners = mesh.positions[:, :2].astype(np.float64) - np.array([10.0, -5.0])
        assert np.allclose(np.hypot(corners[:, 0], corners[:, 1]).max(), math.hypot(20.0, 10.0),
                           atol=1e-4)

    def test_a_turned_box_is_turned_counter_clockwise(self) -> None:
        mesh = boxes([(0.0, 0.0)], (100.0, 10.0), 0.0, 10.0, 90.0)
        low, high = mesh.bounds()
        assert float(high[1] - low[1]) == pytest.approx(100.0, abs=1e-4)  # its long side runs north
        assert float(high[0] - low[0]) == pytest.approx(10.0, abs=1e-4)

    def test_many_boxes_in_one_call(self) -> None:
        centres = np.stack([np.arange(50) * 12.0, np.zeros(50)], axis=1)
        tops = 100.0 + np.arange(50) * 0.5
        mesh = boxes(centres, (7.44, 2.2), 2.0, tops, 0.0)
        mesh.validate()
        assert mesh.triangle_count == 500
        assert float(mesh.bounds()[1][2]) == float(np.float32(tops.max()))
        with_bottoms = boxes(centres, (7.44, 2.2), 2.0, tops, 0.0, bottom=True)
        assert with_bottoms.triangle_count == 600

    def test_no_boxes_is_an_empty_mesh(self) -> None:
        assert boxes(np.zeros((0, 2)), (1.0, 1.0), 0.0, 1.0).vertex_count == 0


class TestBevelledBoxes:
    @pytest.mark.parametrize("angle", [0.0, 37.0])
    def test_shape(self, angle: float) -> None:
        mesh = bevelled_boxes([(0.0, 0.0)], (9.0, 9.0), 0.0, 120.0, 1.0, angle)
        mesh.validate()
        assert mesh.triangle_count == 38
        low, high = mesh.bounds()
        assert float(low[2]) == 0.0 and float(high[2]) == 120.0
        assert_faces_look_away_from(mesh, (0.0, 0.0, 60.0))
        assert float(flat_dots(mesh).min()) > 0.999  # every bevel face is planar
        # the top face is the outline drawn in by the bevel, the foot is the full outline
        top = mesh.positions[mesh.positions[:, 2] == 120.0][:, :2].astype(np.float64)
        foot = mesh.positions[mesh.positions[:, 2] == 0.0][:, :2].astype(np.float64)
        assert np.hypot(top[:, 0], top[:, 1]).max() < np.hypot(foot[:, 0], foot[:, 1]).max() - 0.9

    def test_the_bevel_is_limited_by_the_box(self) -> None:
        mesh = bevelled_boxes([(0.0, 0.0)], (2.0, 2.0), 0.0, 1.0, 50.0)
        mesh.validate()
        assert float(mesh.bounds()[1][2]) == 1.0


class TestPolygons:
    def test_signed_area_and_ccw(self) -> None:
        assert signed_area(SQUARE) == 10000.0 and signed_area(SQUARE[::-1]) == -10000.0
        assert signed_area(ccw_ring(SQUARE[::-1])) == 10000.0
        closed_twice = [*SQUARE, SQUARE[0]]
        assert len(ccw_ring(closed_twice)) == 4

    def test_clean_path_drops_repeated_points(self) -> None:
        assert len(clean_path([(0, 0), (0, 0), (5, 0), (5, 0.0001), (9, 0)])) == 3

    @pytest.mark.parametrize("distance", [30.0, -4.0])
    def test_offset_moves_every_edge_by_the_distance(self, distance: float) -> None:
        for ring in (SQUARE, L_SHAPE):
            grown = offset_ring(ring, distance)
            source = ccw_ring(ring)
            assert len(grown) == len(source)
            for index in range(len(source)):  # each edge keeps its direction, moves `distance`
                a, b = source[index], source[(index + 1) % len(source)]
                ga, gb = grown[index], grown[(index + 1) % len(source)]
                edge = (b - a) / np.linalg.norm(b - a)
                outward = np.array([edge[1], -edge[0]])
                assert float((ga - a) @ outward) == pytest.approx(distance, abs=1e-9)
                assert float((gb - b) @ outward) == pytest.approx(distance, abs=1e-9)
                moved = gb - ga
                assert abs(float(moved[0] * edge[1] - moved[1] * edge[0])) < 1e-9

    def test_offset_area_of_a_square(self) -> None:
        assert signed_area(offset_ring(SQUARE, 30.0)) == pytest.approx(160.0 ** 2)
        assert signed_area(offset_ring(SQUARE, -5.0)) == pytest.approx(90.0 ** 2)

    def test_a_corner_keeps_its_mitre_up_to_two_offsets(self) -> None:
        """BEVEL_BEYOND = 2: an interior angle of 60° (a mitre of exactly 2 offsets) is
        still mitred, whatever the last bit of the coordinates says."""
        assert BEVEL_BEYOND == 2.0 and MITER_LIMIT == 4.0
        side = 400.0
        equilateral = [(0.0, 0.0), (side, 0.0), (side / 2.0, side * math.sqrt(3.0) / 2.0)]
        for turn in (0.0, 17.0, 90.0, 213.5):
            c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
            ring = [(x * c - y * s, x * s + y * c) for x, y in equilateral]
            grown = offset_ring(ring, 30.0)
            assert len(grown) == 3
            assert np.allclose(np.linalg.norm(grown - ccw_ring(ring), axis=1), 60.0)

    @pytest.mark.parametrize(("apex_deg", "mitre"), [(59.0, 2.031), (30.0, 3.864), (20.0, 5.759),
                                                     (5.0, 22.926)])
    def test_a_sharper_corner_is_bevelled_when_the_edges_run_apart(
        self, apex_deg: float, mitre: float
    ) -> None:
        """Review round 1, P2-10. Outward at an acute corner the mitre is
        1 / sin(angle / 2) offsets long — a spike. It becomes two points, the ends of
        the two moved edges, each exactly one offset from the corner."""
        assert 1.0 / math.sin(math.radians(apex_deg) / 2.0) == pytest.approx(mitre, abs=1e-3)
        half_base = 200.0
        apex = (0.0, half_base / math.tan(math.radians(apex_deg) / 2.0))
        ring = [(-half_base, 0.0), (half_base, 0.0), apex]  # the other two corners are > 60°
        distance = 30.0
        grown = offset_ring(ring, distance)
        assert len(grown) == 4  # one corner became two points
        source = ccw_ring(ring)
        # every point within BEVEL_BEYOND offsets of the corner it came from …
        nearest = np.linalg.norm(grown[:, None, :] - source[None, :, :], axis=2).min(axis=1)
        assert float(nearest.max()) <= BEVEL_BEYOND * distance + 1e-9
        # … the two at the apex exactly ONE offset from it (round 0: `mitre` offsets, cut at 4)
        at_apex = grown[np.argsort(np.linalg.norm(grown - np.asarray(apex), axis=1))[:2]]
        assert np.allclose(np.linalg.norm(at_apex - np.asarray(apex), axis=1), distance)
        # every edge of the ring is still moved by exactly the distance, parallel to itself
        for index in range(3):
            a, b = source[index], source[(index + 1) % 3]
            edge = (b - a) / np.linalg.norm(b - a)
            outward = np.array([edge[1], -edge[0]])
            on_line = np.isclose((grown - a) @ outward, distance, atol=1e-9)
            assert int(on_line.sum()) == 2  # its two ends
        assert signed_area(grown) > signed_area(ring)  # still a simple, larger polygon

    def test_inward_at_an_acute_corner_the_mitre_is_the_true_intersection_and_is_kept(self) -> None:
        """A soil inset or a hedge core at a 30° corner: the two moved edges MEET there,
        3.9 offsets in from the corner. Cutting that short would let the inset poke into
        the frame it is meant to clear."""
        apex = (0.0, 200.0 / math.tan(math.radians(15.0)))
        ring = [(-200.0, 0.0), (200.0, 0.0), apex]
        inner = offset_ring(ring, -5.0)
        assert len(inner) == 3
        assert float(np.linalg.norm(inner[2] - np.asarray(apex))) == pytest.approx(
            5.0 / math.sin(math.radians(15.0)), abs=1e-9)
        source = ccw_ring(ring)
        for index in range(3):  # every edge exactly 5 cm in
            a, b = source[index], source[(index + 1) % 3]
            edge = (b - a) / np.linalg.norm(b - a)
            outward = np.array([edge[1], -edge[0]])
            assert float((inner[index] - a) @ outward) == pytest.approx(-5.0, abs=1e-9)
            assert float((inner[(index + 1) % 3] - a) @ outward) == pytest.approx(-5.0, abs=1e-9)

    def test_a_reflex_corner_is_bevelled_for_an_inward_offset(self) -> None:
        """The mirror case: at a deep notch the moved edges run apart when moved INWARD."""
        notch = [(0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (330.0, 300.0), (200.0, 20.0),
                 (70.0, 300.0), (0.0, 300.0)]  # a 50° notch cut into the top
        assert signed_area(notch) > 0.0
        inner = offset_ring(notch, -10.0)
        assert len(inner) == len(notch) + 1  # the notch's tip became two points
        tip = np.asarray((200.0, 20.0))
        at_tip = inner[np.argsort(np.linalg.norm(inner - tip, axis=1))[:2]]
        assert np.allclose(np.linalg.norm(at_tip - tip, axis=1), 10.0)
        # outward the same two edges run together: their true intersection, one point
        outer = offset_ring(notch, 10.0)
        assert len(outer) == len(notch)
        assert float(np.linalg.norm(outer - tip, axis=1).min()) == pytest.approx(
            10.0 / math.sin(math.atan2(130.0, 280.0)), abs=1e-9)

    def test_triangles_cover_a_concave_polygon_exactly(self) -> None:
        plan = polygon_triangles(L_SHAPE)
        areas = [signed_area(t) for t in plan]
        assert min(areas) > 0.0  # all counter-clockwise
        assert sum(areas) == pytest.approx(signed_area(L_SHAPE))

    @pytest.mark.parametrize("up", [True, False])
    def test_cap(self, up: bool) -> None:
        mesh = polygon_cap(L_SHAPE[::-1], 38.0, RED, up=up)  # clockwise input
        mesh.validate()
        assert np.allclose(mesh.positions[:, 2], 38.0)
        assert np.allclose(mesh.normals[:, 2], 1.0 if up else -1.0)

    def test_prism(self) -> None:
        mesh = prism(L_SHAPE, 0.0, 147.0, RED)
        mesh.validate()
        assert float(mesh.bounds()[1][2]) == 147.0 and float(mesh.bounds()[0][2]) == 0.0
        corners, winding = triangles_of(mesh)
        assert winding[:, 2].min() > -1e-9  # no face looks down: walls and a lid
        assert prism(L_SHAPE, 0.0, 147.0, top=False).triangle_count == 12
        assert prism(SQUARE, 5.0, 5.0).vertex_count == 0

    def test_split_by_line(self) -> None:
        plan = polygon_triangles(L_SHAPE)
        left, right = split_triangles_by_line(plan, (0.0, 60.0), (0.0, 1.0))  # the line y = 60
        assert min(signed_area(t) for t in left) > 0.0 and min(signed_area(t) for t in right) > 0.0
        assert left[:, :, 1].min() >= 60.0 - 1e-9 and right[:, :, 1].max() <= 60.0 + 1e-9
        total = sum(signed_area(t) for t in left) + sum(signed_area(t) for t in right)
        assert total == pytest.approx(signed_area(L_SHAPE))
        assert sum(signed_area(t) for t in right) == pytest.approx(300.0 * 60.0)
        nothing, everything = split_triangles_by_line(plan, (0.0, 500.0), (0.0, 1.0))
        assert len(nothing) == 0 and len(everything) == len(plan)


BOX_PROFILE = [(-5.0, 0.0), (5.0, 0.0), (5.0, 40.0), (-5.0, 40.0)]  # counter-clockwise in (lateral, z)


def _distance_to_segment(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    step = b - a
    t = np.clip(((points - a) @ step) / float(step @ step), 0.0, 1.0)
    return np.linalg.norm(points - (a + t[:, None] * step), axis=1)


class TestSweep:
    def test_a_straight_run_is_a_box(self) -> None:
        mesh = sweep(BOX_PROFILE, [(0.0, 0.0), (200.0, 0.0)], RED)
        mesh.validate()
        assert mesh.triangle_count == 4 * 2 + 2 * 2  # four walls, two ends
        low, high = mesh.bounds()
        assert (float(low[0]), float(high[0])) == (0.0, 200.0)
        assert (float(low[1]), float(high[1])) == (-5.0, 5.0)
        assert (float(low[2]), float(high[2])) == (0.0, 40.0)
        assert_faces_look_away_from(mesh, (100.0, 0.0, 20.0))

    def test_lateral_is_to_the_left_of_travel(self) -> None:
        lopsided = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]  # only to the left
        east = sweep(lopsided, [(0.0, 0.0), (100.0, 0.0)])
        assert float(east.bounds()[0][1]) == 0.0 and float(east.bounds()[1][1]) == 10.0  # left of east = north
        north = sweep(lopsided, [(0.0, 0.0), (0.0, 100.0)])
        assert float(north.bounds()[0][0]) == -10.0 and float(north.bounds()[1][0]) == 0.0  # left of north = west

    def test_a_corner_is_mitred_and_every_wall_stays_planar(self) -> None:
        path = [(0.0, 0.0), (200.0, 0.0), (200.0, 150.0), (60.0, 220.0)]
        mesh = sweep(BOX_PROFILE, path)
        mesh.validate()
        assert float(flat_dots(mesh).min()) > 0.9999
        # plan area of a mitred strip = centre-line length × width, whatever the corners do
        length = 200.0 + 150.0 + math.hypot(140.0, 70.0)
        top = triangles_of(mesh)[0]
        lids = top[np.isclose(top[:, :, 2], 40.0).all(axis=1)]
        area = sum(signed_area(t[:, :2]) for t in lids)
        assert area == pytest.approx(length * 10.0, rel=1e-6)  # float32 vertices

    def test_a_closed_path_has_no_ends_and_encloses_nothing(self) -> None:
        loop = sweep(BOX_PROFILE, SQUARE, closed=True)
        loop.validate()
        assert loop.triangle_count == 4 * 4 * 2  # four walls per side, no caps
        corners = triangles_of(loop)[0]
        lids = corners[np.isclose(corners[:, :, 2], 40.0).all(axis=1)]
        assert sum(signed_area(t[:, :2]) for t in lids) == pytest.approx(400.0 * 10.0)
        # the repeated first point of a "closed" polyline is the same loop
        again = sweep(BOX_PROFILE, [*SQUARE, SQUARE[0]], closed=True)
        assert again == loop

    def test_edges_can_be_left_out_and_coloured(self) -> None:
        green = (0.0, 1.0, 0.0, 1.0)
        mesh = sweep(BOX_PROFILE, [(0.0, 0.0), (100.0, 0.0)], [RED, green, RED, green],
                     edges=[False, True, True, True], caps=False)
        assert mesh.triangle_count == 3 * 2
        assert float(triangles_of(mesh)[0][:, :, 2].max(axis=1).min()) > 0.0  # the ground face is gone
        corners, winding = triangles_of(mesh)
        lid = np.isclose(winding[:, 2], 1.0)
        assert np.allclose(mesh.colors[mesh.indices[lid].reshape(-1)], RED)

    def test_an_open_profile_is_a_sheet(self) -> None:
        sheet = sweep([(5.0, 0.0), (5.0, 40.0), (-5.0, 40.0)], [(0.0, 0.0), (100.0, 0.0)],
                      profile_closed=False)
        sheet.validate()
        assert sheet.triangle_count == 4  # two edges, no caps

    def test_degenerate_input_is_empty(self) -> None:
        assert sweep(BOX_PROFILE, [(0.0, 0.0)]).vertex_count == 0
        assert sweep(BOX_PROFILE, [(0.0, 0.0), (0.0, 0.0)]).vertex_count == 0
        assert sweep([(0.0, 0.0)], [(0.0, 0.0), (9.0, 0.0)]).vertex_count == 0
        assert sweep(BOX_PROFILE, [(0.0, 0.0), (9.0, 0.0)], closed=True).vertex_count == 0

    def test_a_hairpin_does_not_spike(self) -> None:
        """Review round 1, P2-10: round 0 cut a hairpin's mitre at 4 offsets — a 20 cm
        spike past the bend on this 10 cm section. Its outside is bevelled: nothing is
        further than one offset from the line."""
        path = [(0.0, 0.0), (100.0, 0.0), (0.0, 1.0)]
        mesh = sweep(BOX_PROFILE, path)
        mesh.validate()
        low, high = mesh.bounds()
        assert float(high[0]) <= 100.0 + 5.0 + 1e-3  # round 0: 120.0
        plan = mesh.positions.astype(np.float64)[:, :2]
        away = np.minimum(_distance_to_segment(plan, np.asarray(path[0]), np.asarray(path[1])),
                          _distance_to_segment(plan, np.asarray(path[1]), np.asarray(path[2])))
        assert float(away.max()) <= 5.0 + 1e-3
        assert float(flat_dots(mesh).min()) > 0.9999
        assert (float(low[2]), float(high[2])) == (0.0, 40.0)

    @pytest.mark.parametrize("turn_deg", [121.0, 150.0, 174.0, 179.9])
    @pytest.mark.parametrize("left", [True, False], ids=["left-turn", "right-turn"])
    def test_a_sharp_bend_is_bevelled_on_its_outside(self, turn_deg: float, left: bool) -> None:
        sign = 1.0 if left else -1.0
        heading = math.radians(turn_deg) * sign
        bend = np.asarray((300.0, 0.0))
        path = [(0.0, 0.0), tuple(bend),
                (300.0 + 300.0 * math.cos(heading), 300.0 * math.sin(heading))]
        mesh = sweep(BOX_PROFILE, path)
        mesh.validate()
        corners, winding = triangles_of(mesh)
        plan = mesh.positions.astype(np.float64)[:, :2]
        # THE bound: no vertex further than its lateral offset from the line. The outside
        # ends square on each segment; the inside is the two inner edges' intersection.
        # (Round 0: the outside mitre, 5 / cos(turn / 2) = 10.2 … 20 cm from the bend.)
        away = np.minimum(_distance_to_segment(plan, np.asarray(path[0]), bend),
                          _distance_to_segment(plan, bend, np.asarray(path[2])))
        assert float(away.max()) <= 5.0 + 1e-3
        # the bevel is a real face: vertical, looking out along the bend's bisector, with
        # every corner one offset from the bend
        normal_in = np.array([0.0, 1.0]) * sign          # the first segment's inside
        normal_out = np.array([-math.sin(heading), math.cos(heading)]) * sign
        bisector = -(normal_in + normal_out)
        bisector /= np.linalg.norm(bisector)
        bevel = (np.abs(winding[:, 2]) < 1e-6) & (winding[:, :2] @ bisector > 0.999)
        assert int(bevel.sum()) == 2  # the section's one outer side: a quad
        assert np.allclose(np.linalg.norm(corners[bevel][:, :, :2] - bend, axis=2), 5.0, atol=1e-3)
        assert float(flat_dots(mesh).min()) > 0.9999  # every face, the bevel's too, is planar
        # the lid has no hole at the bend: some top triangle lies over the bend itself
        lids = corners[np.isclose(corners[:, :, 2], 40.0).all(axis=1)][:, :, :2]
        assert all(signed_area(t) > 0.0 for t in lids)  # all look up

        def over(point: np.ndarray) -> bool:
            a, b, c = lids[:, 0], lids[:, 1], lids[:, 2]
            d1 = (b[:, 0] - a[:, 0]) * (point[1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (point[0] - a[:, 0])
            d2 = (c[:, 0] - b[:, 0]) * (point[1] - b[:, 1]) - (c[:, 1] - b[:, 1]) * (point[0] - b[:, 0])
            d3 = (a[:, 0] - c[:, 0]) * (point[1] - c[:, 1]) - (a[:, 1] - c[:, 1]) * (point[0] - c[:, 0])
            return bool(((d1 >= -1e-9) & (d2 >= -1e-9) & (d3 >= -1e-9)).any())

        # the bevel's chord runs between two points one offset from the bend, so it passes
        # 5 · cos(turn / 2) from the bend: 2.5 cm at 121°, through the bend itself at 180°
        chord = 5.0 * math.cos(math.radians(turn_deg) / 2.0)
        assert over(bend - 1.0 * bisector)               # just inside the bend: under the lid
        if chord > 0.5:
            assert over(bend + 0.5 * chord * bisector)   # between the bend and the bevel: lid
        assert not over(bend + (chord + 0.5) * bisector)  # past the bevel: open air (round 0: lid)

    def test_a_bend_of_120_degrees_is_still_mitred(self) -> None:
        heading = math.radians(120.0)
        bend = np.asarray((300.0, 0.0))
        path = [(0.0, 0.0), tuple(bend),
                (300.0 + 300.0 * math.cos(heading), 300.0 * math.sin(heading))]
        mesh = sweep(BOX_PROFILE, path)
        assert mesh.triangle_count == 2 * 4 * 2 + 2 * 2  # two segments, two ends: no bevel face
        plan = mesh.positions.astype(np.float64)[:, :2]
        at_the_bend = plan[np.linalg.norm(plan - bend, axis=1) < 50.0]
        # both sides of the section sit on the mitre: 2 offsets from the bend
        assert np.allclose(np.linalg.norm(at_the_bend - bend, axis=1), 2.0 * 5.0, atol=1e-3)

    def test_a_closed_loop_with_an_acute_corner(self) -> None:
        apex = (0.0, 200.0 / math.tan(math.radians(15.0)))
        loop = sweep(BOX_PROFILE, [(-200.0, 0.0), (200.0, 0.0), apex], closed=True)
        loop.validate()
        plan = loop.positions.astype(np.float64)[:, :2]
        assert float(plan[:, 1].max()) <= apex[1] + 5.0 + 1e-3  # round 0: + 19.3 (5 / sin 15°)
        assert float(flat_dots(loop).min()) > 0.9999

    def test_the_reach_at_a_sharp_bend_depends_on_the_legs(self) -> None:
        """Review round 2, P2-5. The furthest a swept vertex lies from the path, in
        offsets: ``BEVEL_BEYOND`` when every leg is at least ``MITER_LIMIT`` offsets
        long; with shorter legs the inside mitre of a sharp bend lies beyond the leg's
        other end, and the bound is the mitre's own length, ``MITER_LIMIT``. Pinned:
        a 10 cm half width along 20 cm legs at 160° reaches 2.06 offsets."""
        def away(path: list[tuple[float, float]]) -> float:
            mesh = sweep(BOX_PROFILE, path)
            mesh.validate()
            plan = mesh.positions.astype(np.float64)[:, :2]
            line = np.asarray(path, dtype=np.float64)
            distance = np.min([_distance_to_segment(plan, a, b)
                               for a, b in zip(line[:-1], line[1:], strict=True)], axis=0)
            return float(distance.max()) / 5.0

        def zigzag(legs: list[float], turns: list[float]) -> list[tuple[float, float]]:
            points, heading = [(0.0, 0.0)], 0.0
            for index, leg in enumerate(legs):
                points.append((points[-1][0] + leg * math.cos(heading),
                               points[-1][1] + leg * math.sin(heading)))
                if index < len(turns):
                    heading += math.radians(turns[index])
            return points

        assert away(zigzag([10.0] * 4, [160.0, -160.0, 160.0])) == pytest.approx(2.06, abs=0.01)
        assert away(zigzag([30.0] * 4, [160.0, -160.0, 160.0])) == pytest.approx(1.0, abs=1e-3)
        rng = np.random.Generator(np.random.PCG64(20261011))
        worst_short, worst_long = 0.0, 0.0
        for _ in range(400):
            count = int(rng.integers(2, 6))
            turns = [float(rng.choice([-1.0, 1.0]) * rng.uniform(5.0, 178.0)) for _ in range(count - 1)]
            short = [float(rng.uniform(0.2, 6.0)) * 5.0 for _ in range(count)]
            long = [float(rng.uniform(MITER_LIMIT, 8.0)) * 5.0 for _ in range(count)]
            worst_short = max(worst_short, away(zigzag(short, turns)))
            worst_long = max(worst_long, away(zigzag(long, turns)))
        assert worst_long <= BEVEL_BEYOND + 1e-6          # the stated bound, where it holds
        assert BEVEL_BEYOND < worst_short <= MITER_LIMIT + 1e-6  # … and the real one elsewhere

    def test_plank(self) -> None:
        board = plank((0.0, 0.0), (0.0, 180.0), 14.0, 20.0, 24.0, 0.5, RED)
        board.validate()
        assert board.triangle_count == 28
        low, high = board.bounds()
        assert (float(low[2]), float(high[2])) == (20.0, 24.0)
        assert (float(low[0]), float(high[0])) == (-7.0, 7.0)
        assert_faces_look_away_from(board, (0.0, 90.0, 22.0))


POT = [(30.0, 0.0), (40.0, 30.0), (37.0, 30.0), (37.0, 5.0)]  # out, rim, in


class TestLathe:
    def test_ring_vertices_are_the_2d_footprint_s(self) -> None:
        mesh = lathe(POT, RED)
        mesh.validate()
        assert mesh.triangle_count == 3 * 24 * 2
        rim = mesh.positions[np.isclose(mesh.positions[:, 2], 30.0)
                             & np.isclose(np.hypot(mesh.positions[:, 0], mesh.positions[:, 1]), 40.0,
                                          atol=1e-3)]
        footprint = np.asarray(circle_footprint(0.0, 0.0, 40.0), dtype=np.float32)
        for corner in footprint:
            assert np.isclose(rim[:, :2], corner, atol=1e-4).all(axis=1).any()
        assert float(np.hypot(mesh.positions[:, 0], mesh.positions[:, 1]).max()) == pytest.approx(40.0, abs=1e-4)

    def test_normals_face_out_of_the_wall(self) -> None:
        mesh = lathe(POT)
        dots, flat = normal_vs_winding(mesh)
        assert not flat.all()  # smooth round the axis
        assert float(dots.min()) > 0.99  # 24 segments: the mean normal is within 7.5° of the facet
        corners, winding = triangles_of(mesh)
        centre = corners.mean(axis=1)
        radial = centre[:, :2] / np.linalg.norm(centre[:, :2], axis=1, keepdims=True)
        outer = np.isclose(corners[:, :, 2].min(axis=1), 0.0)  # the outer wall touches the ground
        inner = np.isclose(corners[:, :, 2].min(axis=1), 5.0)
        assert ((winding[outer, :2] * radial[outer]).sum(axis=1) > 0.0).all()  # looks out
        assert ((winding[inner, :2] * radial[inner]).sum(axis=1) < 0.0).all()  # looks into the pot
        rim = ~outer & ~inner
        assert (winding[rim, 2] > 0.99).all()  # the rim looks up

    def test_zero_length_profile_edges_are_dropped(self) -> None:
        assert lathe([(30.0, 0.0), (30.0, 0.0), (30.0, 10.0)]).triangle_count == 48
        assert lathe([(30.0, 0.0)]).vertex_count == 0


class TestTubes:
    def test_wires(self) -> None:
        mesh = tubes([(0, 0, 0), (0, 0, 0)], [(0, 0, 100), (50, 0, 50)], 0.4, 0.4, RED, sides=3)
        mesh.validate()
        assert mesh.triangle_count == 12
        dots, _flat = normal_vs_winding(mesh)
        assert float(dots.min()) > 0.4  # 3 sides: a facet is 60° from its corner normals
        assert float(mesh.positions[:, 2].max()) == 100.0

    def test_it_is_the_spike_s_tubes(self) -> None:
        """Drift guard for the one primitive ported unchanged: the same frustums as the
        L0 spike's ``tubes`` gave for these inputs (frozen when L1.10 deleted it)."""
        spike = SPIKE["meshes"]["tubes_three_six_sided"]
        starts = np.array([[0.0, 0.0, 0.0], [10.0, 5.0, 2.0], [3.0, 3.0, 3.0]], np.float32)
        ends = np.array([[0.0, 0.0, 100.0], [60.0, -5.0, 40.0], [3.0, 80.0, 3.0]], np.float32)
        radius_start = np.array([1.0, 2.0, 0.5], np.float32)
        radius_end = np.array([0.5, 2.0, 0.5], np.float32)
        ours = tubes(starts, ends, radius_start, radius_end, RED, sides=6)
        assert np.allclose(ours.positions, spike["positions"], atol=1e-5)
        assert np.allclose(ours.normals, spike["normals"], atol=1e-6)
        assert np.allclose(ours.colors, spike["colors"], atol=1e-6)
        assert np.array_equal(ours.indices.reshape(-1), np.asarray(spike["indices"]))

    def test_six_sides_are_smooth(self) -> None:
        mesh = tubes([(0, 0, 0)], [(100, 0, 0)], 3.0, 3.0)
        mesh.validate()
        dots, _flat = normal_vs_winding(mesh)
        assert float(dots.min()) > 0.85
        assert tubes(np.zeros((0, 3)), np.zeros((0, 3)), 1.0, 1.0).vertex_count == 0


# ── the two truth rules every builder goes through ───────────────────────────


def _record(kind: str, height: float | None) -> Record:
    return Record("id-1", kind, "rectangle", (tuple(SQUARE),), Transform(), Material(kind),
                  height_cm=height, params=EMPTY_PARAMS)


class TestFit:
    def test_parts_built_to_the_height_are_left_alone(self) -> None:
        parts = (MeshPart(prism_mesh([tuple(SQUARE)], 87.3)),)
        assert top_cm(parts) == float(np.float32(87.3))
        assert fit_scale(parts, 87.3) == pytest.approx(1.0, abs=1e-6)
        assert fit_parts(parts, 87.3) is parts

    def test_the_safety_net_scales_all_parts_with_one_factor(self) -> None:
        low = MeshPart(prism_mesh([tuple(SQUARE)], 50.0), name="low")
        tall = MeshPart(boxes([(0.0, 0.0)], (4.0, 4.0), 0.0, 115.6), name="tall")
        assert fit_scale((low, tall), 100.0) == pytest.approx(100.0 / 115.6, rel=1e-6)
        fitted = fit_parts((low, tall), 100.0)
        assert top_cm(fitted) == pytest.approx(100.0, abs=1e-4)
        assert float(fitted[0].mesh.positions[:, 2].max()) == pytest.approx(50.0 * 100.0 / 115.6, abs=1e-4)
        for part in fitted:
            part.validate()  # the normals took the inverse transpose
        assert fitted[0].name == "low" and fitted[1].name == "tall"

    def test_no_parts(self) -> None:
        assert top_cm(()) is None and fit_scale((), 100.0) == 1.0 and fit_parts((), 100.0) == ()

    def test_nominal_heights_come_from_the_2d_resolver_s_tables(self) -> None:
        from open_garden_planner.core.container_model import DEFAULT_HEIGHT_CM
        from open_garden_planner.core.object_height import DEFAULT_HEIGHTS_CM, effective_height_cm

        assert nominal_height_cm("FENCE") == DEFAULT_HEIGHTS_CM["FENCE"] == 120.0
        assert nominal_height_cm("CONTAINER_ROUND") == DEFAULT_HEIGHT_CM == 30.0
        assert nominal_height_cm("GARDEN_BED") is None and nominal_height_cm("LAWN") is None
        for kind in ("HOUSE", "GARAGE_SHED", "TOOL_SHED", "FENCE", "WALL", "RAISED_BED", "CONTAINER",
                     "WALL_PLANTER", "CONTAINER_ROUND", "HEDGE_SECTION", "HEDGE_POLYGON"):
            assert nominal_height_cm(kind) == effective_height_cm(kind, None)


class TestBuiltBuilder:
    @staticmethod
    def _shape(scale: float = 1.0):
        def shape(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(record.footprints, height_cm * scale), name="body"),
                    MeshPart(Mesh.empty(), name="nothing"))
        return shape

    def test_a_height_is_built_and_casts(self) -> None:
        builder = BuiltBuilder(self._shape(), "probe")
        parts = builder(_record("FENCE", 77.0))
        assert [p.name for p in parts] == ["body"]  # empty parts are dropped
        assert top_cm(parts) == 77.0 and parts[0].casts_shadow
        assert builder.fit_scale(_record("FENCE", 77.0)) == 1.0

    def test_no_height_is_decoration_at_the_nominal_height_without_a_shadow(self) -> None:
        builder = BuiltBuilder(self._shape(), "probe")
        parts = builder(_record("FENCE", None))
        assert top_cm(parts) == 120.0 and not parts[0].casts_shadow
        assert builder(_record("GARDEN_BED", None)) == ()  # no nominal height: ground

    def test_a_shape_that_misses_the_height_is_fitted_and_tells(self) -> None:
        builder = BuiltBuilder(self._shape(1.156), "too tall")  # the L0 BBQ: +15.6 %
        record = _record("FENCE", 100.0)
        assert builder.fit_scale(record) == pytest.approx(1.0 / 1.156, rel=1e-6)
        assert top_cm(builder.raw(record)) == pytest.approx(115.6, abs=1e-4)
        assert top_cm(builder(record)) == pytest.approx(100.0, abs=1e-4)

    def test_it_does_not_change_the_record_or_its_parts_kinds(self) -> None:
        builder = BuiltBuilder(self._shape(), "probe")
        record = _record("FENCE", 50.0)
        assert builder(record) == builder(dataclasses.replace(record, item_id="other"))
        assert "probe" in repr(builder)
