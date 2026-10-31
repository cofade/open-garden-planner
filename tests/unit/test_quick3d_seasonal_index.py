"""Unit tests for Quick3D seasonal index and sparse updates (#598)."""

from __future__ import annotations

import pytest

from open_garden_planner.core.phenology import PhenologyState
from open_garden_planner.core.scene3d import EnginePose, engine_buffers
from open_garden_planner.core.scene3d.build import prism_mesh
from open_garden_planner.ui.view3d.quick3d.adapter import PartSpec
from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


@pytest.fixture
def host(qtbot):  # noqa: ARG001 - Qt init
    h = Quick3DHost(size=(64, 48), prefer_software=True)
    yield h
    h.close()


def test_seasonal_parts_indexed_and_supports_excluded(host):
    buffers = engine_buffers(prism_mesh([SQUARE], 10.0))
    pose = EnginePose(position=(0, 0, 0), yaw_deg=0)
    white = (255, 255, 255, 255)

    # 1. Non-seasonal part (wood trunk)
    wood_spec = PartSpec(item_id="plant-1", part_index=0, name="wood", kind="vc",
                         buffers=buffers, casts_shadow=True)
    wood_part = host.create_part(wood_spec, pose, white)

    # 2. Seasonal part (foliage)
    foliage_spec = PartSpec(item_id="plant-1", part_index=1, name="foliage", kind="foliage",
                            buffers=buffers, casts_shadow=True)
    foliage_part = host.create_part(foliage_spec, pose, white)

    # 3. Support part (fence)
    fence_spec = PartSpec(item_id="fence-1", part_index=0, name="panel", kind="vc",
                          buffers=buffers, casts_shadow=True)
    fence_part = host.create_part(fence_spec, pose, white)

    # Verify QML seasonalParts indexing:
    seasonal_parts = host._root.property("seasonalParts").toVariant()
    assert "fence-1" not in seasonal_parts
    assert "plant-1" in seasonal_parts
    parts_list = seasonal_parts["plant-1"]
    # Only foliage should be indexed under plant-1, not wood
    assert len(parts_list) == 1
    assert parts_list[0].property("partName") == "foliage"

    # Test destroyPart unregisters from index
    host.destroy_part(foliage_part)
    seasonal_parts_after = host._root.property("seasonalParts").toVariant()
    assert "plant-1" not in seasonal_parts_after

    # Clean up remaining
    host.destroy_part(wood_part)
    host.destroy_part(fence_part)


def test_sparse_plant_seasons_update(host):
    state_a = PhenologyState(
        leaf_density=0.8,
        autumn_color=0.0,
        autumn_tint_linear=(0.0, 0.0, 0.0),
        bloom=0.0,
        ripeness=0.0,
        snow=0.0,
        foliage_tint_linear=(0.1, 0.2, 0.3),
        foliage_tint_rgba=(25, 51, 76, 255),
        accent_opacity=0.0,
        accent_tint_linear=(1.0, 1.0, 1.0),
        accent_tint_rgba=(255, 255, 255, 255),
    )
    state_b = PhenologyState(
        leaf_density=1.0,
        autumn_color=0.0,
        autumn_tint_linear=(0.0, 0.0, 0.0),
        bloom=1.0,
        ripeness=0.0,
        snow=0.0,
        foliage_tint_linear=(0.2, 0.4, 0.1),
        foliage_tint_rgba=(51, 102, 25, 255),
        accent_opacity=1.0,
        accent_tint_linear=(1.0, 1.0, 1.0),
        accent_tint_rgba=(255, 255, 255, 255),
    )

    # Initial update
    host.set_plant_seasons({"p1": state_a, "p2": state_a})
    assert host._last_plant_seasons["p1"] == state_a
    assert host._last_plant_seasons["p2"] == state_a

    # QML has both
    seasons = host._root.property("plantSeasons").toVariant()
    assert "p1" in seasons and "p2" in seasons

    # Sparse update where only p2 changes:
    host.set_plant_seasons({"p1": state_a, "p2": state_b})
    assert host._last_plant_seasons["p1"] == state_a
    assert host._last_plant_seasons["p2"] == state_b

    # p1 state in QML is preserved, p2 is updated
    seasons2 = host._root.property("plantSeasons").toVariant()
    assert seasons2["p2"][4] == 1.0  # bloom

    # Clear resets host and QML states
    host.clear()
    assert len(host._last_plant_seasons) == 0
    assert len(host._root.property("plantSeasons").toVariant()) == 0
    assert len(host._root.property("seasonalParts").toVariant()) == 0
