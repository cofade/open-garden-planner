## Case study: a test that passed and still errored on Qt 6.12 (#391)

- **Symptom:** after the bump to Qt 6.12, `test_app_destruction_reclaims_all_child_widgets`
  passed its body and ERRORED in teardown (`RuntimeError: wrapped C/C++ object of type
  GardenPlannerApp has been deleted`); the next test then failed "previous item was not torn
  down properly". On `master` (6.11) both passed.
- **Wrong theories:** the new `motionPreferenceChanged` connection holding the window
  (disabling it changed nothing); a PyQt 6.12 lambda leak (a minimal lambda-on-a-child
  reproduction freed on both versions).
- **Key evidence:** a refcount census of the graph reachable from the closed window: every
  holder was a closure cell of a lambda kept by a C++ connection proxy; one more round of
  `sendPostedEvents(DeferredDelete)` plus `gc.collect()` freed it on 6.12, while one round
  had been enough on 6.11 — the same probe run in a `master` worktree with its own 6.11 venv.
- **Root cause:** Qt 6.12 frees a destroyed window's connection proxies one deferred-delete
  round later; the test's flush did one round and collected before it.
- **Fix:** flush two rounds with a collection after each (PF-TST-36). No product change: the
  running event loop turns on.
- **Lesson:** to tell an upgrade's behaviour change from a latent bug, run the same probe on
  the old version side by side (a second worktree with its own venv is cheap) before
  touching product code.
