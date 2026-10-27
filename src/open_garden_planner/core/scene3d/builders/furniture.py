"""Furniture: tables, seats, a parasol, a grill, a fire pit, a pot (Phase 17 L4, #388).

``TABLE_RECTANGULAR``, ``TABLE_ROUND``, ``CHAIR``, ``BENCH``, ``PARASOL``,
``LOUNGER``, ``BBQ_GRILL``, ``FIRE_PIT``, ``PLANTER_POT`` and ``PICNIC_TABLE``
— each one the 3D twin of its 2D sprite (``scripts/generate_object_sprites.py``
``build_<object>``): the same parts where the sprite shows them, the same
materials (``palette``, mirrored from the shared ``MATERIALS``), the same side
up — a chair's back, a bench's backrest and a lounger's head end lie on the
sprite's TOP edge, the item's local +y (``kit.ObjectBox``).

The truth rules (``common``): the top of every object is its height EXACTLY — a
backrest's top rail, a parasol's finial, a kettle's lid, a fire pit's stones;
nothing reaches beyond the footprint (``verify_builder`` holds every builder to
10 cm, issue #388's truth gate); every kind has a default height
(``core/object_height.DEFAULT_HEIGHTS_CM``) and casts its shadow.
Seats, rails and the like keep their real-world heights and give way to a low
``height`` (a seat is never above two thirds of the object).

Not built, because the top is the height: a parasol's open-top vent, a grill's
lid handle above its dome, a trampoline net (``play``). Not built, because they
are 2D detail: screws, grain, a cushion's tufts.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from ..build import BuilderRegistry
from ..mesh import Mesh, MeshPart
from ..record import Record
from . import palette
from .beds import round_profile
from .common import BuiltBuilder, plain_block
from .kit import (
    ObjectBox,
    ball,
    beam,
    board,
    cylinder,
    object_box,
    placed,
    rod,
    seed_of,
    slab,
    slabs,
    turned,
    unit_circle,
)
from .primitives import flat_mesh, prism

#: The kinds this module builds.
KINDS: Final[tuple[str, ...]] = (
    "TABLE_RECTANGULAR", "TABLE_ROUND", "CHAIR", "BENCH", "PARASOL", "LOUNGER",
    "BBQ_GRILL", "FIRE_PIT", "PLANTER_POT", "PICNIC_TABLE",
)

#: A table top is this thick (cm), and never more than this share of the table.
TOP_CM: Final = 4.0
#: The seat of a chair, a bench or a picnic table: its usual height (cm) and the
#: largest share of the object's height it may take.
SEAT_CM: Final = 45.0
SEAT_SHARE: Final = 0.6

Color = tuple[float, float, float, float]


def _seat(height_cm: float, usual: float = SEAT_CM) -> float:
    return min(usual, SEAT_SHARE * height_cm)


def _top(height_cm: float) -> float:
    return min(TOP_CM, 0.12 * height_cm)


def _part(meshes: list[Mesh], box: ObjectBox, name: str, kind: str = "vc") -> MeshPart:
    return MeshPart(placed(meshes, box), kind, name=name)


# ── tables ───────────────────────────────────────────────────────────────────


def _table_rectangular(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """Oak breadboard top (six planks between two end boards), an apron, four legs."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    w, d, h = box.half_w, box.half_d, height_cm
    top = _top(h)
    inset = min(6.0, 0.08 * min(box.width, box.depth))
    end = min(12.0, 0.08 * box.width)
    meshes = [slab(-w, -w + end, -d, d, h - top, h, palette.PLANK.linear, 0.8),
              slab(w - end, w, -d, d, h - top, h, palette.PLANK.linear, 0.8)]
    planks, gap = 6, min(1.3, 0.02 * box.depth)
    width = (box.depth - gap * (planks - 1)) / planks
    for index in range(planks):
        y = -d + width / 2.0 + index * (width + gap)
        meshes.append(board((-w + end + 0.6, y), (w - end - 0.6, y), width, h - top, h,
                            palette.OAK_LIGHT.linear if index % 2 else palette.PLANK.linear))
    apron = min(8.0, 0.12 * h)
    rail = 2.5
    meshes += [
        slab(-w + inset, w - inset, -d + inset, -d + inset + rail, h - top - apron, h - top,
             palette.PLANK_GROOVE.linear),
        slab(-w + inset, w - inset, d - inset - rail, d - inset, h - top - apron, h - top,
             palette.PLANK_GROOVE.linear),
        slab(-w + inset, -w + inset + rail, -d + inset, d - inset, h - top - apron, h - top,
             palette.PLANK_GROOVE.linear),
        slab(w - inset - rail, w - inset, -d + inset, d - inset, h - top - apron, h - top,
             palette.PLANK_GROOVE.linear),
    ]
    leg = min(5.5, 0.1 * min(box.width, box.depth))
    meshes.append(slabs([(sx * (w - inset - leg / 2), sy * (d - inset - leg / 2), leg, leg)
                         for sx in (-1, 1) for sy in (-1, 1)], 0.0, h - top,
                        palette.PLANK.linear, 0.6))
    return (_part(meshes, box, "table"),)


