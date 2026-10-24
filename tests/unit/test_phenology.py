"""Unit tests for Plant Forge L3.5: seasonal accents (fruits, blossoms, umbels, pods, tubers) and core/phenology.py (#387)."""

from __future__ import annotations

import ast
import datetime
import math
import time
from pathlib import Path

import pytest

from open_garden_planner.core.phenology import (
    PhenologyState,
    evaluate_phenology,
    evaluate_phenology_batch,
    evaluate_phenology_for_records,
    seasonal_day_of_year,
    seasonal_month,
)
from open_garden_planner.core.plant_art import (
    CATEGORIES,
    FEATURE_KEYS,
    SPECIES,
    SpriteRef,
    recipe_for,
    traits_for,
)
from open_garden_planner.core.plant_forge import (
    ACCENT_FAMILIES,
    LOD0,
    LOD0_TRIANGLE_BUDGET,
    LOD1,
    LOD1_TRIANGLE_BUDGET,
    LOD2,
    LOD2_TRIANGLE_BUDGET,
    PART_ACCENTS,
    PART_FOLIAGE,
    PART_WOOD,
    ForgeCache,
    build_accents,
    forge_plant,
    forge_record,
)
from open_garden_planner.core.scene3d import (
    Material,
    MeshPart,
    Params,
    Record,
    RecordingSink,
    Transform,
    verify_builder,
)
from open_garden_planner.ui.view3d.forge_worker import ForgeWorker

REPO_ROOT = Path(__file__).resolve().parents[2]
PHENOLOGY_PATH = REPO_ROOT / "src" / "open_garden_planner" / "core" / "phenology.py"
ACCENTS_PATH = REPO_ROOT / "src" / "open_garden_planner" / "core" / "plant_forge" / "accents.py"

ALL_SPRITES: tuple[SpriteRef, ...] = tuple(
    [SpriteRef("species", k) for k in sorted(SPECIES)]
    + [SpriteRef("categories", k) for k in sorted(CATEGORIES)]
)

DECIDUOUS_SPRITES: tuple[SpriteRef, ...] = tuple(
    s for s in ALL_SPRITES if traits_for(s).deciduous
)

EVERGREEN_SPRITES: tuple[SpriteRef, ...] = tuple(
    s for s in ALL_SPRITES if not traits_for(s).deciduous
)


