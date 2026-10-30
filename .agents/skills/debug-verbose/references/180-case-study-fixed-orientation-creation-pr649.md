# Case study: orientation creation rotated a FIXED rectangle (PR #649 owner pass)

**Symptom.** Owner manual step 5 selected the Perpendicular tool, then a
triangle edge and the midpoint of a locked rectangle edge. The rectangle
rotated despite its padlock. The resulting picture also appeared parallel.

**Evidence before the fix.** A tagged wrapper at the rectangle's
`_apply_rotation` recorded a FIXED item changing from 0 to -41.309932 degrees.
The caller stack was PerpendicularConstraintTool ->
CanvasView._execute_constraint_with_solve -> AddConstraintCommand.execute.
The rotation-only branch executes directly, so the FIXED position solver
never gets a chance to prevent the rotation. `has_rotation_constraint` only
means PARALLEL/PERPENDICULAR; treating it as a general rotation permission
check was the wrong assumption. The independent endpoint-vector dot product
was 8.4e-17 in this reproduction: its selected edges were perpendicular.
That does not establish which edges the owner's saved scene held.

**Fix.** Both tools use one planner. Existing orientation connections form a
co-rotation group. Any FIXED member pins the whole group. Prefer the usual
target group when free, otherwise try the other group. If neither can turn
without changing FIXED geometry or an existing relation, explain the refusal
before creating a command. Already satisfied relations need no rotation.
The payload uses the canonical apply_rotation function and one undo entry.

**Regression evidence.** The original locked-rectangle case failed before the
fix. The matrix uses actual selected-edge endpoints, not item angles, across
Parallel/Perpendicular, four rectangle edges, 15/45/215 degrees and either
locked endpoint. Other cases pin FIXED chain members, free chain propagation,
both-fixed refusal with an existing redo entry, satisfied fixed relations,
and incompatible existing orientation components. A real application toolbar
click plus viewport mouse clicks reproduces the owner's ordering and verifies
undo/redo and scene-space geometry across save/reload.

**Lesson.** A rotation-only command bypasses the positional solver's lock
checks. Permission must be decided over every object in its proposed rotation
payload. An item's stored rotation difference is not evidence that two picked
edges are perpendicular: measure those edges in scene space.
