"""The plant recipe tables — one source for the 2D sprites and the 3D plants.

Every plant the app draws is a RECIPE: an archetype (``a="canopy"``, ``"mound"``,
``"rosette"`` …), a palette (``pal="fresh"``) and a few per-species numbers and
features. Until Phase 17 L1.7 (#385) these tables lived in
``scripts/generate_plant_sprites.py`` and the 3D spike kept a copy of the
palettes. Now there is one home:

- ``scripts/generate_plant_sprites.py`` imports the tables and draws the 123 SVGs
  from them (its output is byte-identical to before the move; pinned by
  ``tests/unit/test_plant_sprite_conformance.py``);
- ``core/scene3d/builders/plants.py`` reads the SAME recipe to build a plant's
  3D silhouette, so a species' archetype and colours cannot differ between the
  plan and the 3D view.

``PALETTES``, ``FRUITS``, ``FLOWERS``, ``SPECIES`` and ``CATEGORIES`` below were
moved verbatim, in their original order — order matters: the generator seeds each
sprite from its name, and the tables' order is the order files are written in.

The module is data plus two one-line rules, standard library only (pinned by an
AST scan, ``tests/unit/test_plant_art.py``). That is a rule about THIS FILE's
imports, and it is what lets the sprite generator — a script that needs no Qt —
execute the file by its path. It is not a promise about importing it by name:
``import open_garden_planner.core.plant_art.recipes`` first runs
``open_garden_planner/core/__init__.py``, which loads PyQt6 for other ``core``
modules. The Qt-free 3D builders import it by name (the app has Qt anyway); the
generator must not, and a test runs it with PyQt6 blocked. Style contract and
the meaning of every recipe key:
``resources/plants/README.md`` and §8.22 of the crosscutting concepts.

To change a plant: edit its recipe here, run the generator, commit both.
"""

# ruff: noqa: C408 - dict() keyword style is deliberate: the 123-entry recipe
# tables read far better as dict(a=..., pal=...) than as quoted-key literals.

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, TypeAlias

#: One recipe. ``a`` (the archetype) is the only key every recipe has; the sprite
#: generator refuses a key it does not know (``_KNOWN_KEYS`` there).
Recipe: TypeAlias = dict[str, Any]

#: A palette's anchors, in the order ``pal()`` takes them: leaf tip outer → inner,
#: leaf base outer → inner, the occlusion under a leaf, the leaf rib.
PALETTE_ANCHORS: Final = ("t0", "t1", "b0", "b1", "occ", "rib")
#: The palette of a recipe that names none.
DEFAULT_PALETTE: Final = "fresh"
#: The hedge sprite's palette. ``hedge_section`` is the one recipe without a
#: ``pal`` key: its sprite is drawn by ``build_hedge``, which reads no recipe.
HEDGE_PALETTE: Final = "dark"


# palette = leaf-ring color anchors: tip outer->inner, base outer->inner + occlusion + rib
def pal(t0: str, t1: str, b0: str, b1: str, occ: str, rib: str) -> dict[str, str]:
    return {"t0": t0, "t1": t1, "b0": b0, "b1": b1, "occ": occ, "rib": rib}


PALETTES: dict[str, dict[str, str]] = {
    # approved in the #281 style lab
    "fresh": pal("#54ab4b", "#b7f094", "#1b5a2e", "#4aa557", "#0f3d22", "#1c5230"),
    "crisp": pal("#5cb63e", "#a8e678", "#276e1d", "#55a53a", "#143f10", "#2c6e1e"),
    "silver": pal("#93b287", "#c7dabc", "#42603c", "#66875e", "#26381f", "#3f5b39"),
    # supporting families
    "dark": pal("#3d8f45", "#8fd07a", "#12452a", "#2f7f42", "#092e18", "#144a2c"),
    "teal": pal("#4f9070", "#a8d8b8", "#1d4a38", "#3c7a5c", "#0f2e21", "#1e5240"),
    "yellow": pal("#7dbb45", "#d6ef9a", "#3f7423", "#6aa63d", "#23480f", "#33641c"),
    "olive": pal("#7d9c4a", "#c3d795", "#46601f", "#6d8a3a", "#2a3c11", "#3e5519"),
    "redleaf": pal("#a04a52", "#d99aa0", "#5c1f28", "#8a3a44", "#3a1016", "#5c1f28"),
    "autumn": pal("#b3703c", "#e8b06a", "#6b3318", "#96562a", "#401c0a", "#6b3318"),
}

