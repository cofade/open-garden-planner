"""Camera tours as the plan file keeps them (issue #737, ADR-072 addendum).

The model and its one reader, Qt-free: what is written, that reading it back gives the
same tour, what a file may NOT do to the load (the trust boundary, architecture contract
invariant 14), and the three commands' undo contract. End to end through the dialog and a
real plan file: ``tests/integration/test_tour_persistence.py``.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date, time
from typing import Any

import pytest

from open_garden_planner.core.camera_path import (
    MAX_DURATION_S,
    MIN_DURATION_S,
    CameraKey,
    CameraPath,
    DroneOrbit,
    tour_frames,
)
from open_garden_planner.core.camera_tours import (
    DEFAULT_DURATION_S,
    DEFAULT_ORBIT_PITCH_DEG,
    DEFAULT_SIZE,
    MAX_NAME_LENGTH,
    MAX_REACH_CM,
    MAX_TOUR_KEYS,
    MAX_TOURS,
    ORBIT_SECONDS_PER_TURN,
    PLAN_KEY,
    SavedTour,
    checked_tours,
    clean_tour_name,
    default_duration_s,
    dump_tours,
    find_tour,
    load_tours,
)
from open_garden_planner.core.commands import (
    CommandManager,
    DeleteCameraTourCommand,
    RenameCameraTourCommand,
    SaveCameraTourCommand,
)
from open_garden_planner.core.plan_io import PlanValidationError, validate_plan_data
from open_garden_planner.core.project import FILE_VERSION, ProjectData, ProjectManager
from open_garden_planner.core.scene3d.camera import CameraPose
from open_garden_planner.core.templates import template_plan

KEYS = (
    CameraKey((0.0, -900.0, 350.0), (400.0, 300.0, 0.0), 40.0),
    CameraKey((1200.5, -200.25, 180.0), (400.0, 300.0, 60.0), 35.0),
    CameraKey((900.0, 1100.0, 420.125), (380.0, 310.0, 0.0), 40.0),
)
ORBIT = DroneOrbit(CameraPose((400.0, 300.0), 2150.75, 33.5, 28.25), 40.0, 2.0, False)


def flight(name: str = "Promo Flight", **changes: Any) -> SavedTour:
    return replace(SavedTour(name, "path", keys=KEYS), **changes)


def orbit(name: str = "Drone", **changes: Any) -> SavedTour:
    return replace(SavedTour(name, "orbit", orbit=ORBIT), **changes)


def held(name: str = "Time-lapse", **changes: Any) -> SavedTour:
    return replace(SavedTour(name, "hold", held=KEYS[0]), **changes)


def through_json(value: Any) -> Any:
    """What a plan file does to it: JSON text and back."""
    return json.loads(json.dumps(value, allow_nan=False))


EVERY_KIND = [
    pytest.param(flight(), id="path"),
    pytest.param(flight(closed=True, keys=KEYS[:2]), id="path-two-keys-closed"),
    pytest.param(flight(date_range=(date(2026, 3, 1), date(2026, 10, 31)), duration_s=45.5,
                        fps=60, size=(3840, 2160)), id="path-year-4k"),
    pytest.param(orbit(), id="orbit"),
    pytest.param(orbit(orbit=replace(ORBIT, ease=True)), id="orbit-eased"),
    pytest.param(orbit(keys=KEYS), id="orbit-that-keeps-its-keys"),
    pytest.param(held(time_range=(time(6, 0), time(21, 30))), id="hold-day"),
    pytest.param(held(), id="hold"),
]


# ── the model ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tour", EVERY_KIND)
def test_a_tour_read_back_from_the_file_is_the_same_tour(tour: SavedTour) -> None:
    assert SavedTour.from_dict(through_json(tour.to_dict())) == tour


@pytest.mark.parametrize("tour", EVERY_KIND)
def test_a_tour_read_back_flies_the_same_frames(tour: SavedTour) -> None:
    """Not "about the same": JSON keeps a float exactly, so every frame's camera, date and
    time is equal."""
    again = SavedTour.from_dict(through_json(tour.to_dict()))
    assert list(tour_frames(again.spec())) == list(tour_frames(tour.spec()))


@pytest.mark.parametrize("tours", [(), (flight(),), (flight(), orbit(), held(), flight("Second"))],
                         ids=["none", "one", "many"])
def test_a_list_of_tours_round_trips_in_its_order(tours: tuple[SavedTour, ...]) -> None:
    assert load_tours(through_json(dump_tours(tours))) == (tours, 0)


def test_unset_optionals_are_not_written_and_read_back_as_unset() -> None:
    written = held().to_dict()
    assert set(written) == {"name", "motion", "held", "duration_s", "fps", "size"}
    assert set(flight().to_dict()) == {"name", "motion", "keys", "duration_s", "fps", "size"}
    assert set(orbit().to_dict()) == {"name", "motion", "orbit", "duration_s", "fps", "size"}
    again = SavedTour.from_dict(through_json(written))
    assert (again.keys, again.closed, again.orbit, again.date_range, again.time_range) == (
        (), False, None, None, None)


def test_the_least_a_file_must_say_and_the_defaults_for_the_rest() -> None:
    tour = SavedTour.from_dict({"name": "Bare", "motion": "hold", "held": {
        "eye": [0, 0, 170], "target": [0, 500, 100]}})
    assert (tour.duration_s, tour.fps, tour.size) == (DEFAULT_DURATION_S, 30, DEFAULT_SIZE)
    assert tour.held == CameraKey((0.0, 0.0, 170.0), (0.0, 500.0, 100.0), 40.0)


#: An orbit exactly as a plan saved before #807 holds it (ADR-072 addendum's example).
ORBIT_BEFORE_EASING = {
    "name": "Drone", "motion": "orbit",
    "orbit": {"target": [1200.0, 800.0], "distance_cm": 2150.75, "yaw_deg": 33.5,
              "pitch_deg": 28.25, "fov_deg": 40.0, "turns": 2, "clockwise": False},
    "duration_s": 12.0, "fps": 30, "size": [1920, 1080],
}


def test_an_orbit_saved_before_easing_flies_its_old_frames_and_is_written_back_unchanged() -> None:
    """#807: easing is a new field of an orbit, absent in every older file. Absent is no
    easing: the old file's orbit loops at one speed, frame for frame what it flew before,
    and saving it again writes the very same entry."""
    tour = SavedTour.from_dict(through_json(ORBIT_BEFORE_EASING))
    assert tour.orbit is not None and tour.orbit.ease is False and tour.orbit.closed
    assert tour.to_dict() == ORBIT_BEFORE_EASING
    pose = tour.orbit.pose
    frames = list(tour_frames(tour.spec()))
    assert len(frames) == 360
    for frame in frames:   # the orbit's formula before #807: yaw + sign x 360 x turns x i / n
        yaw = pose.yaw_deg + -1.0 * 360.0 * 2.0 * (frame.index / len(frames))
        at = CameraPose(pose.target, pose.distance_cm, yaw, pose.pitch_deg)
        assert frame.key == CameraKey(at.eye, at.target_scene, 40.0)


def test_an_eased_orbit_is_written_with_its_one_new_field() -> None:
    eased = orbit(orbit=replace(ORBIT, ease=True)).to_dict()
    plain = orbit().to_dict()
    assert eased["orbit"] == {**plain["orbit"], "ease": True}
    assert {key: value for key, value in eased.items() if key != "orbit"} == {
        key: value for key, value in plain.items() if key != "orbit"}


@pytest.mark.parametrize("value", ["true", 1, None, [], {"on": True}, 1.0])
def test_only_a_true_ease_eases_and_the_tour_is_kept(value: Any) -> None:
    """A setting, like ``closed``: anything but JSON's true is the old even orbit."""
    raw = through_json(ORBIT_BEFORE_EASING)
    raw["orbit"]["ease"] = value
    tour = SavedTour.from_dict(raw)
    assert tour.orbit is not None and tour.orbit.ease is False


