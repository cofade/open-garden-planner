"""Facades: windows on the long walls, a door toward the nearest path (Phase 17 L4.1).

The plan holds no windows and no doors. A building without them reads as a
block, so L4.1 adds a HEURISTIC facade — stated as one, never a claim about the
real building:

- **The door** goes in the middle of the wall that FACES the nearest path
  (``params["door_wall"]``: that wall's index, which ``door_wall_index`` finds
  for the snapshot from the nearest PATH point — a garage's nearest DRIVEWAY
  first). Only WHICH wall: a building that moves along its path keeps its door
  where it is, and its mesh (a move re-poses, it does not rebuild — ADR-059). A
  plan without a path: the longest wall, the one facing the item's own −y (its
  front, for an unrotated building) when two are as long. A garage gets a
  sectional garage door, a shed a narrow plank door.
- **Windows** sit on every wall long enough for them, evenly spaced, never on
  the door, and only where the wall reaches above them — a gable end's sloping
  top, a mono-pitch roof's low side, a garden shed's low eaves all decide. A
  house with walls tall enough gets an upper row.

Everything stays on the walls: a frame, a pane, a sill or a step stands at most
``MAX_PROUD_CM`` proud of the wall (the truth gate: nothing beyond the footprint
plus 10 cm) and under the wall's top (``wall_top``, from the roof), so the
building's top stays its height. Colours are the sprites' (``palette``): white
frames, dark glass, a stone sill, a walnut door, brass. Every element is a box,
and all of a facade's boxes are made in ONE ``flat_mesh`` call.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import ArrayLike

from ..mesh import Mesh
from . import palette
from .primitives import F64, ccw_ring, flat_mesh, quad_triangles

#: The most a facade element stands out of its wall (cm): a step, a sill.
MAX_PROUD_CM: Final = 9.0
#: The most windows one wall gets (a wall kilometres long: wider apart), and in all.
MAX_WINDOWS_PER_WALL: Final = 24
MAX_WINDOWS_TOTAL: Final = 96
#: A window or a door keeps this far under the wall's top (cm).
HEADROOM_CM: Final = 10.0
#: A wall shorter than this (cm) is no wall of the facade (a sliver of the outline).
MIN_WALL_CM: Final = 1.0

Color = tuple[float, float, float, float]

#: The six faces of a box, as corners (along, up, out) ∈ {0, 1}³, and the axis
#: (±along, ±up, ±out) each looks along.
_FACES: Final = np.array([
    [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    [(1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)],
    [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
    [(1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)],
    [(0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)],
    [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
], dtype=np.float64)
_FACE_AXES: Final = np.array([(0, 0, 1), (0, 0, -1), (-1, 0, 0), (1, 0, 0), (0, 1, 0), (0, -1, 0)],
                             dtype=np.float64)


@dataclass(frozen=True, slots=True)
class FacadeSpec:
    """The sizes of one building kind's openings (cm)."""

    door_w: float
    door_h: float
    window_w: float
    window_h: float
    sill: float
    spacing: float          # one window per this much wall
    min_wall: float         # a shorter wall gets none
    margin: float           # kept clear at each end of a wall
    upper_row: float = 0.0  # a second row this much higher (0: none)
    garage: bool = False    # a sectional garage door instead of a door
    max_windows: int = 99   # in all


SPECS: Final[dict[str, FacadeSpec]] = {
    "HOUSE": FacadeSpec(100.0, 205.0, 110.0, 120.0, 85.0, 260.0, 180.0, 60.0, upper_row=280.0),
    "GARAGE_SHED": FacadeSpec(250.0, 210.0, 80.0, 60.0, 130.0, 350.0, 250.0, 40.0, garage=True),
    "TOOL_SHED": FacadeSpec(90.0, 190.0, 60.0, 50.0, 110.0, 400.0, 150.0, 25.0, max_windows=1),
}


@dataclass(frozen=True, slots=True)
class _Wall:
    start: F64
    along: F64      # unit, along the wall
    out: F64        # unit, out of the building
    length: float

    def point(self, s: float, proud: float) -> F64:
        here: F64 = self.start + self.along * s + self.out * proud
        return here


def _walls(ring: F64) -> list[_Wall]:
    """The walls of a counter-clockwise ring, in its order (slivers left out) — the
    indices ``params["door_wall"]`` names."""
    walls = []
    for index in range(len(ring)):
        start, end = ring[index], ring[(index + 1) % len(ring)]
        edge = end - start
        length = float(np.linalg.norm(edge))
        if length < MIN_WALL_CM:
            continue
        along = edge / length
        walls.append(_Wall(start, along, np.array([along[1], -along[0]]), length))
    return walls


