"""Which sprite — and so which recipe — does a plant get? One answer for 2D and 3D.

The 2D canvas draws a plant from an SVG chosen by three facts of the item: its
object type, its species string and its plant category. That choice used to be
a private function of ``core/plant_renderer`` (a Qt module). Since Phase 17 L1.7
(#385) the rule and the maps it reads live here, Qt-free:

- ``plant_renderer._resolve_svg_path`` calls ``resolve_sprite`` and turns the
  answer into a file path;
- the 3D plant builder calls ``resolve_recipe`` and builds the recipe of the very
  sprite the canvas shows. A species the canvas draws with a category sprite
  gets the category's recipe in 3D too.

The rule was the 2D rule, extracted. It has since been made correct (#446): the
extracted rule matched a species name by SUBSTRING, so a melon was drawn as an
eggplant ("melon" is inside "solanum melongena"), a scientific name as a rose
("Petroselinum crispum" contains "rose"), a plant whose name merely CONTAINS
another plant's name as that other plant ("peach_tree" as a pea), and a
whitespace-only species as a rose (the empty string is inside every key).

The name is now matched as a WHOLE name or alias, and a name no sprite knows
falls back to the plant's category sprite. **Three of the issue's examples
survive that fix** - "Lemon Balm", "Bean (Bush)" and "Sweet Potato" still take
a fruit or vegetable sprite, because their names contain a whole word that is
another plant's name ("lemon", "bean", "potato"). Fixing those needs a curated
alias table, which the owner declined; the residue is pinned in
``tests/unit/test_plant_art.py``, so that a later change to the rule has to say
so.

``tests/fixtures/plant_art/sprite_resolution_golden.json`` holds 1,562 answers
of the resolver — the golden is regenerated from the rule, and
``scripts/make_sprite_resolution_golden.py`` keeps a statement-for-statement
copy of it as the fixture's provenance (and of the rule it replaced, as
``legacy_resolve``); ``tests/unit/test_plant_art.py`` holds this module to
both.

Kinds and categories are plain NAMES here (``"TREE"``, ``"ROUND_DECIDUOUS"``):
``core.object_types`` imports Qt, and a 3D record carries names anyway.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, TypeAlias

from .recipes import CATEGORIES, SPECIES, Recipe

#: The two sprite groups — the sub-directories of ``resources/plants`` and the
#: two recipe tables.
GROUP_SPECIES: Final = "species"
GROUP_CATEGORIES: Final = "categories"


@dataclass(frozen=True, slots=True)
class SpriteRef:
    """One sprite: ``group`` (``"species"`` or ``"categories"``) and ``name`` — the
    SVG's file stem and the key of its recipe."""

    group: str
    name: str


#: Plant object type (``ObjectType`` name) → the ``PlantCategory`` name it is drawn
#: with when neither a species nor a category says otherwise.
DEFAULT_CATEGORY: Final[dict[str, str]] = {
    "TREE": "ROUND_DECIDUOUS",
    "SHRUB": "SPREADING_SHRUB",
    "PERENNIAL": "FLOWERING_PERENNIAL",
}

#: The object types that are plants. ``plant_renderer.is_plant_type`` answers from
#: the same table (drift-guarded in ``tests/unit/test_plant_art.py``).
PLANT_KINDS: Final[frozenset[str]] = frozenset(DEFAULT_CATEGORY)

#: ``PlantCategory`` name → sprite file stem under ``resources/plants/categories``
#: (and the key of its recipe in ``recipes.CATEGORIES``).
CATEGORY_SPRITES: Final[dict[str, str]] = {
    "ROUND_DECIDUOUS": "round_deciduous",
    "COLUMNAR_TREE": "columnar_tree",
    "WEEPING_TREE": "weeping_tree",
    "CONIFER": "conifer",
    "SPREADING_SHRUB": "spreading_shrub",
    "COMPACT_SHRUB": "compact_shrub",
    "ORNAMENTAL_GRASS": "ornamental_grass",
    "FLOWERING_PERENNIAL": "flowering_perennial",
    "GROUND_COVER": "ground_cover",
    "CLIMBING_PLANT": "climbing_plant",
    "HEDGE_SECTION": "hedge_section",
    "VEGETABLE": "vegetable",
    "HERB": "herb",
    "FRUIT_TREE": "fruit_tree",
    "PALM": "palm",
}

