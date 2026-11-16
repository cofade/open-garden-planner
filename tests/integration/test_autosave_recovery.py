"""Recovery keeps the same complete document as Save (#797), without marking it saved."""

from dataclasses import fields
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.camera_path import CameraKey
from open_garden_planner.core.camera_tours import SavedTour
from open_garden_planner.core.plan_io import read_plan
from open_garden_planner.core.project import ProjectData, ProjectManager
from open_garden_planner.models.journal_note import JournalNote
from open_garden_planner.services.autosave_service import AutoSaveManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem


def populated_project(scene: CanvasScene) -> ProjectManager:
    """Exercise every plan store; a new ProjectData field requires a deliberate fixture."""
    note = JournalNote(id="journal", date="2026-11-16", text="Recovered note",
                       scene_x=100, scene_y=200)
    tour = SavedTour("Recovery", "hold", held=CameraKey((0, -900, 350), (400, 300, 0), 40))
    metadata = {
        "location": {"latitude": 52.52, "longitude": 13.405, "name": "Berlin"},
        "north_angle_deg": 37.0,
        "task_completions": ["task"],
        "seed_inventory": [{"id": "packet", "species_key": "tomato", "quantity": 5}],
        "propagation_overrides": {"tomato": {"sow": {"start": "2026-03-01"}}},
        "crop_rotation": {"bed": {"2025": ["Solanaceae"]}},
        "season_year": 2026,
        "linked_seasons": [{"year": 2025, "file": "previous.ogp"}],
        "soil_tests": {"global": {"records": [{"date": "2026-11-16", "ph": 6.5}]}},
        "pest_disease_logs": {"bed": {"entries": [{"date": "2026-11-16", "notes": "Slugs"}]}},
        "shopping_list_prices": {"tomato": 3.5},
        "excluded_shopping_items": ["tomato"],
        "enabled_amendments": ["compost"],
        "prefer_organic": False,
        "succession_plans": {"bed": {"slots": [{"species_key": "tomato"}]}},
        "auto_assign_permaculture_layers": True,
        "garden_journal_notes": {note.id: note.to_dict()},
        "manual_tasks": {"task": {"id": "task", "title": "Water", "due_date": "2026-11-16"}},
        "task_states": {"task": {"status": "done", "done_date": "2026-11-16"}},
        "harvest_logs": {"bed": {"entries": [{"date": "2026-11-16", "quantity_kg": 2.5}]}},
        "camera_tours": [tour.to_dict()],
    }
    scene_fields = {"canvas_width", "canvas_height", "objects", "layers", "constraints", "guides"}
    assert {field.name for field in fields(ProjectData)} == scene_fields | metadata.keys()
    project = ProjectManager()
    project._restore_project_metadata(ProjectData(**metadata))
    scene.addItem(RectangleItem(100, 200, 300, 400, layer_id=scene.active_layer.id))
    pin = JournalPinItem(100, 200, note.id, layer_id=scene.active_layer.id)
    scene.addItem(pin)
    pin.setPos(QPointF(321, 432))  # The dragged pin, rather than the old note, is authoritative.
    return project


@pytest.mark.parametrize("saved", [False, True])
def test_recovery_preserves_every_store_and_save_identity(qtbot, tmp_path: Path, monkeypatch, saved):
    scene = CanvasScene(1700, 1300)
    project = populated_project(scene)
    original = tmp_path / "original.ogp"
    if saved:
        project.save(scene, original)
    project.mark_dirty()
    manager = AutoSaveManager(project)
    manager.set_scene(scene)
    manager.set_project_path(original if saved else None)
    recovery = tmp_path / "recovery.ogp"
    monkeypatch.setattr(manager, "_get_autosave_path", lambda: recovery)
    signals = []
    project.project_changed.connect(signals.append)
    flushes = []
    project.before_save.connect(lambda: flushes.append(True))

    assert manager.perform_autosave()
    assert project.is_dirty and project.current_file == (original if saved else None)
    assert signals == [], "an autosave must not retarget the user's document"
    assert project.garden_journal_notes["journal"]["scene_x"] == (321 if saved else 100)
    recovered = ProjectManager()
    recovered_scene = CanvasScene()
    recovered.load(recovered_scene, recovery)
    actual = recovered._build_project_data(recovered_scene)
    expected = project._build_project_data(scene)
    assert actual == expected
    assert flushes == [True], "pending form edits must be flushed just as for Save"
    assert actual.garden_journal_notes["journal"]["scene_x"] == 321
    assert actual.camera_tours

    manual = tmp_path / "manual.ogp"
    project.save(scene, manual)
    autosaved = read_plan(recovery)
    assert autosaved.pop("autosave_metadata")["original_file"] == (str(original) if saved else None)
    saved_data = read_plan(manual)
    autosaved.pop("metadata")
    saved_data.pop("metadata")
    assert autosaved == saved_data, "new persisted keys must not bypass recovery"


def test_application_autosaves_and_recovers_pending_edits(qtbot, monkeypatch, tmp_path):
    """Exercise the window's real autosave binding and its crash-recovery loader."""
    from PyQt6.QtWidgets import QMessageBox

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import get_settings
    from tests.integration.test_properties_text_edit_undo import _name_edit

    get_settings().show_welcome_on_startup = False
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    project = window._project_manager
    project.set_location({"name": "Berlin", "latitude": 52.52, "longitude": 13.405})
    note = JournalNote(text="Recovered journal", date="2026-11-16", scene_x=100, scene_y=200)
    project.set_journal_note(note)
    project.set_camera_tours((SavedTour("Held view", "hold", held=CameraKey(
        (0, -900, 350), (400, 300, 0), 40)),))
    item = RectangleItem(100, 200, 300, 400, layer_id=window.canvas_scene.active_layer.id)
    window.canvas_scene.addItem(item)
    window.canvas_scene.clearSelection()
    item.setSelected(True)
    # The real Properties panel debounces names; recovery must flush the edit.
    _name_edit(window.properties_panel).setText("Pending name")
    recovery = tmp_path / "recover.ogp"
    monkeypatch.setattr(window._autosave_manager, "_get_autosave_path", lambda: recovery)
    assert window._autosave_manager.perform_autosave()
    assert any(obj.get("name") == "Pending name" for obj in read_plan(recovery)["objects"])
    project.new_project()
    window.canvas_scene.clear()
    notices = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: notices.append(args[1]))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: pytest.fail(str(args)))
    window._load_recovery_file(recovery)
    assert notices
    assert project.location["name"] == "Berlin"
    assert project.garden_journal_notes[note.id]["text"] == note.text
    assert project.camera_tours[0].name == "Held view"
    assert project.is_dirty and project.current_file is None
    assert not window.canvas_view.command_manager.can_undo


def test_failed_autosave_keeps_existing_recovery_and_dirty_document(qtbot, monkeypatch, tmp_path):
    scene = CanvasScene()
    project = populated_project(scene)
    project.mark_dirty()
    recovery = tmp_path / "recovery.ogp"
    recovery.write_bytes(b"previous recovery")
    manager = AutoSaveManager(project)
    manager.set_scene(scene)
    monkeypatch.setattr(manager, "_get_autosave_path", lambda: recovery)

    def refuse(*args):
        raise OSError("Disk full")

    monkeypatch.setattr("open_garden_planner.core.plan_io.write_plan", refuse)
    with qtbot.waitSignal(manager.autosave_failed, timeout=1000):
        assert not manager.perform_autosave()
    assert recovery.read_bytes() == b"previous recovery"
    assert project.is_dirty and project.current_file is None
