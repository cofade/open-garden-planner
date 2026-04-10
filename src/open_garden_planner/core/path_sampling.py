"""Sample evenly-spaced points along a QPainterPath."""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath


def sample_points_along_path(
    path: QPainterPath,
    count: int,
    start_pct: float = 0.0,
    end_pct: float = 1.0,
    follow_tangent: bool = False,
) -> list[tuple[QPointF, float]]:
    """Return *count* evenly-spaced (position, angle) samples along *path*.

    Uses arc-length parameterization so spacing is visually uniform even on
    paths with uneven segment lengths.

    Args:
        path: The path to sample along.
        count: Number of sample points (must be >= 2).
        start_pct: Fraction of total path length to start at (0.0 - 1.0).
        end_pct: Fraction of total path length to stop at (0.0 - 1.0).
        follow_tangent: If True, return the tangent angle at each point;
            otherwise angle is always 0.0.

    Returns:
        List of (point, angle_degrees) tuples.
    """
    total_length = path.length()
    if total_length < 1e-6 or count < 1:
        return []

    start_len = total_length * max(0.0, min(start_pct, 1.0))
    end_len = total_length * max(0.0, min(end_pct, 1.0))
    usable = end_len - start_len
    if usable < 1e-6:
        return []

    results: list[tuple[QPointF, float]] = []
    for i in range(count):
        d = start_len + usable / 2.0 if count == 1 else start_len + usable * i / (count - 1)
        t = path.percentAtLength(d)
        pt = path.pointAtPercent(t)
        angle = path.angleAtPercent(t) if follow_tangent else 0.0
        results.append((pt, angle))
    return results