# fruit / berry gradient triads: (highlight, mid, dark)
FRUITS: dict[str, tuple[str, str, str]] = {
    "apple": ("#ff8a63", "#e33f28", "#941106"),
    "cherry": ("#ff7a6e", "#d92c3a", "#8a0f1f"),
    "plum": ("#9d8fdd", "#6a55b8", "#3b2f78"),
    "peach": ("#ffc08a", "#f08a4a", "#b35418"),
    "pear": ("#e4e08a", "#c3cf56", "#8a9a2e"),
    "lemon": ("#fff2a0", "#f2d549", "#c9a422"),
    "orange": ("#ffc069", "#f2952e", "#c26a10"),
    "olive": ("#7a8a52", "#4a5630", "#2a3418"),
    "fig": ("#8a6a9d", "#5c3f78", "#33204a"),
    "nut": ("#c9d47a", "#a3b34e", "#6b7a2a"),
    "blueberry": ("#8fa4e0", "#5468b8", "#2c3a78"),
    "blackberry": ("#7a6a94", "#443a5e", "#201a30"),
    "gooseberry": ("#d8e89a", "#a8c860", "#6e8a34"),
    "tomato": ("#ff8a63", "#e8402a", "#9c1608"),
    "green": ("#b8d878", "#7aa843", "#476b22"),
    "eggplant": ("#7a5bb5", "#4a2f80", "#291452"),
    "pumpkin": ("#ffb35c", "#ef8324", "#b3540c"),
    "butternut": ("#f0d09a", "#d4a860", "#9a7232"),
}

# flower petal specs: (petal_outer, petal_tip_light, center)
FLOWERS: dict[str, tuple[str, str, str]] = {
    "white": ("#e8e4d8", "#fbf9f2", "#e8c34a"),
    "pink": ("#e88aa8", "#f7c3d3", "#e8c34a"),
    "rose_red": ("#c9384f", "#ef7f92", "#8a1c30"),
    "magenta": ("#c04a94", "#e894c4", "#f0d060"),
    "purple": ("#8a5fc0", "#c3a3e8", "#f0d060"),
    "violet_face": ("#6a4aa8", "#9a7fd0", "#f2cf4e"),
    "blue": ("#5c7fd0", "#a3b8ec", "#f0d060"),
    "yellow": ("#f2c53a", "#fae48a", "#c98a1e"),
    "gold": ("#f0a832", "#f8cf6e", "#a86414"),
    "orange": ("#ef8330", "#f8b878", "#b3540c"),
    "red": ("#d8402e", "#f28a70", "#8a1608"),
    "cream": ("#f2ecd0", "#fbf8ea", "#d8b84a"),
    "lilac": ("#a98fe0", "#d0c0f0", "#6b46ab"),
}


