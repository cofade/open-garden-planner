"""End-to-end integration test for the embedded Agent API MCP server.

Boots ``AgentApiServer`` in-process on an ephemeral port against a real scene,
then drives it with the real MCP streamable-HTTP client from a worker thread
while the main thread pumps the Qt event loop (so the bridge can marshal the
scene read onto the main thread). This exercises the full chain:
client -> server thread -> tool handler -> MainThreadBridge -> snapshot_dict /
diagnostics_snapshot.
"""

from __future__ import annotations

import asyncio
import base64
import json
import socket
import threading
from collections.abc import Callable
from typing import Any

from open_garden_planner.agent_api import (
    AgentApiServer,
    AgentProviders,
    MainThreadBridge,
)
from open_garden_planner.agent_api.exports import (
    export_csv_file,
    export_dxf_file,
    export_pdf_file,
    save_plan_file,
)
from open_garden_planner.agent_api.render import render_canvas_image
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _providers(scene: Any) -> AgentProviders:
    bridge = MainThreadBridge()
    project_manager = ProjectManager()
    soil_service = SoilService(project_manager)
    return AgentProviders(
        snapshot=lambda: bridge.run_on_main(
            lambda: project_manager.snapshot_dict(scene)
        ),
        diagnostics=lambda: bridge.run_on_main(
            lambda: project_manager.diagnostics_snapshot(scene)
        ),
        render=lambda region, layers, width_px: bridge.run_on_main(
            lambda: render_canvas_image(scene, region, layers, width_px)
        ),
        save_plan=lambda file_path: bridge.run_on_main(
            lambda: save_plan_file(scene, project_manager, soil_service, file_path)
        ),
        export_pdf=lambda file_path, paper_size, orientation: bridge.run_on_main(
            lambda: export_pdf_file(
                scene, project_manager, file_path, paper_size, orientation
            )
        ),
        export_dxf=lambda file_path: bridge.run_on_main(
            lambda: export_dxf_file(scene, project_manager, file_path)
        ),
        export_csv=lambda kind, file_path: bridge.run_on_main(
            lambda: export_csv_file(scene, project_manager, soil_service, kind, file_path)
        ),
    )


def _drive(server: AgentApiServer, body: Callable[[Any], Any], result: dict[str, Any]) -> None:
    """Run an MCP client session against ``server`` and call ``body(session)``."""

    async def run() -> None:
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
            await body(session)

    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - surface to the assertion below
        result["error"] = exc
    finally:
        result["done"] = True


