## Case study: 10-second shutdown that only happened with a client attached (issue #373, fixed 2026-10-02)

**Symptom**: closing the app took about 10 seconds, with two log lines: a WARNING that the
Agent API thread "did not stop within 5.0s", then an ERROR that it was "STILL RUNNING after
5.0s + 5.0s". Intermittent - it did not happen every time the app closed.

**Wrong theories**. (1) The app wiring missing `MainThreadBridge.abort_pending()` before
`stop()` - that is exactly what the `server.py:248` `_STOP_TIMEOUT_S` comment says callers must do. Falsified
by reading the code: `application._stop_agent_api` already calls `abort_pending()` first.
(2) uvicorn's `force_exit` needing to be set - plausible from uvicorn's docs, and the obvious
first fix. **Measured and falsified**: `force_exit = True` alone left the shutdown at 10.01 s.
That is the single most useful result in this case, because it is the fix everyone reaches for.

**Key evidence**: a watchdog thread that dumped every thread stack and every live asyncio task
6 seconds into the join.

```
--- thread 43964 ---
  _run
    loop.run_until_complete(server.serve())
      ...
        self._selector.select(timeout)      <- the loop is IDLE
--- WATCHDOG: 12 live asyncio task(s) ---
  task: Task-1 ... Server.serve            state=PENDING
  task: sse_starlette.sse.EventSourceResponse.__call__.<locals>.cancel_on_finish
  task: mcp.server.session.ServerSession._receive_loop
  task: Task-7 ... _shutdown_watcher
  task: mcp.server.streamable_http_manager.StreamableHTTPSessionManager._handle_stateless_request
```

The stack showed `serve()` suspended in the event-loop selector - **not** in a Python frame
inside the shutdown path - and the task dump named the blockers: the MCP `ServerSession`
receive loop and sse-starlette's stream. Reproduction confirmed the trigger: **0.19 s with no
client, 10.03 s with a client holding the SSE stream open**.

**Root cause**: uvicorn's graceful shutdown waits for open connections to finish. An MCP
client holding the SSE stream open never closes it, so `serve()` never returned and both
5-second joins expired. `force_exit` skips uvicorn's connection drain but the MCP session/SSE
tasks keep the loop alive past it, which is why it did not help on its own.

**Fix**: `stop()` stores the loop on the server and, via `call_soon_threadsafe`, cancels the
loop's tasks and calls `loop.stop()`. `run_until_complete` then raises
`RuntimeError("Event loop stopped")`, which `_run` recognises as the deliberate path and does
**not** log as a crash. Measured after: 0.58 s with a streaming client, 0.00 s without.

**Lesson**: (1) **A lifecycle defect whose reproduction needs a concurrent peer will not be
found by a single-threaded test of the happy path** - no test held a client across a stop, so
the fast default path stayed green. (2) The obvious library-supplied fix (`force_exit`) can be
wrong; only measuring it proved it. (3) A stack dump that shows a loop **idle in its selector**
says "nothing is running and something is still awaited" - pair it with an asyncio task dump,
which names the waiters the stack cannot.


