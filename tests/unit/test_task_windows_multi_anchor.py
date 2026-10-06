"""#414 — every GUI task surface must see the windows the agent already saw.

The Tasks tab, the planting-calendar dashboard and the Gantt each anchored their
frost-relative windows on the **current year's** last spring frost, while the
agent's ``get_tasks`` / ``get_task_calendar`` (``generate_for_date_window``)
anchored on every year whose frost can reach the requested dates. So a window
anchored on another year's frost appeared in the agent and on no GUI surface:

* a 20 September frost put a tomato harvest at 29 Nov 2026 – 7 Feb 2027, which
  the Tasks tab and dashboard dropped entirely on 1 January 2027 — a
  tomato-only plan then read "No tasks — you're all caught up." while the task
  was open;
* a 15 February frost put broad-bean sowing at 21 Dec 2026 – 18 Jan 2027, not
  listed before 1 January;
* a 9 April frost put garlic's autumn sowing (9–23 Oct 2026) on no GUI surface.

The measurement itself is **not** this file. It is
`scripts/measure_task_window_sweep.py`, which prints every figure quoted in ADR-029, §11.4, the roadmap and
CLAUDE.md/AGENTS.md: over the 64 bundled species that carry calendar offsets x 6
frost dates x every 10th day of 2026 (222 cases), **1,849 missed (task, frost
date, day) cases before the fix, 0 after, with 0 listed that the agent did not
list**. The absolute count is harness-dependent — all 118 species on every day
gives 2,669 before / 0 after — so quote the harness with the number.

What THIS file pins is the invariant, on a smaller fixture: `agent <= gui` and
`gui <= agent` over two hand-written species (GARLIC, TOMATO) x 6 frost dates x
every 15th day, i.e. it fails if either surface hides a task the other can see.

Qt-free, so the sweep is cheap: the GUI's listing rule is
``classify_urgency(...) is not None`` applied to the shared generator's output,
which is exactly what the widgets do (invariant: both sides read the same
function). The widget-level counterpart is
``tests/integration/test_task_windows_multi_anchor.py``.
"""

from __future__ import annotations

import datetime

import pytest

from open_garden_planner.services.task_generator import (
    PlanState,
    PlantRowInput,
    classify_urgency,
    generate_actionable_for_surface,
    generate_for_date_window,
)

# Garlic as bundled: sown 26..24 weeks BEFORE the frost, harvested 26..32 weeks
# after it. A 9 April frost therefore puts the sowing in October and the harvest
# the following April — both far from "today" in January.
GARLIC = PlantRowInput(
    display_name="Garlic",
    species_key="allium sativum",
    direct_sow_start=-26,
    direct_sow_end=-24,
    harvest_start=26,
    harvest_end=32,
)

# A southern plan: 20 September frost, harvest 10..18 weeks later.
TOMATO = PlantRowInput(
    display_name="Tomato",
    species_key="solanum_lycopersicum",
    indoor_sow_start=-8,
    indoor_sow_end=-6,
    transplant_start=4,
    harvest_start=10,
    harvest_end=18,
)


def _state(row: PlantRowInput, frost_mmdd: str, today: datetime.date) -> PlanState:
    last_frost = datetime.date(
        today.year, *(int(p) for p in frost_mmdd.split("-"))
    )
    return PlanState(
        today=today,
        year=today.year,
        last_frost=last_frost,
        plant_rows=(row,),
    )


def _gui_ids(state: PlanState) -> set[str]:
    """The task ids a GUI surface lists (the shared multi-anchor + urgency rule)."""
    return {t.task_id for t in generate_actionable_for_surface(state)}


def _agent_ids(state: PlanState, start: datetime.date, end: datetime.date) -> set[str]:
    """The task ids the agent's date-window read returns.

    Mirrors the agent call sites, which pass ``actionable_only=False`` — an
    explicit date-window read wants the complete dated schedule, not the urgent
    subset (see ``build_plan_state``). Getting this wrong hides the very
    windows #414 is about.
    """
    from dataclasses import replace

    return {
        t.task_id
        for t in generate_for_date_window(replace(state, actionable_only=False), start, end)
    }


