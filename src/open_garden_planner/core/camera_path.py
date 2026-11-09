"""Camera tours as plain data (Phase 17 L6.2, #390, ADR-072). Qt-free.

A tour is three things: how the CAMERA moves (``CameraPath`` through the user's own
keyframes, ``DroneOrbit`` around the plan, or ``HeldCamera``), what the sim clock does
meanwhile (nothing, a day or a stretch of the year) and how long it lasts.
``tour_frames`` turns that into the exact list of frames, so that a video is the same
frames whoever renders it and however long each frame takes: a tour never runs on a
wall clock.

``CameraPath`` is a CENTRIPETAL Catmull-Rom spline (alpha 0.5). The uniform variant
overshoots and can loop between keys of very different spacing, and the camera would
swing through a hedge on the way; the centripetal one cannot form a cusp or a loop
inside a segment (Yuksel et al., 2011). It is travelled at constant speed, measured
along the spline, and an open path eases in and out.

Truth (``ogp-lush-cinematic`` §1): a tour moves the camera and the clock and nothing
else. The sun, the plants and the weather are whatever the plan says at that moment.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray

from .scene3d.camera import CameraPose

__all__ = ["DATE_STEPS_PER_S", "DEFAULT_FPS", "EYE_SAMPLES_PER_S", "FRAME_RATES", "MAX_DURATION_S",
           "MIN_DURATION_S", "MIN_EYE_CM", "WIND_START_S",
           "CameraKey", "CameraMotion", "CameraPath", "DroneOrbit", "HeldCamera", "TourFrame",
           "TourSpec", "distinct_keys", "frame_count", "path_eyes", "tour_frames"]

Point3 = tuple[float, float, float]

#: The frame rates a tour offers.
FRAME_RATES: Final = (24, 25, 30, 50, 60)
DEFAULT_FPS: Final = 30
MIN_DURATION_S: Final = 1.0
MAX_DURATION_S: Final = 600.0
#: A spline may swing below the keys it joins; the eye stays this far above the ground.
MIN_EYE_CM: Final = 20.0
#: The wind's clock at a tour's first frame, seconds. At 0 the wind is at rest and the
#: shaders ease the sway in over two seconds (``Garden.qml``): a tour starts in full wind.
WIND_START_S: Final = 10.0
#: Spline samples per segment for the arc-length table: a few centimetres of error on
#: the longest path a plan can ask for, and nothing a viewer could see as a speed change.
_SAMPLES_PER_SEGMENT: Final = 64
#: The field of view's weight against centimetres in a key's distance: a key that only
#: zooms is a real key (and a change of 1 degree counts like a move of 10 cm).
_FOV_WEIGHT_CM: Final = 10.0
#: A year's time-lapse moves the plan date at most this often per second of video. A new
#: date regrows every dated plant, and each regrowth costs the view its Models: about a
#: second of rendering and 2 MB that #531 never gives back (measured on the small bench
#: plan). Nobody sees a plant grow between two of eight frames a second; a 12 s video is
#: then 96 regrowths and a quarter of the time.
DATE_STEPS_PER_S: Final = 8.0
#: How often per second ``path_eyes`` samples a flight: a plant's detail changes over metres.
EYE_SAMPLES_PER_S: Final = 4.0
_ALPHA: Final = 0.5
_EASE_SHARE: Final = 0.15


def _finite(*values: float) -> bool:
    return all(math.isfinite(value) for value in values)


@dataclass(frozen=True, slots=True)
class CameraKey:
    """A camera placement: ``eye`` looking at ``target`` (scene E, N, up, cm)."""

    eye: Point3
    target: Point3
    fov_deg: float = 40.0

    def __post_init__(self) -> None:
        if (len(self.eye) != 3 or len(self.target) != 3
                or not _finite(*self.eye, *self.target, self.fov_deg)):
            raise ValueError(f"CameraKey needs finite (E, N, up) points, got {self!r}")
        if not 0.0 < self.fov_deg < 180.0:
            raise ValueError(f"CameraKey.fov_deg must be inside (0, 180), got {self.fov_deg!r}")
        if tuple(self.eye) == tuple(self.target):
            raise ValueError("CameraKey: the eye and the target are the same point")


class CameraMotion(Protocol):
    """Where the camera is at ``u`` in 0..1. ``closed``: the last frame must not repeat
    the first one (``tour_frames``)."""

    @property
    def closed(self) -> bool: ...

    def at(self, u: float) -> CameraKey: ...


def _safe_key(eye: NDArray[np.float64], target: NDArray[np.float64], fov: float) -> CameraKey:
    """A key from spline values: the eye above the ground, the target not on the eye."""
    placed = (float(eye[0]), float(eye[1]), max(float(eye[2]), MIN_EYE_CM))
    aim = (float(target[0]), float(target[1]), float(target[2]))
    if math.dist(placed, aim) < 1.0:   # the spline passed through its own target: look ahead
        aim = (aim[0], aim[1] + 1.0, aim[2])
    return CameraKey(placed, aim, min(max(fov, 1.0), 170.0))


def _ease(u: float) -> float:
    """Constant speed with a soft start and stop: the first and last ``_EASE_SHARE`` of
    the time accelerate and brake, linearly in speed (a continuous velocity)."""
    share = _EASE_SHARE
    peak = 1.0 / (1.0 - share)
    if u < share:
        return 0.5 * peak * u * u / share
    if u > 1.0 - share:
        rest = 1.0 - u
        return 1.0 - 0.5 * peak * rest * rest / share
    return peak * (u - share / 2.0)


def distinct_keys(keys: Sequence[CameraKey], *, closed: bool = False) -> tuple[CameraKey, ...]:
    """The keys a path is made of: consecutive identical keys count once, and a closed
    path does not name its first key again at the end. THE one rule for "can these keys
    be flown": ``CameraPath`` builds on it, and a saved tour is checked with it without
    paying for the spline (``core/camera_tours.py``)."""
    kept: list[CameraKey] = []
    for key in keys:
        if not kept or key != kept[-1]:
            kept.append(key)
    if closed and len(kept) > 1 and kept[0] == kept[-1]:
        kept.pop()
    return tuple(kept)


class CameraPath:
    """The spline through two or more keys (module docstring). Immutable once built.

    ``closed=True`` returns to the first key, with no stop there. Consecutive identical
    keys count once. Raises ``ValueError`` below two different keys.
    """

    def __init__(self, keys: Sequence[CameraKey], *, closed: bool = False) -> None:
        kept = distinct_keys(keys, closed=closed)
        if len(kept) < 2:
            raise ValueError("A camera path needs at least two different keys")
        self.keys: Final = kept
        self._closed = bool(closed)
        rows = np.array([(*key.eye, *key.target, key.fov_deg * _FOV_WEIGHT_CM) for key in kept],
                        dtype=np.float64)
        self._controls = self._with_ends(rows)
        gaps = np.linalg.norm(np.diff(self._controls, axis=0), axis=1)
        self._knots = np.concatenate(([0.0], np.cumsum(np.maximum(gaps, 1e-6) ** _ALPHA)))
        self._segments = len(self._controls) - 3
        self._table_t, self._table_s = self._arc_table()

    @property
    def closed(self) -> bool:
        return self._closed

    def _with_ends(self, rows: NDArray[np.float64]) -> NDArray[np.float64]:
        if self._closed:
            return np.vstack((rows[-1], rows, rows[0], rows[1]))
        return np.vstack((2.0 * rows[0] - rows[1], rows, 2.0 * rows[-1] - rows[-2]))

    def _value(self, segment: int, fraction: float) -> NDArray[np.float64]:
        """Barry and Goldman's pyramid over one segment, at ``fraction`` in 0..1."""
        p0, p1, p2, p3 = self._controls[segment:segment + 4]
        t0, t1, t2, t3 = self._knots[segment:segment + 4]
        t = t1 + (t2 - t1) * fraction
        a1 = ((t1 - t) * p0 + (t - t0) * p1) / (t1 - t0)
        a2 = ((t2 - t) * p1 + (t - t1) * p2) / (t2 - t1)
        a3 = ((t3 - t) * p2 + (t - t2) * p3) / (t3 - t2)
        b1 = ((t2 - t) * a1 + (t - t0) * a2) / (t2 - t0)
        b2 = ((t3 - t) * a2 + (t - t1) * a3) / (t3 - t1)
        result: NDArray[np.float64] = ((t2 - t) * b1 + (t - t1) * b2) / (t2 - t1)
        return result

    def _arc_table(self) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """(spline position, share of the whole travel) — the table behind constant speed."""
        steps = _SAMPLES_PER_SEGMENT * self._segments
        positions = np.linspace(0.0, float(self._segments), steps + 1)
        rows = np.array([self._at_position(float(position)) for position in positions])
        lengths = np.linalg.norm(np.diff(rows, axis=0), axis=1)
        travelled = np.concatenate(([0.0], np.cumsum(lengths)))
        return positions, travelled / max(float(travelled[-1]), 1e-9)

    def _at_position(self, position: float) -> NDArray[np.float64]:
        segment = min(int(position), self._segments - 1)
        return self._value(segment, position - segment)

    def at(self, u: float) -> CameraKey:
        """The camera at ``u`` in 0..1 of the path (clamped), at constant speed; an open
        path eases in and out."""
        share = min(max(float(u), 0.0), 1.0)
        if not self._closed:
            share = _ease(share)
        position = float(np.interp(share, self._table_s, self._table_t))
        row = self._at_position(position)
        return _safe_key(row[0:3], row[3:6], float(row[6]) / _FOV_WEIGHT_CM)