# --------------------------------------------------------------------------- #
# species table — one compact recipe per species (108)
# --------------------------------------------------------------------------- #
SPECIES: dict[str, Recipe] = {
    # trees
    "apple_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="apple", n=4)),
    "pear_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="pear", n=4)),
    "plum_tree": dict(a="canopy", pal="dark", fruit=dict(kind="plum", n=4, size=(2.8, 3.5))),
    "peach_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="peach", n=4)),
    "cherry_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="cherry", n=5, size=(2.2, 2.8))),
    "fig_tree": dict(a="canopy", pal="dark", leaf_scale=1.25, n_out=12, frilly=True,
                     fruit=dict(kind="fig", n=3, size=(3.0, 3.8), per=(1, 2))),
    "olive_tree": dict(a="canopy", pal="silver", leaf_scale=0.8, n_out=22,
                       fruit=dict(kind="olive", scatter=True, n=8, size=(1.6, 2.1))),
    "lemon_tree": dict(a="canopy", pal="dark", fruit=dict(kind="lemon", n=4, size=(3.0, 3.8))),
    "orange_tree": dict(a="canopy", pal="dark", fruit=dict(kind="orange", n=4, size=(3.2, 4.0))),
    "walnut_tree": dict(a="canopy", pal="fresh", leaf_scale=1.1,
                        fruit=dict(kind="nut", scatter=True, n=6, size=(2.2, 2.8), occ="#2a3311")),
    "oak": dict(a="canopy", pal="dark", frilly=True, leaf_scale=1.15, n_out=14),
    "maple": dict(a="canopy", pal="autumn", leaf_scale=1.1, n_out=15, frilly=True),
    "birch": dict(a="canopy", pal="yellow", leaf_scale=0.75, n_out=20),
    "willow": dict(a="canopy", pal="silver", leaf_scale=0.9, n_out=24),
    "magnolia": dict(a="canopy", pal="fresh", leaf_scale=1.1, n_out=14,
                     flowers=dict(spec="pink", petals=9, radius=8.0, n=5)),
    "pine": dict(a="conifer", pal="dark"),
    "spruce": dict(a="conifer", pal="teal", r=45),
    # shrubs
    "boxwood": dict(a="mound", pal="dark", leaf_scale=0.7, n_out=20),
    "rhododendron": dict(a="mound", pal="dark",
                         clusters=dict(radius=8.5, dark="#b3487f", light="#eeb3d3",
                                       occ="#6b1f4a", n=5)),
    "holly": dict(a="mound", pal="dark", frilly=True, leaf_scale=0.95,
                  fruit=dict(kind="cherry", n=4, size=(1.8, 2.3), per=(2, 4))),
    "privet": dict(a="mound", pal="dark", leaf_scale=0.8, n_out=18,
                   umbels=dict(col="#f2ecd0", light="#fbf8ea", n=3, radius=4.0)),
    "juniper": dict(a="conifer", pal="teal", r=40),
    "forsythia": dict(a="mound", pal="yellow",
                      flowers=dict(spec="yellow", petals=4, radius=4.4, n=11, zone=(6, 30))),
    "lilac": dict(a="mound", pal="fresh",
                  clusters=dict(radius=8.0, dark="#8a68c0", light="#d0c0f0",
                                occ="#4a2f80", n=5)),
    "viburnum": dict(a="mound", pal="dark",
                     clusters=dict(radius=7.5, dark="#d8d4c0", light="#fbf9f0",
                                   occ="#6b6a50", n=5)),
    "barberry": dict(a="mound", pal="redleaf", shadow_col="#2a0d10",
                     fruit=dict(kind="cherry", scatter=True, n=8, size=(1.4, 1.9))),
    "camellia": dict(a="mound", pal="dark",
                     flowers=dict(spec="pink", petals=8, radius=7.0, n=5, double=True)),
    "spirea": dict(a="mound", pal="fresh",
                   flowers=dict(spec="white", petals=5, radius=3.0, n=11, zone=(8, 30))),
    "elderberry": dict(a="mound", pal="dark",
                       umbels=dict(col="#f2ecd0", light="#fbf8ea", n=5, radius=6.0)),
    "blueberry": dict(a="mound", pal="teal",
                      fruit=dict(kind="blueberry", scatter=True, n=12, size=(1.7, 2.3))),
    "raspberry": dict(a="mound", pal="fresh", frilly=True,
                      fruit=dict(kind="cherry", scatter=True, n=10, size=(2.0, 2.6))),
    "blackberry": dict(a="mound", pal="dark",
                       fruit=dict(kind="blackberry", scatter=True, n=11, size=(1.9, 2.6))),
    "gooseberry": dict(a="mound", pal="fresh",
                       fruit=dict(kind="gooseberry", scatter=True, n=9, size=(2.0, 2.6),
                                  occ="#2a3a10")),
    "currant": dict(a="mound", pal="fresh",
                    fruit=dict(kind="cherry", scatter=True, n=13, size=(1.5, 2.0))),
    "rose": dict(a="mound", pal="dark",
                 flowers=dict(spec="rose_red", petals=9, radius=6.5, n=5, double=True)),
    "hydrangea": dict(a="mound", pal="fresh",
                      clusters=dict(radius=9.0, dark="#5c7fd0", light="#c3d0f0",
                                    occ="#2a3a78", n=5)),
    "hibiscus": dict(a="mound", pal="dark",
                     flowers=dict(spec="red", petals=5, radius=8.5, n=4)),
    "jasmine": dict(a="climber", pal="dark",
                    flowers=dict(spec="white", petals=5, radius=4.0, n=9)),
    "clematis": dict(a="climber", pal="fresh",
                     flowers=dict(spec="purple", petals=6, radius=7.5, n=5)),
    "wisteria": dict(a="climber", pal="fresh",
                     clusters=dict(radius=6.5, dark="#8a68c0", light="#d0c0f0",
                                   occ="#4a2f80", n=7, zone=(10, 28))),
    # vegetables
    "tomato": dict(a="mound", pal="fresh", fruit=dict(kind="tomato", n=4, size=(3.4, 4.3)),
                   fruit2=dict(kind="green", n=3, size=(2.2, 2.8))),
    "pepper": dict(a="mound", pal="fresh", fruit=dict(kind="tomato", n=3, size=(3.4, 4.2)),
                   fruit2=dict(kind="lemon", n=3, size=(2.6, 3.2))),
    "eggplant": dict(a="mound", pal="dark",
                     fruit=dict(kind="eggplant", n=3, size=(3.6, 4.6), per=(1, 2))),
    "zucchini": dict(a="mound", pal="crisp", frilly=True, leaf_scale=1.3, n_out=10,
                     pods=dict(n=4, dark="#1f5c14", light="#5ca438", length=10.0),
                     flowers=dict(spec="yellow", petals=5, radius=4.0, n=2)),
    "cucumber": dict(a="climber", pal="crisp", frilly=True,
                     pods=dict(n=6, dark="#3f8226", light="#9fdf6f", length=9.0),
                     flowers=dict(spec="yellow", petals=5, radius=3.2, n=3)),
    "pumpkin": dict(a="mound", pal="fresh", frilly=True, leaf_scale=1.35, n_out=10,
                    fruit=dict(kind="pumpkin", n=2, size=(6.0, 8.0), per=(1, 1),
                               zone=(12, 20))),
    "squash": dict(a="mound", pal="fresh", frilly=True, leaf_scale=1.3, n_out=10,
                   fruit=dict(kind="butternut", n=2, size=(4.5, 6.0), per=(1, 2),
                              zone=(12, 20))),
    "bean": dict(a="climber", pal="fresh", pods=dict(n=9, dark="#3f8226", light="#9fdf6f")),
    "pea": dict(a="climber", pal="crisp", pods=dict(n=8, dark="#3f8226", light="#9fdf6f"),
                flowers=dict(spec="white", petals=5, radius=3.6, n=3)),
    "corn": dict(a="allium", pal="yellow", n_out=14, leaf_scale=1.3,
                 umbels=dict(n=1, zone=(0, 2), radius=6.5, col="#f0cf5a", light="#fae89a")),
    "carrot": dict(a="feathery", pal="crisp",
                   bulb=dict(radius=6.0, triad=("#f2a950", "#e07f28", "#a04f0e"))),
    "radish": dict(a="rosette", pal="crisp", leaf_scale=0.85, heart=False,
                   bulb=dict(radius=6.5, triad=("#f28a96", "#d8404f", "#8a1626"))),
    "beet": dict(a="rosette", pal="dark", rib_color="#c93548", rib_width=1.1, heart=False,
                 bulb=dict(radius=7.5, triad=("#c05a6a", "#8a2038", "#4a0f1e"))),
    "turnip": dict(a="rosette", pal="fresh", heart=False,
                   bulb=dict(radius=7.0, triad=("#f4eede", "#d9c3dd", "#8a5f9d"))),
    "potato": dict(a="mound", pal="fresh",
                   flowers=dict(spec="white", petals=5, radius=3.8, n=4)),
    "onion": dict(a="allium", pal="fresh",
                  bulb=dict(radius=7.0, triad=("#e8c890", "#c89050", "#8a5a24"))),
    "garlic": dict(a="allium", pal="silver",
                   bulb=dict(radius=6.0, triad=("#f4efe0", "#ddd2b8", "#a89878"))),
    "leek": dict(a="allium", pal="teal",
                 bulb=dict(radius=5.0, triad=("#e8f0d8", "#c3d8a8", "#8aa86a"))),
    "celery": dict(a="rosette", pal="yellow", leaf_scale=0.9, rib_color="#cde8a0",
                   rib_width=1.3),
    "broccoli": dict(a="head", pal="teal", head=("#2a5f33", "#4a8a50", "#77b070")),
    "cauliflower": dict(a="head", pal="fresh", head=("#c9bf98", "#e8dfc0", "#f8f2e0")),
    "cabbage": dict(a="rosette", pal="teal", leaf_scale=1.1),
    "kale": dict(a="rosette", pal="teal", leaf_scale=1.05, heart=False, n_out=11),
    "spinach": dict(a="rosette", pal="fresh", leaf_scale=0.95),
    "lettuce": dict(a="rosette", pal="crisp"),
    "arugula": dict(a="rosette", pal="yellow", leaf_scale=0.9, n_out=11),
    "chard": dict(a="rosette", pal="crisp", rib_color="#d63b47", rib_width=1.1),
    "artichoke": dict(a="head", pal="silver", frilly=True,
                      head=("#55684a", "#7a8f62", "#a8b88a"), head_scale=0.32),
    "asparagus": dict(a="feathery", pal="olive"),
    "rhubarb": dict(a="rosette", pal="fresh", leaf_scale=1.3, n_out=8,
                    rib_color="#c93548", rib_width=1.3, heart=False),
    "okra": dict(a="mound", pal="yellow",
                 pods=dict(n=6, dark="#3f7423", light="#a8cf70", length=9.0),
                 flowers=dict(spec="cream", petals=5, radius=5.0, n=2)),
    # herbs
    "basil": dict(a="mound", pal="crisp", leaf_scale=1.1),
    "rosemary": dict(a="mound", pal="dark", narrow=True, n_out=30,
                     flowers=dict(spec="blue", petals=4, radius=2.6, n=5)),
    "thyme": dict(a="mound", pal="olive", leaf_scale=0.55, n_out=22,
                  flowers=dict(spec="pink", petals=4, radius=2.4, n=6)),
    "sage": dict(a="mound", pal="silver", leaf_scale=0.9,
                 flowers=dict(spec="purple", petals=4, radius=3.0, n=5)),
    "mint": dict(a="mound", pal="crisp", frilly=True, leaf_scale=0.95),
    "parsley": dict(a="rosette", pal="crisp", leaf_scale=0.8, n_out=12, heart=False),
    "cilantro": dict(a="rosette", pal="yellow", leaf_scale=0.75, heart=False,
                     umbels=dict(col="#f4f0e0", light="#ffffff", n=3, radius=4.0)),
    "dill": dict(a="feathery", pal="yellow",
                 umbels=dict(col="#e8c34a", light="#f8e48a", n=4, radius=5.0)),
    "chives": dict(a="allium", pal="crisp", n_out=22, leaf_scale=0.8,
                   clusters=dict(radius=3.4, dark="#8a5fc0", light="#d0c0f0",
                                 occ="#4a2f80", n=7, zone=(20, 32))),
    "oregano": dict(a="mound", pal="yellow", leaf_scale=0.75,
                    flowers=dict(spec="pink", petals=4, radius=3.0, n=7)),
    "tarragon": dict(a="mound", pal="olive", narrow=True, n_out=28),
    "lemongrass": dict(a="grass", pal="yellow", r=42, n_out=34),
    "chamomile": dict(a="feathery", pal="yellow",
                      flowers=dict(spec="white", petals=10, radius=4.8, n=8)),
    "fennel": dict(a="feathery", pal="olive",
                   umbels=dict(col="#e8c34a", light="#f8e48a", n=3, radius=5.0)),
    "marjoram": dict(a="mound", pal="yellow", leaf_scale=0.7, n_out=18,
                     flowers=dict(spec="white", petals=4, radius=2.8, n=6)),
    "bay_laurel": dict(a="mound", pal="dark"),
    "stevia": dict(a="mound", pal="crisp", leaf_scale=0.85),
    "sorrel": dict(a="rosette", pal="crisp", heart=False, n_out=9),
    "borage": dict(a="mound", pal="silver",
                   flowers=dict(spec="blue", petals=5, radius=4.5, n=7)),
    "lovage": dict(a="rosette", pal="yellow", leaf_scale=1.1, heart=False),
    # flowers
    "lavender": dict(a="mound", pal="silver", narrow=True, n_out=26,
                     puffs=dict(dark="#6b46ab", light="#a98fe0", n=9, start=(20.0, 22.5))),
    "tulip": dict(a="grass", pal="crisp", r=36,
                  flowers=dict(spec="red", petals=6, radius=6.0, n=5, zone=(8, 24))),
    "daffodil": dict(a="grass", pal="crisp", r=36,
                     flowers=dict(spec="yellow", petals=6, radius=6.5, n=5, zone=(8, 24))),
    "dahlia": dict(a="mound", pal="fresh",
                   flowers=dict(spec="magenta", petals=12, radius=8.0, n=4, double=True)),
    "peony": dict(a="mound", pal="fresh",
                  flowers=dict(spec="pink", petals=10, radius=8.5, n=4, double=True)),
    "iris": dict(a="grass", pal="teal", r=38,
                 flowers=dict(spec="purple", petals=3, radius=7.5, n=4, double=True,
                              zone=(8, 26))),
    "lily": dict(a="grass", pal="crisp", r=36,
                 flowers=dict(spec="orange", petals=6, radius=7.5, n=4, zone=(8, 24))),
    "marigold": dict(a="mound", pal="fresh",
                     flowers=dict(spec="gold", petals=10, radius=6.0, n=6, double=True)),
    "zinnia": dict(a="mound", pal="fresh",
                   flowers=dict(spec="red", petals=10, radius=6.0, n=6, double=True)),
    "cosmos": dict(a="feathery", pal="fresh",
                   flowers=dict(spec="pink", petals=8, radius=6.5, n=6)),
    "aster": dict(a="mound", pal="fresh",
                  flowers=dict(spec="purple", petals=12, radius=6.5, n=6)),
    "chrysanthemum": dict(a="mound", pal="fresh",
                          flowers=dict(spec="gold", petals=12, radius=7.0, n=5, double=True)),
    "geranium": dict(a="mound", pal="fresh",
                     clusters=dict(radius=6.5, dark="#c03030", light="#f28a80",
                                   occ="#5c1010", n=6)),
    "petunia": dict(a="mound", pal="fresh",
                    flowers=dict(spec="magenta", petals=5, radius=6.5, n=7)),
    "pansy": dict(a="mound", pal="crisp", r=34,
                  flowers=dict(spec="violet_face", petals=5, radius=6.0, n=6)),
    "crocus": dict(a="grass", pal="crisp", r=34,
                   flowers=dict(spec="purple", petals=6, radius=5.0, n=5, zone=(6, 22))),
    "sunflower": dict(a="flower", pal="fresh",
                      flowers=dict(spec="gold", petals=16, double=True)),
}

