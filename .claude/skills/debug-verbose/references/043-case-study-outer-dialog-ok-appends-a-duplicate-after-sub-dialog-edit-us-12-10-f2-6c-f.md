## Case study: outer dialog OK appends a duplicate after sub-dialog edit (US-12.10/F2.6c, fixed 2026-05-03)

**Symptom**: Editing a past soil-test record via the History tab → sub-dialog accepted, history list updated. But after closing and reopening the bed's soil dialog, there were now *two* records: the edited original and a duplicate of the pre-edit values.

**Wrong theories**:
- `EditSoilTestCommand` was appending instead of replacing (verified by direct unit test — it correctly mutated by id).
- Race condition in the canvas refresh callback (no — the duplicate was on disk).
- The user pressed OK on the sub-dialog twice (single press confirmed).

**Key signal**: the *outer* dialog's status bar showed "Soil test recorded" after the user closed the dialog with OK. They thought OK = "save my changes", but the outer dialog's `result_record()` had already been built from the entry tab, which was populated at construction time with the *pre-edit* `existing_latest`. So `AddSoilTestCommand` appended a stale copy.

**Root cause**: [application.py:_open_soil_test_dialog](src/open_garden_planner/app/application.py) unconditionally fired `AddSoilTestCommand` on every accepted dialog, regardless of whether the entry tab actually changed.

**Fix**: Compare `result_record()` to the original `existing` field-by-field (ignoring `id` and `date`); if equal, status-bar "No changes" and skip the command. The user's OK becomes a no-op when they only used History-tab affordances.

**Lesson**: Modal dialogs that mix "view past data + edit current data" hide a state-capture trap: any sub-dialog that mutates the underlying state leaves the outer dialog showing stale form values. Either keep state-mutating actions out of the outer dialog (separate browser/editor flows) or *always* compare-before-commit on accept. Don't trust the user's OK to mean "I want to save the entry tab" if the entry tab was never touched.

---