@dataclass(frozen=True, slots=True)
class DroneOrbit:
    """Around a point on the ground at one distance and pitch. Starts at ``pose`` (so a
    tour starts where the user framed it) and turns ``turns`` times; the eye comes from
    the orbit camera's own ``CameraPose.eye``, so yaw means what it means in the view."""

    pose: CameraPose
    fov_deg: float = 40.0
    turns: float = 1.0
    clockwise: bool = True

    def __post_init__(self) -> None:
        if not _finite(self.turns) or self.turns == 0.0:
            raise ValueError(f"DroneOrbit.turns must be finite and not 0, got {self.turns!r}")

    @property
    def closed(self) -> bool:
        return float(self.turns).is_integer()

    def at(self, u: float) -> CameraKey:
        share = min(max(float(u), 0.0), 1.0)
        sign = 1.0 if self.clockwise else -1.0
        pose = CameraPose(self.pose.target, self.pose.distance_cm,
                          self.pose.yaw_deg + sign * 360.0 * self.turns * share,
                          self.pose.pitch_deg)
        return CameraKey(pose.eye, pose.target_scene, self.fov_deg)


@dataclass(frozen=True, slots=True)
class HeldCamera:
    """The camera does not move: a time-lapse from one place."""

    key: CameraKey

    @property
    def closed(self) -> bool:
        return False

    def at(self, _u: float) -> CameraKey:
        return self.key


