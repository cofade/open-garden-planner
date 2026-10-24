"""Forged conifers (tiered whorls), palms (ringed trunk + pinnate fronds), shrubs, and leaf-hull hedges (Phase 17 L3.2, #387).

Handles ``"conifer"``, ``"palm"``, ``"mound"``, and ``"hedge"`` recipes across
``LOD0`` (≤ 25k tris), ``LOD1`` (≤ 6k tris), and ``LOD2`` (≤ 800 tris).

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

import math

import numpy as np

from ..plant_art.traits3d import Traits3D
from ..scene3d.mesh import MeshPart
from .assemble import fit_forged_parts
from .foliage import RawGeo, concat_geo, empty_geo, micro_leaves, normalize_vec, palette_leaf_colors
from .lod import LOD0, LOD1, triangle_budget_for_lod, validate_lod
from .trees import bark_linear_rgba
from .tube import frustum_tubes


def _seed_rng(seed: int, salt: int) -> np.random.Generator:
    mixed = ((int(seed) * 2654435761) ^ salt) & 0xFFFFFFFFFFFFFFFF
    return np.random.default_rng(mixed)


def build_forged_conifer(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a conifer with central trunk, tiered branch whorls, and needle sprays."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0xC041FE12)

    if lod == LOD0:
        n_tiers = 9 if traits.crown.shape != "columnar" else 11
        branches_per_tier = 6
        needles_per_branch = 26
        sides = 6
    elif lod == LOD1:
        n_tiers = 6
        branches_per_tier = 5
        needles_per_branch = 12
        sides = 5
    else:
        n_tiers = 4
        branches_per_tier = 4
        needles_per_branch = 4
        sides = 4

    trunk_share = max(traits.crown.trunk_share, 0.10)
    lean_az = float(rng.uniform(0.0, 2.0 * math.pi))
    lean_r = float(rng.uniform(0.05, 0.16)) * radius_cm
    apex_xy = np.array([math.cos(lean_az) * lean_r, math.sin(lean_az) * lean_r], dtype=np.float64)

    # Trunk segments + tiered whorl branches
    p0_list: list[np.ndarray] = []
    p1_list: list[np.ndarray] = []
    r0_list: list[float] = []
    r1_list: list[float] = []

    trunk_r0 = max(height_cm * traits.branching.trunk_base_ratio * 1.35, radius_cm * 0.08, 1.2)
    trunk_segs = 5 if lod == LOD0 else 3
    z_vals = np.linspace(0.0, height_cm * 0.94, trunk_segs + 1)
    for i in range(trunk_segs):
        t0 = i / trunk_segs
        t1 = (i + 1) / trunk_segs
        xy0 = apex_xy * (t0**1.3)
        xy1 = apex_xy * (t1**1.3)
        p0_list.append(np.array([xy0[0], xy0[1], z_vals[i]], dtype=np.float64))
        p1_list.append(np.array([xy1[0], xy1[1], z_vals[i + 1]], dtype=np.float64))
        r0_list.append(trunk_r0 * (1.0 - 0.82 * t0))
        r1_list.append(trunk_r0 * (1.0 - 0.82 * t1))

    # Seed-perturbed tier heights so two conifers have distinct tier silhouettes
    base_t = np.linspace(0.0, 1.0, n_tiers)
    tier_t = np.clip(base_t + rng.uniform(-0.055, 0.055, size=n_tiers), 0.02, 0.98)
    tier_t.sort()
    tier_t[0] = 0.0
    tier_t[-1] = 1.0

    # Seed-specific asymmetric dominant bough azimuth
    dom_az = float(rng.uniform(0.0, 2.0 * math.pi))
    gap_tier = int(rng.integers(1, max(2, n_tiers - 1)))

    leaf_anchors: list[np.ndarray] = []
    leaf_dirs: list[np.ndarray] = []

    for ti, frac in enumerate(tier_t):
        z_tier = height_cm * (trunk_share + (0.95 - trunk_share) * frac)
        if traits.crown.shape == "columnar":
            env = (0.55 + 0.45 * math.sin(frac * math.pi * 0.88)) * (1.0 - 0.35 * frac)
        elif traits.crown.shape in ("spreading", "flat"):
            env = 0.65 + 0.35 * (1.0 - 0.45 * frac)
        else:
            env = (1.0 - 0.78 * (frac**0.92)) * (0.85 + 0.15 * math.sin(frac * math.pi))

        if ti == gap_tier:
            env *= 0.68
        tier_reach = max(radius_cm * env, radius_cm * 0.16)
        trunk_xy = apex_xy * ((z_tier / max(height_cm, 1.0)) ** 1.3)

        az_base = np.linspace(0.0, 2.0 * math.pi, branches_per_tier, endpoint=False)
        az_tier = az_base + float(rng.uniform(0.0, 2.0 * math.pi)) + rng.uniform(
            -0.25, 0.25, size=branches_per_tier
        )
        for b_az in az_tier:
            asym = 1.0 + 0.32 * math.cos(float(b_az) - dom_az)
            b_len = tier_reach * asym * float(rng.uniform(0.74, 1.12))
            droop_dz = -b_len * (traits.crown.droop * 0.55 - 0.18 * frac)
            start = np.array([trunk_xy[0], trunk_xy[1], z_tier], dtype=np.float64)
            end = np.array(
                [
                    trunk_xy[0] + math.cos(float(b_az)) * b_len,
                    trunk_xy[1] + math.sin(float(b_az)) * b_len,
                    max(height_cm * 0.05, z_tier + droop_dz),
                ],
                dtype=np.float64,
            )
            br0 = max(trunk_r0 * 0.28 * (1.0 - 0.6 * frac), 0.35)
            p0_list.append(start)
            p1_list.append(end)
            r0_list.append(br0)
            r1_list.append(br0 * 0.28)

            # Distribute needle spray centres along the outer 75% of each tier branch
            s_steps = np.linspace(0.25, 1.0, needles_per_branch)[:, None]
            pts = start[None, :] * (1.0 - s_steps) + end[None, :] * s_steps
            jitter = rng.normal(0.0, b_len * 0.12, size=(needles_per_branch, 3))
            jitter[:, 2] *= 0.55
            pts = pts + jitter
            leaf_anchors.append(pts)
            b_dir = normalize_vec((end - start)[None, :])[0]
            leaf_dirs.append(np.repeat(b_dir[None, :], needles_per_branch, axis=0))

    # Apex leader spray so the top reaches height_cm cleanly
    leader_pts = np.column_stack(
        [
            apex_xy[0] + rng.normal(0.0, radius_cm * 0.08, size=10),
            apex_xy[1] + rng.normal(0.0, radius_cm * 0.08, size=10),
            np.linspace(height_cm * 0.88, height_cm, 10),
        ]
    )
    leaf_anchors.append(leader_pts)
    leaf_dirs.append(np.tile(np.array([[0.0, 0.0, 1.0]], dtype=np.float64), (10, 1)))

    wood = frustum_tubes(
        np.asarray(p0_list),
        np.asarray(p1_list),
        np.asarray(r0_list),
        np.asarray(r1_list),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    all_leaf_pts = np.concatenate(leaf_anchors, axis=0)
    all_leaf_dirs = np.concatenate(leaf_dirs, axis=0)
    accent_geo = accents if accents is not None else empty_geo()

    budget_leaves = max((triangle_budget_for_lod(lod) - wood.triangle_count - accent_geo.triangle_count - 16) // 2, 32)
    if len(all_leaf_pts) > budget_leaves:
        sel = np.linspace(0, len(all_leaf_pts) - 1, budget_leaves, dtype=np.int32)
        all_leaf_pts = all_leaf_pts[sel]
        all_leaf_dirs = all_leaf_dirs[sel]

    crown_center = np.array([0.0, 0.0, height_cm * 0.48], dtype=np.float64)
    outward = normalize_vec(0.65 * all_leaf_dirs + 0.35 * normalize_vec(all_leaf_pts - crown_center[None, :]))

    z_min = float(all_leaf_pts[:, 2].min())
    height_frac = (all_leaf_pts[:, 2] - z_min) / max(float(all_leaf_pts[:, 2].max()) - z_min, 1.0)
    radial_dist = np.hypot(all_leaf_pts[:, 0], all_leaf_pts[:, 1])
    depth_frac = radial_dist / max(float(radial_dist.max()), 1.0)
    colors = palette_leaf_colors(traits.palette, traits.sprite, height_frac, depth_frac, rng)

    lod_scale = 1.0 if lod == LOD0 else (1.5 if lod == LOD1 else 2.4)
    needle_len = max(min(height_cm, radius_cm * 2.2) * 0.075 * lod_scale, 2.5) * rng.uniform(
        0.8, 1.25, size=len(all_leaf_pts)
    )
    needle_wid = needle_len * max(traits.leaf.width_ratio, 0.32)

    foliage = micro_leaves(
        all_leaf_pts,
        outward,
        needle_len,
        needle_wid,
        colors,
        rng,
        center=crown_center,
        spherize=0.68,
        droop=traits.crown.droop,
        cup=0.05,
    )
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


def build_forged_palm(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a palm with a curved ringed trunk and arching pinnate fronds."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0x9A13F00D)

    if lod == LOD0:
        trunk_rings = 9
        n_fronds = 15
        leaflets_per_side = 12
        sides = 7
    elif lod == LOD1:
        trunk_rings = 6
        n_fronds = 10
        leaflets_per_side = 7
        sides = 5
    else:
        trunk_rings = 4
        n_fronds = 7
        leaflets_per_side = 3
        sides = 4

    # Seed-specific curved trunk up to the crown shaft
    lean_az = float(rng.uniform(0.0, 2.0 * math.pi))
    lean_mag = float(rng.uniform(0.14, 0.34)) * radius_cm
    shaft_z = height_cm * max(traits.crown.trunk_share, 0.64)

    t_steps = np.linspace(0.0, 1.0, trunk_rings + 1)
    curve = (t_steps**1.45) * lean_mag
    tx = math.cos(lean_az) * curve
    ty = math.sin(lean_az) * curve
    tz = t_steps * shaft_z
    trunk_pts = np.column_stack([tx, ty, tz])

    base_r = max(height_cm * traits.branching.trunk_base_ratio * 1.4, radius_cm * 0.08, 1.5)
    ring_r = base_r * (1.0 - 0.38 * t_steps)
    # Subtle palm trunk ring ribs on alternating segments
    r0 = ring_r[:-1] * 1.04
    r1 = ring_r[1:] * 0.96

    wood = frustum_tubes(
        trunk_pts[:-1],
        trunk_pts[1:],
        r0,
        r1,
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    crown_origin = trunk_pts[-1]
    frond_az = np.linspace(0.0, 2.0 * math.pi, n_fronds, endpoint=False) + float(
        rng.uniform(0.0, 2.0 * math.pi)
    ) + rng.uniform(-0.22, 0.22, size=n_fronds)
    # Mix upper ascending fronds and lower arching/drooping fronds
    frond_elev = np.linspace(0.68, -0.18, n_fronds) + rng.uniform(-0.12, 0.12, size=n_fronds)
    rng.shuffle(frond_elev)

    leaflet_pos_list: list[np.ndarray] = []
    leaflet_out_list: list[np.ndarray] = []
    leaflet_len_list: list[np.ndarray] = []
    leaflet_wid_list: list[np.ndarray] = []
    leaflet_hf_list: list[np.ndarray] = []
    leaflet_df_list: list[np.ndarray] = []

    lod_scale = 1.0 if lod == LOD0 else (1.45 if lod == LOD1 else 2.2)

    for f_i in range(n_fronds):
        az = float(frond_az[f_i])
        el = float(frond_elev[f_i])
        reach = radius_cm * float(rng.uniform(0.78, 1.08))
        horiz = np.array([math.cos(az), math.sin(az), 0.0], dtype=np.float64)
        side_vec = np.array([-math.sin(az), math.cos(az), 0.0], dtype=np.float64)

        s = np.linspace(0.12, 0.98, leaflets_per_side)
        # Parabolic arch of the frond rachis
        arch_z = reach * (math.sin(el) * s - 0.58 * (s**1.85))
        rachis_pts = crown_origin[None, :] + horiz[None, :] * (reach * s[:, None])
        rachis_pts[:, 2] += arch_z

        # Two rows of V-folded leaflets along the rachis
        taper = np.sin(s * math.pi * 0.92) ** 0.65
        l_len = max(radius_cm * 0.26 * lod_scale, 3.0) * taper
        l_wid = l_len * (0.24 if lod == LOD0 else 0.36)

        for sign in (-1.0, 1.0):
            lat_xy = normalize_vec((side_vec * sign + horiz * 0.35)[None, :])[0]
            l_pts = rachis_pts + side_vec[None, :] * (sign * radius_cm * 0.02)
            out_dir = normalize_vec(
                np.column_stack(
                    [
                        np.full_like(s, lat_xy[0] * 0.55 + horiz[0] * 0.25),
                        np.full_like(s, lat_xy[1] * 0.55 + horiz[1] * 0.25),
                        0.65 - 0.45 * s,
                    ]
                )
            )
            leaflet_pos_list.append(l_pts)
            leaflet_out_list.append(out_dir)
            leaflet_len_list.append(l_len)
            leaflet_wid_list.append(l_wid)
            leaflet_hf_list.append(np.clip(0.35 + 0.65 * (1.0 - s * 0.4), 0.0, 1.0))
            leaflet_df_list.append(s)

    all_pos = np.concatenate(leaflet_pos_list, axis=0)
    all_out = np.concatenate(leaflet_out_list, axis=0)
    all_len = np.concatenate(leaflet_len_list, axis=0)
    all_wid = np.concatenate(leaflet_wid_list, axis=0)
    all_hf = np.concatenate(leaflet_hf_list, axis=0)
    all_df = np.concatenate(leaflet_df_list, axis=0)

    colors = palette_leaf_colors(traits.palette, traits.sprite, all_hf, all_df, rng)
    foliage = micro_leaves(
        all_pos,
        all_out,
        all_len,
        all_wid,
        colors,
        rng,
        center=crown_origin,
        spherize=0.58,
        droop=0.32,
        cup=0.06,
    )
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


def build_forged_shrub(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a multi-stem shrub or bushy mound (`"mound"` archetype)."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0x5B128B01)

    if lod == LOD0:
        n_stems = 7
        segs_per_stem = 4
        leaves_per_lobe = 140
        sides = 5
    elif lod == LOD1:
        n_stems = 6
        segs_per_stem = 3
        leaves_per_lobe = 58
        sides = 4
    else:
        n_stems = 4
        segs_per_stem = 2
        leaves_per_lobe = 18
        sides = 4

    # Seed-specific multi-stem basal branching and asymmetric lobe centres
    stem_az = np.linspace(0.0, 2.0 * math.pi, n_stems, endpoint=False) + float(
        rng.uniform(0.0, 2.0 * math.pi)
    ) + rng.uniform(-0.35, 0.35, size=n_stems)
    stem_reach = radius_cm * rng.uniform(0.32, 0.68, size=n_stems)
    stem_top_z = height_cm * rng.uniform(0.42, 0.78, size=n_stems)
    # Ensure one dominant high lobe and one low side lobe per seed for distinct silhouettes
    tall_idx = int(rng.integers(0, n_stems))
    stem_top_z[tall_idx] = height_cm * float(rng.uniform(0.76, 0.88))
    stem_reach[tall_idx] = radius_cm * float(rng.uniform(0.18, 0.42))
    wide_idx = (tall_idx + int(rng.integers(1, n_stems))) % n_stems
    stem_reach[wide_idx] = radius_cm * float(rng.uniform(0.62, 0.78))
    stem_top_z[wide_idx] = height_cm * float(rng.uniform(0.34, 0.52))

    p0_list: list[np.ndarray] = []
    p1_list: list[np.ndarray] = []
    r0_list: list[float] = []
    r1_list: list[float] = []
    lobe_centers: list[np.ndarray] = []

    base_stem_r = max(height_cm * traits.branching.trunk_base_ratio * 0.9, 0.45)

    for s_i in range(n_stems):
        az = float(stem_az[s_i])
        r_target = float(stem_reach[s_i])
        z_target = float(stem_top_z[s_i])
        cur = np.array(
            [math.cos(az) * radius_cm * 0.06, math.sin(az) * radius_cm * 0.06, 0.0],
            dtype=np.float64,
        )
        for step_i in range(segs_per_stem):
            t1 = (step_i + 1) / segs_per_stem
            wobble = rng.normal(0.0, radius_cm * 0.04, size=2)
            nxt = np.array(
                [
                    math.cos(az) * r_target * (t1**1.15) + wobble[0],
                    math.sin(az) * r_target * (t1**1.15) + wobble[1],
                    z_target * (t1**0.9),
                ],
                dtype=np.float64,
            )
            p0_list.append(cur)
            p1_list.append(nxt)
            r0_list.append(base_stem_r * (1.0 - 0.65 * (step_i / segs_per_stem)))
            r1_list.append(base_stem_r * (1.0 - 0.65 * t1))
            cur = nxt
            if step_i >= segs_per_stem - 2:
                lobe_centers.append(cur.copy())

    wood = frustum_tubes(
        np.asarray(p0_list),
        np.asarray(p1_list),
        np.asarray(r0_list),
        np.asarray(r1_list),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    lobe_arr = np.asarray(lobe_centers, dtype=np.float64)
    n_lobes = len(lobe_arr)
    lobe_rx = radius_cm * rng.uniform(0.28, 0.48, size=(n_lobes, 1))
    lobe_rz = height_cm * rng.uniform(0.22, 0.38, size=(n_lobes, 1))

    base_centers = np.repeat(lobe_arr, leaves_per_lobe, axis=0)
    rx_rep = np.repeat(lobe_rx, leaves_per_lobe, axis=0)
    rz_rep = np.repeat(lobe_rz, leaves_per_lobe, axis=0)
    total_leaves = len(base_centers)

    dirs = normalize_vec(rng.normal(0.0, 1.0, size=(total_leaves, 3)))
    shell_r = rng.uniform(0.30, 1.0, size=(total_leaves, 1)) ** 0.55
    offsets = np.column_stack(
        [
            dirs[:, 0:1] * rx_rep * shell_r,
            dirs[:, 1:2] * rx_rep * shell_r,
            dirs[:, 2:3] * rz_rep * shell_r,
        ]
    )
    leaf_pts = base_centers + offsets
    leaf_pts[:, 2] = np.clip(leaf_pts[:, 2], height_cm * 0.04, height_cm)

    crown_center = np.array([0.0, 0.0, height_cm * 0.45], dtype=np.float64)
    outward = normalize_vec(0.6 * dirs + 0.4 * normalize_vec(leaf_pts - crown_center[None, :]))

    z_min = float(np.min(leaf_pts[:, 2]))
    height_frac = (leaf_pts[:, 2] - z_min) / max(float(np.max(leaf_pts[:, 2])) - z_min, 1.0)
    dist_c = np.linalg.norm(leaf_pts - crown_center[None, :], axis=1)
    depth_frac = dist_c / max(float(np.max(dist_c)), 1.0)
    colors = palette_leaf_colors(traits.palette, traits.sprite, height_frac, depth_frac, rng)

    lod_scale = 1.0 if lod == LOD0 else (1.55 if lod == LOD1 else 2.5)
    base_len = max(min(height_cm, radius_cm * 2.0) * 0.095 * traits.leaf.leaf_scale * lod_scale, 1.8)
    lengths = base_len * rng.uniform(0.78, 1.24, size=total_leaves)
    widths = lengths * traits.leaf.width_ratio

    foliage = micro_leaves(
        leaf_pts,
        outward,
        lengths,
        widths,
        colors,
        rng,
        center=crown_center,
        spherize=0.72,
        droop=traits.crown.droop,
        cup=0.07 if traits.leaf.frilly else 0.03,
    )
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


def build_forged_hedge(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a living hedge unit (`"hedge"` archetype) with woody core and micro-leaf hull."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0x4ED6E123)

    if lod == LOD0:
        n_stems = 5
        n_billows = 8
        leaves_per_billow = 140
        sides = 5
    elif lod == LOD1:
        n_stems = 4
        n_billows = 6
        leaves_per_billow = 65
        sides = 4
    else:
        n_stems = 3
        n_billows = 5
        leaves_per_billow = 22
        sides = 4

    # Interior woody stems rising from ground
    stem_x = np.linspace(-radius_cm * 0.45, radius_cm * 0.45, n_stems) + rng.uniform(
        -radius_cm * 0.08, radius_cm * 0.08, size=n_stems
    )
    stem_y = rng.uniform(-radius_cm * 0.25, radius_cm * 0.25, size=n_stems)
    p0 = np.column_stack([stem_x, stem_y, np.zeros(n_stems)])
    p1 = np.column_stack(
        [
            stem_x + rng.uniform(-radius_cm * 0.12, radius_cm * 0.12, size=n_stems),
            stem_y + rng.uniform(-radius_cm * 0.12, radius_cm * 0.12, size=n_stems),
            height_cm * rng.uniform(0.55, 0.78, size=n_stems),
        ]
    )
    stem_r = max(height_cm * 0.022, 0.6)
    wood = frustum_tubes(
        p0,
        p1,
        np.full(n_stems, stem_r),
        np.full(n_stems, stem_r * 0.45),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    # Seed-specific overlapping foliage billows forming a living clipped hedge hull
    b_az = np.linspace(0.0, 2.0 * math.pi, n_billows, endpoint=False) + float(
        rng.uniform(0.0, 2.0 * math.pi)
    ) + rng.uniform(-0.32, 0.32, size=n_billows)
    b_rad = radius_cm * rng.uniform(0.28, 0.64, size=n_billows)
    b_z = height_cm * rng.uniform(0.32, 0.76, size=n_billows)
    # Give one billow a high crest and another a lower shoulder for natural non-clone outline
    crest_i = int(rng.integers(0, n_billows))
    b_z[crest_i] = height_cm * float(rng.uniform(0.75, 0.88))
    b_rad[crest_i] = radius_cm * float(rng.uniform(0.20, 0.45))

    b_centers = np.column_stack([b_rad * np.cos(b_az), b_rad * np.sin(b_az), b_z])
    b_rx = radius_cm * rng.uniform(0.32, 0.52, size=(n_billows, 1))
    b_rz = height_cm * rng.uniform(0.26, 0.44, size=(n_billows, 1))

    centers_rep = np.repeat(b_centers, leaves_per_billow, axis=0)
    rx_rep = np.repeat(b_rx, leaves_per_billow, axis=0)
    rz_rep = np.repeat(b_rz, leaves_per_billow, axis=0)
    total_leaves = len(centers_rep)

    dirs = normalize_vec(rng.normal(0.0, 1.0, size=(total_leaves, 3)))
    # Concentrate leaves on the outer skin of each billow (leaf hull)
    shell = rng.uniform(0.68, 1.04, size=(total_leaves, 1))
    leaf_pts = centers_rep + np.column_stack(
        [dirs[:, 0:1] * rx_rep * shell, dirs[:, 1:2] * rx_rep * shell, dirs[:, 2:3] * rz_rep * shell]
    )
    leaf_pts[:, 2] = np.clip(leaf_pts[:, 2], height_cm * 0.03, height_cm)

    hull_center = np.array([0.0, 0.0, height_cm * 0.48], dtype=np.float64)
    outward = normalize_vec(0.55 * dirs + 0.45 * normalize_vec(leaf_pts - hull_center[None, :]))

    z_min = float(np.min(leaf_pts[:, 2]))
    height_frac = (leaf_pts[:, 2] - z_min) / max(float(np.max(leaf_pts[:, 2])) - z_min, 1.0)
    dist_c = np.linalg.norm(leaf_pts - hull_center[None, :], axis=1)
    depth_frac = dist_c / max(float(np.max(dist_c)), 1.0)
    colors = palette_leaf_colors(traits.palette, traits.sprite, height_frac, depth_frac, rng)

    lod_scale = 1.0 if lod == LOD0 else (1.55 if lod == LOD1 else 2.5)
    base_len = max(min(height_cm, radius_cm * 2.0) * 0.08 * traits.leaf.leaf_scale * lod_scale, 1.6)
    lengths = base_len * rng.uniform(0.82, 1.20, size=total_leaves)
    widths = lengths * traits.leaf.width_ratio

    foliage = micro_leaves(
        leaf_pts,
        outward,
        lengths,
        widths,
        colors,
        rng,
        center=hull_center,
        spherize=0.75,
        droop=0.10,
        cup=0.04,
    )
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


__all__ = [
    "build_forged_conifer",
    "build_forged_hedge",
    "build_forged_palm",
    "build_forged_shrub",
    "concat_geo",
]