# --------------------------------------------------------------------------- #
# category table (15)
# --------------------------------------------------------------------------- #
CATEGORIES: dict[str, Recipe] = {
    "round_deciduous": dict(a="canopy", pal="fresh"),
    "columnar_tree": dict(a="canopy", pal="dark", r=36, leaf_scale=0.8, n_out=20),
    "weeping_tree": dict(a="canopy", pal="silver", leaf_scale=0.9, n_out=24),
    "conifer": dict(a="conifer", pal="dark"),
    "spreading_shrub": dict(a="mound", pal="fresh", r=42),
    "compact_shrub": dict(a="mound", pal="dark", r=34, leaf_scale=0.8),
    "ornamental_grass": dict(a="grass", pal="olive"),
    "flowering_perennial": dict(a="mound", pal="fresh",
                                flowers=dict(spec="pink", petals=8, radius=6.0, n=6)),
    "ground_cover": dict(a="ground", pal="crisp",
                         flowers=dict(spec="white", petals=5, radius=3.0, n=5)),
    "climbing_plant": dict(a="climber", pal="fresh",
                           flowers=dict(spec="purple", petals=5, radius=5.0, n=5)),
    "hedge_section": dict(a="hedge"),
    "vegetable": dict(a="rosette", pal="crisp", leaf_scale=0.95),
    "herb": dict(a="mound", pal="crisp", leaf_scale=0.8,
                 flowers=dict(spec="white", petals=4, radius=2.8, n=4)),
    "fruit_tree": dict(a="canopy", pal="fresh", fruit=dict(kind="apple", n=4)),
    "palm": dict(a="palm", pal="olive"),
}


