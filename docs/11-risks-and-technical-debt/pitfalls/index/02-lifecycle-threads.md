# Lifecycle & Threads Pitfalls (PF-LIF)

| ID | Rule | Status | Where | Legacy |
|---|---|---|---|---|
| PF-LIF-01 | A teardown that stops a thread must confirm the thread is dead and escalate loudly when it is not; a bounded join that expires and only logs leaves a live thread to crash an unrelated test. | standing | [02](../02-lifecycle-threads.md#pf-lif-01) |  |
| PF-LIF-02 | A Qt dialog never joins a network worker synchronously in `closeEvent()`; it cancels cooperatively, closes on the worker's terminal signal, and logs worker tracebacks only after scrubbing. | standing | [02](../02-lifecycle-threads.md#pf-lif-02) |  |
| PF-LIF-03 | A private list tracking scene items is dropped inside `CanvasScene.clear()`, the chokepoint that destroys them, not at the one call site that crashed, and every sibling list is audited too. | standing | [02](../02-lifecycle-threads.md#pf-lif-03) |  |
| PF-LIF-04 | A network `QThread` worker exposes `cancel()` and `shutdown(timeout_ms)`, and `closeEvent` shuts it down and unparents it before the window is destroyed, or Qt aborts the process. | standing | [02](../02-lifecycle-threads.md#pf-lif-04) |  |
| PF-LIF-05 | Every `scene.changed` slot that starts a `QTimer` wraps `.start()` in `contextlib.suppress(RuntimeError)`, because the scene still emits during teardown after the timer is deleted. | standing | [02](../02-lifecycle-threads.md#pf-lif-05) |  |
| PF-LIF-06 | A slot bound to an app-global Qt signal such as `QApplication.focusChanged` must survive firing after its widget is destroyed, with both its disconnect and its body made teardown-safe. | standing | [02](../02-lifecycle-threads.md#pf-lif-06) |  |
| PF-LIF-07 | Every new `ItemIgnoresTransformations` drag handle joins the allow-list in `CanvasView.mousePressEvent`, because Qt drops its mouse grab and the view re-grabs only known handle types. | pointer | [02](../02-lifecycle-threads.md#pf-lif-07) |  |
| PF-LIF-08 | `QGraphicsScene.changed` ignores plain Python attribute writes, so any path that re-parents a plant calls `trigger_soil_mismatch_refresh(scene)` or goes through `SetParentBedCommand`. | pointer | [02](../02-lifecycle-threads.md#pf-lif-08) |  |
| PF-LIF-09 | Every `scene.changed` slot, and any timer slot it restarts, applies its target state once, touching `update()`, `setVisible()` or items only when a value changed and never clearing then setting. | standing | [02](../02-lifecycle-threads.md#pf-lif-09) |  |
| PF-LIF-10 | Never subclass `QWebEnginePage` to capture `javaScriptConsoleMessage`, which crashes the process with no traceback; read a page's console output over remote debugging instead. | standing | [02](../02-lifecycle-threads.md#pf-lif-10) |  |
| PF-LIF-11 | Keep displayed sun results separate from requested inputs, withdraw stale measurements immediately and debounce scene collection itself. | standing | [02](../02-lifecycle-threads.md#pf-lif-11) |  |
