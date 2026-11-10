"""Authoring gates for the bundled teaching plans, independent of rendering."""

import json
import math
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

RESOURCES = Path(__file__).parents[2] / "src/open_garden_planner/resources"
EXAMPLES = RESOURCES / "examples"
SLUGS = ("raised-bed", "food-forest", "balcony")   # the teaching plans
SHOWCASE = "family-garden"                         # the 3D view's showcase: no tutorial
BENCH = Path(__file__).parents[1] / "fixtures/plans/bench_small.ogp"


def load(slug, language=""):
    return json.loads((EXAMPLES / language / f"{slug}.ogp").read_text(encoding="utf-8"))


def species(obj):
    return obj.get("metadata", {}).get("plant_species", {}).get("scientific_name", "").lower()


def test_main_raised_bed_is_full_and_mature_footprints_clear_the_actual_sprite_soil():
    plan = load("raised-bed")
    bed = next(o for o in plan["objects"] if o.get("object_type") == "RAISED_BED")
    assert (bed["width"], bed["height"]) == (400, 200)
    # Read the shipped artwork: a future sprite rim change must recheck placement.
    svg = ET.parse(RESOURCES / "objects/infrastructure/raised_bed.svg").getroot()
    soil = svg.find("{http://www.w3.org/2000/svg}rect").attrib
    _, _, art_w, art_h = map(float, svg.attrib["viewBox"].split())
    left = bed["x"] + float(soil["x"]) / art_w * bed["width"]
    bottom = bed["y"] + float(soil["y"]) / art_h * bed["height"]
    right = left + float(soil["width"]) / art_w * bed["width"]
    top = bottom + float(soil["height"]) / art_h * bed["height"]
    plants = [o for o in plan["objects"] if o.get("parent_bed_id") == bed["item_id"]]
    assert Counter(map(species, plants)) == {
        "lactuca sativa": 16, "daucus carota": 60, "raphanus sativus": 88,
    }
    for plant in plants:
        radius = plant["radius"]
        assert left <= plant["center_x"] - radius <= plant["center_x"] + radius <= right
        assert bottom <= plant["center_y"] - radius <= plant["center_y"] + radius <= top
    reference = date(2026, 9, 21)
    ages = {"lactuca sativa": 51, "daucus carota": 98, "raphanus sativus": 32}
    for plant in plants:
        planted = date.fromisoformat(plant["metadata"]["plant_instance"]["planting_date"])
        assert (reference - planted).days == ages[species(plant)]


def test_forest_uses_established_trees_grouped_ground_cover_and_local_guild_members():
    plan = load("food-forest")
    plants = [o for o in plan["objects"] if species(o)]
    assert not any(species(o) == "solanum tuberosum" for o in plants)
    assert Counter(map(species, plants)) == {
        "malus domestica": 1, "prunus persica": 1, "ribes rubrum": 3,
        "fragaria ananassa": 24, "allium schoenoprasum": 12,
        "borago officinalis": 10, "daucus carota": 60, "phaseolus coccineus": 3,
    }
    apple = next(o for o in plants if species(o) == "malus domestica")
    for plant in plants:
        assert plant.get("parent_bed_id"), species(plant)
        planted = plant["metadata"]["plant_instance"]["planting_date"]
        if species(plant) in {"malus domestica", "prunus persica", "ribes rubrum"}:
            assert planted <= "2019-11-10"
        if plant["metadata"].get("guild"):
            distance = math.hypot(plant["center_x"] - apple["center_x"],
                                  plant["center_y"] - apple["center_y"])
            assert distance <= apple["radius"] + 75
    members = [o for o in plants if o["metadata"].get("guild")]
    assert Counter(o["metadata"]["guild"]["role"] for o in members) == {
        "centre": 1, "ground_cover": 16, "pollinator_attractor": 4,
    }
    trellis = next(o for o in plan["objects"] if o.get("object_type") == "TRELLIS")
    assert all(o["parent_bed_id"] == trellis["item_id"] for o in plants
               if species(o) == "phaseolus coccineus")