@dataclass(frozen=True, slots=True)
class TourFrame:
    """One frame of a tour: where the camera is, what the clock says (None: leave it)."""

    index: int
    u: float
    key: CameraKey
    plan_date: date | None
    time_of_day: time | None
    wind_time_s: float


@dataclass(frozen=True, slots=True)
class TourSpec:
    """A whole tour. ``date_range``: the plan date sweeps from the first to the second day;
    ``time_range``: the time of day does. Both may be given (a year at a moving hour)."""

    motion: CameraMotion
    duration_s: float
    fps: int = DEFAULT_FPS
    date_range: tuple[date, date] | None = None
    time_range: tuple[time, time] | None = None
    wind: bool = True

    def __post_init__(self) -> None:
        if not _finite(self.duration_s) or not MIN_DURATION_S <= self.duration_s <= MAX_DURATION_S:
            raise ValueError(f"A tour lasts {MIN_DURATION_S:g} to {MAX_DURATION_S:g} s, "
                             f"got {self.duration_s!r}")
        if self.fps not in FRAME_RATES:
            raise ValueError(f"A tour's frame rate is one of {FRAME_RATES}, got {self.fps!r}")
        if self.date_range is not None and self.date_range[1] < self.date_range[0]:
            raise ValueError("A tour's date range must not run backwards")
        if self.time_range is not None and self.time_range[1] < self.time_range[0]:
            raise ValueError("A tour's time range must not run backwards")


def frame_count(spec: TourSpec) -> int:
    """How many frames the tour has: at least two."""
    return max(2, round(spec.duration_s * spec.fps))


def _date_at(span: tuple[date, date], u: float, steps: int) -> date:
    """The day at ``u``, in at most ``steps`` steps from the first day to the last."""
    days = (span[1] - span[0]).days
    if days == 0:
        return span[0]
    steps = min(steps, days)
    return span[0] + timedelta(days=round(days * round(u * steps) / steps))


def _time_at(span: tuple[time, time], u: float) -> time:
    first = span[0].hour * 3600 + span[0].minute * 60 + span[0].second
    last = span[1].hour * 3600 + span[1].minute * 60 + span[1].second
    seconds = round(first + (last - first) * u)
    return time(seconds // 3600, seconds // 60 % 60, seconds % 60)


def path_eyes(spec: TourSpec) -> tuple[Point3, ...]:
    """Where the tour's camera will be, without computing every frame: a plant's detail follows
    the nearest of these during a recording (``ForgeWorker.fly_path``)."""
    last = max(1, math.ceil(spec.duration_s * EYE_SAMPLES_PER_S))
    return tuple(spec.motion.at(index / last).eye for index in range(last + 1))


def tour_frames(spec: TourSpec) -> Iterator[TourFrame]:
    """The tour's frames in order, each computed from its index alone (module docstring).

    A closed motion ends one frame before its start, so a looped video does not stutter;
    the clock's ranges always reach their last value on the last frame."""
    count = frame_count(spec)
    last = count - 1
    closed = spec.motion.closed
    date_steps = max(1, math.ceil(spec.duration_s * DATE_STEPS_PER_S))
    for index in range(count):
        u = index / last
        travel = index / count if closed else u
        yield TourFrame(
            index=index, u=u, key=spec.motion.at(travel),
            plan_date=None if spec.date_range is None else _date_at(spec.date_range, u, date_steps),
            time_of_day=None if spec.time_range is None else _time_at(spec.time_range, u),
            wind_time_s=WIND_START_S + index / spec.fps if spec.wind else 0.0,
        )
