"""Integration test: the Agent API server stops promptly, even with a client (issue #373).

Symptom: closing the app took ~10 s, with the log

    WARNING Agent API server thread did not stop within 5.0s; ...
    ERROR   Agent API server thread 'agent-api-mcp' is STILL RUNNING ...

Root cause (measured 2026-10-02): uvicorn's graceful shutdown waits for open
connections, and an MCP client holding the SSE stream open never closes it, so
``serve()`` never returned and both joins expired. ``stop()`` now escalates:
a graceful ``should_exit`` first, then (after ``_GRACEFUL_STOP_S``) cancelling the
loop's tasks and stopping the loop. These tests drive the real server
over the real transport.

**Why the thresholds are not `_STOP_TIMEOUT_S`.** The defect is a 10 s
shutdown; the fix is sub-second. Asserting ``elapsed < 5.0`` sits exactly on the
join timeout and flakes under a loaded full-suite run (observed: this file
passed standalone and in a slice, then failed three tests in an 18-minute run).
Measured stop times: ~0.2 s with no client, ~1.3-2.2 s with a client streaming
(the graceful bound plus the forced unwind), and 10.02 s for the regression. ``_PROMPT_SHUTDOWN_MAX_S``
therefore sits at 4.0 s — well above the ~1 s a healthy stop takes even on a busy
machine, and well below the ~10 s a regression costs. A failure names both
numbers so a genuine regression and a slow runner are distinguishable.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from typing import Any

from open_garden_planner.agent_api import AgentApiServer, AgentProviders

#: A healthy stop is ~0.2 s idle and ~1.3-2.2 s with a streaming client (the
#: graceful bound is part of that); a #373 regression is ~10 s.
#: 4.0 s cleanly separates them without sitting on the 5 s join timeout.
_PROMPT_SHUTDOWN_MAX_S = 4.0



from tests.integration.agent_task_soil_stubs import TASK_SOIL_STUBS


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
        **TASK_SOIL_STUBS,
        get_history=_unused,
        suggest_companions=_unused,
        find_compatible_sets=_unused,
        find_sets_for_bed=_unused,
        check_placement=_unused,
    )


def _assert_own_server_thread_stopped(server: AgentApiServer) -> None:
    """The server's OWN thread is gone — not a global scan.

    A global ``threading.enumerate()`` scan for ``SERVER_THREAD_NAME`` couples
    this file to every other test that builds a server: a leak elsewhere (the
    integration conftest only *warns* on one) would fail these tests even though
    their own server stopped cleanly. Assert on this server's thread handle.
    """
    from open_garden_planner.agent_api.server import SERVER_THREAD_NAME

    thread = server._thread  # noqa: SLF001 - the handle is what stop() clears
    assert thread is None, (
        f"stop() left its own server thread handle set ({SERVER_THREAD_NAME})"
    )


def test_stop_without_a_client_is_prompt(caplog: Any) -> None:
    server = AgentApiServer(_providers(), port=_free_port())
    server.start()
    try:
        with caplog.at_level(logging.WARNING):
            started = time.monotonic()
            server.stop()
            elapsed = time.monotonic() - started
        assert elapsed < _PROMPT_SHUTDOWN_MAX_S, (
            f"stop() took {elapsed:.2f}s without a client "
            f"(limit {_PROMPT_SHUTDOWN_MAX_S}s; a #373 regression is ~10s)"
        )
        assert "did not stop within" not in caplog.text
        assert "STILL RUNNING" not in caplog.text
        # A graceful close must be QUIET. Cancelling uvicorn's lifespan task
        # unconditionally logged a CancelledError traceback at ERROR on every
        # stop (senior review, PR #381) — the very console surface #373 was
        # filed from — so assert on ANY logger, not two substrings.
        noisy = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert not noisy, (
            "a graceful stop() logged at ERROR: "
            + "; ".join(f"{r.name}: {r.getMessage()[:80]}" for r in noisy)
        )
    finally:
        server.stop()
    _assert_own_server_thread_stopped(server)


def _wait_for_established_stream(server: AgentApiServer, timeout: float = 10.0) -> bool:
    """Wait until the server has a live SSE task, not just a TCP connection.

    Polling the loop's task list is the real precondition: ``force_exit`` alone
    failed because the MCP *session/SSE tasks* keep the loop alive, so a stream
    that has connected but not yet spawned those tasks would not exercise the
    defect. A fixed sleep is a race (review P2-6) — a slow machine could reach
    ``stop()`` before the task existed, making the test pass vacuously.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        loop = server._loop  # noqa: SLF001 - the handle the fix stores
        if loop is not None and not loop.is_closed():
            for task in asyncio.all_tasks(loop):
                name = task.get_name()
                coro = str(task.get_coro())
                if "sse" in name.lower() or "sse" in coro.lower() or "EventSource" in coro:
                    return True
        time.sleep(0.05)
    return False


def test_stop_with_a_streaming_client_is_prompt(caplog: Any) -> None:
    """The #373 regression: an open SSE stream must not delay shutdown 10 s."""
    import httpx

    port = _free_port()
    server = AgentApiServer(_providers(), port=port)
    server.start()

    release = threading.Event()

    def _hold_stream() -> None:
        try:
            with (
                httpx.Client(timeout=None) as client,
                client.stream(
                    "GET",
                    f"http://127.0.0.1:{port}/mcp",
                    headers={"Accept": "text/event-stream"},
                ) as response,
            ):
                for _ in response.iter_lines():
                    if release.is_set():
                        break
        except Exception:  # noqa: BLE001 - the stream is expected to be cut
            pass

    holder = threading.Thread(target=_hold_stream, daemon=True)
    holder.start()
    # Wait for the SSE task itself, not a fixed delay (review P2-6).
    assert _wait_for_established_stream(server), (
        "the SSE stream never established a task; the test cannot exercise #373"
    )

    try:
        with caplog.at_level(logging.WARNING, logger="open_garden_planner.agent_api.server"):
            started = time.monotonic()
            server.stop()
            elapsed = time.monotonic() - started
        assert elapsed < _PROMPT_SHUTDOWN_MAX_S, (
            f"stop() took {elapsed:.2f}s with a streaming client (limit "
            f"{_PROMPT_SHUTDOWN_MAX_S}s) — the #373 slow shutdown has regressed "
            "(a regression costs ~10s)"
        )
        assert "did not stop within" not in caplog.text
        assert "STILL RUNNING" not in caplog.text
        # The forced path ends run_until_complete with a deliberate RuntimeError;
        # if the _forced_stop flag stops working it is logged as a crash.
        assert "crashed" not in caplog.text
    finally:
        release.set()
        holder.join(timeout=3.0)
        server.stop()

    _assert_own_server_thread_stopped(server)


def test_stop_is_idempotent(caplog: Any) -> None:
    server = AgentApiServer(_providers(), port=_free_port())
    server.start()
    server.stop()
    with caplog.at_level(logging.ERROR, logger="open_garden_planner.agent_api.server"):
        server.stop()  # second call must be a harmless no-op
    assert "STILL RUNNING" not in caplog.text
    _assert_own_server_thread_stopped(server)
