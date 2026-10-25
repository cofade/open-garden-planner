"""Space-colonisation branching skeleton and pipe-model radii for Plant Forge (Phase 17 L3.1, #387).

Algorithm (Runions et al. 2007, adapted for fast NumPy execution):
1. Sample ``attractors`` points inside a seed-perturbed multi-lobe crown volume
   above ``trunk_share * height_cm``.
2. Grow the main trunk from ``(base_x, base_y, 0)`` up to the crown base with
   seed-driven lean and primary scaffold forks so every seed produces a genuinely
   distinct silhouette (IoU < 0.95).
3. Iteratively associate each active attractor with its nearest skeleton node
   within ``influence_radius`` (maintained incrementally via ``d2_min`` so each
   growth step touches only newly grown nodes), average normalized pull vectors
   plus phototropism/gravitropism (`up_bias`) and seed jitter, and spawn new nodes
   at ``step_cm`` distance.
4. Prune attractors within ``kill_radius`` of any skeleton node.
5. Compute branch radii bottom-up with the pipe model (`r_parent^p = sum(r_child^p)`).

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..plant_art.traits3d import BranchingTraits, CrownTraits
from .foliage import normalize_vec


@dataclass(frozen=True)
class Skeleton:
    """Directed tree graph of 3D skeleton nodes in the item-local scene frame (cm)."""

    positions: np.ndarray     # (N, 3) float64
    parents: np.ndarray       # (N,) int32, -1 for root(s)
    radii: np.ndarray         # (N,) float64
    order: np.ndarray         # (N,) int32, 0 = trunk
    tip_indices: np.ndarray   # (K,) int32, terminal or high-order nodes
    continuation: np.ndarray  # (N,) int32, primary child index or -1


def _sample_crown_attractors(
    count: int,
    height_cm: float,
    radius_cm: float,
    crown: CrownTraits,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample ``count`` attractors inside a seed-specific multi-lobe crown."""
    z0 = height_cm * crown.trunk_share
    crown_h = max(height_cm - z0, height_cm * 0.25)
    rz = max(crown_h * 0.5, 2.0)
    cz = z0 + rz
    rx = max(radius_cm * 0.92, 2.0)
    ry = max(radius_cm * 0.92 * crown.aspect_xy, 2.0)

    # Seed-specific sub-lobes (5..7 lobes) give each tree seed a distinct crown outline
    n_lobes = int(rng.integers(5, 8))
    lobe_az = np.linspace(0.0, 2.0 * math.pi, n_lobes, endpoint=False) + rng.uniform(
        -0.38, 0.38, size=n_lobes
    )
    lobe_polar = rng.uniform(0.32, 0.72, size=n_lobes)
    lobe_z = rng.uniform(-0.42, 0.52, size=n_lobes)
    # Force one strong high lobe and one wide side lobe per seed for organic asymmetry
    top_idx = int(rng.integers(0, n_lobes))
    lobe_z[top_idx] = rng.uniform(0.35, 0.62)
    lobe_polar[top_idx] = rng.uniform(0.15, 0.45)
    side_idx = (top_idx + int(rng.integers(1, n_lobes))) % n_lobes
    lobe_polar[side_idx] = rng.uniform(0.55, 0.78)
    lobe_z[side_idx] = rng.uniform(-0.25, 0.25)

    lobe_centers = np.column_stack(
        [
            rx * lobe_polar * np.cos(lobe_az),
            ry * lobe_polar * np.sin(lobe_az),
            cz + rz * lobe_z,
        ]
    )
    lobe_radii = np.column_stack(
        [
            rx * rng.uniform(0.36, 0.58, size=n_lobes),
            ry * rng.uniform(0.36, 0.58, size=n_lobes),
            rz * rng.uniform(0.38, 0.62, size=n_lobes),
        ]
    )
    lobe_weights = rng.uniform(0.6, 1.5, size=n_lobes)
    lobe_weights /= lobe_weights.sum()

    chosen = rng.choice(n_lobes, size=count, p=lobe_weights)
    u = rng.normal(0.0, 1.0, size=(count, 3))
    u = normalize_vec(u)
    # Bias toward outer shell of each lobe where sunlight reaches leaves
    r = rng.uniform(0.22, 1.0, size=(count, 1)) ** (1.0 / 2.4)
    local = u * r * lobe_radii[chosen]
    pts = lobe_centers[chosen] + local

    # Shape envelope modulation
    rel_z = np.clip((pts[:, 2] - z0) / max(crown_h, 1.0), 0.0, 1.0)
    if crown.shape == "columnar":
        envelope = 0.55 + 0.45 * np.sin(rel_z * math.pi)
        pts[:, 0] *= envelope * 0.72
        pts[:, 1] *= envelope * 0.72
    elif crown.shape == "vase":
        envelope = 0.45 + 0.68 * (rel_z**0.75)
        pts[:, 0] *= envelope
        pts[:, 1] *= envelope
    elif crown.shape == "weeping":
        envelope = 0.62 + 0.52 * (1.0 - 0.45 * rel_z)
        pts[:, 0] *= envelope
        pts[:, 1] *= envelope
        pts[:, 2] -= 0.12 * crown_h * (np.hypot(pts[:, 0], pts[:, 1]) / max(rx, 1.0))
    elif crown.shape == "umbrella":
        pts[:, 2] = z0 + crown_h * (0.52 + 0.48 * rel_z * 0.65)
        envelope = 0.58 + 0.55 * (rel_z**0.5)
        pts[:, 0] *= envelope
        pts[:, 1] *= envelope

    pts[:, 2] = np.clip(pts[:, 2], max(z0 * 0.65, height_cm * 0.14), height_cm)
    return pts


