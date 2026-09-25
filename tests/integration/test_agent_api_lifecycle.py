"""Issue #365: ``new_plan`` / ``open_plan`` over the REAL MCP transport.

Why this file exists separately from ``test_agent_api_default_on.py`` (which
covers the same tools at the main-thread-body level): both tools originally
returned ``ExportResult(**result)`` while their providers returned a dict with
no ``format`` key and a ``None`` ``file_path`` against a ``str`` field. So both
raised a pydantic ``ValidationError`` on **every successful call over the
wire** — while all 22 body-level tests passed, because the body never builds
the result model. Only the transport crosses that boundary.

The lesson is general, and is why the check below is structural rather than
per-tool: a tool's declared return model is a contract, and testing the
provider is not the same as testing the tool.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.agent_api.server import AgentApiServer
from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings

_TOKEN = "lifecycle-transport-token-abcdef123456"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _drive(server: AgentApiServer, body: Any, result: dict[str, Any]) -> None:
    async def run() -> None:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client as http_client

        await body((http_client, ClientSession, server.url))

    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - surfaced to the assertion
        result["error"] = exc
    finally:
        result["done"] = True


def _run(server: AgentApiServer, body: Any, qtbot: Any) -> None:
    result: dict[str, Any] = {}
    threading.Thread(
        target=_drive, args=(server, body, result), name="mcp-lifecycle-test-client"
    ).start()
    qtbot.waitUntil(lambda: result.get("done", False), timeout=20000)
    assert result.get("error") is None, result.get("error")


@pytest.fixture()
def app(qtbot: Any, monkeypatch: Any) -> Any:
    """A real GardenPlannerApp with the welcome dialog suppressed.

    Uses the app's OWN ``_build_agent_providers()`` rather than a stub, because
    the bug lived in the seam between the real provider and the tool's declared
    return model — a stub would have hidden it a second time.
    """
    get_settings().show_welcome_on_startup = False
    # The agent path does its own dirty check and never calls this GUI
    # confirmation; stub it so a stray call cannot raise a modal in a test.
    monkeypatch.setattr(
        GardenPlannerApp, "_confirm_discard_changes", lambda _self: True, raising=False
    )
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    yield win
    win._stop_agent_api()


def _server(win: Any) -> AgentApiServer:
    server = AgentApiServer(
        win._build_agent_providers(),
        port=_free_port(),
        write_token=_TOKEN,
        writes_enabled=True,
    )
    server.start()
    return server


def _caller(result: dict[str, Any]) -> Any:
    """A body that makes one authenticated tool call and captures the payload."""

    async def body(ctx: Any) -> None:
        http_client, ClientSession, url = ctx
        headers = {"Authorization": f"Bearer {_TOKEN}"}
        async with (
            http_client(url, headers=headers) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            call = await session.call_tool(result["tool"], result["args"])
            assert not call.isError, f"{result['tool']} returned an error: {call.content}"
            result["payload"] = call.structuredContent

    return body


def test_new_plan_returns_a_valid_payload_over_the_transport(
    app: Any, qtbot: Any
) -> None:
    """The P0 regression. `new_plan` used to raise ValidationError here on
    every SUCCESSFUL call, because the plan was already replaced before the
    model rejected the result."""
    server = _server(app)
    try:
        result = {"tool": "new_plan", "args": {"width_cm": 900.0, "height_cm": 700.0}}
        _run(server, _caller(result), qtbot)
    finally:
        server.stop()

    payload = result["payload"]
    assert payload["width_cm"] == pytest.approx(900.0)
    assert payload["height_cm"] == pytest.approx(700.0)
    # A new plan has never been saved, so there is no file - and the model must
    # accept that rather than demanding a string.
    assert payload["file_path"] is None
    assert payload["was_dirty"] is False
    assert app.canvas_scene.width_cm == pytest.approx(900.0)


def test_open_plan_returns_a_valid_payload_over_the_transport(
    app: Any, qtbot: Any, tmp_path: Path
) -> None:
    """Same contract for `open_plan`, whose result carries the loaded path."""
    target = tmp_path / "transport.ogp"
    app._do_agent_new_plan(900.0, 700.0, True)
    app._do_agent_create_object("TREE", 10.0, 10.0, None, None, None, None, None)
    from open_garden_planner.agent_api.exports import save_plan_file

    save_plan_file(
        app.canvas_scene, app._project_manager, app._soil_service, str(target)
    )
    assert target.exists()
    # Saving cleared the dirty flag, so make it dirty AGAIN. This is what makes
    # the `was_dirty` assertion below meaningful rather than trivially False.
    app._do_agent_create_object("TREE", 200.0, 200.0, None, None, None, None, None)
    assert app._project_manager.is_dirty is True

    server = _server(app)
    try:
        result = {
            "tool": "open_plan",
            "args": {"file_path": str(target), "force": True},
        }
        _run(server, _caller(result), qtbot)
    finally:
        server.stop()

    payload = result["payload"]
    assert payload["file_path"] == str(target)
    assert payload["width_cm"] == pytest.approx(900.0)
    # Reported from BEFORE the load, which resets the flag — this is the one
    # fact an agent needs when it passed force=true and may have just discarded
    # work. Read after the load it would always be False.
    assert payload["was_dirty"] is True
    assert len(app.canvas_scene.items()) == 1  # back to the saved state


def test_lifecycle_tools_refuse_a_dirty_plan_over_the_transport(
    app: Any, qtbot: Any
) -> None:
    """The refusal is reported as a tool error, not a success payload — and the
    document survives it."""
    app._do_agent_create_object("TREE", 10.0, 10.0, None, None, None, None, None)
    before = len(app.canvas_scene.items())

    server = _server(app)
    try:
        seen: dict[str, Any] = {}

        async def body(ctx: Any) -> None:
            http_client, ClientSession, url = ctx
            headers = {"Authorization": f"Bearer {_TOKEN}"}
            async with (
                http_client(url, headers=headers) as (r, w, _),
                ClientSession(r, w) as session,
            ):
                await session.initialize()
                call = await session.call_tool("new_plan", {})
                seen["is_error"] = call.isError
                seen["text"] = "".join(
                    getattr(c, "text", "") for c in call.content
                )

        _run(server, body, qtbot)
    finally:
        server.stop()

    assert seen["is_error"] is True
    assert "unsaved changes" in seen["text"]
    assert len(app.canvas_scene.items()) == before
    assert app._project_manager.is_dirty is True
