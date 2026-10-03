"""End-to-end integration tests for the US-D3.3 / US-D3.4 agent tools.

These drive the REAL ``GardenPlannerApp`` wiring rather than a test-local mirror
of it. That choice is the point of the file: #291 shipped six releases with the
embedded server never starting in the frozen exe, and the recurring failure mode
this repo keeps paying for is a tool that is unit-tested, registered, and never
actually wired to anything. A harness that re-implements the provider body would
test itself and pass happily while the real ``_do_agent_*`` method raised on
first call.

Two layers are covered, because they fail differently:

* the READ tools over a real MCP client, so the transport, the ``@mcp.tool()``
  registration and the main-thread hop are all exercised; and
* the WRITE tools through the app's own provider methods, which is where the
  one-undo-step and refusal contracts actually live.

Every write assertion checks the UNDO DEPTH, not merely that undo works — "undo
does something" passes for a write that pushed three commands.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

TODAY = "2026-10-03"
LOCATION = {
    "latitude": 52.5,
    "longitude": 13.4,
    "frost_dates": {"last_spring_frost": "04-15", "first_fall_frost": "10-20"},
}


@pytest.fixture(autouse=True)
def _no_welcome_dialog(_reset_app_settings: Any) -> None:
    get_settings().show_welcome_on_startup = False


@pytest.fixture
def app(qtbot: Any):
    """A real app with one soil bed, one trellis and a geo-location.

    The TRELLIS matters: it is a plant parent but holds no soil (ADR-031's whole
    reason for two predicates), so the soil tools must refuse it exactly as
    ``set_succession_plan`` does.
    """
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win._project_manager.set_location(LOCATION)

    bed = RectangleItem(0, 0, 200, 100)
    bed.object_type = ObjectType.RAISED_BED
    win.canvas_scene.addItem(bed)

    trellis = RectangleItem(600, 0, 200, 100)
    trellis.object_type = ObjectType.TRELLIS
    win.canvas_scene.addItem(trellis)

    win._agent_set_frost_alerts([])
    # These tests deliberately dirty the plan, and pytestqt closes the window in
    # its own teardown — where closeEvent raises a MODAL unsaved-changes dialog
    # and hangs the run. Neutralise it on the INSTANCE (not the class, so no
    # other suite is affected) rather than relying on a fixture finalizer that
    # may run after pytestqt has already closed the window.
    win._confirm_discard_changes = lambda *_a, **_k: False
    yield win
    win._stop_agent_api()


@pytest.fixture
def bed_id(app: Any) -> str:
    for item in app.canvas_scene.items():
        if getattr(item, "object_type", None) is ObjectType.RAISED_BED:
            return str(item.item_id)
    raise AssertionError("fixture did not create a bed")


@pytest.fixture
def trellis_id(app: Any) -> str:
    for item in app.canvas_scene.items():
        if getattr(item, "object_type", None) is ObjectType.TRELLIS:
            return str(item.item_id)
    raise AssertionError("fixture did not create a trellis")


def _undo_depth(app: Any) -> int:
    return app._agent_get_history()["undo_depth"]


def _redo_depth(app: Any) -> int:
    return app._agent_get_history()["redo_depth"]


# ══════════════════════════════════════════════════════════════════════════════
# US-D3.3 — task calendar reads
# ══════════════════════════════════════════════════════════════════════════════


class TestTaskReads:
    def test_get_tasks_reports_coverage_and_a_window(self, app: Any) -> None:
        result = app._agent_get_tasks(today=TODAY)
        assert result["coverage"] == "full", "the fixture has frost dates"
        assert result["today"] == TODAY
        assert result["from_date"] == "2026-09-03"
        assert result["to_date"] == "2026-11-02"
        assert isinstance(result["tasks"], list)

    def test_get_tasks_is_reproducible(self, app: Any) -> None:
        """Two calls, same reference date, byte-identical answer."""
        assert app._agent_get_tasks(today=TODAY) == app._agent_get_tasks(today=TODAY)

    def test_missing_location_degrades_loudly(self, app: Any) -> None:
        """No geo-location ⇒ no frost dates ⇒ the marker, not an empty week."""
        app._project_manager.set_location({})
        result = app._agent_get_tasks(today=TODAY)
        assert result["coverage"] == "no_frost_dates"

    def test_unknown_source_is_refused_not_ignored(self, app: Any) -> None:
        """A typo must not silently return 'everything'."""
        with pytest.raises(ValueError, match="not a task source"):
            app._agent_get_tasks(source="calender", today=TODAY)

    @pytest.mark.parametrize(
        "source", ["calendar", "propagation", "succession", "frost", "manual"]
    )
    def test_declared_sources_are_accepted(self, app: Any, source: str) -> None:
        assert app._agent_get_tasks(source=source, today=TODAY)["total"] >= 0

    def test_malformed_injected_date_is_refused(self, app: Any) -> None:
        with pytest.raises(ValueError, match="ISO date"):
            app._agent_get_tasks(today="03/10/2026")

    def test_malformed_window_date_is_refused(self, app: Any) -> None:
        with pytest.raises(ValueError, match="ISO date"):
            app._agent_get_tasks(from_date="yesterday", today=TODAY)

    def test_get_task_calendar_buckets_by_month(self, app: Any) -> None:
        result = app._agent_get_task_calendar(today=TODAY)
        assert result["year"] == 2026
        assert result["coverage"] == "full"
        for month in result["months"]:
            assert len(month["month"]) == 7 and month["month"][4] == "-"
            assert month["total"] == sum(month["by_source"].values())

    def test_calendar_year_out_of_range_is_refused(self, app: Any) -> None:
        with pytest.raises(ValueError, match="out of range"):
            app._agent_get_task_calendar(year=12, today=TODAY)


# ══════════════════════════════════════════════════════════════════════════════
# US-D3.3 — manual-task writes: ONE undo step each, refusals inert
# ══════════════════════════════════════════════════════════════════════════════


class TestManualTaskWrites:
    def test_add_then_undo_removes_the_task(self, app: Any) -> None:
        before = _undo_depth(app)
        result = app._agent_add_manual_task(
            title="Order seed", date="2026-10-05", notes="tomato", bed_id=None
        )
        assert _undo_depth(app) == before + 1, "exactly one undo step"

        task_id = result["task_id"]
        assert task_id in app._project_manager.manual_tasks
        # `manual_tasks` holds ManualTask.to_dict() values, not objects.
        assert app._project_manager.manual_tasks[task_id]["title"] == "Order seed"

        app._agent_undo()
        assert task_id not in app._project_manager.manual_tasks
        assert _undo_depth(app) == before

    def test_edit_is_one_undo_step_and_restores(self, app: Any) -> None:
        created = app._agent_add_manual_task(title="Order seed", date="2026-10-05")
        task_id = created["task_id"]
        before_edit = _undo_depth(app)

        app._agent_edit_manual_task(
            task_id=task_id, title="Order seeds NOW", date="2026-10-06"
        )
        assert _undo_depth(app) == before_edit + 1
        assert app._project_manager.manual_tasks[task_id]["title"] == "Order seeds NOW"

        app._agent_undo()
        assert app._project_manager.manual_tasks[task_id]["title"] == "Order seed"

    def test_delete_is_one_undo_step_and_restores(self, app: Any) -> None:
        created = app._agent_add_manual_task(title="Order seed")
        task_id = created["task_id"]
        before_delete = _undo_depth(app)

        result = app._agent_delete_manual_task(task_id)
        assert result["deleted"] is True
        assert _undo_depth(app) == before_delete + 1
        assert task_id not in app._project_manager.manual_tasks

        app._agent_undo()
        assert task_id in app._project_manager.manual_tasks

    def test_added_task_is_visible_to_get_tasks(self, app: Any) -> None:
        app._agent_add_manual_task(title="Order seed", date=TODAY)
        tasks = app._agent_get_tasks(source="manual", today=TODAY)
        assert [t["title"] for t in tasks["tasks"]] == ["Order seed"]

    def test_undated_task_is_visible_in_a_filtered_read(self, app: Any) -> None:
        app._agent_add_manual_task(title="Undated chore")
        tasks = app._agent_get_tasks(source="manual", from_date=TODAY, to_date=TODAY)
        assert [t["title"] for t in tasks["tasks"]] == ["Undated chore"]

    def test_task_ids_are_unique_across_calls(self, app: Any) -> None:
        a = app._agent_add_manual_task(title="One")
        b = app._agent_add_manual_task(title="Two")
        assert a["task_id"] != b["task_id"]

    # -- refusals: scene AND stack must be untouched -----------------------

    def test_empty_title_is_refused_inertly(self, app: Any) -> None:
        before, tasks_before = _undo_depth(app), dict(app._project_manager.manual_tasks)
        with pytest.raises(ValueError, match="title is required"):
            app._agent_add_manual_task(title="   ")
        assert _undo_depth(app) == before
        assert app._project_manager.manual_tasks == tasks_before

    def test_malformed_date_is_refused_inertly(self, app: Any) -> None:
        before = _undo_depth(app)
        with pytest.raises(ValueError, match="ISO date"):
            app._agent_add_manual_task(title="Order seed", date="soon")
        assert _undo_depth(app) == before
        assert app._project_manager.manual_tasks == {}

    def test_unknown_bed_is_refused_inertly(self, app: Any) -> None:
        before = _undo_depth(app)
        with pytest.raises(ValueError):
            app._agent_add_manual_task(title="Order seed", bed_id="not-a-uuid")
        assert _undo_depth(app) == before
        assert app._project_manager.manual_tasks == {}

    def test_trellis_is_refused_as_a_task_bed(self, app: Any, trellis_id: str) -> None:
        """A trellis holds no soil; it is still refused for a bed-linked task."""
        before = _undo_depth(app)
        with pytest.raises(ValueError):
            app._agent_add_manual_task(title="Order seed", bed_id=trellis_id)
        assert _undo_depth(app) == before

    def test_editing_a_generated_task_is_refused_by_name(self, app: Any) -> None:
        """Generated tasks are derived state, rebuilt on every read."""
        from open_garden_planner.services.task_generator import make_calendar_task_id

        generated_id = make_calendar_task_id("solanum_lycopersicum", "direct_sow", 2026)
        before = _undo_depth(app)
        with pytest.raises(ValueError, match="derived from the plan"):
            app._agent_edit_manual_task(task_id=generated_id, title="Hijacked")
        assert _undo_depth(app) == before, "the refusal must not push a command"

    def test_deleting_a_generated_task_is_refused_by_name(self, app: Any) -> None:
        from open_garden_planner.services.task_generator import make_calendar_task_id

        generated_id = make_calendar_task_id("solanum_lycopersicum", "direct_sow", 2026)
        before = _undo_depth(app)
        with pytest.raises(ValueError, match="derived from the plan"):
            app._agent_delete_manual_task(generated_id)
        assert _undo_depth(app) == before

    def test_deleting_an_unknown_task_is_refused(self, app: Any) -> None:
        before = _undo_depth(app)
        with pytest.raises(ValueError, match="No manual task"):
            app._agent_delete_manual_task("11111111-1111-1111-1111-111111111111")
        assert _undo_depth(app) == before

    def test_redo_restores_a_deleted_task(self, app: Any) -> None:
        """add -> delete -> undo -> redo walks the stack both ways."""
        created = app._agent_add_manual_task(title="Order seed")
        app._agent_delete_manual_task(created["task_id"])
        assert created["task_id"] not in app._project_manager.manual_tasks

        app._agent_undo()
        assert created["task_id"] in app._project_manager.manual_tasks, (
            "undoing the delete must bring the task back"
        )
        assert _redo_depth(app) == 1

        app._agent_redo()
        assert created["task_id"] not in app._project_manager.manual_tasks, (
            "redoing the delete must remove it again"
        )
        assert _redo_depth(app) == 0


# ══════════════════════════════════════════════════════════════════════════════
# US-D3.4 — soil reads
# ══════════════════════════════════════════════════════════════════════════════


class TestSoilReads:
    def test_untested_bed_is_never_reported_as_fine(self, app: Any, bed_id: str) -> None:
        result = app._agent_get_soil_status(bed_id=bed_id, today=TODAY)
        beds = result["beds"]
        assert len(beds) == 1
        assert beds[0]["coverage"] == "no_soil_test"
        assert beds[0]["record_source"] == "none"
        assert beds[0]["overall_health_level"] == "unknown"
        assert beds[0]["levels"] == {}

    def test_global_default_is_labelled_as_the_default(self, app: Any, bed_id: str) -> None:
        """A plan-wide reading must never look like this bed's own."""
        app._agent_record_soil_test(
            bed_id=None, ph=6.5, n_level=3, p_level=3, k_level=3
        )
        status = app._agent_get_soil_status(bed_id=bed_id, today=TODAY)["beds"][0]
        assert status["record_source"] == "global"
        assert status["coverage"] == "ok"
        assert status["ph"] == 6.5

    def test_bed_record_reports_its_own_source(
        self, app: Any, bed_id: str
    ) -> None:
        app._agent_record_soil_test(bed_id=bed_id, ph=6.5, n_level=3)
        status = app._agent_get_soil_status(bed_id=bed_id, today=TODAY)["beds"][0]
        assert status["record_source"] == "bed"
        assert status["levels"]["n"]["health_level"] == "good"

    def test_secondary_has_no_health_rating(
        self, app: Any, bed_id: str
    ) -> None:
        """The engine rates pH and N/P/K only; Ca/Mg/S must not borrow a rating."""
        app._agent_record_soil_test(bed_id=bed_id, ph=6.5, ca_level=0)
        levels = app._agent_get_soil_status(bed_id=bed_id, today=TODAY)["beds"][0]["levels"]
        assert levels["ca"]["level"] == 0
        assert levels["ca"]["health_level"] is None

    def test_trellis_is_refused_for_soil(self, app: Any, trellis_id: str) -> None:
        with pytest.raises(ValueError):
            app._agent_get_soil_status(bed_id=trellis_id, today=TODAY)

    def test_recommendations_are_empty_but_labelled_when_untested(
        self, app: Any, bed_id: str
    ) -> None:
        result = app._agent_recommend_amendments(bed_id=bed_id, today=TODAY)
        assert result["coverage"] == "no_soil_test"
        assert result["recommendations"] == []

    def test_recommendations_appear_once_a_test_exists(
        self, app: Any, bed_id: str
    ) -> None:
        app._agent_record_soil_test(bed_id=bed_id, ph=5.0, n_level=0, k_level=1)
        result = app._agent_recommend_amendments(bed_id=bed_id, today=TODAY)
        assert result["coverage"] == "ok"
        assert result["total"] > 0, "acidic, N-depleted soil must produce advice"
        for rec in result["recommendations"]:
            assert rec["amendment_id"], "a stable machine key is required"
            assert rec["display_name"], "and a display name beside it"

    def test_mismatches_agree_with_the_diagnostics_flags(
        self, app: Any, bed_id: str
    ) -> None:
        """The agent's disagreements and the user's borders must not diverge."""
        app._agent_record_soil_test(bed_id=bed_id, ph=8.5, n_level=3, k_level=3)
        result = app._agent_get_soil_mismatches(bed_id=bed_id, today=TODAY)
        assert result["beds"][bed_id]["coverage"] == "ok"
        for mismatch in result["beds"][bed_id]["mismatches"]:
            assert len(mismatch["reason_codes"]) == len(mismatch["reasons"])
            assert set(mismatch["reason_codes"]) <= {
                "ph_low", "ph_high",
                "n_high_demand", "p_high_demand", "k_high_demand",
            }

    def test_untested_bed_mismatches_are_labelled(
        self, app: Any, bed_id: str
    ) -> None:
        result = app._agent_get_soil_mismatches(bed_id=bed_id, today=TODAY)
        assert result["beds"][bed_id]["coverage"] == "no_soil_test"


