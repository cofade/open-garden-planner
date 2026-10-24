"""End-to-end integration tests for Phase 17 L3 "Plant Forge" (#387).

Exercises the complete pipeline:
- Live `CanvasScene` items (trees, shrubs, perennials, trellises, fences) ->
  `snapshot_records` -> `SceneSync` / `ForgeWorker` -> `RecordingSink`;
- All 13 plant archetypes forged from the shared 2D recipe table (`core.plant_art`);
- Climber support resolution (`TRELLIS` parent -> nearest `FENCE`/`PERGOLA` <= 50 cm -> bean poles);
- `ForgeWorker` priority ordering (`visible plants first, latest wins`) and LOD switching;
- Seasonal phenology date scrubbing (`core.phenology`) across Northern and Southern hemispheres;
- L3.6 cold-vs-warm build latency verification confirming in-memory `ForgeCache` suffices without disk cache.
"""

from __future__ import annotations

import datetime
import time

from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plant_art import ARCHETYPES, CATEGORIES, SPECIES, SpriteRef
from open_garden_planner.core.plant_forge import (
    LOD0,
    LOD1,
    PARAM_CLIMBER_SUPPORT,
    PART_ACCENTS,
    PART_FOLIAGE,
    PART_WOOD,
    SUPPORT_BEAN_POLES,
    SUPPORT_FENCE,
    SUPPORT_TRELLIS,
    ForgeCache,
    enrich_climber_records,
    forge_plant,
    register_forged_plants,
)
from open_garden_planner.core.scene3d import RecordingSink, SceneSync
from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d.forge_worker import ForgeWorker
from open_garden_planner.ui.view3d.snapshot import snapshot_records


def _add_plant_circle(
    scene: CanvasScene,
    object_type: ObjectType,
    scene_x: float,
    scene_y: float,
    radius_cm: float,
    height_cm: float,
    species_name: str,
    *,
    parent_bed_id: str | None = None,
) -> CircleItem:
    item = CircleItem(
        scene_x,
        scene_y,
        radius_cm,
        object_type=object_type,
        metadata={
            "height_cm": height_cm,
            "plant_species": {"common_name": species_name},
        },
    )
    item.plant_species = species_name
    if parent_bed_id is not None:
        item.parent_bed_id = parent_bed_id
    scene.addItem(item)
    return item


