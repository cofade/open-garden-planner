"""#414 end-to-end: the GUI task surfaces list the multi-year anchored windows.

The Qt-free sweep in ``tests/unit/test_task_windows_multi_anchor.py`` pins the
generation logic (measured over 64 bundled species and 222 frost-date/day
cases: **1,849** (task, frost date, day) cases missed on master, **0** after).
This file drives the real widgets — ``TasksView`` and the planting calendar's
dashboard and Gantt — because the bug was partly that each surface built its own
list instead of consuming the shared engine.

Observed failing on master before the fix:

* the Tasks tab dropped a tomato harvest running 29 Nov 2026 – 7 Feb 2027 on
  1 January 2027 (a tomato-only plan read "No tasks — you're all caught up.");
* the dashboard omitted it too;
* the Gantt recomputed its bars from the current year's frost, so a window
  anchored on another year had no bar at all.
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

import datetime

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.views.planting_calendar_view import PlantingCalendarView
from open_garden_planner.ui.views.tasks_view import TasksView

# A southern plan: 20 September last spring frost, so the tomato harvest runs
# 10..18 weeks later — 29 Nov 2026 to 7 Feb 2027, across the new year.
TOMATO = {
    "scientific_name": "Solanum lycopersicum",
    "common_name": "Tomato",
    "source_id": "12345",
    "indoor_sow_start": -8,
    "indoor_sow_end": -6,
    "transplant_start": 4,
    "transplant_end": 6,
    "harvest_start": 10,
    "harvest_end": 18,
}

TODAY = datetime.date(2027, 1, 1)
FROST = "09-20"


def _build(frost: str = FROST):
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    plant = CircleItem(
        center_x=100, center_y=100, radius=20,
        object_type=ObjectType.TREE, name="Tomato",
    )
    plant.metadata["plant_species"] = dict(TOMATO)
    scene.addItem(plant)
    pm = ProjectManager()
    pm.set_location({"frost_dates": {"last_spring_frost": frost}})
    return scene, pm


def _rendered_task_ids(qtbot, monkeypatch) -> set[str]:
    """The task ids the Tasks tab actually rendered into a section.

    Captured at ``_add_section``, the one point every listed task passes
    through — reading the widgets instead would only see formatted label text.
    """
    captured: list[str] = []
    original = TasksView._add_section

    def spy(self, title, color, tasks, **kwargs):  # type: ignore[no-untyped-def]
        captured.extend(t.task_id for t in tasks)
        return original(self, title, color, tasks, **kwargs)

    monkeypatch.setattr(TasksView, "_add_section", spy)

    scene, pm = _build()
    view = TasksView(scene, pm)
    qtbot.addWidget(view)
    with _pinned_today(TODAY):
        view.refresh()
    return set(captured)


class _pinned_today:
    """Pin ``date.today()`` — the defect is about which year "today" falls in."""

    def __init__(self, day: datetime.date) -> None:
        self._day = day

    def __enter__(self):
        import open_garden_planner.services.task_generator as tg

        self._tg = tg
        self._real = tg.datetime.date

        class _Frozen(datetime.date):
            @classmethod
            def today(cls):  # type: ignore[override]
                return self._day

        tg.datetime.date = _Frozen
        return self

    def __exit__(self, *exc):
        self._tg.datetime.date = self._real
        return False


class TestTasksTab:
    def test_a_window_open_in_january_is_still_listed(self, qtbot, monkeypatch) -> None:
        """The #414 headline: a harvest spanning New Year vanished on 1 Jan."""
        ids = _rendered_task_ids(qtbot, monkeypatch)
        assert any(i.endswith(":harvest:2026") for i in ids), (
            f"expected the 2026-anchored tomato harvest, got {sorted(ids)}"
        )

    def test_the_tab_is_not_flooded_with_far_future_windows(self, qtbot, monkeypatch) -> None:
        """The urgency filter must survive the multi-anchor change.

        Without the post-filter the tab would list every task of the decade —
        the regression the helper's ``actionable_only=False`` inner pass makes
        easy to introduce.
        """
        ids = _rendered_task_ids(qtbot, monkeypatch)
        assert len(ids) < 20, f"the tab listed {len(ids)} tasks; the urgency filter leaked"
        assert not any(i.endswith(":harvest:2028") for i in ids), (
            "a harvest anchored two years out is not actionable and must not be listed"
        )


