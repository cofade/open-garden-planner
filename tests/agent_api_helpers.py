"""Shared helpers for tests that need a real `AgentApiServer` on a loopback port (#509).

**Why this module exists.** Ten test files each carried their own copy of
`_free_port()`:

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

That is this repository's "a second copy of a gate list is how a gate goes missing"
shape, and it had a cost beyond duplication. `free_port()` is **not a reservation**:
the probe socket is closed before the caller binds, so the port is free in name only.
Under serial execution the window is microscopic. Under `pytest -n auto` it is not —
measured with 20 workers, `test_agent_api_dns_rebinding.py` failed with
`RuntimeError: Agent API server failed to start`, because the thread's own
`create_server` hit `OSError: [Errno 10048]` after the pre-bind check had already
passed.

So the fix is not "pick a better port". It is **retry**, because losing the race is
inherent to asking the OS for a port and then releasing it. `start_server()` below
takes a fresh port and tries again.

**What it deliberately does not do.** It does not catch `RuntimeError` wholesale. A
`RuntimeError` from `start()` with any other message is a product failure and is
re-raised immediately rather than retried five times — a helper that swallows real
defects is worse than the flake it was written to remove.
"""

from __future__ import annotations

import socket
from typing import Any

from open_garden_planner.agent_api.server import AgentApiServer, PortInUseError

# The only RuntimeError `AgentApiServer.start()` raises for "the bind lost a race" is
# this one; `start()` raises it after the server thread dies before uvicorn is
# listening (server.py:2667). Matching the message is what keeps an unrelated
# RuntimeError from being mistaken for a port collision.
NOT_STARTED = "Agent API server failed to start"

# A collision needs two workers drawing the same ephemeral port within the same
# millisecond. Six attempts makes a second collision improbable without turning a real
# problem into a long silent wait.
PORT_ATTEMPTS = 6


def free_port() -> int:
    """Ask the OS for an unused loopback port.

    This does **not** reserve it — see the module docstring. Use `start_server()`,
    not this function plus a bare `start()`, or you have reintroduced the race.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(providers: Any, **kwargs: Any) -> tuple[AgentApiServer, int]:
    """Start a real server on an OS-assigned port, retrying if the port was taken.

    Returns the running server and the port it actually bound, because callers
    address it by port in HTTP probes.

    Args:
        providers: the `AgentProviders` bundle to serve.
        **kwargs: passed through to `AgentApiServer` (write_token, writes_enabled).
    """
    for attempt in range(PORT_ATTEMPTS):
        port = free_port()
        server = AgentApiServer(providers, port=port, **kwargs)
        try:
            server.start()
        except PortInUseError:
            # The pre-bind socket check saw the port busy. Nothing was started.
            continue
        except RuntimeError as exc:
            if str(exc) != NOT_STARTED:
                raise
            # The thread lost the race inside create_server and died. `start()` has
            # already cleared its thread/server references, so there is nothing to stop.
            continue
        # `start()` returning normally has TWO meanings, and the difference matters:
        # either uvicorn reported itself ready, or the ready-deadline expired and it
        # logged a warning (server.py:2671). `AgentApiServer.is_running` is only "the
        # thread is alive", which is true in both - so testing it would hand back a
        # server that is running but not listening, which is the exact defect this
        # module's docstring says it refuses to create. Use the same predicate
        # `start()` itself waited on. It reaches into a private attribute because the
        # class exposes no public readiness check; that is a gap worth noting, not a
        # licence to use the weaker one.
        if getattr(server._server, "started", False):
            return server, port
        # Not ready, and this is not a port collision: a readiness that misses its
        # deadline is a product-side delay. Do not retry it - retrying here is what
        # turns a real defect into a slow pass. Stop the live thread first, because
        # abandoning it would leak a running server and eventually a port.
        server.stop()
        raise AssertionError(
            f"the AgentApiServer on port {port} did not become ready within its "
            f"deadline (attempt {attempt + 1}/{PORT_ATTEMPTS}). `start()` logged a "
            "warning instead of raising, so the thread was alive but uvicorn never "
            "reported `started`. Retrying would hide a product-side delay."
        )
    # Only reachable by exhausting every attempt on a genuine collision. Without this
    # the function falls off the end and hands back `None` for the caller to unpack,
    # which surfaces as a TypeError about tuples rather than about ports.
    raise AssertionError(
        f"could not start an AgentApiServer on an ephemeral port in "
        f"{PORT_ATTEMPTS} attempts; this is not a port collision any more, so it is "
        f"reported rather than retried silently"
    )
