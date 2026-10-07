# ruff: noqa: ARG001, ARG002
"""#396 — the Agent API's only browser barrier is now OGP's, not an SDK default.

The loopback MCP server is unauthenticated for reads by design (ADR-033
loopback trust), so the thing that stops a web page from reaching it through DNS
rebinding is the ``Host``/``Origin`` validation the transport applies. That
validation used to be a property of whichever ``mcp`` wheel resolved at build
time: with the declared floor (``>=1.12``) a 1.22.0 wheel answered a crafted
``Host: evil.example`` initialize with **HTTP 200 and a full MCP result**, while
1.23.0+ answers 421. These tests pin OUR configuration, both as an object
(asserted directly) and over the real transport (the behaviour that matters).

The object-level assertion is what makes the suite meaningful: with the SDK
default alone, a 1.30.0 wheel would pass the black-box tests while a 1.22.0
wheel silently exposed the server. Deleting the explicit settings must break
these tests — see ``test_the_bound_port_appears_in_the_allow_lists`` (renamed from
``test_settings_are_constructed_by_ogp_not_inherited`` in b6353e7).

Measured on master (v1.29.4, mcp 1.30.0 installed) with this file in place: the
421/403 transport tests PASS even with our settings deleted, and so does a naive
"settings is not None and the flag is True" assertion — the installed SDK's
loopback auto-enable produces exactly that object. The assertions here are
therefore deliberately the ones the SDK default *cannot* satisfy: that
``allowed_hosts`` names the bound port, and that nothing is a wildcard. Deleting
the ``transport_security=`` argument fails 3 of the 4 object-level tests.

The exposure this closes is a source install resolving <=1.22, where the same
PoC returned HTTP 200 with a full initialize result.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

import pytest

from open_garden_planner.agent_api import providers as _providers
from open_garden_planner.agent_api.server import AgentApiServer, build_server


def _stub_providers() -> _providers.AgentProviders:
    return _providers.AgentProviders(
        **dict.fromkeys(_providers.AgentProviders.__dataclass_fields__)
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# ── Unit level: the settings OGP constructs ────────────────────────────────────

class TestExplicitTransportSecurity:
    def _settings(self, port: int) -> Any:
        mcp = build_server(_stub_providers(), port=port)
        return mcp.settings.transport_security

    def test_the_bound_port_appears_in_the_allow_lists(self) -> None:
        """The assertion that detects removal of our explicit settings.

        Deliberately NOT ``settings is not None`` / the enable flag: with mcp
        1.30.0 installed the SDK auto-enables protection for a loopback host and
        returns a non-None settings object with the flag already True, so those
        two assertions pass with our configuration deleted (measured). What the
        SDK default does NOT carry is a port-specific allow-list, so naming the
        bound port is what actually pins the behaviour.
        """
        port = _free_port()
        allowed = self._settings(port).allowed_hosts
        assert f"127.0.0.1:{port}" in allowed, (
            "allowed_hosts must name the bound port explicitly; the SDK default "
            "has no port-specific entry, which is what made this a product "
            "property rather than ours (#396)"
        )
        assert f"localhost:{port}" in allowed

    def test_no_wildcard_port_or_host_entries(self) -> None:
        """A ``*`` or ``:*`` entry would restore the SDK default's breadth."""
        settings = self._settings(_free_port())
        for entry in [*settings.allowed_hosts, *settings.allowed_origins]:
            assert not entry.endswith(":*"), entry
            assert entry.strip() not in ("*", ""), entry

    def test_allow_lists_have_no_duplicates(self) -> None:
        """``host`` defaults to 127.0.0.1, so a naive list repeats that entry."""
        settings = self._settings(8765)
        assert len(settings.allowed_hosts) == len(set(settings.allowed_hosts))
        assert len(settings.allowed_origins) == len(set(settings.allowed_origins))

    def test_a_non_loopback_bind_host_is_carried_through(self) -> None:
        """The list is built from the host actually bound, not hardcoded."""
        settings = build_server(_stub_providers(), host="localhost", port=9999)
        assert "localhost:9999" in settings.settings.transport_security.allowed_hosts


# ── Transport level: the behaviour a browser actually meets ────────────────────

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "rebind-probe", "version": "0"},
    },
}


def _post(port: int, headers: dict[str, str]) -> tuple[int, str]:
    """POST a real MCP initialize with hand-crafted headers; return (status, body)."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(_INITIALIZE).encode(),
        headers={
            "Content-Type": "application/json",
            # The streamable-HTTP transport requires both media types in
            # Accept; without it the protocol layer answers 406 and the probe
            # would never reach the security middleware.
            "Accept": "application/json, text/event-stream",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


@pytest.fixture()
def live_server(qtbot: Any) -> Any:
    """A real AgentApiServer on an ephemeral loopback port."""
    port = _free_port()
    server = AgentApiServer(_stub_providers(), port=port)
    server.start()
    qtbot.waitUntil(lambda: bool(server.is_running), timeout=20000)
    yield server, port
    server.stop()


class TestHostHeaderValidation:
    def test_normal_host_is_accepted(self, live_server: Any) -> None:
        _server, port = live_server
        status, _body = _post(port, {"Host": f"127.0.0.1:{port}"})
        assert status == 200

    @pytest.mark.parametrize("host", ["evil.example", "evil.example:{port}"])
    def test_hostile_host_is_rejected_with_421(
        self, live_server: Any, host: str
    ) -> None:
        _server, port = live_server
        status, _body = _post(port, {"Host": host.format(port=port)})
        assert status == 421, "a non-loopback Host must not reach the MCP endpoint"


class TestOriginValidation:
    def test_loopback_origin_is_accepted(self, live_server: Any) -> None:
        _server, port = live_server
        status, _body = _post(
            port, {"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"}
        )
        assert status == 200

    @pytest.mark.parametrize("origin", ["http://evil.example", "https://evil.example"])
    def test_hostile_origin_is_rejected_with_403(
        self, live_server: Any, origin: str
    ) -> None:
        _server, port = live_server
        status, _body = _post(port, {"Host": f"127.0.0.1:{port}", "Origin": origin})
        assert status == 403, "a remote Origin must not reach the MCP endpoint"


class TestDeclaredFloorMatchesTheBehaviour:
    def test_floor_is_1_23_or_newer(self) -> None:
        """The declared dependency floor is the first SDK that auto-enables the
        loopback guard; a lower floor admits wheels where it is off (#396)."""
        import re
        from pathlib import Path

        pyproject = (
            Path(__file__).resolve().parents[2] / "pyproject.toml"
        ).read_text(encoding="utf-8")
        match = re.search(r'"mcp>=(\d+)\.(\d+)', pyproject)
        assert match is not None, "could not find the mcp floor in pyproject.toml"
        major, minor = int(match.group(1)), int(match.group(2))
        assert (major, minor) >= (1, 23), (
            f"mcp floor is {major}.{minor}; the loopback transport-security "
            "auto-enable first appears in 1.23.0"
        )
