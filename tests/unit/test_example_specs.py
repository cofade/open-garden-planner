"""The rules every bundled example plan is held to, read off the shipped files.

``tests/example_specs.py`` states what each plan is meant to be. Nothing here names a
plan: every test runs over the table, and the first one requires that the table and the
shipped files are the same set, so a new plan is checked the day it ships.
"""

import json

import pytest

from open_garden_planner.core.camera_tours import load_tours
from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES
from open_garden_planner.core.templates import example_showcase_moment
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES, bundled_examples
from tests.example_specs import (
    CENTRAL_EUROPEAN_ZONES,
    COGNATES,
    HINTS,
    ORBIT,
    SPECS,
)

LANGUAGES = ("de", "es")          # the languages a plan itself ships in, beside English
EVERY = sorted(SPECS)


def load(slug, language=""):
    return json.loads((BUNDLED_EXAMPLES / language / f"{slug}.ogp").read_text(encoding="utf-8"))


def sidecar(slug):
    return json.loads((BUNDLED_EXAMPLES / f"{slug}.meta.json").read_text(encoding="utf-8"))


def plants_of(plan):
    return [o for o in plan["objects"] if o.get("metadata", {}).get("plant_species")]


def test_the_table_and_the_shipped_files_name_the_same_plans():
    assert {path.stem for path in BUNDLED_EXAMPLES.glob("*.ogp")} == set(SPECS)
    for language in LANGUAGES:
        assert {path.stem for path in (BUNDLED_EXAMPLES / language).glob("*.ogp")} == set(SPECS)
    assert {path.name.removesuffix(".meta.json")
            for path in BUNDLED_EXAMPLES.glob("*.meta.json")} == set(SPECS)


def test_the_gallery_lists_the_examples_in_their_fixed_order():
    orders = {slug: spec.order for slug, spec in SPECS.items()}
    assert len(set(orders.values())) == len(orders), "two examples share a place"
    assert all(sidecar(slug)["order"] == order for slug, order in orders.items())
    expected = sorted(orders, key=orders.get)
    for language in SUPPORTED_LANGUAGES:
        assert [entry.path.stem for entry in bundled_examples(language)] == expected


@pytest.mark.parametrize("slug", EVERY)
def test_an_example_has_its_place_its_plants_and_its_north(slug):
    spec, plan = SPECS[slug], load(slug)
    location = plan["location"]
    assert (location["latitude"], location["longitude"]) == pytest.approx(spec.place, abs=1e-4)
    assert location["timezone"] in CENTRAL_EUROPEAN_ZONES
    assert set(location["frost_dates"]) == {"last_spring_frost", "first_fall_frost"}
    assert len(plants_of(plan)) == spec.plants
    assert plan.get("north_angle_deg", 0.0) == spec.north_angle_deg
    ids = [o["item_id"] for o in plan["objects"]]
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("slug", EVERY)
@pytest.mark.parametrize("language", ("", *LANGUAGES))
def test_the_hint_lies_alone_on_the_top_layer_and_is_the_plans_only_text(slug, language):
    """Hide that layer and the plan is ready for a picture: nothing else may lie on it, and
    no other text may lie anywhere."""
    plan = load(slug, language)
    texts = [o for o in plan["objects"] if o["type"] == "text"]
    hint_layers = [layer for layer in plan["layers"] if layer["name"] == HINTS[language]]
    if not SPECS[slug].hint:
        assert not texts and not hint_layers
        return
    (layer,), (hint,) = hint_layers, texts
    assert layer["visible"] and not layer["locked"]
    assert layer["z_order"] == max(each["z_order"] for each in plan["layers"])
    assert [o["item_id"] for o in plan["objects"] if o["layer_id"] == layer["id"]] == [hint["item_id"]]
    assert hint["content"].strip() and len(hint["content"].split("\n")) <= 4
    if language:
        assert hint["content"] != load(slug)["objects"][plan["objects"].index(hint)]["content"]


@pytest.mark.parametrize("slug", EVERY)
@pytest.mark.parametrize("language", ("", *LANGUAGES))
def test_an_example_ships_its_stored_tours_and_every_one_of_them_loads(slug, language):
    plan, english = load(slug, language), load(slug)
    tours, skipped = load_tours(plan["camera_tours"])
    assert not skipped
    assert [tour["name"] for tour in english["camera_tours"]] == list(SPECS[slug].tours)
    orbit = tours[0]
    assert orbit.motion == "orbit" and orbit.orbit.ease and orbit.orbit.turns == 1
    assert orbit.date_range is None and orbit.time_range is None, "the orbit plays at the showcase moment"
    assert orbit.orbit.pose.target == pytest.approx(
        (plan["canvas"]["width"] / 2, plan["canvas"]["height"] / 2))
    if language:
        for mine, theirs in zip(plan["camera_tours"], english["camera_tours"], strict=True):
            assert mine["name"] != theirs["name"], "a tour's name is translated"
            assert {k: v for k, v in mine.items() if k != "name"} == {
                k: v for k, v in theirs.items() if k != "name"}
    else:
        assert english["camera_tours"][0]["name"] == ORBIT


@pytest.mark.parametrize("slug", EVERY)
def test_every_copy_of_an_example_names_the_same_moment_and_title_set(slug):
    meta, spec = sidecar(slug), SPECS[slug]
    moments = {example_showcase_moment(BUNDLED_EXAMPLES / folder / f"{slug}.ogp")
               for folder in ("", *LANGUAGES)}
    assert len(moments) == 1 and next(iter(moments))[0] == spec.day
    for language in SUPPORTED_LANGUAGES:
        assert meta[f"name_{language}"] and meta[f"description_{language}"]
        assert str(spec.day.year) in meta[f"description_{language}"]
    assert meta["tags"] and meta["license"] == "CC-BY-SA-4.0"


@pytest.mark.parametrize("slug", EVERY)
@pytest.mark.parametrize("language", LANGUAGES)
def test_a_translated_copy_keeps_the_geometry_and_names_every_plant_in_its_language(slug, language):
    original, translated = load(slug), load(slug, language)
    assert translated["location"] == original["location"]
    assert translated["canvas"] == original["canvas"]
    geometry = ("item_id", "type", "object_type", "x", "y", "center_x", "center_y", "radius",
                "width", "height", "rotation_angle", "points", "parent_bed_id", "child_item_ids",
                "layer_id")
    for old, new in zip(original["objects"], translated["objects"], strict=True):
        assert {k: old.get(k) for k in geometry} == {k: new.get(k) for k in geometry}
    for old, new in zip(plants_of(original), plants_of(translated), strict=True):
        before, after = old["metadata"]["plant_species"], new["metadata"]["plant_species"]
        assert {k: v for k, v in before.items() if k != "common_name"} == {
            k: v for k, v in after.items() if k != "common_name"}, "botany stays canonical"
        if before["common_name"] not in COGNATES[language]:
            assert before["common_name"] != after["common_name"], before["common_name"]
        assert old["metadata"].get("plant_instance") == new["metadata"].get("plant_instance")
