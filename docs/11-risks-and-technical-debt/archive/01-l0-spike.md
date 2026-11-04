# Archive 01: Phase 17 L0 spike

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.5 The Qt Quick 3D spike: engine traps, and a "hang" that was a stopwatch problem (ADR-048, Phase 17 L0)

Each of these cost a round trip during the L0 spike. The engine facts are kept
current in the `ogp-3d-renderer` skill; this entry records why they bite.

**1. A headless 3D test needs a real RHI context.** The `offscreen` QPA plugin
selects the *software* scene graph, which renders no 3D at all — the frame is
empty, not wrong. Linux render tests run under `xvfb-run` with
`QT_QPA_PLATFORM=xcb` and `QSG_RHI_BACKEND=opengl` (Mesa llvmpipe), which needs
`libegl1` and `libxcb-cursor0`. Calling `QQuick3D.idealSurfaceFormat()` before the
`QGuiApplication` exists segfaults.

**2. Conventions that read as art bugs.** A `DirectionalLight` has no `lookAt`
(cameras do) and shines down its local −Z, so an un-oriented sun leaves only sky
light: the first renders were uniformly pale blue. Models use `castsShadows`,
lights `castsShadow`. `ProceduralSkyTextureData` puts its sun at compass bearing
`sunLongitude − 90°`, and the scene environment pre-filters its light probe
**once per Texture object** — updating the texture's properties moved nothing, so
the sky's sun stayed in the north until each sun change built a fresh Texture.
Both are pinned by the spike's sky probe, which reads the disc 25° off-centre (max error 0.85° on OpenGL and 1.4° on D3D11, including up to ~0.6° of the probe's own model error before its bearing maths accounted for the camera pitch).

**3. The `QQuickWidget` host was broken in two ways no screenshot showed.** It has
no `frameSwapped` (frames are counted on its offscreen window's
`afterRendering`), and `QQuickWidget.update()` only re-composites the last texture,
so a "wait for a new frame" loop waited forever. Its window's `isExposed()` is
always False. And the first split-pan measurement said the 3D widget made 2D
panning **70× faster** (0.08 ms vs 5.45 ms): a synchronous `repaint()` never
reaches the flush, which is exactly where a `QQuickWidget` makes the whole window
pay for RHI composition. Measured with event processing, the cost is ×1.42 on
llvmpipe. *A benchmark result that is better than the no-op baseline is a broken
benchmark.*

**4. A QML function's returned object is a `QJSValue`, not a dict** — call
`.toVariant()`. The picking helper had never been exercised and failed on its
first use.

**5. The 56-minute "hang" that was a stopwatch problem.** Windows evidence run
v1 built the frozen exe, passed `--selftest`, then ran the spike for 56 minutes
until the job limit killed it — with no output. Three things made it
uninvestigable: a GUI-subsystem exe has no stdout (`print` is a no-op, the #291
precedent); `Start-Process -Wait` has no timeout; and the artifact host is not
reachable from where the log was read. After the spike learned to write its own
timestamped log, per-phase metrics and a `faulthandler` watchdog, run v2 showed
frames arriving about once a second under Direct3D 11 on WARP — and **one
`grabWindow()` of the sky-lit scene taking ~100 s**. v1 had simply asked for
many of those. *Tooling that must run headless writes its own evidence; without
timestamps, "slow" and "hung" are indistinguishable.*

