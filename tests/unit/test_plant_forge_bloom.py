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

from open_garden_planner.core.phenology import evaluate_phenology
from open_garden_planner.core.plant_art import (
    CATEGORY_TRAITS,
    FLOWERS,
    SPECIES_TRAITS,
    SpriteRef,
    traits_for,
)
from open_garden_planner.core.plant_forge import (
    LOD0,
    LOD1,
    LOD2,
    PART_FOLIAGE,
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
from open_garden_planner.core.plant_forge.herbaceous import BULB_LEAF_TOP

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
    assert float(flowers.positions[:, 2].min()) > leaf_top
    # the plant's top is a flower's, at its height
    assert float(flowers.positions[:, 2].max()) == pytest.approx(height, abs=1e-3)


def test_a_bulb_at_lod2_keeps_its_scapes_to_the_top() -> None:
    parts = forge_plant(SpriteRef("species", "tulip"), 70.0, 10.0, seed=7, lod=LOD2, cache=None)
    assert FLOWER_PART not in {p.name for p in parts}
    top = max(float(p.mesh.positions[:, 2].max()) for p in parts)
    assert top == pytest.approx(70.0, abs=1e-3)


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
def test_outside_its_bloom_a_precocious_bloomer_keeps_its_usual_leaves(
    species: str, latitude: float,
) -> None:
    """The rule never touches a day out of bloom, and the leaves have unfolded by the
    bloom window's last day: no jump when the flowers go. Oak: the same deciduous year."""
    sprite = SpriteRef("species", species)
    oak = SpriteRef("species", "oak")
    for day in _days():
        state = evaluate_phenology(sprite, day, latitude_deg=latitude)
        usual = evaluate_phenology(oak, day, latitude_deg=latitude).leaf_density
        if state.bloom == 0.0:
            assert state.leaf_density == usual, day
        else:
            assert state.leaf_density <= usual, day
            following = evaluate_phenology(sprite, day + datetime.timedelta(days=1),
                                           latitude_deg=latitude)
            if following.bloom == 0.0:   # the window's last day
                assert state.leaf_density == pytest.approx(usual, abs=0.02), day


@pytest.mark.parametrize("species", ["apple_tree", "pear_tree", "lilac", "oak"])
def test_a_plant_that_flowers_among_its_leaves_keeps_them(species: str) -> None:
    sprite = SpriteRef("species", species)
    oak = SpriteRef("species", "oak")
    for day in _days():
        assert (evaluate_phenology(sprite, day).leaf_density
                == evaluate_phenology(oak, day).leaf_density), day


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
