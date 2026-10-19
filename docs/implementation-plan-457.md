# Audit A5 implementation plan — issue #457

Prepared 13 October 2026 outside Plan mode, after the requested twenty-minute
release wait and `git pull --ff-only origin master`. Base: `ca92f048` (v1.30.3).
Branch: `fix/457-constraint-descriptors-solver-assertions`.
Canonical specification: [issue #457](https://github.com/cofade/open-garden-planner/issues/457).
#406 is shipped through #477; #453 and its version synchronization are merged.

## Scope and acceptance mapping

| Finding | Deliverable | Evidence required |
|---|---|---|
| AUD-012 | Inventory repeated type dispatch; one immutable presentation descriptor per `ConstraintType`, starting with constraint-panel rows | Enum drift guard, independent expected rendering for all seventeen types, English/German runtime checks, existing icon/theme tests and real panel/history workflow |
| AUD-023 | Fresh reproducible sampled mutation replay and stronger numerical assertions | Existing-test and strengthened-test outcomes per mutant; independently computed residuals, feasibility, pinned anchors, conflict identities and input/graph preservation |

Historical audit mutation counts and co-change ratios remain historical. The raw
mutmut artifacts are absent from this clone. The new sample must identify exact
source substitutions and test selections, and must not claim to reproduce the
historical population or a full-suite mutation score.

## Verified starting points

- `core/constraints.py`: seventeen enum members, `AnchorRef`, graph solver,
  `solve_anchored`, temporary validation and conflict queries.
- `core/constraint_solver_newton.py`: mutable rigid/vertex state, excluded pinned
  variables, centimetre residuals, central differences and damped least squares.
  Newton excludes FIXED/PARALLEL/PERPENDICULAR/EQUAL. Its convergence flag and
  returned residual must agree with independently measured geometry.
- `ui/panels/constraints_panel.py`: independent type-icon map, status-color
  dispatch, detail/tooltip dispatch and row-layout dispatch. The row receives
  enum names, and unknown names currently fall back to distance presentation.
  FIXED always uses its gold dot, even when the satisfaction tooltip is Violated.
  ANGLE uses degrees; distance/edge length use centimetres converted to metres;
  TANGENT displays the absolute radius. Symmetry targets are axis coordinates.
- `ConstraintsPanel._is_satisfied` has geometric/status dispatch with a separate
  responsibility. `dimension_lines.py`, creation tools and both solver passes
  also dispatch by type for geometry, not merely presentation.
- `test_iconography_3c.py` imports the panel's private icon table: migrate its
  exhaustiveness assertion to the descriptor registry, preserving real pixmap
  and theme-change checks.
- Fresh initial focused baseline: 157 tests passed (constraints, drag, tangent,
  panel and hybrid solver), 2.01 seconds on this Windows environment.

## Architecture and implementation choices

1. Add `ui/constraint_presentation.py`, with frozen descriptor values and a
   read-only enum-keyed registry. Descriptors own icon name, satisfied RGB color,
   always-colored flag, detail/tooltip/row templates and display scaling.
   A small formatter renders a descriptor using the existing `ConstraintListItem`
   translation context. Declare source templates through `QT_TR_NOOP` and
   translate at rendering time; registration alone is not evidence of localization.
2. Keep presentation in UI rather than injecting Qt translation or QColor into
   solver data. The descriptor contains no solver callbacks, state mutation,
   command factories or residual formulas. Use RGB tuples rather than shared
   mutable QColor objects. Retain the existing unknown-name distance fallback.
3. Replace panel row dispatch with registry lookup and formatting. Preserve row
   text, tooltip values, icons, theme refresh and delete signal. Do not merge the
   geometric satisfaction evaluator into the presentation descriptor.
4. Inventory all relevant production type-dispatch sites in a reproducible report.
   Explicitly distinguish presentation duplication removed here from geometry
   dispatch deliberately retained. This is a first extraction, not a solver rewrite
   or the A4/A6/A7 structural refactor.
5. Add a stdlib mutation replay script. Run in isolated temporary source overlays
   and fresh pytest processes; never mutate the development source or copy `.env`.
   Guard each exact substitution and distinguish killed, survived, timeout and
   invalid/collection errors. Save source hashes, test selection and outcomes.
   Establish unmutated controls before interpreting mutation results.
6. Select mutations around residual formulas, state writeback, pinning, anchor
   offsets, feasibility and conflict reporting. Replay the sample against the old
   relevant unit/integration/UI tests before writing the new assertions. Run the
   strengthened tests against confirmed survivors and document equivalents or
   out-of-contract mutations rather than inventing arbitrary iteration checks.
7. Keep production solver behavior unchanged unless a measured invariant exposes
   a real defect. If one appears, load debug-verbose immediately, instrument and
   reproduce, observe the regression failing before fixing, and document the
   evidence and mirrored case study. No tolerance relaxation or count-pinning.

Architecture invariants: raw scene centimetres (1); canonical pivot/geometry apply
paths (2); existing command stack and one gesture/undo step (3–4); unchanged file
format (9); UI/core dependency direction (10–11); translated display (16).

## Work sequence

1. Capture current dispatch inventory and mutation selection; run existing tests
   against unmutated controls and each isolated mutation. Commit reproducible
   evidence, not transient test logs or credentials.
2. Write descriptor tests with independent expected results for every enum value,
   immutability/exhaustiveness, unknown fallback, target units, gold FIXED and red
   violated dots. Write runtime German checks against the compiled `.qm`, including
   formatted labels/tooltips. Observe the missing descriptor contract failing first.
3. Implement the registry and panel extraction; update the existing icon guard and
   register/compile translation templates. Run focused panel/icon/i18n checks.
4. Add numerical tests covering rigid and deformable solves, asymmetric nonzero
   anchor offsets, both signs of distance axes, symmetry axes, coupled constraints,
   attainable/incompatible systems and unchanged pinned state. Compute expected
   geometry independently of the solver's return flags.
5. Directly exercise `validate_constraint`, `project_to_feasible` and
   `find_conflicting_constraints`, asserting actual returned IDs and exact graph,
   adjacency and input preservation after compatible/incompatible/exception paths.
   Assert physical error relative to requested centimetre tolerance; never assert
   an arbitrary iteration count.
6. Add a real CanvasView/tool/panel integration workflow: create a constraint via
   gestures, verify row text and tooltip, select/delete through panel signals, and
   undo/redo while preserving graph IDs and a single history operation per action.
   Reuse existing fixtures and canonical command paths.
7. Replay mutations against the strengthened selection, then run full quality gates.
8. Update docs, commit, create a fresh review worktree, run independent
   senior-reviewer; resolve all P0/P1 and repeat review after fixes. Re-run the gate
   battery after review changes. Push and open one draft PR against master with
   `Closes #457`; wait for all CI checks and verify draft/base/closing references.

## Documentation deliverables

- This plan and a fresh A5 evidence report beside the audit reconciliation.
- ADR-012 addendum: immutable presentation descriptors separated from geometry,
  independent numerical assertions and honest sampled mutation scope.
- Building-block description for the presentation module and §8.10/§8.12 test and
  presentation contracts. Runtime sequence changes only if behavior changes.
- Living debt register/reconciliation and roadmap: implemented pending owner
  acceptance; preserve the dated audit snapshot and keep epic #392 open.
- Synchronized AGENTS.md/CLAUDE.md progress note, mirrored skill updates only where
  their factual claims change; validate citations and offline wiki sources.

## Gate and handoff checklist

- Focused checks after each meaningful change, then `pytest tests/ -v` in one run.
- `ruff check src/ tests/ scripts/`, HIGH Bandit, full i18n/interpolation gates.
- Dependency lock/export, secrets, strict mypy per-file baseline, agent-context
  parity, skill citations and offline wiki validation. Linux coverage floors through
  CI; report actual per-layer counts and any local timing caveats honestly.
- Frozen PyInstaller build with controlled PATH to avoid the known Poppler/ICU
  contamination, detached `Start-Process --selftest` (exit 0) and eight-second
  startup smoke (124). Verify the affected real widgets and translated presentation.
- Independent review has no outstanding P0/P1; all required GitHub checks green.
- Owner-only remainder: visible row/icon/color/theme/layout readability in both
  languages and real mouse-driven constrained movement/conflict dialog behavior.
  Give exact reachable steps and expected observations from the verified artifact.

The original planning task stopped at a reviewed draft PR ready for owner manual
acceptance. Owner acceptance and the subsequent `finalize-us` invocation on
14 October 2026 authorized protected merge, automatic version synchronization
and wiki publication. See the roadmap delivery record. Tags remain CI-owned.