def test_get_plan_summary_end_to_end(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    scene.addItem(RectangleItem(0, 0, 100, 80, object_type=ObjectType.RAISED_BED))
    scene.addItem(CircleItem(200, 200, 30, object_type=ObjectType.TREE))

    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()
    assert server.is_running

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        tools = await session.list_tools()
        result["tools"] = [t.name for t in tools.tools]
        call = await session.call_tool("get_plan_summary", {})
        result["summary"] = call.structuredContent

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")
        assert "get_plan_summary" in result["tools"]
        # All US-D1.2/D1.3/D1.4 read/query/vision/export tools are registered
        # alongside the summary.
        for name in (
            "list_objects",
            "get_object",
            "objects_in_region",
            "objects_in",
            "plants_in_bed",
            "nearest_objects",
            "measure_distance",
            "get_diagnostics",
            "render_canvas_image",
            "save_plan",
            "export_pdf",
            "export_dxf",
            "export_csv",
        ):
            assert name in result["tools"], name
        summary = result["summary"]
        assert summary["bed_count"] == 1
        assert summary["plant_count"] == 1
        assert summary["shape_count"] == 0
        assert summary["canvas_width_cm"] == scene.width_cm
        assert summary["is_dirty"] is False
    finally:
        server.stop()

    assert server.is_running is False


def test_read_query_tools_end_to_end(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    bed = RectangleItem(0, 0, 200, 100, object_type=ObjectType.RAISED_BED)
    bed.name = "Bed A"
    tree = CircleItem(50, 50, 15, object_type=ObjectType.TREE)
    tree.name = "Apple"
    herb = CircleItem(150, 50, 10, object_type=ObjectType.PERENNIAL)
    herb.name = "Mint"
    tree.parent_bed_id = bed.item_id
    herb.parent_bed_id = bed.item_id
    bed._child_item_ids = [tree.item_id, herb.item_id]
    # A computed warning the canvas would badge: companion conflict on the tree.
    tree.set_antagonist_warning(True)
    for item in (bed, tree, herb):
        scene.addItem(item)

    bed_id = str(bed.item_id)
    tree_id = str(tree.item_id)
    herb_id = str(herb.item_id)

    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()
    assert server.is_running

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        plants = await session.call_tool("list_objects", {"type": "plant"})
        result["plants"] = plants.structuredContent["result"]

        detail = await session.call_tool("get_object", {"item_id": tree_id})
        result["tree"] = detail.structuredContent["result"]

        in_bed = await session.call_tool("plants_in_bed", {"bed_id": bed_id})
        result["in_bed"] = in_bed.structuredContent["result"]

        measure = await session.call_tool(
            "measure_distance", {"id_a": tree_id, "id_b": herb_id}
        )
        result["measure"] = measure.structuredContent["result"]

        diags = await session.call_tool("get_diagnostics", {})
        result["diagnostics"] = diags.structuredContent["result"]

        # raw=True must preserve serialiser-only keys through FastMCP's structured
        # content — the dict-first union return guards against the model coercing
        # them away (verified vs mcp 1.28.1). Pin it end-to-end so an SDK bump or a
        # union-order "tidy" can't silently regress raw mode with the suite green.
        raw = await session.call_tool("list_objects", {"type": "circle", "raw": True})
        result["raw"] = raw.structuredContent["result"]

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")

        assert {p["item_id"] for p in result["plants"]} == {tree_id, herb_id}

        tree = result["tree"]
        assert tree["object_type"] == "TREE"
        assert tree["parent_bed_id"] == bed_id
        assert tree["center_x_cm"] == 50.0

        assert {p["item_id"] for p in result["in_bed"]} == {tree_id, herb_id}

        assert result["measure"]["distance_cm"] == 100.0

        diags = result["diagnostics"]
        assert len(diags) == 1
        assert diags[0]["kind"] == "companion_conflict"
        assert diags[0]["item_ids"] == [tree_id]

        raw = result["raw"]
        assert {r["item_id"] for r in raw} == {tree_id, herb_id}
        # 'radius'/'center_x' are serialiser-only keys absent from the curated ObjectRef.
        assert all("radius" in r and "center_x" in r for r in raw)
    finally:
        server.stop()

    assert server.is_running is False


def test_resources_end_to_end(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    bed = RectangleItem(0, 0, 200, 100, object_type=ObjectType.RAISED_BED)
    tree = CircleItem(50, 50, 15, object_type=ObjectType.TREE)
    tree.name = "Apple"
    tree.parent_bed_id = bed.item_id
    bed._child_item_ids = [tree.item_id]
    tree.set_antagonist_warning(True)
    for item in (bed, tree):
        scene.addItem(item)

    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()
    assert server.is_running

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        listing = await session.list_resources()
        result["uris"] = {str(r.uri) for r in listing.resources}

        plan = await session.read_resource("garden://plan")
        result["plan"] = json.loads(plan.contents[0].text)

        plan_raw = await session.read_resource("garden://plan/raw")
        result["plan_raw"] = json.loads(plan_raw.contents[0].text)

        canvas_png = await session.read_resource("garden://canvas.png")
        blob = canvas_png.contents[0]
        result["canvas_png_mime"] = blob.mimeType
        result["canvas_png_bytes"] = base64.b64decode(blob.blob)

        diagnostics = await session.read_resource("garden://diagnostics")
        result["diagnostics"] = json.loads(diagnostics.contents[0].text)

        species = await session.read_resource("garden://species")
        result["species"] = json.loads(species.contents[0].text)

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")

        assert result["uris"] == {
            "garden://plan",
            "garden://plan/raw",
            "garden://canvas.png",
            "garden://diagnostics",
            "garden://species",
        }

        assert result["plan"]["bed_count"] == 1
        assert result["plan"]["plant_count"] == 1

        raw_objects = result["plan_raw"]["objects"]
        assert any("center_x" in obj for obj in raw_objects)  # raw-only key

        assert result["canvas_png_mime"] == "image/png"
        assert result["canvas_png_bytes"].startswith(b"\x89PNG")

        assert len(result["diagnostics"]) == 1
        assert result["diagnostics"][0]["kind"] == "companion_conflict"

        from open_garden_planner.services.bundled_species_db import get_species_db

        assert len(result["species"]) == len(get_species_db())
        assert all("scientific_name" in s and "common_name" in s for s in result["species"])
    finally:
        server.stop()

    assert server.is_running is False


def test_prompts_end_to_end(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    bed = RectangleItem(0, 0, 200, 100, object_type=ObjectType.RAISED_BED)
    tree = CircleItem(50, 50, 15, object_type=ObjectType.TREE)
    tree.name = "Apple"
    scene.addItem(bed)
    scene.addItem(tree)

    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()
    assert server.is_running

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        listing = await session.list_prompts()
        result["names"] = {p.name for p in listing.prompts}

        audit = await session.get_prompt("audit-plan")
        result["audit_text"] = audit.messages[0].content.text

        describe = await session.get_prompt("describe-garden")
        result["describe_text"] = describe.messages[0].content.text

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")

        assert result["names"] == {"audit-plan", "describe-garden"}
        assert "Beds/containers: 1" in result["audit_text"]
        assert "Plants: 1" in result["audit_text"]
        assert "Apple" in result["describe_text"]
    finally:
        server.stop()

    assert server.is_running is False
