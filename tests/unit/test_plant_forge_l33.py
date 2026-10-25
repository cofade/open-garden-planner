"""Unit tests for Plant Forge L3.3: rosettes, grasses, pinnate/feathery leaves, alliums, heads, ground covers, and flowers (#387)."""

from __future__ import annotations

import colorsys
import math
import time

import numpy as np
import pytest

from open_garden_planner.core.plant_art import (
    CATEGORIES,
    PALETTES,
    SPECIES,
    SpriteRef,
    palette_key,
    recipe_for,
)
from open_garden_planner.core.plant_forge import (
    LOD0,
    LOD0_TRIANGLE_BUDGET,
    LOD1,
    LOD1_TRIANGLE_BUDGET,
    LOD2,
    LOD2_TRIANGLE_BUDGET,
    PART_FOLIAGE,
    PART_WOOD,
    forge_plant,
    forge_record,
    silhouette_iou,
)
from open_garden_planner.core.scene3d import (
    Material,
    Params,
    Record,
    Transform,
    verify_builder,
)

L33_ARCHETYPES = frozenset({"rosette", "grass", "feathery", "allium", "head", "ground", "flower"})

L33_SPRITES: tuple[SpriteRef, ...] = tuple(
    [SpriteRef("species", k) for k, r in sorted(SPECIES.items()) if r["a"] in L33_ARCHETYPES]
    + [SpriteRef("categories", k) for k, r in sorted(CATEGORIES.items()) if r["a"] in L33_ARCHETYPES]
)


def _circle_ring(radius_cm: float, n: int = 32) -> tuple[tuple[float, float], ...]:
    return tuple(
        (radius_cm * math.cos(2.0 * math.pi * i / n), radius_cm * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    )


def _size_for_archetype(archetype: str) -> tuple[float, float]:
    if archetype == "rosette":
        return 35.0, 22.0
    if archetype == "grass":
        return 110.0, 40.0
    if archetype == "feathery":
        return 65.0, 30.0
    if archetype == "allium":
        return 60.0, 18.0
    if archetype == "head":
        return 55.0, 30.0
    if archetype == "ground":
        return 22.0, 45.0
    return 140.0, 35.0


def _linear_to_srgb01(lin: np.ndarray) -> np.ndarray:
    c = np.clip(lin, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1.0 / 2.4)) - 0.055)


def _hue_deg(rgb01: np.ndarray) -> float:
    h, _s, _v = colorsys.rgb_to_hsv(float(rgb01[0]), float(rgb01[1]), float(rgb01[2]))
    return h * 360.0


class TestL33HerbaceousArchetypes:
    """Verify all 7 herbaceous archetypes (rosette, grass, feathery, allium, head, ground, flower)."""

    def test_l33_recipe_coverage(self) -> None:
        archetypes_seen = {recipe_for(s)["a"] for s in L33_SPRITES}
        assert archetypes_seen == L33_ARCHETYPES
        assert len(L33_SPRITES) == 39

    @pytest.mark.parametrize("sprite", L33_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_dimensional_truth_and_verify_builder(self, sprite: SpriteRef) -> None:
        arch = str(recipe_for(sprite)["a"])
        h, r = _size_for_archetype(arch)
        rec = Record(
            item_id=f"{sprite.group}-{sprite.name}",
            kind="PERENNIAL",
            name=sprite.name,
            shape="circle",
            footprints=(_circle_ring(r),),
            height_cm=h,
            transform=Transform(),
            material=Material(key="plant"),
            params=Params(
                {
                    "sprite_species": sprite.name if sprite.group == "species" else "",
                    "plant_category": sprite.name if sprite.group == "categories" else "rosette",
                    "radius_cm": r,
                    "seed": 101,
                }
            ),
        )
        parts = verify_builder(forge_record, rec, height_tolerance=0.03)
        names = {p.name for p in parts}
        assert PART_WOOD in names
        assert PART_FOLIAGE in names

        all_pos = np.concatenate([p.mesh.positions for p in parts], axis=0)
        z_min = float(all_pos[:, 2].min())
        z_max = float(all_pos[:, 2].max())
        span_x = float(all_pos[:, 0].max() - all_pos[:, 0].min())
        span_y = float(all_pos[:, 1].max() - all_pos[:, 1].min())
        max_span = max(span_x, span_y)

        assert z_min == pytest.approx(0.0, abs=1e-4)
        assert abs(z_max - h) <= 0.03 * h
        assert abs(max_span - 2.0 * r) <= 0.10 * (2.0 * r)

    @pytest.mark.parametrize("sprite", L33_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_lod_triangle_caps_and_ordering(self, sprite: SpriteRef) -> None:
        arch = str(recipe_for(sprite)["a"])
        h, r = _size_for_archetype(arch)
        p0 = forge_plant(sprite, h, r, seed=101, lod=LOD0, cache=None)
        p1 = forge_plant(sprite, h, r, seed=101, lod=LOD1, cache=None)
        p2 = forge_plant(sprite, h, r, seed=101, lod=LOD2, cache=None)

        t0 = sum(p.mesh.triangle_count for p in p0)
        t1 = sum(p.mesh.triangle_count for p in p1)
        t2 = sum(p.mesh.triangle_count for p in p2)

        assert 0 < t2 <= LOD2_TRIANGLE_BUDGET == 800
        assert t2 < t1 <= LOD1_TRIANGLE_BUDGET == 6_000
        assert t1 < t0 <= LOD0_TRIANGLE_BUDGET == 25_000

    @pytest.mark.parametrize("sprite", L33_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_no_clones_across_seeds(self, sprite: SpriteRef) -> None:
        arch = str(recipe_for(sprite)["a"])
        h, r = _size_for_archetype(arch)
        p_a = forge_plant(sprite, h, r, seed=101, lod=LOD0, cache=None)
        p_b = forge_plant(sprite, h, r, seed=202, lod=LOD0, cache=None)
        iou = silhouette_iou(p_a, p_b, h, r)
        assert iou < 0.95, f"{sprite} ({arch}): silhouette IoU {iou:.4f} >= 0.95"

    @pytest.mark.parametrize("sprite", L33_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_foliage_hue_and_albedo(self, sprite: SpriteRef) -> None:
        arch = str(recipe_for(sprite)["a"])
        h, r = _size_for_archetype(arch)
        parts = forge_plant(sprite, h, r, seed=101, lod=LOD0, cache=None)
        foliage = next(p.mesh for p in parts if p.name == PART_FOLIAGE)
        srgb = _linear_to_srgb01(foliage.colors[:, :3].astype(np.float64))

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
        anchor_offsets = [(ah - centre + 180.0) % 360.0 - 180.0 for ah in anchor_hues]
        mean_hue = _hue_deg(srgb.mean(axis=0))
        mean_offset = (mean_hue - centre + 180.0) % 360.0 - 180.0
        assert min(anchor_offsets) - 5.0 <= mean_offset <= max(anchor_offsets) + 5.0

    @pytest.mark.perf
    def test_median_build_time_under_150ms(self) -> None:
        durations_ms: list[float] = []
        for sprite in L33_SPRITES:
            arch = str(recipe_for(sprite)["a"])
            h, r = _size_for_archetype(arch)
            t0 = time.perf_counter()
            forge_plant(sprite, h, r, seed=303, lod=LOD0, cache=None)
            t1 = time.perf_counter()
            durations_ms.append((t1 - t0) * 1000.0)
        median_ms = float(np.median(durations_ms))
        assert median_ms <= 150.0, f"Median cold build time {median_ms:.2f} ms > 150 ms"

