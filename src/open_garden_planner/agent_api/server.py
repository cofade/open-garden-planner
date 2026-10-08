"""Embedded MCP server for the Agent API (US-D1.1–D1.6, US-D2.0–D2.6).

Runs an MCP streamable-HTTP server inside the running GUI on a background daemon
thread, bound to loopback only. Structural, spatial, diagnostics, and vision
(render) query tools are read-only. US-D1.4 adds four file-producing tools
(``save_plan``/``export_pdf``/``export_dxf``/``export_csv``) that write a file
to disk via the same services the GUI's File > Export/Save menu already calls
— they don't need the token auth D2's scene-mutating write tools use
(ADR-033): ``save_plan`` persists exactly what's already on screen (the same
effect as Ctrl+S), and the export tools produce a new deliverable file without
touching the live plan. The D2 write surface and its global ``undo``/``redo``
providers reuse the same ``MainThreadBridge`` boundary (via the injected
``AgentProviders`` callables) for every scene edit. US-D1.5 adds read-only
resources (``garden://plan``,
``garden://plan/raw``, ``garden://canvas.png``, ``garden://diagnostics``,
``garden://species``, ``garden://plant-lists``) and 2 read-analysis prompts (``audit-plan``,
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
import contextlib
import contextvars
import logging
import secrets
import socket
import threading
import time
import urllib.parse
from typing import TYPE_CHECKING, Annotated, Any, Literal

from mcp.server.fastmcp.utilities.types import Image
from pydantic import Field, StrictFloat, StrictInt

from open_garden_planner.agent_api import creates as agent_creates
from open_garden_planner.agent_api import prompts as agent_prompts
from open_garden_planner.agent_api import queries
from open_garden_planner.agent_api.diagnostics import diagnostics_from_records
from open_garden_planner.agent_api.mapping import (
    layers_from_snapshot,
    plan_summary_from_snapshot,
)
from open_garden_planner.agent_api.providers import AgentProviders
from open_garden_planner.agent_api.render import DEFAULT_IMAGE_PX
from open_garden_planner.agent_api.schema import (
    AmendmentPlanView,
    CompanionSuggestion,
    CompatibleSet,
    Diagnostic,
    ExportResult,
    GeometryResult,
    HistoryResult,
    HistoryState,
    Layer,
    ManualTaskResult,
    Measurement,
    ObjectDetail,
    ObjectRef,
    PlacementCheck,
    PlanLifecycleResult,
    PlanSummary,
    RenderMeta,
    SoilMismatchBedsView,
    SoilStatusListView,
    SuccessionGap,
    SuccessionPlanView,
    SuccessionSuggestion,
    TaskCalendarView,
    TaskListView,
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
# reads the token off every HTTP request (from the ``Authorization: Bearer``
# header or a ``?token=`` URL query param) and stashes it in this ContextVar.
# Each write tool's ``async``
# handler then calls ``_require_write_auth`` — which runs in the SAME request
# task as the middleware, so it sees that request's token — BEFORE any thread
# offload. Verified end-to-end against mcp 1.28.1 with ``stateless_http=True``.
_presented_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agent_api_presented_token", default=None
)

# ``float | None = None`` cannot distinguish an omitted optional argument from
# an explicit JSON ``null``.  Some JSON stacks normalize non-finite numbers
# (Infinity/NaN) to null before Pydantic sees them; treating that as “use the
# default” would turn a hostile offset into a valid callout.  A private,
# JSON-serializable sentinel preserves omission while allowing the create
# handler to reject explicit null before it reaches the provider.  The public
# schema therefore exposes a number (not null) and hides the internal default.
_UNSET_OFFSET: Any = "__open_garden_planner_omitted_offset__"


def _hide_schema_default(schema: dict[str, Any]) -> None:
    """Keep an omission sentinel out of the published MCP input schema."""
    schema.pop("default", None)


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
# How long stop() lets uvicorn shut down GRACEFULLY (should_exit only: lifespan
# shutdown, connection drain) before escalating to cancelling the loop's tasks.
# A healthy stop with no client measures ~0.2 s; only a client holding an SSE
# stream open (issue #373) ever outlasts this. Escalating instead of always
# forcing keeps the common path free of the CancelledError tracebacks that
# cancelling uvicorn's lifespan task logs at ERROR.
_GRACEFUL_STOP_S = 1.0
# Grace period AFTER the main join expires. `should_exit` asks uvicorn to finish
# gracefully; it then still has to unwind the ASGI stack and close its loop, and
# on a loaded machine that can take longer than the join allows. Without this,
# stop() returned with the thread STILL RUNNING and merely logged a warning —
# and a uvicorn loop left running keeps its sockets and its Qt main-thread bridge
# alive, which is how an unrelated Qt test segfaulted at interpreter teardown on
# CI (the crash stack named this module's `_run`). Bounded, and only reached when
# the first join already expired.
_STOP_GRACE_S = 5.0
# The thread name, so a leak is identifiable in a thread dump and assertable.
SERVER_THREAD_NAME = "agent-api-mcp"


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
    host: str = "127.0.0.1",
    port: int = 8765,
) -> FastMCP:
    """Create a configured ``FastMCP`` instance with the read/query tools registered.

    Decoupled from the GUI: the only dependency is ``providers``, a bundle of
    callables returning plain data or applying one command to the live plan (in
    the app each hops to the Qt main thread via ``MainThreadBridge``).

    Every Qt-touching tool is ``async def`` and offloads its provider via
    ``anyio.to_thread.run_sync`` — see the :class:`MainThreadBridge` house rule:
    the SDK runs *sync* handlers inline on the event loop, so a sync handler that
    blocks on a main-thread hop would stall the uvicorn loop.

    Coordinates throughout are the plan's native scene frame: centimetres, CAD
    **Y-up** (ADR-002) — origin at the south-west (bottom-left) corner, +x is
    east/right and **+y is north/up** (a larger y is further north / higher on
    the canvas). Read-only ``raw=True`` switches a tool from the curated agent
    schema to the underlying ``.ogp`` serialiser dict(s).

    Args:
        writes_enabled: When true AND ``write_token`` is set, the scene-mutating
            write tools (``create_object``/``move_object``/
            ``set_object_position``/``delete_object``/``resize_object``/
            ``rotate_object``/``set_vertex``/``add_vertex``/``delete_vertex``/
            ``set_species``/``set_parent_bed``/``arrange_object``, the US-D2.4 layer tools
            ``set_object_layer``/``create_layer``/``rename_layer``/
            ``delete_layer``/``set_active_layer``/``set_layer_property``, and
            the global history tools ``undo``/``redo``) are registered. When
            either is missing the write tools are omitted entirely — they don't
            appear in the agent's tool list. This gating (plus the per-call
            token check) is the D2 write gate ADR-033 requires.
        write_token: The bearer token every write call must present (see
            ``_require_write_auth``). Read tools never require it.
        host: The loopback address the server binds. Used to build the
            Host/Origin allow-lists below (#396).
        port: The port the server binds. Same purpose.
    """
    import anyio
    from mcp.server.fastmcp import FastMCP, Image
    from mcp.server.transport_security import TransportSecuritySettings

    writes_active = bool(writes_enabled and write_token)
    write_note = (
        " scene-mutating tools (including move_object/delete_object and "
        "undo/redo) edit the live plan (the history is the same global LIFO "
        "stack used by the GUI) and require the write token, delivered in the "
        "server URL as '?token=<token>' "
        "(the 'Connect AI Assistant' dialog sets this up for a client)."
        if writes_active
        else ""
    )
    # Host/Origin validation (DNS-rebinding protection, #396).
    #
    # The Agent API is loopback-only and reads are unauthenticated by design
    # (ADR-033 loopback trust), so the ONLY thing stopping a web page from
    # reaching it via DNS rebinding is that a browser sends the page's Host and
    # Origin. The SDK auto-enables this for loopback hosts from mcp 1.23.0, and
    # the declared floor (>=1.12) admitted SDKs that leave it OFF — measured: on
    # mcp 1.22.0 a crafted `Host: evil.example` initialize returned HTTP 200
    # with a full result, where 1.30.0 answers 421. That made the protection a
    # property of whichever wheel resolved at build time rather than of the
    # product, so it is now configured explicitly here and asserted by
    # tests/integration/test_agent_api_dns_rebinding.py.
    #
    # The allow-lists name the exact loopback origins this server can be reached at:
    # the bind address, 127.0.0.1 and localhost on the bound port (a browser client
    # and the "Connect AI Assistant" dialog both use the loopback URL), plus the
    # IPv6 loopback literal the SDK matches as a string. Deliberately NO ``:*``
    # port wildcard: the port is fixed for the life of the server, so a wildcard
    # would only widen the barrier to any port on loopback, which is the breadth
    # the SDK's own default has and the reason this is configured here at all.
    # ``dict.fromkeys`` de-duplicates because ``host`` defaults to 127.0.0.1.
    loopback_hosts = dict.fromkeys(
        [f"{host}:{port}", f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"]
    )
    loopback_origins = dict.fromkeys(
        [
            f"http://{host}:{port}",
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            f"http://[::1]:{port}",
        ]
    )
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(loopback_hosts),
        allowed_origins=list(loopback_origins),
    )
    mcp = FastMCP(
        "Open Garden Planner",
        transport_security=transport_security,
        instructions=(
            "Read and reason about the garden plan currently open in Open Garden "
            "Planner. Objects are addressed by a stable UUID (item_id) and "
            "located in centimetres on the canvas. Use list_objects/get_object to "
            "inspect structure, get_geometry for stable low-level vertices, curves, "
            "extents and constraints, the spatial tools to locate and measure, and "
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

        Objects are listed bottom→top in stacking order (layer order first,
        then position within the layer) — the same order ObjectRef.stack_index
        is computed from. (get_diagnostics is NOT in this order.)

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

        The result's stack_index is its 0-based position within its layer,
        bottom→top, as displayed — compare it only against other objects on
        the same layer.

        Args:
            item_id: The object's stable UUID.
            raw: If true, return the underlying serialiser dict instead of the
                curated schema.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return queries.get_object(snapshot, item_id, raw=raw)

    @mcp.tool()
    async def get_geometry(item_id: str) -> GeometryResult:
        """Return live low-level geometry and constraints for one object.

        This is the read side of the D2.6 escape hatches. Coordinates and
        points use the same centimetre, CAD Y-up scene frame as every other
        Agent API tool. Polygon/polyline vertices are the vertices' CURRENT
        scene positions (after item rotation), not the pre-rotation points in
        the raw ``.ogp`` serializer.

        The result includes the object's centre, native dimensions/radius,
        curve or leader data when applicable, vertex capabilities, and every
        referencing constraint in deterministic order. If ``is_constrained`` is
        true, geometry writes deliberately refuse rather than run the GUI's
        multi-item live solver: inspect ``constraints`` and ask the user to
        remove or edit them in the app.

        Reads remain unauthenticated under the documented loopback model and
        never mutate the plan.

        Args:
            item_id: Stable UUID of a top-level object.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.get_geometry(item_id=item_id)
        )
        return GeometryResult(**result)

    @mcp.tool()
    async def objects_in_region(
        x: float, y: float, width: float, height: float, raw: bool = False
    ) -> list[dict[str, Any]] | list[ObjectRef]:
        """Objects whose bounding box intersects a rectangle (scene cm).

        Listed bottom→top in stacking order (layer order first, then position
        within the layer), same as list_objects.

        Args:
            x: West (minimum-x) edge of the query rectangle, in scene cm.
            y: South (minimum-y) edge of the query rectangle, in scene cm; the
                rectangle extends north to y + height (the scene is Y-up).
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
        container capacity overruns, crop-rotation conflicts, and objects lying
        entirely outside the plan canvas (invisible in the app). Unlike
        list_objects/objects_in_region/get_object, these are NOT listed in
        stacking order.

        Args:
            kind: Optional filter — one of 'companion_conflict', 'spacing_overlap',
                'soil_mismatch', 'capacity_overrun', 'crop_rotation',
                'outside_canvas'.
        """
        records = await anyio.to_thread.run_sync(providers.diagnostics)
        return diagnostics_from_records(records, kind=kind)

    @mcp.tool()
    async def get_history() -> HistoryState:
        """Report the current undo/redo stack state (US-D2.7, read-only).

        Lets an agent assert the D2 undo contract — "one call = one undo step"
        and "refusals leave the stack untouched" — without reading the GUI's
        Edit menu. This is the same global LIFO stack Ctrl+Z / undo / redo
        use; calling this tool never mutates it.

        Returns:
            HistoryState with undo_depth, redo_depth, next_undo_text, and
            next_redo_text (the same strings the GUI's Edit menu shows).
        """
        result = await anyio.to_thread.run_sync(providers.get_history)
        return HistoryState(**result)

    # --- US-D3.1: domain-intelligence tools (read-only) ----------------------

    @mcp.tool()
    async def suggest_companions(
        species_key: str,
        exclude_antagonists_of: list[str] | None = None,
    ) -> list[CompanionSuggestion]:
        """Suggest companion plants for a species, ranked by benefit (US-D3.1).

        Returns a ranked list of beneficial companions with reasons and
        source attribution. Antagonists of the excluded species are filtered
        out. Read-only; no token required.

        Each suggestion carries `species_key` (a stable machine key) and
        `name` (a DISPLAY STRING in the user's current UI language). Branch on
        `species_key`, never on `name`.

        Args:
            species_key: The species to find companions for (common name,
                scientific name, or alias).
            exclude_antagonists_of: Optional list of species keys whose
                antagonists should be excluded (e.g. plants already in the bed).
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.suggest_companions(species_key, exclude_antagonists_of)
        )
        return [CompanionSuggestion(**item) for item in result]

    @mcp.tool()
    async def find_compatible_sets(
        candidates: list[str],
        size: int = 3,
        must_include: list[str] | None = None,
    ) -> list[CompatibleSet]:
        """Find mutually compatible sets of plants among candidates (US-D3.1).

        Uses Bron–Kerbosch over the beneficial companion graph, with
        antagonist edges as hard exclusions. Each set is a maximal clique of
        mutually beneficial, non-antagonistic species. Read-only; no token
        required.

        Args:
            candidates: Species keys to consider. Capped at 60 PLUS anything in
                must_include, which is never dropped by the cap.
            size: Minimum set size, 2–5. This is a FLOOR, not an exact target:
                a request for 4 or 5 legitimately returns nothing when the graph
                has no clique that large.
            must_include: Species keys that must be in every returned set
                (e.g. plants already in the bed). NOTE: requiring a whole bed's
                plants makes the result empty for most real beds — use
                find_sets_for_bed, which ranks by bed coverage instead.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.find_compatible_sets(candidates, size, must_include)
        )
        return [CompatibleSet(**item) for item in result]

    @mcp.tool()
    async def find_sets_for_bed(bed_plants: list[str], size: int = 3) -> dict[str, Any]:
        """Compatible planting sets for the plants ALREADY in a bed, ranked.

        This is the tool to reach for when the question is "what should I plant
        in this bed?" rather than "which plants go together?". It is NOT
        find_compatible_sets with must_include=bed_plants: maximal-clique search
        only emits maximal sets, so requiring every bed plant to appear in every
        set returns nothing for most real beds (measured: 91% of two-plant beds,
        100% of three-plant beds) — which is exactly the situation the caller is
        trying to resolve.

        Builds a palette from the given plants plus their beneficial companions,
        finds the mutually compatible sets, and ranks them by how many of
        ``bed_plants`` each one already satisfies.

        A bed-internal antagonism is reported in ``conflicts`` and is the only
        thing that blocks keeping everything. ``uncovered`` lists plants in no
        returned set and makes NO claim about why — a plant absent because no
        third mutual partner exists is not a clash.

        Args:
            bed_plants: Species keys of the plants currently in the bed.
            size: Preferred set size, 2–5. The search steps DOWN from this
                rather than returning nothing when no set of exactly this size
                exists; ``searched_size`` reports what was actually used.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.find_sets_for_bed(bed_plants, size)
        )
        return {
            "sets": result["sets"],
            "conflicts": result["conflicts"],
            "uncovered": result["uncovered"],
            "bed_plants": result["bed_plants"],
            "searched_size": result["searched_size"],
        }

    @mcp.tool()
    async def check_placement(
        species_key: str,
        bed_id: str,
        bed_plants: list[str] | None = None,
    ) -> PlacementCheck:
        """Check a species against the plants already in a bed (US-D3.1).

        Reports which of the bed's plants are antagonistic or beneficial to the
        species, read from the same companion database the GUI's Companion panel
        uses. Read-only; no token required.

        NOT CHECKED HERE: spacing and soil. Both come back as null on purpose —
        the full diagnostics are available via get_diagnostics, and reporting a
        fabricated True would be worse than reporting nothing.

        Args:
            species_key: The species to check.
            bed_id: The bed to check against. It is RESOLVED, so an id that
                names no bed reports overall='unknown_bed' rather than looking
                like an empty bed.
            bed_plants: Optional override for the bed's contents. Omit it to
                read the bed's real plants from the plan; pass it only to ask
                about a hypothetical arrangement.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.check_placement(species_key, bed_id, bed_plants)
        )
        return PlacementCheck(**result)

    @mcp.tool()
    async def get_succession_plan(
        bed_id: str,
        year: int | None = None,
        today: str | None = None,
    ) -> SuccessionPlanView:
        """A bed's succession plan: what is in it, and what is next (US-D3.2).

        Succession is several sequential crops in ONE bed within a season. This
        returns the bed's slots sorted by date, which slot is running on
        ``today``, which comes next, and the season segments so you can reason
        in seasons rather than raw dates.

        The four season segments are 'early_spring', 'late_spring', 'summer' and
        'fall'. They are frost-relative (computed from the plan's geo-location)
        when the plan HAS one; otherwise they fall back to approximate
        calendar-month boundaries and the response says so twice — check
        ``coverage`` and ``segments_are_fallback`` before treating a segment date
        as authoritative.

        A bed with no plan reports ``has_plan: false``. That is different from an
        empty plan, which reports ``has_plan: true`` with no entries. Read-only;
        no token required.

        Args:
            bed_id: The bed's stable UUID. It must be a soil-capable bed
                (GARDEN_BED, RAISED_BED, CONTAINER, CONTAINER_ROUND or
                WALL_PLANTER) — a TRELLIS is refused, because it holds no soil.
            year: Plan year. Defaults to the stored plan's year, else the
                current year.
            today: ISO 'YYYY-MM-DD' reference date for current_entry/next_entry.
                Defaults to the real today; pass it explicitly to make a
                reasoning step reproducible, and the response echoes it back as
                ``reference_date``.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.get_succession_plan(bed_id, year, today)
        )
        return SuccessionPlanView(**result)

    @mcp.tool()
    async def find_succession_gaps(
        bed_id: str,
        year: int | None = None,
        today: str | None = None,
    ) -> list[SuccessionGap]:
        """When is this bed free? The uncovered ranges of its growing season.

        This is the question you actually want answered ("what can I put in bed 3
        after the garlic comes out in July?"), so it is a tool rather than
        something every client computes differently. Each range carries its
        season label and an inclusive day count, and the ranges are returned in
        season order.

        A slot whose dates are unparseable covers NOTHING, so a malformed entry
        shows up as a gap rather than silently reading as a full bed.

        Feed a range straight into suggest_succession's ``gap_start``/``gap_end``.
        Read-only; no token required.

        Args:
            bed_id: The bed's stable UUID (soil-capable types only).
            year: Plan year; defaults to the stored plan's year.
            today: ISO 'YYYY-MM-DD' reference date, used only to default the plan
                year when ``year`` is omitted. The gaps are a property of the
                plan and the season segments, not of this date, so each gap
                carries no timestamp of its own.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.find_succession_gaps(bed_id, year, today)
        )
        return [SuccessionGap(**item) for item in result]

    @mcp.tool()
    async def suggest_succession(
        bed_id: str,
        gap_start: str,
        gap_end: str,
        candidates: list[str] | None = None,
    ) -> list[SuccessionSuggestion]:
        """Rank crops for one succession gap in this bed.

        Filters candidates two ways, in order: a crop whose botanical family
        the bed already used EARLIER IN THIS PLAN, or whose family is inside the
        3-year crop-rotation cooldown, is excluded; and what survives is ranked by
        whether its days-to-maturity fits the gap. A crop antagonistic to a
        neighbour overlapping the window is excluded too, but see the limit
        noted below before reading anything into that.

        ``candidates`` is a list of species names/keys to consider — leave it out
        and nothing is suggested (an unrestricted search over 118 species would
        be noise). Read the bundled species via the garden://species resource or
        get_object payloads to build the list.

        HONEST LIMITS, so you do not over-read the result:

        * ``fits_window: false`` means the crop is too slow for the gap OR its
          maturity is unknown. It does NOT mean the crop was rejected — check
          ``days_to_maturity`` to tell those apart. An unknown maturity is never
          reported as a fit.
        * An empty list means every candidate was excluded, which is a real
          answer: widen ``candidates`` or shorten the gap.
        * A gap is uncovered BY CONSTRUCTION, so nothing in this bed's own plan
          overlaps it and there is normally no concurrent neighbour to exclude.
          The antagonism filter only bites when a slot from OUTSIDE this plan
          overlaps the window; when none does it excludes nothing, and the
          absence of a rejection is not evidence that a candidate is
          antagonist-free.
        * ``family`` empty means no rotation claim could be made for that crop,
          not that it is rotation-safe.

        The ``reasons`` strings are English and NOT localised (MCP output is an
        English API contract, ADR-033) — they are for a human reading the
        result and must not be parsed. Branch on ``species_key``, ``family``,
        ``days_to_maturity`` and ``fits_window``.

        Read-only; no token required.

        Args:
            bed_id: The bed's stable UUID (soil-capable types only). Supplies
                the plan the exclusions are computed against.
            gap_start: ISO 'YYYY-MM-DD' start of the window to fill — usually a
                range straight from find_succession_gaps.
            gap_end: ISO 'YYYY-MM-DD' end of the window.
            candidates: Species names or keys to consider. Omit for none.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.suggest_succession(
                bed_id, gap_start, gap_end, candidates
            )
        )
        return [SuccessionSuggestion(**item) for item in result]

    @mcp.tool()
    async def get_tasks(
        from_date: str | None = None,
        to_date: str | None = None,
        source: str | None = None,
        bed_id: str | None = None,
        species_key: str | None = None,
        include_dismissed: bool = False,
        today: str | None = None,
    ) -> TaskListView:
        """The garden's task calendar for a date window (US-D3.3).

        This is the whole task engine - seven generators over the live plan -
        reachable for the first time. It answers "what should I do this week?".

        Defaults to today +/- 30 days. Pass `today` to make the answer
        reproducible: the same inputs always return the same tasks, and an
        omitted `today` means the real current date.

        The default mirrors the GUI's actionable reminders. An explicit date
        window generates the complete schedule for its calendar years before
        filtering, including past/future tasks with null urgency. Propagation
        uses the GUI's calculator, seed-packet data and stored overrides.

        Each task carries the generator's own fields PLUS two the engine does not
        store: `urgency`, computed at render time from the dates and the
        reference date ('today', 'overdue', 'this_week', 'upcoming', or null when
        not actionable), and `status`, read from the same store the Tasks tab
        uses ('open', 'done', 'snoozed', 'dismissed' or 'archived').

        TWO KINDS OF FIELD, and the difference matters:

        * `task_id`, `task_type` and `source` are stable English machine keys and
          part of this API's contract. Branch on these.
        * `title` and `notes` are DISPLAY STRINGS in the user's current UI
          language, because the generators build them through Qt's translation
          layer. They are NOT part of the English contract. Never parse them,
          and never match on them — under a German UI they are German.

        `coverage` says what the answer is built on:

        * 'full' - the plan has a location, so frost dates exist and the
          calendar and propagation tasks were generated.
        * 'no_frost_dates' - the plan has NO geo-location, so there are no
          frost dates and NO calendar or propagation tasks exist. Every other
          task kind (manual, succession, soil, frost) is still returned. This is
          NOT 'there is nothing to do' — the engine could not compute the
          planting calendar. Say so rather than reporting an empty week.

        Generated tasks cannot be edited or deleted: they are derived state
        rebuilt on every call. Use add_manual_task for new work, and tell the
        user to dismiss or complete a task in the Tasks tab — a status change is
        not an undoable agent write, so it is deliberately not exposed here.

        Read-only; no token required.

        Args:
            from_date: ISO window start. Defaults to `today` minus 30 days.
            to_date: ISO window end. Defaults to `today` plus 30 days.
            source: Keep only this source: 'calendar', 'propagation',
                'succession', 'soil', 'frost' or
                'manual'. Both soil generators use 'soil'; distinguish them
                by task_type ('soil_amendment' or 'soil_mismatch'). An unknown
                value is refused, not ignored.
            bed_id: Keep only tasks linked to this bed.
            species_key: Keep only tasks for this canonical species key.
            include_dismissed: Show dismissed tasks, each with its status.
            today: ISO reference date for urgency and status. Defaults to the
                real current date.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.get_tasks(
                from_date, to_date, source, bed_id, species_key, include_dismissed, today
            )
        )
        return TaskListView(**result)

    @mcp.tool()
    async def get_task_calendar(year: int | None = None, today: str | None = None) -> TaskCalendarView:
        """Month-by-month overview of the task load (US-D3.3).

        Use this first when you want to see how busy the year is before pulling
        the individual tasks — `get_tasks` for the detail, this for the shape.

        A task is counted in EVERY month its window touches, so a three-week
        task spanning a month boundary appears in both. `total` therefore counts
        task-months, not distinct tasks.

        Generates the COMPLETE requested calendar year rather than only today's
        actionable reminders. A cross-year window is clipped to this year;
        urgency still uses `today`, not an invented date in the requested year.

        `actionable` counts the tasks whose urgency is not null — the ones worth
        reading. A task with no urgency is not urgent and is not in that count,
        but it is still in `total` and in `by_urgency` under 'none'.

        `coverage` carries the same meaning as in `get_tasks`: 'no_frost_dates'
        means the plan has no location, so no calendar or propagation tasks could
        be generated. It never means the year is empty.

        As in `get_tasks`, `by_source` and `by_urgency` keys are stable English
        machine keys.

        Read-only; no token required.

        Args:
            year: Four-digit year. Defaults to the reference date's year.
            today: ISO reference date. Defaults to the real current date.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.get_task_calendar(year, today)
        )
        return TaskCalendarView(**result)

    @mcp.tool()
    async def get_soil_status(bed_id: str | None = None, today: str | None = None) -> SoilStatusListView:
        """One bed's soil readings and what they mean (US-D3.4).

        Answers the question `get_diagnostics` cannot: it tells you a plant
        disagrees with its soil, and this tells you the actual pH and NPK, how
        healthy each is, and when the soil was last tested.

        `record_source` says WHICH record answered, and you must relay it:

        * 'bed' - the bed's own most recent test.
        * 'global' - the PLAN-WIDE default's most recent test, because this bed
          has none of its own. These readings are a plan-wide assumption, not a
          measurement of this bed.
        * 'none' - neither exists; `coverage` is 'no_soil_test'.

        `coverage: 'no_soil_test'` means UNTESTED, never 'the soil is fine'. There
        is no such thing as a passing grade for a missing test.

        `beds` holds one result for the requested bed. Omit `bed_id` to get
        every soil-capable bed in the plan, sorted by UUID. Each result carries
        its own `record_source` and `coverage`; no beds means an empty list.

        `levels` is keyed by the stable nutrient key 'n', 'p', 'k', 'ca', 'mg',
        's'. Each carries the recorded kit level and its derived `health_level`
        ('unknown', 'good', 'fair', 'poor'). A null level means not tested, and
        its health_level is 'unknown' for N/P/K — a gap in the data, not a poor
        reading. Ca/Mg/S carry null health_level because the engine defines no
        rating for those secondaries, even when a kit level was recorded.

        `overall_health_level` is the WORST non-unknown level across pH and the
        N/P/K, and 'unknown' only when all four inputs are unknown. It does not
        rate Ca/Mg/S.

        `is_test_overdue` is the app's own seasonal staleness check. When it is
        true, say the reading is old rather than recommending against it.

        Read-only; no token required.

        Args:
            bed_id: Soil-capable bed UUID, or omit for every bed.
            today: ISO reference date for the overdue check. Defaults to the
                real current date.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.get_soil_status(bed_id, today)
        )
        return SoilStatusListView(**result)

    @mcp.tool()
    async def recommend_amendments(bed_id: str, today: str | None = None) -> AmendmentPlanView:
        """What to add to this bed's soil, and how much (US-D3.4).

        The engine the GUI's own recommendation dialog uses, returned in full:
        for each amendment, its stable id, the amount in grams for THIS bed, the
        nutrient or property it acts on, and the reading it moves.

        TWO KINDS OF FIELD:

        * `amendment_id`, `target_kind` and `fixes` are stable English machine
          keys. Branch on these.
        * `display_name` is a DISPLAY STRING in the user's current UI language.
          It is NOT part of this API's contract — never match on it.

        `quantity_g` is already scaled to the bed's area, so do not scale it
        again. A recommendation of 0 g means the engine considered the substance
        and decided none is needed; it is not a rounding artefact.

        `coverage: 'no_soil_test'` with an empty list means the bed is UNTESTED,
        not that it needs nothing.

        An empty `recommendations` list with `coverage: 'ok'` means the engine
        recommends no amendment from the readings it can assess. It does not
        prove healthy soil: existing lab ppm readings are not converted to kit
        levels. Check get_soil_status and report unknown readings honestly.

        Read-only; no token required.

        Args:
            bed_id: Soil-capable bed UUID.
            today: ISO reference date. Defaults to the real current date.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.recommend_amendments(bed_id, today)
        )
        return AmendmentPlanView(**result)

    @mcp.tool()
    async def get_soil_mismatches(bed_id: str | None = None, today: str | None = None) -> SoilMismatchBedsView:
        """Which plants in a bed disagree with its soil, and on what (US-D3.4).

        `get_diagnostics` already reports a soil-mismatch FLAG per bed; this
        returns the individual conflicting plants and the numbers behind those flags. The two agree by
        construction — if they ever disagree, that is a bug worth reporting.

        `reason_codes` are stable English machine keys, and they are what you
        should reason with:

            'ph_low' / 'ph_high'      the soil's pH is outside the plant's range
            'n_high_demand'           the plant is a heavy N feeder and N is low
            'p_high_demand'           the plant is a heavy P feeder and P is low
            'k_high_demand'           the plant is a heavy K feeder and K is low

        `reasons` holds the matching sentences, DISPLAY STRINGS in the user's
        current UI language, paired positionally with `reason_codes`. Never parse
        them — the numbers in them are formatted for a human.

        Note the asymmetry the codes make explicit: a pH mismatch is reported for
        ANY plant whose range the soil falls outside, whereas a nutrient
        mismatch needs BOTH a heavy feeder AND a low reading. A plant absent from
        this list is not necessarily happy — it may simply not have declared a
        requirement that the soil breaks.

        `beds` groups results by bed UUID. Each result has its own `coverage`,
        `total` and `mismatches`. Per-bed `coverage` is 'no_soil_test' when
        neither the bed nor the plan has a record: UNTESTED, not 'no disagreements'.

        Top-level `coverage` is 'no_beds' for an empty plan, 'no_soil_test'
        when all beds are untested, 'partial_soil_tests' when some are untested,
        or 'ok' when every bed has an effective test. It is not a health rating.

        Omit `bed_id` to check every soil-capable bed.

        Read-only; no token required.

        Args:
            bed_id: Soil-capable bed UUID, or omit for every bed.
            today: ISO reference date. Defaults to the real current date.
        """
        result = await anyio.to_thread.run_sync(
            lambda: providers.get_soil_mismatches(bed_id, today)
        )
        return SoilMismatchBedsView(**result)

    @mcp.tool()
    async def list_layers() -> list[Layer]:
        """List the plan's layers, top of the stack first (US-D2.4).

        Each layer carries its stable id (address layers by this — names are
        not unique), visibility, lock state, opacity, z-order, whether it is
        the ACTIVE layer new objects land on, and its top-level object count.
        The same list is embedded in get_plan_summary's 'layers' field.

        A locked layer protects its OBJECTS: while it is locked, the write
        tools refuse to edit objects on it, move objects onto it, or delete
        it. The lock itself IS agent-writable via set_layer_property
        (issue #365), so an agent that needs to edit a locked layer unlocks it
        first and edits second — two calls, two undo steps, both visible.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        return layers_from_snapshot(snapshot)

    @mcp.tool()
    async def list_creatable_types() -> list[dict[str, Any]]:
        """List every object type the create_object tool accepts or refuses.

        Each entry gives the semantic type, its canonical geometry family,
        required and optional parameters, and (for deliberately excluded
        types) the reason. Use this discovery tool instead of parsing the
        create_object docstring or guessing whether a type wants dimensions
        or vertices.
        """
        return agent_creates.list_creatable_types()

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
            x: West (minimum-x) edge of the region to render, scene cm. Must be
                given together with y/width/height, or all four omitted (full
                canvas).
            y: South (minimum-y) edge of the region to render, scene cm; the
                region extends north to y + height (the scene is Y-up).
            width: Region width in cm.
            height: Region height in cm.
            layers: Optional allowlist of layer NAMES or layer IDS — both are
                accepted (the id, from list_layers, is the unambiguous address
                since names need not be unique); unknown entries are ignored.
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
        async def create_object(
            object_type: str,
            x: float | None = None,
            y: float | None = None,
            width: float | None = None,
            height: float | None = None,
            radius: float | None = None,
            name: str | None = None,
            species: str | None = None,
            points: list[list[float]] | None = None,
            text: str | None = None,
            box_dx: Annotated[
                float, Field(json_schema_extra=_hide_schema_default)
            ] = _UNSET_OFFSET,
            box_dy: Annotated[
                float, Field(json_schema_extra=_hide_schema_default)
            ] = _UNSET_OFFSET,
        ) -> WriteResult:
            """Create one object on the plan.

            Call list_creatable_types first for the complete machine-readable
            roster. Circles use centre + radius (plants may omit radius),
            rectangles and ellipses use centre + width/height, polygons use
            points or a rectangular footprint, polylines use points, and
            GENERIC_CALLOUT uses a leader target (x/y) plus text.

            Position is the object's CENTRE, in the same scene frame the read
            tools report -- so you can place an object relative to one you just
            read without converting anything. The canvas is CAD Y-up: a larger
            y is further NORTH.

            The object is CLAMPED to the canvas: a centre outside the canvas is
            shifted back so the whole object lies inside. An object cannot be
            created fully off-plan (where it would be invisible).

            A new plant is stamped with today's planting date (which drives the
            growth, shadow and sun-hours views) and, when 'species' matches the
            bundled species database, is auto-populated with that species' data.
            A plant created inside a bed is automatically linked to that bed,
            within this same single undo step -- the bed's id comes back as
            new_parent_bed_id.

            The object lands on the currently active layer. Fails if that layer
            is locked, if the dimensions don't fit the type's shape (e.g. width
            on a round type), or if a dimension is zero, negative or not finite.

            Args:
                object_type: One of the names listed above.
                x: Centre/leader-target X in scene cm, where applicable.
                    Omit it for point-built polygons/polylines.
                y: Centre/leader-target Y in scene cm, where applicable.
                    Omit it for point-built polygons/polylines.
                width: Width in cm. Required for rectangular types, rejected
                    for round ones.
                height: Height in cm. Same rule as width.
                radius: Radius in cm. For round types only; optional for plants
                    (defaults above), required for CONTAINER_ROUND.
                name: Optional display name for the object.
                species: Optional species name for a plant, e.g. 'Tomato'. A
                    match in the bundled database populates the plant's data.
                points: Polygon/polyline vertices as ``[[x, y], ...]`` in
                    scene cm. Polygons need at least three; polylines at least
                    two. Do not pass width/height with explicit points.
                text: Required callout text for GENERIC_CALLOUT.
                box_dx: Optional signed callout text-box X offset from the
                    leader tip, bounded to +/- twice the larger canvas dimension.
                    Omit for the default; null is not a valid offset.
                box_dy: Optional signed callout text-box Y offset from the
                    leader tip, bounded to +/- twice the larger canvas dimension.
                    Omit for the default; null is not a valid offset.
            """
            _require_write_auth(write_token)
            if box_dx is _UNSET_OFFSET:
                box_dx = None
            elif box_dx is None:
                raise ValueError("box_dx must be a finite number, not null")
            if box_dy is _UNSET_OFFSET:
                box_dy = None
            elif box_dy is None:
                raise ValueError("box_dy must be a finite number, not null")
            # Called by keyword: the provider takes eight positional args of
            # which six are float|None / str|None, so a width/height (or
            # name/species) transposition anywhere along this chain would be
            # type-identical and silently produce the wrong object.
            result = await anyio.to_thread.run_sync(
                lambda: providers.create_object(
                    object_type=object_type,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    radius=radius,
                    name=name,
                    species=species,
                    points=points,
                    text=text,
                    box_dx=box_dx,
                    box_dy=box_dy,
                )
            )
            return WriteResult(**result)

        @mcp.tool()
        async def move_object(item_id: str, dx: float, dy: float) -> WriteResult:
            """Move one object by a relative offset.

            The canvas is CAD Y-up: a positive dy moves the object NORTH (up on
            screen), a negative dy moves it SOUTH (down); a positive dx moves it
            east (right), a negative dx west. Offsets are in the same scene frame
            the read tools report, so to move an object south you pass a NEGATIVE
            dy.

            Moving a bed/container/trellis carries its contained plants along.
            Moving a plant re-evaluates its bed membership afterward — crossing
            into or out of a bed reparents it. This is usually one undo step;
            it becomes two only when reparenting happens (see the result's
            children_moved/bed_membership_changed/new_parent_bed_id).

            The move is CLAMPED to the canvas: an offset that would push the
            object (or a plant it carries) fully off-plan is trimmed so the
            object stays at the canvas edge instead. An object that is ALREADY
            off-plan is snapped fully back onto the plan, whatever direction
            was requested.

            Fails if the object (or a plant it contains) participates in a
            geometric constraint. This refusal is permanent for one-shot agent
            moves: call get_geometry on the blocking object to inspect the
            constraint, then remove/edit it in the app. Journal pins also remain
            unsupported by scene writes.

            Args:
                item_id: The object's stable UUID (from list_objects/get_object).
                dx: Horizontal offset in scene cm: a positive dx moves the object
                    east (right), a negative dx moves it west (left).
                dy: Vertical offset in scene cm. The canvas is CAD Y-up, so a
                    positive dy moves the object NORTH (up on screen) and a
                    negative dy moves it SOUTH (down). This is the SAME frame the
                    read tools report positions in (a larger y is further north),
                    so you can move relative to a position you just read without
                    flipping any axis. To move an object SOUTH, pass a NEGATIVE dy.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.move_object(item_id, dx, dy)
            )
            return WriteResult(**result)

        @mcp.tool()
        async def set_object_position(
            item_id: str, x: float, y: float
        ) -> WriteResult:
            """Set one object's absolute centre in scene centimetres.

            This is the absolute counterpart to ``move_object``. The centre is
            exactly the coordinate reported by ``get_object`` and the result's
            x/y, in the native CAD Y-up frame. Moving a bed/container/trellis
            carries its contained plants; moving a plant re-evaluates bed
            membership, so those cases inherit ``move_object``'s one-or-two
            undo-step contract.

            Call ``get_geometry`` first for a constrained object. This tool
            permanently refuses constrained geometry rather than silently
            skipping the GUI's multi-item live solver. It also refuses group
            members, journal pins, and objects on locked layers.

            The resulting position is CLAMPED to the canvas, so the object
            cannot be placed fully off-plan.

            Args:
                item_id: Stable UUID from list_objects/get_object.
                x: Absolute centre X in scene cm.
                y: Absolute centre Y in scene cm; larger is further north.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.set_object_position(
                    item_id=item_id, x=x, y=y
                )
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

        @mcp.tool()
        async def undo() -> HistoryResult:
            """Undo exactly one command on the global GUI-shared history stack.

            This is a write tool and requires the Agent API token. The stack is
            global: an undo call may reverse a human GUI edit or an earlier
            agent edit, and one call reverses exactly one command. A move that
            created two command entries therefore needs two undo calls. History
            is not persisted in the project file. Calling undo when the stack is
            empty is an explicit refusal, not a successful no-op.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(providers.undo)
            return HistoryResult(**result)

        @mcp.tool()
        async def redo() -> HistoryResult:
            """Redo exactly one command on the global GUI-shared history stack.

            This is a write tool and requires the Agent API token. The stack is
            global: a redo call may reapply a human GUI edit or an earlier
            agent edit, and one call reapplies exactly one command. Calling
            redo when the stack is empty is an explicit refusal, not a
            successful no-op.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(providers.redo)
            return HistoryResult(**result)

        # --- US-D3.2: succession write --------------------------------------

        @mcp.tool()
        async def set_succession_plan(
            bed_id: str,
            entries: list[dict] | None = None,
            year: int | None = None,
        ) -> WriteResult:
            """Write a bed's succession plan, or delete it (US-D3.2).

            This REPLACES the bed's whole plan for the year, the same way the
            GUI's succession dialog does when you press OK - it is not an append.
            Read the current plan first (get_succession_plan) and send the full
            set of slots you want to keep.

            ONE call is ONE undo step, including a delete, so a single Ctrl+Z (or
            a single ``undo`` call) restores the previous plan exactly. Use
            ``entries: []`` - or omit it - to DELETE the plan.

            Refused, leaving both the plan and the undo stack untouched, when the
            id is unknown or is not a soil-capable bed (a TRELLIS holds no soil);
            two slots overlap in time (one bed cannot grow two crops on the same
            days); a date is not ISO YYYY-MM-DD; a slot ends before it starts; or
            a species_key is in neither the bundled database nor the plan.

            Each slot must end at least one day BEFORE the next one begins. A
            one-day overlap - one slot ending the very day the next starts - is
            refused, because one bed cannot grow two crops on the same day.
            find_succession_gaps already returns windows in exactly that shape:
            consecutive gaps are adjacent, never overlapping, so filling every
            reported gap in order is accepted.
            This is a write tool and requires the Agent API token.

            Args:
                bed_id: The bed's stable UUID. Soil-capable types only.
                entries: The complete slot list, each
                    {species_key, common_name, start_date, end_date, notes} with
                    ISO dates. Send [] to delete the plan. ``common_name`` is
                    display text; the machine contract is ``species_key``.
                year: Plan year. Defaults to the current year.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.set_succession_plan(bed_id, entries, year)
            )
            return WriteResult(**result)

        # --- US-D3.3: manual-task writes ------------------------------------

        @mcp.tool()
        async def add_manual_task(
            title: str,
            date: str | None = None,
            notes: str | None = None,
            bed_id: str | None = None,
        ) -> ManualTaskResult:
            """File one user-authored task (US-D3.3).

            Use this for work the garden engine cannot derive - a reminder to
            order seed, a note to visit a supplier. For anything the engine CAN
            derive (sowing, transplanting, frost, soil work), read get_tasks
            first: the derived tasks already exist and are regenerated on every
            call, so a manual copy of one will drift.

            ONE call is ONE undo step, so a single Ctrl+Z removes it.

            Refused, leaving the task list and the undo stack untouched, when the
            title is empty; `date` is not an ISO YYYY-MM-DD date; or `bed_id` is
            not a bed in this plan.

            This is a write tool and requires the Agent API token.

            Args:
                title: What to do. Required, non-empty.
                date: Optional ISO due date. Omit for an undated task, which
                    always appears in a filtered read.
                notes: Optional detail.
                bed_id: Optional bed UUID to link the task to.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.add_manual_task(
                    title=title, date=date, notes=notes, bed_id=bed_id, task_id=None
                )
            )
            return ManualTaskResult(**result)

        @mcp.tool()
        async def edit_manual_task(
            task_id: str,
            title: str,
            date: str | None = None,
            notes: str | None = None,
            bed_id: str | None = None,
        ) -> ManualTaskResult:
            """Change one manual task (US-D3.3). ONE undo step.

            Send every field you want the task to have afterwards: this replaces
            the stored values rather than merging into them, so an omitted
            optional field is cleared. Read the task with get_tasks first.

            Refused, leaving the task list and the undo stack untouched, when the
            id is unknown; the task is GENERATED (calendar, propagation,
            succession, soil, amendment, mismatch or frost) rather than manual -
            generated tasks are derived state rebuilt on every call, so editing
            one would be silently undone by the next read; the title is empty; or
            `date` / `bed_id` is invalid.

            This is a write tool and requires the Agent API token.

            Args:
                task_id: The manual task's id, from get_tasks.
                title: The new title. Required, non-empty.
                date: New ISO due date, or omit to make it undated.
                notes: New notes, or omit to clear.
                bed_id: New bed link, or omit to clear.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.edit_manual_task(
                    title=title, date=date, notes=notes, bed_id=bed_id, task_id=task_id
                )
            )
            return ManualTaskResult(**result)

        @mcp.tool()
        async def delete_manual_task(task_id: str) -> ManualTaskResult:
            """Delete one manual task (US-D3.3). ONE undo step.

            Refused, leaving the task list and the undo stack untouched, when the
            id is unknown or names a GENERATED task. A generated task cannot be
            deleted because it is not stored - it is rebuilt from the plan on
            every call, so deleting it would achieve nothing and would report a
            success that does not survive the next read.

            Dismissal and completion of a task are also refused, for any task:
            that is a task-status write, and it is not undoable, so it would be
            the one agent write a single Ctrl+Z could not reverse. The user does
            that in the Tasks tab.

            This is a write tool and requires the Agent API token.

            Args:
                task_id: The manual task's id, from get_tasks.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.delete_manual_task(task_id)
            )
            return ManualTaskResult(**result)

        # --- US-D3.4: soil-test write ----------------------------------------

        @mcp.tool()
        async def record_soil_test(
            bed_id: str | None = None,
            ph: StrictFloat | None = None,
            n_level: StrictInt | None = None,
            p_level: StrictInt | None = None,
            k_level: StrictInt | None = None,
            ca_level: StrictInt | None = None,
            mg_level: StrictInt | None = None,
            s_level: StrictInt | None = None,
            soil_texture: str | None = None,
            test_date: str | None = None,
            notes: str | None = None,
        ) -> WriteResult:
            """Record a soil test on the Rapitest KIT scale (US-D3.4).

            The nutrient arguments are CATEGORICAL KIT READINGS, not laboratory
            values. Each nutrient has its own range, and passing a number from
            the wrong one is refused rather than stored:

                n_level, p_level   integers 0-4
                k_level            integer 1-4 (the kit has no zero for K)
                ca_level, mg_level, s_level   integers 0-2

            A lab report in ppm is NOT accepted here, and this is deliberate: the
            plan stores lab ppm values separately, but no engine reads them - the
            health ratings, the amendment recommendations and the mismatch checks
            all read the kit levels. A test recorded from ppm alone would report
            unknown health and recommend nothing while looking complete. Enter a
            lab report in the Soil Test dialog instead.

            ONE call is ONE undo step, so a single Ctrl+Z removes the record.

            Refused, leaving the soil-test store and the undo stack untouched,
            when any level is outside its own range or is not a whole number; pH
            is outside 0.0-14.0 or not finite; `bed_id` is unknown or names an
            object that holds no soil (a TRELLIS is a plant parent but holds no
            soil, so it is refused); `soil_texture` is not one of sandy, loamy,
            clayey, compacted; `test_date` is not ISO YYYY-MM-DD or is in the
            future; or NO reading at all was supplied.

            Pass bed_id=None to record the plan-wide default, the same target the
            GUI offers. get_soil_status then reports that reading as coming from
            the plan rather than from any one bed.

            This is a write tool and requires the Agent API token.

            Args:
                bed_id: Soil-capable bed UUID, or omit for the plan-wide default.
                ph: Measured pH, 0.0-14.0.
                n_level: Nitrogen kit level, 0-4.
                p_level: Phosphorus kit level, 0-4.
                k_level: Potassium kit level, 1-4.
                ca_level: Calcium kit level, 0-2.
                mg_level: Magnesium kit level, 0-2.
                s_level: Sulfur kit level, 0-2.
                soil_texture: One of sandy, loamy, clayey, compacted.
                test_date: ISO date the sample was taken. Defaults to today;
                    a future date is refused.
                notes: Free-text detail.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.record_soil_test(
                    bed_id=bed_id,
                    ph=ph,
                    n_level=n_level,
                    p_level=p_level,
                    k_level=k_level,
                    ca_level=ca_level,
                    mg_level=mg_level,
                    s_level=s_level,
                    soil_texture=soil_texture,
                    test_date=test_date,
                    notes=notes,
                )
            )
            return WriteResult(**result)

        # --- US-D2.2: resize / rotate --------------------------------------

        @mcp.tool()
        async def resize_object(
            item_id: str,
            width: float | None = None,
            height: float | None = None,
            radius: float | None = None,
        ) -> WriteResult:
            """Resize one object to absolute target dimensions, in centimetres.

            The object's CENTRE stays exactly where it is, for every type -- so
            the x/y you read before the resize is still valid afterwards, and
            the object grows outward in all directions rather than drifting.
            The result echoes the resulting centre back.

            Pass the dimensions that fit the object's shape:

            * Round objects (plants, CONTAINER_ROUND, circular beds): 'radius'.
            * Rectangular objects (beds, containers, structures): 'width'
              and/or 'height'. Omit one to leave that axis unchanged.

            These are ABSOLUTE targets, not deltas -- width=120 means "make it
            120 cm wide", the same vocabulary create_object uses.

            Resizing a bed does NOT move or re-link the plants inside it (the
            app's own resize behaves the same way), so shrinking a bed can leave
            a plant linked to a bed it no longer sits inside. Use
            set_parent_bed if you need to correct that.

            Fails if the object is drawn from vertices rather than a
            width/height box (polygons, polylines, fences, paths — use
            get_geometry with set_vertex/add_vertex/delete_vertex instead), if
            the dimension doesn't fit the shape, if a value
            is zero/negative/not finite or implausibly large for the plan, if
            the object participates in a geometric constraint, if it's a
            journal pin or a group member, or if it's on a locked layer.

            Args:
                item_id: The object's stable UUID (from list_objects/get_object).
                width: Target width in cm. Rectangular objects only.
                height: Target height in cm. Rectangular objects only.
                radius: Target radius in cm. Round objects only.
            """
            _require_write_auth(write_token)
            # Called by keyword: width/height/radius are all float|None, so a
            # transposition anywhere along this chain would be type-identical
            # and silently resize the wrong axis (the create_object precedent).
            result = await anyio.to_thread.run_sync(
                lambda: providers.resize_object(
                    item_id=item_id, width=width, height=height, radius=radius
                )
            )
            return WriteResult(**result)

        @mcp.tool()
        async def rotate_object(
            item_id: str, angle: float, relative: bool = False
        ) -> WriteResult:
            """Rotate one object, in degrees.

            A POSITIVE angle rotates the object COUNTER-CLOCKWISE: an object
            whose long axis points east points north after +90. Pass a negative
            angle to turn it clockwise. The object rotates about its own
            centre, which does not move.

            By default 'angle' is the object's new ABSOLUTE rotation, so
            calling rotate_object(id, 90) twice leaves it at 90 degrees. Pass
            relative=True to add to the current rotation instead, so the same
            two calls leave it at 180. The resulting angle is normalised into
            [0, 360) and returned as rotation_deg.

            Like resize_object, rotating a bed does NOT move or re-link the
            plants inside it, so a rotation can leave a plant linked to a bed it
            no longer sits inside. Use set_parent_bed to correct that.

            Fails if the object participates in a geometric constraint, if it's
            a journal pin or a group member, if it's on a locked layer, or if
            the angle is not finite.

            Args:
                item_id: The object's stable UUID (from list_objects/get_object).
                angle: Degrees. Positive is COUNTER-CLOCKWISE.
                relative: False (default) sets the absolute angle; True adds to
                    the object's current rotation.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.rotate_object(item_id, angle, relative)
            )
            return WriteResult(**result)

        # --- US-D2.6: low-level vertex geometry ----------------------------

        @mcp.tool()
        async def set_vertex(
            item_id: str, index: int, x: float, y: float
        ) -> WriteResult:
            """Move one polygon/polyline vertex to an absolute scene point.

            Call ``get_geometry`` first. Vertex indices are zero-based and
            x/y use the same centimetre, CAD Y-up frame as the returned vertex.
            Exactly one undo step restores the original vertex list. Setting a
            vertex to where it already is is refused as a no-op: feed a vertex
            back only after changing its x/y, otherwise the call adds no command
            and reports nothing to change.

            Constrained objects are refused permanently: the GUI's live solver
            may move several connected items, which this one-shot tool does not
            emulate. Rectangles are rect-backed and use ``resize_object`` instead.

            Args:
                item_id: Polygon or polyline UUID.
                index: Existing vertex index.
                x: Requested vertex X in scene cm.
                y: Requested vertex Y in scene cm.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.set_vertex(
                    item_id=item_id, index=index, x=x, y=y
                )
            )
            return WriteResult(**result)

        @mcp.tool()
        async def add_vertex(
            item_id: str, index: int, x: float, y: float
        ) -> WriteResult:
            """Insert one polygon/polyline vertex at a list index.

            ``index`` is the FINAL index of the inserted point: zero inserts at
            the start, ``vertex_count`` appends, and values in between insert in
            the middle. Exactly one undo step removes it again.

            Call ``get_geometry`` first and refuse if ``is_constrained`` is true.
            Rectangles use ``resize_object``, not vertex insertion.

            Args:
                item_id: Polygon or polyline UUID.
                index: Final insertion index from 0 through current vertex_count.
                x: New vertex X in scene cm.
                y: New vertex Y in scene cm.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.add_vertex(
                    item_id=item_id, index=index, x=x, y=y
                )
            )
            return WriteResult(**result)

        @mcp.tool()
        async def delete_vertex(item_id: str, index: int) -> WriteResult:
            """Delete one polygon/polyline vertex (exactly one undo step).

            A polygon must retain at least three vertices and a polyline at
            least two; a deletion that would cross that minimum is refused with
            no scene or history change. Call ``get_geometry`` first and refuse
            constrained objects.

            Args:
                item_id: Polygon or polyline UUID.
                index: Existing zero-based vertex index to remove.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.delete_vertex(item_id=item_id, index=index)
            )
            return WriteResult(**result)

        # --- US-D2.3: species / parent bed ---------------------------------

        @mcp.tool()
        async def set_species(
            item_id: str,
            species: str | None = None,
            apply_database_size: bool = True,
        ) -> WriteResult:
            """Assign (or clear) the species of an existing plant.

            The counterpart to create_object's 'species' argument, for plants
            that already exist -- including ones the user drew by hand and
            never named. Assigning a species populates the plant's data, which
            is what makes the plant-detail panel, the planting calendar and the
            soil/pH mismatch warnings light up for it.

            The species name is matched against the app's bundled database by
            scientific name, common name, or alias -- read the garden://species
            resource for the full list. An unknown name is rejected rather than
            guessed at.

            As in the app, the plant's drawn footprint adopts the species' real
            mature size (diameter = max_spread_cm). If the user has set a
            manual spacing override that disagrees with the database, the app
            would ask which to keep; apply_database_size is your answer to that
            question -- True (default) takes the database values, False keeps
            the user's. Note this only decides the conflict: without an
            override the footprint always adopts the database size.

            Pass species=None to clear the species. The footprint is left as
            drawn in that case.

            Because assigning a species resizes the plant's footprint, this
            counts as a geometry change: it fails on an object that
            participates in a geometric constraint, exactly as resize_object
            does. Clearing a species resizes nothing and is allowed on a
            constrained plant.

            Also fails if the object is not a plant (TREE/SHRUB/PERENNIAL), if
            the species is unknown, if the plant already has that species or has
            no species to clear, if it's a journal pin or group member, or if
            it's on a locked layer.

            Args:
                item_id: The plant's stable UUID (from list_objects/get_object).
                species: Species name -- scientific, common, or a known alias.
                    Omit or pass null to clear the plant's species.
                apply_database_size: How to resolve a conflicting manual
                    spacing override, as described above.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.set_species(item_id, species, apply_database_size)
            )
            return WriteResult(**result)

        @mcp.tool()
        async def set_parent_bed(
            item_id: str, bed_id: str | None = None
        ) -> WriteResult:
            """Link a plant to a bed, or detach it -- WITHOUT moving the plant.

            This changes the relationship only; the plant stays exactly where
            it is on the canvas. Use it for the case move_object cannot reach:
            a plant that is already sitting inside a bed but isn't linked to it
            (which happens whenever a bed is drawn around existing plants).
            Linking is what makes the plant count towards the bed's capacity,
            inherit its soil readings, and appear in plants_in_bed.

            The plant does NOT have to be geometrically inside the bed -- the
            app's own Link action doesn't require it either. The result's
            link_is_geometric tells you whether the link and the geometry
            agree, so you can point out a mismatch.

            Pass bed_id=None to detach the plant from whatever bed it is in.

            A plant's parent can be a garden bed, raised bed, container, round
            container, wall planter, or a TRELLIS. Note a trellis holds plants
            but has no soil, so a plant on one has no soil readings.

            Fails if the object is not a plant, if bed_id names something that
            cannot hold plants, if the plant is already in that state, if
            either object is a journal pin or group member, or if either is on
            a locked layer.

            Args:
                item_id: The plant's stable UUID (from list_objects/get_object).
                bed_id: The target bed's stable UUID, or null to detach.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.set_parent_bed(item_id, bed_id)
            )
            return WriteResult(**result)

        # --- issue #338: stacking order -------------------------------------

        @mcp.tool()
        async def arrange_object(
            item_id: str,
            action: Literal[
                "bring_to_front", "bring_forward", "send_backward", "send_to_back"
            ],
        ) -> WriteResult:
            """Bring to front / bring forward / send backward / send to back.

            Reorders one object within its OWN layer only — never across
            layers. 'bring_to_front'/'send_to_back' move it to the top/bottom
            of its layer; 'bring_forward'/'send_backward' step it past the
            single nearest object in its layer whose bounding box OVERLAPS it
            (a non-overlapping neighbour is skipped entirely).

            A bed/container carries its contained plants along as one block
            (their relative order among themselves is kept), and a plant can
            never be arranged below its own bed — 'send_to_back'/
            'send_backward' on a lone plant stops just above its bed rather
            than reaching further down, which correctly reports as a refusal
            ("already at back") when the plant is already there.

            Fails (raises, nothing changed) when the object is already at the
            front/back of its layer, or when bring_forward/send_backward finds
            no overlapping object to step past. Also fails, like every D2
            write tool, if the object is on a locked layer, is a journal pin,
            or is a member of a group. Exactly one undo step.

            Args:
                item_id: The object's stable UUID (from list_objects/get_object).
                action: One of 'bring_to_front', 'bring_forward',
                    'send_backward', 'send_to_back'.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.arrange_object(item_id, action)
            )
            return WriteResult(**result)

        # --- US-D2.4: layer tools -------------------------------------------
        #
        # Read side is list_layers (unauthenticated, registered with the other
        # reads). Every tool here runs the SAME core/commands.py layer command
        # the GUI's own surfaces run (invariant #5) — exactly one undo step per
        # call, except set_active_layer, which is session state and says so.

        @mcp.tool()
        async def set_object_layer(item_id: str, layer_id: str) -> WriteResult:
            """Move one object to a different layer (one undoable step).

            Only the addressed object changes layer: a bed's contained plants
            keep their own layer, exactly as when the user moves the bed alone
            via the GUI's "Move to Layer" menu. Undo restores the object's
            original layer AND its exact stacking position within it.

            Layer ids come from list_layers (or any object's layer_id field).
            Fails if the object is on a locked layer, if the TARGET layer is
            locked, if the object is a journal pin or a group member, if
            either id is unknown, or if the object is already on that layer.

            Args:
                item_id: The object's stable UUID (from list_objects/get_object).
                layer_id: The target layer's stable UUID (from list_layers).
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.set_object_layer(item_id, layer_id)
            )
            return WriteResult(**result)

        @mcp.tool()
        async def create_layer(name: str) -> WriteResult:
            """Create a new layer at the TOP of the stack and activate it.

            Mirrors the Layers panel's add button: the new layer becomes the
            active layer, so objects created afterwards (create_object) land
            on it until the user or set_active_layer switches again. Undo
            removes the layer and restores the previously active one. The new
            layer's id comes back as layer_id.

            Fails if the name is empty or whitespace-only. Duplicate names are
            allowed (as in the app) — address layers by id, not name.

            Args:
                name: Display name for the new layer.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.create_layer(name)
            )
            return WriteResult(**result)

        @mcp.tool()
        async def rename_layer(layer_id: str, name: str) -> WriteResult:
            """Rename a layer (one undoable step).

            Works on a locked layer too — the lock protects the layer's
            objects from editing, not the layer's own name.

            Fails if the id is unknown, if the name is empty or
            whitespace-only, or if the layer already has that name.

            Args:
                layer_id: The layer's stable UUID (from list_layers).
                name: The new display name.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.rename_layer(layer_id, name)
            )
            return WriteResult(**result)

        @mcp.tool()
        async def delete_layer(layer_id: str) -> WriteResult:
            """Delete a layer — its objects SURVIVE on a sibling layer.

            Deleting a layer never deletes the objects on it: they are moved
            to a replacement layer (the topmost remaining one), and the layer
            removal plus every object reassignment is ONE undo step. The
            result's objects_moved reports how many objects were reassigned.

            Fails if the layer is locked (unlock it first with
            set_layer_property(layer_id, locked=False) — a locked layer's
            objects are protected, but the lock itself is agent-writable since
            issue #365), if it is the plan's only layer, or if the id is
            unknown.

            Args:
                layer_id: The layer's stable UUID (from list_layers).
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.delete_layer(layer_id)
            )
            return WriteResult(**result)

        @mcp.tool()
        async def set_active_layer(layer_id: str) -> WriteResult:
            """Switch which layer new objects land on.

            Session state, NOT a document change: there is no undo step (the
            active layer is not saved with the plan), the plan is not marked
            dirty, and no object moves. Undoable layer edits are the other
            five layer tools. The Layers panel's selection follows the switch.

            Fails if the id is unknown or the layer is already active.
            Activating a locked layer is allowed, but creating onto it is not
            (create_object refuses a locked active layer).

            Args:
                layer_id: The layer's stable UUID (from list_layers).
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.set_active_layer(layer_id)
            )
            return WriteResult(**result)

        @mcp.tool()
        async def set_layer_property(
            layer_id: str,
            visible: bool | None = None,
            opacity: float | None = None,
            locked: bool | None = None,
        ) -> WriteResult:
            """Show/hide a layer, set its opacity, or lock/unlock it (one undoable step).

            Pass exactly ONE of 'visible'/'opacity'/'locked' per call — each
            property change is one undo step, and one call is one undo step;
            make separate calls to change more than one. Hiding a layer hides
            every object on it (render_canvas_image without a layers argument
            reflects it); the change is undoable like the Layers panel's eye
            toggle.

            'locked' IS changeable, in both directions (issue #365 — a
            deliberate policy reversal of the original D2.4 decision). While a
            layer is locked, the write tools refuse to edit its objects, move
            objects onto it, or delete it; to edit a locked layer, unlock it
            first and edit second. Both calls are ordinary undo steps, so the
            user sees and can reverse the whole sequence.

            Fails if the id is unknown, if none or more than one of
            'visible'/'opacity'/'locked' are given, if opacity is outside
            [0.0, 1.0], or if the layer already has the requested value.

            Args:
                layer_id: The layer's stable UUID (from list_layers).
                visible: True to show the layer, False to hide it.
                opacity: Layer opacity, 0.0 (invisible) to 1.0 (opaque).
                locked: True to lock the layer, False to unlock it. While
                    locked, the write tools refuse to edit its objects.
            """
            _require_write_auth(write_token)
            # Called by keyword: visible/locked are both bool|None, so a
            # transposition would be type-identical — which is exactly why the
            # one-property-per-call rule is enforced in the provider, not here.
            result = await anyio.to_thread.run_sync(
                lambda: providers.set_layer_property(
                    layer_id=layer_id,
                    visible=visible,
                    opacity=opacity,
                    locked=locked,
                )
            )
            return WriteResult(**result)

        # --- issue #365: document lifecycle (token-gated) ---------------------
        # Placed HERE, inside the writes-active block, rather than beside
        # save_plan: save_plan only writes a new file, but new_plan and
        # open_plan REPLACE the open document and can discard unsaved work —
        # strictly more destructive than delete_object, so they take the same
        # double gate (tool registered only when writes are on, plus a token
        # on every call).

        @mcp.tool()
        async def new_plan(
            width_cm: float | None = None,
            height_cm: float | None = None,
            force: bool = False,
        ) -> PlanLifecycleResult:
            """Discard the open plan and start a fresh, empty one.

            Without this an agent can only ever work on whatever plan the user
            happens to have open, so every session either inherits the user's
            document or is useless. The canvas keeps the current size unless
            you give one.

            This DISCARDS the open document, so it is refused when the plan
            has unsaved changes unless force=true. The GUI asks the user at
            that point; an agent cannot raise a prompt, so it must be told
            explicitly. Save first with save_plan if the work matters.

            Not an undo step: a new document resets the undo stack, so there is
            nothing to Ctrl+Z back to. The new plan starts clean and is not
            marked dirty until something is added to it.

            Fails if a dimension is not finite or is outside 50-100000 cm, or
            if the plan is dirty and force is not set.

            Args:
                width_cm: Canvas width in centimetres. Omit to keep the
                    current width.
                height_cm: Canvas height in centimetres. Omit to keep the
                    current height.
                force: Discard unsaved changes instead of refusing.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.new_plan(width_cm, height_cm, force)
            )
            return PlanLifecycleResult(**result)

        @mcp.tool()
        async def open_plan(file_path: str, force: bool = False) -> PlanLifecycleResult:
            """Load an existing ``.ogp`` garden plan from disk.

            Closes the round trip: with this, save_plan and new_plan, an agent
            can open a file the user names, work on it, and verify its own
            work without touching the GUI.

            This REPLACES the open document, so it is refused when the plan
            has unsaved changes unless force=true. The GUI asks the user at
            that point; an agent cannot raise a prompt, so it must be told
            explicitly.

            Not an undo step: loading a document resets the undo stack, so
            there is nothing to Ctrl+Z back to. Use force=false unless you are
            certain the open plan is disposable.

            Fails if the path is empty, is not a ``.ogp`` file, does not
            exist, is not a file, or if the file cannot be parsed; and if the
            plan is dirty and force is not set.

            Args:
                file_path: Path to the ``.ogp`` file to load.
                force: Discard unsaved changes instead of refusing.
            """
            _require_write_auth(write_token)
            result = await anyio.to_thread.run_sync(
                lambda: providers.open_plan(file_path, force)
            )
            return PlanLifecycleResult(**result)

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

    @mcp.resource("garden://plant-lists", mime_type="application/json")
    async def plant_lists_resource() -> list[dict[str, Any]]:
        """User-defined plant lists and favorites catalog (US-G4)."""

        def _get_lists() -> list[dict[str, Any]]:
            from open_garden_planner.models.plant_lists import (  # noqa: PLC0415
                get_plant_list_store,
            )

            store = get_plant_list_store()
            result: list[dict[str, Any]] = []
            for pl in store.all_lists():
                result.append(
                    {
                        "id": pl.id,
                        "name": pl.name,
                        "description": pl.description,
                        "entries": [
                            {
                                "id": entry.id,
                                "species_key": entry.species_key,
                                "common_name": entry.species.common_name
                                if entry.species
                                else "",
                                "scientific_name": entry.species.scientific_name
                                if entry.species
                                else "",
                                "note": entry.note,
                                "added_at": entry.added_at,
                            }
                            for entry in pl.entries
                        ],
                    }
                )
            return result

        return await anyio.to_thread.run_sync(_get_lists)

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

    @mcp.prompt(name="plan-polyculture-bed")
    async def plan_polyculture_bed(bed_id: str) -> str:
        """Plan a polyculture bed using compatible sets (US-D3.1).

        Finds compatible sets among the bed's current plants plus common
        companions, then asks the agent to choose the best set.
        """
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        # Find the bed and its plants
        bed_obj = queries.get_object(snapshot, bed_id)
        existing_plants: list[str] = []
        if bed_obj and hasattr(bed_obj, "child_item_ids"):
            for child_id in bed_obj.child_item_ids:
                child = queries.get_object(snapshot, child_id)
                # species_NAME, not species_key: ObjectDetail.species_key is
                # populated from the top-level `plant_species` ATTRIBUTE, which
                # only a gallery-picked plant has — a plant assigned by species
                # search, or by the agent's own set_species tool, stores the
                # record in metadata and leaves the attribute unset, so
                # species_key is None. queries._species_name covers both cases
                # and is exactly what this needs (P1-2). Reading species_key
                # here silently dropped every search-assigned plant, so a bed
                # of them rendered as empty AND the corn/tomato antagonism this
                # prompt exists to surface was never reported.
                if child is not None:
                    name = child.species_name or child.species_key
                    if name:
                        existing_plants.append(name)

        # Rank sets by bed coverage and surface conflicts. NOT
        # find_compatible_sets(must_include=existing_plants) — that returns
        # nothing unless the bed already is a complete clique (P0-2), and then
        # the prompt advises "add more species", which cannot help.
        result = await anyio.to_thread.run_sync(
            lambda: providers.find_sets_for_bed(existing_plants, 3)
        )

        return agent_prompts.render_plan_polyculture_bed_prompt(
            bed_id,
            [CompatibleSet(**s) for s in result["sets"]],
            result["bed_plants"],
            result["conflicts"],
            result["uncovered"],
            result["searched_size"],
        )

    @mcp.prompt(name="plan-succession")
    async def plan_succession(bed_id: str) -> str:
        """Compose a full-season succession brief for one bed (US-D3.2).

        Gathers the bed's current plan, its uncovered windows, and ranked
        candidates for the first open window, then asks the agent for a complete
        slot list it can write back with set_succession_plan.
        """
        plan_raw = await anyio.to_thread.run_sync(
            lambda: providers.get_succession_plan(bed_id, None, None)
        )
        plan = SuccessionPlanView(**plan_raw)
        gaps = [
            SuccessionGap(**g)
            for g in await anyio.to_thread.run_sync(
                lambda: providers.find_succession_gaps(bed_id, None, None)
            )
        ]

        suggestions: list[SuccessionSuggestion] = []
        if gaps:
            first = gaps[0]
            names = [record.get("common_name", "") for record in get_species_db().values()]
            suggestions = [
                SuccessionSuggestion(**s)
                for s in await anyio.to_thread.run_sync(
                    lambda: providers.suggest_succession(
                        bed_id, first.start_date, first.end_date, names
                    )
                )
            ]

        return agent_prompts.render_plan_succession_prompt(
            bed_id, plan, gaps, suggestions
        )

    @mcp.prompt(name="plan-my-week")
    async def plan_my_week(today: str | None = None) -> str:
        """Compose a prioritised seven-day garden brief (US-D3.3).

        Gathers the current task window, the month-bucketed overview, the plan
        summary and the open diagnostics, then asks for the coming week ranked
        by what is time-critical.

        When the plan has no geo-location there are no frost dates and no
        calendar tasks; the brief says so explicitly rather than presenting an
        empty week.

        Args:
            today: ISO reference date. Defaults to the real current date; pass
                it to render a reproducible brief.
        """
        task_raw = await anyio.to_thread.run_sync(
            lambda: providers.get_tasks(
                None, None, None, None, None, None, today
            )
        )
        task_list = TaskListView(**task_raw)
        calendar = TaskCalendarView(
            **await anyio.to_thread.run_sync(
                lambda: providers.get_task_calendar(None, today)
            )
        )
        # Two separate hops (benign TOCTOU), exactly as `audit-plan` does: this is
        # read-only advisory text, so a snapshot drifting by one scene edit
        # between hops has no correctness consequence here.
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        records = await anyio.to_thread.run_sync(providers.diagnostics)
        return agent_prompts.render_plan_my_week_prompt(
            task_list,
            calendar,
            plan_summary_from_snapshot(snapshot),
            diagnostics_from_records(records),
        )

    @mcp.prompt(name="plan-soil-amendments")
    async def plan_soil_amendments(bed_id: str) -> str:
        """Compose a prioritised soil-amendment brief for one bed (US-D3.4).

        Gathers the bed's effective soil record, its amendment recommendations,
        the plants that disagree with that soil and what is growing there, then
        asks for a prioritised amendment plan with timing.

        An untested bed yields a brief that asks for a test. It is never
        presented as healthy.
        """
        status = SoilStatusListView(
            **await anyio.to_thread.run_sync(
                lambda: providers.get_soil_status(bed_id, None)
            )
        ).beds[0]
        plan = AmendmentPlanView(
            **await anyio.to_thread.run_sync(
                lambda: providers.recommend_amendments(bed_id, None)
            )
        )
        mismatches = SoilMismatchBedsView(
            **await anyio.to_thread.run_sync(
                lambda: providers.get_soil_mismatches(bed_id, None)
            )
        ).beds[bed_id]
        # "What is growing here" comes from the snapshot + queries, the same
        # path `plan-polyculture-bed` uses. `child.species_name or
        # child.species_key`, because ObjectDetail.species_key is populated only
        # from the top-level attribute a gallery-picked plant carries — a
        # search-assigned or agent-assigned plant keeps its record in metadata
        # and leaves the attribute unset.
        snapshot = await anyio.to_thread.run_sync(providers.snapshot)
        planted: list[str] = []
        bed_obj = queries.get_object(snapshot, bed_id)
        if bed_obj is not None:
            for child_id in getattr(bed_obj, "child_item_ids", ()) or ():
                child = queries.get_object(snapshot, child_id)
                if child is None:
                    continue
                name = child.species_name or child.species_key
                if name:
                    planted.append(name)
        return agent_prompts.render_plan_soil_amendments_prompt(
            status, plan, mismatches, planted
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
        self._loop: asyncio.AbstractEventLoop | None = None
        # Set by stop() immediately before it forces the loop down (#373), so
        # _run can tell the deliberate "Event loop stopped" RuntimeError from a
        # genuine crash without matching CPython's message text.
        self._forced_stop = False
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
            host=self._host,
            port=self._port,
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
            # Do NOT let uvicorn install its default logging config (issue #291).
            # uvicorn's default formatter does `sys.stdout.isatty()` at dictConfig
            # time (uvicorn/logging.py), and a PyInstaller **windowed** build
            # launched with no inherited stdout handle (a double-click, or CI's
            # Start-Process) has sys.stdout/sys.stderr None -- so Config.__init__
            # raises
            # "ValueError: Unable to configure formatter 'default'" and the server
            # never starts. That is invisible from source and from a console=True
            # build, which is why it shipped: the Agent API was dead in every
            # released exe. We want none of uvicorn's logging anyway (log_level and
            # access_log above already say so), so pass None and keep our own.
            log_config=None,
            lifespan="on",
        )
        server = uvicorn.Server(config)
        # No signal-handler handling needed: uvicorn's serve() installs them via
        # capture_signals(), which is a no-op off the main thread — and we run
        # the event loop on a worker thread.
        self._server = server
        self._forced_stop = False

        thread = threading.Thread(target=self._run, args=(server,),
                                  name=SERVER_THREAD_NAME, daemon=True)
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

    def _run(self, server: uvicorn.Server) -> None:
        """Own the server's event loop on this background thread.

        The loop handle is stored on ``self`` so :meth:`stop` can reach across
        the thread boundary (``call_soon_threadsafe``) to unwind it — see the
        shutdown fix in :meth:`stop` (issue #373).
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(server.serve())
        except RuntimeError:
            # A forced stop() calls loop.stop(), which makes run_until_complete
            # raise "Event loop stopped before Future completed". That is the
            # expected escalation path (#373), not a crash, so it must not be
            # logged as one — but only when stop() actually forced it.
            if not self._forced_stop:
                logger.exception("Agent API server crashed")
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

    def _cancel_loop_tasks(self) -> None:
        """Cancel every task on the server loop and ask it to stop.

        Runs ON the loop thread (via ``call_soon_threadsafe``). Cancelling the
        outstanding MCP session / SSE / lifespan tasks is what lets
        ``run_until_complete(server.serve())`` return, so the thread can be
        joined promptly even while a client holds the SSE stream open (#373).
        """
        loop = self._loop
        if loop is None:
            return
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.stop()

    def _force_stop(
        self,
        server: uvicorn.Server | None,
        loop: asyncio.AbstractEventLoop | None,
    ) -> None:
        """Escalate a shutdown the graceful path did not finish (#373)."""
        self._forced_stop = True
        if server is not None:
            # Skips uvicorn's connection drain. Alone it does NOT fix #373 (the
            # MCP session/SSE tasks keep the loop alive past it), hence the
            # task cancellation below.
            server.force_exit = True
        if loop is not None and not loop.is_closed():
            with contextlib.suppress(RuntimeError):
                # Loop closed between the check and the call — nothing to do.
                loop.call_soon_threadsafe(self._cancel_loop_tasks)

    def stop(self, timeout: float = _STOP_TIMEOUT_S) -> None:
        """Stop the server (idempotent), joining the background thread.

        Leaving a uvicorn thread running is not a cosmetic problem: it keeps its
        listening socket and its main-thread bridge alive, so the process can
        crash later, somewhere unrelated, during Qt teardown. So a join that
        expires gets a second bounded chance, and surviving THAT is an ERROR
        rather than a warning — a leak nobody can see is a leak nobody fixes.

        An MCP client holding the SSE stream open used to defeat that: uvicorn's
        graceful shutdown waits for open connections, which such a client never
        closes, so ``serve()`` never returned and both joins expired (measured
        2026-10-02: 10.0 s with a client streaming, 0.19 s without — issue #373).
        So shutdown ESCALATES: ``should_exit`` first (clean, ~0.2 s when no
        client is attached), and only if the thread outlasts
        ``_GRACEFUL_STOP_S`` are the loop's tasks cancelled and the loop
        stopped. A dropped client stream at shutdown is the correct outcome.
        Cancelling unconditionally would also cancel uvicorn's lifespan task and
        log a CancelledError traceback at ERROR on every close.
        """
        with self._lock:
            server = self._server
            thread = self._thread
            loop = self._loop
            if server is not None:
                server.should_exit = True
            if thread is not None:
                thread.join(timeout=min(_GRACEFUL_STOP_S, timeout))
                if thread.is_alive():
                    self._force_stop(server, loop)
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning(
                        "Agent API server thread did not stop within %.1fs; "
                        "giving it a further %.1fs to unwind",
                        timeout,
                        _STOP_GRACE_S,
                    )
                    thread.join(timeout=_STOP_GRACE_S)
                if thread.is_alive():
                    logger.error(
                        "Agent API server thread %r is STILL RUNNING after "
                        "%.1fs + %.1fs; the process may crash during teardown",
                        SERVER_THREAD_NAME,
                        timeout,
                        _STOP_GRACE_S,
                    )
            self._thread = None
            self._server = None
            self._loop = None
