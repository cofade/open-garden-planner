# Case study: live year animation flashed v0 silhouettes and bare trunk stumps and froze for 4-5 s (#995, #996)

## Symptom
During manual testing of PR #994 (`#973`) in `spring-garden.ogp` with **Animate -> Year (Normal)**, trees repeatedly dropped back to low-quality v0 bulbous silhouettes (`build_silhouette`) or bare conical trunk stumps (`_trunk`) before refining back into forged branching trees, distant trees remained stuck as silhouettes/stumps for seconds, and the application stuttered heavily with multi-second UI freezes.

## Wrong theories
- "The 2 % geometric size buckets in `ForgeCache` (`#973`) were not being hit." — False: `ForgeCache` had a 90.2 % hit rate (`119` hits, `13` misses in 6 s), yet `v0_build_plant` was still called **132 times** before `ForgeWorker` was even consulted.
- "The 5-second freezes were inside `ForgeWorker` synthesis or `SceneSync.apply`." — False: timing every callback showed `SceneSync.apply` took `239 ms / 12 calls` and `_step_forge` took `1,250 ms / 87 calls`; the 5-second freezes occurred inside `QApplication.notify` on `QQuickView` (`UpdateRequest`) immediately after `QQuickWindow.releaseResources()` or an `AutoPreset` quality downgrade (`high -> medium -> low`).

## Key log lines
```text
[PROBE] 6s Year Animation in VIEW3D:
  v0_build_plant calls:         132 (80.1 ms)
  sun_shadow_recompute calls:   26 (1143.3 ms)
  host_release_caches calls:    2 (2.9 ms call, followed by 5032.3 ms QQuickView UpdateRequest!)
  AutoPreset step-downs:        high -> medium (4330.7 ms UpdateRequest), medium -> low (5546.1 ms UpdateRequest)
```

## Root cause
1. **Unconditional v0 downgrade (`#995`):** Every 500 ms (`DATE_REGROW_MS`), `Scene3DController._apply_ticket` detected `changes.geometry` for all 11 dated growing plants and called `SceneSync.apply(records)` with `prepared=None`. That built v0 `build_silhouette` parts on the GUI thread and destroyed the forged parts. Then `Workspace._on_applied` called `ForgeWorker.invalidate()`, deleting `_applied_state`. In winter/early spring (`leaf_density == 0`), the QML node kept `leaf_density == 0`, so the v0 silhouette rendered its `"foliage"` crown invisible and left only its conical `"wood"` trunk (`_trunk`) — a bare brown pole! And `_step_background` processed only 1 plant per 10 ms tick in camera-priority order, starving distant trees.
2. **4-5 s RHI stalls and hidden 2D work (`#996`):** Replacing 11 plants every 500 ms incremented `Workspace._retired` until `_release_engine_caches()` called `QQuickWindow.releaseResources()`, which dropped compiled RHI pipelines and stalled the next `QQuickView` frame for `5.03 s`. Meanwhile `AutoPreset` sampled frame counts during `ForgeWorker` uploads and playback, stepping down `high -> medium -> low` (`4.33 s` and `5.55 s` shader-recompile stalls), and `SunShadowController._recompute` solved 2D shadow polygons on every 200 ms tick even in pure `VIEW3D` mode (`1,143.3 ms`).

## Fix and lesson
- `Scene3DController` now calls `ForgeWorker.prepare_for_sync(records, build_ids)` before `SceneSync.apply`: warm 2 % bucket hits are stretched and applied immediately; cold bucket misses stretch the last forged mesh (`_applied_parts`) for the immediate frame while the new bucket builds in the background; newly appearing dated plants entering a forged scene are forged directly.
- `Workspace` connects `SimClock.date_changed` to `ForgeWorker.scrub_date`, batches up to 16 plants per `_step_forge` turn, holds `LookController.hold_preset` and defers `_release_engine_caches()` while `SunSimToolbar` playback is active, and calls `LookController.pause_auto_sample()` during pipeline passes and `ForgeWorker` uploads.
- `SunShadowController` skips 2D shadow polygon solves in pure `VIEW3D` mode unless `DrapeMode.SHADOWS` is active, `CanvasScene.refresh_timeline` invalidates only plants whose canopy radius changed, and `GardenPlannerApp` defers heavy 2D date diagnostic sweeps during active playback.
- After fix (6 s year playback on `spring-garden.ogp` in `VIEW3D`): `0` `v0_build_plant` calls, `0` hidden 2D shadow solves, `0` cache releases, preset `high -> high`, `242` frames presented (~40.3 FPS), max `processEvents` turn `137.2 ms`.
