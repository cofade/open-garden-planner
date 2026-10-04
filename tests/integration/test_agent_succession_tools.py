"""Integration test for the US-D3.2 succession agent tools (issue #331).

Boots the Agent API server in-process on an ephemeral port and drives it with
the real MCP streamable-HTTP client.

The write tool is wired to the REAL ``SetSuccessionPlanCommand`` on a REAL
``ProjectManager`` and ``CommandManager`` — not a stub. D3.2 is the first agent
write into ``ProjectData`` rather than the scene graph, so the properties worth
proving are "exactly one undo step", "the refusal path touches nothing", and
"undo restores the previous plan exactly". A stubbed provider would pass all
three assertions vacuously.
"""

from __future__ import annotations

import asyncio
import datetime
import socket
import threading
import uuid
from typing import Any

from open_garden_planner.agent_api import (
    AgentApiServer,
    AgentProviders,
    MainThreadBridge,
)
from open_garden_planner.agent_api.domain import (
    SuccessionPlanError,
    build_succession_plan_for_agent,
    find_succession_gaps_for_agent,
    get_succession_plan_for_agent,
    suggest_succession_for_agent,
)
from open_garden_planner.agent_api.history import history_from_command_manager
from open_garden_planner.agent_api.schema import WriteResult
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import CommandManager, SetSuccessionPlanCommand
from open_garden_planner.core.object_types import ObjectType, is_bed_type
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.services.bundled_species_db import get_species_db, lookup_species
from open_garden_planner.ui.canvas.items import RectangleItem

LOCATION: dict[str, Any] = {
    "latitude": 52.5,
    "longitude": 13.4,
    "frost_dates": {
        "last_spring_frost": "04-15",
        "first_fall_frost": "10-15",
        "hardiness_zone": "7a",
    },
}
TODAY = datetime.date(2026, 6, 15)


from tests.integration.agent_task_soil_stubs import TASK_SOIL_STUBS


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port: int = sock.getsockname()[1]
    sock.close()
    return port


def _pump(qtbot: Any, coro: Any) -> None:
    """Run `coro` on a worker thread while the Qt loop keeps running.

    Required because every provider hops through ``MainThreadBridge.run_on_main``,
    which blocks until the MAIN thread services the queued call — so the client
    cannot share the main thread with the loop pump.
    """
    loop = asyncio.new_event_loop()
    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["value"] = loop.run_until_complete(coro)
        except Exception as exc:  # noqa: BLE001 - re-raised on the main thread
            box["error"] = exc
        finally:
            loop.close()

    thread = threading.Thread(target=_run, name="mcp-test-client")
    thread.start()
    while thread.is_alive():
        qtbot.wait(10)
    thread.join()
    if "error" in box:
        raise box["error"]


def _http_client() -> Any:
    try:
        from mcp.client.streamable_http import streamable_http_client
    except ImportError:
        from mcp.client.streamable_http import streamablehttp_client as streamable_http_client
    return streamable_http_client


