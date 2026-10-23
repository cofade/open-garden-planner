"""Plants in the 3D pipeline, end to end (Phase 17 L1.7, #385 — §8.10).

live plant items → ``snapshot_records`` → ``SceneSync`` (plant builder registered)
→ ``RecordingSink``

A real canvas is planted the way a user plants it — gallery drops (the real
``dropEvent``) for a tree, a shrub and perennials of ten archetypes with bundled
species, category plants with a height the user typed, and one tree drawn with
the TREE tool that the plan knows no height for. Then the plan date is scrubbed.

After every step the sink is asserted: each plant's top is the height the 2D
shadow resolves for that date, its widest span is the canopy the 2D shadow
uses, it stands where the item stands, its archetype is the one of the sprite
the canvas draws for it — and a date change rebuilds exactly the plants that
grew. Nothing is rendered: the sink is the recording double (L1.2 runs the same
flow against Qt Quick 3D).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent

from open_garden_planner.core import plant_renderer
from open_garden_planner.core.commands import MoveItemsCommand
from open_garden_planner.core.object_height import METADATA_KEY, effective_height_cm
from open_garden_planner.core.plant_art import SPECIES_SPRITES, SpriteRef
from open_garden_planner.core.plant_height_estimate import ESTIMATED_HEIGHT_PARAM
from open_garden_planner.core.scene3d import (
    MAX_LENGTH_CM,
    PARAM_SPECIES_NAME,
    PARAM_SPRITE_SPECIES,
    BuilderRegistry,
    Record,
    RecordingSink,
    SceneDiff,
    SceneSync,
)
from open_garden_planner.core.scene3d.builders.plants import (
    PART_FOLIAGE,
    PART_WOOD,
    TRIANGLE_BUDGET,
    plant_archetype,
    plant_sprite,
    register,
)
from open_garden_planner.core.tools import ToolType
from open_garden_planner.services.bundled_species_db import lookup_species, merge_calendar_data
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.footprints import plant_canopy_radius_cm
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.plant_species_assignment import apply_species_to_item
from open_garden_planner.ui.view3d.snapshot import SkippedItem, SkipReason, snapshot_records
from open_garden_planner.ui.widgets.gallery_data import (
    GalleryItem,
    all_items,
    build_toolbar_categories,
)

REPO = Path(__file__).resolve().parents[2]
JUNE_2026, JUNE_2027 = date(2026, 6, 21), date(2027, 6, 21)
BEGIN, COMMIT = ("begin", None), ("commit", None)

#: What is planted: label → (gallery MIME tail, archetype the sprite's recipe names).
GALLERY = {
    "apple": ("TREE:species=apple tree", "canopy"),
    "spruce": ("TREE:species=spruce", "conifer"),
    "hydrangea": ("SHRUB:species=hydrangea", "mound"),
    "tomato": ("PERENNIAL:species=tomato", "mound"),
    "lettuce": ("PERENNIAL:species=lettuce", "rosette"),
    "broccoli": ("PERENNIAL:species=broccoli", "head"),
    "leek": ("PERENNIAL:species=leek", "allium"),
    "iris": ("PERENNIAL:species=iris", "grass"),
    "carrot": ("PERENNIAL:species=carrot", "feathery"),
    "sunflower": ("PERENNIAL:species=sunflower", "flower"),
    "cucumber": ("PERENNIAL:species=cucumber", "climber"),
    # no species data, so no height — until the user types one (below)
    "palm": ("TREE:category=PALM", "palm"),
    "hedge": ("SHRUB:category=HEDGE_SECTION", "hedge"),
    "carpet": ("PERENNIAL:category=GROUND_COVER", "ground"),
}
TYPED_HEIGHTS = {"palm": 520.0, "hedge": 140.0, "carpet": 12.0}
WOODY = {"canopy", "conifer", "palm"}
#: measured by the user on the day they were planted: these two grow with the date
MEASURED = {
    "apple": {"planting_date": "2024-04-01", "current_height_cm": 180.0,
              "current_spread_cm": 120.0},
    "tomato": {"planting_date": "2026-05-15", "current_height_cm": 25.0,
               "current_spread_cm": 20.0},
}


def drop(view: CanvasView, mime_tail: str, at: QPointF) -> CircleItem:
    """A gallery drop through the real ``dropEvent``; returns the new plant."""
    before = {id(item) for item in view.scene().items()}
    mime = QMimeData()
    mime.setText(f"gallery:{mime_tail}")
    view.dropEvent(QDropEvent(QPointF(view.mapFromScene(at)), Qt.DropAction.CopyAction, mime,
                              Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    new = [item for item in view.scene().items()
           if isinstance(item, CircleItem) and id(item) not in before]
    assert len(new) == 1
    return new[0]


class Garden:
    """The planted canvas plus the pipeline L1.3 will own, in miniature."""

    def __init__(self, view: CanvasView, mouse_event) -> None:
        self.view = view
        self.scene = view.scene()
        self.plants: dict[str, CircleItem] = {}
        for index, (label, (mime_tail, _archetype)) in enumerate(GALLERY.items()):
            where = QPointF(400.0 + 600.0 * (index % 5), 500.0 + 700.0 * (index // 5))
            self.plants[label] = drop(view, mime_tail, where)
        for label, height in TYPED_HEIGHTS.items():
            self.plants[label].metadata[METADATA_KEY] = height
        for label, instance in MEASURED.items():
            self.plants[label].metadata["plant_instance"] = dict(instance)
        # a tree drawn with the real tool: a click for the centre, one for the rim
        view.set_active_tool(ToolType.TREE)
        tool = view.tool_manager.active_tool
        tool.mouse_press(mouse_event, QPointF(3600.0, 2400.0))
        tool.mouse_press(mouse_event, QPointF(3750.0, 2400.0))
        drawn = [item for item in self.scene.items() if isinstance(item, CircleItem)
                 and item not in self.plants.values()]
        assert len(drawn) == 1
        self.plants["unknown"] = drawn[0]
        registry = BuilderRegistry()
        register(registry)
        self.sink = RecordingSink()
        self.sync = SceneSync(self.sink, registry, validate=True)

    def item_id(self, label: str) -> str:
        return str(self.plants[label].item_id)

    def tick(self, at: date) -> tuple[SceneDiff, list[tuple[str, str | None]], dict[str, Record]]:
        self.sink.clear_calls()
        records = snapshot_records(self.scene, at)
        changes = self.sync.apply(records)
        assert not self.sync.failures, {k: str(v.error) for k, v in self.sync.failures.items()}
        fresh = SceneSync(RecordingSink(), self.sync.registry, validate=True)
        fresh.apply(records)                       # incremental == a build from scratch
        assert isinstance(fresh.sink, RecordingSink)
        assert self.sink.state() == fresh.sink.state()
        return changes, self.sink.ops(), records

    def assert_matches_the_plan(self, records: dict[str, Record], at: date) -> None:
        """Every plant in the sink is the plan's plant: size, place, archetype."""
        for label, item in self.plants.items():
            record = records[self.item_id(label)]
            held = self.sink.item(record.item_id)
            # ── the numbers 2D resolves, asked independently of the record ────────
            height = effective_height_cm(item.object_type, item.metadata, at_date=at)
            radius = plant_canopy_radius_cm(item, at) or item.radius
            assert record.height_cm == height
            assert record.params["radius_cm"] == pytest.approx(radius, abs=1e-6)
            centre = item.mapToScene(item.rect().center())
            assert (held.transform.east_cm, held.transform.north_cm) == pytest.approx(
                (centre.x(), centre.y()), abs=1e-6)
            points = np.concatenate([part.mesh.positions for part in held.parts])
            low, high = points.min(axis=0), points.max(axis=0)
            assert low[2] == pytest.approx(0.0, abs=1e-3)
            assert max(high[0] - low[0], high[1] - low[1]) == pytest.approx(2 * radius, rel=1e-5)
            assert sum(part.mesh.triangle_count for part in held.parts) <= TRIANGLE_BUDGET
            # ── the sprite the canvas draws is the recipe 3D builds ───────────────
            drawn = plant_renderer._resolve_svg_path(
                item.object_type, item.plant_species, item.plant_category)
            sprite = plant_sprite(record)
            assert drawn is not None and sprite is not None
            assert (drawn.parent.name, drawn.stem) == (sprite.group, sprite.name), label
            names = {part.name for part in held.parts}
            if label == "unknown":
                # #557: no height anywhere, but the plan still knows the
                # canopy — the tree renders at the illustrative TREE fallback
                # (labelled estimated) instead of the former low marker.
                assert height is None
                assert record.params.get(ESTIMATED_HEIGHT_PARAM) == pytest.approx(400.0)
                assert plant_archetype(record) == "canopy"
                assert names == {PART_WOOD, PART_FOLIAGE}
                assert all(part.casts_shadow for part in held.parts)
                assert high[2] == pytest.approx(400.0, rel=1e-5)
                continue
            archetype = GALLERY[label][1]
            assert plant_archetype(record) == archetype, label
            assert height is not None and high[2] == pytest.approx(height, rel=1e-5), label
            assert names == ({PART_WOOD, PART_FOLIAGE} if archetype in WOODY else {PART_FOLIAGE})
            assert all(part.casts_shadow for part in held.parts)


