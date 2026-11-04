"""Resolved supports must affect final, posed climbing wood (PR #593)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from open_garden_planner.core.plant_forge import (
    ForgeCache,
    enrich_climber_records,
    forge_record,
)
from open_garden_planner.core.scene3d import Material, Params, Record, Transform


def support_scene(
    offset: float = 45.0, *, rotation: float = 0.0, plant_rotation: float = 0.0,
    kind: str = "FENCE", base: float = 0.0,
) -> tuple[Record, Record]:
    """The same plant/support relationship, rigidly moved in the world."""
    angle = np.deg2rad(rotation)
    plant = Record(
        item_id="jasmine", kind="SHRUB", name="Jasmine", shape="circle",
        footprints=(((45.0, 0.0), (0.0, 45.0), (-45.0, 0.0), (0.0, -45.0)),),
        height_cm=210.0, material=Material(key="plant"),
        transform=Transform(320.0, -170.0, plant_rotation, base),
        parent_id="support" if kind == "TRELLIS" else None,
        params=Params({"sprite_species": "jasmine", "plant_category": "climbing_plant",
                       "radius_cm": 45.0, "seed": "same-plant"}),
    )
    support = Record(
        item_id="support", kind=kind, name="Support", shape="polyline", footprints=(),
        path=((-200.0, 0.0), (200.0, 0.0)), path_width_cm=10.0,
        height_cm=180.0, material=Material(key="fence"),
        transform=Transform(320.0 - np.sin(angle) * offset,
                            -170.0 + np.cos(angle) * offset, rotation),
    )
    return plant, support


def posed_positions(record: Record, parts: tuple, name: str | None = None) -> np.ndarray:
    points = np.concatenate([p.mesh.positions for p in parts if name is None or p.name == name])
    angle = np.deg2rad(record.transform.rotation_deg)
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    result = points.astype(float).copy()
    result[:, :2] = points[:, :2] @ rot.T + [record.transform.east_cm, record.transform.north_cm]
    result[:, 2] += record.transform.base_cm
    return result


@pytest.mark.parametrize("lod", [0, 1, 2])
@pytest.mark.parametrize("rotation,plant_rotation,kind", [
    (0.0, 0.0, "FENCE"), (67.0, 121.0, "FENCE"), (123.0, 37.0, "TRELLIS"),
])
def test_final_wood_touches_actual_support_and_keeps_plan_bounds(
    lod: int, rotation: float, plant_rotation: float, kind: str,
) -> None:
    plant, support = support_scene(rotation=rotation, plant_rotation=plant_rotation, kind=kind, base=18.0)
    enriched = enrich_climber_records([plant, support])[0]
    parts = forge_record(enriched, lod=lod, cache=None)
    wood = posed_positions(plant, parts, "wood")
    angle = np.deg2rad(rotation)
    normal = np.array([-np.sin(angle), np.cos(angle)])
    relative = wood[:, :2] - [plant.transform.east_cm, plant.transform.north_cm]
    depth = relative @ normal
    in_support = (depth >= 40.0) & (depth <= 50.0)
    below_support_top = wood[:, 2] <= support.height_cm
    assert np.count_nonzero(in_support & below_support_top) >= 4
    points = np.concatenate([p.mesh.positions for p in parts])
    assert points[:, 2].min() == pytest.approx(0.0, abs=1e-4)
    assert points[:, 2].max() == pytest.approx(210.0, abs=1e-3)
    assert np.hypot(points[:, 0], points[:, 1]).max() <= 45.0 * 1.04 + 1e-4
    assert max(np.ptp(points[:, 0]), np.ptp(points[:, 1])) >= 81.0


def test_opposite_supports_change_signature_and_mirror_training_even_when_unreachable() -> None:
    cache = ForgeCache(max_entries=16)
    results = []
    for offset in (98.0, -98.0):
        plant, support = support_scene(offset)
        enriched = enrich_climber_records([plant, support])[0]
        parts = forge_record(enriched, cache=cache)
        wood = posed_positions(plant, parts, "wood")
        results.append((enriched.params["climber_support"], wood[:, 1] + 170.0))
    assert results[0][0] != results[1][0]
    assert np.max(results[0][1]) > 35.0
    assert np.min(results[1][1]) < -35.0
    assert np.mean(results[0][1]) > 15.0
    assert np.mean(results[1][1]) < -15.0
    # A support beyond the recorded canopy is selected but contact is never invented.
    assert np.max(np.abs(results[0][1])) < 93.0


def test_support_move_changes_only_transient_geometry_inputs() -> None:
    plant, support = support_scene()
    before = enrich_climber_records([plant, support])[0]
    after = enrich_climber_records([plant, replace(support, transform=Transform(320, -215))])[0]
    assert before.params != after.params
    assert before.transform == after.transform == plant.transform
    assert before.height_cm == after.height_cm == plant.height_cm
    assert before.footprints == after.footprints == plant.footprints


def test_canvas_snapshot_to_final_forge_follows_fence_after_move(qtbot: object) -> None:
    from PyQt6.QtCore import QPointF

    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    scene = CanvasScene(1000, 1000)
    plant = CircleItem(400, 400, 45, object_type=ObjectType.SHRUB,
                       metadata={"height_cm": 210})
    plant.plant_species = "jasmine"
    scene.addItem(plant)
    fence = PolylineItem([QPointF(200, 445), QPointF(600, 445)], object_type=ObjectType.FENCE)
    fence.metadata["height_cm"] = 180
    scene.addItem(fence)
    medians = []
    for shift in (0, -90):
        fence.setPos(0, shift)
        raw = snapshot_records(scene, date(2026, 6, 21))
        records = {r.item_id: r for r in enrich_climber_records(raw.values())}
        rec = records[str(plant.item_id)]
        support = raw[str(fence.item_id)]
        wood = posed_positions(rec, forge_record(rec, cache=None), "wood")
        # Snapshot uses the scene frame's own Y convention. Measure both from
        # the actual posed support, rather than reconstructing canvas polarity.
        support_points = np.asarray(support.path)
        angle = np.deg2rad(support.transform.rotation_deg)
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        a, b = support_points @ rotation.T + [support.transform.east_cm, support.transform.north_cm]
        delta = b - a
        t = np.clip((wood[:, :2] - a) @ delta / np.dot(delta, delta), 0, 1)
        distance = np.linalg.norm(wood[:, :2] - a - t[:, None] * delta, axis=1)
        assert np.count_nonzero((distance < support.path_width_cm * 0.5) & (wood[:, 2] < 180)) > 4
        medians.append(np.median(wood[:, 1] - rec.transform.north_cm))
    assert medians[0] * medians[1] < 0
