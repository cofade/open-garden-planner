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
from numpy.typing import NDArray

from ..plant_art import PLANT_KINDS, traits_for
from ..plant_art.traits3d import Traits3D
from ..scene3d import PARAM_RADIUS_CM, MeshPart, Params, Record
from ..scene3d.builders.plants import plant_sprite
from .assemble import fit_forged_parts
from .foliage import RawGeo, empty_geo, micro_leaves, normalize_vec, palette_leaf_colors
from .lod import LOD0, LOD1, validate_lod
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


def climber_support_signature(records: Iterable[Record]) -> tuple[tuple[object, ...], ...]:
    """Exact dependencies of support enrichment, excluding a plant's own height.

    Geometry/pose changes, membership and support height invalidate resolution;
    seasonal plant height, material and display name do not. All plant sprite
    inputs are included so a species edit can enter or leave the climber set.
    """
    signature: list[tuple[object, ...]] = []
    for rec in records:
        if rec.kind in PLANT_KINDS:
            signature.append((rec.item_id, rec.kind, rec.transform, rec.parent_id,
                              tuple((key, rec.params.get(key)) for key in
                                    ("sprite_species", "plant_category", "radius_cm", PARAM_CLIMBER_SUPPORT))))
        elif rec.kind in ("TRELLIS", "PERGOLA", "ARBOUR", "FENCE", "WALL"):
            signature.append((rec.item_id, rec.kind, rec.transform, rec.path,
                              rec.footprints, rec.path_width_cm, rec.height_cm))
    return tuple(signature)


def _seed_rng(seed: int, salt: int) -> np.random.Generator:
    mixed = ((int(seed) * 2654435761) ^ salt) & 0xFFFFFFFFFFFFFFFF
    return np.random.default_rng(mixed)


def _support_segments(rec: Record) -> NDArray[np.float64]:
    """Independent physical support segments in world XY (never join separate rings)."""
    local: list[tuple[NDArray[np.float64], NDArray[np.float64]]] = []
    if rec.path:
        points = np.asarray(rec.path, dtype=float)
        local.extend(zip(points[:-1], points[1:], strict=True))
    elif rec.kind == "TRELLIS" and rec.footprints:
        # The trellis lattice lies on its long centre axis, not its footprint rim.
        points = np.asarray(rec.footprints[0], dtype=float)
        low, high = points.min(axis=0), points.max(axis=0)
        center = (low + high) * 0.5
        axis = int(np.argmax(high - low))
        first, last = center.copy(), center.copy()
        first[axis], last[axis] = low[axis], high[axis]
        local.append((first, last))
    else:
        for ring in rec.footprints:
            points = np.asarray(ring, dtype=float)
            if len(points) >= 2:
                local.extend(zip(points, np.roll(points, -1, axis=0), strict=True))
    if not local:
        local.append((np.zeros(2, dtype=np.float64), np.zeros(2, dtype=np.float64)))
    angle = math.radians(rec.transform.rotation_deg)
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    world: NDArray[np.float64] = (
        np.asarray(local, dtype=float) @ rotation.T + [rec.transform.east_cm, rec.transform.north_cm]
    )
    return world


def _concrete_support(plant: Record, support: Record, kind: str) -> dict[str, Any]:
    """Nearest finite segment, expressed in the plant's own unshifted frame."""
    segments = _support_segments(support)
    origin = np.array([plant.transform.east_cm, plant.transform.north_cm])
    delta = segments[:, 1] - segments[:, 0]
    length2 = np.sum(delta * delta, axis=1)
    fraction = np.clip(np.sum((origin - segments[:, 0]) * delta, axis=1) / np.maximum(length2, 1e-12), 0, 1)
    nearest = segments[:, 0] + fraction[:, None] * delta
    distances = np.linalg.norm(nearest - origin, axis=1)
    index = int(np.argmin(distances))
    angle = math.radians(-plant.transform.rotation_deg)
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    segment = (segments[index] - origin) @ rotation.T
    tangent = segment[1] - segment[0]
    azimuth = math.degrees(math.atan2(tangent[1], tangent[0])) % 360.0
    width = float(support.path_width_cm or 0.0)
    raw_radius = plant.params.get(PARAM_RADIUS_CM, 0.0)
    if not isinstance(raw_radius, (int, float, str)):
        raise TypeError("Climber canopy radius must be a numeric value")
    radius = float(raw_radius)
    return {
        "kind": kind,
        "azimuth_deg": azimuth,
        "distance_cm": max(0.0, float(distances[index]) - radius - width * 0.5),
        "segment_cm": tuple(float(v) for v in segment.ravel()),
        "width_cm": width,
        "height_cm": float(support.height_cm or 0.0) + support.transform.base_cm - plant.transform.base_cm,
        "base_cm": support.transform.base_cm - plant.transform.base_cm,
    }


