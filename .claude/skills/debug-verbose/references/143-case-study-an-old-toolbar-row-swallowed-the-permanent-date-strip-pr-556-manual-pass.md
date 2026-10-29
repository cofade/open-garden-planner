## Case study: an old toolbar row swallowed the permanent date strip (PR #556 manual pass)

**Symptom.** Plan & Sun was clipped at the left while the drawing toolbar grew tall.
**Wrong theory.** Passing fresh-layout tests and proving unrelated layout failures
pre-existing had been treated as sufficient visual acceptance. They never restored
the owner's legacy shared row.
**Evidence.** A native instrumented startup using an isolated copy of saved UI state
reproduced the owner's screenshot: `[TOOLBAR] SunSimToolbar (0, 25, 259, 137) break False`
at window width 1707. The restore hook included traceback.format_stack(). Restoring
an independent row produced width 1707 and normal drawing-toolbar height 40.
**Root cause/fix.** QMainWindow state replays toolbar topology, not just visibility.
The immutable toolbar rows now remain application-owned: restore window bounds and
splitter proportions with restore_window_state=False. Preserve existing settings blobs.
A replay-then-rehome attempt aborted natively before the restored window's first show;
the adopted fix never replays the obsolete topology. Both legacy positions failed first.
**Lesson.** Test upgrades from persisted UI state and inspect the real themed app.
The fresh-state layout and the existence of a toolbar do not prove its usable width.
Pins: test_restored_shared_row_cannot_squeeze_the_permanent_plan_strip in
tests/integration/test_toolbar_state_persistence.py and
test_fixed_layout_can_restore_bounds_without_replaying_toolbar_state in
tests/unit/test_ui_state.py. Temporary probes remain outside committed source.