@pytest.fixture()
def garden(canvas: CanvasView, mouse_event) -> Garden:
    return Garden(canvas, mouse_event)


def test_a_planted_garden_is_built_to_the_plan_and_grows_with_the_date(garden: Garden) -> None:
    # ── first tick: everything is added, every plant built once ───────────────
    changes, calls, records = garden.tick(JUNE_2026)
    ids = [garden.item_id(label) for label in garden.plants]
    assert sorted(changes.added) == sorted(ids) and len(ids) == 15
    assert calls[0] == BEGIN and calls[-1] == COMMIT
    assert sorted(calls[1:-1]) == sorted(("add", item_id) for item_id in ids)
    assert garden.sync.build_count == 15
    garden.assert_matches_the_plan(records, JUNE_2026)
    # the species plants stand at their species' mature size, the measured two part-grown
    assert records[garden.item_id("spruce")].height_cm == 5000.0
    assert records[garden.item_id("lettuce")].height_cm == 30.0
    assert 180.0 < records[garden.item_id("apple")].height_cm < 800.0
    assert 25.0 < records[garden.item_id("tomato")].height_cm < 200.0

    # ── nothing changed: silence ──────────────────────────────────────────────
    assert garden.tick(JUNE_2026)[:2] == (SceneDiff(), [])

    # ── a year later: exactly the two measured, dated plants regrow ───────────
    june = records
    changes, calls, records = garden.tick(JUNE_2027)
    grown = sorted(garden.item_id(label) for label in MEASURED)
    assert sorted(changes.geometry) == grown
    assert changes == SceneDiff(geometry=changes.geometry)
    assert calls == [BEGIN, *(("replace_geometry", item_id) for item_id in changes.geometry),
                     COMMIT]
    assert garden.sync.build_count == 17                       # two builds, no more
    for label in MEASURED:
        item_id = garden.item_id(label)
        assert records[item_id].height_cm > june[item_id].height_cm
        assert records[item_id].params["radius_cm"] > june[item_id].params["radius_cm"]
    assert records[garden.item_id("tomato")].height_cm == 200.0   # an annual: full grown
    garden.assert_matches_the_plan(records, JUNE_2027)

    # ── scrubbing back shrinks them again; the others were never touched ──────
    changes, calls, records = garden.tick(JUNE_2026)
    assert sorted(changes.geometry) == grown and garden.sync.build_count == 19
    assert records == june
    garden.assert_matches_the_plan(records, JUNE_2026)