def resolve_climber_support(
    plant_record: Record,
    scene_records: Mapping[str, Record] | Iterable[Record],
    *,
    max_distance_cm: float = CLIMBER_SUPPORT_MAX_DISTANCE_CM,
) -> dict[str, Any]:
    """Resolve support precedence, retaining its actual finite geometry and side.

    A nearby support outside the recorded canopy is a training direction only:
    forging must not enlarge the plant's footprint to pretend it makes contact.
    """
    by_id = scene_records if isinstance(scene_records, Mapping) else {r.item_id: r for r in scene_records}
    if plant_record.parent_id and plant_record.parent_id in by_id:
        parent = by_id[plant_record.parent_id]
        if parent.kind in ("TRELLIS", "PERGOLA", "ARBOUR"):
            kind = SUPPORT_TRELLIS if parent.kind == "TRELLIS" else SUPPORT_PERGOLA
            result = _concrete_support(plant_record, parent, kind)
            result["distance_cm"] = 0.0  # Explicit parent wins regardless of proximity.
            return result

    best = None
    best_distance: tuple[float, float, str] = (float("inf"), float("inf"), "")
    for candidate in by_id.values():
        if candidate.item_id == plant_record.item_id:
            continue
        if candidate.kind in ("FENCE", "WALL"):
            kind = SUPPORT_FENCE
        elif candidate.kind in ("PERGOLA", "ARBOUR"):
            kind = SUPPORT_PERGOLA
        elif candidate.kind == "TRELLIS":
            kind = SUPPORT_TRELLIS
        else:
            continue
        result = _concrete_support(plant_record, candidate, kind)
        gap = result["distance_cm"]
        # The true distance breaks ties between supports intersecting the canopy.
        segment = np.asarray(result["segment_cm"]).reshape(2, 2)
        direction = segment[1] - segment[0]
        share = np.clip(-np.dot(segment[0], direction) / max(np.dot(direction, direction), 1e-12), 0, 1)
        center_distance = float(np.linalg.norm(segment[0] + share * direction))
        distance = (gap, center_distance, candidate.item_id)
        if gap <= max_distance_cm and (best is None or distance < best_distance):
            best, best_distance = result, distance
    if best is not None:
        return best
    return {"kind": SUPPORT_BEAN_POLES, "azimuth_deg": 0.0, "distance_cm": 0.0}


def enrich_climber_records(records: Iterable[Record]) -> list[Record]:
    """Attach resolved ``climber_support`` params to every climber record in ``records``."""
    rec_list = list(records)
    by_id = {r.item_id: r for r in rec_list}
    return [enrich_climber_record(rec, by_id) for rec in rec_list]


