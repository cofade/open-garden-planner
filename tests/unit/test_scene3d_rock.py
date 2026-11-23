"""A stone-filled polygon is a rock, not a flat-topped prism (#955)."""

from __future__ import annotations

import numpy as np
import pytest

from open_garden_planner.core.scene3d import Material, Params, Record, Transform
from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.core.scene3d.record import (
    PARAM_SEED,
    PARAM_SURFACE_PATTERN,
    SHAPE_POLYGON,
)


def rock_record(*, item_id: str = "rock", pattern: str = "STONE", height: float = 60.0,
                points: tuple[tuple[float, float], ...] = (
                    (-90.0, -35.0), (-55.0, -60.0), (20.0, -55.0), (75.0, -25.0),
                    (90.0, 20.0), (45.0, 55.0), (-25.0, 60.0), (-80.0, 30.0))) -> Record:
    return Record(
        item_id=item_id, kind="GENERIC_POLYGON", shape=SHAPE_POLYGON,
        footprints=(points,), transform=Transform(), height_cm=height,
        material=Material("GENERIC_POLYGON"),
        params=Params({PARAM_SEED: "rock", PARAM_SURFACE_PATTERN: pattern}),
    )


def test_a_stone_polygon_is_domed_and_keeps_its_two_dimensional_stone_picture() -> None:
    record = rock_record()
    parts = production_registry().build(record)
    assert parts, "a stone-filled polygon with a height is a solid"
    top = max(float(part.mesh.positions[:, 2].max()) for part in parts)
    assert top == pytest.approx(record.height_cm, abs=1e-4)
    cap = next(part for part in parts if part.name == "rock")
    assert cap.fill_texture, "the canvas's stone picture stays on the rock's top"
    heights = cap.mesh.positions[:, 2]
    assert len(np.unique(np.round(heights, 4))) >= 4, "a domed top, not one flat cap"
    assert np.count_nonzero(np.abs(heights) > 1.0) >= len(cap.mesh.positions) // 2


def test_a_polygon_in_another_fill_is_the_plain_prism() -> None:
    record = rock_record(pattern="SOLID")
    parts = production_registry().build(record)
    assert [part.name for part in parts] == ["prism_sides", "prism"]


def test_the_rock_stays_on_its_footprint_and_its_highest_point_is_one_peak() -> None:
    record = rock_record()
    parts = production_registry().build(record)
    cap = next(part for part in parts if part.name == "rock")
    ring = np.asarray(record.footprints[0], dtype=np.float64)
    low, high = ring.min(axis=0) - 1e-4, ring.max(axis=0) + 1e-4
    xy = cap.mesh.positions[:, :2]
    assert np.all(xy >= low) and np.all(xy <= high)
    tops = np.round(cap.mesh.positions[:, 2], 5)
    assert int((tops == tops.max()).sum()) == 1


def test_a_concave_stone_polygon_falls_back_to_its_honest_prism() -> None:
    concave = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (55.0, 35.0),
               (0.0, 100.0))
    record = rock_record(points=concave)
    assert [part.name for part in production_registry().build(record)] == [
        "prism_sides", "prism"]


def test_two_rocks_are_not_clones_and_their_widest_ring_is_at_the_ground() -> None:
    """#960 review round 2: the example's three rocks were one bollard profile at
    three sizes. A per-record ring-scale jitter makes their domes differ while the
    base ring stays on the footprint, and the widest ring is the one at the ground."""
    ring = np.asarray(rock_record().footprints[0], dtype=np.float64)
    first = next(part for part in production_registry().build(rock_record(item_id="rock-a"))
                 if part.name == "rock")
    second = next(part for part in production_registry().build(rock_record(item_id="rock-b"))
                  if part.name == "rock")
    assert first.mesh.positions.shape == second.mesh.positions.shape
    assert not np.allclose(first.mesh.positions, second.mesh.positions), "two clones"
    ground = first.mesh.positions[np.isclose(first.mesh.positions[:, 2], 0.0)]
    assert ground.size
    assert np.ptp(ground[:, 0]) >= 0.95 * np.ptp(ring[:, 0])
    assert np.ptp(ground[:, 1]) >= 0.95 * np.ptp(ring[:, 1])
