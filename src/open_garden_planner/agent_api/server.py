"""Embedded MCP server for the Agent API (US-D1.1 spike).

Runs an MCP streamable-HTTP server inside the running GUI on a background daemon
thread, bound to loopback only. Read-only in this spike: a single tool,
``get_plan_summary``. Built write-ready — later phases reuse the same
``MainThreadBridge`` boundary (via the injected ``snapshot_provider``) for edits.

``mcp``/``uvicorn`` are imported lazily inside functions so importing the
package costs nothing until the server is actually started.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from open_garden_planner.agent_api.mapping import plan_summary_from_snapshot
from open_garden_planner.agent_api.schema import PlanSummary

if TYPE_CHECKING:
    import uvicorn
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

SnapshotProvider = Callable[[], dict[str, Any]]

# Max time start() blocks the caller waiting for uvicorn to report "listening".
_READY_TIMEOUT_S = 5.0
# Max time stop() waits to join the server thread. Callers should abort the
# MainThreadBridge first (see app wiring) so an in-flight tool handler cannot
# stall this join on a main-thread hop that will never be serviced during close.
_STOP_TIMEOUT_S = 5.0


class PortInUseError(RuntimeError):
    """Raised when the configured Agent API port is already bound."""

    def __init__(self, port: int) -> None:
        super().__init__(f"Port {port} is already in use")
        self.port = port


def build_server(
    snapshot_provider: SnapshotProvider, *, stateless_http: bool = True
) -> FastMCP:
    """Create a configured ``FastMCP`` instance with the read tools registered.

    Decoupled from the GUI: the only dependency is ``snapshot_provider``, a
    callable returning a read-only ``.ogp``-shaped dict of the live plan (in the
    app it hops to the Qt main thread via ``MainThreadBridge``).
    """
    import anyio
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "Open Garden Planner",
        instructions=(
            "Read and reason about the garden plan currently open in Open "
            "Garden Planner. This spike exposes a single read tool."
        ),
        stateless_http=stateless_http,
        log_level="WARNING",
    )

    @mcp.tool()
    async def get_plan_summary() -> PlanSummary:
        """Summarise the garden plan currently open in the app.

        Returns object counts (beds, plants, other shapes), canvas size, layer
        names, the file name, and whether there are unsaved changes.
        """
        # ASYNC handler (see MainThreadBridge house rule): the SDK runs sync
        # handlers inline on the event loop, so offload snapshot_provider — which
        # blocks on a hop to the Qt main thread — to a worker thread, keeping the
        # loop free.
        snapshot = await anyio.to_thread.run_sync(snapshot_provider)
        return plan_summary_from_snapshot(snapshot)

    return mcp


class AgentApiServer:
    """Lifecycle wrapper around an embedded MCP streamable-HTTP server."""

    def __init__(
        self,
        snapshot_provider: SnapshotProvider,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        path: str = "/mcp",
    ) -> None:
        self._snapshot_provider = snapshot_provider
        self._host = host
        self._port = port
        self._path = path if path.startswith("/") else f"/{path}"
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        """The streamable-HTTP endpoint MCP clients connect to."""
        return f"http://{self._host}:{self._port}{self._path}"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the server (idempotent). Raises ``PortInUseError`` if bound."""
        with self._lock:
            if self.is_running:
                return
            self._check_port_free()
            self._start_locked()

    def _check_port_free(self) -> None:
        # Pre-bind so we can surface a precise error instead of uvicorn dying on
        # a background thread. 127.0.0.1 only — never 0.0.0.0 (loopback policy).
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((self._host, self._port))
        except OSError as exc:
            raise PortInUseError(self._port) from exc
        finally:
            probe.close()

    def _start_locked(self) -> None:
        import uvicorn

        mcp = build_server(self._snapshot_provider)
        mcp.settings.streamable_http_path = self._path
        app = mcp.streamable_http_app()

        config = uvicorn.Config(
            app,
            host=self._host,
            port=self._port,
            log_level="warning",
            lifespan="on",
        )
        server = uvicorn.Server(config)
        # No signal-handler handling needed: uvicorn's serve() installs them via
        # capture_signals(), which is a no-op off the main thread — and we run
        # the event loop on a worker thread.
        self._server = server

        thread = threading.Thread(target=self._run, args=(server,),
                                  name="agent-api-mcp", daemon=True)
        self._thread = thread
        thread.start()

        # Block briefly until uvicorn is listening (or the thread dies), so the
        # caller knows the endpoint is reachable on return.
        deadline = time.monotonic() + _READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if not thread.is_alive():
                self._thread = None
                self._server = None
                raise RuntimeError("Agent API server failed to start")
            if getattr(server, "started", False):
                return
            time.sleep(0.02)
        logger.warning("Agent API server did not report ready within %.0fs",
                       _READY_TIMEOUT_S)

    @staticmethod
    def _run(server: uvicorn.Server) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        except Exception:  # noqa: BLE001 - log and let the thread end
            logger.exception("Agent API server crashed")
        finally:
            # Drain any tasks left pending by the ASGI stack (e.g. sse-starlette's
            # shutdown watcher) so the loop closes without "Task was destroyed".
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

    def stop(self, timeout: float = _STOP_TIMEOUT_S) -> None:
        """Stop the server (idempotent), joining the background thread."""
        with self._lock:
            server = self._server
            thread = self._thread
            if server is not None:
                server.should_exit = True
            if thread is not None:
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning(
                        "Agent API server thread did not stop within %.1fs",
                        timeout,
                    )
            self._thread = None
            self._server = None
