"""A showcase weather survives save/reopen (#944)."""

from __future__ import annotations

import json
from pathlib import Path

from open_garden_planner.core.project import ProjectManager


def test_a_plan_snow_weather_is_saved_and_opens_again(canvas, tmp_path: Path) -> None:
    path = tmp_path / "winter-garden.ogp"
    manager = ProjectManager()
    manager.set_plan_weather("snow")
    assert manager.is_dirty
    manager.save(canvas.scene(), path)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["weather"] == "snow" and stored["version"] == "1.4"

    reopened = ProjectManager()
    reopened.load(canvas.scene(), path)
    assert reopened.plan_weather == "snow"
    assert not reopened.is_dirty

    reopened.set_plan_weather("clear")
    assert reopened.is_dirty and reopened.plan_weather == "clear"
    assert "weather" not in reopened._build_project_data(canvas.scene()).to_dict()


def test_the_window_stores_a_concrete_weather_and_opens_in_it(
        qtbot, monkeypatch, tmp_path: Path) -> None:
    """#944 through the real window: the toolbar's choice is the plan's, a save keeps it,
    reopening applies it, and Today's forecast is never stored."""
    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import get_settings

    get_settings().show_welcome_on_startup = False
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    living = window._workspace.living
    manager = window._project_manager
    assert living.weather_choice == "clear" and manager.plan_weather == "clear"

    living.set_weather("snow")
    assert manager.plan_weather == "snow" and manager.is_dirty

    path = tmp_path / "winter-garden.ogp"
    manager.save(window.canvas_scene, path)
    living.set_weather("clear")
    assert manager.plan_weather == "clear" and manager.is_dirty

    window._open_project_file(str(path))
    assert living.weather_choice == "snow", "the plan's own sky, not the old session's"
    assert manager.plan_weather == "snow" and not manager.is_dirty

    living.set_weather("today")
    assert manager.plan_weather == "snow", "a forecast choice is not a plan fact"
