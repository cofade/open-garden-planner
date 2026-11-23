"""Unit tests for Plant Forge L3.2: conifers (tiered whorls), palms, shrubs, and leaf-hull hedges (#387)."""

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
    traits_for,
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
    build_forged_palm,
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

L32_ARCHETYPES = frozenset({"conifer", "palm", "mound", "hedge"})

L32_SPRITES: tuple[SpriteRef, ...] = tuple(
    [SpriteRef("species", k) for k, r in sorted(SPECIES.items()) if r["a"] in L32_ARCHETYPES]
    + [SpriteRef("categories", k) for k, r in sorted(CATEGORIES.items()) if r["a"] in L32_ARCHETYPES]
)


def _circle_ring(radius_cm: float, n: int = 32) -> tuple[tuple[float, float], ...]:
    return tuple(
        (radius_cm * math.cos(2.0 * math.pi * i / n), radius_cm * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    )


def _size_for_archetype(archetype: str) -> tuple[float, float, str]:
    if archetype == "conifer":
        return 520.0, 140.0, "TREE"
    if archetype == "palm":
        return 480.0, 160.0, "TREE"
    if archetype == "hedge":
        return 160.0, 75.0, "SHRUB"
    return 140.0, 65.0, "SHRUB"


def _linear_to_srgb01(lin: np.ndarray) -> np.ndarray:
    c = np.clip(lin, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1.0 / 2.4)) - 0.055)


def _hue_deg(rgb01: np.ndarray) -> float:
    h, _s, _v = colorsys.rgb_to_hsv(float(rgb01[0]), float(rgb01[1]), float(rgb01[2]))
    return h * 360.0