#: Species name (lower case: common names, scientific names, aliases) → sprite file
#: stem under ``resources/plants/species`` (and the key of its recipe in
#: ``recipes.SPECIES``). ORDER MATTERS: the partial match below takes the first
#: key that fits.
SPECIES_SPRITES: Final[dict[str, str]] = {
    "rose": "rose",
    "rosa": "rose",
    "lavender": "lavender",
    "lavandula": "lavender",
    "apple": "apple_tree",
    "apple tree": "apple_tree",
    "malus": "apple_tree",
    "cherry": "cherry_tree",
    "cherry tree": "cherry_tree",
    "prunus": "cherry_tree",
    "sunflower": "sunflower",
    "helianthus": "sunflower",
    "tomato": "tomato",
    "solanum lycopersicum": "tomato",
    "boxwood": "boxwood",
    "buxus": "boxwood",
    "box": "boxwood",
    "rhododendron": "rhododendron",
    "azalea": "rhododendron",
    # Vegetables
    "pepper": "pepper",
    "bell pepper": "pepper",
    "capsicum": "pepper",
    "eggplant": "eggplant",
    "aubergine": "eggplant",
    "solanum melongena": "eggplant",
    "zucchini": "zucchini",
    "courgette": "zucchini",
    "cucurbita pepo": "zucchini",
    "cucumber": "cucumber",
    "cucumis sativus": "cucumber",
    "pumpkin": "pumpkin",
    "cucurbita maxima": "pumpkin",
    "squash": "squash",
    "butternut": "squash",
    "bean": "bean",
    "green bean": "bean",
    "phaseolus": "bean",
    "pea": "pea",
    "pisum sativum": "pea",
    "corn": "corn",
    "maize": "corn",
    "zea mays": "corn",
    "carrot": "carrot",
    "daucus carota": "carrot",
    "radish": "radish",
    "raphanus": "radish",
    "beet": "beet",
    "beetroot": "beet",
    "beta vulgaris": "beet",
    "turnip": "turnip",
    "brassica rapa": "turnip",
    "potato": "potato",
    "solanum tuberosum": "potato",
    "onion": "onion",
    "allium cepa": "onion",
    "garlic": "garlic",
    "allium sativum": "garlic",
    "leek": "leek",
    "allium ampeloprasum": "leek",
    "celery": "celery",
    "apium graveolens": "celery",
    "broccoli": "broccoli",
    "brassica oleracea": "broccoli",
    "cauliflower": "cauliflower",
    "cabbage": "cabbage",
    "kale": "kale",
    "spinach": "spinach",
    "spinacia oleracea": "spinach",
    "lettuce": "lettuce",
    "lactuca sativa": "lettuce",
    "arugula": "arugula",
    "rocket": "arugula",
    "eruca vesicaria": "arugula",
    "chard": "chard",
    "swiss chard": "chard",
    "artichoke": "artichoke",
    "cynara": "artichoke",
    "asparagus": "asparagus",
    "rhubarb": "rhubarb",
    "rheum": "rhubarb",
    "okra": "okra",
    "abelmoschus": "okra",
    # Herbs
    "basil": "basil",
    "ocimum basilicum": "basil",
    "rosemary": "rosemary",
    "salvia rosmarinus": "rosemary",
    "rosmarinus": "rosemary",
    "thyme": "thyme",
    "thymus": "thyme",
    "sage": "sage",
    "salvia officinalis": "sage",
    "mint": "mint",
    "mentha": "mint",
    "peppermint": "mint",
    "spearmint": "mint",
    "parsley": "parsley",
    "petroselinum": "parsley",
    "cilantro": "cilantro",
    "coriander": "cilantro",
    "coriandrum sativum": "cilantro",
    "dill": "dill",
    "anethum graveolens": "dill",
    "chives": "chives",
    "allium schoenoprasum": "chives",
    "oregano": "oregano",
    "origanum vulgare": "oregano",
    "tarragon": "tarragon",
    "artemisia dracunculus": "tarragon",
    "lemongrass": "lemongrass",
    "cymbopogon": "lemongrass",
    "chamomile": "chamomile",
    "matricaria chamomilla": "chamomile",
    "fennel": "fennel",
    "foeniculum vulgare": "fennel",
    "marjoram": "marjoram",
    "origanum majorana": "marjoram",
    "bay laurel": "bay_laurel",
    "bay": "bay_laurel",
    "laurus nobilis": "bay_laurel",
    "stevia": "stevia",
    "stevia rebaudiana": "stevia",
    "sorrel": "sorrel",
    "rumex acetosa": "sorrel",
    "borage": "borage",
    "borago officinalis": "borage",
    "lovage": "lovage",
    "levisticum officinale": "lovage",
    # Flowers
    "tulip": "tulip",
    "tulipa": "tulip",
    "daffodil": "daffodil",
    "narcissus": "daffodil",
    "dahlia": "dahlia",
    "peony": "peony",
    "paeonia": "peony",
    "iris": "iris",
    "lily": "lily",
    "lilium": "lily",
    "marigold": "marigold",
    "tagetes": "marigold",
    "zinnia": "zinnia",
    "cosmos": "cosmos",
    "aster": "aster",
    "chrysanthemum": "chrysanthemum",
    "mum": "chrysanthemum",
    "geranium": "geranium",
    "pelargonium": "geranium",
    "petunia": "petunia",
    "pansy": "pansy",
    "viola": "pansy",
    "hydrangea": "hydrangea",
    "clematis": "clematis",
    "wisteria": "wisteria",
    "jasmine": "jasmine",
    "jasminum": "jasmine",
    "hibiscus": "hibiscus",
    "crocus": "crocus",
    # Trees
    "pear": "pear_tree",
    "pear tree": "pear_tree",
    "pyrus": "pear_tree",
    "plum": "plum_tree",
    "plum tree": "plum_tree",
    "peach": "peach_tree",
    "peach tree": "peach_tree",
    "prunus persica": "peach_tree",
    "fig": "fig_tree",
    "fig tree": "fig_tree",
    "ficus carica": "fig_tree",
    "olive": "olive_tree",
    "olive tree": "olive_tree",
    "olea europaea": "olive_tree",
    "lemon": "lemon_tree",
    "lemon tree": "lemon_tree",
    "citrus limon": "lemon_tree",
    "orange": "orange_tree",
    "orange tree": "orange_tree",
    "citrus sinensis": "orange_tree",
    "walnut": "walnut_tree",
    "walnut tree": "walnut_tree",
    "juglans": "walnut_tree",
    "oak": "oak",
    "quercus": "oak",
    "maple": "maple",
    "acer": "maple",
    "birch": "birch",
    "betula": "birch",
    "willow": "willow",
    "salix": "willow",
    "magnolia": "magnolia",
    "pine": "pine",
    "pinus": "pine",
    "spruce": "spruce",
    "picea": "spruce",
    # Shrubs
    "blueberry": "blueberry",
    "vaccinium": "blueberry",
    "raspberry": "raspberry",
    "rubus idaeus": "raspberry",
    "blackberry": "blackberry",
    "rubus fruticosus": "blackberry",
    "gooseberry": "gooseberry",
    "ribes uva-crispa": "gooseberry",
    "currant": "currant",
    "ribes": "currant",
    "redcurrant": "currant",
    "blackcurrant": "currant",
    "holly": "holly",
    "ilex": "holly",
    "privet": "privet",
    "ligustrum": "privet",
    "juniper": "juniper",
    "juniperus": "juniper",
    "forsythia": "forsythia",
    "lilac": "lilac",
    "syringa": "lilac",
    "viburnum": "viburnum",
    "barberry": "barberry",
    "berberis": "barberry",
    "camellia": "camellia",
    "spirea": "spirea",
    "spiraea": "spirea",
    "elderberry": "elderberry",
    "sambucus": "elderberry",
    "elder": "elderberry",
}


