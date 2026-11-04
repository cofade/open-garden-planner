## Case study: live capture harness saw "capture did not complete" while the feature worked (Issue #346, fixed 2026-09-01)

**Symptom.** The end-to-end live verification of the JS view capture printed nothing after "starting capture" and the process exited with code 0 — the harness reported the dialog had not accepted.

**Wrong theories.** The capture pipeline was suspected: JS `beginCapture` failing silently, the `tilesloaded`+`idle` readiness gate never firing, the widget grab returning a blank.

**Key evidence.** Wrapping the dialog's methods with print traces showed the full chain working — `beginCapture → 'ok'`, `captureReady`, grab → crop → `accept()` — followed instantly by process exit.

**Root cause.** Two stacked harness/pitfall findings: (1) `QDialog.accept()` hides the window, so with `quitOnLastWindowClosed` the event loop ended before the harness's 500 ms poll could read `fetch_result`; (2) the earlier "map never ready" polls were blind — the page declares `let map` / `let bridge` (top-level `let` never attaches to `window`), so `runJavaScript("window.map")` returns undefined while the real map sits healthy on screen.

**Fix.** Poll page-scope expressions (`typeof map !== 'undefined' && map && map.getZoom`) and hook the accept itself instead of racing a timer against window-closed quiescence.

**Lesson.** A verification harness that polls an event-driven Qt flow needs to instrument the *end state transition* (the accept), not poll the result — and any JS probe of a page written with `let` must scope to the page, not `window`. Both red herrings wasted a debugging round on a pipeline that had already succeeded; the process had exited because success itself hides the dialog.

