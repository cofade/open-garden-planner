"""The plan's north orientation: one angle, additive to the ``.ogp`` format (#663).

The plan's drawing frame has +Y = North (ADR-002). A survey or satellite plan can
have true north at an angle to that frame; rotating every object would destroy the
alignment with the background, dimensions and construction geometry. This module
owns the angle that says how the drawing is turned relative to the compass:

``north_angle_deg`` is the direction of TRUE NORTH on the plan, in degrees
clockwise from plan-up. 0 = north up, 90 = north to the right, 135 =
down-right. The N arrow on the canvas and on the PDF's overview page points at
this angle, and every solar consumer maps a compass azimuth into the scene frame
with :func:`open_garden_planner.core.solar.scene_azimuth`.

The value is plan metadata only: no object coordinate is ever rewritten. It is
written as an additive top-level key (default 0 for old files), so
``FILE_VERSION`` does not move.
"""

from __future__ import annotations

import logging
import math

_LOG = logging.getLogger(__name__)

#: The default for every plan that never named its north.
DEFAULT_NORTH_ANGLE_DEG = 0.0


def normalize_north_angle(value: object) -> float:
    """Validate *value* and return it in ``[0, 360)``.

    Raises ``ValueError`` for a bool, a non-number, a non-finite number, or a
    number too large to convert. The ONE validity rule for the dialog, the
    command and a loaded file.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"north angle must be a number, not {type(value).__name__}")
    try:
        angle = float(value)
    except OverflowError as error:  # a 400-digit integer in a hostile file
        raise ValueError("north angle is not finite") from error
    if not math.isfinite(angle):
        raise ValueError("north angle is not finite")
    return angle % 360.0


def north_angle_from_plan(value: object) -> float:
    """The angle a loaded plan carries, or the default for a missing/bad one.

    Load is a trust boundary: an unreadable value must not keep a plan from
    opening. A non-numeric or malformed value is logged and read as 0 (north
    up), the same state every older file has. A non-finite number never reaches
    this function: ``plan_io`` refuses it like every other numeric in the file.
    """
    if value is None:
        return DEFAULT_NORTH_ANGLE_DEG
    try:
        return normalize_north_angle(value)
    except ValueError:
        _LOG.warning("plan north: ignoring an invalid north_angle_deg %r", value)
        return DEFAULT_NORTH_ANGLE_DEG


def north_direction(angle_deg: object) -> tuple[float, float]:
    """A unit vector pointing at true north, in the scene frame (E, N).

    ``(sin a, cos a)`` for a clockwise-from-up angle: 0 -> (0, 1) up,
    90 -> (1, 0) right, 135 -> down-right. Shared by the canvas arrow, the PDF
    arrow and any surface that must point north on the plan.
    """
    angle = math.radians(normalize_north_angle(angle_deg))
    return (math.sin(angle), math.cos(angle))
