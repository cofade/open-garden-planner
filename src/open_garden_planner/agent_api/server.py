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
from typing import TYPE_CHECKING, Any

from open_garden_planner.agent_api import queries
from open_garden_planner.agent_api.diagnostics import diagnostics_from_records
from open_garden_planner.agent_api.mapping import plan_summary_from_snapshot
from open_garden_planner.agent_api.providers import AgentProviders
from open_garden_planner.agent_api.schema import (
    Diagnostic,
    Measurement,
    ObjectDetail,
    ObjectRef,
    PlanSummary,
)

if TYPE_CHECKING:
    import uvicorn
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

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
    providers: AgentProviders, *, stateless_http: bool = True
) -> FastMCP:
    """Create a configured ``FastMCP`` instance with the read/query tools registered.

    Decoupled from the GUI: the only dependency is ``providers``, a bundle of
    callables returning read-only plain data about the live plan (in the app each
    hops to the Qt main thread via ``MainThreadBridge``).

    Every Qt-touching tool is ``async def`` and offloads its provider via
    ``anyio.to_thread.run_sync`` — see the :class:`MainThreadBridge` house rule:
    the SDK runs *sync* handlers inline on the event loop, so a sync handler that
    blocks on a main-thread hop would stall the uvicorn loop.

    Coordinates throughout are the plan's native scene frame (centimetres, origin
    top-left, +x right, +y down). Read-only ``raw=True`` switches a tool from the
    curated agent schema to the underlying ``.ogp`` serialiser dict(s).
    """
    import anyio
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "Open Garden Planner",
        instructions=(
            "Read and reason about the garden plan currently open in Open Garden "
            "Planner. Objects are addressed by a stable UUID (item_id) and "
            "located in centimetres on the canvas. Use list_objects/get_object to "
            "inspect structure, the spatial tools to locate and measure, and "
            "get_diagnostics for the plan's current warnings. This server is "
            "read-only."
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
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return plan_summary_from_snapshot(snapshot)

    @mcp.tool()
    async def list_objects(
        type: str | None = None,
        layer: str | None = None,
        parent: str | None = None,
        raw: bool = False,
    ) -> list[dict[str, Any]] | list[ObjectRef]:
        """List the plan's top-level objects, newest filters applied.

        Args:
            type: Optional filter — an ObjectType name ('TREE', 'RAISED_BED'), a
                category ('bed', 'plant', 'shape'), or a geometry kind ('circle').
            layer: Optional layer name or layer id to restrict to.
            parent: Optional bed/container id — only its direct children.
            raw: If true, return the underlying serialiser dicts instead of the
                curated schema.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return queries.list_objects(
            snapshot, type=type, layer=layer, parent=parent, raw=raw
        )

    @mcp.tool()
    async def get_object(
        item_id: str, raw: bool = False
    ) -> dict[str, Any] | ObjectDetail | None:
        """Return full detail for one object by its UUID, or null if not found.

        Args:
            item_id: The object's stable UUID.
            raw: If true, return the underlying serialiser dict instead of the
                curated schema.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return queries.get_object(snapshot, item_id, raw=raw)

    @mcp.tool()
    async def objects_in_region(
        x: float, y: float, width: float, height: float, raw: bool = False
    ) -> list[dict[str, Any]] | list[ObjectRef]:
        """Objects whose bounding box intersects a rectangle (scene cm).

        Args:
            x: Left edge of the query rectangle, in scene cm.
            y: Top edge of the query rectangle, in scene cm.
            width: Rectangle width in cm.
            height: Rectangle height in cm.
            raw: If true, return serialiser dicts instead of the curated schema.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return queries.objects_in_region(snapshot, x, y, width, height, raw=raw)

    @mcp.tool()
    async def objects_in(
        parent_id: str, raw: bool = False
    ) -> list[dict[str, Any]] | list[ObjectRef]:
        """Objects contained in a bed/container (its direct children).

        Args:
            parent_id: UUID of the bed/container.
            raw: If true, return serialiser dicts instead of the curated schema.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return queries.objects_in(snapshot, parent_id, raw=raw)

    @mcp.tool()
    async def plants_in_bed(
        bed_id: str, raw: bool = False
    ) -> list[dict[str, Any]] | list[ObjectRef]:
        """Plant objects contained in the given bed/container.

        Args:
            bed_id: UUID of the bed/container.
            raw: If true, return serialiser dicts instead of the curated schema.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return queries.plants_in_bed(snapshot, bed_id, raw=raw)

    @mcp.tool()
    async def nearest_objects(
        x: float,
        y: float,
        k: int = 5,
        type: str | None = None,
        raw: bool = False,
    ) -> list[dict[str, Any]] | list[ObjectRef]:
        """The k objects whose centres are closest to a point (scene cm).

        Args:
            x: Point X in scene cm.
            y: Point Y in scene cm.
            k: Maximum number of objects to return (closest first).
            type: Optional type/category/geometry filter (see list_objects).
            raw: If true, return serialiser dicts instead of the curated schema.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return queries.nearest_objects(snapshot, x, y, k=k, type=type, raw=raw)

    @mcp.tool()
    async def measure_distance(id_a: str, id_b: str) -> Measurement | None:
        """Centre-to-centre distance between two objects, or null if either is unknown.

        Args:
            id_a: UUID of the first object.
            id_b: UUID of the second object.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return queries.measure_distance(snapshot, id_a, id_b)

    @mcp.tool()
    async def get_diagnostics(kind: str | None = None) -> list[Diagnostic]:
        """Report the plan's current warnings (the same ones shown as canvas badges).

        Covers companion conflicts, spacing overlaps, soil/pH mismatches,
        container capacity overruns, and crop-rotation conflicts.

        Args:
            kind: Optional filter — one of 'companion_conflict', 'spacing_overlap',
                'soil_mismatch', 'capacity_overrun', 'crop_rotation'.
        """
        records = await anyio.to_thread.run_sync(providers.diagnostics)
        return diagnostics_from_records(records, kind=kind)

    return mcp


class AgentApiServer:
    """Lifecycle wrapper around an embedded MCP streamable-HTTP server."""

    def __init__(
        self,
        providers: AgentProviders,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        path: str = "/mcp",
    ) -> None:
        self._providers = providers
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

        mcp = build_server(self._providers)
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
