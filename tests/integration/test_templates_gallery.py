"""F5: real Welcome -> loader -> edit -> Save As; export, refusal and transport."""

import asyncio
import json
import threading
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.example_library import bundled_examples
from open_garden_planner.ui.dialogs.welcome_dialog import WelcomeDialog
from tests.agent_api_helpers import start_server


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr("open_garden_planner.services.example_library.user_templates_dir", lambda: tmp_path)
    win = GardenPlannerApp()
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    qtbot.addWidget(win)
    return win


@pytest.mark.parametrize("entry", bundled_examples(), ids=lambda e: e.path.stem)
def test_welcome_opens_untitled_copy_and_save_as_leaves_bundle_unchanged(window, entry, qtbot, tmp_path):
    source, mtime = entry.path.read_bytes(), entry.path.stat().st_mtime_ns
    recent = get_settings().recent_files
    dialog = WelcomeDialog(window)
    qtbot.addWidget(dialog)
    dialog.template_selected.connect(window._open_template_file)
    gallery = dialog._gallery
    index = next(i for i in range(gallery.list.count())
                 if gallery.list.item(i).data(Qt.ItemDataRole.UserRole) == str(entry.path))
    gallery.list.setCurrentRow(index)
    qtbot.mouseClick(gallery.open_button, Qt.MouseButton.LeftButton)
    manager = window._project_manager
    assert manager.current_file is None and manager.is_dirty
    assert window.canvas_view.command_manager._undo_stack == []
    assert get_settings().recent_files == recent
    assert manager.location is None
    assert manager.snapshot_dict(window.canvas_scene)["objects"]
    original_count = len(manager.snapshot_dict(window.canvas_scene)["objects"])
    plant = next(item for item in window.canvas_scene.items()
                 if getattr(item, "plant_species", ""))
    window.canvas_scene.clearSelection()
    plant.setSelected(True)
    window.canvas_view.duplicate_selected()
    assert len(window.canvas_view.command_manager._undo_stack) == 1
    assert len(manager.snapshot_dict(window.canvas_scene)["objects"]) == original_count + 1
    window.canvas_view.command_manager.undo()
    assert len(manager.snapshot_dict(window.canvas_scene)["objects"]) == original_count
    window.canvas_view.command_manager.redo()
    target = tmp_path / "my-design.ogp"
    window._save_to_file(target)
    assert manager.current_file == target and not manager.is_dirty
    assert entry.path.read_bytes() == source and entry.path.stat().st_mtime_ns == mtime
    assert target.exists()


def test_file_template_export_and_reimport_through_menu_slots(window, monkeypatch, tmp_path):
    window._load_project_file(str(bundled_examples()[0].path))
    manager = window._project_manager
    manager.set_location({"latitude": 51, "longitude": 13})
    original_file, original_dirty = manager.current_file, manager.is_dirty
    exported = tmp_path / "portable.ogp"
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: (str(exported), ""))
    window._on_save_template()
    assert manager.current_file == original_file and manager.is_dirty == original_dirty
    assert "location" not in json.loads(exported.read_text(encoding="utf-8"))
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: (str(exported), ""))
    window._on_new_from_template()
    assert manager.current_file is None and manager.is_dirty
    assert manager.location is None


def test_cancel_and_invalid_template_preserve_document_history_and_autosave(window, monkeypatch, tmp_path):
    manager = window._project_manager
    window._load_project_file(str(bundled_examples()[0].path), as_template=True)
    before = manager.snapshot_dict(window.canvas_scene)
    autosave = window._autosave_manager
    calls = []
    monkeypatch.setattr(autosave, "clear_autosave", lambda: calls.append(True))
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: False)
    window._open_template_file(str(bundled_examples()[1].path))
    unchanged = manager.snapshot_dict(window.canvas_scene)
    before.pop("metadata", None)
    unchanged.pop("metadata", None)
    assert unchanged == before
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    bad = tmp_path / "bad.ogp"
    bad.write_text('{"canvas": {"width": -5}}', encoding="utf-8")
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args))
    window._open_template_file(str(bad))
    after = manager.snapshot_dict(window.canvas_scene)
    before.pop("metadata", None)
    after.pop("metadata", None)
    assert after == before
    assert errors and not calls


def test_export_refuses_to_overwrite_live_project_or_bundle(window, tmp_path):
    manager = window._project_manager
    own = tmp_path / "own.ogp"
    manager.save(window.canvas_scene, own)
    before = own.read_bytes()
    with pytest.raises(ValueError, match="filename"):
        manager.save_template(window.canvas_scene, own)
    with pytest.raises(ValueError, match="filename"):
        manager.save_template(window.canvas_scene, bundled_examples()[0].path)
    assert own.read_bytes() == before and manager.current_file == own and not manager.is_dirty


def test_template_load_strips_personal_data_even_from_an_ordinary_plan(window, tmp_path):
    path = tmp_path / "ordinary.ogp"
    path.write_text(json.dumps({"version": "1.4", "canvas": {"width": 500, "height": 300},
                                "location": {"latitude": 51}, "garden_journal_notes": {"secret": {}},
                                "harvest_logs": {"secret": {}}, "objects": []}), encoding="utf-8")
    window._load_project_file(str(path), as_template=True)
    assert window._project_manager.current_file is None
    snapshot = window._project_manager.snapshot_dict(window.canvas_scene)
    assert not {"location", "garden_journal_notes", "harvest_logs"} & snapshot.keys()


def test_examples_resource_over_real_transport_is_read_only(window, qtbot):
    server, _ = start_server(window._build_agent_providers())
    result = {}

    async def read():
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(server.url) as (r, w, _), ClientSession(r, w) as client:
            await client.initialize()
            response = await client.read_resource("garden://examples")
            result["entries"] = json.loads(response.contents[0].text)

    def drive():
        try:
            asyncio.run(read())
        except Exception as exc:
            result["error"] = exc
        finally:
            result["done"] = True

    before = window._project_manager.snapshot_dict(window.canvas_scene)
    thread = threading.Thread(target=drive)
    try:
        thread.start()
        qtbot.waitUntil(lambda: result.get("done", False), timeout=20000)
        assert "error" not in result, result.get("error")
        assert len(result["entries"]) == 3
        assert all(Path(e["path"]).is_file() for e in result["entries"])
        after = window._project_manager.snapshot_dict(window.canvas_scene)
        before.pop("metadata", None)
        after.pop("metadata", None)
        assert after == before
    finally:
        server.stop()
        thread.join(timeout=5)


def test_dogfood_sample_is_a_copy_of_the_maintained_example(tmp_path, qtbot):
    from scripts.dogfood_agent_api import emit_sample

    from open_garden_planner.services.example_library import BUNDLED_EXAMPLES

    result = asyncio.run(emit_sample(0, "unused", tmp_path))
    assert Path(result["ogp"]).read_bytes() == (BUNDLED_EXAMPLES / "raised-bed.ogp").read_bytes()
    assert Path(result["png"]).read_bytes() == (BUNDLED_EXAMPLES / "raised-bed.png").read_bytes()
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    scene = CanvasScene()
    manager = ProjectManager()
    manager.load(scene, Path(result["ogp"]))
    assert manager.succession_plans
