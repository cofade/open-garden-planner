"""Seasonal 3D accent builders for Plant Forge: fruits, blossoms, umbels, pods, and tubers (Phase 17 L3.5, #387).

Builds 3D geometry (`PART_ACCENTS`) from the 2D recipe feature keys in
`core.plant_art.recipes` (`fruit`, `fruit2`, `flowers`, `clusters`, `puffs`,
`umbels`, `pods`, `bulb`) plus spring `blossom_spec` on fruiting trees and shrubs.
All colours are derived strictly from `core.plant_art` (`FRUITS`, `FLOWERS`,
`PALETTES`) in linear light, with `WHITE_BARK_SHADE = 0.7` applied to bright
white petals/umbels so low winter/spring sun never clips.

Flowers (#940) stand as ``Traits3D.flower`` says: a crown's are as many as cover its
share of the crown's surface (``blossom_count``), on the crown's outer shell; a bulb's
and a stemmed flower's own builders place theirs (``flowers_geo``). Every petal is
double-sided with bent normals, so a flower shows from above and below.

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np

from ..plant_art import FLOWERS, FRUITS, PALETTES, WHITE_BARK_SHADE, recipe_for
from ..plant_art.traits3d import FlowerTraits, Traits3D
from ..scene3d.color import srgb_to_linear
from ..scene3d.mesh import MeshPart
from .assemble import PART_FOLIAGE, PART_WOOD, REACH_MAX, _fix_vc_flat_normals
from .foliage import RawGeo, concat_geo, crown_surface_cm2, empty_geo, normalize_vec
from .lod import LOD0, LOD1, LOD2, triangle_budget_for_lod, validate_lod
from .trees import bark_linear_rgba
from .tube import frustum_tubes

FLOWER_PART: Final[str] = "flowers"
FRUIT_PART: Final[str] = "fruits"
TUBER_PART: Final[str] = "tubers"
SEASONAL_PARTS: Final[frozenset[str]] = frozenset({FLOWER_PART, FRUIT_PART, TUBER_PART})

ACCENT_FAMILIES: Final[frozenset[str]] = frozenset(
    {"fruits", "blossoms", "umbels", "pods", "tubers"}
)


def _seed_rng(seed: int, salt: int) -> np.random.Generator:
    mixed = (int(seed) * 2654435761 + int(salt) * 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    return np.random.default_rng(mixed)


def _hex_to_linear_rgb(hex_color: str) -> np.ndarray:
    """Convert `#rrggbb` to linear-light RGB float32, shading bright whites by `WHITE_BARK_SHADE`."""
    r, g, b = srgb_to_linear(hex_color)[:3]
    arr = np.array([float(r), float(g), float(b)], dtype=np.float64)
    # Apply WHITE_BARK_SHADE (0.7) to near-white petals/umbels so direct sunlight never clips
    if float(np.max(arr)) > 0.78 and float(np.min(arr)) > 0.62:
        arr *= WHITE_BARK_SHADE
    return np.clip(arr, 0.02, 0.88).astype(np.float32)


def _select_crown_anchors(
    anchor_points: np.ndarray | None,
    count: int,
    height_cm: float,
    radius_cm: float,
    rng: np.random.Generator,
    *,
    z_range: tuple[float, float] = (0.35, 0.92),
    radial_range: tuple[float, float] = (0.45, 0.92),
) -> np.ndarray:
    """Pick `count` well-distributed 3D anchor points on the outer crown/foliage."""
    if count <= 0:
        return np.zeros((0, 3), dtype=np.float64)

    if anchor_points is not None and len(anchor_points) >= 4:
        pts = np.asarray(anchor_points, dtype=np.float64)
        z_min_want = height_cm * z_range[0]
        z_max_want = height_cm * z_range[1]
        r_xy = np.hypot(pts[:, 0], pts[:, 1])
        r_min_want = radius_cm * radial_range[0] * 0.65
        mask = (pts[:, 2] >= z_min_want) & (pts[:, 2] <= z_max_want) & (r_xy >= r_min_want)
        candidates = pts[mask]
        if len(candidates) < count:
            candidates = pts
        # Stratify by azimuth sector so accents spread evenly around the plant
        az = np.arctan2(candidates[:, 1], candidates[:, 0])
        order = np.argsort(az)
        candidates = candidates[order]
        indices = np.linspace(0, len(candidates) - 1, count, dtype=np.int64)
        jitter = rng.integers(-max(1, len(candidates) // (count * 3 + 1)), max(2, len(candidates) // (count * 3 + 1)), size=count)
        indices = np.clip(indices + jitter, 0, len(candidates) - 1)
        chosen: np.ndarray = np.asarray(candidates[indices], dtype=np.float64).copy()
        # Pull slightly inward so accent geometry never breaches REACH_MAX * radius_cm
        chosen[:, 0] *= 0.92
        chosen[:, 1] *= 0.92
        chosen[:, 2] = np.clip(chosen[:, 2], height_cm * 0.06, height_cm * 0.95)
        return chosen

    # Procedural fallback when no foliage anchor cloud is provided
    idx = np.arange(count, dtype=np.float64)
    az = float(rng.uniform(0.0, 2.0 * math.pi)) + idx * (2.0 * math.pi / max(count, 1)) + rng.uniform(-0.28, 0.28, size=count)
    r = radius_cm * rng.uniform(radial_range[0], radial_range[1], size=count)
    z = height_cm * rng.uniform(z_range[0], z_range[1], size=count)
    return np.column_stack([np.cos(az) * r, np.sin(az) * r, z])


def _spheroids_geo(
    centers: np.ndarray,
    radii_xy: np.ndarray,
    radii_z: np.ndarray,
    color_top: np.ndarray,
    color_mid: np.ndarray,
    color_bot: np.ndarray,
    *,
    sides: int = 6,
) -> RawGeo:
    """Build low-poly closed spheroids (2 rings + top/bottom poles = `4 * sides` tris each)."""
    n = len(centers)
    if n == 0:
        return empty_geo()

    s = max(int(sides), 4)
    angles = np.linspace(0.0, 2.0 * math.pi, s, endpoint=False, dtype=np.float64)
    ca = np.cos(angles)
    sa = np.sin(angles)

    # 2 + 2*s vertices per spheroid:
    # 0: bottom pole (z = -rz)
    # 1..s: lower ring (z = -0.38 * rz, r = 0.88 * rxy)
    # s+1..2s: upper ring (z = +0.38 * rz, r = 0.88 * rxy)
    # 2s+1: top pole (z = +rz)
    v_per = 2 * s + 2
    local = np.zeros((v_per, 3), dtype=np.float64)
    local[0] = [0.0, 0.0, -1.0]
    local[1 : 1 + s, 0] = 0.88 * ca
    local[1 : 1 + s, 1] = 0.88 * sa
    local[1 : 1 + s, 2] = -0.38
    local[1 + s : 1 + 2 * s, 0] = 0.88 * ca
    local[1 + s : 1 + 2 * s, 1] = 0.88 * sa
    local[1 + s : 1 + 2 * s, 2] = 0.38
    local[2 * s + 1] = [0.0, 0.0, 1.0]

    local_nrm = normalize_vec(local)

    # Scale per instance: (N, v_per, 3)
    scale = np.stack([radii_xy, radii_xy, radii_z], axis=-1)[:, None, :]
    pos = (centers[:, None, :] + local[None, :, :] * scale).reshape(-1, 3).astype(np.float32)
    inv_scale = 1.0 / np.maximum(scale, 1e-4)
    nrm = normalize_vec((local_nrm[None, :, :] * inv_scale).reshape(-1, 3)).astype(np.float32)

    # Colours per vertex ring
    c_bot = np.asarray(color_bot, dtype=np.float32)
    c_mid = np.asarray(color_mid, dtype=np.float32)
    c_top = np.asarray(color_top, dtype=np.float32)
    c_low = (0.55 * c_mid + 0.45 * c_bot).astype(np.float32)
    c_high = (0.65 * c_top + 0.35 * c_mid).astype(np.float32)

    col_single = np.ones((v_per, 4), dtype=np.float32)
    col_single[0, :3] = c_bot
    col_single[1 : 1 + s, :3] = c_low
    col_single[1 + s : 1 + 2 * s, :3] = c_high
    col_single[2 * s + 1, :3] = c_top
    col = np.tile(col_single, (n, 1))

    # Triangles per spheroid (4 * s)
    base_tris: list[tuple[int, int, int]] = []
    top_idx = 2 * s + 1
    for i in range(s):
        nxt = (i + 1) % s
        l0 = 1 + i
        l1 = 1 + nxt
        u0 = 1 + s + i
        u1 = 1 + s + nxt
        # Bottom fan (outward CCW seen from outside below)
        base_tris.append((0, l1, l0))
        # Middle belt
        base_tris.append((l0, l1, u1))
        base_tris.append((l0, u1, u0))
        # Top fan
        base_tris.append((u0, u1, top_idx))

    t_single = np.asarray(base_tris, dtype=np.uint32)  # (4*s, 3)
    offsets = (np.arange(n, dtype=np.uint32) * v_per)[:, None, None]
    tri = (t_single[None, :, :] + offsets).reshape(-1, 3)
    uv = np.zeros((len(pos), 2), dtype=np.float32)
    return RawGeo(pos=pos, nrm=nrm, col=col, uv=uv, tri=tri)


def build_fruit_accents(
    fruit_spec: Mapping[str, Any],
    height_cm: float,
    radius_cm: float,
    rng: np.random.Generator,
    *,
    lod: int = LOD0,
    anchor_points: np.ndarray | None = None,
) -> RawGeo:
    """Build 3D fruit spheroids/clusters from a recipe `fruit` or `fruit2` mapping."""
    if lod == LOD2:
        return empty_geo()

    kind = str(fruit_spec.get("kind", "apple"))
    hl_hex, mid_hex, dark_hex = FRUITS.get(kind, FRUITS["apple"])
    c_top = _hex_to_linear_rgb(hl_hex)
    c_mid = _hex_to_linear_rgb(mid_hex)
    c_bot = _hex_to_linear_rgb(dark_hex)

    base_n = int(fruit_spec.get("n", 4))
    per = fruit_spec.get("per", (1, 2))
    per_mean = 0.5 * (int(per[0]) + int(per[1])) if isinstance(per, Sequence) and len(per) >= 2 else 1.5
    cluster_mult = 2 if lod == LOD0 else 1
    total_clusters = max(2, int(round(base_n * cluster_mult)))

    size_pair = fruit_spec.get("size", (3.0, 3.8))
    ref_size = 0.5 * (float(size_pair[0]) + float(size_pair[1])) if isinstance(size_pair, Sequence) and len(size_pair) >= 2 else 3.2
    plant_scale = max(min(height_cm, radius_cm * 2.0) / 140.0, 0.35)
    fruit_r = np.clip(ref_size * 0.72 * plant_scale, 0.9, max(radius_cm * 0.16, 1.5))

    is_ground_vine = kind in ("pumpkin", "butternut")
    z_range = (0.06, 0.30) if is_ground_vine else (0.32, 0.84)
    anchors = _select_crown_anchors(
        anchor_points,
        total_clusters,
        height_cm,
        radius_cm,
        rng,
        z_range=z_range,
        radial_range=(0.45, 0.88),
    )

    items_per_cluster = max(1, int(round(per_mean))) if not is_ground_vine else 1
    # A grape bunch hangs: berries stacked down a cone that narrows to its tip (#940)
    hanging_bunch = kind == "grape"
    centers_list: list[np.ndarray] = []
    for a_pt in anchors:
        for k in range(items_per_cluster):
            if hanging_bunch:
                depth = k / max(items_per_cluster - 1, 1)
                offset = rng.normal(0.0, fruit_r * 0.8 * (1.0 - 0.65 * depth), size=3)
                offset[2] = -fruit_r * 3.4 * depth
            else:
                offset = rng.normal(0.0, fruit_r * 0.65, size=3) if k > 0 else np.zeros(3)
            # Hang slightly below twig/foliage node
            offset[2] -= fruit_r * 0.55
            centers_list.append(a_pt + offset)

    centers = np.asarray(centers_list, dtype=np.float64)
    n_fruits = len(centers)
    r_xy = fruit_r * rng.uniform(0.88, 1.14, size=n_fruits)
    # Pear, fig, lemon, olive, eggplant, and butternut are slightly elongated vertically
    aspect_z = 1.32 if kind in ("pear", "fig", "lemon", "olive", "eggplant", "butternut") else (0.78 if kind == "pumpkin" else 1.02)
    r_z = r_xy * aspect_z
    sides = 6 if lod == LOD0 else 5
    return _spheroids_geo(centers, r_xy, r_z, c_top, c_mid, c_bot, sides=sides)


#: How far a petal's tip rises along its flower's facing, per unit of ``cup`` and of the
#: flower's radius (#940): a cup of 1.15 is a tulip's goblet, 1.5 times as deep as wide.
PETAL_RISE_PER_CUP: Final[float] = 1.3
#: A petal's width as a share of the ring it stands on, so that the petals of a flower
#: close into one coloured disc (or goblet) instead of a thin star (#940).
PETAL_RING_SHARE: Final[float] = 0.88
#: A petal's normals lean to the sky by this much (a unit normal plus this up) and out
#: from its flower's centre by ``PETAL_SPREAD_BEND`` per unit of radius: a petal is
#: thin, and seen from below it shows the sun through it, not a black back (#940).
PETAL_SKY_BEND: Final[float] = 0.8
PETAL_SPREAD_BEND: Final[float] = 0.35
#: A bulb's flower whose cup reaches this is a goblet (tulip 1.15, crocus 1.0): its tepals
#: lean to the sky by only this share of ``PETAL_SKY_BEND`` and their outside keeps its
#: own normal (a crown's goblets - a magnolia's, seen from below - stay thin sheets).
GOBLET_CUP: Final[float] = 0.8
GOBLET_SKY_SHARE: Final[float] = 0.25
#: How far a petal's tip turns from the petal's colour to its light tip colour - the 2D
#: sprite's mix for a double flower's inner ring (``generate_plant_sprites.flower_head``);
#: a flower may set its own (``FlowerTraits.tip_light``).
PETAL_TIP_LIGHT: Final[float] = 0.45
#: Petals drawn per flower at LOD0 (quads) and LOD1 (one triangle each, single whorl).
PETALS_MAX_LOD0: Final[int] = 10
PETALS_MAX_LOD1: Final[int] = 6
#: How far a flower may grow when its LOD cannot afford the flowers its crown holds:
#: fewer, larger flowers keep the crown's share in bloom, as fewer, larger leaves keep
#: a distant crown's leaf area (``foliage.crown_leaf_budget``) (#940).
FLOWER_ENLARGE_MAX: Final[dict[int, float]] = {LOD0: 1.8, LOD1: 3.0}
#: Triangles kept free of a LOD's budget when the flowers are counted.
FLOWER_BUDGET_RESERVE: Final[int] = 64
#: A plant's flowers take at most this share of its LOD's triangle budget (#940, review
#: 2): built all year and shown in bloom, they had grown a plan's plant triangles by up
#: to 80 % (the food forest: currants, chives, asters and fruit trees filling budgets).
FLOWER_BUDGET_SHARE: Final[float] = 0.4


def _flower_budget(lod: int, max_tris: int | None) -> int:
    """The triangles a plant's flowers may take at ``lod``: what its budget leaves them
    (``max_tris``), at most ``FLOWER_BUDGET_SHARE`` of the LOD's budget."""
    cap = int(FLOWER_BUDGET_SHARE * triangle_budget_for_lod(lod))
    return cap if max_tris is None else min(int(max_tris), cap)
