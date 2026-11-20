# Case study: a reference-point branch crashed the suite once every ten app windows (#666)

**Symptom.** The three-file sequence `tests/integration/test_example_generation.py`
+ `tests/unit/test_app_locale.py` + `tests/ui/test_language_menu.py` crashed 3 of 5
runs with `Windows fatal exception: 0xC0000374` (once `0xC0000005`), always at
pytest-qt's `plugin.py::_process_events` during the teardown of the **second**
language-menu test. Clean `master` was 0/10 on the same sequence. It was not a
test failure: the worker process was gone.

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
sequence (`gc.disable()` at test-module import) ran the old ten-window file 0/3:
the fault is in the destruction of a Python-owned Qt graph, not in the added action,
the translation or a timer. `_reclaim_widgets` closes and deletes top-level widgets,
but the view/scene graph is cyclic garbage only the collector finds, and a collection
inside event processing is the family PF-CAN-61 records.

**Fix.** `tests/ui/test_language_menu.py` builds **one** `GardenPlannerApp` and asserts
its whole Language submenu against it (0/6 crashes, 38% faster; the assertions are
strictly stronger - exact ordered list). PF-TST-41 records the rule and the controls.

**Key line.** `Windows fatal exception: code 0xc0000374` under
`pytestqt/plugin.py line 220 in _process_events`, at the teardown of a test that had
just PASSED.

**Lesson.** When a feature branch turns a green suite red with a heap fault, the
question is not "which new line is wrong" but "what did the branch add to the
per-process heap churn". Measure controls on `master` before blaming the feature:
window count, one removed widget, GC off. A crash that moves between tests is a
lifetime problem, and the fix belongs in the harness's churn, not in a deleted
assertion.
