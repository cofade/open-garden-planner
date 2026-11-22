"""#940: flowers that show in 3D.

The rules pinned here: a crown's flowers are counted by its surface, never a fixed
number; a bulb's flowers stand on scapes above its leaves; every petal shows from both
sides; a plant that flowers before or with its leaves carries fewer of them while it
flowers, and exactly its usual leaves outside its bloom window; the flowers keep their
2D colours; and every flowering species holds the truth gates at every LOD.
"""

from __future__ import annotations

import colorsys
import datetime
from dataclasses import replace

import numpy as np
import pytest

from open_garden_planner.core.phenology import BLOOM_RAMP_DAYS, evaluate_phenology, seasonal_month
from open_garden_planner.core.plant_art import (
    CATEGORY_TRAITS,
    FLOWERS,
    SPECIES_TRAITS,
    SpriteRef,
    traits_for,
)
from open_garden_planner.core.plant_art.traits3d import FLOWER_HABITS
from open_garden_planner.core.plant_forge import (
    LOD0,
    LOD1,
    LOD2,
    PART_FOLIAGE,
    PART_WOOD,
    forge_plant,
    triangle_budget_for_lod,
)
from open_garden_planner.core.plant_forge.accents import (
    CROWN_SHELL,
    FLOWER_PART,
    blossom_count,
    crown_flower_anchors,
    flower_triangles,
    flowers_geo,
)
from open_garden_planner.core.plant_forge.foliage import crown_surface_cm2
from open_garden_planner.core.plant_forge.herbaceous import BULB_LEAF_TOP, BULB_NECK
from open_garden_planner.core.plant_forge.trees import bark_linear_rgba

FLOWERING: tuple[SpriteRef, ...] = tuple(
    SpriteRef(group, name)
    for group, table in (("species", SPECIES_TRAITS), ("categories", CATEGORY_TRAITS))
    for name, traits in sorted(table.items())
    if traits.flower is not None
)
BULBS: tuple[SpriteRef, ...] = tuple(
    s for s in FLOWERING if traits_for(s).flower.habit == "scape"  # type: ignore[union-attr]
)
PRECOCIOUS = ("magnolia", "forsythia", "peach_tree", "plum_tree", "cherry_tree")


def _part(parts, name: str):
    return next(p.mesh for p in parts if p.name == name)


def _flower_count(sprite: SpriteRef, height: float, radius: float, lod: int = LOD0) -> float:
    parts = forge_plant(sprite, height, radius, seed=101, lod=lod, cache=None)
    flower = traits_for(sprite).flower
    assert flower is not None
    return _part(parts, FLOWER_PART).triangle_count / flower_triangles(flower, lod)


def test_every_flower_has_a_habit_its_archetype_builds() -> None:
    """A bulb (grass) stands on scapes, a stemmed flower carries heads, every other
    flowering plant spreads its flowers on its crown; clusters, puffs and umbels have none."""
    habit_of = {"grass": "scape", "flower": "head"}
    for sprite in FLOWERING:
        traits = traits_for(sprite)
        assert traits.flower is not None and traits.flower.habit in FLOWER_HABITS
        assert traits.flower.habit == habit_of.get(traits.archetype, "crown"), sprite
        assert traits.flower.radius_cm > 0.0 and 0.0 < traits.flower.cover <= 0.5, sprite
    for name in ("lilac", "lavender", "dill", "rhododendron"):
        assert traits_for(SpriteRef("species", name)).flower is None