def _circle_ring(radius_cm: float, n: int = 32) -> tuple[tuple[float, float], ...]:
    return tuple(
        (radius_cm * math.cos(2.0 * math.pi * i / n), radius_cm * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    )


def _plant_record(
    sprite: SpriteRef,
    *,
    item_id: str = "plant-1",
    height_cm: float = 180.0,
    radius_cm: float = 70.0,
    seed: int = 101,
) -> Record:
    return Record(
        item_id=item_id,
        kind="TREE",
        name=sprite.name,
        shape="circle",
        footprints=(_circle_ring(radius_cm),),
        height_cm=height_cm,
        transform=Transform(),
        material=Material(key="plant"),
        params=Params(
            {
                "sprite_species": sprite.name if sprite.group == "species" else "",
                "plant_category": sprite.name if sprite.group == "categories" else "round_deciduous",
                "radius_cm": radius_cm,
                "seed": seed,
            }
        ),
    )


class TestL35ArchitectureAndQtFree:
    """Verify core/phenology.py and core/plant_forge/accents.py are strictly Qt-free."""

    @pytest.mark.parametrize("path", [PHENOLOGY_PATH, ACCENTS_PATH], ids=lambda p: p.name)
    def test_module_is_qt_free(self, path: Path) -> None:
        forbidden = {"PyQt6", "PySide6", "shiboken6"}
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


class TestL35SeasonalAccents:
    """Verify all 5 accent families (fruits, blossoms, umbels, pods, tubers) build valid 3D meshes."""

    def test_accent_families_constant(self) -> None:
        assert frozenset({"fruits", "blossoms", "umbels", "pods", "tubers"}) == ACCENT_FAMILIES

    @pytest.mark.parametrize(
        ("species_name", "expected_family"),
        [
            # 1. Fruits (`fruit`, `fruit2`)
            ("apple_tree", "fruits"),
            ("cherry_tree", "fruits"),
            ("tomato", "fruits"),
            ("pepper", "fruits"),
            ("pumpkin", "fruits"),
            ("blueberry", "fruits"),
            # 2. Blossoms (`flowers`, `clusters`, `puffs`)
            ("magnolia", "blossoms"),
            ("rose", "blossoms"),
            ("lilac", "blossoms"),
            ("hydrangea", "blossoms"),
            ("wisteria", "blossoms"),
            ("lavender", "blossoms"),
            ("sunflower", "blossoms"),
            # 3. Umbels (`umbels`)
            ("dill", "umbels"),
            ("fennel", "umbels"),
            ("cilantro", "umbels"),
            ("elderberry", "umbels"),
            # 4. Pods (`pods`)
            ("bean", "pods"),
            ("pea", "pods"),
            ("cucumber", "pods"),
            ("zucchini", "pods"),
            ("okra", "pods"),
            # 5. Tubers / root crowns (`bulb`)
            ("carrot", "tubers"),
            ("radish", "tubers"),
            ("beet", "tubers"),
            ("turnip", "tubers"),
            ("onion", "tubers"),
            ("garlic", "tubers"),
            ("leek", "tubers"),
        ],
    )
    def test_accent_family_emits_valid_part_accents(self, species_name: str, expected_family: str) -> None:
        _ = expected_family
        sprite = SpriteRef("species", species_name)
        rec = _plant_record(sprite, item_id=f"test-{species_name}", height_cm=150.0, radius_cm=60.0, seed=101)
        parts = verify_builder(forge_record, rec, height_tolerance=0.03)
        part_names = {p.name for p in parts}
        assert PART_WOOD in part_names
        assert PART_FOLIAGE in part_names
        assert PART_ACCENTS in part_names

        accent_part = next(p for p in parts if p.name == PART_ACCENTS)
        accent_part.validate()
        assert accent_part.mesh.triangle_count >= 12
        # Verify linear colours are strictly within valid non-clipping range
        assert float(accent_part.mesh.colors[:, :3].min()) >= 0.01
        assert float(accent_part.mesh.colors[:, :3].max()) <= 0.90

        # Verify LOD ordering and budgets still hold with accents included
        p0 = forge_plant(sprite, 150.0, 60.0, seed=101, lod=LOD0, cache=None)
        p1 = forge_plant(sprite, 150.0, 60.0, seed=101, lod=LOD1, cache=None)
        p2 = forge_plant(sprite, 150.0, 60.0, seed=101, lod=LOD2, cache=None)
        t0 = sum(p.mesh.triangle_count for p in p0)
        t1 = sum(p.mesh.triangle_count for p in p1)
        t2 = sum(p.mesh.triangle_count for p in p2)
        assert 0 < t2 <= LOD2_TRIANGLE_BUDGET
        assert t2 < t1 <= LOD1_TRIANGLE_BUDGET
        assert t1 < t0 <= LOD0_TRIANGLE_BUDGET

    def test_every_recipe_with_feature_keys_builds_accents(self) -> None:
        featured_count = 0
        for sprite in ALL_SPRITES:
            recipe = recipe_for(sprite)
            traits = traits_for(sprite)
            if (set(recipe) & FEATURE_KEYS) or traits.blossom_spec is not None:
                featured_count += 1
                geo = build_accents(traits, 120.0, 50.0, seed=42, lod=LOD0)
                assert geo.triangle_count > 0, f"{sprite} failed to build accent geometry"
                part = MeshPart(mesh=geo.to_mesh(), material_kind="vc", casts_shadow=True, tinted=False, name=PART_ACCENTS)
                part.validate()
        assert featured_count >= 80


class TestL35PhenologyAndHemispheres:
    """Verify deciduous bare periods (Jan at 52 N, Jul at 35 S), evergreens never bare, and shader values."""

    @pytest.mark.parametrize("sprite", DECIDUOUS_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_deciduous_bare_in_january_52n_and_july_35s(self, sprite: SpriteRef) -> None:
        jan_15 = datetime.date(2026, 1, 15)
        jul_15 = datetime.date(2026, 7, 15)

        # Gate 1: Deciduous bare in January at 52 deg N
        state_nh_winter = evaluate_phenology(sprite, jan_15, latitude_deg=52.0)
        assert state_nh_winter.leaf_density == 0.0
        assert state_nh_winter.foliage_opacity == 0.0
        assert state_nh_winter.shader_values()["uOpacity"] == 0.0

        # Summer in Northern Hemisphere (July at 52 deg N): full leaf
        state_nh_summer = evaluate_phenology(sprite, jul_15, latitude_deg=52.0)
        assert state_nh_summer.leaf_density == 1.0

        # Gate 2: Deciduous bare in July at 35 deg S (latitude_deg = -35.0)
        state_sh_winter = evaluate_phenology(sprite, jul_15, latitude_deg=-35.0)
        assert state_sh_winter.leaf_density == 0.0
        assert state_sh_winter.foliage_opacity == 0.0

        # Summer in Southern Hemisphere (January at 35 deg S): full leaf
        state_sh_summer = evaluate_phenology(sprite, jan_15, latitude_deg=-35.0)
        assert state_sh_summer.leaf_density == 1.0

    @pytest.mark.parametrize("sprite", EVERGREEN_SPRITES, ids=lambda s: f"{s.group}/{s.name}")
    def test_evergreens_never_bare_across_all_12_months_both_hemispheres(self, sprite: SpriteRef) -> None:
        assert len(EVERGREEN_SPRITES) >= 15
        for month in range(1, 13):
            d = datetime.date(2026, month, 15)
            st_nh = evaluate_phenology(sprite, d, latitude_deg=52.0)
            st_sh = evaluate_phenology(sprite, d, latitude_deg=-35.0)
            assert st_nh.leaf_density == 1.0, f"{sprite} bare in month {month} at 52 N"
            assert st_sh.leaf_density == 1.0, f"{sprite} bare in month {month} at 35 S"
            assert st_nh.autumn_color == 0.0
            assert st_sh.autumn_color == 0.0

    def test_seasonal_transitions_spring_autumn_bloom_ripeness_snow(self) -> None:
        apple = SpriteRef("species", "apple_tree")

        # Spring budburst & bloom (April / May at 52 N)
        may_10 = datetime.date(2026, 5, 10)
        st_spring = evaluate_phenology(apple, may_10, latitude_deg=52.0)
        assert st_spring.leaf_density == 1.0
        assert st_spring.bloom == 1.0
        assert st_spring.ripeness == 0.0
        assert st_spring.snow == 0.0

        # Southern Hemisphere spring bloom (November at 35 S corresponds to May NH)
        nov_10 = datetime.date(2026, 11, 10)
        st_sh_spring = evaluate_phenology(apple, nov_10, latitude_deg=-35.0)
        assert st_sh_spring.leaf_density == 1.0
        assert st_sh_spring.bloom == 1.0

        # Late summer / early autumn harvest & colour (September / October at 52 N)
        sep_20 = datetime.date(2026, 9, 20)
        st_sep = evaluate_phenology(apple, sep_20, latitude_deg=52.0)
        assert st_sep.ripeness > 0.7
        assert st_sep.bloom == 0.0

        oct_25 = datetime.date(2026, 10, 25)
        st_oct = evaluate_phenology(apple, oct_25, latitude_deg=52.0)
        assert st_oct.autumn_color > 0.8
        assert st_oct.autumn_mix == st_oct.autumn_color
        assert st_oct.foliage_tint_linear != (1.0, 1.0, 1.0)

        # Deep winter snow at 52 N vs mild winter at 30 N
        jan_15 = datetime.date(2026, 1, 15)
        st_jan_52n = evaluate_phenology(apple, jan_15, latitude_deg=52.0)
        st_jan_30n = evaluate_phenology(apple, jan_15, latitude_deg=30.0)
        assert st_jan_52n.snow > 0.0
        assert st_jan_30n.snow == 0.0

    def test_frost_date_shifts_harvest_ripeness_window(self) -> None:
        radish = SpriteRef("species", "radish")  # harvest_weeks = (3, 5)
        # Early frost (March 1) -> radish ripe in late March / April
        early_frost = datetime.date(2026, 3, 1)
        st_apr_early = evaluate_phenology(
            radish,
            datetime.date(2026, 4, 1),
            latitude_deg=52.0,
            last_frost=early_frost,
        )
        # Late frost (May 25) -> radish not yet ripe on April 1
        late_frost = datetime.date(2026, 5, 25)
        st_apr_late = evaluate_phenology(
            radish,
            datetime.date(2026, 4, 1),
            latitude_deg=52.0,
            last_frost=late_frost,
        )
        assert st_apr_early.ripeness > 0.0
        assert st_apr_late.ripeness == 0.0

    def test_phenology_never_decides_plant_existence(self) -> None:
        """Whether a plant exists on plan_date is decided only by #315, never by phenology.py."""
        sprites = [
            SpriteRef("species", "tomato"),
            SpriteRef("species", "apple_tree"),
            SpriteRef("species", "pine"),
            SpriteRef("species", "carrot"),
        ]
        records = [_plant_record(s, item_id=f"item-{i}") for i, s in enumerate(sprites)]
        for month in (1, 4, 7, 10):
            states = evaluate_phenology_for_records(records, datetime.date(2026, month, 15))
            # Every passed plant record receives a PhenologyState; none is dropped
            assert set(states.keys()) == {r.item_id for r in records}
            assert all(isinstance(v, PhenologyState) for v in states.values())

    def test_seasonal_helpers_hemisphere_symmetry(self) -> None:
        assert seasonal_month(datetime.date(2026, 1, 15), 52.0) == 1
        assert seasonal_month(datetime.date(2026, 7, 15), -35.0) == 1
        doy_nh = seasonal_day_of_year(datetime.date(2026, 1, 15), 52.0)
        doy_sh = seasonal_day_of_year(datetime.date(2026, 7, 17), -35.0)
        assert abs(doy_nh - doy_sh) <= 2.0


class TestL35Scrubbing300PlantsPerformance:
    """Gate: scrubbing 300 plants across dates completes in <= 16 ms."""

    def test_scrubbing_300_plants_under_16ms(self) -> None:
        # Build 300 plant records cycling across all 123 recipes
        records = [
            _plant_record(
                ALL_SPRITES[i % len(ALL_SPRITES)],
                item_id=f"plant-{i}",
                seed=1000 + i,
            )
            for i in range(300)
        ]

        sink = RecordingSink()
        worker = ForgeWorker(sink, cache=ForgeCache(max_entries=256))
        worker.submit_snapshot(records, force_lod=LOD2)

        dates = [
            datetime.date(2026, 1, 15),
            datetime.date(2026, 4, 20),
            datetime.date(2026, 7, 15),
            datetime.date(2026, 10, 22),
        ]

        # Measure cold and warm date scrubs across 300 plants
        for target_date in dates:
            t0 = time.perf_counter()
            states = worker.scrub_date(target_date, latitude_deg=52.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            assert len(states) == 300
            assert elapsed_ms <= 16.0, f"Scrubbing 300 plants on {target_date} took {elapsed_ms:.2f} ms > 16 ms"

        # Also test direct batch evaluation for 300 plants
        t0 = time.perf_counter()
        batch_states = evaluate_phenology_batch(records, datetime.date(2026, 5, 18), latitude_deg=-35.0)
        batch_ms = (time.perf_counter() - t0) * 1000.0
        assert len(batch_states) == 300
        assert batch_ms <= 16.0, f"Batch evaluation of 300 plants took {batch_ms:.2f} ms > 16 ms"