class TestPlantForgeEndToEndIntegration:
    """End-to-end integration workflow from CanvasScene through snapshot_records, SceneSync, and ForgeWorker."""

    def test_canvas_scene_to_forged_3d_scene_sync(self, qtbot: object) -> None:
        _ = qtbot
        scene = CanvasScene(2000, 2000)

        # Representative species covering all major families + seasonal accents
        _add_plant_circle(scene, ObjectType.TREE, 300.0, 300.0, 160.0, 400.0, "apple_tree")
        _add_plant_circle(scene, ObjectType.TREE, 700.0, 300.0, 140.0, 480.0, "pine")
        _add_plant_circle(scene, ObjectType.SHRUB, 300.0, 700.0, 65.0, 150.0, "lilac")
        _add_plant_circle(scene, ObjectType.PERENNIAL, 550.0, 700.0, 35.0, 140.0, "sunflower")
        _add_plant_circle(scene, ObjectType.PERENNIAL, 750.0, 700.0, 22.0, 35.0, "radish")
        _add_plant_circle(scene, ObjectType.PERENNIAL, 950.0, 700.0, 28.0, 65.0, "dill")

        records = snapshot_records(scene, datetime.date(2026, 6, 15))
        assert len(records) == 6

        sink = RecordingSink()
        registry = production_registry()
        register_forged_plants(registry, lod=LOD1)
        sync = SceneSync(sink, registry, validate=True)

        diff = sync.apply(records)
        assert len(diff.added) == 6
        assert len(sync.failures) == 0
        assert sink.state() == sync.expected_state()

        for item_id in records:
            parts = sink.item(item_id).parts
            names = {p.name for p in parts}
            assert PART_WOOD in names
            assert PART_FOLIAGE in names

        # Apple tree, lilac, sunflower, radish, dill all have seasonal accents at LOD1
        apple_id = next(k for k, r in records.items() if r.params.get("sprite_species") == "apple_tree")
        assert PART_ACCENTS in {p.name for p in sink.item(apple_id).parts}

    def test_climber_support_end_to_end_on_canvas(self, qtbot: object) -> None:
        _ = qtbot
        scene = CanvasScene(2000, 2000)

        # 1. Trellis parent with linked clematis
        trellis = RectangleItem(
            100.0,
            190.0,
            160.0,
            20.0,
            object_type=ObjectType.TRELLIS,
            metadata={"height_cm": 200.0},
        )
        scene.addItem(trellis)
        clematis = _add_plant_circle(
            scene,
            ObjectType.SHRUB,
            180.0,
            200.0,
            40.0,
            190.0,
            "clematis",
            parent_bed_id=str(trellis.item_id),
        )

        # 2. Fence with nearby jasmine (within 50 cm)
        fence = PolylineItem(
            [QPointF(400.0, 600.0), QPointF(800.0, 600.0)],
            object_type=ObjectType.FENCE,
        )
        fence.metadata["height_cm"] = 180.0
        scene.addItem(fence)
        jasmine = _add_plant_circle(
            scene,
            ObjectType.SHRUB,
            600.0,
            660.0,  # 60 cm from fence centre, radius 40 cm -> ~15 cm gap <= 50 cm
            40.0,
            175.0,
            "jasmine",
        )

        # 3. Standalone bean climber far from structures -> bean poles
        bean = _add_plant_circle(
            scene,
            ObjectType.PERENNIAL,
            1400.0,
            1400.0,
            35.0,
            180.0,
            "bean",
        )

        raw_records = snapshot_records(scene, datetime.date(2026, 7, 1))
        enriched = {r.item_id: r for r in enrich_climber_records(raw_records.values())}

        assert enriched[str(clematis.item_id)].params[PARAM_CLIMBER_SUPPORT][0] == SUPPORT_TRELLIS
        assert enriched[str(jasmine.item_id)].params[PARAM_CLIMBER_SUPPORT][0] == SUPPORT_FENCE
        assert enriched[str(bean.item_id)].params[PARAM_CLIMBER_SUPPORT][0] == SUPPORT_BEAN_POLES

    def test_forge_worker_progressive_upgrade_and_phenology_scrub(self, qtbot: object) -> None:
        _ = qtbot
        scene = CanvasScene(2000, 2000)

        p_near = _add_plant_circle(scene, ObjectType.TREE, 200.0, 250.0, 150.0, 380.0, "cherry_tree")
        p_far = _add_plant_circle(scene, ObjectType.TREE, 200.0, 1600.0, 150.0, 380.0, "oak")
        p_ever = _add_plant_circle(scene, ObjectType.TREE, 600.0, 400.0, 130.0, 450.0, "spruce")

        records = snapshot_records(scene, datetime.date(2026, 5, 10))
        sink = RecordingSink()
        sync = SceneSync(sink, production_registry())
        sync.apply(records)

        worker = ForgeWorker(sink, cache=ForgeCache(max_entries=32))
        near_rec = records[str(p_near.item_id)]
        worker.submit_snapshot(
            records.values(),
            camera_pos=(near_rec.transform.east_cm, near_rec.transform.north_cm, 170.0),
            camera_forward=(0.0, -1.0, 0.0),
        )

        order = worker.pending_order()
        assert order[0] == str(p_near.item_id)
        upgraded = worker.drain()
        assert len(upgraded) == 3

        # Scrub across winter and summer in both hemispheres without rebuilding geometry
        uploads_before = len([c for c in sink.calls if c.op == "replace_geometry"])
        winter_nh = worker.scrub_date(datetime.date(2026, 1, 15), latitude_deg=52.0)
        winter_sh = worker.scrub_date(datetime.date(2026, 7, 15), latitude_deg=-35.0)
        uploads_after = len([c for c in sink.calls if c.op == "replace_geometry"])

        assert uploads_after == uploads_before
        assert winter_nh[str(p_near.item_id)].leaf_density == 0.0
        assert winter_nh[str(p_far.item_id)].leaf_density == 0.0
        assert winter_nh[str(p_ever.item_id)].leaf_density == 1.0
        assert winter_sh[str(p_near.item_id)].leaf_density == 0.0
        assert winter_sh[str(p_ever.item_id)].leaf_density == 1.0

    def test_l36_all_13_archetypes_and_cache_latency_budget(self) -> None:
        """L3.6 gate: verify all 13 archetypes build cleanly and warm cache hits take < 1 ms."""
        cache = ForgeCache(max_entries=256)
        rep_by_arch: dict[str, SpriteRef] = {}
        for name, rec in sorted(SPECIES.items()):
            rep_by_arch.setdefault(str(rec["a"]), SpriteRef("species", name))
        for name, rec in sorted(CATEGORIES.items()):
            rep_by_arch.setdefault(str(rec["a"]), SpriteRef("categories", name))

        assert set(rep_by_arch.keys()) == ARCHETYPES

        t_cold_start = time.perf_counter()
        for sprite in rep_by_arch.values():
            parts = forge_plant(sprite, 160.0, 65.0, seed=77, lod=LOD0, cache=cache)
            assert len(parts) >= 2
            for part in parts:
                part.validate()
        cold_ms = (time.perf_counter() - t_cold_start) * 1000.0

        t_warm_start = time.perf_counter()
        for sprite in rep_by_arch.values():
            parts = forge_plant(sprite, 160.0, 65.0, seed=77, lod=LOD0, cache=cache)
            assert len(parts) >= 2
        warm_ms = (time.perf_counter() - t_warm_start) * 1000.0

        # Cold build of all 13 archetypes at LOD0 well under 1.5s; warm cache under 5 ms
        assert cold_ms < 1500.0
        assert warm_ms < 5.0
        assert cache.hits == len(ARCHETYPES)