#: A cluster (a lilac's panicle, a rhododendron's truss, a pelargonium's umbel) is 0.6 of
#: its recipe radius (a lilac's 4.8 cm, a hydrangea's 5.4) and its plant's clusters cover
#: this share of the crown's surface in full bloom (#940, review 2).
CLUSTER_CM_PER_RECIPE_RADIUS: Final[float] = 0.6
CLUSTER_COVER: Final[float] = 0.15
#: A shrub that flowers on bare wood ties each flower to its nearest wood with a twig at
#: LOD0 (#940, review 2): three sides (6 triangles), paid from its flowers' budget.
TWIG_TRIANGLES: Final[int] = 6
TWIG_RADIUS_CM: Final[float] = 0.2


def _frame_for(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two unit vectors ``(t, b)`` with ``(t, b, axis)`` right-handed, per row of ``axis``."""
    helper = np.zeros_like(axis)
    polar = np.abs(axis[:, 2]) >= 0.92
    helper[polar, 0] = 1.0
    helper[~polar, 2] = 1.0
    tangent = normalize_vec(np.cross(helper, axis))
    bitangent = normalize_vec(np.cross(axis, tangent))
    return tangent, bitangent


#: A flower's phase lies in [0, FLOWER_PHASE_MAX): the engine opens a plant's flowers in
#: phase order as its bloom rises and fades them as it falls (``qml/screen.vert``).
FLOWER_PHASE_MAX: Final[float] = 0.999


def with_phase(geo: RawGeo, phase: np.ndarray) -> RawGeo:
    """``geo`` - ``len(phase)`` equal blocks of vertices, one a flower - with each block's
    UV.y set to its flower's phase (#940, review 2). While a plant's bloom is below 1 the
    engine collapses every flower whose phase is not below it, in every pass, its shadow
    too: flowers open and fade one by one instead of a whole crown popping or dithering."""
    if geo.vertex_count == 0 or len(phase) == 0 or geo.vertex_count % len(phase):
        return geo
    geo.uv = geo.uv.copy()
    geo.uv[:, 1] = np.repeat(np.asarray(phase, dtype=np.float32), geo.vertex_count // len(phase))
    return geo


def _oriented_spheroids_geo(
    centers: np.ndarray,
    axes: np.ndarray,
    radii_xy: np.ndarray,
    radii_axis: np.ndarray,
    color_top: np.ndarray,
    color_mid: np.ndarray,
    color_bot: np.ndarray,
    *,
    sides: int,
) -> RawGeo:
    """``_spheroids_geo`` with each spheroid's pole turned from +z to its row of ``axes``."""
    geo = _spheroids_geo(np.zeros_like(centers), radii_xy, radii_axis, color_top, color_mid,
                         color_bot, sides=sides)
    if geo.vertex_count == 0:
        return geo
    per = geo.vertex_count // len(centers)
    tangent, bitangent = _frame_for(axes)
    basis = np.stack([tangent, bitangent, axes], axis=1)            # (N, 3 local, 3 world)
    local = geo.pos.astype(np.float64).reshape(len(centers), per, 3)
    geo.pos = (np.einsum("npk,nkw->npw", local, basis) + centers[:, None, :]).reshape(-1, 3).astype(np.float32)
    local_n = geo.nrm.astype(np.float64).reshape(len(centers), per, 3)
    geo.nrm = normalize_vec(np.einsum("npk,nkw->npw", local_n, basis).reshape(-1, 3)).astype(np.float32)
    return geo


def _petals_geo(
    centers: np.ndarray,
    facing: np.ndarray,
    radii: np.ndarray,
    n_petals: int,
    cup: float,
    petal: np.ndarray,
    light: np.ndarray,
    rng: np.random.Generator,
    *,
    quad: bool,
    tip_light: float = 0.45,
    goblet: bool = False,
    phase: np.ndarray | None = None,
) -> RawGeo:
    """One whorl of petals round each flower, DOUBLE-SIDED: every petal twice, once
    wound to face its flower's ``facing`` (the inside of the cup: ``petal`` at the base
    to ``light`` at the tip) and once wound away from it (the petal's back). The plant's
    ``vc`` material culls back faces, so a single-sided petal vanishes from half the
    world - before #940 every petal faced the ground and no flower showed from above.

    A petal widens from its base to a blunt tip that closes the ring with its
    neighbours (``PETAL_RING_SHARE``), so a flower reads as one disc or goblet, not a
    spiky star. ``quad``: two triangles (a fan-shaped petal); else one (a wedge).
    Its normals are BENT, like the foliage's: toward the sky (``PETAL_SKY_BEND``) and
    out along the petal from its flower's centre, and both faces take the front's: a
    thin petal seen from below takes the sun through it, lit like its upper side,
    instead of the black (then dark violet) of a face turned from the light; bent along
    the petal only, so its two halves shade alike (a bend across it drew pinwheels).
    ``tip_light``: how far the tip turns toward the light colour."""
    n = len(centers)
    p = max(int(n_petals), 3)
    if n == 0:
        return empty_geo()
    tangent, bitangent = _frame_for(facing)
    turn = rng.uniform(0.0, 2.0 * math.pi, size=(n, 1))
    angle = turn + 2.0 * math.pi * np.arange(p)[None, :] / p + rng.uniform(-0.08, 0.08, size=(n, p))
    ca, sa = np.cos(angle)[..., None], np.sin(angle)[..., None]          # (n, p, 1)
    radial = ca * tangent[:, None, :] + sa * bitangent[:, None, :]       # (n, p, 3)
    side = -sa * tangent[:, None, :] + ca * bitangent[:, None, :]
    up = facing[:, None, :]
    r = radii[:, None, None]
    c = centers[:, None, :]
    rise = PETAL_RISE_PER_CUP * float(cup) * r
    tip_w = PETAL_RING_SHARE * 2.0 * math.pi * r / p                      # closes the ring
    base = c + radial * (0.10 * r)
    tip = c + radial * r + up * rise
    # the 2D flower: a petal of `petal` with a light tip over about a third of it
    tip_col = petal + float(tip_light) * (light - petal)
    if quad:
        corners = [base - side * (0.12 * tip_w), tip - side * (0.5 * tip_w),
                   tip + side * (0.5 * tip_w), base + side * (0.12 * tip_w)]
        front_tri = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)   # wound to face +facing
        front_col = [petal * 0.92, tip_col, tip_col, petal * 0.92]
        back_col = [petal * 0.82, petal * 0.95, petal * 0.95, petal * 0.82]
    else:
        corners = [base, tip - side * (0.5 * tip_w), tip + side * (0.5 * tip_w)]
        front_tri = np.array([[0, 1, 2]], dtype=np.uint32)
        front_col = [petal * 0.92, tip_col, tip_col]
        back_col = [petal * 0.82, petal * 0.95, petal * 0.95]
    k = len(corners)
    v = np.stack(corners, axis=2)                                         # (n, p, k, 3)
    # the face's winding normal; a deep cup can tip a petal past its flower's plane, so
    # each front face is wound toward +facing
    face_n = normalize_vec(np.cross(v[:, :, front_tri[0, 1]] - v[:, :, 0],
                                    v[:, :, front_tri[0, 2]] - v[:, :, 0]))
    wrong = (face_n * up).sum(axis=-1) < 0.0                              # (n, p)
    face_n = np.where(wrong[..., None], -face_n, face_n)
    tri_one = np.where(wrong.reshape(-1, 1, 1), front_tri[:, ::-1][None], front_tri[None])
    offsets = (np.arange(n * p, dtype=np.uint32) * k)[:, None, None]
    front = (tri_one + offsets).reshape(-1, 3).astype(np.uint32)
    pts = v.reshape(-1, 3)
    count = len(pts)
    back = (front[:, ::-1] + count).astype(np.uint32)

    # a bulb's goblet stands to the sky and is seen from its side: its steep tepals lean
    # to the sky less, and their outside keeps its own normal (a crocus goblet lit like a
    # lawn read pale lilac, +12 degrees off its purple); an open petal is a thin sheet
    sky = np.array([0.0, 0.0, PETAL_SKY_BEND * (GOBLET_SKY_SHARE if goblet else 1.0)])
    along = radial[:, :, None, :]
    reach = ((v - c[:, :, None, :]) * along).sum(axis=-1, keepdims=True) / r[:, :, None, :]
    spread = PETAL_SPREAD_BEND * reach * along
    n_front = normalize_vec(face_n[:, :, None, :] + sky + spread).reshape(-1, 3)
    n_back = (normalize_vec(-face_n[:, :, None, :] + sky + spread).reshape(-1, 3) if goblet
              else n_front)

    col_front = np.ones((k, 4), dtype=np.float32)
    col_back = np.ones((k, 4), dtype=np.float32)
    col_front[:, :3] = np.asarray(front_col, dtype=np.float32)
    col_back[:, :3] = np.asarray(back_col, dtype=np.float32)
    col = np.concatenate([np.tile(col_front, (n * p, 1)), np.tile(col_back, (n * p, 1))])
    pos = np.concatenate([pts, pts]).astype(np.float32)
    nrm = np.concatenate([n_front, n_back]).astype(np.float32)
    uv = np.zeros((len(pos), 2), dtype=np.float32)
    if phase is not None:
        uv[:, 1] = np.tile(np.repeat(np.asarray(phase, dtype=np.float32), p * k), 2)
    return RawGeo(pos=pos, nrm=nrm, col=col, uv=uv, tri=np.concatenate([front, back]))