def _table_round(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A round teak top with a chamfered edge on four legs."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    r, h = box.radius, height_cm
    top = _top(h)
    cut = min(1.2, 0.3 * top)
    disc = turned([(0.0, h - top), (r - cut, h - top), (r, h - top + cut), (r, h - cut),
                   (r - cut, h), (0.0, h)], palette.TEAK.linear)
    leg = min(5.0, 0.12 * r)
    at = 0.55 * r * unit_circle(4, 45.0)
    legs = slabs([(x, y, leg, leg) for x, y in at], 0.0, h - top, palette.TEAK_DARK.linear, 0.6,
                 angles_deg=[45.0, 135.0, 225.0, 315.0])
    ring_z = min(0.3 * h, h - top - 2.0)
    braces = rod([(at[i, 0], at[i, 1], ring_z) for i in range(4)],
                 [(at[(i + 1) % 4, 0], at[(i + 1) % 4, 1], ring_z) for i in range(4)],
                 min(1.2, 0.03 * r), palette.TEAK_DARK.linear)
    return (_part([disc, legs, braces], box, "table"),)


# ── seats ────────────────────────────────────────────────────────────────────


def _chair(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """An oak armchair with a cream cushion; the backrest on the sprite's top edge."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    h = height_cm
    seat = _seat(h)
    frame = min(5.0, 0.3 * seat)
    x0, y_front = box.sprite(4, 47, 50, 50)
    x1, y_back = box.sprite(46, 9, 50, 50)
    meshes = [slab(x0, x1, y_front, y_back, seat - frame, seat, palette.PLANK.linear, 1.0)]
    cx0, cy0 = box.sprite(8, 44, 50, 50)
    cx1, cy1 = box.sprite(42, 13, 50, 50)
    cushion = min(5.0, 0.5 * (h - seat))
    meshes.append(slab(cx0, cx1, cy0, cy1, seat, seat + cushion, palette.CANVAS_CREAM.linear, 2.0))
    arm_top = min(seat + 21.0, seat + 0.55 * (h - seat))
    for u0, u1 in ((1, 7), (43, 49)):
        ax0, ay0 = box.sprite(u0, 46, 50, 50)
        ax1, ay1 = box.sprite(u1, 8, 50, 50)
        meshes.append(slab(ax0, ax1, ay0, ay1, arm_top - 3.0, arm_top, palette.PLANK.linear, 0.8))
        meshes.append(slab(ax0, ax1, ay0, ay0 + min(4.0, 0.5 * (ay1 - ay0)), seat, arm_top - 3.0,
                           palette.PLANK_GROOVE.linear))
    bx0, by0 = box.sprite(1, 10, 50, 50)
    bx1, by1 = box.sprite(49, 1, 50, 50)
    back = (by0 + by1) / 2.0
    half_t = min(2.0, 0.5 * (by1 - by0))
    rail = min(8.0, 0.3 * (h - seat))
    meshes.append(slab(bx0, bx1, back - half_t, back + half_t, h - rail, h, palette.PLANK.linear, 0.8))
    low_rail = seat + min(12.0, 0.35 * (h - seat))
    meshes.append(slab(bx0, bx1, back - half_t, back + half_t, low_rail, low_rail + rail * 0.6,
                       palette.PLANK.linear, 0.6))
    slat = (bx1 - bx0) / 9.0
    meshes.append(slabs([(bx0 + slat * (2 * k + 1.5), back, slat * 0.8, 2.0 * half_t * 0.8)
                         for k in range(4)], seat, h - rail, palette.OAK_LIGHT.linear, 0.3))
    leg = min(4.0, 0.08 * box.width)
    corners = [box.sprite(u, v, 50, 50) for u in (7, 43) for v in (12, 44)]
    meshes.append(slabs([(x, y, leg, leg) for x, y in corners], 0.0, seat - frame,
                        palette.PLANK_GROOVE.linear, 0.4))
    return (_part(meshes, box, "chair"),)


def _bench(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A teak garden bench on iron end frames; the backrest on the sprite's top edge."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    w, h = box.half_w, height_cm
    seat = _seat(h, 42.0)
    arm = min(seat + 22.0, seat + 0.55 * (h - seat))
    plank_t = min(4.0, 0.25 * seat)
    view = (180.0, 60.0)
    # iron end frames: front and back legs, a foot rail, an arm post; the back upright
    _, y_front = box.sprite(0, 54, *view)
    _, y_back = box.sprite(0, 6, *view)
    _, y_rest = box.sprite(0, 9.5, *view)
    iron: list[Mesh] = []
    teak: list[Mesh] = []
    for u0, u1 in ((4.0, 12.0), (168.0, 176.0)):
        x0, _ = box.sprite(u0, 0, *view)
        x1, _ = box.sprite(u1, 0, *view)
        iron.append(slab(x0, x1, y_front, y_front + 5.0, 0.0, arm - 3.0, palette.IRON.linear, 0.6))
        iron.append(slab(x0, x1, y_rest - 2.5, y_rest + 2.5, 0.0, h, palette.IRON.linear, 0.6))
        iron.append(slab(x0, x1, y_front, y_rest, 6.0, 10.0, palette.IRON.linear))
        iron.append(slab(x0, x1, y_front, y_rest, seat - plank_t - 4.0, seat - plank_t,
                         palette.IRON.linear))
        cap0, _ = box.sprite(u0 - 2.0, 0, *view)
        cap1, _ = box.sprite(u1 + 2.0, 0, *view)
        teak.append(slab(max(cap0, -w), min(cap1, w), y_front - 1.0, y_rest - 3.0, arm - 3.0, arm,
                         palette.TEAK.linear, 0.8))
    sx0, _ = box.sprite(10, 0, *view)
    sx1, _ = box.sprite(170, 0, *view)
    _, sy0 = box.sprite(0, 56, *view)
    _, sy1 = box.sprite(0, 18, *view)
    gap = 1.6
    width = (sy1 - sy0 - 2 * gap) / 3.0
    for index in range(3):
        y = sy0 + width / 2.0 + index * (width + gap)
        teak.append(board((sx0, y), (sx1, y), width, seat - plank_t, seat,
                          palette.TEAK_LIGHT.linear if index == 1 else palette.TEAK.linear))
    slat = min(10.0, 0.4 * (h - seat))
    for z1 in (h, seat + min(18.0, 0.55 * (h - seat))):
        teak.append(slab(sx0, sx1, y_rest - 1.5, y_rest + 1.5, z1 - slat, z1, palette.TEAK.linear, 0.6))
    return (_part(iron + teak, box, "bench"),)


def _lounger(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """An aluminium sun lounger: flat seat and leg cushions, the back raised toward the
    sprite's top edge (its head pillow)."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    h = height_cm
    view = (70.0, 190.0)
    rail_top = min(30.0, 0.38 * h)
    rail_t = min(6.0, 0.3 * rail_top)
    cushion = min(8.0, 0.15 * h)
    metal: list[Mesh] = []
    for u0, u1 in ((3.0, 10.0), (60.0, 67.0)):
        x0, y0 = box.sprite(u0, 186, *view)
        x1, y1 = box.sprite(u1, 4, *view)
        metal.append(slab(x0, x1, y0, y1, rail_top - rail_t, rail_top, palette.STEEL.linear, 1.0))
        leg = x1 - x0
        metal.append(slabs([((x0 + x1) / 2.0, y0 + leg, leg, leg), ((x0 + x1) / 2.0, y1 - leg, leg, leg)],
                           0.0, rail_top - rail_t, palette.STEEL_DARK.linear, 0.4))
    fx0, _ = box.sprite(10, 0, *view)
    fx1, _ = box.sprite(60, 0, *view)
    fabric: list[Mesh] = []
    for v0, v1 in ((151.0, 184.0), (99.0, 148.0)):
        _, y0 = box.sprite(0, v1, *view)
        _, y1 = box.sprite(0, v0, *view)
        fabric.append(slab(fx0, fx1, y0, y1, rail_top, rail_top + cushion, palette.CANVAS_BLUE.linear, 2.5))
    _, hinge = box.sprite(0, 96, *view)
    _, head = box.sprite(0, 8, *view)
    thick = cushion
    run = head - hinge
    base = rail_top + cushion / 2.0
    # the back's upper end lies ``thick / 2 · cos(tilt)`` under the height, so its top
    # corner is the height: the tilt depends on that end, so settle it (converges at once)
    end_z = h
    for _ in range(6):
        end_z = h - (thick / 2.0) * math.cos(math.atan2(end_z - base, run))
    rise = end_z - base
    start = np.array([0.0, hinge, base])
    end = np.array([0.0, head, end_z])
    pillow_at = start + 0.72 * (end - start)
    fabric.append(beam(start, pillow_at, fx1 - fx0, thick, palette.CANVAS_BLUE.linear,
                       across=(1.0, 0.0, 0.0)))
    fabric.append(beam(pillow_at, end, fx1 - fx0 - 4.0, thick, palette.CANVAS_CREAM.linear,
                       across=(1.0, 0.0, 0.0)))
    strut_y = hinge + 0.6 * run
    strut_z = rail_top + 0.6 * rise - thick / 2.0
    metal.append(rod([(sx, strut_y, rail_top) for sx in (fx0 + 3.0, fx1 - 3.0)],
                     [(sx, strut_y, strut_z) for sx in (fx0 + 3.0, fx1 - 3.0)], 1.0,
                     palette.STEEL_DARK.linear))
    return (_part(metal + fabric, box, "lounger"),)


def _picnic_table(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """An oak picnic table: a five-board top, two bench boards, A-frame legs."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    d, h = box.half_d, height_cm
    view = (180.0, 150.0)
    top = _top(h)
    seat = _seat(h)
    meshes: list[Mesh] = []
    x0, _ = box.sprite(6, 0, *view)
    x1, _ = box.sprite(174, 0, *view)
    _, ty0 = box.sprite(0, 112, *view)
    _, ty1 = box.sprite(0, 38, *view)
    gap = 1.4
    width = (ty1 - ty0 - 4 * gap) / 5.0
    for index in range(5):
        y = ty0 + width / 2.0 + index * (width + gap)
        meshes.append(board((x0, y), (x1, y), width, h - top, h,
                            palette.OAK_LIGHT.linear if index % 2 else palette.PLANK.linear))
    bx0, _ = box.sprite(14, 0, *view)
    bx1, _ = box.sprite(166, 0, *view)
    for v0, v1 in ((6.0, 30.0), (120.0, 144.0)):
        _, y0 = box.sprite(0, v1, *view)
        _, y1 = box.sprite(0, v0, *view)
        half = (y1 - y0 - gap) / 2.0
        for y in (y0 + half / 2.0, y1 - half / 2.0):
            meshes.append(board((bx0, y), (bx1, y), half, seat - top, seat, palette.PLANK.linear))
    leg_w = min(7.0, 0.05 * box.width)
    for u in (16.0, 164.0):
        x, _ = box.sprite(u, 0, *view)
        meshes.append(slab(x - leg_w / 2.0, x + leg_w / 2.0, ty0, ty1, h - top - 6.0, h - top,
                           palette.PLANK_GROOVE.linear))
        meshes.append(slab(x - leg_w / 2.0, x + leg_w / 2.0, -d + 1.0, d - 1.0, seat - top - 6.0,
                           seat - top, palette.PLANK_GROOVE.linear))
        for sign in (-1.0, 1.0):
            meshes.append(beam((x, 0.0, h - top - 3.0), (x, sign * (d - 4.0), 0.0), leg_w, 4.0,
                               palette.PLANK_GROOVE.linear, across=(1.0, 0.0, 0.0)))
    return (_part(meshes, box, "picnic table"),)


# ── the round ones ───────────────────────────────────────────────────────────


def _parasol(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A market parasol: a concrete base, a pole, eight cream and red panels with a
    valance, ribs underneath and a brass finial at the very top."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    h = height_cm
    reach = box.radius - 2.0
    base_r = min(25.0, 0.3 * box.radius)
    base_h = min(8.0, 0.05 * h)
    finial = min(7.0, 0.05 * h)
    apex = h - finial - 2.0
    # the canopy drops a third of its reach — never more than a third of the apex's
    # height: a 30 cm parasol put its rim and pole base under the ground (3D review of #388)
    drop = min(0.32 * reach, 0.35 * apex)
    rim = apex - drop
    valance = min(8.0, 0.25 * drop + 2.0, 0.5 * rim)
    pole_r = min(2.5, 0.2 * base_r)
    frame = [cylinder(0.0, 0.0, base_r, 0.0, base_h, palette.CONCRETE.linear, top_radius=base_r * 0.85),
             cylinder(0.0, 0.0, pole_r, base_h, h - finial, palette.STEEL.linear, segments=8),
             cylinder(0.0, 0.0, min(3.5, 1.4 * pole_r), h - finial, h, palette.BRASS.linear,
                      top_radius=0.0, segments=8)]
    panels = 8
    rim_points = reach * unit_circle(2 * panels)  # every other one is a panel's middle
    tip = np.array([0.0, 0.0, apex])
    triangles: list[np.ndarray] = []
    colors: list[Color] = []
    for index in range(panels):
        a, m, b = (rim_points[(2 * index + k) % (2 * panels)] for k in range(3))
        color = palette.CANVAS_CREAM.linear if index % 2 == 0 else palette.CANVAS_RED.linear
        for p, q in ((a, m), (m, b)):
            upper = np.array([tip, [*p, rim], [*q, rim]])
            triangles += [upper, upper[[0, 2, 1]]]  # both faces: seen from below too
            lower = np.array([[*p, rim], [*q, rim - valance], [*q, rim]])
            lower2 = np.array([[*p, rim], [*p, rim - valance], [*q, rim - valance]])
            triangles += [lower, lower[[0, 2, 1]], lower2, lower2[[0, 2, 1]]]
            colors += [color] * 6
    canopy = flat_mesh(np.stack(triangles), np.asarray(colors))
    ribs = rod([(0.0, 0.0, max(base_h + 1.0, rim - 0.35 * drop - 10.0))] * panels,
               [(x * 0.98, y * 0.98, rim - 1.0) for x, y in rim_points[::2]], 0.8,
               palette.STEEL.linear, sides=4)
    return (_part([*frame, ribs], box, "pole"), _part([canopy], box, "canopy"))


def _bbq_grill(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A black kettle grill on three steel legs, its oak side shelf on the sprite's
    right; the lid's dome is the top."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    h = height_cm
    r = box.radius
    kettle = 0.7 * r
    cx = -0.15 * r
    centre = h - 0.95 * kettle
    bottom = centre - 0.8 * kettle
    if bottom < 0.15 * h:  # a low grill: the kettle sits on short legs
        kettle = h / 1.9
        centre = h - 0.95 * kettle
        bottom = centre - 0.8 * kettle
    steps = 8
    bowl = [(kettle * math.sin(t), centre - 0.8 * kettle * math.cos(t))
            for t in np.linspace(0.0, math.pi / 2.0, steps + 1)]
    lid = [(kettle * 1.01 * math.cos(t), centre + 0.95 * kettle * math.sin(t))
           for t in np.linspace(0.0, math.pi / 2.0, steps + 1)]
    profile = [(0.0, bowl[0][1]), *bowl[1:], (kettle * 1.01, centre), *lid[1:]]
    colors = ([palette.ENAMEL_BLACK.linear] * steps + [palette.STEEL.linear]
              + [palette.ENAMEL_BLACK_LIGHT.linear] + [palette.ENAMEL_BLACK.linear] * (steps - 1))
    body = turned(profile, np.asarray(colors), cx, 0.0)
    feet = 0.82 * kettle * unit_circle(3, 0.0)
    legs = rod([(cx + x, y, 0.0) for x, y in feet],
               [(cx + 0.5 * x, 0.5 * y, bottom + 2.0) for x, y in feet], min(1.6, 0.05 * r),
               palette.STEEL.linear)
    sx0, sx1 = 0.55 * r, 0.95 * r
    shelf_z = min(centre, h - 2.0)
    shelf = [slab(sx0, sx1, -0.5 * r, 0.5 * r, shelf_z - 2.5, shelf_z, palette.PLANK.linear, 0.6),
             rod([(cx + kettle * 0.9, s * 0.3 * r, centre - 4.0) for s in (-1, 1)],
                 [(sx0 + 1.0, s * 0.3 * r, shelf_z - 2.5) for s in (-1, 1)], 0.8,
                 palette.STEEL.linear, sides=4)]
    return (_part([body, legs, *shelf], box, "grill"),)


def _fire_pit(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A ring of fourteen sandstone wedges round an ash bed, three logs and embers."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    r, h = box.radius, height_cm
    count = 14
    inner, outer = 0.7 * r, 0.96 * r
    gap = math.radians(1.4)  # the sprite's 1.4 degrees each side of a stone
    rng = np.random.Generator(np.random.PCG64(seed_of(record, "fire pit")))
    light = rng.random(count) < 0.5
    stones = []
    for index in range(count):
        a0 = 2.0 * math.pi * index / count + gap
        a1 = 2.0 * math.pi * (index + 1) / count - gap
        arc = np.linspace(a0, a1, 4)
        ring = np.concatenate([np.stack([outer * np.cos(arc), outer * np.sin(arc)], axis=1),
                               np.stack([inner * np.cos(arc[::-1]), inner * np.sin(arc[::-1])], axis=1)])
        tone = palette.SANDSTONE_LIGHT if light[index] else palette.SANDSTONE
        stones.append(prism(ring, 0.0, h, tone.linear))
    bed_top = min(6.0, 0.2 * h)
    ash = cylinder(0.0, 0.0, 0.72 * r, 0.0, bed_top, palette.ASH_DARK.linear)
    log_r = min(4.0, 0.08 * r, 0.2 * h)
    log_z = bed_top + log_r
    logs = []
    for angle in (-32.0, 40.0, 100.0):
        a = math.radians(angle)
        half = 0.42 * r
        logs.append(rod([(-half * math.cos(a), -half * math.sin(a), log_z)],
                        [(half * math.cos(a), half * math.sin(a), log_z)], log_r,
                        palette.TIMBER.linear, sides=8))
    ember_at = 0.35 * r * rng.random((9, 1)) * unit_circle(9, float(rng.uniform(0, 40)))
    embers = [ball(float(x), float(y), bed_top, min(3.0, 0.06 * r),
                   (palette.EMBER_MID if k % 2 else palette.EMBER_DARK).linear, squash=0.5,
                   rings=4, segments=6) for k, (x, y) in enumerate(ember_at)]
    return (_part([*stones, ash, *logs, *embers], box, "fire pit"),)


def _planter_pot(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A tapered terracotta pot with a rim band, soil a little under the rim — the
    round container's own profile (``beds.round_profile``), in the sprite's colours."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    r, h = box.radius, height_cm
    soil = h - min(4.0, 0.1 * h)
    profile, wall = round_profile(r, h, "terracotta", soil)
    pot = turned(profile, palette.TERRACOTTA.linear)
    earth = cylinder(0.0, 0.0, r - wall, max(0.0, soil - 1.0), soil, palette.SOIL.linear)
    return (_part([pot, earth], box, "pot"),)


build_table_rectangular: Final = BuiltBuilder(_table_rectangular, "rectangular table")
build_table_round: Final = BuiltBuilder(_table_round, "round table")
build_chair: Final = BuiltBuilder(_chair, "chair")
build_bench: Final = BuiltBuilder(_bench, "bench")
build_parasol: Final = BuiltBuilder(_parasol, "parasol")
build_lounger: Final = BuiltBuilder(_lounger, "lounger")
build_bbq_grill: Final = BuiltBuilder(_bbq_grill, "grill")
build_fire_pit: Final = BuiltBuilder(_fire_pit, "fire pit")
build_planter_pot: Final = BuiltBuilder(_planter_pot, "planter pot")
build_picnic_table: Final = BuiltBuilder(_picnic_table, "picnic table")

BUILDERS: Final[dict[str, BuiltBuilder]] = {
    "TABLE_RECTANGULAR": build_table_rectangular,
    "TABLE_ROUND": build_table_round,
    "CHAIR": build_chair,
    "BENCH": build_bench,
    "PARASOL": build_parasol,
    "LOUNGER": build_lounger,
    "BBQ_GRILL": build_bbq_grill,
    "FIRE_PIT": build_fire_pit,
    "PLANTER_POT": build_planter_pot,
    "PICNIC_TABLE": build_picnic_table,
}


def register(registry: BuilderRegistry) -> None:
    for kind, builder in BUILDERS.items():
        registry.register(kind, builder)
