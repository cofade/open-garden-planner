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
from .assemble import fit_forged_parts
from .foliage import RawGeo, concat_geo, empty_geo, micro_leaves, normalize_vec, palette_leaf_colors
from .lod import LOD0, LOD1, validate_lod
from .trees import bark_linear_rgba
from .tube import frustum_tubes

GOLDEN_ANGLE: float = math.pi * (3.0 - math.sqrt(5.0))


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

    z_max = max(float(verts[:, 2].max()), 1.0)
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
    """Forge an arching fountain grass / cereal clump (`"grass"` archetype)."""
    validate_lod(lod)
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
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


__all__ = [
    "GOLDEN_ANGLE",
    "build_forged_allium",
    "build_forged_feathery",
    "build_forged_flower",
    "build_forged_grass",
    "build_forged_ground",
    "build_forged_head",
    "build_forged_rosette",
    "srgb_to_linear",
]

