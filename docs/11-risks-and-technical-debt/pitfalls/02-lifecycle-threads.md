# Pitfalls: lifecycle, threads, timers and signals

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-LIF-01

- **Rule:** A teardown that stops a thread must confirm the thread is dead and escalate loudly when it is not; a bounded join that expires and only logs leaves a live thread to crash an unrelated test.
- **Pinned by:** `tests/integration/test_agent_api_lifecycle.py::TestServerTeardownLeavesNothingRunning`
- **Source:** #366
- **Status:** standing
- **Legacy:** b1faaa9 README L188

- **A teardown that gives up quietly turns into a crash somewhere else, and the "somewhere else" is the only symptom you get.** (Issue #366, found by CI segfaulting — on this branch ~50% of runs, exit 139): the stack named `agent_api/server.py:_run`, i.e. `loop.run_until_complete(server.serve())`, still executing while an **unrelated** Qt test (`test_minimap_widget.py`) was tearing down. Chased to ground with a throwaway pytest plugin that stamped each server thread with the test that created it, which found the mechanism: **`GardenPlannerApp.__init__` schedules `QTimer.singleShot(1500, _maybe_start_agent_api)`**, so *any* test that builds the app can start a REAL uvicorn server 1.5 s later — on whatever event loop runs then, frequently a *different* test. Most such tests called `_stop_agent_api()` in teardown; the ones that did not left a live server thread holding its sockets and its `MainThreadBridge`, alive into interpreter teardown. Four lessons. (1) **A deferred start is a start you cannot see at the call site**: attributing the leak to the test running when the thread appeared points at an innocent bystander, and only stamping the thread with its creating test finds the culprit. (2) **A bounded `join(timeout=...)` that expires and only logs is not a teardown** — `AgentApiServer.stop()` set `should_exit`, joined once for 5 s, warned, and returned with the thread still running. It now takes a second bounded grace join and escalates to `logger.error`, because a leak nobody can see is a leak nobody fixes. (3) **The failing test is rarely the guilty one**; the stack is the evidence, and it pointed three suites away. (4) **Pin the invariant instead of hoping**: `TestServerTeardownLeavesNothingRunning` asserts the thread a server started is dead after `stop()` (three back-to-back cycles), and an autouse `tests/integration/conftest.py` fixture stops any live agent server after every test and *says so* when one is found. Verified by running the whole suite under the leak plugin: **0 threads survive at session end**, down from 1. Honest caveat: this is the only defect the crash stack named, and the flake may have more than one cause — if it recurs, treat it as its own issue rather than assuming this fixed it.

### PF-LIF-02

- **Rule:** A Qt dialog never joins a network worker synchronously in `closeEvent()`; it cancels cooperatively, closes on the worker's terminal signal, and logs worker tracebacks only after scrubbing.
- **Pinned by:** `tests/integration/test_map_picker_dialog.py::test_close_does_not_block_on_in_flight_worker`; `tests/integration/test_map_picker_dialog.py::test_worker_logs_scrubbed_traceback_for_unexpected_failure`
- **Source:** #342, #344
- **Status:** standing
- **Legacy:** b1faaa9 README L201

- **A Qt dialog must not synchronously join a network worker during `closeEvent()`.** (Issue #342 / PR #344): closing the satellite picker while a Static Maps request was slow could freeze the GUI for the request timeout because `MapPickerDialog.closeEvent()` called `QThread.wait()` even after requesting interruption, while `google_maps_service._fetch_tile()` could remain inside `requests.get(timeout=10)`. The fix keeps the dialog alive, routes `reject()` and `closeEvent()` through one cancellation request, and rejects only from the worker's terminal signal; `GardenPlannerApp` tracks the modal picker so application shutdown follows the same path. Unexpected worker tracebacks are formatted and scrubbed before logging, while the dialog receives only a generic message. Pinned by `tests/integration/test_map_picker_dialog.py::TestFetchFlow::test_close_does_not_block_on_in_flight_worker` and `test_worker_logs_scrubbed_traceback_for_unexpected_failure`. Lesson: cancellation can be cooperative without making GUI teardown blocking; every Qt worker that touches network I/O needs an asynchronous owner lifecycle and a secret-safe diagnostic path.

### PF-LIF-03

- **Rule:** A private list tracking scene items is dropped inside `CanvasScene.clear()`, the chokepoint that destroys them, not at the one call site that crashed, and every sibling list is audited too.
- **Pinned by:** `tests/unit/test_compare_overlay.py::TestCompareOverlaySurvivesSceneClear`; `tests/unit/test_compare_overlay.py::TestCalibrationSurvivesSceneClear`; `tests/unit/test_compare_overlay.py::TestCompareOverlayClearedOnProjectLoad`; `tests/integration/test_compare_overlay.py`
- **Source:** #337, #339
- **Status:** standing
- **Legacy:** b1faaa9 README L205

**A private item-tracking list must be dropped at the SAME chokepoint that destroys the items it tracks, not just at the one call site that happened to crash — and an audit that finds one sibling case must check for others in the same class (issue #337, shipped 2026-08-21 in v1.27.2 via PR #339).** Symptom: clicking File → New Plan with a plan that had the compare overlay (US-10.7) in use showed an error popup: ``RuntimeError: wrapped C/C++ object of type QGraphicsEllipseItem has been deleted``. Root cause: `_on_new_project()` called `scene.clear()` (which destroys every C++ QGraphicsItem in the scene), then called `clear_compare_overlay()` which iterated `self._compare_items` and called `removeItem()` on each Python wrapper — the C++ object behind each wrapper was already destroyed by `scene.clear()`. **Round 1** guarded only `clear_compare_overlay()` (a `contextlib.suppress(RuntimeError)`) and reordered the two calls in `_on_new_project()` — senior review reproduced the identical `RuntimeError` three lines below, in `set_compare_overlay_visible()`, which reads the same `_compare_items` list and is reachable from the "Show Previous Season Overlay" menu action any time stale wrappers survive a `scene.clear()` the guarded method didn't run for. The same review found a second, independent path to stale state: `_deserialize_to_scene()` (project load) removes items by an isinstance allow-list that never included the overlay's `QGraphicsEllipseItem`/`QGraphicsSimpleTextItem`, so opening a new plan could leave the previous plan's ghosted plants painted on the new canvas. **Round 1 fix**: `CanvasScene.clear()` overridden to drop `_compare_items` before calling `super().clear()` — one chokepoint, so both readers are safe by construction; `_deserialize_to_scene()` calls `clear_compare_overlay()` before its own item removal; the `except Exception` branch of `_load_compare_overlay_from_previous_season()` also clears the overlay. **Round 2**: a second senior-review pass, live-testing the round-1 fix rather than reading it, reproduced the *identical* `RuntimeError` on `_calibration_markers` — the scene's other private `QGraphicsItem`-tracking list (image-calibration crosshairs/lines), 800 lines away in the same class, exposed via `start_image_calibration()` → `add_calibration_point()` → `scene.clear()` → `cancel_calibration()`. It also found `_compare_overlay_visible` was left `True` by the round-1 `clear()` override even though the items were gone, so a freshly loaded overlay could silently start invisible/desynced from the menu action's checked state. **Round 2 fix**: `CanvasScene.clear()` now also drops `_calibration_markers`, `_calibration_points`, `_calibration_image`, `_calibration_mode`, and `_compare_overlay_visible`; `_open_project_file()`'s `except Exception` branch resets the compare-overlay action state and calls `clear_compare_overlay()` so a load failure mid-open cannot leave it stale either. **Known still-open**: three other sites in this codebase guard the *identical* hazard with `contextlib.suppress(RuntimeError)` / `except RuntimeError` instead of a chokepoint fix — `ui/canvas/sun_shadow_controller.py` (`_debounce.start()`, `_overlay` accessor) and `ui/canvas/sun_heatmap.py` (`_overlay` accessor, an items-iteration loop) — left alone here because they track different containers with different teardown lifecycles; audit them individually before assuming this entry closes the bug class. **Lesson**: when a private list tracks references into a container that has its own bulk-teardown method (`QGraphicsScene.clear()`), make that teardown method itself responsible for dropping the list — guarding or reordering the one call site a bug report names fixes the report, not the bug class; and when a review finds one sibling case, grep the same class for every other tracking list before declaring the audit done, because the second sibling (`_calibration_markers`) was sitting in the same file the whole time. Pinned by `tests/unit/test_compare_overlay.py` (`CanvasScene.clear()` drops the compare-overlay list, resets its visibility flag, drops the calibration trackers, and project load via `ProjectManager.load()` cannot leave a ghosted item behind) and `tests/integration/test_compare_overlay.py` (drives the real File → New Plan menu action end-to-end, then exercises the previously-unguarded `set_compare_overlay_visible` reader via the toggle action).

### PF-LIF-04

- **Rule:** A network `QThread` worker exposes `cancel()` and `shutdown(timeout_ms)`, and `closeEvent` shuts it down and unparents it before the window is destroyed, or Qt aborts the process.
- **Pinned by:** `tests/unit/test_update_checker.py::TestUpdateCheckerLifecycle`; `tests/integration/test_weather_widget.py::TestWeatherWidgetLifecycle`
- **Source:** #480, #483
- **Status:** standing
- **Legacy:** b1faaa9 README L237

- **A background `QThread` with a parent `QObject` aborts the app with `0xC0000409` (`QThread: Destroyed while thread is still running`) on window close (issues #480, #483).**
  Network workers (`UpdateChecker`, `_WeatherFetchWorker`) created with the main window or widgets as parent outlive normal actions when an HTTP request blocks synchronously in `run()`. Closing the window runs Qt's C++ destructor `~QThread()` on the running thread, triggering `qFatal("QThread: Destroyed while thread is still running")`. Python daemon threads do not bypass Qt C++ parent-child destruction.
  **Fix**: Background worker threads must expose `cancel()` and `shutdown(timeout_ms)`. In `shutdown()`, set the cancellation flag, disconnect all signals with `contextlib.suppress(TypeError, RuntimeError)`, call `setParent(None)` to sever the parent-child ownership link, and call `wait(timeout_ms)`. In `GardenPlannerApp.closeEvent`, invoke `shutdown()` on in-flight services before window destruction. Pinned by `tests/unit/test_update_checker.py` and `tests/integration/test_weather_widget.py`.

### PF-LIF-05

- **Rule:** Every `scene.changed` slot that starts a `QTimer` wraps `.start()` in `contextlib.suppress(RuntimeError)`, because the scene still emits during teardown after the timer is deleted.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #230
- **Status:** standing
- **Legacy:** b1faaa9 README L254

- **A `scene.changed` slot that touches a `QTimer` must guard against the C++ object being torn down** (#230 CI crash): handlers wired to `QGraphicsScene.changed` that call `self._some_timer.start()` (the soil-mismatch / companion / spacing debouncers) can fire **during widget/app teardown** — the scene still emits `changed` as it is cleared, after the owning view's child `QTimer` has been deleted. Accessing the deleted timer raises `RuntimeError: wrapped C/C++ object of type QTimer has been deleted` *inside a Qt slot*, which Qt/pytest-qt escalates to `Fatal Python error: Aborted` — aborting the whole interpreter (locally it was timing-dependent and passed; on the CI Linux runner it reliably crashed the Test job). Symptom: a test that builds the full `GardenPlannerApp` and mutates the scene passes, then the *next* test errors and the run aborts mid-suite. Fix/contract: every `scene.changed` slot that starts a timer must wrap the `.start()` in `with contextlib.suppress(RuntimeError):` (see `canvas_view._on_scene_changed_for_soil`, `application._on_scene_changed_for_{companion,spacing,plant_search}`). Timers driven by *command/status* signals (`stack_changed`, `task_states_changed`) don't need it — those signals aren't emitted during teardown. **Never connect `scene.changed` to a bare `lambda: self._timer.start()`** — a lambda can't be made teardown-safe.

### PF-LIF-06

- **Rule:** A slot bound to an app-global Qt signal such as `QApplication.focusChanged` must survive firing after its widget is destroyed, with both its disconnect and its body made teardown-safe.
- **Pinned by:** none — The body names no test for this rule; the one test it cites is the unrelated test that failed, not a guard.
- **Source:** #235
- **Status:** standing
- **Legacy:** b1faaa9 README L256

- **A slot connected to an *application*-global signal (`QApplication.focusChanged`) outlives its widget and must be teardown-safe** (US-C1 PR #235, surfaced merging master's `global_search` into the new full-app harvest tests): `GlobalSearchField` connects `app.focusChanged → self._on_focus_changed` (the popup is a `Qt.ToolTip` that must close when focus leaves) and tried to clean up with `self.destroyed.connect(lambda _: app.focusChanged.disconnect(self._on_focus_changed))`. Two teardown faults: (1) Qt **already** auto-disconnects a destroyed receiver, so the explicit `disconnect` raced to `TypeError: 'method' object is not connected`; (2) because the connection is to the **process-global** `QApplication` (one instance across the whole test session, unlike a per-window signal), a stray `focusChanged` could still invoke `_on_focus_changed` on a field whose C++ object was gone, raising from inside the slot. pytest-qt captures any exception raised in a Qt slot during a test and **fails that test** — so the leak from one test's torn-down window failed an unrelated later full-app test (`test_harvest.py::TestHarvestNavigation`), "passes alone, fails in the full run". Fix: wrap the disconnect in `contextlib.suppress(TypeError, RuntimeError)` and guard `_on_focus_changed`'s body in `try/except RuntimeError: return`. Rule: any handler bound to an app-global Qt signal (`focusChanged`, `applicationStateChanged`, `aboutToQuit`, …) must assume it can fire after its widget is destroyed — make both the disconnect and the slot body teardown-safe; a bare `destroyed`-lambda disconnect is not enough.

### PF-LIF-07

- **Rule:** Every new `ItemIgnoresTransformations` drag handle joins the allow-list in `CanvasView.mousePressEvent`, because Qt drops its mouse grab and the view re-grabs only known handle types.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #193
- **Status:** pointer → [ogp-qt-cad-reference: 3. `ItemIgnoresTransformations` — what it buys and its two traps](../../../.claude/skills/ogp-qt-cad-reference/SKILL.md#3-itemignorestransformations--what-it-buys-and-its-two-traps)
- **Legacy:** b1faaa9 README L290

Held in [ogp-qt-cad-reference: 3. `ItemIgnoresTransformations` — what it buys and its two traps](../../../.claude/skills/ogp-qt-cad-reference/SKILL.md#3-itemignorestransformations--what-it-buys-and-its-two-traps). The entry keeps the rule and its pin; the account is in the link.

### PF-LIF-08

- **Rule:** `QGraphicsScene.changed` ignores plain Python attribute writes, so any path that re-parents a plant calls `trigger_soil_mismatch_refresh(scene)` or goes through `SetParentBedCommand`.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #173
- **Status:** pointer → [debug-verbose: Case study: soil-mismatch warning goes stale on plant move/reparent (issue #173, fixed 2026-05-07)](../../../.claude/skills/debug-verbose/SKILL.md#case-study-soil-mismatch-warning-goes-stale-on-plant-movereparent-issue-173-fixed-2026-05-07)
- **Legacy:** b1faaa9 README L304

Held in [debug-verbose: Case study: soil-mismatch warning goes stale on plant move/reparent (issue #173, fixed 2026-05-07)](../../../.claude/skills/debug-verbose/SKILL.md#case-study-soil-mismatch-warning-goes-stale-on-plant-movereparent-issue-173-fixed-2026-05-07). The entry keeps the rule and its pin; the account is in the link.

### PF-LIF-09

- **Rule:** Every `scene.changed` slot, and any timer slot it restarts, applies its target state once, touching `update()`, `setVisible()` or items only when a value changed and never clearing then setting.
- **Pinned by:** `tests/integration/test_idle_scene_quiescence.py`; `tests/unit/test_minimap_widget.py::TestMinimapIdleQuiescence`
- **Source:** #305
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l398-qgraphicsscenechanged-feedback-loops-a-slot-driven-by-scenechanged-that-itself-mutates-the-scene-runs-forever-while-the-app-is-idle)
- **Legacy:** b1faaa9 README L398

### PF-LIF-10

- **Rule:** Never subclass `QWebEnginePage` to capture `javaScriptConsoleMessage`, which crashes the process with no traceback; read a page's console output over remote debugging instead.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #346
- **Status:** standing
- **Legacy:** b1faaa9 README L422

- **Subclassing `QWebEnginePage` to siphon `javaScriptConsoleMessage` hard-crashes the process** (#346 spike, 2026-09-01): overriding the console-message hook in a Python `QWebEnginePage` subclass (with or without calling `super()`) crash-exited the app with `STATUS_STACK_BUFFER_OVERRUN (0xC0000409)` and **no Python traceback** — first seen as the whole spike process dying with an empty exit. Symptom shape: a fatally clean exit, nothing on stderr. Rule: never subclass `QWebEnginePage` for telemetry; if a WebEngine page's console output is ever needed, use the remote-debugging/CDP route instead.