def flower_lod_form(flower: FlowerTraits, lod: int) -> tuple[int, bool, bool, int]:
    """``(petals, quad petals, second whorl, disc sides)`` of one flower at ``lod``."""
    if lod == LOD0:
        return min(flower.petals, PETALS_MAX_LOD0), not flower.wedge, flower.double, 5
    return min(flower.petals, PETALS_MAX_LOD1), False, False, 4


def flower_triangles(flower: FlowerTraits, lod: int) -> int:
    """Triangles one flower costs at ``lod`` (both faces of every petal, and its disc)."""
    petals, quad, double, disc_sides = flower_lod_form(flower, lod)
    per_whorl = petals * (4 if quad else 2)
    disc = 4 * disc_sides if flower.disc_radius > 0.0 else 0
    return per_whorl * (2 if double else 1) + disc


def blossom_count(
    surface_cm2: float, cover: float, radius_cm: float, affordable: int, *, enlarge_max: float,
) -> tuple[int, float]:
    """``(count, radius_cm)`` of the flowers that cover ``cover`` of ``surface_cm2`` (#940).

    The count follows the crown's surface, never a fixed number. When the LOD cannot
    afford it, fewer flowers each grow - up to ``enlarge_max`` times - so the share of
    the crown in bloom holds as far as it can."""
    if affordable <= 0 or cover <= 0.0 or surface_cm2 <= 0.0:
        return 0, radius_cm
    wanted = max(1, math.ceil(cover * surface_cm2 / (math.pi * radius_cm * radius_cm)))
    count = min(wanted, int(affordable))
    return count, radius_cm * min(math.sqrt(wanted / count), enlarge_max)


