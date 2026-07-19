"""Unit tests for the Agent API write-tool bearer-token gate (US-D2.0).

These exercise the pure gate logic without a running server:
  - ``_require_write_auth`` accepts the exact token, rejects wrong/missing.
  - ``_bearer_token_middleware`` extracts the token from either the
    ``Authorization: Bearer`` header or the ``?token=`` query param into the
    ContextVar (the URL query token wins when both are present).
  - the write tools are registered only when writes are enabled AND a token
    is configured (the ADR-033/ADR-036 gate).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from open_garden_planner.agent_api.providers import AgentProviders
from open_garden_planner.agent_api.server import (
    WriteAuthError,
    _bearer_token_middleware,
    _presented_token,
    _require_write_auth,
    build_server,
)


def _stub_providers() -> AgentProviders:
    def _boom(*_a: Any) -> dict[str, Any]:
        raise AssertionError("provider must not run in an auth-only test")

    return AgentProviders(
        snapshot=lambda: {},
        diagnostics=lambda: [],
        render=lambda *_a: {},
        save_plan=lambda _p: {},
        export_pdf=lambda *_a: {},
        export_dxf=lambda _p: {},
        export_csv=lambda *_a: {},
        move_object=_boom,
        delete_object=_boom,
    )


def _tool_names(mcp: Any) -> list[str]:
    return [t.name for t in asyncio.run(mcp.list_tools())]


def test_require_write_auth_accepts_exact_token() -> None:
    _presented_token.set("s3cret")
    _require_write_auth("s3cret")  # no raise


@pytest.mark.parametrize("presented", [None, "", "wrong", "s3cre", "s3crett"])
def test_require_write_auth_rejects_bad_token(presented: str | None) -> None:
    _presented_token.set(presented)
    with pytest.raises(WriteAuthError):
        _require_write_auth("s3cret")


def test_require_write_auth_rejects_non_ascii_without_raising_typeerror() -> None:
    """secrets.compare_digest raises TypeError on non-ASCII str input; a
    malformed/hostile Authorization header must fail closed as a normal
    WriteAuthError, never propagate an unhandled exception."""
    _presented_token.set("café")
    with pytest.raises(WriteAuthError):
        _require_write_auth("s3cret")


def test_require_write_auth_rejects_when_no_token_configured() -> None:
    # Even a present header can't authorise if the server has no token.
    _presented_token.set("anything")
    with pytest.raises(WriteAuthError):
        _require_write_auth(None)


def test_write_tools_absent_when_writes_disabled() -> None:
    names = _tool_names(build_server(_stub_providers(), writes_enabled=False))
    assert "move_object" not in names
    assert "delete_object" not in names
    # Read tools still present.
    assert "get_plan_summary" in names


def test_write_tools_absent_when_token_missing() -> None:
    names = _tool_names(
        build_server(_stub_providers(), writes_enabled=True, write_token=None)
    )
    assert "move_object" not in names
    assert "delete_object" not in names


def test_write_tools_present_when_enabled_and_tokened() -> None:
    names = _tool_names(
        build_server(_stub_providers(), writes_enabled=True, write_token="tok")
    )
    assert "move_object" in names
    assert "delete_object" in names


def _run_middleware(
    headers: list[tuple[bytes, bytes]], query_string: bytes = b""
) -> str | None:
    """Drive the ASGI middleware with a fake HTTP scope; return the captured token."""
    return _run_middleware_full(headers, query_string)["token"]


def _run_middleware_full(
    headers: list[tuple[bytes, bytes]], query_string: bytes = b""
) -> dict[str, Any]:
    """Like ``_run_middleware`` but also returns the (possibly mutated) scope's
    ``query_string`` as seen by the downstream app."""
    captured: dict[str, Any] = {}

    async def inner(scope: dict[str, Any], receive: Any, send: Any) -> None:
        captured["token"] = _presented_token.get()
        captured["downstream_query_string"] = scope.get("query_string")

    wrapped = _bearer_token_middleware(inner)

    async def drive() -> None:
        _presented_token.set("stale-from-a-previous-request")
        scope = {"type": "http", "headers": headers, "query_string": query_string}
        await wrapped(scope, None, None)

    asyncio.run(drive())
    return captured


def test_middleware_extracts_bearer_token() -> None:
    assert _run_middleware([(b"authorization", b"Bearer abc123")]) == "abc123"


def test_middleware_is_case_insensitive_on_scheme() -> None:
    assert _run_middleware([(b"authorization", b"bearer abc123")]) == "abc123"


def test_middleware_sets_none_without_header() -> None:
    # No Authorization header -> None (not the stale value from a prior request).
    assert _run_middleware([(b"content-type", b"application/json")]) is None


def test_middleware_ignores_non_bearer_scheme() -> None:
    assert _run_middleware([(b"authorization", b"Basic Zm9v")]) is None


def test_middleware_extracts_query_param_token() -> None:
    # The ?token= route Claude Code needs (headers not transmitted on tool calls).
    assert _run_middleware([], query_string=b"token=abc123") == "abc123"


def test_middleware_query_token_among_other_params() -> None:
    assert _run_middleware([], query_string=b"foo=bar&token=abc123&baz=1") == "abc123"


def test_middleware_query_token_wins_over_header() -> None:
    # Both present: the URL query token wins (it's the reliable primary channel;
    # a stale legacy header must not shadow a fresh URL token).
    got = _run_middleware(
        [(b"authorization", b"Bearer from-header")], query_string=b"token=from-query"
    )
    assert got == "from-query"


def test_middleware_falls_back_to_query_when_header_non_bearer() -> None:
    # A non-Bearer header yields no header token, so the query param is used.
    got = _run_middleware(
        [(b"authorization", b"Basic Zm9v")], query_string=b"token=from-query"
    )
    assert got == "from-query"


def test_middleware_sets_none_without_header_or_query() -> None:
    assert _run_middleware([], query_string=b"") is None


def test_middleware_strips_token_from_scope_for_downstream() -> None:
    # Defense-in-depth: the secret must not survive in the scope the MCP app /
    # any access logger sees.
    got = _run_middleware_full([], query_string=b"foo=bar&token=s3cret&baz=1")
    assert got["token"] == "s3cret"
    downstream = got["downstream_query_string"].decode("latin-1")
    assert "token" not in downstream
    assert "s3cret" not in downstream
    # Other params are preserved.
    assert "foo=bar" in downstream
    assert "baz=1" in downstream


def test_middleware_leaves_scope_untouched_when_token_in_header() -> None:
    # No query token to strip; the query string passes through unchanged.
    got = _run_middleware_full(
        [(b"authorization", b"Bearer h")], query_string=b"foo=bar"
    )
    assert got["token"] == "h"
    assert got["downstream_query_string"] == b"foo=bar"


def test_middleware_strips_query_token_even_when_header_present() -> None:
    # A query token is stripped from the scope regardless of whether a header is
    # also present — the secret must never survive downstream.
    got = _run_middleware_full(
        [(b"authorization", b"Bearer h")], query_string=b"token=s3cret&keep=1"
    )
    downstream = got["downstream_query_string"].decode("latin-1")
    assert "s3cret" not in downstream
    assert "keep=1" in downstream
