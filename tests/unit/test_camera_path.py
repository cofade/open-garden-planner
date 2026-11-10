"""Camera tours as plain data (Phase 17 L6.2, #390): the spline, the orbit, the frame list."""

from __future__ import annotations

import ast
import math
from datetime import date, time
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core import camera_path
from open_garden_planner.core.camera_path import (
    DATE_STEPS_PER_S,
    EYE_SAMPLES_PER_S,
    FRAME_RATES,
    MIN_EYE_CM,
    WIND_START_S,
    CameraKey,
    CameraPath,
    DroneOrbit,
    HeldCamera,
    TourSpec,
    frame_count,
    path_eyes,
    tour_frames,
)
from open_garden_planner.core.scene3d.camera import CameraPose

KEYS = (
    CameraKey((0.0, 0.0, 300.0), (500.0, 500.0, 0.0), 40.0),
    CameraKey((1000.0, 0.0, 400.0), (500.0, 500.0, 0.0), 40.0),
    CameraKey((1000.0, 1000.0, 200.0), (500.0, 500.0, 100.0), 30.0),
    CameraKey((0.0, 1000.0, 600.0), (500.0, 500.0, 0.0), 50.0),
)


def eyes(path: CameraPath, samples: int = 400) -> np.ndarray:
    return np.array([path.at(index / (samples - 1)).eye for index in range(samples)])