@pytest.mark.parametrize(("motion", "turns", "clock", "seconds"), [
    ("orbit", 1, "none", 30.0), ("orbit", 4, "none", 120.0),
    ("orbit", 1, "day", DEFAULT_DURATION_S), ("orbit", 2, "year", DEFAULT_DURATION_S),
    ("path", 1, "none", DEFAULT_DURATION_S), ("hold", 3, "year", DEFAULT_DURATION_S),
])
def test_a_new_tour_lasts_thirty_seconds_a_turn_when_it_only_orbits(motion: str, turns: int,
                                                                      clock: str, seconds: float) -> None:
    """#807: 12 s a turn is 1 degree a frame at 30 fps, and the horizon a lower tilt brings
    into view crossed the frame in 2.2 s. A time-lapse keeps 12 s: a year's regrowths cost
    a second and 2 MB each (#531), eight for each second of video."""
    assert default_duration_s(motion, turns, clock) == seconds
    assert ORBIT_SECONDS_PER_TURN == 30.0 and MIN_DURATION_S <= 4 * 30.0 <= MAX_DURATION_S


def test_a_new_orbits_tilt_is_in_the_range_an_orbit_may_have() -> None:
    from open_garden_planner.core.camera_path import orbit_pitch_range

    low, high = orbit_pitch_range(3000.0)
    assert low < DEFAULT_ORBIT_PITCH_DEG == 18.0 < high


