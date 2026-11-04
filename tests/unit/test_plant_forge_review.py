"""Regression contracts found during PR #593's independent review."""

import datetime as dt

import numpy as np
import pytest

from open_garden_planner.core.phenology import evaluate_phenology
from open_garden_planner.core.plant_art import SpriteRef, resolve_sprite
from open_garden_planner.core.plant_forge import forge_plant
from open_garden_planner.core.plant_forge.cache import ForgeCache, make_cache_key


@pytest.mark.parametrize("day,ripe", [(21, False), (22, True), (5, True), (6, False)])
def test_harvest_uses_exact_days_instead_of_whole_months(day, ripe):
    month = 3 if day > 10 else 4
    state = evaluate_phenology(
        SpriteRef("species", "radish"), dt.date(2026, month, day),
        last_frost=dt.date(2026, 3, 1),
    )
    assert (state.ripeness > 0) is ripe


def test_apple_flowers_and_fruit_are_independently_addressable():
    parts = forge_plant(SpriteRef("species", "apple_tree"), 400, 180, seed=42, cache=None)
    names = {part.name for part in parts}
    assert {"flowers", "fruits"} <= names


def test_southern_frost_calendar_is_already_local():
    state = evaluate_phenology(
        SpriteRef("species", "radish"), dt.date(2026, 10, 1), latitude_deg=-35,
        last_frost=dt.date(2026, 9, 1),
    )
    assert state.ripeness > 0


@pytest.mark.parametrize("name", ["Lemon Balm", "Melissa officinalis", "lemon_balm"])
def test_exact_herb_alias_wins_over_lemon_word(name):
    assert resolve_sprite("PERENNIAL", name) == SpriteRef("categories", "herb")


@pytest.mark.parametrize("species", ["apple_tree", "willow", "birch", "oak", "cherry_tree", "maple"])
@pytest.mark.parametrize("lod", [0, 1, 2])
def test_winter_skeleton_keeps_ground_and_height(species, lod):
    parts = forge_plant(SpriteRef("species", species), 400, 150, seed=77, lod=lod, cache=None)
    wood = next(part.mesh for part in parts if part.name == "wood")
    assert float(wood.positions[:, 2].min()) == pytest.approx(0, abs=0.1)
    assert float(wood.positions[:, 2].max()) == pytest.approx(400, abs=0.1)


def test_cache_enforces_bytes_and_does_not_retain_oversize_entries():
    parts = forge_plant(SpriteRef("species", "oak"), 400, 150, seed=77, lod=2, cache=None)
    size = sum(a.nbytes for p in parts for a in (
        p.mesh.positions, p.mesh.normals, p.mesh.colors, p.mesh.uvs, p.mesh.indices,
    ))
    cache = ForgeCache(max_entries=256, max_bytes=size)
    first = make_cache_key("species", "oak", 77, 2, 400, 150)
    second = make_cache_key("species", "oak", 78, 2, 400, 150)
    cache.put(first, parts)
    cache.put(second, parts)
    assert cache.get(first) is None
    assert cache.get(second) is parts
    assert cache.current_bytes == size
    cache.clear()
    assert cache.current_bytes == 0
    tiny = ForgeCache(max_bytes=size - 1)
    tiny.put(first, parts)
    assert tiny.get(first) is None


@pytest.mark.parametrize("species,height,radius", [("birch", 929, 148), ("spruce", 877, 127)])
@pytest.mark.parametrize("lod", [0, 1, 2])
def test_tall_crowns_retain_foliage_coverage_at_every_lod(species, height, radius, lod):
    parts = forge_plant(SpriteRef("species", species), height, radius, seed=77, lod=lod, cache=None)
    mesh = next(p.mesh for p in parts if p.name == "foliage")
    tri = mesh.positions[mesh.indices]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum() / 2
    from open_garden_planner.core.plant_art import traits_for
    share = traits_for(SpriteRef("species", species)).crown.trunk_share
    rz = height * (1 - share) / 2
    surface = 4 * np.pi * ((radius**3.215 + 2 * (radius * rz)**1.6075) / 3)**(1 / 1.6075)
    # The review's sparse crowns read .077..315. The measured style target is
    # 1.6; allow fitting/overlap to reduce area, but never back to those poles.
    assert area / surface >= 0.8


