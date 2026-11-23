"""The camera tours an example plan ships with, computed from the plan itself.

No view is open when a plan is authored, so the orbit is framed the way the Camera Tour
dialog frames one: the plan rectangle and the highest thing on it, seen from the dialog's
default tilt. Every number is rounded before it is stored: ``--check`` compares the JSON,
and the last bit of a sine differs between platforms.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from open_garden_planner.core.camera_path import CameraKey, DroneOrbit, clamp_orbit_pitch
from open_garden_planner.core.camera_tours import (
    DEFAULT_DURATION_S,
    DEFAULT_ORBIT_PITCH_DEG,
    DEFAULT_SIZE,
    ORBIT_SECONDS_PER_TURN,
    SavedTour,
)
from open_garden_planner.core.scene3d.camera import Bounds, CameraPose, frame_pose
from open_garden_planner.core.solar import scene_azimuth, solar_position
from open_garden_planner.ui.view3d.snapshot import snapshot_records

from .i18n import text

ORBIT = text("Garden orbit", "Rundflug", "Vuelo alrededor del jardín")
#: The camera starts with the sun behind it and to one side, so the first frame is lit
#: from the front and the shadows fall away across the picture.
SUN_BEHIND_DEG = 140.0


def showcase_moment(meta: dict) -> tuple[date, time]:
    """A sidecar's showcase date and UTC time of day."""
    return date.fromisoformat(meta["showcase_date"]), time.fromisoformat(meta["showcase_utc_time"])


def plan_bounds(scene, day: date) -> Bounds:
    """The plan rectangle and the highest thing standing on it on ``day``."""
    top = 0.0
    for record in snapshot_records(scene, day).values():
        if record.height_cm is not None:
            top = max(top, record.transform.base_cm + record.height_cm)
    return Bounds.of_plan(scene.width_cm, scene.height_cm, top)


class Framing:
    """How the plan fits a 16:9 picture: what a plan module is given to build its tours."""

    def __init__(self, scene, manager, meta: dict, *, pitch_deg: float = DEFAULT_ORBIT_PITCH_DEG,
                 sun_offset_deg: float = SUN_BEHIND_DEG, closer: float = 1.0) -> None:
        #: The plan's own orbit: how steeply it looks down (a walled garden needs more
        #: than the dialog's default to be seen over its wall) and where it starts.
        self.pitch_deg, self.sun_offset_deg = float(pitch_deg), float(sun_offset_deg)
        #: ... and how much nearer than "everything in the picture all the way round": the
        #: box that is fitted reaches up to the plan's highest tree at all four corners,
        #: so one tall birch makes a small garden small in its own orbit.
        self.closer = float(closer)
        self.day, self.utc_time = showcase_moment(meta)
        self.bounds = plan_bounds(scene, self.day)
        self.aspect = DEFAULT_SIZE[0] / DEFAULT_SIZE[1]
        location = manager.location or {}
        sun = solar_position(location["latitude"], location["longitude"],
                             datetime.combine(self.day, self.utc_time, tzinfo=UTC))
        #: The sun's bearing at the showcase moment in the plan's own frame.
        self.sun_bearing = scene_azimuth(sun.azimuth_deg, manager.north_angle_deg)

    def pose(self, yaw_deg: float, pitch_deg: float) -> CameraPose:
        """The whole plan seen along ``yaw_deg`` (0 = plan-up), tilted ``pitch_deg`` down."""
        framed = frame_pose(self.bounds, self.aspect, yaw_deg=float(yaw_deg), pitch_deg=float(pitch_deg))
        east, north = framed.target
        return CameraPose((round(east, 1), round(north, 1)), float(round(framed.distance_cm)),
                          round(float(yaw_deg) % 360.0, 1), round(float(pitch_deg), 1))

    def orbit(self) -> CameraPose:
        """Where the orbit starts: far enough to keep the whole plan in the picture all the
        way round, at the plan's own pitch, and turned by the plan's own offset from the
        showcase sun (by default the sun is behind the camera)."""
        distance = max(frame_pose(self.bounds, self.aspect, yaw_deg=float(yaw),
                                  pitch_deg=self.pitch_deg).distance_cm
                       for yaw in range(0, 360, 5))
        east, north = self.bounds.center
        distance *= self.closer
        return CameraPose((round(east, 1), round(north, 1)), float(round(distance)),
                          round((self.sun_bearing + self.sun_offset_deg) % 360.0, 1),
                          round(clamp_orbit_pitch(self.pitch_deg, distance), 1))


def orbit_tour(pose: CameraPose, name: str = ORBIT, *, turns: float = 1.0,
               clockwise: bool = True,
               date_range=None, time_range=None, duration_s: float | None = None) -> SavedTour:
    """One eased part or whole turn around the plan. With a range it is a time-lapse of
    the day or the year, at the length the dialog gives a time-lapse."""
    lapse = date_range is not None or time_range is not None
    if duration_s is None:
        duration_s = DEFAULT_DURATION_S if lapse else ORBIT_SECONDS_PER_TURN * turns
    return SavedTour(name=name, motion="orbit",
                     orbit=DroneOrbit(pose, turns=turns, clockwise=clockwise, ease=True),
                     date_range=date_range, time_range=time_range, duration_s=duration_s)


def held_tour(pose: CameraPose, name: str, *, date_range=None, time_range=None,
              duration_s: float = DEFAULT_DURATION_S) -> SavedTour:
    """The camera stands still while the day or the year passes."""
    assert (date_range is None) != (time_range is None), "a held tour is a time-lapse"
    eye = tuple(round(value, 1) for value in pose.eye)
    return SavedTour(name=name, motion="hold", held=CameraKey(eye, pose.target_scene),
                     date_range=date_range, time_range=time_range, duration_s=duration_s)
