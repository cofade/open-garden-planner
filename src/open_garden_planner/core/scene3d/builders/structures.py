"""Garden structures: pergola, trellis, greenhouse (Phase 17 L4.3, #388).

Mostly air — and built as such: posts, beams, rafters, slats and glass, never a
block. The 2D sun study casts an item with a height as its footprint prism; for
the two OPEN FRAMES here — the pergola and the trellis — it weights that prism by
the share of it these very members shade (#698, ``open_frames``: the fences'
porosity question, #440, answered for frames). A greenhouse is still the solid
prism in 2D, by recorded decision (``core.object_height.SOLID_2D_DECISIONS``),
while its glass casts no shadow here (``ogp-lush-cinematic`` §4).

- **PERGOLA** (#769, ``core.pergola``'s one layout with the 2D picture): four
  posts carrying a perimeter of four beams, nine rafters across the depth and five
  purlins on top — the purlins' top is the height. The 2D shade reads the same
  layout (``pergola_members``).
- **TRELLIS** (no sprite: a ``LATTICE`` fill in the item's colour, so ``tinted``):
  a post at each end of the footprint's LONG side, a top and a bottom rail and a
  diagonal lattice between them, in the vertical plane through the footprint's
  middle — what a climber is tied to (L3 grows climbers up to it).
- **GREENHOUSE** (#768, a ``GLASS`` fill in the item's colour): an aluminium
  frame on a concrete kerb, glass walls, glass gables and a pitched glass roof
  along the plan's ridge; its ridge beam's top is the height. The glass is
  ``tinted`` (the item's fill), translucent and casts no shadow. A box footprint
  whose live ridge is the natural long axis gets the framed house; any other
  footprint or ridge gets ``roofs.gable_roof`` in glass over its walls.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from ...greenhouse import bay_count
from ...pergola import PergolaLayout
from ...pergola import layout as pergola_layout
from ..build import BuilderRegistry
from ..mesh import Mesh, MeshPart
from ..record import PARAM_RIDGE, Record
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
from .roofs import Ridge, RoofStyle, bounding_box_ridge, gable_roof, ridge_of

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
    # ONE layout with the 2D picture and the gallery (``core.pergola``): posts,
    # four perimeter beams, nine rafters and five purlins; the purlins' top is the
    # item's height (#769).
    plan = pergola_layout(box.width, box.depth, height_cm)
    if plan is None:
        return plain_block(record, height_cm)
    return (_part(_pergola_meshes(plan, chamfered=True), box, "pergola"),)


def _pergola_meshes(plan: PergolaLayout, *, chamfered: bool) -> list[Mesh]:
    """The layout's four member groups as boxes at their heights. ``chamfered``: with
    the edges the built pergola shows; without, the same boxes plain."""
    def edge(bevel: float) -> float:
        return bevel if chamfered else 0.0

    return [
        slabs([r.as_slab() for r in plan.posts], 0.0, plan.beam_bottom,
              palette.PLANK_GROOVE.linear, edge(1.0)),
        slabs([r.as_slab() for r in plan.beams], plan.beam_bottom, plan.deck,
              palette.PLANK.linear, edge(1.0)),
        # oak mid, as the beams: the light oak clipped on the rafters' sunlit sides
        slabs([r.as_slab() for r in plan.rafters], plan.deck, plan.rafter_top,
              palette.PLANK.linear, edge(0.8)),
        slabs([r.as_slab() for r in plan.purlins], plan.rafter_top, plan.height,
              palette.OAK_LIGHT.linear, edge(0.5)),
    ]


def pergola_members(record: Record, height_cm: float) -> Mesh | None:
    """The pergola's 22 members as PLAIN boxes, placed as the built pergola is — or
    None where ``_pergola`` builds the plain block instead (no box footprint, no
    usable layout).

    What the 2D sun study weighs a pergola's shadow by (#698, ``open_frames``): the
    one layout of ``core.pergola``, so the 2D picture, the 3D build and the 2D shade
    are the same members. Without the chamfers the boxes are a few millimetres
    fuller than the built timber and a quarter of its triangles — the shadow
    agreement table holds the two within its tolerance.
    """
    box = object_box(record)
    if box is None or box.round:
        return None
    plan = pergola_layout(box.width, box.depth, height_cm)
    if plan is None:
        return None
    return placed(_pergola_meshes(plan, chamfered=False), box)


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
    return (MeshPart(placed([mesh], box), "vc", tinted=True, name="trellis"),)


GLASS_ROOF: Final = RoofStyle(tile=palette.GLASS, cap=palette.STEEL, timber=palette.STEEL,
                              overhang_cm=3.0, pitch_deg=30.0, slab_cm=2.0, cap_rise_cm=3.0,
                              cap_half_width_cm=4.0, eave_floor_cm=150.0, eave_floor_share=0.7)


def _box_ridge(box: ObjectBox) -> Ridge:
    """The ridge the framed house is built on: the box's long axis, through its
    centre, in the item's own frame (the same line ``bounding_box_ridge`` gives a
    rectangle, and the one ``core.roof_ridge`` draws in 2D)."""
    if box.width >= box.depth:
        return ((box.cx - box.half_w, box.cy), (box.cx + box.half_w, box.cy))
    return ((box.cx, box.cy - box.half_d), (box.cx, box.cy + box.half_d))


def _same_ridge(one: Ridge, other: Ridge, tolerance_cm: float = 1.0) -> bool:
    """Whether two ridge lines are the same segment, end order ignored (an edited
    ridge is authoritative in direction: a dragged endpoint may swap them)."""

    def near(a: tuple[float, float], b: tuple[float, float]) -> bool:
        return abs(a[0] - b[0]) <= tolerance_cm and abs(a[1] - b[1]) <= tolerance_cm

    return (near(one[0], other[0]) and near(one[1], other[1])) or (
        near(one[0], other[1]) and near(one[1], other[0])
    )


def _roof_glass_and_frame(mesh: Mesh) -> tuple[Mesh, Mesh]:
    """Split a gable roof into its GLASS-tile triangles and its aluminium frame
    (the cap and the timber/fascia), so only the glass takes the item's tint
    (#768). Colours are per vertex; a triangle belongs to the tile when all three
    of its vertices carry the tile colour. The tile subset is neutralised to
    ``palette.TINT`` because the sink multiplies a tinted part by the item's
    colour — a part that is tinted twice would render darker than its walls."""
    tile = np.asarray(palette.GLASS.linear, dtype=np.float32)
    triangles = mesh.colors[mesh.indices]  # (n, 3, 4)
    is_glass = np.all(np.isclose(triangles, tile, atol=1e-5), axis=(1, 2))

    def subset(mask: np.ndarray) -> Mesh:
        indices = mesh.indices[mask]
        if not len(indices):
            return Mesh.empty()
        used, inverse = np.unique(indices, return_inverse=True)
        return Mesh.from_arrays(
            mesh.positions[used], mesh.normals[used], mesh.colors[used], mesh.uvs[used],
            inverse.reshape(-1, 3).astype(np.uint32),
        )

    glass = subset(is_glass)
    if glass.vertex_count:
        white = np.broadcast_to(np.asarray(palette.TINT, dtype=np.float32), glass.colors.shape)
        glass = Mesh.from_arrays(glass.positions, glass.normals, white, glass.uvs, glass.indices)
    return glass, subset(~is_glass)


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
    bays = bay_count(2.0 * L)
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
    """The glasshouse (#768): the framed house where its live ridge is the box's
    natural long axis, else the plan's own ridge under a glass gable roof."""
    box = object_box(record)
    live = ridge_of(record.params.get(PARAM_RIDGE))
    if box is not None and not box.round and (
        live is None or _same_ridge(live, _box_ridge(box))
    ):
        return _greenhouse_box(box, height_cm)
    if not has_one_plain_ring(record):
        return plain_block(record, height_cm)
    footprint = footprint_of(record)
    ridge = live if live is not None else bounding_box_ridge(footprint)
    built = gable_roof(footprint, ridge, height_cm, GLASS_ROOF) if ridge is not None else None
    if built is None:
        return plain_block(record, height_cm)
    # Walls in the item's glass tint; the roof's glass tiles take the same tint,
    # while its aluminium cap/fascia stays grey (#768).
    glass_roof, frame_roof = _roof_glass_and_frame(built.roof)
    parts = [MeshPart(built.walls, "glass", casts_shadow=False, tinted=True, name="glass")]
    if glass_roof.vertex_count:
        parts.append(MeshPart(glass_roof, "glass", casts_shadow=False, tinted=True, name="glass"))
    if frame_roof.vertex_count:
        parts.append(MeshPart(frame_roof, "roof", casts_shadow=False, name="roof"))
    return tuple(parts)


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
