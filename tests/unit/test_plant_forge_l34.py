"""Unit tests for Plant Forge L3.4: climbers on TRELLIS parent, nearest fence/pergola (≤ 50 cm), or bean poles (#387)."""

from __future__ import annotations

import colorsys
import dataclasses
import math
import time

import numpy as np
import pytest

from open_garden_planner.core.plant_art import (
    ARCHETYPES,
    CATEGORIES,
    PALETTES,
    SPECIES,
    SpriteRef,
    palette_key,
    recipe_for,
)
from open_garden_planner.core.plant_forge import (
    CLIMBER_SUPPORT_MAX_DISTANCE_CM,
    LOD0,
    LOD0_TRIANGLE_BUDGET,
    LOD1,
    LOD1_TRIANGLE_BUDGET,
    LOD2,
    LOD2_TRIANGLE_BUDGET,
    PARAM_CLIMBER_SUPPORT,
    PART_FOLIAGE,
    PART_WOOD,
    SUPPORT_BEAN_POLES,
    SUPPORT_FENCE,
    SUPPORT_PERGOLA,
    SUPPORT_TRELLIS,
    ForgeCache,
    enrich_climber_records,
    forge_plant,
    forge_record,
    resolve_climber_support,
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

CLIMBER_SPRITES: tuple[SpriteRef, ...] = tuple(
    [SpriteRef("species", k) for k, r in sorted(SPECIES.items()) if r["a"] == "climber"]
    + [SpriteRef("categories", k) for k, r in sorted(CATEGORIES.items()) if r["a"] == "climber"]
)


def _circle_ring(radius_cm: float, n: int = 32) -> tuple[tuple[float, float], ...]:
    return tuple(
        (radius_cm * math.cos(2.0 * math.pi * i / n), radius_cm * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    )


def _rect_ring(w: float, d: float) -> tuple[tuple[float, float], ...]:
    hw, hd = w * 0.5, d * 0.5
    return ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))


def _climber_record(
    sprite: SpriteRef,
    height_cm: float = 210.0,
    radius_cm: float = 45.0,
    *,
    item_id: str = "climber-1",
    seed: int = 101,
    east_cm: float = 0.0,
    north_cm: float = 0.0,
    parent_id: str | None = None,
    support: dict[str, object] | None = None,
) -> Record:
    params_dict: dict[str, object] = {
        "sprite_species": sprite.name if sprite.group == "species" else "",
        "plant_category": sprite.name if sprite.group == "categories" else "climbing_plant",
        "radius_cm": radius_cm,
        "seed": seed,
    }
    if support is not None:
        params_dict[PARAM_CLIMBER_SUPPORT] = (
            str(support.get("kind", SUPPORT_BEAN_POLES)),
            float(support.get("azimuth_deg", 0.0)),
            float(support.get("distance_cm", 0.0)),
        )
    return Record(
        item_id=item_id,
        kind="SHRUB",
        name=sprite.name,
        shape="circle",
        footprints=(_circle_ring(radius_cm),),
        height_cm=height_cm,
        transform=Transform(east_cm=east_cm, north_cm=north_cm),
        material=Material(key="climber"),
        parent_id=parent_id,
        params=Params(params_dict),
    )


def _linear_to_srgb01(lin: np.ndarray) -> np.ndarray:
    c = np.clip(lin, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1.0 / 2.4)) - 0.055)


def _hue_deg(rgb01: np.ndarray) -> float:
    h, _s, _v = colorsys.rgb_to_hsv(float(rgb01[0]), float(rgb01[1]), float(rgb01[2]))
    return h * 360.0


