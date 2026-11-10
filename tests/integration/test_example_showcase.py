"""#795: a bundled example opens in a showcase state, however late the wall clock is.

Every test drives the gallery's own path (File > New from example > Open Selected
ends in ``GardenPlannerApp._open_template_file``) in a real main window whose
session clock was seeded late in the evening, when the sun is long down.
"""

import json
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core import sim_clock
from open_garden_planner.core.object_types import is_plant_type
from open_garden_planner.core.solar import solar_position
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.models.seed_inventory import get_seed_inventory
from open_garden_planner.services.example_library import bundled_examples
from open_garden_planner.ui.canvas.sun_shadow_controller import STATE_ACTIVE, STATE_NIGHT

#: The instant the session starts at: 22:30 on a November evening in Germany, where all
#: four gardens lie. An instant and not a wall reading: the sun is down over the gardens
#: then on a machine in any time zone, so no assertion below depends on where the suite
#: runs (the clock reads wall time in the machine's zone).
LATE = datetime(2026, 11, 10, 21, 30, tzinfo=UTC)
#: Each example's reference date (its sidecar's ``showcase_date``).
REFERENCE = {"family-garden": date(2026, 6, 21), "food-forest": date(2026, 9, 21),
             "raised-bed": date(2026, 9, 21), "balcony": date(2026, 9, 21)}
SLUGS = tuple(REFERENCE)


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(sim_clock, "_now_to_the_minute", lambda: LATE)
    monkeypatch.setattr("open_garden_planner.services.example_library.user_templates_dir", lambda: tmp_path)
    get_settings().show_welcome_on_startup = False
    win = GardenPlannerApp()
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    qtbot.addWidget(win)
    assert win._sim_clock.utc == LATE
    #: the wall reading the user's session started with, in this machine's zone
    win.started_at = win._sim_clock.wall
    return win


def entry_of(slug, language="en"):
    return next(entry for entry in bundled_examples(language) if entry.path.stem == slug)


def open_example(window, slug, language="en"):
    entry = entry_of(slug, language)
    window._open_template_file(str(entry.path))
    assert window._project_manager.current_file is None, "an example opens as an untitled copy"
    return entry


def plants_by_id(window):
    return {str(item.item_id): item for item in window.canvas_scene.items()
            if is_plant_type(getattr(item, "object_type", None))}


# ── 1. the sun ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("slug", SLUGS)
def test_an_example_opens_in_daylight_on_its_reference_date_however_late_it_is(window, slug):
    settings = get_settings()._settings
    before = {key: settings.value(key) for key in settings.allKeys()}

    open_example(window, slug)

    clock = window._sim_clock
    assert clock.plan_date == REFERENCE[slug]
    assert clock.utc.time() == time(11, 0), "13:00 on a wall clock in the example's own place"
    place = window._project_manager.location
    sun = solar_position(place["latitude"], place["longitude"], clock.utc)
    assert sun.elevation_deg > 30, f"{slug}: the sun stands {sun.elevation_deg:.1f} degrees up"
    assert window._sun_controller.state == STATE_ACTIVE, "the plan is not night-dimmed"
    # the toolbar is a view of the one clock and shows the moment it stands at
    assert window._sun_toolbar.current_wall_datetime() == clock.wall
    # session state only: no setting was written, so no later session starts there
    assert {key: settings.value(key) for key in settings.allKeys()} == before


@pytest.mark.parametrize("language", ("de", "es"))
def test_a_translated_example_opens_at_the_same_moment(window, language):
    open_example(window, "raised-bed")
    english = window._sim_clock.instant
    open_example(window, "raised-bed", language)
    assert window._sim_clock.instant == english
    assert window._sim_clock.plan_date == REFERENCE["raised-bed"]