#: "Is this sprite there?" — a file for the 2D renderer, a recipe for 3D.
Available: TypeAlias = Callable[[SpriteRef], bool]


def _normalise(name: str) -> str:
    """A species name folded to the form the tables are keyed by: lower case,
    blanks collapsed, and ``-`` and ``_`` read as the blank they stand for.

    The tables spell a name in words ("apple tree"), the gallery and the
    database spell the same name in a file stem ("apple_tree") or with a
    hyphen ("apple-tree"). All three are one name.
    """
    return re.sub(r"[\s\-_]+", " ", name.lower()).strip()


#: Every species key, normalised, to the sprite it names. The first key wins
#: when two keys normalise to the same string.
_NORMALISED_SPECIES: Final[dict[str, str]] = {}

#: Every species key as (its words, its length, the sprite it names), in table
#: order. The table's order is the tie-break of the last matching rule.
_SPECIES_WORDS: Final[list[tuple[frozenset[str], int, str]]] = []

for _key, _stem in SPECIES_SPRITES.items():
    _normalised = _normalise(_key)
    _NORMALISED_SPECIES.setdefault(_normalised, _stem)
    _SPECIES_WORDS.append((frozenset(_normalised.split()), len(_normalised), _stem))


def species_candidates(species: str) -> list[str]:
    """The sprite stems a species name can mean, best first.

    Three rules, in order (#446):

    1. **The whole name.** The name, normalised, is a key of the table.
    2. **The name contains a key.** Every word of a key is a word of the name
       — "Broad Bean" names the bean, "Winter Squash" the squash. The key with
       the most words wins, so "prunus persica" beats "prunus".
    3. **A key contains the name.** Every word of the name is a word of the key
       — "Solanum" names the tomato. The key with the fewest extra words wins;
      a tie keeps the table's order.

    A name that matches none of them is no species the sprites know, and the
    caller falls back to the plant's category sprite.
    """
    if not species:
        return []
    wanted = _normalise(species)
    if not wanted:
        return []
    found: list[str] = []
    exact = _NORMALISED_SPECIES.get(wanted)
    if exact is not None:
        found.append(exact)
    words = frozenset(wanted.split())
    contained = sorted(
        ((len(key_words), length, index, stem)
         for index, (key_words, length, stem) in enumerate(_SPECIES_WORDS)
         if key_words <= words),
        key=lambda row: (-row[0], -row[1], row[2]),
    )
    found.extend(row[3] for row in contained)
    supersets = sorted(
        ((len(key_words) - len(words), index, stem)
         for index, (key_words, _length, stem) in enumerate(_SPECIES_WORDS)
         if words <= key_words),
        key=lambda row: (row[0], row[1]),
    )
    found.extend(row[2] for row in supersets)
    return list(dict.fromkeys(found))


