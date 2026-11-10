"""Owner acceptance: shipped learning plans retain their public demonstration state."""

from copy import deepcopy

import pytest

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


@pytest.mark.parametrize("source", ["raised-bed.ogp", "de/raised-bed.ogp", "es/raised-bed.ogp"])
def test_known_bundled_copy_keeps_its_demo_state_but_still_drops_private_history(qtbot, monkeypatch, source):
    """Kept: the public place, the fictional soil sample and (#795) the fictional harvest
    history. Every other history and preference of a plan stays out of an example copy."""
    raw = {"version": "1.4", "canvas": {"width": 700, "height": 500}, "objects": [],
           "location": {"latitude": 52.52, "longitude": 13.405, "timezone": "Europe/Berlin"},
           "soil_tests": {"global": {"target_id": "global", "records": [
               {"id": "demo", "date": "2026-04-01", "ph": 6.5, "n_level": 1,
                "p_level": 2, "k_level": 2, "notes": "Demonstration only"}]}},
           "harvest_logs": {"demo-plant": {"target_id": "demo-plant", "species_key": "daucus carota",
                                           "species_name": "Carrot", "records": [
               {"id": "demo-harvest", "date": "2026-09-10", "quantity": 1.1, "unit": "kg",
                "notes": "Fictional example entry"}]}},
           "task_states": {"private": {}}, "pest_disease_logs": {"private": {}},
           "seed_inventory": [{"id": "private"}], "manual_tasks": {"private": {}},
           "garden_journal_notes": {"private": {}}, "unknown_private": "secret"}
    original = deepcopy(raw)
    monkeypatch.setattr("open_garden_planner.core.project.read_plan", lambda _path: raw)
    manager = ProjectManager()
    scene = CanvasScene()
    manager.load(scene, BUNDLED_EXAMPLES / source, as_template=True)
    assert manager.location == raw["location"]
    snapshot = manager.snapshot_dict(scene)
    assert snapshot["soil_tests"] == raw["soil_tests"]
    assert snapshot["harvest_logs"] == raw["harvest_logs"]
    assert not {"task_states", "pest_disease_logs", "seed_inventory", "manual_tasks",
                "garden_journal_notes", "unknown_private"} & snapshot.keys()
    assert manager.current_file is None and manager.is_dirty
    assert raw == original


def test_an_external_copy_of_an_example_is_still_a_private_user_template(qtbot, monkeypatch, tmp_path):
    raw = {"version": "1.4", "canvas": {"width": 700, "height": 500}, "objects": [],
           "location": {"latitude": 52.52, "longitude": 13.405},
           "soil_tests": {"global": {"target_id": "global", "records": []}},
           "harvest_logs": {"mine": {"target_id": "mine", "records": [
               {"id": "h", "date": "2026-09-10", "quantity": 1.0, "unit": "kg"}]}}}
    monkeypatch.setattr("open_garden_planner.core.project.read_plan", lambda _path: raw)
    manager = ProjectManager()
    scene = CanvasScene()
    manager.load(scene, tmp_path / "raised-bed.ogp", as_template=True)
    assert manager.location is None
    assert not {"soil_tests", "harvest_logs"} & manager.snapshot_dict(scene).keys()
