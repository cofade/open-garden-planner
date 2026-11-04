## Case study: stale-row semantics do not mean exact search selection (#315)

**Symptom.** Searching for no matches left previous canvas objects selected.
**Wrong theory.** The click-by-UUID helper was assumed suitable for bulk highlights.
**Evidence.** Review traced its explicit "no resolved ids: preserve selection" branch;
the new zero-match Search and Select All regressions fail against that implementation.
**Root cause.** A stale click preserves selection, while a search replaces it exactly.
**Fix.** Bulk highlighting resolves live click targets once and uses replace_selection,
which clears an empty result, avoiding repeated full-scene UUID walks.
**Lesson.** Reuse the helper whose contract matches the operation, not its name.
Pinned by tests/integration/test_find_replace.py::test_no_matches_clear_previous_canvas_selection.

