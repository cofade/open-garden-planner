## Case study: Saved-plan recovery was never discovered (#797) (2026-11-16)

**Symptom:** The owner saw the autosave message, killed the frozen app and restarted.
No recovery appeared; opening the original showed old work.

**Theories checked:** The snapshot was not necessarily missing. The owner log recorded
an adjacent saved-plan backup, followed by its deletion when the original opened.
The prior complete-store tests invoked the recovery loader directly and bypassed discovery.

**Evidence:** A temporary pytest plugin printed discovery candidates and the cleanup
call stack. Six new workflow assertions failed before the correction:

```text
[RECOVERY-DISCOVERY] candidates=[]
[RECOVERY-CLEAR] target=.../~autosave_saved.ogp exists=True
_open_project_file -> _load_project_file -> clear_autosave
```

**Root cause:** Startup searched only the temporary untitled filename, and GUI Open
never called the existing per-project finder. Loading the original rebound the
manager's filename before cleanup; cleanup then deleted that original's unoffered
backup. Save As had the same ownership error in reverse.

**Fix:** Search the untitled candidate plus ten recent plans and check each explicitly
opened plan. Verify the recorded original identity and freshness. Share one modal
offer, retain No, delete only on Discard, and stop normal opening after a failed Yes.
Track written/adopted paths separately from the current filename. Recover one plan
per startup and guard nested startup callbacks while a recovery modal is active.

**Regression evidence:** `tests/integration/test_autosave_recovery.py` exercises real
startup and GUI Open, all three choices, Save As, foreign destination preservation,
multiple candidates, nested startup and failed recovery. Unit tests cover stale
candidates, deduplication and symlink-entry cleanup. The instrumentation was external
to the tracked source and is not part of the product.

**Review follow-up:** Two isolated workflow extensions also failed before their
fixes: a second explicit open after failed Yes loaded the old original, and
No followed by another autosave overwrote the deferred backup. A Yes no longer
caches the refusal for later explicit opens. New snapshots use a per-document
UUID path, reused across timer ticks, and discovery recognizes legacy plus UUID
filenames. Declining recovery, editing, autosaving and accepting close/discard preserves the deferred
bytes and makes the older recovery discoverable again. Distinct untitled documents
retain independent snapshots too.

**Lesson:** Recovery is discovery, decision, load and retention. A direct loader test
cannot prove the path a person takes after restarting the app.
