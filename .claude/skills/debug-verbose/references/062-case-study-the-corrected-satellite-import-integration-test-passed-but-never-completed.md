## Case study: the corrected satellite import integration test passed but never completed teardown (Issue #342, fixed 2026-08-30)

**Symptom.** After the wrapper API failure was fixed, the test printed `PASSED` but pytest produced no summary and remained alive until interrupted.

**Wrong theories.** A leaking WebEngine object, an unjoined map worker, and the Agent API timer were all plausible because the test exercised the real main window.

**Key evidence.** The import handler at `GardenPlannerApp._on_load_satellite_background()` marks the project dirty; `GardenPlannerApp.closeEvent()` then calls `_confirm_discard_changes()`, whose modal save prompt cannot be answered in the offscreen pytest-qt teardown.

**Root cause.** The test intentionally exercised a mutating import workflow but left the window dirty, so the normal close path opened a headless modal dialog after the test body had already passed.

**Fix.** Call `win._project_manager.mark_clean()` immediately after asserting the import path has completed, before pytest-qt closes the window; this preserves the production workflow while making teardown deterministic.

**Lesson.** For headless Qt integration tests that mutate a document, inspect the production close path and neutralize its expected user prompt in test cleanup. A passing test body is not a passing test process when teardown can enter a modal loop.