def enrich_climber_record(
    rec: Record, scene_records: Mapping[str, Record] | Iterable[Record],
) -> Record:
    """Resolve one immutable plant record, suitable for a background forge job."""
    if rec.kind not in PLANT_KINDS or PARAM_CLIMBER_SUPPORT in rec.params:
        return rec
    sprite = plant_sprite(rec)
    if sprite is None or traits_for(sprite).archetype != "climber":
        return rec
    sup = resolve_climber_support(rec, scene_records)
    merged = dict(rec.params)
    merged[PARAM_CLIMBER_SUPPORT] = (
        str(sup["kind"]), float(sup["azimuth_deg"]), float(sup["distance_cm"]),
        *sup.get("segment_cm", ()),
        *(float(sup[key]) for key in ("width_cm", "height_cm", "base_cm") if key in sup),
    )
    return dataclasses.replace(rec, params=Params(merged))


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
    support_map = support if isinstance(support, Mapping) else {}
    concrete = "segment_cm" in support_map and sup_kind != SUPPORT_BEAN_POLES
    target = np.zeros(2, dtype=float)
    train_top = height_cm
    if concrete:
        segment = np.asarray(support_map["segment_cm"], dtype=float).reshape(2, 2)
        delta = segment[1] - segment[0]
        fraction = np.clip(-np.dot(segment[0], delta) / max(np.dot(delta, delta), 1e-12), 0, 1)
        target = segment[0] + fraction * delta
        distance = float(np.linalg.norm(target))
        # Aim inside the near quarter of the physical strip, if reachable.
        # Unreachable supports keep their direction but cannot enlarge the canopy.
        width = float(support_map.get("width_cm", 0.0))
        if distance > 1e-9:
            target *= min(max(0.0, distance - width * 0.25), radius_cm) / distance
        train_top = max(0.0, min(height_cm, float(support_map.get("height_cm", height_cm))))

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
        # Three bamboo poles meeting near the apex + spiralling vines.
        n_poles = 3
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
    elif concrete:
        along = np.array([math.cos(az_rad), math.sin(az_rad)])
        support_base = max(0.0, float(support_map.get("base_cm", 0.0)))
        contact_z = min(height_cm, max(height_cm * 0.03,
                        support_base + max(0.0, train_top - support_base) * 0.45))
        leader_count = max(1, n_vines // 2)
        lateral_count = n_vines - leader_count
        for v_i in range(n_vines):
            leader = v_i < leader_count
            if leader:
                v_top_z = height_cm * (0.99 if v_i == 0 else float(rng.uniform(0.78, 0.96)))
            else:
                v_top_z = height_cm * float(rng.uniform(0.58, 0.72))
            # Ascending basal shoots branch before the leader reaches its
            # support. A junction on the fence made them turn sharply away
            # from it halfway up the plant, outlining a decorative loop.
            branch_z = min(contact_z, height_cm * 0.18)
            branch_xy = target * min(branch_z / max(contact_z, 1e-6), 1.0)
            fan_angle = 2.0 * math.pi * (v_i - leader_count) / max(lateral_count, 1)
            fan_tip = np.array([math.cos(fan_angle), math.sin(fan_angle)]) * radius_cm * 0.88
            prev_pt = None
            # The contact node must survive coarse LOD, including short fences;
            # a long triangle jumping above the support is not attachment.
            steps = np.unique(np.r_[np.linspace(0.0, 1.0, vine_steps + 1),
                                    min(1.0, contact_z / v_top_z)])
            for k, t in enumerate(steps):
                z = v_top_z * t
                approach = min(z / max(contact_z, 1e-6), 1.0)
                xy = target * approach
                if z > contact_z and leader and v_i:
                    remaining = math.sqrt(max(radius_cm**2 - float(np.dot(target, target)), 0.0))
                    xy += along * remaining * 0.5 * math.sin(t * math.pi + v_i)
                    # Keep leaders along the actual finite support segment.
                    projection = np.dot(xy - segment[0], delta) / max(np.dot(delta, delta), 1e-12)
                    xy += delta * (np.clip(projection, 0, 1) - projection)
                if not leader and z > branch_z:
                    branch_share = (z - branch_z) / max(v_top_z - branch_z, 1e-6)
                    xy = branch_xy * (1 - branch_share) + fan_tip * branch_share
                cur_pt = np.array([xy[0], xy[1], z])
                if prev_pt is not None:
                    p0_list.append(prev_pt)
                    p1_list.append(cur_pt)
                    r0_list.append(vine_r * (1.0 - 0.55 * float(steps[k - 1])))
                    r1_list.append(vine_r * (1.0 - 0.55 * t))
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
    if concrete:
        # Leaf spread is decorative; the woody training coordinates are fixed.
        # Expand the leaf envelope about the true anchor, never recenter wood.
        for axis in (0, 1):
            low, high = float(foliage.pos[:, axis].min()), float(foliage.pos[:, axis].max())
            if low < 0 < high:
                foliage.pos[:, axis] *= np.where(foliage.pos[:, axis] < 0, radius_cm / -low, radius_cm / high)
    return fit_forged_parts(wood, foliage, accent_geo, height_cm, radius_cm,
                            structural_height=traits.deciduous or concrete,
                            preserve_horizontal_frame=concrete)


__all__ = [
    "CLIMBER_SUPPORT_MAX_DISTANCE_CM",
    "PARAM_CLIMBER_SUPPORT",
    "SUPPORT_BEAN_POLES",
    "SUPPORT_FENCE",
    "SUPPORT_KINDS",
    "SUPPORT_PERGOLA",
    "SUPPORT_TRELLIS",
    "build_forged_climber",
    "climber_support_signature",
    "enrich_climber_record",
    "enrich_climber_records",
    "resolve_climber_support",
]