def test_a_field_this_build_does_not_know_is_left_out_and_the_tour_is_kept() -> None:
    raw = {**flight().to_dict(), "lens_flare": {"strength": 3}, "comment": "from a later build"}
    tour = SavedTour.from_dict(through_json(raw))
    assert tour == flight() and "lens_flare" not in tour.to_dict()


def test_a_saved_tour_can_always_be_rendered() -> None:
    """The invariant the dialog and the loader rest on: what is a ``SavedTour`` has a spec."""
    with pytest.raises(ValueError, match="two different keys"):
        SavedTour("One key", "path", keys=KEYS[:1])
    with pytest.raises(ValueError, match="two different keys"):
        SavedTour("Same key twice", "path", keys=(KEYS[0], KEYS[0]))
    with pytest.raises(ValueError, match="orbit"):
        SavedTour("No orbit", "orbit")
    with pytest.raises(ValueError, match="view"):
        SavedTour("No view", "hold")
    with pytest.raises(ValueError, match="not both"):
        flight(date_range=(date(2026, 1, 1), date(2026, 2, 1)), time_range=(time(6), time(7)))
    with pytest.raises(ValueError, match="backwards"):
        flight(date_range=(date(2026, 2, 1), date(2026, 1, 1)))
    with pytest.raises(ValueError):
        flight(duration_s=0.0)
    with pytest.raises(ValueError):
        flight(fps=31)
    with pytest.raises(ValueError):
        flight(size=(640, 360))
    with pytest.raises(ValueError):
        flight(keys=KEYS * 40)   # 120 keys
    with pytest.raises(ValueError):
        flight(keys=list(KEYS))  # a list is no snapshot: the tour must stay what it was
    with pytest.raises(ValueError):
        flight(size=[1920, 1080])
    for turns in (0.5, 2.5, 5.0, -1.0):   # what the file could not say again
        with pytest.raises(ValueError, match="whole turns"):
            orbit(orbit=replace(ORBIT, turns=turns))


def test_the_path_rule_is_the_camera_paths_own() -> None:
    """One rule for "can these keys be flown" (``camera_path.distinct_keys``): what the
    model takes, ``CameraPath`` builds, and the other way round."""
    for keys, closed in (((KEYS[0], KEYS[1], KEYS[1]), False), ((KEYS[0], KEYS[1], KEYS[0]), True)):
        assert CameraPath(keys, closed=closed).keys == SavedTour(
            "Tour", "path", keys=keys, closed=closed).camera_motion().keys  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        CameraPath((KEYS[0], KEYS[0]), closed=True)
    with pytest.raises(ValueError):
        SavedTour("Tour", "path", keys=(KEYS[0], KEYS[0]), closed=True)


