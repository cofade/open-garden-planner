"""Space-colonisation broadleaf tree builder for Plant Forge (Phase 17 L3.1, #387).

Handles all ``"canopy"`` recipes (15 species + 4 category fallbacks) across
``LOD0`` (≤ 25k tris), ``LOD1`` (≤ 6k tris), and ``LOD2`` (≤ 800 tris).

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

import numpy as np

from ..plant_art.traits3d import BranchingTraits, Traits3D
from ..scene3d.color import srgb_to_linear
from ..scene3d.mesh import MeshPart
from .assemble import fit_forged_parts
from .foliage import RawGeo, empty_geo, micro_leaves, normalize_vec, palette_leaf_colors
from .lod import LOD0, LOD1, lod_skeleton_budget, triangle_budget_for_lod, validate_lod
from .skeleton import Skeleton, grow_skeleton
from .tube import limb_tubes


def bark_linear_rgba(branching: BranchingTraits) -> tuple[float, float, float, float]:
    """Return linear RGBA colour for ``branching`` (`bark_color` × `bark_shade`)."""
    r, g, b = srgb_to_linear(branching.bark_color)[:3]
    shade = float(branching.bark_shade)
    return (float(r) * shade, float(g) * shade, float(b) * shade, 1.0)


def build_tree_foliage_from_skeleton(
    skeleton: Skeleton,
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    rng: np.random.Generator,
    lod: int,
    wood_tris: int,
) -> RawGeo:
    """Spawn micro-leaf clusters around ``skeleton.tip_indices`` within ``lod``'s triangle budget."""
    tips = skeleton.tip_indices
    if len(tips) == 0:
        return empty_geo()

    budget_tris = max(triangle_budget_for_lod(lod) - wood_tris - 32, 60)
    max_leaves = budget_tris // 2  # 2 triangles per micro-leaf

    if lod == LOD0:
        leaves_per_tip = 14
        leaf_scale = 1.0
    elif lod == LOD1:
        leaves_per_tip = 7
        leaf_scale = 1.45
    else:
        leaves_per_tip = 3
        leaf_scale = 2.35

    total_wanted = len(tips) * leaves_per_tip
    if total_wanted > max_leaves:
        leaves_per_tip = max(1, max_leaves // max(len(tips), 1))
        if len(tips) * leaves_per_tip > max_leaves:
            tips = tips[:max_leaves]
            leaves_per_tip = 1

    tip_pos = skeleton.positions[tips]
    k_tips = len(tip_pos)
    total_leaves = k_tips * leaves_per_tip
    if total_leaves == 0:
        return empty_geo()

    # Cluster radius around each twig tip scales with tree size and LOD
    cluster_r = max(min(height_cm, radius_cm * 2.0) * 0.085 * leaf_scale, 2.5)
    if traits.crown.shape == "weeping":
        cluster_r *= 1.15

    # Repeat tip centres and add spherical/ellipsoidal spray offsets
    base_pts = np.repeat(tip_pos, leaves_per_tip, axis=0)
    spray_dir = normalize_vec(rng.normal(0.0, 1.0, size=(total_leaves, 3)))
    if traits.crown.shape == "weeping":
        spray_dir[:, 2] -= 0.45
        spray_dir = normalize_vec(spray_dir)
    spray_dist = cluster_r * (rng.uniform(0.15, 1.0, size=(total_leaves, 1)) ** 0.6)
    leaf_pts = base_pts + spray_dir * spray_dist

    crown_z = height_cm * (0.5 * traits.crown.trunk_share + 0.52)
    crown_center = np.array([0.0, 0.0, crown_z], dtype=np.float64)
    outward = normalize_vec(leaf_pts - crown_center[None, :])

    # Height and radial depth fractions for palette gradient + interior AO
    z_min = float(leaf_pts[:, 2].min())
    z_span = max(float(leaf_pts[:, 2].max()) - z_min, 1.0)
    height_frac = (leaf_pts[:, 2] - z_min) / z_span
    dist_c = np.linalg.norm(leaf_pts - crown_center[None, :], axis=1)
    depth_frac = dist_c / max(float(dist_c.max()), 1.0)

    colors = palette_leaf_colors(
        traits.palette,
        traits.sprite,
        height_frac,
        depth_frac,
        rng,
    )

    # Scale leaf dimensions proportionally so crowns read clearly at any plant scale
    scale_factor = max(height_cm / 320.0, 0.35) * leaf_scale
    base_len = max(traits.leaf.length_cm * scale_factor * 1.45, 2.2)
    lengths = base_len * rng.uniform(0.82, 1.22, size=total_leaves)
    widths = lengths * traits.leaf.width_ratio * (1.15 if traits.leaf.frilly else 1.0)

    droop = traits.crown.droop + (0.38 if traits.crown.shape == "weeping" else 0.0)
    return micro_leaves(
        leaf_pts,
        outward,
        lengths,
        widths,
        colors,
        rng,
        center=crown_center,
        spherize=0.74,
        droop=droop,
        cup=0.08 if traits.leaf.frilly else 0.03,
    )


def build_forged_tree(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Build a forged broadleaf tree (`PART_WOOD`, `PART_FOLIAGE`, optional `PART_ACCENTS`)."""
    validate_lod(lod)
    rng = np.random.default_rng((int(seed) * 2654435761 + 0x9E3779B9) & 0xFFFFFFFFFFFFFFFF)
    max_nodes, attr_count, limb_sides = lod_skeleton_budget(lod, traits.branching.attractors)

    skeleton = grow_skeleton(
        height_cm,
        radius_cm,
        traits.crown,
        traits.branching,
        rng,
        max_nodes=max_nodes,
        attractors=attr_count,
    )
    wood = limb_tubes(
        skeleton,
        sides=limb_sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )
    accent_geo = accents if accents is not None else empty_geo()
    foliage = build_tree_foliage_from_skeleton(
        skeleton,
        traits,
        height_cm,
        radius_cm,
        rng,
        lod,
        wood.triangle_count + accent_geo.triangle_count,
    )
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


__all__ = [
    "bark_linear_rgba",
    "build_forged_tree",
    "build_tree_foliage_from_skeleton",
]
