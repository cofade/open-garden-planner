"""Tests for tests/agent_api_helpers.py — the port-race retry (#509).

The helper exists because ten test files each had their own copy of a
`_free_port()` that does not reserve anything, and under `-n auto` a worker could
lose the race between the probe socket closing and the server binding.

A retry helper has one dangerous failure mode, and it is the mirror image of the bug
it fixes: **it swallows real defects.** `AgentApiServer.start()` raises `RuntimeError`
when the server thread dies before listening, which is the race — but it can raise a
`RuntimeError` for other reasons too, and those must surface immediately rather than
burn five attempts and then report a port collision that never happened. These tests
pin that distinction, because it is the part a future edit would plausibly get wrong.
"""

from __future__ import annotations

import socket

import pytest

from open_garden_planner.agent_api.server import PortInUseError
from tests.agent_api_helpers import NOT_STARTED, PORT_ATTEMPTS, free_port, start_server


class _FakeUvicorn:
    """The uvicorn object `start()` waits on via `getattr(server, "started", False)`."""

    def __init__(self) -> None:
        self.started = False


class _FakeServer:
    """Stands in for `AgentApiServer`; records the ports it was constructed with.

    Models the real class's two distinct readiness states, because that distinction is
    the one the helper depends on:

    - `is_running` is "the thread is alive", and it is true whether or not uvicorn ever
      reported `started`;
    - `_server.started` is what `start()` itself polls, and it is the only true
      readiness signal.

    A fake that conflates them cannot test the difference — and conflating them is
    exactly the bug this helper's second round of review caught.
    """

    def __init__(self, providers: object, *, port: int, **kwargs: object) -> None:
        self.providers = providers
        self.port = port
        self.kwargs = kwargs
        self.start_calls = 0
        self.stopped = False
        self._running = False
        self._server = _FakeUvicorn()

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self.start_calls += 1
        self._running = True
        self._server.started = True

    def stop(self) -> None:
        self.stopped = True
        self._running = False


def _bindable_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_free_port_returns_a_bindable_port() -> None:
    port = free_port()
    assert 1024 < port < 65536
    # Still bindable: the point is that the OS offered it, not that we kept it.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


def test_happy_path_starts_once_and_returns_the_bound_port(monkeypatch) -> None:
    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", _FakeServer)
    server, port = start_server(object(), write_token="tok")
    assert server.start_calls == 1
    assert server.port == port
    assert server.kwargs == {"write_token": "tok"}


def test_retries_when_the_pre_bind_check_finds_the_port_busy(monkeypatch) -> None:
    """`PortInUseError` is the documented collision signal — retry it."""
    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", _FakeServer)
    attempts: list[int] = []

    def flaky(providers: object, *, port: int, **kwargs: object) -> _FakeServer:
        attempts.append(port)
        server = _FakeServer(providers, port=port, **kwargs)
        if len(attempts) < 3:
            server.start = _raise(PortInUseError(port))  # type: ignore[method-assign]
        return server

    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", flaky)
    server, port = start_server(object())
    assert len(attempts) == 3, "should have taken a fresh port after each collision"
    assert len(set(attempts)) > 1, "a retry must draw a NEW port, not reuse the old one"
    assert port == attempts[-1]


def test_retries_when_the_thread_dies_before_listening(monkeypatch) -> None:
    """The measured failure: the thread hit EADDRINUSE inside create_server."""
    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", _FakeServer)
    calls = {"n": 0}

    def flaky(providers: object, *, port: int, **kwargs: object) -> _FakeServer:
        calls["n"] += 1
        server = _FakeServer(providers, port=port, **kwargs)
        if calls["n"] == 1:
            server.start = _raise(RuntimeError(NOT_STARTED))  # type: ignore[method-assign]
        return server

    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", flaky)
    server, _port = start_server(object())
    assert calls["n"] == 2
    assert server.is_running


def test_a_different_runtime_error_is_a_product_failure_and_must_surface(monkeypatch) -> None:
    """The mirror-image risk: an unrelated RuntimeError must not be retried."""
    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", _FakeServer)
    calls = {"n": 0}

    def broken(providers: object, *, port: int, **kwargs: object) -> _FakeServer:
        calls["n"] += 1
        server = _FakeServer(providers, port=port, **kwargs)
        server.start = _raise(RuntimeError("tool registration blew up"))  # type: ignore[method-assign]
        return server

    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", broken)
    with pytest.raises(RuntimeError, match="tool registration blew up"):
        start_server(object())
    assert calls["n"] == 1, "must not burn attempts on a failure that is not a port race"


def test_exhausting_the_attempts_is_reported_not_retried_forever(monkeypatch) -> None:
    """Two things at once, because they are the same assertion.

    The loop is bounded, and the bound is reported rather than retried silently. It must
    also not **fall off its end**: a retry loop that exhausts without an explicit raise
    returns `None` implicitly, and the caller then fails at the unpacking with a
    TypeError about tuples — which says nothing about ports and sends the next reader
    looking in the wrong place. That hole was real: it was introduced in this same change
    while the readiness branch above was being rewritten, which is why the bound needs a
    test of its own rather than being trusted as a `for`-loop's obvious ending.
    """
    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", _FakeServer)

    def always_busy(providers: object, *, port: int, **kwargs: object) -> _FakeServer:
        server = _FakeServer(providers, port=port, **kwargs)
        server.start = _raise(PortInUseError(port))  # type: ignore[method-assign]
        return server

    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", always_busy)
    with pytest.raises(AssertionError, match="not a port collision"):
        start_server(object())


def test_a_server_that_returns_but_never_became_ready_is_reported_not_retried(monkeypatch) -> None:
    """`start()` returning normally does not mean uvicorn is listening.

    The thread hit the ready-deadline instead of the death check, so `start()` returned
    with a logged warning and `is_running` True. The first version of this test asserted
    the opposite - that the helper retries into a working server - which is the
    mirror-image defect: a readiness that misses its deadline is a product-side delay,
    not a port collision, and retrying it turns a real defect into a slow pass.

    It also asserts the live thread is stopped. Abandoning it would leak a running
    server and, eventually, the port.
    """
    created: list[_FakeServer] = []

    def silent(providers: object, *, port: int, **kwargs: object) -> _FakeServer:
        server = _FakeServer(providers, port=port, **kwargs)
        # The thread comes up but never reports `started` — the deadline path.
        server.start = lambda: server._server.__setattr__("started", False)  # type: ignore[method-assign]
        server._running = True
        created.append(server)
        return server

    monkeypatch.setattr("tests.agent_api_helpers.AgentApiServer", silent)
    with pytest.raises(AssertionError, match="did not become ready"):
        start_server(object())
    assert len(created) == 1, "a readiness deadline is not a collision; do not retry it"
    assert created[0].stopped, "the live thread must be stopped, not abandoned"


def test_attempt_count_is_bounded() -> None:
    """A retry loop with no ceiling is a hang, not a retry."""
    assert 2 <= PORT_ATTEMPTS <= 10


def _raise(exc: BaseException):
    def _do_raise() -> None:
        raise exc

    return _do_raise
