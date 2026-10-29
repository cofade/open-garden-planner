## Case study: panel commit boundaries erased redo or lost notes (PR #566, 2026-10-23)

**Symptom.** Immediate Save/Close omitted notes; pending Properties Name erased
redo after Undo; revisiting a spinbox merged two completed edits; unselected
lock badges survived unlock. Ordinary focused updates froze unrelated fields.
**Wrong theories.** A timer/selection flush was assumed to cover persistence;
widget identity was assumed to define a numeric gesture. No other theory was
adopted before reproducing the boundaries.
**Evidence.** Eight real-widget regressions failed first. External tagged
instrumentation printed `[566-EDIT] _on_name_commit` with traceback.format_stack
through set_selected_items -> _flush_pending_text_commits after undo. Spin depth
was 1 instead of 2; a clean document's discard check returned True after notes.
**Root cause.** Commit timing depended on incidental refresh/selection, and badge
derivation depended on a selected Properties item rather than the constraint scene.
**Fix.** Flush before history selection, save and dirty guards; never during the
post-navigation refresh. End numeric gestures on editingFinished, refresh unrelated
fields in place and derive every lock badge from scene constraint refresh. The
regressions also cover all object-menu families and real tool-created locks.
Further dimension tests caught the legacy current_diameter_cm alias and the
initially uncentered circle pivot after reload; both now preserve the width contract.
**Lesson.** Test editor boundaries and scene state without selection. A green
private-handler test does not establish save, focus, or history behavior. The
temporary profile probe and its stack output remain outside production.

The next review exposed two actual focus boundaries: Qt can report the spinbox
itself instead of its inner line editor, and an old QTextCursor changes when its
document is replaced. Normalize both focus shapes and preserve numeric cursor
offsets. An unchanged online species must also return before library conversion:
otherwise a focus flush creates a custom entry and Undo repeatedly undoes that
phantom edit. Compare editable form values before changing species identity.
Real focused-spin, notes-caret, online no-op and nested-snapshot regressions pin
these paths in the same package integration file.