# ══════════════════════════════════════════════════════════════════════════════
# US-D3.4 — record_soil_test: the highest-risk write in the story
# ══════════════════════════════════════════════════════════════════════════════


class TestRecordSoilTest:
    def test_records_and_is_one_undo_step(self, app: Any, bed_id: str) -> None:
        before = _undo_depth(app)
        app._agent_record_soil_test(
            bed_id=bed_id, ph=6.5, n_level=2, p_level=3, k_level=3, ca_level=1
        )
        assert _undo_depth(app) == before + 1
        assert app._project_manager.soil_tests, "the record must be stored"
        assert app._project_manager.is_dirty, "a stored change marks the plan dirty"

        app._agent_undo()
        assert app._project_manager.soil_tests == {}, (
            "one Ctrl+Z must remove the whole record"
        )

    def test_recorded_test_is_visible_to_the_status_read(
        self, app: Any, bed_id: str
    ) -> None:
        app._agent_record_soil_test(bed_id=bed_id, ph=7.9, n_level=1, k_level=1)
        status = app._agent_get_soil_status(bed_id=bed_id, today=TODAY)["beds"][0]
        assert status["coverage"] == "ok"
        assert status["ph"] == 7.9
        assert status["levels"]["n"]["health_level"] == "poor"

    def test_global_target_is_the_plan_wide_default(self, app: Any) -> None:
        app._agent_record_soil_test(bed_id=None, ph=6.8)
        assert app._project_manager.soil_tests, "recorded against the global target"

    def test_future_test_date_is_refused_inertly(self, app: Any, bed_id: str) -> None:
        before = _undo_depth(app)
        future = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
        with pytest.raises(ValueError, match="in the future"):
            app._agent_record_soil_test(bed_id=bed_id, ph=6.5, test_date=future)
        assert _undo_depth(app) == before
        assert app._project_manager.soil_tests == {}

    @pytest.mark.parametrize(
        ("field", "value", "scale_text"),
        [
            ("n_level", 40, "0-4"),
            ("k_level", 0, "1-4"),      # the kit has no K0
            ("ca_level", 7, "0-2"),
        ],
    )
    def test_rapitest_ranges_are_enforced_inertly(
        self, app: Any, bed_id: str, field: str, value: int, scale_text: str
    ) -> None:
        """The single highest-risk input in the story."""
        before = _undo_depth(app)
        with pytest.raises(ValueError) as excinfo:
            app._agent_record_soil_test(bed_id=bed_id, **{field: value})
        message = str(excinfo.value)
        assert "Rapitest" in message
        assert scale_text in message, "the error must state the accepted range"
        assert _undo_depth(app) == before
        assert app._project_manager.soil_tests == {}

    def test_no_readings_is_refused_inertly(self, app: Any, bed_id: str) -> None:
        before = _undo_depth(app)
        with pytest.raises(ValueError, match="no readings"):
            app._agent_record_soil_test(bed_id=bed_id, notes="just a note")
        assert _undo_depth(app) == before
        assert app._project_manager.soil_tests == {}

    def test_trellis_is_refused_inertly(self, app: Any, trellis_id: str) -> None:
        before = _undo_depth(app)
        with pytest.raises(ValueError):
            app._agent_record_soil_test(bed_id=trellis_id, ph=6.5)
        assert _undo_depth(app) == before
        assert app._project_manager.soil_tests == {}

    def test_undo_then_redo_round_trips(self, app: Any, bed_id: str) -> None:
        app._agent_record_soil_test(bed_id=bed_id, ph=6.5, n_level=2)
        app._agent_undo()
        assert app._project_manager.soil_tests == {}
        app._agent_redo()
        assert app._project_manager.soil_tests


