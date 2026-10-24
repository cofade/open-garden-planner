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
    attach_accents,
    build_accents,
    build_blossom_accents,
    build_fruit_accents,
    build_pod_accents,
    build_tuber_accents,
    build_umbel_accents,
)
from .assemble import PART_ACCENTS, PART_FOLIAGE, PART_WOOD, fit_forged_parts, silhouette_iou
from .cache import DEFAULT_FORGE_CACHE, CacheKey, ForgeCache, make_cache_key
from .climbers import (
    CLIMBER_SUPPORT_MAX_DISTANCE_CM,
    PARAM_CLIMBER_SUPPORT,
    SUPPORT_BEAN_POLES,
    SUPPORT_FENCE,
    SUPPORT_KINDS,
    SUPPORT_PERGOLA,
    SUPPORT_TRELLIS,
    build_forged_climber,
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


def _support_signature(support: Mapping[str, Any] | tuple[Any, ...] | None) -> str:
    if not support:
        return ""
    if isinstance(support, Mapping):
        return json.dumps(dict(support), sort_keys=True, separators=(",", ":"))
    return json.dumps(list(support), separators=(",", ":"))


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
    """Forge a 3D plant mesh for ``sprite`` at ``(height_cm, radius_cm, seed, lod)``."""
    validate_lod(lod)
    h = float(height_cm)
    r = float(radius_cm)
    if not (math.isfinite(h) and math.isfinite(r)) or h <= 0.0 or r <= 0.0:
        raise ValueError(f"height_cm and radius_cm must be finite positive floats, got ({h!r}, {r!r})")

    extra_sig = _support_signature(support)
    if not include_accents:
        extra_sig = f"{extra_sig}|no_accents"
    key = make_cache_key(sprite.group, sprite.name, seed, lod, h, r, extra_sig)

    def _build() -> tuple[MeshPart, ...]:
        traits = traits_for(sprite)
        if traits.archetype == "canopy":
            parts = build_forged_tree(traits, h, r, seed, lod=lod)
        elif traits.archetype == "conifer":
            parts = build_forged_conifer(traits, h, r, seed, lod=lod)
        elif traits.archetype == "palm":
            parts = build_forged_palm(traits, h, r, seed, lod=lod)
        elif traits.archetype == "mound":
            parts = build_forged_shrub(traits, h, r, seed, lod=lod)
        elif traits.archetype == "hedge":
            parts = build_forged_hedge(traits, h, r, seed, lod=lod)
        elif traits.archetype == "rosette":
            parts = build_forged_rosette(traits, h, r, seed, lod=lod)
        elif traits.archetype == "grass":
            parts = build_forged_grass(traits, h, r, seed, lod=lod)
        elif traits.archetype == "feathery":
            parts = build_forged_feathery(traits, h, r, seed, lod=lod)
        elif traits.archetype == "allium":
            parts = build_forged_allium(traits, h, r, seed, lod=lod)
        elif traits.archetype == "head":
            parts = build_forged_head(traits, h, r, seed, lod=lod)
        elif traits.archetype == "ground":
            parts = build_forged_ground(traits, h, r, seed, lod=lod)
        elif traits.archetype == "flower":
            parts = build_forged_flower(traits, h, r, seed, lod=lod)
        elif traits.archetype == "climber":
            parts = build_forged_climber(traits, h, r, seed, lod=lod, support=support)
        else:
            return build_silhouette(recipe_for(sprite), int(seed), h, r)
        if include_accents:
            parts = attach_accents(parts, traits, h, r, seed, lod=lod)
        return parts

    if cache is None:
        return _build()
    return cache.get_or_build(key, _build)


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
        support_map = {
            "kind": str(support[0]),
            "azimuth_deg": float(support[1]),
            "distance_cm": float(support[2]) if len(support) >= 3 else 0.0,
        }
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


__all__ = [
    "ACCENT_FAMILIES",
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
    "resolve_climber_support",
    "select_lod",
    "silhouette_iou",
    "triangle_budget_for_lod",
    "validate_lod",
]