def test_blossom_count_is_the_crown_surface_over_one_flower() -> None:
    small, r_small = blossom_count(10_000.0, 0.3, 3.5, 10**6, enlarge_max=1.8)
    large, r_large = blossom_count(40_000.0, 0.3, 3.5, 10**6, enlarge_max=1.8)
    assert large == pytest.approx(4 * small, rel=0.01)
    assert r_small == r_large == 3.5
    # a LOD that cannot afford them: fewer, larger flowers, never past the cap
    few, r_few = blossom_count(40_000.0, 0.3, 3.5, large // 2, enlarge_max=1.8)
    assert few == large // 2
    assert r_few == pytest.approx(3.5 * np.sqrt(large / few), rel=0.01)
    fewer, r_fewer = blossom_count(40_000.0, 0.3, 3.5, large // 9, enlarge_max=1.8)
    assert (fewer, r_fewer) == (large // 9, pytest.approx(3.5 * 1.8))
    assert blossom_count(40_000.0, 0.3, 3.5, 0, enlarge_max=1.8)[0] == 0


@pytest.mark.parametrize(
    ("species", "small", "large"),
    [
        ("magnolia", (200.0, 80.0), (300.0, 120.0)),
        ("cherry_tree", (160.0, 50.0), (240.0, 75.0)),
        ("aster", (60.0, 20.0), (90.0, 30.0)),
        ("rose", (60.0, 20.0), (90.0, 30.0)),
    ],
)
def test_flower_count_scales_with_the_crown_surface(species: str, small, large) -> None:
    sprite = SpriteRef("species", species)
    traits = traits_for(sprite)
    counts = [_flower_count(sprite, *size) for size in (small, large)]
    surfaces = [crown_surface_cm2(*size, traits.crown.trunk_share) for size in (small, large)]
    assert counts[0] >= 3
    assert counts[1] / counts[0] == pytest.approx(surfaces[1] / surfaces[0], rel=0.06)
    for size in (small, large):   # both counts were affordable: none was capped
        parts = forge_plant(sprite, *size, seed=101, lod=LOD0, cache=None)
        assert sum(p.mesh.triangle_count for p in parts) < triangle_budget_for_lod(LOD0) - 200


def test_a_blossom_tree_carries_hundreds_of_flowers() -> None:
    # the spring garden's cherry (529 cm, 195 cm radius): before #940, 12 flowers
    assert _flower_count(SpriteRef("species", "cherry_tree"), 529.0, 195.0) >= 400
    assert _flower_count(SpriteRef("species", "magnolia"), 324.0, 148.0) >= 150


def _nearest_wood_cm(parts, bark: np.ndarray) -> np.ndarray:
    """Per petal vertex, the distance (cm) to the nearest point sampled on the wood - the
    wood part and the twigs (``bark``-coloured) a shrub's flowers part carries."""
    wood = _part(parts, PART_WOOD)
    flowers_mesh = _part(parts, FLOWER_PART)
    is_twig = np.abs(flowers_mesh.colors[:, :3] - bark[None, :]).max(axis=1) < 1e-4
    twig_tri = flowers_mesh.indices[is_twig[flowers_mesh.indices].all(axis=1)]
    tri = np.concatenate([wood.positions.astype(np.float64)[wood.indices],
                          flowers_mesh.positions.astype(np.float64)[twig_tri]])
    rng = np.random.default_rng(0)
    uv = rng.random((len(tri), 6, 2))
    uv = np.where(uv.sum(axis=-1, keepdims=True) > 1.0, 1.0 - uv, uv)
    samples = (tri[:, None, 0] + uv[..., :1] * (tri[:, None, 1] - tri[:, None, 0])
               + uv[..., 1:] * (tri[:, None, 2] - tri[:, None, 0])).reshape(-1, 3)
    samples = np.concatenate([samples, wood.positions.astype(np.float64)])
    flowers = flowers_mesh.positions.astype(np.float64)[~is_twig]
    out = np.empty(len(flowers))
    for i in range(0, len(flowers), 2000):
        chunk = flowers[i:i + 2000]
        d2 = ((chunk[:, None, :] - samples[None, :, :]) ** 2).sum(axis=-1)
        out[i:i + 2000] = np.sqrt(d2.min(axis=1))
    return out


@pytest.mark.parametrize(("species", "height", "radius"), [
    ("cherry_tree", 528.9, 195.3), ("magnolia", 324.0, 147.7), ("plum_tree", 352.5, 142.9),
    ("forsythia", 174.0, 76.5),
])
def test_a_precocious_bloomers_flowers_sit_on_its_wood(species: str, height: float, radius: float) -> None:
    """Its leaves are screen-doored down to 6-18 % in bloom, so its flowers stand on its
    twigs, not on leaves that are gone: a cherry's flowers floated a median 26.9 cm from
    any wood, 42.6 % over 30 cm (review 2). A tree's flowers sit on its outer twigs; a
    shrub's (a forsythia's seven stems) each on a twig of its own from its nearest wood."""
    sprite = SpriteRef("species", species)
    parts = forge_plant(sprite, height, radius, seed=7, lod=LOD0, cache=None)
    bark = np.asarray(bark_linear_rgba(traits_for(sprite).branching)[:3], dtype=np.float32)
    distance = _nearest_wood_cm(parts, bark)
    assert float(np.median(distance)) < 5.0
    assert float(np.percentile(distance, 90)) < 15.0
    assert float(np.mean(distance > 30.0)) == 0.0


@pytest.mark.parametrize(("species", "height", "radius"), [
    ("lilac", 243.0, 88.2), ("rhododendron", 123.9, 62.0), ("hydrangea", 150.0, 70.0),
    ("geranium", 40.0, 20.0),
])
def test_a_crowns_flower_clusters_follow_its_surface(species: str, height: float, radius: float) -> None:
    """A lilac's panicles, a rhododendron's trusses: as many as cover 0.15 of the crown's
    surface, 0.6 of their recipe radius - not a fixed 10 at a plant-scaled size, which
    left every truss hidden in a green crown (review 2)."""
    sprite = SpriteRef("species", species)

    def clusters(h: float, r: float) -> float:
        parts = forge_plant(sprite, h, r, seed=7, lod=LOD0, cache=None)
        assert sum(p.mesh.triangle_count for p in parts) <= triangle_budget_for_lod(LOD0)
        return _part(parts, FLOWER_PART).triangle_count / (7 * 4 * 5)

    assert clusters(height, radius) >= 12          # the plan's size: a crown in flower
    small, large = (height * 0.3, radius * 0.3), (height * 0.45, radius * 0.45)   # under the cap
    trunk = traits_for(sprite).crown.trunk_share
    want = clusters(*small) * crown_surface_cm2(*large, trunk) / crown_surface_cm2(*small, trunk)
    assert abs(clusters(*large) - want) <= max(1.0, 0.06 * want)   # the count rounds up


@pytest.mark.parametrize(("species", "corners"), [("magnolia", 4), ("cherry_tree", 3)])
def test_petals_are_lit_alike_on_both_faces_and_both_halves(species: str, corners: int) -> None:
    """An open petal's back takes its front's normal (a thin petal lit like one sheet: no
    dark violet undersides) and the normal bends only along the petal (no pinwheel): a
    quad petal (magnolia) and a wedge (a cherry's spur blossom)."""
    flower = replace(traits_for(SpriteRef("species", species)).flower, disc_radius=0.0)
    geo = flowers_geo(flower, "pink", np.zeros((3, 3)), np.tile([0.0, 0.0, 1.0], (3, 1)),
                      np.full(3, 4.0), np.random.default_rng(2), lod=LOD0)
    half = len(geo.pos) // 2
    np.testing.assert_allclose(geo.nrm[:half], geo.nrm[half:])
    assert float(geo.nrm[:, 2].min()) > 0.0           # every petal leans to the sky
    petals = geo.nrm[:half].reshape(-1, corners, 3)
    np.testing.assert_allclose(petals[:, 1], petals[:, 2], atol=1e-6)   # the tip's corners
    if corners == 4:
        np.testing.assert_allclose(petals[:, 0], petals[:, 3], atol=1e-6)   # the base's


def test_a_bulbs_goblet_keeps_its_outside_normal_and_the_crocus_its_purple() -> None:
    """A bulb's goblet stands to the sky and is seen from its side: its outside keeps its
    own normal; the crocus's petals are shaded so the filmic curve keeps them purple."""
    crocus = traits_for(SpriteRef("species", "crocus")).flower
    assert crocus.habit == "scape" and crocus.shade < 1.0 and crocus.tip_light < 0.45
    geo = flowers_geo(replace(crocus, disc_radius=0.0), "purple", np.zeros((2, 3)),
                      np.tile([0.0, 0.0, 1.0], (2, 1)), np.full(2, 2.5),
                      np.random.default_rng(3), lod=LOD0)
    half = len(geo.pos) // 2
    assert not np.allclose(geo.nrm[:half], geo.nrm[half:])
    light = np.array([int(FLOWERS["purple"][1][i:i + 2], 16) / 255.0 for i in (1, 3, 5)])
    lin = np.where(light <= 0.04045, light / 12.92, ((light + 0.055) / 1.055) ** 2.4)
    assert float(geo.col[:, :3].max()) <= float(lin.max()) * crocus.shade * 1.01


@pytest.mark.parametrize("species", ["apple_tree", "forsythia", "tulip", "lilac", "lavender",
                                     "dill", "sunflower", "rose"])
def test_each_flower_carries_one_phase(species: str) -> None:
    """The engine opens and fades a plant's flowers one by one by their phase (UV.y,
    ``qml/screen.vert``): every vertex of one flower - petals, centre, twig, scape,
    cluster - shares it, phases lie in [0, 1) and spread over it (review 2: a whole crown
    popped in or out of flower, its shadow with it)."""
    parts = forge_plant(SpriteRef("species", species), 150.0, 60.0, seed=7, lod=LOD0, cache=None)
    mesh = _part(parts, FLOWER_PART)
    phase = mesh.uvs[:, 1].astype(np.float64)
    assert float(phase.min()) >= 0.0 and float(phase.max()) < 1.0
    # a triangle never spans two flowers
    tri = phase[mesh.indices]
    assert float(np.abs(tri - tri[:, :1]).max()) == 0.0
    distinct = np.unique(phase)
    assert len(distinct) >= 3 and float(distinct.max() - distinct.min()) > 0.5


def test_crown_flowers_anchor_on_the_outer_shell() -> None:
    rng = np.random.default_rng(3)
    dirs = rng.normal(size=(8000, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    cloud = dirs * rng.uniform(0.0, 1.0, size=(8000, 1)) * 100.0   # a crown with leaves inside
    anchors, outward = crown_flower_anchors(cloud, 300, np.random.default_rng(5))
    reach = np.linalg.norm(anchors, axis=1) / 100.0
    assert float(np.median(reach)) > CROWN_SHELL
    assert float(np.median(np.linalg.norm(cloud, axis=1) / 100.0)) < CROWN_SHELL
    assert np.allclose(np.linalg.norm(outward, axis=1), 1.0)


@pytest.mark.parametrize("sprite", BULBS, ids=lambda s: s.name)
@pytest.mark.parametrize(("height", "radius"), [(15.0, 5.0), (50.0, 10.0), (70.0, 10.0)])
@pytest.mark.parametrize("lod", [LOD0, LOD1])
def test_bulb_flowers_stand_on_scapes_above_their_leaves(
    sprite: SpriteRef, height: float, radius: float, lod: int,
) -> None:
    parts = forge_plant(sprite, height, radius, seed=7, lod=lod, cache=None)
    leaves = _part(parts, PART_FOLIAGE)
    flowers = _part(parts, FLOWER_PART)
    leaf_top = float(leaves.positions[:, 2].max())
    assert leaf_top <= BULB_LEAF_TOP * height + 1e-3
    # the part holds the scapes (stem green) and the flowers: every petal above the leaves
    stem = np.asarray(bark_linear_rgba(traits_for(sprite).branching)[:3], dtype=np.float32)
    is_stem = np.abs(flowers.colors[:, :3] - stem).max(axis=1) < 1e-4
    assert is_stem.any() and (~is_stem).any()
    assert float(flowers.positions[~is_stem, 2].min()) > leaf_top
    # the plant's top is a flower's, at its height
    assert float(flowers.positions[:, 2].max()) == pytest.approx(height, abs=1e-3)
    # out of bloom (the flowers part hidden) no bare stalk stands: the wood is the neck
    assert float(_part(parts, PART_WOOD).positions[:, 2].max()) <= BULB_NECK * height * 1.05  # the fit


def test_a_bulb_at_lod2_carries_its_scapes_with_its_flowers() -> None:
    """#971/#948: at LOD2 a bulb's scapes were its wood: a bunch of bare stalks ten months
    a year. They are the flowers' stalks, so they live in the flowers part, whose far
    patches carry the petal colour; out of bloom the part hides and the leaves remain."""
    parts = forge_plant(SpriteRef("species", "tulip"), 70.0, 10.0, seed=7, lod=LOD2, cache=None)
    assert FLOWER_PART in {p.name for p in parts}
    flowers = _part(parts, FLOWER_PART)
    assert float(flowers.positions[:, 2].max()) == pytest.approx(70.0, abs=1e-3)
    leaves = _part(parts, PART_FOLIAGE)
    assert float(leaves.positions[:, 2].max()) <= 0.61 * 70.0
    wood = _part(parts, PART_WOOD)
    assert float(wood.positions[:, 2].max()) <= 0.10 * 70.0


@pytest.mark.parametrize("species", ["tulip", "magnolia", "rose", "cherry_tree", "sunflower"])
@pytest.mark.parametrize("lod", [LOD0, LOD1])
def test_every_petal_shows_from_above_and_below(species: str, lod: int) -> None:
    parts = forge_plant(SpriteRef("species", species), 150.0, 60.0, seed=11, lod=lod, cache=None)
    mesh = _part(parts, FLOWER_PART)
    tri = mesh.positions.astype(np.float64)[mesh.indices]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(cross, axis=1)
    facing_up = float(area[cross[:, 2] > 0].sum() / area.sum())
    # before #940 every petal was wound toward the ground: 14 % faced the sky
    assert 0.4 <= facing_up <= 0.6


@pytest.mark.parametrize(
    "sprite",
    [s for s in FLOWERING
     if colorsys.rgb_to_hsv(*(int(FLOWERS[traits_for(s).blossom_spec][0][i:i + 2], 16) / 255.0
                              for i in (1, 3, 5)))[1] > 0.3],
    ids=lambda s: s.name,
)
def test_petals_keep_the_2d_sprite_hue(sprite: SpriteRef) -> None:
    traits = traits_for(sprite)
    flower = replace(traits.flower, disc_radius=0.0)
    spec = str(traits.blossom_spec)
    geo = flowers_geo(flower, spec, np.zeros((6, 3)), np.tile([0.0, 0.0, 1.0], (6, 1)),
                      np.full(6, 3.0), np.random.default_rng(1), lod=LOD0)
    lin = geo.col[:, :3].astype(np.float64).mean(axis=0)
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    hue = colorsys.rgb_to_hsv(*srgb)[0] * 360.0
    want = colorsys.rgb_to_hsv(*(int(FLOWERS[spec][0][i:i + 2], 16) / 255.0 for i in (1, 3, 5)))[0] * 360.0
    assert abs((hue - want + 180.0) % 360.0 - 180.0) <= 10.0


def _days(year: int = 2026):
    day = datetime.date(year, 1, 1)
    while day.year == year:
        yield day
        day += datetime.timedelta(days=1)


@pytest.mark.parametrize("species", PRECOCIOUS)
def test_a_precocious_bloomer_carries_fewer_leaves_in_bloom(species: str) -> None:
    sprite = SpriteRef("species", species)
    traits = traits_for(sprite)
    assert traits.bloom_leaf_density < 0.5
    first = datetime.date(2026, traits.bloom_months[0], 20)
    in_bloom = evaluate_phenology(sprite, first, latitude_deg=50.0)
    summer = evaluate_phenology(sprite, datetime.date(2026, 7, 15), latitude_deg=50.0)
    assert in_bloom.bloom == 1.0
    assert in_bloom.leaf_density <= traits.bloom_leaf_density + 1e-9
    assert summer.leaf_density == 1.0


@pytest.mark.parametrize("species", PRECOCIOUS)
@pytest.mark.parametrize("latitude", [50.0, -35.0])
def test_a_precocious_bloomer_holds_its_leaves_until_it_has_flowered(
    species: str, latitude: float,
) -> None:
    """From budburst until its window opens its leaves stay at its bloom share, through
    the window too until they unfold over its last quarter; after it, the season's own
    (the oak's: the same deciduous year). No day jumps: a cherry's leaves fell from 0.54
    on 31 March to 0.18 on 1 April when the hold began with the window (review 2)."""
    sprite = SpriteRef("species", species)
    oak = SpriteRef("species", "oak")
    traits = traits_for(sprite)
    previous = None
    for day in _days():
        state = evaluate_phenology(sprite, day, latitude_deg=latitude)
        usual = evaluate_phenology(oak, day, latitude_deg=latitude).leaf_density
        month = seasonal_month(day, latitude)
        if month < traits.bloom_months[0]:
            assert state.leaf_density == min(usual, traits.bloom_leaf_density), day
        elif month in traits.bloom_months:
            assert state.leaf_density <= usual, day
        else:
            assert state.leaf_density == usual, day
        if previous is not None:
            assert abs(state.leaf_density - previous) <= 0.1, day
        previous = state.leaf_density


@pytest.mark.parametrize("sprite", [s for s in FLOWERING if traits_for(s).bloom_months]
                         + [SpriteRef("species", n) for n in ("lilac", "lavender", "dill")],
                         ids=lambda s: s.name)
def test_flowers_open_and_fade_over_days_not_overnight(sprite: SpriteRef) -> None:
    """A bloom window's months are whole; a plant's flowering is not. Bloom opens over the
    window's first ``BLOOM_RAMP_DAYS`` and fades over its last, in both hemispheres - a
    whole tree no longer pops in or out of flower on the 1st (review 2)."""
    step = 1.5 / BLOOM_RAMP_DAYS + 1e-6     # a smoothstep's steepest slope
    for latitude in (50.0, -35.0):
        previous = None
        for day in _days():
            bloom = evaluate_phenology(sprite, day, latitude_deg=latitude).bloom
            if previous is not None:
                assert abs(bloom - previous) <= step, (latitude, day)
            previous = bloom
        assert previous is not None


@pytest.mark.parametrize("species", ["apple_tree", "pear_tree", "lilac", "oak"])
def test_a_plant_that_flowers_among_its_leaves_keeps_them(species: str) -> None:
    sprite = SpriteRef("species", species)
    oak = SpriteRef("species", "oak")
    for day in _days():
        assert (evaluate_phenology(sprite, day).leaf_density
                == evaluate_phenology(oak, day).leaf_density), day


@pytest.mark.parametrize("species", ["tulip", "daffodil", "crocus", "iris", "lily",
                                     "onion", "garlic", "leek", "chives", "corn"])
def test_a_clump_of_blades_keeps_its_spread_on_every_seed(species: str) -> None:
    """A bulb's or an allium's few leaves set its box; the fit's pull onto REACH_MAX took
    a diagonal tip in (a daffodil at LOD2: 0.868 of its spread, an onion 0.847). Four
    leaves along the plan's axes hold it at 2 r on every seed and LOD (#940)."""
    sprite = SpriteRef("species", species)
    for height, radius in ((15.0, 5.0), (50.0, 10.0), (60.0, 7.5)):
        for lod in (LOD0, LOD1, LOD2):
            for seed in range(64):
                parts = forge_plant(sprite, height, radius, seed=seed, lod=lod, cache=None)
                pos = np.concatenate([p.mesh.positions for p in parts]).astype(np.float64)
                span = max(np.ptp(pos[:, 0]), np.ptp(pos[:, 1]))
                assert abs(span - 2.0 * radius) <= 0.10 * 2.0 * radius, (height, lod, seed, span)


@pytest.mark.parametrize(
    "sprite",
    [SpriteRef("species", name) for name in
     ("pear_tree", "plum_tree", "cherry_tree", "jasmine", "clematis", "wisteria",
      "cucumber", "pea", "sunflower")]
    + [SpriteRef("categories", "climbing_plant")],
    ids=lambda s: f"{s.group}/{s.name}",
)
def test_a_sparse_far_crown_keeps_its_spread_on_every_seed(sprite: SpriteRef) -> None:
    """#970: at LOD2 a sparse crown's box sits on diagonals, and the fit's pull onto
    REACH_MAX took it to 0.865-0.893 of its diameter on some seeds (a jasmine seed 50,
    a cucumber seed 50, a sunflower seed 23). Four leaves on the plan's axes hold it."""
    for height, radius in ((150.0, 40.0), (420.0, 180.0), (800.0, 300.0)):
        for seed in range(32):
            parts = forge_plant(sprite, height, radius, seed=seed, lod=LOD2, cache=None)
            pos = np.concatenate([p.mesh.positions for p in parts]).astype(np.float64)
            span = max(np.ptp(pos[:, 0]), np.ptp(pos[:, 1]))
            assert abs(span - 2.0 * radius) <= 0.10 * 2.0 * radius, (
                height, radius, seed, span / (2.0 * radius))


@pytest.mark.parametrize(("species", "families"), [
    ("cherry_tree", {"flowers", "fruits"}),
    ("apple_tree", {"flowers", "fruits"}),
    ("blueberry", {"flowers", "fruits"}),
    ("rose", {"flowers"}),
    ("lavender", {"flowers"}),
    ("jasmine", {"flowers"}),
])
def test_a_far_crown_keeps_its_crop_as_patches(species: str, families: set[str]) -> None:
    """#948: beyond 45 m LOD2 built no accent at all, so a blossoming orchard or a
    ripening berry row lost its crop. A few large patches per family carry the colour,
    inside the LOD2 budget and the plant's own height and reach."""
    height, radius = 420.0, 180.0
    parts = forge_plant(SpriteRef("species", species), height, radius, seed=7,
                        lod=LOD2, cache=None)
    names = {p.name for p in parts}
    assert families <= names, names
    assert sum(p.mesh.triangle_count for p in parts) <= triangle_budget_for_lod(LOD2)
    for family in families:
        mesh = _part(parts, family)
        pos = mesh.positions.astype(np.float64)
        assert pos[:, 2].max() <= height + 1e-3
        assert float(np.hypot(pos[:, 0], pos[:, 1]).max()) <= radius * 1.04 + 1e-3
        # the far representation is a patch cloud, not a substitute LOD0 crop
        assert mesh.triangle_count <= 64


@pytest.mark.parametrize(("species", "colour"), [
    ("rhododendron", "#eeb3d3"),   # its clusters' own light pink, not FLOWERS["pink"]
    ("lilac", "#d0c0f0"),
    ("cherry_tree", "#e88aa8"),    # its flowers recipe's outer pink
])
def test_a_far_crop_takes_the_recipe_s_own_colour(species: str, colour: str) -> None:
    """#948: the far patch is the plant's own flower colour - a clusters plant's recipe
    entry, not the generic `blossom_spec` fallback that reads lighter than its trusses."""
    from open_garden_planner.core.plant_forge.accents import _hex_to_linear_rgb, build_far_accents

    geo = build_far_accents(
        traits_for(SpriteRef("species", species)), 150.0, 60.0,
        np.random.default_rng(3), family="flowers", max_tris=4,
    )
    np.testing.assert_allclose(geo.col[0, :3], _hex_to_linear_rgb(colour), atol=1e-5)


@pytest.mark.parametrize("species", ["oak", "birch", "boxwood"])
def test_a_leaf_only_far_crown_gets_no_crop(species: str) -> None:
    parts = forge_plant(SpriteRef("species", species), 420.0, 180.0, seed=7,
                        lod=LOD2, cache=None)
    assert not ({FLOWER_PART, "fruits"} & {p.name for p in parts})


@pytest.mark.parametrize("species", ["tulip", "daffodil", "crocus"])
def test_a_far_bulb_keeps_its_flowers_on_its_scapes(species: str) -> None:
    """#963/#948: a bulb at LOD2 no longer loses its flower colour, and its scapes live
    in the flowers part (they are hidden out of bloom, unlike wood)."""
    parts = forge_plant(SpriteRef("species", species), 30.0, 5.0, seed=7,
                        lod=LOD2, cache=None)
    assert FLOWER_PART in {p.name for p in parts}
    flowers = _part(parts, FLOWER_PART)
    assert flowers.triangle_count > 0
    assert float(flowers.positions[:, 2].max()) == pytest.approx(30.0, abs=0.02)
    # out of bloom the part hides: the leaves are the visible top
    assert float(_part(parts, PART_FOLIAGE).positions[:, 2].max()) <= 0.61 * 30.0


@pytest.mark.parametrize("sprite", FLOWERING, ids=lambda s: f"{s.group}/{s.name}")
def test_every_flowering_species_holds_the_truth_gates_at_every_lod(sprite: SpriteRef) -> None:
    for height, radius in ((420.0, 180.0), (90.0, 30.0)):
        for lod in (LOD0, LOD1, LOD2):
            parts = forge_plant(sprite, height, radius, seed=101, lod=lod, cache=None)
            again = forge_plant(sprite, height, radius, seed=101, lod=lod, cache=None)
            pos = np.concatenate([p.mesh.positions for p in parts]).astype(np.float64)
            assert np.isfinite(pos).all()
            assert float(pos[:, 2].min()) == pytest.approx(0.0, abs=1e-3)
            assert abs(float(pos[:, 2].max()) - height) <= 0.03 * height
            span = max(np.ptp(pos[:, 0]), np.ptp(pos[:, 1]))
            assert abs(span - 2.0 * radius) <= 0.10 * 2.0 * radius
            assert sum(p.mesh.triangle_count for p in parts) <= triangle_budget_for_lod(lod)
            for part, twin in zip(parts, again, strict=True):
                part.validate()
                np.testing.assert_allclose(part.mesh.positions, twin.mesh.positions, atol=1e-4)
            if lod == LOD0:   # two seeds, two plants in flower: no clones
                other = forge_plant(sprite, height, radius, seed=202, lod=lod, cache=None)
                mine = _part(parts, FLOWER_PART).positions
                theirs = _part(other, FLOWER_PART).positions
                assert mine.shape != theirs.shape or not np.allclose(mine, theirs, atol=0.5)