def test_moving_a_plant_re_poses_it_and_builds_nothing(garden: Garden) -> None:
    garden.tick(JUNE_2026)
    built = garden.sync.build_count
    tree = garden.plants["apple"]
    garden.view.command_manager.execute(MoveItemsCommand([tree], QPointF(250.0, -125.0)))
    changes, calls, records = garden.tick(JUNE_2026)
    assert changes == SceneDiff(transform=(garden.item_id("apple"),))
    assert calls == [BEGIN, ("update_transform", garden.item_id("apple")), COMMIT]
    assert garden.sync.build_count == built
    garden.assert_matches_the_plan(records, JUNE_2026)


def test_a_typed_height_turns_the_placeholder_into_a_tree_and_back(garden: Garden) -> None:
    """The tree drawn with the tool has no species and no measurement: the plan
    knows its canopy, not its height. 3D shows the illustrative estimated TREE
    form (#557) — until a height is typed into the Properties panel's field
    (``object_height_cm``), and back again when it is cleared."""
    _, _, records = garden.tick(JUNE_2026)
    unknown, item_id = garden.plants["unknown"], garden.item_id("unknown")
    assert {part.name for part in garden.sink.item(item_id).parts} == {PART_WOOD, PART_FOLIAGE}
    assert plant_archetype(records[item_id]) == "canopy"   # estimated TREE form
    assert records[item_id].height_cm is None
    assert records[item_id].params.get(ESTIMATED_HEIGHT_PARAM) == pytest.approx(400.0)

    unknown.metadata[METADATA_KEY] = 650.0
    changes, calls, records = garden.tick(JUNE_2026)
    assert changes == SceneDiff(geometry=(item_id,))
    assert calls == [BEGIN, ("replace_geometry", item_id), COMMIT]
    held = garden.sink.item(item_id)
    assert {part.name for part in held.parts} == {PART_WOOD, PART_FOLIAGE}
    assert plant_archetype(records[item_id]) == "canopy"       # a TREE's default sprite
    assert max(float(part.mesh.positions[:, 2].max()) for part in held.parts) == pytest.approx(650.0)
    assert all(part.casts_shadow for part in held.parts) and records[item_id].casts_shadow

    del unknown.metadata[METADATA_KEY]
    changes, calls, records = garden.tick(JUNE_2026)
    assert calls == [BEGIN, ("replace_geometry", item_id), COMMIT]
    assert {part.name for part in garden.sink.item(item_id).parts} == {PART_WOOD, PART_FOLIAGE}
    assert records[item_id].height_cm is None
    assert plant_archetype(records[item_id]) == "canopy"   # back to the estimated form


