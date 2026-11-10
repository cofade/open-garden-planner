"""Camera tours kept in the plan file (issue #737, ADR-072 addendum). Qt-free.

A saved tour is what the Camera Tour dialog needs to make the same video again next
week: a name, how the camera moves (its keyframes, its orbit or its one held view), what
the clock does meanwhile, how long it lasts, its frame rate and its picture size. It holds
nothing of the garden: rendering it later renders the garden as it is then.

In the ``.ogp`` the tours are the optional top-level list ``camera_tours``. The key is
additive: a build that does not know it opens the file without it (and writes the file
back without it), so ``FILE_VERSION`` does not move.

The plan file is untrusted input. ``load_tours`` is the ONE reader: an entry that is not a
tour this build can render is skipped and counted, a setting outside its range is put back
into it, and nothing here can raise into the load of the rest of the plan. Geometry (a
key, an orbit's pose) is never repaired: a path with one key changed is another video.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time
from typing import Any, Final

from .camera_path import (
    DEFAULT_FPS,
    FRAME_RATES,
    MAX_DURATION_S,
    MIN_DURATION_S,
    CameraKey,
    CameraMotion,
    CameraPath,
    DroneOrbit,
    HeldCamera,
    TourSpec,
    distinct_keys,
)
from .plain_text import REPLACEMENT, log_text, normalise_text
from .scene3d.camera import FOV_DEG, CameraPose

__all__ = ["DEFAULT_DURATION_S", "DEFAULT_SIZE", "MAX_NAME_LENGTH", "MAX_REACH_CM", "MAX_TOURS",
           "MAX_TOUR_KEYS", "MOTIONS", "ORBIT_TURNS", "PLAN_KEY", "TOUR_SIZES", "SavedTour",
           "checked_tours", "clean_tour_name", "dump_tours", "find_tour", "load_tours"]

_LOG: Final = logging.getLogger(__name__)

#: The tours' key in the plan file.
PLAN_KEY: Final = "camera_tours"
#: How a tour's camera moves, as the dialog's combo and the file name it.
MOTIONS: Final = ("orbit", "path", "hold")
#: A tour's sizes: all 16:9 and all HD, because an untagged stream below HD would be
#: played with the wrong colours (``core/video_yuv.py``).
TOUR_SIZES: Final = ((1280, 720), (1920, 1080), (2560, 1440), (3840, 2160))
DEFAULT_SIZE: Final = (1920, 1080)
DEFAULT_DURATION_S: Final = 12.0
#: The whole turns a drone orbit offers.
ORBIT_TURNS: Final = (1, 4)
#: The most tours a plan keeps, and the most keyframes one tour has. Far above what a
#: person sets up by hand; a file that asks for more is not asking for a video.
MAX_TOURS: Final = 50
MAX_TOUR_KEYS: Final = 100
MAX_NAME_LENGTH: Final = 60
#: No camera is further than this from the plan's origin: ten times the largest canvas.
MAX_REACH_CM: Final = 1_000_000.0


def clean_tour_name(text: object) -> str:
    """A tour's name as it is kept: one line, no control characters, at most
    ``MAX_NAME_LENGTH`` characters. Empty when nothing is left."""
    raw = text if isinstance(text, str) else ""
    line = normalise_text(raw[:4 * MAX_NAME_LENGTH + 16]).replace(REPLACEMENT, " ")
    return " ".join(line.split())[:MAX_NAME_LENGTH].rstrip()


def _number(value: Any, what: str, low: float = -MAX_REACH_CM, high: float = MAX_REACH_CM) -> float:
    """A finite number inside ``low..high``. A string is not a number here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} is not a number")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"{what} is too large") from error
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{what} is outside {low:g}..{high:g}")
    return number


def _point(value: Any, what: str, size: int = 3) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{what} is not a point of {size} numbers")
    return tuple(_number(part, what) for part in value)


