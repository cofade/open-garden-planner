# Pitfalls: test-suite hygiene and isolation

Standing rules for this area, one entry each. The heading is the rule. Pins and sources are listed under each entry. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-TST-01

- **Rule:** Hold a worker in flight when proving GUI responsiveness
- **Pinned by:** `tests/integration/test_sun_mismatch.py::test_explicit_worker_keeps_gui_responsive`
- **Source:** #490
- **Status:** standing
- **Legacy:** README L101

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

- **Rule:** Within-day simulation tests must fix time as well as date
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L146

- **Within-day simulation tests must fix time as well as date** (ADR-053): the
  sun-mismatch workflow set the date, retained 23:49 from the host, then added an
  hour. Correct next-day invalidation contradicted its `ready` assertion. Tagged
  datetime/caller tracing reproduced the same failure alone. Set the fixture to
  noon with `set_time_of_day`; retain worker, cache and date-invalidation checks.
  Do not change production clock semantics or relax timeouts to fix the fixture.

### PF-TST-03

- **Rule:** Every placeable graphics item must be covered by serializer round-trip matrix tests.
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #394
- **Status:** standing
- **Legacy:** README L181

- **Every placeable graphics item must be covered by serializer round-trip matrix tests.** (Issue #394, AUD-001, AUD-017, TD-010, TD-019): Free-text annotations (`TextItem`) were serializable on the clipboard since v1.1 but completely missing from `ProjectManager._serialize_item_core` and `_deserialize_item_core`. Saving a plan containing text annotations silently dropped them. Unit tests tested persistence for common shapes but lacked an exhaustive matrix across all concrete placeable item types. Fix: `TextItem` is serialized natively under `type: "text"` with font, color, content, and position attributes. A comprehensive round-trip matrix test (`tests/integration/test_item_roundtrip_matrix.py`) verifies exact dictionary equality and round-trip fidelity across every concrete placeable item in the application.

### PF-TST-04

- **Rule:** A cleanup fixture that runs in the wrong ORDER is not a cleanup — and a plausible mechanism is not a mechanism.
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** #366
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l184-a-cleanup-fixture-that-runs-in-the-wrong-order-is-not-a-cleanup--and-a-plausible-mechanism-is-not-a-mechanism)
- **Legacy:** README L184

### PF-TST-05


- **Rule:** A test that exercises a real external binary will exercise it on the developer's machine.
- **Pinned by:** none — the home holds this rule (see Status); no test is named here
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L196

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-TST-06

- **Rule:** `QSettings.setDefaultFormat()` / `setPath()` are process-global statics Qt never reverts — never call them from a test
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #285
- **Status:** standing
- **Legacy:** README L366

