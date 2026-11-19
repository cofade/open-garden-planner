"""The shipped example plans and sidecars are what ``scripts/generate_examples.py`` makes.

Nothing ran the generator in a test: its output had drifted from the files that ship in
three ways, each found by regenerating an unchanged tree (#795). A bare ``setRotation``
on the balcony chairs was never saved as an angle and, under the current serializer,
moved them to x = -257; the table of translations took a second, different Spanish
"Compost" from whichever plan was authored later; and the sidecars' Russian attribution
was hand-added and would have been dropped. This gate compares what ships with what the
generator authors now, through the same production constructors and serializer.

Thumbnails are not compared: they are rendered with the machine's fonts.
"""

import importlib
import json
import sys
from datetime import date
from itertools import pairwise
from pathlib import Path

import pytest
from PyQt6.QtCore import QTranslator

from open_garden_planner.core.cad_geometry import point_to_segment_distance
from open_garden_planner.core.i18n import _TRANSLATIONS_DIR
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.scene3d.record import PARAM_RADIUS_CM
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.footprints import standing_point
from open_garden_planner.ui.canvas.items import CircleItem, PolylineItem
from open_garden_planner.ui.view3d.snapshot import snapshot_records
from tests.example_specs import SPECS

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(scope="module")
def generator():
    sys.path.insert(0, str(SCRIPTS))
    try:
        yield importlib.import_module("generate_examples")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_the_generator_authors_the_plans_of_the_table_and_no_other(generator):
    """A plan that is in the generator and not in ``tests/example_specs.py`` would ship
    with none of the rules checked on it."""
    assert set(generator.AUTHORS) == set(SPECS)


@pytest.mark.parametrize("slug", sorted(SPECS))
def test_the_shipped_files_are_what_the_generator_makes(qtbot, generator, slug):
    content = generator.example_content(slug)
    assert set(content) == {f"{slug}.ogp", f"{slug}.meta.json", f"de/{slug}.ogp", f"es/{slug}.ogp"}
    for name, expected in content.items():
        shipped = json.loads((BUNDLED_EXAMPLES / name).read_text(encoding="utf-8"))
        assert shipped == expected, f"{name} is stale: rerun scripts/generate_examples.py"


def test_family_garden_gravel_clears_the_projected_birch_canopy(qtbot):
    scene = CanvasScene()
    manager = ProjectManager()
    manager.load(scene, BUNDLED_EXAMPLES / "family-garden.ogp", as_template=True)
    sidecar = json.loads((BUNDLED_EXAMPLES / "family-garden.meta.json").read_text(encoding="utf-8"))
    records = snapshot_records(scene, date.fromisoformat(sidecar["showcase_date"]))
    birch = next(item for item in scene.items() if isinstance(item, CircleItem)
                 and item.metadata.get("plant_species", {}).get("common_name") == "Birch")
    gravel = next(item for item in scene.items()
                  if isinstance(item, PolylineItem) and item.name == "Gravel path")
    centre = standing_point(birch)
    assert centre is not None
    radius = records[str(birch.item_id)].params[PARAM_RADIUS_CM]
    assert isinstance(radius, float) and radius > birch.radius
    route = [gravel.mapToScene(point) for point in gravel.points]
    distance = min(point_to_segment_distance(centre, a, b)[0] for a, b in pairwise(route))
    assert distance - radius - gravel.stroke_width / 2 >= 2.5


@pytest.mark.parametrize("language", ("de", "es"))
def test_example_species_names_match_the_translated_gallery(qtbot, generator, language):
    from example_plans.i18n import localized_plan

    translator = QTranslator()
    assert translator.load(str(_TRANSLATIONS_DIR / f"open_garden_planner_{language}.qm"))
    names = ("Geranium", "Marigold")
    plan = {"objects": [{"metadata": {"plant_species": {"common_name": name}}} for name in names]}
    localized = localized_plan(plan, language)
    assert [
        item["metadata"]["plant_species"]["common_name"] for item in localized["objects"]
    ] == [translator.translate("GalleryData", name) for name in names]


def test_the_check_mode_names_a_stale_file(qtbot, generator, monkeypatch, tmp_path):
    """``--check`` is this comparison for a person: it must not pass on a stale file."""
    for source in BUNDLED_EXAMPLES.glob("balcony.*"):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    for language in ("de", "es"):
        (tmp_path / language).mkdir()
        (tmp_path / language / "balcony.ogp").write_bytes(
            (BUNDLED_EXAMPLES / language / "balcony.ogp").read_bytes())
    monkeypatch.setattr(generator, "BUNDLED_EXAMPLES", tmp_path)
    assert generator.stale_files(["balcony"]) == []

    plan = json.loads((tmp_path / "es" / "balcony.ogp").read_text(encoding="utf-8"))
    plan["objects"][0]["name"] = "edited by hand"
    (tmp_path / "es" / "balcony.ogp").write_text(json.dumps(plan), encoding="utf-8")
    (tmp_path / "balcony.meta.json").unlink()
    assert generator.stale_files(["balcony"]) == ["balcony.meta.json", "es/balcony.ogp"]


def test_a_word_without_a_translation_stops_the_generation(generator):
    """It fell back to English silently, and the translated plan shipped with an English
    name in it. A word outside the translated fields is never touched, even one the table
    knows: a registered word must not rewrite a value that only reads the same."""
    from example_plans.i18n import MissingTranslation, localized_plan

    with pytest.raises(MissingTranslation, match="objects/name"):
        localized_plan({"objects": [{"name": "A name nobody translated"}]}, "de", "demo")
    untouched = {"objects": [{"object_type": "Compost", "name": ""}], "canvas": {"note": "Compost"}}
    assert localized_plan(untouched, "de") == untouched
    assert localized_plan({"objects": [{"name": "Compost"}]}, "es") == {"objects": [{"name": "Compostador"}]}
