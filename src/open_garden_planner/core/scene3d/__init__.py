"""Qt-free 3D scene core (Phase 17 L1.1, #385, ADR-054).

Two contracts live here until L1.10 removes Qt 3D:

- the LEGACY contract (``legacy``: ``Scene3DRecord``, ``records_from_raw``,
  ``extrude_footprint`` …) — every name of the former ``core/scene3d.py``
  module, re-exported below so its importers did not change;
- contract v2, in the sibling modules.
"""

from __future__ import annotations

from .legacy import (
    DECAL_LIFT_CM,
    DECAL_MAX_LIFT_CM,
    DECAL_STACK_STEP_CM,
    FLAT_THICKNESS_CM,
    Scene3DRecord,
    extrude_footprint,
    records_from_raw,
    sun_direction_scene,
    to_engine_frame,
    triangulate_polygon,
)

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
