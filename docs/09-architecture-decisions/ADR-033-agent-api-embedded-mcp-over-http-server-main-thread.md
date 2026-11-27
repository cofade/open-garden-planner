---
id: ADR-033
title: "Agent API — Embedded MCP-over-HTTP Server + Main-Thread Marshaling Boundary (US-D1.1)"
status: "Accepted (Phase 13 — Package D, US-D1.1 spike). Read-only surface; built write-ready."
legacy_anchor: adr-033-agent-api--embedded-mcp-over-http-server--main-thread-marshaling-boundary-us-d11
---

# ADR-033: Agent API — Embedded MCP-over-HTTP Server + Main-Thread Marshaling Boundary (US-D1.1)

**Status**: Accepted (Phase 13 — Package D, US-D1.1 spike). Read-only surface; built write-ready.
**Context**: We want AI agents (Claude, Cursor, any MCP client) to work on the garden plan currently open in the GUI (epic #237). The app is a long-running PyQt6 GUI; classic stdio MCP servers are spawned per-session by the client and can't reach a running process. Edits (a later phase) must be safe against Qt's main-thread-only rule and go through the existing undo system, and the whole thing must bundle into the PyInstaller exe.
**Decision**:
- **Embed an MCP streamable-HTTP server inside the app.** `agent_api/server.py` builds a `FastMCP` (mcp Python SDK, pinned `>=1.12,<2.0`), takes its `streamable_http_app()` ASGI app, and drives it with a `uvicorn.Server` we own, run on a **daemon `threading.Thread`** with its own asyncio loop. We drive uvicorn ourselves (not `run_streamable_http_async`) so `stop()` can set `should_exit` + join cleanly. `stateless_http=True` (local single client → no SSE session to drain). Bound to **127.0.0.1 only**, **on by default** (read-only; a Settings toggle disables it), **auto-start on launch**, no auth (loopback trust; token auth is a hard prerequisite before write tools — delivered in **ADR-036**, US-D2.0). Default-on chosen after manual testing showed an opt-in toggle was an adoption dealbreaker (nobody enables a localhost server they can't see).
- **Main-thread marshaling boundary** (`agent_api/bridge.py`, `MainThreadBridge(QObject)`). Tool handlers run on a server thread and must never touch Qt directly. `run_on_main(fn)` emits a `QueuedConnection` signal carrying `(fn, concurrent.futures.Future)`; the slot runs `fn` on the main thread and resolves the future; the caller blocks on `future.result(timeout)`. This is the reusable, **write-ready** core — later edit tools route through it identically.
- **Async tool handlers are mandatory for Qt-touching tools.** Verified in mcp 1.28.1 `func_metadata`: the SDK calls a **sync** tool handler *inline on the event loop*, but `await`s an `async` one. A sync handler calling `run_on_main` would block the uvicorn loop on `future.result()`. So `get_plan_summary` is `async def` and offloads the blocking snapshot read via `await anyio.to_thread.run_sync(snapshot_provider)`, keeping the loop free. (The original spike comment claimed the SDK offloads sync tools to a thread — false; corrected here and in the `bridge.py` house-rule docstring.)
- **Clean shutdown.** `MainThreadBridge.abort_pending()` fails any in-flight `run_on_main` immediately; `application._stop_agent_api()` calls it *before* `server.stop()` so a tool request in flight at close can't deadlock the join on a main-thread hop the (tearing-down) main thread will never service. Server is stopped first in `closeEvent`.
- **Decoupled core.** The server depends only on an injected `snapshot_provider: () -> dict`, never the main window — so the server/schema/mapping are unit-testable without a GUI.
**Alternatives considered**:
- *Stdio MCP bridge process forwarding to the app over IPC* — matches the classic launch model but adds a relay process + handshake; the embedded HTTP server reaches the live app directly. Deferred.
- *Sync tool handler blocking the loop briefly per read* — works for one idle-GUI read but the documented model would be false and it risks a multi-second UI freeze on close; rejected in favour of async + `to_thread` + `abort_pending`.
- *Per-request scene serialization on the server thread* — unsafe (Qt off the main thread); the bridge is the price of live access.
## Addendum (#396 — the browser is a caller, and the Host/Origin guard is ours)

The "loopback trust" above reasons about a **local process** (an MCP client the
user launched). It does not cover a **browser**, which is a local process acting
on behalf of a remote page: a page on `evil.example` can reach
`http://127.0.0.1:8765/mcp`, and loopback binding does not stop it because the
request originates on this machine. The only barrier is the transport's
`Host`/`Origin` validation, so that guard is now **explicitly configured by OGP**
rather than inherited from the SDK:

- `build_server(..., host=..., port=...)` constructs
  `TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[...],
  allowed_origins=[...])` covering the bound loopback address, `localhost`, and the
  bound port, and passes it to `FastMCP(transport_security=...)`.
- A hostile `Host` is answered **421**, a hostile `Origin` **403**; the loopback
  connect URL and the "Connect AI Assistant" dialog keep working. The allow-lists
  name the **exact** host:port pairs (the bind address, `127.0.0.1`, `localhost`
  and the IPv6 loopback literal) with **no `:*` port wildcard**: the port is fixed
  for the life of the server, so a wildcard would only restore the breadth of the
  default this decision exists to replace.
- The dependency floor rises to **`mcp>=1.23`** — the first release whose FastMCP
  auto-enables the loopback guard. The explicit settings are the defence; the
  floor stops the SDK default from silently regressing under us.

**Why this was a product decision and not just a version bump.** The audit
measured that under the old floor a 1.22.0 wheel answered a crafted
`Host: evil.example` initialize with **HTTP 200 and a full MCP result** (all six
hostile variants), while the 1.30.0 wheel that every released exe bundled answers
421/403. So no shipped exe is known to be exposed, but the exposure was a property
of *whichever wheel resolved at build time* rather than of the product — the kind
of inheritance this codebase has been bitten by before. `build_server` now takes
the host/port it will bind, which is also what makes the allow-list exact instead
of a wildcard.

**Consequence for tests.** The black-box 421/403 tests alone are not sufficient:
with mcp 1.30.0 installed they **pass even with our settings deleted** (measured —
the SDK's loopback auto-enable covers the behaviour). Worse, an assertion of the
form "the settings object is not None and the flag is True" *also* passes with our
configuration removed, because the SDK auto-enable returns exactly such an object.
The assertions that actually detect removal are the ones the SDK default cannot
satisfy: that `allowed_hosts` names the **bound port** (the default carries no
port-specific entry) and that no entry is a `*` / `:*` wildcard. Measured: deleting
the `transport_security=` argument fails three of the four object-level tests.

**Still unchanged**: tokenless read tools remain loopback trust (challenged
decision C2 in the audit snapshot) — this addendum only makes the browser vector
explicit and enforced, and does not re-open that question.

**Consequences**: New runtime deps (`mcp`, `uvicorn`, `starlette`, `pydantic` + transitive `anyio`/`sse-starlette`/`pydantic-core`/`pydantic-settings`/`httpx`/`cryptography`), bundled via `installer/ogp.spec` (see §7 deployment). If the main thread is wedged longer than the bridge's `DEFAULT_TIMEOUT_S`, `run_on_main` raises (on the offload worker) and the SDK surfaces it to the client as a tool error — the agent sees a failed call, the GUI never hangs. MCP tool/resource/prompt descriptions are an English API contract (exempt from i18n); only the Settings UI strings go through `tr()`. No `FILE_VERSION` change (read-only + an additive `snapshot_dict` built from the existing serializer). Tests: `tests/unit/test_agent_api_bridge.py` (marshaling, exception/timeout/abort), `tests/integration/test_agent_api_server.py` (real MCP client end-to-end). The marshaling boundary is the contract D2 (write tools) builds on.
