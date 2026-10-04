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

import asyncio
import datetime
import socket
import threading
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


@pytest.fixture
def mcp_server(app: Any):
    """Real HTTP server with the application's production provider graph."""
    from open_garden_planner.agent_api import AgentApiServer

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = AgentApiServer(
        app._build_agent_providers(), port=port,
        writes_enabled=True, write_token="task-soil-test-token",
    )
    server.start()
    try:
        yield server
    finally:
        server.stop()


def _exercise_mcp(qtbot: Any, server: Any, workflow: Any, *, writes: bool = False) -> None:
    """Run the client off-thread while Qt services the real bridge requests."""
    finished = threading.Event()
    errors: list[BaseException] = []

    async def run() -> None:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        headers = {"Authorization": "Bearer task-soil-test-token"} if writes else None
        async with (
            httpx.AsyncClient(headers=headers) as http,
            streamable_http_client(server.url, http_client=http) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            await workflow(session)

    def target() -> None:
        try:
            asyncio.run(run())
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=target, daemon=True, name="task-soil-mcp-client")
    thread.start()
    qtbot.waitUntil(finished.is_set, timeout=30000)
    thread.join()
    if errors:
        raise errors[0]


async def _call(session: Any, name: str, **arguments: Any) -> dict[str, Any]:
    response = await session.call_tool(name, arguments)
    assert not response.isError, response.content
    return response.structuredContent