def door_wall_index(footprint: ArrayLike, target: tuple[float, float]) -> int | None:
    """The index of the wall a door toward ``target`` (a point in the footprint's own
    frame) goes on: among the walls that FACE it, the nearest; None for a footprint
    without walls. What the snapshot writes into ``params["door_wall"]``."""
    walls = _walls(ccw_ring(footprint))
    if not walls:
        return None
    point = np.asarray(target, dtype=np.float64)

    def distance(wall: _Wall) -> float:
        s = float(np.clip((point - wall.start) @ wall.along, 0.0, wall.length))
        return float(np.linalg.norm(point - wall.point(s, 0.0)))

    facing = [i for i, wall in enumerate(walls)
              if float((point - wall.point(wall.length / 2.0, 0.0)) @ wall.out) > 0.0]
    pool = facing or list(range(len(walls)))
    return min(pool, key=lambda i: distance(walls[i]))


def _front_wall(walls: list[_Wall]) -> int:
    """The door's wall without a path: the longest, the one facing −y of equals."""
    longest = max(wall.length for wall in walls)
    candidates = [i for i, wall in enumerate(walls) if wall.length >= longest - 1.0]
    return min(candidates, key=lambda i: float(walls[i].out[1]))


class _Boxes:
    """Boxes on walls, collected and made into one mesh at the end."""

    def __init__(self) -> None:
        self.quads: list[F64] = []
        self.out: list[F64] = []
        self.colors: list[Color] = []

    def add(self, wall: _Wall, s0: float, s1: float, z0: float, z1: float, p0: float, p1: float,
            color: Color) -> None:
        """A box on ``wall``: ``s0``–``s1`` along it, ``z0``–``z1`` up it, ``p0``–``p1``
        out of it (cm)."""
        if s1 - s0 < 0.1 or z1 - z0 < 0.1 or p1 - p0 < 0.05:
            return
        along = np.array([*wall.along, 0.0])
        out = np.array([*wall.out, 0.0])
        up = np.array([0.0, 0.0, 1.0])
        origin = np.array([*wall.start, 0.0])
        size = np.array([s1 - s0, z1 - z0, p1 - p0])
        low = np.array([s0, z0, p0])
        local = low + _FACES * size  # (6, 4, 3) in (along, up, out)
        frame = np.stack([along, up, out])  # rows: the three axes in the scene
        self.quads.append(origin + local @ frame)
        self.out.append(_FACE_AXES @ frame)
        self.colors.append(color)

    def mesh(self) -> Mesh:
        if not self.quads:
            return Mesh.empty()
        quads = np.concatenate(self.quads)
        outward = np.repeat(np.concatenate(self.out), 2, axis=0)
        colors = np.repeat(np.asarray(self.colors, dtype=np.float64), 12, axis=0)
        return flat_mesh(quad_triangles(quads), colors, outward=outward)


def _fits(wall: _Wall, wall_top: Callable[[F64], F64], s0: float, s1: float, top: float) -> bool:
    ends = np.stack([wall.point(s0, 0.0), wall.point(s1, 0.0)])
    return bool((wall_top(ends) >= top + HEADROOM_CM).all())


def _window(boxes: _Boxes, wall: _Wall, centre: float, sill: float, spec: FacadeSpec) -> None:
    s0, s1 = centre - spec.window_w / 2.0, centre + spec.window_w / 2.0
    z0, z1 = sill, sill + spec.window_h
    frame, white = min(6.0, 0.1 * spec.window_w), palette.STEEL_LIGHT.linear
    transom = z0 + 0.62 * spec.window_h
    boxes.add(wall, s0 + frame, s1 - frame, z0 + frame, z1 - frame, 0.0, 1.0, palette.GLASS_OCC.linear)
    boxes.add(wall, s0, s0 + frame, z0, z1, 0.0, 3.0, white)
    boxes.add(wall, s1 - frame, s1, z0, z1, 0.0, 3.0, white)
    boxes.add(wall, s0 + frame, s1 - frame, z1 - frame, z1, 0.0, 3.0, white)
    boxes.add(wall, s0 + frame, s1 - frame, z0, z0 + frame, 0.0, 3.0, white)
    boxes.add(wall, centre - 2.0, centre + 2.0, z0 + frame, z1 - frame, 0.0, 2.5, white)
    boxes.add(wall, s0 + frame, s1 - frame, transom - 2.0, transom + 2.0, 0.0, 2.5, white)
    boxes.add(wall, s0 - 4.0, s1 + 4.0, z0 - 5.0, z0, 0.0, 5.0, palette.STONE_LIGHT.linear)


