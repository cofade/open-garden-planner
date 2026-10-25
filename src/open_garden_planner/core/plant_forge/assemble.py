"""Part assembly, dimensional truth fitting, and silhouette IoU for Plant Forge (Phase 17 L3.1, #387).

Every forged plant is fitted so that:
- its base sits at ``z = 0.0``;
- its maximum height is ``height_cm`` (within the ±3 % gate — exact to float32);
- its horizontal spread matches ``2 * radius_cm`` (within the ±10 % gate);
- no vertex exceeds ``REACH_MAX * radius_cm`` from the item origin (so
  ``verify_builder``'s plan-overreach check passes on every plant size).

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np

from ..scene3d.mesh import MeshPart
from .foliage import RawGeo, normalize_vec

PART_WOOD: Final[str] = "wood"
PART_FOLIAGE: Final[str] = "foliage"
PART_ACCENTS: Final[str] = "accents"

REACH_MAX: Final[float] = 1.04


def _fix_vc_flat_normals(pos: np.ndarray, nrm: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Ensure every flat-shaded triangle in a ``vc`` mesh stores its exact winding normal."""
    out = normalize_vec(nrm.astype(np.float64)).astype(np.float32)
    if len(tri) == 0:
        return out
    t = tri.reshape(-1, 3)
    p = pos.astype(np.float64)
    cross = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
    area2 = np.linalg.norm(cross, axis=1)
    keep = area2 > 1e-6
    if not np.any(keep):
        return out
    n_tri = out.astype(np.float64)[t[keep]]
    flat = np.abs(n_tri - n_tri[:, :1]).max(axis=(1, 2)) < 1e-5
    if np.any(flat):
        flat_indices = np.flatnonzero(keep)[flat]
        winding = (cross[flat_indices] / area2[flat_indices, None]).astype(np.float32)
        for f_idx, wn in zip(flat_indices, winding, strict=True):
            out[t[f_idx, 0]] = wn
            out[t[f_idx, 1]] = wn
            out[t[f_idx, 2]] = wn
    return out


def fit_forged_parts(
    wood: RawGeo,
    foliage: RawGeo,
    accents: RawGeo,
    height_cm: float,
    radius_cm: float,
    *,
    structural_height: bool = False,
) -> tuple[MeshPart, ...]:
    """Fit ``(wood, foliage, accents)`` to ``height_cm`` and ``radius_cm`` and wrap as ``MeshPart``s."""
    raw_list = [
        (PART_WOOD, "vc", wood),
        (PART_FOLIAGE, "foliage", foliage),
        (PART_ACCENTS, "vc", accents),
    ]
    non_empty = [(name, mat, g.copy()) for name, mat, g in raw_list if g.vertex_count > 0 and g.triangle_count > 0]
    if not non_empty:
        return ()

    all_pos = np.concatenate([g.pos for _, _, g in non_empty], axis=0)
    z_min = float(all_pos[:, 2].min())
    z_max = float(all_pos[:, 2].max())
    if structural_height and wood.vertex_count:
        # The structural skeleton owns the common frame. Scaling wood alone
        # moves the twigs away from their leaves and exposes bare summer spikes.
        # Leaves beyond that frame are trimmed at the final ground/top bounds.
        z_min = float(wood.pos[:, 2].min())
        z_max = float(wood.pos[:, 2].max())
    z_span = max(z_max - z_min, 1e-4)
    sz = float(height_cm) / z_span

    # Compute horizontal bounds from upper 85% of plant so crown is centred on (0, 0)
    # while the trunk base stays anchored near (0, 0).
    x_min = float(all_pos[:, 0].min())
    x_max = float(all_pos[:, 0].max())
    y_min = float(all_pos[:, 1].min())
    y_max = float(all_pos[:, 1].max())
    cx = 0.5 * (x_min + x_max)
    cy = 0.5 * (y_min + y_max)
    span_x = x_max - x_min
    span_y = y_max - y_min
    xy_span = max(span_x, span_y, 1e-4)
    target_diameter = 2.0 * float(radius_cm)
    sxy = target_diameter / xy_span
    inv_scale = np.array([1.0 / max(sxy, 1e-5), 1.0 / max(sxy, 1e-5), 1.0 / max(sz, 1e-5)], dtype=np.float32)

    limit_r = float(radius_cm) * REACH_MAX
    parts: list[MeshPart] = []

    for name, mat, geo in non_empty:
        p = geo.pos.copy()
        p[:, 2] = (p[:, 2] - z_min) * sz
        # Smoothly blend horizontal centring above ground so trunk base doesn't jump off-centre
        if name == PART_WOOD:
            collar = np.clip(p[:, 2] / max(float(height_cm) * 0.18, 1e-3), 0.0, 1.0)
            p[:, 0] = (p[:, 0] - cx * collar) * sxy
            p[:, 1] = (p[:, 1] - cy * collar) * sxy
        else:
            p[:, 0] = (p[:, 0] - cx) * sxy
            p[:, 1] = (p[:, 1] - cy) * sxy

        # Clamp any stray leaf/twig tips outside REACH_MAX * radius_cm
        r = np.hypot(p[:, 0], p[:, 1])
        far = r > limit_r
        if np.any(far):
            factor = limit_r / np.maximum(r[far], 1e-6)
            p[far, 0] *= factor
            p[far, 1] *= factor

        p[:, 2] = np.clip(p[:, 2], 0.0, float(height_cm))
        geo.pos = p.astype(np.float32)

        if name == PART_WOOD:
            geo.uv = np.zeros((len(geo.pos), 2), dtype=np.float32)
        else:
            geo.uv = geo.uv.copy()
            geo.uv[:, 0] = np.clip(geo.pos[:, 2] / max(float(height_cm), 1e-6), 0.0, 1.0)
            geo.uv[:, 1] = np.clip(geo.uv[:, 1], 0.0, 0.999999)

        scaled_nrm = normalize_vec(geo.nrm * inv_scale[None, :]).astype(np.float32)
        if mat == "vc":
            geo.nrm = _fix_vc_flat_normals(geo.pos, scaled_nrm, geo.tri)
        else:
            geo.nrm = scaled_nrm

        parts.append(
            MeshPart(
                mesh=geo.to_mesh(),
                material_kind=mat,
                casts_shadow=True,
                tinted=False,
                name=name,
            )
        )

    return tuple(parts)


