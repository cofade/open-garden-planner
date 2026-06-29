"""End-to-end integration test for the embedded Agent API MCP server.

Boots ``AgentApiServer`` in-process on an ephemeral port against a real scene,
then drives it with the real MCP streamable-HTTP client from a worker thread
while the main thread pumps the Qt event loop (so the bridge can marshal the
scene read onto the main thread). This exercises the full chain:
client -> server thread -> tool handler -> MainThreadBridge -> snapshot_dict.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from typing import Any

from open_garden_planner.agent_api import AgentApiServer, MainThreadBridge
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_get_plan_summary_end_to_end(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    scene.addItem(RectangleItem(0, 0, 100, 80, object_type=ObjectType.RAISED_BED))
    scene.addItem(CircleItem(200, 200, 30, object_type=ObjectType.TREE))

    bridge = MainThreadBridge()
    project_manager = ProjectManager()

    def snapshot() -> dict[str, Any]:
        return bridge.run_on_main(lambda: project_manager.snapshot_dict(scene))

    server = AgentApiServer(snapshot, port=_free_port())
    server.start()
    assert server.is_running

    result: dict[str, Any] = {}

    def run_client() -> None:
        async def drive() -> None:
            from mcp import ClientSession

            try:  # SDK renamed it; fall back for the pinned floor (mcp>=1.12)
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
                tools = await session.list_tools()
                result["tools"] = [t.name for t in tools.tools]
                call = await session.call_tool("get_plan_summary", {})
                result["summary"] = call.structuredContent

        try:
            asyncio.run(drive())
        except Exception as exc:  # noqa: BLE001 - surface to the assertion below
            result["error"] = exc
        finally:
            result["done"] = True

    client_thread = threading.Thread(target=run_client, name="mcp-test-client")
    client_thread.start()
    try:
        # Pump the Qt event loop so the bridge can service the snapshot read
        # while the client call is in flight.
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        client_thread.join(timeout=5.0)

        assert result.get("error") is None, result.get("error")
        assert "get_plan_summary" in result["tools"]
        summary = result["summary"]
        assert summary["bed_count"] == 1
        assert summary["plant_count"] == 1
        assert summary["shape_count"] == 0
        assert summary["canvas_width_cm"] == scene.width_cm
        assert summary["is_dirty"] is False
    finally:
        server.stop()

    assert server.is_running is False