# --------------------------------------------------------------------------- #
# what the tables say about themselves
# --------------------------------------------------------------------------- #
#: Recipe keys that draw fruit, flowers, pods or roots ON TOP of the foliage — the
#: generator's "features" block. They are the part of a plant a season decides,
#: so the 3D view v0 builds none of them (``ogp-lush-cinematic`` §1, "Season").
FEATURE_KEYS: Final[frozenset[str]] = frozenset(
    {"pods", "fruit", "fruit2", "flowers", "puffs", "clusters", "umbels", "bulb"}
)

#: Every archetype a recipe uses. A consumer that dispatches on ``a`` covers all
#: of them (the generator raises on an unknown one; the 3D builder is pinned to
#: this set by ``tests/unit/test_scene3d_plants.py``).
ARCHETYPES: Final[frozenset[str]] = frozenset(
    str(recipe["a"]) for table in (SPECIES, CATEGORIES) for recipe in table.values()
)


def palette_key(recipe: Mapping[str, Any]) -> str:
    """The name of the palette a recipe is drawn in (a key of ``PALETTES``).

    The hedge is always ``HEDGE_PALETTE`` — its drawing code never read a recipe;
    every other recipe names its palette or takes ``DEFAULT_PALETTE``.
    """
    if recipe.get("a") == "hedge":
        return HEDGE_PALETTE
    return str(recipe.get("pal", DEFAULT_PALETTE))
