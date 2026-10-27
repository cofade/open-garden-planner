"""Owner acceptance: shipped learning plans retain their public demonstration state."""

from copy import deepcopy

import pytest

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


@pytest.mark.parametrize("source", ["raised-bed.ogp", "de/raised-bed.ogp", "es/raised-bed.ogp"])
def test_known_bundled_copy_keeps_demo_sun_and_soil_but_still_drops_private_history(qtbot, monkeypatch, source):
    raw = {"version": "1.4", "canvas": {"width": 700, "height": 500}, "objects": [],
           "location": {"latitude": 52.52, "longitude": 13.405, "timezone": "Europe/Berlin"},
           "soil_tests": {"global": {"target_id": "global", "records": [
               {"id": "demo", "date": "2026-04-01", "ph": 6.5, "n_level": 1,
                "p_level": 2, "k_level": 2, "notes": "Demonstration only"}]}},
           "harvest_logs": {"private": {}}, "task_states": {"private": {}},
           "garden_journal_notes": {"private": {}}, "unknown_private": "secret"}
    original = deepcopy(raw)
    monkeypatch.setattr("open_garden_planner.core.project.read_plan", lambda _path: raw)
    manager = ProjectManager()
    scene = CanvasScene()
    manager.load(scene, BUNDLED_EXAMPLES / source, as_template=True)
    assert manager.location == raw["location"]
    snapshot = manager.snapshot_dict(scene)
    assert snapshot["soil_tests"] == raw["soil_tests"]
    assert not {"harvest_logs", "task_states", "garden_journal_notes", "unknown_private"} & snapshot.keys()
    assert manager.current_file is None and manager.is_dirty
    assert raw == original


def test_an_external_copy_of_an_example_is_still_a_private_user_template(qtbot, monkeypatch, tmp_path):
    raw = {"version": "1.4", "canvas": {"width": 700, "height": 500}, "objects": [],
           "location": {"latitude": 52.52, "longitude": 13.405},
           "soil_tests": {"global": {"target_id": "global", "records": []}}}
    monkeypatch.setattr("open_garden_planner.core.project.read_plan", lambda _path: raw)
    manager = ProjectManager()
    scene = CanvasScene()
    manager.load(scene, tmp_path / "raised-bed.ogp", as_template=True)
    assert manager.location is None
    assert "soil_tests" not in manager.snapshot_dict(scene)
