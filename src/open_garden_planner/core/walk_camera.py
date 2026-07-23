"""Qt-free walk-camera math for the 3D walkthrough (US-E7, #262).

The walkthrough is a CAMERA MODE on the US-E6 view, not a renderer: the
engine's first-person controller handles input, and these helpers pin the
two physical rules — the eye stays at eye height on the flat ground plane
(v2.0's stated flat-ground assumption) and the camera cannot leave the
plan bounds (+ a small margin). Scene frame throughout (E, N, up).
"""

from __future__ import annotations

import math

#: Fixed eye height — one named constant, deliberately not configurable
#: in the MVP (FR-SUN-07).
EYE_HEIGHT_CM = 165.0

#: How far beyond the plan edge the walker may step (breathing room so
#: the fence line can be viewed from "just outside").
BOUNDS_MARGIN_CM = 150.0

#: Pitch limit — stops the gimbal flip at straight-up/straight-down.
PITCH_LIMIT_DEG = 89.0

#: Ground movement speed (cm/s) — a brisk walk. Movement is HORIZONTAL: the
#: engine's first-person controller would move along the (pitched) view
#: vector, so looking up would lift the walker off the ground and slow the
#: forward pace by cos(pitch); we drive movement ourselves instead.
WALK_SPEED_CM_S = 350.0


def clamp_walk_position(
    east: float,
    north: float,
    width_cm: float,
    height_cm: float,
    margin_cm: float = BOUNDS_MARGIN_CM,
) -> tuple[float, float]:
    """Clamp a ground position to the plan rectangle plus margin."""
    return (
        min(max(east, -margin_cm), width_cm + margin_cm),
        min(max(north, -margin_cm), height_cm + margin_cm),
    )


def walk_step(
    east: float,
    north: float,
    yaw_deg: float,
    forward: float,
    strafe: float,
    distance: float,
) -> tuple[float, float]:
    """Advance a ground position horizontally along compass ``yaw``.

    ``forward`` (+1 ahead / −1 back) moves along the yaw heading; ``strafe``
    (+1 right / −1 left) along its right-hand perpendicular. The pitch is
    deliberately ignored — walking speed never depends on where you look
    (the fix for "forward is slow / drifts up when looking up"). Diagonal
    input is normalized so it isn't faster than a cardinal step.
    """
    magnitude = math.hypot(forward, strafe)
    if magnitude <= 1e-9 or distance == 0.0:
        return (east, north)
    forward /= magnitude
    strafe /= magnitude
    yaw = math.radians(yaw_deg)
    sin_yaw, cos_yaw = math.sin(yaw), math.cos(yaw)
    # forward heading = (sin, cos); right-hand perpendicular = (cos, −sin).
    return (
        east + distance * (forward * sin_yaw + strafe * cos_yaw),
        north + distance * (forward * cos_yaw - strafe * sin_yaw),
    )


def look_direction(yaw_deg: float, pitch_deg: float) -> tuple[float, float, float]:
    """Unit look vector from compass yaw (clockwise from north) + pitch.

    Pitch is clamped to ±PITCH_LIMIT_DEG — the vector stays unit-length
    and never flips over the zenith (the ±89° gate from issue #262).
    """
    pitch = max(-PITCH_LIMIT_DEG, min(PITCH_LIMIT_DEG, pitch_deg))
    yaw = math.radians(yaw_deg)
    pitch_rad = math.radians(pitch)
    cos_pitch = math.cos(pitch_rad)
    return (
        math.sin(yaw) * cos_pitch,
        math.cos(yaw) * cos_pitch,
        math.sin(pitch_rad),
    )
