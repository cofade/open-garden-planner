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

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.agent_api import (
    AgentApiServer,
    AgentProviders,
    MainThreadBridge,
)
from open_garden_planner.core.commands import (
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
)
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

    def _create(
        object_type: str,
        x: float,
        y: float,
        width: float | None,
        height: float | None,
        radius: float | None,
        name: str | None,
        species: str | None,
    ) -> dict[str, Any]:
        """Stand-in mirroring the real provider's shape (one CreateItemCommand).

        Like _move/_delete above, this pins the TRANSPORT + auth contract, not
        the GUI orchestration -- that lives in test_agent_api_default_on.py,
        which drives the real GardenPlannerApp.
        """
        item = CircleItem(x, y, radius or 30.0, object_type=ObjectType[object_type])
        cmd = CreateItemCommand(scene, item)
        view.command_manager.execute(cmd)
        return {
            "item_id": str(item.item_id),
            "action": "create",
            "undo_description": cmd.description,
            "x": x,
            "y": y,
        }

    def _resize(
        item_id: str,
        width: float | None,
        height: float | None,
        radius: float | None,
    ) -> dict[str, Any]:
        """Stand-in mirroring the real provider's shape (one ResizeItemCommand).

        Like _move/_delete, this pins the TRANSPORT + auth contract; the GUI
        orchestration (centre preservation, the shared apply path, refusals)
        lives in test_agent_api_default_on.py against the real app.
        """
        from open_garden_planner.core.commands import ResizeItemCommand
        from open_garden_planner.ui.canvas.geometry_apply import (
            apply_rect_like_geometry,
            build_circle_resize,
        )

        item = _resolve(item_id)
        diameter = 2 * (radius if radius is not None else 30.0)
        old_geometry, new_geometry = build_circle_resize(
            item, diameter, keep_center=True
        )
        cmd = ResizeItemCommand(
            item, old_geometry, new_geometry, apply_rect_like_geometry
        )
        view.command_manager.execute(cmd)
        return {
            "item_id": item_id,
            "action": "resize",
            "undo_description": cmd.description,
            "radius": diameter / 2.0,
        }

    def _rotate(item_id: str, angle: float, relative: bool) -> dict[str, Any]:
        """Stand-in mirroring the real provider's shape (one RotateItemCommand)."""
        from open_garden_planner.core.commands import RotateItemCommand
        from open_garden_planner.ui.canvas.geometry_apply import apply_rotation

        item = _resolve(item_id)
        current = float(item.rotation_angle)
        new_angle = (angle + current if relative else angle) % 360.0
        cmd = RotateItemCommand(item, current, new_angle, apply_rotation)
        view.command_manager.execute(cmd)
        return {
            "item_id": item_id,
            "action": "rotate",
            "undo_description": cmd.description,
            "rotation_deg": new_angle,
        }

    def _set_species(
        item_id: str, species: str | None, apply_database_size: bool
    ) -> dict[str, Any]:
        """Stand-in mirroring the real provider (one ApplySpeciesCommand)."""
        from open_garden_planner.services.bundled_species_db import (
            lookup_species,
            merge_calendar_data,
        )
        from open_garden_planner.ui.plant_species_assignment import (
            apply_species_to_item,
        )

        item = _resolve(item_id)
        record = lookup_species(species or "")
        if record is None:
            raise ValueError(f"No species named {species!r}")
        species_dict = merge_calendar_data(dict(record))
        apply_species_to_item(
            item, species_dict, confirm=lambda: apply_database_size
        )
        return {
            "item_id": item_id,
            "action": "set_species",
            "undo_description": "Apply species data",
            "species_key": species_dict.get("scientific_name"),
        }

    def _set_parent_bed(item_id: str, bed_id: str | None) -> dict[str, Any]:
        """Stand-in mirroring the real provider (one SetParentBedCommand)."""
        from open_garden_planner.core.commands import SetParentBedCommand

        plant = _resolve(item_id)
        bed = _resolve(bed_id) if bed_id else None
        new_parent = bed.item_id if bed is not None else None
        link_is_geometric = (
            bool(bed.contains(bed.mapFromScene(
                plant.mapToScene(plant.boundingRect().center())
            )))
            if bed is not None
            else None
        )
        cmd = SetParentBedCommand(scene, plant, plant.parent_bed_id, new_parent)
        view.command_manager.execute(cmd)
        return {
            "item_id": item_id,
            "action": "set_parent_bed",
            "undo_description": cmd.description,
            "bed_membership_changed": True,
            "new_parent_bed_id": str(new_parent) if new_parent else None,
            "link_is_geometric": link_is_geometric,
        }

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
        # Keyword-only, matching the CreateObjectProvider protocol: server.py
        # calls this by keyword so a width/height transposition can't happen.
        create_object=lambda **kw: bridge.run_on_main(lambda: _create(**kw)),
        move_object=lambda item_id, dx, dy: bridge.run_on_main(
            lambda: _move(item_id, dx, dy)
        ),
        delete_object=lambda item_id: bridge.run_on_main(lambda: _delete(item_id)),
        # Keyword-only, matching the ResizeObjectProvider protocol, for the
        # same reason create_object is: width/height/radius are all float|None.
        resize_object=lambda **kw: bridge.run_on_main(lambda: _resize(**kw)),
        rotate_object=lambda item_id, angle, relative: bridge.run_on_main(
            lambda: _rotate(item_id, angle, relative)
        ),
        set_species=lambda item_id, species, apply_database_size: bridge.run_on_main(
            lambda: _set_species(item_id, species, apply_database_size)
        ),
        set_parent_bed=lambda item_id, bed_id: bridge.run_on_main(
            lambda: _set_parent_bed(item_id, bed_id)
        ),
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
