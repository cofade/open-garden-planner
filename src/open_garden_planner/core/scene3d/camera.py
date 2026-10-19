"""The orbit camera of the 3D workspace — pose, clamps, framing, damping (L1.3, ADR-065).

Qt-free, standard library only. The UI layer (``ui/view3d/``) owns ONE
``OrbitCamera`` per main window, forwards mouse, wheel and key input to it, steps
it with a timer while it moves, and hands ``pose.eye`` / ``pose.target_scene`` to
the engine host. Nothing in here knows a scene, a record or a window — which is
what makes the workspace's first rule a property of the code and not of care:

    **Edits never move the camera.** The pose changes through the methods of
    this class and through nothing else, and the workspace calls them for four
    reasons only: user input, the "reset view" action, the first open, and a
    document change.

Frame: the SCENE frame of ``core/scene3d`` (x = East, y = North, z = up, cm).
The camera looks at a point ON THE GROUND (``target``) from ``distance_cm``
away. ``yaw_deg`` is the compass bearing it looks along (0 = north, 90 = east),
``pitch_deg`` how far the view tilts DOWN from the horizontal (90 = straight
down). The house style follows ``core/walk_camera.py``.

Damping: every input moves the GOAL; ``step(dt)`` moves the pose towards it as a
critically damped spring — the fastest approach without overshoot from rest —
integrated EXACTLY, so a stalled timer (one long step) lands where many short
steps would, and nothing depends on the frame rate. Distance is damped in
proportion (its logarithm), so a zoom feels the same near and far and can never
pass through zero. When pose and goal agree to well below a pixel the pose
becomes the goal exactly and ``step`` returns False: the caller stops its timer,
and an idle view costs nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

#: Vertical field of view of the workspace camera (the engine's default shot).
FOV_DEG: Final = 40.0
#: The view never drops to (or under) the horizon and never reaches straight
#: down, where the engine's look-at has no "up" left.
MIN_PITCH_DEG: Final = 5.0
MAX_PITCH_DEG: Final = 89.0
#: Half a metre to 600 m. The engine's far plane is 800 m (``Garden.qml``).
MIN_DISTANCE_CM: Final = 50.0
MAX_DISTANCE_CM: Final = 60_000.0
#: How far beyond the plan's edge the look-at point may be panned.
PAN_MARGIN_CM: Final = 1_000.0
#: A framed plan fills the view up to 1 / FRAME_MARGIN of its half-extent.
FRAME_MARGIN: Final = 1.08
#: Where the shipped Qt 3D view puts its camera: plan centre + this x the plan's
#: diagonal, in ITS engine frame (x east, y up, z = -north) —
#: ``ui/view3d/qt3d_adapter.py::_frame_camera``. The new view opens from the same
#: side, so the two show the same garden the same way round.
SHIPPED_VIEW_OFFSET: Final = (0.55, 0.5, 0.6)
DEFAULT_YAW_DEG: Final = math.degrees(
    math.atan2(-SHIPPED_VIEW_OFFSET[0], SHIPPED_VIEW_OFFSET[2])) % 360.0
DEFAULT_PITCH_DEG: Final = math.degrees(math.atan2(
    SHIPPED_VIEW_OFFSET[1], math.hypot(SHIPPED_VIEW_OFFSET[0], SHIPPED_VIEW_OFFSET[2])))

#: The spring's angular frequency, 1/s. 18 settles any input in about 0.7 s and
#: covers 90 % of the way in about 0.2 s.
STIFFNESS: Final = 18.0
#: Below these distances from the goal — and these speeds — the camera is at rest.
_REST_CM: Final = 0.05
_REST_DEG: Final = 0.01
_REST_LOG: Final = 1e-4
_REST_CM_S: Final = 1.0
_REST_DEG_S: Final = 0.2
_REST_LOG_S: Final = 2e-3
#: A drag at a grazing view would throw the target across the plan: the ground
#: under the cursor moves 1 / sin(pitch) per screen centimetre, capped here.
_MIN_DRAG_SIN: Final = 0.3


def _finite(*values: float) -> bool:
    return all(math.isfinite(value) for value in values)


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


@dataclass(frozen=True, slots=True)
class Bounds:
    """What a framed view must show: the plan rectangle on the ground (scene E, N)
    and how high things stand on it."""

    min_east: float
    min_north: float
    max_east: float
    max_north: float
    height_cm: float = 0.0

    def __post_init__(self) -> None:
        values = (self.min_east, self.min_north, self.max_east, self.max_north, self.height_cm)
        if not _finite(*values):
            raise ValueError(f"Bounds needs finite numbers, got {self!r}")
        if self.min_east > self.max_east or self.min_north > self.max_north:
            raise ValueError(f"Bounds must be ordered (min <= max), got {self!r}")
        if self.height_cm < 0.0:
            raise ValueError(f"Bounds.height_cm must not be negative, got {self.height_cm!r}")

    @classmethod
    def of_plan(cls, width_cm: float, depth_cm: float, height_cm: float = 0.0) -> Bounds:
        """The plan rectangle from scene (0, 0) to (width east, depth north)."""
        return cls(0.0, 0.0, width_cm, depth_cm, height_cm)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.min_east + self.max_east) / 2.0, (self.min_north + self.max_north) / 2.0)


@dataclass(frozen=True, slots=True)
class CameraPose:
    """Where the camera is: plain data (module docstring for the four numbers)."""

    target: tuple[float, float]
    distance_cm: float
    yaw_deg: float
    pitch_deg: float

    def __post_init__(self) -> None:
        if len(self.target) != 2 or not _finite(*self.target, self.distance_cm, self.yaw_deg,
                                               self.pitch_deg):
            raise ValueError(f"CameraPose needs finite numbers, got {self!r}")
        if self.distance_cm <= 0.0:
            raise ValueError(f"CameraPose.distance_cm must be positive, got {self.distance_cm!r}")

    @property
    def target_scene(self) -> tuple[float, float, float]:
        """The point looked at, scene frame (E, N, up) — on the ground."""
        return (self.target[0], self.target[1], 0.0)

    @property
    def eye(self) -> tuple[float, float, float]:
        """Where the camera stands, scene frame (E, N, up)."""
        forward = _forward(self.yaw_deg, self.pitch_deg)
        return (self.target[0] - self.distance_cm * forward[0],
                self.target[1] - self.distance_cm * forward[1],
                -self.distance_cm * forward[2])


def _forward(yaw_deg: float, pitch_deg: float) -> tuple[float, float, float]:
    """Unit vector along the view (scene frame)."""
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    return (math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), -math.sin(pitch))


def _right(yaw_deg: float) -> tuple[float, float, float]:
    """Unit vector to the right of the view — always level."""
    yaw = math.radians(yaw_deg)
    return (math.cos(yaw), -math.sin(yaw), 0.0)


def _up(yaw_deg: float, pitch_deg: float) -> tuple[float, float, float]:
    """Unit vector up the image (scene frame)."""
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    return (math.sin(yaw) * math.sin(pitch), math.cos(yaw) * math.sin(pitch), math.cos(pitch))


def _dot(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def frame_pose(bounds: Bounds, aspect: float, *, fov_deg: float = FOV_DEG,
               yaw_deg: float = DEFAULT_YAW_DEG,
               pitch_deg: float = DEFAULT_PITCH_DEG) -> CameraPose:
    """The pose that shows all of ``bounds`` in a view of ``aspect`` (width / height).

    The target is the middle of the plan; the distance is the smallest at which
    every corner of the box (the rectangle, from the ground up to
    ``bounds.height_cm``) lies inside the view with ``FRAME_MARGIN`` to spare —
    computed corner by corner, not from a bounding sphere, so a long narrow plan
    fills a wide view. Clamped to the camera's distance range.
    """
    if not math.isfinite(aspect) or aspect <= 0.0:
        raise ValueError(f"aspect must be a positive width / height ratio, got {aspect!r}")
    if not 0.0 < fov_deg < 180.0:
        raise ValueError(f"fov_deg must be inside (0, 180), got {fov_deg!r}")
    tan_vertical = math.tan(math.radians(fov_deg) / 2.0)
    tan_horizontal = tan_vertical * aspect
    forward, right, up = _forward(yaw_deg, pitch_deg), _right(yaw_deg), _up(yaw_deg, pitch_deg)
    center = bounds.center
    needed = 0.0
    for east in (bounds.min_east, bounds.max_east):
        for north in (bounds.min_north, bounds.max_north):
            for height in (0.0, bounds.height_cm):
                corner = (east - center[0], north - center[1], height)
                depth = _dot(corner, forward)
                needed = max(needed,
                             abs(_dot(corner, right)) * FRAME_MARGIN / tan_horizontal - depth,
                             abs(_dot(corner, up)) * FRAME_MARGIN / tan_vertical - depth)
    return CameraPose(center, _clamp(needed, MIN_DISTANCE_CM, MAX_DISTANCE_CM), yaw_deg, pitch_deg)


def _nearest_turn(yaw_deg: float, near_deg: float) -> float:
    """The angle that looks the same way as ``yaw_deg`` — a whole number of turns
    away from it — and is nearest to ``near_deg``. No turn at all returns ``yaw_deg``
    itself, bit for bit."""
    return yaw_deg + 360.0 * round((near_deg - yaw_deg) / 360.0)


def _damped(value: float, velocity: float, goal: float, stiffness: float,
            dt: float) -> tuple[float, float]:
    """One exact step of a critically damped spring: x(t) = (a + b t) e^(-w t)."""
    decay = math.exp(-stiffness * dt)
    offset = value - goal
    drift = (velocity + stiffness * offset) * dt
    return goal + (offset + drift) * decay, (velocity - stiffness * drift) * decay


class OrbitCamera:
    """A goal pose, and a pose that follows it (module docstring). Not thread-safe."""

    def __init__(self, pose: CameraPose | None = None, *, stiffness: float = STIFFNESS) -> None:
        if not math.isfinite(stiffness) or stiffness <= 0.0:
            raise ValueError(f"stiffness must be positive, got {stiffness!r}")
        start = pose if pose is not None else CameraPose(
            (0.0, 0.0), 2_000.0, DEFAULT_YAW_DEG, DEFAULT_PITCH_DEG)
        self._stiffness = stiffness
        self._pose = start
        self._goal = start
        self._bounds: Bounds | None = None
        # velocities of: east, north, ln(distance), yaw, pitch
        self._velocity = [0.0, 0.0, 0.0, 0.0, 0.0]
        self._moving = False

    # ── reads ────────────────────────────────────────────────────────────────

    @property
    def pose(self) -> CameraPose:
        """Where the camera IS (what the engine is shown)."""
        return self._pose

    @property
    def goal(self) -> CameraPose:
        """Where the camera is heading."""
        return self._goal

    @property
    def moving(self) -> bool:
        """True while ``step`` still has something to do."""
        return self._moving

    @property
    def bounds(self) -> Bounds | None:
        return self._bounds

    # ── input: each moves the GOAL ───────────────────────────────────────────

    def set_bounds(self, bounds: Bounds | None) -> None:
        """What a later pan is limited to (the plan plus ``PAN_MARGIN_CM``). Moves
        NOTHING by itself — a plan that shrinks under the camera is an edit."""
        self._bounds = bounds

    def orbit(self, yaw_delta_deg: float, pitch_delta_deg: float) -> None:
        """Turn around the target: yaw is free, pitch stays between the limits."""
        goal = self._goal
        self._aim(CameraPose(
            goal.target, goal.distance_cm, goal.yaw_deg + yaw_delta_deg,
            _clamp(goal.pitch_deg + pitch_delta_deg, MIN_PITCH_DEG, MAX_PITCH_DEG)))

    def zoom(self, factor: float) -> None:
        """Multiply the distance (``factor`` < 1 comes closer)."""
        if not math.isfinite(factor) or factor <= 0.0:
            raise ValueError(f"a zoom factor is a positive number, got {factor!r}")
        goal = self._goal
        self._aim(CameraPose(
            goal.target, _clamp(goal.distance_cm * factor, MIN_DISTANCE_CM, MAX_DISTANCE_CM),
            goal.yaw_deg, goal.pitch_deg))

    def pan(self, right_cm: float, forward_cm: float) -> None:
        """Move the target over the ground, relative to the view: to its right and
        away from the camera."""
        goal = self._goal
        right = _right(goal.yaw_deg)
        east = goal.target[0] + right_cm * right[0] + forward_cm * -right[1]
        north = goal.target[1] + right_cm * right[1] + forward_cm * right[0]
        bounds = self._bounds
        if bounds is not None:
            east = _clamp(east, bounds.min_east - PAN_MARGIN_CM, bounds.max_east + PAN_MARGIN_CM)
            north = _clamp(north, bounds.min_north - PAN_MARGIN_CM,
                           bounds.max_north + PAN_MARGIN_CM)
        self._aim(CameraPose((east, north), goal.distance_cm, goal.yaw_deg, goal.pitch_deg))

    def drag_pixels(self, dx_px: float, dy_px: float, *, viewport_height_px: float,
                    fov_deg: float = FOV_DEG) -> None:
        """Pan as a hand on the ground would: the mouse moved ``dx`` px to the right
        and ``dy`` px DOWN the view, and the ground follows it."""
        if viewport_height_px <= 0.0:
            return
        goal = self._goal
        cm_per_px = (2.0 * goal.distance_cm * math.tan(math.radians(fov_deg) / 2.0)
                     / viewport_height_px)
        steepness = max(math.sin(math.radians(goal.pitch_deg)), _MIN_DRAG_SIN)
        self.pan(-dx_px * cm_per_px, dy_px * cm_per_px / steepness)

    def frame(self, bounds: Bounds, aspect: float, *, fov_deg: float = FOV_DEG,
              snap: bool = False) -> None:
        """Head for the pose that shows the whole plan from the default side, and
        take ``bounds`` as the pan limits. ``snap``: be there at once (first open).

        The default side is reached by the SHORTEST turn. Yaw is free while
        orbiting — six turns of the mouse are a yaw of 2,160 degrees more — and
        aiming at the default yaw itself unwound every one of them (measured: from
        2,477.5 degrees back to 317.5, six full spins). The goal is the equivalent
        angle nearest to where the camera is; a snap lands on the default itself."""
        self._bounds = bounds
        goal = frame_pose(bounds, aspect, fov_deg=fov_deg)
        if not snap:
            goal = CameraPose(goal.target, goal.distance_cm,
                              _nearest_turn(goal.yaw_deg, self._pose.yaw_deg), goal.pitch_deg)
        self._aim(goal)
        if snap:
            self.snap()

    def snap(self) -> None:
        """The pose becomes the goal now; the camera is at rest."""
        self._pose = self._goal
        self._velocity = [0.0, 0.0, 0.0, 0.0, 0.0]
        self._moving = False

    # ── time ─────────────────────────────────────────────────────────────────

    def step(self, dt_s: float) -> bool:
        """Advance the pose by ``dt_s`` seconds; True while the camera still moves.

        A step of no time (zero, negative, not a number) moves nothing.
        """
        if not self._moving:
            return False
        if not math.isfinite(dt_s) or dt_s <= 0.0:
            return True
        pose, goal, velocity, stiffness = self._pose, self._goal, self._velocity, self._stiffness
        east, velocity[0] = _damped(pose.target[0], velocity[0], goal.target[0], stiffness, dt_s)
        north, velocity[1] = _damped(pose.target[1], velocity[1], goal.target[1], stiffness, dt_s)
        log_distance, velocity[2] = _damped(
            math.log(pose.distance_cm), velocity[2], math.log(goal.distance_cm), stiffness, dt_s)
        yaw, velocity[3] = _damped(pose.yaw_deg, velocity[3], goal.yaw_deg, stiffness, dt_s)
        pitch, velocity[4] = _damped(pose.pitch_deg, velocity[4], goal.pitch_deg, stiffness, dt_s)
        at_rest = (
            abs(east - goal.target[0]) <= _REST_CM and abs(north - goal.target[1]) <= _REST_CM
            and abs(log_distance - math.log(goal.distance_cm)) <= _REST_LOG
            and abs(yaw - goal.yaw_deg) <= _REST_DEG and abs(pitch - goal.pitch_deg) <= _REST_DEG
            and abs(velocity[0]) <= _REST_CM_S and abs(velocity[1]) <= _REST_CM_S
            and abs(velocity[2]) <= _REST_LOG_S
            and abs(velocity[3]) <= _REST_DEG_S and abs(velocity[4]) <= _REST_DEG_S)
        if at_rest:
            self.snap()
            return False
        self._pose = CameraPose((east, north), math.exp(log_distance), yaw, pitch)
        return True

    # ── internals ────────────────────────────────────────────────────────────

    def _aim(self, goal: CameraPose) -> None:
        if goal == self._goal:
            return  # input that changes nothing wakes nothing
        self._goal = goal
        self._moving = True