class SuccessionHarness:
    """Real ProjectManager + CommandManager behind real succession providers."""

    def __init__(self) -> None:
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        self.bridge = MainThreadBridge()
        self.scene = CanvasScene()

        self.bed = RectangleItem(0, 0, 200, 100)
        self.bed.object_type = ObjectType.RAISED_BED
        self.scene.addItem(self.bed)
        self.bed_id = str(self.bed.item_id)

        # A TRELLIS is a plant parent but holds no soil (ADR-031's whole reason for
        # two predicates). Succession planning is a soil-container feature, so the
        # tools must refuse it - `is_plant_parent_type` (which check_placement uses)
        # would have accepted it.
        self.trellis = RectangleItem(500, 0, 200, 100)
        self.trellis.object_type = ObjectType.TRELLIS
        self.scene.addItem(self.trellis)
        self.trellis_id = str(self.trellis.item_id)

        self.pm = ProjectManager()
        self.pm.set_location(LOCATION)
        self.cm = CommandManager()
        self.providers = self._build_providers()

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _known_species_keys() -> set[str]:
        keys: set[str] = set()
        for record in get_species_db().values():
            key = species_key(record)
            if key and key != "_unknown":
                keys.add(key)
        return keys

    @staticmethod
    def _records(names: list[str] | None) -> list[dict]:
        out: list[dict] = []
        for name in names or []:
            found = lookup_species(str(name))
            if found is not None:
                out.append(dict(found))
        return out

    def _resolve_soil_bed(self, bed_id: str) -> None:
        try:
            target = uuid.UUID(bed_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError(f"{bed_id!r} is not a valid bed id") from None
        item = self.scene.find_item_by_id(target)
        if item is None:
            raise ValueError(f"No object with id {bed_id!r} in this plan")
        if not is_bed_type(getattr(item, "object_type", None)):
            raise ValueError(
                f"{bed_id!r} is a {getattr(item, 'object_type', None)} - "
                "succession planning needs a soil-capable bed"
            )

    @staticmethod
    def _parse_today(today: str | None) -> datetime.date:
        if not today:
            return datetime.date.today()
        return datetime.date.fromisoformat(today)

    def _undo_depth(self) -> int:
        return history_from_command_manager(self.cm).undo_depth

    # -- the real write body --------------------------------------------

    def _write(
        self,
        bed_id: str,
        entries: list[dict] | None,
        year: int | None,
    ) -> dict[str, Any]:
        """Mirror ``_open_succession_plan_dialog``: ONE undoable command."""
        self._resolve_soil_bed(bed_id)
        resolved_year = year or datetime.date.today().year
        plan = build_succession_plan_for_agent(
            entries,
            bed_id,
            resolved_year,
            known_species_keys=self._known_species_keys(),
        )
        self.cm.execute(SetSuccessionPlanCommand(self.pm, bed_id, plan))
        return WriteResult(
            action="set_succession_plan",
            undo_description=(
                "Delete succession plan"
                if plan is None
                else f"Set succession plan ({len(plan.entries)} entries)"
            ),
        ).model_dump()

    def _build_providers(self) -> AgentProviders:
        bridge = self.bridge
        pm = self.pm
        scene = self.scene
        cm = self.cm

        return AgentProviders(
            snapshot=lambda: bridge.run_on_main(lambda: pm.snapshot_dict(scene)),
            diagnostics=lambda: bridge.run_on_main(lambda: pm.diagnostics_snapshot(scene)),
            render=lambda region, layers, width_px: bridge.run_on_main(lambda: {}),
            save_plan=lambda file_path: bridge.run_on_main(lambda: {}),
            new_plan=lambda *a: {},
            open_plan=lambda *a: {},
            export_pdf=lambda *a: bridge.run_on_main(lambda: {}),
            export_dxf=lambda *a: bridge.run_on_main(lambda: {}),
            export_csv=lambda *a: bridge.run_on_main(lambda: {}),
            create_object=lambda **kw: {},
            get_geometry=lambda item_id: {},
            move_object=lambda *a: {},
            set_object_position=lambda *a: {},
            delete_object=lambda *a: {},
            resize_object=lambda *a: {},
            rotate_object=lambda *a: {},
            set_vertex=lambda *a: {},
            add_vertex=lambda *a: {},
            delete_vertex=lambda *a: {},
            set_species=lambda *a: {},
            set_parent_bed=lambda *a: {},
            arrange_object=lambda *a: {},
            set_object_layer=lambda *a: {},
            create_layer=lambda *a: {},
            rename_layer=lambda *a: {},
            delete_layer=lambda *a: {},
            set_active_layer=lambda *a: {},
            set_layer_property=lambda *a: {},
            undo=lambda: bridge.run_on_main(lambda: {}),
            redo=lambda: bridge.run_on_main(lambda: {}),
            **TASK_SOIL_STUBS,
            get_history=lambda: bridge.run_on_main(
                lambda: history_from_command_manager(cm).model_dump()
            ),
            suggest_companions=lambda *a: [],
            find_compatible_sets=lambda *a: [],
            find_sets_for_bed=lambda *a: {},
            check_placement=lambda *a: {},
            get_succession_plan=lambda bed_id, year=None, today=None: bridge.run_on_main(
                lambda: self.get_plan(bed_id, year, today)
            ),
            find_succession_gaps=lambda bed_id, year=None, today=None: bridge.run_on_main(
                lambda: self.gaps(bed_id, year, today)
            ),
            suggest_succession=(
                lambda bed_id, gap_start, gap_end, candidates=None: bridge.run_on_main(
                    lambda: self.suggest(bed_id, gap_start, gap_end, candidates)
                )
            ),
            set_succession_plan=lambda bed_id, entries, year=None: bridge.run_on_main(
                lambda: self._write(bed_id, entries, year)
            ),
        )

    def get_plan(self, bed_id: str, year: int | None, today: str | None) -> dict[str, Any]:
        self._resolve_soil_bed(bed_id)
        return get_succession_plan_for_agent(
            self.pm.succession_plans.get(bed_id),
            bed_id,
            year=year,
            today=self._parse_today(today),
            location=self.pm.location,
        ).model_dump()

    def gaps(self, bed_id: str, year: int | None, today: str | None) -> list[dict]:
        self._resolve_soil_bed(bed_id)
        return [
            g.model_dump()
            for g in find_succession_gaps_for_agent(
                self.pm.succession_plans.get(bed_id),
                year=year,
                today=self._parse_today(today),
                location=self.pm.location,
            )
        ]

    def suggest(
        self,
        bed_id: str,
        gap_start: str,
        gap_end: str,
        candidates: list[str] | None,
    ) -> list[dict[str, Any]]:
        self._resolve_soil_bed(bed_id)
        plan_raw = self.pm.succession_plans.get(bed_id) or {}
        within = self._families_before(plan_raw, gap_start)
        neighbours = [e.get("species_key", "") for e in plan_raw.get("entries", [])]
        return [
            s.model_dump()
            for s in suggest_succession_for_agent(
                candidates=self._records(candidates),
                gap_start=gap_start,
                gap_end=gap_end,
                within_plan_families=within,
                neighbour_keys=neighbours,
            )
        ]

    @staticmethod
    def _families_before(plan_raw: dict, gap_start: str) -> list[str]:
        from open_garden_planner.agent_api.domain import _parse_iso

        start = _parse_iso(gap_start)
        families: list[str] = []
        for entry in plan_raw.get("entries", []):
            entry_start = _parse_iso(str(entry.get("start_date", "")))
            if start is None or entry_start is None or entry_start >= start:
                continue
            found = lookup_species(entry.get("common_name") or entry.get("species_key") or "")
            if found is not None and found.get("family"):
                families.append(str(found["family"]))
        return families


class TestSuccessionReadTools:
    """Reads over the real MCP transport."""

    def test_get_succession_plan_over_mcp(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        h._write(
            h.bed_id,
            [
                {
                    "species_key": "lactuca sativa",
                    "common_name": "Lettuce",
                    "start_date": "2026-08-01",
                    "end_date": "2026-09-01",
                },
                {
                    "species_key": "phaseolus vulgaris",
                    "common_name": "Bean (Bush)",
                    "start_date": "2026-06-01",
                    "end_date": "2026-07-15",
                },
            ],
            2026,
        )
        server = AgentApiServer(h.providers, port=_free_port())
        server.start()
        out: dict[str, Any] = {}

        async def run() -> None:
            from mcp import ClientSession

            async with (
                _http_client()(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool(
                    "get_succession_plan",
                    {"bed_id": h.bed_id, "today": "2026-06-20"},
                )
                out["isError"] = call.isError
                out["data"] = call.structuredContent

        try:
            _pump(qtbot, run())
        finally:
            server.stop()

        assert not out.get("isError"), out.get("data")
        data = out["data"]
        if isinstance(data, dict) and set(data.keys()) == {"result"}:
            data = data["result"]
        assert data["has_plan"] is True
        assert [e["species_key"] for e in data["entries"]] == [
            "phaseolus vulgaris",
            "lactuca sativa",
        ]
        assert data["current_entry"]["species_key"] == "phaseolus vulgaris"
        assert data["next_entry"]["species_key"] == "lactuca sativa"
        assert data["reference_date"] == "2026-06-20"
        assert data["coverage"] == "full"
        assert data["segments_are_fallback"] is False
        assert [s["segment"] for s in data["segments"]] == [
            "early_spring",
            "late_spring",
            "summer",
            "fall",
        ]

    def test_find_succession_gaps_over_mcp(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        server = AgentApiServer(h.providers, port=_free_port())
        server.start()
        out: dict[str, Any] = {}

        async def run() -> None:
            from mcp import ClientSession

            async with (
                _http_client()(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool(
                    "find_succession_gaps", {"bed_id": h.bed_id, "year": 2026}
                )
                out["isError"] = call.isError
                out["data"] = call.structuredContent

        try:
            _pump(qtbot, run())
        finally:
            server.stop()

        assert not out.get("isError"), out.get("data")
        data = out["data"]
        if isinstance(data, dict) and set(data.keys()) == {"result"}:
            data = data["result"]
        assert [g["segment"] for g in data] == [
            "early_spring",
            "late_spring",
            "summer",
            "fall",
        ]
        assert all(g["days"] > 0 for g in data)

    def test_no_location_reports_the_marker_over_mcp(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        h.pm.set_location({})
        server = AgentApiServer(h.providers, port=_free_port())
        server.start()
        out: dict[str, Any] = {}

        async def run() -> None:
            from mcp import ClientSession

            async with (
                _http_client()(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool(
                    "get_succession_plan", {"bed_id": h.bed_id}
                )
                out["data"] = call.structuredContent

        try:
            _pump(qtbot, run())
        finally:
            server.stop()

        data = out["data"]
        assert data["coverage"] == "no_frost_dates"
        assert data["segments_are_fallback"] is True
        # The marker arrives WITH fallback segments, not instead of them.
        assert len(data["segments"]) == 4

    def test_a_trellis_is_refused_by_the_read_tools(self, qtbot: Any) -> None:
        """A plant-parent that holds no soil is not a succession bed."""
        h = SuccessionHarness()
        server = AgentApiServer(h.providers, port=_free_port())
        server.start()
        out: dict[str, Any] = {}

        async def run() -> None:
            from mcp import ClientSession

            async with (
                _http_client()(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool(
                    "get_succession_plan", {"bed_id": h.trellis_id}
                )
                out["isError"] = call.isError
                out["text"] = call.content[0].text if call.content else ""

        try:
            _pump(qtbot, run())
        finally:
            server.stop()

        assert out.get("isError")
        assert "soil-capable" in out.get("text", "")

    def test_unknown_bed_is_refused_not_reported_empty(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        server = AgentApiServer(h.providers, port=_free_port())
        server.start()
        out: dict[str, Any] = {}

        async def run() -> None:
            from mcp import ClientSession

            async with (
                _http_client()(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool(
                    "get_succession_plan", {"bed_id": str(uuid.uuid4())}
                )
                out["isError"] = call.isError

        try:
            _pump(qtbot, run())
        finally:
            server.stop()

        assert out.get("isError")


class TestSetSuccessionPlan:
    """The token-gated write: undo steps, refusals, exact restoration."""

    def _token_server(self, h: SuccessionHarness) -> AgentApiServer:
        return AgentApiServer(
            h.providers, port=_free_port(), writes_enabled=True, write_token="tok"
        )

    @staticmethod
    def _url(server: AgentApiServer) -> str:
        return f"{server.url}?token=tok"

    def _call(self, qtbot: Any, h: SuccessionHarness, name: str, args: dict) -> dict:
        server = self._token_server(h)
        server.start()
        out: dict[str, Any] = {}

        async def run() -> None:
            from mcp import ClientSession

            async with (
                _http_client()(self._url(server)) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool(name, args)
                out["isError"] = call.isError
                out["data"] = call.structuredContent
                out["text"] = call.content[0].text if call.content else ""

        try:
            _pump(qtbot, run())
        finally:
            server.stop()
        return out

    def test_write_then_undo_is_exactly_one_step(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        before_depth = h._undo_depth()
        out = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {
                "bed_id": h.bed_id,
                "year": 2026,
                "entries": [
                    {
                        "species_key": "phaseolus vulgaris",
                        "common_name": "Bean (Bush)",
                        "start_date": "2026-06-01",
                        "end_date": "2026-07-15",
                    }
                ],
            },
        )
        assert not out["isError"], out["text"]
        assert h.pm.succession_plans[h.bed_id]["entries"][0]["species_key"] == "phaseolus vulgaris"
        assert h._undo_depth() == before_depth + 1

        h.cm.undo()
        assert h.bed_id not in h.pm.succession_plans
        assert h._undo_depth() == before_depth

    def test_undo_restores_the_previous_plan_exactly(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        original = {
            "bed_id": h.bed_id,
            "year": 2026,
            "entries": [
                {
                    "id": "keep-me",
                    "species_key": "phaseolus vulgaris",
                    "common_name": "Bean (Bush)",
                    "start_date": "2026-06-01",
                    "end_date": "2026-07-15",
                }
            ],
        }
        h.pm.set_succession_plan(h.bed_id, original)
        snapshot = dict(h.pm.succession_plans[h.bed_id])

        out = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {
                "bed_id": h.bed_id,
                "year": 2026,
                "entries": [
                    {
                        "species_key": "lactuca sativa",
                        "common_name": "Lettuce",
                        "start_date": "2026-08-01",
                        "end_date": "2026-09-01",
                    }
                ],
            },
        )
        assert not out["isError"], out["text"]
        assert h.pm.succession_plans[h.bed_id]["entries"][0]["species_key"] == "lactuca sativa"

        h.cm.undo()
        assert h.pm.succession_plans[h.bed_id] == snapshot

    def test_empty_entries_deletes_in_one_step(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        h.pm.set_succession_plan(
            h.bed_id,
            {
                "bed_id": h.bed_id,
                "year": 2026,
                "entries": [
                    {
                        "id": "x",
                        "species_key": "phaseolus vulgaris",
                        "common_name": "Bean (Bush)",
                        "start_date": "2026-06-01",
                        "end_date": "2026-07-15",
                    }
                ],
            },
        )
        before_depth = h._undo_depth()
        out = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {"bed_id": h.bed_id, "year": 2026, "entries": []},
        )
        assert not out["isError"], out["text"]
        assert h.bed_id not in h.pm.succession_plans
        assert h._undo_depth() == before_depth + 1
        h.cm.undo()
        assert h.bed_id in h.pm.succession_plans

    def test_the_write_marks_the_project_dirty(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        depth_before = h.cm.undo_depth
        out = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {
                "bed_id": h.bed_id,
                "year": 2026,
                "entries": [
                    {
                        "species_key": "phaseolus vulgaris",
                        "common_name": "Bean (Bush)",
                        "start_date": "2026-06-01",
                        "end_date": "2026-07-15",
                    }
                ],
            },
        )
        assert not out["isError"], out["text"]
        # CommandManager.execute emits stack_changed, which is what marks dirty.
        assert h.cm.undo_depth > depth_before

    # -- refusals: nothing touched --------------------------------------

    def _assert_refused_cleanly(
        self,
        h: SuccessionHarness,
        out: dict,
        expect: str,
    ) -> None:
        assert out["isError"], "expected a refusal"
        assert expect.lower() in out["text"].lower(), out["text"]

    def test_overlapping_slots_are_refused_and_touch_nothing(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        out = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {
                "bed_id": h.bed_id,
                "year": 2026,
                "entries": [
                    {
                        "species_key": "phaseolus vulgaris",
                        "common_name": "Bean (Bush)",
                        "start_date": "2026-06-01",
                        "end_date": "2026-07-15",
                    },
                    {
                        "species_key": "lactuca sativa",
                        "common_name": "Lettuce",
                        "start_date": "2026-07-01",
                        "end_date": "2026-08-01",
                    },
                ],
            },
        )
        self._assert_refused_cleanly(h, out, "overlap")
        assert h.pm.succession_plans == {}
        assert h._undo_depth() == 0

    def test_bad_date_is_refused_and_touches_nothing(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        out = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {
                "bed_id": h.bed_id,
                "year": 2026,
                "entries": [
                    {
                        "species_key": "phaseolus vulgaris",
                        "common_name": "Bean (Bush)",
                        "start_date": "01/06/2026",
                        "end_date": "2026-07-15",
                    }
                ],
            },
        )
        self._assert_refused_cleanly(h, out, "non-ISO")
        assert h.pm.succession_plans == {}
        assert h._undo_depth() == 0

    def test_unknown_species_is_refused(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        out = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {
                "bed_id": h.bed_id,
                "year": 2026,
                "entries": [
                    {
                        "species_key": "definitely-not-a-species",
                        "common_name": "Unicorn",
                        "start_date": "2026-06-01",
                        "end_date": "2026-07-15",
                    }
                ],
            },
        )
        self._assert_refused_cleanly(h, out, "Unknown species_key")
        assert h.pm.succession_plans == {}
        assert h._undo_depth() == 0

    def test_trellis_target_is_refused(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        out = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {
                "bed_id": h.trellis_id,
                "year": 2026,
                "entries": [
                    {
                        "species_key": "phaseolus vulgaris",
                        "common_name": "Bean (Bush)",
                        "start_date": "2026-06-01",
                        "end_date": "2026-07-15",
                    }
                ],
            },
        )
        self._assert_refused_cleanly(h, out, "soil-capable")
        assert h.pm.succession_plans == {}
        assert h._undo_depth() == 0

    def test_refusal_after_a_good_write_preserves_the_good_write(
        self, qtbot: Any
    ) -> None:
        """The important negative: a refusal must not half-apply."""
        h = SuccessionHarness()
        good = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {
                "bed_id": h.bed_id,
                "year": 2026,
                "entries": [
                    {
                        "species_key": "phaseolus vulgaris",
                        "common_name": "Bean (Bush)",
                        "start_date": "2026-06-01",
                        "end_date": "2026-07-15",
                    }
                ],
            },
        )
        assert not good["isError"], good["text"]
        stored = dict(h.pm.succession_plans[h.bed_id])
        depth = h._undo_depth()

        bad = self._call(
            qtbot,
            h,
            "set_succession_plan",
            {
                "bed_id": h.bed_id,
                "year": 2026,
                "entries": [
                    {
                        "species_key": "phaseolus vulgaris",
                        "common_name": "Bean (Bush)",
                        "start_date": "2026-06-01",
                        "end_date": "2026-07-15",
                    },
                    {
                        "species_key": "lactuca sativa",
                        "common_name": "Lettuce",
                        "start_date": "2026-07-01",
                        "end_date": "2026-08-01",
                    },
                ],
            },
        )
        self._assert_refused_cleanly(h, bad, "overlap")
        assert h.pm.succession_plans[h.bed_id] == stored
        assert h._undo_depth() == depth

    def test_the_tool_is_absent_without_writes_enabled(self, qtbot: Any) -> None:
        h = SuccessionHarness()
        server = AgentApiServer(h.providers, port=_free_port())
        server.start()
        out: dict[str, Any] = {}

        async def run() -> None:
            from mcp import ClientSession

            async with (
                _http_client()(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                tools = await session.list_tools()
                out["names"] = {t.name for t in tools.tools}

        try:
            _pump(qtbot, run())
        finally:
            server.stop()

        assert "set_succession_plan" not in out["names"]
        # The read tools are ungated.
        assert {
            "get_succession_plan",
            "find_succession_gaps",
            "suggest_succession",
        } <= out["names"]


class TestValidatorDirectly:
    """The validator's contract, without the transport."""

    def test_omitting_entries_deletes(self) -> None:
        assert build_succession_plan_for_agent(None, "b", 2026) is None

    def test_error_is_a_valueerror_so_the_server_can_translate_it(self) -> None:
        assert issubclass(SuccessionPlanError, ValueError)