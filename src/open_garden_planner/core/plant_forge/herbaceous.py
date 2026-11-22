"""Forged herbaceous archetypes for Plant Forge (Phase 17 L3.3, #387):
rosettes, grasses, pinnate/feathery leaves, alliums, heads, ground covers, and flowers.

Handles ``"rosette"``, ``"grass"``, ``"feathery"``, ``"allium"``, ``"head"``,
``"ground"``, and ``"flower"`` recipes across ``LOD0`` (≤ 25k tris), ``LOD1``
(≤ 6k tris), and ``LOD2`` (≤ 800 tris).

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

import math

import numpy as np

from ..plant_art import recipe_for
from ..plant_art.traits3d import Traits3D
from ..scene3d.color import srgb_to_linear
from ..scene3d.mesh import MeshPart
from .accents import (
    FLOWER_PART,
    FLOWER_PHASE_MAX,
    PETAL_RISE_PER_CUP,
    far_flower_tint,
    far_patches_geo,
    flower_accent_colour,
    flower_part,
    flowers_geo,
    with_phase,
)
from .assemble import PART_WOOD, fit_forged_parts
from .foliage import (
    RawGeo,
    concat_geo,
    crown_leaf_budget,
    empty_geo,
    micro_leaves,
    normalize_vec,
    palette_leaf_colors,
)
from .lod import LOD0, LOD1, LOD2, validate_lod
from .trees import bark_linear_rgba
from .tube import frustum_tubes

GOLDEN_ANGLE: float = math.pi * (3.0 - math.sqrt(5.0))


#: How far a pinned leaf may turn off its plan axis (rad): within it the leaf's tip stays
#: inside REACH_MAX once the fit has scaled the box to the canopy (cos 0.15 = 0.989).
_AXIS_PIN_JITTER: float = 0.15


def _pin_spread_to_axes(azimuths: np.ndarray, reaches: np.ndarray, rng: np.random.Generator) -> None:
    """Turn the last four leaves (the outermost) onto the plan's four axes at the
    clump's longest reach, in place (#940). The fit scales the clump's BOX to the canopy
    diameter and then pulls every vertex beyond ``REACH_MAX`` back onto the circle: with
    a few leaves the box's extremes sit on diagonals, the pull takes them in, and the
    clump came out at 0.87 of its spread (a daffodil at LOD2). Leaves along the axes
    hold the box's extremes where the pull never reaches."""
    k = min(4, len(azimuths))
    azimuths[-k:] = np.arange(k) * (math.pi / 2.0) + rng.uniform(-_AXIS_PIN_JITTER, _AXIS_PIN_JITTER, size=k)
    reaches[-k:] = float(reaches.max())


def _seed_rng(seed: int, salt: int) -> np.random.Generator:
    mixed = ((int(seed) * 2654435761) ^ salt) & 0xFFFFFFFFFFFFFFFF
    return np.random.default_rng(mixed)


def _curved_blades_geo(
    origins: np.ndarray,
    azimuths: np.ndarray,
    reaches: np.ndarray,
    peak_z: np.ndarray,
    tip_z: np.ndarray,
    base_widths: np.ndarray,
    tip_width_ratio: float,
    segs: int,
    colors_per_blade: np.ndarray,
    rng: np.random.Generator,
    *,
    center: np.ndarray,
    cup: float = 0.08,
) -> RawGeo:
    """Build multi-segment arched/cupped blades ``(B, segs)`` as a single ``RawGeo``."""
    b = len(origins)
    if b == 0:
        return empty_geo()

    s_Count = max(int(segs), 2)
    t = np.linspace(0.0, 1.0, s_Count + 1, dtype=np.float64)[None, :]  # (1, S+1)

    cos_az = np.cos(azimuths)[:, None]
    sin_az = np.sin(azimuths)[:, None]
    horiz_r = reaches[:, None] * (t**0.92)

    # Quadratic Bezier arch in Z from origin_z through peak_z to tip_z
    z0 = origins[:, 2:3]
    zp = peak_z[:, None]
    zt = tip_z[:, None]
    z_curve = ((1.0 - t) ** 2) * z0 + 2.0 * (1.0 - t) * t * zp + (t**2) * zt

    cx = origins[:, 0:1] + cos_az * horiz_r
    cy = origins[:, 1:2] + sin_az * horiz_r
    cz = np.maximum(z_curve, 0.0)

    # Width envelope along blade: widens slightly in mid-blade then tapers to tip
    w_env = np.sin(t * math.pi * 0.85) * (1.0 - tip_width_ratio) + tip_width_ratio * (1.0 - 0.6 * t)
    w_env[:, 0] = 0.45
    half_w = 0.5 * base_widths[:, None] * w_env

    side_x = -sin_az
    side_y = cos_az
    cup_dz = half_w * float(cup)

    # Left and right rails along each blade: (B, S+1, 2, 3)
    left = np.stack([cx + side_x * half_w, cy + side_y * half_w, cz + cup_dz], axis=-1)
    right = np.stack([cx - side_x * half_w, cy - side_y * half_w, cz + cup_dz], axis=-1)
    verts = np.stack([left, right], axis=2).reshape(-1, 3).astype(np.float32)

    # Spherized outward normals
    nrm = normalize_vec(verts.astype(np.float64) - center[None, :])
    nrm[:, 2] = np.maximum(nrm[:, 2], 0.15)
    nrm = normalize_vec(nrm).astype(np.float32)

    v_per_blade = 2 * (s_Count + 1)
    cols = np.repeat(colors_per_blade.astype(np.float32), v_per_blade, axis=0)
    # Brighten blade tips slightly
    ring_t = np.repeat(np.linspace(0.92, 1.06, s_Count + 1, dtype=np.float32), 2)
    shade_t = np.tile(ring_t, b)[:, None]
    cols[:, :3] = np.clip(cols[:, :3] * shade_t, 0.0, 1.0)

    z_max = max(float(np.max(verts[:, 2])), 1.0)
    wind = np.clip(verts[:, 2:3] / z_max, 0.0, 1.0).astype(np.float32)
    phases = np.repeat(rng.random((b, 1), dtype=np.float32), v_per_blade, axis=0)
    uv = np.concatenate([wind, phases], axis=1)

    # Triangles per blade segment: 2 vertices per step -> quad [2*k, 2*k+1, 2*k+3, 2*k+2]
    k_idx = np.arange(s_Count, dtype=np.uint32)
    i0 = 2 * k_idx
    i1 = 2 * k_idx + 1
    i2 = 2 * (k_idx + 1)
    i3 = 2 * (k_idx + 1) + 1
    blade_tris = np.concatenate(
        [np.stack([i0, i1, i3], axis=1), np.stack([i0, i3, i2], axis=1)],
        axis=0,
    )  # (2*S, 3)
    offsets = (np.arange(b, dtype=np.uint32) * v_per_blade)[:, None, None]
    tri = (blade_tris[None, :, :] + offsets).reshape(-1, 3)
    return RawGeo(pos=verts, nrm=nrm, col=cols, uv=uv, tri=tri)