def test_the_module_is_free_of_qt() -> None:
    tree = ast.parse(Path(camera_path.__file__).read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(name.startswith("PyQt6") for name in imported)


def test_an_open_path_starts_and_ends_on_its_keys() -> None:
    path = CameraPath(KEYS)
    assert path.at(0.0) == KEYS[0]
    start, end = path.at(0.0), path.at(1.0)
    assert end.eye == pytest.approx(KEYS[-1].eye)
    assert end.target == pytest.approx(KEYS[-1].target)
    assert end.fov_deg == pytest.approx(KEYS[-1].fov_deg)
    assert start.fov_deg == pytest.approx(KEYS[0].fov_deg)


@pytest.mark.parametrize("key", KEYS)
def test_the_spline_passes_through_every_key(key: CameraKey) -> None:
    path = CameraPath(KEYS)
    nearest = min(math.dist(eye, key.eye) for eye in eyes(path, 4000))
    assert nearest < 2.0, f"the path misses a key by {nearest:.1f} cm"


def test_a_closed_path_comes_back_without_a_stop() -> None:
    path = CameraPath(KEYS, closed=True)
    assert path.closed
    assert path.at(1.0).eye == pytest.approx(path.at(0.0).eye)
    # no easing and constant speed: the steps either side of the seam are like any other
    points = eyes(path, 401)
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    assert steps.max() / np.median(steps) < 1.6


def test_the_speed_along_an_open_path_is_constant_between_its_soft_ends() -> None:
    """Keys 10 m and 30 cm apart: a spline travelled by its parameter would crawl and race."""
    keys = (CameraKey((0.0, 0.0, 300.0), (0.0, 500.0, 0.0)),
            CameraKey((1000.0, 0.0, 300.0), (0.0, 500.0, 0.0)),
            CameraKey((1030.0, 0.0, 300.0), (0.0, 500.0, 0.0)),
            CameraKey((2000.0, 0.0, 300.0), (0.0, 500.0, 0.0)))
    points = eyes(CameraPath(keys), 201)
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    middle = steps[40:160]
    assert middle.max() / middle.min() < 1.25
    assert steps[0] < middle.mean() * 0.25, "it eases in"
    assert steps[-1] < middle.mean() * 0.25, "it eases out"


def test_the_centripetal_spline_does_not_overshoot_uneven_keys() -> None:
    """The reason for the centripetal form: between keys of very different spacing the
    uniform spline swings far past them (and can loop)."""
    keys = (CameraKey((0.0, 0.0, 200.0), (0.0, 1.0, 200.0)),
            CameraKey((1000.0, 0.0, 200.0), (1000.0, 1.0, 200.0)),
            CameraKey((1010.0, 10.0, 200.0), (1010.0, 11.0, 200.0)),
            CameraKey((1010.0, 1000.0, 200.0), (1010.0, 1001.0, 200.0)))
    points = eyes(CameraPath(keys), 800)
    assert points[:, 0].max() < 1010.0 + 15.0
    assert points[:, 1].min() > -15.0


def test_the_eye_stays_above_the_ground_where_the_spline_would_dip() -> None:
    keys = (CameraKey((0.0, 0.0, 1000.0), (100.0, 0.0, 0.0)),
            CameraKey((100.0, 0.0, 25.0), (200.0, 0.0, 0.0)),
            CameraKey((200.0, 0.0, 1000.0), (300.0, 0.0, 0.0)))
    assert eyes(CameraPath(keys), 500)[:, 2].min() >= MIN_EYE_CM


def test_identical_keys_count_once_and_two_different_ones_are_needed() -> None:
    assert len(CameraPath((KEYS[0], KEYS[0], KEYS[1], KEYS[1])).keys) == 2
    for keys in ((), (KEYS[0],), (KEYS[0], KEYS[0])):
        with pytest.raises(ValueError, match="at least two"):
            CameraPath(keys)


def test_a_key_that_only_zooms_is_a_real_key() -> None:
    near = CameraKey(KEYS[0].eye, KEYS[0].target, 60.0)
    path = CameraPath((KEYS[0], near))
    assert path.at(0.5).fov_deg == pytest.approx(50.0, abs=0.5)
    assert path.at(0.5).eye == pytest.approx(KEYS[0].eye)


@pytest.mark.parametrize("bad", [
    {"eye": (0.0, 0.0, float("nan")), "target": (1.0, 0.0, 0.0)},
    {"eye": (0.0, 0.0, 0.0), "target": (0.0, 0.0, 0.0)},
    {"eye": (0.0, 0.0, 0.0), "target": (1.0, 0.0, 0.0), "fov_deg": 0.0},
    {"eye": (0.0, 0.0, 0.0), "target": (1.0, 0.0, 0.0), "fov_deg": 180.0},
    {"eye": (0.0, 0.0), "target": (1.0, 0.0, 0.0)},
])
def test_a_key_refuses_what_no_camera_can_be(bad: dict) -> None:
    with pytest.raises(ValueError):
        CameraKey(**bad)


POSE = CameraPose((1200.0, 800.0), 2500.0, 35.0, 30.0)


def test_a_drone_orbit_starts_where_the_view_is_and_keeps_its_distance_and_height() -> None:
    orbit = DroneOrbit(POSE)
    assert orbit.closed
    assert orbit.at(0.0).eye == pytest.approx(POSE.eye)
    assert orbit.at(0.0).target == pytest.approx(POSE.target_scene)
    for u in (0.1, 0.33, 0.5, 0.77):
        key = orbit.at(u)
        assert math.dist(key.eye, key.target) == pytest.approx(POSE.distance_cm)
        assert key.eye[2] == pytest.approx(POSE.eye[2])
    assert orbit.at(1.0).eye == pytest.approx(orbit.at(0.0).eye)


def test_a_clockwise_drone_orbit_turns_clockwise_seen_from_above() -> None:
    """Yaw means what it means in the view: seen from above with north up, the eye's compass
    bearing from the target grows."""
    def bearing(orbit: DroneOrbit, u: float) -> float:
        key = orbit.at(u)
        return math.degrees(math.atan2(key.eye[0] - POSE.target[0], key.eye[1] - POSE.target[1]))

    clockwise, other = DroneOrbit(POSE), DroneOrbit(POSE, clockwise=False)
    assert (bearing(clockwise, 0.01) - bearing(clockwise, 0.0)) % 360.0 < 180.0
    assert (bearing(other, 0.01) - bearing(other, 0.0)) % 360.0 > 180.0


def test_half_a_turn_is_not_a_loop() -> None:
    assert not DroneOrbit(POSE, turns=0.5).closed
    assert DroneOrbit(POSE, turns=2.0).closed
    with pytest.raises(ValueError):
        DroneOrbit(POSE, turns=0.0)


def yaw_steps(orbit: DroneOrbit, frames: int = 360) -> np.ndarray:
    """The orbit's turn per frame, in degrees, over ``frames`` frames of its tour."""
    spec = TourSpec(orbit, frames / 30.0, 30)
    bearings = [math.degrees(math.atan2(frame.key.eye[0] - POSE.target[0],
                                        frame.key.eye[1] - POSE.target[1]))
                for frame in tour_frames(spec)]
    return np.diff(np.unwrap(np.radians(bearings))) * 180.0 / math.pi


def test_an_orbit_that_does_not_ease_flies_the_frames_it_always_flew() -> None:
    """#807: easing is new and opt-in. Every orbit before it - and every saved one that does
    not ask - turns at one speed and ends one step before its start (the loop's seam)."""
    orbit = DroneOrbit(POSE, turns=2.0)
    assert not orbit.ease and orbit.closed
    frames = list(tour_frames(TourSpec(orbit, 4.0, 30)))
    for frame in frames:   # the expression the orbit has always used, to the last bit
        expected = CameraPose(POSE.target, POSE.distance_cm,
                              POSE.yaw_deg + 1.0 * 360.0 * 2.0 * (frame.index / len(frames)),
                              POSE.pitch_deg)
        assert frame.key == CameraKey(expected.eye, expected.target_scene, 40.0)


def test_an_eased_orbit_starts_and_stops_at_rest_and_is_not_a_loop() -> None:
    orbit = DroneOrbit(POSE, turns=1.0, ease=True)
    assert not orbit.closed, "it stops where it started: a loop would stutter at the seam"
    steps = yaw_steps(orbit)
    cruise = np.median(steps)
    assert steps[0] < 0.01 * cruise and steps[-1] < 0.01 * cruise, "at rest at both ends"
    assert steps.sum() == pytest.approx(360.0), "a whole turn, from rest to rest"
    assert cruise == pytest.approx(360.0 / 359 / (1.0 - camera_path.ORBIT_EASE_SHARE), rel=1e-3)
    assert orbit.at(1.0).eye == pytest.approx(orbit.at(0.0).eye)


def test_an_eased_orbit_changes_its_speed_smoothly() -> None:
    """No kick: the speed and its change are continuous where the ease meets the cruise
    (a raised cosine, so the acceleration is 0 at rest and at the cruise)."""
    frames = 900
    steps = yaw_steps(DroneOrbit(POSE, turns=1.0, ease=True), frames)
    change = np.diff(steps)
    ramp = camera_path.ORBIT_EASE_SHARE * (frames - 1)
    cruise = 360.0 / (frames - 1) / (1.0 - camera_path.ORBIT_EASE_SHARE)
    # the raised cosine's largest change of speed, and the largest change of that, per frame
    assert np.abs(change).max() <= cruise * math.pi / (2.0 * ramp) * 1.01
    assert np.abs(np.diff(change)).max() <= cruise * math.pi ** 2 / (2.0 * ramp ** 2) * 1.05
    joint = round(ramp)
    # (a linear ramp, the keyframe path's, changes its speed by its whole amount at once)
    assert abs(change[0]) < 0.05 * np.abs(change).max(), "it leaves rest without a kick"
    assert np.abs(change[joint - 2:joint + 2]).max() < 0.05 * np.abs(change).max(), \
        "and joins the cruise without one"


def test_an_eased_orbit_turns_both_ways_and_a_whole_number_of_times() -> None:
    clockwise = DroneOrbit(POSE, turns=2.0, ease=True)
    other = DroneOrbit(POSE, turns=2.0, clockwise=False, ease=True)
    assert yaw_steps(clockwise).sum() == pytest.approx(720.0)
    assert yaw_steps(other).sum() == pytest.approx(-720.0)


@pytest.mark.parametrize(("distance", "low"), [(5000.0, 5.0), (2300.0, 5.0), (100.0, 11.54),
                                               (40.0, 30.0), (10.0, 89.0)])
def test_an_orbits_pitch_keeps_the_eye_above_the_ground(distance: float, low: float) -> None:
    """The view's own range (5 to 89 degrees), and never an eye lower than MIN_EYE_CM: a
    short orbit tilts up instead of skimming the lawn."""
    floor, ceiling = camera_path.orbit_pitch_range(distance)
    assert floor == pytest.approx(low, abs=0.01) and ceiling == 89.0
    eye = CameraPose((0.0, 0.0), distance, 0.0, floor).eye
    assert eye[2] >= min(MIN_EYE_CM, distance * math.sin(math.radians(89.0))) - 1e-9


def test_a_pitch_outside_the_range_is_put_back_into_it() -> None:
    assert camera_path.clamp_orbit_pitch(1.0, 5000.0) == 5.0
    assert camera_path.clamp_orbit_pitch(95.0, 5000.0) == 89.0
    assert camera_path.clamp_orbit_pitch(18.5, 5000.0) == 18.5
    assert camera_path.clamp_orbit_pitch(10.0, 100.0) == pytest.approx(11.54, abs=0.01)


def test_a_held_camera_stays() -> None:
    held = HeldCamera(KEYS[0])
    assert held.at(0.0) == held.at(1.0) == KEYS[0]
    assert not held.closed


def test_a_tour_has_exactly_its_frames_each_from_its_index_alone() -> None:
    spec = TourSpec(CameraPath(KEYS), 2.0, 30)
    frames = list(tour_frames(spec))
    assert frame_count(spec) == len(frames) == 60
    assert [frame.index for frame in frames] == list(range(60))
    assert frames == list(tour_frames(spec)), "the same spec is the same frames"
    assert frames[0].u == 0.0 and frames[-1].u == 1.0
    assert frames[0].plan_date is None and frames[0].time_of_day is None


@pytest.mark.parametrize("fps", FRAME_RATES)
def test_a_looped_tour_ends_one_step_before_its_start(fps: int) -> None:
    """A closed motion must not repeat its first frame, or a looped video stutters — for
    every frame rate: the step shrinks with it."""
    frames = list(tour_frames(TourSpec(DroneOrbit(POSE), 2.0, fps)))
    first, second, last = frames[0], frames[1], frames[-1]
    step = math.dist(first.key.eye, second.key.eye)
    assert math.dist(last.key.eye, first.key.eye) == pytest.approx(step, rel=0.02)


def test_the_wind_clock_of_a_tour_is_the_video_time_past_the_shaders_ease_in() -> None:
    frames = list(tour_frames(TourSpec(HeldCamera(KEYS[0]), 1.0, 30)))
    assert frames[0].wind_time_s == WIND_START_S > 2.0
    assert frames[30 - 1].wind_time_s == pytest.approx(WIND_START_S + 29 / 30)
    still = list(tour_frames(TourSpec(HeldCamera(KEYS[0]), 1.0, 30, wind=False)))
    assert {frame.wind_time_s for frame in still} == {0.0}, "reduced motion: at rest"


def test_a_time_lapse_reaches_both_ends_of_its_ranges() -> None:
    spec = TourSpec(HeldCamera(KEYS[0]), 1.0, 24, date_range=(date(2026, 3, 1), date(2026, 10, 31)),
                    time_range=(time(6, 0), time(21, 30)))
    frames = list(tour_frames(spec))
    assert frames[0].plan_date == date(2026, 3, 1) and frames[-1].plan_date == date(2026, 10, 31)
    assert frames[0].time_of_day == time(6, 0) and frames[-1].time_of_day == time(21, 30)
    days = [frame.plan_date for frame in frames]
    assert days == sorted(days), "the date only moves forward"


def test_a_year_moves_in_steps_a_video_second_can_show() -> None:
    """Each new date regrows every dated plant (#531): at most DATE_STEPS_PER_S of them per
    second, whatever the frame rate — and a short range still shows all its days."""
    spec = TourSpec(HeldCamera(KEYS[0]), 12.0, 60, date_range=(date(2026, 3, 1), date(2026, 10, 31)))
    days = [frame.plan_date for frame in tour_frames(spec)]
    assert len(set(days)) <= 12.0 * DATE_STEPS_PER_S + 1
    assert days[0] == date(2026, 3, 1) and days[-1] == date(2026, 10, 31)
    gaps = {(later - earlier).days for earlier, later in zip(sorted(set(days)), sorted(set(days))[1:],
                                                             strict=False)}
    assert max(gaps) - min(gaps) <= 1, "evenly"
    short = TourSpec(HeldCamera(KEYS[0]), 10.0, 30, date_range=(date(2026, 5, 1), date(2026, 5, 4)))
    assert len({frame.plan_date for frame in tour_frames(short)}) == 4
    one = TourSpec(HeldCamera(KEYS[0]), 1.0, 24, date_range=(date(2026, 5, 1), date(2026, 5, 1)))
    assert {frame.plan_date for frame in tour_frames(one)} == {date(2026, 5, 1)}


def test_the_clock_reaches_its_end_on_a_looped_camera_too() -> None:
    spec = TourSpec(DroneOrbit(POSE), 1.0, 24, time_range=(time(8, 0), time(20, 0)))
    assert list(tour_frames(spec))[-1].time_of_day == time(20, 0)


@pytest.mark.parametrize("bad", [
    {"duration_s": 0.5}, {"duration_s": 601.0}, {"duration_s": float("nan")}, {"fps": 29},
    {"date_range": (date(2026, 5, 2), date(2026, 5, 1))},
    {"time_range": (time(9, 0), time(8, 0))},
])
def test_a_tour_refuses_what_cannot_be_rendered(bad: dict) -> None:
    arguments = {"motion": HeldCamera(KEYS[0]), "duration_s": 5.0} | bad
    with pytest.raises(ValueError):
        TourSpec(**arguments)


def test_the_shortest_tour_still_has_two_frames() -> None:
    assert frame_count(TourSpec(HeldCamera(KEYS[0]), 1.0, 24)) == 24
    assert len(list(tour_frames(TourSpec(HeldCamera(KEYS[0]), 1.0, 24)))) == 24


def test_a_flights_eyes_are_where_its_frames_go() -> None:
    path = CameraPath((CameraKey((0.0, 0.0, 200.0), (0.0, 100.0, 0.0)),
                       CameraKey((1000.0, 0.0, 200.0), (1000.0, 100.0, 0.0))))
    spec = TourSpec(path, 5.0, 30)
    eyes = path_eyes(spec)
    assert len(eyes) == 5 * EYE_SAMPLES_PER_S + 1
    assert eyes[0] == pytest.approx((0.0, 0.0, 200.0)) and eyes[-1] == pytest.approx((1000.0, 0.0, 200.0))
    frames = list(tour_frames(spec))
    assert frames[0].key.eye == pytest.approx(eyes[0]) and frames[-1].key.eye == pytest.approx(eyes[-1])


def test_a_held_camera_has_one_place_to_be() -> None:
    key = CameraKey((0.0, 0.0, 200.0), (0.0, 100.0, 0.0))
    assert set(path_eyes(TourSpec(HeldCamera(key), 2.0, 30))) == {key.eye}


def test_a_closed_flight_samples_all_the_way_round() -> None:
    pose = CameraPose((0.0, 0.0), 1000.0, 0.0, 30.0)
    eyes = path_eyes(TourSpec(DroneOrbit(pose), 4.0, 30))
    east = [eye[0] for eye in eyes]
    north = [eye[1] for eye in eyes]
    assert min(east) < -500.0 < 500.0 < max(east) and min(north) < -500.0 < 500.0 < max(north)
