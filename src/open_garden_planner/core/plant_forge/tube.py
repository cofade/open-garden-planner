"""Seamless rotation-minimising limb tubes and frustum primitives for Plant Forge (Phase 17 L3.1, #387).

``limb_tubes`` traces continuation chains from the space-colonisation ``Skeleton``
and sweeps a closed ``sides``-gon cross-section along each chain using parallel
transport (rotation-minimising frames), so consecutive branch segments share a
single vertex ring at every joint without seams or twist.

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

import math

import numpy as np

from .foliage import RawGeo, concat_geo, empty_geo, normalize_vec
from .skeleton import Skeleton


def _initial_frame(tangent: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return an orthonormal ``(u, v)`` frame perpendicular to unit vector ``tangent``."""
    ref = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    if abs(float(tangent[0])) > 0.85:
        ref = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    u = np.cross(tangent, ref)
    u /= max(float(np.linalg.norm(u)), 1e-12)
    v = np.cross(tangent, u)
    v /= max(float(np.linalg.norm(v)), 1e-12)
    return u, v


def _transport_frame(
    u: np.ndarray,
    v: np.ndarray,
    t_prev: np.ndarray,
    t_next: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Parallel-transport ``(u, v)`` from ``t_prev`` to ``t_next`` (twist-free)."""
    axis = np.cross(t_prev, t_next)
    sin_a = float(np.linalg.norm(axis))
    cos_a = float(np.clip(np.dot(t_prev, t_next), -1.0, 1.0))
    if sin_a < 1e-7:
        if cos_a < 0.0:
            return -u, -v
        return u, v
    axis /= sin_a
    # Rodrigues' rotation formula
    u_new = u * cos_a + np.cross(axis, u) * sin_a + axis * float(np.dot(axis, u)) * (1.0 - cos_a)
    u_new -= t_next * float(np.dot(u_new, t_next))
    u_new /= max(float(np.linalg.norm(u_new)), 1e-12)
    v_new = np.cross(t_next, u_new)
    v_new /= max(float(np.linalg.norm(v_new)), 1e-12)
    return u_new, v_new


def limb_tubes(
    skeleton: Skeleton,
    *,
    sides: int = 7,
    color_rgba: tuple[float, float, float, float],
) -> RawGeo:
    """Build seamless tubular wood geometry for ``skeleton``.

    Continuation chains share vertex rings across joints; side branches socket
    cleanly into their parent node's position and radius.
    """
    n_nodes = len(skeleton.positions)
    if n_nodes < 2:
        return empty_geo()

    s = max(int(sides), 3)
    angles = np.linspace(0.0, 2.0 * math.pi, s, endpoint=False, dtype=np.float64)
    cos_a = np.cos(angles)[:, None]  # (s, 1)
    sin_a = np.sin(angles)[:, None]  # (s, 1)

    visited_as_child = np.zeros(n_nodes, dtype=bool)
    visited_as_child[0] = True

    chains: list[list[int]] = []
    for start in range(n_nodes):
        if start > 0 and visited_as_child[start]:
            continue
        p = int(skeleton.parents[start])
        chain = [p, start] if p >= 0 else [start]
        if start > 0:
            visited_as_child[start] = True
        cur = start
        while True:
            nxt = int(skeleton.continuation[cur])
            if nxt < 0 or visited_as_child[nxt]:
                break
            visited_as_child[nxt] = True
            chain.append(nxt)
            cur = nxt
        if len(chain) >= 2:
            chains.append(chain)

    if not chains:
        return empty_geo()

    total_rings = sum(len(c) for c in chains)
    total_segs = sum(len(c) - 1 for c in chains)
    pos = np.zeros((total_rings * s, 3), dtype=np.float32)
    nrm = np.zeros((total_rings * s, 3), dtype=np.float32)
    col = np.zeros((total_rings * s, 4), dtype=np.float32)
    uv = np.zeros((total_rings * s, 2), dtype=np.float32)
    tri = np.zeros((total_segs * s * 2, 3), dtype=np.uint32)

    base_col = np.asarray(color_rgba, dtype=np.float32)
    z_max = max(float(skeleton.positions[:, 2].max()), 1.0)

    ring_idx = np.arange(s, dtype=np.uint32)
    next_ring_idx = (ring_idx + 1) % s

    v_cursor = 0
    t_cursor = 0

    ring_node_indices: list[int] = []
    ring_tangents_list: list[np.ndarray] = []
    ring_refs_list: list[np.ndarray] = []

    for chain in chains:
        m = len(chain)
        ring_node_indices.extend(chain)
        chain_pts = skeleton.positions[chain]
        seg_vecs = chain_pts[1:] - chain_pts[:-1]
        seg_tangents = normalize_vec(seg_vecs)
        tangents = np.empty((m, 3), dtype=np.float64)
        tangents[0] = seg_tangents[0]
        tangents[-1] = seg_tangents[-1]
        if m > 2:
            tangents[1:-1] = normalize_vec(seg_tangents[:-1] + seg_tangents[1:])
        ring_tangents_list.append(tangents)

        # Pick reference axis per chain furthest from its tangents to avoid twist/flip
        max_abs_x = float(np.abs(tangents[:, 0]).max())
        max_abs_y = float(np.abs(tangents[:, 1]).max())
        ref = np.array([0.0, 1.0, 0.0] if max_abs_x > max_abs_y else [1.0, 0.0, 0.0], dtype=np.float64)
        ring_refs_list.append(np.broadcast_to(ref[None, :], (m, 3)))

        for k in range(m - 1):
            b0 = np.uint32(v_cursor + k * s)
            b1 = np.uint32(v_cursor + (k + 1) * s)
            t0 = slice(t_cursor, t_cursor + s)
            t1 = slice(t_cursor + s, t_cursor + 2 * s)
            tri[t0, 0] = b0 + ring_idx
            tri[t0, 1] = b0 + next_ring_idx
            tri[t0, 2] = b1 + next_ring_idx
            tri[t1, 0] = b0 + ring_idx
            tri[t1, 1] = b1 + next_ring_idx
            tri[t1, 2] = b1 + ring_idx
            t_cursor += 2 * s

        v_cursor += m * s

    node_idx_arr = np.asarray(ring_node_indices, dtype=np.int32)
    all_tangents = np.concatenate(ring_tangents_list, axis=0)
    all_refs = np.concatenate(ring_refs_list, axis=0)
    u_all = normalize_vec(np.cross(all_tangents, all_refs))
    v_all = normalize_vec(np.cross(all_tangents, u_all))

    # (R, s, 3)
    radial_all = cos_a[None, :, :] * u_all[:, None, :] + sin_a[None, :, :] * v_all[:, None, :]
    centers_all = skeleton.positions[node_idx_arr]
    radii_all = skeleton.radii[node_idx_arr]
    orders_all = skeleton.order[node_idx_arr]

    pos = (centers_all[:, None, :] + radii_all[:, None, None] * radial_all).reshape(-1, 3).astype(np.float32)
    nrm = radial_all.reshape(-1, 3).astype(np.float32)

    z_frac = np.clip(centers_all[:, 2] / z_max, 0.0, 1.0)
    ord_frac = np.minimum(orders_all.astype(np.float64) / 4.0, 1.0)
    shade = ((0.84 + 0.16 * z_frac) * (0.86 + 0.14 * ord_frac)).astype(np.float32)
    ring_cols = np.empty((total_rings, 4), dtype=np.float32)
    ring_cols[:, :3] = np.clip(base_col[None, :3] * shade[:, None], 0.0, 1.0)
    ring_cols[:, 3] = base_col[3]
    col = np.repeat(ring_cols, s, axis=0)

    sway = (z_frac * ord_frac * 0.45).astype(np.float32)
    uv[:, 0] = np.repeat(sway, s)
    uv[:, 1] = 0.0

    return RawGeo(pos=pos, nrm=nrm, col=col, uv=uv, tri=tri)


def frustum_tubes(
    p0: np.ndarray,
    p1: np.ndarray,
    r0: np.ndarray,
    r1: np.ndarray,
    *,
    sides: int,
    color_rgba: tuple[float, float, float, float],
) -> RawGeo:
    """Vectorised frustum tubes for arrays of segment endpoints ``p0, p1`` ``(M, 3)``."""
    p0_a = np.asarray(p0, dtype=np.float64).reshape(-1, 3)
    p1_a = np.asarray(p1, dtype=np.float64).reshape(-1, 3)
    axis = p1_a - p0_a
    lengths = np.linalg.norm(axis, axis=1)
    keep = lengths > 1e-5
    if not np.any(keep):
        return empty_geo()

    p0_a = p0_a[keep]
    p1_a = p1_a[keep]
    r0_a = np.broadcast_to(np.asarray(r0, dtype=np.float64), (len(keep),))[keep]
    r1_a = np.broadcast_to(np.asarray(r1, dtype=np.float64), (len(keep),))[keep]
    w = axis[keep] / lengths[keep, None]
    m = len(p0_a)
    s = max(int(sides), 3)

    ref = np.zeros_like(w)
    use_y = np.abs(w[:, 0]) > 0.85
    ref[~use_y, 0] = 1.0
    ref[use_y, 1] = 1.0
    u = normalize_vec(np.cross(w, ref))
    v = normalize_vec(np.cross(w, u))

    angles = np.linspace(0.0, 2.0 * math.pi, s, endpoint=False, dtype=np.float64)
    ca = np.cos(angles)[None, :, None]
    sa = np.sin(angles)[None, :, None]
    radial = ca * u[:, None, :] + sa * v[:, None, :]  # (m, s, 3)

    ring0 = p0_a[:, None, :] + r0_a[:, None, None] * radial
    ring1 = p1_a[:, None, :] + r1_a[:, None, None] * radial
    pos = np.concatenate([ring0, ring1], axis=1).reshape(-1, 3).astype(np.float32)
    nrm = np.concatenate([radial, radial], axis=1).reshape(-1, 3).astype(np.float32)

    col = np.broadcast_to(
        np.asarray(color_rgba, dtype=np.float32)[None, :], (len(pos), 4)
    ).copy()
    z_max = max(float(np.max(pos[:, 2])), 1.0)
    uv = np.zeros((len(pos), 2), dtype=np.float32)
    uv[:, 0] = np.clip(pos[:, 2] / z_max, 0.0, 1.0) * 0.35

    idx = np.arange(s, dtype=np.uint32)
    nxt = (idx + 1) % s
    t0 = np.stack([idx, nxt, s + nxt], axis=1)
    t1 = np.stack([idx, s + nxt, s + idx], axis=1)
    seg_tris = np.concatenate([t0, t1], axis=0)
    offsets = (np.arange(m, dtype=np.uint32) * (2 * s))[:, None, None]
    tri = (seg_tris[None, :, :] + offsets).reshape(-1, 3)
    return RawGeo(pos=pos, nrm=nrm, col=col, uv=uv, tri=tri)


def cylinder_geo(
    base_xyz: tuple[float, float, float],
    top_xyz: tuple[float, float, float],
    r0: float,
    r1: float,
    *,
    sides: int,
    color_rgba: tuple[float, float, float, float],
    cap_top: bool = False,
) -> RawGeo:
    """Build a single frustum from ``base_xyz`` to ``top_xyz`` with optional flat top cap."""
    body = frustum_tubes(
        np.asarray([base_xyz], dtype=np.float64),
        np.asarray([top_xyz], dtype=np.float64),
        np.asarray([r0], dtype=np.float64),
        np.asarray([r1], dtype=np.float64),
        sides=sides,
        color_rgba=color_rgba,
    )
    if not cap_top or r1 <= 1e-5 or body.vertex_count == 0:
        return body

    s = max(int(sides), 3)
    # Extract the top ring vertices from body (indices s .. 2*s - 1)
    top_ring = body.pos[s : 2 * s].copy()
    center = np.asarray(top_xyz, dtype=np.float32).reshape(1, 3)
    cap_pos = np.concatenate([top_ring, center], axis=0)

    axis = np.asarray(top_xyz, dtype=np.float64) - np.asarray(base_xyz, dtype=np.float64)
    cap_n = normalize_vec(axis[None, :]).astype(np.float32)
    cap_nrm = np.repeat(cap_n, s + 1, axis=0)
    cap_col = np.broadcast_to(
        np.asarray(color_rgba, dtype=np.float32)[None, :], (s + 1, 4)
    ).copy()
    cap_uv = np.zeros((s + 1, 2), dtype=np.float32)

    idx = np.arange(s, dtype=np.uint32)
    nxt = (idx + 1) % s
    center_idx = np.full(s, s, dtype=np.uint32)
    cap_tri = np.stack([idx, nxt, center_idx], axis=1)
    return concat_geo([body, RawGeo(pos=cap_pos, nrm=cap_nrm, col=cap_col, uv=cap_uv, tri=cap_tri)])


__all__ = [
    "cylinder_geo",
    "frustum_tubes",
    "limb_tubes",
]
