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


@pytest.fixture
def recovery_window(qtbot, monkeypatch, tmp_path):
    from PyQt6.QtWidgets import QMessageBox

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import get_settings

    # Drive startup explicitly, without its delayed callback racing the test.
    startup = GardenPlannerApp._startup_sequence
    monkeypatch.setattr(GardenPlannerApp, "_startup_sequence", lambda _self: None)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    get_settings().show_welcome_on_startup = False
    get_settings().recent_files = []
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: pytest.fail(str(args)))
    yield window, lambda: startup(window)
    window._project_manager.mark_clean()


def crashed_saved_plan(tmp_path):
    """A prior process saved the original, edited it, autosaved, then died."""
    import os

    scene = CanvasScene()
    item = RectangleItem(100, 200, 300, 400, name="Original name")
    scene.addItem(item)
    project = ProjectManager()
    path = tmp_path / "saved.ogp"
    project.save(scene, path)
    original = path.read_bytes()
    item.name = "Recovered name"
    project.set_journal_note(JournalNote(id="recovered-note", text="Recovered note"))
    manager = AutoSaveManager(project)
    manager.set_scene(scene)
    manager.set_project_path(path)
    assert manager.perform_autosave()
    backup = manager._get_autosave_path()
    # Explicit ordering, independent of filesystem timestamp resolution.
    stamp = 1_700_000_000_000_000_000
    os.utime(path, ns=(stamp, stamp))
    os.utime(backup, ns=(stamp + 1_000_000_000, stamp + 1_000_000_000))
    return path, backup, original


def test_startup_finds_saved_plan_recovers_and_save_as_consumes_backup(
    recovery_window, monkeypatch, tmp_path,
):
    from PyQt6.QtWidgets import QMessageBox

    window, startup = recovery_window
    original, backup, original_bytes = crashed_saved_plan(tmp_path)
    prompts = []

    def accept(*args):
        prompts.append(args[2])
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", accept)
    startup()
    assert len(prompts) == 1, "startup must discover the saved plan's adjacent autosave"
    assert "Recovered name" in {getattr(i, "name", "") for i in window.canvas_scene.items()}
    assert window._project_manager.garden_journal_notes["recovered-note"]["text"] == "Recovered note"
    assert window._project_manager.current_file is None and window._project_manager.is_dirty
    assert backup.exists(), "accepting recovery must not delete the only durable recovered copy"
    assert original.read_bytes() == original_bytes
    restored = tmp_path / "restored.ogp"
    window._save_to_file(restored)
    assert any(i.get("name") == "Recovered name" for i in read_plan(restored)["objects"])
    assert not backup.exists(), "successful Save As consumes the adopted recovery copy"
    assert original.read_bytes() == original_bytes


@pytest.mark.parametrize("choice", ["Yes", "No", "Discard"])
def test_open_original_offers_adjacent_recovery_even_outside_recent_files(
    recovery_window, monkeypatch, tmp_path, choice,
):
    from PyQt6.QtWidgets import QMessageBox

    from open_garden_planner.app.settings import get_settings

    window, _startup = recovery_window
    original, backup, original_bytes = crashed_saved_plan(tmp_path)
    get_settings().recent_files = []
    backup_bytes = backup.read_bytes()
    prompts = []

    def answer(*args):
        prompts.append(args[2])
        return getattr(QMessageBox.StandardButton, choice)

    monkeypatch.setattr(QMessageBox, "question", answer)
    window._open_project_file(str(original))
    assert len(prompts) == 1
    names = {getattr(i, "name", "") for i in window.canvas_scene.items()}
    assert ("Recovered name" if choice == "Yes" else "Original name") in names
    assert window._project_manager.is_dirty == (choice == "Yes")
    assert window._project_manager.current_file == (None if choice == "Yes" else original)
    if choice == "Discard":
        assert not backup.exists()
    else:
        assert backup.read_bytes() == backup_bytes, "No defers recovery; only Discard deletes it"
    assert original.read_bytes() == original_bytes


def test_programmatic_load_does_not_delete_unowned_destination_autosave(
    recovery_window, tmp_path,
):
    window, _startup = recovery_window
    original, backup, _original_bytes = crashed_saved_plan(tmp_path)
    backup_bytes = backup.read_bytes()
    window._load_project_file(str(original))
    assert backup.read_bytes() == backup_bytes, "loading an original must not destroy its recovery"


