# Archive 11: Phase 17 L1.9 and L1.10 default flip and Qt 3D removal

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.20 What the default flip and the removal of Qt 3D taught (Phase 17 L1.9 / L1.10, #385)

Symptom → root cause → fix (ADR-060 addendum "the default and the removal", §8.29.9; tests
§8.10.13).

1. **A strict xfail turned red the day its fix was to be measured — without the fix.**
   *Symptom:* the wind soak's strict xfail (FU-L14-2: "committed memory grows 2.1 to 2.6 MB a
   minute while the wind runs", registered bound 2.0) PASSED on 2026-10-19 on the unchanged
   code (`--runxfail`; strict, it would have failed the render tier). *Root cause:* not found —
   the growth L1.4 had measured did not reproduce: six alternating soaks of 4 to 5 minutes,
   three with L1.4's `FrameAnimation` and three with the planned fix (a C++ `NumberAnimation`
   on `windTime`, no JavaScript per frame), read 0.77 / 1.04 / 0.89 and 2.03 / 1.04 / 0.46 MB a
   minute from the first sample to the last (second-half slopes 0.17 / 1.26 / 0.23 and 1.51 /
   0.83 / 0.00): the two clocks inside each other's spread. *Fix:* the clock change was
   reverted (it changed nothing measurable) and the xfail removed — and a seventh run the same day (the final render tier on the L1.9/L1.10 tree) read a second-half slope of 2.637
   MB a minute: intermittent, not gone. The gate is a non-strict xfail again (#534). *Lesson:* run the unchanged code first; a fix measured
   alone would have been credited with a difference that was already there.
2. **"Settled" must know every timer that books a pass.** *Symptom:* after the date-playback
   throttle, the workspace workflow test read `[begin, set_sun, commit]` where it expected the
   tree's regrowth. *Root cause:* the throttle's trailing regrowth waits on a third timer;
   `Scene3DController.idle` and the tests' `pipeline_settled` knew only the posted pass and the
   tick timer, so "nothing is on its way" was true while a regrowth was booked. *Fix:* both
   include `_date_timer` (§8.10.13).
3. **The same test, and the time between two of its writes.** *Symptom:* that test also wrote
   the date twice about 200 ms apart: inside the 500 ms interval on the dev box (the second
   date deferred), outside it on a loaded runner (regrown at once). *Root cause:* its
   expectation depended on the machine's speed. *Fix:* it pins `DATE_REGROW_MIN_MS = 0`; the
   throttle's own tests make bursts deterministic (one turn of the event loop) and keep the
   wall-clock bound in a `perf` test with a control arm.
4. **The menu text promised a window.** "&3D View…" — the ellipsis says "opens a dialog or a
   window", and the action now switches a mode of the main window. The text lost its
   ellipsis (a new source string: German and Spanish had to follow, the gate of #496 says
   so) and its status tip says "beside the plan".
5. **Qt 3D ignored Qt Quick's software switch.** *Symptom:* the old window's "WARP" budget run
   reported the RTX 4070 as its adapter and GPU-speed numbers. *Root cause:*
   `QSG_RHI_PREFER_SOFTWARE_RENDERER` is read by Qt Quick's scene graph; Qt 3D creates its own
   RHI and does not read it. *Fix:* none needed after L1.10 — the row says "not measured"
   rather than reporting a GPU run as WARP. *Lesson:* check the adapter a run REPORTS, not the
   switch it was given.
6. **A sleeping display presents no frames.** *Symptom:* the frame-cost board measured 0 fps on
   the RTX 4070. *Root cause:* the desktop's display was asleep; a vblank-paced swap chain
   presents nothing then. *Fix:* the GPU rows ran timer-paced (`QT_D3D_NO_VBLANK_THREAD=1`,
   capped near 60) and say so. *Lesson:* a frame rate of 0 is a measurement of the display
   first.
7. **A mock that accepts every call proved a call, not a light.** *Symptom:* moved from the
   old window's `MagicMock` onto the workspace's recording engine, "a date edit moves the 3D
   light" failed: no `set_sun` reached the engine. *Root cause:* the test plan had no location,
   so the light is the fixed default sun, which no date moves; the mock had answered the old
   app's unconditional `set_sun` call. *Fix:* the test gives the plan a location. *Lesson:* a
   recording double that keeps the protocol (here: a repeated sun sends nothing) finds what a
   catch-all mock hides.
8. **A lock refresh changes more than the packages it drops.** *Symptom:* `uv lock --offline`
   after removing two pins removed their two entries from `uv.lock` — and reordered three
   resolution-marker lines. *Root cause:* uv writes the marker list in its own order; the
   strings were the same and no version changed (checked line by line). The PEP 751 export
   (`pylock.toml`) changed by exactly the two packages' 26 lines. *Lesson:* read a lock diff
   by what it resolves, and say what else moved.
9. **A branch merged after the removal used the deleted spike.** *Symptom:* after L1.5 joined,
   a ground-bake test imported `spike_q3d.runner.MEADOW_ALBEDO`. *Root cause:* L1.5 was written
   while the spike existed; the removal and the new use met only at the merge. *Fix:* the test
   reads the meadow from the frozen reference. *Lesson:* after merging into a removal, scan the
   merged tree for every removed name, not only the files that conflicted.
10. **A local build bundles what the build environment has installed, not what the lock pins.**
   *Symptom:* the first frozen build after the removal, made with the shared development venv,
   still carried Qt 3D's eleven `Qt63D*.dll` and the `qml/Qt3D` folder — though nothing imports
   them and the spec names none of them. *Root cause:* that venv still had `PyQt6-3D-Qt6`
   installed (removing a pin does not uninstall a wheel); the QML hook collects the QML modules
   it finds in the installed `PyQt6/Qt6/qml` folder, and their plugins pull their DLLs in.
   *Fix:* the before / after bundles were built in ONE clean environment synced from each tree's
   lock (`uv sync --locked`), which is what CI and the release do; after pulling this change,
   re-sync a development venv (`uv sync --locked …`, ogp-build-and-run) before building locally.
   *Lesson:* judge a bundle built from a locked environment; a dev venv's bundle answers what
   the dev venv holds.
