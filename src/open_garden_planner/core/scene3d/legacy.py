"""The pre-L1.1 3D contract of the Qt 3D view (US-E6, #261) — what is left of it.

Until Phase 17 L1.1 (#385, ADR-064) this was ``core/scene3d.py``. It still feeds
the shipped Qt 3D window and the dormant spike, and ``core.scene3d`` re-exports
every name it ever had, so no importer changed.

What lives here now, and goes with Qt 3D and the spike in L1.10: the
``Scene3DRecord`` contract (``records_from_raw``, the ``DECAL_*`` /
``FLAT_THICKNESS_CM`` constants), ``extrude_footprint`` (scene-space prisms) and
the scalar ``to_engine_frame``.

What moved out because contract v2 is built on it, and STAYS after L1.10:
``triangulate_polygon`` (now ``polygon.py``) and ``sun_direction_scene`` (now
``frame.py``). Both are imported back below, unchanged, so
``core.scene3d.legacy.triangulate_polygon`` still resolves.

Frames (§8.20 discipline):
- SCENE frame: x = East, y = North, z = up, centimeters (ADR-002 + height).
- ENGINE frame (Qt3D default Y-up): x = East, y = up, z = −North — apply
  ``to_engine_frame`` exactly ONCE, at the adapter boundary. All geometry
  in this module stays in the scene frame.
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple, cast

from ..shadow_geometry import Polygon
from .frame import sun_direction_scene
from .polygon import _signed_area, triangulate_polygon

__all__ = [
    "DECAL_LIFT_CM",
    "DECAL_MAX_LIFT_CM",
    "DECAL_STACK_STEP_CM",
    "FLAT_THICKNESS_CM",
    "Scene3DRecord",
    "extrude_footprint",
    "records_from_raw",
    "sun_direction_scene",
    "to_engine_frame",
    "triangulate_polygon",
]

#: Items without a height render as thin ground decals of this thickness.
FLAT_THICKNESS_CM = 2.0

#: Flat decals (paths, lawns, in-ground beds) are all coplanar at ground level,
#: so the depth buffer z-fights between them and the ground. Lift them clear of
#: the ground and step each one up the 2D stacking order so a higher layer
#: renders ON TOP (matching the 2D "higher layer covers lower"), rather than
#: intersecting. Small enough to still read as flat ground markings.
DECAL_LIFT_CM = 1.0
DECAL_STACK_STEP_CM = 1.0
#: Cap the cumulative lift so a plan with many flat decals doesn't float its
#: top paths so high they stop reading as ground markings (beyond this depth,
#: overlapping decals are rare enough that residual z-fighting is acceptable).
DECAL_MAX_LIFT_CM = 10.0


class Scene3DRecord(NamedTuple):
    """One item of the plan, ready for the engine adapter."""

    footprint: tuple[tuple[float, float], ...]
    height_cm: float
    color_rgba: tuple[int, int, int, int]
    kind: str  # "extruded" | "flat"
    name: str
    base_cm: float = 0.0  # vertical lift (flat decals stack up the 2D order)


def records_from_raw(
    raw_items: list[dict[str, Any]],
) -> list[Scene3DRecord]:
    """Validate + normalize collector output into engine-ready records.

    Each raw dict: ``footprint`` (list of (x, y)), ``height_cm``
    (float | None), ``color_rgba`` ((r, g, b, a)), ``name`` (str).
    Items without a positive height become flat decals; degenerate
    footprints (< 3 vertices) are dropped.
    """
    records: list[Scene3DRecord] = []
    decal_rank = 0  # raw_items arrive bottom-to-top; step decals up that order
    for raw in raw_items:
        footprint = tuple(
            (float(x), float(y)) for x, y in raw.get("footprint", ())
        )
        if len(footprint) < 3:
            continue
        height = raw.get("height_cm")
        if height is not None and height > 0:
            kind, height_cm, base_cm = "extruded", float(height), 0.0
        else:
            kind, height_cm = "flat", FLAT_THICKNESS_CM
            base_cm = min(
                DECAL_LIFT_CM + decal_rank * DECAL_STACK_STEP_CM,
                DECAL_MAX_LIFT_CM,
            )
            decal_rank += 1
        color = raw.get("color_rgba") or (150, 150, 150, 255)
        records.append(
            Scene3DRecord(
                footprint=footprint,
                height_cm=height_cm,
                color_rgba=cast("tuple[int, int, int, int]", tuple(int(c) for c in color)),
                kind=kind,
                name=str(raw.get("name", "")),
                base_cm=base_cm,
            )
        )
    return records


# ── prism extrusion ─────────────────────────────────────────────


def extrude_footprint(
    footprint: Polygon, height_cm: float, base_cm: float = 0.0
) -> tuple[list[float], list[float]]:
    """Triangle soup (positions, normals) for an extruded prism, SCENE frame.

    Side walls (two triangles per edge, outward flat normals) + top cap
    (ear-clipped, +up normals). The bottom cap is omitted — prisms sit on
    the ground plane and their underside is never visible. Vertex winding
    is chosen so front faces point outward/up (CCW seen from outside).
    """
    if len(footprint) < 3 or height_cm <= 0:
        return [], []
    ring = list(footprint)
    if _signed_area(ring) < 0:
        ring.reverse()  # CCW so edge normals point outward
    positions: list[float] = []
    normals: list[float] = []
    top = base_cm + height_cm
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        edge = math.hypot(x2 - x1, y2 - y1)
        if edge <= 1e-9:
            continue
        nx, ny = (y2 - y1) / edge, -(x2 - x1) / edge  # outward for CCW ring
        quad = [
            (x1, y1, base_cm), (x2, y2, base_cm), (x2, y2, top),
            (x1, y1, base_cm), (x2, y2, top), (x1, y1, top),
        ]
        for px, py, pz in quad:
            positions.extend((px, py, pz))
            normals.extend((nx, ny, 0.0))
    for i1, i2, i3 in triangulate_polygon(ring):
        for idx in (i1, i2, i3):
            x, y = ring[idx]
            positions.extend((x, y, top))
            normals.extend((0.0, 0.0, 1.0))
    return positions, normals


# ── frame mapping ────────────────────────────────────


def to_engine_frame(
    east: float, north: float, up: float
) -> tuple[float, float, float]:
    """Scene (E, N, up) → Qt3D default Y-up frame (x=E, y=up, z=−N).

    Applied exactly once, at the adapter boundary — the §8.20 rule
    transplanted to 3D. A second application anywhere mirrors the garden.
    """
    return (east, up, -north)