- **`QSettings.setDefaultFormat()` / `setPath()` are process-global statics Qt never reverts — never call them from a test** (test-suite isolation): a test fixture in `tests/unit/test_ui_state.py` redirected `UiStateStore`'s settings to a temp INI file by calling `QSettings.setDefaultFormat(IniFormat)` + `QSettings.setPath(IniFormat, UserScope, tmp_path)`. Those are **static, process-wide** and are *not* auto-reverted (the `monkeypatch` arg was declared but unused). After that unit test ran (~⅔ through the suite), the global default format pointed at a `tmp_path` pytest had since deleted, so **every** `QSettings`/`AppSettings` constructed *later in the session* — the `get_settings()` singleton behind the snap-toggle handlers and the welcome dialog — wrote to a dead path and every getter fell back to its coded default. Symptom: 6 settings-persistence tests (`test_anchor_snap`, `test_nearest_snap_workflow`, `test_perpendicular_snap`, `test_tangent_snap`, `test_welcome_dialog`) **fail only in the full run, pass in isolation, and CI stays green** (different collection order/platform dodges the poison). The uniform tell: every failing getter returns exactly the *default* value, i.e. the setter write never persisted. Fix: isolate by `monkeypatch.setattr("open_garden_planner.app.settings.create_qsettings", <factory returning QSettings(ini_path, IniFormat)>)` (auto-reverts, touches no global state) — never the global statics. *(Recipe updated by #285: `ui_state.py` no longer has a `QSettings` name to patch, and `tests/unit/test_settings_chokepoint.py` forbids re-adding one — there is now a single factory to redirect, which is what `tests/unit/test_ui_state.py` does.)* Defensive backstop in [`tests/conftest.py`](../../../tests/conftest.py): the session `isolate_qsettings` fixture now captures `QSettings.defaultFormat()` and restores it at teardown (a tripwire for a future `setDefaultFormat` leak — it does **not** cover a `setPath`-only leak), and a function-scoped autouse `_reset_app_settings` clears the `cofade_test` store + nulls the `_settings_instance` singleton around every test so per-test value pollution can't accumulate either. Lesson: a green CI does not prove the local full suite is clean; a "passes alone, fails together" failure whose actual value is always the default is almost always shared global/singleton state, not the code under test. The deeper smell this entry flagged as a follow-up — `UiStateStore` and `AppSettings` each constructing their own store inline, so there was no single chokepoint to isolate — **is fixed (#285 / ADR-041)**: `app/settings.create_qsettings()` is that shared factory, and one fixture now isolates everything. The `defaultFormat()` capture in `isolate_qsettings` was also upgraded from a silent repair to a real tripwire (it restores, then asserts) — a backstop that quietly fixes the damage reports nothing.

### PF-TST-07

- **Rule:** A full-app integration test that outlives ~500 ms must silence the startup Welcome dialog — its modal `exec()` blocks pytest-qt forever
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #279
- **Status:** standing
- **Legacy:** README L377

- **A full-app integration test that outlives ~500 ms must silence the startup Welcome dialog — its modal `exec()` blocks pytest-qt forever** (#279 test-infra finding): `GardenPlannerApp` arms `QTimer.singleShot(500, self._startup_sequence)`, which — with `show_welcome_on_startup` enabled, the default on dev machines — opens the **modal** `WelcomeDialog` via `dialog.exec()`. Headless nobody closes it, so the first event processing after the timer fires (typically pytest-qt's `_process_events` between/after tests) parks the session inside the modal event loop forever — and because pytest's output is block-buffered, the log stays EMPTY, so the hang masquerades as a collection freeze. Existing app-boot tests never hit it because they finish inside the 500 ms window; the #279 theme-switch tests (pixel scans + two full restyles) were the first to outlive it. Fix pattern (`tests/integration/test_icon_system.py::_make_app`): `monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda self: None)` before construction, alongside the established `QMessageBox.question` → Discard patch. Diagnosis tool that found it: `pytest -o faulthandler_timeout=40` dumps every thread's stack at the hang moment — reach for it whenever a Qt test "hangs with no output." Re-hit on 2026-08-17 (Package 3a): the fix had been applied per file, and only three of 34 app-building test files carried it, so a full `pytest tests/` run stalled for 18 minutes inside `tests/integration/test_trellis.py`. The stall showed only as an old log modification time. The fix now lives in `tests/conftest.py::_silence_welcome_dialog`.

### PF-TST-08

- **Rule:** `UiStateStore` builds its own `QSettings`, so it escapes the conftest isolation — full-app tests read *and overwrite* the developer's real window state
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #283, #285
- **Status:** standing
- **Legacy:** README L385

- **`UiStateStore` builds its own `QSettings`, so it escapes the conftest isolation — full-app tests read *and overwrite* the developer's real window state** (#283 test-infra finding — **Closed (#285)**): `tests/conftest.py::isolate_qsettings` redirects `AppSettings` only, but `app/ui_state.py` constructs `QSettings("cofade", "Open Garden Planner")` directly. Every `GardenPlannerApp()` in a test therefore restored whatever geometry and toolbar layout the developer's own app last saved — and wrote it back at teardown, because pytest-qt closes registered widgets and `closeEvent` → `_save_ui_state()` persists. Symptom while writing #283's regression tests: a toolbar-visibility assertion passed under pristine settings and failed locally with the *fix applied*, purely because an earlier experiment had left a different toolbar layout in the real store — an hour lost to "the fix doesn't work" when the test harness was the variable. First patched by an autouse `_isolate_ui_state` fixture pointing `ui_state.QSettings` at the test key; local runs then also matched CI, where the store is always pristine (so `_geometry_restored` is False and the window maximizes). Lesson: a store that bypasses the settings chokepoint also bypasses the test isolation built on it. **Closed by #285 / ADR-041**, which made the tourniquet unnecessary rather than permanent: `app/settings.create_qsettings()` is the only place that constructs — or even names — a settings store, `UiStateStore` takes its backend from there, `_isolate_ui_state` is deleted, and `tests/conftest.py` redirects the whole app by rebinding two module names *at its own import time*. **The mechanism is specified once, in §8.8 — read it there, and change it there.** Do not re-derive it in this entry: three earlier attempts to summarise it here, in ADR-041 and in `CLAUDE.md` each drifted out of sync with the code within one commit, which is how reviews 2, 3 and 4 all found a doc/code mismatch. What belongs here is the evidence: reverting the chokepoint makes `tests/integration/test_settings_isolation.py` fail with exactly 3 reads + 3 writes to the real key, and hashing the real store's 29 values around a 47-test full-app file leaves them byte-identical.

### PF-TST-09

- **Rule:** The test suite wrote into the developer's real plant library — isolating one store is not isolating the process
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** #285
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l387-the-test-suite-wrote-into-the-developers-real-plant-library--isolating-one-store-is-not-isolating-the-process)
- **Legacy:** README L387

### PF-TST-10

- **Rule:** A "nobody may use X" gate belongs in the AST, not in a regex — and it must be falsified twice
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #285
- **Status:** standing
- **Legacy:** README L396

- **A "nobody may use X" gate belongs in the AST, not in a regex — and it must be falsified twice** (#285, gate-design lesson): `test_settings_chokepoint.py` started as a line-anchored regex for `QSettings\s*\(`. Falsifying it by restoring the pre-#285 code as `from PyQt6.QtCore import QSettings as _Q` … `_Q("cofade", …)` — a two-line edit anyone could make while "just fixing an import cycle" — sailed through, so an **import** pattern was added. A senior review then broke *that* in one experiment: `from PyQt6.QtCore import (\n    QSettings as _Q,\n)` names the class on a line with no `import` keyword, so both regexes passed and only the behavioural test caught the bug. Rewritten as an `ast` walk over `Import`/`ImportFrom`/`Name`/`Attribute`, all spellings collapse into one check — and the same walk cheaply expresses a rule no regex could ("no `create_qsettings()` call that is evaluated at import time", distinguishing a function *body* from a decorator or default argument). Lessons for every textual gate in this repo (QSS colors, icon conformance, texture tileability): match the **name binding**, not just the use, because you cannot use what you have not first named; prefer the AST when the language has one; give every detector a **positive control** fed the exact escape it exists to catch, since a detector that stops matching anything reads as a green gate forever; and treat "my falsification passed" as one data point, not proof — the second reviewer found the second hole in one try.

### PF-TST-11


- **Rule:** The Welcome-dialog hang above was re-hit on 2026-08-17 (Package 3a) — because its fix was per-file, and only three of 34 app-building test files had it.
- **Pinned by:** `tests/conftest.py`; `tests/conftest.py::_silence_welcome_dialog`; `tests/integration/test_trellis.py`
- **Source:** none recorded
- **Status:** pointer → [PF-TST-07](07-test-suite-hygiene.md#pf-tst-07)
- **Legacy:** README L402

Duplicate of [PF-TST-07](07-test-suite-hygiene.md#pf-tst-07): the 2026-08-17 re-hit of the Welcome-dialog hang. Its facts are merged into that entry.

### PF-TST-12

- **Rule:** A "byte-deterministic" PNG gate is a zlib gate in disguise — compare decoded pixels, never file bytes
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #309
- **Status:** standing
- **Legacy:** README L406

- **A "byte-deterministic" PNG gate is a zlib gate in disguise — compare decoded pixels, never file bytes** (Package 3b #309, 2026-08-18): the plan called for a byte-exact `--check` on the regenerated textures. PNG is lossless, but the deflate stream is produced by whatever zlib Pillow's wheel bundles (zlib vs zlib-ng, per platform and release) — the Windows dev machine and the Linux CI runner can encode *identical pixels* to *different bytes*, so a byte gate flaps between environments or forces a Pillow pin. Fix: `--check` decodes the committed PNG and compares arrays; regeneration rewrites a file only when its pixels change (otherwise every cross-platform run would produce a spurious diff). Same reasoning applies to any binary artifact with a compressor in the encode path (PNG, zip, gzip'd fixtures): the art is the pixels; the bytes are the tool's. The SVG generators are unaffected — they emit text.

### PF-TST-13


- **Rule:** A hidden wrap seam is located by measuring `|row0 − row255|` per column, not by theorising about the layout
- **Pinned by:** none — the home holds this rule (see Status); no test is named here
- **Source:** #309
- **Status:** pointer → [debug-verbose: Case study: regenerated wood texture fails the seam gate in y — the "obvious" layout theories w](../../../.claude/skills/debug-verbose/SKILL.md#case-study-regenerated-wood-texture-fails-the-seam-gate-in-y--the-obvious-layout-theories-were-wrong-one-primitive-default-was-the-bug-package-3b-309-fixed-2026-08-18)
- **Legacy:** README L408

Held in [debug-verbose: Case study: regenerated wood texture fails the seam gate in y — the "obvious" layout theories w](../../../.claude/skills/debug-verbose/SKILL.md#case-study-regenerated-wood-texture-fails-the-seam-gate-in-y--the-obvious-layout-theories-were-wrong-one-primitive-default-was-the-bug-package-3b-309-fixed-2026-08-18). The entry keeps the rule and its pin; the account is in the link.

### PF-TST-14


- **Rule:** A debounce `QTimer` armed by a test outlives the test — and a timer slot that can open a modal `QMessageBox` becomes a heap-corruption crash in whatever test runs 500 ms later
- **Pinned by:** `tests/unit/test_plant_search_dialog_timer.py`
- **Source:** #210, #310
- **Status:** pointer → [debug-verbose: Case study: Trefle search results never carried sun/water/pH/foliage data -- dead code, a wrong](../../../.claude/skills/debug-verbose/SKILL.md#case-study-trefle-search-results-never-carried-sunwaterphfoliage-data----dead-code-a-wrong-theory-refuted-live-and-three-more-bugs-found-only-by-trying-to-break-the-fix-issue-297-fixed-2026-08-10)
- **Legacy:** README L410

Held in [debug-verbose: Case study: Trefle search results never carried sun/water/pH/foliage data -- dead code, a wrong](../../../.claude/skills/debug-verbose/SKILL.md#case-study-trefle-search-results-never-carried-sunwaterphfoliage-data----dead-code-a-wrong-theory-refuted-live-and-three-more-bugs-found-only-by-trying-to-break-the-fix-issue-297-fixed-2026-08-10). The entry keeps the rule and its pin; the account is in the link.

### PF-TST-15

- **Rule:** JavaScript `let` declarations never land on `window` — verification JS that reads `window.map`/`window.bridge` from a page written with top-level `let` returns `undefined` forever, even when the page state is perfectly healthy
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #346
- **Status:** standing
- **Legacy:** README L424

- **JavaScript `let` declarations never land on `window` — verification JS that reads `window.map`/`window.bridge` from a page written with top-level `let` returns `undefined` forever, even when the page state is perfectly healthy** (#346 live harness, 2026-09-01): the picker page (and the spike before it) declares `let map`, `let bridge`, `let drawingRectangle`. Polling `runJavaScript("window.map")` is therefore a blind probe — it reports "not ready" while the map is on screen. Use `runJavaScript("typeof map !== 'undefined' && map && ...")` (page-scope evaluation), or expose a dedicated status function on `window` from the page itself.

### PF-TST-16

- **Rule:** A real short-interval `QTimer` racing pytest-qt's `waitUntil` loop segfaults the linux-offscreen suite — drive timer-handler coverage by emitting the signal instead
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #346
- **Status:** standing
- **Legacy:** README L428

- **A real short-interval `QTimer` racing pytest-qt's `waitUntil` loop segfaults the linux-offscreen suite — drive timer-handler coverage by emitting the signal instead** (#346 finalization, 2026-09-01): three capture tests set the dialog's 20 s watchdog to a 10 ms interval and `start()`ed it inside a `qtbot.waitUntil(...)` poll of the handler's side effect. Local Windows was green; the windows-differ linux-offscreen CI run aborted with `Fatal Python error: Segmentation fault` — always inside `TestMinimapIdleQuiescence` (an *unrelated* file whose quiescence counting is a natural crash site for corruption planted earlier), at a different member test each run, at the same 66% suite position. Diagnosis recipe that pinned it: (1) trigger master's own CI via a throwaway probe branch (ruled out a runner-flake; master was green); (2) bisect across CI runs — disabling the two new test files → green; re-enabling the unit file → green; skipping all tests but collecting the file (`pytestmark = skip`) → green (collection-time imports innocent); halving the classes (skip ErrorMapping/Eea/RoundTrip/Bridge) → red; only ButtonLifecycle → green; only Success → green; only Cancel without watchdog tests → green. The three watchdog tests were the only red constellation — the combination of a real 10 ms single-shot racing the pytest-qt poll loop was the difference. Fix: emit the timer's signal directly (`dialog._capture_watchdog.timeout.emit()`) — identical handler coverage, zero timing races — and keep the real watchdog timing to the live E2E harness. Rules: never `setInterval(10)+start` a *widget-owned* timer inside a `waitUntil` in a Qt test — if the goal is handler logic, emit the signal; if the goal is real timing, use a live-session harness. Watch out when re-adding: pytest collects `*_test.py` module-level imports in alphabetical file order, so a new test file's *module imports* change nothing here — the poison was execution, not collection.

### PF-TST-17


- **Rule:** JS-side guards comparing a NUMBER token with its STRING form silently eat every capture report — the capture "times out" while every test is green
- **Pinned by:** `scripts/live_capture_harness.py`
- **Source:** #346, #347
- **Status:** pointer → [debug-verbose: Case study: live capture harness saw "capture did not complete" while the feature worked (Issue](../../../.claude/skills/debug-verbose/SKILL.md#case-study-live-capture-harness-saw-capture-did-not-complete-while-the-feature-worked-issue-346-fixed-2026-09-01)
- **Legacy:** README L432

Held in [debug-verbose: Case study: live capture harness saw "capture did not complete" while the feature worked (Issue](../../../.claude/skills/debug-verbose/SKILL.md#case-study-live-capture-harness-saw-capture-did-not-complete-while-the-feature-worked-issue-346-fixed-2026-09-01). The entry keeps the rule and its pin; the account is in the link.

### PF-TST-18

- **Rule:** A single wall-clock CI sample cannot distinguish a scheduler spike from a spatial-index regression (issue #354, 2026-09-24).
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #354
- **Status:** standing
- **Legacy:** README L462

**A single wall-clock CI sample cannot distinguish a scheduler spike from a spatial-index regression (issue #354, 2026-09-24).** Symptom: one Python 3.11/Linux run measured 284.1 ms against a 250 ms hard limit while a parallel run and the complete local suite passed; the branch did not touch the spatial-index implementation. Repeating the old test unchanged would preserve the flake. The fix warms the path, records five rebuild and five query samples, and gates medians (200 ms build, 1 ms query) with the sample list in the failure message. Repeated local Python 3.12/Windows samples were about 15 ms median, and the historical 284 ms observation is retained as the calibration outlier. Lesson: performance tests should protect a sustained regression statistically, not assert that one shared runner owns a quiet CPU; report the distribution when the platform is noisy.

### PF-TST-19

- **Rule:** The four bugs a manual pass found that a green suite could not (#377, #380, #373)
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** #373, #377, #378, #380
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l630-the-four-bugs-a-manual-pass-found-that-a-green-suite-could-not-377-380-373)
- **Legacy:** README L630 (legacy 11.4.2)

### PF-TST-20

- **Rule:** `qtbot.addWidget` closes a widget, and closing is not deleting
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** #509
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l3322-qtbotaddwidget-closes-a-widget-and-closing-is-not-deleting)
- **Legacy:** README L3322

### PF-TST-21

- **Rule:** **Two autouse fixtures, one merely depending on the other, are an atomicity claim with
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #509
- **Status:** standing
- **Legacy:** README L3360

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

- **Rule:** **A test that writes into the git working tree is unsafe under any scheduler, and
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #507, #509
- **Status:** standing
- **Legacy:** README L3383

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

- **Rule:** **`pytest-timeout`'s per-test bound is necessary but not sufficient for a Qt suite
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #509
- **Status:** standing
- **Legacy:** README L3402

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