def test_the_placeholder_means_the_plan_gives_no_height_and_nothing_else(garden: Garden) -> None:
    """What ``height_cm is None`` says: NO source of the plan gives this plant a
    height (#557: the pipeline then renders the estimated category form, and
    the neutral marker remains for plants with no resolvable sprite or no
    canopy circle). It does not say "a height the pipeline could not use":

    - a typed height that is infinite or beyond 10 km (``MAX_LENGTH_CM``; a
      hand-edited plan) gives the plant NO record: it is left out and reported
      (``out_of_range``), not shown as a marker. (Until the scene contract's
      second fix round an infinite height silently became ``height_cm=None`` —
      a marker saying "no height" about a plant that had one.)
    - a typed height that is no positive number (0, negative, NaN, text, a bool)
      is no typed height at all — ``core.object_height`` reads it so for the 2D
      shadow too — and the next source decides: none for a drawn tree (the
      estimated form), the species' size for a species plant.
    """
    garden.tick(JUNE_2026)
    unknown, unknown_id = garden.plants["unknown"], garden.item_id("unknown")
    apple, apple_id = garden.plants["apple"], garden.item_id("apple")
    grown_apple = effective_height_cm(apple.object_type, apple.metadata, at_date=JUNE_2026)
    assert grown_apple is not None and 180.0 < grown_apple < 800.0

    for beyond in (float("inf"), 2.0e6, 1.0e300):
        unknown.metadata[METADATA_KEY] = beyond
        skipped: list[SkippedItem] = []
        records = snapshot_records(garden.scene, JUNE_2026, skipped=skipped)
        assert unknown_id not in records, beyond
        assert [(s.item_id, s.kind, s.reason) for s in skipped] == [
            (unknown_id, "TREE", SkipReason.OUT_OF_RANGE)], beyond
        garden.sync.apply(records)
        assert not garden.sync.failures
        assert unknown_id not in garden.sink.item_ids()        # left out: no marker, no plant
        assert len(garden.sink.item_ids()) == 14

    unknown.metadata[METADATA_KEY] = MAX_LENGTH_CM              # the tallest a plan can hold: a plant
    records = snapshot_records(garden.scene, JUNE_2026)
    garden.sync.apply(records)
    assert not garden.sync.failures
    assert plant_archetype(records[unknown_id]) == "canopy"
    held = garden.sink.item(unknown_id)
    assert max(float(part.mesh.positions[:, 2].max()) for part in held.parts) == pytest.approx(
        MAX_LENGTH_CM, rel=1e-6)

    for nothing in (0.0, -5.0, float("nan"), "tall", True, None):
        unknown.metadata[METADATA_KEY] = nothing
        apple.metadata[METADATA_KEY] = nothing
        skipped = []
        records = snapshot_records(garden.scene, JUNE_2026, skipped=skipped)
        assert not skipped, nothing
        assert records[unknown_id].height_cm is None, nothing   # the plan gives it no height
        assert plant_archetype(records[unknown_id]) == "canopy", nothing  # estimated form, not the marker
        assert records[apple_id].height_cm == grown_apple       # its measured, dated size decides
        assert plant_archetype(records[apple_id]) == "canopy"
        garden.sync.apply(records)
        assert {part.name for part in garden.sink.item(unknown_id).parts} == {PART_WOOD, PART_FOLIAGE}
    del unknown.metadata[METADATA_KEY], apple.metadata[METADATA_KEY]


