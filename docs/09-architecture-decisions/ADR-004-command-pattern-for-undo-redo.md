---
id: ADR-004
title: "Command Pattern for Undo/Redo"
status: "Accepted (CommandManager; see Addenda)"
legacy_anchor: adr-004-command-pattern-for-undoredo
---

# ADR-004: Command Pattern for Undo/Redo

**Status**: Accepted (CommandManager; see Addenda)
**Context**: Need robust undo/redo support for all editing operations.
**Decision**: Wrap all modifications in Command objects, managed via CommandManager (replaces original QUndoStack).
**Rationale**: Industry standard pattern. Qt provides QUndoStack. Clean separation of actions from UI.
**Consequences**: Every new editing operation requires a corresponding Command class. More code but predictable behavior.

## Addendum (2026-10-23, #559/#560 — panel commit boundaries)

The application uses its existing CommandManager, rather than QUndoStack. Species
and instance edits store deep snapshots; command merge_from applies subsequent
ticks of the same numeric gesture. editingFinished closes that gesture.
before_history_navigation flushes active editors before choosing a stack entry;
history_navigated only refreshes. This replaces discarding staged notes after undo
and prevents post-undo commands from erasing redo. An active edit is the first edit
undone. ProjectManager.before_save and document dirty guards share the flush path.
Callbacks remain registered until form teardown, so repeated save/undo cycles work.
Ordinary refresh protects each focused editor instead of skipping the whole form.

Plan undo restores the item's species/instance identity and dependent geometry;
shared custom-library updates are intentionally not rolled back. No dependency,
new persisted lock flag or file-format change. See section 8.32 and the package
integration tests.

## Addendum (2026-11-10, #827 — the way OFF the stack)

`CommandManager.discard(command)` is the sanctioned removal for a gesture
cancelled before it became a real change — an empty text annotation placed
with a click and removed again with Esc or by the click that starts the next
annotation. `undo()` is no substitute: it parks
the command on the redo stack, where a redo resurrects the item the
cancellation just removed. `discard` pops only the exact top command (LIFO
identity, refused otherwise with no mutation), never touches the redo stack,
emits `can_undo_changed` + `stack_changed` but neither `command_executed` nor
the history-navigation pair, and leaves reversing the command's effect to the
caller. `CanvasView.add_item()` returns the command it executed so the
creating tool can hand it back; the tool discards FIRST and removes the scene
item only on a `True` return, so scene and history always move together. A
refused discard leaves the blank item in the scene — an item-plus-command
pair is consistent in both directions, and `project.py` round-trips an empty
`TextItem` — while a scene without its command is exactly the #827 bug.
Section 8.2 and PF-PER-29 hold the mechanics; the two entry points onto the
stack (`execute` / `register_applied`) are unchanged.

Retained tradeoff: a click+Esc placement still marks a previously clean
project dirty and bumps `plan_revision` for a net-zero gesture, because the
click's `execute()` fires `stack_changed` before the cancellation exists and
neither `mark_dirty` nor the monotonic revision counter can be withdrawn from
`discard()` alone. Making the gesture truly net-zero is a design of its own
(defer the execute, or snapshot and reconcile dirty state + revision across
`ProjectManager` and `CanvasScene`); tracked in #909. Pinned by
`tests/unit/test_commands.py::TestCommandManagerDiscard` and
`tests/integration/test_tool_switching.py::test_escaping_an_empty_text_annotation_leaves_no_ghost_undo_entry`.

## Addendum (2026-11-14, #904/#909 — the net-zero annotation gesture)

**Status**: Shipped in v1.40.1 (PR #913); owner manual testing passed on 2026-11-14.

The tradeoff above is resolved. A placement that may still be cancelled now runs
through `CanvasView.add_cancellable_item()`, which keeps the immediate
`execute()` (every placement tool relies on it) but suppresses only the synchronous
creation and withdrawal bumps with `CanvasScene.begin_plan_change_hold()` /
`end_plan_change_hold(commit=False)`. No hold spans user input. The editor's
completion commits a kept placement as one revision; unrelated scene writes during
editing announce immediately. The revision never moves for a net-zero gesture and never
rewinds, so revision-keyed consumers (the 3D view, `SunExportGate`) keep their
monotonic contract.

The dirty flag is still latched by `stack_changed` when the command executes;
`CanvasView.discard_cancellable_placement()` restores it from the snapshot taken
before the placement only when `CommandManager.mutation_serial` proves no other
command ran and `ProjectManager.dirty_serial` proves no direct project edit
(location, soil, tasks) asked for the dirty state in the meantime. A refused
discard, an interleaved command or a direct edit therefore keeps the project
dirty. An unchanged scene `plan_revision` is also required, covering direct scene
writes (resize/add/remove/move) that do not request project dirtiness themselves.
`ProjectManager.restore_dirty()` is the one setter for that path.

The Callout tool uses the same seam (#904): Escape on a callout with no text
discards its `CreateItemCommand` and removes the item, exactly as the Text tool
does; a callout with text is committed and kept. Both editors notify their tool when
editing ends; the tool disconnects that notification before resolving its pending
pair. Save and history navigation flush inline annotation editors first. Placement
identity guards stop a stale completion from committing another placement, and a
destroyed item's completion is a no-op. `dirty_serial` counts every dirty, clean and
restore request, even when the flag stays unchanged.

Alternatives rejected: deferring the command's `execute()` until the annotation
is committed (breaks the execute-immediately contract and leaves an un-undoable
item on screen); rewinding `plan_revision` to the snapshot (an ABA value for
consumers that key on it); restoring the dirty flag unconditionally (would hide a
real change made between placement and cancellation); a hold spanning the whole
gesture (delayed unrelated revisions and could drop a canvas resize on cancellation).

No `.ogp` change and no `FILE_VERSION` bump. Pinned by
`tests/integration/test_tool_switching.py::TestEscapeReturnsToSelect::test_escaping_an_empty_text_annotation_leaves_the_plan_revision_alone`,
`...::test_a_committed_text_annotation_announces_one_plan_change`,
`...::test_a_cancelled_empty_annotation_leaves_a_clean_project_clean`,
`tests/integration/test_callout.py::TestCancel::test_escaping_an_empty_callout_withdraws_it_and_its_history_entry`
and `tests/unit/test_commands.py::TestMutationSerial`.