def _key_from(raw: Any, what: str) -> CameraKey:
    if not isinstance(raw, dict):
        raise ValueError(f"{what} is not a camera key")
    eye = _point(raw.get("eye"), f"{what}.eye")
    target = _point(raw.get("target"), f"{what}.target")
    return CameraKey((eye[0], eye[1], eye[2]), (target[0], target[1], target[2]),
                     _number(raw.get("fov_deg", FOV_DEG), f"{what}.fov_deg", 0.0, 180.0))


def _key_dict(key: CameraKey) -> dict[str, Any]:
    return {"eye": list(key.eye), "target": list(key.target), "fov_deg": key.fov_deg}


def _orbit_from(raw: Any) -> DroneOrbit:
    if not isinstance(raw, dict):
        raise ValueError("orbit is not an orbit")
    target = _point(raw.get("target"), "orbit.target", 2)
    pose = CameraPose((target[0], target[1]),
                      _number(raw.get("distance_cm"), "orbit.distance_cm", 0.0),
                      _number(raw.get("yaw_deg"), "orbit.yaw_deg"),
                      _number(raw.get("pitch_deg"), "orbit.pitch_deg", -90.0, 90.0))
    turns = round(_number(raw.get("turns", 1), "orbit.turns"))
    return DroneOrbit(pose, _number(raw.get("fov_deg", FOV_DEG), "orbit.fov_deg", 0.0, 180.0),
                      float(min(max(turns, ORBIT_TURNS[0]), ORBIT_TURNS[1])),
                      raw.get("clockwise", True) is not False,
                      # #807, additive: an orbit saved before easing existed has no "ease",
                      # and flies the even loop it always flew
                      ease=raw.get("ease") is True)


def _orbit_dict(orbit: DroneOrbit) -> dict[str, Any]:
    pose = orbit.pose
    data: dict[str, Any] = {"target": list(pose.target), "distance_cm": pose.distance_cm,
                            "yaw_deg": pose.yaw_deg, "pitch_deg": pose.pitch_deg,
                            "fov_deg": orbit.fov_deg, "turns": int(orbit.turns),
                            "clockwise": orbit.clockwise}
    if orbit.ease:   # only when set: an even orbit is written as every older build wrote it
        data["ease"] = True
    return data


def _span(raw: Any, what: str, parse: Any) -> tuple[Any, Any]:
    if (not isinstance(raw, (list, tuple)) or len(raw) != 2
            or not all(isinstance(part, str) and len(part) <= 16 for part in raw)):
        raise ValueError(f"{what} is not a pair of texts")
    return (parse(raw[0]), parse(raw[1]))


def _minute(text: str) -> time:
    moment = time.fromisoformat(text)
    return time(moment.hour, moment.minute)   # the dialog sets hours and minutes


