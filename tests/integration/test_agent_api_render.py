"""End-to-end integration test for the Agent API's render_canvas_image tool (US-D1.3).

Boots ``AgentApiServer`` in-process against a real scene (mirroring
``test_agent_api_server.py``'s pattern), drives a real MCP client, and decodes
the returned PNG. Pins two things that were empirically discovered, not
assumed, while designing this tool (see ADR-034 addendum / schema.py):

  1. Registration must succeed and a call must return exactly
     ``[ImageContent, TextContent]`` — NOT ``structuredContent`` like the other
     9 tools — because ``Image`` isn't pydantic-representable and the tool is
     registered with ``structured_output=False`` (verified against mcp 1.28.1;
     the naive design crashes ``build_server()`` at decoration time instead).
  2. The rendered image's pixel Y-axis is inverted relative to the D1.2 scene
     frame (``RenderMeta.px_per_cm``'s documented correction formula) — this
     test cross-checks that formula end-to-end through the real MCP call,
     complementing the dedicated unit-level proof in
     ``test_agent_api_render_coordinate_frame.py``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import socket
import threading
from collections.abc import Callable
from typing import Any

from PyQt6.QtGui import QColor, QImage

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
from open_garden_planner.models.layer import Layer
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.canvas.items import CircleItem


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
        snapshot=lambda: bridge.run_on_main(lambda: project_manager.snapshot_dict(scene)),
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
        # Write providers are unused by these read-only render tests.
        move_object=lambda *_a: _unused("move_object"),
        delete_object=lambda *_a: _unused("delete_object"),
    )


def _unused(name: str) -> dict[str, Any]:
    raise AssertionError(f"{name} should not be called in a read-only test")


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


def _decode_png(image_content: Any) -> QImage:
    data = base64.b64decode(image_content.data)
    img = QImage()
    assert img.loadFromData(data, "PNG")
    return img


def _cm_to_px(meta: dict[str, Any], x_cm: float, y_cm: float) -> tuple[int, int]:
    """The documented RenderMeta.px_per_cm correction formula."""
    px_per_cm = meta["px_per_cm"]
    px_x = (x_cm - meta["region_x_cm"]) * px_per_cm
    px_y = meta["image_height_px"] - (y_cm - meta["region_y_cm"]) * px_per_cm
    return round(px_x), round(px_y)


def test_render_canvas_image_full_canvas_default(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    red = CircleItem(1000, 1000, 60, object_type=ObjectType.GENERIC_CIRCLE)
    red.setBrush(QColor(255, 0, 0))
    scene.addItem(red)

    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()
    assert server.is_running

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        tools = await session.list_tools()
        result["tools"] = [t.name for t in tools.tools]
        result["call"] = await session.call_tool("render_canvas_image", {})

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")
        assert "render_canvas_image" in result["tools"]

        call = result["call"]
        assert call.isError is not True
        # structured_output=False: no structuredContent, exactly 2 content blocks.
        assert call.structuredContent is None
        assert len(call.content) == 2
        image_block, text_block = call.content
        assert image_block.type == "image"
        assert image_block.mimeType == "image/png"
        assert text_block.type == "text"

        meta = json.loads(text_block.text)
        assert meta["region_x_cm"] == 0.0
        assert meta["region_y_cm"] == 0.0
        assert meta["region_width_cm"] == scene.width_cm
        assert meta["region_height_cm"] == scene.height_cm
        assert meta["layers_rendered"] is None

        img = _decode_png(image_block)
        assert img.width() == meta["image_width_px"]
        assert img.height() == meta["image_height_px"]

        background = img.pixelColor(0, 0)
        px_x, px_y = _cm_to_px(meta, 1000, 1000)
        assert img.pixelColor(px_x, px_y) != background
    finally:
        server.stop()

    assert server.is_running is False


def test_render_canvas_image_explicit_region(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool(
            "render_canvas_image",
            {"x": 100.0, "y": 200.0, "width": 400.0, "height": 300.0, "image_width_px": 256},
        )

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")

        _, text_block = result["call"].content
        meta = json.loads(text_block.text)
        assert (meta["region_x_cm"], meta["region_y_cm"]) == (100.0, 200.0)
        assert (meta["region_width_cm"], meta["region_height_cm"]) == (400.0, 300.0)
        assert meta["image_width_px"] == 256
        assert meta["image_height_px"] == round(256 * (300.0 / 400.0))
    finally:
        server.stop()


def test_render_canvas_image_partial_region_args_error(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool("render_canvas_image", {"x": 0.0})

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")
        assert result["call"].isError is True
    finally:
        server.stop()


def test_render_canvas_image_layers_filter_hides_and_restores(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    layer_a = Layer(name="Layer A")
    layer_b = Layer(name="Layer B")
    scene.set_layers([layer_a, layer_b])

    red = CircleItem(1000, 1000, 80, object_type=ObjectType.GENERIC_CIRCLE, layer_id=layer_a.id)
    red.setBrush(QColor(255, 0, 0))
    blue = CircleItem(3000, 1000, 80, object_type=ObjectType.GENERIC_CIRCLE, layer_id=layer_b.id)
    blue.setBrush(QColor(0, 0, 255))
    scene.addItem(red)
    scene.addItem(blue)

    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool("render_canvas_image", {"layers": ["Layer A"]})

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")

        image_block, text_block = result["call"].content
        meta = json.loads(text_block.text)
        assert meta["layers_rendered"] == ["Layer A"]

        img = _decode_png(image_block)
        background = img.pixelColor(0, 0)
        red_px = _cm_to_px(meta, 1000, 1000)
        blue_px = _cm_to_px(meta, 3000, 1000)
        assert img.pixelColor(*red_px) != background
        # Layer B was hidden for the render: its location is plain background,
        # not compared via a channel threshold (the canvas background itself
        # can have a high blue channel, e.g. beige == (245, 245, 220)).
        assert img.pixelColor(*blue_px) == background

        # Live scene state must be restored after the call.
        assert red.isVisible()
        assert blue.isVisible()
    finally:
        server.stop()


def test_render_canvas_image_layers_filter_shows_layer_hidden_in_ui(
    canvas: Any, qtbot: Any
) -> None:
    """An allowed layer must render even if the user has it toggled off live.

    Regression test: ``layers`` is a full override of what's shown, not a
    subtractive filter layered on top of the live Layers-panel state — an
    agent explicitly asking for "Layer B" must get it, even if a human
    happens to have that layer hidden in the GUI right now.
    """
    scene = canvas.scene()
    layer_a = Layer(name="Layer A")
    layer_b = Layer(name="Layer B")
    scene.set_layers([layer_a, layer_b])

    red = CircleItem(1000, 1000, 80, object_type=ObjectType.GENERIC_CIRCLE, layer_id=layer_a.id)
    red.setBrush(QColor(255, 0, 0))
    blue = CircleItem(3000, 1000, 80, object_type=ObjectType.GENERIC_CIRCLE, layer_id=layer_b.id)
    blue.setBrush(QColor(0, 0, 255))
    scene.addItem(red)
    scene.addItem(blue)
    scene.update_layer_visibility(layer_b.id, False)
    assert blue.isVisible() is False  # sanity: the UI really has it hidden

    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool("render_canvas_image", {"layers": ["Layer B"]})

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")

        image_block, text_block = result["call"].content
        meta = json.loads(text_block.text)

        img = _decode_png(image_block)
        background = img.pixelColor(0, 0)
        blue_px = _cm_to_px(meta, 3000, 1000)
        # Layer B was explicitly requested: it must appear even though the
        # live UI currently has it hidden.
        assert img.pixelColor(*blue_px) != background

        # Restored to the pre-render (hidden) state afterward, not left visible.
        assert blue.isVisible() is False
        assert red.isVisible() is True
    finally:
        server.stop()


def test_render_canvas_image_unknown_layer_name_is_tolerated(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    layer_a = Layer(name="Layer A")
    scene.set_layers([layer_a])
    red = CircleItem(1000, 1000, 80, object_type=ObjectType.GENERIC_CIRCLE, layer_id=layer_a.id)
    red.setBrush(QColor(255, 0, 0))
    scene.addItem(red)

    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool(
            "render_canvas_image", {"layers": ["totally-made-up-name"]}
        )

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")
        assert result["call"].isError is not True
        assert red.isVisible()  # restored, not left hidden
    finally:
        server.stop()


def test_render_canvas_image_preserves_selection(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    circle = CircleItem(1000, 1000, 60, object_type=ObjectType.GENERIC_CIRCLE)
    scene.addItem(circle)
    circle.setSelected(True)

    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()

    result: dict[str, Any] = {}

    async def body(session: Any) -> None:
        result["call"] = await session.call_tool("render_canvas_image", {})

    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-test-client"
    ).start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert result.get("error") is None, result.get("error")
        assert result["call"].isError is not True
        assert circle.isSelected()
    finally:
        server.stop()
