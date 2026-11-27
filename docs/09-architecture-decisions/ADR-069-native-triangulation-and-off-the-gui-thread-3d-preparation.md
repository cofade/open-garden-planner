---
id: ADR-069
title: "Native triangulation and off-the-GUI-thread 3D preparation"
status: "Accepted; shipped in v1.34.11 (PR #676) for #452: native triangulation, the cooperative sliced read and the geometry lane. The decision's #531 half was first built with a NEW geometry object assigned to each live Model; that renders nothing while still picking, and it was WITHDRAWN on 2026-11-01 together with #598's seasonal-parts index. **Superseded on 2026-11-24 (shipped in v1.42.1, PR #1016; owner's manual test 2026-11-25):** a regrown part loads new buffers into the geometry object its live Model already has (#531, the addenda below), and the seasonal index is back (#598, ADR-064's addendum \"the seasonal callback's headroom\"). Release counting: #1014. #475 (raster lane, padded tiles) is NOT covered by this decision."
refs: ["#452", "#531", "#598"]
legacy_anchor: adr-069-native-triangulation-and-off-the-gui-thread-3d-preparation-452-531-598
---

# ADR-069: Native triangulation and off-the-GUI-thread 3D preparation

**Status**: Accepted; shipped in v1.34.11 (PR #676) for #452: native triangulation, the
cooperative sliced read and the geometry lane. The decision's #531 half was first built
with a NEW geometry object assigned to each live Model; that renders nothing while still
picking, and it was WITHDRAWN on 2026-11-01 together with #598's seasonal-parts index.
**Superseded on 2026-11-24 (shipped in v1.42.1, PR #1016; owner's manual test 2026-11-25):** a
regrown part loads new buffers into the geometry object its
live Model already has (#531, the addenda below), and the seasonal index is back (#598,
ADR-064's addendum "the seasonal callback's headroom"). Release counting: #1014.
#475 (raster lane, padded tiles) is NOT covered by this decision.

**Date**: 2026-11-01.

**Context.** The 3D view reads a whole plan on the GUI thread and builds every
changed item's meshes there. Both halves cost the sum of the plan: the issue measured
4.0 s, 5.4 s and 12.6 s for three deliberately huge plans, 33-40 s for two hundred
items at the per-item work bound, and a plan of 160 beds of 1,000 vertices paid about
two seconds in the builders alone. The shared pure-Python ear clipper priced a region
at O(n²) and verified each triangle against every edge — 0.75 s for one 1,000-vertex
bed cap — and its admission bound left a real 900-point drawn path out of 3D. The
budget was per item; the plan had none. A plan-wide budget was rejected earlier
because it would make one item's record depend on what else is on the plan.

**Decision.**

1. **One production triangulator: `mapbox-earcut` (ISC).** `polygon.cut_region` — the
   region cutter the record layer proves a buildable region with — now cuts a region
   with holes, or a hole-free ring of 256 vertices or more, in ONE native call. The
   shared ear clipper remains the cut for small hole-free rings (its triangles are
   pinned by the golden meshes and it is faster below that size) and, in
   `polygon.triangulate_polygon`, as the test reference and the builders' fallback for
   a ring the native cut refuses. The native answer is not trusted for being an answer:
   flat triangles are dropped, every remaining triangle must face up, and areas must
   add up before the cut is used.
2. **`polygon_triangles` uses the same cutter for big caps.** A cap of 256 vertices or
   more goes through `cut_region`, so the cut the record layer already proved is the
   one the builder gets (the memory is shared). A 1,000-vertex bed's cap fell from
   0.75 s to under a millisecond; 160 of them from 37 s to 2.1 s.
3. **The work bound is repriced, not removed.** `MAX_REGION_WORK` stays 150 M units,
   now priced from the measured native cost (`_earcut_work`: 2,000 units per vertex
   plus 3 per vertex squared — the worst case measured on a 16,000-vertex spiral,
   611 ms). `MAX_ITEM_VERTICES` stays 16,384. A 16,384-vertex circle is still refused;
   a 4,096-vertex ring and a slab of 200 touching holes are now buildable.
4. **The whole-plan read is cooperative.** `snapshot.snapshot_steps` is a generator
   that yields before every item; `snapshot_records` is the loop that drives it to the
   end (the synchronous API — exports, tests, the offscreen renderer).
   `SceneSyncController` drives it in `CAPTURE_SLICE_MS` (4 ms) slices, one item
   minimum per slice, between turns of the event loop, and applies the whole read once.
   Ownership: only the GUI thread reads Qt items; the records are plain immutable data.
   A change during the read does NOT restart it (a drag would starve it forever): the
   pass applies the coherent earlier snapshot, an item deleted since is dropped, and
   the read the change leaves owed follows at once. A document change, a reset, hiding
   3D or shutdown DROP it — a new plan is never assembled from the old plan's items.
5. **Heavy geometry goes to one worker lane.** When a pass's changed items hold
   `PREPARE_OFF_THREAD_VERTICES` (20,000) outline vertices or more, the controller hands
   those records to `SceneSync.prepare` on a single-worker `ThreadPoolExecutor` — the
   same builder path, no sink — and applies its answer through
   `SceneSync.apply(prepared=...)`, which uses the parts instead of building them.
   One flight at a time; a newer pass waits in one slot and replaces the one waiting.
   Below the threshold the pass builds its own items (a thread hop would only make an
   edit later). The builder memories are `ring_keyed` (safe from several threads, like
   `lru_cache`), and records are immutable.
6. **No second implementation.** `apply` still diffs, transacts, contains builder and
   sink failures, reports skips and recovers through the reset; the lane only moves the
   build. A failure on the lane is left out of the prepared map and paid again — and
   reported — by the apply.

**Rejected.**
- *A plan-wide work budget:* one item's record would depend on what else is on the plan
  (the issue's own objection).
- *Simplifying traced boundaries approximately:* the outline is the user's data.
- *Smaller native triangulation for everything:* below 256 vertices the shared clipper
  is faster (measured 2.3 ms against 4.0 ms at 100 vertices), and its triangles are
  what the golden meshes pin.
- *Moving the Qt reads off the GUI thread:* QGraphicsItem access is GUI-thread only.
  The split is therefore records (GUI thread, sliced) and meshes (worker, whole).
- *A signal per completed build:* a future's cross-thread signal needs a receiver in the
  worker's affinity; one 10 ms poll of one flight costs nothing and keeps the state on
  the GUI thread.
- *A per-item incremental apply:* `SceneSync.apply` takes the whole snapshot and diffs
  it; batching records would have meant a second apply path.

**Consequences and limits.** The GUI heartbeat (a 1 ms precise timer on the main
thread) while the three issue plans are read: p95 1.7-3.6 ms, max 8-20 ms, against
4.0/5.4/12.6 s in one block before (`scripts/measure_capture_heartbeat.py`; engine not
started — this is the pipeline's own GUI work). The read is still wall-clock slower than
a single block in total (2.3 s against 4.0 s for the first plan only because the builder
fix removed two minutes of the old cost). A plan whose builder is slow but whose
outlines are small stays on the GUI thread by design: the threshold is vertices, not
measured time. The cooperative read holds `snapshot_generation` open across event-loop
turns, so a synchronous snapshot taken meanwhile advances the generation — correct, but
it makes the next slice recompute more than it would alone. Ground tiles (#475) are
still painted on the GUI thread by the controller's ground passes; they are already
sliced by a 10 ms budget, and moving them to a raster lane is #475's remaining work.

Slicing moved a net reconciliation's cost from one turn into the turns that follow it,
and the preview-move gate noticed (`test_a_preview_mouse_move_costs_in_split_what_it_
costs_in_plan`): on the hosted runner a whole-plan read of the 424-record bench plan
takes 114 ms, and 16 of them landed inside 160 measured preview moves — ratios 4.61,
5.83 and 4.78 against the 2.0 bound, while the same test on a quiet machine reads 1.00.
The passes were not the preview's: each was the net reconciling after a quiet timer that
fired LATE, because the 2D side had held the GUI thread for about a second and the
preview's repaint was still queued. A timer that fires proves the loop is alive now, not
that the scene was still for the quiet time. The net therefore waits `NET_SETTLE_MS`
(50 ms) after its quiet timer, and a repaint inside that window restarts the whole quiet
time (`_net_quiet`/`_arm_net`); the bounded `NET_MAX_WAIT_S` path still reconciles a
scene that never quiets. On a probe with a 600 ms block inside every tenth preview turn,
the mid-round reads fall from 4 to 1 (the one after the tool stops).

**Verification.** `tests/integration/test_view3d_sync_controller.py` pins the slicing,
the stale-read policy, deleted items, document replacement, hiding, `flush` and the
lane, and the late-timer settle
(`test_a_quiet_timer_that_fired_after_a_blocked_loop_waits_for_a_settle`);
`tests/unit/test_scene3d_polygon.py` pins the pricing, the capacity
and the refusals; `tests/perf/test_scene3d_snapshot_budget.py` pins the read's budget.
The golden meshes still match below the threshold.

## Addendum (2026-11-24, #531 — a regrown part keeps its Model)

**Decision.** `Quick3DSink.replace_geometry` keeps every Model that a new piece of the
same `_reuse_key` (material kind, surface, ground detail, fill picture — what a Model is
fixed to for life) can take, and loads the new buffers into **the geometry object that
Model already has** (`EngineScene.reload_part` → `BufferGeometry.reload`). Old Models no
piece takes are destroyed first; pieces no old Model fits get new Models. The sink counts
`models_reused`, `models_destroyed` and `items_retired` (an item that lost at least one
Model), and the workspace counts a cache release from `items_retired` instead of
"every item whose geometry changed" — a release lets Qt keep about half of the ground's
same-size tile textures (#532), so a release nothing needs is itself a leak.

**Why it works now when the withdrawn path did not.** The withdrawn code built a NEW
`BufferGeometry` for the live Model and dropped the old one; this one never gives a live
Model a second geometry object, and never gives a geometry object a second Model (the L0
rule stands). Proven in pixels on Direct3D 11 (RTX 4070) and WARP:
`test_replace_geometry_changes_the_silhouette` now asserts the replaced item's two Models
were reused (none destroyed) and its silhouette IoU ≥ 0.95; a forged tree regrown in place
from LOD0 to LOD1 (custom foliage material, shadows) draws the same frame as fresh Models
with the same parts — 0 channels differ, 60,549 differ from LOD0
(`test_a_forged_tree_regrown_in_place_draws_what_a_fresh_build_draws`). The Linux render
tier (OpenGL, llvmpipe) runs both in CI.

**Measured** (the held date key of `workspace_default_measure.date_playback`, 20 dated
apple trees, a regrowth on EVERY step — `interval_ms=0` — 60 s, RTX 4070, branch and
`master` alternating, 2026-11-24):

| Tree | Steps in 60 s | Committed MB per step | GPU MB/min | Cache releases | Models destroyed |
|---|---|---|---|---|---|
| `master` (three runs) | 121, 123, 123 | 2.23, 2.77, 3.38 | 71.5, 65.9, 78.9 | 6, 6, 6 | every regrowth's |
| reuse, the old release count (one run) | 151 | 1.87 | 95.7 | 7 | — |
| reuse + `items_retired` (two runs) | 429, 384 | 0.27, 0.25 | 3.5, −7.9 | 0, 0 | 67 of 36,031 / 32,179 |

Most of the old cost was the cache releases the regrowths triggered (each keeps about half of
the ground's tile textures, #532); reuse is what lets the count drop them. The steps are
faster too (3.5x in the same minute) because a regrowth no longer creates Models. What
remains (about 13 kB a regrowth, committed only) is not resolved by this measurement: #1013, on
which #804 depends. The 500 ms regrowth interval
(`DATE_REGROW_MIN_MS`) and the time-lapse's `DATE_STEPS_PER_S` were chosen for the old
cost; they stay until #804 re-measures them.

**Addendum 2 (2026-11-24, the owner's manual test of #531): a held date still grew the
process, through the ground.** Holding the date field's arrow key from today to July 2031
on the food-forest example grew the process from about 950 MB to over 1.4 GB. The cause was
not the plants: a lawn's fill follows the date on a four-day grid, every change re-baked every
tile under the lawn, and a re-baked tile is a new Model with a new texture, which the engine
keeps memory of (#532). Stubbing the host's `set_ground` left a second-half slope of 0.0 and
+25 MB in 240 s, against 58-66 MB a minute for three unstubbed runs (RTX 4070). Held, the
lawns made 619 and 648 tile uploads in two 300 s runs where the unchanged code made 1223 and
7779, and the process grew 104 and 98 MB against 122 and 218 (private bytes swing by 100 MB
and every run has a warm-up of about 100 MB: the two light runs, 122 against 104 MB, are inside
that noise, so the upload count is the firmer number). The hold reduces the re-bakes, it
does not end them: at most one lawn re-bake every 10 s remains while a key is held. The alternative that mirrors this ADR - load the
re-baked picture into the tile's own `QQuick3DTextureData` - does not draw for a texture of
256 x 256 pixels or more (it shows the old picture; 128 x 128 and below work), so it was
dropped (`ground_tiles.py` docstring). **Decision:** while the date keeps changing the
lawns keep the colour of the date they last showed (`SEASON_REST_MS`, `SEASON_MAX_HOLD_MS`,
`Scene3DController._season_date_for`); the meadow's tint follows the same date. The plants
and the light still follow every step. Consequence: during a held key or a year animation the
lawns' colour changes at most every 10 s and settles 0.8 s after the date does
(FR-3D-GROUND-09). A recorded tour never holds (`Scene3DController.hold_season = False`
while a tour records: its date steps, under 800 ms apart, would leave the lawn on an old colour), and `idle` waits for the
trailing pass of a held lawn, so a rendered picture an agent asks for is exact.

**Addendum 3 (2026-11-25, #1014 — ONE retirement counter on the protocol).** The
first #531 delivery read `items_retired` where a sink happened to have it and fell back
to the sync controller's old per-pass estimate otherwise, so two counters described one
fact: the sink's exact one, and `_retired_by_reset + len(removed) + len(geometry)`.
`EngineSink` now declares `items_retired`, `RecordingSink` implements it with the same
`core.scene3d.model_reuse_key` rule the Qt Quick 3D sink uses for its Models, and the
estimate is gone. `TickReport.retired` is the sink's counter delta since the previous
report (a `reset()`'s `clear()` is therefore included), and `Workspace._count_retired`
reads the same counter. The RecordingSink's rule made one old expectation visible: a
resize keeps every part's reuse key, so production retired **nothing**, while the
removed estimate said one.

Cadence, measured on the recording sink with the product's thresholds
(`RELEASE_AFTER_RETIRED` 64, `RELEASE_NOW_RETIRED` 512): twenty moves, a resize and an
undo/redo pair retire 0 Models; two deleted beds retire 2. An ordinary editing minute
therefore needs about thirty-two copies of that session to trigger one quiet release,
while a reset's `clear()` retires every held item at once, and a mass delete crosses the
flood threshold the same way. The thresholds stand; they now mean "a flood", not
"a session".
