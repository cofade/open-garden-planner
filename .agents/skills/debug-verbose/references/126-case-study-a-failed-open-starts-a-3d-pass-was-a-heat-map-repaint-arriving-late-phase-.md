## Case study: "a failed open starts a 3D pass" was a heat-map repaint arriving late (Phase 17 L1.3 re-check, 2026-10-19)

**Symptom**: a pin asserting that a FAILED file open leaves the 3D pipeline untouched failed
6 of 10 runs under `-n 4` (`(2, 2, 0) == (1, 1, 0)`: one extra snapshot) once its window was
widened past the quiet-time net, and never alone.
**Wrong theories**: the new "an announcement expires one turn after its pass" rule made the
open's own repaint unexplained; the failed open touches the scene.
**Key log lines** (prints to a per-pid file — xdist does not forward `-s` output): a
`changed([QRectF(-2500, -1500, 10000, 6000)])` 0–30 ms around the call with NO Python caller of
`scene.update` / `invalidate` (wrapped and traced), and in the passing runs the same full-scene
`changed` arriving BEFORE the call.
**Root cause**: the heat map's overlay repaints the whole scene once more after it is shown;
under load that repaint lands after the test's `waitUntil(controller.idle)` returned, arms the
net, and its pass is blamed on the open. The product was clean (the reviewer's idle-first probe:
0 repaints, 0 snapshots).
**Fix**: settle = idle AND no non-empty `changed` for longer than the net's quiet time, then
act. **Lesson**: "idle once" is not "settled" when another subsystem repaints asynchronously; a
negative window must start from a scene that has been quiet for longer than the window's own
timer. Under xdist, log to a file per pid.


