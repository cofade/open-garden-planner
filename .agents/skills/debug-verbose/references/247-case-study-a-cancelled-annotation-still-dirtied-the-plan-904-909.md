## Case study: a cancelled annotation still dirtied the plan (#904, #909, fixed 2026-11-14)

**Symptom**: placing a text note and pressing Esc left no item and no undo entry, yet
the window title kept its unsaved marker and closing asked to save. The same code path
served the Callout tool, where Esc left the empty callout in the scene as well.

**Wrong theories**:
- `CommandManager.discard()` could withdraw the dirty flag, because it already withdraws
  the command.
- The plan revision could simply be set back to its pre-gesture value.
- The dirty flag is derivable from the undo depth, so removing the command fixes it.

**Evidence**: the old gesture, replayed against a real window with the settled seam in
place, showed every bump a net-zero gesture used to make:

```text
clean:              dirty=False rev=0
after execute:      dirty=True  rev=3   <- item add + command + stack_changed
after discard:      dirty=True  rev=4   <- discard's stack_changed
after removeItem:   dirty=True  rev=5   <- the item leaving the scene
```

**Root cause**: the placement click executes its `CreateItemCommand` immediately, so
`stack_changed` reaches `ProjectManager.mark_dirty` before a cancellation exists.
`mark_dirty` is idempotent and cannot be withdrawn from `discard()`; `plan_revision` is
bumped by four independent chokepoints, so "undo the bump" is not a single operation.

**Fix** (`CanvasView.add_cancellable_item` and `CanvasScene`'s plan-change hold): the
gesture's plan-change announcements are held while the annotation may still be
cancelled. A committed note releases one revision; a cancelled one releases none. The
dirty flag is restored from a snapshot only when `CommandManager.mutation_serial` and
`ProjectManager.dirty_serial` prove that nothing but the discard changed the document
since the placement. The Callout tool now uses the same
seam, so an empty callout leaves neither scene item nor history entry.

**Lesson**: a cancellation seam must own the *document* state, not just the scene and
the undo stack. Suppress and coalesce announcements for the gesture instead of rewinding
a monotonic counter (revision-keyed consumers would see an ABA replay), and guard any
snapshot restore with a mutation counter. Pinned by
`tests/integration/test_tool_switching.py::test_a_cancelled_empty_annotation_leaves_a_clean_project_clean`,
`tests/integration/test_callout.py::test_escaping_an_empty_callout_withdraws_it_and_its_history_entry`
and `tests/unit/test_commands.py`.
