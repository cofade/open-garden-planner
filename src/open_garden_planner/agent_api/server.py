"""Embedded MCP server for the Agent API (US-D1.1/D1.2/D1.3/D1.4/D1.5).

Runs an MCP streamable-HTTP server inside the running GUI on a background daemon
thread, bound to loopback only. Structural, spatial, diagnostics, and vision
(render) query tools are read-only. US-D1.4 adds four file-producing tools
(``save_plan``/``export_pdf``/``export_dxf``/``export_csv``) that write a file
to disk via the same services the GUI's File > Export/Save menu already calls
— they don't need the token auth D2's scene-mutating write tools will require
(ADR-033): ``save_plan`` persists exactly what's already on screen (the same
effect as Ctrl+S), and the export tools produce a new deliverable file without
touching the live plan. Built write-ready — later phases reuse the same
``MainThreadBridge`` boundary (via the injected ``AgentProviders`` callables)
for scene edits. US-D1.5 adds 5 read-only resources (``garden://plan``,
``garden://plan/raw``, ``garden://canvas.png``, ``garden://diagnostics``,
``garden://species``) and 2 read-analysis prompts (``audit-plan``,
``describe-garden``) — see the resource/prompt registrations at the bottom of
``build_server()`` below.

``FastMCP``/``uvicorn`` are imported lazily inside functions so importing the
``agent_api`` package costs nothing until the server is actually started (see
``agent_api/__init__.py``'s own lazy ``__getattr__`` gate, which is what keeps
importing *this* module itself deferred). ``Image`` is imported eagerly at
module level: with ``from __future__ import annotations`` in effect, every
``@mcp.tool()`` registration calls ``inspect.signature(func, eval_str=True)``
inside the SDK's ``func_metadata`` (this runs unconditionally, regardless of
``structured_output``) to resolve each stringified annotation via the
*function's own* ``__globals__`` — not the enclosing ``build_server()``
call's locals — so a tool parameter/return type must be a real module-level
name, not merely imported inside ``build_server()`` (empirically confirmed:
the latter raises ``NameError`` at server-build time). Both names live under
the same ``mcp.server.fastmcp`` package, so this costs nothing extra beyond
what ``FastMCP`` already pays the moment the server actually starts.

**Resources are simpler than tools** (verified by reading ``mcp`` 1.28.1's
``fastmcp/server.py``/``fastmcp/resources/types.py``/``lowlevel/server.py``
source directly, US-D1.5): ``@mcp.resource(uri)`` only calls plain
``inspect.signature(fn)`` (no ``eval_str``) to detect URI/function params, and
every resource here is zero-argument, so the tool-only ``NameError`` gotcha
above does not apply. ``FunctionResource.read()`` returns ``bytes`` as-is,
``str`` as-is, and anything else (a pydantic model, a plain ``dict``/``list``)
via ``pydantic_core.to_json(..., fallback=str)`` — no manual
``json.dumps``/``model_dump_json()`` needed for ``garden://plan``/``garden://
plan/raw``/``garden://diagnostics``/``garden://species``. The lowlevel
``read_resource`` handler then pattern-matches the result: ``bytes`` ->
``BlobResourceContents`` (base64-encoded, using the resource's declared
``mime_type``), ``str`` -> ``TextResourceContents``. So ``garden://
canvas.png`` just returns raw PNG ``bytes`` with ``mime_type="image/png"`` on
the decorator — **no** ``Image``/``structured_output=False`` workaround (that
was specifically a tool-dispatch quirk, D1.3). ``@mcp.prompt()`` is equally
direct: a plain ``str`` return is wrapped as
``[UserMessage(TextContent(text=result))]`` automatically.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import secrets
import socket
import threading
import time
import urllib.parse
from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp.utilities.types import Image

from open_garden_planner.agent_api import prompts as agent_prompts
from open_garden_planner.agent_api import queries
from open_garden_planner.agent_api.diagnostics import diagnostics_from_records
from open_garden_planner.agent_api.mapping import plan_summary_from_snapshot
from open_garden_planner.agent_api.providers import AgentProviders
from open_garden_planner.agent_api.render import DEFAULT_IMAGE_PX
from open_garden_planner.agent_api.schema import (
    Diagnostic,
    ExportResult,
    Measurement,
    ObjectDetail,
    ObjectRef,
    PlanSummary,
    RenderMeta,
    WriteResult,
)
from open_garden_planner.services.bundled_species_db import get_species_db

if TYPE_CHECKING:
    import uvicorn
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# --- Write-tool bearer-token gate (US-D2.0) --------------------------------
#
# Reads stay open (loopback trust, ADR-033) so D1 clients onboarded without a
# token keep working; only the scene-mutating write tools require the token. We
# therefore gate PER TOOL, not with a blanket middleware over the whole server.
#
# ``_bearer_token_middleware`` (applied to the ASGI app in ``_start_locked``)
# reads the ``Authorization: Bearer <token>`` header off every HTTP request and
# stashes the presented value in this ContextVar. Each write tool's ``async``
# handler then calls ``_require_write_auth`` — which runs in the SAME request
# task as the middleware, so it sees that request's token — BEFORE any thread
# offload. Verified end-to-end against mcp 1.28.1 with ``stateless_http=True``.
_presented_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agent_api_presented_token", default=None
)


class WriteAuthError(Exception):
    """Raised when a write tool is called without a valid bearer token.

    Surfaces to the MCP client as a failed tool call (the SDK renders a raised
    exception as an error result), telling the agent the token is missing/wrong
    without leaking the expected value.
    """


def _require_write_auth(expected_token: str | None) -> None:
    """Reject the current write-tool call unless the request bore the token.

    ``expected_token`` is the server's configured token; ``None`` means writes
    are not configured at all (defensive — the write tools aren't even
    registered in that case). Comparison is constant-time. ``secrets.
    compare_digest`` raises ``TypeError`` on non-ASCII ``str`` input — our own
    tokens are always ASCII (``secrets.token_urlsafe``), but a malformed or
    hostile token (from either the ``Authorization`` header or the ``?token=``
    query param) is untrusted input and must fail closed (a rejection), not
    propagate an unhandled exception; the ``isascii()`` guard short-circuits
    before ever calling it with unsupported input.
    """
    presented = _presented_token.get()
    valid = (
        bool(expected_token)
        and presented is not None
        and presented.isascii()
        and expected_token.isascii()
        and secrets.compare_digest(presented, expected_token)
    )
    if not valid:
        raise WriteAuthError(
            "This tool requires the Agent API write token, but this request "
            "didn't send a valid one. The reliable way to supply it is in the "
            "server URL as a query parameter — 'http://127.0.0.1:<port>/mcp"
            "?token=<token>' — which every MCP client transmits on every "
            "request. Open Garden Planner's 'Connect AI Assistant' dialog (Help "
            "menu) sets this up for you; after (re)registering, reconnect or "
            "restart the client so it picks up the new URL. (An 'Authorization: "
            "Bearer <token>' header also works for clients that reliably send "
            "it, but some — notably Claude Code on streamable-HTTP — store the "
            "header yet omit it on tool-call requests, so prefer the URL token.)"
        )


def _bearer_token_middleware(app: Any) -> Any:
    """Wrap an ASGI ``app`` so each request's presented token lands in the ContextVar.

    Pure ASGI (no Starlette ``BaseHTTPMiddleware``) so it adds no per-request
    task hop and can't interfere with the streamable-HTTP body streaming. Only
    HTTP scopes carry a token; anything else passes straight through.

    A client may present the token two ways, checked in this order:

    1. ``Authorization: Bearer <token>`` header — the conventional route.
    2. A ``?token=<token>`` URL query parameter — the fallback, because some
       MCP clients (notably Claude Code on streamable-HTTP, anthropics/
       claude-code#50464 / #28293) store a configured header but omit it on
       tool-call POSTs, while the configured URL (query string included) is
       always transmitted since it's the request target. Delivering the secret
       in the URL preserves the same threat model (a caller without the token
       still can't write) without depending on header transmission.

    The **URL query token wins** when both are present: it is the reliable
    primary channel (some clients drop configured headers on tool calls), so a
    stale legacy ``Authorization`` header left in a config can't shadow a fresh
    URL token. Validation (constant-time compare, ASCII guard) happens later in
    ``_require_write_auth``.

    A query token is **stripped from ``scope["query_string"]`` immediately**
    (whether or not a header is also present) so no downstream ASGI handler or
    access log can observe the secret (defense-in-depth; the MCP app routes on
    the path, not the query, so nothing after us needs the ``token`` param).
    """

    async def wrapped(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            header_token: str | None = None
            for key, value in scope.get("headers") or []:
                if key == b"authorization":
                    raw = value.decode("latin-1")
                    if raw[:7].lower() == "bearer ":
                        header_token = raw[7:].strip()
                    break
            query_token: str | None = None
            qs = scope.get("query_string") or b""
            if qs:
                params = urllib.parse.parse_qsl(qs.decode("latin-1"))
                for key, value in params:
                    if key == "token":
                        query_token = value
                        break
                if query_token is not None:
                    scope["query_string"] = urllib.parse.urlencode(
                        [(k, v) for k, v in params if k != "token"]
                    ).encode("latin-1")
            _presented_token.set(query_token if query_token is not None else header_token)
        await app(scope, receive, send)

    return wrapped

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
    providers: AgentProviders,
    *,
    stateless_http: bool = True,
    write_token: str | None = None,
    writes_enabled: bool = False,
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

    Args:
        writes_enabled: When true AND ``write_token`` is set, the scene-mutating
            write tools (``move_object``/``delete_object``) are registered. When
            either is missing the write tools are omitted entirely — they don't
            appear in the agent's tool list. This gating (plus the per-call
            token check) is the D2 write gate ADR-033 requires.
        write_token: The bearer token every write call must present (see
            ``_require_write_auth``). Read tools never require it.
    """
    import anyio
    from mcp.server.fastmcp import FastMCP, Image

    writes_active = bool(writes_enabled and write_token)
    write_note = (
        " move_object/delete_object edit the live plan (each is one undoable "
        "step) and require an 'Authorization: Bearer <token>' header."
        if writes_active
        else ""
    )
    mcp = FastMCP(
        "Open Garden Planner",
        instructions=(
            "Read and reason about the garden plan currently open in Open Garden "
            "Planner. Objects are addressed by a stable UUID (item_id) and "
            "located in centimetres on the canvas. Use list_objects/get_object to "
            "inspect structure, the spatial tools to locate and measure, and "
            "get_diagnostics for the plan's current warnings. save_plan/"
            "export_pdf/export_dxf/export_csv write a file to disk (the "
            "project's own .ogp, or a PDF/DXF/CSV deliverable) but do not "
            "otherwise modify the plan." + write_note
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

    # structured_output=False: Image is not pydantic-representable, so the
    # default schema-generation path crashes build_server() at decoration time
    # (verified against mcp 1.28.1). This skips schema/model creation and lets
    # _convert_to_content() flatten the list into [ImageContent, TextContent]
    # directly — this tool has no structuredContent, unlike the other 9.
    @mcp.tool(structured_output=False)
    async def render_canvas_image(
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        layers: list[str] | None = None,
        image_width_px: int = DEFAULT_IMAGE_PX,
    ) -> list[Image | RenderMeta]:
        """Render a PNG screenshot of the garden plan canvas, plus render metadata.

        Args:
            x: Left edge of the region to render, scene cm. Must be given
                together with y/width/height, or all four omitted (full canvas).
            y: Top edge of the region to render, scene cm.
            width: Region width in cm.
            height: Region height in cm.
            layers: Optional layer-name allowlist; unknown names are ignored.
                Omit to render the current live layer visibility as-is.
            image_width_px: Output width in pixels, clamped to [128, 2048];
                default 1024. Output height is derived from the region's
                aspect ratio and independently clamped to the same bounds.
        """
        region: tuple[float, float, float, float] | None
        if x is None and y is None and width is None and height is None:
            region = None
        elif x is not None and y is not None and width is not None and height is not None:
            region = (x, y, width, height)
        else:
            raise ValueError(
                "x, y, width, and height must all be given together, or all omitted."
            )
        result = await anyio.to_thread.run_sync(
            lambda: providers.render(region, layers, image_width_px)
        )
        return [
            Image(data=result["png_bytes"], format="png"),
            RenderMeta(
                region_x_cm=result["region"][0],
                region_y_cm=result["region"][1],
                region_width_cm=result["region"][2],
                region_height_cm=result["region"][3],
                image_width_px=result["image_width_px"],
                image_height_px=result["image_height_px"],
                px_per_cm=result["px_per_cm"],
                layers_rendered=result["layers_rendered"],
            ),
        ]

    @mcp.tool()
    async def save_plan(file_path: str | None = None) -> ExportResult:
        """Save the live plan to its ``.ogp`` file (Save), or to a new path (Save As).

        Args:
            file_path: Optional destination path. Omit to save to the
                currently open file — this requires a project already open,
                otherwise an error is raised (mirrors the GUI: a brand-new
                project always needs an explicit Save As first). Given a
                path, this becomes the project's file going forward, same as
                File > Save As.
        """
        result = await anyio.to_thread.run_sync(lambda: providers.save_plan(file_path))
        return ExportResult(**result)

    @mcp.tool()
    async def export_pdf(
        file_path: str | None = None,
        paper_size: Literal["A4", "A3", "Letter", "Legal"] = "A4",
        orientation: Literal["landscape", "portrait"] = "landscape",
    ) -> ExportResult:
        """Export the full garden PDF report (cover, overview, plant list, legend).

        Args:
            file_path: Optional destination path. Omit for a default name next
                to the open project (or the app's Documents folder).
            paper_size: 'A4', 'A3', 'Letter', or 'Legal'.
            orientation: 'landscape' or 'portrait'.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.export_pdf(file_path, paper_size, orientation)
        )
        return ExportResult(**result)

    @mcp.tool()
    async def export_dxf(file_path: str | None = None) -> ExportResult:
        """Export the plan to a DXF drawing (visible, non-construction items only).

        Args:
            file_path: Optional destination path. Omit for a default name next
                to the open project (or the app's Documents folder).
        """
        result = await anyio.to_thread.run_sync(lambda: providers.export_dxf(file_path))
        return ExportResult(**result)

    @mcp.tool()
    async def export_csv(
        kind: Literal["shopping_list", "harvest"] = "shopping_list",
        file_path: str | None = None,
    ) -> ExportResult:
        """Export a CSV: the shopping list, or garden-wide harvest totals.

        Args:
            kind: 'shopping_list' (plants/seeds/materials to buy) or
                'harvest' (per-species/year totals from the harvest log).
            file_path: Optional destination path. Omit for a default name next
                to the open project (or the app's Documents folder).
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.export_csv(kind, file_path)
        )
        return ExportResult(**result)

    # --- US-D2.0: scene-mutating write tools (token-gated) ------------------
    # Registered only when writes are enabled AND a token is configured. Each
    # tool checks the token first (in this async task, before the thread hop),
    # then routes through a provider that runs ONE undoable command on the Qt
    # main thread — invariants #3/#4/#13: one agent write = one Ctrl-Z step.
    if writes_active:

        @mcp.tool()
        async def move_object(item_id: str, dx: float, dy: float) -> WriteResult:
            """Move one object by a relative offset.

            Moving a bed/container/trellis carries its contained plants along.
            Moving a plant re-evaluates its bed membership afterward — crossing
            into or out of a bed reparents it. This is usually one undo step;
            it becomes two only when reparenting happens (see the result's
            children_moved/bed_membership_changed/new_parent_bed_id).

            Fails if the object (or a plant it contains) participates in a
            geometric constraint, or if it's a journal pin — neither is
            supported yet; use the app for those.

            Args:
                item_id: The object's stable UUID (from list_objects/get_object).
                dx: Horizontal offset in scene cm (+x is right).
                dy: Vertical offset in scene cm (+y is down) — the SAME frame the
                    read tools report positions in, so you can move an object
                    relative to a position you just read without flipping any axis.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.move_object(item_id, dx, dy)
            )
            return WriteResult(**result)

        @mcp.tool()
        async def delete_object(item_id: str) -> WriteResult:
            """Delete one object from the plan (one undoable step).

            Deleting a bed/container detaches its contained plants (kept, not
            deleted); a HOUSE's linked roof ridge is deleted along with it; any
            geometric constraint referencing the object is removed. Undo
            restores the object and all of the above together.

            Fails if the object is a journal pin — not supported yet.

            Args:
                item_id: The object's stable UUID (from list_objects/get_object).
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.delete_object(item_id)
            )
            return WriteResult(**result)

    # --- US-D1.5: resources + read-analysis prompts -------------------------

    @mcp.resource("garden://plan", mime_type="application/json")
    async def plan_resource() -> PlanSummary:
        """The curated plan summary — same data as get_plan_summary()."""
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return plan_summary_from_snapshot(snapshot)

    @mcp.resource("garden://plan/raw", mime_type="application/json")
    async def plan_raw_resource() -> dict[str, Any]:
        """The underlying .ogp-shaped snapshot dict, uncurated."""
        return await anyio.to_thread.run_sync(providers.snapshot)

    @mcp.resource("garden://canvas.png", mime_type="image/png")
    async def canvas_png_resource() -> bytes:
        """A PNG render of the full live canvas (no region/layer filtering)."""
        result = await anyio.to_thread.run_sync(
            lambda: providers.render(None, None, DEFAULT_IMAGE_PX)
        )
        return result["png_bytes"]

    @mcp.resource("garden://diagnostics", mime_type="application/json")
    async def diagnostics_resource() -> list[Diagnostic]:
        """The plan's current warnings — same data as get_diagnostics()."""
        records = await anyio.to_thread.run_sync(providers.diagnostics)
        return diagnostics_from_records(records)

    @mcp.resource("garden://species", mime_type="application/json")
    async def species_resource() -> list[dict[str, Any]]:
        """The bundled species database (static data — no main-thread hop needed).

        Still offloaded to a worker thread (not called inline) so the
        first-call JSON load/parse can never block the uvicorn event loop,
        matching every other resource/tool handler here.
        """
        return await anyio.to_thread.run_sync(lambda: list(get_species_db().values()))

    @mcp.prompt(name="audit-plan")
    async def audit_plan() -> str:
        """Summarise the plan's layout + diagnostics and suggest improvements."""
        # Two separate main-thread hops (benign TOCTOU): this is read-only
        # advisory text, not an atomic action — unlike render's single-hop
        # region+layers+encode, a snapshot/diagnostics pair drifting by one
        # scene edit between hops has no correctness consequence here.
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        records = await anyio.to_thread.run_sync(providers.diagnostics)
        return agent_prompts.render_audit_plan_prompt(
            plan_summary_from_snapshot(snapshot), diagnostics_from_records(records)
        )

    @mcp.prompt(name="describe-garden")
    async def describe_garden() -> str:
        """A narrative description of the garden plan for a human or agent."""
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return agent_prompts.render_describe_garden_prompt(
            plan_summary_from_snapshot(snapshot), queries.list_objects(snapshot)
        )

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
        write_token: str | None = None,
        writes_enabled: bool = False,
    ) -> None:
        self._providers = providers
        self._host = host
        self._port = port
        self._path = path if path.startswith("/") else f"/{path}"
        self._write_token = write_token
        self._writes_enabled = writes_enabled
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        """The streamable-HTTP endpoint MCP clients connect to."""
        return f"http://{self._host}:{self._port}{self._path}"

    @property
    def write_token(self) -> str | None:
        """The bearer token this server was started with, or None if writes are off.

        This — not the current settings value — is the authoritative token a
        client must present, because the running server validates the token it
        was *built* with. Regenerating the settings token without a restart
        doesn't change what this server accepts (mirrors ``url`` deriving from
        the live server, US-D1.6 round 3).
        """
        return self._write_token if self._writes_enabled else None

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

        mcp = build_server(
            self._providers,
            write_token=self._write_token,
            writes_enabled=self._writes_enabled,
        )
        mcp.settings.streamable_http_path = self._path
        # Wrap so each request's bearer token reaches the write tools' auth check
        # via the module ContextVar. Reads ignore it (loopback trust unchanged).
        app = _bearer_token_middleware(mcp.streamable_http_app())

        config = uvicorn.Config(
            app,
            host=self._host,
            port=self._port,
            log_level="warning",
            # Never write an access log: request URLs carry the write token as a
            # ?token= query param (ADR-036 URL-delivery addendum), so logging the
            # request line would persist the secret. Explicit, not merely implied
            # by the warning log level.
            access_log=False,
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