def has_recipe(sprite: SpriteRef) -> bool:
    """True when the recipe tables know this sprite (what 3D asks)."""
    return sprite.name in (SPECIES if sprite.group == GROUP_SPECIES else CATEGORIES)


def recipe_for(sprite: SpriteRef) -> Recipe:
    """The recipe of a sprite; ``KeyError`` for one the tables do not know."""
    return (SPECIES if sprite.group == GROUP_SPECIES else CATEGORIES)[sprite.name]


def resolve_sprite(
    kind: str,
    species: str = "",
    category: str | None = None,
    *,
    available: Available | None = None,
) -> SpriteRef | None:
    """The sprite of a plant, or None when ``kind`` is not a plant type.

    Priority:

    1. the species sprite — the name matched as a whole name, then as a name
       that contains a key, then as a name a key contains (``species_candidates``);
    2. the sprite of ``category`` (a ``PlantCategory`` name);
    3. the sprite of the kind's default category.

    ``available`` says whether a candidate exists; a candidate that does not is
    skipped and the next rule applies (the 2D renderer passes "the SVG file
    exists", 3D ``has_recipe``). None means every candidate exists.
    """
    default = DEFAULT_CATEGORY.get(kind)
    if default is None:
        return None

    def usable(group: str, name: str) -> SpriteRef | None:
        sprite = SpriteRef(group, name)
        return sprite if available is None or available(sprite) else None

    for stem in species_candidates(species):
        if (found := usable(GROUP_SPECIES, stem)) is not None:
            return found
    for category_name in (category, default):
        if category_name is None:
            continue
        name = CATEGORY_SPRITES.get(category_name, "")
        if name and (found := usable(GROUP_CATEGORIES, name)) is not None:
            return found
    return None


def resolve_recipe(
    kind: str, species: str = "", category: str | None = None
) -> tuple[SpriteRef, Recipe] | None:
    """``resolve_sprite`` over the sprites that have a recipe, with the recipe —
    what the 3D plant builder asks. None when ``kind`` is not a plant type."""
    sprite = resolve_sprite(kind, species, category, available=has_recipe)
    return None if sprite is None else (sprite, recipe_for(sprite))


def names_a_species_sprite(kind: str, name: str, category: str | None = None) -> bool:
    """True when ``name`` names a sprite of its own (not the category's)."""
    sprite = resolve_sprite(kind, name, category)
    return sprite is not None and sprite.group == GROUP_SPECIES


def species_name_for_record(
    record: Mapping[str, object], kind: str, category: str | None = None
) -> str:
    """The name a plant should carry for a species record, so that the sprite
    resolver draws the species the record names (#445).

    The record's common name when a sprite answers to it, else its scientific
    name when one does, else the common name itself — a name the sprites do
    not know is still the plant's name; it simply draws its category's sprite.

    The name is what the item CARRIES, not what the record happens to call the
    plant: the item's own species string is what the 2D renderer and the 3D
    plant builder both resolve from, so a name that only lives in the record's
    data can never change what the plant looks like.
    """
    common = str(record.get("common_name") or "").strip()
    scientific = str(record.get("scientific_name") or "").strip()
    for name in (common, scientific):
        if name and names_a_species_sprite(kind, name, category):
            return name
    return common or scientific