# ══════════════════════════════════════════════════════════════════════════════
# The wiring itself — the #291 lesson
# ══════════════════════════════════════════════════════════════════════════════


class TestProviderWiring:
    """Every new provider must be reachable from the bundle the server gets.

    A provider that exists on the class but is missing from the
    ``AgentProviders(...)`` construction would leave the tool permanently dead
    while every other test still passed.
    """

    NEW_PROVIDERS = (
        "get_tasks",
        "get_task_calendar",
        "add_manual_task",
        "edit_manual_task",
        "delete_manual_task",
        "get_soil_status",
        "recommend_amendments",
        "get_soil_mismatches",
        "record_soil_test",
    )

    def test_all_new_providers_are_bound(self, app: Any) -> None:
        import asyncio

        from open_garden_planner.agent_api.server import build_server

        tools = asyncio.run(
            build_server(_bundle(app), write_token=None, writes_enabled=False).list_tools()
        )
        names = {t.name for t in tools}
        gated = {
            "add_manual_task", "edit_manual_task", "delete_manual_task", "record_soil_test",
        }
        missing = set(self.NEW_PROVIDERS) - names - gated
        assert not missing, f"unreachable read tools: {missing}"
        for name in gated:
            assert name not in names, (
                f"{name} must NOT be registered without the ADR-036 double gate"
            )

    def test_write_tools_appear_only_with_the_gate(self, app: Any) -> None:
        import asyncio

        from open_garden_planner.agent_api.server import build_server

        ungated = asyncio.run(
            build_server(_bundle(app), write_token=None, writes_enabled=False).list_tools()
        )
        assert not {"add_manual_task", "record_soil_test"} & {t.name for t in ungated}

        gated = asyncio.run(
            build_server(
                _bundle(app), write_token="t0ken", writes_enabled=True
            ).list_tools()
        )
        gated_names = {t.name for t in gated}
        for name in ("add_manual_task", "edit_manual_task", "delete_manual_task", "record_soil_test"):
            assert name in gated_names, f"{name} missing even with the gate open"

    def test_all_six_prompts_are_registered(self, app: Any) -> None:
        import asyncio

        from open_garden_planner.agent_api.server import build_server

        prompts = asyncio.run(build_server(_bundle(app), write_token=None, writes_enabled=False).list_prompts())
        names = {p.name for p in prompts}
        assert {"plan-my-week", "plan-soil-amendments"} <= names

    def test_plan_my_week_prompt_renders_real_data(self, app: Any) -> None:

        from open_garden_planner.agent_api.mapping import plan_summary_from_snapshot
        from open_garden_planner.agent_api.prompts import render_plan_my_week_prompt
        from open_garden_planner.agent_api.schema import TaskCalendarView, TaskListView

        task_list = TaskListView(**app._agent_get_tasks(today=TODAY))
        calendar = TaskCalendarView(**app._agent_get_task_calendar(today=TODAY))
        summary = plan_summary_from_snapshot(app._agent_snapshot())
        text = render_plan_my_week_prompt(task_list, calendar, summary, [])
        assert TODAY in text
        assert "Produce a prioritised plan" in text

    def test_plan_my_week_says_so_when_location_is_missing(self, app: Any) -> None:
        """The degradation must reach the PROMPT, not just the tool payload."""
        from open_garden_planner.agent_api.mapping import plan_summary_from_snapshot
        from open_garden_planner.agent_api.prompts import render_plan_my_week_prompt
        from open_garden_planner.agent_api.schema import TaskCalendarView, TaskListView

        app._project_manager.set_location({})
        task_list = TaskListView(**app._agent_get_tasks(today=TODAY))
        calendar = TaskCalendarView(**app._agent_get_task_calendar(today=TODAY))
        text = render_plan_my_week_prompt(
            task_list, calendar, plan_summary_from_snapshot(app._agent_snapshot()), []
        )
        assert "no geo-location" in text
        assert "Do not tell the user the week is empty" in text

    def test_soil_prompt_asks_for_a_test_when_untested(
        self, app: Any, bed_id: str
    ) -> None:
        from open_garden_planner.agent_api.domain import (
            _soil_status_from,
            get_soil_mismatches_for_agent,
            recommend_amendments_for_agent,
        )
        from open_garden_planner.agent_api.prompts import (
            render_plan_soil_amendments_prompt,
        )

        status = _soil_status_from(
            bed_id=bed_id,
            bed_name="Bed",
            record=None,
            record_source="none",
            history=None,
            today=datetime.date(2026, 10, 3),
            health_level=app._soil_service.health_level,
            is_test_overdue=app._soil_service.is_test_overdue,
        )
        text = render_plan_soil_amendments_prompt(
            status,
            recommend_amendments_for_agent(
                bed_id=bed_id, record=None, today=datetime.date(2026, 10, 3), recommendations=[]
            ),
            get_soil_mismatches_for_agent(
                bed_id=bed_id, today=datetime.date(2026, 10, 3), details=[]
            ),
            [],
        )
        assert "no soil test" in text
        assert "Do NOT describe the soil as fine" in text


