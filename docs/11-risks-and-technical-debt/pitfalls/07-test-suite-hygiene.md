# Pitfalls: test-suite hygiene and isolation

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-TST-01

- **Rule:** A GUI-responsiveness test holds the real worker in flight with an Event and counts heartbeat ticks only while it runs on another thread, so the count cannot depend on compute duration.
- **Pinned by:** `tests/integration/test_sun_mismatch.py::test_explicit_worker_keeps_gui_responsive`
- **Source:** #490
- **Status:** standing
- **Legacy:** b1faaa9 README L101

- **Hold a worker in flight when proving GUI responsiveness** (PR #490): the
  sun-mismatch heartbeat test failed on CI with two ticks instead of three while
  three other full CI runs and the local suite passed. Tagged worker/timer traces
  showed that the count depended on compute duration and included post-completion
  ticks. The test now holds the real computation with an Event, requires three
  heartbeat ticks while the worker is running/pending on a different thread, then
  releases it and validates the real result. Failure cleanup always releases the
  worker; the timer interval and result timeout are unchanged. Pinned by
  `tests/integration/test_sun_mismatch.py::test_explicit_worker_keeps_gui_responsive`;
  a synchronous-worker mutation was observed failing its thread assertion.

### PF-TST-02

- **Rule:** A within-day simulation test sets the time of day as well as the date, such as noon via `set_time_of_day`, rather than inheriting the host clock, changing clock semantics or relaxing timeouts.
- **Pinned by:** none — the body names no test as a guard; the noon setting it describes lives in the sun-mismatch test setup, which applies the rule rather than failing when it is broken.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L146

- **Within-day simulation tests must fix time as well as date** (ADR-053): the
  sun-mismatch workflow set the date, retained 23:49 from the host, then added an
  hour. Correct next-day invalidation contradicted its `ready` assertion. Tagged
  datetime/caller tracing reproduced the same failure alone. Set the fixture to
  noon with `set_time_of_day`; retain worker, cache and date-invalidation checks.
  Do not change production clock semantics or relax timeouts to fix the fixture.

### PF-TST-03

- **Rule:** Every concrete placeable graphics item, `TextItem` included, round-trips through the `ProjectManager` serializer with exact dictionary equality, checked by one matrix over every item class.
- **Pinned by:** `tests/integration/test_item_roundtrip_matrix.py`
- **Source:** #394
- **Status:** standing
- **Legacy:** b1faaa9 README L181

- **Every placeable graphics item must be covered by serializer round-trip matrix tests.** (Issue #394, AUD-001, AUD-017, TD-010, TD-019): Free-text annotations (`TextItem`) were serializable on the clipboard since v1.1 but completely missing from `ProjectManager._serialize_item_core` and `_deserialize_item_core`. Saving a plan containing text annotations silently dropped them. Unit tests tested persistence for common shapes but lacked an exhaustive matrix across all concrete placeable item types. Fix: `TextItem` is serialized natively under `type: "text"` with font, color, content, and position attributes. A comprehensive round-trip matrix test (`tests/integration/test_item_roundtrip_matrix.py`) verifies exact dictionary equality and round-trip fidelity across every concrete placeable item in the application.

### PF-TST-04

- **Rule:** Pytest tears fixtures down in reverse setup order, so an ordering-sensitive teardown declares its dependencies such as `qtbot` explicitly, and a mechanism is verified before it is documented.
- **Pinned by:** none — the body names no test as a pin; its guard is an autouse fixture in `tests/integration/conftest.py`, and the two test files it names are cited only as outside that guard's reach.
- **Source:** #366
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l184-a-cleanup-fixture-that-runs-in-the-wrong-order-is-not-a-cleanup--and-a-plausible-mechanism-is-not-a-mechanism)
- **Legacy:** b1faaa9 README L184

### PF-TST-05

- **Rule:** A test that could reach a real external CLI stubs `shutil.which` for the whole module, so its default is no CLI rather than whatever happens to be installed on the developer's machine.
- **Pinned by:** none — the body names no test file; the remedy is an autouse module fixture that stubs `shutil.which`, which applies the rule rather than failing when it is broken.
- **Source:** #366
- **Status:** standing
- **Legacy:** b1faaa9 README L196

- **Tests that probe third-party binaries must never run them against the developer's real user environment.** (Issue #366): a unit test called `detect_clients()`, which executed `opencode mcp add --global` and modified the developer's own `~/.config/opencode/opencode.jsonc`. `shutil.which` finds those CLIs on a machine that has them, so "no CLI" is not the default a test gets. The fix is an **autouse fixture that stubs `shutil.which` for the whole module**, so the default is "no CLI" rather than "whatever happens to be installed here" — and the scar is worth more than the fix, because the same test produced the single most useful finding in the change: OpenCode's real container key is `mcp.servers`, not the `mcp` its published schema implies (`additionalProperties: {}`, which says nothing). The developer's config was restored.

### PF-TST-06

- **Rule:** Tests never call `QSettings.setDefaultFormat()` or `setPath()`, process-global statics Qt never reverts; they redirect the `create_qsettings` factory with `monkeypatch` instead.
- **Pinned by:** `tests/unit/test_settings_chokepoint.py`
- **Source:** #285
- **Status:** standing
- **Legacy:** b1faaa9 README L366

- **`QSettings.setDefaultFormat()` / `setPath()` are process-global statics Qt never reverts — never call them from a test** (test-suite isolation): a test fixture in `tests/unit/test_ui_state.py` redirected `UiStateStore`'s settings to a temp INI file by calling `QSettings.setDefaultFormat(IniFormat)` + `QSettings.setPath(IniFormat, UserScope, tmp_path)`. Those are **static, process-wide** and are *not* auto-reverted (the `monkeypatch` arg was declared but unused). After that unit test ran (~⅔ through the suite), the global default format pointed at a `tmp_path` pytest had since deleted, so **every** `QSettings`/`AppSettings` constructed *later in the session* — the `get_settings()` singleton behind the snap-toggle handlers and the welcome dialog — wrote to a dead path and every getter fell back to its coded default. Symptom: 6 settings-persistence tests (`test_anchor_snap`, `test_nearest_snap_workflow`, `test_perpendicular_snap`, `test_tangent_snap`, `test_welcome_dialog`) **fail only in the full run, pass in isolation, and CI stays green** (different collection order/platform dodges the poison). The uniform tell: every failing getter returns exactly the *default* value, i.e. the setter write never persisted. Fix: isolate by `monkeypatch.setattr("open_garden_planner.app.settings.create_qsettings", <factory returning QSettings(ini_path, IniFormat)>)` (auto-reverts, touches no global state) — never the global statics. *(Recipe updated by #285: `ui_state.py` no longer has a `QSettings` name to patch, and `tests/unit/test_settings_chokepoint.py` forbids re-adding one — there is now a single factory to redirect, which is what `tests/unit/test_ui_state.py` does.)* Defensive backstop in [`tests/conftest.py`](../../../tests/conftest.py): the session `isolate_qsettings` fixture now captures `QSettings.defaultFormat()` and restores it at teardown (a tripwire for a future `setDefaultFormat` leak — it does **not** cover a `setPath`-only leak), and a function-scoped autouse `_reset_app_settings` clears the `cofade_test` store + nulls the `_settings_instance` singleton around every test so per-test value pollution can't accumulate either. Lesson: a green CI does not prove the local full suite is clean; a "passes alone, fails together" failure whose actual value is always the default is almost always shared global/singleton state, not the code under test. The deeper smell this entry flagged as a follow-up — `UiStateStore` and `AppSettings` each constructing their own store inline, so there was no single chokepoint to isolate — **is fixed (#285 / ADR-041)**: `app/settings.create_qsettings()` is that shared factory, and one fixture now isolates everything. The `defaultFormat()` capture in `isolate_qsettings` was also upgraded from a silent repair to a real tripwire (it restores, then asserts) — a backstop that quietly fixes the damage reports nothing.

### PF-TST-07

- **Rule:** A full-app test that outlives the 500 ms startup timer silences the modal Welcome dialog, whose `exec()` otherwise blocks pytest-qt forever behind an empty log.
- **Pinned by:** `tests/conftest.py::_silence_welcome_dialog`
- **Source:** #279
- **Status:** standing
- **Legacy:** b1faaa9 README L377

- **A full-app integration test that outlives ~500 ms must silence the startup Welcome dialog — its modal `exec()` blocks pytest-qt forever** (#279 test-infra finding): `GardenPlannerApp` arms `QTimer.singleShot(500, self._startup_sequence)`, which — with `show_welcome_on_startup` enabled, the default on dev machines — opens the **modal** `WelcomeDialog` via `dialog.exec()`. Headless nobody closes it, so the first event processing after the timer fires (typically pytest-qt's `_process_events` between/after tests) parks the session inside the modal event loop forever — and because pytest's output is block-buffered, the log stays EMPTY, so the hang masquerades as a collection freeze. Existing app-boot tests never hit it because they finish inside the 500 ms window; the #279 theme-switch tests (pixel scans + two full restyles) were the first to outlive it. Fix pattern (`tests/integration/test_icon_system.py::_make_app`): `monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda self: None)` before construction, alongside the established `QMessageBox.question` → Discard patch. Diagnosis tool that found it: `pytest -o faulthandler_timeout=40` dumps every thread's stack at the hang moment — reach for it whenever a Qt test "hangs with no output." Re-hit on 2026-08-17 (Package 3a): the fix had been applied per file, and only three of 34 app-building test files carried it, so a full `pytest tests/` run stalled for 18 minutes inside `tests/integration/test_trellis.py`. The stall showed only as an old log modification time. The fix now lives in `tests/conftest.py::_silence_welcome_dialog`.

### PF-TST-08

- **Rule:** Every settings store, `UiStateStore` included, takes its backend from `app/settings.create_qsettings()`, because a store that bypasses the chokepoint also bypasses the test isolation built on it.
- **Pinned by:** `tests/integration/test_settings_isolation.py`
- **Source:** #283, #285
- **Status:** standing
- **Legacy:** b1faaa9 README L385

- **`UiStateStore` builds its own `QSettings`, so it escapes the conftest isolation — full-app tests read *and overwrite* the developer's real window state** (#283 test-infra finding — **Closed (#285)**): `tests/conftest.py::isolate_qsettings` redirects `AppSettings` only, but `app/ui_state.py` constructs `QSettings("cofade", "Open Garden Planner")` directly. Every `GardenPlannerApp()` in a test therefore restored whatever geometry and toolbar layout the developer's own app last saved — and wrote it back at teardown, because pytest-qt closes registered widgets and `closeEvent` → `_save_ui_state()` persists. Symptom while writing #283's regression tests: a toolbar-visibility assertion passed under pristine settings and failed locally with the *fix applied*, purely because an earlier experiment had left a different toolbar layout in the real store — an hour lost to "the fix doesn't work" when the test harness was the variable. First patched by an autouse `_isolate_ui_state` fixture pointing `ui_state.QSettings` at the test key; local runs then also matched CI, where the store is always pristine (so `_geometry_restored` is False and the window maximizes). Lesson: a store that bypasses the settings chokepoint also bypasses the test isolation built on it. **Closed by #285 / ADR-041**, which made the tourniquet unnecessary rather than permanent: `app/settings.create_qsettings()` is the only place that constructs — or even names — a settings store, `UiStateStore` takes its backend from there, `_isolate_ui_state` is deleted, and `tests/conftest.py` redirects the whole app by rebinding two module names *at its own import time*. **The mechanism is specified once, in §8.8 — read it there, and change it there.** Do not re-derive it in this entry: three earlier attempts to summarise it here, in ADR-041 and in `CLAUDE.md` each drifted out of sync with the code within one commit, which is how reviews 2, 3 and 4 all found a doc/code mismatch. What belongs here is the evidence: reverting the chokepoint makes `tests/integration/test_settings_isolation.py` fail with exactly 3 reads + 3 writes to the real key, and hashing the real store's 29 values around a 47-test full-app file leaves them byte-identical.

### PF-TST-09

- **Rule:** Isolating one store is not isolating the process, so every place the app touches (`get_app_data_dir`, `QStandardPaths`, `Path.home()`, the temp directory) is redirected in each process running it.
- **Pinned by:** `tests/integration/test_app_data_isolation.py`
- **Source:** #285
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l387-the-test-suite-wrote-into-the-developers-real-plant-library--isolating-one-store-is-not-isolating-the-process)
- **Legacy:** b1faaa9 README L387

### PF-TST-10

- **Rule:** A 'nobody may use X' gate walks the AST and matches the name binding rather than a regex over uses, and every detector has a positive control fed the exact escape it exists to catch.
- **Pinned by:** `tests/unit/test_settings_chokepoint.py`
- **Source:** #285
- **Status:** standing
- **Legacy:** b1faaa9 README L396

- **A "nobody may use X" gate belongs in the AST, not in a regex — and it must be falsified twice** (#285, gate-design lesson): `test_settings_chokepoint.py` started as a line-anchored regex for `QSettings\s*\(`. Falsifying it by restoring the pre-#285 code as `from PyQt6.QtCore import QSettings as _Q` … `_Q("cofade", …)` — a two-line edit anyone could make while "just fixing an import cycle" — sailed through, so an **import** pattern was added. A senior review then broke *that* in one experiment: `from PyQt6.QtCore import (\n    QSettings as _Q,\n)` names the class on a line with no `import` keyword, so both regexes passed and only the behavioural test caught the bug. Rewritten as an `ast` walk over `Import`/`ImportFrom`/`Name`/`Attribute`, all spellings collapse into one check — and the same walk cheaply expresses a rule no regex could ("no `create_qsettings()` call that is evaluated at import time", distinguishing a function *body* from a decorator or default argument). Lessons for every textual gate in this repo (QSS colors, icon conformance, texture tileability): match the **name binding**, not just the use, because you cannot use what you have not first named; prefer the AST when the language has one; give every detector a **positive control** fed the exact escape it exists to catch, since a detector that stops matching anything reads as a green gate forever; and treat "my falsification passed" as one data point, not proof — the second reviewer found the second hole in one try.

### PF-TST-11

- **Rule:** The Welcome dialog is silenced session-wide by a class patch in `tests/conftest.py`, not per file or by a settings write alone, and a QSettings key other live instances share is never `clear()`ed.
- **Pinned by:** none — the body names the hang site `tests/integration/test_trellis.py` and remedy fixtures in `tests/conftest.py`, including a black-hole tripwire, and none of these is a test.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L402

- **The Welcome-dialog hang above was re-hit on 2026-08-17 (Package 3a) — because its fix was per-file, and only three of 34 app-building test files had it.** A full `pytest tests/` run stalled silently for 18 minutes inside `tests/integration/test_trellis.py` (2nd test), noticed only because the log's **modification time** was old — the tail looked like normal progress. A first write-up of this incident misfiled it as an unsolved "leaked slot" hang and reached for `pytest-timeout` as the fix; the senior review's stack dump (`application.py` → `dialog.exec()` inside pytest-qt's teardown `processEvents()`) pointed straight back at the entry above, which nobody had grepped for "Welcome" first — an institutional-memory failure committed inside a documentation commit. **Fix (structural):** `tests/conftest.py::_silence_welcome_dialog` — a **session**-scoped autouse fixture that replaces `GardenPlannerApp._show_welcome_dialog` with a no-op for the whole run (the class-level patch three files had applied per file), plus `_disable_welcome_dialog`, a per-test store write of `KEY_SHOW_WELCOME=False`. The class patch is the load-bearing one: a store-only guard was tried first and *lost a race once in a full run* — the read returned the default inside a `qtbot.wait` although both a conftest and a module fixture had written `False` before the app was built (`test_idle_scene_quiescence.py`, 2026-08-17). **The mechanism was then pinned down with two 15-line probes, and it is a second, independent pitfall (Windows registry backend):** a `QSettings` that has called `clear()` deletes its registry key **when it is destroyed** (`deleteWriteHandleOnExit`), and **every store built between that `clear()` and that destruction becomes a "black hole" — its writes vanish and its reads return defaults** (probe: `t.clear()`; build `s`; `s.setValue("x", 1)` reads 1; `del t` → `s.value("x")` reads the default and further writes are lost). **And the clearing instance was in ANOTHER PROCESS.** The test key was a fixed name (`cofade_test / Open Garden Planner Test`), so a second pytest run on the same machine — here the senior-reviewer agent running the suite in its worktree while the main battery ran — shared it, and every one of *its* per-test `clear()`s deleted the key under *this* process's live singleton. Decisive experiment: the same three files produce black holes on every run with a deliberately concurrent pytest process, and pass 3/3 under the same concurrency with the fix below. It also explains why the failures moved between tests and runs, and why "passes alone" told nothing. **Fix (three layers, all in `tests/conftest.py`):** (1) **per-process test key** — `TEST_APPLICATION = f"Open Garden Planner Test {os.getpid()}"`, so concurrent suites cannot see each other's key (the session-end `clear()` removes this process's key; a crashed run leaves an orphan `… Test <pid>` under `HKCU\Software\cofade_test`, harmless); (2) `_reset_app_settings` wipes per key (`remove(key)` for `allKeys()`, then `sync()`) instead of `clear()` — defence in depth against the same mechanism inside one process; (3) a **tripwire** at teardown that probes the live singleton and fails the test with "settings singleton is a BLACK HOLE …" if it is dead — the next such incident is a diagnosis, not a mystery. Rules: **never `clear()` a QSettings key that other live instances (in any process) share — `remove()` keys instead; and never assume a settings-based test guard is airtight when a concurrent process can exist (the senior-reviewer worktree runs the suite while you do).** `pytest-timeout` (MIT, dev dependency; `[tool.pytest.ini_options] timeout = 180`) stays — as a guard against *unknown* hangs, not as the fix for this one: on Linux/CI the signal method fails just the hung test; on Windows the thread method dumps every thread's stack and aborts the run, which names the culprit. **Lessons:** (1) before writing a new §11.4 entry, grep §11.4 for the symptom's nouns — this file is only institutional memory if it is read; (2) a hang guard is worth having, but never ship a detector for a landmine you know how to defuse without also defusing it; (3) when waiting on a long run, watch the log's **age**, not its tail (`stat -c %Y` vs `date +%s`); if it stalls, kill it, run the stalled file alone, then after its collection-order predecessors — or use `-o faulthandler_timeout=40` as the "silence the startup Welcome dialog" entry above prescribes.

### PF-TST-12

- **Rule:** A determinism gate on a compressed binary artifact such as a PNG compares decoded pixels, never file bytes, because different zlib builds can encode identical pixels to different bytes.
- **Pinned by:** none — the body names only the texture generator's `--check` mode, which is a script, and no test.
- **Source:** #309
- **Status:** standing
- **Legacy:** b1faaa9 README L406

- **A "byte-deterministic" PNG gate is a zlib gate in disguise — compare decoded pixels, never file bytes** (Package 3b #309, 2026-08-18): the plan called for a byte-exact `--check` on the regenerated textures. PNG is lossless, but the deflate stream is produced by whatever zlib Pillow's wheel bundles (zlib vs zlib-ng, per platform and release) — the Windows dev machine and the Linux CI runner can encode *identical pixels* to *different bytes*, so a byte gate flaps between environments or forces a Pillow pin. Fix: `--check` decodes the committed PNG and compares arrays; regeneration rewrites a file only when its pixels change (otherwise every cross-platform run would produce a spurious diff). Same reasoning applies to any binary artifact with a compressor in the encode path (PNG, zip, gzip'd fixtures): the art is the pixels; the bytes are the tool's. The SVG generators are unaffected — they emit text.

### PF-TST-13

- **Rule:** A hidden texture wrap seam is located by measuring the per-column difference between row 0 and row 255, not by theorising about the layout, because the metric already knows where the seam is.
- **Pinned by:** none — the body names no test; it describes a measurement method for locating a texture seam.
- **Source:** #309
- **Status:** pointer → [debug-verbose: Case study: regenerated wood texture fails the seam gate in y — the "obvious" layout theories were wrong; one primitive default was the bug (Package 3b #309, fixed 2026-08-18)](../../../.claude/skills/debug-verbose/SKILL.md#case-study-regenerated-wood-texture-fails-the-seam-gate-in-y--the-obvious-layout-theories-were-wrong-one-primitive-default-was-the-bug-package-3b-309-fixed-2026-08-18)
- **Legacy:** b1faaa9 README L408

Held in [debug-verbose: Case study: regenerated wood texture fails the seam gate in y — the "obvious" layout theories were wrong; one primitive default was the bug (Package 3b #309, fixed 2026-08-18)](../../../.claude/skills/debug-verbose/SKILL.md#case-study-regenerated-wood-texture-fails-the-seam-gate-in-y--the-obvious-layout-theories-were-wrong-one-primitive-default-was-the-bug-package-3b-309-fixed-2026-08-18). The entry keeps the rule and its pin; the account is in the link.

### PF-TST-14

- **Rule:** A `QTimer` in a widget takes the widget as parent, a debounced action stops its own timer when it runs, and a timer whose slot can open a modal is stopped in `done()` or `closeEvent`.
- **Pinned by:** `tests/unit/test_plant_search_dialog_timer.py`
- **Source:** #210, #310
- **Status:** standing
- **Legacy:** b1faaa9 README L410

- **A debounce `QTimer` armed by a test outlives the test — and a timer slot that can open a modal `QMessageBox` becomes a heap-corruption crash in whatever test runs 500 ms later** (Package 3c #310, 2026-08-18): `PlantSearchDialog` created its debounce timer as `QTimer()` (no parent). Every test that typed into `search_input` armed it, called `_perform_search()` synchronously, and finished well inside 500 ms — leaving the timer ARMED (a file-logged probe over the full battery counted 17 such calls, all with `timer.isActive() == True`). Two mechanisms are consistent with what was observed, and the run that crashed predates the probe, so the exact liveness state at fire time is not known: (a) the dialog's Python object had been collected → the C++ dialog deleted → the *unparented* timer (Python-owned, still referenced through the signal connection) fired into a dead widget; or (b) the dialog was still alive (its own `timeout → bound method` connection forms a reference cycle that only a later GC breaks) and the slot opened a modal `QMessageBox.warning(self)` in the middle of another test's `processEvents`, whose nested loop then processed the deferred deletion of that very dialog under the modal's feet. Either way the symptom was `Windows fatal exception: code 0xc0000374` in `test_plant_sprite_rendering.py`, a file that has nothing to do with plant search, and it had never fired before because the timing landed in harmless places until two new test files shifted the schedule. Fix, three legs, covering both mechanisms: `QTimer(self)` (lifetime bound to the widget — closes (a)), `done()` stops it (a pending debounced action must be settled before the dialog goes — the #210 flush rule), and **`_perform_search()` itself stops it first** (a search that runs NOW must not run again 500 ms later — this is what closes (b), and it is why the first fix round with parenting alone still aborted). Pinned by `tests/unit/test_plant_search_dialog_timer.py`. Rules: any `QTimer` created in a widget takes that widget as parent; a debounced action settles its own timer when it runs; any timer slot that can open a modal or touch child widgets is stopped in `done()`/`closeEvent`. Diagnostic tell: the crash's stack ends in a widget method under `pytestqt/plugin.py … _process_events` during the SETUP or CALL of an unrelated test — read the crashing FRAME, not the test name; the culprit is whichever earlier test left a timer or thread alive; log the probe to a file, pytest capture dies with the process (playbook row 37).

### PF-TST-15

- **Rule:** Top-level JavaScript `let` bindings never land on `window`, so a readiness probe evaluates them in page scope (`typeof map !== 'undefined'`) or calls a status function the page exposes on `window`.
- **Pinned by:** none — the body names no test; it describes how a live-harness probe should read page state.
- **Source:** #346
- **Status:** standing
- **Legacy:** b1faaa9 README L424

- **JavaScript `let` declarations never land on `window` — verification JS that reads `window.map`/`window.bridge` from a page written with top-level `let` returns `undefined` forever, even when the page state is perfectly healthy** (#346 live harness, 2026-09-01): the picker page (and the spike before it) declares `let map`, `let bridge`, `let drawingRectangle`. Polling `runJavaScript("window.map")` is therefore a blind probe — it reports "not ready" while the map is on screen. Use `runJavaScript("typeof map !== 'undefined' && map && ...")` (page-scope evaluation), or expose a dedicated status function on `window` from the page itself.

### PF-TST-16

- **Rule:** A Qt test covers a timer handler by emitting the timer's `timeout` signal directly, never by starting a widget-owned short-interval timer inside a `qtbot.waitUntil` poll.
- **Pinned by:** none — the body names no test as a pin; `TestMinimapIdleQuiescence` is cited only as the unrelated crash site.
- **Source:** #346
- **Status:** standing
- **Legacy:** b1faaa9 README L428

- **A real short-interval `QTimer` racing pytest-qt's `waitUntil` loop segfaults the linux-offscreen suite — drive timer-handler coverage by emitting the signal instead** (#346 finalization, 2026-09-01): three capture tests set the dialog's 20 s watchdog to a 10 ms interval and `start()`ed it inside a `qtbot.waitUntil(...)` poll of the handler's side effect. Local Windows was green; the windows-differ linux-offscreen CI run aborted with `Fatal Python error: Segmentation fault` — always inside `TestMinimapIdleQuiescence` (an *unrelated* file whose quiescence counting is a natural crash site for corruption planted earlier), at a different member test each run, at the same 66% suite position. Diagnosis recipe that pinned it: (1) trigger master's own CI via a throwaway probe branch (ruled out a runner-flake; master was green); (2) bisect across CI runs — disabling the two new test files → green; re-enabling the unit file → green; skipping all tests but collecting the file (`pytestmark = skip`) → green (collection-time imports innocent); halving the classes (skip ErrorMapping/Eea/RoundTrip/Bridge) → red; only ButtonLifecycle → green; only Success → green; only Cancel without watchdog tests → green. The three watchdog tests were the only red constellation — the combination of a real 10 ms single-shot racing the pytest-qt poll loop was the difference. Fix: emit the timer's signal directly (`dialog._capture_watchdog.timeout.emit()`) — identical handler coverage, zero timing races — and keep the real watchdog timing to the live E2E harness. Rules: never `setInterval(10)+start` a *widget-owned* timer inside a `waitUntil` in a Qt test — if the goal is handler logic, emit the signal; if the goal is real timing, use a live-session harness. Watch out when re-adding: pytest collects `*_test.py` module-level imports in alphabetical file order, so a new test file's *module imports* change nothing here — the poison was execution, not collection.

### PF-TST-17

- **Rule:** A page-side JavaScript guard that compares a value echoed from Python stringifies both operands or stores the value stringified, because a number never strictly equals its string form.
- **Pinned by:** `tests/integration/test_map_picker_capture.py::TestBridgeContract`
- **Source:** #346, #347
- **Status:** standing
- **Legacy:** b1faaa9 README L432

- **JS-side guards comparing a NUMBER token with its STRING form silently eat every capture report — the capture "times out" while every test is green** (#347 live manual test, 2026-09-02): the new capture choreography's page-side guards read `if (!captureState || captureState.token !== String(token)) return;`. Python calls `window.beginCaptureChrome(1)` — a JS **number** literal — so `captureState.token` was a number, `String(token)` a string, and `1 !== '1'` was **always true**. Every profile/frame readiness report died in the guard; Python's 20 s watchdog then popped "The capture timed out — check your network or the API key" while the map was perfectly healthy. All 109 automated tests were green because they drive the QtWebEngine-free bridge directly and never execute the page's JavaScript. The `TestBridgeContract` drift guard only greps function *names*. Fix: stringify at **storage** (`captureState = { token: String(token), … }`) so the echo comparison is string-vs-string; the drift guard now also pins `token: String(token)` in the HTML. Proof: `scripts/live_capture_harness.py` (real dialog + real map + real key) showed `js_result 'ok'` then silence; after the fix it shows the full profile → frame → stitch sequence completing. Rule: **any page-side guard that compares a value echoed from Python must stringify BOTH operands (or store stringified)** — Python hand-builds JS literals, and `1 !== '1'` is a silent always-false guard, exactly the failure shape that automated tests cannot see (same lesson as #346's live harness — the page's JavaScript is only exercised by a live run).

### PF-TST-18

- **Rule:** A performance test gates the median of repeated warmed samples and reports the sample list on failure, because one wall-clock sample on a shared runner cannot tell a scheduler spike from a regression.
- **Pinned by:** none — the body names no test file or function; the median-gated spatial-index test it describes applies the rule rather than guarding it.
- **Source:** #354
- **Status:** standing
- **Legacy:** b1faaa9 README L462

**A single wall-clock CI sample cannot distinguish a scheduler spike from a spatial-index regression (issue #354, 2026-09-24).** Symptom: one Python 3.11/Linux run measured 284.1 ms against a 250 ms hard limit while a parallel run and the complete local suite passed; the branch did not touch the spatial-index implementation. Repeating the old test unchanged would preserve the flake. The fix warms the path, records five rebuild and five query samples, and gates medians (200 ms build, 1 ms query) with the sample list in the failure message. Repeated local Python 3.12/Windows samples were about 15 ms median, and the historical 284 ms observation is retained as the calibration outlier. Lesson: performance tests should protect a sustained regression statistically, not assert that one shared runner owns a quiet CPU; report the distribution when the platform is noisy.

### PF-TST-19

- **Rule:** A green suite is evidence only about the paths it exercises, so a regression test reproduces the exposing condition, such as a preview over an existing item or a stop with a client attached.
- **Pinned by:** `tests/integration/test_tool_preview_z_order.py`; `tests/integration/test_agent_api_shutdown.py`
- **Source:** #373, #377, #378, #380
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l630-the-four-bugs-a-manual-pass-found-that-a-green-suite-could-not-377-380-373)
- **Legacy:** b1faaa9 README L630 (legacy 11.4.2)

### PF-TST-20

- **Rule:** `qtbot.addWidget` only closes a widget, so a root-conftest autouse fixture `deleteLater()`s every top-level widget after each test and flushes `QEvent.Type.DeferredDelete` by name.
- **Pinned by:** none — the body names no test; the remedy is an autouse fixture in `tests/conftest.py`, and the test files it names are victims of the leak.
- **Source:** #509
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l3322-qtbotaddwidget-closes-a-widget-and-closing-is-not-deleting)
- **Legacy:** b1faaa9 README L3322

### PF-TST-21

- **Rule:** A settings value tests rely on is written in the same fixture that wipes the store, never by a second fixture that merely depends on it, or for an instant an absent key reads the production default.
- **Pinned by:** none — the body names no test; the remedy and its tripwire live in `tests/conftest.py` fixtures, which are not tests.
- **Source:** #509
- **Status:** standing
- **Legacy:** b1faaa9 README L3360

- **Two autouse fixtures, one merely depending on the other, are an atomicity claim with
  no coverage** (issue #509, 18 October 2026). `tests/conftest.py` wiped every settings
  key in `_reset_app_settings` and wrote `KEY_AGENT_API_ENABLED = False` in a second
  fixture that merely *depended* on the first. Between the two there was a real instant
  in which the key did not exist at all, so a read returned the production default
  (`DEFAULT_AGENT_API_ENABLED = True`) and the port read 8765. A `GardenPlannerApp` from
  an earlier test arms `QTimer.singleShot(1500, self._maybe_start_agent_api)`, and a
  timer landing in that window started a **real** `AgentApiServer`; two workers doing
  that collided with `OSError: [Errno 10048]`. The window was always there — serial runs
  simply made it microseconds wide against a 1500 ms timer — and it is the same shape as
  the Welcome-dialog entry in the same conftest, where a per-test settings write lost a
  race with a 500 ms timer and the fix was to patch the **method** instead. Two further
  facts close it here: `singleShot` is handed the **bound method**
  `self._maybe_start_agent_api`, which PyQt auto-disconnects when the receiver is
  destroyed, so a fixture that destroys each test's widgets cancels the pending timer
  outright; and the write belongs **inside** the wipe, so there is no instant to lose.
  **Lesson: order a fixture's dependencies carefully and you have documented a gap, not
  closed it; a default of `True` behind an absent key is a loaded weapon the moment
  anything is deferred.** Also: `QSettings.value(key, default)` returns the raw QVariant,
  so `setValue(key, False)` reads back as the **string** `'false'` — a tripwire asserting
  `value is not True` passes for that string *and* for the absent key, which is exactly
  the state it exists to catch. Read it the way the product does, `type=bool`.

### PF-TST-22

- **Rule:** A test never creates, stages or deletes files in the git working tree; it works in a throwaway `git init` repository under `tmp_path`, which stays safe under any scheduler and any interruption.
- **Pinned by:** none — the body names only the canary test that now follows the rule and the chokepoint test it disturbed, and neither fails when a test writes into the working tree.
- **Source:** #507, #509
- **Status:** standing
- **Legacy:** b1faaa9 README L3383

- **A test that writes into the git working tree is unsafe under any scheduler, and
  serial execution hides it** (issue #509, 18 October 2026). `test_gate_commands.py`'s
  secret-checker canary staged `scripts/_canary_<tag>.py` in the **real** repository,
  scanned, then unstaged and deleted — the only test in the suite that mutated shared
  state. `test_settings_chokepoint.py` globs that same tree (`root.rglob("*.py")`) and
  reads what it found, and those are two moments: under `pytest -n 8` one worker's
  `rglob` could list the canary inside the other worker's write-to-unlink window and die
  with `FileNotFoundError` on the read — three failures in one run — while the same window
  let the canary's own file-wide scan read a *sibling worker's* staged canary and report a
  credential that was never committed anywhere. #507 separately found that an interrupted
  run left the canary staged and the next `git commit -a` published it (a one-line canary
  really was committed on PR #507). The fix is not a scheduler: the canary is now staged
  in a throwaway `git init`-ed repo under `tmp_path`, so nothing outside the temp directory
  is created, staged or deleted even if the process dies mid-test — which makes #507's
  hazard structurally impossible rather than hardened. **Lesson: `@pytest.mark.xdist_group`
  would have hidden this and left the two-concurrent-pytest-process case (the 2026-08-17
  incident that made `TEST_APPLICATION` per-PID) exactly as dangerous; and a hazard that
  exists only under a scheduler is usually a hazard that exists without one too.**

### PF-TST-23

- **Rule:** Asking the OS for a free port and closing the socket is not a reservation, so one shared helper retries only the port-in-use failures and re-raises every other `RuntimeError` at once.
- **Pinned by:** none — the body names no test for the shared port-retry helper, and `tests/perf/test_nfr_budgets.py` is cited only as evidence about the CI frame budget.
- **Source:** #509
- **Status:** standing
- **Legacy:** b1faaa9 README L3402

- **`pytest-timeout`'s per-test bound is necessary but not sufficient for a Qt suite,
  and asking the OS for a free port is not a reservation** (issue #509, 18 October 2026).
  Two distinct time hazards, both found the hard way. First, ten test files each carried
  their own copy of `_free_port()` — `bind(("127.0.0.1", 0))`, read the port, **close the
  socket** — and the caller then binds it, so the port is free in name only. Serially the
  window is microscopic; with `-n auto` on 20 workers it is not, and the measured failure
  was `RuntimeError: Agent API server failed to start`, because uvicorn's own
  `create_server` hit `OSError: [Errno 10048]` after the pre-bind socket check had already
  passed. Two `-n 8` runs gave 2 failures and 1 failure, so **capping the worker count would
  not have addressed it, only lowered the odds** — the fix is a retry, in one shared helper,
  because losing that race is inherent to asking the OS for a port and then releasing it.
  That helper retries `PortInUseError` and the exact string
  `"Agent API server failed to start"`, and re-raises every other `RuntimeError`
  immediately: a retry that swallows real product defects is worse than the flake it was
  written to remove.
  Second, and **this correction is itself the lesson**: an earlier draft of this entry
  claimed "`--cov` and the perf tests are mutually exclusive - the repaint budget fails at
  **20.29 ms against a 16.70 ms budget** under tracing ... so the `Coverage` job has been
  measuring something it cannot gate". Both halves were wrong, and the error is the one this
  section exists to prevent. `tests/perf/test_nfr_budgets.py:56-57` reads
  `_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"` and `FRAME_BUDGET_MS = 50.0 if _IS_CI else 16.7`, so on CI
  the budget is **50 ms**. The 20.29 ms was measured **here**, against the **local** 16.7 ms
  budget, and was generalised to a configuration nobody ran - and `gh run view 39076508170`
  records master's `Coverage` job **succeeded** at `412f01bd`. One variable, both ways, same
  file: `CI=true` -> 6 passed; unset -> 1 failed.
  **Lesson: a measurement taken against one configuration says nothing about another.**
  **Lesson: a number that arrives from a reviewer's report is still a number you did not
  take - the same discipline applies to your own review round.**
  **Lesson: a missing `finally` around a side effect is a correctness bug and an unbounded
  retry loop is a hang; both are worth catching by asking what a helper swallows, not what
  it returns.**

### PF-TST-24

- **Rule:** A measurement that travels in an attribute is a wall-clock assertion too: the perf-marker guard follows the carrier into the local support modules, scoped to the class that owns it, and a value that is only counted is not a duration.
- **Pinned by:** `tests/unit/test_perf_marker_guard.py::test_a_measurement_that_travels_in_an_attribute_is_seen`; `tests/unit/test_perf_marker_guard.py::test_a_test_that_times_nothing_is_not_seen`
- **Source:** #528
- **Status:** standing
- **Legacy:** none (new entry)

The guard matched a timing SOURCE and followed the call graph - and a
measurement that travels in an ATTRIBUTE was invisible: the stopwatch sat in one
method, the assertion read the attribute it filled, and often the two were in
different modules (the class that owns the attribute is usually in a support
module beside the test). The ground bake's G3 gate was marked `perf` BY HAND
for exactly that reason.

The carrier is now followed: an attribute is timed when a clock-reading method
of its class fills it, and the guard looks into the local support modules a test
file imports. The attribute is scoped to its class, so one class's stopwatch
never taints another class's attribute of the same name - that is the half of
the bare-name collision that reaches this guard.

A value that is only COUNTED is not a duration: `len(timestamps)` is how the
gates that count repaints and passes are written, and they are meant to hold on
any machine under any load and to run beside the workers (ADR-058). Counting
them as durations would have dragged them onto the quiet runner.