class TestPlantingCalendarDashboard:
    def test_dashboard_lists_the_spanning_harvest(self, qtbot) -> None:
        scene, pm = _build()
        view = PlantingCalendarView(scene, pm)
        qtbot.addWidget(view)
        with _pinned_today(TODAY):
            view.refresh()
            ids = {t.task_id for t in view._current_dashboard_tasks}
        assert any(i.endswith(":harvest:2026") for i in ids), sorted(ids)


class TestGanttDrawsAdjacentAnchorWindows:
    def test_a_window_clipped_to_the_year_edge_is_drawn(self, qtbot) -> None:
        """The signature of an adjacent-year anchor: a bar clipped to 1 Jan/31 Dec.

        On master the Gantt recomputed every window from the displayed year's
        frost, so nothing could ever be clipped at a year boundary.
        """
        scene, pm = _build()
        view = PlantingCalendarView(scene, pm)
        qtbot.addWidget(view)
        with _pinned_today(datetime.date(2027, 6, 1)):
            view.refresh()
            year = 2027
            windows, _prop_steps = view._compute_gantt_windows(year)

        assert windows, "the Gantt received no windows at all"
        edges = {
            datetime.date(year, 1, 1), datetime.date(year, 12, 31)
        }
        clipped = [
            w for values in windows.values() for w in values
            if w.start in edges or w.end in edges
        ]
        assert clipped, (
            "no window was clipped to a year edge, which is the signature of a "
            "window anchored on an adjacent year's frost"
        )

    def test_gantt_and_dashboard_read_the_same_snapshot(self, qtbot) -> None:
        """One snapshot feeds both, so they cannot disagree about anchor years."""
        scene, pm = _build()
        view = PlantingCalendarView(scene, pm)
        qtbot.addWidget(view)
        with _pinned_today(TODAY):
            view.refresh()
            assert view._plan_state is not None
            year = TODAY.year
            windows, _ = view._compute_gantt_windows(year)
            # Every Gantt window's species must also appear in the plan state.
            assert set(windows) <= {r.species_key for r in view._plan_state.plant_rows}


class TestFeb29FrostPlan:
    """A 29-February frost must not produce an empty surface (#414)."""

    @pytest.mark.parametrize("year", [2027, 2028], ids=["non_leap", "leap"])
    def test_a_plan_with_a_feb_29_frost_has_tasks_in_every_year(self, year: int) -> None:
        from open_garden_planner.services.task_generator import (
            build_plan_state,
            generate_actionable_for_surface,
        )

        scene, pm = _build(frost="02-29")
        today = datetime.date(year, 6, 1)

        state = build_plan_state(scene, pm, today=today, year=year)
        assert state.last_frost is not None, (
            f"{year}: a 29-February frost must resolve, not vanish"
        )
        assert generate_actionable_for_surface(state), (
            f"{year}: the surface is empty for a plan that has a frost date; "
            f"resolved frost was {state.last_frost}"
        )

    def test_non_leap_year_substitutes_one_march(self) -> None:
        """The substitution is a real, dated value — not a silently missing plan."""
        from open_garden_planner.services.frost_dates import (
            NON_LEAP_SUBSTITUTE_MONTH_DAY,
            parse_frost,
        )

        assert parse_frost("02-29", 2028) == datetime.date(2028, 2, 29)
        assert parse_frost("02-29", 2027) == datetime.date(
            2027, *NON_LEAP_SUBSTITUTE_MONTH_DAY
        )
