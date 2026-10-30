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

**Review round (independent senior review, 2026-10-29).** The first pass missed
three things a reader of the gesture would not: (1) a rotation's partner can be a
PLANT (the solver moves it out of its bed — its link must be re-decided) or a BED
(its plants must travel with it, live, not at release); (2) object snapping and
canvas clamping still ran during rotation and could translate the selected
partner from the second mouse-move, moving the pivot with no undo entry; (3) the
view's swallowed-release safety net cleared the propagation tracking before it
registered the rotation, losing the partner corrections it exists to preserve.
All three are fixed and pinned: partner-plant and partner-bed cases in
`test_constrained_rotation.py`, a real swallowed-release test with a partner, and
snap/clamp skipped while `_rotating_item` is set. Vertex-level solver corrections
to a deformable partner are now recorded in the same command too.

**Review round 4 (2026-10-30).** Tagged viewport probes found two more omissions.
`[CARRY] plant after FIXED=(0,0), after carry=(17.279739,-2.277910)`
with a caller stack at `drag_constraints` showed that post-solve bed carrying
undid FIXED enforcement. An independently solved plant needed delta
`(44.135146,9.686515)`, but was overwritten by the same bed delta, leaving
its 608.276253 cm relation at 579.510675 cm. The solver was not the cause:
the later implicit carry was. The shared `bed_child_has_constraints` guard
now preserves constrained children in the live and command carry paths.
Membership still follows the resulting geometry.

A second trace showed `[ROTATE] initial=0 current=0 vertices_changed=True
registered=False`: a 0 ? 60 ? 0 degree drag left polygon vertices displaced
by 3.19 cm but the angle-only early return skipped history. Registration now
collects partner changes before deciding whether the gesture is a no-op.
Partner-only changes have one undo entry; a click with no changes has none.
Both regressions failed before the fix in `test_constrained_rotation.py`;
FIXED command-carry cases also cover `test_bed_membership_reconciliation.py`.
The lesson is to inspect the complete gesture payload both before declaring
it unchanged and before adding implicit movement after a constraint solve.

**Review round 5.** Direct bed drag still re-added a FIXED child at release:
`[DRAG] before release child=(0,0); after release child=(200,0)`.
The release collector and older keyboard expansion had bypassed the
new command guard by presenting inherited moves as explicit moves. They now
use the same eligibility predicate. The agent keeps its established stricter
preflight: it considers every child and refuses the entire bed move if any
child is constrained. A full-suite regression exposed that filtering the
agent payload first would silently relax this refusal contract; that change
was removed. The full-application regression parametrises nudge/drag/agent
over FIXED and independent DISTANCE child constraints. It checks GUI
one-step undo/redo and verifies that agent refusal changes neither geometry
nor history.

**Integration with merged PR #650.** The touch recognizer finalizes an active
handle when a second finger starts a pinch. Its ordinary-drag cleanup cleared
`_constraint_propagated_starts` before that release: tagged trace
`[TOUCH-ROT] tracked=1 -> 0`, then undo left the partner at
`(817.279739,297.722090)` instead of `(800,300)`. Preserve rotation partner
snapshots until the synthetic release records them, then clear them. The
regression drives both GestureStarted and adoption after a lost start through
the real event filter, and pins one-step undo/redo and cleared gesture state.
