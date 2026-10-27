"""Portable template field policy, recursive content and bundled catalog contracts."""

import json
from copy import deepcopy
from dataclasses import fields

import pytest

from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES
from open_garden_planner.core.project import ProjectData
from open_garden_planner.core.templates import (
    KEEP_PROJECT_FIELDS,
    STRIP_PROJECT_FIELDS,
    example_copy_plan,
    template_plan,
)
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES, bundled_examples


def test_every_project_field_has_one_explicit_policy(qtbot):
    assert not KEEP_PROJECT_FIELDS & STRIP_PROJECT_FIELDS
    assert {f.name for f in fields(ProjectData)} == KEEP_PROJECT_FIELDS | STRIP_PROJECT_FIELDS


def test_every_private_field_and_unknown_top_level_field_is_removed(qtbot):
    plan = {key: {"private": "data"} for key in STRIP_PROJECT_FIELDS}
    plan |= {"version": "1.4", "canvas": {"width": 500, "height": 500},
             "objects": [], "layers": [], "future_private_field": "secret"}
    original = deepcopy(plan)
    clean = template_plan(plan)
    assert not STRIP_PROJECT_FIELDS & clean.keys()
    assert set(clean) == {"version", "canvas", "objects", "layers"}
    assert plan == original
    clean["canvas"]["width"] = 900
    assert plan == original


@pytest.mark.parametrize("path", [r"C:\Users\Owner\photo.jpg", r"C:private.jpg",
                                    r"\\server\share\photo.jpg", "/home/owner/photo.jpg",
                                    "file:///C:/Users/owner/photo.jpg", r"\private\photo.jpg"])
def test_absolute_paths_are_removed_at_any_depth(path, qtbot):
    plan = {"objects": [{"type": "group", "children": [
        {"type": "background_image", "path": "relative.jpg"},
        {"type": "journal_pin", "note_id": "private"},
        {"type": "circle", "metadata": {"custom": [path, {path: "secret"}],
                                        "photos": ["relative-photo.jpg"],
                                        "geo_metadata": {"latitude": 51},
                                        "plant_species": {"scientific_name": "Daucus carota"}}},
    ]}]}
    child = template_plan(plan)["objects"][0]["children"]
    assert len(child) == 1
    assert child[0]["metadata"] == {"custom": [{}],
                                    "plant_species": {"scientific_name": "Daucus carota"}}


def test_portable_content_and_unknown_key_tolerance(qtbot):
    content = {"objects": [{"type": "group", "smart_symbol": {"id": "example", "version": 1},
                            "metadata": {"guild": {"guild_id": "guild"}}, "children": []}],
               "constraints": [{"type": "distance"}], "succession_plans": {"bed": {"year": 2027}},
               "auto_assign_permaculture_layers": True}
    clean = template_plan(content)
    assert clean == content
    # A pre-F consumer can ignore the additive keys and still read the base geometry.
    legacy = {k: v for k, v in clean.items() if k not in {
        "succession_plans", "auto_assign_permaculture_layers"}}
    assert ProjectData.from_dict(legacy).objects == content["objects"]
    assert ProjectData.from_dict(clean | {"unknown_future_key": True}).objects == content["objects"]


def test_catalog_content_is_localized_and_has_provenance(qtbot):
    entries = bundled_examples()
    assert len(entries) >= 3
    provenance = (BUNDLED_EXAMPLES / "PROVENANCE.md").read_text(encoding="utf-8")
    for entry in entries:
        assert entry.path.name in provenance
        assert entry.thumbnail.stat().st_size > 1000
        meta = json.loads(entry.path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        assert meta["license"] == "CC-BY-SA-4.0" and meta["attribution"]
        for language in SUPPORTED_LANGUAGES:
            assert meta["name_" + language] and meta["description_" + language]
        plan = json.loads(entry.path.read_text(encoding="utf-8"))
        clean = template_plan(plan)
        assert not {"location", "soil_tests", "metadata"} & clean.keys()
        assert clean["objects"] == plan["objects"]
        assert example_copy_plan(plan, entry.path) == {k: v for k, v in plan.items() if k != "metadata"}


def test_bundled_parent_links_and_forest_layers_follow_render_order(qtbot):
    for entry in bundled_examples():
        plan = json.loads(entry.path.read_text(encoding="utf-8"))
        objects = {obj["item_id"]: obj for obj in plan["objects"]}
        layers = {layer["id"]: layer["z_order"] for layer in plan["layers"]}
        for obj in objects.values():
            if obj.get("parent_bed_id"):
                bed = objects[obj["parent_bed_id"]]
                # Same-layer parent clamps or a higher explicit layer keep
                # plants above boxes/supports. In-ground beds are in the
                # separate ground band, below every semantic plant layer.
                if bed.get("metadata", {}).get("object_height_cm", 0) > 0:
                    assert layers[obj["layer_id"]] >= layers[bed["layer_id"]]
                assert obj["item_id"] in bed["child_item_ids"]
        if entry.path.stem == "food-forest":
            assert len({layer["permaculture_layer"] for layer in plan["layers"]}) == 7
            assert any(obj.get("metadata", {}).get("guild") for obj in objects.values())


def test_local_template_listing_never_parses_untrusted_plan_content(qtbot, tmp_path, monkeypatch):
    from open_garden_planner.services.example_library import gallery_entries

    (tmp_path / "corrupt.ogp").write_text("not JSON", encoding="utf-8")
    monkeypatch.setattr("open_garden_planner.services.example_library.user_templates_dir", lambda: tmp_path)
    assert gallery_entries()[-1].name == "corrupt"


def test_polycluture_has_no_bundled_antagonistic_pair(qtbot):
    from itertools import combinations

    from open_garden_planner.services.companion_planting_service import CompanionPlantingService
    from open_garden_planner.services.example_library import BUNDLED_EXAMPLES

    plan = json.loads((BUNDLED_EXAMPLES / "raised-bed.ogp").read_text(encoding="utf-8"))
    names = {obj["plant_species"] for obj in plan["objects"] if obj.get("plant_species")}
    service = CompanionPlantingService()
    for a, b in combinations(names, 2):
        relationship = service.get_relationship(a, b)
        assert relationship is None or relationship.type != "antagonistic"


@pytest.mark.parametrize("custom_type", ["background_image", "journal_pin", [], {"kind": "custom"}])
def test_custom_type_fields_are_data_not_canvas_records(qtbot, custom_type):
    custom = {"type": custom_type, "cultivar": "kept text", "nested": {"type": "journal_pin"}}
    plan = {"objects": [{"type": "circle", "metadata": {"plant_instance": {"custom_fields": custom}}}]}
    assert template_plan(plan) == plan