def test_balcony_is_furnished_and_separates_three_watering_groups():
    plan = load("balcony")
    objects = plan["objects"]
    kinds = Counter(o.get("object_type") for o in objects)
    assert kinds["CHAIR"] == 2 and kinds["TABLE_RECTANGULAR"] == kinds["PARASOL"] == 1
    assert kinds["WALL"] == kinds["FENCE"] == 1
    containers = [o for o in objects if o.get("object_type") == "CONTAINER"]
    counts = {}
    for container in containers:
        plants = [o for o in objects if o.get("parent_bed_id") == container["item_id"]]
        assert len({species(o) for o in plants}) == 1
        counts[species(plants[0])] = len(plants)
        for plant in plants:
            r = plant["radius"]
            assert container["x"] + 3 <= plant["center_x"] - r
            assert plant["center_x"] + r <= container["x"] + container["width"] - 3
            assert container["y"] + 3 <= plant["center_y"] - r
            assert plant["center_y"] + r <= container["y"] + container["height"] - 3
    assert counts == {"ocimum basilicum": 4, "petroselinum crispum": 6, "thymus vulgaris": 4}


@pytest.mark.parametrize("slug", SLUGS)
def test_site_tutorial_and_reciprocal_bed_links_are_real_saved_content(slug):
    plan = load(slug)
    assert 0 < plan["location"]["latitude"] < 90
    assert plan["location"]["timezone"] == "Europe/Berlin"
    assert set(plan["location"]["frost_dates"]) == {"last_spring_frost", "first_fall_frost"}
    notes = [o for o in plan["objects"] if o["type"] == "text"]
    assert notes and all("21 Sep 2026" in o["content"] and not o.get("name") for o in notes)
    by_id = {o["item_id"]: o for o in plan["objects"]}
    assert len(by_id) == len(plan["objects"])
    for obj in plan["objects"]:
        if parent_id := obj.get("parent_bed_id"):
            assert obj["item_id"] in by_id[parent_id]["child_item_ids"]
    for target, history in plan.get("soil_tests", {}).items():
        assert target in by_id and history["target_id"] == target
        assert "Fictional" in history["records"][0]["notes"]


#: Where the showcase stands apart from the bench plan, besides its path widths: what
#: stood in the 50 cm stepping-stone walk was moved out of it (the bench plan's walk is a
#: 6 cm line and its numbers are pinned, so the fixture keeps its layout). By the plant's
#: common name or the object's name: the centre in the bench plan, and in the showcase.
MOVED = {
    "Bird bath": ((560.0, 470.0), (620.0, 450.0)),
    "Geranium": ((630.0, 681.0), (612.0, 681.0)),
    "Chrysanthemum": ((712.0, 681.0), (746.0, 681.0)),
    "Lily": ((794.0, 681.0), (811.0, 681.0)),      # makes room for the chrysanthemum
}


def label(obj):
    return obj.get("name") or obj.get("metadata", {}).get("plant_species", {}).get("common_name", "")


def test_the_showcase_is_the_bench_plan_and_cannot_drift_from_it():
    """The plan of every Beauty Board: same items and ids (a plant's shape is seeded by its
    id), same plants, and the same geometry but for the four centres listed in ``MOVED``.
    Regenerating the fixture without the example, or the other way round, fails here."""
    plan, bench = load(SHOWCASE), json.loads(BENCH.read_text(encoding="utf-8"))
    assert plan["canvas"] == bench["canvas"]
    assert plan["version"] == bench["version"]
    assert len(plan["objects"]) == len(bench["objects"])
    fields = ("item_id", "type", "object_type", "x", "y", "center_x", "center_y", "radius", "width",
              "height", "rotation", "points", "parent_bed_id", "child_item_ids", "name")
    moved = set()
    for shipped, fixture in zip(plan["objects"], bench["objects"], strict=True):
        expected = {k: fixture.get(k) for k in fields}
        if label(fixture) in MOVED and fixture["type"] == "circle":
            before, after = MOVED[label(fixture)]
            assert (fixture["center_x"], fixture["center_y"]) == before, label(fixture)
            expected |= {"center_x": after[0], "center_y": after[1]}
            moved.add(label(fixture))
        assert {k: shipped.get(k) for k in fields} == expected, label(fixture)
        assert shipped.get("metadata", {}).get("plant_species") == fixture.get("metadata", {}).get("plant_species")
    assert moved == set(MOVED), "each name stands for exactly one object"
    for key in ("latitude", "longitude", "frost_dates"):
        assert plan["location"][key] == bench["location"][key]


