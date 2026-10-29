## 5. Snap engine + constraint solver theory

### Snap pipeline (ADR-020/023, §8.16)

`core/snap/` is a pure orchestration layer over existing geometry helpers
(`measure_snapper.get_anchor_points`, `core/snap/geometry.item_edges`) — it
owns no point enumeration of its own. Architecture:

- **Provider registry**: each `SnapProvider` owns one mode and a `priority`;
  the registry picks the lowest priority, then distance. Verified priorities:
  endpoint **10** < intersection **15** < center **20** < perpendicular **25**
  < tangent **26** < midpoint **30** < edge **40** < nearest **45** (`core/
  snap/providers/*.py`). Two candidates within sub-pixel distance are common
  (a corner is also two edge endpoints) — priority, not distance, breaks it.
- **QuadTree** (`core/snap/spatial_index.py`): bounded depth 6; items spanning
  multiple quadrants are inserted into *every* overlapping child, deduped at
  query time via an `id()` set. Rebuilt **lazily** by
  `CanvasView._ensure_snap_index()` on the first query after `scene.changed`
  — never eagerly per signal (~3 ms build at 1000 items would dominate).
- `PointSnapper.snap()` widens the query window to 4× the threshold so
  intersections of edges starting outside the cursor area still surface;
  the O(n²) intersection step is capped at `MAX_SEGMENTS_PER_QUERY = 60`.
- **Reference-point providers** (ADR-023): perpendicular and tangent are not
  functions of cursor+scene alone — they need the active tool's `last_point`,
  passed as the optional `reference_point` kwarg through
  `SnapRegistry`/`PointSnapper` (providers stay pure functions; no provider
  reaches into the view).
- Integration rule: `CanvasView._maybe_apply_anchor_snap` is the single
  dispatcher; anchor snap beats grid snap because `snap_point()`
  short-circuits grid rounding when a point-snap matched. Tools opt out via
  `BaseTool.skip_anchor_snap = True`. Each snap kind must also get a glyph in
  `_draw_point_snap_glyph` (square=endpoint, circle=center, triangle=midpoint,
  X=intersection, dot=edge, hourglass=nearest, ⊥=perpendicular).

### Constraint solver (ADR-012, §8.12)

`core/constraints.py` + `core/constraint_solver_newton.py`; **17** constraint
types (`ConstraintType` in `core/constraints.py` — TANGENT was added by ADR-024;
docs/08 §8.12's "16 types" line and its §8.12.8 residual table are stale on this
count); **two-phase solve** in every `solve_anchored`:

1. **Gauss-Seidel warm start** — each constraint resolved by a 1-D projection
   along its own direction. Cheap; converges when constraints don't couple.
   Cap: 20 iterations.
2. **Newton-Raphson refinement** — only when the warm-start residual exceeds
   tolerance. Stacks all non-orientation constraints into a residual vector
   `F(x)`; damped Newton on `J·Δx = −F` with a *numerical* central-difference
   Jacobian (`h = 1e-3 cm`), `numpy.linalg.lstsq` (rank-deficient →
   minimum-norm step), Armijo backtracking (α halves, accept only strict
   `max|F|` decrease). Caps: 25 Newton iterations, 15 backtracks.

Why two phases: Gauss-Seidel alone cannot solve coupled systems — canonical
case: two `EDGE_LENGTH` constraints sharing a vertex; the feasible point is a
two-circle intersection unreachable by alternating 1-D projections. For that
exact case a **geometric fast path** exists: `two_circle_intersection()`
(closed form; returns the root nearest the current vertex, `None` → fall back
to Newton).

Convergence: `max|F| ≤ tolerance`; default **0.1 cm**, relaxed to **1.0 cm**
for drag-time solves. The per-type residual formulas (all scaled to cm) are
tabulated in §8.12.8 of `docs/08-crosscutting-concepts/README.md` — read them
there before adding a type. Which types Newton skips vs which permit resize are
two *different* sets — don't conflate them:
- **Newton skips `PARALLEL`, `PERPENDICULAR`, `EQUAL`, `FIXED`** (warm-start-only,
  `constraint_solver_newton.py` ~lines 128–140). `HORIZONTAL` and `VERTICAL` DO
  get Newton residuals (`ay − by` / `ax − bx`, ~lines 193–196) — a solver
  investigator told "Newton skips HORIZONTAL" would look in the wrong phase.
- **The resize-permitting set is the five *scale-invariant* orientation types
  `HORIZONTAL`, `VERTICAL`, `PARALLEL`, `PERPENDICULAR`, `EQUAL`** (any other,
  including `FIXED`, blocks resize) — `_has_blocking_constraints` in
  `ui/canvas/items/resize_handle.py` ~line 246.

**The sub-pixel tolerance lesson (PR #169, §11.4)**: live-drag projection
(`ConstraintGraph.project_to_feasible`) must use `tolerance=1e-4`, not a
cm-scale tolerance. `newton_refine` early-returns when `max_err <= tol`, and
the iteration *starts* from the raw cursor position — with 0.5 cm slack the
cursor near a feasible point returns **unchanged** frame after frame, letting
a "fully constrained" vertex slip up to the slack band per frame (looks like
the whole rigid polyline translating). Full-graph solves keep cm tolerances;
only the per-frame projection needs sub-render precision.

Conflict detection on add: the view trial-runs the solver
(`find_conflicting_constraints`); existing constraints with post-solve
residual > 1.0 cm trigger the Override/Cancel dialog instead of silently
distorting geometry.

---

