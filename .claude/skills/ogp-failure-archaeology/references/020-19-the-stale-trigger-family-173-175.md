## 19. The stale-trigger family (#173/#175)

Source: §11.4 + debug-verbose case study (2026-05-07).

- Symptom: soil-mismatch bed border stayed stale on plant move/reparent but updated on
  any *unrelated* edit — recompute logic proven correct.
- Wrong theories: recompute bug; `_child_item_ids` not updated; debounce timer broken.
- Root cause: `QGraphicsScene.changed` fires only on **visual** change; mutating
  `parent_bed_id`/`_child_item_ids` is a plain Python attribute write — no signal, no
  debounce restart.
- Fix + durable pattern: put the refresh trigger *inside the command*
  (`SetParentBedCommand` calls `trigger_soil_mismatch_refresh` on execute AND undo),
  never at every caller. Bonus rule from the fix: any "do X also at site Y" fix means
  grep for *every* call site of the same operation — there are almost always 3–5 more.
  (Update, #338: the same command originally also called a since-deleted
  `ensure_z_above_parent` helper for the z-ordering half of this fix; that mechanism was
  replaced by the derive-only stacking clamp — see the entry below.)
- Status: closed. Related: `tests/unit/test_plant_bed_relationship.py`,
  `tests/unit/test_plant_bed_zorder.py`.

---

