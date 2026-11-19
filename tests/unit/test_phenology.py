"""Unit tests for Plant Forge L3.5: seasonal accents (fruits, blossoms, umbels, pods, tubers) and core/phenology.py (#387)."""

from __future__ import annotations

import ast
import dataclasses
import datetime
import math
import time
from pathlib import Path

import pytest

from open_garden_planner.core.phenology import (
    DEFAULT_LATITUDE_DEG,
    PhenologyState,
    evaluate_phenology,
    evaluate_phenology_batch,
    evaluate_phenology_for_records,
    plan_latitude,
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
    SEASONAL_PARTS,
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
from tests.perf.test_scene3d_snapshot_budget import budget_factor, traced

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
        assert part_names & SEASONAL_PARTS

        accent_parts = [p for p in parts if p.name in SEASONAL_PARTS]
        assert sum(p.mesh.triangle_count for p in accent_parts) >= 12
        for part in accent_parts:
            part.validate()
            assert float(part.mesh.colors[:, :3].min()) >= 0.01
            assert float(part.mesh.colors[:, :3].max()) <= 0.90

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
                if traits.flower is not None and traits.flower.habit != "crown":
                    # a bulb's scapes and a stemmed flower's heads: its own builder
                    # places the flowers (#940), not ``build_accents``
                    parts = forge_plant(sprite, 120.0, 50.0, seed=42, lod=LOD0, cache=None)
                    flowers = [p for p in parts if p.name == "flowers"]
                    assert flowers and flowers[0].mesh.triangle_count > 0, sprite
                    flowers[0].validate()
                    continue
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

    def test_a_perennials_recorded_harvest_ripens_only_in_its_fruit_months(self) -> None:
        """#940: a grape vine's record carries harvest weeks 18-24 after the last frost.
        After a 1 February frost (Valencia) that window is June-July, but grapes ripen in
        the vine's own months (9, 10): no ripe grapes on 21 June. After a 15 May frost the
        window (18 September - 30 October) lies inside them and still ripens. An annual's
        months ARE its window, so a tomato's recorded harvest is not cut."""
        vine = _plant_record(SpriteRef("species", "grape_vine"))
        vine = dataclasses.replace(
            vine, params=Params({**vine.params, "harvest_start": 18, "harvest_end": 24}))
        valencia = {"last_spring_frost": "02-01", "first_fall_frost": "12-15"}
        berlin = {"last_spring_frost": "05-15", "first_fall_frost": "10-15"}
        june = evaluate_phenology(vine, datetime.date(2026, 6, 21), latitude_deg=39.5,
                                  frost_dates=valencia)
        assert june.ripeness == 0.0 and june.accent_opacity == 0.0
        october = evaluate_phenology(vine, datetime.date(2026, 10, 1), latitude_deg=52.5,
                                     frost_dates=berlin)
        assert october.ripeness > 0.5
        tomato = _plant_record(SpriteRef("species", "tomato"))
        tomato = dataclasses.replace(
            tomato, params=Params({**tomato.params, "harvest_start": 6, "harvest_end": 30}))
        november = evaluate_phenology(tomato, datetime.date(2026, 11, 10), latitude_deg=52.5,
                                      frost_dates={"last_spring_frost": "05-15",
                                                   "first_fall_frost": "12-31"})
        assert november.ripeness > 0.0   # outside the tomato's derived months, inside its record

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


def _phenology_budget_ms() -> float:
    # Keep the real 16 ms gate in Test, including on CI. Coverage measures its
    # tracer too; use the suite's existing tracer allowance, without CI slack.
    return 16.0 * budget_factor(is_traced=traced(), is_ci=False)


@pytest.mark.parametrize(("tracing", "elapsed_ms", "passes"), [
    (False, 16.0, True), (False, 17.0, False), (True, 17.0, True), (True, 161.0, False),
])
def test_the_product_budget_stays_16ms_and_only_tracing_gets_an_allowance(
        monkeypatch, tracing: bool, elapsed_ms: float, passes: bool) -> None:
    monkeypatch.setitem(globals(), "traced", lambda: tracing)
    assert (elapsed_ms <= _phenology_budget_ms()) is passes


class TestL35Scrubbing300PlantsPerformance:
    """Gate: scrubbing 300 plants across dates completes in <= 16 ms."""

    @pytest.mark.perf
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
        budget_ms = _phenology_budget_ms()

        # Measure cold and warm date scrubs across 300 plants
        for target_date in dates:
            t0 = time.perf_counter()
            states = worker.scrub_date(target_date, latitude_deg=52.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            assert len(states) == 300
            assert elapsed_ms <= budget_ms, f"Scrubbing 300 plants on {target_date} took {elapsed_ms:.2f} ms > {budget_ms:g} ms"

        # Also test direct batch evaluation for 300 plants
        t0 = time.perf_counter()
        batch_states = evaluate_phenology_batch(records, datetime.date(2026, 5, 18), latitude_deg=-35.0)
        batch_ms = (time.perf_counter() - t0) * 1000.0
        assert len(batch_states) == 300
        assert batch_ms <= budget_ms, f"Batch evaluation of 300 plants took {batch_ms:.2f} ms > {budget_ms:g} ms"


def test_fruit_ripeness_tint_changes_while_the_plant_is_also_flowering():
    tomato = SpriteRef("species", "tomato")
    early = evaluate_phenology(tomato, datetime.date(2026, 7, 4),
                               last_frost=datetime.date(2026, 4, 25))
    late = evaluate_phenology(tomato, datetime.date(2026, 7, 28),
                              last_frost=datetime.date(2026, 4, 25))
    assert early.bloom > 0 and late.bloom > 0
    assert early.accent_tint_linear != late.accent_tint_linear


@pytest.mark.parametrize(("location", "expected"), [
    ({"latitude": -33.87, "longitude": 151.21}, -33.87),
    ({"latitude": 0, "longitude": 0}, 0.0),
    ({"latitude": 64.1, "longitude": 18.9}, 64.1),
    ({"latitude": 64.1}, DEFAULT_LATITUDE_DEG),
    (None, DEFAULT_LATITUDE_DEG),
    ({}, DEFAULT_LATITUDE_DEG),
    ({"latitude": "52.5", "longitude": 13.4}, DEFAULT_LATITUDE_DEG),
    ({"latitude": True, "longitude": 13.4}, DEFAULT_LATITUDE_DEG),
    ({"latitude": float("nan"), "longitude": 13.4}, DEFAULT_LATITUDE_DEG),
    ({"latitude": float("-inf"), "longitude": 13.4}, DEFAULT_LATITUDE_DEG),
    ({"latitude": -91.0, "longitude": 13.4}, DEFAULT_LATITUDE_DEG),
    ("not a location", DEFAULT_LATITUDE_DEG),
    ({"latitude": 10 ** 400, "longitude": 13.4}, DEFAULT_LATITUDE_DEG),
], ids=["south", "equator", "north", "no-longitude", "none", "empty", "text", "bool", "nan",
        "inf", "beyond", "hostile", "overflow"])
def test_one_latitude_reader_for_the_3d_view(location: object, expected: float) -> None:
    """The plan latitude the 3D view's phenology, the garden's life and the look's
    hemisphere read (senior review of L5: three readers, one checking for NaN): the
    latitude of a valid ``plan_place`` — both coordinates real, finite, in range — else
    the default (so a location without a longitude is no place either)."""
    assert plan_latitude(location) == expected


# ── #940: a hardy plant flowers by its own months, a tender one after the last frost ──

#: Frost dates of a cool temperate garden (the plan's ``location["frost_dates"]``).
_FROST_0515_1015 = {"last_spring_frost": "05-15", "first_fall_frost": "10-15"}


def _bloom(stem: str, day: datetime.date, group: str = "species") -> float:
    return evaluate_phenology(SpriteRef(group, stem), day, latitude_deg=52.5,
                              frost_dates=_FROST_0515_1015).bloom


@pytest.mark.parametrize(("stem", "day"), [
    ("crocus", datetime.date(2026, 3, 15)),
    ("daffodil", datetime.date(2026, 4, 1)),
    ("tulip", datetime.date(2026, 4, 18)),
    ("apple_tree", datetime.date(2026, 4, 18)),
    ("magnolia", datetime.date(2026, 4, 18)),
    ("forsythia", datetime.date(2026, 3, 20)),
    ("chrysanthemum", datetime.date(2026, 11, 2)),
    ("aster", datetime.date(2026, 10, 20)),
])
def test_a_hardy_plant_flowers_outside_the_frost_free_season(stem: str, day: datetime.date) -> None:
    """Before the last frost (05-15) and after the first (10-15) a hardy plant still
    flowers in its own months: the gate that zeroed every bloom outside the season
    left a garden with no crocus, no daffodil and nothing in flower in April."""
    assert traits_for(SpriteRef("species", stem)).frost_hardy_bloom is True
    assert _bloom(stem, day) == 1.0


def test_a_tender_plant_waits_for_the_last_frost() -> None:
    """A tomato is planted out after the last frost: in its own bloom months (May-July)
    it shows no flowers until the frost-free season starts, then it does."""
    assert traits_for(SpriteRef("species", "tomato")).frost_hardy_bloom is False
    assert _bloom("tomato", datetime.date(2026, 4, 18)) == 0.0
    assert _bloom("tomato", datetime.date(2026, 5, 10)) == 0.0   # in its months, before the frost
    assert _bloom("tomato", datetime.date(2026, 6, 1)) == 1.0
    assert _bloom("dahlia", datetime.date(2026, 10, 20)) == 0.0  # in its months, after the frost


def test_a_category_fallback_stays_gated() -> None:
    """A category says nothing about hardiness: its flowers keep the frost-free season."""
    assert all(not traits_for(SpriteRef("categories", stem)).frost_hardy_bloom for stem in CATEGORIES)
    assert _bloom("flowering_perennial", datetime.date(2026, 5, 10), "categories") == 0.0
    assert _bloom("flowering_perennial", datetime.date(2026, 6, 10), "categories") == 1.0


def test_nothing_flowers_in_december() -> None:
    december = datetime.date(2026, 12, 15)
    in_flower = [f"{group}/{stem}" for group, table in (("species", SPECIES), ("categories", CATEGORIES))
                 for stem in table if _bloom(stem, december, group) > 0.0]
    assert in_flower == []


def test_without_frost_dates_the_bloom_months_alone_decide() -> None:
    """No frost dates, no seasonal claim: a tomato flowers in May like a crocus in March
    (from the 20th: its flowers open over the window's first ten days, #940)."""
    tomato = evaluate_phenology(SpriteRef("species", "tomato"), datetime.date(2026, 5, 20),
                                latitude_deg=52.5)
    assert tomato.bloom == 1.0


def test_the_hardy_set_never_names_a_tender_bundled_species() -> None:
    """Drift guard against the species file: every bundled record that draws one of
    the hardy stems (as a gallery drop names it) is hardy or half-hardy, never tender,
    and every hardy stem is a species recipe that has bloom months to keep."""
    import json

    from open_garden_planner.core.plant_art.resolve import resolve_sprite

    plants = json.loads((REPO_ROOT / "src/open_garden_planner/resources/data/plant_species.json")
                        .read_text(encoding="utf-8"))["plants"]
    hardy = {stem for stem in SPECIES if traits_for(SpriteRef("species", stem)).frost_hardy_bloom}
    assert hardy, "the hardy set is empty"
    for stem in hardy:
        assert traits_for(SpriteRef("species", stem)).bloom_months, stem
    tolerance_of: dict[str, set[str]] = {}
    for record in plants:
        sprite = resolve_sprite("PERENNIAL", record["common_name"])
        if sprite is not None and sprite.group == "species":
            tolerance_of.setdefault(sprite.name, set()).add(record["frost_tolerance"])
    tender = sorted(stem for stem in hardy if "tender" in tolerance_of.get(stem, set()))
    assert tender == []
    # and the guard can fail: tomatoes are tender
    assert "tender" in tolerance_of["tomato"]