class TestL34ClimberSupportResolution:
    """Verify the 3-tier support resolution rule: TRELLIS parent -> nearest fence/pergola (<= 50 cm) -> bean poles."""

    def test_trellis_parent_takes_precedence_over_nearby_fence(self) -> None:
        ref = SpriteRef("species", "clematis")
        trellis = Record(
            item_id="trellis-1",
            kind="TRELLIS",
            name="Garden Trellis",
            shape="rectangle",
            footprints=(_rect_ring(180.0, 15.0),),
            height_cm=200.0,
            transform=Transform(east_cm=100.0, north_cm=100.0, rotation_deg=35.0),
            material=Material(key="trellis"),
        )
        fence = Record(
            item_id="fence-1",
            kind="FENCE",
            name="Close Fence",
            shape="polyline",
            footprints=(),
            path=((90.0, 100.0), (110.0, 100.0)),
            path_width_cm=8.0,
            height_cm=180.0,
            transform=Transform(),
            material=Material(key="fence"),
        )
        climber = _climber_record(
            ref,
            item_id="clematis-1",
            east_cm=100.0,
            north_cm=100.0,
            parent_id="trellis-1",
        )
        sup = resolve_climber_support(climber, [trellis, fence, climber])
        assert sup["kind"] == SUPPORT_TRELLIS
        assert sup["azimuth_deg"] == pytest.approx(35.0)
        assert sup["distance_cm"] == 0.0

    def test_nearest_fence_within_50cm_vs_beyond_50cm(self) -> None:
        ref = SpriteRef("species", "jasmine")
        assert pytest.approx(50.0) == CLIMBER_SUPPORT_MAX_DISTANCE_CM

        # Fence along y = 100, width = 10 cm (half_w = 5 cm).
        # Climber at (0, 0) with radius 45 cm -> canopy edge at y = 45 cm.
        # If fence is at y = 98 cm -> center dist = 98, gap = 98 - 45 - 5 = 48 cm (<= 50 cm -> FENCE).
        fence_near = Record(
            item_id="fence-near",
            kind="FENCE",
            name="Fence Near",
            shape="polyline",
            footprints=(),
            path=((-200.0, 98.0), (200.0, 98.0)),
            path_width_cm=10.0,
            height_cm=180.0,
            transform=Transform(),
            material=Material(key="fence"),
        )
        climber = _climber_record(ref, radius_cm=45.0, east_cm=0.0, north_cm=0.0)
        sup_near = resolve_climber_support(climber, [fence_near, climber])
        assert sup_near["kind"] == SUPPORT_FENCE
        assert sup_near["distance_cm"] == pytest.approx(48.0, abs=0.1)

        # If fence is at y = 104 cm -> gap = 104 - 45 - 5 = 54 cm (> 50 cm -> BEAN_POLES).
        fence_far = dataclasses.replace(fence_near, path=((-200.0, 104.0), (200.0, 104.0)))
        sup_far = resolve_climber_support(climber, [fence_far, climber])
        assert sup_far["kind"] == SUPPORT_BEAN_POLES

    def test_nearest_pergola_within_50cm(self) -> None:
        ref = SpriteRef("species", "wisteria")
        pergola = Record(
            item_id="pergola-1",
            kind="PERGOLA",
            name="Pergola",
            shape="rectangle",
            footprints=(_rect_ring(300.0, 200.0),),
            height_cm=240.0,
            transform=Transform(east_cm=0.0, north_cm=160.0, rotation_deg=90.0),
            material=Material(key="pergola"),
        )
        # Pergola southern edge in world coords (rotated 90 deg: local x=±150 -> world y=160±150, so y=10..310)
        climber = _climber_record(ref, radius_cm=40.0, east_cm=0.0, north_cm=0.0)
        sup = resolve_climber_support(climber, [pergola, climber])
        assert sup["kind"] == SUPPORT_PERGOLA

    def test_forge_worker_enriches_climber_support_from_snapshot(self) -> None:
        sink = RecordingSink()
        worker = ForgeWorker(sink, cache=ForgeCache(max_entries=16))
        ref = SpriteRef("species", "bean")
        trellis = Record(
            item_id="trellis-1",
            kind="TRELLIS",
            name="Trellis",
            shape="rectangle",
            footprints=(_rect_ring(120.0, 12.0),),
            height_cm=200.0,
            transform=Transform(east_cm=50.0, north_cm=50.0, rotation_deg=20.0),
            material=Material(key="trellis"),
        )
        c_trellis = _climber_record(ref, item_id="bean-trellis", east_cm=50.0, north_cm=50.0, parent_id="trellis-1")
        c_poles = _climber_record(ref, item_id="bean-poles", east_cm=500.0, north_cm=500.0)

        enriched = enrich_climber_records([trellis, c_trellis, c_poles])
        by_id = {r.item_id: r for r in enriched}
        assert by_id["bean-trellis"].params[PARAM_CLIMBER_SUPPORT][0] == SUPPORT_TRELLIS
        assert by_id["bean-poles"].params[PARAM_CLIMBER_SUPPORT][0] == SUPPORT_BEAN_POLES

        sink.begin()
        sink.add("bean-trellis", (), c_trellis.transform, c_trellis.material)
        sink.add("bean-poles", (), c_poles.transform, c_poles.material)
        sink.commit()

        worker.submit_snapshot([trellis, c_trellis, c_poles], force_lod=LOD2)
        worker.drain()
        parts_trellis = sink.item("bean-trellis").parts
        parts_poles = sink.item("bean-poles").parts
        assert parts_trellis != parts_poles


