"""Main-thread marshaling boundary for the Agent API.

The embedded MCP server (see :mod:`open_garden_planner.agent_api.server`) runs on
a background thread; its tool handlers must NOT touch Qt objects directly because
Qt is not thread-safe. :class:`MainThreadBridge` lets a worker thread run a
callable ON the Qt main thread and get the result (or exception) back
synchronously.

**House rule** (verified against mcp 1.28.1 ``func_metadata`` tool dispatch): the
MCP SDK calls a *synchronous* tool handler **inline on the asyncio event loop**;
only ``async def`` handlers yield the loop. So a Qt-touching tool must NOT call
:meth:`run_on_main` from a sync handler — that would block the uvicorn loop on
``Future.result()``. Instead, declare the tool ``async def`` and offload the
blocking call to a worker thread, e.g.::

    @mcp.tool()
    async def get_plan_summary() -> PlanSummary:
        return await anyio.to_thread.run_sync(snapshot_provider)  # provider calls run_on_main

That worker thread then blocks in :meth:`run_on_main` while the event loop stays
free. :meth:`abort_pending` lets shutdown unblock any in-flight call immediately
so closing the app never waits on a stalled main-thread hop.

This bridge is the reusable, write-ready core: later phases route edits through
``run_on_main`` exactly the same way reads do.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from concurrent.futures import Future, InvalidStateError
from typing import Any, TypeVar

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal

T = TypeVar("T")

#: Default time a worker waits for the main thread to service a queued call.
DEFAULT_TIMEOUT_S = 5.0


class BridgeClosedError(RuntimeError):
    """Raised in a worker when its queued main-thread call is aborted (shutdown)."""


class MainThreadBridge(QObject):
    """Run callables on the Qt main thread from any thread, synchronously."""

    # Carry the callable + its Future as opaque objects so PyQt does not try to
    # marshal them through the C++ type system.
    _invoke = pyqtSignal(object, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._pending: set[Future[Any]] = set()
        # QueuedConnection => the slot runs in the thread that owns this QObject
        # (the main thread), regardless of which thread emits the signal.
        self._invoke.connect(  # type: ignore[call-arg]
            self._on_invoke, Qt.ConnectionType.QueuedConnection
        )

    def run_on_main(self, fn: Callable[[], T], *, timeout: float = DEFAULT_TIMEOUT_S) -> T:
        """Execute ``fn`` on the main thread and return its result.

        If called from the main thread, ``fn`` runs inline (no event-loop hop).
        Otherwise the call is queued to the main thread and this method blocks
        (up to ``timeout`` seconds) for the result. Exceptions raised by ``fn``
        propagate to the caller; a timeout raises
        ``concurrent.futures.TimeoutError``; an :meth:`abort_pending` during the
        wait raises :class:`BridgeClosedError`.
        """
        if QThread.currentThread() is self.thread():
            return fn()
        future: Future[T] = Future()
        with self._lock:
            self._pending.add(future)
        try:
            self._invoke.emit(fn, future)
            return future.result(timeout=timeout)
        finally:
            with self._lock:
                self._pending.discard(future)

    def abort_pending(self) -> None:
        """Fail every in-flight :meth:`run_on_main` call immediately.

        Called on shutdown so blocked worker threads return at once, letting the
        server's event loop process ``should_exit`` without waiting on the main
        thread (which is busy tearing down). Safe to call repeatedly.
        """
        with self._lock:
            pending = list(self._pending)
        for future in pending:
            if not future.done():
                # InvalidStateError: raced with _on_invoke completing it — fine.
                with contextlib.suppress(InvalidStateError):
                    future.set_exception(BridgeClosedError("Agent API shutting down"))

    def _on_invoke(self, fn: Callable[[], Any], future: Future[Any]) -> None:
        """Run a queued callable on the main thread and resolve its future."""
        if future.done():
            return  # aborted (abort_pending) before we got here
        try:
            result = fn()
        except BaseException as exc:  # noqa: BLE001 - propagate to the caller thread
            # InvalidStateError: raced with abort_pending; the caller already saw
            # BridgeClosedError, so dropping this result is correct.
            with contextlib.suppress(InvalidStateError):
                future.set_exception(exc)
        else:
            with contextlib.suppress(InvalidStateError):
                future.set_result(result)
