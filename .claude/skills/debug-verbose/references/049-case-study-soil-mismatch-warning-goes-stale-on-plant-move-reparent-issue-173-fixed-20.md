## Case study: soil-mismatch warning goes stale on plant move/reparent (issue #173, fixed 2026-05-07)

**Symptom**: User drops a tomato (auto-populated with `ph_min=6.0` after #170) into a bed with `pH=4.0`. Bed edges turn red ✓. Drags the tomato outside → edges *stay* red. Bumps bed pH 4.0 → 4.1 → edges flip green. Drags the tomato *back into* the bed → edges *stay* green. Bumps pH 4.1 → 4.2 → red again. The recompute logic is correct; what's broken is the *trigger*.

**Wrong theories**:
- `_update_soil_mismatches` had a bug (verified — synchronous calls from soil-test save worked perfectly).
- `_child_item_ids` wasn't being updated by `SetParentBedCommand` (verified — it was, immediately).
- The 500 ms debounce timer wasn't firing (the most plausible-sounding theory, and partly true — see root cause).

**Key signal**: tracing `_update_soil_mismatches` showed it ran on every soil-test save and every position change *during* the drag, but never *after* the parent-link mutation that completes the drop. Cross-referenced with Qt docs: `QGraphicsScene.changed` is described as "emitted when the scene changes", which everyone reads as "any state change". It is not — it's "any *visual* change". Python attribute writes don't trigger it.

**Root cause**: `ui/canvas/canvas_view.py:1128` `_on_scene_changed_for_soil` — the debounce that drives soil-mismatch refresh is wired exclusively to `scene.changed`. After a drag, `_update_plant_bed_relationships` calls `SetParentBedCommand` which mutates `parent_bed_id` and `_child_item_ids` — plain attribute writes that emit no Qt signal and trigger no scene-rect invalidation. The 500 ms timer never restarts for the parent-link change. The next genuine scene change (e.g. the user editing pH) is what finally refreshes — explaining why steps 4 and 6 of the repro work and steps 3 and 5 don't.

**Fix**: Add `trigger_soil_mismatch_refresh(scene)` (commands.py) that walks `scene.views()` and calls `refresh_soil_mismatches()` on the canvas. Call it from `SetParentBedCommand.execute/undo` so every attach/detach call site (drag, properties-panel "Unlink", future) stays in sync. Bonus catch in the same fix: `SetParentBedCommand` also wasn't elevating the plant's z above the bed's, so a plant drawn before its bed rendered behind it after attach — same class of bug (mutation without re-establishing the invariants the rest of the canvas assumes). Both invariants — z elevation and soil-mismatch refresh — now run inside the command, with the elevation rolled back symmetrically on undo via a `_pre_execute_z` snapshot.

**Lesson**: When a debounced/event-driven refresh handler exists, it imposes an *implicit contract* on every callsite: "if you change state I depend on, you must also produce the event I'm listening to." Python attribute writes never satisfy that contract. Two durable mitigations: (a) funnel state changes through Commands and put the refresh trigger inside the Command rather than at every caller; (b) when adding a new debounced handler, write down the contract in the docstring so the next person extending the code paths knows it exists. Bonus rule: any time you find a fix that's "do X also at site Y", grep for *every* callsite of the same operation — there are almost always 3-5 more.

---