class TestTheIssuesWorkedExamples:
    def test_tomato_harvest_is_listed_in_early_january(self) -> None:
        """#414: the harvest 29 Nov 2026 – 7 Feb 2027 left the GUI on 1 Jan 2027."""
        today = datetime.date(2027, 1, 1)
        state = _state(TOMATO, "09-20", today)

        agent = _agent_ids(
            state, datetime.date(2026, 12, 1), datetime.date(2027, 2, 28)
        )
        harvest_ids = {i for i in agent if i.endswith(":harvest:2026")}

        assert harvest_ids, "the agent must list the 2026-anchored harvest"
        assert harvest_ids <= _gui_ids(state), (
            "the GUI listed nothing the agent did not; the tomato harvest "
            "disappeared from the Tasks tab and dashboard while still open"
        )

    def test_garlic_autumn_sowing_is_listed_in_october(self) -> None:
        """#414: with a 9 April frost the sowing 9–23 Oct 2026 reached no surface."""
        today = datetime.date(2026, 10, 15)
        state = _state(GARLIC, "04-09", today)

        agent = _agent_ids(state, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))
        sowing_ids = {i for i in agent if ":direct_sow:" in i}
        assert sowing_ids
        assert sowing_ids <= _gui_ids(state)

    def test_broad_bean_sowing_spanning_new_year_is_listed(self) -> None:
        """A 15 February frost puts broad-bean sowing 21 Dec – 18 Jan."""
        row = PlantRowInput(
            display_name="Broad Bean",
            species_key="vicia faba",
            direct_sow_start=-8,
            direct_sow_end=-4,
        )
        today = datetime.date(2026, 12, 28)
        state = _state(row, "02-15", today)
        agent = _agent_ids(
            state, datetime.date(2026, 12, 1), datetime.date(2027, 1, 31)
        )
        assert agent
        assert agent <= _gui_ids(state)


class TestGuiNeverListsLessThanTheAgent:
    """The core invariant, stated the way #414 measured it.

    "The GUI's own listing rule (``classify_urgency`` not None) applied to BOTH
    sides." Comparing raw agent output against the filtered GUI list would be
    apples to oranges — the urgency window deliberately hides a window that
    starts in 43 days. On master this sweep found 177,393 missed
    (task, frost date, day) cases over 53 frost dates and every day of 2026; the
    sweep below is the regression guard, parametrised rather than exhaustive
    because each case is a full multi-anchor generation.
    """

    @staticmethod
    def _actionable(ids: set[str], state: PlanState, tasks: list) -> set[str]:
        return {
            t.task_id for t in tasks
            if t.task_id in ids
            and classify_urgency(t.start_date, t.end_date, state.today) is not None
        }

    @pytest.mark.parametrize("frost", ["03-15", "04-09", "05-15", "09-20", "10-15", "11-15"])
    def test_no_gui_surface_misses_a_window_the_agent_lists(self, frost: str) -> None:
        from dataclasses import replace

        for row in (GARLIC, TOMATO):
            for day_offset in range(0, 365, 15):
                today = datetime.date(2026, 1, 1) + datetime.timedelta(days=day_offset)
                try:
                    state = _state(row, frost, today)
                except ValueError:
                    continue
                start = today - datetime.timedelta(days=45)
                end = today + datetime.timedelta(days=45)
                agent_tasks = generate_for_date_window(
                    replace(state, actionable_only=False), start, end
                )
                agent = {
                    t.task_id for t in agent_tasks
                    if classify_urgency(t.start_date, t.end_date, state.today) is not None
                }
                gui = _gui_ids(state)
                assert agent <= gui, (
                    f"{row.species_key} frost={frost} today={today}: "
                    f"agent lists {sorted(agent - gui)} but no GUI surface does"
                )
                # The other direction. Six documents quote a measured 0 surplus
                # here; before this assertion it was prose, not a test. NOTE what
                # this fixture can and cannot catch: because the GUI's span is a
                # subset of the harness's agent span and both sides call the same
                # generator, this catches a widened/loosened GUI window rather
                # than a deleted urgency filter — `test_the_gui_still_filters_by_
                # urgency` covers that one.
                assert gui <= agent, (
                    f"{row.species_key} frost={frost} today={today}: the GUI lists "
                    f"{sorted(gui - agent)} that the agent does not — the urgency "
                    "filter leaked"
                )

    def test_the_gui_still_filters_by_urgency(self) -> None:
        """The helper must NOT turn the Tasks tab into a decade-long list.

        ``generate_for_date_window`` internally runs with
        ``actionable_only=False``; the post-filter is what keeps the GUI listing
        narrow. Without it the tab would show every task of the next ten years.
        """
        state = _state(GARLIC, "04-09", datetime.date(2026, 1, 5))
        listed = generate_actionable_for_surface(state)
        for task in listed:
            assert classify_urgency(task.start_date, task.end_date, state.today) is not None

        # A harvest 26..32 weeks out is not actionable on 5 January, so the tab
        # must not list it, even though it exists.
        harvest = [t for t in listed if t.task_type == "harvest"]
        assert harvest == [], (
            "the 2026-anchored garlic harvest (8 Oct - 19 Nov) is not actionable "
            "on 5 January and must not appear"
        )


