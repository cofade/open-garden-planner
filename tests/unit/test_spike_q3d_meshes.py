"""Truth and budget gates for the spike's procedural meshes (ADR-047, plan §9).

The look may be stylised; the numbers may not lie. Every plant's bounding box
IS the data (height from the resolver, spread from the 2D canopy) because
``fit_to`` enforces it for all archetypes at once. Determinism uses a tolerance,
not a hash: numpy's SIMD trig differs across CPUs/builds (plan finding F9).
"""

from __future__ import annotations

import numpy as np
import pytest

from open_garden_planner.spike_q3d import meshes as M

PLANTS = [
    ("Apple Tree", "TREE", 420.0, 340.0),
    ("Birch", "TREE", 900.0, 280.0),
    ("Spruce", "TREE", 800.0, 240.0),
    ("Tomato", "PERENNIAL", 200.0, 90.0),
    ("Lettuce", "PERENNIAL", 30.0, 30.0),
    ("Cabbage", "PERENNIAL", 50.0, 90.0),
    ("Onion", "PERENNIAL", 60.0, 15.0),
    ("Chives", "PERENNIAL", 40.0, 30.0),
    ("Sunflower", "PERENNIAL", 300.0, 90.0),
    ("Lavender", "PERENNIAL", 90.0, 120.0),
    ("Hydrangea", "SHRUB", 150.0, 110.0),
    ("Unknown Plant", "SHRUB", 120.0, 100.0),
]


@pytest.mark.parametrize(("species", "ot", "height", "spread"), PLANTS)
def test_plant_bbox_is_the_data(species: str, ot: str, height: float, spread: float) -> None:
    mesh = M.plant_mesh(species, M.item_seed("fixed-" + species), height, spread, ot)
    lo, hi = mesh.bounds()
    assert lo[2] == pytest.approx(0.0, abs=0.5)          # stands on the ground
    assert hi[2] == pytest.approx(height, rel=0.03)      # height gate ±3 %
    span = max(hi[0] - lo[0], hi[1] - lo[1])
    assert span == pytest.approx(spread, rel=0.10)       # spread gate ±10 %
    assert not np.isnan(mesh.positions).any()
    assert not np.isnan(mesh.normals).any()


@pytest.mark.parametrize(("species", "ot", "height", "spread"), PLANTS[:4])
def test_triangle_budget(species: str, ot: str, height: float, spread: float) -> None:
    mesh = M.plant_mesh(species, 7, height, spread, ot)
    budget = 25_000 if ot == "TREE" else 6_000
    assert 0 < mesh.triangle_count <= budget


def test_same_seed_same_mesh_within_tolerance() -> None:
    a = M.plant_mesh("Apple Tree", 1234, 420.0, 340.0, "TREE")
    b = M.plant_mesh("Apple Tree", 1234, 420.0, 340.0, "TREE")
    assert a.vertex_count == b.vertex_count
    assert np.max(np.abs(a.positions - b.positions)) <= 1e-3


def test_different_seeds_are_not_clones() -> None:
    a = M.plant_mesh("Apple Tree", 1, 420.0, 340.0, "TREE")
    b = M.plant_mesh("Apple Tree", 2, 420.0, 340.0, "TREE")
    assert a.vertex_count != b.vertex_count or not np.allclose(a.positions, b.positions)


def test_item_seed_is_stable() -> None:
    assert M.item_seed("abc") == M.item_seed("abc")
    assert M.item_seed("abc") != M.item_seed("abd")


def test_gable_house_ridge_reaches_effective_height() -> None:
    fp = [(0.0, 0.0), (900.0, 0.0), (900.0, 540.0), (0.0, 540.0)]
    mesh = M.gable_house(fp, ((0.0, 270.0), (900.0, 270.0)), 650.0)
    top = float(mesh.positions[:, 2].max())
    assert top == pytest.approx(650.0 + 13.0, abs=1.0)  # ridge + 6 cm slab + 7 cm cap
    walls = M.prism(fp, 10.0, 0.0, "#ffffff")
    assert walls.triangle_count > 0


def test_grass_stays_inside_lawn_and_out_of_the_pond() -> None:
    lawn = [(0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 300.0)]
    pond = [(150.0, 100.0), (250.0, 100.0), (250.0, 200.0), (150.0, 200.0)]
    mesh = M.grass(lawn, 3, 400.0, exclude=[pond])
    roots = mesh.positions[::5]  # first vertex of each blade = its root
    assert roots[:, 0].min() >= -2.0 and roots[:, 0].max() <= 402.0
    in_pond = (roots[:, 0] > 152) & (roots[:, 0] < 248) & (roots[:, 1] > 102) & (roots[:, 1] < 198)
    assert not in_pond.any()
    assert mesh.uv[:, 0].min() == 0.0 and mesh.uv[:, 0].max() == 1.0  # wind weight base→tip


def test_concat_offsets_indices() -> None:
    a = M.box(0, 0, 0, 10, 10, 10, "#ffffff")
    b = M.box(50, 0, 0, 10, 10, 10, "#ffffff")
    both = M.MeshData.concat([a, b])
    assert both.vertex_count == a.vertex_count + b.vertex_count
    assert int(both.indices.max()) == both.vertex_count - 1
