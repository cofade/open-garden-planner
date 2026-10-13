"""Real application document-preservation workflows for A1."""

import json

import pytest

from open_garden_planner.agent_api.history import history_from_command_manager
from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.commands import CreateItemCommand
from open_garden_planner.ui.canvas.items import RectangleItem


@pytest.mark.parametrize("bad", [
    {"canvas": {"width": float("nan"), "height": 1000}},
    {"objects": [{"type": "rectangle", "x": 1e308, "y": 0, "width": 1e308, "height": 100}]},
    {"objects": [{"type": "group", "children": [{"type": "circle", "radius": "NaN"}]}]},
], ids=["canvas", "extent-overflow", "group"])
def test_rejected_open_preserves_active_document_and_history(qtbot, tmp_path, monkeypatch, bad):
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda *_: None)
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    scene, manager, pm = app.canvas_scene, app.canvas_view.command_manager, app._project_manager
    path = tmp_path / "good.ogp"
    pm.save(scene, path)
    item = RectangleItem(100, 100, 200, 100)
    manager.execute(CreateItemCommand(scene, item))
    item.setSelected(True)
    app._autosave_manager._current_project_path = path
    assert app._autosave_manager.perform_autosave()
    autosave = app._autosave_manager._get_autosave_path()
    original, recovery = path.read_bytes(), autosave.read_bytes()
    history = history_from_command_manager(manager)
    title, recent = app.windowTitle(), get_settings().recent_files
    invalid = tmp_path / "invalid.ogp"
    invalid.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        app._load_project_file(str(invalid))
    assert item in scene.items() and item.isSelected()
    assert history_from_command_manager(manager) == history
    assert pm.current_file == path and pm.is_dirty
    assert app.windowTitle() == title
    assert get_settings().recent_files == recent
    assert path.read_bytes() == original and autosave.read_bytes() == recovery
    pm.mark_clean()
    app.close()


def test_failed_autosave_keeps_recovery_file(qtbot, tmp_path):
    from open_garden_planner.services.autosave_service import AutoSaveManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    scene = CanvasScene()
    item = RectangleItem(0, 0, 100, 100)
    scene.addItem(item)
    autosave = AutoSaveManager()
    autosave._scene = scene
    path = tmp_path / "recovery.ogp"
    autosave._save_to_file(path)
    original = path.read_bytes()
    item.metadata["poison"] = float("inf")
    with pytest.raises(ValueError):
        autosave._save_to_file(path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("angle", [0, 45, 215])
def test_valid_rotated_plan_roundtrips_with_strict_io(qtbot, tmp_path, angle):
    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    scene = CanvasScene()
    item = RectangleItem(200, 200, 200, 100)
    item._apply_rotation(angle)
    scene.addItem(item)
    centre = item.mapToScene(item.rect().center())
    pm = ProjectManager()
    path = tmp_path / "rotation.ogp"
    pm.save(scene, path)
    pm.load(scene, path)
    loaded = next(it for it in scene.items() if getattr(it, "item_id", None) == item.item_id)
    assert loaded.rotation_angle == angle
    assert loaded.mapToScene(loaded.rect().center()) == centre
    if angle:
        assert loaded.transformOriginPoint() == loaded.rect().center()
