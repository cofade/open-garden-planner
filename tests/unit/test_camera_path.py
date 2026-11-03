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
    FRAME_RATES,
    MIN_EYE_CM,
    WIND_START_S,
    CameraKey,
    CameraPath,
    DroneOrbit,
    HeldCamera,
    TourSpec,
    frame_count,
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