class TestL34ClimberBuildersAndAll123Coverage:
    """Verify all 16 climber recipes and confirm all 13 archetypes / 123 recipes are forged."""

    def test_all_7_climber_recipes_and_all_13_archetypes_covered(self) -> None:
        assert len(CLIMBER_SPRITES) == 7
        all_archetypes = {r["a"] for r in SPECIES.values()} | {r["a"] for r in CATEGORIES.values()}
        assert all_archetypes == ARCHETYPES
        assert len(SPECIES) + len(CATEGORIES) == 123

    @pytest.mark.parametrize("sprite", CLIMBER_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    @pytest.mark.parametrize("support_kind", [SUPPORT_BEAN_POLES, SUPPORT_TRELLIS, SUPPORT_FENCE, SUPPORT_PERGOLA])
    def test_dimensional_truth_and_verify_builder(self, sprite: SpriteRef, support_kind: str) -> None:
        rec = _climber_record(
            sprite,
            height_cm=210.0,
            radius_cm=45.0,
            seed=101,
            support={"kind": support_kind, "azimuth_deg": 25.0, "distance_cm": 12.0},
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
        assert abs(z_max - 210.0) <= 0.03 * 210.0
        assert abs(max_span - 90.0) <= 0.10 * 90.0

    @pytest.mark.parametrize("sprite", CLIMBER_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_lod_triangle_caps_and_ordering(self, sprite: SpriteRef) -> None:
        p0 = forge_plant(sprite, 210.0, 45.0, seed=101, lod=LOD0, cache=None)
        p1 = forge_plant(sprite, 210.0, 45.0, seed=101, lod=LOD1, cache=None)
        p2 = forge_plant(sprite, 210.0, 45.0, seed=101, lod=LOD2, cache=None)

        t0 = sum(p.mesh.triangle_count for p in p0)
        t1 = sum(p.mesh.triangle_count for p in p1)
        t2 = sum(p.mesh.triangle_count for p in p2)

        assert 0 < t2 <= LOD2_TRIANGLE_BUDGET == 800
        assert t2 < t1 <= LOD1_TRIANGLE_BUDGET == 6_000
        assert t1 < t0 <= LOD0_TRIANGLE_BUDGET == 25_000

    @pytest.mark.parametrize("sprite", CLIMBER_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_no_clones_across_seeds(self, sprite: SpriteRef) -> None:
        p_a = forge_plant(sprite, 210.0, 45.0, seed=101, lod=LOD0, cache=None)
        p_b = forge_plant(sprite, 210.0, 45.0, seed=202, lod=LOD0, cache=None)
        iou = silhouette_iou(p_a, p_b, 210.0, 45.0)
        assert iou < 0.95, f"{sprite}: silhouette IoU {iou:.4f} >= 0.95"

    @pytest.mark.parametrize("sprite", CLIMBER_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_foliage_hue_and_albedo(self, sprite: SpriteRef) -> None:
        parts = forge_plant(sprite, 210.0, 45.0, seed=101, lod=LOD0, cache=None)
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
        for sprite in CLIMBER_SPRITES:
            t0 = time.perf_counter()
            forge_plant(sprite, 210.0, 45.0, seed=303, lod=LOD0, cache=None)
            t1 = time.perf_counter()
            durations_ms.append((t1 - t0) * 1000.0)
        median_ms = float(np.median(durations_ms))
        assert median_ms <= 150.0, f"Median cold build time {median_ms:.2f} ms > 150 ms"
