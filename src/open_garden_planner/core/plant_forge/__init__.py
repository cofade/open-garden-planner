"""Plant Forge — procedural 3D species models from the 2D sprite recipes (Phase 17 L3, #387).

Turns the 2D recipe table (`core.plant_art`) + 3D structural traits
(`core.plant_art.traits3d`) into species-accurate, multi-LOD 3D meshes (`LOD0`,
`LOD1`, `LOD2`) in the item-local scene frame (x = East, y = North, z = up, cm).

Qt-free: standard library, NumPy, `core.plant_art`, and `core.scene3d` only.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ..plant_art import (
    PLANT_KINDS,
    SpriteRef,
    has_recipe,
    recipe_for,
    resolve_sprite,
    traits_for,
)
from ..scene3d import (
    MAX_LENGTH_CM,
    PARAM_RADIUS_CM,
    PARAM_SEED,
    BuilderRegistry,
    MeshPart,
    Record,
    default_builder,
    item_seed,
)
from ..scene3d.builders.plants import (
    build_silhouette,
    placeholder_parts,
    plant_sprite,
)
from .accents import (
    ACCENT_FAMILIES,
    FLOWER_PART,
    FRUIT_PART,
    SEASONAL_PARTS,
    TUBER_PART,
    attach_accents,
    build_accents,
    build_blossom_accents,
    build_fruit_accents,
    build_pod_accents,
    build_tuber_accents,
    build_umbel_accents,
)
from .assemble import PART_ACCENTS, PART_FOLIAGE, PART_WOOD, fit_forged_parts, silhouette_iou
from .cache import (
    DEFAULT_FORGE_CACHE,
    QUANT_STEP,
    CacheKey,
    ForgeCache,
    make_cache_key,
    quantised_size_cm,
    size_bucket,
)
from .climbers import (
    CLIMBER_SUPPORT_MAX_DISTANCE_CM,
    PARAM_CLIMBER_SUPPORT,
    SUPPORT_BEAN_POLES,
    SUPPORT_FENCE,
    SUPPORT_KINDS,
    SUPPORT_PERGOLA,
    SUPPORT_TRELLIS,
    build_forged_climber,
    climber_support_signature,
    enrich_climber_record,
    enrich_climber_records,
    resolve_climber_support,
)
from .foliage import RawGeo, concat_geo, empty_geo, micro_leaves, palette_leaf_colors
from .herbaceous import (
    GOLDEN_ANGLE,
    build_forged_allium,
    build_forged_feathery,
    build_forged_flower,
    build_forged_grass,
    build_forged_ground,
    build_forged_head,
    build_forged_rosette,
)
from .lod import (
    LOD0,
    LOD0_MAX_DISTANCE_CM,
    LOD0_TRIANGLE_BUDGET,
    LOD1,
    LOD1_MAX_DISTANCE_CM,
    LOD1_TRIANGLE_BUDGET,
    LOD2,
    LOD2_TRIANGLE_BUDGET,
    LOD_LEVELS,
    LOD_TRIANGLE_BUDGETS,
    lod_skeleton_budget,
    select_lod,
    triangle_budget_for_lod,
    validate_lod,
)
from .skeleton import Skeleton, grow_skeleton
from .trees import bark_linear_rgba, build_forged_tree, build_tree_foliage_from_skeleton
from .tube import cylinder_geo, frustum_tubes, limb_tubes
from .woody import (
    build_forged_conifer,
    build_forged_hedge,
    build_forged_palm,
    build_forged_shrub,
)


def _bucketed_support(
    support: Mapping[str, Any] | None, step_cm: float,
) -> Mapping[str, Any] | None:
    """A climber's support with its distance at the bucket centre (#973), so every shape
    inside one cache bucket is built at the same distance and the contact error is at most
    half a step."""
    if not support or step_cm <= 0.0:
        return support
    data = dict(support)
    distance = data.get("distance_cm")
    if isinstance(distance, (int, float)) and not isinstance(distance, bool):
        data["distance_cm"] = round(float(distance) / step_cm) * step_cm
    return data


def _support_signature(
    support: Mapping[str, Any] | tuple[Any, ...] | None,
    *,
    distance_step_cm: float | None = None,
) -> str:
    """The cache part of a climber's support: its GEOMETRY, not the plant's own size.

    ``distance_cm`` is derived from the plant's exact canopy radius
    (``climbers.resolve_climber_support``), so a growing fence-trained climber changed the
    key every day (#973 review). It is bucketed to the same relative step as the plant's
    own size (2 % of its radius), so the shape and its support training stay together
    across a season; the support contact may be off by that half step, well inside the
    50 cm support search.
    """
    if not support:
        return ""

    def _distance(value: object) -> object:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            step = distance_step_cm if distance_step_cm and distance_step_cm > 0 else 1.0
            return round(float(value) / step) * step
        return value

    if isinstance(support, Mapping):
        data = dict(support)
        data["distance_cm"] = _distance(data.get("distance_cm"))
        return json.dumps(data, sort_keys=True, separators=(",", ":"))
    values = list(support)
    if len(values) >= 3:
        values[2] = _distance(values[2])
    return json.dumps(values, separators=(",", ":"))


def forge_plant(
    sprite: SpriteRef,
    height_cm: float,
    radius_cm: float,
    *,
    seed: int = 0,
    lod: int = LOD0,
    cache: ForgeCache | None = DEFAULT_FORGE_CACHE,
    support: Mapping[str, Any] | None = None,
    include_accents: bool = True,
) -> tuple[MeshPart, ...]:
    """Forge a 3D plant mesh for ``sprite`` at ``(height_cm, radius_cm, seed, lod)``.

    With a cache, the mesh is built at the 2 % size bucket and stretched to the exact
    height and spread (#973); without one, the exact size is built."""
    validate_lod(lod)
    h = float(height_cm)
    r = float(radius_cm)
    if not (math.isfinite(h) and math.isfinite(r)) or h <= 0.0 or r <= 0.0:
        raise ValueError(f"height_cm and radius_cm must be finite positive floats, got ({h!r}, {r!r})")

    # #973: with a cache, forge one shape per 2 % size bucket and stretch it to the exact
    # size, so a tree that grows a little each day keeps its form instead of being
    # re-randomised. Without a cache there is nothing to reuse: build the exact size.
    h_bucket = h if cache is None else quantised_size_cm(h)
    r_bucket = r if cache is None else quantised_size_cm(r)
    # The climber's support distance is bucketed by the SAME relative step as the size, and
    # the builder uses the bucket centre, so a growing climber's key and its support
    # contact are stable inside one size bucket (error at most half a step).
    distance_step = 0.02 * r_bucket
    build_support = _bucketed_support(support, distance_step)
    extra_sig = _support_signature(build_support, distance_step_cm=distance_step)
    if not include_accents:
        extra_sig = f"{extra_sig}|no_accents"
    key = make_cache_key(sprite.group, sprite.name, seed, lod, h_bucket, r_bucket, extra_sig)

    def _build() -> tuple[MeshPart, ...]:
        traits = traits_for(sprite)
        if traits.archetype == "canopy":
            parts = build_forged_tree(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "conifer":
            parts = build_forged_conifer(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "palm":
            parts = build_forged_palm(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "mound":
            parts = build_forged_shrub(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "hedge":
            parts = build_forged_hedge(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "rosette":
            parts = build_forged_rosette(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "grass":
            parts = build_forged_grass(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "feathery":
            parts = build_forged_feathery(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "allium":
            parts = build_forged_allium(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "head":
            parts = build_forged_head(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "ground":
            parts = build_forged_ground(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "flower":
            parts = build_forged_flower(traits, h_bucket, r_bucket, seed, lod=lod)
        elif traits.archetype == "climber":
            parts = build_forged_climber(traits, h_bucket, r_bucket, seed, lod=lod,
                                         support=build_support)
        else:
            return build_silhouette(recipe_for(sprite), int(seed), h_bucket, r_bucket)
        if include_accents:
            return attach_accents(parts, traits, h_bucket, r_bucket, seed, lod=lod)
        # a bulb's or a stemmed flower's builder placed its own flowers (#940)
        return tuple(p for p in parts if p.name not in SEASONAL_PARTS)

    built = _build() if cache is None else cache.get_or_build(key, _build)
    if h_bucket == h and r_bucket == r:
        return built
    return tuple(
        replace(part, mesh=part.mesh.scaled(r / r_bucket, r / r_bucket, h / h_bucket))
        for part in built
    )


def forge_species_plant(
    kind: str,
    common_name: str,
    scientific_name: str = "",
    plant_category: str | None = None,
    *,
    height_cm: float,
    radius_cm: float,
    seed: int = 0,
    lod: int = LOD0,
    cache: ForgeCache | None = DEFAULT_FORGE_CACHE,
    support: Mapping[str, Any] | None = None,
) -> tuple[MeshPart, ...]:
    """Resolve ``(kind, common_name, scientific_name, plant_category)`` and forge the plant."""
    species_text = f"{common_name} {scientific_name}".strip() if scientific_name else common_name
    sprite = resolve_sprite(
        kind,
        species_text,
        plant_category,
        available=has_recipe,
    )
    if sprite is None:
        sprite = SpriteRef("categories", "round_deciduous")
    return forge_plant(
        sprite,
        height_cm,
        radius_cm,
        seed=seed,
        lod=lod,
        cache=cache,
        support=support,
    )


def _estimated_fallback_cm(record: Record) -> float | None:
    try:
        from ..plant_height_estimate import ESTIMATED_HEIGHT_PARAM

        est = record.params.get(ESTIMATED_HEIGHT_PARAM)
        if isinstance(est, bool) or not isinstance(est, (int, float)):
            return None
        val = float(est)
        return val if val > 0.0 else None
    except Exception:
        return None


def forge_record(
    record: Record,
    *,
    lod: int = LOD0,
    cache: ForgeCache | None = DEFAULT_FORGE_CACHE,
) -> tuple[MeshPart, ...]:
    """Pure ``Record -> tuple[MeshPart, ...]`` builder using Plant Forge (`verify_builder`-clean)."""
    if record.kind not in PLANT_KINDS:
        return default_builder(record)
    sprite = plant_sprite(record)
    raw_radius = record.params.get(PARAM_RADIUS_CM)
    if (
        sprite is None
        or isinstance(raw_radius, bool)
        or not isinstance(raw_radius, (int, float))
        or not math.isfinite(raw_radius)
        or float(raw_radius) <= 0.0
    ):
        return default_builder(record)

    radius = float(raw_radius)
    height = record.height_cm
    if height is None:
        height = _estimated_fallback_cm(record)
        if height is None or height > MAX_LENGTH_CM or radius > MAX_LENGTH_CM:
            return placeholder_parts(radius)

    raw_seed = record.params.get(PARAM_SEED)
    seed = item_seed(str(raw_seed) if raw_seed is not None else "", "plant")
    support = record.params.get("climber_support")
    if isinstance(support, Mapping):
        support_map: Mapping[str, Any] | None = support
    elif isinstance(support, tuple) and len(support) >= 2:
        s1 = support[1]
        s2 = support[2] if len(support) >= 3 else 0.0
        support_map = {
            "kind": str(support[0]),
            "azimuth_deg": float(s1) if isinstance(s1, (int, float, str)) else 0.0,
            "distance_cm": float(s2) if isinstance(s2, (int, float, str)) else 0.0,
        }
        if len(support) >= 10:
            support_map = dict(support_map, segment_cm=support[3:7],
                               width_cm=support[7], height_cm=support[8], base_cm=support[9])
    else:
        support_map = None
    return forge_plant(
        sprite,
        float(height),
        radius,
        seed=seed,
        lod=lod,
        cache=cache,
        support=support_map,
    )


def register_forged_plants(
    registry: BuilderRegistry,
    *,
    lod: int = LOD0,
    replace: bool = True,
) -> None:
    """Register `forge_record` for all `PLANT_KINDS` (`TREE`, `SHRUB`, `PERENNIAL`) on `registry`."""
    validate_lod(lod)

    def _builder(record: Record) -> tuple[MeshPart, ...]:
        return forge_record(record, lod=lod)

    for kind in sorted(PLANT_KINDS):
        registry.register(kind, _builder, replace=replace)


__all__ = [
    "ACCENT_FAMILIES",
    "FLOWER_PART",
    "FRUIT_PART",
    "SEASONAL_PARTS",
    "TUBER_PART",
    "CLIMBER_SUPPORT_MAX_DISTANCE_CM",
    "CacheKey",
    "DEFAULT_FORGE_CACHE",
    "ForgeCache",
    "GOLDEN_ANGLE",
    "LOD0",
    "LOD0_MAX_DISTANCE_CM",
    "LOD0_TRIANGLE_BUDGET",
    "LOD1",
    "LOD1_MAX_DISTANCE_CM",
    "LOD1_TRIANGLE_BUDGET",
    "LOD2",
    "LOD2_TRIANGLE_BUDGET",
    "LOD_LEVELS",
    "LOD_TRIANGLE_BUDGETS",
    "PARAM_CLIMBER_SUPPORT",
    "PART_ACCENTS",
    "PART_FOLIAGE",
    "PART_WOOD",
    "QUANT_STEP",
    "RawGeo",
    "SUPPORT_BEAN_POLES",
    "SUPPORT_FENCE",
    "SUPPORT_KINDS",
    "SUPPORT_PERGOLA",
    "SUPPORT_TRELLIS",
    "Skeleton",
    "attach_accents",
    "bark_linear_rgba",
    "build_accents",
    "build_blossom_accents",
    "build_forged_allium",
    "build_forged_climber",
    "climber_support_signature",
    "build_forged_conifer",
    "build_forged_feathery",
    "build_forged_flower",
    "build_forged_grass",
    "build_forged_ground",
    "build_forged_head",
    "build_forged_hedge",
    "build_forged_palm",
    "build_forged_rosette",
    "build_forged_shrub",
    "build_forged_tree",
    "build_fruit_accents",
    "build_pod_accents",
    "build_tree_foliage_from_skeleton",
    "build_tuber_accents",
    "build_umbel_accents",
    "concat_geo",
    "cylinder_geo",
    "empty_geo",
    "enrich_climber_records",
    "enrich_climber_record",
    "fit_forged_parts",
    "forge_plant",
    "forge_record",
    "forge_species_plant",
    "frustum_tubes",
    "grow_skeleton",
    "limb_tubes",
    "lod_skeleton_budget",
    "make_cache_key",
    "micro_leaves",
    "palette_leaf_colors",
    "quantised_size_cm",
    "register_forged_plants",
    "resolve_climber_support",
    "select_lod",
    "silhouette_iou",
    "size_bucket",
    "triangle_budget_for_lod",
    "validate_lod",
]