# ══════════════════════════════════════════════════════════════════════════════
# Drift guard for the shared stub module
# ══════════════════════════════════════════════════════════════════════════════


def test_stub_module_covers_exactly_the_new_fields() -> None:
    """The shared stub set must not drift from the dataclass.

    ``AgentProviders`` has no defaults, so a *missing* field raises TypeError at
    construction — that direction is covered for free. This catches the other
    one: a STALE stub name that is no longer a field would otherwise sit in nine
    suites looking load-bearing while meaning nothing.
    """
    from tests.integration.agent_task_soil_stubs import assert_stub_coverage

    assert_stub_coverage()


def _bundle(app: Any):
    """Build the real provider bundle from the running app.

    ``GardenPlannerApp`` assembles its ``AgentProviders`` inline where it starts
    the server, so this reproduces that call with the app's own bound methods.
    A stub bundle would pass the wiring tests without exercising anything.
    """
    from open_garden_planner.agent_api.history import history_from_command_manager
    from open_garden_planner.agent_api.providers import AgentProviders

    cm = app.canvas_view.command_manager
    bridge = app._agent_bridge
    app._agent_frost_alerts = getattr(app, "_agent_frost_alerts", [])

    def _hist() -> dict[str, Any]:
        return history_from_command_manager(cm).model_dump()

    return AgentProviders(
        snapshot=lambda: bridge.run_on_main(
            lambda: app._project_manager.snapshot_dict(app.canvas_scene)
        ),
        diagnostics=lambda: bridge.run_on_main(
            lambda: app._project_manager.diagnostics_snapshot(app.canvas_scene)
        ),
        get_history=lambda: bridge.run_on_main(_hist),
        render=lambda *_a: {},
        save_plan=lambda *_a: {},
        new_plan=lambda *_a: {},
        open_plan=lambda *_a: {},
        export_pdf=lambda *_a: {},
        export_dxf=lambda *_a: {},
        export_csv=lambda *_a: {},
        create_object=lambda *_a, **_k: {},
        get_geometry=lambda *_a: {},
        move_object=lambda *_a: {},
        set_object_position=lambda *_a: {},
        delete_object=lambda *_a: {},
        resize_object=lambda *_a: {},
        rotate_object=lambda *_a: {},
        set_vertex=lambda *_a: {},
        add_vertex=lambda *_a: {},
        delete_vertex=lambda *_a: {},
        set_species=lambda *_a: {},
        set_parent_bed=lambda *_a: {},
        arrange_object=lambda *_a: {},
        set_object_layer=lambda *_a: {},
        create_layer=lambda *_a: {},
        rename_layer=lambda *_a: {},
        delete_layer=lambda *_a: {},
        set_active_layer=lambda *_a: {},
        set_layer_property=lambda *_a: {},
        undo=lambda: bridge.run_on_main(lambda: app._do_agent_undo()),
        redo=lambda: bridge.run_on_main(lambda: app._do_agent_redo()),
        suggest_companions=lambda *_a: [],
        find_compatible_sets=lambda *_a: [],
        find_sets_for_bed=lambda *_a: {},
        check_placement=lambda *_a: {},
        get_succession_plan=lambda *_a: {},
        find_succession_gaps=lambda *_a: [],
        suggest_succession=lambda *_a: [],
        set_succession_plan=lambda *_a: {},
        # The nine under test, bound to the app's REAL methods.
        get_tasks=app._agent_get_tasks,
        get_task_calendar=app._agent_get_task_calendar,
        add_manual_task=app._agent_add_manual_task,
        edit_manual_task=app._agent_edit_manual_task,
        delete_manual_task=app._agent_delete_manual_task,
        get_soil_status=app._agent_get_soil_status,
        recommend_amendments=app._agent_recommend_amendments,
        get_soil_mismatches=app._agent_get_soil_mismatches,
        record_soil_test=app._agent_record_soil_test,
    )
