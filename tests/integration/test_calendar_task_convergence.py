"""Convergence (#228): the planting-calendar dashboard and the Tasks tab are now
driven by the SAME generation engine and the SAME status store, so done / snooze /
dismiss for a given task id agree across both surfaces.

The calendar shows only actionable, still-open tasks; the Tasks tab classifies the
same task by ``effective_status``. Both read the project's single ``task_states``
store, so a status set on either surface is reflected on the other.
"""
# ruff: noqa: ARG001, ARG002

import datetime

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.services.task_generator import build_plan_state, generate_all
from open_garden_planner.services.task_status import effective_status
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.views.planting_calendar_view import PlantingCalendarView

TODAY = datetime.date.today()

_SPECIES = {
    "scientific_name": "Solanum lycopersicum",
    "common_name": "Tomato",
    "source_id": "12345",
    "harvest_start": 0,  # harvest window opens *today* (last_frost == today)
    "harvest_end": 0,
}


def _harvest_id() -> str:
    key = species_key(_SPECIES)
    return f"{key}:harvest:{TODAY.year}"


def _build():
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    plant = CircleItem(
        center_x=100, center_y=100, radius=20,
        object_type=ObjectType.TREE, name="Tomato",
    )
    plant.metadata["plant_species"] = dict(_SPECIES)
    scene.addItem(plant)
    pm = ProjectManager()
    pm.set_location({"frost_dates": {"last_spring_frost": TODAY.strftime("%m-%d")}})
    return scene, pm


def _calendar_tids(view: PlantingCalendarView) -> set[str]:
    return {t.task_id for t in view._current_dashboard_tasks}


def _tasks_tab_status(scene, pm, tid: str) -> str | None:
    """Mirror TasksView.refresh: generate from the unified engine, resolve status."""
    tasks = generate_all(build_plan_state(scene, pm, frost_alerts=[], soil_service=None))
    if not any(t.task_id == tid for t in tasks):
        return None
    return effective_status(pm.task_states.get(tid), TODAY)


class TestCalendarTasksTabConvergence:
    def test_done_snooze_dismiss_agree_across_surfaces(self, qtbot) -> None:
        scene, pm = _build()
        view = PlantingCalendarView(scene, pm)
        qtbot.addWidget(view)
        tid = _harvest_id()

        # Both surfaces derive the SAME task_id and start with it open/visible.
        view.refresh()
        assert tid in _calendar_tids(view)
        assert _tasks_tab_status(scene, pm, tid) == "open"

        # (a) Done via the calendar's "Done" toggle (set_task_completion) →
        #     hidden on the calendar, "done" on the Tasks tab.
        pm.set_task_completion(tid, True)
        view.refresh()
        assert tid not in _calendar_tids(view)
        assert _tasks_tab_status(scene, pm, tid) == "done"

        # (b) Snooze via the Tasks-tab path (set_task_status) → hidden on the
        #     calendar, "snoozed" on the Tasks tab.
        future = (TODAY + datetime.timedelta(days=10)).isoformat()
        pm.set_task_status(tid, "open", snooze_until=future)
        view.refresh()
        assert tid not in _calendar_tids(view)
        assert _tasks_tab_status(scene, pm, tid) == "snoozed"

        # (c) Dismiss → hidden on both surfaces.
        pm.set_task_status(tid, "dismissed")
        view.refresh()
        assert tid not in _calendar_tids(view)
        assert _tasks_tab_status(scene, pm, tid) == "dismissed"
