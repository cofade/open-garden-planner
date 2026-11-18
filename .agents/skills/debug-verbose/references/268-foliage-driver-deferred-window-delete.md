## Case study: the foliage driver published success before its window was gone (#893)

**Symptom:** A foliage render driver completed every frame and then exited with
a native access violation.

**Theories checked:** The old effects-chain crash is one possible Qt failure,
but the Medium capture was complete and the historical trace gave no failing
native frame.

**Evidence:** The local child printed `[FOLIAGE-EXIT] native window deleted=False`
after the host closed, then logged `[done] status=ok`. The host had posted the
native view for deferred deletion without draining the posted events.

**Fix:** Process deferred deletions and require the native view to be gone
inside the driver's existing watchdog, then judge both its status and exit code.

**Lesson:** A successful pixel readback proves nothing about native teardown.
Assert destruction before publishing the result. The old access violation did
not recur in the focused baseline run.
