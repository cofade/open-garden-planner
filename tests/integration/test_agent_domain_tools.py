"""Integration test for the Agent API domain-intelligence tools (US-D3.1, #319)
and the history tool (US-D2.7, #362).

Boots the Agent API server in-process on an ephemeral port against a real
scene, then drives it with the real MCP streamable-HTTP client.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from typing import Any

from open_garden_planner.agent_api import (
    AgentApiServer,
    AgentProviders,
    MainThreadBridge,
)
from open_garden_planner.agent_api.domain import (
    check_placement_for_agent,
    find_compatible_sets_for_agent,
    suggest_companions_for_agent,
)
from open_garden_planner.agent_api.history import history_from_command_manager
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.companion_sets import find_sets_for_bed
from open_garden_planner.services.companion_planting_service import (
    CompanionPlantingService,
)
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem


from tests.integration.agent_task_soil_stubs import TASK_SOIL_STUBS


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _providers(scene: Any, command_manager: Any) -> AgentProviders:
    bridge = MainThreadBridge()
    project_manager = ProjectManager()
    soil_service = SoilService(project_manager)
    companion_service = CompanionPlantingService()
    return AgentProviders(
        snapshot=lambda: bridge.run_on_main(
            lambda: project_manager.snapshot_dict(scene)
        ),
        diagnostics=lambda: bridge.run_on_main(
            lambda: project_manager.diagnostics_snapshot(scene)
        ),
        render=lambda region, layers, width_px: bridge.run_on_main(
            lambda: {}
        ),
        save_plan=lambda file_path: bridge.run_on_main(lambda: {}),
        new_plan=lambda *_a: {},
        open_plan=lambda *_a: {},
        export_pdf=lambda file_path, paper_size, orientation: bridge.run_on_main(
            lambda: {}
        ),
        export_dxf=lambda file_path: bridge.run_on_main(lambda: {}),
        export_csv=lambda kind, file_path: bridge.run_on_main(lambda: {}),
        create_object=lambda **kw: {},
        get_geometry=lambda item_id: {},
        get_succession_plan=lambda bed_id, year=None, today=None: {},
        find_succession_gaps=lambda bed_id, year=None, today=None: [],
        suggest_succession=lambda *a, **k: [],
        set_succession_plan=lambda *a, **k: {},
        move_object=lambda item_id, dx, dy: {},
        set_object_position=lambda item_id, x, y: {},
        delete_object=lambda item_id: {},
        resize_object=lambda item_id, width, height, radius: {},
        rotate_object=lambda item_id, angle, relative: {},
        set_vertex=lambda item_id, index, x, y: {},
        add_vertex=lambda item_id, index, x, y: {},
        delete_vertex=lambda item_id, index: {},
        set_species=lambda item_id, species, apply_database_size: {},
        set_parent_bed=lambda item_id, bed_id: {},
        arrange_object=lambda item_id, action: {},
        set_object_layer=lambda item_id, layer_id: {},
        create_layer=lambda name: {},
        rename_layer=lambda layer_id, name: {},
        delete_layer=lambda layer_id: {},
        set_active_layer=lambda layer_id: {},
        set_layer_property=lambda layer_id, visible, opacity, locked: {},
        undo=lambda: bridge.run_on_main(lambda: {}),
        redo=lambda: bridge.run_on_main(lambda: {}),
        **TASK_SOIL_STUBS,
        get_history=lambda: bridge.run_on_main(
            lambda: history_from_command_manager(command_manager).model_dump()
        ),
        suggest_companions=lambda species_key, exclude_antagonists_of: [
            s.model_dump()
            for s in suggest_companions_for_agent(
                companion_service, species_key, exclude_antagonists_of=exclude_antagonists_of
            )
        ],
        find_compatible_sets=lambda candidates, size, must_include: [
            s.model_dump()
            for s in find_compatible_sets_for_agent(
                companion_service, candidates, size=size, must_include=must_include
            )
        ],
        find_sets_for_bed=lambda bed_plants, size: find_sets_for_bed(
            companion_service, bed_plants, size=size
        ),
        check_placement=lambda species_key, bed_id, bed_plants: check_placement_for_agent(
            companion_service, species_key, bed_id, bed_plants=bed_plants
        ).model_dump(),
    )


class TestDomainToolsIntegration:
    """Integration tests for the domain-intelligence MCP tools."""

    def test_suggest_companions_over_mcp(self, qtbot: Any) -> None:
        """suggest_companions should return ranked companions over MCP."""
        scene = _make_scene()
        command_manager = _make_command_manager()
        providers = _providers(scene, command_manager)
        server = AgentApiServer(providers, port=_free_port())
        server.start()
        assert server.is_running

        result: dict[str, Any] = {}

        async def _run() -> None:
            from mcp import ClientSession

            try:
                from mcp.client.streamable_http import (
                    streamable_http_client as http_client,
                )
            except ImportError:
                from mcp.client.streamable_http import (
                    streamablehttp_client as http_client,
                )

            async with (
                http_client(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool(
                    "suggest_companions",
                    {"species_key": "tomato"},
                )
                result["data"] = call.structuredContent
                result["isError"] = call.isError

        _run_with_qt_loop(qtbot, _run())
        server.stop()

        assert not result.get("isError")
        data = result.get("data")
        # MCP wraps list results in {'result': [...]}
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
        assert isinstance(data, list)
        assert len(data) > 0
        first = data[0]
        assert "species_key" in first
        assert "name" in first
        assert "score" in first

    def test_find_compatible_sets_over_mcp(self, qtbot: Any) -> None:
        """find_compatible_sets should return compatible sets over MCP."""
        scene = _make_scene()
        command_manager = _make_command_manager()
        providers = _providers(scene, command_manager)
        server = AgentApiServer(providers, port=_free_port())
        server.start()
        assert server.is_running

        result: dict[str, Any] = {}

        async def _run() -> None:
            from mcp import ClientSession

            try:
                from mcp.client.streamable_http import (
                    streamable_http_client as http_client,
                )
            except ImportError:
                from mcp.client.streamable_http import (
                    streamablehttp_client as http_client,
                )

            async with (
                http_client(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool(
                    "find_compatible_sets",
                    {
                        "candidates": ["corn", "bean", "squash"],
                        "size": 3,
                    },
                )
                result["data"] = call.structuredContent
                result["isError"] = call.isError

        _run_with_qt_loop(qtbot, _run())
        server.stop()

        assert not result.get("isError")
        data = result.get("data")
        # MCP wraps list results in {'result': [...]}
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
        assert isinstance(data, list)
        assert len(data) > 0
        members_sets = [set(s["members"]) for s in data]
        assert any(
            {"corn", "bean", "squash"}.issubset(m)
            for m in members_sets
        )

    def test_get_history_over_mcp(self, qtbot: Any) -> None:
        """get_history should return the current stack state over MCP."""
        scene = _make_scene()
        command_manager = _make_command_manager()
        providers = _providers(scene, command_manager)
        server = AgentApiServer(providers, port=_free_port())
        server.start()
        assert server.is_running

        result: dict[str, Any] = {}

        async def _run() -> None:
            from mcp import ClientSession

            try:
                from mcp.client.streamable_http import (
                    streamable_http_client as http_client,
                )
            except ImportError:
                from mcp.client.streamable_http import (
                    streamablehttp_client as http_client,
                )

            async with (
                http_client(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool("get_history", {})
                result["data"] = call.structuredContent
                result["isError"] = call.isError

        _run_with_qt_loop(qtbot, _run())
        server.stop()

        assert not result.get("isError")
        data = result.get("data")
        assert "undo_depth" in data
        assert "redo_depth" in data
        assert "next_undo_text" in data
        assert "next_redo_text" in data

    def test_check_placement_over_mcp(self, qtbot: Any) -> None:
        """check_placement should return placement info over MCP."""
        scene = _make_scene()
        command_manager = _make_command_manager()
        providers = _providers(scene, command_manager)
        server = AgentApiServer(providers, port=_free_port())
        server.start()
        assert server.is_running

        result: dict[str, Any] = {}

        async def _run() -> None:
            from mcp import ClientSession

            try:
                from mcp.client.streamable_http import (
                    streamable_http_client as http_client,
                )
            except ImportError:
                from mcp.client.streamable_http import (
                    streamablehttp_client as http_client,
                )

            async with (
                http_client(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                call = await session.call_tool(
                    "check_placement",
                    {
                        "species_key": "tomato",
                        "bed_id": "bed-1",
                        "bed_plants": ["basil", "potato"],
                    },
                )
                result["data"] = call.structuredContent
                result["isError"] = call.isError

        _run_with_qt_loop(qtbot, _run())
        server.stop()

        assert not result.get("isError")
        data = result.get("data")
        assert "species_key" in data
        assert "bed_id" in data
        assert "antagonists_present" in data
        assert "companions_present" in data
        assert "spacing_ok" in data
        assert "soil_ok" in data
        assert "overall" in data
        # Tomato and potato are antagonistic
        assert "potato" in data["antagonists_present"]
        # Tomato and basil are beneficial
        assert "basil" in data["companions_present"]
        assert data["overall"] == "critical"

    def test_get_history_does_not_mutate_stack(self, qtbot: Any) -> None:
        """Calling get_history must not change the undo/redo depths."""
        scene = _make_scene()
        command_manager = _make_command_manager()
        providers = _providers(scene, command_manager)
        server = AgentApiServer(providers, port=_free_port())
        server.start()
        assert server.is_running

        result: dict[str, Any] = {}

        async def _run() -> None:
            from mcp import ClientSession

            try:
                from mcp.client.streamable_http import (
                    streamable_http_client as http_client,
                )
            except ImportError:
                from mcp.client.streamable_http import (
                    streamablehttp_client as http_client,
                )

            async with (
                http_client(server.url) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                # Call get_history multiple times, KEEPING each payload.
                # Reading `command_manager.undo_depth` afterwards is not the
                # same assertion: the manager is only zero because nothing
                # ever pushed to it, so that check would pass even if every
                # call lied about its depth. Comparing the three returned
                # payloads to each other is what FR-AGENT-24 actually claims,
                # and it is a real invariant â€” a mutating call would show up
                # as a differing depth between consecutive reads.
                payloads: list[dict[str, Any]] = []
                for _ in range(3):
                    call = await session.call_tool("get_history", {})
                    result["isError"] = call.isError
                    # FastMCP puts the returned pydantic model's own fields at
                    # the top level of structuredContent (the same shape the
                    # check_placement test above relies on).
                    payloads.append(dict(call.structuredContent or {}))
                result["payloads"] = payloads

        _run_with_qt_loop(qtbot, _run())
        server.stop()

        assert not result.get("isError")
        payloads = result.get("payloads") or []
        assert len(payloads) == 3
        first = payloads[0]
        assert first["undo_depth"] == 0
        assert first["redo_depth"] == 0
        # Every call reported the same depths, and none of them reports a
        # phantom step (a "you could undo this" hint must be absent when the
        # stack is empty, not a fabricated label).
        for payload in payloads:
            assert payload["undo_depth"] == first["undo_depth"]
            assert payload["redo_depth"] == first["redo_depth"]
        assert first.get("next_undo_text") in (None, ""), (
            "an empty undo stack must not advertise an undo label"
        )


def _make_scene() -> Any:
    """Create a minimal canvas scene for testing."""
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    scene = CanvasScene()
    # Add a simple bed
    bed = RectangleItem(0, 0, 200, 100)
    # The ObjectType ENUM, not the string: is_plant_parent_type() â€” which
    # the check_placement bed resolution now depends on â€” returns False for a
    # plain string, so a string here is a trap for any later test that
    # routes this scene through that path.
    bed.object_type = ObjectType.RAISED_BED
    scene.addItem(bed)
    return scene


def _make_command_manager() -> Any:
    """Create a command manager for testing."""
    from open_garden_planner.core.commands import CommandManager

    return CommandManager()


def _run_with_qt_loop(qtbot: Any, coro: Any) -> None:
    """Run an async coroutine while pumping the Qt event loop."""
    import asyncio
    from concurrent.futures import Future

    loop = asyncio.new_event_loop()
    future: Future = Future()

    def _run() -> None:
        try:
            result = loop.run_until_complete(coro)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)

    thread = threading.Thread(target=_run)
    thread.start()

    # Pump Qt event loop while waiting
    while not future.done():
        qtbot.wait(10)

    thread.join()
    loop.close()

    if future.exception():
        raise future.exception()