def flowers_geo(
    flower: FlowerTraits,
    spec: str,
    centers: np.ndarray,
    facing: np.ndarray,
    radii: np.ndarray,
    rng: np.random.Generator,
    *,
    lod: int,
    phase: np.ndarray | None = None,
) -> RawGeo:
    """Flowers of ``flower``'s form at ``centers``, each turned to its row of ``facing``,
    in the colours of ``FLOWERS[spec]`` (the 2D table): petals, a second inner whorl for
    a double flower, and its centre - each flower carrying its ``phase`` (``with_phase``;
    drawn here when not given)."""
    if len(centers) == 0:
        return empty_geo()
    if phase is None:
        phase = rng.random(len(centers)) * FLOWER_PHASE_MAX
    outer_hex, light_hex, center_hex = FLOWERS.get(spec, FLOWERS["white"])
    c_outer = _hex_to_linear_rgb(outer_hex) * np.float32(flower.shade)
    c_light = _hex_to_linear_rgb(light_hex) * np.float32(flower.shade)
    c_center = _hex_to_linear_rgb(center_hex)
    petals, quad, double, disc_sides = flower_lod_form(flower, lod)
    facing = normalize_vec(np.asarray(facing, dtype=np.float64))
    centers = np.asarray(centers, dtype=np.float64)
    radii = np.asarray(radii, dtype=np.float64)
    goblet = flower.habit == "scape" and flower.cup >= GOBLET_CUP
    geos = [_petals_geo(centers, facing, radii, petals, flower.cup, c_outer, c_light, rng,
                        quad=quad, tip_light=flower.tip_light, goblet=goblet, phase=phase)]
    if double:
        # the inner whorl: smaller and deeper, in the 2D sprite's inner colour
        inner = c_outer + PETAL_TIP_LIGHT * (c_light - c_outer)
        geos.append(_petals_geo(centers + facing * (0.06 * radii[:, None]), facing, radii * 0.66,
                                petals, flower.cup + 0.35, inner, c_light, rng, quad=quad,
                                tip_light=flower.tip_light, phase=phase))
    if flower.disc_radius > 0.0:
        disc_r = np.maximum(radii * flower.disc_radius, 0.3)
        depth = np.maximum(radii * flower.disc_depth, 0.2)
        geos.append(with_phase(_oriented_spheroids_geo(
            centers + facing * (0.5 * depth[:, None]), facing, disc_r, depth,
            c_center, c_center * 0.85, c_center * 0.65, sides=disc_sides,
        ), phase))
    return concat_geo(geos)


def _flower_facing(outward: np.ndarray, face_up: float, rng: np.random.Generator) -> np.ndarray:
    """``outward`` turned toward the sky by ``face_up`` (0..1), with a little scatter."""
    up = np.array([0.0, 0.0, 1.0], dtype=np.float64)[None, :]
    turned = (1.0 - float(face_up)) * normalize_vec(outward) + float(face_up) * up
    return normalize_vec(turned + rng.normal(0.0, 0.12, size=outward.shape))


#: The crown's outer shell (#940): a flower anchors on a leaf at least this far out
#: along its direction from the crown's centre, as a share of the farthest leaf there.
CROWN_SHELL: Final[float] = 0.78
#: Direction bins round the crown's centre (azimuth x height) the shell is measured in.
_SHELL_AZIMUTH_BINS: Final[int] = 18
_SHELL_HEIGHT_BINS: Final[int] = 9
#: No flower faces more steeply down than this (z of its outward direction): what
#: hangs under the crown is hidden by it from every camera but a worm's.
_SHELL_LOWEST_Z: Final[float] = -0.55


