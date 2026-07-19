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
