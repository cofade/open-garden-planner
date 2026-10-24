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
