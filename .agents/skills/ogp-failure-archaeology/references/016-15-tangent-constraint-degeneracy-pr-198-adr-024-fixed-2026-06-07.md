## 15. Tangent-constraint degeneracy (PR #198, ADR-024, fixed 2026-06-07)

Source: debug-verbose case study "tangent constraint flips…", ADR-024.

- Symptom evolution across four fix attempts: v1 line stalls radial ("stable but
  wrong") → v2 (signed residual) flips to the opposite side on a large drag → v3
  (continuity warm-start) tangency drifts off → v4 (drop POINT_ON_CIRCLE) tangent holds
  but the contact slides along the line. Each fix traded one face of the same bug.
- Wrong theories, all disproved by instrumentation: inverted sign (the `[TANGENT]` emit
  log showed sign correct at creation); creation-time solve flipping it (no-op at the
  snapped point); coordinate-space mismatch (both scene coords).
- Evidence: per-frame `[TANGENT]` log showed `signed_dist` sliding `+320 → 0 → −320` —
  a clean trajectory *through the centre*, not a one-shot sign error. Reproduced headless
  only after matching the user's exact drag magnitude+direction from the log.
- Root cause: tangency expressed as "perpendicular distance centre→line = ±radius" has a
  gradient (line-normal) **parallel** to POINT_ON_CIRCLE's radial gradient at the tangent
  configuration → rank-deficient Jacobian → drift/stall/flip. v1–v3 were all faces of
  this one ill-conditioning.
- Fix: re-express `TANGENT` as "edge ⟂ radius at the contact" (residual
  `(C−v1)·(v0−v1)/|edge|`), whose gradient is *orthogonal* to the radial one — emit it
  WITH POINT_ON_CIRCLE for a full-rank pair; keep the continuity warm-start (the contact
  still has two antipodal solutions).
- Lessons: residual *formulation* decides conditioning, not the geometry you mean; two
  constraints with parallel gradients at the solution are rank-deficient no matter the
  warm-start; multi-solution constraints need continuous warm-starting; when a GUI bug
  won't reproduce headless, extract the exact user coordinates from instrumentation and
  drive the exact live code path.
- Status: closed. Pinned by `tests/unit/test_constraint_tangent_math.py`. Related §11.4
  entry: live-drag projection tolerance must be sub-pixel (`tolerance=1e-4` in
  `project_to_feasible` — cm-scale tolerance let the vertex slip with the cursor).

---