**6. A geometry does not survive its Model, and an array repeater kills every Model.**
The Windows run's picks came back 0/20 while the container's were 20/20 — not a
platform difference: the Windows command ran the IoU and orientation probes first,
and both swap the scene's models out and back. Once the Model using a
`QQuick3DGeometry` is destroyed, handing the same geometry to a new Model renders
nothing and picks nothing (the frame equals an empty scene's); `update()` does
not restore it, a full re-upload does. And a `Repeater3D` over a JS array
recreates **every** delegate on any change, so a model present before and after
the change came back blank too. The first fix re-uploaded only removed models and
measured 19/20 — the miss was the model that had never left. *A probe that
mutates shared state must restore it through the same path the product uses, and
the measurement that follows it must run in the same order in CI as on the dev
box.*

**7. A gate on `*.yml` sees temporary workflows too.** The evidence workflow
copied the frozen-exe `Start-Process` gate shape and turned CI red through
`tests/unit/test_gate_commands.py` (Rule 1: the command has one home,
`ogp-change-control` §2.8). The fix was not a second copy of the gate: the
evidence run goes through a driver script with a hard timeout and does not
repeat `--selftest`.

**8. A keep-alive list is a leak with a good excuse.** A texture created in
Python is owned by Python, so the spike appended every ground texture to a list
to keep it alive while QML showed it. The first soak with real project reloads
(plan from disk into a new scene, ground re-baked, every model and geometry new)
exited 0 but grew RSS by one baked ground — 2400×1600 RGBA, ~15 MB plus its GPU
copy — per reload, linearly (771 → 1035 MB over 10 reloads). Holding only the
shown texture settled at ~885 MB. Both variants grew ~70 MB on the first reload,
so total growth could not tell a leak from an allocator settling; the slope over
the second half of the reloads can, and the soak now reports and gates it
(< 10 MB/reload). Two Windows runs of that gate then failed without showing a
leak, and without ruling one out: the working set (trimmed and regrown by the
OS) cannot judge a leak at all, and five points of private bytes cannot resolve
10 MB/reload against WARP's ±30–60 MB swings. Re-fitting the gate after each
failure was its own smell (senior review), so the final gate was fixed before
the next run: 20 reloads, private bytes, a Theil–Sen slope, and a positive
control on the same runner that must fire on 25 MB per reload. Windows runs
v9–v19 passed it (1.5–9.0 MB/reload; identical code read 9.0 and 1.8), yet every
one of them, after an early dip, rose 5–10 MB per reload. In longer soaks,
identical code rose +196 and +62 MB by reload 50, and over reloads 51–100 the
five 100-reload runs (the same soak path, not the same code) had slopes of 0.21,
2.03, 3.05, 0.08 and 3.50 MB/reload, the 0.08 an interval that includes zero.
Over reloads 11–20 the same gate read 0.00–0.46 MB/reload on Linux (llvmpipe
RSS); no Linux soak runs past reload 20. The cause is not identified, so the
leak half stays open on D3D11. Three readings of these
curves overreached in turn (a ceiling, a slowdown, a "threefold" pinned on the
wrong pair of runs), so the record now gives numbers, not shapes. The gate
answers "is there a trend over the last ten reloads", not "did memory grow",
so the record carries the whole curve
(ADR-048 entry 10). *Hold the one object in use, not every object
that ever was; judge a leak by its slope, and trust a gate only after you have
seen it fire on the machine it judges.*

**9. An `x or default` threshold turns a perfect zero into a failure.** The
evidence driver judged the projection check as
`(pick.get("max_projection_err_px") or 99) < 1.0`, so a measured 0.0 px read as
99 and failed the run. Thresholds now go through explicit number checks that
fail on a missing or null metric instead of substituting a default, and a probe
that was requested but wrote nothing fails the verdict.

**10. A shader that does not compile is a warning, not an error.** Renaming one
call in the pond's `water.frag` printed `QSpirvCompiler: Failed to parse shader`
as a `QtWarningMsg` to stderr; the run exited 0 with `status: ok` while 449 pond
pixels changed colour (senior review, measured). The frozen exe has no stderr,
so on Windows nothing would have shown at all. The spike now records every Qt
message through `qInstallMessageHandler` into its log and `metrics.json`, and a
shader or QML error ends the run with exit 4 (not 3, which the MSVC CRT's
`abort()` also returns on Windows); a render test breaks the shader on
purpose as the positive control. *Any headless render path must read Qt's
messages, not only its exit code.*

**11. Importing a tool script can take over the suite's settings key.**
`scripts/make_bench_plans.py` pointed the settings names at its own throwaway
key at module scope. `tests/integration/test_bench_plans.py` imports the script
to regenerate the fixtures, so every later test in that pytest process ran on
the script's fixed key instead of conftest's per-process one, the guard against
the "black hole" of two runs sharing a key (ADR-041). The rebinding moved into
`main()`, and an autouse check now fails any test that leaves the names changed
(it caught the old script at once). *A rebinding of process-wide names belongs
in an entry point, never at import time.*

**12. A procedural sky bound live regenerates on every input.**
`ProceduralSkyTextureData` recomputes the whole sky synchronously on the GUI
thread for each input change (~190 ms at high quality on llvmpipe). The spike
bound its inputs to root properties and built a default sky at load, so one
open regenerated it for each look and sun input and threw the first one away:
~4.7 s of CPU, filed under "QML load" or no bucket at all (senior review).
Built once per sun change, inputs set at low quality and raised last, the
frames are bit-identical and that cost drops to ~0.4 s (QML load 1709 → 70 ms,
`set_look` 791 → 0.1 ms, `set_sun` 2192 → 344 ms; llvmpipe, 640×360, commit
a275da2 — ADR-048 entry 6 and the `ogp-3d-renderer` skill cite the same run).
*An input bound live to an expensive generator is a hidden loop; time every
bucket and require the buckets to add up.*

**13. A texture re-attached after a detach renders white, and a guard on
identity did not see it.** The IoU and orientation probes clear the ground
texture for their measurement; `preserved_state()` set the same
`QQuick3DTextureData` back, and Qt Quick 3D drew the plan ground white until the
next project reload (mean difference 13.1 on the frame, all of it in the ground
half). `update()` alone does nothing; `setTextureData(textureData())` plus
`update()`, or a fresh object, restores it: the texture twin of item 6.
`preserved_state`'s guard checked that the shown texture was the one Python
held, which stayed true throughout. A second-window frame comparison caught it
(9.8 mean luma). The first diagnosis, a stale reference frame "fixed" with a
settle wait, was validated by a run without `--iou`, the trigger, so it proved
nothing (senior review, pass 4). Every restore is now checked in pixels
(`probe_restore_frame_diff`: 9.83 before the fix, 0.0 after). *A validation run
that omits the trigger proves nothing; check a contract in the currency it
promises.*

**14. From a git worktree, a test's subprocess ran the main checkout's code.**
`tests/conftest.py` puts the checkout's `src` on the *test* process's path only.
A child started as `python -m open_garden_planner` or `python -c "import
open_garden_planner"` resolves the package through the venv's editable install,
and that points at the main checkout. So a render-tier or isolation test run in a
worktree (where every review and creator agent works) judged other code, and was
green or red for the wrong commit (found by 3D creator round 4). The spike's
render tier and isolation test now put the checkout's own `src` first on the
child's `PYTHONPATH`; `scripts/bench_view3d.py` inserts it itself. *A subprocess
does not inherit the parent's import path; pin it, or the test measures whatever
the environment happens to point at.*

**15. A rule ported by hand drifts from its source.** Symptom: none on the
bench. The spike shows fruit only in a species' harvest window
(`runner.in_harvest_window`), and that port returned False on every asparagus
harvest date at frost dates from 4 January on, and on rhubarb's from 1 January
until just before the frost's anniversary (291 of 1,096 harvest days in
2026–2028 at a 04-09 frost, 783 at 09-20). Neither has a fruit look in the
spike, so no frame changed. Cause: the port took a fixed ±1-year frost anchor
and was checked against the single-year `generate_calendar_tasks`, while the
generator the agent's task tools use (`get_tasks`, `get_task_calendar`),
`generate_for_date_window`, derives the anchor years from the offsets (a
29 February frost: ADR-048 entry 18). Fix: the port derives the range the same
way, pinned by a test that compares the two every day of three years, asparagus
and a southern plan included (ADR-048 entry 18 cites the review passes; PR #413
holds their history). The check also showed that every GUI task surface anchors
on one year (TD-037). *Pin a port to its source day by day, find the source the
product actually calls before naming a deviation, and sweep what the user sees
before saying a fix changed it.*
