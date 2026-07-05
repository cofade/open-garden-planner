#!/usr/bin/env python3
"""Probe the Open Garden Planner Agent API (embedded MCP server) — stdlib only.

The running GUI hosts a read-only MCP streamable-HTTP server on
http://127.0.0.1:8765/mcp (loopback only, stateless). This script lets you
inspect it without an MCP client:

    python3 probe_agent_api.py                    # list tool names
    python3 probe_agent_api.py --port 9000        # non-default port
    python3 probe_agent_api.py --call get_plan_summary
    python3 probe_agent_api.py --call nearest_objects --args '{"x":100,"y":200,"k":3}'

Exit codes:
    0  success
    2  bad usage / bad --args JSON
    3  cannot connect (app not running, Agent API disabled, or wrong port)
    4  server responded but with an error / unparseable payload

Responses may arrive as plain JSON or as Server-Sent Events (SSE,
``data: {...}`` lines) — both are handled. If the server demands an
``initialize`` handshake first (non-stateless config), one is attempted
automatically and any ``mcp-session-id`` header is forwarded.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-03-26"


def _post(url: str, payload: dict, session_id: str | None = None):
    """POST a JSON-RPC message; return (parsed JSON-RPC response, session-id)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        sid = resp.headers.get("mcp-session-id")
        body = resp.read().decode("utf-8", errors="replace")
        ctype = resp.headers.get("Content-Type", "")
    if "text/event-stream" in ctype:
        # Take the last data: line that parses as JSON (SSE framing).
        parsed = None
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    parsed = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        return parsed, sid
    if not body.strip():
        return None, sid  # notifications get empty 202 replies
    return json.loads(body), sid


def _rpc(url: str, method: str, params: dict | None, msg_id: int,
         session_id: str | None):
    payload: dict = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        payload["params"] = params
    return _post(url, payload, session_id)


def _initialize(url: str):
    """Perform the MCP initialize handshake; return the session id (if any)."""
    resp, sid = _rpc(url, "initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "probe_agent_api", "version": "1.0"},
    }, msg_id=0, session_id=None)
    if resp is not None and "error" in resp:
        raise RuntimeError(f"initialize failed: {resp['error']}")
    # Fire-and-forget initialized notification (some configs require it).
    try:
        _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    except (urllib.error.HTTPError, urllib.error.URLError):
        pass
    return sid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--path", default="/mcp")
    ap.add_argument("--call", metavar="TOOL", help="call a tool instead of listing")
    ap.add_argument("--args", default="{}", metavar="JSON",
                    help="JSON object of tool arguments (with --call)")
    opts = ap.parse_args()

    url = f"http://{opts.host}:{opts.port}{opts.path}"
    try:
        tool_args = json.loads(opts.args)
    except json.JSONDecodeError as exc:
        print(f"bad --args JSON: {exc}", file=sys.stderr)
        return 2

    if opts.call:
        method, params = "tools/call", {"name": opts.call, "arguments": tool_args}
    else:
        method, params = "tools/list", None

    session_id: str | None = None
    for attempt in (1, 2):
        try:
            resp, _ = _rpc(url, method, params, msg_id=1, session_id=session_id)
        except (ConnectionError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            print(f"CANNOT CONNECT to {url}: {reason}\n"
                  "-> Is the app running? Is the Agent API enabled in "
                  "Preferences? Default port is 8765.", file=sys.stderr)
            return 3
        except urllib.error.HTTPError as exc:
            if attempt == 1:  # maybe the server wants an initialize first
                try:
                    session_id = _initialize(url)
                    continue
                except Exception as exc2:  # noqa: BLE001
                    print(f"HTTP {exc.code} and handshake failed: {exc2}",
                          file=sys.stderr)
                    return 4
            print(f"HTTP error from server: {exc}", file=sys.stderr)
            return 4
        break

    if resp is None:
        print("empty/unparseable response from server", file=sys.stderr)
        return 4
    if "error" in resp:
        print(f"JSON-RPC error: {json.dumps(resp['error'], indent=2)}",
              file=sys.stderr)
        return 4

    result = resp.get("result", {})
    if opts.call:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        tools = result.get("tools", [])
        print(f"{len(tools)} tool(s) at {url}:")
        for t in tools:
            desc = (t.get("description") or "").strip().splitlines()
            print(f"  - {t['name']}: {desc[0] if desc else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