def grow_skeleton(
    height_cm: float,
    radius_cm: float,
    crown: CrownTraits,
    branching: BranchingTraits,
    rng: np.random.Generator,
    *,
    max_nodes: int = 650,
    attractors: int | None = None,
    trunk_base_xy: tuple[float, float] = (0.0, 0.0),
) -> Skeleton:
    """Grow a space-colonisation skeleton for a tree or woody shrub."""
    num_attr = attractors if attractors is not None else branching.attractors
    attr = _sample_crown_attractors(num_attr, height_cm, radius_cm, crown, rng)
    active = np.ones(len(attr), dtype=bool)

    step = max(height_cm * 0.048, 1.5)
    kill_r2 = max(step * 1.45, step * 1.15) ** 2
    influence_r2 = max(height_cm * 0.34, step * 3.5) ** 2

    cap = max(max_nodes, 32)
    pos = np.zeros((cap, 3), dtype=np.float64)
    parent = np.full(cap, -1, dtype=np.int32)
    order = np.zeros(cap, dtype=np.int32)
    dirs = np.zeros((cap, 3), dtype=np.float64)

    # 1. Grow trunk from base to crown base with subtle seed-dependent lean
    trunk_top_z = height_cm * max(crown.trunk_share, 0.18)
    trunk_steps = max(3, min(14, int(round(trunk_top_z / step))))
    lean_angle = float(rng.uniform(0.0, 2.0 * math.pi))
    lean_mag = float(rng.uniform(0.03, 0.14)) * min(radius_cm, height_cm * 0.22)
    lean_dx = math.cos(lean_angle) * lean_mag / trunk_steps
    lean_dy = math.sin(lean_angle) * lean_mag / trunk_steps
    dz = trunk_top_z / trunk_steps

    pos[0] = [trunk_base_xy[0], trunk_base_xy[1], 0.0]
    dirs[0] = [0.0, 0.0, 1.0]
    n = 1
    for _i in range(1, trunk_steps + 1):
        if n >= cap:
            break
        wobble = rng.normal(0.0, step * 0.05, size=2)
        nxt = pos[n - 1] + np.array([lean_dx + wobble[0], lean_dy + wobble[1], dz])
        nxt[2] = max(nxt[2], pos[n - 1, 2] + dz * 0.5)
        pos[n] = nxt
        parent[n] = n - 1
        order[n] = 0
        dirs[n] = normalize_vec((pos[n] - pos[n - 1])[None, :])[0]
        n += 1

    # 2. Seed primary scaffold limbs at the crown collar so branches reach all lobes
    collar_idx = n - 1
    n_scaffold = int(rng.integers(3, 6))
    scaf_az = np.linspace(0.0, 2.0 * math.pi, n_scaffold, endpoint=False) + rng.uniform(
        -0.42, 0.42, size=n_scaffold
    )
    for k in range(n_scaffold):
        if n >= cap:
            break
        elev = float(rng.uniform(0.32, 0.72))
        d = normalize_vec(
            np.array(
                [[math.cos(scaf_az[k]) * math.cos(elev), math.sin(scaf_az[k]) * math.cos(elev), math.sin(elev)]]
            )
        )[0]
        spawn_parent = max(1, collar_idx - int(rng.integers(0, min(2, collar_idx))))
        pos[n] = pos[spawn_parent] + d * step
        parent[n] = spawn_parent
        order[n] = 1
        dirs[n] = d
        n += 1

    # Incremental nearest-node tables for active attractors
    diff0 = attr[:, None, :] - pos[None, :n, :]
    d2_0 = (diff0 * diff0).sum(axis=2)
    nearest_node = d2_0.argmin(axis=1).astype(np.int32)
    d2_min = d2_0[np.arange(len(attr)), nearest_node]
    active &= d2_min > kill_r2

    up_vec = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    max_iters = 56
    for _ in range(max_iters):
        if n >= cap or not np.any(active):
            break
        act_idx = np.flatnonzero(active)
        in_range = d2_min[act_idx] <= influence_r2
        if not np.any(in_range):
            break

        valid_attr = act_idx[in_range]
        winners = nearest_node[valid_attr]
        vecs = attr[valid_attr] - pos[winners]
        dists = np.sqrt(np.maximum(d2_min[valid_attr], 1e-12))[:, None]
        unit_vecs = vecs / dists

        unique_parents, inv = np.unique(winners, return_inverse=True)
        sums = np.zeros((len(unique_parents), 3), dtype=np.float64)
        np.add.at(sums, inv, unit_vecs)

        child_counts = np.bincount(parent[1:n], minlength=n)
        old_n = n
        for p_idx, pull in zip(unique_parents, sums, strict=True):
            if n >= cap:
                break
            p_i = int(p_idx)
            pull_dir = normalize_vec(pull[None, :])[0]
            # Blend parent inertia, attractor pull, tropism, and seed jitter
            jitter = rng.normal(0.0, branching.gnarl, size=3)
            raw_dir = (
                0.32 * dirs[p_i]
                + 0.68 * pull_dir
                + branching.apical_bias * up_vec
                + jitter
            )
            if crown.shape == "weeping" and order[p_i] >= 2:
                raw_dir[2] -= 0.35
            new_dir = normalize_vec(raw_dir[None, :])[0]
            new_pos = pos[p_i] + new_dir * step
            new_pos[2] = max(new_pos[2], height_cm * 0.05)

            pos[n] = new_pos
            parent[n] = p_i
            is_fork = child_counts[p_i] > 0
            order[n] = min(order[p_i] + (1 if is_fork else 0), 5)
            dirs[n] = new_dir
            child_counts[p_i] += 1
            n += 1

        if n == old_n:
            break

        # Incremental distance update against only the newly added nodes [old_n:n]
        act_idx = np.flatnonzero(active)
        new_diff = attr[act_idx, None, :] - pos[None, old_n:n, :]
        new_d2 = (new_diff * new_diff).sum(axis=2)
        best_local = new_d2.argmin(axis=1)
        best_d2 = new_d2[np.arange(len(act_idx)), best_local]
        improved = best_d2 < d2_min[act_idx]
        if np.any(improved):
            imp_attr = act_idx[improved]
            d2_min[imp_attr] = best_d2[improved]
            nearest_node[imp_attr] = old_n + best_local[improved]
            active[imp_attr] = d2_min[imp_attr] > kill_r2

    pos = pos[:n]
    parent = parent[:n]
    order = order[:n]
    dirs = dirs[:n]

    # 3. Pipe-model radius propagation + continuation child selection
    tip_r = max(height_cm * branching.trunk_base_ratio * 0.16, 0.35)
    power = max(branching.pipe_exponent, 1.8)
    accum = np.full(n, tip_r**power, dtype=np.float64)
    has_child = np.zeros(n, dtype=bool)
    continuation = np.full(n, -1, dtype=np.int32)
    best_child_weight = np.full(n, -1.0, dtype=np.float64)

    for i in range(n - 1, 0, -1):
        p_i = int(parent[i])
        if p_i >= 0:
            has_child[p_i] = True
            accum[p_i] += accum[i]
            # Prefer straightest, thickest child as continuation of the limb
            align = max(0.1, float(np.dot(dirs[p_i], dirs[i])))
            weight = accum[i] * (0.65 + 0.35 * align)
            if weight > best_child_weight[p_i]:
                best_child_weight[p_i] = weight
                continuation[p_i] = i

    radii = accum ** (1.0 / power)
    max_trunk_r = max(height_cm * 0.055, radius_cm * 0.18, tip_r * 2.5)
    if radii[0] > max_trunk_r:
        scale = (max_trunk_r - tip_r) / max(radii[0] - tip_r, 1e-6)
        radii = tip_r + (radii - tip_r) * scale
    # Subtle root flare at base node
    radii[0] *= 1.18

    tips = np.flatnonzero(~has_child | (order >= 2)).astype(np.int32)
    if len(tips) == 0:
        tips = np.arange(max(0, n - 4), n, dtype=np.int32)

    return Skeleton(
        positions=pos,
        parents=parent,
        radii=radii,
        order=order,
        tip_indices=tips,
        continuation=continuation,
    )


__all__ = [
    "Skeleton",
    "grow_skeleton",
]
