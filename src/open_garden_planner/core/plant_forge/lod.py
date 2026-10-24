"""Level-of-Detail (LOD) budgets and distance thresholds for Plant Forge (Phase 17 L3.1, #387).

Qt-free: standard library only.
"""

from __future__ import annotations

from typing import Final

#: Full-detail close-up model: space-colonisation skeleton + micro-leaves + seasonal accents.
LOD0: Final[int] = 0
#: Medium-distance model: coarsened skeleton + clustered micro-leaves.
LOD1: Final[int] = 1
#: Far-distance model: simplified trunk + low-poly crown shell.
LOD2: Final[int] = 2

LOD_LEVELS: Final[tuple[int, int, int]] = (LOD0, LOD1, LOD2)

#: Per-plant total triangle caps (wood + foliage + accents) per LOD level (L3.1 gate).
LOD0_TRIANGLE_BUDGET: Final[int] = 25_000
LOD1_TRIANGLE_BUDGET: Final[int] = 6_000
LOD2_TRIANGLE_BUDGET: Final[int] = 800

LOD_TRIANGLE_BUDGETS: Final[dict[int, int]] = {
    LOD0: LOD0_TRIANGLE_BUDGET,
    LOD1: LOD1_TRIANGLE_BUDGET,
    LOD2: LOD2_TRIANGLE_BUDGET,
}

#: Camera distance thresholds (cm) for automatic LOD selection.
LOD0_MAX_DISTANCE_CM: Final[float] = 1_800.0
LOD1_MAX_DISTANCE_CM: Final[float] = 4_500.0


def validate_lod(lod: int) -> int:
    """Validate that ``lod`` is one of ``LOD0``, ``LOD1``, ``LOD2``."""
    if lod not in LOD_TRIANGLE_BUDGETS:
        raise ValueError(f"lod must be one of {LOD_LEVELS}, got {lod!r}")
    return lod


def triangle_budget_for_lod(lod: int) -> int:
    """Return the maximum triangle count allowed for ``lod``."""
    validate_lod(lod)
    return LOD_TRIANGLE_BUDGETS[lod]


def select_lod(distance_cm: float) -> int:
    """Select ``LOD0``, ``LOD1`` or ``LOD2`` for a plant at ``distance_cm`` from the camera."""
    if distance_cm <= LOD0_MAX_DISTANCE_CM:
        return LOD0
    if distance_cm <= LOD1_MAX_DISTANCE_CM:
        return LOD1
    return LOD2


def lod_skeleton_budget(lod: int, base_attractors: int) -> tuple[int, int, int]:
    """Return ``(max_nodes, attractors, limb_sides)`` for ``lod``."""
    validate_lod(lod)
    if lod == LOD0:
        return (720, max(120, min(base_attractors, 520)), 7)
    if lod == LOD1:
        return (180, max(48, min(base_attractors // 3, 140)), 5)
    return (28, max(16, min(base_attractors // 10, 28)), 4)


__all__ = [
    "LOD0",
    "LOD0_MAX_DISTANCE_CM",
    "LOD0_TRIANGLE_BUDGET",
    "LOD1",
    "LOD1_MAX_DISTANCE_CM",
    "LOD1_TRIANGLE_BUDGET",
    "LOD2",
    "LOD2_TRIANGLE_BUDGET",
    "LOD_LEVELS",
    "LOD_TRIANGLE_BUDGETS",
    "lod_skeleton_budget",
    "select_lod",
    "triangle_budget_for_lod",
    "validate_lod",
]
