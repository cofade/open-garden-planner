"""Garden utilities: compost bin, cold frame, rain barrel, water tap, wheelbarrow,
bird bath (Phase 17 L4, #388).

The 3D twins of their sprites (``scripts/generate_object_sprites.py``
``build_<object>``) under the rules of ``furniture`` (its module docstring). What
the height is, per object:

- **compost bin**: its corner posts and top slats; the heap stays a hand under it;
- **cold frame**: the top of its high back — the sprite's top edge, where the
  hinges are; the glass lid slopes from there to the low front (a ``glass`` part:
  it casts no shadow);
- **rain barrel**: the lid's cap; the tap and the overflow spout point to the
  sprite's right, as drawn;
- **water tap**: the brass cross handle on its concrete post;
- **wheelbarrow**: the tub's rim; the wheel at the sprite's top, the handles at
  its bottom;
- **bird bath**: the basin's rim; the water a little under it (a ``water`` part).
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
    beam,
    cylinder,
    object_box,
    placed,
    rod,
    seed_of,
    slab,
    slabs,
    turned,
    turned_mesh,
)
from .primitives import F64, flat_mesh, polygon_cap, prism, quad_triangles

#: The kinds this module builds.
KINDS: Final[tuple[str, ...]] = (
    "COMPOST_BIN", "COLD_FRAME", "RAIN_BARREL", "WATER_TAP", "WHEELBARROW", "BIRD_BATH",
)

Color = tuple[float, float, float, float]


def _part(meshes: list[Mesh], box: ObjectBox, name: str, kind: str = "vc", *,
          casts_shadow: bool = True) -> MeshPart:
    return MeshPart(placed(meshes, box), kind, casts_shadow=casts_shadow, name=name)


def _compost_bin(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A slatted grey-wood bin: four corner posts, horizontal slats with gaps between
    them, a compost heap inside."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    w, d, h = box.half_w, box.half_d, height_cm
    post = min(9.0, 0.1 * min(box.width, box.depth))
    meshes = [slabs([(sx * (w - post / 2.0), sy * (d - post / 2.0), post, post)
                     for sx in (-1, 1) for sy in (-1, 1)], 0.0, h, palette.GREY_WOOD_DARK.linear, 0.8)]
    slat_h, gap = min(10.0, 0.4 * h), 2.0
    count = min(MAX_REPEATS // 10, max(1, int((h + gap) // (slat_h + gap))))
    if count * (slat_h + gap) < h - slat_h:  # a bin taller than the slats can cover: wider slats
        slat_h = (h + gap) / count - gap
    slat_t = min(2.5, 0.5 * post)
    tops = h - np.arange(count) * (slat_h + gap)
    for index, top in enumerate(tops):
        bottom = max(0.0, top - slat_h)
        color = (palette.GREY_WOOD if index % 2 == 0 else palette.GREY_WOOD_LIGHT).linear
        inset = post / 2.0 - slat_t / 2.0
        meshes += [
            slab(-w + post, w - post, -d + inset, -d + inset + slat_t, bottom, top, color),
            slab(-w + post, w - post, d - inset - slat_t, d - inset, bottom, top, color),
            slab(-w + inset, -w + inset + slat_t, -d + post, d - post, bottom, top, color),
            slab(w - inset - slat_t, w - inset, -d + post, d - post, bottom, top, color),
        ]
    heap_r = min(w, d) - post
    heap_top = max(1.0, min(0.6 * h, h - 10.0))
    if heap_r > 1.0:
        steps = 6
        dome = [(heap_r * math.cos(t), heap_top * math.sin(t))
                for t in np.linspace(0.0, math.pi / 2.0, steps + 1)]
        colors = [(palette.COMPOST if k < steps - 2 else palette.COMPOST_LIGHT).linear
                  for k in range(steps)]
        meshes.append(turned(dome, np.asarray(colors)))
    return (_part(meshes, box, "compost bin"),)


def _cycled(mesh: Mesh) -> Mesh:
    """``mesh`` with its axes cycled (x, y, z) → (y, z, x): a prism built in the plan
    becomes one standing in the y-z plane (a rotation: the winding survives)."""
    if not mesh.vertex_count:
        return mesh
    order = [2, 0, 1]
    return Mesh.from_arrays(mesh.positions[:, order], mesh.normals[:, order], mesh.colors, mesh.uvs,
                            mesh.indices)


def _cold_frame(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A pine box, high at the back (the sprite's top edge), low at the front, with a
    sloping three-pane glass lid; soil and seedlings inside."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    w, d, h = box.half_w, box.half_d, height_cm
    front = 0.62 * h
    t = min(5.0, 0.1 * min(box.width, box.depth))
    wood = palette.PINE.linear
    meshes: list[Mesh] = [slab(-w, w, d - t, d, 0.0, h, wood, 0.5),
                          slab(-w, w, -d, -d + t, 0.0, front, wood, 0.5)]
    side = np.array([[-d + t, 0.0], [d - t, 0.0], [d - t, h - (h - front) * t / box.depth],
                     [-d + t, front + (h - front) * t / box.depth]])
    for x0 in (-w, w - t):
        # the side's trapezoid in the (y, z) plane, extruded along x: built in the plan
        # as (y, z) → cycled into place
        meshes.append(_cycled(prism(side, x0, x0 + t, wood)))
    soil_top = min(6.0, 0.2 * front)
    meshes.append(slab(-w + t, w - t, -d + t, d - t, 0.0, soil_top, palette.SOIL.linear))
    rng = np.random.Generator(np.random.PCG64(seed_of(record, "cold frame")))
    seedlings = []
    for row in (-0.3, 0.3):
        for col in np.linspace(-0.75, 0.75, 6):
            x = col * (w - t) + rng.uniform(-1.5, 1.5)
            y = row * (d - t) + rng.uniform(-1.5, 1.5)
            seedlings.append(cylinder(x, y, min(2.5, 0.1 * d), soil_top, soil_top + min(6.0, 0.4 * front),
                                      palette.GRASS_BIT.linear, top_radius=0.0, segments=5))
    meshes += seedlings
    # the lid: the plane through the back's top edge and the front's top edge
    slope = np.array([0.0, box.depth, h - front])
    slope /= float(np.linalg.norm(slope))
    normal = np.array([0.0, -slope[2], slope[1]])  # up and toward the front
    rail = min(4.0, 0.5 * t + 1.0)

    def on_lid(x: float, y: float, below: float) -> F64:
        z = front + (h - front) * (y + d) / box.depth
        point: F64 = np.array([x, y, z]) - normal * below
        return point

    frame_color = palette.PINE_LIGHT.linear
    for x in (-w + rail / 2.0, -w / 3.0, w / 3.0, w - rail / 2.0):
        meshes.append(beam(on_lid(x, -d, rail / 2.0), on_lid(x, d, rail / 2.0), rail, rail,
                           frame_color, across=(1.0, 0.0, 0.0)))
    for y in (-d + rail / 2.0, d - rail / 2.0):
        meshes.append(beam(on_lid(-w, y, rail / 2.0), on_lid(w, y, rail / 2.0), rail, rail,
                           frame_color, across=(0.0, slope[1], slope[2])))
    panes = []
    for x0, x1 in ((-w, -w / 3.0), (-w / 3.0, w / 3.0), (w / 3.0, w)):
        quad = np.array([on_lid(x0, -d, rail * 0.6), on_lid(x1, -d, rail * 0.6),
                         on_lid(x1, d, rail * 0.6), on_lid(x0, d, rail * 0.6)])
        panes.append(flat_mesh(quad_triangles(quad[None]), palette.GLASS.linear, outward=normal))
    return (_part(meshes, box, "cold frame"),
            _part(panes, box, "glass", "glass", casts_shadow=False))


def _rain_barrel(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A green barrel with a waist, two hoops and a domed lid; a brass tap low and a
    steel overflow spout high, both toward the sprite's right."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    r, h = box.radius, height_cm
    body = 0.9 * r
    lid = min(4.0, 0.06 * h)
    profile = [(0.0, 0.0), (0.86 * body, 0.0), (0.97 * body, 0.25 * h), (body, 0.5 * h),
               (0.97 * body, 0.75 * h), (0.92 * body, h - lid), (0.88 * body, h - lid),
               (0.35 * body, h - 0.3 * lid), (0.2 * body, h), (0.0, h)]
    green, light = palette.PLASTIC_GREEN.linear, palette.PLASTIC_GREEN_LIGHT.linear
    colors = [green, green, green, green, green, light, light, light, light]
    barrel = turned(profile, np.asarray(colors))
    hoops = [turned([(0.97 * body + 0.6, z - 1.5), (0.97 * body + 0.6, z + 1.5)], light)
             for z in (0.25 * h, 0.75 * h)]
    hoops += [turned([(0.97 * body + 0.6, z + 1.5), (0.97 * body - 0.5, z + 1.5)], light)
              for z in (0.25 * h, 0.75 * h)]
    tap_z = min(12.0, 0.15 * h)
    tap = turned_mesh(cylinder(0.0, 0.0, min(1.6, 0.06 * r), 0.0, r - 0.88 * body + 1.0,
                               palette.BRASS.linear, segments=8), "y", 90.0)
    tap = tap.translated(0.88 * body, 0.0, tap_z)
    spout = turned_mesh(cylinder(0.0, 0.0, min(2.0, 0.07 * r), 0.0, r - 0.92 * body,
                                 palette.STEEL.linear, segments=8), "y", 90.0)
    spout = spout.translated(0.92 * body, 0.0, h - lid - 4.0)
    return (_part([barrel, *hoops, tap, spout], box, "rain barrel"),)


def _water_tap(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A concrete standpipe post with a brass tap: the spout toward the sprite's right,
    the cross handle on top."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    r, h = box.radius, height_cm
    side = 1.38 * r  # the sprite's 14 of 20: its corners stay inside the circle
    handle = min(3.0, 0.1 * h)
    pipe_top = h - handle
    post_top = pipe_top - min(7.0, 0.25 * h)
    half = side / 2.0
    meshes = [slab(-half, half, -half, half, 0.0, post_top, palette.CONCRETE.linear, 1.0),
              cylinder(0.0, 0.0, min(1.6, 0.2 * half), post_top, pipe_top, palette.BRASS.linear,
                       segments=8)]
    spout_len = 0.85 * r
    spout = turned_mesh(cylinder(0.0, 0.0, min(1.2, 0.15 * half), 0.0, spout_len, palette.BRASS.linear,
                                 segments=8), "y", 90.0)
    meshes.append(spout.translated(0.0, 0.0, pipe_top - 2.5))
    arm = min(4.2, 0.4 * r)
    bar = min(1.8, 0.2 * r)
    meshes += [slab(-arm, arm, -bar / 2.0, bar / 2.0, pipe_top, h, palette.BRASS.linear),
               slab(-bar / 2.0, bar / 2.0, -arm, arm, pipe_top, h, palette.BRASS.linear)]
    return (_part(meshes, box, "water tap"),)


def _frustum(bottom: F64, top: F64, z0: float, z1: float, color: Color) -> Mesh:
    """The sides of a frustum between two counter-clockwise rings of equal length."""
    low = np.concatenate([bottom, np.full((len(bottom), 1), z0)], axis=1)
    high = np.concatenate([top, np.full((len(top), 1), z1)], axis=1)
    quads = np.stack([low, np.roll(low, -1, axis=0), np.roll(high, -1, axis=0), high], axis=1)
    centre = np.array([*top.mean(axis=0), (z0 + z1) / 2.0])
    outward = quads.mean(axis=1) - centre
    outward[:, 2] = 0.0
    return flat_mesh(quad_triangles(quads), color, outward=np.repeat(outward, 2, axis=0))


def _wheelbarrow(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A green enamel tub of soil on a rubber wheel (the sprite's top) with oak
    handles and two steel legs (its bottom)."""
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    d, h = box.half_d, height_cm
    view = (60.0, 140.0)
    wheel = min(17.0, 0.12 * box.depth, 0.3 * h)
    wheel_y = d - wheel - 1.0
    tub_low = max(wheel * 1.2, 0.42 * h)
    _, front = box.sprite(0, 22, *view)
    _, back = box.sprite(0, 104, *view)
    rim_x, base_x = 0.42 * box.width, 0.25 * box.width
    top_ring = np.array([[-rim_x, back], [rim_x, back], [rim_x, front], [-rim_x, front]])
    bottom_ring = np.array([[-base_x, back + 0.15 * (front - back)], [base_x, back + 0.15 * (front - back)],
                            [base_x, front - 0.25 * (front - back)], [-base_x, front - 0.25 * (front - back)]])
    green = palette.ENAMEL_GREEN.linear
    lip = min(2.5, 0.1 * rim_x)
    inner_top = np.array([[-rim_x + lip, back + lip], [rim_x - lip, back + lip],
                          [rim_x - lip, front - lip], [-rim_x + lip, front - lip]])
    load = h - min(6.0, 0.2 * (h - tub_low))
    tub = [_frustum(bottom_ring, top_ring, tub_low, h, green),
           polygon_cap(bottom_ring, tub_low, green, up=False),
           flat_mesh(quad_triangles(np.stack([
               np.concatenate([top_ring, np.full((4, 1), h)], axis=1),
               np.concatenate([np.roll(top_ring, -1, axis=0), np.full((4, 1), h)], axis=1),
               np.concatenate([np.roll(inner_top, -1, axis=0), np.full((4, 1), h)], axis=1),
               np.concatenate([inner_top, np.full((4, 1), h)], axis=1)], axis=1)),
               palette.ENAMEL_GREEN_LIGHT.linear, outward=(0.0, 0.0, 1.0)),
           polygon_cap(inner_top, load, palette.SOIL.linear)]
    # the inner walls, from the lip down to the load
    inner_walls = _frustum(inner_top, inner_top, load - 0.5, h, green)
    tub.append(Mesh.from_arrays(inner_walls.positions, -inner_walls.normals, inner_walls.colors,
                                inner_walls.uvs, inner_walls.indices[:, [0, 2, 1]]))
    tyre_w = min(8.0, 0.25 * box.width)
    tyre = [(wheel * 0.55, -tyre_w / 2.0), (wheel * 0.9, -tyre_w / 2.0), (wheel, 0.0),
            (wheel * 0.9, tyre_w / 2.0), (wheel * 0.55, tyre_w / 2.0)]
    wheel_mesh = turned([(p[0], p[1]) for p in tyre], palette.RUBBER.linear, segments=16)
    hub = cylinder(0.0, 0.0, wheel * 0.55, -tyre_w / 2.0 + 0.5, tyre_w / 2.0 - 0.5, palette.STEEL.linear,
                   bottom=True, segments=12)
    wheel_part = turned_mesh(Mesh.merge([wheel_mesh, hub]), "y", 90.0).translated(0.0, wheel_y, wheel)
    steel = palette.STEEL.linear
    fork = rod([(sx, wheel_y, wheel) for sx in (-tyre_w / 2.0 - 1.0, tyre_w / 2.0 + 1.0)],
               [(sx * 2.0, front - 0.2 * (front - back), tub_low) for sx in (-tyre_w / 2.0 - 1.0,
                                                                              tyre_w / 2.0 + 1.0)],
               1.2, steel)
    handle_x = 0.3 * box.width
    _, grip_y = box.sprite(0, 134, *view)
    handles = rod([(sx * handle_x, front - 0.3 * (front - back), tub_low + 2.0) for sx in (-1, 1)],
                  [(sx * handle_x * 1.1, grip_y, min(0.75 * h, h - 3.0)) for sx in (-1, 1)],
                  min(2.2, 0.06 * box.width), palette.PLANK.linear)
    grips = rod([(sx * handle_x * 1.08, grip_y + 8.0, min(0.75 * h, h - 3.0) - 1.0) for sx in (-1, 1)],
                [(sx * handle_x * 1.1, grip_y, min(0.75 * h, h - 3.0)) for sx in (-1, 1)],
                min(2.6, 0.07 * box.width), palette.RUBBER.linear)
    legs = rod([(sx * base_x, back + 0.3 * (front - back), tub_low) for sx in (-1, 1)],
               [(sx * base_x * 1.05, back + 0.2 * (front - back), 0.0) for sx in (-1, 1)], 1.4, steel)
    return (_part([*tub, wheel_part, fork, handles, grips, legs], box, "wheelbarrow"),)


