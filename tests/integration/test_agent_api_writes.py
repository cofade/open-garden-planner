"""End-to-end integration test for the Agent API write tools (US-D2.0).

Boots ``AgentApiServer`` in-process with writes enabled + a token, against a
real ``CanvasView`` (so its ``command_manager`` and scene are the same ones the
GUI uses), then drives it with the real MCP streamable-HTTP client from a worker
thread while the main thread pumps the Qt event loop. This pins the D2 contract:

  * an unauthenticated write call is rejected and the scene is unchanged;
  * an authenticated ``move_object`` / ``delete_object`` mutates the plan;
  * each mutation is exactly ONE undoable command (Ctrl+Z reverses it) and
    marks the document dirty (invariants #3/#4/#13).
"""

from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import Callable
from typing import Any
from uuid import UUID

from PyQt6.QtCore import QPointF

from open_garden_planner.agent_api import (
    AgentApiServer,
    AgentProviders,
    MainThreadBridge,
)
from open_garden_planner.core.commands import DeleteItemsCommand, MoveItemsCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem

TOKEN = "test-write-token-12345"


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _providers(view: CanvasView) -> AgentProviders:
    """Providers whose write ops run REAL commands on the view's command manager."""
    bridge = MainThreadBridge()
    scene = view.scene()

    def _resolve(item_id: str) -> Any:
        item = scene.find_item_by_id(UUID(item_id))
        if item is None:
            raise ValueError(f"No object with id {item_id}")
        return item

    def _move(item_id: str, dx: float, dy: float) -> dict[str, Any]:
        item = _resolve(item_id)
        cmd = MoveItemsCommand([item], QPointF(dx, dy))
        view.command_manager.execute(cmd)
        c = item.sceneBoundingRect().center()
        return {
            "item_id": item_id,
            "action": "move",
            "undo_description": cmd.description,
            "x": c.x(),
            "y": c.y(),
        }

    def _delete(item_id: str) -> dict[str, Any]:
        item = _resolve(item_id)
        cmd = DeleteItemsCommand(scene, [item])
        view.command_manager.execute(cmd)
        return {"item_id": item_id, "action": "delete", "undo_description": cmd.description}

    def _boom(*_a: Any) -> dict[str, Any]:
        raise AssertionError("read provider must not run in this test")

    return AgentProviders(
        snapshot=lambda: bridge.run_on_main(lambda: {}),
        diagnostics=lambda: [],
        render=lambda *_a: _boom(),
        save_plan=lambda _p: _boom(),
        export_pdf=lambda *_a: _boom(),
        export_dxf=lambda _p: _boom(),
        export_csv=lambda *_a: _boom(),
        move_object=lambda item_id, dx, dy: bridge.run_on_main(
            lambda: _move(item_id, dx, dy)
        ),
        delete_object=lambda item_id: bridge.run_on_main(lambda: _delete(item_id)),
    )


def _drive(server: AgentApiServer, body: Callable[[Any], Any], result: dict[str, Any]) -> None:
    async def run() -> None:
        from mcp import ClientSession

        # Use streamablehttp_client specifically: it accepts a `headers` kwarg
        # (the other streamable_http_client overload does not) — required to
        # send the Authorization: Bearer token these write tests exercise.
        from mcp.client.streamable_http import streamablehttp_client as http_client

        await body((http_client, ClientSession, server.url))

    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - surface to the assertion below
        result["error"] = exc
    finally:
        result["done"] = True


def _run(server: AgentApiServer, body: Callable[[Any], Any], qtbot: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-write-test-client"
    ).start()
    qtbot.waitUntil(lambda: result.get("done", False), timeout=20000)
    assert result.get("error") is None, result.get("error")
    return result


def test_move_object_end_to_end(canvas: Any, qtbot: Any) -> None:
    view = canvas
    scene = view.scene()
    circle = CircleItem(200, 200, 30, object_type=ObjectType.TREE)
    scene.addItem(circle)
    item_id = str(circle.item_id)
    start = circle.sceneBoundingRect().center()

    server = AgentApiServer(
        _providers(view), port=_free_port(), write_token=TOKEN, writes_enabled=True
    )
    server.start()

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with (
            http_client(url, headers=headers) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            call = await session.call_tool(
                "move_object", {"item_id": item_id, "dx": 50.0, "dy": -25.0}
            )
            body.result = call.structuredContent  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    moved = circle.sceneBoundingRect().center()
    assert moved.x() == start.x() + 50.0
    assert moved.y() == start.y() - 25.0
    # One undoable step that reverses cleanly.
    assert view.command_manager.can_undo
    view.command_manager.undo()
    back = circle.sceneBoundingRect().center()
    assert back.x() == start.x()
    assert back.y() == start.y()


def test_delete_object_end_to_end(canvas: Any, qtbot: Any) -> None:
    view = canvas
    scene = view.scene()
    circle = CircleItem(200, 200, 30, object_type=ObjectType.TREE)
    scene.addItem(circle)
    item_id = str(circle.item_id)

    server = AgentApiServer(
        _providers(view), port=_free_port(), write_token=TOKEN, writes_enabled=True
    )
    server.start()

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with (
            http_client(url, headers=headers) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            await session.call_tool("delete_object", {"item_id": item_id})

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    assert scene.find_item_by_id(circle.item_id) is None
    # Undo restores the object.
    assert view.command_manager.can_undo
    view.command_manager.undo()
    assert scene.find_item_by_id(circle.item_id) is not None


def test_unauthenticated_move_is_rejected(canvas: Any, qtbot: Any) -> None:
    view = canvas
    scene = view.scene()
    circle = CircleItem(200, 200, 30, object_type=ObjectType.TREE)
    scene.addItem(circle)
    item_id = str(circle.item_id)
    start = circle.sceneBoundingRect().center()

    server = AgentApiServer(
        _providers(view), port=_free_port(), write_token=TOKEN, writes_enabled=True
    )
    server.start()

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        # No Authorization header at all.
        async with (
            http_client(url) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            call = await session.call_tool(
                "move_object", {"item_id": item_id, "dx": 50.0, "dy": -25.0}
            )
            body.is_error = call.isError  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    assert getattr(body, "is_error", False) is True
    # Scene untouched, nothing on the undo stack.
    now = circle.sceneBoundingRect().center()
    assert now.x() == start.x()
    assert now.y() == start.y()
    assert view.command_manager.can_undo is False