class TestL32ConifersPalmsShrubsHedges:
    """Verify all 52 conifer, palm, shrub (mound), and hedge recipes."""

    def test_l32_recipe_coverage(self) -> None:
        archetypes_seen = {recipe_for(s)["a"] for s in L32_SPRITES}
        assert archetypes_seen == L32_ARCHETYPES
        assert len(L32_SPRITES) == 58

    @pytest.mark.parametrize("sprite", L32_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_dimensional_truth_and_verify_builder(self, sprite: SpriteRef) -> None:
        arch = str(recipe_for(sprite)["a"])
        h, r, kind = _size_for_archetype(arch)
        rec = Record(
            item_id=f"{sprite.group}-{sprite.name}",
            kind=kind,
            name=sprite.name,
            shape="circle",
            footprints=(_circle_ring(r),),
            height_cm=h,
            transform=Transform(),
            material=Material(key="plant"),
            params=Params(
                {
                    "sprite_species": sprite.name if sprite.group == "species" else "",
                    "plant_category": sprite.name if sprite.group == "categories" else "shrub",
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

    def test_a_scots_pine_is_an_umbrella_not_a_spruce_cone(self) -> None:
        """#960: a long bare trunk carrying a broad, flat-topped head."""
        traits = traits_for(SpriteRef("species", "pine"))
        assert traits.crown.shape == "umbrella"
        assert traits.crown.trunk_share > 0.5
        parts = forge_plant(SpriteRef("species", "pine"), 480.0, 160.0, seed=101,
                            lod=LOD0, cache=None)
        foliage = next(part for part in parts if part.name == PART_FOLIAGE)
        z = foliage.mesh.positions[:, 2]
        assert float(z.min()) > 0.35 * 480.0, "the crown begins above a long bare trunk"
        bands = []
        for low, high in ((0.4, 0.6), (0.6, 0.8), (0.8, 0.95)):
            band = foliage.mesh.positions[(z >= low * 480.0) & (z < high * 480.0)]
            bands.append(float(np.ptp(band[:, 0])) if len(band) else 0.0)
        assert bands[1] >= 0.8 * bands[0], "the head stays broad instead of tapering at once"
        wood = next(part for part in parts if part.name == PART_WOOD).mesh.positions
        for low, high in ((0.5, 0.7), (0.7, 0.9)):
            branch = wood[(wood[:, 2] >= low * 480.0) & (wood[:, 2] < high * 480.0)]
            needles = foliage.mesh.positions[
                (foliage.mesh.positions[:, 2] >= low * 480.0)
                & (foliage.mesh.positions[:, 2] < high * 480.0)]
            assert len(branch) and len(needles)
            assert (np.hypot(branch[:, 0], branch[:, 1]).max()
                    <= np.hypot(needles[:, 0], needles[:, 1]).max()), (
                "the branch wood stays inside the needle spray, not outside it")

    def test_a_dwarf_palm_is_trunkless_and_a_tall_palm_is_not(self) -> None:
        """#949: the trunk height follows the plant, not one 0.64-trunk-height look,
        and the trunk base always stays grounded at z = 0 across all LODs."""
        palm = SpriteRef("categories", "palm")
        traits = traits_for(palm)
        tall = build_forged_palm(traits, 480.0, 160.0, seed=101, lod=LOD0)
        dwarf = build_forged_palm(traits, 90.0, 85.0, seed=101, lod=LOD0)

        def foliage_height(parts: tuple) -> tuple[float, float]:
            foliage = next(part for part in parts if part.name == PART_FOLIAGE)
            z = foliage.mesh.positions[:, 2]
            return float(z.min()), float(z.max())

        tall_low, tall_high = foliage_height(tall)
        dwarf_low, dwarf_high = foliage_height(dwarf)
        assert tall_low > 0.45 * 480.0, "the tall windmill palm keeps its bare trunk"
        assert dwarf_low < 0.25 * 90.0, "the dwarf's fronds begin near the ground"
        assert dwarf_high <= 90.0 + 1e-3 and tall_high <= 480.0 + 1e-3
        for height, radius in ((90.0, 85.0), (150.0, 120.0), (480.0, 160.0)):
            for lod in (LOD0, LOD1, LOD2):
                parts = build_forged_palm(traits, height, radius, seed=101, lod=lod)
                wood = next(part for part in parts if part.name == PART_WOOD)
                assert float(wood.mesh.positions[:, 2].min()) == pytest.approx(0.0, abs=1e-3), (
                    height, radius, lod)

    @pytest.mark.parametrize("sprite", L32_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_lod_triangle_caps_and_ordering(self, sprite: SpriteRef) -> None:
        arch = str(recipe_for(sprite)["a"])
        h, r, _kind = _size_for_archetype(arch)
        p0 = forge_plant(sprite, h, r, seed=101, lod=LOD0, cache=None)
        p1 = forge_plant(sprite, h, r, seed=101, lod=LOD1, cache=None)
        p2 = forge_plant(sprite, h, r, seed=101, lod=LOD2, cache=None)

        t0 = sum(p.mesh.triangle_count for p in p0)
        t1 = sum(p.mesh.triangle_count for p in p1)
        t2 = sum(p.mesh.triangle_count for p in p2)

        assert 0 < t2 <= LOD2_TRIANGLE_BUDGET == 800
        assert t2 < t1 <= LOD1_TRIANGLE_BUDGET == 6_000
        assert t1 < t0 <= LOD0_TRIANGLE_BUDGET == 25_000

    @pytest.mark.parametrize("sprite", L32_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_no_clones_across_seeds(self, sprite: SpriteRef) -> None:
        arch = str(recipe_for(sprite)["a"])
        h, r, _kind = _size_for_archetype(arch)
        p_a = forge_plant(sprite, h, r, seed=101, lod=LOD0, cache=None)
        p_b = forge_plant(sprite, h, r, seed=202, lod=LOD0, cache=None)
        iou = silhouette_iou(p_a, p_b, h, r)
        assert iou < 0.95, f"{sprite} ({arch}): silhouette IoU {iou:.4f} >= 0.95"

    @pytest.mark.parametrize("sprite", L32_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_foliage_hue_and_albedo(self, sprite: SpriteRef) -> None:
        arch = str(recipe_for(sprite)["a"])
        h, r, _kind = _size_for_archetype(arch)
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
        for sprite in L32_SPRITES:
            arch = str(recipe_for(sprite)["a"])
            h, r, _kind = _size_for_archetype(arch)
            t0 = time.perf_counter()
            forge_plant(sprite, h, r, seed=303, lod=LOD0, cache=None)
            t1 = time.perf_counter()
            durations_ms.append((t1 - t0) * 1000.0)
        median_ms = float(np.median(durations_ms))
        assert median_ms <= 150.0, f"Median cold build time {median_ms:.2f} ms > 150 ms"
