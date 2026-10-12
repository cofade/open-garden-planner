"""A garden wall with a coping, swept along a centre line (Phase 17 L1.6).

Geometry only: which polyline becomes a wall is decided in ``lines.py`` (a WALL
without a style, and any line in the ``STONE_WALL`` style).

Built from the polyline's centre line, never from the stroke outline in
``record.footprints``: a wall round a garden is a closed loop whose stroke is an
outer ring with the garden as its hole (``record.holes``). Extruding the outer
ring alone would fill the garden with stone, and even the ring minus its hole
is only the drawn line weight, not a wall. A closed centre line is swept as a loop (mitred all round, no ends);
an open one gets two flat ends. A hairpin is bevelled on its outside
(``primitives.BEVEL_BEYOND``), so the coping grows no spike.

One ``tinted`` part: in 2D a wall is seen in its stroke colour (every polyline
style paints from the item's pen), so that is its colour here.

The plan holds no thickness for a wall — its stroke width is a line weight
(4–5 cm). The body is ``max(stroke, 30)`` cm (the L0 board's wall), the coping
4 cm wider on each side.
"""

from __future__ import annotations

from typing import Final

from ..mesh import Mesh, MeshPart
from ..record import Record
from .palette import TINT
from .primitives import F64, sweep

#: Body thickness when the stroke is thinner (cm).
WALL_THICKNESS_CM: Final = 30.0
#: How far the coping oversails the body on each side (cm).
COPING_OVERSAIL_CM: Final = 4.0
#: The coping is this tall at most (cm), and at most this share of the wall.
COPING_HEIGHT_CM: Final = 8.0
COPING_SHARE: Final = 0.2


def body_thickness_cm(record: Record) -> float:
    """The wall body's thickness: the drawn stroke, but at least a wall's."""
    return max(record.path_width_cm or 0.0, WALL_THICKNESS_CM)


def wall_mesh(line: F64, closed: bool, thickness_cm: float, height_cm: float) -> Mesh:
    """Body plus coping along ``line``; the coping's top is exactly ``height_cm``."""
    half = thickness_cm / 2.0
    cap_half = half + COPING_OVERSAIL_CM
    coping = min(COPING_HEIGHT_CM, COPING_SHARE * height_cm)
    chamfer = min(2.0, coping / 3.0)
    under = height_cm - coping
    profile = [
        (-half, 0.0), (half, 0.0), (half, under), (cap_half, under), (cap_half, height_cm - chamfer),
        (cap_half - chamfer, height_cm), (-cap_half + chamfer, height_cm),
        (-cap_half, height_cm - chamfer), (-cap_half, under), (-half, under),
    ]
    on_the_ground = [False] + [True] * (len(profile) - 1)
    return sweep(profile, line, TINT, closed=closed, edges=on_the_ground)


def wall_parts(record: Record, line: F64, closed: bool, height_cm: float) -> tuple[MeshPart, ...]:
    """The one part of a wall along ``line`` (the record's centre line)."""
    mesh = wall_mesh(line, closed, body_thickness_cm(record), height_cm)
    return (MeshPart(mesh, "vc", tinted=True, name="wall"),)


def triangle_budget(record: Record) -> int:
    """The most triangles a wall may have: per path segment its 9 faces (18
    triangles) and, if the joint after it is a bevelled hairpin, 18 more; the two
    ends of an open wall are 16 — so 36 per segment + 20."""
    return 36 * max(len(record.path) - 1, 1) + 20
