## Case study: linux-offscreen suite segfaults in an unrelated minimap test — CI-bisect pinned a 10 ms watchdog timer racing pytest-qt's wait loop (Issue #346 finalization, fixed 2026-09-01)

**Symptom.** CI (`Test` job, linux offscreen) aborted with `Fatal Python error: Segmentation fault` — always in `test_minimap_widget.py::TestMinimapIdleQuiescence`, a different member test each run, always at ~66% of the suite. Local Windows green, every time.

**Wrong theories.** (1) A runner flake / pre-existing master instability. (2) Collection-time import of `map_picker_dialog` (QtWebEngine) from the new test module shifting the corruption schedule. (3) The QPixmap/QPainter grab stand-in churning offscreen memory.

**Key evidence.** CI-bisect as the instrument, seven pushes: a throwaway probe branch at `origin/master` HEAD ran green → the branch introduces it; disabling both new test files → green; unit file only → green; `pytestmark = skip` (collect everything, run nothing) → green (collection imports innocent); skipping the second half of classes → red; only the lifecycle class → green; only the success class → green; the cancel class without its three watchdog tests → green. The three watchdog tests — each of which did `_capture_watchdog.setInterval(10); _capture_watchdog.start(10)` inside a `qtbot.waitUntil(lambda: dialog._capture_in_progress is False)` — were the only red constellation.

**Root cause.** A real 10 ms single-shot QTimer racing pytest-qt's process-events wait loop in the offscreen platform destabilised Qt's native timer/event machinery; the corruption surfaced later, in the quiescence-counting minimap tests (exactly row 37's "the test *after* the guilty one errors" shape, but a segfault instead of an abort).

**Fix.** The tests now drive the handler deterministically by emitting the signal (`dialog._capture_watchdog.timeout.emit()` — same slot, synchronously, no real timer); the real 20 s watchdog timing remains covered by the live E2E harness. Pinned §11.4 ("short-interval QTimer racing pytest-qt's waitUntil").

**Lesson.** When CI is red on linux offscreen and green locally, treat CI itself as the instrument: master-probe first (one push), then bisect by *skipping*, not by editing logic. And never race a widget timer against `waitUntil` in a Qt test — emit the signal if the goal is handler coverage.

