"""Support geometry dependencies and trained-climber truth gates (PR #593)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from open_garden_planner.core.plant_forge import (
    LOD_TRIANGLE_BUDGETS,
    climber_support_signature,
    enrich_climber_record,
    forge_record,
)
from open_garden_planner.core.scene3d import Params, Transform, verify_builder
from tests.integration.test_plant_forge_support_geometry import support_scene


def test_support_dependencies_exclude_only_plant_height_and_appearance() -> None:
    plant, support = support_scene()
    baseline = climber_support_signature([plant, support])
    assert baseline == climber_support_signature([replace(plant, height_cm=500, name="Changed"), support])
    variants = [
        (replace(plant, parent_id=support.item_id), support),
        (replace(plant, transform=Transform(320, -170, 35)), support),
        (replace(plant, params=Params(dict(plant.params, radius_cm=30))), support),
        (replace(plant, params=Params(dict(plant.params, sprite_species="apple_tree"))), support),
        (plant, replace(support, path=((-100, 0), (100, 0)))),
        (plant, replace(support, height_cm=120)),
        (plant, replace(support, path_width_cm=20)),
        (plant, replace(support, transform=Transform(320, -125, 45))),
        (plant, replace(support, kind="PERGOLA")),
    ]
    for pair in variants:
        assert climber_support_signature(pair) != baseline
    assert climber_support_signature([plant]) != baseline


@pytest.mark.parametrize("lod", [0, 1, 2])
@pytest.mark.parametrize("sprite", ["jasmine", "clematis", "wisteria", "bean", "pea", "cucumber"])
def test_trained_climber_truth_determinism_and_variation(lod: int, sprite: str) -> None:
    plant, support = support_scene()
    plant = replace(plant, params=Params(dict(plant.params, sprite_species=sprite)))
    enriched = enrich_climber_record(plant, {support.item_id: support})
    parts = verify_builder(lambda rec: forge_record(rec, lod=lod, cache=None), enriched)
    repeated = forge_record(enriched, lod=lod, cache=None)
    other = forge_record(replace(enriched, params=Params(dict(enriched.params, seed="another-uuid"))),
                         lod=lod, cache=None)
    assert sum(p.mesh.triangle_count for p in parts) <= LOD_TRIANGLE_BUDGETS[lod]
    for part, same in zip(parts, repeated, strict=True):
        np.testing.assert_allclose(part.mesh.positions, same.mesh.positions, atol=1e-5)
        np.testing.assert_allclose(np.linalg.norm(part.mesh.normals, axis=1), 1.0, atol=1e-5)
        assert np.isfinite(part.mesh.positions).all()
    foliage = next(p.mesh.positions for p in parts if p.name == "foliage")
    other_foliage = next(p.mesh.positions for p in other if p.name == "foliage")
    assert foliage.shape != other_foliage.shape or not np.allclose(foliage, other_foliage, atol=1e-4)
    wood = next(p.mesh.positions for p in parts if p.name == "wood")
    assert np.linalg.norm(wood[wood[:, 2] < 1e-4, :2], axis=1).min() < 1.5
    points = np.concatenate([p.mesh.positions for p in parts])
    assert np.linalg.norm(points[:, :2], axis=1).max() <= 45 * 1.04 + 1e-4


@pytest.mark.parametrize("lod", [0, 1, 2])
def test_fallback_builds_exactly_three_grounded_bamboo_poles(lod: int, monkeypatch: pytest.MonkeyPatch) -> None:
    from open_garden_planner.core.plant_art import SpriteRef, traits_for
    from open_garden_planner.core.plant_forge import climbers

    original = climbers.frustum_tubes
    segments = []

    def record_tubes(first: np.ndarray, last: np.ndarray, *args: object, **kwargs: object):
        segments.append((first, last))
        return original(first, last, *args, **kwargs)

    monkeypatch.setattr(climbers, "frustum_tubes", record_tubes)
    climbers.build_forged_climber(traits_for(SpriteRef("species", "jasmine")), 210, 45, 101, lod=lod)
    first, last = segments[0]
    poles = (first[:, 2] == 0) & (last[:, 2] > 210 * 0.85)
    assert np.count_nonzero(poles) == 3


@pytest.mark.parametrize("lod", [0, 1, 2])
def test_short_support_keeps_a_contact_node_at_coarse_lod(lod: int) -> None:
    plant, support = support_scene()
    support = replace(support, height_cm=25)
    enriched = enrich_climber_record(plant, [support])
    wood = next(p.mesh.positions for p in forge_record(enriched, lod=lod, cache=None) if p.name == "wood")
    assert np.count_nonzero((wood[:, 1] >= 40) & (wood[:, 2] < 25)) >= 4
