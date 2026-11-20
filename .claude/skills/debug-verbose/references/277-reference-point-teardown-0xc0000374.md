# Case study: a reference-point branch crashed the suite once every ten app windows (#666)

**Symptom.** The three-file sequence `tests/integration/test_example_generation.py`
+ `tests/unit/test_app_locale.py` + `tests/ui/test_language_menu.py` crashed 3 of 5
runs with `Windows fatal exception: 0xC0000374` (once `0xC0000005`), always at
pytest-qt's `plugin.py::_process_events` during the teardown of the **second**
language-menu test. Clean `master` was 0/10 on the same sequence. Later, two
full-suite runs on the branch each lost an xdist worker in
`tests/ui/test_main_window.py::TestPreviewMode`, while master's full run was clean.
It was never a test failure: the worker process was gone.

**Wrong theories, each measured and rejected.**

1. *A sixth main-toolbar button corrupted Qt's teardown.* The branch had added one
   for the new tool; removing it was not enough - a text-only Garden-menu `QAction`
   still crashed, and a verbose run showed the crash on a run where the toolbar had
   no sixth button.
2. *The new Garden-menu action is the trigger.* Removing only that action ran 0/6
   clean, which looked conclusive. But `master` with a dummy tenth window also ran
   0/6, so window count alone was not it either; the action was one more allocation,
   not a code path (none of its slots ever ran in these tests).
3. *The 500 ms startup sequence fires on a closed window and opens a modal.*
   `find_recovery_files()` returns empty in the isolated test data dir, and guarding
   `_startup_sequence` with a closing flag still crashed (a different fault code).
4. *The French catalog corrupts the translator.* All five `.qm` files load and
   translate; the English UI installs no translator at all. `scripts/check_translations.py`
   was green.

**The distinguishing experiment.** Disabling Python's cyclic collector for the
sequence (`gc.disable()` at test-module import) ran the old ten-window file 0/3.
That placed the fault in a Python-owned Qt object destroyed by the collector while
something still touched it. Reading `GardenPlannerApp._enter_preview_mode` found
the something: `QTimer.singleShot(50, self.canvas_view.fit_in_view)`. Every
`TestPreviewMode` test enters and leaves preview within milliseconds, so the
timer was still armed at teardown, fired into the next test's `processEvents`,
and called `fit_in_view` on a view the collector was dismantling. The branch's
extra per-window allocation only shifted the timing enough to expose it.

**Fix.** Two legs:

1. The preview fit is a member `QTimer` stopped in `_exit_preview_mode` and in
   `closeEvent` (PF-TST-14's rule: a timer armed by a gesture is settled when the
   gesture ends). This also removes a stale fit after leaving preview.
2. `tests/ui/test_language_menu.py` builds **one** `GardenPlannerApp` and asserts
   its whole Language submenu against it (0/6 crashes, 38% faster; the assertions
   are strictly stronger - exact ordered list). PF-TST-41 records the amplifier
   rule.

**Key line.** `Windows fatal exception: code 0xc0000374` under
`pytestqt/plugin.py line 220 in _process_events`, at the teardown of a test that had
just PASSED.

**Lesson.** A crash that moves between tests is a lifetime problem, and the frame
under `_process_events` is only where the allocator noticed. Two measurements paid
for themselves: the GC-off control (it told us the collector was involved) and
reading the gesture's own code for an armed timer (it found the singleShot). A
feature branch that only changes timing is still the branch that must fix the
latent timer - and the harness fix (one app per file) stays because it removes the
amplifier, not because it hides the cause.