def _shell_mask(
    points: np.ndarray, frame: np.ndarray, threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(in_shell, outward, half)`` of ``points`` in the crown box of ``frame`` (points):
    a point is in the shell when it lies at least ``threshold`` as far out along its
    direction from the box's centre as the farthest point there (18 x 9 direction bins),
    and does not face more steeply down than ``_SHELL_LOWEST_Z``."""
    lo, hi = frame.min(axis=0), frame.max(axis=0)
    centre = 0.5 * (lo + hi)
    half = np.maximum(0.5 * (hi - lo), 1e-3)
    rel = (points - centre) / half                   # the crown as a unit sphere
    dist = np.linalg.norm(rel, axis=1)
    dirs = rel / np.maximum(dist, 1e-9)[:, None]
    az = np.floor((np.arctan2(dirs[:, 1], dirs[:, 0]) + math.pi) / (2.0 * math.pi)
                  * _SHELL_AZIMUTH_BINS).astype(np.int64) % _SHELL_AZIMUTH_BINS
    el = np.clip(np.floor((dirs[:, 2] + 1.0) * 0.5 * _SHELL_HEIGHT_BINS).astype(np.int64),
                 0, _SHELL_HEIGHT_BINS - 1)
    cell = az * _SHELL_HEIGHT_BINS + el
    farthest = np.zeros(_SHELL_AZIMUTH_BINS * _SHELL_HEIGHT_BINS)
    np.maximum.at(farthest, cell, dist)
    shell = (dist >= threshold * farthest[cell]) & (dirs[:, 2] >= _SHELL_LOWEST_Z)
    return shell, normalize_vec(dirs * half[None, :]), half   # outward in the crown's own shape


def crown_flower_anchors(
    points: np.ndarray, count: int, rng: np.random.Generator, *, min_z: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """``count`` anchors on the outer shell of the foliage ``points`` and their outward
    directions (#940). A flower inside the crown is hidden by its leaves: the anchors are
    leaves within ``CROWN_SHELL`` of the farthest leaf in their direction from the
    crown's centre (the foliage's bounding-box centre). ``min_z``: none lower (an
    allium's flower heads stand at its top)."""
    pts = np.asarray(points, dtype=np.float64)
    if count <= 0 or len(pts) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3))
    shell, outward_all, half = _shell_mask(pts, pts, CROWN_SHELL)
    if min_z is not None:
        shell &= pts[:, 2] >= min_z
    candidates = np.flatnonzero(shell)
    if len(candidates) == 0:
        candidates = np.arange(len(pts))
    if count <= len(candidates):
        chosen = rng.choice(candidates, size=count, replace=False)
        jitter = np.zeros((count, 3))
    else:
        chosen = rng.choice(candidates, size=count, replace=True)
        jitter = rng.normal(0.0, 0.04, size=(count, 3)) * half[None, :]
    return pts[chosen] + jitter, outward_all[chosen]


#: A plant that flowers before its leaves carries its flowers on its wood, not on leaves
#: the season has screen-doored away (#940, review 2: a cherry's flowers floated a median
#: 27 cm from any wood): on the wood's outer 30 % in the crown's box - its twigs.
WOOD_SHELL: Final[float] = 0.70


def wood_flower_anchors(
    positions: np.ndarray,
    indices: np.ndarray,
    count: int,
    rng: np.random.Generator,
    *,
    crown: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """``count`` points ON the wood's outer twigs (``WOOD_SHELL`` of the crown box of
    ``crown``, the foliage's points, else the wood's own) and their outward directions:
    a random point on a random shell triangle, so each flower sits on a twig."""
    pos = np.asarray(positions, dtype=np.float64)
    tri = np.asarray(indices, dtype=np.int64).reshape(-1, 3)
    if count <= 0 or len(tri) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3))
    corners = pos[tri]                                            # (T, 3, 3)
    centroids = corners.mean(axis=1)
    frame = np.asarray(crown, dtype=np.float64) if crown is not None and len(crown) >= 4 else pos
    shell, outward_all, _half = _shell_mask(centroids, frame, WOOD_SHELL)
    candidates = np.flatnonzero(shell)
    if len(candidates) == 0:
        candidates = np.arange(len(tri))
    chosen = rng.choice(candidates, size=count, replace=count > len(candidates))
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1.0
    u, v = np.where(flip, 1.0 - u, u), np.where(flip, 1.0 - v, v)
    a, b, c = corners[chosen, 0], corners[chosen, 1], corners[chosen, 2]
    return a + u[:, None] * (b - a) + v[:, None] * (c - a), outward_all[chosen]


def _crown_flowers_geo(
    traits: Traits3D,
    flower: FlowerTraits,
    height_cm: float,
    radius_cm: float,
    rng: np.random.Generator,
    *,
    lod: int,
    anchor_points: np.ndarray | None,
    max_tris: int | None,
    wood: tuple[np.ndarray, np.ndarray] | None = None,
) -> RawGeo:
    """A crown's flowers (#940): as many as cover ``flower.cover`` of the crown's surface
    (``foliage.crown_surface_cm2``), within the LOD's budget, on its outer shell - the
    leaves', or for a plant that flowers before its leaves the outer twigs of ``wood``
    (its positions and triangle indices)."""
    budget = _flower_budget(lod, max_tris)
    bare_wood = traits.bloom_leaf_density < 1.0 and wood is not None and len(wood[1]) > 0
    # a tree's skeleton has twigs enough to carry its flowers; a shrub's few stems do not
    # (a forsythia's flowers along its seven stems read as yellow bottle-brushes), so a
    # shrub that flowers on bare wood keeps its flowers on its crown's shell, each on a
    # twig of its own from the nearest wood, at LOD0
    on_wood = bare_wood and traits.archetype == "canopy"
    twigs = bare_wood and not on_wood and lod == LOD0
    per_flower = flower_triangles(flower, lod) + (TWIG_TRIANGLES if twigs else 0)
    affordable = max(0, budget - FLOWER_BUDGET_RESERVE) // per_flower
    surface = crown_surface_cm2(height_cm, radius_cm, traits.crown.trunk_share)
    count, radius = blossom_count(surface, flower.cover, flower.radius_cm, affordable,
                                  enlarge_max=FLOWER_ENLARGE_MAX.get(lod, 1.0))
    if count == 0:
        return empty_geo()
    if on_wood:
        assert wood is not None
        anchors, outward = wood_flower_anchors(wood[0], wood[1], count, rng, crown=anchor_points)
    elif anchor_points is not None and len(anchor_points) >= 4:
        anchors, outward = crown_flower_anchors(anchor_points, count, rng)
    else:
        anchors = _select_crown_anchors(None, count, height_cm, radius_cm, rng,
                                        z_range=(0.42, 0.94), radial_range=(0.40, 0.90))
        crown_c = np.array([0.0, 0.0, height_cm * 0.45], dtype=np.float64)
        outward = normalize_vec(anchors - crown_c[None, :])
    facing = _flower_facing(outward, flower.face_up, rng)
    radii = radius * rng.uniform(0.85, 1.15, size=count)
    # the flower sits on the leaf or twig it anchors on, not inside it
    centers = anchors + outward * (0.35 * radii[:, None])
    phase = rng.random(count) * FLOWER_PHASE_MAX
    geo = flowers_geo(flower, str(traits.blossom_spec or "white"), centers, facing, radii,
                      rng, lod=lod, phase=phase)
    if not twigs:
        return geo
    assert wood is not None
    return concat_geo([with_phase(_twigs_to_wood(wood, anchors, traits, rng), phase), geo])


def _twigs_to_wood(
    wood: tuple[np.ndarray, np.ndarray], tips: np.ndarray, traits: Traits3D,
    rng: np.random.Generator,
) -> RawGeo:
    """A thin twig (``TWIG_TRIANGLES``) to each of ``tips`` from the nearest of points spread
    over the wood's triangles (not its ring vertices, where the twigs met in starbursts)."""
    tri = np.asarray(wood[0], dtype=np.float64)[np.asarray(wood[1], dtype=np.int64).reshape(-1, 3)]
    uv = rng.random((len(tri), 6, 2))
    uv = np.where(uv.sum(axis=-1, keepdims=True) > 1.0, 1.0 - uv, uv)
    wood_points = (tri[:, None, 0] + uv[..., :1] * (tri[:, None, 1] - tri[:, None, 0])
                   + uv[..., 1:] * (tri[:, None, 2] - tri[:, None, 0])).reshape(-1, 3)
    nearest = np.empty(len(tips), dtype=np.int64)
    w2 = (wood_points * wood_points).sum(axis=1)
    for i in range(0, len(tips), 2048):
        chunk = tips[i:i + 2048]
        d2 = (chunk * chunk).sum(axis=1)[:, None] + w2[None, :] - 2.0 * chunk @ wood_points.T
        nearest[i:i + 2048] = np.argmin(d2, axis=1)
    return frustum_tubes(wood_points[nearest], tips, np.full(len(tips), TWIG_RADIUS_CM),
                         np.full(len(tips), TWIG_RADIUS_CM * 0.4), sides=3,
                         color_rgba=bark_linear_rgba(traits.branching))