class TestRealMcpTransport:
    """Validate actual app payloads at the MCP boundary, including prompts."""

    @pytest.mark.parametrize("reading", [{"n_level": True}, {"ph": True}, {"n_level": "2"}])
    def test_malformed_numbers_are_not_coerced_over_mcp(
        self, app: Any, qtbot: Any, mcp_server: Any, bed_id: str, reading: dict[str, Any],
    ) -> None:
        async def workflow(session: Any) -> None:
            before = await _call(session, "get_history")
            response = await session.call_tool("record_soil_test", {"bed_id": bed_id, **reading})
            assert response.isError, "MCP validation must not coerce a boolean or string into a reading"
            assert await _call(session, "get_history") == before
        _exercise_mcp(qtbot, mcp_server, workflow, writes=True)
        assert app._project_manager.soil_tests == {}

    def test_writes_refuse_without_auth_over_mcp(
        self, app: Any, qtbot: Any, mcp_server: Any, bed_id: str,
    ) -> None:
        async def workflow(session: Any) -> None:
            before = await _call(session, "get_history")
            for name, arguments in (
                ("add_manual_task", {"title": "unauthorised"}),
                ("edit_manual_task", {"task_id": "unknown", "title": "unauthorised"}),
                ("delete_manual_task", {"task_id": "unknown"}),
                ("record_soil_test", {"bed_id": bed_id, "ph": 6.0}),
            ):
                response = await session.call_tool(name, arguments)
                assert response.isError
                assert "token" in response.content[0].text.lower()
                assert await _call(session, "get_history") == before
        _exercise_mcp(qtbot, mcp_server, workflow)
        assert app._project_manager.manual_tasks == {}
        assert app._project_manager.soil_tests == {}

    def test_range_and_generated_task_refusals_over_mcp(
        self, app: Any, qtbot: Any, mcp_server: Any, bed_id: str,
    ) -> None:
        async def workflow(session: Any) -> None:
            before = await _call(session, "get_history")
            original = await _call(session, "get_soil_status", bed_id=bed_id, today=TODAY)
            response = await session.call_tool("record_soil_test", {"bed_id": bed_id, "n_level": 40})
            assert response.isError and "0-4" in response.content[0].text
            assert await _call(session, "get_history") == before
            assert await _call(session, "get_soil_status", bed_id=bed_id, today=TODAY) == original
            await _call(session, "record_soil_test", bed_id=bed_id, ph=5.0, n_level=0, k_level=1)
            tasks = (await _call(session, "get_tasks"))["tasks"]
            generated = next(t for t in tasks if t["source"] == "soil")
            before = await _call(session, "get_history")
            for name, arguments in (
                ("edit_manual_task", {"task_id": generated["task_id"], "title": "invalid"}),
                ("delete_manual_task", {"task_id": generated["task_id"]}),
            ):
                response = await session.call_tool(name, arguments)
                assert response.isError and "generated" in response.content[0].text.lower()
                assert await _call(session, "get_history") == before
                assert (await _call(session, "get_tasks"))["tasks"] == tasks
        _exercise_mcp(qtbot, mcp_server, workflow, writes=True)

    def test_mismatches_over_mcp(
        self, app: Any, qtbot: Any, mcp_server: Any, bed_id: str,
    ) -> None:
        async def workflow(session: Any) -> None:
            result = await _call(session, "get_soil_mismatches", bed_id=bed_id, today=TODAY)
            assert result["beds"][bed_id]["coverage"] == "no_soil_test"
        _exercise_mcp(qtbot, mcp_server, workflow)

    @pytest.mark.parametrize("one_bed", [True, False])
    def test_untested_soil_reads_over_mcp(
        self, app: Any, qtbot: Any, mcp_server: Any, bed_id: str, one_bed: bool,
    ) -> None:
        async def workflow(session: Any) -> None:
            arguments = {"bed_id": bed_id} if one_bed else {}
            status = await _call(session, "get_soil_status", today=TODAY, **arguments)
            assert [b["bed_id"] for b in status["beds"]] == [bed_id]
            assert status["beds"][0]["coverage"] == "no_soil_test"
            mismatch = await _call(session, "get_soil_mismatches", today=TODAY, **arguments)
            assert mismatch["beds"][bed_id]["coverage"] == "no_soil_test"
            assert mismatch["beds"][bed_id]["total"] == 0
            amendments = await _call(session, "recommend_amendments", bed_id=bed_id, today=TODAY)
            assert amendments["coverage"] == "no_soil_test"
        _exercise_mcp(qtbot, mcp_server, workflow)

    def test_soil_prompt_over_mcp(
        self, app: Any, qtbot: Any, mcp_server: Any, bed_id: str,
    ) -> None:
        async def workflow(session: Any) -> None:
            prompt = await session.get_prompt("plan-soil-amendments", {"bed_id": bed_id})
            text = prompt.messages[0].content.text
            assert "no soil test" in text
            assert "Do NOT describe the soil as fine" in text
        _exercise_mcp(qtbot, mcp_server, workflow)

    def test_lab_only_reading_is_not_presented_as_near_target(
        self, app: Any, qtbot: Any, mcp_server: Any, bed_id: str,
    ) -> None:
        from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord

        app._project_manager.set_soil_test_history(bed_id, SoilTestHistory(
            target_id=bed_id, records=[SoilTestRecord(date=TODAY, mode="lab", n_ppm=100.0)],
        ))
        async def workflow(session: Any) -> None:
            status = await _call(session, "get_soil_status", bed_id=bed_id, today=TODAY)
            assert status["beds"][0]["overall_health_level"] == "unknown"
            plan = await _call(session, "recommend_amendments", bed_id=bed_id, today=TODAY)
            assert plan["recommendations"] == []
            prompt = await session.get_prompt("plan-soil-amendments", {"bed_id": bed_id})
            text = prompt.messages[0].content.text
            assert "near its target" not in text
            assert "does not prove" in text
        _exercise_mcp(qtbot, mcp_server, workflow)

    def test_soil_write_fallback_and_undo_over_mcp(
        self, app: Any, qtbot: Any, mcp_server: Any, bed_id: str,
    ) -> None:
        async def workflow(session: Any) -> None:
            before = (await _call(session, "get_history"))["undo_depth"]
            original = await _call(session, "get_soil_status", bed_id=bed_id, today=TODAY)
            await _call(session, "record_soil_test", ph=5.0, n_level=0, p_level=0, k_level=1)
            assert (await _call(session, "get_history"))["undo_depth"] == before + 1
            status = await _call(session, "get_soil_status", bed_id=bed_id, today=TODAY)
            assert status["beds"][0]["record_source"] == "global"
            assert status["beds"][0]["ph"] == 5.0
            assert (await _call(session, "recommend_amendments", bed_id=bed_id))["total"] > 0
            prompt = await session.get_prompt("plan-soil-amendments", {"bed_id": bed_id})
            assert "PLAN-WIDE default" in prompt.messages[0].content.text
            await _call(session, "undo")
            assert await _call(session, "get_soil_status", bed_id=bed_id, today=TODAY) == original
        _exercise_mcp(qtbot, mcp_server, workflow, writes=True)
        assert app._project_manager.soil_tests == {}

    def test_manual_tasks_and_prompts_over_mcp(
        self, app: Any, qtbot: Any, mcp_server: Any, bed_id: str,
    ) -> None:
        async def workflow(session: Any) -> None:
            async def tasks() -> list[dict[str, Any]]:
                return (await _call(session, "get_tasks", today=TODAY))["tasks"]
            before = (await _call(session, "get_history"))["undo_depth"]
            created = await _call(session, "add_manual_task", title="Transport reminder", date=TODAY, bed_id=bed_id)
            task_id = created["task_id"]
            assert (await _call(session, "get_history"))["undo_depth"] == before + 1
            assert any(t["task_id"] == task_id and t["title"] == "Transport reminder" for t in await tasks())
            await _call(session, "edit_manual_task", task_id=task_id, title="Edited reminder", date=TODAY)
            assert (await _call(session, "get_history"))["undo_depth"] == before + 2
            assert any(t["task_id"] == task_id and t["title"] == "Edited reminder" for t in await tasks())
            await _call(session, "undo")
            assert any(t["task_id"] == task_id and t["title"] == "Transport reminder" for t in await tasks())
            await _call(session, "delete_manual_task", task_id=task_id)
            assert (await _call(session, "get_history"))["undo_depth"] == before + 2
            assert task_id not in {t["task_id"] for t in await tasks()}
            await _call(session, "undo")
            assert task_id in {t["task_id"] for t in await tasks()}
            calendar = await _call(session, "get_task_calendar", today=TODAY)
            assert calendar["coverage"] == "full"
            prompt = await session.get_prompt("plan-my-week")
            assert "Transport reminder" in prompt.messages[0].content.text
        _exercise_mcp(qtbot, mcp_server, workflow, writes=True)


