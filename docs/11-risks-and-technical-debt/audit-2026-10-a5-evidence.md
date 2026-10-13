# Audit A5 evidence — #457 (AUD-012, AUD-023)

13 October 2026. Base `ca92f048` (v1.30.3); implementation awaits owner acceptance.
See [the implementation plan](../implementation-plan-457.md) and ADR-012 addendum.
The dated audit snapshot is unchanged. This report measures a new, explicitly scoped
sample; it does not reproduce the historical mutmut population or co-change ratios.

## Dispatch inventory and extraction

The AST inventory is reproducible with:

```powershell
venv/Scripts/python.exe scripts/replay_constraint_mutations.py --inventory-only --output "$env:TEMP/a5-dispatch.json"
```

[Recorded inventory](audit-2026-10-a5-dispatch.json) lists each current function,
path, source line and count of if conditions containing a ConstraintType reference
or enum-name string. Nested functions are counted independently. This is a source
inventory, not a complexity or co-change metric. The panel row's `_setup_ui` had
27 if statements at the base revision; after extraction it has zero. AST-count
all If nodes in ConstraintListItem._setup_ui on the base/current source to reproduce
that specific before/after number.

| Site | Responsibility and A5 disposition |
|---|---|
| `ConstraintListItem._setup_ui` | Icon/color/detail/tooltip/layout dispatch replaced by one immutable descriptor for each of 17 enum members |
| `ConstraintsPanel._is_satisfied` | Geometric evaluation retained; not presentation data |
| `DimensionLineManager._update_constraint`, `get_constraint_at` | Annotation geometry and picking retained |
| `ConstraintGraph.solve`, `solve_anchored`, `find_conflicting_constraints`; Newton residual evaluation | Mathematical dispatch retained |
| `constraint_tool.py`, `canvas_view.py`, `resize_handle.py` | Creation, conflict labels, drag/resize capability and command orchestration retained |

The canonical UI registry owns RGB tuples, icon names, translatable row/detail/
tooltip templates and target conversion. Existing `ConstraintListItem` context,
unknown-name distance fallback, always-gold FIXED dot, tangent absolute radius,
angle degrees and metre precision are preserved. Enum coverage and independent
English expected results cover every type. Compiled German translator checks
exercise actual formatted widget text. Existing theme/icon tests still pass.

## Reproducible sampled mutation comparison

```powershell
venv/Scripts/python.exe scripts/replay_constraint_mutations.py --selection baseline --source-ref ca92f048 --timeout 45 --output "$env:TEMP/a5-baseline.json"
venv/Scripts/python.exe scripts/replay_constraint_mutations.py --selection strengthened --timeout 45 --output "$env:TEMP/a5-strengthened.json"
```

The baseline uses both solver modules from the base revision and excludes new A5
tests. The selection includes all constraint-named files plus direct consumers of
ConstraintType/ConstraintGraph/Newton/feasibility/conflict/projection across unit,
integration and UI tests. It is **not** every transitive GUI consumer or the full
suite. The recorded selections/hashes/exact substitutions are in
[baseline](audit-2026-10-a5-mutations-baseline.json) and
[strengthened](audit-2026-10-a5-mutations-strengthened.json).

Each unmutated control passed: **432 tests across 28 files** before A5; **501 tests
across 32 files** after A5. Mutants use temporary import overlays and fresh pytest
processes, stopping at the first assertion failure. Working source and `.env` are
never copied/overwritten. A source substitution must occur exactly once and compile.
Non-test exits/collection failures are invalid; timeouts are separate evidence.

| Explicit mutation | Existing relevant tests | Strengthened tests |
|---|---|---|
| Newton horizontal symmetry: remove factor two from axis | survived | killed by horizontal symmetry geometry |
| Newton vertical symmetry: remove factor two from axis | survived | killed by vertical symmetry geometry |
| Newton pinned anchor: subtract Y offset | killed | killed by nonzero offset geometry |
| Newton final reported residual forced to zero | timeout (45 seconds; unresolved baseline outcome) | killed by actual infeasible residual |
| Newton final state writeback omitted | killed | killed by resulting symmetry geometry |
| Anchored solver ignores supplied pins | killed | killed by pinned offset geometry |
| Anchored solver subtracts Y offset | killed | killed by nonzero offset geometry |
| Conflict query drops returned identities | killed | killed by exact conflicting ID assertion |

