"""Author the offline example plans and thumbnails through production paths.

Run from the repository root. Layouts are illustrative, not climate prescriptions.
Deterministic IDs and dates keep content reviewable across regenerations.

Each plan is one module of the ``example_plans`` package beside this script, which is the
command line and the one place the shipped files come from. ``family-garden`` is the 3D
view's showcase: the very plan the bench fixture ``bench_small.ogp`` is.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

os.environ.setdefault("QT_QPA_PLATFORM", "minimal:enable_fonts")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import script_isolation

if __name__ == "__main__":
    script_isolation.isolate_profile()

from example_plans import PLANS
from example_plans.authoring import hint_layer_id
from example_plans.i18n import localized_plan
from example_plans.thumbnails import thumbnail
from example_plans.tours import SUN_BEHIND_DEG, Framing, orbit_tour, showcase_moment
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.camera_tours import DEFAULT_ORBIT_PITCH_DEG, load_tours
from open_garden_planner.core.plan_io import write_plan
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


def _stable_ids(value, slug, identities=None, keep=lambda _id: False):
    """``value`` with every id replaced by one numbered in the order the ids appear.
    An id ``keep`` says yes to stays: it is one the plan gave itself."""
    identities = {} if identities is None else identities
    if isinstance(value, str):
        try:
            UUID(value)
        except ValueError:
            return value
        if keep(value):
            return value
        if value not in identities:
            identities[value] = str(uuid5(NAMESPACE_URL, f"ogp-example/{slug}/{len(identities)}"))
        return identities[value]
    if isinstance(value, dict):
        return {_stable_ids(k, slug, identities, keep): _stable_ids(v, slug, identities, keep)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_stable_ids(v, slug, identities, keep) for v in value]
    return value


def _own_ids(raw, slug, ids):
    """The plan with ids that are the same on every run. How, is the plan module's ``IDS``:

    - ``"keyed"`` (the default): every item id is made from what the item is and where it
      stands, so adding an item changes no other id; a plant's sprite turn and 3D shape
      are seeded by its id. Only ids the app made at random are numbered.
    - ``"serial"``: the three first plans. Every id is numbered in the order it appears,
      except the hint layer's own and those a module names in ``OWN_IDS``, so that giving
      a plan that layer, or the food forest its orchard, renumbered no item that was there.
    - ``"bench"``: the showcase keeps the bench plan's ids, which are fixed by its seed.
    """
    if ids == "bench":
        return raw
    if ids == "serial":
        own = {str(hint_layer_id(slug)), *getattr(PLANS[slug], "OWN_IDS", ())}
        return _stable_ids(raw, slug, keep=lambda value: value in own)
    assert ids == "keyed", ids
    return _stable_ids(raw, slug + "/made", keep=lambda value: UUID(value).version == 5)


AUTHORS = {slug: plan.build for slug, plan in PLANS.items()}
METADATA = {slug: plan.META for slug, plan in PLANS.items()}
LANGUAGES = ("de", "es")
ATTRIBUTION = {
    "license": "CC-BY-SA-4.0",
    "attribution": "Open Garden Planner contributors; CC-BY-SA-4.0; see PROVENANCE.md.",
    "attribution_en": "Open Garden Planner contributors; bundled CC-BY-SA-4.0 species data; see PROVENANCE.md.",
    "attribution_de": "Mitwirkende von Open Garden Planner; mitgelieferte Artendaten unter CC-BY-SA-4.0; siehe PROVENANCE.md.",
    "attribution_es": "Colaboradores de Open Garden Planner; datos de especies incluidos bajo CC-BY-SA-4.0; véase PROVENANCE.md.",
    "attribution_ru": "Авторы Open Garden Planner; встроенные данные видов под лицензией CC-BY-SA-4.0; см. PROVENANCE.md.",
}


def example_content(slug):
    """What ships for ``slug``, as data: ``{file name under examples/: JSON content}``.

    The canonical English plan, its ``de/`` and ``es/`` copies and the sidecar. The one
    place the shipped files come from: ``main`` writes it, ``--check`` and
    ``tests/integration/test_example_generation.py`` compare the shipped files with it.
    """
    module = PLANS[slug]
    scene, manager = AUTHORS[slug]()
    for item in scene.items():
        if hasattr(item, "label_visible"):
            item.label_visible = False
    framing = Framing(scene, manager, module.META,
                      pitch_deg=getattr(module, "ORBIT_PITCH_DEG", DEFAULT_ORBIT_PITCH_DEG),
                      sun_offset_deg=getattr(module, "ORBIT_SUN_OFFSET_DEG", SUN_BEHIND_DEG),
                      closer=getattr(module, "ORBIT_CLOSER", 1.0))
    manager.set_camera_tours([orbit_tour(framing.orbit()),
                              *getattr(module, "more_tours", lambda _framing: [])(framing)])
    raw = manager._build_project_data(scene).to_dict()
    raw["metadata"] = {"modified": "2026-10-26T00:00:00+00:00"}
    scene.clear()
    plan = _own_ids(raw, slug, getattr(module, "IDS", "keyed"))
    content = {slug + ".ogp": plan, slug + ".meta.json": METADATA[slug] | ATTRIBUTION}
    for language in LANGUAGES:
        content[f"{language}/{slug}.ogp"] = localized_plan(plan, language, slug)
    for name, copy in content.items():
        if name.endswith(".ogp"):
            # a name over 60 characters or one used twice would be dropped on load, silently
            tours, skipped = load_tours(copy["camera_tours"])
            assert not skipped and len(tours) == len(copy["camera_tours"]), (name, skipped)
    return content


def stale_files(slugs):
    """The shipped plan and sidecar files that are not what the generator makes now."""
    stale = []
    for slug in slugs:
        for name, expected in example_content(slug).items():
            shipped = BUNDLED_EXAMPLES / name
            if not shipped.is_file() or json.loads(shipped.read_text(encoding="utf-8")) != expected:
                stale.append(name)
    return stale


def main(argv=None):
    script_isolation.isolate()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("slugs", nargs="*", metavar="slug",
                        help="the example plans to regenerate (default: all): " + ", ".join(AUTHORS))
    parser.add_argument("--check", action="store_true",
                        help="compare the shipped plans and sidecars with what the generator makes; "
                             "write nothing (thumbnails are not compared: fonts differ by machine)")
    args = parser.parse_args(argv)
    if unknown := set(args.slugs) - set(AUTHORS):
        parser.error(f"no such example: {', '.join(sorted(unknown))}")
    app = QApplication.instance() or QApplication([])
    slugs = args.slugs or list(AUTHORS)
    if args.check:
        stale = stale_files(slugs)
        for name in stale:
            print(f"STALE: {name} - rerun scripts/generate_examples.py")
        print("examples: " + ("FAIL" if stale else "OK"))
        return 1 if stale else 0
    BUNDLED_EXAMPLES.mkdir(parents=True, exist_ok=True)
    manager = ProjectManager()
    scene = CanvasScene()
    for slug in slugs:
        for name, content in example_content(slug).items():
            path = BUNDLED_EXAMPLES / name
            path.parent.mkdir(exist_ok=True)
            if path.suffix == ".ogp":
                write_plan(path, content)
            else:
                path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Render the saved content itself, including its stable sprite seed IDs. One
        # picture serves every language: the hint layer, the only text in a plan, is hidden.
        path = BUNDLED_EXAMPLES / (slug + ".ogp")
        manager.load(scene, path, as_template=True)
        # At the plan's showcase moment, as the app shows it: plants are drawn at the
        # size they have on that day, and what is planted later is not there yet.
        clock = SimClock()
        clock.set_utc_time_on(*showcase_moment(METADATA[slug]))
        scene.bind_plan_clock(clock)
        for layer in scene.layers:
            if layer.id == hint_layer_id(slug):
                scene.update_layer_visibility(layer.id, False)
        thumbnail(scene, path.with_suffix(".png"), getattr(PLANS[slug], "THUMBNAIL", None))
        for language in LANGUAGES:
            (BUNDLED_EXAMPLES / language / (slug + ".png")).unlink(missing_ok=True)
        scene.clear()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
