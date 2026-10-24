"""Forged climbers and support resolution for Plant Forge (Phase 17 L3.4, #387).

Support precedence for a climbing plant (`"climber"` archetype):
1. ``"trellis"``: if the plant's ``parent_id`` references a ``TRELLIS`` item in the scene.
2. ``"fence"`` / ``"pergola"``: else if the nearest ``FENCE`` or ``PERGOLA`` in the scene
   lies within ``CLIMBER_SUPPORT_MAX_DISTANCE_CM`` (50 cm) of the plant's canopy edge.
3. ``"bean_poles"``: else the climber builds a procedural tripod/wigwam of bean poles.

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Mapping
from typing import Any, Final

import numpy as np

from ..plant_art import PLANT_KINDS, traits_for
from ..plant_art.traits3d import Traits3D
from ..scene3d import PARAM_RADIUS_CM, MeshPart, Params, Record
from ..scene3d.builders.plants import plant_sprite
from .assemble import fit_forged_parts
from .foliage import RawGeo, empty_geo, micro_leaves, normalize_vec, palette_leaf_colors
from .lod import LOD0, LOD1, LOD2, validate_lod
from .trees import bark_linear_rgba
from .tube import frustum_tubes

PARAM_CLIMBER_SUPPORT: Final[str] = "climber_support"
CLIMBER_SUPPORT_MAX_DISTANCE_CM: Final[float] = 50.0

SUPPORT_TRELLIS: Final[str] = "trellis"
SUPPORT_FENCE: Final[str] = "fence"
SUPPORT_PERGOLA: Final[str] = "pergola"
SUPPORT_BEAN_POLES: Final[str] = "bean_poles"

SUPPORT_KINDS: Final[frozenset[str]] = frozenset({
    SUPPORT_TRELLIS,
    SUPPORT_FENCE,
    SUPPORT_PERGOLA,
    SUPPORT_BEAN_POLES,
})


def _seed_rng(seed: int, salt: int) -> np.random.Generator:
    mixed = ((int(seed) * 2654435761) ^ salt) & 0xFFFFFFFFFFFFFFFF
    return np.random.default_rng(mixed)


def _world_points_of_record(rec: Record) -> tuple[np.ndarray, float]:
    """Return world XY vertices ``(M, 2)`` and rotation angle (deg) for ``rec``."""
    tx = float(rec.transform.east_cm)
    ty = float(rec.transform.north_cm)
    rot_rad = math.radians(float(rec.transform.rotation_deg))
    ca = math.cos(rot_rad)
    sa = math.sin(rot_rad)

    local_pts: list[tuple[float, float]] = []
    if rec.path:
        local_pts.extend((float(x), float(y)) for x, y in rec.path)
    for ring in rec.footprints:
        pts_ring = [(float(x), float(y)) for x, y in ring]
        if len(pts_ring) >= 2 and pts_ring[0] != pts_ring[-1]:
            pts_ring.append(pts_ring[0])
        local_pts.extend(pts_ring)
    if not local_pts:
        local_pts.append((0.0, 0.0))

    arr = np.asarray(local_pts, dtype=np.float64)
    wx = tx + arr[:, 0] * ca - arr[:, 1] * sa
    wy = ty + arr[:, 0] * sa + arr[:, 1] * ca
    return np.column_stack([wx, wy]), float(rec.transform.rotation_deg)


def _min_distance_and_tangent_deg(
    px: float,
    py: float,
    world_pts: np.ndarray,
    default_deg: float,
) -> tuple[float, float]:
    """Return minimum distance from ``(px, py)`` to polyline/ring segments in ``world_pts`` and segment azimuth."""
    if len(world_pts) == 0:
        return float("inf"), default_deg
    if len(world_pts) == 1:
        d = math.hypot(px - float(world_pts[0, 0]), py - float(world_pts[0, 1]))
        return d, default_deg

    best_d = float("inf")
    best_deg = default_deg
    for i in range(len(world_pts) - 1):
        ax, ay = float(world_pts[i, 0]), float(world_pts[i, 1])
        bx, by = float(world_pts[i + 1, 0]), float(world_pts[i + 1, 1])
        dx = bx - ax
        dy = by - ay
        l2 = dx * dx + dy * dy
        if l2 <= 1e-9:
            d = math.hypot(px - ax, py - ay)
            deg = default_deg
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
            cx = ax + t * dx
            cy = ay + t * dy
            d = math.hypot(px - cx, py - cy)
            deg = math.degrees(math.atan2(dy, dx)) % 360.0
        if d < best_d:
            best_d = d
            best_deg = deg
    return best_d, best_deg


def resolve_climber_support(
    plant_record: Record,
    scene_records: Mapping[str, Record] | Iterable[Record],
    *,
    max_distance_cm: float = CLIMBER_SUPPORT_MAX_DISTANCE_CM,
) -> dict[str, Any]:
    """Determine the support dict (`kind`, `azimuth_deg`, `distance_cm`) for ``plant_record``."""
    by_id: dict[str, Record] = (
        dict(scene_records)
        if isinstance(scene_records, Mapping)
        else {r.item_id: r for r in scene_records}
    )

    # 1. Explicit TRELLIS parent
    if plant_record.parent_id and plant_record.parent_id in by_id:
        parent = by_id[plant_record.parent_id]
        if parent.kind in ("TRELLIS", "PERGOLA", "ARBOUR"):
            _, rot_deg = _world_points_of_record(parent)
            rel_deg = (rot_deg - float(plant_record.transform.rotation_deg)) % 360.0
            support_kind = SUPPORT_TRELLIS if parent.kind == "TRELLIS" else SUPPORT_PERGOLA
            return {
                "kind": support_kind,
                "azimuth_deg": round(rel_deg, 1),
                "distance_cm": 0.0,
            }

    # 2. Nearest FENCE, PERGOLA, or TRELLIS within <= 50 cm of the climber's canopy circle
    px = float(plant_record.transform.east_cm)
    py = float(plant_record.transform.north_cm)
    raw_r = plant_record.params.get(PARAM_RADIUS_CM, 0.0)
    plant_r = float(raw_r) if isinstance(raw_r, (int, float)) and not isinstance(raw_r, bool) else 0.0

    best_kind: str | None = None
    best_gap = float("inf")
    best_deg = 0.0

    for cand in by_id.values():
        if cand.item_id == plant_record.item_id:
            continue
        if cand.kind in ("FENCE", "WALL"):
            cand_kind = SUPPORT_FENCE
        elif cand.kind in ("PERGOLA", "ARBOUR"):
            cand_kind = SUPPORT_PERGOLA
        elif cand.kind == "TRELLIS":
            cand_kind = SUPPORT_TRELLIS
        else:
            continue

        pts, default_deg = _world_points_of_record(cand)
        dist_center, seg_deg = _min_distance_and_tangent_deg(px, py, pts, default_deg)
        half_w = float(cand.path_width_cm or 0.0) * 0.5
        gap = max(0.0, dist_center - plant_r - half_w)
        if gap <= max_distance_cm and gap < best_gap:
            best_gap = gap
            best_kind = cand_kind
            best_deg = (seg_deg - float(plant_record.transform.rotation_deg)) % 360.0

    if best_kind is not None:
        return {
            "kind": best_kind,
            "azimuth_deg": round(best_deg, 1),
            "distance_cm": round(best_gap, 2),
        }

    # 3. Procedural tripod of bean poles
    return {
        "kind": SUPPORT_BEAN_POLES,
        "azimuth_deg": 0.0,
        "distance_cm": 0.0,
    }


def enrich_climber_records(records: Iterable[Record]) -> list[Record]:
    """Attach resolved ``climber_support`` params to every climber record in ``records``."""
    rec_list = list(records)
    by_id = {r.item_id: r for r in rec_list}
    out: list[Record] = []

    for rec in rec_list:
        if rec.kind in PLANT_KINDS:
            sprite = plant_sprite(rec)
            if (
                sprite is not None
                and traits_for(sprite).archetype == "climber"
                and PARAM_CLIMBER_SUPPORT not in rec.params
            ):
                sup = resolve_climber_support(rec, by_id)
                merged = dict(rec.params)
                merged[PARAM_CLIMBER_SUPPORT] = (
                    str(sup["kind"]),
                    float(sup["azimuth_deg"]),
                    float(sup["distance_cm"]),
                )
                rec = dataclasses.replace(rec, params=Params(merged))
        out.append(rec)
    return out


def build_forged_climber(
    traits: Traits3D,
    height_cm: float,
    radius_cm: float,
    seed: int,
    *,
    lod: int = LOD0,
    support: Mapping[str, Any] | None = None,
    accents: RawGeo | None = None,
) -> tuple[MeshPart, ...]:
    """Forge a climbing plant (`"climber"` archetype) on its resolved support."""
    validate_lod(lod)
    rng = _seed_rng(seed, 0xC113BE12)

    if isinstance(support, Mapping):
        sup_kind = str(support.get("kind", SUPPORT_BEAN_POLES))
        az_deg = float(support.get("azimuth_deg", 0.0))
    elif isinstance(support, tuple) and len(support) >= 2:
        sup_kind = str(support[0])
        az_deg = float(support[1])
    else:
        sup_kind = SUPPORT_BEAN_POLES
        az_deg = 0.0
    if sup_kind not in SUPPORT_KINDS:
        sup_kind = SUPPORT_BEAN_POLES
    az_rad = math.radians(az_deg)

    if lod == LOD0:
        n_vines = 6
        vine_steps = 12
        leaves_per_node = 14
        sides = 5
    elif lod == LOD1:
        n_vines = 4
        vine_steps = 8
        leaves_per_node = 8
        sides = 4
    else:
        n_vines = 3
        vine_steps = 5
        leaves_per_node = 4
        sides = 4

    p0_list: list[np.ndarray] = []
    p1_list: list[np.ndarray] = []
    r0_list: list[float] = []
    r1_list: list[float] = []
    vine_nodes: list[np.ndarray] = []

    pole_r = max(min(height_cm, radius_cm * 2.0) * 0.022, 0.45)
    vine_r = max(pole_r * 0.65, 0.32)

    if sup_kind == SUPPORT_BEAN_POLES:
        # 4-pole bamboo wigwam/tripod meeting near the apex + spiralling vines
        n_poles = 4 if lod != LOD2 else 3
        pole_az = np.linspace(0.0, 2.0 * math.pi, n_poles, endpoint=False) + float(
            rng.uniform(0.0, 2.0 * math.pi)
        )
        apex_lean = float(rng.uniform(0.06, 0.20)) * radius_cm
        apex_az = float(rng.uniform(0.0, 2.0 * math.pi))
        apex_xy = np.array([math.cos(apex_az) * apex_lean, math.sin(apex_az) * apex_lean], dtype=np.float64)
        tie_z = height_cm * 0.90

        for p_a in pole_az:
            base_pt = np.array(
                [math.cos(float(p_a)) * radius_cm * 0.72, math.sin(float(p_a)) * radius_cm * 0.72, 0.0],
                dtype=np.float64,
            )
            top_pt = np.array(
                [
                    apex_xy[0] - math.cos(float(p_a)) * radius_cm * 0.08,
                    apex_xy[1] - math.sin(float(p_a)) * radius_cm * 0.08,
                    tie_z,
                ],
                dtype=np.float64,
            )
            p0_list.append(base_pt)
            p1_list.append(top_pt)
            r0_list.append(pole_r)
            r1_list.append(pole_r * 0.78)

        # Helical vines climbing each pole with seed-driven asymmetry
        dom_az = float(rng.uniform(0.0, 2.0 * math.pi))
        for v_i in range(n_vines):
            base_a = float(pole_az[v_i % n_poles]) + float(rng.uniform(-0.25, 0.25))
            v_top_z = height_cm * float(rng.uniform(0.68, 0.98))
            if v_i == 0:
                v_top_z = height_cm * 0.99
            turns = float(rng.uniform(1.5, 2.8))
            prev_pt: np.ndarray | None = None
            for k in range(vine_steps + 1):
                t = k / vine_steps
                cone_r = radius_cm * (0.74 * (1.0 - 0.78 * t)) * (1.0 + 0.24 * math.cos(base_a - dom_az))
                theta = base_a + turns * 2.0 * math.pi * t
                cur_pt = np.array(
                    [
                        apex_xy[0] * t + math.cos(theta) * cone_r,
                        apex_xy[1] * t + math.sin(theta) * cone_r,
                        v_top_z * t,
                    ],
                    dtype=np.float64,
                )
                if prev_pt is not None:
                    p0_list.append(prev_pt)
                    p1_list.append(cur_pt)
                    r0_list.append(vine_r * (1.0 - 0.5 * ((k - 1) / vine_steps)))
                    r1_list.append(vine_r * (1.0 - 0.5 * t))
                if k >= 1:
                    vine_nodes.append(cur_pt)
                prev_pt = cur_pt
    else:
        # Trellis, Fence, or Pergola trained vine wall / arch along az_rad
        along = np.array([math.cos(az_rad), math.sin(az_rad)], dtype=np.float64)
        perp = np.array([-math.sin(az_rad), math.cos(az_rad)], dtype=np.float64)
        dom_side = float(rng.choice([-1.0, 1.0])) * float(rng.uniform(0.18, 0.38))

        for v_i in range(n_vines):
            frac_v = (v_i / max(n_vines - 1, 1)) * 2.0 - 1.0
            v_top_z = height_cm * float(rng.uniform(0.65, 0.98))
            if v_i == n_vines // 2:
                v_top_z = height_cm * 0.99
            prev_pt = None
            for k in range(vine_steps + 1):
                t = k / vine_steps
                # Fan out horizontally along the support plane as the vine climbs
                u_span = radius_cm * 0.88 * (frac_v * (0.35 + 0.65 * (t**0.8)) + dom_side * math.sin(t * math.pi))
                # Pergola drapes horizontally across the top 25% of height
                if sup_kind == SUPPORT_PERGOLA and t > 0.72:
                    v_depth = radius_cm * (0.25 + 0.55 * ((t - 0.72) / 0.28)) * math.sin(v_i * 1.7 + k)
                else:
                    v_depth = radius_cm * 0.28 * math.sin(t * math.pi * 2.2 + v_i)
                xy = along * u_span + perp * v_depth
                cur_pt = np.array([xy[0], xy[1], v_top_z * (t**0.88)], dtype=np.float64)
                if prev_pt is not None:
                    p0_list.append(prev_pt)
                    p1_list.append(cur_pt)
                    r0_list.append(vine_r * (1.0 - 0.55 * ((k - 1) / vine_steps)))
                    r1_list.append(vine_r * (1.0 - 0.55 * t))
                if k >= 1:
                    vine_nodes.append(cur_pt)
                prev_pt = cur_pt

    wood = frustum_tubes(
        np.asarray(p0_list),
        np.asarray(p1_list),
        np.asarray(r0_list),
        np.asarray(r1_list),
        sides=sides,
        color_rgba=bark_linear_rgba(traits.branching),
    )

    node_arr = np.asarray(vine_nodes, dtype=np.float64)
    base_pts = np.repeat(node_arr, leaves_per_node, axis=0)
    total_leaves = len(base_pts)
    spray_r = max(min(height_cm, radius_cm * 2.0) * 0.11, 2.0)
    dirs = normalize_vec(rng.normal(0.0, 1.0, size=(total_leaves, 3)))
    leaf_pts = base_pts + dirs * (spray_r * (rng.uniform(0.2, 1.0, size=(total_leaves, 1)) ** 0.6))
    leaf_pts[:, 2] = np.clip(leaf_pts[:, 2], height_cm * 0.04, height_cm)

    center = np.array([0.0, 0.0, height_cm * 0.52], dtype=np.float64)
    outward = normalize_vec(0.6 * dirs + 0.4 * normalize_vec(leaf_pts - center[None, :]))
    colors = palette_leaf_colors(
        traits.palette,
        traits.sprite,
        leaf_pts[:, 2] / max(height_cm, 1.0),
        np.hypot(leaf_pts[:, 0], leaf_pts[:, 1]) / max(radius_cm, 1.0),
        rng,
    )

    lod_scale = 1.0 if lod == LOD0 else (1.5 if lod == LOD1 else 2.3)
    l_len = max(min(height_cm, radius_cm * 2.0) * 0.11 * traits.leaf.leaf_scale * lod_scale, 2.0) * rng.uniform(
        0.8, 1.25, size=total_leaves
    )
    l_wid = l_len * traits.leaf.width_ratio
    foliage = micro_leaves(
        leaf_pts,
        outward,
        l_len,
        l_wid,
        colors,
        rng,
        center=center,
        spherize=0.68,
        droop=traits.crown.droop,
        cup=0.06,
    )
    accent_geo = accents if accents is not None else empty_geo()
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm)


__all__ = [
    "CLIMBER_SUPPORT_MAX_DISTANCE_CM",
    "PARAM_CLIMBER_SUPPORT",
    "SUPPORT_BEAN_POLES",
    "SUPPORT_FENCE",
    "SUPPORT_KINDS",
    "SUPPORT_PERGOLA",
    "SUPPORT_TRELLIS",
    "build_forged_climber",
    "enrich_climber_records",
    "resolve_climber_support",
]
