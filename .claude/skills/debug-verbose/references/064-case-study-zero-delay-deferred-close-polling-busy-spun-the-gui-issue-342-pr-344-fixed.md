## Case study: zero-delay deferred-close polling busy-spun the GUI (Issue #342 / PR #344, fixed 2026-08-31)

**Symptom**: After the GUI close request returned, a blocked satellite request kept the event loop busy while the deferred-close timer repeatedly re-fired.

**Wrong theories**: A zero-delay timer was treated as harmless because each callback was short, and worker interruption was assumed to complete before the next callback.

**Key evidence**: Review of the lifecycle state showed `_complete_deferred_close()` scheduling another zero-delay callback while `_fetch_in_progress` remained true. The request could remain blocked until its network timeout, so the GUI loop had no quiet interval.

**Root cause**: Deferred polling on the GUI thread was being used to wait for a worker whose cancellation was cooperative and asynchronous.

**Fix**: Close only from the identity-checked `QThread.finished` path; route `reject()` and `closeEvent()` through the same cancellation state machine, and have the application track an active modal picker during application shutdown. Escape and parent-window close now have regression coverage.

**Lesson**: A zero-delay retry loop is still a busy loop when the condition depends on I/O. Use the worker's terminal signal as the completion event, and guard every dialog rejection path—not just the window-manager close event.

