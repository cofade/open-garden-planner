---
id: ADR-012
title: "Hybrid Constraint Solver (Gauss-Seidel warm-start + Newton-Raphson refinement)"
status: "Accepted (Phase 11 — issue #140)"
legacy_anchor: adr-012-hybrid-constraint-solver-gauss-seidel-warm-start--newton-raphson-refinement
---

# ADR-012: Hybrid Constraint Solver (Gauss-Seidel warm-start + Newton-Raphson refinement)

**Status**: Accepted (Phase 11 — issue #140)
**Context**: The original solver was a pure Gauss-Seidel relaxation loop. It resolves every constraint by a 1D projection along its own geometric direction. This works for decoupled systems but diverges on coupled ones — the canonical failure is two `EDGE_LENGTH` constraints sharing a vertex, where the feasible position is the intersection of two circles. Users reported that constraining edge A to 4.53 m and adjacent edge B to 5.00 m left edge A drifting to 5.21 m (both constraints geometrically satisfiable).
**Decision**: Keep Gauss-Seidel as a fast warm-start, then run damped Newton-Raphson refinement (`constraint_solver_newton.py`) when the residual exceeds tolerance. Add a closed-form circle-circle fast path for the shared-vertex case. Add `numpy` as an explicit dependency (`>=1.24`) for `linalg.lstsq`.
**Alternatives considered**:
- *Pure geometric closed-form* — would need a case per constraint-pair (O(16²)); brittle and high-maintenance.
- *scipy.optimize* — adds ~40 MB to the installer for a problem numpy solves in <20 variables.
- *Analytic Jacobian* — a nice-to-have optimization, but numerical central differences cost microseconds; deferred as TD-008.
**Consequences**: Robust behaviour for user-built CAD sketches (matches SolveSpace/Onshape expectations). +1 runtime dependency (numpy). Jacobian is numerical, not analytic — mild perf ceiling, no correctness impact. See §8.12 for the full solver architecture.

**Addendum (Audit A5, #457, 2026-10-13).** Shared presentation is an immutable,
enum-keyed registry in `ui/constraint_presentation.py`: icon, RGB color, translated
detail/tooltip/row templates and target display conversion. Panel rows consume it;
the established `ConstraintListItem` translation context is preserved. Geometry,
residuals and satisfaction evaluation remain separate. Injecting UI callbacks into
the solver or rewriting its per-type mathematics was rejected: presentation
exhaustiveness does not establish geometric equivalence. No dependency or file-format
change. Enum, independent rendering, runtime German and panel/history tests pin the
extraction. Numerical oracles assert physical residuals, feasibility, pinned state
and exact conflict IDs, rather than an arbitrary iteration count. A no-variable
Newton call must evaluate residuals before reporting convergence; incompatible
pinned anchors are not a solved system. The fresh eight-mutant sample and its test
selection are recorded in `audits/2026-10/audit-2026-10-a5-evidence.md`; historical mutmut counts
are not a current full-suite measurement.

**Addendum (CAD-precision package, #669/#670, 2026-10-31).** The incidence path had
drifted into three answers to one question, and the trial answered a different question
than the application. Six decisions, each pinned:

1. **One residual.** `constraints.incidence_error(type, a, b, c, target)` is the single
   definition of the `POINT_ON_EDGE` / `POINT_ON_CIRCLE` / `TANGENT` residual. The
   Gauss-Seidel pass, `find_conflicting_constraints` and `ConstraintsPanel._is_satisfied`
   call it; the panel previously fell through to an anchor-to-anchor distance and painted
   satisfied constraints red (#669).
2. **One tolerance pair.** `DISPLAY_TOLERANCE_CM = 0.1` is what the panel reports;
   `APPLY_TOLERANCE_CM = 0.05` is what a *committed* application solve targets
   (`validate_constraint` and `_compute_constraint_solve_moves`). Live drags keep the
   cm-scale tolerance: they run per mouse frame and a sub-millimetre chase is invisible
   while the cursor moves. A constraint the user adds therefore meets the precision the
   panel then displays (#670 cause 4).
3. **A trial joins a component, it does not re-solve the plan.** `validate_constraint`
   restricts positions, offsets, deformable items and pins to the connected component the
   trial link creates. A knowingly violated constraint in an unrelated component is not a
   reason to refuse a satisfiable one (#670 cause 1). **The application and the conflict
   scan answer the same scoped question:** `_compute_constraint_solve_moves()` (and the
   edge-length path) accept the trial's component, `find_conflicting_constraints()` scopes
   its solve and its rescan to that component, and `_constraint_reference_pins()` supplies
   the same pins to the trial, the dialog and the applied solve. The dialog's 1.0 cm
   threshold is a separate, deliberate question — "would this visibly distort an existing
   relation?" — not the application's convergence tolerance.
4. **The trial pins what the application pins.** One rule,
   `CanvasView._constraint_reference_pins`: B stays still (A moves to B) unless A
   is always pinned (construction geometry, or a FIXED constraint), or both
   anchors share a VERTEX-DEFORMABLE item (polygon/polyline). A self-constraint on
   a rigid shape pins that shape, so the solver cannot translate it; if the
   constraint is a self `EDGE_LENGTH`, the solver makes no move at all (a rigid
   edge length changes through a resize, not through the positional solver), and
   the distance dialog and the Properties resize refuse that edit with a
   translated message. It feeds the feasibility trial and every application
   surface, and `solve_anchored()` only injects a `FIXED` item that the solve
   actually contains, so an out-of-component locked pair cannot make a scoped
   trial non-convergent (#670 causes 1–2).
5. **Reconstruct resolved state from deltas, symmetrically.** `find_conflicting_constraints`
   rebuilds every vertex as `pre-solve vertex + item delta + vertex delta`. A polygon that
   translated rigidly has no vertex delta, which is exactly when the old reconstruction
   evaluated its pre-solve position (#670 cause 3).
6. **An edge reference is an index, not a direction.** `measure_snapper.resolve_anchor_point`
   (and `anchor_offset_table`) matches polygon/polyline edge anchors by `anchor_index`,
   because their `EDGE_*` type is re-derived from the current dominant axis. Dimension
   lines, drag enforcement and the solver's offset table all use it (#670 cause 6), and
   `POINT_ON_EDGE` resolves its third anchor through the same vertex-aware helper the rest
   of the solver uses (#670 cause 5).

No `.ogp` format change: FIXED targets are **re-derived on every load** from the loaded
item's own `pos()` — the shape serializers fold the Qt translation into the geometry, so a
saved target names a frame the reload no longer has; only a target captured after loading
is truthful (round-2 review). Tests: `tests/unit/test_incidence_consistency.py` (all six
causes plus the panel residual definitions and the precision pair) and
`tests/integration/test_cad_precision_integrity.py` (the real add-constraint path: an
unrelated broken component neither moves nor raises a dialog, a cross-component trial the
trial rejects is reported by the conflict scan, a locked pair at non-zero `pos()` does not
block a compatible link, a point-on-edge added through the view lands on the edge and shows
satisfied, and a lock on a MOVED item keeps its scene geometry through save → drag → save).
The four application surfaces (add, Properties resize, distance edit, vertex-drag correction)
share the component scope, and each has an integration test with an unrelated broken
component; the new-constraint surfaces also share the pin rule.

**Addendum (rigid shapes and topology, #670 review).** "Same item" does not mean "can
deform its vertices": `measure_snapper.is_vertex_deformable()` is the one predicate for
polygons/polylines. The pin rule leaves a self-constraint's item free only when it is
vertex-deformable; the solver MEASURES a self-constraint on a rigid item but never moves the
item — moving it translates both anchors, so every iteration re-applied the full correction
(measured before the fix: a 200 cm top edge edited to 400 left the edge at 200 and moved the
item to −4000 cm). The measured residual still counts towards convergence, so the trial
refuses an unsatisfiable one and the conflict dialog fires, while Newton does not receive it
(a translation-invariant residual would floor the refinement). A rigid shape's edge length
follows its size, not the solver, so the distance dialog and the Properties resize both
refuse that edit and ask the user to remove the constraint before resizing.
Vertex insert/delete renumber indexed anchors (`CORNER`, `ENDPOINT` and `EDGE_*`) through
`AddVertexCommand`/`DeleteVertexCommand`, which capture a before-state and restore it on
undo; the Agent API, GUI and undo/redo share that invariant. A corner edit also reconciles
bed membership in the same undo step (`ReconcileBedMembershipCommand`), so a plant left
outside a chamfered bed is unlinked — and relinked on undo — rather than staying attached
to geometry it no longer touches.

**Addendum (replacement identity, #668).** A command that rebuilds a shape (`inherit_item_identity()`
in `core/item_look.py`) keeps the source's UUID, name, metadata copy, parent/child links,
layer, stack rank, label flags and transform — including the stored `rotation_angle` the
serializer reads, which `setRotation()` alone does not update. Identity does not extend to
topology: a corner edit replaces one vertex with two and renumbers every later indexed
anchor (`CORNER`/`ENDPOINT` **and** `EDGE_*` midpoints), and a trim turns a closed shape
into an open line. Those edits are **refused** when the item carries any indexed anchor
(corner edits) or is a plant-parent / carries any constraint (trim), with a translated
status message, rather than silently retargeting an anchor or attaching a bed's records to
a fence.

**Addendum (2026-10-23, issue #552 — FIXED closes the panel path).** The canvas
drag, arrange and vertex paths honoured FIXED; the Properties panel X/Y fields
did not (an empty propagation set fell through to a plain `MoveItemsCommand`,
a data-integrity defect: the moved position is what a save writes). The panel
now refuses the edit when `_is_item_fixed`, restores the pinned values and
explains why. Lock/Unlock lives in the item right-click menu, backed by the
existing `AddConstraintCommand` / `RemoveConstraintCommand` with
`AnchorType.CENTER` (no second lock state, no new persisted field), and a
`ItemIgnoresTransformations` padlock badge re-derived by the scene constraint
refresh and after load, including unselected objects. PositionLockMixin shares
this behavior across shapes, paths, curves and text.

**Addendum (2026-10-30, PR #649 owner manual step 5).**
**Status:** Shipped in v1.34.9 (PR #649) after owner manual acceptance on 2026-10-30.

Creating an
inter-object PARALLEL or PERPENDICULAR relation is an automatic rotation,
so it must honor FIXED before the rotation-only command is executed.
Both tools use `_plan_edge_rotation`: existing orientation constraints form
a co-rotation group, and one FIXED member pins the group. Preserve the usual
second-object preference where possible, then try the other free group.
Never rotate one group relative to itself and thereby break an existing
orientation relation. If no group is free, refuse before graph, geometry or
history changes and explain how the user can unlock/remove a constraint.
An already satisfied relation is allowed without rotating either object.
The canonical rotation applier and AddConstraintCommand still provide the
single undo step. No persisted lock angle or new file-format field is needed.

The picked scene-space edge vectors are the correctness oracle: dot product
zero for perpendicular, cross product zero for parallel. A polygon's edge
need not align with its bounding-box axis, so comparing item rotation angles
would miss the owner's suspected wrong-edge result. The numeric reproduction
proved the FIXED violation; it did not reproduce parallel selected edges.
A later visual probe did identify a wrongly attached indicator: the resolver
used index-only matching for all shapes, but every rectangle edge has index 0.
Only polygon/polyline vertex edges use that dynamic-classification fallback;
rectangle, ellipse and circle edge anchors match their unique edge type.
The connector itself is asserted against the selected edge midpoints.
`tests/integration/test_orientation_constraint_locks.py` pins these contracts,
including the real toolbar/viewport and save/reload path.