def _distance_to_polyline(point, line):
    """The distance from ``point`` to the nearest point of the polyline ``line``."""
    best = math.inf
    for (ax, ay), (bx, by) in zip(line, line[1:], strict=False):
        dx, dy = bx - ax, by - ay
        along = ((point[0] - ax) * dx + (point[1] - ay) * dy) / (dx * dx + dy * dy)
        along = min(1.0, max(0.0, along))
        best = min(best, math.hypot(point[0] - ax - along * dx, point[1] - ay - along * dy))
    return best


def _outline(obj):
    """An object's outline as points (a rectangle's corners, a polygon's or line's points)."""
    if obj["type"] == "rectangle":
        assert not obj.get("rotation") and not obj.get("rotation_angle"), obj.get("name")
        x, y, w, h = obj["x"], obj["y"], obj["width"], obj["height"]
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
    points = [(p["x"], p["y"]) for p in obj["points"]]
    return points + points[:1] if obj["type"] == "polygon" else points


def _segments_cross(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def _gap_to_walk(obj, walk, half_width):
    """How far ``obj`` stays clear of the walk's edge (negative: it stands in it)."""
    if obj["type"] == "circle":
        return _distance_to_polyline((obj["center_x"], obj["center_y"]), walk) - half_width - obj["radius"]
    outline = _outline(obj)
    own_half = obj.get("stroke_width", 0.0) / 2 if obj["type"] == "polyline" else 0.0
    for a, b in zip(outline, outline[1:], strict=False):
        for c, d in zip(walk, walk[1:], strict=False):
            if _segments_cross(a, b, c, d):
                return -half_width
    nearest = min([_distance_to_polyline(p, walk) for p in outline]
                  + [_distance_to_polyline(p, outline) for p in walk])
    return nearest - half_width - own_half


@pytest.mark.parametrize("language", ("", "de", "es"))
def test_nothing_stands_in_the_showcases_stepping_stone_walk(language):
    """The stones are a 50 cm walk from the terrace to the pond. A bird bath stood on it,
    and a chrysanthemum and a geranium grew into it (review of #795). Only the ground it
    is laid on or through may lie under it: the lawn, the terrace, the perennial border."""
    plan, english = load(SHOWCASE, language), load(SHOWCASE)
    names = {o["item_id"]: label(o) for o in english["objects"]}
    stones = next(o for o in plan["objects"] if names[o["item_id"]] == "Stepping stones")
    walk = [(p["x"], p["y"]) for p in stones["points"]]
    assert walk == [(700.0, 720.0), (640.0, 600.0), (560.0, 520.0), (500.0, 420.0)], (
        "the path's points are not moved: other test data is pinned to them")
    half_width = stones["stroke_width"] / 2
    ground = {"Lawn", "Terrace", "Perennial border"}
    in_the_walk, nearest = [], {}
    for obj in plan["objects"]:
        name = names[obj["item_id"]]
        if obj is stones or name in ground:
            continue
        gap = _gap_to_walk(obj, walk, half_width)
        if gap < 5.0:
            in_the_walk.append((name, round(gap, 1)))
        nearest[name] = min(gap, nearest.get(name, math.inf))
    assert not in_the_walk, in_the_walk
    # and the test sees the plan: what stands beside the walk is near it, the walk ends
    # short of the pond's rim
    assert 5 <= nearest["Geranium"] < 15 and 5 <= nearest["Chrysanthemum"] < 15
    assert 20 <= nearest["Bird bath"] < 60 and 0 < nearest["Pond"] < 10
    # the plants of the border keep their distance from each other as well
    border = sorted(o["center_x"] for o in plan["objects"]
                    if o.get("parent_bed_id") == next(
                        i for i, n in names.items() if n == "Perennial border"))
    assert len(border) == 10 and min(b - a for a, b in zip(border, border[1:], strict=False)) >= 60


def test_the_showcase_is_a_real_saved_plan_with_its_links_and_place():
    plan = load(SHOWCASE)
    assert plan["location"]["timezone"] == "Europe/Berlin"
    by_id = {o["item_id"]: o for o in plan["objects"]}
    assert len(by_id) == len(plan["objects"]) == 100
    assert sum(1 for o in plan["objects"] if species(o) or o.get("object_type") in
               {"TREE", "SHRUB", "PERENNIAL"}) == 61
    for obj in plan["objects"]:
        if parent_id := obj.get("parent_bed_id"):
            assert obj["item_id"] in by_id[parent_id]["child_item_ids"]
    # #768: every glasshouse in the showcase is ridge-bearing, with its linked
    # aluminium ROOF_RIDGE (a saved example must show the current tool, not an
    # older non-ridge greenhouse).
    greenhouses = [o for o in plan["objects"] if o.get("object_type") == "GREENHOUSE"]
    assert greenhouses
    for greenhouse in greenhouses:
        ridge = by_id[greenhouse["metadata"]["ridge_item_id"]]
        assert ridge["object_type"] == "ROOF_RIDGE"
        assert ridge["metadata"]["owner_polygon_id"] == greenhouse["item_id"]
        assert ridge["metadata"]["ridge_finish"] == "aluminium"
    # it shows off the built world: every class of the 3D pipeline stands in it
    kinds = {o.get("object_type") for o in plan["objects"]}
    assert {"HOUSE", "ROOF_RIDGE", "GREENHOUSE", "GARAGE_SHED", "PERGOLA", "RAISED_BED", "POND_POOL",
            "TRAMPOLINE", "TRELLIS", "FENCE", "HEDGE_POLYGON", "WALL", "TREE"} <= kinds


@pytest.mark.parametrize("language", ("de", "es"))
def test_the_showcase_is_translated_and_keeps_its_geometry_and_plants(language):
    original, translated = load(SHOWCASE), load(SHOWCASE, language)
    assert translated["location"] == original["location"]
    assert translated["canvas"] == original["canvas"]
    geometry = ("item_id", "type", "object_type", "x", "y", "center_x", "center_y", "radius", "width",
                "height", "rotation", "points", "parent_bed_id", "child_item_ids")
    names_changed = 0
    for old, new in zip(original["objects"], translated["objects"], strict=True):
        assert {k: old.get(k) for k in geometry} == {k: new.get(k) for k in geometry}
        names_changed += old.get("name") != new.get("name")
        if species(old):
            before, after = old["metadata"]["plant_species"], new["metadata"]["plant_species"]
            assert {k: v for k, v in before.items() if k != "common_name"} == {
                k: v for k, v in after.items() if k != "common_name"}
    # every name of the plan has its translation (a name left in English fails here)
    english = {o.get("name") for o in original["objects"]} - {None, ""}
    still = english & {o.get("name") for o in translated["objects"]}
    assert not still, f"untranslated in {language}: {sorted(still)}"
    assert names_changed > 0


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("language", ("de", "es"))
def test_localized_examples_keep_geometry_ids_art_and_botanical_truth(slug, language):
    original, translated = load(slug), load(slug, language)
    assert translated["location"] == original["location"]
    assert translated["canvas"] == original["canvas"]
    geometry = ("item_id", "type", "x", "y", "center_x", "center_y", "radius", "width",
                "height", "rotation", "points", "plant_species", "parent_bed_id", "child_item_ids")
    for old, new in zip(original["objects"], translated["objects"], strict=True):
        assert {k: old.get(k) for k in geometry} == {k: new.get(k) for k in geometry}
        if species(old):
            before, after = old["metadata"]["plant_species"], new["metadata"]["plant_species"]
            assert {k: v for k, v in before.items() if k != "common_name"} == {
                k: v for k, v in after.items() if k != "common_name"}
            assert before["common_name"] != after["common_name"]
            assert old["metadata"]["plant_instance"] == new["metadata"]["plant_instance"]
        if old["type"] == "text":
            assert old["content"] != new["content"]


def test_the_showcases_trees_stand_before_a_time_lapse_starts_and_the_beds_come_up_in_it():
    """A full-grown birch must not pop in on the fixture's one planting day (3D review)."""
    from open_garden_planner.core.growth_model import years_to_maturity

    plan = load(SHOWCASE)
    plants = [o for o in plan["objects"] if o.get("metadata", {}).get("plant_instance")]
    established = seasonal = 0
    for plant in plants:
        metadata = plant["metadata"]
        planted = metadata["plant_instance"]["planting_date"]
        if years_to_maturity(metadata["plant_species"], plant.get("object_type", "")) >= 1.0:
            assert planted <= "2026-03-01", metadata["plant_species"].get("common_name")
            # one date for all of them, but for the tree that has borne fruit
            assert (planted == "2026-03-01") != (metadata["plant_species"]["common_name"] == "Cherry Tree")
            established += 1
        else:
            assert planted == "2026-04-15"
            seasonal += 1
    assert established and seasonal


# ── #795: the showcase state ────────────────────────────────────────────────

EVERY = (*SLUGS, SHOWCASE)
REFERENCE = {"family-garden": "2026-06-21", "food-forest": "2026-09-21",
             "raised-bed": "2026-09-21", "balcony": "2026-09-21"}


@pytest.mark.parametrize("language", ("", "de", "es"))
def test_the_showcases_paths_are_as_wide_as_a_path_one_walks_on(language):
    """They kept the bench fixture's 8 and 6 cm and were hairlines in the plan and in 3D."""
    paths = {o["name"]: o for o in load(SHOWCASE, language)["objects"] if o.get("object_type") == "PATH"}
    assert sorted(path["stroke_width"] for path in paths.values()) == [50.0, 80.0]
    bench = {o["name"]: o for o in json.loads(BENCH.read_text(encoding="utf-8"))["objects"]
             if o.get("object_type") == "PATH"}
    assert sorted(path["stroke_width"] for path in bench.values()) == [6.0, 8.0], (
        "the bench fixture keeps the widths its pinned numbers were measured with")


@pytest.mark.parametrize("slug", EVERY)
def test_no_example_path_is_a_hairline(slug):
    paths = [o for o in load(slug)["objects"] if o.get("object_type") == "PATH"]
    assert paths or slug == "balcony"
    for path in paths:
        width = path["stroke_width"] if path["type"] == "polyline" else min(path["width"], path["height"])
        assert width >= 40, (slug, path.get("name"), width)


@pytest.mark.parametrize("slug", EVERY)
def test_the_sidecar_names_a_daytime_moment_on_the_reference_date(slug):
    meta = json.loads((EXAMPLES / f"{slug}.meta.json").read_text(encoding="utf-8"))
    assert meta["showcase_date"] == REFERENCE[slug]
    hour, minute = map(int, meta["showcase_utc_time"].split(":"))
    assert 9 <= hour <= 13 and 0 <= minute < 60     # 11:00 to 15:00 on a Berlin summer-time clock
    for language in ("en", "de", "es", "ru"):
        assert str(date.fromisoformat(REFERENCE[slug]).year) in meta[f"description_{language}"]
        assert meta[f"attribution_{language}"]


@pytest.mark.parametrize("slug", EVERY)
@pytest.mark.parametrize("language", ("", "de", "es"))
def test_the_harvest_history_is_fictional_and_fits_its_plants_and_the_reference_date(slug, language):
    plan, original = load(slug, language), load(slug)
    by_id = {o["item_id"]: o for o in plan["objects"]}
    logs = plan["harvest_logs"]
    assert 3 <= len(logs) <= 8, "a small history"
    seen = set()
    for target, history in logs.items():
        plant = by_id[target]
        snapshot = plant["metadata"]["plant_species"]
        assert history["target_id"] == target
        # the canonical species key (ADR-016): the bundled records have no source id
        assert "source_id" not in snapshot
        assert history["species_key"] == snapshot["scientific_name"].strip().lower()
        assert history["species_key"] not in seen, "one plant carries a species' history"
        seen.add(history["species_key"])
        assert history["species_name"] == snapshot["common_name"]
        planted = plant["metadata"]["plant_instance"]["planting_date"]
        dates = [record["date"] for record in history["records"]]
        assert dates == sorted(dates) and len(set(dates)) == len(dates)
        for record, english in zip(history["records"], original["harvest_logs"][target]["records"], strict=True):
            assert planted <= record["date"] <= REFERENCE[slug]
            assert record["quantity"] > 0 and record["unit"] in {"kg", "g", "pcs", "bunch"}
            assert set(record) <= {"id", "date", "quantity", "unit", "quality", "notes"}
            assert {k: record[k] for k in ("id", "date", "quantity", "unit")} == {
                k: english[k] for k in ("id", "date", "quantity", "unit")}
            assert "Fictional" in english["notes"]
            if language:
                assert record["notes"] != english["notes"], "the remark is translated"
                assert ("quality" in record) == ("quality" in english)
                if "quality" in english:
                    assert record["quality"] != english["quality"]
    ids = [record["id"] for history in logs.values() for record in history["records"]]
    assert len(set(ids)) == len(ids)


#: How long after planting a woody plant can have given a harvest, in years.
BEARS_AFTER_YEARS = {"TREE": 3.0, "SHRUB": 1.0}


@pytest.mark.parametrize("slug", EVERY)
def test_a_harvest_fits_the_age_of_the_plant_that_gave_it(slug):
    """A cherry tree planted on 1 March 2026 gave 6.5 kg in June 2026 (review of #795).
    A tree bears years after it was planted, a shrub the year after, and the crop of a
    young tree is small."""
    from open_garden_planner.core.growth_model import years_to_maturity

    plan = load(slug)
    by_id = {o["item_id"]: o for o in plan["objects"]}
    woody = 0
    for target, history in plan["harvest_logs"].items():
        plant = by_id[target]
        kind = plant.get("object_type", "")
        wait = BEARS_AFTER_YEARS.get(kind)
        # a runner bean is drawn as a shrub by its height and ripens within its season
        if wait is None or years_to_maturity(plant["metadata"]["plant_species"], kind) < 1.0:
            continue
        woody += 1
        planted = date.fromisoformat(plant["metadata"]["plant_instance"]["planting_date"])
        first = date.fromisoformat(min(record["date"] for record in history["records"]))
        years = (first - planted).days / 365.25
        assert years >= wait, (slug, history["species_name"], planted, first)
        per_year = Counter()
        for record in history["records"]:
            assert record["unit"] == "kg", (slug, history["species_name"])
            per_year[record["date"][:4]] += record["quantity"]
        # at most 7 kg a year of age since planting: 6.5 kg from a tree in its fourth
        # summer, 60 kg from one in its eleventh
        for year, kilograms in per_year.items():
            age = (date(int(year), 12, 31) - planted).days / 365.25
            assert kilograms <= 7.0 * age, (slug, history["species_name"], year, kilograms, age)
    assert woody == {"family-garden": 1, "food-forest": 3}.get(slug, 0)


def test_the_showcases_cherry_is_a_tree_of_several_years_with_the_crown_it_had():
    """Planted in autumn 2022 as a nursery tree. Its crown on the reference date is the one
    the plan was drawn with (the bench plan's cherry, grown from 1 March to 21 June)."""
    from open_garden_planner.core.growth_model import grown_height_cm, grown_spread_cm

    def cherry(plan):
        return next(o for o in plan["objects"] if label(o) == "Cherry Tree")

    shipped, bench = cherry(load(SHOWCASE)), cherry(json.loads(BENCH.read_text(encoding="utf-8")))
    instance = shipped["metadata"]["plant_instance"]
    assert instance == {"planting_date": "2022-11-05", "current_spread_cm": 130.0,
                        "current_height_cm": 150.0}
    assert shipped["radius"] == bench["radius"] == 180.0, "the drawn footprint is the bench plan's"
    day, species = date(2026, 6, 21), shipped["metadata"]["plant_species"]
    as_drawn = dict(bench["metadata"], plant_instance=dict(
        bench["metadata"]["plant_instance"], planting_date="2026-03-01"))
    was = grown_spread_cm(species, as_drawn, day, "TREE")
    now = grown_spread_cm(species, shipped["metadata"], day, "TREE")
    assert was == pytest.approx(373.5, abs=0.1) and now == pytest.approx(was, abs=1.0)
    # the tree is taller than the spring-planted one was: 6.4 m against 5.1 m
    assert grown_height_cm(species, shipped["metadata"], day, "TREE") == pytest.approx(639.7, abs=0.5)
    assert grown_height_cm(species, as_drawn, day, "TREE") == pytest.approx(511.3, abs=0.5)


def _luminance(argb):
    red, green, blue = (int(argb[i:i + 2], 16) / 255 for i in (3, 5, 7))
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (red, green, blue)]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("language", ("", "de", "es"))
def test_a_tutorial_note_has_an_ink_for_the_ground_it_lies_on(slug, language):
    """A note has no halo: dark ink sank into the lawn texture (#795)."""
    plan = load(slug, language)
    surfaces = [o for o in plan["objects"] if o["type"] == "rectangle" and o.get("object_type") in
                {"LAWN", "TERRACE_PATIO", "PATH", "GARDEN_BED", "RAISED_BED"}]
    for note in (o for o in plan["objects"] if o["type"] == "text"):
        under = [s for s in surfaces if s["x"] <= note["x"] <= s["x"] + s["width"]
                 and s["y"] <= note["y"] <= s["y"] + s["height"]]
        ground = min(under, key=lambda s: s["width"] * s["height"])["object_type"]
        ink = _luminance(note["text_color"])
        if ground == "LAWN":
            assert ink > 0.85 and note["bold"], (slug, ground, note["text_color"])
        else:
            assert ground == "TERRACE_PATIO" and ink < 0.05, (slug, ground, note["text_color"])


def test_the_balcony_chairs_face_the_table_and_stand_where_they_were_drawn():
    """A bare ``setRotation`` was never saved: the chairs shipped unrotated, and a
    regeneration under the current serializer moved them to x = -257."""
    chairs = [o for o in load("balcony")["objects"] if o.get("object_type") == "CHAIR"]
    assert [(c["x"], c["y"], c["width"], c["height"]) for c in chairs] == [
        (120.0, 215.0, 42.0, 42.0), (292.0, 215.0, 42.0, 42.0)]
    assert [c["rotation_angle"] for c in chairs] == [90.0, -90.0]


@pytest.mark.parametrize("language", ("de", "es"))
def test_one_english_name_has_one_translation_in_every_example(language):
    """The showcase's "Compostador" became "Compost" whenever all four were regenerated."""
    names = {}
    for slug in EVERY:
        for old, new in zip(load(slug)["objects"], load(slug, language)["objects"], strict=True):
            if old.get("name"):
                assert names.setdefault(old["name"], new["name"]) == new["name"], (slug, old["name"])