def _duration(value: Any) -> float:
    """A setting, so it is put back into its range; what is no number is the default."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_DURATION_S
    try:
        seconds = float(value)
    except OverflowError:
        return MAX_DURATION_S
    if not math.isfinite(seconds):
        return DEFAULT_DURATION_S
    return min(max(seconds, MIN_DURATION_S), MAX_DURATION_S)


#: Stands for a tour's motion while only its settings are checked.
_STILL: Final = HeldCamera(CameraKey((0.0, 0.0, 100.0), (0.0, 100.0, 0.0)))


@dataclass(frozen=True, slots=True)
class SavedTour:
    """One tour of a plan (module docstring). Immutable: a list of them is its own
    undo snapshot.

    ``keys`` are kept whatever the motion is (they are the user's own work); ``orbit``
    is there when the motion is ``"orbit"`` and ``held`` when it is ``"hold"``. At most
    one of the two ranges is set: the dialog offers a day or a stretch of the year.
    A ``SavedTour`` can always be rendered: ``spec()`` never fails."""

    name: str
    motion: str
    keys: tuple[CameraKey, ...] = ()
    closed: bool = False
    orbit: DroneOrbit | None = None
    held: CameraKey | None = None
    date_range: tuple[date, date] | None = None
    time_range: tuple[time, time] | None = None
    duration_s: float = DEFAULT_DURATION_S
    fps: int = DEFAULT_FPS
    size: tuple[int, int] = DEFAULT_SIZE

    def __post_init__(self) -> None:
        if not self.name or self.name != clean_tour_name(self.name):
            raise ValueError(f"A tour needs a clean name, got {self.name!r}")
        if self.motion not in MOTIONS:
            raise ValueError(f"A tour's motion is one of {MOTIONS}, got {self.motion!r}")
        if not isinstance(self.keys, tuple) or len(self.keys) > MAX_TOUR_KEYS:
            raise ValueError(f"A tour has a tuple of at most {MAX_TOUR_KEYS} keys")
        if self.motion == "path" and len(distinct_keys(self.keys, closed=self.closed)) < 2:
            raise ValueError("A keyframe tour needs at least two different keys")
        if self.motion == "orbit" and self.orbit is None:
            raise ValueError("An orbit tour needs its orbit")
        if self.orbit is not None and not (
                float(self.orbit.turns).is_integer()
                and ORBIT_TURNS[0] <= self.orbit.turns <= ORBIT_TURNS[1]):
            raise ValueError(f"An orbit makes {ORBIT_TURNS[0]} to {ORBIT_TURNS[1]} whole turns, "
                             f"got {self.orbit.turns!r}")
        if self.motion == "hold" and self.held is None:
            raise ValueError("A held tour needs its view")
        if self.date_range is not None and self.time_range is not None:
            raise ValueError("A tour sweeps the year or the day, not both")
        if self.size not in TOUR_SIZES:
            raise ValueError(f"A tour's size is one of {TOUR_SIZES}, got {self.size!r}")
        # the duration, the frame rate and the ranges: TourSpec's own rules, without the spline
        TourSpec(_STILL, self.duration_s, self.fps, date_range=self.date_range,
                 time_range=self.time_range)

    def camera_motion(self) -> CameraMotion:
        """How the camera moves. Builds the spline of a keyframe tour: not for a loop."""
        if self.motion == "path":
            return CameraPath(self.keys, closed=self.closed)
        if self.motion == "hold":
            assert self.held is not None
            return HeldCamera(self.held)
        assert self.orbit is not None
        return self.orbit

    def spec(self, *, wind: bool = True) -> TourSpec:
        """The tour as the recorder takes it."""
        return TourSpec(self.camera_motion(), self.duration_s, self.fps,
                        date_range=self.date_range, time_range=self.time_range, wind=wind)

    def to_dict(self) -> dict[str, Any]:
        """The tour as the plan file holds it: only what its motion needs."""
        data: dict[str, Any] = {"name": self.name, "motion": self.motion}
        if self.keys:
            data["keys"] = [_key_dict(key) for key in self.keys]
        if self.closed:
            data["closed"] = True
        if self.orbit is not None:
            data["orbit"] = _orbit_dict(self.orbit)
        if self.held is not None:
            data["held"] = _key_dict(self.held)
        if self.date_range is not None:
            data["date_range"] = [day.isoformat() for day in self.date_range]
        if self.time_range is not None:
            data["time_range"] = [moment.isoformat("minutes") for moment in self.time_range]
        data["duration_s"] = self.duration_s
        data["fps"] = self.fps
        data["size"] = list(self.size)
        return data

    @classmethod
    def from_dict(cls, raw: Any) -> SavedTour:
        """A tour from the plan file. ``ValueError`` (or any other error: the caller is
        ``load_tours``) when it is not one; a setting outside its range is put back in."""
        if not isinstance(raw, dict):
            raise ValueError("a tour is not an object")
        motion = raw.get("motion")
        if not isinstance(motion, str) or motion not in MOTIONS:
            raise ValueError("unknown motion")
        keys_raw = raw.get("keys", [])
        if not isinstance(keys_raw, list) or len(keys_raw) > MAX_TOUR_KEYS:
            raise ValueError("keys is not a list of at most MAX_TOUR_KEYS keys")
        fps = raw.get("fps", DEFAULT_FPS)
        size_raw = raw.get("size")
        size = (tuple(size_raw) if isinstance(size_raw, list) and len(size_raw) == 2
                and all(type(side) is int for side in size_raw) else DEFAULT_SIZE)
        return cls(
            name=clean_tour_name(raw.get("name")),
            motion=motion,
            keys=tuple(_key_from(key, f"keys[{index}]") for index, key in enumerate(keys_raw)),
            closed=raw.get("closed") is True,
            orbit=_orbit_from(raw.get("orbit")) if motion == "orbit" else None,
            held=_key_from(raw.get("held"), "held") if motion == "hold" else None,
            date_range=(_span(raw["date_range"], "date_range", date.fromisoformat)
                        if raw.get("date_range") is not None else None),
            time_range=(_span(raw["time_range"], "time_range", _minute)
                        if raw.get("time_range") is not None else None),
            duration_s=_duration(raw.get("duration_s")),
            fps=fps if type(fps) is int and fps in FRAME_RATES else DEFAULT_FPS,
            size=size if size in TOUR_SIZES else DEFAULT_SIZE,
        )


def find_tour(tours: Iterable[SavedTour], name: str) -> SavedTour | None:
    """The tour of that name. Names are one name whatever their case."""
    wanted = name.casefold()
    return next((tour for tour in tours if tour.name.casefold() == wanted), None)


def checked_tours(tours: Iterable[SavedTour]) -> tuple[SavedTour, ...]:
    """``tours`` as a plan may keep them: at most ``MAX_TOURS``, no name twice.
    ``ValueError`` otherwise: this is the app's own write path, not a file."""
    kept = tuple(tours)
    if not all(isinstance(tour, SavedTour) for tour in kept):
        raise TypeError("A plan's tours are SavedTour objects")
    if len(kept) > MAX_TOURS:
        raise ValueError(f"A plan keeps at most {MAX_TOURS} tours, got {len(kept)}")
    if len({tour.name.casefold() for tour in kept}) != len(kept):
        raise ValueError("Two tours of a plan have the same name")
    return kept


def load_tours(raw: Any) -> tuple[tuple[SavedTour, ...], int]:
    """The tours of a plan file, and how many of its entries were skipped.

    THE trust boundary (module docstring; architecture contract, invariant 14): one
    broad ``except`` per entry, so that no family of error in a hostile entry reaches
    the load of the plan. A second tour of a name is skipped, and so is everything
    after the ``MAX_TOURS``-th tour."""
    if raw is None or raw == []:
        return (), 0
    if not isinstance(raw, list):
        _LOG.warning("Camera tours: the plan's %s is not a list; ignored", PLAN_KEY)
        return (), 1
    kept: list[SavedTour] = []
    names: set[str] = set()
    for index, entry in enumerate(raw):
        if len(kept) >= MAX_TOURS:
            break
        try:
            tour = SavedTour.from_dict(entry)
        except Exception as error:   # untrusted input: skip it, whatever it raises
            _LOG.warning("Camera tours: entry %d is not a tour this build can render (%s: %s)",
                         index, type(error).__name__, log_text(error))
            continue
        if tour.name.casefold() in names:
            _LOG.warning("Camera tours: entry %d repeats the name %s; skipped", index,
                         log_text(tour.name))
            continue
        names.add(tour.name.casefold())
        kept.append(tour)
    skipped = len(raw) - len(kept)
    if skipped:
        _LOG.warning("Camera tours: %d of %d entries were skipped", skipped, len(raw))
    return tuple(kept), skipped


def dump_tours(tours: Iterable[SavedTour]) -> list[dict[str, Any]]:
    """The tours as the plan file holds them."""
    return [tour.to_dict() for tour in tours]