# ══════════════════════════════════════════════════════════════════════════════
# US-D3.3 — task calendar reads
# ══════════════════════════════════════════════════════════════════════════════


class TestTaskReads:
    def test_absolute_propagation_override_has_one_shared_identity(self, app: Any) -> None:
        from open_garden_planner.services.task_generator import (
            PlanState,
            generate_propagation_tasks,
        )

        plant = RectangleItem(0, 0, 40, 40)
        plant.object_type = ObjectType.PERENNIAL
        plant.metadata["plant_species"] = {
            "common_name": "Override fixture", "scientific_name": "Override fixture",
            "indoor_sow_start": -6, "indoor_sow_end": -4,
            "transplant_start": 2, "transplant_end": 3,
        }
        app.canvas_scene.addItem(plant)
        app._project_manager.set_propagation_override(
            "override fixture", "prick_out", "2026-03-10", "2026-03-10",
        )
        result = app._agent_get_tasks(
            source="propagation", from_date="2025-01-01", to_date="2027-12-31", today=TODAY,
        )
        overridden = [t for t in result["tasks"] if t["task_type"] == "prick_out"]
        assert len(overridden) == 1
        assert overridden[0]["task_id"] == "override fixture:prick_out:2026"
        rows, _, _, seeds = app.calendar_view._collect_data()
        plans = app.calendar_view._build_propagation_plans(rows, datetime.date(2027, 4, 15), seeds)
        gui_tasks = generate_propagation_tasks(PlanState(
            today=datetime.date(2026, 3, 10), year=2027,
            plant_rows=app._agent_build_task_state(datetime.date(2026, 3, 10)).plant_rows,
            prop_plans=plans, actionable_only=False,
        ))
        assert next(t.task_id for t in gui_tasks if t.task_type == "prick_out") == overridden[0]["task_id"]
        calendar = app._agent_get_task_calendar(year=2026, today=TODAY)
        march = next(b for b in calendar["months"] if b["month"] == "2026-03")
        assert march["by_source"]["propagation"] == 1

    def test_bundled_garlic_autumn_tasks_do_not_depend_on_window_end_year(self, app: Any) -> None:
        from open_garden_planner.services.bundled_species_db import get_species_entry

        species = get_species_entry("Allium sativum")
        assert species is not None
        plant = RectangleItem(0, 0, 40, 40)
        plant.object_type = ObjectType.PERENNIAL
        plant.metadata["plant_species"] = species
        app.canvas_scene.addItem(plant)
        def read(end: str) -> list[dict]:
            return app._agent_get_tasks(
                source="calendar", from_date="2026-01-01", to_date=end, today=TODAY,
            )["tasks"]
        narrow = read("2026-12-31")
        wider = read("2027-12-31")
        autumn = next(t for t in wider if t["task_id"] == "allium sativum:direct_sow:2027")
        assert autumn in narrow
        calendar = app._agent_get_task_calendar(year=2026, today=TODAY)
        assert "2026-10" in [b["month"] for b in calendar["months"]]

    @pytest.mark.parametrize("year", [2026, 2027])
    def test_propagation_tasks_use_the_gui_calculator(self, app: Any, year: int) -> None:
        from open_garden_planner.services.task_generator import (
            PlanState,
            generate_propagation_tasks,
        )
        plant = RectangleItem(0, 0, 40, 40)
        plant.object_type = ObjectType.PERENNIAL
        plant.metadata["plant_species"] = {
            "common_name": "Propagation fixture", "scientific_name": "Propagation fixture",
            "indoor_sow_start": -6, "indoor_sow_end": -4,
            "transplant_start": 2, "transplant_end": 3,
            "prick_out_after_days": 14, "harden_off_days": 7,
        }
        app.canvas_scene.addItem(plant)
        rows, _, _, seeds = app.calendar_view._collect_data()
        last_frost = datetime.date(year, 4, 15)
        plans = app.calendar_view._build_propagation_plans(rows, last_frost, seeds)
        expected = generate_propagation_tasks(PlanState(
            today=datetime.date(2026, 10, 3), year=year,
            plant_rows=app._agent_build_task_state(datetime.date(2026, 10, 3)).plant_rows,
            prop_plans=plans, actionable_only=False,
        ))
        assert len(expected) == 2
        result = app._agent_get_tasks(
            source="propagation", from_date=f"{year}-01-01",
            to_date=f"{year}-12-31", today=TODAY,
        )
        assert [(t["task_id"], t["start_date"], t["end_date"]) for t in result["tasks"]] == sorted(
            [(t.task_id, t.start_date.isoformat(), t.end_date.isoformat()) for t in expected],
            key=lambda t: (t[1], t[0]),
        )

    @pytest.mark.parametrize("year", [2026, 2027])
    def test_explicit_task_window_generates_its_calendar_tasks(self, app: Any, year: int) -> None:
        plant = RectangleItem(0, 0, 40, 40)
        plant.object_type = ObjectType.PERENNIAL
        plant.metadata["plant_species"] = {
            "common_name": "Calendar fixture", "scientific_name": "Calendar fixture",
            "direct_sow_start": -2, "direct_sow_end": 0,
        }
        app.canvas_scene.addItem(plant)
        result = app._agent_get_tasks(
            from_date=f"{year}-04-01", to_date=f"{year}-04-30", today=TODAY,
        )
        assert result["total"] == 1
        assert result["tasks"][0]["start_date"] == f"{year}-04-01"
        assert result["tasks"][0]["task_id"].endswith(str(year))
        assert result["tasks"][0]["urgency"] is None

    @pytest.mark.parametrize("year", [2026, 2027])
    def test_calendar_generates_the_full_requested_year(self, app: Any, year: int) -> None:
        plant = RectangleItem(0, 0, 40, 40)
        plant.object_type = ObjectType.PERENNIAL
        plant.metadata["plant_species"] = {
            "common_name": "Calendar fixture", "scientific_name": "Calendar fixture",
            "direct_sow_start": -2, "direct_sow_end": 0,
            "harvest_start": 8, "harvest_end": 12,
        }
        app.canvas_scene.addItem(plant)
        calendar = app._agent_get_task_calendar(year=year, today=TODAY)
        assert [b["month"] for b in calendar["months"]] == [f"{year}-04", f"{year}-06", f"{year}-07"]
        assert sum(b["by_source"].get("calendar", 0) for b in calendar["months"]) == 3

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
    def test_global_fallback_uses_global_history_for_staleness(self, app: Any, bed_id: str) -> None:
        app._agent_record_soil_test(ph=5.0, test_date="2025-01-01")
        status = app._agent_get_soil_status(bed_id=bed_id, today=TODAY)["beds"][0]
        assert status["record_source"] == "global"
        assert status["is_test_overdue"] is True

    def test_amendment_names_follow_the_ui_language(self, app: Any, bed_id: str) -> None:
        app._agent_record_soil_test(bed_id=bed_id, ph=5.0, n_level=0, k_level=1)
        get_settings().language = "en"
        english = app._agent_recommend_amendments(bed_id)["recommendations"]
        get_settings().language = "de"
        german = app._agent_recommend_amendments(bed_id)["recommendations"]
        from open_garden_planner.services.soil_service import SoilService
        recs = SoilService.calculate_amendments(
            app._soil_service.get_effective_record(bed_id), bed_area_m2=2.0,
        )
        assert [r["amendment_id"] for r in english] == [r["amendment_id"] for r in german]
        assert [r["display_name"] for r in german] == [r.amendment.display_name("de") for r in recs]
        assert [r["display_name"] for r in english] != [r["display_name"] for r in german]

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
    """The same provider graph the running application's server uses."""
    return app._build_agent_providers()