def build_blossom_accents(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    rng: np.random.Generator,
    *,
    lod: int = LOD0,
    anchor_points: np.ndarray | None = None,
    max_tris: int | None = None,
    wood: tuple[np.ndarray, np.ndarray] | None = None,
) -> RawGeo:
    """Build 3D blossoms: a crown's flowers (``Traits3D.flower`` with the ``crown`` habit:
    a ``flowers`` recipe or a fruit tree's blossom), ``clusters`` and ``puffs``. A bulb's
    and a stemmed flower's own builders place theirs (``scape`` / ``head``, #940).
    ``max_tris``: the LOD's triangles left for them; ``wood``: the plant's wood (positions,
    triangle indices) a plant that flowers on bare wood carries them on."""
    if lod == LOD2:
        return empty_geo()

    recipe = recipe_for(traits.sprite)
    geos: list[RawGeo] = []

    # 1. A crown's flowers, counted by its surface (#940)
    flower = traits.flower
    if flower is not None and flower.habit == "crown":
        geos.append(_crown_flowers_geo(traits, flower, height_cm, radius_cm, rng, lod=lod,
                                       anchor_points=anchor_points, max_tris=max_tris,
                                       wood=wood))

    # 2. `clusters` (lilac, hydrangea, rhododendron, viburnum, wisteria, chives, geranium):
    # counted by the crown's surface and sized as they really are, like a crown's flowers
    # (#940, review 2: a fixed 10 and the plant-scaled size hid every truss in a crown)
    clusters_dict = recipe.get("clusters")
    if isinstance(clusters_dict, Mapping):
        c_dark = _hex_to_linear_rgb(str(clusters_dict.get("dark", "#8a68c0")))
        c_light = _hex_to_linear_rgb(str(clusters_dict.get("light", "#d0c0f0")))
        c_occ = _hex_to_linear_rgb(str(clusters_dict.get("occ", "#4a2f80")))
        florets_per = 7 if lod == LOD0 else 4
        sides = 5 if lod == LOD0 else 4
        budget = _flower_budget(lod, max_tris)
        affordable = max(0, budget - FLOWER_BUDGET_RESERVE) // (florets_per * 4 * sides)
        surface = crown_surface_cm2(height_cm, radius_cm, traits.crown.trunk_share)
        n_clusters, cl_r = blossom_count(
            surface, CLUSTER_COVER,
            CLUSTER_CM_PER_RECIPE_RADIUS * float(clusters_dict.get("radius", 7.0)),
            affordable, enlarge_max=FLOWER_ENLARGE_MAX.get(lod, 1.0))
        if n_clusters:
            min_z = height_cm * 0.65 if traits.archetype == "allium" else None
            if anchor_points is not None and len(anchor_points) >= 4:
                anchors, outward = crown_flower_anchors(anchor_points, n_clusters, rng, min_z=min_z)
            else:
                anchors = _select_crown_anchors(None, n_clusters, height_cm, radius_cm, rng,
                                                z_range=(0.45, 0.92), radial_range=(0.45, 0.88))
                outward = normalize_vec(anchors - np.array([0.0, 0.0, height_cm * 0.45])[None, :])
            anchors = anchors + outward * (0.3 * cl_r)         # on the leaves, not in them
            pendulous = traits.sprite.name == "wisteria"
            frac = np.arange(florets_per, dtype=np.float64) / max(florets_per - 1, 1)
            if pendulous:   # a hanging conical raceme
                dz = -cl_r * 1.6 * frac
                spread = cl_r * 0.45 * (1.0 - 0.65 * frac)
            else:           # an upright panicle or a domed truss
                dz = cl_r * 0.85 * frac
                spread = cl_r * 0.55 * (1.0 - 0.45 * frac)
            ang = (np.arange(florets_per) * 2.39996)[None, :] + rng.uniform(
                -0.3, 0.3, size=(n_clusters, florets_per))
            f_centers = anchors[:, None, :] + np.stack(
                [np.cos(ang) * spread, np.sin(ang) * spread, np.broadcast_to(dz, ang.shape)], axis=-1)
            f_r = np.broadcast_to(cl_r * (0.36 - 0.10 * frac), ang.shape).reshape(-1)
            phase = np.repeat(rng.random(n_clusters) * FLOWER_PHASE_MAX, florets_per)
            geos.append(with_phase(_spheroids_geo(
                f_centers.reshape(-1, 3), f_r, f_r * (1.25 if pendulous else 0.95),
                c_light, c_dark, c_occ, sides=sides,
            ), phase))

    # 3. `puffs` (lavender flower spikes)
    puffs_dict = recipe.get("puffs")
    if isinstance(puffs_dict, Mapping):
        c_dark = _hex_to_linear_rgb(str(puffs_dict.get("dark", "#6b46ab")))
        c_light = _hex_to_linear_rgb(str(puffs_dict.get("light", "#a98fe0")))
        n_puffs = max(5, int(puffs_dict.get("n", 9)) * (2 if lod == LOD0 else 1))
        anchors = _select_crown_anchors(
            anchor_points,
            n_puffs,
            height_cm,
            radius_cm,
            rng,
            z_range=(0.68, 0.94),
            radial_range=(0.35, 0.88),
        )
        spike_h = max(height_cm * 0.14, 2.2)
        spike_r = max(radius_cm * 0.045, 0.65)
        crown_c = np.array([0.0, 0.0, height_cm * 0.35], dtype=np.float64)
        dirs = normalize_vec(anchors - crown_c[None, :] + np.array([0.0, 0.0, height_cm * 0.6])[None, :])
        p0 = anchors - dirs * (spike_h * 0.35)
        p1 = anchors + dirs * (spike_h * 0.65)
        c_mid = 0.5 * (c_dark + c_light)
        geos.append(with_phase(
            frustum_tubes(
                p0,
                p1,
                np.full(len(anchors), spike_r, dtype=np.float64),
                np.full(len(anchors), spike_r * 0.45, dtype=np.float64),
                sides=5 if lod == LOD0 else 4,
                color_rgba=(float(c_mid[0]), float(c_mid[1]), float(c_mid[2]), 1.0),
            ), rng.random(len(anchors)) * FLOWER_PHASE_MAX,
        ))

    return concat_geo(geos)