def test_save_as_removes_own_untitled_snapshot_and_preserves_foreign_backup(
    recovery_window, tmp_path,
):
    window, _startup = recovery_window
    destination, foreign_backup, _original_bytes = crashed_saved_plan(tmp_path)
    foreign_bytes = foreign_backup.read_bytes()
    window.canvas_scene.addItem(RectangleItem(10, 20, 30, 40, name="Untitled work"))
    window._project_manager.mark_dirty()
    assert window._autosave_manager.perform_autosave()
    untitled = window._autosave_manager._get_autosave_path()
    assert untitled.exists() and untitled != foreign_backup
    window._save_to_file(destination)
    assert not untitled.exists()
    assert foreign_backup.read_bytes() == foreign_bytes


def test_command_line_recovery_does_not_nest_or_repeat_startup_prompts(
    recovery_window, monkeypatch, tmp_path,
):
    from PyQt6.QtWidgets import QMessageBox

    window, startup = recovery_window
    original, _backup, _original_bytes = crashed_saved_plan(tmp_path)
    prompts = []

    def accept(*args):
        prompts.append(args[2])
        startup()  # The delayed callback fires inside a modal question's event loop.
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", accept)
    window._open_project_file(str(original))
    startup()  # It may also be delivered after recovery has already completed.
    assert len(prompts) == 1
    assert window._project_manager.is_dirty and window._project_manager.current_file is None
    assert "Recovered name" in {getattr(i, "name", "") for i in window.canvas_scene.items()}


def test_startup_recovers_only_one_document_and_keeps_other_candidates(
    recovery_window, monkeypatch, tmp_path,
):
    from PyQt6.QtWidgets import QMessageBox

    window, startup = recovery_window
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _first_plan, first_backup, _ = crashed_saved_plan(first)
    _second_plan, second_backup, _ = crashed_saved_plan(second)
    prompts = []

    def accept(*args):
        prompts.append(args[2])
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", accept)
    startup()
    assert len(prompts) == 1, "a second recovery must not overwrite the first recovered document"
    assert first_backup.exists() and second_backup.exists()


def test_declined_own_backup_survives_reloading_original(
    recovery_window, monkeypatch, tmp_path,
):
    from PyQt6.QtWidgets import QMessageBox

    window, _startup = recovery_window
    path = tmp_path / "active.ogp"
    window._save_to_file(path)
    window.canvas_scene.addItem(RectangleItem(10, 20, 30, 40, name="Unsaved work"))
    window._project_manager.mark_dirty()
    assert window._autosave_manager.perform_autosave()
    backup = window._autosave_manager._get_autosave_path()
    previous = backup.read_bytes()
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.No)
    window._open_project_file(str(path))
    assert backup.read_bytes() == previous


def test_recovery_load_failure_does_not_fall_back_to_old_original(
    recovery_window, monkeypatch, tmp_path,
):
    from PyQt6.QtWidgets import QMessageBox

    window, _startup = recovery_window
    original, backup, _ = crashed_saved_plan(tmp_path)
    previous = backup.read_bytes()
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[2]))

    def fail(*args, **kwargs):
        raise OSError("Recovery read failed")

    monkeypatch.setattr(window._project_manager, "load", fail)
    monkeypatch.setattr(window, "_load_project_file", lambda *_: pytest.fail("original opened"))
    window._open_project_file(str(original))
    assert errors and backup.read_bytes() == previous
    window._open_project_file(str(original))
    assert len(errors) == 2 and backup.read_bytes() == previous


def test_declined_recovery_survives_new_autosave_and_document_discard(
    recovery_window, monkeypatch, tmp_path,
):
    from PyQt6.QtWidgets import QMessageBox

    window, _startup = recovery_window
    original, backup, original_bytes = crashed_saved_plan(tmp_path)
    deferred_bytes = backup.read_bytes()
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.No)
    window._open_project_file(str(original))
    window.canvas_scene.addItem(RectangleItem(10, 20, 30, 40, name="Later work"))
    window._project_manager.mark_dirty()
    assert window._autosave_manager.perform_autosave()
    latest = window._autosave_manager._get_autosave_path()
    assert backup.read_bytes() == deferred_bytes
    assert latest != backup and latest.exists()
    assert any(i.get("name") == "Later work" for i in read_plan(latest)["objects"])
    assert AutoSaveManager.find_recovery_for_project(original)[0] == latest
    # Another timer tick reuses this document's path rather than leaking versions.
    assert window._autosave_manager.perform_autosave()
    assert window._autosave_manager._get_autosave_path() == latest
    # Closing after accepted discard cleans only this document; a restarted service can
    # still discover the earlier deferred recovery with its original name/note.
    window.close()
    assert not latest.exists() and backup.read_bytes() == deferred_bytes
    assert AutoSaveManager.find_recovery_for_project(original)[0] == backup
    assert original.read_bytes() == original_bytes
