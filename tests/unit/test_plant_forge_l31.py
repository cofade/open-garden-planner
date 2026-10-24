"""Unit tests for Plant Forge L3.1: core pipeline, broadleaf trees, LODs, golden meshes, and ForgeWorker (#387)."""

from __future__ import annotations

import ast
import colorsys
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.plant_art import (
    CATEGORIES,
    PALETTES,
    SPECIES,
    WHITE_BARK_SHADE,
    SpriteRef,
    palette_key,
    recipe_for,
)
from open_garden_planner.core.plant_forge import (
    LOD0,
    LOD0_MAX_DISTANCE_CM,
    LOD0_TRIANGLE_BUDGET,
    LOD1,
    LOD1_MAX_DISTANCE_CM,
    LOD1_TRIANGLE_BUDGET,
    LOD2,
    LOD2_TRIANGLE_BUDGET,
    PART_FOLIAGE,
    PART_WOOD,
    ForgeCache,
    forge_plant,
    forge_record,
    forge_species_plant,
    select_lod,
    silhouette_iou,
)
from open_garden_planner.core.scene3d import (
    Material,
    Params,
    Record,
    RecordingSink,
    Transform,
    verify_builder,
)
from open_garden_planner.ui.view3d.forge_worker import ForgeWorker

REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_DIR = REPO_ROOT / "src" / "open_garden_planner" / "core" / "plant_forge"
GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "plant_forge" / "forged_trees_golden.json"

CANOPY_SPRITES: tuple[SpriteRef, ...] = tuple(
    [SpriteRef("species", k) for k, r in sorted(SPECIES.items()) if r["a"] == "canopy"]
    + [SpriteRef("categories", k) for k, r in sorted(CATEGORIES.items()) if r["a"] == "canopy"]
)


def _circle_ring(radius_cm: float, n: int = 32) -> tuple[tuple[float, float], ...]:
    return tuple(
        (radius_cm * math.cos(2.0 * math.pi * i / n), radius_cm * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    )


def _tree_record(
    sprite: SpriteRef,
    height_cm: float = 420.0,
    radius_cm: float = 180.0,
    *,
    item_id: str = "tree-1",
    seed: int = 101,
    east_cm: float = 0.0,
    north_cm: float = 0.0,
) -> Record:
    return Record(
        item_id=item_id,
        kind="TREE",
        name=sprite.name,
        shape="circle",
        footprints=(_circle_ring(radius_cm),),
        height_cm=height_cm,
        transform=Transform(east_cm=east_cm, north_cm=north_cm),
        material=Material(key="tree"),
        params=Params(
            {
                "sprite_species": sprite.name if sprite.group == "species" else "",
                "plant_category": sprite.name if sprite.group == "categories" else "round_deciduous",
                "radius_cm": radius_cm,
                "seed": seed,
            }
        ),
    )


def _linear_to_srgb01(lin: np.ndarray) -> np.ndarray:
    c = np.clip(lin, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1.0 / 2.4)) - 0.055)


def _hue_deg(rgb01: np.ndarray) -> float:
    h, _s, _v = colorsys.rgb_to_hsv(float(rgb01[0]), float(rgb01[1]), float(rgb01[2]))
    return h * 360.0


class TestPlantForgeArchitecture:
    """Verify core/plant_forge stays strictly Qt-free."""

    def test_plant_forge_package_is_qt_free(self) -> None:
        py_files = sorted(FORGE_DIR.glob("*.py"))
        assert len(py_files) >= 7
        forbidden = {"PyQt6", "PySide6", "shiboken6"}
        for path in py_files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        assert top not in forbidden, f"{path.name} imports {alias.name}"
                elif isinstance(node, ast.ImportFrom) and node.module:
                    parts = node.module.split(".")
                    assert not (set(parts) & forbidden), f"{path.name} imports {node.module}"
                    assert "ui" not in parts, f"{path.name} imports UI module {node.module}"


