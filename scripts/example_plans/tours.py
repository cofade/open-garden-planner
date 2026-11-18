"""The camera tours an example plan ships with, computed from the plan itself.

No view is open when a plan is authored, so the orbit is framed the way the Camera Tour
dialog frames one: the plan rectangle and the highest thing on it, seen from the dialog's
default tilt. Every number is rounded before it is stored: ``--check`` compares the JSON,
and the last bit of a sine differs between platforms.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from open_garden_planner.core.camera_path import DroneOrbit, clamp_orbit_pitch
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


def orbit_pose(scene, manager, meta: dict, *, sun_offset_deg: float = SUN_BEHIND_DEG) -> CameraPose:
    """Where the orbit starts: far enough to keep the whole plan in a 16:9 frame all the
    way round, and turned so that the sun of the showcase moment is behind the camera."""
    day, utc_time = showcase_moment(meta)
    bounds = plan_bounds(scene, day)
    aspect = DEFAULT_SIZE[0] / DEFAULT_SIZE[1]
    distance = max(frame_pose(bounds, aspect, yaw_deg=float(yaw),
                              pitch_deg=DEFAULT_ORBIT_PITCH_DEG).distance_cm
                   for yaw in range(0, 360, 5))
    location = manager.location or {}
    sun = solar_position(location["latitude"], location["longitude"],
                         datetime.combine(day, utc_time, tzinfo=UTC))
    yaw = (scene_azimuth(sun.azimuth_deg, manager.north_angle_deg) + sun_offset_deg) % 360.0
    east, north = bounds.center
    return CameraPose((round(east, 1), round(north, 1)), float(round(distance)), round(yaw, 1),
                      round(clamp_orbit_pitch(DEFAULT_ORBIT_PITCH_DEG, distance), 1))


def orbit_tour(pose: CameraPose, name: str = ORBIT, *, date_range=None, time_range=None,
               duration_s: float | None = None) -> SavedTour:
    """One eased turn around the plan. With a range it is a time-lapse of the day or the
    year, at the length the dialog gives a time-lapse."""
    lapse = date_range is not None or time_range is not None
    if duration_s is None:
        duration_s = DEFAULT_DURATION_S if lapse else ORBIT_SECONDS_PER_TURN
    return SavedTour(name=name, motion="orbit", orbit=DroneOrbit(pose, ease=True),
                     date_range=date_range, time_range=time_range, duration_s=duration_s)
