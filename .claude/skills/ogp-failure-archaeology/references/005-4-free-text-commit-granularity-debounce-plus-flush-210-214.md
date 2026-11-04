## 4. Free-text commit granularity — debounce plus flush (#210/#214)

Source: §11.4 ("Free-text property fields commit on a debounce…").

- Symptom: typing an N-char name pushed N undo entries and (post-#209) N heavyweight
  `calendar_view.refresh()` calls.
- Rejected design: focus-out-only commit. Manual testing found why: the Edit→Undo
  QAction is disabled until `can_undo` and *shadows* the focused QLineEdit's own undo —
  with focus-out-only commit, mid-edit Ctrl+Z found an empty stack and was a silent
  no-op. The debounce (600 ms) exists so a command exists shortly after the user stops
  typing.
- Second-order trap (senior-review P1, round 2): a form rebuild (`set_selected_items`)
  destroys the field **and its child debounce timer** synchronously — an armed debounce
  at selection-change time meant the edit was live-applied to the model but never
  recorded as a command: silently lost from undo. Fix: `_pending_text_commits` +
  `_flush_pending_text_commits()` runs *before* any rebuild, while widgets are alive;
  commits are idempotent so flushing on every rebuild is safe.
- Status: closed. Pinned by `tests/integration/test_properties_text_edit_undo.py`
  (`test_debounce_commits_without_focus_out`,
  `test_pending_edit_flushed_when_selection_changes`). Any new free-text field MUST
  follow live-apply + debounce/focus-out commit + flush-queue registration.

---