def test_a_species_assigned_from_the_database_is_built_as_the_canvas_draws_it(
    garden: Garden,
) -> None:
    """Assigning a species from the plant database (``ApplySpeciesCommand``) writes
    the item's species DATA *and* its species STRING (#445). The canvas resolves
    its sprite from the string, so the plant is drawn with the oak's sprite -
    and 3D builds that same sprite's recipe (ruling R14: the record carries the
    item's own string, and the builder resolves from it). The data still decides
    the size: the oak's 40 m.

    It used to write only the data, and the plant kept the tree's default
    sprite in both views - 2D and 3D agreed, but on the wrong plant."""
    unknown, item_id = garden.plants["unknown"], garden.item_id("unknown")
    oak = lookup_species("oak")
    assert oak is not None
    apply_species_to_item(unknown, merge_calendar_data(dict(oak)))   # the app's own path
    assert unknown.plant_species == "Oak"
    assert unknown.metadata["plant_species"]["common_name"] == "Oak"
    _changes, _calls, records = garden.tick(JUNE_2026)
    record = records[item_id]
    assert record.height_cm == 4000.0                          # the data gives a height now
    assert record.params[PARAM_SPECIES_NAME] == "Oak"          # ... and a name, for labels
    assert record.params[PARAM_SPRITE_SPECIES] == "Oak"        # the item's own string
    drawn = plant_renderer._resolve_svg_path(
        unknown.object_type, unknown.plant_species, unknown.plant_category)
    sprite = plant_sprite(record)
    assert drawn is not None and sprite is not None
    assert (drawn.parent.name, drawn.stem) == ("species", "oak")   # 2D
    assert (sprite.group, sprite.name) == ("species", "oak")       # 3D: the same


def _drag_data(entry: GalleryItem) -> str:
    """What the gallery puts on the drag (``ui/widgets/category_dropdown.py``)."""
    data = entry.tool_type.name
    if entry.species:
        data += f":species={entry.species}"
    if entry.plant_category:
        data += f":category={entry.plant_category.name}"
    return data


def _drawn_and_built(view: CanvasView, items: list[CircleItem]) -> list[tuple[str, str, str]]:
    """(species string, sprite the canvas draws, sprite 3D builds) of every item where
    the two differ — through the real scene and ``snapshot_records``."""
    records = snapshot_records(view.scene(), JUNE_2026)
    different = []
    for item in items:
        record = records[str(item.item_id)]
        drawn = plant_renderer._resolve_svg_path(
            item.object_type, item.plant_species, item.plant_category)
        built = plant_sprite(record)
        assert drawn is not None and built is not None
        if (drawn.parent.name, drawn.stem) != (built.group, built.name):
            different.append((item.plant_species, f"{drawn.parent.name}/{drawn.stem}",
                              f"{built.group}/{built.name}"))
        assert record.params.get(PARAM_SPRITE_SPECIES, "") == item.plant_species   # raw
    return different