class TestAnchorYearTaskIds:
    def test_different_anchor_years_yield_different_ids(self) -> None:
        """Invariant 6: the id carries the anchor year, so statuses stay separate.

        Two anchor years are two different physical harvests; marking one done
        must not mark the other. This is why the GUI can list several anchors
        without collapsing their status.
        """
        state = _state(TOMATO, "09-20", datetime.date(2027, 1, 1))
        ids = _agent_ids(state, datetime.date(2026, 1, 1), datetime.date(2028, 12, 31))
        harvest_years = {i.rsplit(":", 1)[1] for i in ids if ":harvest:" in i}
        assert len(harvest_years) >= 2, (
            f"expected several anchored harvest ids, got {sorted(ids)}"
        )

    def test_the_same_anchor_is_not_duplicated(self) -> None:
        state = _state(TOMATO, "09-20", datetime.date(2027, 1, 1))
        ids = _agent_ids(state, datetime.date(2026, 1, 1), datetime.date(2028, 12, 31))
        assert len(ids) == len(set(ids))


class TestNoFrostAnchorDegradesGracefully:
    def test_no_location_still_lists_absolute_date_tasks(self) -> None:
        """A plan without frost dates must still show manual/soil tasks."""
        from open_garden_planner.models.task import ManualTask

        state = PlanState(
            today=datetime.date(2026, 6, 1),
            year=2026,
            last_frost=None,
            manual_tasks=(ManualTask(id="m1", title="Buy compost", date="2026-06-01"),),
        )
        ids = _gui_ids(state)
        assert "m1" in ids


class TestManualTasksSurviveTheSurfaceFilter:
    """Regression: both P0s the senior review found, in the same 8 lines.

    ``generate_actionable_for_surface`` applied the urgency filter to EVERY task.
    That (a) raised ``TypeError`` on an undated manual task, taking both task
    tabs down for a plan the agent's own ``add_manual_task`` can produce, and
    (b) filtered manual tasks that ``generate_manual_tasks`` documents as never
    filtered — hiding a December task in June.
    """

    @staticmethod
    def _state(today: datetime.date) -> PlanState:
        from open_garden_planner.models.task import ManualTask

        return PlanState(
            today=today,
            year=today.year,
            last_frost=datetime.date(today.year, 4, 9),
            manual_tasks=(
                ManualTask(id="undated", title="Check hedge", date=None),
                ManualTask(id="long_past", title="Old job", date="2026-01-05"),
                ManualTask(id="far_future", title="Order glass", date="2026-12-20"),
            ),
        )

    def test_an_undated_manual_task_does_not_crash_the_listing(self) -> None:
        """`classify_urgency` dereferences both dates; None must not reach it."""
        state = self._state(datetime.date(2026, 6, 1))
        ids = _gui_ids(state)          # would raise TypeError before the fix
        assert "undated" in ids

    def test_manual_tasks_are_never_urgency_filtered(self) -> None:
        """The generator's documented contract: a manual to-do always appears."""
        state = self._state(datetime.date(2026, 6, 1))
        ids = _gui_ids(state)
        for task_id in ("undated", "long_past", "far_future"):
            assert task_id in ids, f"{task_id} was hidden by the urgency filter"

    def test_the_gui_matches_generate_all_for_manual_tasks(self) -> None:
        """Whatever master listed from the manual generator, we still list."""
        from open_garden_planner.services.task_generator import generate_all

        state = self._state(datetime.date(2026, 6, 1))
        before = {t.task_id for t in generate_all(state) if t.source == "manual"}
        assert before <= _gui_ids(state)
