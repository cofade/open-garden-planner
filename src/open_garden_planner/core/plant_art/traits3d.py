"""3D morphological and phenological traits per plant recipe (Phase 17 L3.0, #387).

The 2D sprite recipes in ``recipes.py`` describe a plant from straight above: its
archetype, leaf palette, and feature accents. Building the same plant in 3D and
animating it across the year requires the vertical and seasonal traits a top-down
sprite never needed:

- **Crown shape** (``CrownTraits``): crown form name, clear-trunk fraction, vertical
  taper (pyramid/egg vs. vase), leaf/twig droop, and horizontal aspect.
- **Branching** (``BranchingTraits``): space-colonisation attractor count, pipe-model
  exponent, trunk base radius ratio, apical tropism, branch gnarl, and 2D-sourced
  bark colour + linear-light shade (``WHITE_BARK_SHADE = 0.7`` for birch so sun-lit
  white bark never clips).
- **Leaves** (``LeafTraits``): leaf shape kind, reference leaf length (cm),
  width-to-length ratio, recipe ``leaf_scale``, ``frilly`` and ``narrow`` flags.
- **Season & phenology** (on ``Traits3D``): ``deciduous`` flag, Northern-Hemisphere
  illustrative ``bloom_months`` (1..12) and ``blossom_spec``, ``harvest_weeks``
  (weeks relative to last spring frost from ``plant_species.json``), ``fruit_months``
  derived from the harvest window via ``fruit_months_from_harvest_window``,
  ``autumn_palette`` (always a key of ``recipes.PALETTES``) and ``frost_hardy_bloom``
  (does the plant flower before the last frost and after the first one: #940).
- **Flowers** (``FlowerTraits``, #940): where they stand (on the crown's surface, on
  scapes above a bulb's leaves, on stem tips), their real size, cup and facing, and the
  share of the crown they cover in full bloom; ``bloom_leaf_density``: the leaves a
  plant that flowers before or with them carries while it is in flower.

Standard library only (no Qt, no numpy — pinned by ``tests/unit/test_plant_art.py``).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, replace
from typing import Final

from .recipes import CATEGORIES, FLOWERS, PALETTES, SPECIES, Recipe, palette_key
from .resolve import GROUP_CATEGORIES, GROUP_SPECIES, SpriteRef, resolve_sprite

#: Linear-light multiplier for birch white bark (``FLOWERS["white"][0] == "#e8e4d8"``)
#: so a low winter sun (14° elevation, n·l ≈ 0.97) never clips trunk pixels to 255.
WHITE_BARK_SHADE: Final[float] = 0.7

#: Reference temperate Northern-Hemisphere last spring frost date (25 April) used when
#: converting ``(harvest_start, harvest_end)`` week offsets to default ``fruit_months``
#: without a plan-specific frost date.
REFERENCE_LAST_FROST: Final[datetime.date] = datetime.date(2026, 4, 25)

#: Allowed crown shape names.
CROWN_SHAPES: Final[frozenset[str]] = frozenset({
    "round",
    "oval",
    "pyramidal",
    "columnar",
    "vase",
    "spreading",
    "weeping",
    "conical",
    "tiered",
    "fan",
    "mound",
    "flat",
    "upright",
})

#: Allowed 3D leaf shape names.
LEAF_SHAPES: Final[frozenset[str]] = frozenset({
    "diamond",
    "ovate",
    "lobed",
    "needle",
    "strap",
    "frond",
    "pinnate",
    "cordate",
    "cupped",
})

#: Allowed 2D-sourced bark hex colours (from ``object_art.materials.MATERIALS`` and
#: ``plant_art.recipes``; drift-guarded in ``tests/unit/test_plant_art.py``).
BARK_WALNUT: Final[str] = "#66432c"       # MATERIALS["walnut"]["mid"]
BARK_WALNUT_DARK: Final[str] = "#3f2617"  # MATERIALS["walnut"]["dark"]
BARK_OAK: Final[str] = "#7d5029"          # MATERIALS["oak"]["dark"]
BARK_TEAK: Final[str] = "#69401c"         # MATERIALS["teak"]["dark"]
BARK_PINE: Final[str] = "#54401e"         # MATERIALS["pine"]["occ"]
BARK_SHINGLE: Final[str] = "#78695a"      # MATERIALS["shingle"]["mid"]
BARK_GREY: Final[str] = "#5f584b"         # MATERIALS["grey_wood"]["dark"]
BARK_BIRCH: Final[str] = FLOWERS["white"][0]  # "#e8e4d8", shaded by WHITE_BARK_SHADE
BARK_STEM: Final[str] = PALETTES["olive"]["b0"]  # "#46601f", herbaceous green stem

BARK_COLORS: Final[frozenset[str]] = frozenset({
    BARK_WALNUT,
    BARK_WALNUT_DARK,
    BARK_OAK,
    BARK_TEAK,
    BARK_PINE,
    BARK_SHINGLE,
    BARK_GREY,
    BARK_BIRCH,
    BARK_STEM,
})


@dataclass(frozen=True, slots=True)
class CrownTraits:
    """3D crown envelope parameters."""

    shape: str = "round"
    trunk_share: float = 0.30
    taper: float = 0.0
    droop: float = 0.15
    aspect_xy: float = 1.0


@dataclass(frozen=True, slots=True)
class BranchingTraits:
    """Space-colonisation and pipe-model branching parameters."""

    attractors: int = 520
    pipe_exponent: float = 2.5
    trunk_base_ratio: float = 0.018
    apical_bias: float = 0.12
    gnarl: float = 0.08
    bark_color: str = BARK_WALNUT
    bark_shade: float = 1.0


@dataclass(frozen=True, slots=True)
class LeafTraits:
    """3D micro-leaf / blade / frond geometry traits."""

    shape: str = "ovate"
    length_cm: float = 12.0
    width_ratio: float = 0.60
    leaf_scale: float = 1.0
    frilly: bool = False
    narrow: bool = False


#: Where a plant's flowers stand (``FlowerTraits.habit``, #940).
FLOWER_HABITS: Final[frozenset[str]] = frozenset({"crown", "scape", "head"})


@dataclass(frozen=True, slots=True)
class FlowerTraits:
    """How a plant's flowers stand in 3D (#940). The 2D recipe draws them from above only.

    ``habit``: ``"crown"`` - on the crown's outer surface; ``"scape"`` - one flower on each
    leafless stalk above the leaves (a bulb); ``"head"`` - one on each stem tip (the
    ``flower`` archetype). ``cover``: the share of the crown's outer surface in flower at
    full bloom (crown), or of the clump's ground seen from above (scape) - it sets how
    many flowers there are (``plant_forge.accents.blossom_count``). ``radius_cm``: one
    flower's real radius - for a blossom tree, one spur's cluster of flowers. ``cup``:
    how far the petals rise (0 a flat star, ~1 a goblet); ``face_up`` turns the flower
    from straight out of the crown (0) to the sky (1). ``disc_radius`` / ``disc_depth``:
    its centre (stamens, a daisy's eye, a daffodil's trumpet) as shares of ``radius_cm``
    across and along its facing; 0: no visible centre. ``tip_light``: how far a petal's
    tip turns toward the 2D light colour (the sprite's 0.45). ``shade``: a scalar on the
    petal's linear colour, hue kept (as ``WHITE_BARK_SHADE`` keeps white from clipping): a
    bright purple goblet facing the sun went magenta under the filmic curve - a crocus read
    pale lilac, its hue rising from 268 to 280 degrees with its brightness (review 2).
    ``wedge``: one triangle a petal at every LOD - a mass of small flowers (a fruit tree's
    spurs, a forsythia) buys twice the flowers within its triangle budget.
    """

    habit: str = "crown"
    radius_cm: float = 3.0
    petals: int = 5
    double: bool = False
    cup: float = 0.28
    face_up: float = 0.45
    disc_radius: float = 0.26
    disc_depth: float = 0.16
    cover: float = 0.10
    tip_light: float = 0.45
    shade: float = 1.0
    wedge: bool = False


@dataclass(frozen=True, slots=True)
class Traits3D:
    """Complete 3D morphological and phenological traits for one sprite recipe."""

    sprite: SpriteRef
    archetype: str
    palette: str
    crown: CrownTraits
    branching: BranchingTraits
    leaf: LeafTraits
    deciduous: bool
    bloom_months: tuple[int, ...]
    blossom_spec: str | None
    fruit_months: tuple[int, ...]
    harvest_weeks: tuple[int, int] | None
    autumn_palette: str
    #: The plant flowers by its own ``bloom_months``, frost season or not: it stays in
    #: the ground over winter (``_FROST_HARDY_BLOOM_STEMS``). False: its flowers wait
    #: for the plan's frost-free season (``core/phenology.py``), as a tender plant is
    #: planted out after the last frost.
    frost_hardy_bloom: bool = False
    #: How its flowers stand in 3D, or None: no ``flowers`` recipe and no fruit-tree
    #: blossom (``FlowerTraits``; clusters, puffs and umbels have their own builders).
    flower: FlowerTraits | None = None
    #: The share of its leaves a deciduous plant carries while it flowers (#940): below
    #: 1.0 it flowers before or with its leaves (``_PRECOCIOUS_BLOOM_LEAF_DENSITY``), and
    #: ``core/phenology.py`` holds its leaves at this share until the last quarter of the
    #: bloom window, when they unfold. 1.0: flowering does not change its leaves.
    bloom_leaf_density: float = 1.0

    @property
    def evergreen(self) -> bool:
        """True when the plant retains its foliage through winter."""
        return not self.deciduous


def fruit_months_from_harvest_window(
    harvest_start: int | float | None,
    harvest_end: int | float | None,
    last_frost: datetime.date = REFERENCE_LAST_FROST,
) -> tuple[int, ...]:
    """Derive sorted calendar months ``(1..12)`` from frost-relative harvest weeks.

    ``harvest_start`` and ``harvest_end`` are week offsets relative to ``last_frost``
    (matching ``plant_species.json`` and ``task_generator.calendar_windows``). Multi-year
    establishment offsets (``harvest_start >= 52``, e.g. asparagus or rhubarb) are folded
    into the annual cycle while preserving window duration.
    """
    if harvest_start is None or harvest_end is None:
        return ()
    start_w = float(harvest_start)
    end_w = float(harvest_end)
    if end_w < start_w:
        start_w, end_w = end_w, start_w
    duration_w = min(end_w - start_w, 52.0)
    if start_w >= 52.0:
        start_w = start_w % 52.0
        end_w = start_w + duration_w
    start_date = last_frost + datetime.timedelta(weeks=start_w)
    end_date = last_frost + datetime.timedelta(weeks=end_w)
    months: set[int] = {start_date.month, end_date.month}
    cursor = start_date
    while cursor <= end_date:
        months.add(cursor.month)
        cursor += datetime.timedelta(days=5)
    return tuple(sorted(months))


#: Harvest windows ``(harvest_start, harvest_end)`` in weeks relative to last spring frost
#: from ``resources/data/plant_species.json`` for species recipes with harvestable parts.
HARVEST_WINDOWS_WEEKS: Final[dict[str, tuple[int, int]]] = {
    # fruiting vegetables & cucurbits
    "tomato": (10, 20),
    "pepper": (12, 20),
    "eggplant": (14, 20),
    "zucchini": (6, 10),
    "cucumber": (8, 12),
    "pumpkin": (14, 20),
    "squash": (14, 20),
    "bean": (7, 16),
    "pea": (8, 14),
    "corn": (10, 14),
    "okra": (10, 16),
    # roots, tubers & alliums
    "carrot": (10, 16),
    "radish": (3, 5),
    "beet": (8, 12),
    "turnip": (6, 10),
    "potato": (10, 18),
    "onion": (18, 24),
    "garlic": (12, 16),
    "leek": (22, 36),
    # brassicas, heads & leafy greens
    "celery": (16, 22),
    "broccoli": (10, 16),
    "cauliflower": (12, 18),
    "cabbage": (12, 20),
    "kale": (8, 20),
    "spinach": (5, 8),
    "lettuce": (6, 10),
    "arugula": (4, 8),
    "chard": (8, 20),
    "artichoke": (18, 26),
    "asparagus": (2, 8),
    "rhubarb": (4, 12),
    "sunflower": (14, 18),
}

#: Curated Northern-Hemisphere fruiting months for perennial trees and shrubs that carry
#: ``fruit`` in their recipe (perennials in ``plant_species.json`` do not define frost-week
#: sowing/harvest offsets).
_PERENNIAL_FRUIT_MONTHS: Final[dict[str, tuple[int, ...]]] = {
    "apple_tree": (8, 9, 10),
    "pear_tree": (8, 9, 10),
    "plum_tree": (7, 8, 9),
    "peach_tree": (7, 8),
    "cherry_tree": (6, 7),
    "fig_tree": (8, 9, 10),
    "olive_tree": (9, 10, 11),
    "lemon_tree": (1, 2, 3, 10, 11, 12),
    "orange_tree": (1, 2, 11, 12),
    "walnut_tree": (9, 10),
    "holly": (1, 2, 10, 11, 12),
    "barberry": (9, 10, 11),
    "blueberry": (6, 7, 8),
    "raspberry": (6, 7, 8, 9),
    "blackberry": (7, 8, 9),
    "gooseberry": (6, 7, 8),
    "currant": (6, 7, 8),
    "grape_vine": (9, 10),
    "fruit_tree": (8, 9, 10),
}

#: Curated Northern-Hemisphere illustrative bloom months ``(1..12)`` per recipe stem.
_BLOOM_MONTHS: Final[dict[str, tuple[int, ...]]] = {
    # spring-blossoming fruit & ornamental trees
    "apple_tree": (4, 5),
    "pear_tree": (4, 5),
    "plum_tree": (3, 4),
    "peach_tree": (3, 4),
    "cherry_tree": (4, 5),
    "olive_tree": (5, 6),
    "lemon_tree": (4, 5, 6),
    "orange_tree": (4, 5),
    "magnolia": (3, 4, 5),
    "fruit_tree": (4, 5),
    # flowering & berry shrubs
    "forsythia": (3, 4),
    "camellia": (2, 3, 4),
    "rhododendron": (4, 5, 6),
    "lilac": (5, 6),
    "viburnum": (5, 6),
    "spirea": (5, 6, 7),
    "elderberry": (5, 6),
    "privet": (6, 7),
    "barberry": (4, 5),
    "blueberry": (4, 5),
    "raspberry": (5, 6),
    "blackberry": (5, 6),
    "gooseberry": (4, 5),
    "currant": (4, 5),
    "rose": (5, 6, 7, 8, 9),
    "hydrangea": (6, 7, 8, 9),
    "hibiscus": (7, 8, 9),
    # climbers
    "wisteria": (4, 5, 6),
    "clematis": (5, 6, 7, 8),
    "jasmine": (6, 7, 8, 9),
    "climbing_plant": (5, 6, 7, 8),
    # vegetables with blossoms
    "tomato": (5, 6, 7),
    "pepper": (6, 7),
    "eggplant": (6, 7),
    "zucchini": (6, 7, 8),
    "cucumber": (6, 7, 8),
    "pumpkin": (6, 7),
    "squash": (6, 7),
    "bean": (6, 7),
    "pea": (5, 6),
    "potato": (6, 7),
    "okra": (7, 8),
    "corn": (7, 8),
    # herbs with flowers/umbels/clusters
    "rosemary": (4, 5, 6),
    "thyme": (5, 6, 7),
    "sage": (5, 6, 7),
    "cilantro": (6, 7),
    "dill": (6, 7, 8),
    "chives": (5, 6, 7),
    "oregano": (6, 7, 8),
    "chamomile": (5, 6, 7, 8),
    "fennel": (7, 8),
    "marjoram": (6, 7, 8),
    "borage": (5, 6, 7, 8),
    "herb": (5, 6, 7),
    # ornamentals & bulbs
    "crocus": (2, 3, 4),
    "daffodil": (3, 4),
    "tulip": (4, 5),
    "pansy": (3, 4, 5, 6, 9, 10),
    "peony": (5, 6),
    "iris": (5, 6),
    "lily": (6, 7, 8),
    "lavender": (6, 7, 8),
    "geranium": (5, 6, 7, 8, 9),
    "petunia": (5, 6, 7, 8, 9),
    "marigold": (6, 7, 8, 9, 10),
    "zinnia": (6, 7, 8, 9),
    "cosmos": (6, 7, 8, 9, 10),
    "sunflower": (7, 8, 9),
    "dahlia": (7, 8, 9, 10),
    "aster": (8, 9, 10),
    "chrysanthemum": (9, 10, 11),
    "flowering_perennial": (5, 6, 7, 8),
    "ground_cover": (4, 5, 6, 7),
}

#: Blossoming species whose recipe carries ``fruit`` rather than ``flowers`` still have a
#: spring blossom colour in ``recipes.FLOWERS``.
_FRUIT_BLOSSOM_SPEC: Final[dict[str, str]] = {
    "apple_tree": "pink",
    "pear_tree": "white",
    "plum_tree": "white",
    "peach_tree": "pink",
    "cherry_tree": "pink",
    "olive_tree": "cream",
    "lemon_tree": "white",
    "orange_tree": "white",
    "barberry": "yellow",
    "blueberry": "white",
    "raspberry": "white",
    "blackberry": "white",
    "gooseberry": "cream",
    "currant": "cream",
    "fruit_tree": "pink",
}

#: Species that flower by their own bloom months even outside the plan's frost-free
#: season (#940): bulbs, hardy perennials and herbs, shrubs, climbers and fruit trees
#: that stay in the ground over winter. Crocus and daffodil flower before the last
#: frost, apple and magnolia blossom often does, asters and chrysanthemums go on
#: after the first. Every other plant is tender or planted out after the last frost,
#: and its flowers wait for the frost-free season. Species stems only: a category
#: says nothing about a plant's hardiness. No bundled record that draws one of these
#: is ``frost_tolerance: "tender"`` (drift-guarded, ``tests/unit/test_phenology.py``).
_FROST_HARDY_BLOOM_STEMS: Final[frozenset[str]] = frozenset({
    # fruit and ornamental trees
    "apple_tree", "pear_tree", "plum_tree", "peach_tree", "cherry_tree", "olive_tree",
    "magnolia",
    # flowering and berry shrubs
    "forsythia", "camellia", "rhododendron", "lilac", "viburnum", "spirea", "elderberry",
    "privet", "barberry", "blueberry", "raspberry", "blackberry", "gooseberry", "currant",
    "rose", "hydrangea", "hibiscus",
    # woody climbers
    "wisteria", "clematis", "jasmine",
    # bulbs and hardy perennials
    "crocus", "daffodil", "tulip", "pansy", "peony", "iris", "lily", "aster", "chrysanthemum",
    # perennial herbs and the frost-hardy pea
    "lavender", "rosemary", "thyme", "sage", "oregano", "chives", "chamomile", "pea",
})

#: Deciduous plants that flower before or with their leaves, and the share of their
#: leaves out while they flower (#940): magnolia and forsythia flower on bare wood,
#: peach, plum and cherry as their buds break. The share is of leaf AREA: the leaves
#: that have broken by then are a few centimetres long, the model's are full-grown.
#: Apple and pear flower among leaves that are already unfolding, so their spring flush
#: stands as it is.
_PRECOCIOUS_BLOOM_LEAF_DENSITY: Final[dict[str, float]] = {
    "magnolia": 0.08,
    "forsythia": 0.06,
    "peach_tree": 0.10,
    "plum_tree": 0.12,
    "cherry_tree": 0.18,
}

#: One flower's real radius is half its recipe radius: the 2D recipes draw a flower
#: about as many sprite units across as it measures in centimetres (#940).
FLOWER_CM_PER_RECIPE_RADIUS: Final[float] = 0.5

#: The share of a crown's outer surface in flower at full bloom, per archetype (#940).
#: A blossom tree is a cloud of flowers; a shrub or a perennial shows one flower in ten.
_BLOOM_COVER: Final[dict[str, float]] = {
    "canopy": 0.30,
    "mound": 0.10,
    "feathery": 0.10,
    "climber": 0.10,
    "ground": 0.15,
    "rosette": 0.10,
}

#: The blossom of a fruit tree (or a berry shrub) whose recipe draws fruit, not flowers:
#: one spur's cluster of three to five flowers on a tree, single small flowers on a shrub.
_TREE_SPUR_BLOSSOM: Final[FlowerTraits] = FlowerTraits(
    radius_cm=3.5, petals=5, cup=0.35, face_up=0.45, disc_radius=0.0,
    cover=_BLOOM_COVER["canopy"], wedge=True,
)
_SHRUB_SPUR_BLOSSOM: Final[FlowerTraits] = FlowerTraits(
    radius_cm=1.5, petals=5, cup=0.30, face_up=0.45, disc_radius=0.0, cover=0.08, wedge=True,
)
#: A bulb's flowers cover this share of its clump's ground seen from above (#940): five
#: tulips on a clump of 10 cm radius, two crocuses on one of 5 cm.
SCAPE_COVER: Final[float] = 0.45

#: Per-species departures from the habit's flower (#940). Masses of small flowers cover
#: more of a crown (forsythia, spirea, asters), a few big ones less (peony, hibiscus);
#: bulbs hold goblets to the sky, while the daffodil's trumpet and the lily look out
#: sideways; a magnolia's flower is twice its recipe radius (15-25 cm across).
_FLOWER_OVERRIDES: Final[dict[str, dict[str, float | int | bool]]] = {
    "magnolia": {"radius_cm": 8.0, "petals": 6, "cup": 1.0, "face_up": 0.75, "disc_radius": 0.0,
                 "cover": 0.14},
    "olive_tree": {"radius_cm": 1.5, "cover": 0.06},
    "lemon_tree": {"cover": 0.10},
    "orange_tree": {"cover": 0.10},
    "forsythia": {"petals": 4, "cup": 0.2, "face_up": 0.2, "disc_radius": 0.0, "cover": 0.45,
                  "wedge": True},
    "spirea": {"disc_radius": 0.0, "cover": 0.30},
    "rose": {"cup": 0.55, "cover": 0.18},
    "peony": {"cup": 0.6, "cover": 0.06},
    "hibiscus": {"cover": 0.05},
    "dahlia": {"cover": 0.06},
    "aster": {"cup": 0.12, "cover": 0.25},
    "chrysanthemum": {"cover": 0.25},
    "pansy": {"cover": 0.25},
    "petunia": {"cover": 0.20},
    "thyme": {"cover": 0.20},
    "chamomile": {"cover": 0.20},
    "tulip": {"cup": 1.15, "disc_radius": 0.2},
    "crocus": {"cup": 1.0, "tip_light": 0.25, "shade": 0.5},
    "daffodil": {"cup": 0.12, "face_up": 0.15, "disc_radius": 0.34, "disc_depth": 0.55},
    "iris": {"cup": 0.7, "face_up": 0.6},
    "lily": {"cup": 0.45, "face_up": 0.25},
    "sunflower": {"radius_cm": 11.0, "cup": 0.05, "disc_radius": 0.45, "disc_depth": 0.12},
}


def _flower_traits_for(stem: str, recipe: Recipe, archetype: str,
                       blossom_spec: str | None) -> FlowerTraits | None:
    """The 3D flower of a recipe (#940): its ``flowers`` key read as real sizes, or a
    fruit tree's spur blossom; None for clusters, puffs and umbels (their own builders)."""
    flowers = recipe.get("flowers")
    if isinstance(flowers, dict):
        habit = "scape" if archetype == "grass" else "head" if archetype == "flower" else "crown"
        flower = FlowerTraits(
            habit=habit,
            radius_cm=FLOWER_CM_PER_RECIPE_RADIUS * float(flowers.get("radius", 5.0)),
            petals=int(flowers.get("petals", 5)),
            double=bool(flowers.get("double", False)),
            cup=0.8 if habit == "scape" else 0.28,
            face_up={"scape": 1.0, "head": 0.35}.get(habit, 0.45),
            cover=SCAPE_COVER if habit == "scape" else _BLOOM_COVER.get(archetype, 0.10),
        )
    elif stem in _FRUIT_BLOSSOM_SPEC and blossom_spec is not None:
        flower = _TREE_SPUR_BLOSSOM if archetype == "canopy" else _SHRUB_SPUR_BLOSSOM
    else:
        return None
    override = _FLOWER_OVERRIDES.get(stem)
    return replace(flower, **override) if override else flower  # type: ignore[arg-type]


#: Evergreen recipes (never shed leaves in winter).
_EVERGREEN_STEMS: Final[frozenset[str]] = frozenset({
    # conifers, palms & bamboo
    "pine",
    "spruce",
    "juniper",
    "conifer",
    "palm",
    "bamboo",
    # evergreen trees
    "olive_tree",
    "lemon_tree",
    "orange_tree",
    # evergreen shrubs, hedges & woody Mediterranean herbs
    "boxwood",
    "holly",
    "camellia",
    "rhododendron",
    "bay_laurel",
    "rosemary",
    "lavender",
    "thyme",
    "sage",
    "compact_shrub",
    "hedge_section",
    "ground_cover",
})

#: Woody deciduous stems (shed leaves in winter; turn autumn colours in fall).
_DECIDUOUS_WOODY_STEMS: Final[frozenset[str]] = frozenset({
    # deciduous trees
    "apple_tree",
    "pear_tree",
    "plum_tree",
    "peach_tree",
    "cherry_tree",
    "fig_tree",
    "walnut_tree",
    "oak",
    "maple",
    "birch",
    "willow",
    "magnolia",
    "japanese_maple",
    "round_deciduous",
    "columnar_tree",
    "weeping_tree",
    "fruit_tree",
    # deciduous shrubs & woody climbers
    "privet",
    "forsythia",
    "lilac",
    "viburnum",
    "barberry",
    "spirea",
    "elderberry",
    "blueberry",
    "raspberry",
    "blackberry",
    "gooseberry",
    "currant",
    "rose",
    "hydrangea",
    "hibiscus",
    "spreading_shrub",
    "jasmine",
    "clematis",
    "wisteria",
    "grape_vine",
    "climbing_plant",
})

#: Per-species crown & branching overrides for canopy and conifer trees.
#: Preserves the dendrological habits measured in the L0 spike and L1.7.
_TREE_OVERRIDES: Final[dict[str, tuple[CrownTraits, BranchingTraits, str, str]]] = {
    # stem: (CrownTraits, BranchingTraits, leaf_shape, autumn_palette)
    "apple_tree": (
        CrownTraits("spreading", trunk_share=0.20, taper=0.15, droop=0.45, aspect_xy=1.05),
        BranchingTraits(520, 2.5, 0.020, 0.08, 0.12, BARK_WALNUT, 1.0),
        "ovate",
        "autumn",
    ),
    "pear_tree": (
        CrownTraits("pyramidal", trunk_share=0.24, taper=0.70, droop=0.10, aspect_xy=0.88),
        BranchingTraits(520, 2.5, 0.018, 0.24, 0.06, BARK_WALNUT_DARK, 1.0),
        "ovate",
        "redleaf",
    ),
    "plum_tree": (
        CrownTraits("round", trunk_share=0.28, taper=0.05, droop=0.25, aspect_xy=1.0),
        BranchingTraits(500, 2.5, 0.018, 0.12, 0.09, BARK_WALNUT_DARK, 1.0),
        "ovate",
        "yellow",
    ),
    "peach_tree": (
        CrownTraits("spreading", trunk_share=0.22, taper=-0.10, droop=0.30, aspect_xy=1.04),
        BranchingTraits(480, 2.5, 0.017, 0.10, 0.10, BARK_TEAK, 1.0),
        "diamond",
        "autumn",
    ),
    "cherry_tree": (
        CrownTraits("oval", trunk_share=0.30, taper=0.10, droop=0.15, aspect_xy=1.0),
        BranchingTraits(520, 2.5, 0.019, 0.14, 0.08, BARK_TEAK, 1.0),
        "ovate",
        "autumn",
    ),
    "fig_tree": (
        CrownTraits("spreading", trunk_share=0.18, taper=-0.20, droop=0.20, aspect_xy=1.08),
        BranchingTraits(460, 2.4, 0.022, 0.06, 0.13, BARK_GREY, 1.0),
        "lobed",
        "yellow",
    ),
    "olive_tree": (
        CrownTraits("spreading", trunk_share=0.26, taper=-0.12, droop=0.22, aspect_xy=1.05),
        BranchingTraits(500, 2.4, 0.024, 0.05, 0.15, BARK_SHINGLE, 1.0),
        "diamond",
        "silver",
    ),
    "lemon_tree": (
        CrownTraits("round", trunk_share=0.22, taper=0.05, droop=0.18, aspect_xy=1.0),
        BranchingTraits(480, 2.5, 0.017, 0.12, 0.08, BARK_GREY, 1.0),
        "ovate",
        "dark",
    ),
    "orange_tree": (
        CrownTraits("round", trunk_share=0.24, taper=0.0, droop=0.15, aspect_xy=1.0),
        BranchingTraits(500, 2.5, 0.018, 0.12, 0.07, BARK_GREY, 1.0),
        "ovate",
        "dark",
    ),
    "walnut_tree": (
        CrownTraits("spreading", trunk_share=0.40, taper=-0.20, droop=0.15, aspect_xy=1.06),
        BranchingTraits(540, 2.5, 0.022, 0.10, 0.10, BARK_SHINGLE, 1.0),
        "pinnate",
        "yellow",
    ),
    "oak": (
        CrownTraits("spreading", trunk_share=0.32, taper=-0.10, droop=0.12, aspect_xy=1.08),
        BranchingTraits(560, 2.5, 0.024, 0.08, 0.14, BARK_WALNUT_DARK, 1.0),
        "lobed",
        "autumn",
    ),
    "maple": (
        CrownTraits("oval", trunk_share=0.30, taper=-0.15, droop=0.15, aspect_xy=1.02),
        BranchingTraits(540, 2.5, 0.020, 0.14, 0.08, BARK_GREY, 1.0),
        "lobed",
        "redleaf",
    ),
    "birch": (
        CrownTraits("oval", trunk_share=0.20, taper=0.25, droop=0.65, aspect_xy=0.88),
        BranchingTraits(500, 2.5, 0.014, 0.20, 0.06, BARK_BIRCH, WHITE_BARK_SHADE),
        "diamond",
        "yellow",
    ),
    "willow": (
        CrownTraits("weeping", trunk_share=0.22, taper=0.18, droop=0.82, aspect_xy=1.06),
        BranchingTraits(540, 2.5, 0.021, -0.08, 0.11, BARK_OAK, 1.0),
        "strap",
        "yellow",
    ),
    "magnolia": (
        CrownTraits("vase", trunk_share=0.12, taper=-0.45, droop=0.05, aspect_xy=1.04),
        BranchingTraits(480, 2.5, 0.018, 0.16, 0.09, BARK_SHINGLE, 1.0),
        "ovate",
        "autumn",
    ),
    # #940: low-branched and layered, as wide as tall; twisting limbs, fine lobed
    # leaves. Its summer palette is already red (the red-leaved garden forms), so its
    # autumn palette is the same one: the season tint warms it, never muddies it.
    "japanese_maple": (
        CrownTraits("spreading", trunk_share=0.14, taper=-0.20, droop=0.30, aspect_xy=1.06),
        BranchingTraits(500, 2.4, 0.016, 0.06, 0.13, BARK_GREY, 1.0),
        "lobed",
        "redleaf",
    ),
    "round_deciduous": (
        CrownTraits("round", trunk_share=0.30, taper=0.0, droop=0.15, aspect_xy=1.0),
        BranchingTraits(520, 2.5, 0.018, 0.12, 0.08, BARK_WALNUT, 1.0),
        "ovate",
        "autumn",
    ),
    "columnar_tree": (
        CrownTraits("columnar", trunk_share=0.16, taper=0.35, droop=0.08, aspect_xy=0.72),
        BranchingTraits(500, 2.5, 0.016, 0.32, 0.05, BARK_GREY, 1.0),
        "ovate",
        "yellow",
    ),
    "weeping_tree": (
        CrownTraits("weeping", trunk_share=0.22, taper=0.18, droop=0.80, aspect_xy=1.05),
        BranchingTraits(520, 2.5, 0.020, -0.06, 0.10, BARK_OAK, 1.0),
        "strap",
        "yellow",
    ),
    "fruit_tree": (
        CrownTraits("spreading", trunk_share=0.22, taper=0.12, droop=0.38, aspect_xy=1.04),
        BranchingTraits(520, 2.5, 0.019, 0.10, 0.10, BARK_WALNUT, 1.0),
        "ovate",
        "autumn",
    ),
}


#: Grass recipes that are a clump of woody culms, not a tuft of basal blades (#940).
#: Their crown is a ``vase`` — what ``plant_forge.herbaceous.build_forged_grass``
#: builds as culms with leaf sprays: the lowest fifth of each culm bare, arching over
#: at the top under its leaves.
_CULM_CLUMP_STEMS: Final[frozenset[str]] = frozenset({"bamboo"})
_CULM_CLUMP_CROWN: Final[CrownTraits] = CrownTraits(
    "vase", trunk_share=0.20, taper=-0.30, droop=0.45, aspect_xy=1.0,
)


def _blossom_spec_for(stem: str, recipe: Recipe) -> str | None:
    flowers = recipe.get("flowers")
    if isinstance(flowers, dict) and isinstance(flowers.get("spec"), str):
        return str(flowers["spec"])
    if "clusters" in recipe or "puffs" in recipe:
        if stem in ("lilac", "wisteria", "lavender", "chives"):
            return "lilac"
        if stem == "hydrangea":
            return "blue"
        if stem == "rhododendron":
            return "pink"
        if stem == "geranium":
            return "red"
        return "white"
    if "umbels" in recipe:
        return "yellow" if stem in ("dill", "fennel", "corn") else "cream"
    return _FRUIT_BLOSSOM_SPEC.get(stem)


def _build_traits(group: str, stem: str, recipe: Recipe) -> Traits3D:
    ref = SpriteRef(group, stem)
    archetype = str(recipe["a"])
    pal = palette_key(recipe)
    leaf_scale = float(recipe.get("leaf_scale", 1.0))
    frilly = bool(recipe.get("frilly", False))
    narrow = bool(recipe.get("narrow", False))
    deciduous = stem in _DECIDUOUS_WOODY_STEMS and stem not in _EVERGREEN_STEMS

    harvest_weeks = HARVEST_WINDOWS_WEEKS.get(stem)
    if harvest_weeks is not None and any(k in recipe for k in ("fruit", "fruit2", "pods", "bulb", "head")):
        fruit_months = fruit_months_from_harvest_window(harvest_weeks[0], harvest_weeks[1])
    elif stem in _PERENNIAL_FRUIT_MONTHS:
        fruit_months = _PERENNIAL_FRUIT_MONTHS[stem]
    else:
        fruit_months = ()

    bloom_months = _BLOOM_MONTHS.get(stem, ())
    blossom_spec = _blossom_spec_for(stem, recipe)

    if stem in _TREE_OVERRIDES:
        crown, branching, leaf_shape, autumn_pal = _TREE_OVERRIDES[stem]
        width_ratio = 0.28 if leaf_shape == "strap" else (0.72 if leaf_shape == "lobed" else 0.60)
        leaf = LeafTraits(
            shape=leaf_shape,
            length_cm=round(13.0 * leaf_scale, 2),
            width_ratio=width_ratio,
            leaf_scale=leaf_scale,
            frilly=frilly,
            narrow=narrow,
        )
        return Traits3D(
            sprite=ref,
            archetype=archetype,
            palette=pal,
            crown=crown,
            branching=branching,
            leaf=leaf,
            deciduous=deciduous,
            bloom_months=bloom_months,
            blossom_spec=blossom_spec,
            fruit_months=fruit_months,
            harvest_weeks=harvest_weeks,
            autumn_palette=autumn_pal if deciduous else pal,
        )

    if archetype == "conifer":
        is_pine = stem == "pine"
        is_juniper = stem == "juniper"
        crown = CrownTraits(
            shape="tiered" if not is_juniper else "conical",
            trunk_share=0.22 if is_pine else (0.08 if is_juniper else 0.12),
            taper=0.65 if is_pine else 0.82,
            droop=0.28 if is_pine else 0.48,
            aspect_xy=1.0,
        )
        branching = BranchingTraits(220, 2.4, 0.020, 0.25, 0.05, BARK_PINE, 1.0)
        leaf = LeafTraits("needle", round(14.0 * leaf_scale, 2), 0.35, leaf_scale, frilly, narrow)
        return Traits3D(
            ref, archetype, pal, crown, branching, leaf, False,
            bloom_months, blossom_spec, fruit_months, harvest_weeks, pal,
        )

    if archetype == "palm":
        crown = CrownTraits("fan", trunk_share=0.62, taper=-0.35, droop=0.55, aspect_xy=1.0)
        branching = BranchingTraits(32, 2.2, 0.028, 0.35, 0.04, BARK_TEAK, 1.0)
        leaf = LeafTraits("frond", round(42.0 * leaf_scale, 2), 0.26, leaf_scale, frilly, narrow)
        return Traits3D(
            ref, archetype, pal, crown, branching, leaf, False,
            bloom_months, blossom_spec, fruit_months, harvest_weeks, pal,
        )

    if archetype == "hedge":
        crown = CrownTraits("flat", trunk_share=0.0, taper=0.04, droop=0.10, aspect_xy=1.0)
        branching = BranchingTraits(140, 2.4, 0.012, 0.15, 0.06, BARK_WALNUT_DARK, 1.0)
        leaf = LeafTraits("ovate", 6.5, 0.62, leaf_scale, frilly, narrow)
        return Traits3D(
            ref, archetype, pal, crown, branching, leaf, False,
            bloom_months, blossom_spec, fruit_months, harvest_weeks, pal,
        )

    if archetype == "climber":
        crown = CrownTraits("upright", trunk_share=0.04, taper=0.0, droop=0.25, aspect_xy=0.75)
        branching = BranchingTraits(180, 2.3, 0.010, 0.28, 0.12, BARK_OAK if deciduous else BARK_STEM, 1.0)
        leaf = LeafTraits(
            "cordate" if frilly else "ovate",
            round(8.5 * leaf_scale, 2),
            0.65,
            leaf_scale,
            frilly,
            narrow,
        )
        autumn_pal = "autumn" if deciduous else pal
        return Traits3D(
            ref, archetype, pal, crown, branching, leaf, deciduous,
            bloom_months, blossom_spec, fruit_months, harvest_weeks, autumn_pal,
        )

    if archetype in ("rosette", "head"):
        crown = CrownTraits("mound", trunk_share=0.0, taper=0.10, droop=-0.10, aspect_xy=1.0)
        branching = BranchingTraits(0, 2.2, 0.010, 0.20, 0.03, BARK_STEM, 1.0)
        leaf = LeafTraits(
            "cupped" if recipe.get("heart", True) else "lobed" if frilly else "ovate",
            round(10.0 * leaf_scale, 2),
            0.74,
            leaf_scale,
            frilly,
            narrow,
        )
        return Traits3D(
            ref, archetype, pal, crown, branching, leaf, False,
            bloom_months, blossom_spec, fruit_months, harvest_weeks, pal,
        )

    if archetype in ("grass", "allium"):
        crown = (_CULM_CLUMP_CROWN if stem in _CULM_CLUMP_STEMS
                 else CrownTraits("upright", trunk_share=0.0, taper=-0.20, droop=0.35, aspect_xy=1.0))
        branching = BranchingTraits(0, 2.2, 0.010, 0.35, 0.03, BARK_STEM, 1.0)
        leaf = LeafTraits("strap", round(18.0 * leaf_scale, 2), 0.18, leaf_scale, frilly, narrow)
        return Traits3D(
            ref, archetype, pal, crown, branching, leaf, False,
            bloom_months, blossom_spec, fruit_months, harvest_weeks, pal,
        )

    if archetype == "feathery":
        crown = CrownTraits("mound", trunk_share=0.04, taper=-0.10, droop=0.28, aspect_xy=1.0)
        branching = BranchingTraits(64, 2.2, 0.010, 0.22, 0.06, BARK_STEM, 1.0)
        leaf = LeafTraits("pinnate", round(11.0 * leaf_scale, 2), 0.38, leaf_scale, frilly, narrow)
        return Traits3D(
            ref, archetype, pal, crown, branching, leaf, False,
            bloom_months, blossom_spec, fruit_months, harvest_weeks, pal,
        )

    if archetype == "flower":
        crown = CrownTraits("upright", trunk_share=0.12, taper=0.15, droop=0.18, aspect_xy=1.0)
        branching = BranchingTraits(24, 2.3, 0.016, 0.38, 0.04, BARK_STEM, 1.0)
        leaf = LeafTraits("cordate", round(14.0 * leaf_scale, 2), 0.72, leaf_scale, frilly, narrow)
        return Traits3D(
            ref, archetype, pal, crown, branching, leaf, False,
            bloom_months, blossom_spec, fruit_months, harvest_weeks, pal,
        )

    if archetype == "ground":
        crown = CrownTraits("flat", trunk_share=0.0, taper=0.25, droop=0.08, aspect_xy=1.08)
        branching = BranchingTraits(48, 2.2, 0.008, 0.04, 0.10, BARK_STEM, 1.0)
        leaf = LeafTraits("ovate", round(4.5 * leaf_scale, 2), 0.68, leaf_scale, frilly, narrow)
        return Traits3D(
            ref, archetype, pal, crown, branching, leaf, False,
            bloom_months, blossom_spec, fruit_months, harvest_weeks, pal,
        )

    # archetype == "mound" (shrubs, herbs, bushy vegetables & perennials)
    is_woody_shrub = deciduous or stem in ("boxwood", "holly", "camellia", "rhododendron", "bay_laurel", "compact_shrub")
    crown = CrownTraits(
        shape="mound" if not narrow else "upright",
        trunk_share=0.08 if is_woody_shrub else 0.04,
        taper=-0.08 if is_woody_shrub else 0.05,
        droop=0.18 if not narrow else 0.08,
        aspect_xy=1.0,
    )
    branching = BranchingTraits(
        attractors=180 if is_woody_shrub else 90,
        pipe_exponent=2.4,
        trunk_base_ratio=0.014 if is_woody_shrub else 0.010,
        apical_bias=0.14,
        gnarl=0.10,
        bark_color=BARK_WALNUT if is_woody_shrub else BARK_STEM,
        bark_shade=1.0,
    )
    leaf = LeafTraits(
        shape="strap" if narrow else ("lobed" if frilly else "ovate"),
        length_cm=round(7.5 * leaf_scale, 2),
        width_ratio=0.30 if narrow else (0.72 if frilly else 0.60),
        leaf_scale=leaf_scale,
        frilly=frilly,
        narrow=narrow,
    )
    autumn_pal = (
        "redleaf"
        if stem in ("blueberry", "viburnum", "barberry", "currant")
        else ("autumn" if deciduous else pal)
    )
    return Traits3D(
        ref, archetype, pal, crown, branching, leaf, deciduous,
        bloom_months, blossom_spec, fruit_months, harvest_weeks, autumn_pal,
    )


def _with_flowering(traits: Traits3D, stem: str, recipe: Recipe) -> Traits3D:
    """``traits`` with how it flowers in 3D (#940): its flower and its leaves in bloom."""
    return replace(
        traits,
        flower=_flower_traits_for(stem, recipe, traits.archetype, traits.blossom_spec),
        bloom_leaf_density=(_PRECOCIOUS_BLOOM_LEAF_DENSITY.get(stem, 1.0)
                            if traits.deciduous else 1.0),
    )


def _species_traits(stem: str, recipe: Recipe) -> Traits3D:
    traits = _with_flowering(_build_traits(GROUP_SPECIES, stem, recipe), stem, recipe)
    return replace(traits, frost_hardy_bloom=True) if stem in _FROST_HARDY_BLOOM_STEMS else traits


#: 3D traits for every species recipe (111).
SPECIES_TRAITS: Final[dict[str, Traits3D]] = {
    stem: _species_traits(stem, recipe) for stem, recipe in SPECIES.items()
}

#: 3D traits for every category recipe (15).
CATEGORY_TRAITS: Final[dict[str, Traits3D]] = {
    stem: _with_flowering(_build_traits(GROUP_CATEGORIES, stem, recipe), stem, recipe)
    for stem, recipe in CATEGORIES.items()
}


def traits_for(sprite: SpriteRef) -> Traits3D:
    """Return the ``Traits3D`` for ``sprite``, or raise ``KeyError``."""
    if sprite.group == GROUP_SPECIES:
        return SPECIES_TRAITS[sprite.name]
    if sprite.group == GROUP_CATEGORIES:
        return CATEGORY_TRAITS[sprite.name]
    raise KeyError(sprite)


def resolve_traits(
    kind: str,
    species: str | None = None,
    category: str | None = None,
) -> Traits3D | None:
    """Resolve ``(kind, species, category)`` through ``resolve_sprite`` to its ``Traits3D``."""
    sprite = resolve_sprite(kind, species or "", category)
    return None if sprite is None else traits_for(sprite)


__all__ = [
    "BARK_BIRCH",
    "BARK_COLORS",
    "BARK_GREY",
    "BARK_OAK",
    "BARK_PINE",
    "BARK_SHINGLE",
    "BARK_STEM",
    "BARK_TEAK",
    "BARK_WALNUT",
    "BARK_WALNUT_DARK",
    "CATEGORY_TRAITS",
    "CROWN_SHAPES",
    "FLOWER_CM_PER_RECIPE_RADIUS",
    "FLOWER_HABITS",
    "SCAPE_COVER",
    "FlowerTraits",
    "HARVEST_WINDOWS_WEEKS",
    "LEAF_SHAPES",
    "REFERENCE_LAST_FROST",
    "SPECIES_TRAITS",
    "WHITE_BARK_SHADE",
    "BranchingTraits",
    "CrownTraits",
    "LeafTraits",
    "Traits3D",
    "fruit_months_from_harvest_window",
    "resolve_traits",
    "traits_for",
]
