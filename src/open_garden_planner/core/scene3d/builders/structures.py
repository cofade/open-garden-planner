"""Garden structures: pergola, trellis, greenhouse (Phase 17 L4.3, #388).

Mostly air — and built as such: posts, beams, rafters, slats and glass, never a
block. Their 2D shadows are NOT what these cast: the 2D sun study extrudes the
whole footprint of an item with a height (a pergola's, a trellis's, a
greenhouse's) as a solid prism, and the meshes here are open frames and glass
that casts no shadow (``ogp-lush-cinematic`` §4). The same porosity question the
fences raise (issue #440); the 3D view shows what is built.

- **PERGOLA** (the sprite ``build_pergola``): four posts, two beams along the
  sprite's width on them, nine rafters along its depth on top — the rafters' top
  is the height. Its default height (250 cm, since L4's second owner pass) casts
  its whole footprint in 2D, these open rafters in 3D.
- **TRELLIS** (no sprite: a ``LATTICE`` fill in the item's colour, so ``tinted``):
  a post at each end of the footprint's LONG side, a top and a bottom rail and a
  diagonal lattice between them, in the vertical plane through the footprint's
  middle — what a climber is tied to (L3 grows climbers up to it).
- **GREENHOUSE** (a ``GLASS`` fill in the item's colour): an aluminium frame on a
  concrete kerb, glass walls, glass gables and a pitched glass roof along the
  long side; its ridge beam's top is the height. The glass is ``tinted`` (the
  item's fill), translucent and casts no shadow. A footprint that is not a box
  gets the gable roof of ``roofs`` in glass over its walls.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from ..build import BuilderRegistry
from ..mesh import Mesh, MeshPart
from ..record import Record
from . import palette
from .common import BuiltBuilder, footprint_of, has_one_plain_ring, plain_block
from .kit import (
    MAX_REPEATS,
    ObjectBox,
    beam,
    beam_under,
    object_box,
    placed,
    slab,
    slabs,
    turned_mesh,
)
from .primitives import F64, flat_mesh, quad_triangles
from .roofs import RoofStyle, bounding_box_ridge, gable_roof

#: The kinds this module builds.
KINDS: Final[tuple[str, ...]] = ("PERGOLA", "TRELLIS", "GREENHOUSE")

#: A tinted part's shading weight (the sink multiplies it with the item's colour).
SHADE: Final = (0.82, 0.82, 0.82, 1.0)
#: A greenhouse's eaves stand at this share of its ridge height (the spike's).
EAVE_SHARE: Final = 0.7
#: The greenhouse's concrete kerb (cm) and its frame's bar (cm).
KERB_CM: Final = 15.0
BAR_CM: Final = 5.0

Color = tuple[float, float, float, float]


def _part(meshes: list[Mesh], box: ObjectBox, name: str, kind: str = "vc", *, tinted: bool = False,
          casts_shadow: bool = True) -> MeshPart:
    return MeshPart(placed(meshes, box), kind, casts_shadow=casts_shadow, tinted=tinted, name=name)


def _pergola(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    w, d, h = box.half_w, box.half_d, height_cm
    post = min(14.0, 0.06 * min(box.width, box.depth))
    inset = min(10.0, 0.04 * min(box.width, box.depth))
    rafter_h = min(12.0, 0.06 * h)
    beam_h = min(18.0, 0.08 * h)
    deck = h - rafter_h
    meshes = [slabs([(sx * (w - inset - post / 2.0), sy * (d - inset - post / 2.0), post, post)
                     for sx in (-1, 1) for sy in (-1, 1)], 0.0, deck - beam_h,
                    palette.PLANK_GROOVE.linear, 1.0)]
    beam_w = min(10.0, 0.8 * post)
    for sy in (-1.0, 1.0):
        y = sy * (d - inset - post / 2.0)
        meshes.append(slab(-w + 1.0, w - 1.0, y - beam_w / 2.0, y + beam_w / 2.0, deck - beam_h, deck,
                           palette.PLANK.linear, 1.0))
    count = 9
    span = box.width - 2.0 * min(30.0, 0.1 * box.width)
    rafter_w = min(8.0, 0.03 * box.width)
    xs = -span / 2.0 + span * np.arange(count) / (count - 1)
    # oak mid, as the beams: the light oak clipped on the rafters' sunlit sides
    meshes.append(slabs([(x, 0.0, rafter_w, box.depth - 2.0) for x in xs], deck, h,
                        palette.PLANK.linear, 0.8))
    return (_part(meshes, box, "pergola"),)


def _clip_line(origin: F64, direction: F64, low: F64, high: F64) -> tuple[F64, F64] | None:
    """The piece of the line ``origin + t·direction`` inside the box ``low``–``high``."""
    t0, t1 = -math.inf, math.inf
    for axis in range(2):
        if abs(direction[axis]) < 1e-12:
            if not low[axis] <= origin[axis] <= high[axis]:
                return None
            continue
        a = (low[axis] - origin[axis]) / direction[axis]
        b = (high[axis] - origin[axis]) / direction[axis]
        t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
    if t1 - t0 < 1.0:
        return None
    return origin + t0 * direction, origin + t1 * direction


def _trellis(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    box = object_box(record)
    if box is None or box.round:
        return plain_block(record, height_cm)
    h = height_cm
    along_x = box.width >= box.depth
    length = max(box.width, box.depth)
    thin = min(box.width, box.depth)
    half = length / 2.0
    post = min(7.0, max(2.0, 0.8 * thin))
    rail = min(5.0, 0.04 * h)
    slat_w, slat_t = min(3.0, 0.6 * post), min(1.5, 0.5 * post)
    meshes: list[Mesh] = [
        slab(-half, -half + post, -post / 2.0, post / 2.0, 0.0, h, palette.TINT, 0.5),
        slab(half - post, half, -post / 2.0, post / 2.0, 0.0, h, palette.TINT, 0.5),
        slab(-half + post, half - post, -slat_t, slat_t, h - rail, h, palette.TINT, 0.4),
        slab(-half + post, half - post, -slat_t, slat_t, min(8.0, 0.1 * h), min(8.0, 0.1 * h) + rail,
             palette.TINT, 0.4),
    ]
    low = np.array([-half + post, min(8.0, 0.1 * h) + rail])
    high = np.array([half - post, h - rail])
    reach = (high - low).sum()
    spacing = max(min(25.0, 0.3 * (high[1] - low[1]) + 5.0), 2.0 * reach / MAX_REPEATS)
    slats = []
    for direction in (np.array([1.0, 1.0]) / math.sqrt(2.0), np.array([1.0, -1.0]) / math.sqrt(2.0)):
        normal = np.array([-direction[1], direction[0]])
        offsets = np.arange(-reach, reach + spacing, spacing)
        for offset in offsets:
            piece = _clip_line(low + normal * offset, direction, low, high)
            if piece is None:
                continue
            (x0, z0), (x1, z1) = piece
            side = slat_t / 2.0 if direction[1] > 0 else -slat_t / 2.0
            slats.append(beam((x0, side, z0), (x1, side, z1), slat_t, slat_w, SHADE,
                              across=(0.0, 1.0, 0.0)))
    meshes += slats
    mesh = Mesh.merge(meshes)
    if not along_x:
        mesh = turned_mesh(mesh, "z", 90.0)
    return (MeshPart(mesh.translated(box.cx, box.cy, 0.0) if box.cx or box.cy else mesh, "vc",
                     tinted=True, name="trellis"),)


GLASS_ROOF: Final = RoofStyle(tile=palette.GLASS, cap=palette.STEEL_LIGHT, timber=palette.STEEL,
                              overhang_cm=3.0, pitch_deg=30.0, slab_cm=2.0, cap_rise_cm=3.0,
                              cap_half_width_cm=4.0, eave_floor_cm=150.0, eave_floor_share=0.7)


def _greenhouse_box(box: ObjectBox, h: float) -> tuple[MeshPart, ...]:
    """The aluminium-and-glass house on a box footprint, its ridge along the long side."""
    along_x = box.width >= box.depth
    long_half = max(box.half_w, box.half_d)
    short_half = min(box.half_w, box.half_d)
    kerb = min(KERB_CM, 0.1 * h)
    bar = min(BAR_CM, 0.04 * min(box.width, box.depth))
    ridge_h = min(6.0, 0.05 * h)
    eave = max(kerb + 10.0, EAVE_SHARE * h)
    ridge_axis = h - ridge_h / 2.0
    concrete, alu, alu_light = palette.CONCRETE.linear, palette.STEEL.linear, palette.STEEL_LIGHT.linear
    L, S = long_half, short_half
    frame: list[Mesh] = [
        slab(-L, L, -S, -S + 6.0, 0.0, kerb, concrete, 0.8), slab(-L, L, S - 6.0, S, 0.0, kerb, concrete, 0.8),
        slab(-L, -L + 6.0, -S + 6.0, S - 6.0, 0.0, kerb, concrete, 0.8),
        slab(L - 6.0, L, -S + 6.0, S - 6.0, 0.0, kerb, concrete, 0.8),
        slab(-L, L, -ridge_h / 2.0, ridge_h / 2.0, h - ridge_h, h, alu_light, 0.5),
    ]
    bays = min(MAX_REPEATS // 12, max(2, round(2.0 * L / 60.0)))
    xs = -L + bar / 2.0 + (2.0 * L - bar) * np.arange(bays + 1) / bays
    for x in xs:
        for sy in (-1.0, 1.0):
            y = sy * (S - bar / 2.0)
            frame.append(slab(x - bar / 2.0, x + bar / 2.0, y - bar / 2.0, y + bar / 2.0, kerb, eave, alu, 0.3))
            frame.append(beam_under((x, 0.0, ridge_axis), (x, y, eave), bar, bar * 0.8, alu,
                                    h - ridge_h * 0.5, across=(1.0, 0.0, 0.0)))
    for sy in (-1.0, 1.0):
        y = sy * (S - bar / 2.0)
        frame.append(slab(-L, L, y - bar / 2.0, y + bar / 2.0, eave - bar, eave, alu_light, 0.3))
        frame.append(slab(-L, L, y - bar / 2.0, y + bar / 2.0, kerb, kerb + bar, alu, 0.3))
    for sx in (-1.0, 1.0):
        x = sx * (L - bar / 2.0)
        frame.append(slab(x - bar / 2.0, x + bar / 2.0, -S + bar, S - bar, kerb, kerb + bar, alu, 0.3))
    # the door on the -long end: two jambs and a lintel
    door_w = min(80.0, 0.5 * 2.0 * S)
    door_top = min(195.0, eave + 0.4 * (h - eave))
    for y in (-door_w / 2.0, door_w / 2.0):
        frame.append(slab(-L, -L + bar, y - bar / 2.0, y + bar / 2.0, kerb, door_top, alu_light, 0.3))
    frame.append(slab(-L, -L + bar, -door_w / 2.0, door_w / 2.0, door_top - bar, door_top, alu_light, 0.3))
    # glass: four walls, two gables, two roof slopes — just inside the frame's faces
    inset = 0.4
    gx, gy = L - inset, S - inset
    top = ridge_axis
    quads = [
        [(-gx, -gy, kerb), (gx, -gy, kerb), (gx, -gy, eave), (-gx, -gy, eave)],
        [(gx, gy, kerb), (-gx, gy, kerb), (-gx, gy, eave), (gx, gy, eave)],
        [(gx, -gy, kerb), (gx, gy, kerb), (gx, gy, eave), (gx, -gy, eave)],
        [(-gx, gy, kerb), (-gx, -gy, kerb), (-gx, -gy, eave), (-gx, gy, eave)],
        [(-gx, -gy, eave), (gx, -gy, eave), (gx, 0.0, top - bar), (-gx, 0.0, top - bar)],
        [(gx, gy, eave), (-gx, gy, eave), (-gx, 0.0, top - bar), (gx, 0.0, top - bar)],
    ]
    triangles = [quad_triangles(np.asarray(quads, dtype=np.float64))]
    triangles.append(np.array([[(gx, -gy, eave), (gx, gy, eave), (gx, 0.0, top - bar)],
                               [(-gx, gy, eave), (-gx, -gy, eave), (-gx, 0.0, top - bar)]]))
    glass = flat_mesh(np.concatenate(triangles), palette.TINT)
    frame_mesh = Mesh.merge(frame)
    if not along_x:
        frame_mesh = turned_mesh(frame_mesh, "z", 90.0)
        glass = turned_mesh(glass, "z", 90.0)
    return (MeshPart(placed([frame_mesh], box), "vc", name="frame"),
            MeshPart(placed([glass], box), "glass", casts_shadow=False, tinted=True, name="glass"))


def _greenhouse(record: Record, height_cm: float) -> tuple[MeshPart, ...]:
    box = object_box(record)
    if box is not None and not box.round:
        return _greenhouse_box(box, height_cm)
    if not has_one_plain_ring(record):
        return plain_block(record, height_cm)
    footprint = footprint_of(record)
    ridge = bounding_box_ridge(footprint)
    built = gable_roof(footprint, ridge, height_cm, GLASS_ROOF) if ridge is not None else None
    if built is None:
        return plain_block(record, height_cm)
    roof = Mesh.from_arrays(built.roof.positions, built.roof.normals,
                            np.broadcast_to(palette.TINT, built.roof.colors.shape), built.roof.uvs,
                            built.roof.indices)
    return (MeshPart(Mesh.merge([built.walls, roof]), "glass", casts_shadow=False, tinted=True,
                     name="glass"),)


build_pergola: Final = BuiltBuilder(_pergola, "pergola")
build_trellis: Final = BuiltBuilder(_trellis, "trellis")
build_greenhouse: Final = BuiltBuilder(_greenhouse, "greenhouse")

BUILDERS: Final[dict[str, BuiltBuilder]] = {
    "PERGOLA": build_pergola,
    "TRELLIS": build_trellis,
    "GREENHOUSE": build_greenhouse,
}


def register(registry: BuilderRegistry) -> None:
    for kind, builder in BUILDERS.items():
        registry.register(kind, builder)