class TestL31BroadleafTreesAndBudgets:
    """Truth, LOD budgets, no-clones, and palette hue gates across all 19 canopy recipes."""

    @pytest.mark.parametrize("sprite", CANOPY_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_dimensional_truth_and_verify_builder(self, sprite: SpriteRef) -> None:
        rec = _tree_record(sprite, height_cm=420.0, radius_cm=180.0, seed=101)
        parts = verify_builder(forge_record, rec, height_tolerance=0.03)
        part_names = {p.name for p in parts}
        assert PART_WOOD in part_names
        assert PART_FOLIAGE in part_names

        all_pos = np.concatenate([p.mesh.positions for p in parts], axis=0)
        z_min = float(all_pos[:, 2].min())
        z_max = float(all_pos[:, 2].max())
        span_x = float(all_pos[:, 0].max() - all_pos[:, 0].min())
        span_y = float(all_pos[:, 1].max() - all_pos[:, 1].min())
        max_span = max(span_x, span_y)

        assert z_min == pytest.approx(0.0, abs=1e-4)
        # Height within ±3 % gate
        assert abs(z_max - 420.0) <= 0.03 * 420.0
        # Spread within ±10 % gate
        assert abs(max_span - 360.0) <= 0.10 * 360.0

        # Wind sway convention: wood uv == 0, foliage uv.x rises from 0 to 1
        for p in parts:
            if p.name == PART_WOOD:
                assert float(np.abs(p.mesh.uvs).max()) == 0.0
            elif p.name == PART_FOLIAGE:
                assert float(p.mesh.uvs[:, 0].max()) == pytest.approx(1.0, abs=0.02)
                assert float(p.mesh.uvs[:, 1].min()) >= 0.0
                assert float(p.mesh.uvs[:, 1].max()) < 1.0

    @pytest.mark.parametrize("sprite", CANOPY_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_lod_triangle_caps_and_ordering(self, sprite: SpriteRef) -> None:
        p0 = forge_plant(sprite, 420.0, 180.0, seed=101, lod=LOD0, cache=None)
        p1 = forge_plant(sprite, 420.0, 180.0, seed=101, lod=LOD1, cache=None)
        p2 = forge_plant(sprite, 420.0, 180.0, seed=101, lod=LOD2, cache=None)

        t0 = sum(p.mesh.triangle_count for p in p0)
        t1 = sum(p.mesh.triangle_count for p in p1)
        t2 = sum(p.mesh.triangle_count for p in p2)

        assert 0 < t2 <= LOD2_TRIANGLE_BUDGET == 800
        assert t2 < t1 <= LOD1_TRIANGLE_BUDGET == 6_000
        assert t1 < t0 <= LOD0_TRIANGLE_BUDGET == 25_000

    @pytest.mark.parametrize("sprite", CANOPY_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_no_clones_across_seeds(self, sprite: SpriteRef) -> None:
        p_a = forge_plant(sprite, 420.0, 180.0, seed=101, lod=LOD0, cache=None)
        p_b = forge_plant(sprite, 420.0, 180.0, seed=202, lod=LOD0, cache=None)
        iou = silhouette_iou(p_a, p_b, 420.0, 180.0)
        assert iou < 0.95, f"{sprite}: silhouette IoU {iou:.4f} >= 0.95"

    @pytest.mark.parametrize("sprite", CANOPY_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_foliage_hue_and_albedo_match_2d_palette(self, sprite: SpriteRef) -> None:
        parts = forge_plant(sprite, 420.0, 180.0, seed=101, lod=LOD0, cache=None)
        foliage = next(p.mesh for p in parts if p.name == PART_FOLIAGE)
        srgb = _linear_to_srgb01(foliage.colors[:, :3].astype(np.float64))

        # Albedo range [40..240] in 0..255 sRGB luma
        luma = srgb @ np.array([0.2126, 0.7152, 0.0722]) * 255.0
        assert float(luma.min()) >= 40.0
        assert float(luma.max()) <= 240.0

        pal = PALETTES[palette_key(recipe_for(sprite))]
        anchor_hues = [
            _hue_deg(
                np.array(
                    [int(pal[k][1:3], 16), int(pal[k][3:5], 16), int(pal[k][5:7], 16)],
                    dtype=np.float64,
                )
                / 255.0
            )
            for k in ("t0", "t1", "b0", "b1")
        ]
        centre = anchor_hues[0]
        anchor_offsets = [(h - centre + 180.0) % 360.0 - 180.0 for h in anchor_hues]
        mean_hue = _hue_deg(srgb.mean(axis=0))
        mean_offset = (mean_hue - centre + 180.0) % 360.0 - 180.0
        assert min(anchor_offsets) - 5.0 <= mean_offset <= max(anchor_offsets) + 5.0

    def test_birch_white_bark_uses_shade_guard(self) -> None:
        parts = forge_plant(SpriteRef("species", "birch"), 500.0, 180.0, seed=7, lod=LOD0, cache=None)
        wood = next(p.mesh for p in parts if p.name == PART_WOOD)
        assert pytest.approx(0.7) == WHITE_BARK_SHADE
        # Shaded birch bark in linear light must stay well below 1.0 so low sun never clips
        assert float(wood.colors[:, :3].max()) <= 0.65

    def test_select_lod_distance_thresholds(self) -> None:
        assert select_lod(0.0) == LOD0
        assert select_lod(LOD0_MAX_DISTANCE_CM) == LOD0
        assert select_lod(LOD0_MAX_DISTANCE_CM + 1.0) == LOD1
        assert select_lod(LOD1_MAX_DISTANCE_CM) == LOD1
        assert select_lod(LOD1_MAX_DISTANCE_CM + 1.0) == LOD2

    def test_forge_species_plant_resolves_whole_word(self) -> None:
        parts = forge_species_plant(
            "TREE",
            "Apple Tree",
            "Malus domestica",
            "fruit_tree",
            height_cm=380.0,
            radius_cm=160.0,
            seed=42,
            lod=LOD0,
            cache=None,
        )
        assert any(p.name == PART_FOLIAGE for p in parts)


class TestL31GoldenMeshesAndPerformance:
    """Verify the 40 golden tree meshes (10 species × 2 seeds × 2 stages) and ≤ 150 ms median."""

    def test_40_golden_tree_meshes_match(self) -> None:
        payload = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        assert payload["count"] == 40
        entries = payload["entries"]
        assert len(entries) == 40

        for entry in entries:
            ref = SpriteRef("species", entry["species"])
            parts = forge_plant(
                ref,
                float(entry["height_cm"]),
                float(entry["radius_cm"]),
                seed=int(entry["seed"]),
                lod=LOD0,
                cache=None,
            )
            assert len(parts) == len(entry["parts"])
            for p, expected in zip(parts, entry["parts"], strict=True):
                m = p.mesh
                bmin, bmax = m.bounds()
                idx_sha = hashlib.sha256(m.indices.tobytes()).hexdigest()[:16]
                assert p.name == expected["name"]
                assert p.material_kind == expected["material_kind"]
                assert m.vertex_count == expected["vertex_count"]
                assert m.triangle_count == expected["triangle_count"]
                assert idx_sha == expected["indices_sha16"]
                np.testing.assert_allclose(bmin, expected["bounds_min"], atol=1e-3)
                np.testing.assert_allclose(bmax, expected["bounds_max"], atol=1e-3)
                np.testing.assert_allclose(m.positions.mean(axis=0), expected["mean_pos"], atol=1e-3)
                np.testing.assert_allclose(m.colors.mean(axis=0), expected["mean_col"], atol=1e-4)

    @pytest.mark.perf
    def test_median_build_time_under_150ms(self) -> None:
        durations_ms: list[float] = []
        for ref in CANOPY_SPRITES:
            t0 = time.perf_counter()
            forge_plant(ref, 420.0, 180.0, seed=303, lod=LOD0, cache=None)
            t1 = time.perf_counter()
            durations_ms.append((t1 - t0) * 1000.0)
        median_ms = float(np.median(durations_ms))
        assert median_ms <= 150.0, f"Median cold build time {median_ms:.2f} ms > 150 ms"


class TestForgeCacheAndWorker:
    """Verify ForgeCache LRU behaviour and ForgeWorker visible-first + latest-wins ordering."""

    def test_forge_cache_lru_eviction(self) -> None:
        cache = ForgeCache(max_entries=2)
        ref = SpriteRef("species", "oak")
        p1 = forge_plant(ref, 400.0, 180.0, seed=1, lod=LOD2, cache=cache)
        p2 = forge_plant(ref, 400.0, 180.0, seed=2, lod=LOD2, cache=cache)
        assert len(cache) == 2
        assert cache.misses == 2
        # Hit seed=1 so seed=2 becomes LRU
        assert forge_plant(ref, 400.0, 180.0, seed=1, lod=LOD2, cache=cache) == p1
        assert cache.hits == 1
        # Adding seed=3 evicts seed=2
        forge_plant(ref, 400.0, 180.0, seed=3, lod=LOD2, cache=cache)
        assert len(cache) == 2
        assert cache.get(("species", "oak", 2, LOD2, 40000, 18000, "")) is None
        assert cache.get(("species", "oak", 1, LOD2, 40000, 18000, "")) == p1
        _ = p2

    def test_forge_worker_orders_visible_plants_first(self) -> None:
        sink = RecordingSink()
        worker = ForgeWorker(sink, cache=ForgeCache(max_entries=16))

        # Camera at origin looking North (+Y):
        # - behind_close is at (0, -200) -> behind camera (dist 200)
        # - front_far is at (0, +900) -> in front of camera (dist 900)
        # - front_near is at (0, +300) -> in front of camera (dist 300)
        ref = SpriteRef("species", "apple_tree")
        r_behind = _tree_record(ref, item_id="behind_close", east_cm=0.0, north_cm=-200.0)
        r_far = _tree_record(ref, item_id="front_far", east_cm=0.0, north_cm=900.0)
        r_near = _tree_record(ref, item_id="front_near", east_cm=0.0, north_cm=300.0)

        sink.begin()
        for r in (r_behind, r_far, r_near):
            sink.add(r.item_id, (), r.transform, r.material)
        sink.commit()

        worker.submit_snapshot(
            [r_behind, r_far, r_near],
            camera_pos=(0.0, 0.0, 170.0),
            camera_forward=(0.0, 1.0, 0.0),
            force_lod=LOD2,
        )
        assert worker.pending_order() == ["front_near", "front_far", "behind_close"]

        upgraded_first = worker.step(max_items=1)
        assert upgraded_first == ["front_near"]
        upgraded_rest = worker.drain()
        assert upgraded_rest == ["front_far", "behind_close"]
        assert worker.pending_count == 0

    def test_forge_worker_latest_wins_supersedes_stale_records_and_completions(self) -> None:
        sink = RecordingSink()
        worker = ForgeWorker(sink, cache=ForgeCache(max_entries=16))
        ref = SpriteRef("species", "oak")

        r_v1 = _tree_record(ref, height_cm=300.0, radius_cm=140.0, item_id="oak-1", seed=10)
        r_v2 = _tree_record(ref, height_cm=480.0, radius_cm=210.0, item_id="oak-1", seed=10)

        sink.begin()
        sink.add("oak-1", (), r_v1.transform, r_v1.material)
        sink.commit()

        worker.submit_record(r_v1, lod=LOD2)
        stale_sig = r_v1.geometry_sig
        stale_parts = forge_record(r_v1, lod=LOD2, cache=None)

        # Supersede with v2 before v1 finishes
        worker.submit_record(r_v2, lod=LOD2)
        assert worker.pending_count == 1

        # Late completion of v1 must be rejected ("latest wins")
        assert worker.apply_completed("oak-1", stale_sig, LOD2, stale_parts) is False
        assert sink.item("oak-1").parts == ()

        # Stepping worker now builds and applies v2 (height 480 cm)
        assert worker.step(max_items=1) == ["oak-1"]
        applied_parts = sink.item("oak-1").parts
        assert len(applied_parts) > 0
        top_z = max(float(p.mesh.positions[:, 2].max()) for p in applied_parts)
        assert top_z == pytest.approx(480.0, rel=0.01)