def build_umbel_accents(
    umbel_spec: Mapping[str, Any],
    palette_name: str,
    height_cm: float,
    radius_cm: float,
    rng: np.random.Generator,
    *,
    lod: int = LOD0,
    anchor_points: np.ndarray | None = None,
) -> RawGeo:
    """Build 3D compound umbels (`umbels` recipe key: spoke rays + floret discs)."""
    if lod == LOD2:
        return empty_geo()

    c_col = _hex_to_linear_rgb(str(umbel_spec.get("col", "#e8c34a")))
    c_light = _hex_to_linear_rgb(str(umbel_spec.get("light", "#f8e48a")))
    pal = PALETTES.get(palette_name, PALETTES["fresh"])
    c_ray = _hex_to_linear_rgb(pal["b1"])

    n_umbels = max(1, int(umbel_spec.get("n", 3)) * (2 if lod == LOD0 else 1))
    ref_r = float(umbel_spec.get("radius", 5.0))
    plant_scale = max(min(height_cm, radius_cm * 2.0) / 100.0, 0.32)
    umbel_r = np.clip(ref_r * 0.85 * plant_scale, 1.5, max(radius_cm * 0.24, 2.5))

    anchors = _select_crown_anchors(
        anchor_points,
        n_umbels,
        height_cm,
        radius_cm,
        rng,
        z_range=(0.65, 0.93),
        radial_range=(0.20, 0.82),
    )

    rays_per_umbel = 6 if lod == LOD0 else 4
    ray_p0: list[np.ndarray] = []
    ray_p1: list[np.ndarray] = []
    floret_centers: list[np.ndarray] = []

    for hub in anchors:
        base_hub = hub - np.array([0.0, 0.0, umbel_r * 0.45], dtype=np.float64)
        # Central ray
        ray_p0.append(base_hub)
        ray_p1.append(hub + np.array([0.0, 0.0, umbel_r * 0.12], dtype=np.float64))
        floret_centers.append(hub + np.array([0.0, 0.0, umbel_r * 0.15], dtype=np.float64))
        for r_i in range(rays_per_umbel):
            ang = 2.0 * math.pi * r_i / rays_per_umbel + float(rng.uniform(-0.15, 0.15))
            tip = hub + np.array(
                [math.cos(ang) * umbel_r * 0.78, math.sin(ang) * umbel_r * 0.78, umbel_r * 0.05],
                dtype=np.float64,
            )
            ray_p0.append(base_hub)
            ray_p1.append(tip)
            floret_centers.append(tip)

    ray_r = max(umbel_r * 0.045, 0.18)
    rays_geo = frustum_tubes(
        np.asarray(ray_p0, dtype=np.float64),
        np.asarray(ray_p1, dtype=np.float64),
        np.full(len(ray_p0), ray_r, dtype=np.float64),
        np.full(len(ray_p0), ray_r * 0.7, dtype=np.float64),
        sides=3,
        color_rgba=(float(c_ray[0]), float(c_ray[1]), float(c_ray[2]), 1.0),
    )

    fc = np.asarray(floret_centers, dtype=np.float64)
    disc_r = np.full(len(fc), max(umbel_r * 0.28, 0.55), dtype=np.float64)
    discs_geo = _spheroids_geo(
        fc,
        disc_r,
        disc_r * 0.42,
        c_light,
        c_col,
        c_col * 0.78,
        sides=5 if lod == LOD0 else 4,
    )
    # one phase an umbel, its rays and its florets (#940, review 2)
    phase = np.repeat(rng.random(len(anchors)) * FLOWER_PHASE_MAX, rays_per_umbel + 1)
    return concat_geo([with_phase(rays_geo, phase), with_phase(discs_geo, phase)])


def build_pod_accents(
    pod_spec: Mapping[str, Any],
    height_cm: float,
    radius_cm: float,
    rng: np.random.Generator,
    *,
    lod: int = LOD0,
    anchor_points: np.ndarray | None = None,
    upright: bool = False,
) -> RawGeo:
    """Build 3D elongated pods (`pods` recipe key: bean, pea, cucumber, zucchini, okra)."""
    if lod == LOD2:
        return empty_geo()

    c_dark = _hex_to_linear_rgb(str(pod_spec.get("dark", "#3f8226")))
    c_light = _hex_to_linear_rgb(str(pod_spec.get("light", "#9fdf6f")))
    c_mid = 0.55 * c_light + 0.45 * c_dark

    n_pods = max(3, int(pod_spec.get("n", 6)) * (2 if lod == LOD0 else 1))
    ref_len = float(pod_spec.get("length", 8.5))
    plant_scale = max(min(height_cm, radius_cm * 2.0) / 110.0, 0.35)
    pod_len = np.clip(ref_len * 0.85 * plant_scale, 2.2, max(height_cm * 0.18, 3.5))
    pod_r = max(pod_len * 0.12, 0.35)

    anchors = _select_crown_anchors(
        anchor_points,
        n_pods,
        height_cm,
        radius_cm,
        rng,
        z_range=(0.25, 0.82),
        radial_range=(0.35, 0.85),
    )

    p0_list: list[np.ndarray] = []
    p1_list: list[np.ndarray] = []
    r0_list: list[float] = []
    r1_list: list[float] = []

    sign_z = 1.0 if upright else -1.0
    for a_pt in anchors:
        az = math.atan2(float(a_pt[1]), float(a_pt[0])) + float(rng.uniform(-0.4, 0.4))
        curve_xy = np.array([math.cos(az), math.sin(az)], dtype=np.float64) * (pod_len * 0.16)
        mid_pt = a_pt + np.array([curve_xy[0] * 0.5, curve_xy[1] * 0.5, sign_z * pod_len * 0.5], dtype=np.float64)
        tip_pt = a_pt + np.array([curve_xy[0], curve_xy[1], sign_z * pod_len], dtype=np.float64)
        # Upper half of pod (calyx -> belly)
        p0_list.append(a_pt)
        p1_list.append(mid_pt)
        r0_list.append(pod_r * 0.55)
        r1_list.append(pod_r)
        # Lower half of pod (belly -> tapered tip)
        p0_list.append(mid_pt)
        p1_list.append(tip_pt)
        r0_list.append(pod_r)
        r1_list.append(pod_r * 0.28)

    return frustum_tubes(
        np.asarray(p0_list, dtype=np.float64),
        np.asarray(p1_list, dtype=np.float64),
        np.asarray(r0_list, dtype=np.float64),
        np.asarray(r1_list, dtype=np.float64),
        sides=5 if lod == LOD0 else 4,
        color_rgba=(float(c_mid[0]), float(c_mid[1]), float(c_mid[2]), 1.0),
    )


def build_tuber_accents(
    bulb_spec: Mapping[str, Any],
    height_cm: float,
    radius_cm: float,
    *,
    lod: int = LOD0,
    basal_center: np.ndarray | None = None,
) -> RawGeo:
    """Build a 3D partially emerged root crown / tuber (`bulb` recipe key) at the plant base."""
    if lod == LOD2:
        return empty_geo()

    triad = bulb_spec.get("triad", ("#e8c890", "#c89050", "#8a5a24"))
    if isinstance(triad, Sequence) and len(triad) >= 3:
        c_top = _hex_to_linear_rgb(str(triad[0]))
        c_mid = _hex_to_linear_rgb(str(triad[1]))
        c_bot = _hex_to_linear_rgb(str(triad[2]))
    else:
        c_top = _hex_to_linear_rgb("#e8c890")
        c_mid = _hex_to_linear_rgb("#c89050")
        c_bot = _hex_to_linear_rgb("#8a5a24")

    ref_r = float(bulb_spec.get("radius", 6.5))
    tuber_r_xy = np.clip(radius_cm * (ref_r / 28.0), max(radius_cm * 0.14, 1.0), max(radius_cm * 0.34, 2.5))
    tuber_r_z = np.clip(height_cm * 0.11, 0.8, max(height_cm * 0.20, 1.8))

    cx = float(basal_center[0]) if basal_center is not None else 0.0
    cy = float(basal_center[1]) if basal_center is not None else 0.0
    center = np.array([[cx, cy, tuber_r_z * 1.05]], dtype=np.float64)

    return _spheroids_geo(
        center,
        np.array([tuber_r_xy], dtype=np.float64),
        np.array([tuber_r_z], dtype=np.float64),
        c_top,
        c_mid,
        c_bot,
        sides=8 if lod == LOD0 else 6,
    )