def test_the_next_document_gets_the_users_own_reading_back(window, tmp_path):
    clock = window._sim_clock
    own_plan = tmp_path / "own.ogp"
    window._save_to_file(own_plan)

    # a new plan after an example: the evening the session started at
    open_example(window, "family-garden")
    window._new_project_document(width_cm=1000, height_cm=800)
    assert clock.wall == window.started_at and clock.utc == LATE

    # the user's own setting, two examples in a row, a scrub inside the example
    mine = datetime(2026, 5, 1, 9, 15)
    window._on_sun_sim_datetime(mine)                 # the toolbar's writer
    open_example(window, "family-garden")
    open_example(window, "balcony")
    assert clock.plan_date == REFERENCE["balcony"]
    window._on_sun_sim_datetime(datetime(2026, 9, 21, 17, 30))   # the tutorial's own step
    window._open_project_file(str(own_plan))
    assert clock.wall == mine, "the user's plan opens on the reading the user chose"

    # and without an example in between nothing is put back: the clock is the user's
    later = datetime(2026, 7, 4, 16, 0)
    window._on_sun_sim_datetime(later)
    window._new_project_document(width_cm=1000, height_cm=800)
    assert clock.wall == later


def test_a_plan_saved_from_an_example_is_the_users_plan(window, tmp_path):
    clock = window._sim_clock
    open_example(window, "food-forest")
    showcase = clock.instant
    saved = tmp_path / "my-forest.ogp"
    window._save_to_file(saved)

    # saving does not turn the lights off under the user's eyes ...
    assert clock.instant == showcase
    # ... and the file carries no clock: nothing of the example's moment is in it
    plan = json.loads(saved.read_text(encoding="utf-8"))
    assert not [key for key in plan if "showcase" in key or "clock" in key or "date" in key]
    assert "2026-09-21T" not in saved.read_text(encoding="utf-8")

    # reopened, it is a plan like any other of the user's: their reading, their night
    window._new_project_document(width_cm=1000, height_cm=800)
    window._open_project_file(str(saved))
    assert window._project_manager.current_file == saved
    assert clock.wall == window.started_at and clock.utc == LATE
    assert window._sun_controller.state == STATE_NIGHT


# ── 2. the tabs ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("language", ("en", "de"))
def test_the_harvest_tab_shows_a_fictional_history_that_fits_the_plants(window, slug, language):
    open_example(window, slug, language)
    window._tab_widget.setCurrentWidget(window.harvest_view)
    view = window.harvest_view
    assert view._table.rowCount() >= 3 and not view._table.isHidden()
    assert view._empty_label.isHidden() and view._export_btn.isEnabled()

    plants = plants_by_id(window)
    logs = window._project_manager.harvest_logs
    shown = {view._table.item(row, 0).text() for row in range(view._table.rowCount())}
    for target, history in logs.items():
        plant = plants[target]                       # a plant of this very plan
        species = plant.metadata["plant_species"]
        assert history["species_key"] == species_key(species)     # the canonical key (ADR-016)
        assert history["species_name"] == species["common_name"] in shown
        planted = plant.metadata["plant_instance"]["planting_date"]
        assert history["records"]
        for record in history["records"]:
            assert planted <= record["date"] <= REFERENCE[slug].isoformat(), (slug, record)
            assert record["quantity"] > 0 and record["unit"] in {"kg", "g", "pcs", "bunch"}
            assert record["notes"], "every entry says that it is fictional"
            if language == "en":
                assert "Fictional" in record["notes"]
            assert "journal_note_id" not in record, "an example copy carries no journal"


@pytest.fixture
def empty_seed_store(monkeypatch):
    """The process-wide seed store, empty for this test and never written."""
    store = get_seed_inventory()
    monkeypatch.setattr(store, "_packets", {})

    def refuse() -> None:
        raise AssertionError("the seed store's file was written")

    monkeypatch.setattr(store, "save", refuse)
    return store


def test_the_seed_inventory_stays_the_users_own_and_says_so(window, empty_seed_store):
    open_example(window, "raised-bed")
    assert empty_seed_store.all() == [], "an example puts nothing into the user's seed store"
    assert window._project_manager.snapshot_dict(window.canvas_scene).get("seed_inventory", []) == []

    window._tab_widget.setCurrentWidget(window.seed_inventory_view)
    view = window.seed_inventory_view
    assert view._store is empty_seed_store
    assert not view._empty_label.isHidden() and view._table.isHidden()
    assert "Add Packet" in view._empty_label.text()