def _rasterize_projection(
    parts: Sequence[MeshPart],
    axis_h: int,
    radius_cm: float,
    height_cm: float,
    grid_size: int,
) -> np.ndarray:
    """Rasterize triangles of ``parts`` projected onto ``(axis_h, z)`` into a boolean grid."""
    grid = np.zeros((grid_size, grid_size), dtype=bool)
    r_lim = max(float(radius_cm) * 1.05, 1.0)
    h_lim = max(float(height_cm), 1.0)

    # Sample each triangle with a dense barycentric point lattice so both large
    # limb triangles and small micro-leaves register accurately on the silhouette grid.
    u_steps = np.linspace(0.0, 1.0, 7)
    bary: list[tuple[float, float, float]] = []
    for u in u_steps:
        for v in u_steps:
            if u + v <= 1.0 + 1e-6:
                bary.append((u, v, max(0.0, 1.0 - u - v)))
    b_arr = np.asarray(bary, dtype=np.float64)  # (B, 3)

    for part in parts:
        m = part.mesh
        if m.triangle_count == 0:
            continue
        pos = m.positions.astype(np.float64)
        tri = m.indices
        p0 = pos[tri[:, 0]]
        p1 = pos[tri[:, 1]]
        p2 = pos[tri[:, 2]]
        # (T, B, 2)
        hx = (
            b_arr[None, :, 0] * p0[:, None, axis_h]
            + b_arr[None, :, 1] * p1[:, None, axis_h]
            + b_arr[None, :, 2] * p2[:, None, axis_h]
        ).ravel()
        hz = (
            b_arr[None, :, 0] * p0[:, None, 2]
            + b_arr[None, :, 1] * p1[:, None, 2]
            + b_arr[None, :, 2] * p2[:, None, 2]
        ).ravel()

        ix = np.clip(((hx + r_lim) / (2.0 * r_lim) * grid_size).astype(np.int32), 0, grid_size - 1)
        iz = np.clip((hz / h_lim * grid_size).astype(np.int32), 0, grid_size - 1)
        grid[iz, ix] = True

    return grid


def silhouette_iou(
    parts_a: Sequence[MeshPart],
    parts_b: Sequence[MeshPart],
    height_cm: float,
    radius_cm: float,
    *,
    grid_size: int = 64,
) -> float:
    """Compute the mean orthographic silhouette IoU (front XZ + side YZ) between two meshes."""
    ious: list[float] = []
    for axis_h in (0, 1):
        ga = _rasterize_projection(parts_a, axis_h, radius_cm, height_cm, grid_size)
        gb = _rasterize_projection(parts_b, axis_h, radius_cm, height_cm, grid_size)
        inter = int(np.count_nonzero(ga & gb))
        union = int(np.count_nonzero(ga | gb))
        ious.append(inter / max(union, 1))
    return float(sum(ious) / len(ious))


__all__ = [
    "PART_ACCENTS",
    "PART_FOLIAGE",
    "PART_WOOD",
    "REACH_MAX",
    "fit_forged_parts",
    "silhouette_iou",
]
