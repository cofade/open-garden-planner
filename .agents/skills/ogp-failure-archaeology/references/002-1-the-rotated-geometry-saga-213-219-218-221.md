## 1. The rotated-geometry saga (#213 → #219 → #218/#221)

Three issues, four PRs (#217, #220, #221), one underlying theme: OGP serializes a circle
as `pos + rect.center()` with rotation as a separate angle pivoting on the centre, so the
whole codebase silently relies on `transformOriginPoint == rect().center()`. Every
chapter below is a different way that invariant got broken. Source: §11.4 (the #213
follow-up block, "Closed (#219)", "Closed (#218)"), ADR-028, debug-verbose case study
"rotated circle drag-resize" (2026-06-17), CLAUDE.md Phase-12-issue-work table.

**Chapter 1 — #213: assigning a species visibly changes nothing.**
- Symptom: assigning a DB species to an existing generic plant didn't visibly resize it.
- Dead end: first cut refreshed only the dashed *spacing ring* — which paints only when
  the item is selected AND `spacing_r > footprint_radius`. A 5 m placeholder given a
  1.5 m shrub shows no ring at all, so "nothing changed on screen".
- Root cause: the visible artefact the user expects to change is the *footprint circle*,
  not the (often hidden) ring. Also: several panel paths wrote
  `metadata["plant_species"]` directly — no `prepareGeometryChange()`/`update()`, no
  repaint, and a manual `spacing_radius_cm` override silently masks the DB value.
- Fix: `ApplySpeciesCommand` (single undoable step) sets metadata AND resizes the drawn
  footprint to `max_spread_cm` via `CircleItem.set_radius_centered()`. Resize is silent;
  only a *conflicting* manual override prompts (Apply/Keep).
- Second trap (senior-review P0, round 2): the resize kept the *visual* centre fixed but
  not `transformOriginPoint` — a **rotated** plant saved a displaced `pos+center` (drift
  on reload, jump on next rotation). Looks correct on screen; an unrotated test passes
  green. `set_radius_centered()` now re-pins the origin.
- Status: closed. Pinned by
  `tests/integration/test_apply_database_species.py::test_apply_keeps_rotated_plant_centered`.

**Chapter 2 — #219: rotated badged plant drifts on save/reload with NO resize involved.**
- Symptom: rotate a plant that shows the antagonist-warning badge, save, reload → drift.
- Root cause: `RotationHandleMixin._apply_rotation` pivoted on `boundingRect().center()`.
  The badge expands `boundingRect()` *asymmetrically* (+x/+y overflow only), so the pivot
  drifted off `rect().center()`. `_antagonist_warning` is runtime-only (never
  serialized), so the save-time pivot (badge on) disagreed with the load-time pivot
  (badge off).
- Fix: pivot about `rect().center()` when the item exposes `rect()`
  (Circle/Rectangle/Ellipse); `boundingRect().center()` only for items with no
  asymmetric decoration (Text/Callout/Polyline). Pivot is now invariant to badge state.
- Lesson: a rotation pivot must come from the *geometric* shape, never the
  decoration-expanded `boundingRect()` — runtime-only decorations otherwise leak into
  persisted geometry.
- Status: closed. Pinned by
  `tests/integration/test_apply_database_species.py::test_rotation_pivots_about_rect_center_with_badge`.

**Chapter 3 — #218/#221: drag-resizing a 45°-rotated circle collapses / drifts / ghosts.**
- Symptom (PR #221 manual test): diagonal corner drag barely changed the diameter or
  collapsed it; centre drifted across the canvas; the dragged handle didn't track the
  cursor; a translucent "ghost" disc lingered.
- Wrong theories: "the #218 re-anchor band-aid is wrong" (it correctly held the
  serialization invariant — the rot was *underneath* it); "the spacing ring should scale
  with the footprint" (no — decoupling is the intended model); "missing
  `prepareGeometryChange` is the whole bug" (only explained the ghost).
- Evidence (the decisive observation): a scripted headless drive of the real
  `ResizeHandle._apply_resize` with cumulative deltas, printing
  rect/radius/pos/origin/visualCenter per step — a `BOTTOM_RIGHT` drag of (80,80) left
  **radius stuck at 50.00**. At exactly 45° a screen-diagonal drag projects entirely onto
  ONE local axis (`local_dy ≈ 0`), so `min(width, height)` picked the *unchanged* axis.
- Root cause, three compounding faults: (1) `min(w,h)` squaring is incoherent once
  `w ≠ h` under rotation; (2) two *disagreeing* inferences of the fixed edge —
  scene-space `abs(pos_x − init_pos.x()) < 0.01` in the item vs rotated-local
  `pos_dx == 0` in the re-anchor — pinned the wrong corner → drift; (3) no
  `prepareGeometryChange()` on shrink → ghost.
- Fix: replace the step, don't patch it. `ResizeHandle._apply_resize` takes the fixed
  corner/edge **authoritatively from the handle position**; the item normalises the rect
  (`_constrain_resize_size` squares it so the handle tracks the cursor); everything goes
  through one primitive `resize_rect_item_keeping_anchor` (does
  `prepareGeometryChange()` + origin re-pin). The rotation-gated `_reanchor` band-aid was
  deleted.
- LESSON (verbatim from §11.4, the saga's headline): **don't post-correct an incoherent
  geometry step — fix the step.** A re-anchor layered over `min(w,h)` + dual fixed-corner
  inference can never be right; the senior review flagged this fragility before it shipped.
- Status: closed. Pinned by `tests/integration/test_rotation_aware_resize.py`
  ({Circle,Rect,Ellipse} × {0°,45°,215°} × {corner,edge}). Sizing precedence now has one
  home: `core/plant_sizing.py` (pinned by `tests/unit/test_plant_sizing.py`). See ADR-028.

---