def _clamp_accent_geo(geo: RawGeo, height_cm: float, radius_cm: float) -> RawGeo:
    """Clamp accent geometry inside `[0, height_cm]` and `REACH_MAX * radius_cm` with valid `vc` normals."""
    if geo.vertex_count == 0 or geo.triangle_count == 0:
        return empty_geo()

    out = geo.copy()
    p = out.pos.astype(np.float64)
    limit_r = float(radius_cm) * (REACH_MAX - 0.01)
    r = np.hypot(p[:, 0], p[:, 1])
    far = r > limit_r
    if np.any(far):
        factor = limit_r / np.maximum(r[far], 1e-6)
        p[far, 0] *= factor
        p[far, 1] *= factor
    p[:, 2] = np.clip(p[:, 2], 0.01, float(height_cm) * 0.995)
    out.pos = p.astype(np.float32)
    out.uv = out.uv.astype(np.float32).copy()
    out.uv[:, 0] = 0.0          # UV.y keeps each flower's phase (``with_phase``)
    out.nrm = _fix_vc_flat_normals(out.pos, out.nrm, out.tri)
    return out


def flower_part(geo: RawGeo, height_cm: float, radius_cm: float) -> MeshPart:
    """``geo`` - flowers a builder placed in its fitted frame (a sunflower's heads, #940) -
    clamped into the plant's height and reach, as the plant's ``flowers`` part."""
    return MeshPart(mesh=_clamp_accent_geo(geo, height_cm, radius_cm).to_mesh(),
                    material_kind="vc", casts_shadow=True, tinted=False, name=FLOWER_PART)


def build_accents(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int = 0,
    *,
    lod: int = LOD0,
    anchor_points: np.ndarray | None = None,
    basal_center: np.ndarray | None = None,
    max_tris: int | None = None,
    family: str | None = None,
    wood: tuple[np.ndarray, np.ndarray] | None = None,
) -> RawGeo:
    """Build combined seasonal accent geometry (`PART_ACCENTS`) for `traits`."""
    validate_lod(lod)
    if lod == LOD2:
        return empty_geo()

    recipe = recipe_for(traits.sprite)
    rng = _seed_rng(seed, 0xACCE5701)
    parts: list[RawGeo] = []

    # 1. Tubers / root crowns (`bulb`)
    bulb_spec = recipe.get("bulb")
    if isinstance(bulb_spec, Mapping) and family in (None, TUBER_PART):
        parts.append(
            build_tuber_accents(
                bulb_spec,
                height_cm,
                radius_cm,
                lod=lod,
                basal_center=basal_center,
            )
        )

    # 2. Pods (`pods`)
    pod_spec = recipe.get("pods")
    if isinstance(pod_spec, Mapping) and family in (None, FRUIT_PART):
        parts.append(
            build_pod_accents(
                pod_spec,
                height_cm,
                radius_cm,
                rng,
                lod=lod,
                anchor_points=anchor_points,
                upright=(traits.sprite.name == "okra"),
            )
        )

    # 3. Umbels (`umbels`)
    umbel_spec = recipe.get("umbels")
    if isinstance(umbel_spec, Mapping) and family in (None, FLOWER_PART):
        parts.append(
            build_umbel_accents(
                umbel_spec,
                traits.palette,
                height_cm,
                radius_cm,
                rng,
                lod=lod,
                anchor_points=anchor_points,
            )
        )

    # 4. Fruits (`fruit`, `fruit2`)
    fruit_spec = recipe.get("fruit")
    if isinstance(fruit_spec, Mapping) and family in (None, FRUIT_PART):
        parts.append(
            build_fruit_accents(
                fruit_spec,
                height_cm,
                radius_cm,
                rng,
                lod=lod,
                anchor_points=anchor_points,
            )
        )
    fruit2_spec = recipe.get("fruit2")
    if isinstance(fruit2_spec, Mapping) and family in (None, FRUIT_PART):
        parts.append(
            build_fruit_accents(
                fruit2_spec,
                height_cm,
                radius_cm,
                rng,
                lod=lod,
                anchor_points=anchor_points,
            )
        )

    # 5. Blossoms (a crown's `flowers` or fruit-tree blossom, `clusters`, `puffs`)
    crown_flower = traits.flower is not None and traits.flower.habit == "crown"
    if family in (None, FLOWER_PART) and (
        crown_flower or "clusters" in recipe or "puffs" in recipe
    ):
        used = sum(part.triangle_count for part in parts)
        parts.append(
            build_blossom_accents(
                traits,
                height_cm,
                radius_cm,
                rng,
                lod=lod,
                anchor_points=anchor_points,
                max_tris=None if max_tris is None else max_tris - used,
                wood=wood,
            )
        )

    if not parts:
        return empty_geo()

    combined = concat_geo(parts)
    if max_tris is not None and combined.triangle_count > max_tris:
        if max_tris <= 0:
            return empty_geo()
        # Keep whole triangles within budget
        kept_tri = combined.tri[:max_tris]
        used = np.zeros(combined.vertex_count, dtype=bool)
        used[kept_tri.ravel()] = True
        remap = np.cumsum(used, dtype=np.uint32) - 1
        combined = RawGeo(
            pos=combined.pos[used],
            nrm=combined.nrm[used],
            col=combined.col[used],
            uv=combined.uv[used],
            tri=remap[kept_tri],
        )

    return _clamp_accent_geo(combined, height_cm, radius_cm)


def attach_accents(
    parts: tuple[MeshPart, ...],
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
) -> tuple[MeshPart, ...]:
    """Attach `PART_ACCENTS` to an already-fitted `(wood, foliage)` part tuple without altering them."""
    if lod == LOD2:
        return parts
    # A bulb's and a stemmed flower's builder places its own flowers (#940)
    present = {p.name for p in parts} & SEASONAL_PARTS

    used_tris = sum(p.mesh.triangle_count for p in parts)
    remaining = triangle_budget_for_lod(lod) - used_tris
    if remaining < 24:
        return parts

    foliage_part = next((p for p in parts if p.name == PART_FOLIAGE), None)
    wood_part = next((p for p in parts if p.name == PART_WOOD), None)
    anchors = foliage_part.mesh.positions if foliage_part is not None else None

    basal_center: np.ndarray | None = None
    if wood_part is not None and wood_part.mesh.vertex_count > 0:
        wpos = wood_part.mesh.positions
        low_mask = wpos[:, 2] <= max(float(height_cm) * 0.15, 2.0)
        if np.any(low_mask):
            basal_center = wpos[low_mask].mean(axis=0).astype(np.float64)

    added: list[MeshPart] = []
    for family in (TUBER_PART, FRUIT_PART, FLOWER_PART):
        if family in present:
            continue
        accent_geo = build_accents(
            traits, height_cm, radius_cm, seed, lod=lod,
            anchor_points=anchors, basal_center=basal_center,
            max_tris=remaining, family=family,
            wood=(wood_part.mesh.positions, wood_part.mesh.indices) if wood_part is not None else None,
        )
        if accent_geo.triangle_count == 0:
            continue
        remaining -= accent_geo.triangle_count
        added.append(MeshPart(
            mesh=accent_geo.to_mesh(), material_kind="vc", casts_shadow=True,
            tinted=False, name=family,
        ))
    return (*parts, *added)



__all__ = [
    "ACCENT_FAMILIES",
    "CROWN_SHELL",
    "FLOWER_ENLARGE_MAX",
    "FLOWER_PART",
    "FRUIT_PART",
    "TUBER_PART",
    "SEASONAL_PARTS",
    "attach_accents",
    "blossom_count",
    "build_accents",
    "build_blossom_accents",
    "build_fruit_accents",
    "build_pod_accents",
    "build_tuber_accents",
    "build_umbel_accents",
    "crown_flower_anchors",
    "flower_part",
    "wood_flower_anchors",
    "with_phase",
    "flower_triangles",
    "flowers_geo",
]