@pytest.mark.parametrize(("typed", "kept"), [
    ("  Promo   flight \n", "Promo flight"),
    ("Tab\tand\r\nbreak", "Tab and break"),
    ("bell\x07 and \u202eoverride", "bell and override"),
    ("x" * 200, "x" * MAX_NAME_LENGTH),
    ("   ", ""),
    ("\x00\x01", ""),
    (None, ""),
    (42, ""),
], ids=["blanks", "line-breaks", "controls", "too-long", "only-blanks", "only-controls", "none",
        "a-number"])
def test_a_name_is_one_clean_line(typed: Any, kept: str) -> None:
    assert clean_tour_name(typed) == kept


def test_names_are_one_name_whatever_their_case() -> None:
    tours = (flight("Promo"), orbit("Drone"))
    assert find_tour(tours, "PROMO") is tours[0] and find_tour(tours, "promo ") is None
    with pytest.raises(ValueError, match="same name"):
        checked_tours((flight("Promo"), orbit("promo")))
    with pytest.raises(ValueError, match="at most"):
        checked_tours(flight(f"Tour {number}") for number in range(MAX_TOURS + 1))
    with pytest.raises(TypeError):
        checked_tours([flight().to_dict()])  # type: ignore[list-item]


# ── settings are put back into their range ───────────────────────────────────


@pytest.mark.parametrize(("field", "written", "read"), [
    ("duration_s", 0.01, MIN_DURATION_S),
    ("duration_s", 1e9, MAX_DURATION_S),
    ("duration_s", -5, MIN_DURATION_S),
    ("duration_s", "12", DEFAULT_DURATION_S),
    ("duration_s", None, DEFAULT_DURATION_S),
    ("duration_s", True, DEFAULT_DURATION_S),
    ("duration_s", 10**400, MAX_DURATION_S),
    ("fps", 31, 30),
    ("fps", 30.0, 30),
    ("fps", "60", 30),
    ("fps", True, 30),
    ("size", [640, 360], DEFAULT_SIZE),
    ("size", [1920.0, 1080.0], DEFAULT_SIZE),
    ("size", [3840, 2160, 1], DEFAULT_SIZE),
    ("size", "4k", DEFAULT_SIZE),
    ("size", [10**9, 10**9], DEFAULT_SIZE),
    ("closed", "yes", False),
    ("closed", 1, False),
])
def test_a_setting_outside_its_range_is_put_back_and_the_tour_is_kept(
        field: str, written: Any, read: Any) -> None:
    tour = SavedTour.from_dict({**flight().to_dict(), field: written})
    assert getattr(tour, field) == read and tour.keys == KEYS


def test_a_duration_that_is_not_finite_is_the_default() -> None:
    """A plan file cannot say NaN (``plan_io`` refuses the document); the reader does not
    rely on that."""
    for value in (math.nan, math.inf, -math.inf):
        assert SavedTour.from_dict({**flight().to_dict(), "duration_s": value}).duration_s == (
            DEFAULT_DURATION_S)


@pytest.mark.parametrize(("turns", "read"), [(0, 1.0), (-3, 1.0), (2.4, 2.0), (99, 4.0)])
def test_an_orbits_turns_are_the_whole_turns_the_dialog_offers(turns: Any, read: float) -> None:
    raw = orbit().to_dict()
    raw["orbit"]["turns"] = turns
    assert SavedTour.from_dict(raw).orbit.turns == read  # type: ignore[union-attr]


# ── the trust boundary ───────────────────────────────────────────────────────


