"""The one zero-angle rule shared by group mutation, persistence and Ungroup.

A floating-point gesture can leave a few micro-degrees behind. Below this
tolerance the app treats the orientation as unchanged everywhere: the Agent API
does not start a turn, a group angle is not written, and Ungroup does not call
the group turned. An accepted turn is therefore always above the tolerance and
always survives save/reload (#1022 review).
"""

from __future__ import annotations

ZERO_ANGLE_DEG = 1e-6


def is_zero_angle(angle: float) -> bool:
    """Whether *angle* is a whole 360° multiple within the shared tolerance."""
    normalized = float(angle) % 360.0
    return min(normalized, 360.0 - normalized) <= ZERO_ANGLE_DEG