def test_structural_fitting_keeps_a_leaf_joint_on_its_branch():
    from open_garden_planner.core.plant_forge.assemble import fit_forged_parts
    from open_garden_planner.core.plant_forge.foliage import RawGeo, empty_geo

    def triangle(points):
        return RawGeo(np.array(points, dtype=np.float32),
                      np.tile([0., 1., 0.], (3, 1)).astype(np.float32),
                      np.ones((3, 4), np.float32), np.zeros((3, 2), np.float32),
                      np.array([[0, 1, 2]], np.uint32))

    wood = triangle([[0, 0, 0], [0, 0, 100], [10, 0, 50]])
    leaves = triangle([[10, 0, 50], [20, 0, 150], [-20, 10, 100]])
    parts = fit_forged_parts(wood, leaves, empty_geo(), 100, 50, structural_height=True)
    assert parts[0].mesh.positions[2, 2] == pytest.approx(parts[1].mesh.positions[0, 2])


@pytest.mark.parametrize("species", ["apple_tree", "cherry_tree", "birch"])
@pytest.mark.parametrize("lod", [0, 1, 2])
def test_summer_foliage_reaches_real_terminal_twigs(species, lod):
    from open_garden_planner.core.plant_art import traits_for
    from open_garden_planner.core.plant_forge.lod import lod_skeleton_budget
    from open_garden_planner.core.plant_forge.skeleton import grow_skeleton
    from open_garden_planner.core.plant_forge.trees import build_tree_foliage_from_skeleton
    from open_garden_planner.core.plant_forge.tube import limb_tubes

    traits = traits_for(SpriteRef("species", species))
    rng = np.random.default_rng(77)
    nodes, attractors, sides = lod_skeleton_budget(lod, traits.branching.attractors)
    skeleton = grow_skeleton(400, 150, traits.crown, traits.branching, rng,
                             max_nodes=nodes, attractors=attractors)
    wood = limb_tubes(skeleton, sides=sides, color_rgba=(.2, .1, .05, 1.))
    foliage = build_tree_foliage_from_skeleton(skeleton, traits, 400, 150, rng,
                                              lod, wood.triangle_count)
    terminals = np.ones(len(skeleton.positions), dtype=bool)
    terminals[skeleton.parents[1:]] = False
    twigs = skeleton.positions[terminals]
    # Every diamond's first vertex is its attachment point. A separately
    # randomized crown can be dense while missing these woody endpoints.
    attachments = foliage.pos[::4]
    distances = np.linalg.norm(twigs[:, None, :] - attachments[None, :, :], axis=2)
    assert float(distances.min(axis=1).max()) < .001


@pytest.mark.parametrize("lod", [0, 1, 2])
@pytest.mark.parametrize("seed", [77, 101, 202])
def test_tall_spruce_crown_has_no_long_bare_tier_gap(lod, seed):
    from PIL import Image, ImageDraw

    parts = forge_plant(SpriteRef("species", "spruce"), 877, 127, seed=seed, lod=lod, cache=None)
    foliage = next(part.mesh for part in parts if part.name == "foliage")
    # Rasterize complete side-projected triangles, not their vertices or a
    # sparse barycentric sample. Inspect the middle65% of the actual crown.
    image = Image.new("1", (256, 512))
    draw = ImageDraw.Draw(image)
    projected = foliage.positions[:, [0, 2]] * [255 / 254, 511 / 877] + [127.5, 0]
    for triangle in foliage.indices:
        draw.polygon([tuple(point) for point in projected[triangle]], fill=1)
    widths = np.asarray(image).sum(axis=1)
    narrow = widths[int(512 * .2):int(512 * .85)] < 20
    transitions = np.flatnonzero(np.diff(np.r_[False, narrow, False]))
    runs = transitions[1::2] - transitions[::2]
    # A vertical run of20px is34cm at this recorded877cm height. The original
    # separated pom-poms left32..72px of almost naked pole between tiers.
    assert max(runs, default=0) <= 20
