## Case study: layer deletion redo bypassed a lock added after undo (D2.4, fixed 2026-09-07)

**Symptom**: Senior review found that deleting a layer, undoing it, locking the replacement layer, and redoing could still delete the source layer and move its items onto the now-locked replacement.

**Wrong theories**: The GUI preflight and `CanvasScene.remove_layer()` guard appeared to cover the transition, and the initial command constructor check made direct execution tests pass. The missed path was command-manager redo, which re-executes an already-constructed command.

**Key evidence**: `CommandManager.redo()` popped the command before calling `execute()`, while `DeleteLayerCommand` checked `replacement.locked` only in `__init__`. The redo path therefore had neither a current precondition check nor a recoverable redo-stack entry.

**Root cause**: A mutable layer lock was treated as a construction-time invariant instead of a mutation-time precondition; redo is a second mutation entry point.

**Fix**: Revalidate the replacement lock at the start of `DeleteLayerCommand.execute()`, restore a command to the redo stack when redo execution raises, and add an undo → lock → redo regression test.

**Lesson**: Every undoable command must enforce mutable preconditions immediately before mutation, including redo. Test the state-changing interleavings explicitly, not only initial command construction.