def _with(base: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """``base`` with the value at a dotted path replaced (``keys.1.eye.2``)."""
    copy = through_json(base)
    node = copy
    *parents, last = path.split(".")
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return copy


FLIGHT, DRONE, HELD = flight().to_dict(), orbit().to_dict(), held().to_dict()
DEEP: Any = []
for _level in range(400):
    DEEP = [DEEP]

HOSTILE = {
    # structural: the wrong type or shape where a tour, a key or a number belongs
    "not-an-object": 42,
    "a-list": [FLIGHT],
    "a-text": "tour",
    "null": None,
    "nested-400-deep": DEEP,
    "empty-object": {},
    "name-missing": {key: value for key, value in FLIGHT.items() if key != "name"},
    "name-a-number": _with(FLIGHT, "name", 7),
    "name-only-controls": _with(FLIGHT, "name", "\x00\x1b"),
    "name-an-object": _with(FLIGHT, "name", {"a": 1}),
    "motion-unknown": _with(FLIGHT, "motion", "teleport"),
    "motion-a-list": _with(FLIGHT, "motion", ["path"]),
    "keys-a-text": _with(FLIGHT, "keys", "all of them"),
    "keys-an-object": _with(FLIGHT, "keys", {"0": FLIGHT["keys"][0]}),
    "key-a-number": _with(FLIGHT, "keys.1", 5),
    "key-without-an-eye": _with(FLIGHT, "keys.1", {"target": [0, 0, 0]}),
    "eye-two-numbers": _with(FLIGHT, "keys.0.eye", [1, 2]),
    "eye-a-text": _with(FLIGHT, "keys.0.eye", "1,2,3"),
    "coordinate-a-text-number": _with(FLIGHT, "keys.0.eye.0", "100"),
    "coordinate-a-bool": _with(FLIGHT, "keys.0.eye.0", True),
    "coordinate-null": _with(FLIGHT, "keys.0.target.2", None),
    "orbit-missing": {key: value for key, value in DRONE.items() if key != "orbit"},
    "orbit-a-list": _with(DRONE, "orbit", [1, 2, 3]),
    "orbit-target-three-numbers": _with(DRONE, "orbit.target", [1, 2, 3]),
    "held-missing": {key: value for key, value in HELD.items() if key != "held"},
    "date-range-a-number": {**FLIGHT, "date_range": 20260301},
    "date-range-one-day": {**FLIGHT, "date_range": ["2026-03-01"]},
    "date-range-no-dates": {**FLIGHT, "date_range": ["spring", "autumn"]},
    "date-range-numbers": {**FLIGHT, "date_range": [1, 2]},
    "date-range-a-megabyte": {**FLIGHT, "date_range": ["2026-03-01" + " " * 1_000_000, "x"]},
    "time-range-no-times": {**FLIGHT, "time_range": ["25:00", "26:00"]},
    # arithmetic: numbers that are numbers and cannot be a camera
    "coordinate-nan": _with(FLIGHT, "keys.0.eye.0", math.nan),
    "coordinate-inf": _with(FLIGHT, "keys.2.target.1", math.inf),
    "coordinate-beyond-the-reach": _with(FLIGHT, "keys.0.eye.2", MAX_REACH_CM * 10),
    "coordinate-1e308": _with(FLIGHT, "keys.0.eye.0", 1e308),
    "coordinate-an-integer-no-float-holds": _with(FLIGHT, "keys.0.eye.0", 10**400),
    "fov-zero": _with(FLIGHT, "keys.0.fov_deg", 0),
    "fov-180": _with(FLIGHT, "keys.0.fov_deg", 180),
    "fov-negative": _with(FLIGHT, "keys.0.fov_deg", -40),
    "fov-nan": _with(FLIGHT, "keys.0.fov_deg", math.nan),
    "eye-on-its-target": _with(FLIGHT, "keys.0.eye", FLIGHT["keys"][0]["target"]),
    "one-key": _with(FLIGHT, "keys", FLIGHT["keys"][:1]),
    "the-same-key-three-times": _with(FLIGHT, "keys", [FLIGHT["keys"][0]] * 3),
    "orbit-distance-zero": _with(DRONE, "orbit.distance_cm", 0),
    "orbit-distance-negative": _with(DRONE, "orbit.distance_cm", -500),
    "orbit-distance-inf": _with(DRONE, "orbit.distance_cm", math.inf),
    "orbit-pitch-200": _with(DRONE, "orbit.pitch_deg", 200),
    "orbit-yaw-nan": _with(DRONE, "orbit.yaw_deg", math.nan),
    "orbit-turns-nan": _with(DRONE, "orbit.turns", math.nan),
    "date-range-backwards": {**FLIGHT, "date_range": ["2026-10-31", "2026-03-01"]},
    "time-range-backwards": {**FLIGHT, "time_range": ["21:00", "06:00"]},
    "both-ranges": {**FLIGHT, "date_range": ["2026-03-01", "2026-10-31"],
                    "time_range": ["06:00", "21:00"]},
    # resource: more than a person sets up
    "a-hundred-thousand-keys": _with(FLIGHT, "keys", FLIGHT["keys"] * 34_000),
    "one-key-too-many": _with(FLIGHT, "keys", (FLIGHT["keys"] * 34)[:MAX_TOUR_KEYS + 1]),
}


@pytest.mark.parametrize("entry", HOSTILE.values(), ids=HOSTILE.keys())
def test_what_is_not_a_tour_is_skipped_and_the_tours_around_it_are_kept(entry: Any) -> None:
    tours, skipped = load_tours([FLIGHT, entry, DRONE])
    assert tours == (flight(), orbit()) and skipped == 1


@pytest.mark.parametrize("family", [KeyError, AttributeError, TypeError, RecursionError,
                                    ZeroDivisionError, OverflowError, UnicodeError, RuntimeError])
def test_no_family_of_error_in_an_entry_reaches_the_load(
        monkeypatch: pytest.MonkeyPatch, family: type[Exception]) -> None:
    """Invariant 14 by construction, not by a list of the errors seen so far: whatever
    reading one entry raises, that entry is skipped and the others are read."""
    read = SavedTour.from_dict.__func__  # type: ignore[attr-defined]

    def poisoned(cls: type[SavedTour], raw: Any) -> SavedTour:
        if isinstance(raw, dict) and raw.get("name") == "Poison":
            raise family("from somewhere inside the reader")
        return read(cls, raw)  # type: ignore[no-any-return]

    monkeypatch.setattr(SavedTour, "from_dict", classmethod(poisoned))
    tours, skipped = load_tours([FLIGHT, {**HELD, "name": "Poison"}, DRONE])
    assert tours == (flight(), orbit()) and skipped == 1


@pytest.mark.parametrize("raw", [42, "tours", {"0": FLIGHT}, True, 3.5, FLIGHT],
                         ids=["number", "text", "object", "bool", "float", "one-tour-bare"])
def test_a_key_that_is_no_list_gives_no_tours_and_no_error(raw: Any) -> None:
    assert load_tours(raw) == ((), 1)


@pytest.mark.parametrize("raw", [None, []], ids=["absent", "empty"])
def test_no_tours_is_not_a_skipped_tour(raw: Any) -> None:
    assert load_tours(raw) == ((), 0)


def test_a_name_twice_keeps_the_first_and_too_many_keeps_the_first_fifty() -> None:
    tours, skipped = load_tours([FLIGHT, {**DRONE, "name": "PROMO FLIGHT"}, HELD])
    assert [tour.name for tour in tours] == ["Promo Flight", "Time-lapse"] and skipped == 1
    many = [{**HELD, "name": f"Tour {number}"} for number in range(MAX_TOURS + 25)]
    tours, skipped = load_tours(many)
    assert len(tours) == MAX_TOURS and skipped == 25
    assert tours[-1].name == f"Tour {MAX_TOURS - 1}"


def test_a_million_entries_cost_what_fifty_cost() -> None:
    """Resource cap: the reader stops when the plan is full, however long the list is."""
    tours, skipped = load_tours([HELD | {"name": f"T{number}"} for number in range(60)]
                                + [None] * 1_000_000)
    assert len(tours) == MAX_TOURS and skipped == 1_000_010


def test_a_hostile_name_is_cleaned_not_trusted() -> None:
    tour = SavedTour.from_dict({**FLIGHT, "name": "<img src='file:///c:/x'>\nERROR forged line"})
    assert tour.name == "<img src='file:///c:/x'> ERROR forged line"   # one line; shown as text
    assert "\n" not in tour.name and len(tour.name) <= MAX_NAME_LENGTH


# ── the plan file ────────────────────────────────────────────────────────────


def plan_with(tours: Any) -> dict[str, Any]:
    data = ProjectData().to_dict()
    data[PLAN_KEY] = tours
    return data


def test_a_plan_without_tours_writes_no_key_and_reads_as_none() -> None:
    assert PLAN_KEY not in ProjectData().to_dict()
    assert ProjectData.from_dict(ProjectData().to_dict()).camera_tours == []
    assert ProjectData.from_dict({}).camera_tours == []


def test_the_tours_are_one_additive_top_level_key_and_the_version_stays() -> None:
    """Row 9 of the architecture contract: additive, so no ``FILE_VERSION`` change. The
    literal is the point: a bump must fail here and be decided, not slip through."""
    without = ProjectData().to_dict()
    with_tours = ProjectData(camera_tours=dump_tours((flight(), orbit()))).to_dict()
    assert FILE_VERSION == "1.4" and with_tours["version"] == "1.4"
    assert set(with_tours) - set(without) == {"camera_tours"} == {PLAN_KEY}
    assert all(with_tours[key] == without[key] for key in without if key != "metadata")
    assert ProjectData.from_dict(through_json(with_tours)).camera_tours == dump_tours(
        (flight(), orbit()))


def test_the_plan_validator_takes_tours_and_refuses_a_non_finite_number_in_one() -> None:
    """``plan_io`` is the document's numeric boundary (AUD-041): a NaN anywhere refuses the
    WHOLE document, in a tour like anywhere else. That policy is older than tours and is
    pinned here so that nobody relaxes it for them by accident."""
    validate_plan_data(plan_with(dump_tours((flight(), orbit(), held()))))
    with pytest.raises(PlanValidationError):
        validate_plan_data(plan_with([HOSTILE["coordinate-nan"]]))
    with pytest.raises(PlanValidationError):
        validate_plan_data(plan_with([HOSTILE["orbit-distance-inf"]]))


def test_a_template_keeps_the_tours_with_the_geometry_they_fly_through() -> None:
    plan = plan_with(dump_tours((flight(),)))
    assert template_plan(plan)[PLAN_KEY] == dump_tours((flight(),))


# ── the project manager and the undo contract ────────────────────────────────


@pytest.fixture()
def plan(qtbot: Any) -> tuple[ProjectManager, CommandManager, list[tuple[SavedTour, ...]]]:
    """A project manager wired to an undo stack the way the app wires it."""
    manager, commands = ProjectManager(), CommandManager()
    commands.stack_changed.connect(manager.mark_dirty)
    seen: list[tuple[SavedTour, ...]] = []
    manager.camera_tours_changed.connect(seen.append)
    return manager, commands, seen


def test_the_manager_keeps_what_it_is_given_says_so_and_is_dirty(plan: Any) -> None:
    manager, _commands, seen = plan
    assert manager.camera_tours == () and not manager.is_dirty
    manager.set_camera_tours([flight(), orbit()])
    assert manager.camera_tours == (flight(), orbit()) == seen[-1] and manager.is_dirty
    with pytest.raises(ValueError):
        manager.set_camera_tours([flight("A"), orbit("a")])
    assert manager.camera_tours == (flight(), orbit()), "a refused list changes nothing"


def test_a_new_project_has_no_tours(plan: Any) -> None:
    manager, _commands, seen = plan
    manager.set_camera_tours([flight()])
    manager.new_project()
    assert manager.camera_tours == () == seen[-1] and not manager.is_dirty


def test_adding_a_tour_is_one_undo_step(plan: Any) -> None:
    manager, commands, _seen = plan
    commands.execute(SaveCameraTourCommand(manager, flight()))
    assert commands.undo_depth == 1 and manager.camera_tours == (flight(),)
    assert commands.undo_description == "Save camera tour"
    commands.execute(SaveCameraTourCommand(manager, orbit()))
    assert commands.undo_depth == 2 and manager.camera_tours == (flight(), orbit())
    commands.undo()
    assert manager.camera_tours == (flight(),) and commands.undo_depth == 1
    commands.undo()
    assert manager.camera_tours == () and commands.undo_depth == 0
    commands.redo()
    commands.redo()
    assert manager.camera_tours == (flight(), orbit()) and commands.redo_depth == 0


def test_changing_a_tour_is_one_undo_step_and_keeps_its_place(plan: Any) -> None:
    manager, commands, _seen = plan
    manager.set_camera_tours([flight(), orbit(), held()])
    before = manager.camera_tours
    longer = orbit(duration_s=40.0, keys=KEYS[:2])
    commands.execute(SaveCameraTourCommand(manager, longer))
    assert commands.undo_depth == 1 and manager.camera_tours == (flight(), longer, held())
    commands.undo()
    assert manager.camera_tours == before and manager.camera_tours[1] is before[1]
    commands.redo()
    assert manager.camera_tours == (flight(), longer, held())


def test_a_tour_saved_under_a_name_in_another_case_replaces_that_tour(plan: Any) -> None:
    manager, commands, _seen = plan
    manager.set_camera_tours([flight("Promo"), orbit()])
    commands.execute(SaveCameraTourCommand(manager, held("PROMO")))
    assert manager.camera_tours == (held("PROMO"), orbit()) and commands.undo_depth == 1


def test_renaming_a_tour_is_one_undo_step(plan: Any) -> None:
    manager, commands, _seen = plan
    manager.set_camera_tours([flight(), orbit()])
    before = manager.camera_tours
    commands.execute(RenameCameraTourCommand(manager, "drone", "Around the House"))
    assert commands.undo_depth == 1 and commands.undo_description == "Rename camera tour"
    assert manager.camera_tours == (flight(), orbit("Around the House"))
    commands.undo()
    assert manager.camera_tours == before
    commands.redo()
    assert manager.camera_tours == (flight(), orbit("Around the House"))


def test_removing_a_tour_is_one_undo_step_and_undo_puts_it_back_in_its_place(plan: Any) -> None:
    manager, commands, _seen = plan
    manager.set_camera_tours([flight(), orbit(), held()])
    before = manager.camera_tours
    commands.execute(DeleteCameraTourCommand(manager, "Drone"))
    assert commands.undo_depth == 1 and commands.undo_description == "Delete camera tour"
    assert manager.camera_tours == (flight(), held())
    commands.undo()
    assert manager.camera_tours == before, "the same tours in the same order"
    commands.redo()
    assert manager.camera_tours == (flight(), held())


def test_a_command_that_cannot_be_built_leaves_the_stack_and_the_plan_alone(plan: Any) -> None:
    manager, commands, _seen = plan
    manager.set_camera_tours([flight(), orbit()])
    manager.mark_clean()
    with pytest.raises(ValueError):
        RenameCameraTourCommand(manager, "Nobody", "Somebody")
    with pytest.raises(ValueError):
        RenameCameraTourCommand(manager, "Drone", "promo flight")   # taken
    with pytest.raises(ValueError):
        DeleteCameraTourCommand(manager, "Nobody")
    manager.set_camera_tours(held(f"Tour {number}") for number in range(MAX_TOURS))
    manager.mark_clean()
    with pytest.raises(ValueError):
        SaveCameraTourCommand(manager, flight("One too many"))
    assert commands.undo_depth == 0 and not manager.is_dirty
    assert len(manager.camera_tours) == MAX_TOURS


def test_undo_and_redo_mark_the_plan_dirty(plan: Any) -> None:
    manager, commands, _seen = plan
    commands.execute(SaveCameraTourCommand(manager, flight()))
    for step in (commands.undo, commands.redo):
        manager.mark_clean()
        step()
        assert manager.is_dirty


def test_a_tour_command_touches_no_canvas_item() -> None:
    """The two O(items) restack scans are skipped for it (#592, #629)."""
    for command in (SaveCameraTourCommand, RenameCameraTourCommand, DeleteCameraTourCommand):
        assert command.changes_ground_band is False and command.changes_containment is False
