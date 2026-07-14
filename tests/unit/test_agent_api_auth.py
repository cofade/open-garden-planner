"""Unit tests for the Agent API write-tool bearer-token gate (US-D2.0).

These exercise the pure gate logic without a running server:
  - ``_require_write_auth`` accepts the exact token, rejects wrong/missing.
  - ``_bearer_token_middleware`` extracts the header into the ContextVar.
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


def _run_middleware(headers: list[tuple[bytes, bytes]]) -> str | None:
    """Drive the ASGI middleware with a fake HTTP scope; return the captured token."""
    captured: dict[str, str | None] = {}

    async def inner(scope: dict[str, Any], receive: Any, send: Any) -> None:
        captured["token"] = _presented_token.get()

    wrapped = _bearer_token_middleware(inner)

    async def drive() -> None:
        _presented_token.set("stale-from-a-previous-request")
        await wrapped({"type": "http", "headers": headers}, None, None)

    asyncio.run(drive())
    return captured["token"]


def test_middleware_extracts_bearer_token() -> None:
    assert _run_middleware([(b"authorization", b"Bearer abc123")]) == "abc123"


def test_middleware_is_case_insensitive_on_scheme() -> None:
    assert _run_middleware([(b"authorization", b"bearer abc123")]) == "abc123"


def test_middleware_sets_none_without_header() -> None:
    # No Authorization header -> None (not the stale value from a prior request).
    assert _run_middleware([(b"content-type", b"application/json")]) is None


def test_middleware_ignores_non_bearer_scheme() -> None:
    assert _run_middleware([(b"authorization", b"Basic Zm9v")]) is None
