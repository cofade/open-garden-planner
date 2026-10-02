"""Integration test: the Agent API server stops promptly, even with a client (issue #373).

Symptom: closing the app took ~10 s, with the log

    WARNING Agent API server thread did not stop within 5.0s; ...
    ERROR   Agent API server thread 'agent-api-mcp' is STILL RUNNING ...

Root cause (measured 2026-10-02): uvicorn's graceful shutdown waits for open
connections, and an MCP client holding the SSE stream open never closes it, so
``serve()`` never returned and both joins expired. Cancelling the loop's tasks
and stopping the loop directly unwinds it. These tests drive the real server
over the real transport.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Any

from open_garden_planner.agent_api import AgentApiServer, AgentProviders
from open_garden_planner.agent_api.server import _STOP_TIMEOUT_S, SERVER_THREAD_NAME


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _unused(*_a: Any, **_k: Any) -> dict[str, Any]:
    raise AssertionError("no provider should run during a start/stop test")


def _providers() -> AgentProviders:
    return AgentProviders(
        snapshot=lambda: {},
        diagnostics=lambda: [],
        render=_unused,
        save_plan=_unused,
        new_plan=_unused,
        open_plan=_unused,
        export_pdf=_unused,
        export_dxf=_unused,
        export_csv=_unused,
        create_object=_unused,
        get_geometry=_unused,
        get_succession_plan=_unused,
        find_succession_gaps=_unused,
        suggest_succession=_unused,
        set_succession_plan=_unused,
        move_object=_unused,
        set_object_position=_unused,
        delete_object=_unused,
        resize_object=_unused,
        rotate_object=_unused,
        set_vertex=_unused,
        add_vertex=_unused,
        delete_vertex=_unused,
        set_species=_unused,
        set_parent_bed=_unused,
        arrange_object=_unused,
        set_object_layer=_unused,
        create_layer=_unused,
        rename_layer=_unused,
        delete_layer=_unused,
        set_active_layer=_unused,
        set_layer_property=_unused,
        undo=_unused,
        redo=_unused,
        get_history=_unused,
        suggest_companions=_unused,
        find_compatible_sets=_unused,
        find_sets_for_bed=_unused,
        check_placement=_unused,
    )


def _assert_no_thread_leak() -> None:
    leaked = [
        t for t in threading.enumerate() if t.name == SERVER_THREAD_NAME and t.is_alive()
    ]
    assert not leaked, f"Agent API thread leaked: {leaked}"


def test_stop_without_a_client_is_prompt(caplog: Any) -> None:
    server = AgentApiServer(_providers(), port=_free_port())
    server.start()
    try:
        with caplog.at_level(logging.WARNING, logger="open_garden_planner.agent_api.server"):
            started = time.monotonic()
            server.stop()
            elapsed = time.monotonic() - started
        assert elapsed < _STOP_TIMEOUT_S, f"stop() took {elapsed:.2f}s without a client"
        assert "did not stop within" not in caplog.text
        assert "STILL RUNNING" not in caplog.text
    finally:
        server.stop()
    _assert_no_thread_leak()


def test_stop_with_a_streaming_client_is_prompt(caplog: Any) -> None:
    """The #373 regression: an open SSE stream must not delay shutdown 10 s."""
    import httpx

    port = _free_port()
    server = AgentApiServer(_providers(), port=port)
    server.start()

    release = threading.Event()

    def _hold_stream() -> None:
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream(
                    "GET",
                    f"http://127.0.0.1:{port}/mcp",
                    headers={"Accept": "text/event-stream"},
                ) as response:
                    for _ in response.iter_lines():
                        if release.is_set():
                            break
        except Exception:  # noqa: BLE001 - the stream is expected to be cut
            pass

    holder = threading.Thread(target=_hold_stream, daemon=True)
    holder.start()
    # Let the connection establish and the SSE task come to life.
    time.sleep(1.0)

    try:
        with caplog.at_level(logging.WARNING, logger="open_garden_planner.agent_api.server"):
            started = time.monotonic()
            server.stop()
            elapsed = time.monotonic() - started
        assert elapsed < _STOP_TIMEOUT_S, (
            f"stop() took {elapsed:.2f}s with a streaming client — the #373 slow "
            "shutdown has regressed"
        )
        assert "did not stop within" not in caplog.text
        assert "STILL RUNNING" not in caplog.text
    finally:
        release.set()
        holder.join(timeout=3.0)
        server.stop()

    _assert_no_thread_leak()


def test_stop_is_idempotent(caplog: Any) -> None:
    server = AgentApiServer(_providers(), port=_free_port())
    server.start()
    server.stop()
    with caplog.at_level(logging.ERROR, logger="open_garden_planner.agent_api.server"):
        server.stop()  # second call must be a harmless no-op
    assert "STILL RUNNING" not in caplog.text
    _assert_no_thread_leak()
