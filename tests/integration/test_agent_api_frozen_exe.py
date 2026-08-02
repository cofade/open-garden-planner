"""Regression pin for issue #291 — the Agent API must start with no stdout.

A PyInstaller **windowed** build (``console=False``, which is what we ship) sets
``sys.stdout`` and ``sys.stderr`` to ``None``. uvicorn's DEFAULT logging config
calls ``sys.stdout.isatty()`` while ``dictConfig`` builds its formatter, so
``uvicorn.Config.__init__`` raised ``ValueError: Unable to configure formatter
'default'`` and the embedded MCP server never started -- in every released exe,
since US-D1.1.

It was invisible three ways over: running from source has a real stdout, a
``console=True`` diagnostic build has a real stdout, and the failure was
swallowed by ``_start_agent_api``'s ``except Exception`` into a
``logger.exception`` that had no handler to write to (with ``sys.stderr`` None,
even ``logging.lastResort`` is mute). The pre-merge exe gate only asserts the
app survives 8 seconds, which a silently-dead subsystem passes.

These tests reproduce the exact condition in-process. ``test_plain_uvicorn_...``
is the POSITIVE CONTROL: it proves the simulated environment really does trigger
the bug, so the passing start-up test below it means something.
"""

from __future__ import annotations

import socket
import sys
from typing import Any

import pytest

from open_garden_planner.agent_api import AgentApiServer, AgentProviders


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _unused(*_a: Any, **_k: Any) -> dict[str, Any]:
    raise AssertionError("no provider should run during a start/stop test")


def _providers() -> AgentProviders:
    """Minimal bundle — these tests only exercise server lifecycle."""
    return AgentProviders(
        snapshot=lambda: {},
        diagnostics=lambda: [],
        render=_unused,
        save_plan=_unused,
        export_pdf=_unused,
        export_dxf=_unused,
        export_csv=_unused,
        move_object=_unused,
        delete_object=_unused,
    )


def test_plain_uvicorn_config_really_does_break_without_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POSITIVE CONTROL for the test below.

    Feeds the detector the exact defect it exists to catch: uvicorn's DEFAULT
    log config under a windowed build's ``sys.stdout is None``. If uvicorn ever
    stops doing ``sys.stdout.isatty()`` at config time, this test fails and the
    next test stops being meaningful -- which is precisely when we want to know.
    """
    import uvicorn

    async def _app(scope: Any, receive: Any, send: Any) -> None:  # pragma: no cover
        return None

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    with pytest.raises(ValueError, match="formatter"):
        uvicorn.Config(_app, host="127.0.0.1", port=_free_port())


def test_server_starts_when_stdout_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real ``AgentApiServer`` must start in a windowed frozen build.

    Deliberately drives the REAL server rather than re-asserting the
    ``uvicorn.Config`` kwargs: duplicating them here would keep passing if
    ``server.py`` later dropped ``log_config=None``.
    """
    port = _free_port()
    server = AgentApiServer(_providers(), port=port)

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    try:
        server.start()
        assert server.is_running, (
            "Agent API did not start with sys.stdout=None — the windowed frozen "
            "build condition from issue #291 has regressed"
        )
        # Actually reachable, not merely flagged as running.
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(2.0)
        try:
            assert probe.connect_ex(("127.0.0.1", port)) == 0, (
                f"nothing listening on {port} despite is_running"
            )
        finally:
            probe.close()
    finally:
        server.stop()