Thus two **confirmed survivors** are eliminated; all eight strengthened executions
fail assertions. The five baseline kills were already covered by the wider relevant
selection. The baseline timeout is neither a survivor nor a killed mutant. No
population mutation score is inferred. No iteration counts, damping constants or
tolerance relaxation are pinned by these tests.

## Measured real defect and remediation

Two pinned anchors at (0,0) and (100,0), with target distance 200 cm, must have
100 cm residual, zero motion and infeasible status. Before the fix the graph
returned `converged=True`, `max_error=0.0`, empty deltas. Both direct-Newton and
graph regression tests failed before modification.

Temporary `[A5-NEWTON]` prints and `traceback.format_stack()` recorded no free
variable slots and the call from `solve_anchored` into the early return. Newton
returned success before computing any residual; the graph then replaced its real
warm-start error with the minimum of that error and zero. Move the no-variable
return after residual evaluation. The same inputs now return infeasible/100 cm
with unchanged pins and inputs. Instrumentation was removed. Mirrored debug-verbose
case studies record the evidence; §11.4 records the general rule.

The real CanvasView feasibility adapter now rejects an incompatible trial between
FIXED items while preserving scene geometry, graph and history. A real registered
45-degree distance gesture, panel row selection/deletion and undo/redo are covered
through GardenPlannerApp wiring. The existing command/serialization paths remain.

## Gate and artifact evidence

### Owner localization finding

Owner checks 1 (theme/readability) and 3 (fixed incompatible target rejection)
passed. Check 2 exposed an unnamed rectangle displayed as `Rectangle` in German.
Tagged tracing showed `[A5-LABEL] GENERIC_RECTANGLE row= Rectangle canonical=
Rechteck`, with the caller stack through command-history refresh. The compiled
translation existed; the object-label builder bypassed it. Direct descriptor
tests supplied `A`/`B` and could not detect this upstream omission.

Use the shared `get_translated_display_name` for all unnamed constraint endpoints
and previous-season compare plants. An exhaustive catalog check covers all 52
object types and found two absent entries, `Hedge`/`Roof Ridge`, now registered as
`Hecke`/`Dachfirst`. Preserve explicit names and stored object data; duplicate
numbering operates on the translated labels. Four regressions failed before
correction: exhaustive object labels, duplicates/explicit names, the real German
distance gesture row/tooltip and all three compare-overlay plant types. Focused
verification: 74 passed. Temporary instrumentation removed. German owner retest
remains pending; the PR stays draft.

The follow-up full gate also exposed an existing host-hour assumption in
`test_sun_mismatch.py`: starting at 23:49 and adding an hour crossed the plan date,
so the heatmap correctly became `absent` rather than the expected `ready`.
An isolated run reproduced the failure, and tagged datetime/caller tracing
confirmed the midnight crossing. The fixture now sets noon explicitly, preserving
the production clock/cache contracts and all worker assertions/timeouts. The full
gate must be repeated after this test-only correction.

First independent review found an additional old icon-table import in the icon-file
sweep, a formatting-boundary difference from multiplication by 0.01, and an incomplete
control-timeout reporting path. All were corrected. Six boundary regressions failed
first; division by 100.0 retains the prior 17.5/20.5 cm display values. The runner's
timeout path is pinned by a focused CLI test. Final focused run: 226 tests passed,
plus the timeout test. An English/German all-type widget board was rendered and
visually inspected, with readable labels, correct icons and status dots.

Final reviewed source `cda81961`: Windows full suite **8313 passed, 37 skipped**
in 910.54 seconds, no failures. Independent fresh-worktree re-review passed 191
tests with no findings. Ruff, HIGH Bandit (0), lock/export, Windows type baseline
(0 regressions), i18n/interpolation (35), parity, citations, secrets and wiki pass.
Controlled-PATH clean frozen build passes detached self-test (0) and eight-second
startup (124 equivalent). A registered Fixed/Fixed/Distance gesture emitted the
conflict warning and preserved scene/graph/history. Final Linux coverage and
cross-platform CI results must be checked on the draft PR's current head. See the roadmap receipt.
Owner manual acceptance and wiki publication
remain pending. Epic #392 remains open; A4/A6/A7 structural extraction and #485's
rotation/constraint interaction are outside this package.
