"""#415 regression, widget level: a multi-step gesture must persist BOTH values.

This file exists because the unit-level twin wired ``step_date_changed`` to a bare
lambda, so the panel under test had nothing behind it. That is exactly what let a
real defect through a green test: in production the signal is connected to
``PlantingCalendarView._on_step_date_changed``, which calls ``refresh()``, which
reaches back into ``_DetailPanel._populate_prop_editor`` and rewrites every date
editor.

So the flush read the editors *inside* the emit loop, and for a gesture touching
two steps the second one persisted a value the re-population had reverted — or was
lost outright. Measured before the fix: arming ``indoor_sow`` start and
``harden_off`` end and flushing stored only ``harden_off``; the user's
``indoor_sow`` start never reached the project.
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

import datetime

import pytest
from PyQt6.QtCore import QDate

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.views.planting_calendar_view import PlantingCalendarView

SPECIES = {
    "scientific_name": "Solanum lycopersicum",
    "common_name": "Tomato",
    "source_id": "414",
    "indoor_sow_start": -8,
    "indoor_sow_end": -6,
    "transplant_start": 4,
    "transplant_start_end": 6,
    "harvest_start": 10,
    "harvest_end": 18,
}


def _view(qtbot) -> tuple[PlantingCalendarView, str]:
    """A real PlantingCalendarView with the propagation editor switched on."""
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    item = CircleItem(
        center_x=100, center_y=100, radius=20,
        object_type=ObjectType.TREE, name="Tomato",
    )
    item.metadata["plant_species"] = dict(SPECIES)
    scene.addItem(item)

    pm = ProjectManager()
    pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})

    view = PlantingCalendarView(scene, pm)
    qtbot.addWidget(view)
    view._prop_toggle.setChecked(True)
    view.refresh()
    view.resize(1200, 900)

    key = next(iter(view._prop_plans))
    panel = view._detail
    panel.set_show_propagation(True)
    panel.show_species(
        PlantSpeciesData.from_dict(SPECIES), key, view._prop_plans[key]
    )
    return view, key


class TestMultiStepGesturePersistsBothValues:
    def test_both_edits_reach_the_project(self, qtbot) -> None:
        """The P0: a multi-step gesture persisted only the first value.

        Two defects were tangled here and both are fixed:
          * the flush read the editors INSIDE the emit loop, so the second step's
            dates were read after the first emit had re-populated them;
          * dragging a start past its end produced an inverted pair, which the
            persistence layer refuses — so the edit was dropped with no feedback.
            The flush now normalises the pair instead.
        """
        view, key = _view(qtbot)
        panel = view._detail

        # Set BOTH dates of each step, so nothing depends on a calculated value
        # left behind in the editor.
        indoor_start, indoor_end = panel._step_rows["indoor_sow"][0:2]
        harden_start, harden_end = panel._step_rows["harden_off"][0:2]
        indoor_start.setDate(QDate(2026, 5, 4))
        indoor_end.setDate(QDate(2026, 5, 20))
        harden_start.setDate(QDate(2026, 6, 1))
        harden_end.setDate(QDate(2026, 6, 20))
        assert sorted(panel._pending_steps) == ["harden_off", "indoor_sow"]

        panel._flush_pending_steps()

        overrides = view._project_manager.propagation_overrides.get(key, {})
        assert overrides.get("indoor_sow") == {
            "start": "2026-05-04", "end": "2026-05-20",
        }, f"the indoor_sow edit was lost or reverted; stored: {overrides}"
        assert overrides.get("harden_off") == {
            "start": "2026-06-01", "end": "2026-06-20",
        }, f"the harden_off edit was lost or reverted; stored: {overrides}"

    def test_a_start_dragged_past_its_end_is_normalised_not_dropped(self, qtbot) -> None:
        """The silent-refusal case the review flagged, pinned at the widget.

        The user moves only the start past the unchanged end. The pair cannot be
        stored as-is, so it must be clamped to a zero-length period and STORED —
        before the fix nothing was stored and the edit simply vanished.
        """
        view, key = _view(qtbot)
        panel = view._detail

        indoor_start, _end = panel._step_rows["indoor_sow"][0:2]
        indoor_start.setDate(QDate(2027, 6, 1))   # far past the calculated end
        panel._flush_pending_steps()

        stored = view._project_manager.propagation_overrides.get(key, {}).get("indoor_sow")
        assert stored is not None, "the edit was silently dropped"
        assert stored["start"] == "2027-06-01"
        assert stored["end"] >= stored["start"], stored

    def test_the_write_path_reports_a_refusal_instead_of_swallowing_it(self) -> None:
        """`set_propagation_override` returns whether it stored, so a refusal is
        observable rather than a silent no-op that looks like a saved edit."""
        pm = ProjectManager()
        assert pm.set_propagation_override("k", "indoor_sow", "2026-12-24", "2026-01-22") is False
        assert pm.propagation_overrides == {}
        assert pm.set_propagation_override("k", "indoor_sow", "2026-01-22", "2026-12-24") is True
        assert pm.set_propagation_override("k", "indoor_sow", "not-a-date", "2026-12-24") is False

    def test_a_stored_value_is_never_inverted_by_the_flush(self, qtbot) -> None:
        """Whatever the gesture, the persisted pair is ordered."""
        view, key = _view(qtbot)
        panel = view._detail
        indoor_start, indoor_end = panel._step_rows["indoor_sow"][0:2]
        indoor_start.setDate(QDate(2026, 6, 1))
        indoor_end.setDate(QDate(2026, 5, 1))
        panel._flush_pending_steps()

        stored = view._project_manager.propagation_overrides.get(key, {}).get("indoor_sow")
        if stored is not None:
            assert stored["end"] >= stored["start"], (
                f"an inverted pair was persisted: {stored}"
            )

    def test_the_flush_is_idempotent(self, qtbot) -> None:
        """A second flush with nothing armed must not write anything again."""
        view, key = _view(qtbot)
        panel = view._detail
        panel._step_rows["indoor_sow"][0].setDate(QDate(2026, 5, 4))
        panel._flush_pending_steps()
        first = dict(view._project_manager.propagation_overrides.get(key, {}))

        panel._flush_pending_steps()
        assert view._project_manager.propagation_overrides.get(key, {}) == first


class TestUndatedAndManualTasksReachTheWidgets:
    """The two P0s from the first review, driven through the REAL TasksView."""

    def test_an_undated_manual_task_does_not_crash_the_tasks_tab(self, qtbot) -> None:
        from open_garden_planner.models.task import ManualTask
        from open_garden_planner.ui.views.tasks_view import TasksView

        scene = CanvasScene(width_cm=2000, height_cm=2000)
        pm = ProjectManager()
        pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})
        pm.set_manual_task(ManualTask(id="undated", title="Check the hedge", date=None))

        view = TasksView(scene, pm)
        qtbot.addWidget(view)
        view.refresh()   # raised TypeError before the fix

    def test_a_far_future_manual_task_is_still_listed(self, qtbot) -> None:
        from open_garden_planner.models.task import ManualTask
        from open_garden_planner.ui.views.tasks_view import TasksView

        scene = CanvasScene(width_cm=2000, height_cm=2000)
        pm = ProjectManager()
        pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})
        far = datetime.date.today().replace(month=12, day=20)
        pm.set_manual_task(ManualTask(id="far", title="Order greenhouse glass",
                                      date=far.isoformat()))

        view = TasksView(scene, pm)
        qtbot.addWidget(view)
        view.refresh()

        from PyQt6.QtWidgets import QLabel

        texts = [w.text() for w in view.findChildren(QLabel)]
        assert any("Order greenhouse glass" in t for t in texts), (
            "a December task must not be hidden when read in June"
        )

    @pytest.mark.parametrize("offset_days", [-200, 3, 200])
    def test_manual_task_status_flows_through_the_widget(
        self, qtbot, offset_days: int
    ) -> None:
        from open_garden_planner.models.task import ManualTask
        from open_garden_planner.ui.views.tasks_view import TasksView

        scene = CanvasScene(width_cm=2000, height_cm=2000)
        pm = ProjectManager()
        pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})
        due = datetime.date.today() + datetime.timedelta(days=offset_days)
        pm.set_manual_task(ManualTask(id="m", title="Distinct task title",
                                      date=due.isoformat()))

        view = TasksView(scene, pm)
        qtbot.addWidget(view)
        view.refresh()

        from PyQt6.QtWidgets import QLabel

        texts = [w.text() for w in view.findChildren(QLabel)]
        assert any("Distinct task title" in t for t in texts), (
            f"a manual task {offset_days:+d} days out was not rendered"
        )