def _door(boxes: _Boxes, wall: _Wall, centre: float, width: float, height: float,
          spec: FacadeSpec) -> None:
    s0, s1 = centre - width / 2.0, centre + width / 2.0
    frame = min(7.0, 0.08 * width)
    if spec.garage:
        panels = 4
        step = (height - frame) / panels
        for k in range(panels):
            boxes.add(wall, s0 + frame, s1 - frame, k * step, (k + 1) * step, 0.0, 1.5,
                      (palette.STEEL if k % 2 == 0 else palette.STEEL_LIGHT).linear)
        dark = palette.STEEL_DARK.linear
        boxes.add(wall, s0, s0 + frame, 0.0, height, 0.0, 2.5, dark)
        boxes.add(wall, s1 - frame, s1, 0.0, height, 0.0, 2.5, dark)
        boxes.add(wall, s0, s1, height - frame, height, 0.0, 2.5, dark)
        return
    white = palette.STEEL_LIGHT.linear
    knob = min(100.0, 0.5 * height)
    boxes.add(wall, s0 + frame, s1 - frame, 0.0, height - frame, 0.0, 2.0, palette.TIMBER.linear)
    boxes.add(wall, s0, s0 + frame, 0.0, height, 0.0, 3.5, white)
    boxes.add(wall, s1 - frame, s1, 0.0, height, 0.0, 3.5, white)
    boxes.add(wall, s0, s1, height - frame, height, 0.0, 3.5, white)
    boxes.add(wall, s1 - frame - 0.25 * width, s1 - frame - 0.25 * width + 4.0, knob, knob + 3.0,
              2.0, 5.0, palette.BRASS.linear)
    boxes.add(wall, s0 - 10.0, s1 + 10.0, 0.0, 4.0, 0.0, MAX_PROUD_CM, palette.STONE.linear)


def facade(kind: str, footprint: ArrayLike, wall_top: Callable[[F64], F64],
           door_wall: int | None) -> Mesh:
    """The windows and the door of a building of ``kind`` on the walls of
    ``footprint`` under ``wall_top`` — the door on wall ``door_wall`` (module
    docstring), or on the front wall when that is None or no wall of this ring."""
    spec = SPECS.get(kind)
    ring = ccw_ring(footprint)
    if spec is None or len(ring) < 3:
        return Mesh.empty()
    walls = _walls(ring)
    if not walls:
        return Mesh.empty()
    boxes = _Boxes()
    door_at = door_wall if door_wall is not None and 0 <= door_wall < len(walls) else _front_wall(walls)
    blocked: dict[int, tuple[float, float]] = {}
    wall = walls[door_at]
    width = min(spec.door_w, 0.75 * wall.length) if spec.garage else spec.door_w
    if wall.length >= width + 2.0 * spec.margin:
        centre = wall.length / 2.0
        ends = np.stack([wall.point(centre - width / 2.0, 0.0), wall.point(centre + width / 2.0, 0.0)])
        height = min(spec.door_h, float(wall_top(ends).min()) - HEADROOM_CM)
        if height >= 0.8 * spec.door_h:
            _door(boxes, wall, centre, width, height, spec)
            blocked[door_at] = (centre - width / 2.0 - 40.0, centre + width / 2.0 + 40.0)
    placed = 0
    limit = min(spec.max_windows, MAX_WINDOWS_TOTAL)
    for index in sorted(range(len(walls)), key=lambda i: -walls[i].length):
        wall = walls[index]
        if wall.length < spec.min_wall or placed >= limit:
            continue
        usable = wall.length - 2.0 * spec.margin
        count = min(MAX_WINDOWS_PER_WALL, max(1, math.floor(usable / spec.spacing)))
        rows = [spec.sill] + ([spec.sill + spec.upper_row] if spec.upper_row else [])
        for k in range(count):
            if placed >= limit:
                break
            centre = spec.margin + (k + 0.5) * usable / count
            s0, s1 = centre - spec.window_w / 2.0, centre + spec.window_w / 2.0
            for row, sill in enumerate(rows):
                gap = blocked.get(index)
                if row == 0 and gap is not None and s1 > gap[0] and s0 < gap[1]:
                    continue
                if not _fits(wall, wall_top, s0, s1, sill + spec.window_h):
                    continue
                _window(boxes, wall, centre, sill, spec)
                placed += 1 if row == 0 else 0
    return boxes.mesh()
