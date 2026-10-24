"""Plant art — the recipe tables and the species → recipe resolution, shared by
the 2D sprites and the 3D plants (Phase 17 L1.7, #385; ADR-059 addendum, §8.22,
§8.29.7).

Two modules, standard library only (no Qt, no numpy — pinned by an AST scan):

- ``recipes`` — ``PALETTES``, ``FRUITS``, ``FLOWERS``, ``SPECIES``, ``CATEGORIES``:
  what a plant looks like. ``scripts/generate_plant_sprites.py`` draws the 123
  SVGs from them; ``core/scene3d/builders/plants.py`` builds 3D silhouettes from
  them.
- ``resolve`` — ``resolve_sprite`` / ``resolve_recipe``: which recipe a plant
  item gets, the one rule the 2D renderer and the 3D builder both ask.

One table and one rule, so the plan and the 3D view cannot disagree about a
plant's archetype or colours. The per-item seed of the 3D builders is
``core.scene3d.item_seed`` — it is not re-exported here, to keep this package
free of numpy.
"""

from __future__ import annotations

from .recipes import (
    ARCHETYPES,
    CATEGORIES,
    DEFAULT_PALETTE,
    FEATURE_KEYS,
    FLOWERS,
    FRUITS,
    HEDGE_PALETTE,
    PALETTE_ANCHORS,
    PALETTES,
    SPECIES,
    Recipe,
    palette_key,
)
from .resolve import (
    CATEGORY_SPRITES,
    DEFAULT_CATEGORY,
    GROUP_CATEGORIES,
    GROUP_SPECIES,
    PLANT_KINDS,
    SPECIES_SPRITES,
    Available,
    SpriteRef,
    has_recipe,
    recipe_for,
    resolve_recipe,
    resolve_sprite,
)
from .traits3d import (
    BARK_BIRCH,
    BARK_COLORS,
    CATEGORY_TRAITS,
    CROWN_SHAPES,
    HARVEST_WINDOWS_WEEKS,
    LEAF_SHAPES,
    REFERENCE_LAST_FROST,
    SPECIES_TRAITS,
    WHITE_BARK_SHADE,
    BranchingTraits,
    CrownTraits,
    LeafTraits,
    Traits3D,
    fruit_months_from_harvest_window,
    resolve_traits,
    traits_for,
)

__all__ = [
    "ARCHETYPES",
    "BARK_BIRCH",
    "BARK_COLORS",
    "CATEGORIES",
    "CATEGORY_SPRITES",
    "CATEGORY_TRAITS",
    "CROWN_SHAPES",
    "DEFAULT_CATEGORY",
    "DEFAULT_PALETTE",
    "FEATURE_KEYS",
    "FLOWERS",
    "FRUITS",
    "GROUP_CATEGORIES",
    "GROUP_SPECIES",
    "HARVEST_WINDOWS_WEEKS",
    "HEDGE_PALETTE",
    "LEAF_SHAPES",
    "PALETTES",
    "PALETTE_ANCHORS",
    "PLANT_KINDS",
    "REFERENCE_LAST_FROST",
    "SPECIES",
    "SPECIES_SPRITES",
    "SPECIES_TRAITS",
    "WHITE_BARK_SHADE",
    "Available",
    "BranchingTraits",
    "CrownTraits",
    "LeafTraits",
    "Recipe",
    "SpriteRef",
    "Traits3D",
    "fruit_months_from_harvest_window",
    "has_recipe",
    "palette_key",
    "recipe_for",
    "resolve_recipe",
    "resolve_sprite",
    "resolve_traits",
    "traits_for",
]