def test_every_gallery_plant_is_built_as_the_sprite_the_canvas_draws(canvas: CanvasView) -> None:
    """ALL plants of the gallery — every species and every category it offers —
    dropped through the real ``dropEvent`` with the drag data the gallery
    composes: the sprite the canvas draws is the recipe 3D builds. The first
    version of this file checked 11 of them and missed the pumpkin: its gallery
    string is "pumpkin", its bundled species data is named "Winter Squash", and
    3D — which resolved from the data's name — built the squash (review round 1,
    P1-2)."""
    plant_tools = (ToolType.TREE, ToolType.SHRUB, ToolType.PERENNIAL)
    entries = [entry for entry in all_items(build_toolbar_categories())
               if entry.tool_type in plant_tools and (entry.species or entry.plant_category)]
    with_species = [entry for entry in entries if entry.species]
    assert len(with_species) >= 85 and len(entries) - len(with_species) >= 12
    items = [drop(canvas, _drag_data(entry),
                  QPointF(80.0 + 110.0 * (n % 40), 200.0 + 400.0 * (n // 40)))
             for n, entry in enumerate(entries)]
    assert _drawn_and_built(canvas, items) == []
    pumpkin = next(item for item in items if item.plant_species == "pumpkin")
    assert pumpkin.metadata["plant_species"]["common_name"] == "Winter Squash"   # the trap
    record = snapshot_records(canvas.scene(), JUNE_2026)[str(pumpkin.item_id)]
    assert record.params[PARAM_SPECIES_NAME] == "Winter Squash"
    assert record.params[PARAM_SPRITE_SPECIES] == "pumpkin"
    assert plant_sprite(record) == SpriteRef("species", "pumpkin")


def test_every_species_string_is_built_as_the_sprite_the_canvas_draws(canvas: CanvasView) -> None:
    """Every key of the species map — 222 strings, on a tree, a shrub and a
    perennial in turn — and the strings the 2D rule is odd about (title case,
    blanks around, blanks ONLY, a name that partially matches another plant's
    key, a name the tables do not know): drawn and built from the same sprite."""
    odd = [" Rose ", "ROSE", "   ", " \t ", "Lemon Balm", "Melon", "Bean (Bush)", "Sweet Cherry",
           "no such plant", "e", "Wild Rose Hip", "sweet potato", "Winter Squash", "Watermelon"]
    strings = [*SPECIES_SPRITES, *(key.title() for key in list(SPECIES_SPRITES)[::9]), *odd]
    assert len(SPECIES_SPRITES) == 222 and not any(":" in text for text in strings)
    tools = ("TREE", "SHRUB", "PERENNIAL")
    items = [drop(canvas, f"{tools[n % 3]}:species={text}",
                  QPointF(80.0 + 110.0 * (n % 40), 200.0 + 300.0 * (n // 40)))
             for n, text in enumerate(strings)]
    assert [item.plant_species for item in items] == strings        # set as dropped, untouched
    assert _drawn_and_built(canvas, items) == []
    # ... and a string of blanks is no species at all: it takes the category's
    # sprite (#446 - the old substring rule answered the rose for it)
    blanks = items[strings.index("   ")]
    drawn = plant_renderer._resolve_svg_path(blanks.object_type, blanks.plant_species, None)
    assert drawn is not None and (drawn.parent.name, drawn.stem) == (
        "categories", "round_deciduous")


# ── the story's measuring script, run as documented, outside pytest ───────────

#: What the child process runs: the script as ``python scripts/measure_plant_art_3d.py``
#: would execute it, then its ``scrub`` — which loads both bench plans. It REFUSES to
#: load anything unless the settings names are a test key: were the script's isolation
#: broken, this test must fail without writing the developer's recent files.
_MEASURE_DRIVER = """
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("measure_script", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules["measure_script"] = module
spec.loader.exec_module(module)
import open_garden_planner.app.settings as settings
if settings.ORGANIZATION_NAME != "cofade_test":
    print("RESULT " + json.dumps({"isolated": False, "organization": settings.ORGANIZATION_NAME}))
    raise SystemExit(0)
sys.argv = ["measure_plant_art_3d.py", "scrub", "--days", "1"]
module.main()
from open_garden_planner.services.plant_library import get_app_data_dir
store = settings.create_qsettings()
print("RESULT " + json.dumps({
    "isolated": True,
    "organization": settings.ORGANIZATION_NAME, "application": settings.APPLICATION_NAME,
    "store": [store.organizationName(), store.applicationName()],
    "recent_files": [os.path.basename(p) for p in (store.value("recent_files") or [])],
    "root": str(module.ISOLATED_PROFILE),
    "environment": {name: os.environ.get(name, "") for name in module._PROFILE_VARIABLES},
    "app_data_dir": str(get_app_data_dir()),
}))
"""


def test_the_measuring_script_keeps_out_of_the_owner_s_stores(tmp_path: Path) -> None:
    """``scripts/measure_plant_art_3d.py scrub`` loads plans, and ``ProjectManager.load``
    ends with ``add_recent_file`` — outside pytest a write to the developer's REAL
    settings (on Windows the registry; no environment variable redirects it). Run by
    hand, the script put the two bench plans at the top of the owner's recent-files
    list, every time. It isolates itself now, as ``tests/conftest.py`` does for the
    suite; this runs it in a child process that has no conftest:

    - the settings names are a per-process TEST key, and the loads' ``recent_files``
      write landed THERE;
    - the profile variables — and so the app-data directory — point into a temporary
      directory of the script's own, not at what the environment handed it;
    - nothing was written under the directories the environment handed it, and the
      temporary profile is gone when the process has exited.
    """
    script = REPO / "scripts" / "measure_plant_art_3d.py"
    handed = {name: tmp_path / "handed" / name for name in ("USERPROFILE", "APPDATA", "LOCALAPPDATA")}
    for directory in handed.values():
        directory.mkdir(parents=True)
    environment = {**os.environ, **{name: str(path) for name, path in handed.items()},
                   "PYTHONPATH": str(REPO / "src"), "QT_QPA_PLATFORM": "offscreen"}
    done = subprocess.run([sys.executable, "-c", textwrap.dedent(_MEASURE_DRIVER), str(script)],
                          env=environment, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=170, check=False)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
    line = next(line for line in done.stdout.splitlines() if line.startswith("RESULT "))
    result = json.loads(line.removeprefix("RESULT "))
    assert result["isolated"], result
    # ── the settings: a test key, and the loads wrote their recent files into it ──
    assert result["organization"] == "cofade_test" == result["store"][0]
    assert result["application"].startswith("Open Garden Planner Measure ")
    assert result["store"][1] == result["application"]
    assert sorted(result["recent_files"]) == ["bench_large.ogp", "bench_small.ogp"]
    assert "settings key: cofade_test / Open Garden Planner Measure" in done.stdout
    # ── the profile: the script's own temporary one, not the one it was handed ───
    root = Path(result["root"])
    for name, value in result["environment"].items():
        assert Path(value).is_relative_to(root), (name, value)
        assert name not in handed or Path(value) != handed[name]
    assert Path(result["app_data_dir"]).is_relative_to(root)
    assert [path for directory in handed.values() for path in directory.rglob("*")] == []
    assert not root.exists()                               # removed at exit


def test_inside_pytest_the_measuring_script_leaves_the_suite_s_isolation_alone() -> None:
    """Loaded in a process that is isolated already (this one: ``tests/conftest.py``),
    the script changes nothing — it must not swap the suite's test key for its own."""
    import open_garden_planner.app.settings as settings

    before = (settings.ORGANIZATION_NAME, settings.APPLICATION_NAME, os.environ.get("APPDATA"))
    assert before[0] == "cofade_test"
    path_before = list(sys.path)
    spec = importlib.util.spec_from_file_location(
        "measure_plant_art_3d_in_pytest", REPO / "scripts" / "measure_plant_art_3d.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        assert module.ISOLATED_PROFILE is None
        assert module.isolate() is None
        assert (settings.ORGANIZATION_NAME, settings.APPLICATION_NAME,
                os.environ.get("APPDATA")) == before
        assert module.TEST_ORGANIZATION == "cofade_test"
    finally:
        sys.path[:] = path_before                          # the script puts its checkout first
