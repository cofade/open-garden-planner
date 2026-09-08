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
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from PyQt6.QtWidgets import QMessageBox

from open_garden_planner.agent_api import (
    AgentApiServer,
    AgentProviders,
)
from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem

TOKEN = "test-write-token-12345"


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


_APP_BY_VIEW: dict[int, GardenPlannerApp] = {}


@pytest.fixture()
def canvas(qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Use a real ``GardenPlannerApp`` so providers are production-wired."""
    get_settings().show_welcome_on_startup = False
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard,
    )
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    view = app.canvas_view
    view.set_snap_enabled(False)
    _APP_BY_VIEW[id(view)] = app
    try:
        yield view
    finally:
        _APP_BY_VIEW.pop(id(view), None)
        app._stop_agent_api()


def _providers(view: CanvasView) -> AgentProviders:
    """Return the exact provider graph the production app gives its server."""
    app = _APP_BY_VIEW.get(id(view))
    if app is None:
        raise AssertionError("canvas fixture did not register its GardenPlannerApp")
    return app._build_agent_providers()


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


def test_create_object_end_to_end(canvas: Any, qtbot: Any) -> None:
    """US-D2.1: an authenticated create_object call reaches the scene over the
    real MCP transport and is one undoable step."""
    from uuid import UUID

    view = canvas
    scene = view.scene()
    before = len(scene.items())

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
                "create_object",
                {"object_type": "TREE", "x": 800.0, "y": 600.0, "radius": 45.0},
            )
            body.result = call.structuredContent  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    created = body.result  # type: ignore[attr-defined]
    assert created["action"] == "create"
    assert len(scene.items()) > before
    item = scene.find_item_by_id(UUID(created["item_id"]))
    assert item is not None

    # One undoable step that reverses cleanly.
    assert view.command_manager.can_undo
    view.command_manager.undo()
    assert scene.find_item_by_id(UUID(created["item_id"])) is None


def test_create_object_shape_families_end_to_end(
    canvas: Any, qtbot: Any, tmp_path: Path
) -> None:
    """US-D2.5: every discovered creatable type crosses the real MCP transport.

    The provider uses the same loader factory as the application-side
    orchestration; this test additionally proves the expanded parameter names
    survive MCP schema generation, auth, marshaling and result decoding.  The
    resulting plan is then saved and loaded again, so the discovery roster is
    also a round-trip contract rather than merely a construction roster.
    """
    from open_garden_planner.agent_api.creates import (
        _CIRCLE_TYPE_NAMES,
        _ELLIPSE_TYPE_NAMES,
        _POLYGON_TYPE_NAMES,
        _POLYLINE_TYPE_NAMES,
        _RECT_TYPE_NAMES,
        CREATABLE_TYPE_NAMES,
    )
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    view = canvas
    scene = view.scene()
    before = len([item for item in scene.items() if item.parentItem() is None])
    server = AgentApiServer(
        _providers(view), port=_free_port(), write_token=TOKEN, writes_enabled=True
    )
    server.start()

    def request_for(object_type: str, index: int) -> dict[str, Any]:
        """Build a small, in-bounds request for each discovered family member."""
        x = 250.0 + (index % 10) * 450.0
        y = 250.0 + (index // 10) * 550.0
        if object_type in _CIRCLE_TYPE_NAMES:
            return {"object_type": object_type, "x": x, "y": y, "radius": 30.0}
        if object_type in _RECT_TYPE_NAMES:
            return {
                "object_type": object_type,
                "x": x,
                "y": y,
                "width": 120.0,
                "height": 80.0,
            }
        if object_type in _ELLIPSE_TYPE_NAMES:
            return {
                "object_type": object_type,
                "x": x,
                "y": y,
                "width": 120.0,
                "height": 80.0,
            }
        if object_type in _POLYGON_TYPE_NAMES:
            return {
                "object_type": object_type,
                "points": [
                    [x - 60.0, y - 40.0],
                    [x + 60.0, y - 40.0],
                    [x + 60.0, y + 40.0],
                    [x - 60.0, y + 40.0],
                ],
            }
        if object_type in _POLYLINE_TYPE_NAMES:
            return {
                "object_type": object_type,
                "points": [[x - 60.0, y - 30.0], [x + 60.0, y + 30.0]],
            }
        return {"object_type": object_type, "x": x, "y": y, "text": "Inspect this area"}

    requests = [
        request_for(object_type, index)
        for index, object_type in enumerate(sorted(CREATABLE_TYPE_NAMES))
    ]

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with (
            http_client(url, headers=headers) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            catalog = await session.call_tool("list_creatable_types", {})
            body.results = [
                (await session.call_tool("create_object", request)).structuredContent
                for request in requests
            ]  # type: ignore[attr-defined]
            body.catalog = catalog.structuredContent["result"]  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    results = body.results  # type: ignore[attr-defined]
    catalog = body.catalog  # type: ignore[attr-defined]
    assert {entry["object_type"] for entry in catalog if entry["creatable"]} == {
        request["object_type"] for request in requests
    }
    assert all(result["action"] == "create" for result in results)
    house_result = next(
        result
        for request, result in zip(requests, results, strict=True)
        if request["object_type"] == "HOUSE"
    )
    assert sum(result["linked_items_created"] for result in results) == 1
    top_level = [item for item in scene.items() if item.parentItem() is None]
    assert len(top_level) == before + len(requests) + 1  # HOUSE's ridge

    manager = ProjectManager()
    save_path = tmp_path / "agent-created-shapes.ogp"
    manager.save(scene, save_path)
    loaded = CanvasScene(width_cm=scene.width_cm, height_cm=scene.height_cm)
    manager.load(loaded, save_path)
    loaded_items = [
        item
        for item in loaded.items()
        if item.parentItem() is None and getattr(item, "object_type", None) is not None
    ]
    loaded_types = {item.object_type.name for item in loaded_items}
    assert {request["object_type"] for request in requests} <= loaded_types
    loaded_ids = {str(item.item_id) for item in loaded_items}
    assert {result["item_id"] for result in results} <= loaded_ids
    house = loaded.find_item_by_id(UUID(house_result["item_id"]))
    assert house is not None
    assert house.metadata.get("ridge_item_id")

    # Every create call produces one undo entry; the HOUSE entry removes
    # both the house and its ridge, proving the composite remains one step.
    for _ in requests:
        view.command_manager.undo()
    assert len([item for item in scene.items() if item.parentItem() is None]) == before


def test_unauthenticated_create_is_rejected(canvas: Any, qtbot: Any) -> None:
    """The write gate covers create_object too, not just move/delete."""
    view = canvas
    scene = view.scene()
    before = len(scene.items())

    server = AgentApiServer(
        _providers(view), port=_free_port(), write_token=TOKEN, writes_enabled=True
    )
    server.start()

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        async with (
            http_client(url) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            call = await session.call_tool(
                "create_object",
                {"object_type": "TREE", "x": 800.0, "y": 600.0, "radius": 45.0},
            )
            body.is_error = call.isError  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    assert body.is_error is True  # type: ignore[attr-defined]
    # Nothing was created and nothing is undoable.
    assert len(scene.items()) == before
    assert view.command_manager.can_undo is False


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


def test_move_object_authenticated_via_query_param(canvas: Any, qtbot: Any) -> None:
    """The ``?token=`` URL route with NO Authorization header — Claude Code does
    not transmit configured headers on tool-call requests (anthropics/claude-code
    #50464), so the token rides the URL, which every client always sends."""
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
        # Token in the URL query string; no headers kwarg at all.
        async with (
            http_client(f"{url}?token={TOKEN}") as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            await session.call_tool(
                "move_object", {"item_id": item_id, "dx": 50.0, "dy": -25.0}
            )

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    moved = circle.sceneBoundingRect().center()
    assert moved.x() == start.x() + 50.0
    assert moved.y() == start.y() - 25.0
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


def test_resize_object_end_to_end(canvas: Any, qtbot: Any) -> None:
    """US-D2.2: an authenticated resize_object call reaches the scene over the
    real MCP transport, preserves the object's centre, and is one undoable
    step. The in-process orchestration tests live in
    test_agent_api_default_on.py; this pins the transport + auth half."""
    view = canvas
    scene = view.scene()
    item = CircleItem(800.0, 600.0, 40.0, object_type=ObjectType.TREE)
    scene.addItem(item)
    before_centre = item.mapToScene(item.rect().center())

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
                "resize_object", {"item_id": str(item.item_id), "radius": 90.0}
            )
            body.result = call.structuredContent  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    resized = body.result  # type: ignore[attr-defined]
    assert resized["action"] == "resize"
    assert resized["radius"] == 90.0
    assert item.radius == 90.0
    after_centre = item.mapToScene(item.rect().center())
    assert abs(after_centre.x() - before_centre.x()) < 1e-6
    assert abs(after_centre.y() - before_centre.y()) < 1e-6

    assert view.command_manager.can_undo
    view.command_manager.undo()
    assert item.radius == 40.0


def test_rotate_object_end_to_end(canvas: Any, qtbot: Any) -> None:
    """US-D2.2: rotate_object over the real transport, absolute by default."""
    view = canvas
    scene = view.scene()
    item = CircleItem(1200.0, 900.0, 50.0, object_type=ObjectType.SHRUB)
    scene.addItem(item)

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
            first = await session.call_tool(
                "rotate_object", {"item_id": str(item.item_id), "angle": 45.0}
            )
            second = await session.call_tool(
                "rotate_object",
                {"item_id": str(item.item_id), "angle": 45.0, "relative": True},
            )
            body.first = first.structuredContent  # type: ignore[attr-defined]
            body.second = second.structuredContent  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    assert body.first["rotation_deg"] == 45.0  # type: ignore[attr-defined]
    assert body.second["rotation_deg"] == 90.0  # type: ignore[attr-defined]
    assert item.rotation_angle == 90.0

    view.command_manager.undo()
    assert item.rotation_angle == 45.0


def test_unauthenticated_resize_and_rotate_are_rejected(
    canvas: Any, qtbot: Any
) -> None:
    """The ADR-036 double gate covers the D2.2 tools too. A write tool that
    forgot its _require_write_auth call would pass every other test in this
    file — this is the one that catches it."""
    view = canvas
    scene = view.scene()
    item = CircleItem(400.0, 400.0, 30.0, object_type=ObjectType.TREE)
    scene.addItem(item)

    server = AgentApiServer(
        _providers(view), port=_free_port(), write_token=TOKEN, writes_enabled=True
    )
    server.start()

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        async with (
            http_client(url) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            resize = await session.call_tool(
                "resize_object", {"item_id": str(item.item_id), "radius": 99.0}
            )
            rotate = await session.call_tool(
                "rotate_object", {"item_id": str(item.item_id), "angle": 90.0}
            )
            body.resize_error = resize.isError  # type: ignore[attr-defined]
            body.rotate_error = rotate.isError  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    assert body.resize_error is True  # type: ignore[attr-defined]
    assert body.rotate_error is True  # type: ignore[attr-defined]
    # And the scene is untouched — a rejected write must not half-apply.
    assert item.radius == 30.0
    assert item.rotation_angle == 0.0
    assert view.command_manager.can_undo is False


def test_set_species_and_set_parent_bed_end_to_end(canvas: Any, qtbot: Any) -> None:
    """US-D2.3 over the real MCP transport.

    Added after a senior-review finding: both D2.3 tools were reachable only
    in-process, so nothing exercised their WriteResult(**result) construction or
    their token gate over the wire — the exact gap the resize/rotate transport
    tests were written to close for D2.2.
    """
    view = canvas
    scene = view.scene()
    bed = RectangleItem(500, 500, 400, 300, object_type=ObjectType.RAISED_BED)
    plant = CircleItem(2000.0, 2000.0, 25.0, object_type=ObjectType.PERENNIAL)
    scene.addItem(bed)
    scene.addItem(plant)
    # Assert the SCENE CENTRE, not pos: set_species resizes the footprint to
    # the species' mature size, and set_radius_centered holds the scene centre
    # while pos necessarily moves with the rect origin. pos would fail here
    # for a reason that has nothing to do with the link change under test.
    plant_centre_before = plant.mapToScene(plant.rect().center())

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
            spec = await session.call_tool(
                "set_species",
                {"item_id": str(plant.item_id), "species": "Tomato"},
            )
            link = await session.call_tool(
                "set_parent_bed",
                {"item_id": str(plant.item_id), "bed_id": str(bed.item_id)},
            )
            body.species = spec.structuredContent  # type: ignore[attr-defined]
            body.link = link.structuredContent  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    species = body.species  # type: ignore[attr-defined]
    link = body.link  # type: ignore[attr-defined]
    assert species["action"] == "set_species"
    assert species["species_key"] == "Solanum lycopersicum"
    assert link["action"] == "set_parent_bed"
    assert link["bed_membership_changed"] is True
    assert link["new_parent_bed_id"] == str(bed.item_id)
    # The plant sits far outside the bed, so the link is valid but not geometric.
    assert link["link_is_geometric"] is False
    # A link change must not move the plant.
    plant_centre_after = plant.mapToScene(plant.rect().center())
    assert plant_centre_after.x() == pytest.approx(plant_centre_before.x())
    assert plant_centre_after.y() == pytest.approx(plant_centre_before.y())
    assert plant.parent_bed_id == bed.item_id

    view.command_manager.undo()
    assert plant.parent_bed_id is None


def test_unauthenticated_species_and_parent_bed_are_rejected(
    canvas: Any, qtbot: Any
) -> None:
    """The ADR-036 double gate covers the D2.3 tools too.

    Senior-review finding: the equivalent test existed for resize/rotate only,
    so a D2.3 tool that forgot its _require_write_auth call would have passed
    every other test in this file.
    """
    view = canvas
    scene = view.scene()
    bed = RectangleItem(500, 500, 400, 300, object_type=ObjectType.RAISED_BED)
    plant = CircleItem(600.0, 600.0, 25.0, object_type=ObjectType.PERENNIAL)
    scene.addItem(bed)
    scene.addItem(plant)

    server = AgentApiServer(
        _providers(view), port=_free_port(), write_token=TOKEN, writes_enabled=True
    )
    server.start()

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        async with (
            http_client(url) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            spec = await session.call_tool(
                "set_species", {"item_id": str(plant.item_id), "species": "Tomato"}
            )
            link = await session.call_tool(
                "set_parent_bed",
                {"item_id": str(plant.item_id), "bed_id": str(bed.item_id)},
            )
            body.species_error = spec.isError  # type: ignore[attr-defined]
            body.link_error = link.isError  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    assert body.species_error is True  # type: ignore[attr-defined]
    assert body.link_error is True  # type: ignore[attr-defined]
    assert plant.metadata.get("plant_species") is None
    assert plant.parent_bed_id is None
    assert view.command_manager.can_undo is False


# --- issue #338: arrange_object over the real transport ---------------------
#
# build_arrange_command (and every non-#338 caller of it) requires items to sit
# on a REAL layer -- a bare item constructed without layer_id (as every other
# test in this file does) is deliberately excluded from stacking (see
# ui/canvas/arrange.py's eligibility filter), so these tests give both
# rectangles the scene's active layer explicitly.


def _add_overlapping_rects(scene: Any) -> tuple[Any, Any]:
    """Two overlapping GARDEN_BED rectangles on the scene's active layer.

    Added in order rect_a then rect_b, so rect_a starts at the BACK (lower
    stacking rank) and rect_b at the FRONT -- the shape every arrange test
    below needs to flip.
    """
    layer_id = scene.active_layer.id
    rect_a = RectangleItem(
        100, 100, 100, 100, object_type=ObjectType.GARDEN_BED, layer_id=layer_id
    )
    rect_b = RectangleItem(
        150, 150, 100, 100, object_type=ObjectType.GARDEN_BED, layer_id=layer_id
    )
    scene.addItem(rect_a)
    scene.addItem(rect_b)
    assert list(scene._normalized_layer_order(layer_id)) == [rect_a, rect_b]
    return rect_a, rect_b


def test_unauthenticated_arrange_is_rejected(canvas: Any, qtbot: Any) -> None:
    view = canvas
    scene = view.scene()
    rect_a, _rect_b = _add_overlapping_rects(scene)
    layer_id = rect_a.layer_id
    before_order = list(scene._normalized_layer_order(layer_id))

    server = AgentApiServer(
        _providers(view), port=_free_port(), write_token=TOKEN, writes_enabled=True
    )
    server.start()

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        async with (
            http_client(url) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            call = await session.call_tool(
                "arrange_object",
                {"item_id": str(rect_a.item_id), "action": "bring_to_front"},
            )
            body.is_error = call.isError  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    assert body.is_error is True  # type: ignore[attr-defined]
    assert list(scene._normalized_layer_order(layer_id)) == before_order
    assert view.command_manager.can_undo is False


def test_arrange_object_bring_to_front_end_to_end(canvas: Any, qtbot: Any) -> None:
    """US-338: an authenticated arrange_object call on the BACK item of two
    overlapping rects flips their z order, in exactly one undo step."""
    view = canvas
    scene = view.scene()
    rect_a, rect_b = _add_overlapping_rects(scene)
    layer_id = rect_a.layer_id

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
                "arrange_object",
                {"item_id": str(rect_a.item_id), "action": "bring_to_front"},
            )
            body.result = call.structuredContent  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    result = body.result  # type: ignore[attr-defined]
    assert result["action"] == "arrange"
    assert result["stack_index"] == 1
    # rect_a is now the FRONT item of the two -- the z order flipped.
    assert list(scene._normalized_layer_order(layer_id)) == [rect_b, rect_a]
    assert rect_a.zValue() > rect_b.zValue()

    assert view.command_manager.can_undo
    view.command_manager.undo()
    assert list(scene._normalized_layer_order(layer_id)) == [rect_a, rect_b]
    assert view.command_manager.can_undo is False


def test_arrange_object_second_identical_call_refuses(canvas: Any, qtbot: Any) -> None:
    """Once at the front, a second bring_to_front is a no-op refusal that
    pushes nothing to the undo stack -- the first call's step is the only one."""
    view = canvas
    scene = view.scene()
    rect_a, _rect_b = _add_overlapping_rects(scene)

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
            first = await session.call_tool(
                "arrange_object",
                {"item_id": str(rect_a.item_id), "action": "bring_to_front"},
            )
            second = await session.call_tool(
                "arrange_object",
                {"item_id": str(rect_a.item_id), "action": "bring_to_front"},
            )
            body.first_error = first.isError  # type: ignore[attr-defined]
            body.second_error = second.isError  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    assert body.first_error is not True  # type: ignore[attr-defined]
    assert body.second_error is True  # type: ignore[attr-defined]
    # The first call pushed exactly one undo step; the refused second pushed none.
    assert view.command_manager.can_undo
    view.command_manager.undo()
    assert view.command_manager.can_undo is False


# --- US-D2.4: layer tools over the real transport ----------------------------
#
# Read -> write -> undo over a real MCP client, per the issue's acceptance
# criteria: list_layers exposes ids, create_layer adds at the top AND activates
# (so the ids round-trip into set_object_layer), and Ctrl+Z restores the
# object's ORIGINAL layer. The fixture above supplies the production
# GardenPlannerApp provider graph; test_agent_api_default_on.py additionally
# pins refusal branches directly on the app for deterministic edge coverage.


def test_layer_tools_read_write_undo_end_to_end(canvas: Any, qtbot: Any) -> None:
    from uuid import UUID

    view = canvas
    scene = view.scene()
    original_layer_id = scene.active_layer.id
    rect = RectangleItem(
        100, 100, 80, 40,
        object_type=ObjectType.GENERIC_RECTANGLE,
        layer_id=original_layer_id,
    )
    scene.addItem(rect)

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
            before = await session.call_tool("list_layers", {})
            created = await session.call_tool("create_layer", {"name": "Agent Layer"})
            after = await session.call_tool("list_layers", {})
            moved = await session.call_tool(
                "set_object_layer",
                {
                    "item_id": str(rect.item_id),
                    "layer_id": created.structuredContent["layer_id"],
                },
            )
            renamed = await session.call_tool(
                "rename_layer",
                {
                    "layer_id": created.structuredContent["layer_id"],
                    "name": "Renamed Agent Layer",
                },
            )
            property_changed = await session.call_tool(
                "set_layer_property",
                {
                    "layer_id": created.structuredContent["layer_id"],
                    "opacity": 0.5,
                },
            )
            active = await session.call_tool(
                "set_active_layer", {"layer_id": str(original_layer_id)}
            )
            deleted = await session.call_tool(
                "delete_layer",
                {"layer_id": created.structuredContent["layer_id"]},
            )
            summary = await session.call_tool("get_plan_summary", {})
            body.before = before.structuredContent["result"]  # type: ignore[attr-defined]
            body.created = created.structuredContent  # type: ignore[attr-defined]
            body.after = after.structuredContent["result"]  # type: ignore[attr-defined]
            body.moved = moved.structuredContent  # type: ignore[attr-defined]
            body.moved_error = moved.isError  # type: ignore[attr-defined]
            body.renamed = renamed.structuredContent  # type: ignore[attr-defined]
            body.property_changed = property_changed.structuredContent  # type: ignore[attr-defined]
            body.active = active.structuredContent  # type: ignore[attr-defined]
            body.deleted = deleted.structuredContent  # type: ignore[attr-defined]
            body.summary_layers = summary.structuredContent["layers"]  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

# list_layers before: the scene's one default layer, active, carrying the rect.
    assert len(body.before) == 1  # type: ignore[attr-defined]
    assert body.before[0]["layer_id"] == str(original_layer_id)  # type: ignore[attr-defined]
    assert body.before[0]["is_active"] is True  # type: ignore[attr-defined]
    assert body.before[0]["object_count"] == 1  # type: ignore[attr-defined]

    # create_layer: new id, and the after-list shows it on TOP and ACTIVE.
    new_layer_id = body.created["layer_id"]  # type: ignore[attr-defined]
    assert body.created["action"] == "create_layer"  # type: ignore[attr-defined]
    assert body.created["item_id"] is None  # type: ignore[attr-defined]
    assert len(body.after) == 2  # type: ignore[attr-defined]
    assert body.after[0]["layer_id"] == new_layer_id  # type: ignore[attr-defined]
    assert body.after[0]["name"] == "Agent Layer"  # type: ignore[attr-defined]
    assert body.after[0]["is_active"] is True  # type: ignore[attr-defined]
    assert body.after[1]["is_active"] is False  # type: ignore[attr-defined]
    assert body.after[0]["z_order"] > body.after[1]["z_order"]  # type: ignore[attr-defined]

    # set_object_layer with the id that came back from create_layer: the object
    # moved, and PlanSummary.layers agrees with list_layers.
    assert body.moved_error is not True  # type: ignore[attr-defined]
    assert body.moved["action"] == "set_object_layer"  # type: ignore[attr-defined]
    assert body.moved["layer_id"] == new_layer_id  # type: ignore[attr-defined]
    assert body.renamed["action"] == "rename_layer"  # type: ignore[attr-defined]
    assert body.property_changed["action"] == "set_layer_property"  # type: ignore[attr-defined]
    assert body.active["action"] == "set_active_layer"  # type: ignore[attr-defined]
    assert body.deleted["action"] == "delete_layer"  # type: ignore[attr-defined]
    assert scene.get_layer_by_id(UUID(new_layer_id)) is None
    assert rect.layer_id == original_layer_id
    assert scene.active_layer.id == original_layer_id
    counts = {lyr["layer_id"]: lyr["object_count"] for lyr in body.summary_layers}  # type: ignore[attr-defined]
    assert counts == {str(original_layer_id): 1}

    # Five document writes (create, move, rename, property, delete) each add
    # exactly one undo entry; set_active_layer deliberately adds none.
    for _ in range(5):
        view.command_manager.undo()
    assert len(scene.layers) == 1
    assert scene.layers[0].id == original_layer_id
    assert rect.layer_id == original_layer_id
    assert view.command_manager.can_undo is False


def test_unauthenticated_layer_tools_are_rejected(canvas: Any, qtbot: Any) -> None:
    """The ADR-036 gate covers every D2.4 layer write tool, and a rejected call
    leaves the scene AND the undo stack untouched."""
    view = canvas
    scene = view.scene()
    layer_id = str(scene.active_layer.id)
    rect = RectangleItem(
        100, 100, 80, 40,
        object_type=ObjectType.GENERIC_RECTANGLE,
        layer_id=scene.active_layer.id,
    )
    scene.addItem(rect)
    layers_before = len(scene.layers)

    server = AgentApiServer(
        _providers(view), port=_free_port(), write_token=TOKEN, writes_enabled=True
    )
    server.start()

    calls = [
        ("set_object_layer", {"item_id": str(rect.item_id), "layer_id": layer_id}),
        ("create_layer", {"name": "Sneaky"}),
        ("rename_layer", {"layer_id": layer_id, "name": "Sneaky"}),
        ("delete_layer", {"layer_id": layer_id}),
        ("set_active_layer", {"layer_id": layer_id}),
        ("set_layer_property", {"layer_id": layer_id, "visible": False}),
    ]

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        async with (
            http_client(url) as (r, w, _),  # NO Authorization header
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            body.errors = [
                (await session.call_tool(name, args)).isError
                for name, args in calls
            ]  # type: ignore[attr-defined]

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()

    assert body.errors == [True] * len(calls)  # type: ignore[attr-defined]
    assert len(scene.layers) == layers_before
    assert scene.layers[0].name != "Sneaky"
    assert rect.layer_id == scene.active_layer.id
    assert rect.isVisible()
    assert view.command_manager.can_undo is False
