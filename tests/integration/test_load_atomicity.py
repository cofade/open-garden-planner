"""Integration tests for load atomicity and document identity protection (Issue #403, AUD-040, TD-017).

Tests:
1. Opening a corrupt .ogp leaves previous scene items completely intact (two-phase load).
2. Opening a corrupt .ogp resets current_file to None and marks project dirty so Ctrl+S cannot overwrite the good plan.
3. In GardenPlannerApp, a failed load leaves any existing autosave file intact on disk.
4. Structurally invalid / non-dict / corrupt JSON fails cleanly without clearing the scene.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem


def test_failed_load_leaves_scene_items_and_file_intact(
    tmp_path: Path, qtbot: Any
) -> None:
    """Scene items and original plan file must remain 100% intact when a corrupt plan fails to load."""
    scene = CanvasScene()
    pm = ProjectManager()

    # Create and save a valid Plan A with 2 items
    item1 = RectangleItem(0.0, 0.0, 100.0, 50.0)
    item1.name = "PlanA_Rect"
    item2 = CircleItem(200.0, 200.0, 40.0)
    item2.name = "PlanA_Circle"
    scene.addItem(item1)
    scene.addItem(item2)

    plan_a_path = tmp_path / "plan_a.ogp"
    pm.save(scene, plan_a_path)
    plan_a_bytes_before = plan_a_path.read_bytes()

    # Load Plan A into pm so current_file is plan_a_path
    pm.load(scene, plan_a_path)
    assert pm.current_file == plan_a_path
    assert not pm.is_dirty

    # Create a corrupt file B that fails during deserialization (e.g. malformed layers structure)
    corrupt_b_path = tmp_path / "corrupt_b.ogp"
    corrupt_b_data = {
        "version": "1.4",
        "canvas_width": 2000.0,
        "canvas_height": 1500.0,
        "layers": "invalid_layers_not_a_list",
        "objects": [
            {
                "type": "rectangle",
                "item_id": str(uuid.uuid4()),
                "name": "From_B",
                "x": 10.0,
                "y": 10.0,
                "width": 100.0,
                "height": 50.0,
            }
        ],
    }
    with open(corrupt_b_path, "w", encoding="utf-8") as f:
        json.dump(corrupt_b_data, f)

    # Attempt to load corrupt B: must raise an exception
    with pytest.raises(TypeError):
        pm.load(scene, corrupt_b_path)

    # Verify atomicity guarantees (AUD-040, TD-017, FIND-01):
    # 1. Because Phase 1 failed before mutating the scene, Plan A remains open and clean
    assert pm.current_file == plan_a_path
    assert not pm.is_dirty

    # 2. Plan A on disk is byte-identical
    assert plan_a_path.read_bytes() == plan_a_bytes_before

    # 3. Scene items remain untouched (still the 2 Plan A items)
    doc_items = [it for it in scene.items() if hasattr(it, "item_id")]
    assert len(doc_items) == 2
    item_names = {getattr(it, "name", "") for it in doc_items}
    assert item_names == {"PlanA_Rect", "PlanA_Circle"}


def test_corrupt_json_fails_cleanly_without_clearing_scene(
    tmp_path: Path, qtbot: Any
) -> None:
    """Non-JSON or truncated files must fail without touching scene items or dirty flag."""
    scene = CanvasScene()
    pm = ProjectManager()

    item = RectangleItem(10.0, 10.0, 50.0, 50.0)
    item.name = "Original_Item"
    scene.addItem(item)

    corrupt_json_path = tmp_path / "corrupt_syntax.ogp"
    corrupt_json_path.write_text("{ incomplete json: [", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        pm.load(scene, corrupt_json_path)

    # File was never loaded, so current_file is still None and dirty flag untouched
    assert pm.current_file is None
    assert not pm.is_dirty

    doc_items = [it for it in scene.items() if hasattr(it, "item_id")]
    assert len(doc_items) == 1
    assert getattr(doc_items[0], "name", "") == "Original_Item"


def test_phase2_failure_resets_document_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot: Any
) -> None:
    """If Phase 2 fails after scene mutation has begun, document identity must be cleared (FIND-01)."""
    scene = CanvasScene()
    pm = ProjectManager()

    item1 = RectangleItem(0.0, 0.0, 100.0, 50.0)
    scene.addItem(item1)
    plan_a_path = tmp_path / "plan_a.ogp"
    pm.save(scene, plan_a_path)
    pm.load(scene, plan_a_path)
    assert pm.current_file == plan_a_path

    # Simulate an unexpected failure in Phase 2 during scene.addItem
    def buggy_add_item(it: Any) -> None:
        raise RuntimeError("Simulated crash in Phase 2")
    monkeypatch.setattr(scene, "addItem", buggy_add_item)

    with pytest.raises(RuntimeError):
        pm.load(scene, plan_a_path)

    # Since scene mutation started, identity must be cleared and marked dirty
    assert pm.current_file is None
    assert pm.is_dirty


def test_app_load_failure_preserves_autosave_and_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot: Any
) -> None:
    """In GardenPlannerApp, failed Phase 1 load must preserve existing autosave and sync identity."""
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda *_args: None)
    app = GardenPlannerApp()
    qtbot.addWidget(app)

    # Create a valid plan A
    plan_a_path = tmp_path / "plan_a.ogp"
    app.canvas_scene.addItem(RectangleItem(0.0, 0.0, 100.0, 50.0))
    app._project_manager.save(app.canvas_scene, plan_a_path)
    app._load_project_file(str(plan_a_path))
    assert app._project_manager.current_file == plan_a_path

    # Simulate an autosave on disk for Plan A
    app._autosave_manager.set_dirty(True)
    assert app._autosave_manager.perform_autosave()
    autosave_path = app._autosave_manager._get_autosave_path()
    assert autosave_path.exists()
    autosave_content_before = autosave_path.read_bytes()

    # Create corrupt file B
    corrupt_b_path = tmp_path / "corrupt_b.ogp"
    corrupt_b_path.write_text(json.dumps({"version": "1.4", "layers": "bad"}), encoding="utf-8")

    # Attempt to load corrupt file B
    with pytest.raises(TypeError):
        app._load_project_file(str(corrupt_b_path))

    # Verify autosave is preserved on disk
    assert autosave_path.exists()
    assert autosave_path.read_bytes() == autosave_content_before

    # Verify project manager current_file is still Plan A (scene was untouched)
    assert app._project_manager.current_file == plan_a_path

    # Verify window title does NOT claim to be file B
    assert str(corrupt_b_path) not in app.windowTitle()

    # Mark clean so closeEvent does not block on modal QMessageBox
    app._project_manager.mark_clean()
    app.close()


def test_app_surfaces_skipped_items_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot: Any
) -> None:
    """When a plan with undecodable items is loaded, a warning is surfaced in status bar (FIND-04)."""
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda *_args: None)
    app = GardenPlannerApp()
    qtbot.addWidget(app)

    plan_data = {
        "version": "1.4",
        "objects": [
            {
                "type": "rectangle",
                "x": 0.0,
                "y": 0.0,
                "width": 100.0,
                "height": 50.0,
            },
            {
                "type": "unknown_future_item",
                "foo": "bar",
            },
        ],
    }
    plan_path = tmp_path / "skipped_items.ogp"
    plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

    app._load_project_file(str(plan_path))
    assert app._project_manager.last_load_skipped_items_count == 1
    assert "Warning: 1 unrecognized item(s)" in app.statusBar().currentMessage()

    app.close()
