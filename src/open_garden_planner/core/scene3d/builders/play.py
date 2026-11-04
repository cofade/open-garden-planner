"""Play and leisure: sandbox, trampoline, hot tub, swing, hammock (Phase 17 L4, #388).

The 3D twins of the #308 roster's sprites (``scripts/generate_object_sprites.py``
``build_<object>``), under the rules of ``furniture`` (its module docstring):
the sprite's parts and materials, its top edge on the item's local +y, the top
EXACTLY at the height, nothing beyond the footprint.

What the height is, per object — the one number the plan holds:

- **sandbox**: the frame's top (the toys lie in the sand below it);
- **trampoline**: the padded rim; the jumping mat is a hand below it. No safety
  net: the height is the rim's, and a net would stand twice as tall;
- **hot tub**: the cladding's rim; the water lies a hand below it (a ``water``
  part, the pond's shader);
- **swing**: the top beam of the A-frame;
- **hammock**: the stand's hooks; the fabric sags to two fifths of it.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from ..build import BuilderRegistry
from ..mesh import Mesh, MeshPart
from ..record import Record
from . import palette
from .common import BuiltBuilder, plain_block
from .kit import (
    MAX_REPEATS,
    ObjectBox,
    ball,
    beam,
    beam_under,
    cylinder,
    object_box,
    placed,
    rod,
    slab,
    turned,
    unit_circle,
)
from .primitives import F64, flat_mesh, polygon_cap, prism, quad_triangles

#: The kinds this module builds.
KINDS: Final[tuple[str, ...]] = ("SANDBOX", "TRAMPOLINE", "HOT_TUB", "SWING", "HAMMOCK")

Color = tuple[float, float, float, float]


def _part(meshes: list[Mesh], box: ObjectBox, name: str, kind: str = "vc", *,
          casts_shadow: bool = True) -> MeshPart:
    return MeshPart(placed(meshes, box), kind, casts_shadow=casts_shadow, name=name)


def _sandbox(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A pine frame full of sand, a seat board across each corner, three toys."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    w, d, h = box.half_w, box.half_d, height_cm
    t = min(10.0, 0.1 * min(box.width, box.depth))
    sand = h - min(7.0, 0.3 * h)
    wood = palette.PINE.linear
    frame = [slab(-w, w, -d, -d + t, 0.0, h, wood, 1.0), slab(-w, w, d - t, d, 0.0, h, wood, 1.0),
             slab(-w, -w + t, -d + t, d - t, 0.0, h, wood, 1.0),
             slab(w - t, w, -d + t, d - t, 0.0, h, wood, 1.0)]
    fill = [slab(-w + t, w - t, -d + t, d - t, 0.0, sand, palette.SAND.linear)]
    seat = min(38.0 / 150.0 * min(box.width, box.depth), 0.45 * min(box.width, box.depth))
    board = min(3.0, 0.2 * h)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            corner = np.array([[sx * w, sy * d], [sx * (w - seat), sy * d], [sx * w, sy * (d - seat)]])
            frame.append(prism(corner, h - board, h, palette.PINE_LIGHT.linear))
    toy = min(3.0, 0.4 * (h - sand))  # every toy stays under the frame's top
    if toy > 0.5:
        bx, by = box.sprite(0.36 * 150, 0.6 * 150, 150, 150)
        fill.append(cylinder(bx, by, min(6.0, 0.08 * box.width), sand - 1.0, sand + 2.0 * toy,
                             palette.ENAMEL_RED.linear, top_radius=min(7.0, 0.09 * box.width)))
        px, py = box.sprite(0.7 * 150, 0.72 * 150, 150, 150)
        fill.append(ball(px, py, sand + toy - 0.5, toy, palette.PLASTIC_BLUE.linear))
        sx, sy = box.sprite(0.62 * 150, 0.42 * 150, 150, 150)
        spade = math.radians(-35.0 - 90.0)
        tip = np.array([math.cos(spade), math.sin(spade)]) * min(18.0, 0.15 * box.width)
        fill.append(beam((sx - tip[0], sy - tip[1], sand + 0.6), (sx + tip[0], sy + tip[1], sand + 0.6),
                         min(5.0, 0.04 * box.width), 1.0, palette.PLASTIC_YELLOW.linear))
    return (_part(frame + fill, box, "sandbox"),)


def _trampoline(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A blue padded rim on a steel ring and six legs, a black mat on springs."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    r, h = box.radius, height_cm
    pad_in = r - min(30.0, 0.22 * r)
    pad_t = min(5.0, 0.08 * h)
    pad = turned([(pad_in, h - pad_t), (r - 1.0, h - pad_t), (r - 1.0, h), (pad_in, h),
                  (pad_in, h - pad_t)], palette.PLASTIC_BLUE.linear, segments=36)
    mat_r = pad_in - min(10.0, 0.07 * r)
    mat_z = h - min(3.5, 0.06 * h)
    mat = turned([(0.0, mat_z - 1.0), (mat_r, mat_z - 1.0), (mat_r, mat_z), (0.0, mat_z)],
                 palette.RUBBER.linear, segments=36)
    springs_at = unit_circle(36)
    springs = rod([(mat_r * x, mat_r * y, mat_z - 0.5) for x, y in springs_at],
                  [(pad_in * x, pad_in * y, mat_z - 0.5) for x, y in springs_at], 0.6,
                  palette.STEEL_LIGHT.linear, sides=4)
    ring_r = r - min(15.0, 0.1 * r)
    ring_z = h - pad_t - 3.0
    around = unit_circle(24)
    frame = [rod([(ring_r * x, ring_r * y, ring_z) for x, y in around],
                 [(ring_r * x, ring_r * y, ring_z) for x, y in np.roll(around, -1, axis=0)], 2.5,
                 palette.STEEL.linear)]
    legs = unit_circle(6, 30.0)
    frame.append(rod([(ring_r * x, ring_r * y, 0.0) for x, y in legs],
                     [(ring_r * x, ring_r * y, ring_z) for x, y in legs], 2.0, palette.STEEL.linear))
    feet = [(legs[k], legs[k + 1]) for k in (0, 2, 4)]
    frame.append(rod([(ring_r * a[0], ring_r * a[1], 2.0) for a, _b in feet],
                     [(ring_r * b[0], ring_r * b[1], 2.0) for _a, b in feet], 2.0, palette.STEEL.linear))
    return (_part([pad, mat, springs, *frame], box, "trampoline"),)


def _rounded_rect(half_w: float, half_d: float, radius: float, per_corner: int = 6,
                  straight: tuple[int, int] = (1, 1)) -> F64:
    """A counter-clockwise rounded rectangle about the origin; its straight sides
    along x and y cut into ``straight`` pieces each (a stave per piece)."""
    radius = max(0.0, min(radius, half_w, half_d))
    corners = (((half_w - radius, -half_d + radius), -90.0), ((half_w - radius, half_d - radius), 0.0),
               ((-half_w + radius, half_d - radius), 90.0), ((-half_w + radius, -half_d + radius), 180.0))
    points: list[tuple[float, float]] = []
    for index, ((cx, cy), start) in enumerate(corners):
        for k in range(per_corner + 1):
            a = math.radians(start + 90.0 * k / per_corner)
            points.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
        # the straight side to the next corner (sides alternate: along y, x, y, x)
        pieces = straight[1] if index % 2 == 0 else straight[0]
        (nx, ny), nstart = corners[(index + 1) % 4]
        a = math.radians(nstart)
        x0, y0 = points[-1]
        x1, y1 = nx + radius * math.cos(a), ny + radius * math.sin(a)
        for k in range(1, pieces):
            t = k / pieces
            points.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    ring: F64 = np.asarray(points)
    return ring


def _band(lower: F64, upper: F64, z_low: float, z_high: float) -> F64:
    """Quads (n, 4, 3) between ring ``lower`` at ``z_low`` and ``upper`` at ``z_high``."""
    a = np.concatenate([lower, np.full((len(lower), 1), z_low)], axis=1)
    b = np.concatenate([upper, np.full((len(upper), 1), z_high)], axis=1)
    quads: F64 = np.stack([a, np.roll(a, -1, axis=0), np.roll(b, -1, axis=0), b], axis=1)
    return quads


def _hot_tub(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A teak-clad tub with rounded corners: staves round the outside, a rim, the
    water a hand below it."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    w, d, h = box.half_w, box.half_d, height_cm
    scale = min(box.width, box.depth) / 220.0
    stave = 9.0  # cm, the sprite's 8 units on a 220 cm tub
    staves = (min(MAX_REPEATS // 2, max(1, round(box.width / stave))),
              min(MAX_REPEATS // 2, max(1, round(box.depth / stave))))
    outer = _rounded_rect(w, d, 22.0 * scale, straight=staves)
    rim = min(26.0 * scale, 0.3 * min(w, d))
    inner = _rounded_rect(w - rim, d - rim, 14.0 * scale, straight=staves)
    water = h - min(12.0, 0.25 * h)
    # the cladding: one quad per outline segment, staves of alternating tone
    walls = quad_triangles(_band(outer, outer, 0.0, h))
    tone = np.where(np.arange(len(outer)) % 2 == 0, 0, 1)
    wall_colors = np.repeat(np.where(tone[:, None] == 0, palette.TEAK.linear, palette.TEAK_DARK.linear),
                            2, axis=0)
    out_dir = np.concatenate([outer + np.roll(outer, -1, axis=0), np.zeros((len(outer), 1))], axis=1) / 2.0
    clad = flat_mesh(walls, wall_colors, outward=np.repeat(out_dir, 2, axis=0))
    top = flat_mesh(quad_triangles(_band(outer, inner, h, h)), palette.TEAK_LIGHT.linear,
                    outward=(0.0, 0.0, 1.0))
    in_dir = -np.concatenate([inner + np.roll(inner, -1, axis=0), np.zeros((len(inner), 1))], axis=1)
    well = flat_mesh(quad_triangles(_band(inner, inner, water - 1.0, h)), palette.TEAK_DARK.linear,
                     outward=np.repeat(in_dir, 2, axis=0))
    surface = polygon_cap(inner, water, palette.WATER.linear)
    return (_part([clad, top, well], box, "tub"),
            _part([surface], box, "water", "water", casts_shadow=False))


def _swing(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A pine A-frame swing: the top beam along the sprite's width, splayed legs at
    each end, two blue seats on ropes."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    w, d, h = box.half_w, box.half_d, height_cm
    beam_h = min(12.0, 0.08 * h)
    beam_w = min(10.0, 0.12 * box.depth)
    wood: list[Mesh] = [slab(-w + 3.0, w - 3.0, -beam_w / 2.0, beam_w / 2.0, h - beam_h, h,
                             palette.PINE.linear, 1.0)]
    leg = min(9.0, 0.06 * box.width)
    top_x = w - min(14.0, 0.07 * box.width)
    foot_x = w - min(6.0, 0.03 * box.width) - leg / 2.0
    for sign in (-1.0, 1.0):
        for side in (-1.0, 1.0):
            wood.append(beam_under((sign * top_x, 0.0, h - beam_h),
                                   (sign * foot_x, side * (d - leg), 0.0), leg, 0.7 * leg,
                                   palette.PINE_DARK.linear, h - 0.5 * beam_h, across=(1.0, 0.0, 0.0)))
    seat_z = min(45.0, 0.3 * h)
    seat_w = min(42.0, 0.21 * box.width)
    seat_d = min(15.0, 0.4 * box.depth)
    seats = []
    ropes = []
    for sx in (-0.16 * box.width, 0.16 * box.width):
        seats.append(slab(sx - seat_w / 2.0, sx + seat_w / 2.0, -seat_d / 2.0, seat_d / 2.0,
                          seat_z - 4.0, seat_z, palette.PLASTIC_BLUE.linear, 1.5))
        for dx in (-seat_w / 2.0 + 3.0, seat_w / 2.0 - 3.0):
            ropes.append(((sx + dx, 0.0, h - beam_h), (sx + dx, 0.0, seat_z)))
    rope = rod([a for a, _b in ropes], [b for _a, b in ropes], 0.8, palette.SANDSTONE_DARK.linear,
               sides=4)
    return (_part([*wood, *seats, rope], box, "swing"),)


def _hammock(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A walnut hammock stand — a base spreader, two feet, two posts to the hooks —
    and a striped teal-and-cream hammock sagging between two spreader bars."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    w, d, h = box.half_w, box.half_d, height_cm
    base = min(8.0, 0.1 * h)
    post = min(9.0, 0.04 * box.width)
    post_x = w - min(14.0, 0.05 * box.width)
    stand = [slab(-post_x, post_x, -5.0, 5.0, 0.0, base, palette.TIMBER.linear, 0.8)]
    foot = min(0.7 * d, d - 1.0)  # the sprite's end bars: 70 % of the depth
    for sign in (-1.0, 1.0):
        x = sign * post_x
        stand.append(slab(x - post / 2.0, x + post / 2.0, -foot, foot, 0.0, base, palette.TIMBER.linear, 0.8))
        stand.append(slab(x - post / 2.0, x + post / 2.0, -post / 2.0, post / 2.0, base, h,
                          palette.WALNUT_LIGHT.linear, 0.8))
        stand.append(beam((sign * (post_x - 0.25 * post_x), 0.0, base),
                          (sign * (post_x - post / 2.0), 0.0, base + 0.45 * (h - base)), 6.0, 4.0,
                          palette.TIMBER.linear, across=(0.0, 1.0, 0.0)))
    a = box.width / 3.0
    b = min(34.0 / 120.0 * box.depth, d - 2.0)
    end_z, low_z = 0.72 * h, 0.42 * h
    strips, across = 24, 6
    xs = np.linspace(-a, a, strips + 1)
    triangles: list[F64] = []
    colors: list[Color] = []
    for i in range(strips):
        color = palette.CANVAS_TEAL.linear if i % 2 == 0 else palette.CANVAS_CREAM.linear
        quads = []
        for x0, x1 in ((xs[i], xs[i + 1]),):
            for j in range(across):
                v0, v1 = -1.0 + 2.0 * j / across, -1.0 + 2.0 * (j + 1) / across

                def point(x: float, v: float) -> tuple[float, float, float]:
                    t = x / a
                    width = b * (0.25 + 0.75 * math.sqrt(max(0.0, 1.0 - t * t)))
                    sag = (end_z - low_z) * (1.0 - t * t)
                    cradle = 0.12 * width * (1.0 - v * v)
                    return (x, v * width, end_z - sag - cradle)

                quads.append([point(x0, v0), point(x1, v0), point(x1, v1), point(x0, v1)])
        tri = quad_triangles(np.asarray(quads))
        triangles += [tri, tri[:, [0, 2, 1]]]  # both faces
        colors += [color] * (2 * len(tri))
    fabric = flat_mesh(np.concatenate(triangles), np.asarray(colors))
    bars = []
    ropes = []
    for sign in (-1.0, 1.0):
        bx = sign * a
        width = b * 0.25
        bars.append(beam((bx, -width - 2.0, end_z), (bx, width + 2.0, end_z), 3.0, 3.0,
                         palette.TIMBER.linear))
        for v in np.linspace(-1.0, 1.0, 5):
            ropes.append(((sign * (post_x - post / 2.0), 0.0, h - 4.0), (bx, v * width, end_z)))
    rope = rod([s for s, _e in ropes], [e for _s, e in ropes], 0.6, palette.SANDSTONE_DARK.linear, sides=4)
    return (_part([*stand, *bars, rope, fabric], box, "hammock"),)


build_sandbox: Final = BuiltBuilder(_sandbox, "sandbox")
build_trampoline: Final = BuiltBuilder(_trampoline, "trampoline")
build_hot_tub: Final = BuiltBuilder(_hot_tub, "hot tub")
build_swing: Final = BuiltBuilder(_swing, "swing")
build_hammock: Final = BuiltBuilder(_hammock, "hammock")

BUILDERS: Final[dict[str, BuiltBuilder]] = {
    "SANDBOX": build_sandbox,
    "TRAMPOLINE": build_trampoline,
    "HOT_TUB": build_hot_tub,
    "SWING": build_swing,
    "HAMMOCK": build_hammock,
}


def register(registry: BuilderRegistry) -> None:
    for kind, builder in BUILDERS.items():
        registry.register(kind, builder)
