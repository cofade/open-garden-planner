# Case study: a rotation was exempt from the constraint solver (#485)

**Symptom.** Rotate a triangle on a corner-to-corner DISTANCE constraint to a
rectangle. The green handle turns the triangle, the partner rectangle does not
move, the dimension turns red and stays red after release and deselection. A
later 1 cm nudge makes the partner jump into place and the dimension turn blue;
undoing that nudge restores the red state. The owner also reported that the
next Ctrl+Z removed the constraint instead of undoing the rotation.

**Wrong theories (all of them plausible, all of them wrong).**

- *The solver cannot handle a rotated item's anchors.* It handles them: the
  probe fed the solver the rotated anchor offsets and it moved the partner
  correctly when called.
- *The dimension line is stale.* `update_dimension_lines` ran on every move and
  on `stack_changed`; it was reporting the truth.
- *`RotateItemCommand` is not registered, hence the "skipped undo".* It IS
  registered — the probe's release trace ended in
  `CommandManager.register_applied(RotateItemCommand)`, and the undo stack held
  exactly one step. The skipped-undo report was **not reproduced** in the
  isolated probe; it remains unexplained and the fix does not claim otherwise.
  A view-level safety net now covers the shape of it (see below).

**What the instrumentation showed.** Debug Verbose wrappers on
`CanvasView.mousePressEvent/mouseMoveEvent/mouseReleaseEvent`,
`DragConstraints._propagate_constraints_during_drag`,
`PolygonItem._on_rotation_end` and `CommandManager.register_applied`, driven by
real QTest viewport events with snapping off:

```
[ROT] press handle parent=PolygonItem
[MOVE] dragging RotationHandle -> propagate SKIPPED by isinstance check
[ROT] release -> register_applied RotateItemCommand angle 0.0 -> 74.9
[UNDO] stack = [AddConstraintCommand, RotateItemCommand]
```

The key line was the second one. The skip was a deliberate one-line guard in
`mouseMoveEvent` — *"Skip during rotation — constraint solving doesn't apply
while rotating"* — and the release path had no correction phase at all
(`_finalize_drag_move` trusted the last command and returned).

**Root cause.** Two independent omissions with one shape: the gesture was not
treated as a constraint-changing edit.

1. The live solver was skipped for `RotationHandle` drags, although a rotation
   moves anchor points exactly like a translation does.
2. `RotateItemCommand` stored angles only, so even a solver correction applied
   live at release could not be part of the undo entry.

**Fix.** Run the solver during the gesture with only the turned item pinned;
record each corrected item's before/after position; put them into the same
`RotateItemCommand`. One rotation = one undo entry that restores the angle and
every partner. FIXED keeps its established meaning (the relation reads red when
the partner cannot move), and the inter-object PARALLEL/PERPENDICULAR refusal
is unchanged. `register_rotation_command` is now the single release path for
all five item classes, and a view-level safety net registers a rotation whose
release never reaches the handle.

**Lesson.** A guard that says "this gesture cannot change X" is a product
decision, not an optimisation — and if it is wrong, the bug hides until an
unrelated action makes the state look correct. Ask what the gesture changes
(anchor positions), not what the handler is called (rotate), and record the
corrections in the command that owns the gesture.
