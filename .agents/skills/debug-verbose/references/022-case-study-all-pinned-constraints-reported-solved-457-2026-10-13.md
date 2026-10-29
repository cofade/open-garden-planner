## Case study: all-pinned constraints reported solved (#457, 2026-10-13)

**Symptom.** Two pinned anchors 100 cm apart with a 200 cm target returned
converged=True and max_error=0.0. Direct Newton and graph regressions failed first.
**Wrong theories.** No theory adopted before tracing; pin mutation was ruled out
by unchanged positions/deltas. The historical mutation score did not prove this bug.
**Evidence.** `[A5-NEWTON] no free slots ... positions ...[0,0]...[100,0]...
constraints [('DISTANCE', 200)]`; `traceback.format_stack()` showed the call from
ConstraintGraph.solve_anchored into Newton's no-variable early return.
**Root cause.** Newton returned success before evaluating residuals. The graph
replaced its real warm-start error with the minimum of that error and zero.
**Fix.** Evaluate residuals before the no-variable return. Preserve pinned geometry
and report actual feasibility/error. No damping, tolerance or iteration changes.
Pinned by `tests/unit/test_constraint_solver_invariants.py` and
`tests/integration/test_constraint_presentation_workflow.py`. Remove trace prints.
**Lesson.** An empty set of movable variables establishes immobility, not feasibility;
assert independently measured residuals and pinned state, not just convergence flags.

