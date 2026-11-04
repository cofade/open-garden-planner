"""The CPU pick oracle (Phase 17 L1.8, the witness of gate G1).

``core/scene3d/pick_oracle.py`` answers "which item is under this view position?"
from the records' own meshes and a camera model of its own. Before the render tier
holds the engine to it, it is held here to three things it did not come from: a
look-at projection written out by hand in this file, the engine story's own
top-down oracle (``quick3d_render_driver.cpu_topmost_hit``), and plain geometry
that can be computed in the head.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from open_garden_planner.core.scene3d import (
    Material,
    MeshPart,
    Params,
    Record,
    Transform,
    default_builder,
    pose_point,
    prism_mesh,
)
from open_garden_planner.core.scene3d.pick_oracle import (
    TOP_DOWN_CAMERA_HEIGHT_CM,
    Ray,
    camera_axes,
    cast,
    cast_all,
    perspective_ray,
    pick_scene,
    project,
    top_down_ray,
)
from tests.integration.quick3d_render_driver import (
    TOP,
    VIEW,
    cpu_topmost_hit,
    oracle_triangles,
    pick_records,
)

DOWN = (0.0, 0.0, -1.0)


def rect(width: float, depth: float) -> tuple[tuple[float, float], ...]:
    half_w, half_d = width / 2.0, depth / 2.0
    return ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))


def box(item_id: str, east: float, north: float, width: float, depth: float, height: float,
        *, rotation: float = 0.0, base: float = 0.0, holes: tuple = ()) -> Record:
    return Record(item_id=item_id, kind="SHED", shape="rectangle",
                  footprints=(rect(width, depth),), holes=holes,
                  transform=Transform(east, north, rotation, base), material=Material("SHED"),
                  height_cm=height, params=Params({"seed": item_id}))


def scene_of(*records: Record):
    return pick_scene({record.item_id: record for record in records}, default_builder)


def down_at(east: float, north: float) -> Ray:
    return Ray((east, north, 5000.0), DOWN)


# ── the rays ─────────────────────────────────────────────────────────────────


def hand_projection(eye, target, fov_deg: float, size, point) -> tuple[float, float]:
    """A look-at view matrix and a perspective divide, written out with numpy — the
    textbook route, sharing no line with the module under test."""
    eye, target, point = (np.array(v, float) for v in (eye, target, point))
    forward = (target - eye) / np.linalg.norm(target - eye)
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    view = np.array([right, up, -forward])          # rows: camera x, y, z (looking down -z)
    cx, cy, cz = view @ (point - eye)
    focal = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    ndc_x = focal / (size[0] / size[1]) * cx / -cz
    ndc_y = focal * cy / -cz
    return ((ndc_x + 1.0) * size[0] / 2.0, (1.0 - ndc_y) * size[1] / 2.0)


CAMERAS = [
    ((1200.0, -1400.0, 1500.0), (1200.0, 800.0, 0.0), 40.0, (640.0, 400.0)),
    ((-300.0, 250.0, 165.0), (400.0, 900.0, 140.0), 60.0, (1600.0, 500.0)),
    ((50.0, 60.0, 900.0), (55.0, 70.0, 0.0), 25.0, (300.0, 700.0)),       # nearly straight down
    ((2500.0, 2500.0, 80.0), (0.0, 0.0, 300.0), 75.0, (800.0, 800.0)),    # looking up
]


@pytest.mark.parametrize(("eye", "target", "fov", "size"), CAMERAS)
def test_the_centre_ray_looks_at_the_target_and_the_edges_are_half_a_field_away(
        eye, target, fov: float, size) -> None:
    centre = perspective_ray(eye, target, fov, size, size[0] / 2.0, size[1] / 2.0)
    aim = np.array(target, float) - np.array(eye, float)
    assert centre.origin == eye
    assert np.allclose(centre.direction, aim / np.linalg.norm(aim), atol=1e-12)
    top = perspective_ray(eye, target, fov, size, size[0] / 2.0, 0.0)
    left = perspective_ray(eye, target, fov, size, 0.0, size[1] / 2.0)
    assert math.degrees(math.acos(np.dot(top.direction, centre.direction))) == pytest.approx(fov / 2.0)
    assert math.degrees(math.acos(np.dot(left.direction, centre.direction))) == pytest.approx(
        math.degrees(math.atan(math.tan(math.radians(fov) / 2.0) * size[0] / size[1])))
    assert top.direction[2] > centre.direction[2], "y runs DOWN the view: row 0 is the top"
    forward, right, up = camera_axes(eye, target)
    assert np.dot(left.direction, right) < 0.0 < np.dot(up, (0.0, 0.0, 1.0))
    assert abs(right[2]) < 1e-12, "no roll: the horizon is level"
    assert np.allclose(np.cross(right, forward), up), "a right-handed frame"


@pytest.mark.parametrize(("eye", "target", "fov", "size"), CAMERAS)
def test_a_ray_through_the_pixel_of_a_point_passes_through_the_point(
        eye, target, fov: float, size) -> None:
    """Against the hand-written projection: project a point, cast the ray back."""
    rng = np.random.default_rng(385)
    forward, right, up = camera_axes(eye, target)
    for _ in range(40):
        depth = float(rng.uniform(50.0, 4000.0))
        spread = math.tan(math.radians(fov) / 2.0) * depth * 0.9
        point = (np.array(eye) + depth * np.array(forward)
                 + rng.uniform(-1, 1) * spread * size[0] / size[1] * np.array(right)
                 + rng.uniform(-1, 1) * spread * np.array(up))
        x, y = hand_projection(eye, target, fov, size, point)
        assert project(eye, target, fov, size, tuple(point)) == pytest.approx((x, y), abs=1e-7)
        ray = perspective_ray(eye, target, fov, size, x, y)
        along = float(np.dot(point - np.array(ray.origin), ray.direction))
        miss = np.linalg.norm(np.array(ray.origin) + along * np.array(ray.direction) - point)
        assert miss < 1e-6, "the ray passes through the point it was aimed at"


def test_a_point_behind_the_camera_has_no_pixel() -> None:
    eye, target = (0.0, 0.0, 100.0), (0.0, 100.0, 100.0)
    assert project(eye, target, 40.0, (400.0, 300.0), (0.0, -50.0, 100.0)) is None
    assert project(eye, target, 40.0, (400.0, 300.0), (0.0, 50.0, 100.0)) == (200.0, 150.0)


def test_the_top_down_ray_is_the_truth_views_projection_read_backwards() -> None:
    from open_garden_planner.ui.view3d.quick3d.shots import TopDownShot, top_down_pixel

    shot = TopDownShot(center=(120.0, -40.0), px_per_cm=0.4)
    size = (480, 360)
    for east, north in ((120.0, -40.0), (0.0, 0.0), (-300.0, 250.0), (431.5, -123.25)):
        x, y = top_down_pixel(east, north, shot, size)
        ray = top_down_ray(shot.center, shot.px_per_cm, size, x, y)
        assert ray.origin == pytest.approx((east, north, TOP_DOWN_CAMERA_HEIGHT_CM))
        assert ray.direction == DOWN


@pytest.mark.parametrize("call", [
    lambda: perspective_ray((0, 0, 0), (0, 0, 0), 40.0, (100.0, 100.0), 0.0, 0.0),
    lambda: perspective_ray((0, 0, 100), (0, 0, 0), 40.0, (100.0, 100.0), 0.0, 0.0),  # straight down
    lambda: perspective_ray((0, 0, 0), (0, 1, 0), 0.0, (100.0, 100.0), 0.0, 0.0),
    lambda: perspective_ray((0, 0, 0), (0, 1, 0), 40.0, (0.0, 100.0), 0.0, 0.0),
    lambda: top_down_ray((0, 0), 0.0, (100.0, 100.0), 0.0, 0.0),
])
def test_a_camera_that_is_none_is_refused(call) -> None:
    with pytest.raises(ValueError):
        call()


# ── the scene and the cast ───────────────────────────────────────────────────


def test_a_ray_from_above_meets_the_top_and_one_from_the_side_the_face() -> None:
    scene = scene_of(box("a", 100.0, 200.0, 80.0, 60.0, 150.0))
    top = cast(scene, down_at(110.0, 190.0))
    assert top is not None and top.item_id == "a" and top.part_index == 1  # the fill cap
    assert top.point == pytest.approx((110.0, 190.0, 150.0)) and top.distance_cm == pytest.approx(4850.0)
    side = cast(scene, Ray((-500.0, 200.0, 40.0), (1.0, 0.0, 0.0)))
    assert side is not None and side.point == pytest.approx((60.0, 200.0, 40.0))
    assert cast(scene, down_at(141.0, 200.0)) is None, "1 cm beside it: the ground is no item"
    assert cast(scene, Ray((100.0, 200.0, 300.0), (0.0, 0.0, 1.0))) is None, "away from it: the sky"


def test_the_nearest_item_along_the_ray_wins() -> None:
    low, tall = box("low", 0.0, 0.0, 300.0, 300.0, 20.0), box("tall", 0.0, 0.0, 40.0, 40.0, 300.0)
    behind = box("behind", 0.0, 400.0, 100.0, 100.0, 100.0)
    scene = scene_of(low, tall, behind)
    assert cast(scene, down_at(0.0, 0.0)).item_id == "tall"       # type: ignore[union-attr]
    assert cast(scene, down_at(100.0, 0.0)).item_id == "low"      # type: ignore[union-attr]
    north = cast(scene, Ray((0.0, -500.0, 10.0), (0.0, 1.0, 0.0)))
    assert north is not None and north.item_id == "low" and north.point[1] == pytest.approx(-150.0)
    over = cast(scene, Ray((0.0, -500.0, 50.0), (0.0, 1.0, 0.0)))  # above the low slab
    assert over is not None and over.item_id == "tall" and over.point[1] == pytest.approx(-20.0)


def test_cast_all_names_every_item_along_the_ray_once_nearest_first() -> None:
    """What a click that falls through a locked item meets next: each item once, where
    the ray first enters it."""
    low, tall = box("low", 0.0, 0.0, 300.0, 300.0, 20.0), box("tall", 0.0, 0.0, 40.0, 40.0, 300.0)
    behind = box("behind", 0.0, 400.0, 100.0, 100.0, 100.0)
    scene = scene_of(behind, tall, low)                     # the order of the scene is not the answer
    through = cast_all(scene, Ray((0.0, -500.0, 10.0), (0.0, 1.0, 0.0)))
    assert [hit.item_id for hit in through] == ["low", "tall", "behind"]
    assert [hit.point[1] for hit in through] == pytest.approx([-150.0, -20.0, 350.0])
    assert [hit.distance_cm for hit in through] == sorted(hit.distance_cm for hit in through)
    assert through[0] == cast(scene, Ray((0.0, -500.0, 10.0), (0.0, 1.0, 0.0)))
    assert [hit.item_id for hit in cast_all(scene, down_at(0.0, 0.0))] == ["tall", "low"]
    assert cast_all(scene, down_at(1000.0, 1000.0)) == ()
    assert cast_all(pick_scene({}, default_builder), down_at(0.0, 0.0)) == ()


def test_a_hole_lets_the_ray_through_to_what_is_below() -> None:
    """A closed fence is an outer ring with the garden as its hole: a click inside it
    meets what stands there — or nothing."""
    hole = tuple(reversed(rect(200.0, 200.0)))
    fence = box("fence", 0.0, 0.0, 240.0, 240.0, 120.0, holes=((hole,),))
    bed = box("bed", 30.0, 30.0, 60.0, 60.0, 40.0)
    scene = scene_of(fence, bed)
    assert cast(scene, down_at(110.0, 0.0)).item_id == "fence"    # type: ignore[union-attr]
    assert cast(scene, down_at(30.0, 30.0)).item_id == "bed"      # type: ignore[union-attr]
    assert cast(scene, down_at(-60.0, -60.0)) is None, "bare ground inside the fence"
    # from inside the courtyard the inner face is met (from behind: no back faces here)
    inner = cast(scene, Ray((-50.0, -50.0, 50.0), (-1.0, 0.0, 0.0)))
    assert inner is not None and inner.item_id == "fence" and inner.point[0] == pytest.approx(-100.0)


@pytest.mark.parametrize("rotation", [0.0, 17.0, 90.0, 213.5])
def test_the_scene_is_posed_by_the_records_transform(rotation: float) -> None:
    bar = box("bar", 400.0, -300.0, 240.0, 60.0, 50.0, rotation=rotation, base=38.0)
    scene = scene_of(bar)
    inside = pose_point(bar.transform, 100.0, 20.0)
    hit = cast(scene, down_at(*inside))
    assert hit is not None and hit.point[2] == pytest.approx(88.0), "base + height"
    outside = pose_point(bar.transform, 100.0, 40.0)
    assert cast(scene, down_at(*outside)) is None


def test_a_record_without_a_solid_is_not_in_the_scene() -> None:
    flat = Record(item_id="lawn", kind="LAWN", shape="rectangle", footprints=(rect(500.0, 500.0),),
                  transform=Transform(), material=Material("LAWN"), params=Params({"seed": "lawn"}))
    scene = scene_of(flat, box("a", 0.0, 0.0, 50.0, 50.0, 50.0))
    assert scene.item_ids == ("a",) and scene.triangle_count == 12 - 2  # a prism has no bottom
    assert cast(scene, down_at(200.0, 200.0)) is None
    assert pick_scene({}, default_builder).triangle_count == 0
    assert cast(pick_scene({}, default_builder), down_at(0.0, 0.0)) is None


def test_the_part_index_names_the_mesh_part_that_was_met() -> None:
    def two_parts(record: Record) -> tuple[MeshPart, ...]:
        low = prism_mesh(record.footprints, 30.0)
        high = prism_mesh((rect(20.0, 20.0),), 200.0)
        return (MeshPart(low, name="body"), MeshPart(prism_mesh((), 1.0)), MeshPart(high, name="mast"))

    scene = pick_scene({"x": box("x", 0.0, 0.0, 100.0, 100.0, 30.0)}, two_parts)
    assert cast(scene, down_at(40.0, 40.0)).part_index == 0        # type: ignore[union-attr]
    assert cast(scene, down_at(0.0, 0.0)).part_index == 2          # type: ignore[union-attr]


def test_it_agrees_with_the_engine_storys_top_down_oracle() -> None:
    """Two oracles written apart — that one projects triangles to the plan and takes
    the highest, this one casts a ray — name the same item over the whole pick scene
    of the engine story (10 items whose boxes overlap)."""
    records = pick_records()
    scene = pick_scene(records, default_builder)
    triangles = oracle_triangles(records)
    rng = np.random.default_rng(1108)
    compared = hits = 0
    for _ in range(600):
        x, y = float(rng.uniform(0.0, VIEW[0])), float(rng.uniform(0.0, VIEW[1]))
        ray = top_down_ray(TOP.center, TOP.px_per_cm, VIEW, x, y)
        expected, height = cpu_topmost_hit(triangles, ray.origin[0], ray.origin[1])
        got = cast(scene, ray)
        # an edge-on wall is met by the ray and has no area in the plan: compare off the edges
        nearby = {cpu_topmost_hit(triangles, ray.origin[0] + dx, ray.origin[1] + dy)[0]
                  for dx in (-0.5, 0.5) for dy in (-0.5, 0.5)}
        if nearby != {expected}:
            continue
        compared += 1
        assert (got.item_id if got is not None else None) == expected
        if got is not None:
            hits += 1
            assert got.point[2] == pytest.approx(height, abs=1e-6)
    assert compared > 500 and hits > 100, (compared, hits)


def test_the_scene_is_read_only() -> None:
    scene = scene_of(box("a", 0.0, 0.0, 50.0, 50.0, 50.0))
    assert not scene.corner.flags.writeable and not scene.edge1.flags.writeable
    with pytest.raises(AttributeError):
        scene.item_ids = ()  # type: ignore[misc]
