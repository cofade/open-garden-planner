"""#859: date-driven surfaces follow the plan's SimClock day, not the wall clock."""

from __future__ import annotations

import datetime

import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.sim_clock import SimClock, plan_day_of
from open_garden_planner.models.succession import SuccessionEntry, SuccessionPlan
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem
from open_garden_planner.ui.views import tasks_view as tasks_module
from open_garden_planner.ui.views.planting_calendar_view import PlantingCalendarView
from open_garden_planner.ui.views.tasks_view import TasksView


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "open_garden_planner.services.example_library.user_templates_dir", lambda: tmp_path
    )
    win = GardenPlannerApp()
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    qtbot.addWidget(win)
    return win


def _entry(name: str, start: str, end: str) -> SuccessionEntry:
    return SuccessionEntry(common_name=name, start_date=start, end_date=end)


class TestCalendarAndTasks:
    def test_the_calendar_dashboard_and_today_line_use_the_plan_day(self, qtbot) -> None:
        scene = CanvasScene(width_cm=1000, height_cm=800)
        clock = SimClock()
        clock.set_date(datetime.date(2031, 7, 1))
        scene.bind_plan_clock(clock)
        pm = ProjectManager()
        pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})
        plant = CircleItem(100, 100, 20, object_type=ObjectType.PERENNIAL, name="Tomato")
        plant.metadata["plant_species"] = {
            "common_name": "Tomato", "scientific_name": "Solanum lycopersicum",
            "source_id": "414", "harvest_start": 10, "harvest_end": 18,
        }
        scene.addItem(plant)

        view = PlantingCalendarView(scene, pm)
        qtbot.addWidget(view)
        view.refresh()
        assert view._plan_state is not None
        assert view._plan_state.today == datetime.date(2031, 7, 1)
        assert view._gantt._today == datetime.date(2031, 7, 1)

        clock.set_date(datetime.date(2032, 3, 20))
        view.refresh()
        assert view._plan_state.today == datetime.date(2032, 3, 20)
        assert view._gantt._today == datetime.date(2032, 3, 20)
        view.shutdown()

    def test_the_tasks_tab_asks_the_generator_for_the_plan_day(
        self, qtbot, monkeypatch
    ) -> None:
        scene = CanvasScene(width_cm=1000, height_cm=800)
        clock = SimClock()
        clock.set_date(datetime.date(2031, 7, 1))
        scene.bind_plan_clock(clock)
        pm = ProjectManager()
        pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})
        seen: list[dict] = []
        real = tasks_module.build_plan_state

        def spy(*args, **kwargs):
            seen.append(dict(kwargs))
            return real(*args, **kwargs)

        monkeypatch.setattr(tasks_module, "build_plan_state", spy)
        view = TasksView(scene, pm)
        qtbot.addWidget(view)
        view.refresh()
        assert seen and seen[-1]["today"] == datetime.date(2031, 7, 1)

    def test_a_fallback_scene_reads_the_wall_day(self) -> None:
        class Plain:
            pass

        assert plan_day_of(Plain()) == datetime.date.today()


class TestSuccessionBadge:
    def test_the_badge_follows_the_plan_day_and_is_rebuilt_on_a_date_change(
        self, window
    ) -> None:
        bed = RectangleItem(
            100, 100, 200, 150, object_type=ObjectType.GARDEN_BED, name="Bed"
        )
        window.canvas_scene.addItem(bed)
        plan = SuccessionPlan(
            bed_id=str(bed.item_id),
            year=2031,
            entries=[
                _entry("Lettuce", "2031-06-01", "2031-07-15"),
                _entry("Kale", "2031-07-16", "2031-09-30"),
            ],
        )
        window._project_manager.set_succession_plan(str(bed.item_id), plan.to_dict())

        window._sim_clock.set_date(datetime.date(2031, 7, 1))
        window._on_sim_date_changed(datetime.date(2031, 7, 1))
        assert ("Lettuce", True) in bed._succession_lines
        assert ("Kale", False) in bed._succession_lines

        window._sim_clock.set_date(datetime.date(2031, 8, 1))
        window._on_sim_date_changed(datetime.date(2031, 8, 1))
        assert ("Kale", True) in bed._succession_lines
        assert ("Lettuce", False) not in bed._succession_lines

    def test_a_date_change_schedules_the_calendar_refresh(self, window) -> None:
        window._sim_clock.set_date(datetime.date(2031, 7, 1))
        window._on_sim_date_changed(datetime.date(2031, 7, 1))
        assert window.calendar_view._refresh_timer.isActive()
