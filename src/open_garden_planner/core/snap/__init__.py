"""Unified snap engine.

A small abstraction over the existing :mod:`measure_snapper` and
:mod:`snapping` modules.  Providers expose snap candidates and the
``SnapRegistry`` orchestrates which providers are active.  This package
adds two new snap modes (midpoint, intersection) on top of the legacy
anchor and bounding-box logic.
"""

from open_garden_planner.core.snap.provider import (
    SnapCandidate,
    SnapCandidateKind,
    SnapProvider,
)
from open_garden_planner.core.snap.registry import SnapRegistry

__all__ = [
    "SnapCandidate",
    "SnapCandidateKind",
    "SnapProvider",
    "SnapRegistry",
]
