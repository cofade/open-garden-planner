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

__all__ = [
    "ARCHETYPES",
    "CATEGORIES",
    "CATEGORY_SPRITES",
    "DEFAULT_CATEGORY",
    "DEFAULT_PALETTE",
    "FEATURE_KEYS",
    "FLOWERS",
    "FRUITS",
    "GROUP_CATEGORIES",
    "GROUP_SPECIES",
    "HEDGE_PALETTE",
    "PALETTES",
    "PALETTE_ANCHORS",
    "PLANT_KINDS",
    "SPECIES",
    "SPECIES_SPRITES",
    "Available",
    "Recipe",
    "SpriteRef",
    "has_recipe",
    "palette_key",
    "recipe_for",
    "resolve_recipe",
    "resolve_sprite",
]