def _bird_bath(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    """A stone bird bath: a plinth, a turned pedestal and a shallow basin whose rim is
    the item's circle; water a little under the rim, a leaf floating on it."""
    box = object_box(record)
    if box is None:
        return plain_block(record, height_cm)
    r, h = box.radius, height_cm
    basin = min(12.0, 0.2 * h)
    plinth = min(6.0, 0.1 * h)
    stone, light = palette.STONE.linear, palette.STONE_LIGHT.linear
    pedestal = turned([(0.0, 0.0), (0.55 * r, 0.0), (0.55 * r, plinth), (0.32 * r, plinth),
                       (0.24 * r, 0.5 * (h - basin)), (0.3 * r, h - basin), (0.0, h - basin)], stone)
    water_z = h - min(3.0, 0.3 * basin)
    bowl = turned([(0.3 * r, h - basin), (0.9 * r, h - 0.45 * basin), (r, h - 2.0), (0.97 * r, h),
                   (0.82 * r, h), (0.72 * r, water_z - 1.0), (0.0, h - 0.7 * basin)],
                  np.asarray([stone, stone, light, light, stone, stone]))
    angle = np.arange(24) * (2.0 * math.pi / 24)
    surface = polygon_cap(np.stack([0.78 * r * np.cos(angle), 0.78 * r * np.sin(angle)], axis=1),
                          water_z, palette.WATER.linear)
    leaf = flat_mesh(np.array([[[0.25 * r, -0.2 * r, water_z + 0.2], [0.33 * r, -0.12 * r, water_z + 0.2],
                                [0.22 * r, -0.08 * r, water_z + 0.2]]]),
                     palette.GRASS_BIT.linear, outward=(0.0, 0.0, 1.0))
    return (_part([pedestal, bowl, leaf], box, "bird bath"),
            _part([surface], box, "water", "water", casts_shadow=False))


build_compost_bin: Final = BuiltBuilder(_compost_bin, "compost bin")
build_cold_frame: Final = BuiltBuilder(_cold_frame, "cold frame")
build_rain_barrel: Final = BuiltBuilder(_rain_barrel, "rain barrel")
build_water_tap: Final = BuiltBuilder(_water_tap, "water tap")
build_wheelbarrow: Final = BuiltBuilder(_wheelbarrow, "wheelbarrow")
build_bird_bath: Final = BuiltBuilder(_bird_bath, "bird bath")

BUILDERS: Final[dict[str, BuiltBuilder]] = {
    "COMPOST_BIN": build_compost_bin,
    "COLD_FRAME": build_cold_frame,
    "RAIN_BARREL": build_rain_barrel,
    "WATER_TAP": build_water_tap,
    "WHEELBARROW": build_wheelbarrow,
    "BIRD_BATH": build_bird_bath,
}


def register(registry: BuilderRegistry) -> None:
    for kind, builder in BUILDERS.items():
        registry.register(kind, builder)
