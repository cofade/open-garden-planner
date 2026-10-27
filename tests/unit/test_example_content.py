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
SLUGS = ("raised-bed", "food-forest", "balcony")


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
