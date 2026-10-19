"""The Qt-free orbit camera of the 3D workspace (Phase 17 L1.3, ADR-060).

``core/scene3d/camera.py`` holds the whole camera: the pose, the clamps, the fit
of a plan into the view and the critically damped follow. Nothing here needs Qt,
a window or a GPU — the UI layer only steps it with a timer and forwards input.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from open_garden_planner.core.scene3d import camera as camera_module
from open_garden_planner.core.scene3d.camera import (
    DEFAULT_PITCH_DEG,
    DEFAULT_YAW_DEG,
    FOV_DEG,
    MAX_DISTANCE_CM,
    MAX_PITCH_DEG,
    MIN_DISTANCE_CM,
    MIN_PITCH_DEG,
    SHIPPED_VIEW_OFFSET,
    Bounds,
    CameraPose,
    OrbitCamera,
    frame_pose,
)

PLAN = Bounds(0.0, 0.0, 5000.0, 3000.0, 600.0)


def _project(pose: CameraPose, point: tuple[float, float, float], aspect: float,
             fov_deg: float = FOV_DEG) -> tuple[float, float, float]:
    """An independent perspective projection: normalised device x, y in [-1, 1] and
    the depth along the view axis (this test's own arithmetic, not the module's)."""
    yaw, pitch = math.radians(pose.yaw_deg), math.radians(pose.pitch_deg)
    forward = (math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), -math.sin(pitch))
    right = (math.cos(yaw), -math.sin(yaw), 0.0)
    up = (math.sin(yaw) * math.sin(pitch), math.cos(yaw) * math.sin(pitch), math.cos(pitch))
    eye = pose.eye
    rel = tuple(p - e for p, e in zip(point, eye, strict=True))
    depth = sum(a * b for a, b in zip(rel, forward, strict=True))
    tan_v = math.tan(math.radians(fov_deg) / 2.0)
    x = sum(a * b for a, b in zip(rel, right, strict=True)) / (depth * tan_v * aspect)
    y = sum(a * b for a, b in zip(rel, up, strict=True)) / (depth * tan_v)
    return x, y, depth


def _corners(bounds: Bounds) -> list[tuple[float, float, float]]:
    return [(e, n, z) for e in (bounds.min_east, bounds.max_east)
            for n in (bounds.min_north, bounds.max_north) for z in (0.0, bounds.height_cm)]


class TestPose:
    def test_yaw_is_the_compass_bearing_the_camera_looks_along(self) -> None:
        north = CameraPose((100.0, 200.0), 1000.0, 0.0, 30.0)
        assert north.eye[0] == pytest.approx(100.0)
        assert north.eye[1] < 200.0, "looking north, the eye stands south of its target"
        east = CameraPose((100.0, 200.0), 1000.0, 90.0, 30.0)
        assert east.eye[0] < 100.0, "looking east, the eye stands west of its target"
        assert east.eye[1] == pytest.approx(200.0)

    def test_pitch_tilts_the_view_down_and_the_eye_keeps_its_distance(self) -> None:
        for pitch in (5.0, 31.0, 60.0, 89.0):
            pose = CameraPose((0.0, 0.0), 800.0, 123.0, pitch)
            east, north, up = pose.eye
            assert up == pytest.approx(800.0 * math.sin(math.radians(pitch)))
            assert math.dist((east, north, up), (0.0, 0.0, 0.0)) == pytest.approx(800.0)

    def test_the_target_is_a_point_on_the_ground(self) -> None:
        assert CameraPose((7.0, 9.0), 500.0, 0.0, 45.0).target_scene == (7.0, 9.0, 0.0)

    def test_the_default_direction_is_the_shipped_3d_views(self) -> None:
        """The Qt 3D view frames a plan from centre + (0.55, 0.5, 0.6) x diagonal in its
        engine frame (x east, y up, z = -north): the new view starts from the same side."""
        east, up, minus_north = SHIPPED_VIEW_OFFSET
        pose = CameraPose((0.0, 0.0), math.sqrt(east**2 + up**2 + minus_north**2),
                          DEFAULT_YAW_DEG, DEFAULT_PITCH_DEG)
        assert pose.eye == pytest.approx((east, -minus_north, up), abs=1e-9)
        assert (east, up, minus_north) == (0.55, 0.5, 0.6)

    @pytest.mark.parametrize("bad", [
        ((math.nan, 0.0), 100.0, 0.0, 30.0), ((0.0, 0.0), math.inf, 0.0, 30.0),
        ((0.0, 0.0), 0.0, 0.0, 30.0), ((0.0, 0.0), -5.0, 0.0, 30.0),
        ((0.0, 0.0), 100.0, math.nan, 30.0), ((0.0, 0.0), 100.0, 0.0, math.inf),
    ])
    def test_a_pose_that_is_not_a_place_is_refused(self, bad: tuple) -> None:
        with pytest.raises(ValueError):
            CameraPose(*bad)


class TestFraming:
    @pytest.mark.parametrize("aspect", [0.3, 0.75, 1.0, 16.0 / 9.0, 3.5])
    @pytest.mark.parametrize("bounds", [
        PLAN, Bounds(0.0, 0.0, 5000.0, 3000.0, 0.0), Bounds(-200.0, 400.0, 100.0, 9000.0, 2500.0),
        Bounds(0.0, 0.0, 300.0, 300.0, 40.0),
    ])
    def test_the_whole_plan_is_inside_the_view_and_fills_it(self, bounds: Bounds,
                                                            aspect: float) -> None:
        pose = frame_pose(bounds, aspect)
        projected = [_project(pose, corner, aspect) for corner in _corners(bounds)]
        assert all(depth > 0.0 for _x, _y, depth in projected)
        reach = max(max(abs(x), abs(y)) for x, y, _depth in projected)
        # inside, with the stated margin — and not lost in the distance either
        assert reach <= 1.0 / camera_module.FRAME_MARGIN + 1e-9
        assert reach >= 1.0 / camera_module.FRAME_MARGIN - 1e-6
        assert pose.target == pytest.approx(
            ((bounds.min_east + bounds.max_east) / 2, (bounds.min_north + bounds.max_north) / 2))
        assert (pose.yaw_deg, pose.pitch_deg) == (DEFAULT_YAW_DEG, DEFAULT_PITCH_DEG)

    def test_the_direction_can_be_kept_while_the_plan_is_fitted_again(self) -> None:
        pose = frame_pose(PLAN, 1.5, yaw_deg=10.0, pitch_deg=70.0)
        assert (pose.yaw_deg, pose.pitch_deg) == (10.0, 70.0)
        assert all(abs(x) <= 1.0 and abs(y) <= 1.0
                   for x, y, _d in (_project(pose, c, 1.5) for c in _corners(PLAN)))

    def test_a_plan_too_large_for_the_far_plane_is_framed_at_the_limit(self) -> None:
        pose = frame_pose(Bounds(0.0, 0.0, 400_000.0, 400_000.0, 0.0), 1.0)
        assert pose.distance_cm == MAX_DISTANCE_CM

    def test_a_point_sized_plan_keeps_a_usable_distance(self) -> None:
        pose = frame_pose(Bounds(10.0, 10.0, 10.0, 10.0, 0.0), 1.0)
        assert pose.distance_cm == MIN_DISTANCE_CM

    @pytest.mark.parametrize("aspect", [0.0, -1.0, math.nan, math.inf])
    def test_an_aspect_that_is_no_shape_is_refused(self, aspect: float) -> None:
        with pytest.raises(ValueError):
            frame_pose(PLAN, aspect)

    def test_bounds_must_be_ordered_and_finite(self) -> None:
        with pytest.raises(ValueError):
            Bounds(10.0, 0.0, 0.0, 10.0)
        with pytest.raises(ValueError):
            Bounds(0.0, 0.0, 10.0, math.nan)
        with pytest.raises(ValueError):
            Bounds(0.0, 0.0, 10.0, 10.0, -1.0)


def _settle(camera: OrbitCamera, dt: float = 1.0 / 60.0, limit: int = 2000) -> int:
    steps = 0
    while camera.step(dt):
        steps += 1
        assert steps < limit, "the camera never settled"
    return steps


class TestInput:
    def test_a_new_camera_stands_still(self) -> None:
        camera = OrbitCamera()
        before = camera.pose
        assert camera.moving is False
        assert camera.step(0.016) is False
        assert camera.pose == before and camera.goal == before

    def test_orbit_turns_the_goal_and_the_pose_follows(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0))
        camera.orbit(40.0, 10.0)
        assert camera.goal.yaw_deg == 40.0 and camera.goal.pitch_deg == 40.0
        assert camera.pose.yaw_deg == 0.0, "the pose only moves when it is stepped"
        assert camera.moving is True
        _settle(camera)
        assert camera.pose == camera.goal

    def test_pitch_is_clamped_between_the_horizon_and_straight_down(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0))
        camera.orbit(0.0, 500.0)
        assert camera.goal.pitch_deg == MAX_PITCH_DEG
        camera.orbit(0.0, -500.0)
        assert camera.goal.pitch_deg == MIN_PITCH_DEG

    def test_zoom_multiplies_the_distance_and_is_clamped(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0))
        camera.zoom(0.5)
        assert camera.goal.distance_cm == 500.0
        camera.zoom(1e-9)
        assert camera.goal.distance_cm == MIN_DISTANCE_CM
        camera.zoom(1e12)
        assert camera.goal.distance_cm == MAX_DISTANCE_CM
        with pytest.raises(ValueError):
            camera.zoom(0.0)

    @pytest.mark.parametrize(("yaw", "right", "forward", "expected"), [
        (0.0, 100.0, 0.0, (100.0, 0.0)),      # looking north: right is east
        (0.0, 0.0, 100.0, (0.0, 100.0)),      # … and forward is north
        (90.0, 100.0, 0.0, (0.0, -100.0)),    # looking east: right is south
        (90.0, 0.0, 100.0, (100.0, 0.0)),
        (180.0, 100.0, 0.0, (-100.0, 0.0)),
    ])
    def test_a_pan_moves_the_target_over_the_ground_relative_to_the_view(
            self, yaw: float, right: float, forward: float,
            expected: tuple[float, float]) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, yaw, 30.0))
        camera.pan(right, forward)
        assert camera.goal.target == pytest.approx(expected, abs=1e-9)
        assert camera.goal.distance_cm == 1000.0

    def test_a_pan_stops_at_the_plan_plus_its_margin(self) -> None:
        camera = OrbitCamera(CameraPose((2500.0, 1500.0), 1000.0, 0.0, 30.0))
        camera.set_bounds(PLAN)
        camera.pan(1e9, 1e9)
        margin = camera_module.PAN_MARGIN_CM
        assert camera.goal.target == (5000.0 + margin, 3000.0 + margin)
        camera.pan(-1e12, -1e12)
        assert camera.goal.target == (-margin, -margin)

    def test_new_bounds_alone_never_move_the_camera(self) -> None:
        """A canvas that shrinks under the camera is an edit, and edits never move it:
        the bounds only limit the NEXT pan."""
        camera = OrbitCamera(CameraPose((4000.0, 2500.0), 1000.0, 0.0, 30.0))
        before = (camera.pose, camera.goal)
        camera.set_bounds(Bounds(0.0, 0.0, 1000.0, 1000.0))
        assert (camera.pose, camera.goal) == before
        assert camera.moving is False

    def test_a_drag_in_pixels_moves_the_ground_under_the_cursor(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 90.0 - 1e-9))
        # straight down, a view 600 px high shows 2 d tan(fov/2) centimetres
        visible = 2.0 * 1000.0 * math.tan(math.radians(FOV_DEG) / 2.0)
        camera.drag_pixels(60.0, 0.0, viewport_height_px=600.0)
        assert camera.goal.target[0] == pytest.approx(-visible / 10.0)  # the ground follows the hand
        camera.snap()
        camera.drag_pixels(0.0, 60.0, viewport_height_px=600.0)
        assert camera.goal.target[1] == pytest.approx(visible / 10.0, rel=1e-6)

    def test_frame_sets_the_goal_and_snap_makes_it_the_pose(self) -> None:
        camera = OrbitCamera()
        camera.frame(PLAN, 1.6)
        assert camera.goal == frame_pose(PLAN, 1.6)
        assert camera.moving is True
        camera.frame(PLAN, 1.6, snap=True)
        assert camera.pose == camera.goal == frame_pose(PLAN, 1.6)
        assert camera.moving is False

    def _at_rest(self, camera: OrbitCamera) -> None:
        for _ in range(2000):
            if not camera.step(1.0 / 60.0):
                return
        raise AssertionError("the camera never came to rest")

    def test_home_after_six_turns_takes_the_shortest_way_back(self) -> None:
        """Yaw is free while orbiting. Aiming at the default yaw itself unwound every
        turn: from 2,477.5 degrees back to 317.5 — six full spins before the plan was
        framed (measured). The goal is the equivalent angle nearest to the camera."""
        camera = OrbitCamera()
        camera.frame(PLAN, 1.6, snap=True)
        home = frame_pose(PLAN, 1.6)
        for _ in range(24):
            camera.orbit(90.0, 0.0)              # six turns to the right
        camera.orbit(20.0, 5.0)                  # … and a little further
        self._at_rest(camera)
        assert camera.pose.yaw_deg == pytest.approx(home.yaw_deg + 6 * 360.0 + 20.0)

        camera.frame(PLAN, 1.6)                  # Home
        assert camera.goal.yaw_deg == home.yaw_deg + 6 * 360.0, "the same side, six turns on"
        assert abs(camera.goal.yaw_deg - camera.pose.yaw_deg) <= 180.0
        travelled, last = 0.0, camera.pose.yaw_deg
        for _ in range(2000):
            moving = camera.step(1.0 / 60.0)
            travelled += abs(camera.pose.yaw_deg - last)
            last = camera.pose.yaw_deg
            if not moving:
                break
        assert travelled == pytest.approx(20.0, abs=0.5), "it turned back the 20 degrees, no more"
        assert camera.pose.eye == pytest.approx(home.eye), "and stands where Home is"
        assert camera.pose.target == home.target and camera.pose.pitch_deg == home.pitch_deg

    @pytest.mark.parametrize(("turned", "expected"), [
        (0.0, 0.0), (179.0, 0.0), (181.0, 360.0), (-181.0, -360.0), (540.5, 720.0),
        (-2000.0, -2160.0),
    ])
    def test_home_is_never_more_than_half_a_turn_away(self, turned: float, expected: float) -> None:
        camera = OrbitCamera()
        camera.frame(PLAN, 1.6, snap=True)
        home = frame_pose(PLAN, 1.6)
        camera.orbit(turned, 0.0)
        camera.snap()
        camera.frame(PLAN, 1.6)
        assert camera.goal.yaw_deg == home.yaw_deg + expected
        assert abs(camera.goal.yaw_deg - camera.pose.yaw_deg) <= 180.0

    def test_a_snap_lands_on_the_default_yaw_itself(self) -> None:
        """A new document frames with a snap: no turn count is carried over."""
        camera = OrbitCamera()
        camera.frame(PLAN, 1.6, snap=True)
        camera.orbit(2000.0, 0.0)
        camera.snap()
        camera.frame(PLAN, 1.6, snap=True)
        assert camera.pose == frame_pose(PLAN, 1.6)

    def test_input_that_changes_nothing_does_not_wake_the_camera(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), MIN_DISTANCE_CM, 0.0, MAX_PITCH_DEG))
        camera.orbit(0.0, 10.0)      # already straight down
        camera.zoom(0.5)             # already as close as it gets
        camera.pan(0.0, 0.0)
        assert camera.moving is False


class TestDamping:
    def test_the_pose_approaches_its_goal_without_overshoot(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0))
        camera.orbit(90.0, 0.0)
        camera.pan(500.0, 0.0)
        last_yaw, last_east = 0.0, 0.0
        while camera.step(1.0 / 60.0):
            assert last_yaw <= camera.pose.yaw_deg <= 90.0 + 1e-9
            assert last_east <= camera.pose.target[0] <= camera.goal.target[0] + 1e-9
            last_yaw, last_east = camera.pose.yaw_deg, camera.pose.target[0]
        assert camera.pose == camera.goal

    def test_it_settles_in_well_under_a_second(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0))
        camera.orbit(180.0, 40.0)
        camera.zoom(4.0)
        camera.pan(2000.0, -1500.0)
        steps = _settle(camera)
        assert steps / 60.0 < 1.0, f"{steps} steps of 1/60 s"

    def test_the_step_size_does_not_change_where_the_pose_is(self) -> None:
        """The integrator is exact: a stalled timer (one long step) lands where many
        short ones would."""
        def run(parts: int) -> CameraPose:
            camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0))
            camera.orbit(70.0, 20.0)
            camera.zoom(3.0)
            camera.pan(300.0, 400.0)
            for _ in range(parts):
                camera.step(0.1 / parts)
            return camera.pose

        coarse, fine = run(1), run(50)
        assert coarse.yaw_deg == pytest.approx(fine.yaw_deg, abs=1e-9)
        assert coarse.pitch_deg == pytest.approx(fine.pitch_deg, abs=1e-9)
        assert coarse.distance_cm == pytest.approx(fine.distance_cm, rel=1e-12)
        assert coarse.target == pytest.approx(fine.target, abs=1e-9)

    def test_zoom_is_damped_in_proportion_so_the_distance_stays_positive(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 50_000.0, 0.0, 30.0))
        camera.zoom(1e-3)
        while camera.step(0.5):
            assert camera.pose.distance_cm > 0.0
        assert camera.pose.distance_cm == camera.goal.distance_cm

    def test_once_settled_the_pose_is_exactly_the_goal_and_stays(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0))
        camera.orbit(33.3, 7.7)
        _settle(camera)
        settled = camera.pose
        assert settled == camera.goal
        for _ in range(100):
            assert camera.step(0.016) is False
        assert camera.pose is settled

    def test_input_during_the_motion_is_followed_smoothly(self) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0))
        camera.orbit(60.0, 0.0)
        for _ in range(5):
            camera.step(1.0 / 60.0)
        mid = camera.pose.yaw_deg
        camera.orbit(-120.0, 0.0)   # the user turns back
        camera.step(1.0 / 60.0)
        # the velocity is continuous: one step later it has not jumped
        assert abs(camera.pose.yaw_deg - mid) < 5.0
        _settle(camera)
        assert camera.pose.yaw_deg == -60.0

    @pytest.mark.parametrize("dt", [0.0, -1.0, math.nan])
    def test_a_step_of_no_time_moves_nothing(self, dt: float) -> None:
        camera = OrbitCamera(CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0))
        camera.orbit(60.0, 0.0)
        before = camera.pose
        assert camera.step(dt) is True
        assert camera.pose == before


def test_the_camera_module_is_qt_free() -> None:
    """Standard library only — the whole camera runs without Qt (ADR-048: Qt-free cores)."""
    source = Path(camera_module.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "math", "dataclasses", "typing"}, imported