def test_the_seed_inventory_shows_its_table_once_it_holds_a_packet(window, empty_seed_store):
    from open_garden_planner.models.seed_inventory import SeedPacket

    view = window.seed_inventory_view
    view.refresh()
    assert not view._empty_label.isHidden() and view._table.isHidden()
    empty_seed_store.add(SeedPacket(species_name="Carrot", purchase_year=2026, quantity=1.0))
    view.refresh()
    assert view._empty_label.isHidden() and not view._table.isHidden()


def test_plant_details_show_a_bundled_plant_as_the_plan_draws_it(window, qtbot):
    open_example(window, "family-garden")
    magnolia = next(item for item in plants_by_id(window).values()
                    if item.metadata["plant_species"]["common_name"] == "Magnolia")
    assert not magnolia.metadata["plant_species"].get("thumbnail_url")
    window.canvas_scene.clearSelection()
    magnolia.setSelected(True)
    panel = window.plant_database_panel
    qtbot.waitUntil(lambda: panel._current_plant_item is magnolia)

    tile = panel._profile_thumbnail
    assert tile.text() == "", "no seedling placeholder"
    picture = tile.pixmap()
    assert picture is not None and not picture.isNull()
    image = picture.toImage()
    painted = sum(1 for x in range(0, image.width(), 4) for y in range(0, image.height(), 4)
                  if image.pixelColor(x, y).alpha() > 200)
    assert painted > 100, "the plant's sprite fills the tile"


# ── 3. the report's title ───────────────────────────────────────────────────


@pytest.mark.parametrize("language", ("en", "de", "es", "ru"))
def test_the_pdf_cover_is_titled_with_the_examples_name_in_the_users_language(
        window, monkeypatch, language):
    from open_garden_planner.ui.dialogs.pdf_report_dialog import PdfReportDialog

    monkeypatch.setattr(get_settings(), "language", language)
    entry = open_example(window, "family-garden", language)
    meta = json.loads((Path(entry.path).parent.parent if language in ("de", "es") else Path(entry.path).parent)
                      .joinpath("family-garden.meta.json").read_text(encoding="utf-8"))
    assert entry.name == meta[f"name_{language}"] != "family-garden"

    offered = []

    def cancel(dialog):
        offered.append(dialog.project_name)
        return PdfReportDialog.DialogCode.Rejected

    monkeypatch.setattr(PdfReportDialog, "exec", cancel)
    window._on_export_pdf_report()
    assert offered == [entry.name]
    # the status bar names the example too, never its path inside the application
    assert entry.name in window.statusBar().currentMessage()
    assert "examples" not in window.statusBar().currentMessage()


# ── 4. the diagnostics list ─────────────────────────────────────────────────


def test_unevaluated_sun_exposure_is_one_row_that_selects_its_plants(window, qtbot):
    open_example(window, "raised-bed")
    panel = window.diagnostics_panel
    qtbot.waitUntil(lambda: sum(record.kind == "sun_evaluation" for record in panel.records) == 174,
                    timeout=10000)
    texts = [panel.rows.item(index).text() for index in range(panel.rows.count())]
    folded = [text for text in texts if "174" in text]
    assert len(folded) == 1 and panel.rows.count() < 10, texts
    assert panel.count_label.text().startswith(f"{panel.rows.count()} of {panel.rows.count()} ")
    # the records stay one per plant: what an agent reads is unchanged
    assert len(panel.records) >= 174

    row = panel.rows.item(texts.index(folded[0]))
    assert len(row.data(Qt.ItemDataRole.UserRole)) >= 1
    panel.rows.itemClicked.emit(row)
    qtbot.waitUntil(lambda: len(window.canvas_scene.selectedItems()) >= 1)
