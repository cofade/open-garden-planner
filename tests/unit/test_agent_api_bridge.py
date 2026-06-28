"""Unit tests for the Agent API main-thread marshaling bridge.

The bridge lets a worker thread run a callable on the Qt main thread and get the
result back. These tests drive it from a real worker thread while the main test
thread pumps the Qt event loop via ``qtbot``.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from PyQt6.QtCore import QThread

from open_garden_planner.agent_api.bridge import BridgeClosedError, MainThreadBridge


class TestMainThreadBridge:
    def test_runs_callable_on_main_thread(self, qtbot: Any) -> None:
        bridge = MainThreadBridge()
        main_thread = QThread.currentThread()
        captured: dict[str, Any] = {}

        def worker() -> None:
            captured["ran_on"] = bridge.run_on_main(
                QThread.currentThread, timeout=5.0
            )
            captured["worker_thread"] = QThread.currentThread()

        thread = threading.Thread(target=worker)
        thread.start()
        qtbot.waitUntil(lambda: "ran_on" in captured, timeout=5000)
        thread.join(timeout=5.0)

        assert captured["ran_on"] is main_thread
        assert captured["worker_thread"] is not main_thread

    def test_same_thread_fast_path(self, qtbot: Any) -> None:
        bridge = MainThreadBridge()
        # Called directly on the main thread: runs inline, no event loop hop.
        assert bridge.run_on_main(lambda: 21 * 2) == 42

    def test_exception_propagates_to_caller(self, qtbot: Any) -> None:
        bridge = MainThreadBridge()
        captured: dict[str, Any] = {}

        def worker() -> None:
            try:
                bridge.run_on_main(lambda: 1 / 0)
            except ZeroDivisionError as exc:
                captured["error"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        qtbot.waitUntil(lambda: "error" in captured, timeout=5000)
        thread.join(timeout=5.0)

        assert isinstance(captured["error"], ZeroDivisionError)

    def test_timeout_when_loop_not_pumped(self, qtbot: Any) -> None:
        bridge = MainThreadBridge()
        captured: dict[str, Any] = {}

        def worker() -> None:
            try:
                # The main thread is blocked on join() below (no event
                # processing), so the queued call cannot complete and must
                # time out.
                bridge.run_on_main(lambda: 1, timeout=0.1)
            except FutureTimeoutError as exc:
                captured["timeout"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=5.0)

        assert "timeout" in captured

    def test_abort_pending_unblocks_in_flight_call(self, qtbot: Any) -> None:
        bridge = MainThreadBridge()
        captured: dict[str, Any] = {}

        def worker() -> None:
            try:
                # Long timeout: only abort_pending should release this. The main
                # thread below deliberately never pumps the Qt loop, so the
                # queued call is not serviced normally.
                bridge.run_on_main(lambda: 1, timeout=30.0)
            except BridgeClosedError as exc:
                captured["aborted"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        # Wait until the worker has registered its pending future WITHOUT pumping
        # Qt events (time.sleep, not qtbot.wait), so the call cannot complete
        # normally before we abort it.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with bridge._lock:  # noqa: SLF001 - white-box check of pending state
                if bridge._pending:
                    break
            time.sleep(0.01)
        bridge.abort_pending()
        thread.join(timeout=5.0)

        assert isinstance(captured.get("aborted"), BridgeClosedError)
