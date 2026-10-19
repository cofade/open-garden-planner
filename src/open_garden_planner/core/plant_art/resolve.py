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

The rule is the 2D rule, extracted — not improved. Its partial match has quirks
("Lemon Balm" takes the lemon tree's sprite, a whitespace-only species the
rose's); they are pinned, because changing them changes what users see in 2D.
``tests/fixtures/plant_art/sprite_resolution_golden.json`` holds 1,562 answers of
the resolver as it was before the extraction; ``tests/unit/test_plant_art.py``
holds this module to them.

Kinds and categories are plain NAMES here (``"TREE"``, ``"ROUND_DECIDUOUS"``):
``core.object_types`` imports Qt, and a 3D record carries names anyway.
"""

from __future__ import annotations

from collections.abc import Callable
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

    Priority, exactly as the 2D renderer has always resolved it:

    1. the species sprite — ``species`` lower-cased and stripped, as an exact key
       of ``SPECIES_SPRITES``, else the FIRST key that contains it or is
       contained in it;
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

    if species:
        wanted = species.lower().strip()
        exact = SPECIES_SPRITES.get(wanted)
        if exact is not None and (found := usable(GROUP_SPECIES, exact)) is not None:
            return found
        for key, name in SPECIES_SPRITES.items():
            if (key in wanted or wanted in key) and (
                found := usable(GROUP_SPECIES, name)
            ) is not None:
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
