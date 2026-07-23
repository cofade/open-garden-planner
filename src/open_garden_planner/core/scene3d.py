"""Qt-free 3D scene description for the 3D view (US-E6, #261).

Everything heavy — triangulation, prism extrusion, the solar-light vector,
the scene→engine frame mapping — lives here, headless-testable, in plain
floats. The Qt3D adapter (`ui/view3d/qt3d_adapter.py`, the ONLY module
allowed to import PyQt6.Qt3D* per ADR-038) just packs these arrays into
GPU buffers. If the engine is ever swapped, this module survives intact.

Frames (§8.20 discipline):
- SCENE frame: x = East, y = North, z = up, centimeters (ADR-002 + height).
- ENGINE frame (Qt3D default Y-up): x = East, y = up, z = −North — apply
  ``to_engine_frame`` exactly ONCE, at the adapter boundary. All geometry
  in this module stays in the scene frame.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from .shadow_geometry import Polygon

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
    raw_items: list[dict],
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
                color_rgba=tuple(int(c) for c in color),
                kind=kind,
                name=str(raw.get("name", "")),
                base_cm=base_cm,
            )
        )
    return records


# ── polygon triangulation (ear clipping) ────────────────────────────


def _signed_area(polygon: Polygon) -> float:
    total = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _point_in_triangle(p, a, b, c) -> bool:
    d1 = _cross(p, a, b)
    d2 = _cross(p, b, c)
    d3 = _cross(p, c, a)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def triangulate_polygon(polygon: Polygon) -> list[tuple[int, int, int]]:
    """Ear-clipping triangulation; returns index triples into ``polygon``.

    Handles convex and concave simple polygons; input winding is
    irrelevant (normalized to CCW internally, indices refer to the
    ORIGINAL order). Falls back to a fan for pathological inputs so the
    renderer always gets triangles rather than nothing.
    """
    n = len(polygon)
    if n < 3:
        return []
    indices = list(range(n))
    if _signed_area(polygon) < 0:
        indices.reverse()  # normalize to CCW traversal
    triangles: list[tuple[int, int, int]] = []
    guard = 0
    while len(indices) > 3 and guard < 10000:
        guard += 1
        ear_found = False
        m = len(indices)
        for i in range(m):
            prev_i, cur_i, next_i = (
                indices[(i - 1) % m],
                indices[i],
                indices[(i + 1) % m],
            )
            a, b, c = polygon[prev_i], polygon[cur_i], polygon[next_i]
            if _cross(a, b, c) <= 0:
                continue  # reflex or collinear — not an ear
            if any(
                _point_in_triangle(polygon[j], a, b, c)
                for j in indices
                if j not in (prev_i, cur_i, next_i)
            ):
                continue
            triangles.append((prev_i, cur_i, next_i))
            indices.pop(i)
            ear_found = True
            break
        if not ear_found:
            break  # numeric degeneracy — fan out the rest below
    if len(indices) == 3:
        triangles.append((indices[0], indices[1], indices[2]))
    elif len(indices) > 3:
        anchor = indices[0]
        for i in range(1, len(indices) - 1):
            triangles.append((anchor, indices[i], indices[i + 1]))
    return triangles


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


# ── solar light + frame mapping ────────────────────────────────────


def sun_direction_scene(
    elevation_deg: float, azimuth_deg: float
) -> tuple[float, float, float]:
    """Unit vector pointing AT the sun, scene frame (E, N, up).

    ``(cos α sin Az, cos α cos Az, sin α)`` — the US-E6 gate pins Berlin
    Jun-21 noon at (−0.2056, −0.4675, 0.8598). The engine's LIGHT direction
    is the negation (light travels away from the sun), mapped by
    ``to_engine_frame`` at the adapter boundary.
    """
    elev = math.radians(elevation_deg)
    az = math.radians(azimuth_deg)
    return (
        math.cos(elev) * math.sin(az),
        math.cos(elev) * math.cos(az),
        math.sin(elev),
    )


def to_engine_frame(
    east: float, north: float, up: float
) -> tuple[float, float, float]:
    """Scene (E, N, up) → Qt3D default Y-up frame (x=E, y=up, z=−N).

    Applied exactly once, at the adapter boundary — the §8.20 rule
    transplanted to 3D. A second application anywhere mirrors the garden.
    """
    return (east, up, -north)