def build_forged_rosette(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a phyllotaxis rosette (`"rosette"` archetype) with cupped blades + micro-leaves."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0x1205E77E)

    if lod == LOD0:
        n_blades = 34
        segs = 5
        n_micro = 240
        sides = 5
    elif lod == LOD1:
        n_blades = 20
        segs = 4
        n_micro = 90
        sides = 4
    else:
        n_blades = 12
        segs = 3
        n_micro = 24
        sides = 4

    # Short basal crown stem (`PART_WOOD`)
    lean_az = float(rng.uniform(0.0, 2.0 * math.pi))
    lean_xy = radius_cm * float(rng.uniform(0.08, 0.22))
    crown_top = np.array(
        [math.cos(lean_az) * lean_xy, math.sin(lean_az) * lean_xy, height_cm * 0.28],
        dtype=np.float64,
    )
    stem_r = max(radius_cm * 0.08, 0.6)
    wood = frustum_tubes(
        np.array([[0.0, 0.0, 0.0]], dtype=np.float64),
        crown_top[None, :],
        np.array([stem_r]),
        np.array([stem_r * 0.65]),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    # Golden-angle phyllotaxis spiral from inner upright heart to outer spreading leaves
    idx = np.arange(n_blades, dtype=np.float64)
    frac = idx / max(n_blades - 1, 1)
    az0 = float(rng.uniform(0.0, 2.0 * math.pi))
    dom_az = float(rng.uniform(0.0, 2.0 * math.pi))
    az = az0 + idx * GOLDEN_ANGLE + rng.uniform(-0.18, 0.18, size=n_blades)

    asym = 1.0 + 0.28 * np.cos(az - dom_az)
    reaches = radius_cm * (0.22 + 0.78 * (frac**0.75)) * asym * rng.uniform(0.85, 1.12, size=n_blades)
    peak_z = height_cm * (0.98 - 0.48 * (frac**0.85)) * (1.0 + 0.18 * np.sin(az - dom_az))
    tip_z = height_cm * (0.82 - 0.68 * (frac**0.75)) * rng.uniform(0.82, 1.12, size=n_blades)
    base_widths = radius_cm * (0.18 + 0.26 * frac) * traits.leaf.width_ratio * 1.35

    origins = np.column_stack(
        [
            np.cos(az) * radius_cm * 0.05 * frac,
            np.sin(az) * radius_cm * 0.05 * frac,
            height_cm * 0.04 * (1.0 - frac),
        ]
    )
    blade_cols = palette_leaf_colors(traits.palette, traits.sprite, 1.0 - 0.65 * frac, frac, rng)
    center = np.array([0.0, 0.0, height_cm * 0.35], dtype=np.float64)

    blades_geo = _curved_blades_geo(
        origins,
        az,
        reaches,
        peak_z,
        tip_z,
        base_widths,
        0.38 if traits.leaf.narrow else 0.72,
        segs,
        blade_cols,
        rng,
        center=center,
        cup=0.14,
    )

    # Add frilly/lobed micro-leaf detail around the rosette whorls
    m_az = rng.uniform(0.0, 2.0 * math.pi, size=n_micro)
    m_f = rng.uniform(0.12, 0.95, size=n_micro)
    m_asym = 1.0 + 0.25 * np.cos(m_az - dom_az)
    m_r = radius_cm * m_f * m_asym
    m_z = height_cm * (0.88 - 0.58 * m_f) * rng.uniform(0.75, 1.15, size=n_micro)
    m_pts = np.column_stack([m_r * np.cos(m_az), m_r * np.sin(m_az), m_z])
    m_out = normalize_vec(m_pts - center[None, :])
    m_cols = palette_leaf_colors(traits.palette, traits.sprite, m_z / max(height_cm, 1.0), m_f, rng)
    m_len = max(min(height_cm, radius_cm) * 0.18, 2.0) * rng.uniform(0.75, 1.25, size=n_micro)
    m_wid = m_len * traits.leaf.width_ratio
    micro_geo = micro_leaves(m_pts, m_out, m_len, m_wid, m_cols, rng, center=center, spherize=0.70, droop=0.12, cup=0.08)

    foliage = concat_geo([blades_geo, micro_geo])
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


def build_forged_grass(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge an arching fountain grass / cereal clump (`"grass"` archetype).

    A grass whose crown is a ``vase`` is a clump of woody culms (bamboo, #940):
    ``_forged_culm_clump`` builds it instead of basal blades.
    """
    validate_lod(lod)
    if traits.crown.shape == "vase":
        return _forged_culm_clump(traits, height_cm, radius_cm, seed, lod=lod, accents=accents)
    if traits.flower is not None and traits.flower.habit == "scape":
        return _forged_flowering_bulb(traits, height_cm, radius_cm, seed, lod=lod)
    rng = _seed_rng(seed, 0x612A5501)

    if lod == LOD0:
        n_culms = 6
        n_blades = 56
        segs = 6
        n_plumes = 120
        sides = 5
    elif lod == LOD1:
        n_culms = 4
        n_blades = 28
        segs = 4
        n_plumes = 50
        sides = 4
    else:
        n_culms = 3
        n_blades = 14
        segs = 3
        n_plumes = 16
        sides = 4

    dom_az = float(rng.uniform(0.0, 2.0 * math.pi))
    culm_az = np.linspace(0.0, 2.0 * math.pi, n_culms, endpoint=False) + float(
        rng.uniform(0.0, 2.0 * math.pi)
    ) + rng.uniform(-0.35, 0.35, size=n_culms)
    culm_r = radius_cm * rng.uniform(0.18, 0.52, size=n_culms) * (1.0 + 0.30 * np.cos(culm_az - dom_az))
    culm_z = height_cm * rng.uniform(0.62, 0.96, size=n_culms)
    culm_z[int(rng.integers(0, n_culms))] = height_cm * 0.98

    p0 = np.column_stack([np.cos(culm_az) * radius_cm * 0.08, np.sin(culm_az) * radius_cm * 0.08, np.zeros(n_culms)])
    p1 = np.column_stack([np.cos(culm_az) * culm_r, np.sin(culm_az) * culm_r, culm_z])
    c_rad = max(min(height_cm, radius_cm) * 0.025, 0.35)
    wood = frustum_tubes(
        p0,
        p1,
        np.full(n_culms, c_rad),
        np.full(n_culms, c_rad * 0.4),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    idx = np.arange(n_blades, dtype=np.float64)
    frac = idx / max(n_blades - 1, 1)
    az = float(rng.uniform(0.0, 2.0 * math.pi)) + idx * GOLDEN_ANGLE + rng.uniform(-0.22, 0.22, size=n_blades)
    asym = 1.0 + 0.34 * np.cos(az - dom_az)
    reaches = radius_cm * (0.28 + 0.72 * (frac**0.7)) * asym * rng.uniform(0.80, 1.15, size=n_blades)
    peak_z = height_cm * (0.98 - 0.28 * frac) * rng.uniform(0.78, 1.05, size=n_blades)
    tip_z = height_cm * (0.85 - 0.58 * frac) * rng.uniform(0.65, 1.05, size=n_blades)
    widths = max(radius_cm * 0.075, 0.8) * rng.uniform(0.75, 1.25, size=n_blades)

    origins = np.column_stack(
        [
            np.cos(az) * radius_cm * 0.12 * frac,
            np.sin(az) * radius_cm * 0.12 * frac,
            np.zeros(n_blades),
        ]
    )
    blade_cols = palette_leaf_colors(traits.palette, traits.sprite, peak_z / max(height_cm, 1.0), frac, rng)
    center = np.array([0.0, 0.0, height_cm * 0.45], dtype=np.float64)
    blades = _curved_blades_geo(
        origins,
        az,
        reaches,
        peak_z,
        tip_z,
        widths,
        0.14,
        segs,
        blade_cols,
        rng,
        center=center,
        cup=0.04,
    )

    # Upper leaf/plume sprays around the culm tips
    chosen = rng.integers(0, n_culms, size=n_plumes)
    plume_pts = p1[chosen] + rng.normal(0.0, radius_cm * 0.14, size=(n_plumes, 3))
    plume_pts[:, 2] = np.clip(plume_pts[:, 2], height_cm * 0.25, height_cm)
    plume_out = normalize_vec(plume_pts - center[None, :])
    plume_cols = palette_leaf_colors(
        traits.palette,
        traits.sprite,
        plume_pts[:, 2] / max(height_cm, 1.0),
        np.ones(n_plumes) * 0.85,
        rng,
    )
    p_len = max(min(height_cm, radius_cm) * 0.16, 2.0) * rng.uniform(0.8, 1.25, size=n_plumes)
    plumes = micro_leaves(plume_pts, plume_out, p_len, p_len * 0.22, plume_cols, rng, center=center, spherize=0.65, droop=0.25)

    foliage = concat_geo([blades, plumes])
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


#: A flowering bulb's leaves stop at this share of its height; leafless scapes carry
#: its flowers above them to the plant's full height (#940). Before, the blades and
#: the leaf sprays at the culm tips reached the top, and the flowers sat among them.
BULB_LEAF_TOP: float = 0.6
#: A bulb's neck - its wood all year, the scapes going with its flowers - as a share of
#: its height.
BULB_NECK: float = 0.05
#: The most flowers one bulb clump shows (a big drift of one item stays affordable).
BULB_FLOWERS_MAX: int = 24
#: Per LOD: strap leaves, segments per leaf, scape sides.
_BULB_LODS: dict[int, tuple[int, int, int]] = {LOD0: (22, 5, 5), LOD1: (14, 4, 4)}
_BULB_LOD2: tuple[int, int, int] = (8, 3, 4)


def bulb_flower_count(radius_cm: float, flower_radius_cm: float, cover: float) -> int:
    """How many flowers a bulb clump of ``radius_cm`` shows: they cover ``cover`` of its
    ground seen from above (``FlowerTraits.cover``), at least one (#940)."""
    share = cover * (radius_cm / max(flower_radius_cm, 1e-3)) ** 2
    return int(min(max(round(share), 1), BULB_FLOWERS_MAX))


def _forged_flowering_bulb(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int,
) -> tuple[MeshPart, ...]:
    """A flowering bulb (tulip, daffodil, crocus, iris, lily; #940): a tuft of strap
    leaves up to ``BULB_LEAF_TOP`` of its height and one leafless scape per flower, the
    flower on its tip at the top. Scapes and flowers are one ``flowers`` part inside the
    fit, so the plant's top is a flower's and out of bloom the bulb is its leaves on its
    neck (its wood) - at LOD2 too, where each scape carries a far patch of its petal
    colour (#948, #971)."""
    flower = traits.flower
    assert flower is not None
    rng = _seed_rng(seed, 0xB01B5CA9)
    n_blades, segs, sides = _BULB_LODS.get(lod, _BULB_LOD2)
    n_flowers = bulb_flower_count(radius_cm, flower.radius_cm, flower.cover)
    r_f = flower.radius_cm * rng.uniform(0.9, 1.1, size=n_flowers)

    # The scapes: a sunflower-seed spiral inside the clump, each flower its own height
    k = np.arange(n_flowers, dtype=np.float64)
    az = float(rng.uniform(0.0, 2.0 * math.pi)) + k * GOLDEN_ANGLE
    reach = radius_cm * np.minimum(0.15 + 0.5 * np.sqrt((k + 0.5) / n_flowers), 0.75)
    reach = np.maximum(reach - 0.4 * r_f, 0.0) if n_flowers > 1 else reach * 0.0
    # how far a flower stands above its scape's tip (the fit takes the rest)
    rise = r_f * np.maximum(PETAL_RISE_PER_CUP * flower.cup * flower.face_up, 1.0 - flower.face_up)
    tip_z = (height_cm - rise) * rng.uniform(0.86, 1.0, size=n_flowers)
    tallest = int(rng.integers(0, n_flowers))
    tip_z[tallest] = height_cm - rise[tallest]
    tips = np.column_stack([np.cos(az) * reach, np.sin(az) * reach, tip_z])
    roots = np.column_stack([np.cos(az) * radius_cm * 0.06, np.sin(az) * radius_cm * 0.06,
                             np.zeros(n_flowers)])
    scape_r = max(min(height_cm, radius_cm) * 0.02, 0.22)
    stem_rgba = bark_linear_rgba(traits.branching)
    scapes = frustum_tubes(roots, tips, np.full(n_flowers, scape_r), np.full(n_flowers, scape_r * 0.7),
                           sides=sides, color_rgba=stem_rgba)
    # the bulb's neck, where its leaves and scapes leave the ground: its wood all year
    neck = frustum_tubes(np.zeros((1, 3)), np.array([[0.0, 0.0, max(height_cm * BULB_NECK, 0.5)]]),
                         np.array([scape_r * 2.4]), np.array([scape_r * 1.6]),
                         sides=sides, color_rgba=stem_rgba)

    # The leaves: broad straps arching from the base, below the flowers
    idx = np.arange(n_blades, dtype=np.float64)
    frac = idx / max(n_blades - 1, 1)
    b_az = float(rng.uniform(0.0, 2.0 * math.pi)) + idx * GOLDEN_ANGLE + rng.uniform(-0.22, 0.22, size=n_blades)
    reaches = radius_cm * (0.35 + 0.65 * (frac ** 0.7)) * rng.uniform(0.80, 1.10, size=n_blades)
    _pin_spread_to_axes(b_az, reaches, rng)
    leaf_top = BULB_LEAF_TOP * height_cm
    peak_z = leaf_top * (1.0 - 0.35 * frac) * rng.uniform(0.80, 1.0, size=n_blades)
    blade_tip_z = leaf_top * (0.75 - 0.55 * frac) * rng.uniform(0.70, 1.0, size=n_blades)
    strap = traits.leaf.length_cm * traits.leaf.width_ratio
    widths = min(strap, radius_cm * 0.35) * rng.uniform(0.80, 1.15, size=n_blades)
    origins = np.column_stack([np.cos(b_az) * radius_cm * 0.1 * frac,
                               np.sin(b_az) * radius_cm * 0.1 * frac, np.zeros(n_blades)])
    cols = palette_leaf_colors(traits.palette, traits.sprite, peak_z / max(height_cm, 1.0), frac, rng)
    center = np.array([0.0, 0.0, leaf_top * 0.5], dtype=np.float64)
    foliage = _curved_blades_geo(origins, b_az, reaches, peak_z, blade_tip_z, widths, 0.30,
                                 segs, cols, rng, center=center, cup=0.10)

    if lod == LOD2:
        # #971/#948: the scapes are the flowers' stalks, so they go with the flowers
        # out of bloom - a bulb in July was a bunch of bare stalks. Each carries a far
        # patch of its petal colour, a bed cue at distance rather than a single-plant read.
        phase = rng.random(n_flowers) * FLOWER_PHASE_MAX
        outward = normalize_vec(np.column_stack([
            np.cos(az), np.sin(az), np.full(n_flowers, 0.8),
        ]))
        far = far_patches_geo(
            tips, outward,
            np.minimum(np.maximum(2.5 * r_f, 0.12 * height_cm), 0.22 * radius_cm),
            far_flower_tint(flower_accent_colour(traits)), phase,
        )
        return fit_forged_parts(
            neck, foliage, concat_geo([with_phase(scapes, phase), far]),
            height_cm, radius_cm, accents_name=FLOWER_PART,
        )
    out = np.column_stack([np.cos(az), np.sin(az), np.zeros(n_flowers)])
    facing = normalize_vec((1.0 - flower.face_up) * out + flower.face_up * np.array([0.0, 0.0, 1.0])
                           + rng.normal(0.0, 0.10, size=(n_flowers, 3)))
    phase = rng.random(n_flowers) * FLOWER_PHASE_MAX
    flowers = flowers_geo(flower, str(traits.blossom_spec or "white"), tips, facing, r_f, rng,
                          lod=lod, phase=phase)
    # A scape is its flower's stalk: it rises with the flower and goes with it, so ten
    # months a year a bulb is its leaves, not a bunch of bare stalks (#940, review 2).
    return fit_forged_parts(neck, foliage, concat_geo([with_phase(scapes, phase), flowers]),
                            height_cm, radius_cm, accents_name=FLOWER_PART)


#: Per LOD: culms, segments per culm, tube sides, the most leaves.
_CULM_LODS: dict[int, tuple[int, int, int, int]] = {
    LOD0: (40, 6, 5, 4500),
    LOD1: (18, 4, 4, 1800),
}
_CULM_LOD2: tuple[int, int, int, int] = (8, 3, 3, 250)


def _forged_culm_clump(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """A clump of slender woody culms that arch outward at the top, leafy in their
    upper part (bamboo, #940) — the grass archetype at 3-4 m.

    The basal-blade fountain of ``build_forged_grass`` stretched to that height is a
    pampas grass of 4 m strap leaves. Here the culms rise from a tight rhizome clump
    (``trunk_share`` of the height bare), lean out and bend over under their leaves
    (``droop``); the leaves are small sprays along the culms, counted by the crown's
    surface (coverage 1.6, ``crown_leaf_budget``). Everything is one vectorised pass.
    """
    rng = _seed_rng(seed, 0x0BA3B000)
    n_culms, segs, sides, max_leaves = _CULM_LODS.get(lod, _CULM_LOD2)

    # Culm feet in the clump, dense toward its middle; each culm leans out along
    # its own azimuth and bends over at the top.
    foot_az = rng.uniform(0.0, 2.0 * math.pi, size=n_culms)
    foot_r = radius_cm * 0.30 * np.sqrt(rng.uniform(0.0, 1.0, size=n_culms))
    lean_az = foot_az + rng.uniform(-0.45, 0.45, size=n_culms)
    tall = rng.uniform(0.62, 1.0, size=n_culms)
    tall[int(rng.integers(0, n_culms))] = 1.0
    # Angle from the vertical along the culm: nearly upright below, arching above.
    lean0 = np.radians(rng.uniform(2.0, 12.0, size=n_culms)) * (0.4 + foot_r / max(radius_cm * 0.3, 1e-6))
    bend = np.radians(rng.uniform(45.0, 80.0, size=n_culms)) * (0.6 + float(traits.crown.droop))
    t = np.linspace(0.0, 1.0, segs + 1)[None, :]
    theta = lean0[:, None] + bend[:, None] * t**2.2
    step = 1.0 / segs
    rise = np.cumsum(np.cos(theta[:, :-1]) * step, axis=1)
    out = np.cumsum(np.sin(theta[:, :-1]) * step, axis=1)
    rise = np.concatenate([np.zeros((n_culms, 1)), rise], axis=1)
    out = np.concatenate([np.zeros((n_culms, 1)), out], axis=1)
    # Scale each culm so its highest point is its own share of the height.
    length = tall * height_cm / np.maximum(rise.max(axis=1), 1e-6)
    z = rise * length[:, None]
    reach = out * length[:, None]
    cx = np.cos(foot_az)[:, None] * foot_r[:, None] + np.cos(lean_az)[:, None] * reach
    cy = np.sin(foot_az)[:, None] * foot_r[:, None] + np.sin(lean_az)[:, None] * reach
    nodes = np.stack([cx, cy, z], axis=-1)                       # (culms, segs + 1, 3)

    culm_r = max(height_cm * 0.0028, 0.4) * rng.uniform(0.8, 1.15, size=n_culms)
    taper = 1.0 - 0.6 * t[0]
    r_nodes = culm_r[:, None] * taper[None, :]
    wood = frustum_tubes(
        nodes[:, :-1].reshape(-1, 3), nodes[:, 1:].reshape(-1, 3),
        r_nodes[:, :-1].reshape(-1), r_nodes[:, 1:].reshape(-1),
        sides=sides, color_rgba=bark_linear_rgba(traits.branching),
    )

    # Leaves on the culms' upper part, as many as cover the crown's surface.
    bare = float(traits.crown.trunk_share)
    base_len = max(traits.leaf.length_cm * max(height_cm / 320.0, 0.35), 2.0)
    total, leaf_len = crown_leaf_budget(height_cm, radius_cm, bare, base_len,
                                        traits.leaf.width_ratio, max_leaves)
    which = rng.integers(0, n_culms, size=total)
    along = bare + (1.0 - bare) * rng.uniform(0.0, 1.0, size=total) ** 0.7
    pos_f = along * segs
    seg_i = np.minimum(pos_f.astype(np.int64), segs - 1)
    frac = (pos_f - seg_i)[:, None]
    anchor = nodes[which, seg_i] * (1.0 - frac) + nodes[which, seg_i + 1] * frac
    spray = leaf_len * 0.9
    jitter = rng.normal(0.0, 1.0, size=(total, 3))
    jitter[:, 2] = -np.abs(jitter[:, 2]) * 0.6                   # sprays hang
    leaf_pts = anchor + normalize_vec(jitter) * (spray * rng.uniform(0.2, 1.0, size=(total, 1)))
    leaf_pts[:, 2] = np.clip(leaf_pts[:, 2], height_cm * bare * 0.8, height_cm)

    center = np.array([0.0, 0.0, height_cm * 0.55], dtype=np.float64)
    radial = leaf_pts - np.array([0.0, 0.0, 1.0]) * leaf_pts[:, 2:3]
    outward = normalize_vec(0.55 * normalize_vec(radial + 1e-6) + 0.45 * normalize_vec(leaf_pts - center))
    colors = palette_leaf_colors(
        traits.palette, traits.sprite, leaf_pts[:, 2] / max(height_cm, 1.0),
        np.hypot(leaf_pts[:, 0], leaf_pts[:, 1]) / max(radius_cm, 1.0), rng,
    )
    lengths = leaf_len * rng.uniform(0.8, 1.2, size=total)
    foliage = micro_leaves(leaf_pts, outward, lengths, lengths * traits.leaf.width_ratio, colors, rng,
                           center=center, spherize=0.62, droop=float(traits.crown.droop), cup=0.04)
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


def build_forged_feathery(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a compound pinnate / feathery herb or fern (`"feathery"` archetype)."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0xFEA74E12)

    if lod == LOD0:
        n_fronds = 14
        pinnae_per_frond = 28
        sides = 5
    elif lod == LOD1:
        n_fronds = 10
        pinnae_per_frond = 14
        sides = 4
    else:
        n_fronds = 6
        pinnae_per_frond = 6
        sides = 4

    dom_az = float(rng.uniform(0.0, 2.0 * math.pi))
    az = np.linspace(0.0, 2.0 * math.pi, n_fronds, endpoint=False) + float(
        rng.uniform(0.0, 2.0 * math.pi)
    ) + rng.uniform(-0.28, 0.28, size=n_fronds)
    asym = 1.0 + 0.32 * np.cos(az - dom_az)
    reaches = radius_cm * rng.uniform(0.62, 1.04, size=n_fronds) * asym
    top_z = height_cm * rng.uniform(0.55, 0.98, size=n_fronds)
    top_z[int(rng.integers(0, n_fronds))] = height_cm

    p0 = np.column_stack([np.cos(az) * radius_cm * 0.05, np.sin(az) * radius_cm * 0.05, np.zeros(n_fronds)])
    p1 = np.column_stack([np.cos(az) * reaches * 0.65, np.sin(az) * reaches * 0.65, top_z * 0.82])
    stem_r = max(min(height_cm, radius_cm) * 0.022, 0.35)
    wood = frustum_tubes(
        p0,
        p1,
        np.full(n_fronds, stem_r),
        np.full(n_fronds, stem_r * 0.38),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    pts_list: list[np.ndarray] = []
    hf_list: list[np.ndarray] = []
    df_list: list[np.ndarray] = []

    for i in range(n_fronds):
        f_az = float(az[i])
        f_r = float(reaches[i])
        f_z = float(top_z[i])
        s = np.linspace(0.18, 1.0, pinnae_per_frond)
        horiz = np.array([math.cos(f_az), math.sin(f_az)], dtype=np.float64)
        lat = np.array([-math.sin(f_az), math.cos(f_az)], dtype=np.float64)
        spread_w = f_r * 0.28 * np.sin(s * math.pi * 0.9)
        alt_sign = np.where((np.arange(pinnae_per_frond) % 2) == 0, 1.0, -1.0)
        xy = (
            horiz[None, :] * (f_r * s[:, None])
            + lat[None, :] * (spread_w * alt_sign * rng.uniform(0.4, 1.0, size=pinnae_per_frond))[:, None]
        )
        z = f_z * (1.15 * s - 0.32 * (s**1.7))
        z = np.clip(z, height_cm * 0.04, height_cm)
        pts_list.append(np.column_stack([xy, z]))
        hf_list.append(z / max(height_cm, 1.0))
        df_list.append(s)

    all_pts = np.concatenate(pts_list, axis=0)
    all_hf = np.concatenate(hf_list, axis=0)
    all_df = np.concatenate(df_list, axis=0)
    center = np.array([0.0, 0.0, height_cm * 0.45], dtype=np.float64)
    outward = normalize_vec(all_pts - center[None, :])
    colors = palette_leaf_colors(traits.palette, traits.sprite, all_hf, all_df, rng)

    lod_scale = 1.0 if lod == LOD0 else (1.5 if lod == LOD1 else 2.3)
    p_len = max(min(height_cm, radius_cm * 1.8) * 0.12 * lod_scale, 1.8) * rng.uniform(0.75, 1.25, size=len(all_pts))
    p_wid = p_len * 0.42
    foliage = micro_leaves(all_pts, outward, p_len, p_wid, colors, rng, center=center, spherize=0.68, droop=0.20, cup=0.04)
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


def build_forged_allium(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge an allium (`"allium"` archetype) with basal neck, upright tubular blades, and scapes."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0xA1110301)

    if lod == LOD0:
        n_blades = 26
        segs = 5
        n_umbel_leaves = 110
        sides = 6
    elif lod == LOD1:
        n_blades = 16
        segs = 4
        n_umbel_leaves = 48
        sides = 5
    else:
        n_blades = 10
        segs = 3
        n_umbel_leaves = 16
        sides = 4

    dom_az = float(rng.uniform(0.0, 2.0 * math.pi))
    neck_lean = radius_cm * float(rng.uniform(0.08, 0.22))
    neck_top = np.array(
        [math.cos(dom_az) * neck_lean, math.sin(dom_az) * neck_lean, height_cm * 0.36],
        dtype=np.float64,
    )
    neck_r = max(radius_cm * 0.11, 0.7)
    wood = frustum_tubes(
        np.array([[0.0, 0.0, 0.0]], dtype=np.float64),
        neck_top[None, :],
        np.array([neck_r * 1.2]),
        np.array([neck_r * 0.75]),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    idx = np.arange(n_blades, dtype=np.float64)
    frac = idx / max(n_blades - 1, 1)
    az = float(rng.uniform(0.0, 2.0 * math.pi)) + idx * GOLDEN_ANGLE + rng.uniform(-0.20, 0.20, size=n_blades)
    asym = 1.0 + 0.32 * np.cos(az - dom_az)
    reaches = radius_cm * (0.25 + 0.75 * (frac**0.8)) * asym * rng.uniform(0.82, 1.15, size=n_blades)
    _pin_spread_to_axes(az, reaches, rng)
    peak_z = height_cm * (0.98 - 0.32 * frac) * rng.uniform(0.82, 1.04, size=n_blades)
    tip_z = height_cm * (0.90 - 0.48 * frac) * rng.uniform(0.75, 1.04, size=n_blades)
    widths = max(radius_cm * 0.095, 0.9) * rng.uniform(0.8, 1.2, size=n_blades)

    origins = np.column_stack(
        [
            np.cos(az) * neck_r * 0.5,
            np.sin(az) * neck_r * 0.5,
            height_cm * 0.08 * (1.0 - 0.5 * frac),
        ]
    )
    blade_cols = palette_leaf_colors(traits.palette, traits.sprite, peak_z / max(height_cm, 1.0), frac, rng)
    center = np.array([0.0, 0.0, height_cm * 0.48], dtype=np.float64)
    blades = _curved_blades_geo(
        origins,
        az,
        reaches,
        peak_z,
        tip_z,
        widths,
        0.18,
        segs,
        blade_cols,
        rng,
        center=center,
        cup=0.16,
    )

    # Upper scape/blade cluster for silhouette fullness
    u_pts = neck_top[None, :] + rng.normal(0.0, radius_cm * 0.24, size=(n_umbel_leaves, 3))
    u_pts[:, 2] = np.clip(height_cm * rng.uniform(0.45, 0.98, size=n_umbel_leaves), height_cm * 0.2, height_cm)
    u_out = normalize_vec(u_pts - center[None, :])
    u_cols = palette_leaf_colors(
        traits.palette,
        traits.sprite,
        u_pts[:, 2] / max(height_cm, 1.0),
        np.hypot(u_pts[:, 0], u_pts[:, 1]) / max(radius_cm, 1.0),
        rng,
    )
    u_len = max(min(height_cm, radius_cm) * 0.16, 1.8) * rng.uniform(0.8, 1.2, size=n_umbel_leaves)
    clusters = micro_leaves(u_pts, u_out, u_len, u_len * 0.28, u_cols, rng, center=center, spherize=0.68, droop=0.12)

    foliage = concat_geo([blades, clusters])
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


def build_forged_head(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a brassica / artichoke head plant (`"head"` archetype) with outer wrapper leaves and central curd/head."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0x4EAD0001)

    if lod == LOD0:
        n_wrappers = 20
        segs = 5
        n_florets = 260
        sides = 6
    elif lod == LOD1:
        n_wrappers = 14
        segs = 4
        n_florets = 100
        sides = 5
    else:
        n_wrappers = 8
        segs = 3
        n_florets = 28
        sides = 4

    dom_az = float(rng.uniform(0.0, 2.0 * math.pi))
    stalk_shift = radius_cm * float(rng.uniform(0.06, 0.18))
    stalk_top = np.array(
        [math.cos(dom_az) * stalk_shift, math.sin(dom_az) * stalk_shift, height_cm * 0.48],
        dtype=np.float64,
    )
    stalk_r = max(radius_cm * 0.12, 0.8)
    wood = frustum_tubes(
        np.array([[0.0, 0.0, 0.0]], dtype=np.float64),
        stalk_top[None, :],
        np.array([stalk_r]),
        np.array([stalk_r * 1.15]),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    # Outer cradling wrapper leaves
    idx = np.arange(n_wrappers, dtype=np.float64)
    frac = idx / max(n_wrappers - 1, 1)
    az = float(rng.uniform(0.0, 2.0 * math.pi)) + idx * GOLDEN_ANGLE + rng.uniform(-0.18, 0.18, size=n_wrappers)
    asym = 1.0 + 0.28 * np.cos(az - dom_az)
    reaches = radius_cm * (0.48 + 0.52 * frac) * asym * rng.uniform(0.86, 1.12, size=n_wrappers)
    peak_z = height_cm * (0.88 - 0.32 * frac) * (1.0 + 0.15 * np.sin(az - dom_az))
    tip_z = height_cm * (0.72 - 0.45 * frac) * rng.uniform(0.82, 1.12, size=n_wrappers)
    widths = radius_cm * (0.28 + 0.24 * frac)

    origins = np.column_stack(
        [
            np.cos(az) * stalk_r * 0.6,
            np.sin(az) * stalk_r * 0.6,
            height_cm * 0.16 * (1.0 - 0.5 * frac),
        ]
    )
    w_cols = palette_leaf_colors(traits.palette, traits.sprite, 0.35 + 0.45 * (1.0 - frac), frac, rng)
    center = np.array([0.0, 0.0, height_cm * 0.52], dtype=np.float64)
    wrappers = _curved_blades_geo(
        origins,
        az,
        reaches,
        peak_z,
        tip_z,
        widths,
        0.68,
        segs,
        w_cols,
        rng,
        center=center,
        cup=0.16,
    )

    # Central domed floret head
    recipe = recipe_for(traits.sprite)
    head_scale = float(recipe.get("head_scale", 0.45))
    head_r = radius_cm * max(head_scale, 0.36)
    u = normalize_vec(rng.normal(0.0, 1.0, size=(n_florets, 3)))
    u[:, 2] = np.abs(u[:, 2]) * 0.85 + 0.15
    u = normalize_vec(u)
    shell = rng.uniform(0.65, 1.0, size=(n_florets, 1))
    floret_pts = stalk_top[None, :] + np.column_stack(
        [u[:, 0:1] * head_r * shell, u[:, 1:2] * head_r * shell, u[:, 2:3] * height_cm * 0.46 * shell]
    )
    floret_pts[:, 2] = np.clip(floret_pts[:, 2], height_cm * 0.28, height_cm)
    f_cols = palette_leaf_colors(
        traits.palette,
        traits.sprite,
        floret_pts[:, 2] / max(height_cm, 1.0),
        np.ones(n_florets) * 0.75,
        rng,
    )
    f_len = max(head_r * 0.25, 1.8) * rng.uniform(0.8, 1.25, size=n_florets)
    florets = micro_leaves(floret_pts, u, f_len, f_len * 0.82, f_cols, rng, center=stalk_top, spherize=0.80, droop=0.05, cup=0.10)

    foliage = concat_geo([wrappers, florets])
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


def build_forged_ground(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a creeping ground-cover mat (`"ground"` archetype) with runners and hummocks."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0x612004D1)

    if lod == LOD0:
        n_runners = 6
        n_hummocks = 7
        leaves_per_hummock = 135
        sides = 4
    elif lod == LOD1:
        n_runners = 5
        n_hummocks = 5
        leaves_per_hummock = 65
        sides = 4
    else:
        n_runners = 4
        n_hummocks = 4
        leaves_per_hummock = 22
        sides = 3

    dom_az = float(rng.uniform(0.0, 2.0 * math.pi))
    r_az = np.linspace(0.0, 2.0 * math.pi, n_runners, endpoint=False) + float(
        rng.uniform(0.0, 2.0 * math.pi)
    ) + rng.uniform(-0.35, 0.35, size=n_runners)
    r_len = radius_cm * rng.uniform(0.45, 0.82, size=n_runners) * (1.0 + 0.24 * np.cos(r_az - dom_az))
    p0 = np.zeros((n_runners, 3), dtype=np.float64)
    p0[:, 2] = height_cm * 0.08
    p1 = np.column_stack([np.cos(r_az) * r_len, np.sin(r_az) * r_len, height_cm * rng.uniform(0.18, 0.42, size=n_runners)])
    stem_r = max(height_cm * 0.04, 0.3)
    wood = frustum_tubes(
        p0,
        p1,
        np.full(n_runners, stem_r),
        np.full(n_runners, stem_r * 0.5),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    h_az = np.linspace(0.0, 2.0 * math.pi, n_hummocks, endpoint=False) + float(
        rng.uniform(0.0, 2.0 * math.pi)
    ) + rng.uniform(-0.35, 0.35, size=n_hummocks)
    h_dist = radius_cm * rng.uniform(0.18, 0.62, size=n_hummocks)
    h_z = height_cm * rng.uniform(0.28, 0.72, size=n_hummocks)
    peak_i = int(rng.integers(0, n_hummocks))
    h_z[peak_i] = height_cm * float(rng.uniform(0.78, 0.92))
    h_dist[peak_i] = radius_cm * float(rng.uniform(0.12, 0.42))

    h_centers = np.column_stack([h_dist * np.cos(h_az), h_dist * np.sin(h_az), h_z * 0.5])
    h_rx = radius_cm * rng.uniform(0.32, 0.52, size=(n_hummocks, 1))
    h_rz = h_z[:, None] * 0.55

    c_rep = np.repeat(h_centers, leaves_per_hummock, axis=0)
    rx_rep = np.repeat(h_rx, leaves_per_hummock, axis=0)
    rz_rep = np.repeat(h_rz, leaves_per_hummock, axis=0)
    total_leaves = len(c_rep)

    u = normalize_vec(rng.normal(0.0, 1.0, size=(total_leaves, 3)))
    u[:, 2] = np.abs(u[:, 2]) * 0.75 + 0.25
    u = normalize_vec(u)
    shell = rng.uniform(0.45, 1.0, size=(total_leaves, 1)) ** 0.6
    leaf_pts = c_rep + np.column_stack([u[:, 0:1] * rx_rep * shell, u[:, 1:2] * rx_rep * shell, u[:, 2:3] * rz_rep * shell])
    leaf_pts[:, 2] = np.clip(leaf_pts[:, 2], height_cm * 0.04, height_cm)

    center = np.array([0.0, 0.0, height_cm * 0.25], dtype=np.float64)
    outward = normalize_vec(0.65 * u + 0.35 * normalize_vec(leaf_pts - center[None, :]))
    colors = palette_leaf_colors(
        traits.palette,
        traits.sprite,
        leaf_pts[:, 2] / max(height_cm, 1.0),
        np.hypot(leaf_pts[:, 0], leaf_pts[:, 1]) / max(radius_cm, 1.0),
        rng,
    )

    lod_scale = 1.0 if lod == LOD0 else (1.55 if lod == LOD1 else 2.4)
    l_len = max(min(height_cm * 0.45, radius_cm * 0.16) * lod_scale, 1.4) * rng.uniform(0.8, 1.25, size=total_leaves)
    l_wid = l_len * traits.leaf.width_ratio
    foliage = micro_leaves(leaf_pts, outward, l_len, l_wid, colors, rng, center=center, spherize=0.72, droop=0.08, cup=0.05)
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


def build_forged_flower(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a tall/stemmed flower (`"flower"` archetype) with stalk, stem leaves, and crown."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0xF108E123)

    if lod == LOD0:
        n_stems = 5
        stem_segs = 4
        n_stem_leaves = 22
        n_crown_leaves = 190
        sides = 5
    elif lod == LOD1:
        n_stems = 4
        stem_segs = 3
        n_stem_leaves = 14
        n_crown_leaves = 80
        sides = 4
    else:
        n_stems = 3
        stem_segs = 2
        n_stem_leaves = 8
        n_crown_leaves = 24
        sides = 4

    dom_az = float(rng.uniform(0.0, 2.0 * math.pi))
    stem_az = np.linspace(0.0, 2.0 * math.pi, n_stems, endpoint=False) + float(
        rng.uniform(0.0, 2.0 * math.pi)
    ) + rng.uniform(-0.35, 0.35, size=n_stems)
    stem_r_reach = radius_cm * rng.uniform(0.22, 0.65, size=n_stems) * (1.0 + 0.28 * np.cos(stem_az - dom_az))
    stem_top_z = height_cm * rng.uniform(0.58, 0.94, size=n_stems)
    main_idx = int(rng.integers(0, n_stems))
    stem_top_z[main_idx] = height_cm * 0.97
    stem_r_reach[main_idx] = radius_cm * float(rng.uniform(0.12, 0.34))

    p0_list: list[np.ndarray] = []
    p1_list: list[np.ndarray] = []
    r0_list: list[float] = []
    r1_list: list[float] = []
    node_pts: list[np.ndarray] = []
    tip_pts: list[np.ndarray] = []

    base_r = max(min(height_cm, radius_cm * 2.0) * 0.028, 0.45)

    for s_i in range(n_stems):
        az = float(stem_az[s_i])
        rr = float(stem_r_reach[s_i])
        zt = float(stem_top_z[s_i])
        cur = np.array([math.cos(az) * radius_cm * 0.05, math.sin(az) * radius_cm * 0.05, 0.0], dtype=np.float64)
        for k in range(stem_segs):
            t1 = (k + 1) / stem_segs
            nxt = np.array(
                [
                    math.cos(az) * rr * (t1**1.2),
                    math.sin(az) * rr * (t1**1.2),
                    zt * t1,
                ],
                dtype=np.float64,
            )
            p0_list.append(cur)
            p1_list.append(nxt)
            r0_list.append(base_r * (1.0 - 0.55 * (k / stem_segs)))
            r1_list.append(base_r * (1.0 - 0.55 * t1))
            cur = nxt
            node_pts.append(cur.copy())
        tip_pts.append(cur.copy())

    wood = frustum_tubes(
        np.asarray(p0_list),
        np.asarray(p1_list),
        np.asarray(r0_list),
        np.asarray(r1_list),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    # Alternating cordate/ovate stem blades + upper leafy calyx whorls
    idx = np.arange(n_stem_leaves, dtype=np.float64)
    frac = idx / max(n_stem_leaves - 1, 1)
    b_az = float(rng.uniform(0.0, 2.0 * math.pi)) + idx * GOLDEN_ANGLE + rng.uniform(-0.20, 0.20, size=n_stem_leaves)
    b_reach = radius_cm * (0.42 + 0.58 * (1.0 - 0.45 * frac)) * (1.0 + 0.25 * np.cos(b_az - dom_az))
    if lod == LOD2:   # #970: the sunflower held 0.881 of its spread at LOD2
        _pin_spread_to_axes(b_az, b_reach, rng)
    node_arr = np.asarray(node_pts, dtype=np.float64)
    chosen_nodes = node_arr[rng.integers(0, len(node_arr), size=n_stem_leaves)]
    b_origins = chosen_nodes.copy()
    b_origins[:, 2] = height_cm * (0.12 + 0.65 * frac)
    b_peak_z = b_origins[:, 2] + height_cm * 0.14
    b_tip_z = b_origins[:, 2] - height_cm * 0.04
    b_widths = radius_cm * (0.22 + 0.16 * (1.0 - frac)) * traits.leaf.width_ratio * 1.3

    b_cols = palette_leaf_colors(traits.palette, traits.sprite, frac, 1.0 - 0.5 * frac, rng)
    center = np.array([0.0, 0.0, height_cm * 0.50], dtype=np.float64)
    stem_blades = _curved_blades_geo(
        b_origins,
        b_az,
        b_reach,
        b_peak_z,
        b_tip_z,
        b_widths,
        0.35,
        3,
        b_cols,
        rng,
        center=center,
        cup=0.08,
    )

    tip_arr = np.asarray(tip_pts, dtype=np.float64)
    c_anchors = tip_arr[rng.integers(0, len(tip_arr), size=n_crown_leaves)]
    c_pts = c_anchors + rng.normal(0.0, radius_cm * 0.24, size=(n_crown_leaves, 3))
    c_pts[:, 2] = np.clip(c_pts[:, 2], height_cm * 0.15, height_cm)
    c_out = normalize_vec(c_pts - center[None, :])
    c_cols = palette_leaf_colors(
        traits.palette,
        traits.sprite,
        c_pts[:, 2] / max(height_cm, 1.0),
        np.hypot(c_pts[:, 0], c_pts[:, 1]) / max(radius_cm, 1.0),
        rng,
    )
    c_len = max(min(height_cm, radius_cm * 2.0) * 0.14, 2.0) * rng.uniform(0.8, 1.25, size=n_crown_leaves)
    crown_micro = micro_leaves(c_pts, c_out, c_len, c_len * traits.leaf.width_ratio, c_cols, rng, center=center, spherize=0.70, droop=0.16)

    foliage = concat_geo([stem_blades, crown_micro])
    accent_geo = accents if accents is not None else empty_geo()
    parts = fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)
    flower = traits.flower
    if flower is None or flower.habit != "head":
        return parts
    # One head on each stem's tip (#940), placed in the fitted frame so the stems and
    # leaves stand exactly as they would without it. A stem is `stem_segs` frustums in a
    # row (`frustum_tubes`: a base ring then a top ring of `sides` vertices each).
    stem_wood = next(p.mesh for p in parts if p.name == PART_WOOD).positions.astype(np.float64)
    rings = stem_wood.reshape(-1, 2, sides, 3)
    tips = rings[(np.arange(n_stems) + 1) * stem_segs - 1, 1].mean(axis=1)
    out = np.column_stack([np.cos(stem_az), np.sin(stem_az), np.zeros(n_stems)])
    facing = normalize_vec((1.0 - flower.face_up) * out + flower.face_up * np.array([0.0, 0.0, 1.0])
                           + rng.normal(0.0, 0.08, size=(n_stems, 3)))
    radii = flower.radius_cm * rng.uniform(0.85, 1.1, size=n_stems)
    if lod == LOD2:
        # #948: a sunflower's head vanished beyond 45 m. A far head is a tilted patch of
        # the petal colour on each stem tip - a cue, not the real disc.
        far = far_patches_geo(
            tips, facing, np.maximum(2.0 * radii, 0.14 * height_cm),
            far_flower_tint(flower_accent_colour(traits)), rng.random(n_stems),
            double_sided=True,
        )
        return (*parts, flower_part(far, height_cm, radius_cm))
    heads = flowers_geo(flower, str(traits.blossom_spec or "white"), tips, facing, radii, rng, lod=lod)
    return (*parts, flower_part(heads, height_cm, radius_cm))


__all__ = [
    "BULB_LEAF_TOP",
    "GOLDEN_ANGLE",
    "bulb_flower_count",
    "build_forged_allium",
    "build_forged_feathery",
    "build_forged_flower",
    "build_forged_grass",
    "build_forged_ground",
    "build_forged_head",
    "build_forged_rosette",
    "srgb_to_linear",
]

