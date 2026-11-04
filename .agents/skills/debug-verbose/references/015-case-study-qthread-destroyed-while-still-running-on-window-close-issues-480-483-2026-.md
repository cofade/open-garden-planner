## Case study: QThread destroyed while still running on window close (issues #480, #483, 2026-10-15)

**Symptom.** Closing the application window while a network worker (such as the update checker or weather forecast worker) is in-flight crashes or aborts with code `0xC0000409` and Qt fatal error `QThread: Destroyed while thread is still running`.

**Wrong theories.** Blaming Python garbage collection order or relying solely on daemon threads. Python daemon threads do not prevent Qt's C++ object tree destructor `~QThread()` from terminating the process when a parent `QObject` is deleted while its child `QThread` is active.

**Evidence.** Triggering an update check or weather fetch and immediately closing the main window resulted in an abnormal exit (`0xC0000409`). Inspecting `GardenPlannerApp.closeEvent` showed `UpdateChecker(self)` had the application window as parent and lacked a cancellation/shutdown handshake.

**Root cause.** When `GardenPlannerApp` closes and is destroyed, its C++ child `QObject`s (including `UpdateChecker` and weather fetch workers) are destroyed. Because network operations block synchronously in `run()`, the thread was still running when Qt's C++ `~QThread()` ran, triggering `qFatal`. Furthermore, signals emitted by in-flight threads could invoke slots on destroyed receivers. If unparented, Python GC could delete the wrapper object while running, triggering the same C++ destructor abort.

**Fix.** Provide an explicit `cancel()` flag and `shutdown()` handshake on background workers (`UpdateChecker`, `_WeatherFetchWorker`). In `shutdown()`, mark cancelled, suppress disconnect errors to detach all signal listeners, clear the QObject parent via `setParent(None)` so window destruction does not destroy the active thread, issue a short `wait()`, and retain in `core.worker_lifecycle._RETIRING_WORKERS` until the `finished` signal fires. Call `shutdown()` in `closeEvent` for update check and weather services alongside the sun heatmap worker. Pin with lifecycle integration and cancellation unit tests. Remove temporary prints before committing.

**Lesson.** Every background `QThread` attached to a parent `QObject` must have a deterministic cancellation and shutdown protocol before parent destruction. Never let `~QThread()` run while `isRunning()` is true.


