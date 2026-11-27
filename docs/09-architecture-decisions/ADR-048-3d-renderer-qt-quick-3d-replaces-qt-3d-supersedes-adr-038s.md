---
id: ADR-048
title: "3D Renderer — Qt Quick 3D replaces Qt 3D (supersedes ADR-038's engine choice) — GO/NO-GO spike (Phase 17, Package L0)"
status: "**Accepted (GO)** (owner decision 2026-10-05, Package L0 \"Proof of Beauty\"). This entry committed its criteria **before** any GO evidence was gathered; the evidence log below records the measurements, and entry 19 the owner-GPU runs."
legacy_anchor: adr-048-3d-renderer--qt-quick-3d-replaces-qt-3d-supersedes-adr-038s-engine-choice--gono-go-spike-phase-17-package-l0
---

# ADR-048: 3D Renderer — Qt Quick 3D replaces Qt 3D (supersedes ADR-038's engine choice) — GO/NO-GO spike (Phase 17, Package L0)

**Status**: **Accepted (GO)** (owner decision 2026-10-05, Package L0 "Proof of Beauty"). This entry committed its criteria **before** any GO evidence was gathered; the evidence log below records the measurements, and entry 19 the owner-GPU runs. | **Context**: Owner goal (2026-10-03): make the 3D mode "modern, beautiful, really usable" in a *Lush Cinematic* look, experience + analyze (editing stays 2D), fully procedural models. ADR-038 chose PyQt6-3D (Qt 3D) among PyQt6-3D, PyVista, pyqtgraph.opengl and a 2.5D fallback — **Qt Quick 3D was never evaluated**. Since then: Qt 3D is deprecated since Qt 6.8 and no longer part of official Qt releases (Riverbank still ships PyQt6-3D up to 6.11.0); its forward renderer has no shadow maps, no image-based lighting and no post-processing out of the box (the US-E6 "lighting-only" MVP), and its separately-versioned wheel pair is the #277 failure class. Qt Quick 3D ships **inside the already-pinned wheels** (`PyQt6==6.11.0` provides `QtQuick3D` with `QQuick3DGeometry` + `QQuick3DTextureData`; `PyQt6-Qt6==6.11.0` provides the runtime incl. Helpers/Effects/Particles/AssetUtils QML modules) and offers PBR, IBL, cascaded soft shadows (blue-noise PCF in 6.11), SSAO, `ExtendedSceneEnvironment` (tonemapping, glow, DOF, LUT, fog; SSGI/SSR in 6.11), particles and custom materials. Timebox: 6 working days, hard stop.

**Decision criteria (GO requires all):**

| # | Criterion | GO threshold |
|---|---|---|
| 1 | **Packaging (DECISIVE)** | frozen `dist/OpenGardenPlanner.exe` renders production-shaped QML for `tests/fixtures/plans/bench_small.ogp` on the owner's Windows machine (auto-screenshot + clean exit), **and** a selftest render passes on `windows-latest` |
| 2 | Graphics API coexistence | the active RHI backend is logged (D3D11 vs OpenGL) in the real process (WebEngine imported at startup); the Google-Maps picker still works before and after the 3D view has been shown in the same session |
| 3 | Embedding | `QQuickWidget` inside the main window keeps 2D canvas pan frame time in Split mode ≤ 1.3× baseline and shows no visible window recreation — otherwise the `QQuickView` container host is chosen (policy outcome, not a kill) |
| 4 | Frame rate | High ≥ 60 fps on a dedicated GPU, Medium ≥ 30 fps on an integrated GPU (or 1440p on the owner's machine as proxy), 1080p, `bench_small` |
| 5 | Open time | cold open ≤ 6 s (first ever, shader compile), warm ≤ 2.5 s |
| 6 | Python geometry path | updating a 100k-vertex `QQuick3DGeometry` ≤ 10 ms on the main thread; creating 1,000 Models ≤ 300 ms; no leak on destroy |
| 7 | Picking | a QML `pickAt(x, y)` helper resolves 20/20 test clicks to the right item |
| 8 | Shadow agreement | top-down shadow-map footprint of a box caster vs `core/shadow_geometry` polygon: IoU ≥ 0.85 at 15°/35°/60° sun elevation |
| 9 | Size | installed size ≤ +60 MB net after trimming unused Quick 3D modules (≤ +150 MB only with explicit owner acceptance) |
| 10 | Stability | 50 show/hide cycles, 10 project reloads, app close while animating, full pytest run: zero aborts |
| 11 | Beauty | owner sign-off of the beauty sheet within 2 rounds (independent `ogp-3d-reviewer` verdict attached) |
| 12 | License | GPL-3.0-compatible, verified from the wheel's LICENSE files and recorded in third-party notices |

**Kill criteria (pre-committed):**
- **K1** — criterion 1 still fails after one focused day of packaging work → NO-GO.
- **K2** — criterion 2 can only be satisfied by breaking the map picker → NO-GO.
- **K3** — Medium < 20 fps on an integrated GPU at render scale 0.75 with shadows on, unless the owner accepts a dedicated-GPU requirement → NO-GO.
- **K4** — beauty rejected twice → NO-GO.
- **K5** — a reproducible abort in the stability soak with no root cause by day 6 → NO-GO.
- **K6** — size above +150 MB without owner acceptance → NO-GO.
- **Policy outcomes, not kills:** criterion 8 < 0.85 → engine shadows ship as *illustrative* and the analytic 2D shadows are draped onto the 3D ground (mandatory); Linux CI rendering infeasible → render tests run on Windows/dev box only; criterion 3 fails → `QQuickView` host.
- **NO-GO path:** the engine-agnostic, Qt-free cores (scene contract v2 + diff, built-world and plant-v0 builders) are kept and a Qt 3D sink is written for them (vertex-coloured materials, live sync, no camera reset). No work is thrown away.

**Candidates:** (a) Qt Quick 3D hosted in a `QQuickWidget` inside the main window; (b) Qt Quick 3D in a `QQuickView` + `QWidget.createWindowContainer`; (c) baseline: the shipped Qt 3D view (US-E6/E7) for the before/after beauty comparison.

**Evidence log** (filled in as measured; machine, backend, frame size and run stated per entry. The Windows runs' `metrics.json` files are committed in [`adr-048-evidence/`](adr-048-evidence/README.md), because CI logs expire):

1. *Linux render feasibility (M10 — not a GO criterion; this one probe ran before the table above was committed, to know whether CI-side evidence was possible at all)*: cloud container, Python 3.11.15, PyQt6 6.11.0 / PyQt6-Qt6 6.11.0, Xvfb + Mesa llvmpipe (LLVM 20.1.2, OpenGL 4.5): a `View3D` with `ExtendedSceneEnvironment`, `ProceduralSkyTextureData` light probe, a shadow-casting `DirectionalLight` and PBR models renders (`GraphicsApi.OpenGL`). Requirements found: `libegl1` (PyQt6's QtQuick3D binding links libEGL), `libxcb-cursor0` (xcb plugin ≥ 6.5); the `offscreen` QPA plugin selects the **software** scene-graph backend, which cannot render 3D — Linux render tests need `xvfb-run` + `QT_QPA_PLATFORM=xcb` + `QSG_RHI_BACKEND=opengl`. Pitfall: calling `QQuick3D.idealSurfaceFormat()` **before** the `QGuiApplication` exists segfaults (PyQt6 6.11, Linux).

2. *Shadow agreement (criterion 8)*: box caster 100 × 100 × 200 cm, azimuth 225°. The probe (`--iou`) compares the engine's shadow-map footprint in a top-down **orthographic** view with the analytic `core/shadow_geometry` polygon on the same pixel grid. In that view the light uses **no cascades** (`csmNumSplits: 0`), so criterion 8 covers the shadow-map pipeline but not the cascaded configuration of the beauty views; a perspective probe with cascades is L1.4 work. IoU at 15° / 35° / 60°:
   - OpenGL on Mesa llvmpipe (container): 0.959 / 0.950 / 0.920 at 1280×720, and 0.980 / 0.985 / 0.964 at 960×540.
   - Direct3D 11 on WARP at 960×540: **0.980 / 0.984 / 0.963**, identical in every Windows run (v2–v6, unfrozen and frozen).
   - Since 6f0c4f4 the probe runs per preset, because every preset has its own shadow-map quality: low 0.970 / 0.963 / 0.937 (D3D11, v6) and 0.963 / 0.968 / 0.937 (container, 1280×720). Low carries a VeryHigh map since creator round 4: 0.984 / 0.982 / 0.964 (D3D11, v14), 0.953 / 0.959 / 0.922 (container, 1280×720) and 0.985 / 0.983 / 0.967 (container, 640×360).

   The value depends on the frame size, which sets the pixel grid, not on the backend.
   - **Scope** (senior review): a box is where the 2D and 3D shadow models agree by construction. On a real plan they differ by design: gable roofs, open pergolas (2D extrudes a solid footprint), plants lifted onto beds, tree crowns on trunks. Criterion 8 therefore shows that the shadow-map pipeline is geometrically right, not that 3D shadows will match the 2D analysis; the analysis stays with the 2D model and is draped onto the 3D ground (plan: the L1.1 scene-pipeline ADR; the epic's reserved ADR-049 went to frost dates, and the L1 ADRs start at ADR-053).
3. *Frame and sky orientation*:
   - **Ground.** The baked north-up ground texture needs `flipV: true`. NCC of the identity variant against the vertically flipped one: 0.943–0.954 vs −0.10…+0.01 (container), 0.949–0.956 vs −0.111…+0.016 (Windows v3, v4, v6 frozen). The probe's pixel grid comes from the grabbed image and its `devicePixelRatio`: built from the logical size, it reported a mirrored ground at 150 % display scale and `--iou` crashed there (senior review); a render test now runs both at `QT_SCALE_FACTOR=1.5`.
   - **Sky.** `ProceduralSkyTextureData` draws its sun at compass bearing `sunLongitude − 90°`, so `sunLongitude = azimuth + 90°`. A disc at the image centre only shows which way the sun is (the pinhole mapping error is zero there), so the probe looks 25° left and right of the solar azimuth and locates the disc off-centre, at azimuths 90°/180°/270°: max abs error **0.85°** (container) and **1.4°** (D3D11, v6 frozen), against the probe's 6° bound. Those readings converted the disc's pixel with the x coordinate alone, which is exact only for an unpitched camera; at the views' 14° pitch that put up to ~0.6° of the probe's own error into each reading (senior review). The probe now inverts the full pitched projection (`pixel_bearing`, unit-tested against an independent forward projection).
   - **Light probe.** The environment pre-filters its light probe **once per Texture object**, so a sun change must build a fresh sky Texture.

   Re-run `--orient` after any Qt upgrade.
4. *Picking (criterion 7)*: a QML `pickAt` helper (`View3D.pick`) is checked against a CPU oracle (the topmost triangle under a vertical ray over every pickable mesh, merged per item) in a top-down orthographic view. The returned JS object arrives in Python as `QJSValue` (`.toVariant()`).
   - **Easy targets** (each item's highest unoccluded triangle): 20/20 at 0.15–0.24 ms median (container); 20/20 in the frozen exe on D3D11 (v4, v6; 0.19 ms median in v6). A picker that only tests bounding boxes would still score 18/20 on them (senior review), so they are not the evidence on their own.
   - **Adversarial targets**, points inside a tall item's bounding box but off its mesh, where a bounding-box picker names the wrong item: **10/10** on OpenGL (container) and on D3D11 (v6 frozen). A unit test pins that the generator really produces such points.
   - **Projection:** the click pixels come from the engine's `mapFrom3DScene`, so a wrong engine projection could aim and pick consistently wrong. An orthographic projection of our own agrees with it to **0.0 px**, and the picked point lies 0.0 cm from the target, on both backends (container; v6 frozen).
   - **Engine rule found on the way:** Windows v3 picked 0/20, reproduced on OpenGL. Once the Model using a `QQuick3DGeometry` is destroyed, handing that geometry to a new Model renders and picks nothing; the frame equals an empty scene's. `update()` does not restore it; a full re-upload of the data does. A `Repeater3D` over a JS array recreates **every** delegate on any array change, so a model present both before and after the change came back blank too. The spike re-uploads every previously shown geometry, and the probe compares the frame before the detach with the frame after the re-attach: mean absolute difference 0.0 on both backends (container; v6 frozen).
   - **Its texture twin** (caught by `--second-window`, diagnosed in senior review, pass 4): a `QQuick3DTextureData` detached from its `Texture` and attached again renders **white**. The IoU and orientation probes clear `groundTexture` for their measurement, and the restore set the same texture object back, so from then until the next project reload the plan ground drew white: mean difference 13.1 against the frame before the probe, all of it in the ground half (llvmpipe, 640×360). `update()` alone changes nothing; `setTextureData(textureData())` plus `update()`, or a fresh texture object, restores it (0.0). `preserved_state` re-uploads a detached ground, and every run checks the restore in pixels (`probe_restore_frame_diff` < 1, measured 9.83 before the fix and 0.0 after, with the IoU and orientation probes in the run; 0.0 in all three render-tier runs that probe at 479d78c, at 100 % and 150 % display scale, and 0.0 on D3D11 in Windows run v11; the render tier and the Windows driver both assert it).
   - **For L1.1/L1.3:** one geometry per Model lifetime, and per-item Model creation (or a list model with incremental inserts and removes) instead of re-assigning one array. **Reuse of a live Model (ADR-069, #531):** the first attempt (2026-11-01) assigned a NEW geometry object to a Model that was already drawing; that renders NOTHING while the item still picks, on both render tiers (0.0 IoU against its own mask), and was withdrawn. Loading new buffers into the geometry object the Model already has draws correctly (2026-11-24, ADR-069 addendum: the same frame as a fresh Model, 0 channels differ, D3D11 and WARP). So: one geometry object per Model lifetime, never a second one on a live Model; a regrown part reloads its own. (The cost measured here — handing one geometry object to a SECOND Model — still never happens.) A texture is re-uploaded whenever it is re-attached.
5. *Python geometry path (criterion 6)*: replacing a 100k-vertex geometry (`NumpyGeometry.set_mesh`: frame mapping, interleave, `QByteArray` copy) takes **10.5 ms median** in the container (n = 10, max 25 ms). On the Windows runners the same code took 14.4 ms (v3), 27.3 ms (v4) and 36.4 ms (v6, max 71.5 ms); runner instances differ by up to 2.5×. That is borderline against ≤ 10 ms; the owner's hardware decides, and the interleave copy is the first optimisation target.
   - **Scope of the number** (senior review): `set_mesh` covers the Python side only. The GUI thread also blocks during the next scene-graph sync, and with `QSG_RENDER_LOOP=basic` the whole render runs on it, so the criterion's main-thread budget is larger than this; L1.1 measures the full edit-to-frame path (≤ 50 ms p95).
   - The time to the next presented frame is recorded but is not a criterion number: on a software rasteriser it is the frame's own render cost.
   - "1,000 Models ≤ 300 ms" is not measured.
6. *Open time (criterion 5)*: `open_ms` runs from the user's request (project loaded, 3D asked for) to the **first finished readback**: ground bake, model build, QML load, scene apply, preset + mood + sun + camera (which builds the sky), then show to readback (`open_breakdown_ms`, checked two-sided: the buckets must explain `open_ms` within 100 ms). The first runs measured only show to the first `frameSwapped`, which marks submission; on a software rasteriser the real cost lands in the next readback (v3: 2.0 s "first frame", then a 68 s grab). Even show-to-readback left out the QML load and the scene build that the user waits through (senior review).
   - **Cold vs warm** is controlled and recorded (`shader_caches`): a run lists the Qt cache entries it found at start (`q3dshadercache`, `qtpipelinecache`, `qmlcache`, `qtshadercache`); `--cold` sets `QT_DISABLE_SHADER_DISK_CACHE`, `QSG_RHI_DISABLE_DISK_CACHE`, `QT_QUICK3D_NO_SHADER_CACHE_LOAD`, `QML_DISABLE_DISK_CACHE` and `MESA_SHADER_CACHE_DISABLE` (all present in the 6.11 runtime) and then neither loads nor writes a cache. A GPU driver keeps its own shader cache, which no flag reaches. Earlier "cold" numbers ran on whatever caches earlier runs had left.
   - **The sky was most of the CPU side** (senior review, round 3: ~3 s of open time sat in no bucket). `ProceduralSkyTextureData` regenerates the whole sky synchronously on the GUI thread for every input change (~190 ms each at high quality), and the spike bound its inputs live: one open built a default sky in the QML load, then regenerated it for each look and sun input. Built once per sun change instead (inputs set at low quality, then raised; frames bit-identical), measured once (llvmpipe, 640×360, golden hour; commit a275da2): QML load 1709 → 70 ms, `set_look` 791 → 0.1 ms, `set_sun` 2192 → 344 ms, so ~4.7 s → ~0.4 s of CPU per open. The numbers below, before this fix, include that cost; how much of the 2.5 s warm budget it would have taken on a GPU is not measured.
   - **Protocol (owner):** one run with `--cold`; then the same shot twice without it. The second of those is warm.
   - **Container** (llvmpipe, 320×180, under concurrent load): first launch into an empty cache home 49.4 s (show to readback 43.8 s, QML 1.8 s), the second launch 36.8 s with three cache entries found, `--cold` 35.5 s. Unloaded (senior review): first launch 24.1 s, warm 20.1 s, cold 23.6 s (show to readback 18.7 / 14.8 / 18.3 s), so warm is measurably faster even on a software rasteriser.
   - **Frozen Windows exe** (WARP, 960×540, show to readback): first frame 4.2 s, ready **63.0 s** (v6). The difference is the first sky light probe's prefilter (entry 14), paid in the first readback. v9, `open_ms`: first launch of the bundle 68.6 s (no caches found), warm relaunch 64.4 s (three caches found), `--cold` unfrozen 68.3 s; in each, the first grab is 57–59 s of it. On WARP the software prefilter swamps both cold vs warm and the sky's CPU cost (those runs predate the sky fix). v10, after the sky fix: QML load 1705 → 52 ms, and preset + mood + sun, which sat in no bucket in v9 (~3.0 s), 0.37–0.39 s; `open_ms` 77.7 s on the first launch, 60.2 s warm, 69.7 s cold unfrozen, the first readback 59–77 s of each. Runner-to-runner variance on WARP is larger than the 3.4 s the fix saved.
   - **A second 3D window in the same process** (`--second-window`, which renders the first window's view; the first version rendered the QML defaults, a different frame): not faster to its first readback (v6 frozen: ready 63.7 s vs 63.0 s; v9 65.3 s). It measures a window the product will not have. Since the fix below, its frame matches the first window's (mean difference 0.0 with the IoU probe in the same run, on llvmpipe and on D3D11 in v11). The 9.75 it read in v9 (9.8 on llvmpipe) was a real defect, which the comparison caught: the first window's ground had been white since the IoU probe (entry 4, the texture twin). It was first misdiagnosed as a stale reference frame and "fixed" with a settle wait; the run that validated that fix left out `--iou`, the trigger, so it proved nothing (senior review, pass 4).
   - **Re-showing a hidden host** to its next presented frame: 6–7 ms median (container), 31–60 ms (Windows v3, v4, v6).
   - All of this is software rendering; criterion 5 (cold ≤ 6 s, warm ≤ 2.5 s) is decided on the owner's GPU.
   - **Consequence for L1.3:** keep one 3D host alive.
7. *Graphics API coexistence (criterion 2, M1)*: in one process, with WebEngine imported before `QApplication` as `main.py` does, a `QWebEngineView` page keeps its exact colour before and after a 3D frame (`--coexist`). This holds on OpenGL (container) and in the **frozen Windows exe on `Direct3D11Rhi`**. `AA_ShareOpenGLContexts` reads False after that import. **The 3D half:** the 3D frame rendered with WebEngine alive equals the same view rendered before WebEngine started, mean absolute difference **0.0** against a reference with luma std 57.9, so not an empty frame (container), and 0.0 against luma std 59.5 in the frozen exe on `Direct3D11Rhi` (v6). The first version accepted "mean luma > 20", which an empty top-down frame over the white clear colour also passes (senior review).
   - **Not measured in L0** (senior review): the criterion's "map picker works before *and after* the 3D view in the same session". The probe samples its page only after the 3D view has been on screen; the spike cannot open the real picker, and the app cannot show Quick 3D yet. The owner run was meant to show the picker works in the bundle that carries Quick 3D, but it did not separately re-walk the picker (entry 19); the full check needs both in one app session: L1.3.
8. *Embedding cost (criterion 3, M2)*: 2D canvas pan step with event processing, `bench_small`, 120 steps, without and with a `QQuickWidget` in the same window:

   | Where | Without 3D widget | With 3D widget | Ratio |
   |---|---|---|---|
   | Container (software composition) | 5.5 ms | 7.9 ms | **×1.42** |
   | Windows WARP, frozen, run v3 | 2.8 ms | 15.9 ms | ×5.7 |
   | Windows WARP, frozen, run v4 | 4.4 ms | 15.8 ms | ×3.6 |
   | Windows WARP, frozen, run v6 | 8.0 ms | 15.9 ms | ×2.0 |

   With the widget present, one pan step took 36 s (v3), 47 s (v4) and 56 s (v6): the first composition after the 3D widget appeared. All of this is software composition, so the owner's hardware decides. The evidence so far favours the policy outcome, the `QQuickView` container host, for the split view. A synchronous `repaint()` does not include the flush; that first measurement read ×0.014.
9. *Frame rate (criterion 4)*: software rasterisers only, not GPU numbers. Frame counts on a software rasteriser say little about cost (entry 6).
   - Mesa llvmpipe, 1280×720, `bench_small`: low 6.3, medium 1.75, high 1.28, ultra 1.2 fps.
   - Frozen exe on WARP, 960×540: low 14.2 / 11.5 / 7.2, high 4.8 / 4.3 / 3.7 fps (v3 / v4 / v6). Between v4 and v6 the creator round (75a6128) gave the low preset a larger shadow map, one cascade and FXAA, and the runner instance changed too; the drop is not isolated.
10. *Stability (criterion 10)*: `--soak N` runs N hide/show cycles; every fifth cycle empties the scene and refills it. Then the window closes while the wind animation runs.
    - **Close while animating:** 8 frames with the animation on, where `windTime` and the frame counter must advance, then a real window close and `app.quit()` inside `app.exec()`. The witness is the **process exit code**, 0 on OpenGL (container) and in the frozen exe on D3D11 (v6): a crash on that path takes the process down. (`app.exec()` itself returns 0 on both quit paths, so its own return value is informational only.) The first version returned a literal `True` while the animation never ticked (senior review).
    - **Project reloads** (after v6): the refill is a full reload, the plan read from disk into a new scene, the ground re-baked and every model and geometry built new while the engine runs. So `--soak 50` is the criterion's "50 show/hide cycles, 10 project reloads". Container (llvmpipe, 640×360, render tier): 10 reloads at 562 ms median, RSS after each refill flat at 1695 → 1699 MB (slope −0.01 MB/reload), exit 0. Frozen exe on D3D11: 10 reloads at 1.2 s median and exit 0 in v7 and v8.
    - **v7 and v8 could not decide leaks on D3D11** (senior review, round 3). v7 read the Windows working set, which the OS trims and regrows (800 → 707 → 766 MB); a trimmed working set cannot rule a leak in or out, so v7 is inconclusive, and its least-squares tail slope of 10.9 MB/reload (Theil–Sen 9.9) failed the gate. v8 read private bytes: they *fell* over the 10 reloads (1062.7 → 997.8 MB, least squares −7.1 MB/reload), but the Theil–Sen slope over the last five read 11.1 MB/reload and failed again. Five points cannot resolve 10 MB/reload against WARP's ±30–60 MB swings. Neither run shows a leak, and neither rules one out.
    - **The gate, fixed before run v9 is read** (no further re-fitting): private bytes on Windows, RSS on Linux; the Theil–Sen slope over the second half of the reloads below 10 MB/reload; in CI with **20 reloads** (`--soak 100`), so ten points carry the slope. It counts as evidence only together with its **positive control on the same runner**: the same soak with 25 MB kept alive per reload (`--soak-leak-mb 25`) must fail on exactly that gate (driver `--expect-leak`); the render tier runs the same control on llvmpipe. If the control does not fire, or the clean run fails, criterion 10's leak half is judged on the owner's machine alone. Private bytes do not see dedicated GPU memory, so on a discrete GPU the gate is blind to VRAM leaks.
    - **v9 on the pre-registered gate** (D3D11, frozen exe, 100 cycles with 20 project reloads, private bytes): the Theil–Sen slope over reloads 11–20 is **1.5 MB/reload** (< 10), exit 0, zero Qt messages. That shows **no trend of 10 MB/reload or more over the last ten reloads**, and no more. The curve is not flat: private bytes fell 133 MB after the first reload (1026.5 → 893.4 MB), then grew **+129 MB over reloads 2–20** (893.4 → 1022.1 MB), almost all of it by reload 12, and flattened there (1017.4 → 1022.1 MB over reloads 12–20). The Theil–Sen slope over all 20 points is 7.3 MB/reload. **The cause of that growth is not explained** (the eleven-run table and the longer soaks below).
    - **The control, as it ran:** on the same runner, with the same 100 cycles and 20 reloads and 25 MB kept alive per reload, but at 640×360 and without the probes (the clean run: 960×540 with every probe; the probes run before the soak). It read **33.6 MB/reload** and failed on exactly that gate, as it must. What the gate can resolve comes from the clean runs' own intervals over reloads 11–20: 3.3–9.8 MB/reload wide in v9–v19, so it separates "no trend" from 25 MB/reload in every run, and from 5 only where the interval is narrower than 5 MB/reload (v10, v11, v13, v15, v19); those intervals exclude zero in 8 of the 11 runs (v9's, −1.70 to 4.18, v18's, −0.68 to 6.65, and v19's, −0.60 to 4.13, do not).
    - **v10, the same gate** (a275da2): 3.8 MB/reload over reloads 11–20; private bytes +73 MB over reloads 2–20 (977.5 → 1050.9 MB, lowest 928.9 at reload 4), Theil–Sen over all 20 points 4.7. Its control read 29.5 MB/reload for the 25 MB it held.
    - **v11, the same gate** (479d78c): 4.0 MB/reload over reloads 11–20; Theil–Sen over all 20 points 3.5. Its control read 28.7 for 25 MB held.
    - **v12, the same gate** (e862785, the first run with creator round 3): **9.0 MB/reload**, a pass but near the bound; its control read 28.3.
    - **The shape on D3D11, eleven runs** (private bytes, frozen exe, 20 reloads each). An earlier version of this entry netted reloads 2–20 to +129 / +73 / −59 MB and concluded that the drift "did not keep its sign"; that hid the pattern every run shows:

      | Run (commit) | Tail gate, reloads 11–20 | Dip: reload 1 → lowest | Rise: lowest → reload 20 | Reloads 12 → 20 | Control, 25 MB held |
      |---|---|---|---|---|---|
      | v9 (6ea2d17) | 1.5 MB/reload | −133 MB by reload 2 | +129 MB over 18 reloads (7.2 per reload) | +5 MB | 33.6 |
      | v10 (a275da2) | 3.8 | −111 MB by reload 4 | +122 MB over 16 (7.6) | +22 MB | 29.5 |
      | v11 (479d78c) | 4.0 | −146 MB by reload 5 | +72 MB over 15 (4.8) | +32 MB | 28.7 |
      | v12 (e862785) | **9.0** | −136 MB by reload 5 | +147 MB over 15 (9.8) | +83 MB | 28.3 |
      | v13 (cf7eb66) | 1.8 | −94 MB by reload 5 | +83 MB over 15 (5.5) | +20 MB | 32.9 |
      | v14 (f1b998e) | 3.4 | −135 MB by reload 5 | +112 MB over 15 (7.5) | +34 MB | 30.9 |
      | v15 (831f808) | 7.5 | −125 MB by reload 4 | +103 MB over 16 (6.4) | +54 MB | 31.2 |
      | v16 (f71cdef) | 4.2 | −128 MB by reload 5 | +90 MB over 15 (6.0) | +24 MB | 32.4 |
      | v17 (308c773) | 5.1 | −106 MB by reload 5 | +121 MB over 15 (8.1) | +68 MB | 29.2 |
      | v18 (46d88ff) | 3.5 | −141 MB by reload 5 | +77 MB over 15 (5.1) | +48 MB | 28.3 |
      | v19 (123f0af) | 1.5 | −118 MB by reload 5 | +73 MB over 15 (4.9) | +9 MB | 29.9 |

      - **The dip** is consistent with memory the probes held and released during the soak: the controls run no probes and never dip (their lowest reading is reload 1 in all eleven runs). They also run a smaller window (640×360 against 960×540), so the probes are not isolated as the cause.
      - **The rise** follows in every run, at 4.8–9.8 MB per reload. The controls read 28.3–33.6 MB/reload for the 25 MB they hold, and every WARP interval lies above 25 (the lowest bound 25.9, v12 and v17). A control interval above 25 does not by itself show the rise: one Linux control (a64ae9e, 25.6–35.4) excludes 25 while its clean run read 0.01. v12 had not flattened by reload 20.
      - **Not Python-side growth of WARP's size, over the gate's window:** over reloads 11–20 the same gate on llvmpipe RSS read 0.00–0.46 MB/reload in the clean run of every render-tier run named by commit: 479d78c 0.02, 36e3d18 0.46, a64ae9e 0.01, f71cdef 0.00, 308c773 0.00, 46d88ff 0.00 (all but 479d78c committed as [`container-render-tier-soaks.json`](adr-048-evidence/container-render-tier-soaks.json)), where WARP read 1.5–9.0. No Linux soak runs past reload 20. A D3D11 resource retained per reload on the spike's path, or a driver cache, is not ruled out and not measured.
      - **What the 20-reload gate decides:** it passed in every run (v9–v19), so criterion 10's gate holds as pre-registered. It cannot tell whether D3D11 memory keeps growing: identical code read 9.0 and 1.8 MB/reload (v12, v13; round-3 code) and 3.4 and 7.5 (v14, v15; round-4 code); v16–v19, the same soak path, read 4.2, 5.1, 3.5 and 1.5.
    - **v13 and v15 repeat earlier code** (cf7eb66 and 831f808 changed only docs and the workflow), and **v16–v19 run the same soak path** (f71cdef changed the probe restore's re-upload, comments and two named constants of unchanged value, on top of the merge with master; 308c773 flag parsing, a probe-only restore check and the harvest-window anchor, which changes no bench frame; 46d88ff removed that check; 123f0af changed a docstring and the CI driver's label): every check green, probe restore and second window 0.0, controls 32.9, 31.2, 32.4, 29.2, 28.3 and 29.9 for 25 MB held.
    - **Longer soaks** (an experiment that does not gate: 640×360, no probes, no injected leak). v14 and v15 are identical code; v16–v19 run the same soak path: of the functions a reload executes, only `in_harvest_window` changed (it gives the bench the same answers on the soak's date), two constants were hoisted at unchanged values, and the merge with master added a function to `app/settings.py` that a reload does not call.

      Intervals in this entry are Sen's normal-approximation rank intervals (floor/ceil ranks, no tie correction) over the stated reloads of one run. They assume independent residuals (the lag-1 autocorrelation of the long soaks' Theil–Sen residuals over reloads 51–100, classic ACF estimator, is 0.17, 0.69, 0.59, 0.24 and 0.71 in v15–v19, so v16's, v17's and v19's intervals in particular are too narrow), and they describe that run only: identical code gave non-overlapping gate intervals in v12 (4.10–13.87) and v13 (0.25–3.54).

      | Run (code) | Reloads | Reload 50 − reload 1 | Decade means (MB) | Theil–Sen, second half (95 % interval) |
      |---|---|---|---|---|
      | v13 (round 3) | 50 | +87 MB | 605.0 / 639.1 / 663.6 / 666.9 / 688.4 | 1.22 MB/reload (0.71–1.89), reloads 26–50 |
      | v14 (round 4) | 50 | +196 MB | 637.9 / 688.9 / 744.0 / 781.2 / 825.7 | 3.78 (2.92–4.66), reloads 26–50 |
      | v15 (round 4) | 100 | +62 MB | 624.2 / 645.0 / 672.1 / 684.6 / 688.0 / 690.1 / 692.7 / 696.0 / 696.6 / 699.2 | 0.21 (0.13–0.29), reloads 51–100 |
      | v16 (round 4) | 100 | +134 MB | 635.5 / 667.8 / 700.6 / 739.5 / 753.3 / 760.9 / 763.1 / 785.2 / 807.5 / 837.3 | 2.03 (1.77–2.27), reloads 51–100 |
      | v17 (round 4) | 100 | +210 MB | 635.8 / 679.2 / 733.0 / 763.0 / 814.0 / 843.6 / 888.2 / 917.1 / 947.1 / 970.5 | 3.05 (2.80–3.25), reloads 51–100 |
      | v18 (round 4) | 100 | +103 MB | 638.9 / 666.1 / 693.5 / 716.7 / 729.0 / 729.5 / 731.5 / 733.2 / 737.0 / 731.7 | 0.08 (−0.01–0.18), reloads 51–100 |
      | v19 (round 4) | 100 | +222 MB | 632.5 / 671.7 / 736.8 / 779.3 / 832.0 / 883.9 / 912.2 / 934.8 / 989.2 / 1018.0 | 3.50 (3.24–3.74), reloads 51–100 |

      - **What it shows**, in numbers only: identical code rose +196 MB by reload 50 in v14 and +62 MB in v15, a factor of 3.2; on the same soak path the rise at reload 50 ranged +62 to +222 MB (v15, v19). Over reloads 51–100 (the interval column), four of the five 100-reload runs had a slope whose 95 % interval lies above zero: v15 0.21 MB/reload, its maximum 704.6 MB at reload 89 and 695.3 at reload 100; v16 2.03 MB/reload, +82.5 MB from reload 51 to 100; v17 3.05 MB/reload, +153.3 MB from reload 51 to 100, its maximum 991.9 MB at reload 100; v19 3.50 MB/reload, +193.8 MB from reload 51 to 100, its maximum 1037.5 MB at reload 100. v18's slope was 0.08 MB/reload, an interval that includes zero; its maximum was 741.2 MB at reload 82 and it read 729.3 at reload 100 (over reloads 81–100: −0.43, interval −0.71 to −0.26). Step by decade: v13 +34 / +25 / +3 / +22 MB; v14 +51 / +55 / +37 / +44; v15 +21 / +27 / +12 / +3 / +2 / +3 / +3 / +1 / +3; v16 +32 / +33 / +39 / +14 / +8 / +2 / +22 / +22 / +30; v17 +43 / +54 / +30 / +51 / +30 / +45 / +29 / +30 / +23; v18 +27 / +27 / +23 / +12 / +1 / +2 / +2 / +4 / −5; v19 +39 / +65 / +43 / +53 / +52 / +28 / +23 / +54 / +29. v16 stayed within 15 MB over reloads 48–71 (Theil–Sen 0.05), then went from 768.1 MB at reload 71 to its maximum, 848.0 MB at reload 99.
      - **Three corrections**, one per review pass (5–7): a ceiling read from two 50-reload curves, although a flat ten-reload stretch inside v13's curve (reloads 23–37) was followed by more growth; then a slowdown read from v15 alone, which v16 contradicts; then a 9.7-fold difference in the late slope called threefold, between runs called the same code that are the same soak path, and a v15 "still rising at reload 100" that its last 20 reloads cannot show (95 % interval over reloads 81–100: −0.15 to 0.40). The record now gives numbers, not shapes.
      - **The cause is not identified.** Over reloads 11–20 the same gate read 0.00–0.46 MB/reload on Linux (llvmpipe RSS), where WARP read 1.5–9.0: over that window this rules out Python-side growth of WARP's size in the spike's own objects, and no Linux soak runs past reload 20 to set beside reloads 51–100. It does not rule out a D3D11 resource retained per reload on the spike's path: WARP keeps GPU resources in system memory, where private bytes see them, and on the owner's discrete GPU they would sit in VRAM, which private bytes do not see.
      - **So criterion 10's leak half is open on D3D11.** An A/B soak (ground re-bake off, geometry rebuild off) would locate the growth; a longer soak would not.
      - **How it closes.** The owner's run cannot close it, only add to it: a GPU resource sits in a discrete GPU's VRAM, which private bytes do not see, while a runtime or driver allocation in system memory would show whether WARP's growth reproduces on real hardware. The spike's share of criterion 10 as written (show/hide cycles, project reloads, close while animating: zero aborts) holds; the full pytest run with the production view is L1.3's. The leak half closes in L1.3, whose production-view soak runs that A/B and adds a dedicated-GPU-memory reading (for example DXGI `QueryVideoMemoryInfo`; not yet tried) under the same pre-registered slope gate. A GO before then accepts the open half explicitly, and the decision records it (senior review, passes 6–7).
    - **Container render tier** (llvmpipe, 640×360, 479d78c), the same gate on RSS: 0.02 MB/reload over reloads 11–20, +4.7 MB over reloads 2–20 (1715.6 → 1720.3 MB), Theil–Sen over all 20 points 0.24. Its control read **25.0 MB/reload** for the 25 MB it held; the five later runs named above read 26.97, 27.85, 28.24, 24.5 and 26.28. Four of their five intervals include 25 (36e3d18 20.6–33.0, f71cdef 18.9–36.7, 308c773 16.6–27.3, 46d88ff 23.7–29.6); a64ae9e's, 25.6–35.4, does not. Until pass 4 that control ran 5 reloads at 320×180, a two- or three-point slope and so a smoke check rather than a control (senior review); it now runs the pre-registered 20 reloads in the clean run's window.
    - **A leak the reloads found, in the spike's own code:** RSS grew linearly, one baked ground (2400×1600 RGBA ≈ 15 MB plus its GPU copy) per reload, 771 → 1035 MB over 10 reloads. `set_ground()` appended every texture to an append-only keep-alive list. Holding only the shown texture settles at ~885 MB; an A/B on llvmpipe isolated it, and the engine and the geometries released their memory. Both variants grew ~70 MB on the first reload, so the soak gates the RSS **slope over the second half of the reloads** (< 10 MB/reload), not the total growth (PF-E3D-04).
    - **Earlier soaks** (same models re-set, no reloads): 10 cycles in the container, 1010.0 → 1010.2 MB; 20 cycles in the frozen exe, 723.6 → 731.5 MB (v4) and 692.0 → 725.4 MB (v6).
    - **Not covered by the spike:** a full pytest run with the production 3D view (L1.3).
11. *Size (criterion 9)*: Windows dist built from this branch and from master in the same job: **626.2–626.3 MB vs 624.5 MB = +1.7 MB**, the same in v2–v6, with 5–6 new files (v6 adds the creator's `water.frag`; output committed as [`windows-v6-footprint.txt`](adr-048-evidence/windows-v6-footprint.txt)). The Qt Quick 3D runtime (Quick3D + ShaderTools, 21.1 MB) **already ships** with today's bundle; only `QtQuick3D.pyd` and the spike's QML files are new. Qt 3D's own DLLs are 5.8 MB.
    - **Baseline method:** the master baseline was checked out over the branch tree in overlay mode, which left `spike_q3d/` in it. That is harmless because master's spec does not collect the folder; from v6 the baseline is a true replacement, and the delta did not change.
    - **Side finding (§11.3):** master's release already ships about 21 MB of Qt Quick 3D runtime it never loads.
12. *Packaging (criterion 1, CI half)*: the frozen Windows exe with the spike bundled passes the unchanged `--selftest` gate (v1). It renders `bench_small` through Qt Quick 3D on Direct3D 11 (v3, v4 and v6, golden hour low and high).
    - **Gap:** the release `--selftest` does **not** import `QtQuick3D` (it checks the Qt 3D bindings), so a broken Quick 3D bundle would ship green today. L1.2 must extend `--selftest`; this is the #277/#291 lesson.
    - The 8-second normal-start smoke of the bundle with the spike passes (v6).
13. *SSGI*: `ssgiEnabled` renders a black frame on Mesa llvmpipe (isolated by toggling SSGI and SSR separately); SSR renders. SSGI is opt-in until verified on a real GPU.
14. *Windows evidence runs* (windows-latest, no GPU, Direct3D 11 on WARP):

    | Run | Run ID | Result |
    |---|---|---|
    | v1 | 37159256533 | Hung for 56 min with no output. |
    | v2 | 37187375015 | Logged the cause: frames arrived about once a second, but one `grabWindow()` of the sky-lit scene took ~100 s. The frozen run failed on a missing `--plan`. |
    | v3 | 37188274098 | Exit 0 everywhere, but it picked 0/20 (entry 4). "Green" meant only the exit code. |
    | v4 | 37189802755 | After the re-attach fix: picks 20/20, and 20/20 after re-attach. One frame wait timed out (golden hour high got 3 of 6 frames in 45 s). |
    | v5 | 37191065475 | Refactor-only re-run of v4's probes; green, not extracted. |
    | v6 | 37199625103 | The first run judged on the thresholds: 20 of 21 checks passed, no frame-wait timeouts. The one FAIL was the driver's own bug: `(x or 99) < 1.0` read the measured 0.0 px projection error as 99. |
    | v7 | 37201554005 | Soak 50 with 10 project reloads: 31 of 32 checks passed. The leak gate failed reading the working set; inconclusive on leaks (entry 10). |
    | v8 | 37203468689 | 32 of 33 checks passed with zero Qt messages; first launch found no caches, the warm relaunch found three. The leak gate, now on private bytes, failed on five noisy points; inconclusive on leaks (entry 10). |
    | v9 | 37206644502 | **Green on every threshold:** the full set (38 checks), the warm relaunch, the cold unfrozen run and the leak gate's positive control, which fired as it must. Zero Qt messages; dist +1.8 MB. Entry 10 says what the leak gate does and does not show. Its second-window frame read 9.75, which no check covered then: the white ground of entry 4. |
    | v10 | 37209726610 | All 39 checks of the full set green, plus the warm relaunch, the cold unfrozen run and the leak control; dist +1.8 MB. But its second-window frame read **9.72**: the settle wait committed in a275da2 had not fixed the white ground (entry 4), as senior review predicted for this run, and no check covered the field yet. The sky fix on D3D11: QML load 1705 → 52 ms, preset + mood + sun ~3.0 s → 0.39 s. |
    | v11 | 37213201005 | **Green on every threshold, 41 checks**, with the two frame checks of senior pass 4: the probes leave the view as they found it (0.0) and the second window renders the first one's view (0.0) on D3D11. Leak gate 4.0 MB/reload, its control 28.7; warm relaunch, cold unfrozen run, zero Qt messages, dist +1.8 MB. |
    | v12 | 37216442834 | The first run with creator round 3 (e862785): **green on every threshold, 41 checks**; probe restore 0.0 and second window 0.0 on D3D11; IoU low 0.970 / 0.963 / 0.937, high 0.980 / 0.984 / 0.963; sky 0.39°. Leak gate **9.0 MB/reload**, a pass near the bound (entry 10); its control 28.3; dist +1.8 MB. |
    | v13 | 37285285890 | The same spike code as v12: **green on every threshold, 41 checks**, probe restore and second window 0.0. Leak gate **1.8** MB/reload (v12: 9.0), its control 32.9. The 50-reload experiment rose +87 MB by reload 50 (entry 10). dist +1.7 MB. |
    | v14 | 37293091187 | The first run with creator round 4 (f1b998e): **green on every threshold, 41 checks**; probe restore and second window 0.0; IoU low **0.984 / 0.982 / 0.964** with the VeryHigh low-preset map (v12: 0.970 / 0.963 / 0.937), high 0.981 / 0.984 / 0.963; sky 0.75°; isolated dark pixels 0 and 5 on the golden-hour frames (golden hour cannot tell sharpening on from off; the render tier gates noon and December, and Windows does not gate it). Leak gate 3.4, control 30.9. The 50-reload experiment rose +196 MB by reload 50 (entry 10). dist +1.7 MB. |
    | v15 | 37296804412 | The same spike code as v14: **green on every threshold, 41 checks**, probe restore and second window 0.0, IoU identical to v14. Leak gate **7.5** MB/reload (v14: 3.4), control 31.2. The 100-reload experiment rose +62 MB by reload 50, with a slope of 0.21 MB/reload over reloads 51–100 (entry 10). dist +1.7 MB. |
    | v16 | 37301609487 | f71cdef, after the merge with master (v1.29.2) and senior pass 5's fixes: **green on every threshold, 41 checks**, with the restore check now required whenever `--iou` or `--orient` ran; probe restore and second window 0.0; IoU and sky identical to v14 and v15. Leak gate **4.2** MB/reload, control 32.4. The 100-reload experiment rose +134 MB by reload 50, with a slope of 2.03 MB/reload over reloads 51–100, and stayed within 15 MB over reloads 48–71 (entry 10). dist +1.8 MB. |
    | v17 | 37308218700 | 308c773, senior pass 6's fixes: **green on every threshold, 41 checks**; every run records the flags it parsed (`args`), and abbreviated flags are refused; probe restore and second window 0.0; IoU and sky identical to v14–v16. Leak gate **5.1** MB/reload, control 29.2. The 100-reload experiment rose +210 MB by reload 50, with a slope of 3.05 MB/reload over reloads 51–100 and its maximum at reload 100 (entry 10). dist +1.8 MB. |
    | v18 | 37312863784 | 46d88ff, the PR head when draft #413 was opened: **green on every threshold, 41 checks**; probe restore and second window 0.0; IoU and sky identical to v14–v17. Leak gate **3.5** MB/reload, control 28.3. The 100-reload experiment rose +103 MB by reload 50; over reloads 51–100 its slope was 0.08 MB/reload, an interval that includes zero, with its maximum at reload 82 (entry 10). dist +1.8 MB. |
    | v19 | 37317036835 | 123f0af, senior pass 8's fixes: **green on every threshold, 41 checks**, the leak gate under its new label; probe restore and second window 0.0; IoU and sky identical to v14–v18. Leak gate **1.5** MB/reload, control 29.9. The 100-reload experiment rose +222 MB by reload 50, with a slope of 3.50 MB/reload over reloads 51–100 and its maximum at reload 100 (entry 10). dist +1.8 MB. |

    - **Cost of a new sky light probe on WARP:** the first frames or grab after each sun change take 40–85 s. Later grabs of the same sky take 20–500 ms, and the basic render loop changes nothing (69 s vs 68 s). On a GPU this is a prefilter pass. For L1.4: rebuild the probe only when the sun has moved noticeably, and give the software fallback no image-based light.
    - **From v6** the driver judges the run on the thresholds, not only on the exit code. After v6 the evidence chain fails closed (senior review, round 2):
      - The driver checks numbers explicitly: a missing or null metric fails, a zero passes. A probe whose flag was given but which wrote nothing fails. The verdict has unit tests with a perfect run and one broken threshold each.
      - **Every Qt message is recorded** in `spike.log` and `metrics.json`. A shader that does not compile, or a QML error, ends the run with status `qt_errors` and exit 4 (not 3, which the MSVC CRT's `abort()` also returns on Windows). Before, renaming one function in `water.frag` left `status: ok` and exit 0 while the pond changed colour, and the message only reached stderr, which the frozen exe does not have. A render test breaks the shader on purpose as the positive control.
      - The soak gates the memory slope over the project reloads (entry 10, with its positive control), and the baseline step fails a dist delta above 60 MB.
      - The driver also fails on any Qt warning (clean runs emit none, measured on llvmpipe and on D3D11 in v8), checks that a first launch found no shader caches and a relaunch found some, and checks the soak's cycle and reload counts.
      - Not asserted: frame rates, timings and the pan ratio. Those are software-rasteriser numbers and decide nothing (entries 4–9).
15. *Licence (criterion 12)*: `PyQt6` 6.11.0 declares `GPL-3.0-only`; the `PyQt6-Qt6` 6.11.0 wheel, which carries the Qt Quick 3D runtime, ships an LGPL v3 licence file. Both are compatible with OGP's GPL-3.0; third-party notices name Qt Quick 3D when L1.2 ships it.
16. *Beauty (criterion 11)*: the Beauty Board of `bench_small` (golden hour, noon, morning, December noon, night and walk at low/medium/high/ultra, with the shipped Qt 3D view as "before") was sent to the owner on 2026-10-03.
    - **First `ogp-3d-reviewer` pass** (2026-10-04, commit 0990371): **REJECT the board, not the engine.** Every engine truth probe passed, but the spike's own code had four truth defects: mirrored roof-slab normals, the December shot built with June plants, 11 built objects over the ±3 % height gate, and the geometry re-attach bug. It also had look defects: a horizon seam and fog band, a night "island", lawn hue −16°, the pond, floating flower heads, trunk banding, and low-preset shadow acne.
    - **`ogp-3d-creator` round 1** (75a6128) fixed all of them, each measured before and after on the board.
    - **Pass 2: APPROVE WITH CHANGES.** The four truth defects are resolved, each pinned by a gate. Three P1s remained: a hard horizon at the low preset, a moon-shadow staircase on the house's gable, and a December frame that read as midsummer. **Creator round 2** (b92a28c) fixed them: fog at every preset (horizon cliff 84.5 / 65.8 / 27.4 → 2.8 / 0.4 / 3.6 luma), filtered moon shadows, and fruit and blooms only in the plan's frost-free season.
    - **Pass 3** (a275da2): **APPROVE WITH CHANGES**, one P1: trees over the 25,000-triangle budget. **Creator round 3** (cherry-picked as 36e3d18) puts every tree of both bench plans on both board dates within it (bench_large June max 40,954 → 24,872) with fewer, larger leaves where capped, and moves the light rig to continuous ramps (December noon clipping 2.45 → 1.56 % at low). Fruit now follows each species' harvest window (entry 18).
    - **Pass 4** (e862785): **APPROVE WITH CHANGES.** Round 3 resolved the budget P1 (re-measured to the triangle, max 24,982), and every truth gate passes. The reviewer's e862785 board is bit-identical to the creator's, and 479d78c leaves every board and probe frame bit-identical to a275da2. One P1 remained, **pre-existing since 6702c22 and missed by passes 1–3**: `sharpnessAmount: 0.08` overshoots into near-black, red-less pixels, 1,500–3,100 per daytime frame (teal-black slits in the picket fences, black stubble on lawns and crowns); at 0.0 they drop 83–99 % with mean luma unchanged (measured). P2s with measured fixes: the 6° golden sun brighter than noon (December clipping 1.56 → 0.37 % at 1.9), an unbounded wood budget at wide aspect (32 of 448 swept trees over 25,000), heavy flower centres, ridge-cap scallops at the low preset, and no shot at the real 6° golden light. **Creator round 4** takes them, followed by pass 5 (owner sign-off came 2026-10-05; entry 19).
    - **Creator round 4** (cherry-picked as 5032135):
      - sharpening off: isolated dark pixels at 1280×720 low, noon 1,554 → 260 and December 2,587 → 28; a render-tier gate fails on the old 0.08 (737 and 700 against a bound of 170, clean frames 38 and 42);
      - the golden sun at 1.9, never brighter than noon: December clipping 1.56 → 0.27 %;
      - wood bounded by construction: 32 → 0 of 448 trees over 25,000 in the reviewer's scratch sweep (not committed; the committed tests cover the bench plans and wide crowns);
      - octahedron flower centres;
      - a VeryHigh shadow map at low: ridge-cap scallops 25 → 2 columns, low IoU 0.953 / 0.959 / 0.922 at 1280×720;
      - a `sunset` shot at 5.9°, the golden anchor of the rig.
    - **Pass 5** (f1b998e): **APPROVE**, no P0 or P1. The reviewer's own board is bit-identical to the creator's (21 of 21 PNGs), and every round-4 claim reproduced: isolated dark pixels as above, December clipping 0.27 % at both presets (noon: 0.25 %), 0 of 448 swept trees over budget against a hand-checked bound of 22,466, ridge-scallop columns 25 → 2, and the sunset shot on the golden anchor with truthful shadow directions. It confirmed that none of its pass-4 numbers came from a render that imported the main checkout's code (PF-E3D-04). Open P2s, deferred to L1: the trampoline mat reads tan in low sun (the broad specular sheen of the shared vertex-colour material; a rubber material measured 97 → 70 luma at golden hour); the roof's tile courses; meadow value noise. `sharpnessAmount` has no clean middle value (0.03 overshoots nearly like 0.08), so it stays at 0, and the frames lost 16–29 % of their edge energy (an owner question).

17. *Custom materials*: the pond's `water.frag` samples the image-based light through Qt-internal shader-library functions (`qt_sampleDiffuse`, `qt_sampleGlossy`, guarded by `QSSG_ENABLE_LIGHT_PROBE`), not documented built-ins, so a Qt upgrade (Package L7 plans 6.12) can break it silently. Since a shader error now fails the run (entry 14), the render tier and the Windows run check it on OpenGL and D3D11; production adopts it only with that check in its own render tests and a line in the L1 ADR.
18. *What L1 inherits, and how the owner measures*:
    - **Inherited as findings, not as code:** the engine rules (entries 3, 4, 6, 10, 14, 17) and the measurement methods. The spike's ~3.3k lines of evidence tooling and prototype builders (`spike_q3d/meshes.py`) are a prototype; L1.6/L1.7 rebuild the builders with product-grade gates, and the evidence tooling is deleted with the spike.
    - **Two L0 simplifications that must not survive into L1** (senior review, pass 4):
      - *Flowers follow one plan-wide season.* Since creator round 3, fruit follows each species' harvest window as the agent's task tools compute it (`get_tasks`, `get_task_calendar`, through `services/task_generator.generate_for_date_window`): the plan's last spring frost plus `harvest_start` … `harvest_end` weeks, anchored on every frost year whose window can reach the date (a 29 February frost: leap years only, and none at all when the year it is parsed for lacks that date; in such a year the spike keeps the frost-free season, so it shows fruit where the generator lists none), the range derived from the offsets (`runner.in_harvest_window`, pinned day by day against it, asparagus and a southern plan included). Every GUI task surface (the planting calendar's Gantt and dashboard, the Tasks tab) anchors on one year, a split in the product that predates the spike (TD-037; senior review, pass 6). An earlier ±1-year anchor in the spike returned False on every asparagus harvest date at frost dates from 4 January on, and on rhubarb's from 1 January until just before the frost's anniversary (291 of 1,096 harvest days in 2026–2028 at a 04-09 frost, 783 at 09-20); neither has a fruit look, so no frame changed: `accents_in_season`, the window's only consumer, returns the frost-free season for a species without one, and a sweep of that decision over 140,288 combinations (the 64 bundled species with harvest weeks, frosts 04-09 and 09-20, every day of 2026–2028) found none different (passes 7–8). For the bench: at Berlin tomatoes fruit 18 June – 27 August, and the 21 June board shows no sweet peppers (2 July – 13 August). A species without harvest weeks falls back to the frost-free window: the bench's apple, cherry, pear and plum have none, so they fruit from 9 April to 31 October. Flowers still follow the plan's frost-free window (`runner.in_frost_free_season`), for every plant at once, so forsythia, magnolia and tulips bloom all summer. L3.5 derives per-plant phenology (`core/phenology.py`).
      - *The Beauty Board is safe by order, not by design.* `_run` grabs the board before any probe. Before the ground re-upload fix (entry 4), every frame after `--iou` or `--orient` had a white ground, and only that order kept the board clean. The pixel check on every restore (`probe_restore_frame_diff`) now makes the order irrelevant; L1's render tests keep that check.
    - **Owner protocol** (criteria 3–6 cannot be judged on a machine CI has; exact commands in the evidence PR): run the frozen bundle with the full flag set and `--cold`, then twice with the same shot and no `--cold` (the third run is the warm one), at 1080p on the dedicated GPU, and with `--presets low,medium` on an integrated GPU if available. Low carries a VeryHigh shadow map since creator round 4 (llvmpipe fps at low: 4.90 before, 4.97 and 4.70 after in one run each by the creator and the reviewer, so within run-to-run noise); if it costs more than about 10 % on the integrated GPU, low goes back to the High map and accepts faint ridge scallops. `metrics.json` and `spike.log` of each run go into this log.

19. *Owner GPU run (2026-10-05)*: the frozen bundle of head `e1794e8`, Windows 11 (build 26200), **Direct3D 11 on the owner's dedicated GPU**, `bench_small`, 1920×1080. The cold full set (`--cold … --iou --orient --pick --update-bench --second-window --coexist --pan-bench --soak 100`) ran to completion: exit 0, `status: ok`, 0 wait timeouts, 0 Qt messages, every board PNG written.
    - **Packaging (1):** the exe rendered all four presets × seven shots; the release gates (`--selftest` exit 0, 8-s smoke) passed on the same build.
    - **Frame rate (4):** low 59.4 / medium 60.0 / high 59.79 / ultra 59.99 fps at 1080p, all at the 60 Hz vsync cap (nominal High ≥ 60). No integrated-GPU `--presets medium` run was available, so kill criterion K3 is untested; the GO records an accepted dedicated-GPU requirement.
    - **Open time (5):** cold `open_ms` 3.47 s (≤ 6); two warm runs 1140 and 1149 ms (`first_ready_ms` 450 / 441 ms), warm 1.15 s (≤ 2.5).
    - **Embedding (3):** 120 pan steps, median without 3D 5.72 ms vs with 3D 16.69 ms → ×2.92; the with-3D median is vsync (≈ 60 fps), so the ratio overstates composition cost. **Policy outcome taken: `QQuickView` host** (the spike's default).
    - **Geometry (6):** `set_mesh` of a 100,489-vertex geometry, median 10.48 ms (max 12.82) against ≤ 10 ms — borderline, 0.5 ms over; to-next-frame median 34.7 ms.
    - **Picking (7), shadow IoU (8), frame orientation:** 20/20 easy + 10/10 adversarial picks, projection error 0.0 px, re-attach frame diff 0.0, probe restore 0.0; shadow IoU high 0.939 / 0.934 / 0.897 and low 0.930 / 0.941 / 0.900 at 15/35/60° (≥ 0.85 on the gated low and high presets; medium reads 0.905 / 0.893 / 0.847, ultra 0.987 / 0.983 / 0.951); ground-texture NCC identity 0.970 vs flip-V 0.012; sky-disc error ≤ 0.17°.
    - **Coexistence (2):** the WebEngine page colour was unchanged (58,123,213 before and after), the 3D frame diff 0.0 against a reference with luma std 42.3, on `Direct3D11Rhi`. The map picker in the bundle was not separately re-walked in this run.
    - **Stability (10):** 100 show/hide cycles with 20 project reloads, reentry median 8.0 ms, exit 0, zero aborts; **the leak reproduced on real hardware** — private bytes rose +140 MB (2372 → 2512 MB) with a tail slope of **15.73 MB/reload over reloads 11–20**, above the pre-registered < 10 gate. Accepted as open (option a); it closes in L1.3. This manual run ran no positive control (the deleted CI driver supplied it); the reading is a gate *failure* accepted as open, so the omission does not weaken the GO.
    - **Protocol note:** the first attempt ran three spike processes at once — a plain PowerShell invocation does not wait on a GUI-subsystem exe — so a later shot's window was not exposed, `wait_frames` timed out, and `grab()` hit an access violation (a tooling robustness gap, not an engine frame defect: with one run at a time and `Start-Process … -Wait`, every run finished with `status: ok`).

**Status by criterion (2026-10-05):**

| # | Criterion | Status |
|---|---|---|
| 1 | Packaging | CI half ✓ (the frozen exe renders the spike on D3D11 in v3, v4, v6 and v9–v19; the 8-s normal-start smoke passes; `--selftest` is green but blind to Quick 3D); **owner half ✓** (frozen exe on Direct3D 11, four presets × seven shots, exit 0; entry 19) |
| 2 | Graphics API coexistence | **RHI coexistence ✓** — in one process, the WebEngine page and the 3D frame are both unchanged, on OpenGL and in the frozen exe on D3D11 (v6; owner run: page colour and frame diff 0.0). The map picker in the bundle was not separately re-walked in the owner run, and "picker before *and* after 3D in one session" is deferred: L1.3 (a recorded deviation, see the Decision) |
| 3 | Embedding | **policy outcome: `QQuickView` host** (the spike default). Owner 1080p: ×2.92 median over 120 pan steps, the with-3D median vsync-capped at ≈ 60 fps so the ratio overstates composition cost (software: ×1.42 llvmpipe, ×2.0–5.7 WARP); entry 19 |
| 4 | Frame rate | **owner, dedicated half ✓**: 1080p, `bench_small`, low 59.4 / medium 60.0 / high 59.79 / ultra 59.99 fps, all vsync-capped at 60 (high at the vsync cap, nominal High ≥ 60). The integrated-GPU medium clause was not run, so the decision records an **accepted dedicated-GPU requirement** (K3 untested); entry 19 |
| 5 | Open time | measured from the request (bake, build, QML load) to the first finished readback, cold/warm recorded; software only (llvmpipe 36–49 s at 320×180 under load; WARP 63 s show-to-readback incl. the first sky-probe prefilter); **owner cold 3.47 s (≤ 6), warm 1.15 s (≤ 2.5)** (protocol: entry 18; entry 19) |
| 6 | Geometry path | **owner 10.48 ms median** (100,489-vertex `set_mesh`, max 12.82) against ≤ 10 ms — borderline, 0.5 ms over; container 10.5 ms, runners 14–36 ms; entry 19 |
| 7 | Picking | ✓ 20/20 easy and 10/10 adversarial targets, projection 0.0 px, also after re-attach, on OpenGL and D3D11 (v6); owner run identical (entry 19) |
| 8 | Shadow agreement | ✓ OpenGL and D3D11, **low and high presets** (orthographic, no cascades); owner run high 0.939 / 0.934 / 0.897 and low 0.930 / 0.941 / 0.900 at 15/35/60° (≥ 0.85). The owner run also measured medium (0.905 / 0.893 / 0.847) and ultra (0.987 / 0.983 / 0.951); medium's 60° reads 0.847, a hair under the bound, on a preset outside the pre-registered low/high set, and the < 0.85 policy (illustrative shadows + draped 2D analysis) covers it. Entry 19 |
| 9 | Size | ✓ +1.7 MB |
| 10 | Stability | the spike's share ✓, zero aborts: close while animating (exit 0, OpenGL and D3D11), 50 cycles + 10 project reloads on OpenGL (slope ≈ 0 after the keep-alive leak fix); the pre-registered leak gate passes on D3D11 in v9–v19 (1.5 / 3.8 / 4.0 / 9.0 / 1.8 / 3.4 / 7.5 / 4.2 / 5.1 / 3.5 / 1.5 MB/reload) and its control fires every time; **leak half open on D3D11:** after an early dip private bytes rise in every run; identical code rose +196 and +62 MB by reload 50 (v14, v15), and over reloads 51–100 four of the five 100-reload runs had a slope whose 95 % interval lies above zero (0.21, 2.03, 3.05 and 3.50 MB/reload) and one, 0.08, an interval that includes zero (the same soak path); cause unidentified (entry 10); over reloads 11–20 llvmpipe RSS read 0.00–0.46 MB/reload where WARP read 1.5–9.0 (no Linux soak past reload 20); it closes in L1.3 (A/B soak, a VRAM reading), or a GO accepts it as open — **taken: option (a)**. **Owner 1080p: 100 cycles + 20 reloads, exit 0, 0 wait timeouts, 0 Qt messages; private bytes +140 MB, tail slope 15.73 MB/reload, above the < 10 gate**; full pytest run with the production view: L1.3 (entry 19) |
| 11 | Beauty | 3D reviewer pass 1 REJECT (spike-code defects) → creator rounds 1–3 → passes 2–4 APPROVE WITH CHANGES (pass 4: one pre-existing P1, the sharpening overshoot) → creator round 4 → **pass 5 APPROVE** (no P0/P1); **owner sign-off 2026-10-05** ("images look good, day and night"); entry 19 |
| 12 | Licence | ✓ |

**Decision**: **GO** (owner, 2026-10-05). Qt Quick 3D replaces Qt 3D for Phase 17; the dormant `--spike-q3d` spike is the L1 foundation and its evidence tooling is deleted with this decision. Owner-GPU run: entry 19.

**Recorded deviations from the pre-committed criteria** (GO requires all; each item not met exactly as written is accepted explicitly, with its measured value and resolution):
- **2** — RHI/WebEngine coexistence passes (page colour and 3D frame unchanged on D3D11), but the map picker was not separately re-walked in the owner run and "picker before *and* after 3D in one session" is deferred to L1.3.
- **3** — the embedding ratio did not meet ≤ 1.3× (owner ×2.92; the with-3D median is vsync-capped, so the ratio overstates composition cost). Policy outcome taken: the `QQuickView` host (the spike default).
- **4** — the dedicated-GPU High clause is met at the 60 Hz vsync cap (~60 fps, measured 59.79); the integrated-GPU Medium clause was not run. An **accepted dedicated-GPU requirement** is recorded (K3 untested).
- **6** — `set_mesh` for a 100k-vertex geometry read 10.48 ms median (max 12.82) against ≤ 10 ms (over budget), and the "1,000 Models ≤ 300 ms" clause is unmeasured. Accepted: `set_mesh` covers the Python side only; L1.1 measures the full edit-to-frame path (≤ 50 ms p95), per entry 5.
- **8** — the gated low and high presets pass (≥ 0.85); medium's 60° reads 0.847, a hair under the bound, on a preset outside the pre-registered low/high set. The < 0.85 policy (illustrative shadows + draped 2D analysis) covers it either way.
- **10** — the spike's share passes (zero aborts; 100 cycles + 20 reloads, exit 0), but the D3D11 leak is open: the owner tail slope read 15.73 MB/reload, above the pre-registered < 10 gate. Accepted as open (option a); it closes in L1.3 with an A/B soak plus a dedicated-GPU-memory reading.

## Addendum L1.2 — the production engine package (2026-10-11, #385 story L1.2)

**Status**: Accepted with L1.2. It turns the GO into code: `ui/view3d/quick3d/`, the Qt Quick 3D
side of ADR-059's `EngineSink`. Nothing is wired into the app yet (L1.3), and the shipped
"3D View…" still opens the Qt 3D window.

**Context.** The spike proved the engine on one long-lived script: build everything, set a model
list, wait for frames, grab. A product needs the opposite shape — a scene that follows edits one
call at a time, a host that is embedded and kept, a render path with no window for tests, tools
and the frozen exe's self-test, and all of it testable on machines without a GPU, because the
release runner has none. Three things the spike left open had to be measured first: whether
`engine_pose`'s rotation sense is the engine's (L1.1's open proof), whether a window that is
never shown can render at all, and what the self-test costs on WARP.

**Decision.**

1. **One package, two engine modules.** `ui/view3d/quick3d/` is the only importer of
   `PyQt6.QtQuick3D` / `QtQuick` / `QtQml` in the product, and inside it only `geometry.py` and
   `host.py` are (`offscreen.py` reaches the engine through `host`). Every decision that is not a
   Qt call sits in an engine-free module — `adapter`, `lifecycle`, `materials`, `look`, `shots`,
   `qt_messages`, `runlog`, the scene and the judge of `selftest` — and the byte layout sits in
   the Qt-free `core/scene3d/interleave.py`.
2. **`Quick3DSink` is pure bookkeeping against a narrow boundary.** It implements `EngineSink`
   and drives `EngineScene` (create / destroy / pose / tint a part, sun, ground, request a
   frame). `Quick3DHost` implements `EngineScene` with real Models; a list-backed double
   implements it in the default test tier. The sink never swallows an engine error. The host
   OWNS every Model; the sink's one teardown, `clear()` (`EngineSink`'s tenth method, which
   `SceneSync.reset()` calls), asks the host once and empties its books whatever the host
   answers — legal at any time, also when the engine is gone. *Corrected in review round 2:*
   a Model leaves the HOST's books only when the engine confirms it is gone, so after a
   failed destroy books and engine still agree and the next `clear()` tries again; a sink
   whose `clear()` failed refuses `begin()` until one went through; and a scene that holds
   Models has an owner — a second sink is refused, at construction and at `attach()`.
3. **One Model per mesh part, one geometry and one material instance per Model.** Created through
   a QML function (`createPart`), never a `Repeater3D` over a list; destroyed hidden-first,
   because `destroy()` is deferred. `BufferGeometry` uploads once, at construction, and has no
   method to upload again — the re-attach rule is structural.
4. **One tint rule for every material kind: `albedo = vertex colour × tint`, in linear light**, the
   tint being a property of the Model. This is what makes `update_material` a property write.
5. **The host is a `QQuickView`; `container()` is how it is embedded** (criterion 3's policy
   outcome, now measured for the container itself). **It is an explicit state machine: six
   states (new, starting, live, hidden, spent, closed) as a pure function of facts the host
   reads from Qt on every call** (`lifecycle.state_of`, engine-free, its whole truth table in
   the unit tests). Every public call answers truthfully for the state or raises
   `HostStateError`. **The contract itself — the facts, the states, the legal calls, what
   `wait_ready()` means, what raises what — is the module docstring of `lifecycle.py` and is
   written down nowhere else** (round 3, below); what follows is how it got its shape.
   *Corrected in review round 1:* the first version guarded `grab()` on `isVisible()` and
   listed three refusals; the engine's condition is "the scene graph is initialised", and the
   difference killed the process in two call orders. *Corrected in review round 2:* three
   predicates were still too few. "No scene graph and not visible" is not "new" — on xcb a
   window shown and hidden again took the offscreen frame and the process segfaulted — so
   `NEW` now means no platform window was EVER created. And "scene graph, visible, exposed"
   is not "live": a collapsed splitter pane is all three and 0 px wide, a window one pixel
   wide draws no 3D, and after a resize the scene can lag the window — so `LIVE` also needs
   an area of at least 2 × 2 px and a root item that has caught up. *Corrected in review
   round 3:* round 2 wrote here "after every resize the scene lags the window by one
   event-loop pass". False twice. `showFullScreen()` delivers its resize INSIDE the call:
   scene and window agree at once, and the render target keeps the old size until the next
   expose — the host read "live" and the grab came back in the old size. And when a parent
   window is maximised, the embedded view has not changed at all until the layout ran. So
   `LIVE` also needs the render target to have caught up — a tenth fact, latched from the
   window's own resize and expose events — and the documentation stopped speaking of
   "passes". *Corrected in review round 4:* that tenth fact could only be switched on by an
   expose — a paint message of the operating system — and Windows sends none to a pane that
   grows where no screen is: the host read "starting" for ever. The fact is gone. **The
   frame is the witness.** The state holds only what Qt reports when it is asked; `LIVE`
   means a frame may be ASKED for; whether it has the window's size is said by the frame,
   which the host checks — to the device pixel — every time it takes one. *Corrected in
   review round 5:* "to the device pixel" was "less than one pixel off", and that is not
   exact: Qt rounds a render target to `qRound(logical × ratio)`, and at 125 % the frame of
   a 442 px pane (553 px) is 0.75 px off the size of a 443 px one — it was handed out. The
   check is Qt's own rounding: at most HALF a device pixel off.
6. **`grab()` on a LIVE host is the synchronisation point.** Nothing in the package or its
   tests waits for a frame to be presented. *Corrected in review round 1:* a host that was just
   shown is not live until its first expose was delivered, and a grab before that is fatal;
   `wait_ready()` pumps the event loop until then, bounded, and its answer is checked wherever
   it is asked. *Round 2:* `wait_ready()` is True only when a grab right after it is truthful;
   it waits only for a host that is on its way, looks again in every pass, blocks for events
   instead of spinning, and gives up as soon as Qt reports that no graphics device will come.
   *Corrected in review round 3:* "True only when a grab right after it is truthful" was
   false after every `showFullScreen()` (20 of 20): `wait_ready()` said True and the grab
   raised. The promise was narrowed to what can be kept, and is pinned in `lifecycle.py`: a
   live host gives the scene at the window's current size or refuses, and after
   `wait_ready()` answered True the next frame call answers. To keep it, `wait_ready()`
   delivers what is pending once for any visible host before it looks — also for one that
   reads live — and a grab that still comes back in another size is a STATE (a
   `HostStateError`; the host reads starting until the next expose), no longer an
   `EngineError`. It also answers False at once when the application is quitting: Qt's
   event loop returns immediately then, and the wait span (158,574 looks in 3.0 s).
   *Corrected in review round 4:* `wait_ready()` proves readiness with a frame of its own —
   True means that frame had the window's size — instead of believing the state. It is back
   within its timeout, the delivery of pending events included (a zero timeout runs no
   event at all; it had taken 1.0 to 1.4 s); its default is 1 s (was 10); and it answers
   False 0.5 s after the last sign of progress, whatever the timeout — "starting" no longer
   means "wait for it". `pick()` and `project()` take a frame of their own after a resize:
   without one the engine picks with the old viewport and misses.
   *Corrected in review round 5:* "back within its timeout" was false, and so was the
   exception stated for it ("the one handler that is running"): one pass of Qt's event
   loop delivers EVERYTHING that is queued — 0.2 s asked, 1.80 s taken behind six handlers
   of 0.3 s. The contract now says what holds: no pass starts once the time is up; the
   call returns within its timeout plus whatever was queued when its last pass began; only
   `wait_ready(0)` is bounded by itself. And it says what the call IS: a nested event loop
   that takes user input — the workspace needs it nowhere on the GUI thread. Silence is
   counted pass by pass, not as wall time (a GUI thread that was busy for 0.7 s inside the
   wait had made it answer False, and True when asked again). `pick()` and `project()`
   took their frame on EVERY call while the render target was behind (200 calls, 200
   frames, all refused): one per refusal now — renewed by a sign of progress, by other
   facts, or after 0.25 s — and a tick that draws stops at its first `HostStateError`.
7. **Offscreen = one never-shown host per frame**, through the real `SceneSync` → sink → host
   path, with every Qt message recorded and an error-class message raising `RenderError`. It is
   for processes that own themselves — it blocks for 0.4–1.3 s and builds a graphics device per
   call — writes nothing unless a log is passed, puts the message handler and Qt's logging rules
   back, refuses a backend that renders no 3D, and names every item whose builder failed.
   *Round 2:* this is the ONLY place a Qt message recorder is installed, because it is the
   only rendering that happens on the calling thread (decision 11) — measured per message, not
   assumed: the recorder counts what arrives on another thread, and the render tier requires
   0. The call refuses to run while a Qt Quick window is shown in the process.
8. **One look, `NEUTRAL_DAY`** — the spike's noon rig, a plain sky colour, no image-based light
   probe, a flat fill derived from the noon sky (its mean in linear light × the spike's probe
   exposure). `set_look(Look)` takes plain data; L1.4 builds the looks.
9. **`--selftest` renders and judges** one hidden 160 × 120 frame containing every material kind.
   ONE watchdog bounds the whole command — the Qt3D and Agent API blocks too, 300 s — and writes
   its reason into the log before it ends the process; the log goes into the app's per-user
   log directory. *Round 2:* the watchdog has two lines of defence. `faulthandler`'s exit
   was measured NOT to end a Windows process whose threads are deadlocked inside Qt (the dump
   is written, the process lives on), so a second process — the same exe, started with
   `--selftest-supervisor` — terminates it from outside ten seconds after the deadline.
   *Round 3:* that process acts for ONE block of ONE process and is built so that it cannot
   act for anything else. The release event's name carries a random nonce per block — named
   per process, a finished block's late supervisor terminated the healthy block after it,
   4.1 s in. It refuses a process that is not its own parent, and in the frozen build one
   that does not run its own image; its arguments are validated before anything is opened;
   and one watchdog is armed per process at a time. And the safety net is checked like the
   subsystems it guards: on Windows the self-test FAILS when its supervising process did
   not start, refused, or did not leave. *Round 4:* a supervisor that found nothing to
   wait for exits 4, not 0 — it never supervised, and the self-test fails on it; a block
   keeps its signalled release event until its supervisor has left, so that one which
   comes up late is "released" and not "lost"; a watchdog that fails while arming disarms
   what it had armed. *Round 5:* a supervisor whose own wait FAILS exits 3 (it said 0:
   everything that was not a timeout counted as a release); and `Armed.supervised` and
   `Armed.gap` are one statement (a supervisor that had not left read as "supervised").
10. **A render tier in two processes**: a driver with a real Qt platform renders; the tests, in
    the ordinary offscreen process, judge with a CPU projection of their own. The host's
    lifecycle is a matrix of call orders, one process each. CI runs the tier in a `render3d`
    job that is not a required check; a second workflow, `frozen-selftest.yml`, builds the
    bundle with the release recipe and runs the frozen gate on every pull request that changes
    shipped code (`src/open_garden_planner/**`, the installer, the locks). *Round 2:* the
    matrix is judged against a table of what a truthful host must answer — a frame with the
    probe at the predicted pixels, or a refusal — never against the state the host reports;
    the first judge was blind to a host that reported the wrong state.
11. **No Python Qt message handler beside a shown window; a shown host reports through
    `health()`.** *This replaces the first version's decision ("a live view's errors have a
    seam: `watch_messages()` / `engine_errors()`"), which review round 2 measured to deadlock
    the process.* Qt Quick renders a shown window on a thread of its own — the threaded render
    loop, on Direct3D 11 (GPU and WARP) and on xcb + OpenGL alike. Qt's message handler is
    process-wide, and PyQt calls a Python handler under the GIL on whichever thread emits the
    message. When the render thread emits one while the GUI thread sits in a Python-called Qt
    function that waits for the render thread — `hide()` does — each waits for the other,
    for good. There is no render-thread-safe Python recorder. So:
    - a recorder is installed only around rendering on the calling thread (decision 7);
    - a SHOWN host learns about itself from what Qt delivers on the GUI thread, collected in
      `Quick3DHost.health()` and written to the app's log as it arrives: the QML engine's
      `warnings` signal, the window's `sceneGraphError` signal, and a count of presented
      frames (`frameSwapped`) — the last two connected QUEUED, so that no Python ever runs on
      the render thread (the host counts slot calls that arrive elsewhere; the tier requires 0);
    - `sceneGraphError` MUST be connected: with nothing connected, Qt answers a graphics
      device that cannot be created with a modal error box and then aborts the process —
      which in the app is the whole 2D application;
    - a shader of a SHIPPED material that does not compile is therefore not reported at run
      time. It is caught BEFORE release: the render tier and the frozen self-test compile
      every shipped shader under a recorder, and the tier shows that a shown window draws
      what the offscreen frame draws, material for material;
    - *round 3:* the host does NOT refuse to show itself while a Python handler is installed
      — ruled out: it cannot know whose handler it is, and the app installs none. The guard
      is static, an AST scan over all of `src/` (`tests/unit/test_quick3d_boundary.py`):
      `qInstallMessageHandler` and `QLoggingCategory.installFilter` only in the recorder
      module (and in the dormant spike's own, which retires in L1.10), the recorder's
      `install` only from `offscreen.py`, a render-thread signal only through the one
      queued-connect helper. Necessary, not sufficient: it cannot see a handler that a
      third-party package installs, nor a Python override of a virtual that Qt calls on the
      render thread.
12. **At rest the wind moves nothing.** With the scene's clock at 0 a vertex is drawn exactly
    where its mesh puts it; the truth principle (ADR-059) does not stop at the shader. "At
    rest" means the clock IS 0 (or the wind strength is): a clock paused at any other value
    leaves the sway in the frame, so a truth probe pins the clock or the strength.

**Ported from the spike unchanged** (each measured there, ADR-048 evidence log): the vertex
layout (stride 48, linear colour); the frame mapping; the sun as
`QQuaternion.rotationTo((0, 0, −1), travel)`; the High preset's shadow settings — bias 5,
`ShadowMapQualityVeryHigh`, PCF16, `pcfFactor` 2, `shadowMapFar` 9000, locked texels, factor 82,
two cascades and none in the orthographic view; the material numbers (vertex-colour 0.78 / 0.35,
roof 0.80 / 0.15, glass, the foliage and grass shaders, the water shader's lighting model and its
`#if QSSG_ENABLE_LIGHT_PROBE` guard); the endless meadow (4 × 4 km, 1 cm under the plan, one
albedo); the cameras (clip planes, 40° field of view, the top camera at 40 m); the pick helper
returning a plain JS object; the Qt-message classifier; the log-plus-watchdog pattern; the noon
rig's numbers.

**Changed, and why.**

| Spike | L1.2 | Why |
|---|---|---|
| `Repeater3D` over a JS array of models | `createPart()` per mesh part | any change of the array recreates every delegate, and a geometry does not survive its Model |
| `NumpyGeometry.set_mesh` re-uploads into one object | `BufferGeometry`: one upload, no re-upload method | one geometry per Model lifetime, enforced by the type |
| interleaving inside the Qt class | `core/scene3d/interleave.py` | the default test run covers the layout byte for byte |
| shared material objects, colour baked into vertices | one material instance per Model, tint as a property | a recolour must not upload geometry |
| the water colour as one uniform for every pond | water albedo = vertex colour × tint (`VAR_COLOR`) | the same rule as every other kind; the mesh carries its colour |
| sky light probe, fog, glow, AO, four presets | plain sky colour, flat fill, one look | L1.4 owns looks; a probe costs 40–85 s once on WARP — nothing for a self-test |
| the meadow hidden and a white probe ground in the orthographic view | the meadow and the plan rectangle always shown | the truth view shows the scene, not a probe rig |
| `wait_frames` on `frameSwapped`, then grab | grab only | a visible window may present one frame and no more (PF-E3D-06) |
| two hosts, `QQuickView` and `QQuickWidget` | `QQuickView` only | criterion 3; the package does not import `QtQuickWidgets` |
| one process-wide message recorder | recorders that chain; an exact `environment` class | a render inside a recorded run, or inside the app, must not deafen the outer listener |
| `SunState` with colour and brightness | direction (`core/scene3d.SunState`) apart from the look | where the sun stands is truth; what it looks like is art direction |

**Alternatives considered — rejected.**

- *Engine imports in the sink.* Then no line of the sync-to-engine logic runs without a GPU.
- *Leaving the host to the render tier alone.* Measured on one tree with one denominator
  (2026-10-11, after review round 1): the default tier covers 674 of the package's 1,060
  statements without the host tests and 993 with them. Added to CI's numbers for the base
  commit (`ui`: 18,880 of 26,500) that is an estimated 70.95 % against the floor of 71 % in the
  first case and 72.11 % in the second — CI's coverage job is the judge, and it passed. The
  host is therefore also exercised under the offscreen platform, where `Garden.qml` loads and
  Models are created, posed and read back without a pixel (`tests/ui/test_quick3d_host.py`).
  (The first version of this entry quoted 511 of 871 and 855 of 879 — two measurements on two
  trees.) After review round 2, measured on Linux in a container: 789 of 1,325 without the
  host tests and 1,176 with them — an estimated 70.69 % and 72.08 % on the same base.
- *Recolour by rewriting vertex colours.* Simple, but an upload per recolour and a second code
  path for something the material can do.
- *A persistent hidden render target (`QQuickRenderControl`).* Not attempted: one hidden host
  per frame serves every consumer L1 has (0.4–1.3 s per frame). Revisit if a tool needs many
  windowless frames per second.
- *Waiting for presented frames.* Measured to stall with the display asleep.
- *The self-test in a child process with the parent as its watchdog.* More moving parts in a
  frozen exe for the same guarantee `faulthandler` gives in-process.
- *A "was shown" flag in the host.* The first version had one. The parent of an embedded
  container shows and hides it without calling the host, so the flag is wrong exactly where
  L1.3 will use the host; Qt's predicates are asked instead.
- *Letting `grab()` wait for the first expose itself.* It would run the event loop inside a
  call that reads like a getter. `grab()` refuses, and `wait_ready()` is the one place that
  pumps.
- *Allowing a grab while hidden.* Measured to return a correct frame on Direct3D 11 (2 of 2).
  Refused all the same: unmeasured on OpenGL, and no caller needs it.
- *A Qt message watch for the live host* (round 1's decision 11). Deadlocks the process
  (round 2, below). Also rejected: keeping the watch and forcing the non-threaded render
  loop (`QSG_RENDER_LOOP=basic`) — the product would run a render loop nobody else tests, to
  buy a notice about shaders that are checked before release anyway; and a C-level handler —
  not available from PyQt.
- *Deriving "new" from `QWindow.handle()`.* The same fact as the `PlatformSurface` event the
  host uses, and PyQt6 6.11 does not bind it; `winId()` would create the window it asks about.
- *Ending a hung self-test from inside.* `faulthandler`'s `exit=True` and a native timer that
  calls `ExitProcess` both hang in the deadlock (DLL detach); a native timer that calls
  `TerminateProcess` on its own process does end it, but with an exit code that is not ours.
  A second process is the only one that decides the exit code and needs nothing from the
  first.
- *Clearing a host that already holds Models when a second sink attaches.* It would destroy
  what somebody else is showing. Refused instead.
- *Deriving "the render target has caught up" from `frameSwapped`* (round 3). That signal is
  queued from the render thread: one emitted before a resize can arrive after it. The
  window's own resize and expose events are delivered on the GUI thread, in order.
- *Deriving it from the window's `Resize` / `Expose` events* — round 3's own choice,
  rejected in round 4: no expose reaches a window that is not on a screen, and a state that
  waits for one waits for ever.
- *A named state "nothing of the view is on any screen", derived from geometry* (round 4;
  the other option the review offered). It would have closed the off-screen case and no
  other. The same stale render target was measured ON the screen — with the view's paint
  events withheld — and on one machine the pane beyond one edge kept its old target while
  the display slept (no update request arrives either) and got the new one while it was
  awake, both on the same day — and on WARP it got the new one either way. Geometry does
  not say whether Qt draws; a frame does. The probe is also
  the smaller change: it removes a fact instead of adding a state.
- *Treating a change of the device pixel ratio as a resize* (round 3). Unmeasured — the
  machine has one scale — and an event whose order relative to the expose is unknown could
  leave a host starting for ever. The grab's own size check covers the case: such a frame
  is refused, never handed out.
- *A run-time refusal in `show()` while a Python Qt message handler is installed* (round 3).
  Decision 11.
- *Naming the supervisor's release event by the process alone* (round 2's). Decision 9.
- *Reading a shown host's shader errors from stderr in the product.* A frozen GUI exe has no
  stderr. (The render tier does read the DRIVER's stderr — that is a test process.)
- *A composite action for the self-test step.* One script in two workflows is duplication; a
  test pins the two texts as identical instead, which leaves the existing guards on
  `release.yml` (the command line itself must be in that file) as they are.
- *The self-test log in the temp directory.* The first version; a predictable name in a shared
  directory (CWE-377). Replaced in review (§8.11).
- *`render3d` as a required check.* A software rasteriser on a shared runner proves correctness,
  not speed, and the job could not be run before it was written.

**Consequences.** New: the package (eleven modules, `Garden.qml`, four shaders),
`core/scene3d/interleave.py`, `Quick3DSink.clear()` and `attach()`, a CI job, the
`frozen-selftest.yml` workflow, a third block in `--selftest`, a watchdog around all three and
the internal `--selftest-supervisor` flag (the exe as the process that ends a hung self-test). No `.ogp`
change, no `FILE_VERSION` bump, no new dependency, no
user-visible string. Bundle +0.08 MB. The spike stays untouched and importable; it and the
spec's spike entries retire in L1.10. Seams left for later stories: `Quick3DHost.container()` and
`set_shot` (L1.3), `set_look(Look)` and `windTime` (L1.4), the plan rectangle in `Garden.qml`
(L1.5), `pick()` → `PickHit` (L1.8).

**Evidence** (Windows 11, RTX 4070 and WARP via `QSG_RHI_PREFER_SOFTWARE_RENDERER=1`, PyQt6
6.11.0, Python 3.12.9, 2026-10-11; the monitor was asleep, which is how the second row was found).

| Question | Measured |
|---|---|
| Can a never-shown window render? | Yes, once: the first hidden grab is pixel-identical to a shown grab (mean abs difference 0.0), WARP vs GPU differ by ≤ 4 of 255; the SECOND hidden grab is the bare clear colour (difference 161). Cost per hidden frame: 0.4–0.5 s with one material, 1.1–1.3 s with all six (three custom shaders), GPU and WARP alike |
| Do frames keep coming on a visible window? | Not with the display asleep: 1 `frameSwapped`, then none in 40 update requests; with `QT_D3D_NO_VBLANK_THREAD=1` about 4 per second; on WARP they flow. A shown grab: 1–9 ms |
| Is `eulerRotation.y = +rotation_deg` counter-clockwise from above? | Yes: mask IoU against the CPU prediction 1.000 / 0.9994 / 1.000 / 0.9895 at 0° / 17° / 90° / 213.5°; against the opposite sense 0.288 (17°) and 0.157 (213.5°) |
| East right, north up? | Centroids of an east and a north box exact to 0.0 px, IoU 1.000; predicted under a mirrored or swapped mapping: IoU 0.000 |
| Shadow vs the analytic 2D shadow | IoU 0.9777 / 0.9763 / 0.9770 at azimuth 225° / 135° / 45°, elevation 35°, 480 × 360 (WARP within 0.0002); direction within 0.02° |
| Lit and shaded faces | luma 229.5 lit vs 126.6 shaded (filmic view), the lit pair following the azimuth in all three cases |
| Radiance of a lit top face (truth view) | predicted 167.2 of 255, measured 171 |
| Tint through `baseColor` vs a shader uniform | 171 vs 169 |
| Picking | 10 of 10 easy targets, 6 of 6 adversarial (inside a bounding box, off the mesh), 0 of 10 false hits on bare ground; our projection vs the engine's 0.0 px; 0.01–0.2 ms per pick |
| Uploads per edit | add 2 items: 2 · move: 0 · recolour: 0 · replace geometry: 1 · remove: 0 · re-add: 1 · clear and re-send: 2 · hide and show: 0; the re-added, the re-sent and the re-shown frame identical to the one before (difference 0.0) |
| Open: request → first finished readback, `bench_small.ogp` (87 Models, 640 × 400; 99 records, 98 since the L1.1 review took the roof ridge out of the snapshot) | GPU: 1.11 s in the first run of the day (QML load 17 ms, first expose with device creation 935 ms, apply 31 ms, grab 21 ms) and 0.40 s in the last (QML load 18 ms, apply 41 ms, grab 25 ms) — the device creation is the part that varies. WARP: 0.17 s and 0.39 s |
| Edit → finished readback (30 moves, the same plan) | GPU: median 7.1 ms, p95 17.9 ms, max 26.8 ms (snapshot 2.3, apply 0.2, grab 4.5); after review round 1 median 7.5 ms, p95 18.0 ms, max 26.2 ms. WARP: median 23.2 ms, then 26.5 ms (p95 29.0). Against ADR-048 entries 5/6's 50 ms p95 |
| Engine import cost in the running app | the package 1 ms; the sink with `core/scene3d` 17 ms; the Qt Quick bindings 17 ms. App start loads none of it |
| Embedding (criterion 3) with the window container | top-level surface stays `RasterSurface`; 2D pan step median 2.56 ms with the 3D container vs 2.63 ms without (×0.97; WARP ×0.92) — and 2.96 vs 2.97 ms (×1.00; WARP ×1.11) in the last run of the day. Control: a `QQuickWidget` makes the surface `Direct3DSurface` and the step 262 ms on this machine (its presents wait for the sleeping display) |
| `--selftest`, the whole command, three runs each | from source: 2.2–4.3 s (GPU), 2.1–5.7 s (WARP). Frozen exe via `Start-Process -Wait -PassThru`: 3.0–4.1 s (GPU), 3.0–3.1 s (WARP), 3.0 s (WARP, every shader cache disabled); 6.1–7.2 s on either adapter while other test suites ran on the machine. Exit 0 in all; exit 1 under the offscreen platform, on a broken shader, on a hang (watchdog) |
| Bundle | 650,815,562 vs 650,736,554 bytes for the base commit: +79,008 bytes (+0.08 MB); smoke exit 124 |
| The whole render tier | first version: 51 tests, about 50 s on the GPU. After review round 1: 79 tests — 114 s on the GPU (79 passed), 112 s on WARP (77 passed, the two hardware-only budgets skipped); zero Qt warnings and errors in the clean runs of both |
| The frozen gate after review round 1 (built from 3c236b6) | smoke: exit 124. `--selftest`, three runs each: 2.95–3.20 s on the GPU, 2.93–3.25 s on WARP, exit 0. The workflows' step script, run as GitHub's pwsh runs it against that exe: verdict first, log after, exit 0; with a platform that renders nothing, `::error::` verdict, log, exit 1; with a directory where the log should be, the exe fails closed (exit 1, "no log"), the step prints its verdict and "the log could not be printed", exit 1 |
| What decides a local bundle's size besides the code | PATH. Built from Git Bash the bundle carries `libcrypto-3-x64.dll` and `libssl-3-x64.dll` — 5,531,448 bytes, byte for byte the files in Git for Windows' `mingw64/bin` — and built from a plain PowerShell process it does not (650,815,562 vs 645,326,627 bytes; the rest differed by 42,513 bytes, this package's own files). Compare sizes only between builds from the same shell; the +79,008 bytes above were |

**Review round 1 (2026-10-11).** An independent review of the first version found no P0, four
P1 and fourteen P2 defects, and CI ran the branch for the first time. None was refuted; each
was reproduced or read in the code before it was fixed. What a green suite had not seen:

1. *Two call orders killed the process* — `show()` then `grab()` before the first expose, and
   one hidden grab followed by `show()`, which the error message recommended. The guard asked
   `isVisible()`. → decisions 5 and 6, the state machine.
2. *The default-tier host tests could not fail on a broken scene file*: their canary ran the
   product. → a canary of bare Qt, and a positive control.
3. *`Quick3DSink.clear()` raised in every order once the host was closed or destroyed*, and
   left its books dirty. → one owner of Model lifetime, decision 2.
4. *The release's self-test step had no time limit, and the in-exe watchdog covered the render
   only.* → decision 9, limits on step and job, the verdict before the log, and the frozen
   gate on pull requests (decision 10).

| Question (review round 1) | Measured |
|---|---|
| What do Qt's predicates say? (visible, exposed, scene graph initialised) | new F F F · after `show()` T F F · after one `processEvents()` T T T · right after `hide()` F T T, then F F T · shown again T F T · minimised T F T. Under the offscreen platform the scene graph reports initialised from birth and nothing 3D is drawn |
| Which grabs kill? | `show()`, then `grabWindow()` before the first expose: the image is right (2,500 of 2,500 probe pixels) and the process is dead within the next event-loop passes — exit 3, `0xC0000005` or `0xC0000374`; 3 of 3 here, 5 of 5 GPU / 3 of 3 WARP / 4 of 4 embedded in the review. One hidden grab, then `show()`: 3 of 3. Embedded, never shown, grabbed, then shown by the parent: 2 of 2 GPU, 1 of 1 WARP |
| Which do not? | the same two orders when the window is destroyed before the event loop runs again (6 of 6 survived — why one host per offscreen frame never met it); a grab while hidden WITH a scene graph (correct frame, 2 of 2); embedding a view that is live, starting or hidden (2 of 2 GPU, 1 of 1 WARP each). *Corrected in round 2:* "show + hide before any event, then the one offscreen grab" stood in this row. It survives on Direct3D 11 and KILLS on xcb (below) |
| The lifecycle matrix (round 1) | 15 call orders, one process each: every one survived and answered as the state table said; the two controls — the killing orders on the raw view — died, 3 of 3 each on the RTX 4070 and on WARP. *The judge compared each answer with the state the host reported, so it could not see a host that reported the wrong state — round 2* |
| Wind at rest | boxes whose every vertex has the full wind weight, wind 40 × the look's: IoU 1.000, offset 0.00 px against the CPU footprint. With the shaders as ported: 10.2 px (foliage) and 18.9 px (grass) off — 20 cm and 38 cm — and no message |
| A broken shader in a SHOWN view | no exception; the leaf is not drawn; four Qt messages classified as errors. *Round 1 recorded them with a Python handler called on Qt's render thread — the arrangement round 2 measured to deadlock; removed (decision 11)* |
| A broken `Garden.qml` under the default-tier host tests | before: 32 skipped, 0 failed. After: 9 failed, 43 errors, 12 passed, 0 skipped |
| A hang outside the render | a `--selftest` whose second block sleeps: exit 1 when the watchdog's time is up, `[watchdog] fired=True … did not finish within …` in the log before the stack dump, which names the sleeping frame |
| Recovery after a failed engine call | the engine refuses the second Model of a transaction that adds two items and moves one: the half-applied frame shows one new box and no move; after `sync.reset()` the engine holds nothing; after `sync.apply` the sink equals `sync.expected_state()`, the Models match it part for part and the frame matches the CPU prediction (IoU ≥ 0.95). The same on a list-backed engine for each of the sink's engine calls |
| The graphics API's name | PyQt6 6.11 names the enum members `OpenGL` but `Direct3D11Rhi`; the first Linux run reported `OpenGL` against a typed list that said `OpenGLRhi`. The name now comes from the enum member |
| First CI run of `render3d` (commit af9300d) | windows-latest: green. ubuntu-latest: 47 passed, 4 skipped, 1 failed — the API name. The four skips are by design: two hardware-only budgets (llvmpipe is a software rasteriser) and two Windows-only self-test checks (WARP; the whole `--selftest`, whose Qt3D block needs the bundled Qt runtime) |

**Review round 2 (2026-10-11).** The re-review confirmed three of the four round-1 fixes and
found the host's central claim — "answers truthfully or raises, never kills" — false in three
measured ways; CI was red on Linux. None of its findings was refuted. What a green suite and
a first fix had not seen:

1. *`NEW` was not safe on xcb*: `show(); hide(); grab()` read "new", took the offscreen frame
   and the process segfaulted in the next event-loop pass. The matrix had pinned that very
   order as safe, from a Windows measurement. → decision 5: `NEW` = no platform window ever.
2. *`LIVE` ignored geometry*: in a collapsed splitter pane the host said "live" and returned a
   blank frame, a bogus pick and a projection of (0, 0). → decision 5: an area and a caught-up
   root item; and the judge no longer asks the host (decision 10).
3. *`watch_messages()` deadlocked the process.* → decision 11.
4. *Teardown was not exception-safe* (the fourth `reset()` "succeeded" with three Models left),
   *`attach()` accepted an occupied host*, *`wait_ready()` span to its timeout*, *the watchdog's
   exit was not guaranteed*, and *tests of the package wrote into the developer's profile.*
   → decisions 2, 6 and 9, and §8.10.8.
5. Found while fixing, before any reviewer saw it: the first supervised watchdog would have
   ENDED A PROCESS THAT HAD FINISHED ITS BLOCK. A block that is over before the supervising
   process is up destroys the release event; the late supervisor found none, waited on the
   process alone and terminated it at the deadline — a pytest run, 310 s after the test that
   called the bounded self-test had passed. A missing event now means "released".

| Question (review round 2) | Measured (Qt 6.11; Direct3D 11 on an RTX 4070 and on WARP; xcb + OpenGL on llvmpipe, Mesa 25.2, Ubuntu 24.04 under xvfb in a container — the CI job's stack) |
|---|---|
| Which thread renders a shown window? | `qt.scenegraph.general` names the **threaded render loop** on Direct3D 11 (GPU and WARP) and on xcb + OpenGL (llvmpipe); `QSG_RENDER_LOOP=basic` selects the basic one. The tier records the answer of every run with its artifacts |
| Which thread delivers the messages of a ONE-SHOT offscreen frame? | the calling thread: 24 of 24 messages of a frame with a broken shader (the shader errors included), 0 from any other thread; asserted for every offscreen frame of the render tier and for each failed render of the shader controls |
| A Python Qt message handler beside a shown window | a handler, `qt.scenegraph.renderloop` debug output switched on, `hide()`: the call never returns — every run, on the GPU, on WARP and on xcb. Without the handler `hide()` returns in 6–9 ms |
| Does the watchdog end that process? | `faulthandler.dump_traceback_later(exit=True)`: the dump is written; on Linux the process then ends (exit 1, 5 of 5); on Windows it stays alive (every run, one observed for three minutes) — `_exit` is `ExitProcess`, which waits in a DLL's detach code. `ExitProcess` from a native timer thread: hangs, 2 of 2. `TerminateProcess` on itself from a native timer thread: ends it, 3 of 3, with an exit code that is not 1. A second process calling `TerminateProcess(handle, 1)`: exit code 1, every run |
| What do Qt's facts say? (platform window ever created · visible · exposed · scene graph) | new 0 F F F · `show()` 1 T F F · one event-loop pass later 1 T T T · `hide()` 1 F T T, then 1 F F T · `show(); hide()` before any event 1 F F F — and it stays so · a window the user closed 1 F F T (its platform window is destroyed; a raw grab is an access violation, on xcb a segfault) · minimised 1 T F T with `visibility() == Minimized` |
| A `QSplitter` pane collapsed to width 0 | window 0 × 500, `geometry().isValid()` false, visible T, exposed T, scene graph T. A raw grab: a 447 × 500 image without one probe pixel; a raw pick: a hit. After every change of size the QML root item has the OLD size until one event-loop pass ran (collapsed: root 447; reopened: root 0) |
| How small can a window be and still show 3D? | 1 px wide or high: the bare clear colour. 2 px: the scene. `MIN_SIDE_PX = 2` |
| `show(); hide(); grab()` on the raw view | Direct3D 11: a correct frame, the process survives. xcb: SIGSEGV in the next event-loop pass, 5 of 5 (and the red CI job) |
| The other killing orders on xcb | shown and grabbed before the first expose; the offscreen frame, then shown; a window the user closed, grabbed: SIGSEGV, SIGBUS or SIGABRT, 5 of 5 each |
| A graphics device that cannot be created (`QT_D3D_ADAPTER_INDEX=9`) | with a slot on `sceneGraphError`: `(ContextNotAvailable, "Failed to initialize graphics backend for D3D11.")` arrives on the GUI thread, the process lives, the window is visible and exposed and never gets a scene graph, 0 frames, `wait_ready()` answers False in 0.02 s. With NO slot: a native modal dialog with that text; the process sits in it; after OK it aborts, exit `0xC0000409`. (`QSG_RHI_BACKEND=bogus` falls back to the default backend; `vulkan` without a driver is an access violation inside Qt — another failure, not covered) |
| A QML function called from Python that fails | missing: PyQt raises `RuntimeError`; one that THROWS: the call returns `None`, silently, and the QML engine emits a warning. Both are an `EngineError` now |
| pytest-qt and the rule of decision 11 | pytest-qt 4.5 installs a Python Qt message handler for every test (`_QtMessageCapture`), unless the test is marked `no_qt_log`. Under the offscreen platform Qt logs "Loading backend software" and announces no render loop; the in-process host tier ran under that handler several hundred times without a hang. It is marked `no_qt_log` all the same, and real-platform hosts stay in child processes |
| The frozen gate after review round 2 (built from 7ca084f, locked Python 3.11) | 646,640,942 bytes, 2,442 files — the exe +37,668 bytes and three QML / shader files +691 against round 1's build, plus Git's two OpenSSL DLLs (the PATH effect below). Smoke: exit 124. `--selftest` through `Start-Process -Wait -PassThru`, three runs each: exit 0; 6.1–7.2 s on the GPU and 7.1 s on WARP with a full test suite running on the machine (3.0–4.9 s for the build of 264f06b on a quieter one); `other_threads=0`; the supervising process started in every run and had nothing to do. The frozen exe AS the supervising process, against a dummy: past the deadline the dummy ends with exit code 1 and the reason is in the log; with the wrong creation time it is left alone; released, the supervisor is gone 0.07 s later; with no event it leaves after 0.4 s |
| Where does `QStandardPaths` point on Windows? | at `<USERPROFILE>/AppData/Roaming` and `…/Local` — the shell expands its known folders from `USERPROFILE`; the `APPDATA` variable is not read. Hence the test children's profile (§8.10.8) |
| The lifecycle matrix (round 2) | 19 call orders and 9 controls, one process each, judged against the truth table: green on the GPU and on WARP, and on xcb in the container — where every control that can run there (the three killing orders, the collapsed pane's wrong frames, the message-handler deadlock) fails the way it was first measured to on Windows, and the fourth killing order, `show(); hide(); grab()`, fails only there |

**Review round 3 (2026-10-11).** The scoped re-review confirmed the three round-2 P1 fixes on
three platforms — CI was green on all eleven jobs, the Linux render job with exactly the 88
passed and 8 skipped the container had predicted — and found two narrow new P1 and ten P2
defects. None was refuted. The first P1 was reproduced here before it was fixed; the second
was fixed from the code and then reproduced against the previous head (the process ends with
exit code 1, 4.7 s in). What a green suite on three platforms had not seen:

1. *`wait_ready()` said True and the next `grab()` raised, after every `showFullScreen()`* —
   and `application.py` calls `showFullScreen()` on the window the workspace embeds into.
   The matrix had no full-screen row, and the truth table could not have had one: the fact
   that differs was not among its nine. → decisions 5 and 6; two window-state orders and a
   seeded random walk in the matrix.
2. *The supervisor's release event was named per process, not per block*: a finished block's
   late supervisor terminated the healthy block after it. Latent — every user armed one
   block per process — and advertised for reuse. → decision 9.
3. *The state contract stood in nine places, and three of them were wrong.* → one place,
   `lifecycle.py`; a test fails a second copy of the state table.
4. *The gate's own safety net could be missing without a word* (`supervisor=none` passed the
   self-test), *a quitting application made `wait_ready()` spin*, *the offscreen recorder's
   "must be 0" was asserted by the render tier only*, and *the frozen workflow's step limits
   added up to its job's.* → decisions 6, 7 and 9, §7.4.

| Question (review round 3) | Measured (Qt 6.11; an event filter on the view; Direct3D 11 on an RTX 4070 unless a row says otherwise) |
|---|---|
| What does `showFullScreen()` deliver, and when? | INSIDE the call: `Resize`, `Move`, `WindowStateChange` — the window is 5120 × 1440 and so is the QML root item, at once; a raw grab then is 320 × 240, the old size. In the next event-loop pass: `Expose`; a raw grab then is 5120 × 1440 |
| `showNormal()` out of full screen | `Resize`, `Move` AND `Expose` inside the call: the grab is right at once |
| `showMaximized()` of a standalone view | nothing inside the call: the window has the new size, the root item the old one. `Resize`, `Move`, `WindowStateChange`, `Expose` in the next pass |
| `showMaximized()` of a main window that embeds the view | nothing has changed for the view — its size, its root item, no event — until the next pass (`Resize`, `Move`, `Expose`); a grab before that is a correct frame of the OLD size |
| A splitter move, `resize()` | `Resize` and `Expose` in the next pass |
| The rule that covers all five | a grab has the wrong size exactly between a `Resize` event and the next `Expose` event of the exposed window. (*Round 4:* true of these five, and not a rule to wait on — where no expose comes the grab stays wrong, and a host that waits for one waits for ever) |
| How long is "the next pass"? | 6–13 ms; up to about 1 s on this machine when a grab preceded the resize and the display is asleep — spent inside Qt's own expose handling, not in the host's wait |
| The reviewer's reproducer against the fix | full screen / normal / maximised, standalone, embedded and re-parented: 38 of 38 transitions give the scene at the new size after `wait_ready()`. Before: `EngineError` after 20 of 20 `showFullScreen()` |
| A seeded random walk (seed 20261011, 250 steps, an embedded host) | GPU: 252 looks — 70 frames, 182 refusals; `wait_ready()` answered True 50 times, each followed by a frame, and False 105 times. WARP: the same 70 / 182 and 50 / 105. xcb + llvmpipe: 63 frames, 189 refusals; True 44 times, False 111 times. No wrong frame, no stuck host and 0 frames of a stale size on any of the three. (*Round 4:* on this machine's 5120 px screen. On the CI runner's 1024 px screen the same walk reported three stuck hosts and three waits of 5 s — its 1203 and 1500 px wide windows put the pane beyond the edge) |
| `QEventLoop.exec()` once the application is quitting | inside a running main loop after `QCoreApplication.quit()`: it returns −1 in about 2 µs, every time. Without a running main loop `quit()` does nothing |
| Two supervised blocks in one process | before: block A (1 s budget, empty), then block B (60 s, healthy) — A's supervisor terminated the process 4.1 s into B. After: both blocks run to their end, exit 0; with the nonce taken out of the event's name again, the pin fails |
| The supervising process, started by hand or aimed elsewhere | a deadline of `nan`, `inf`, `0` or `-1`; a pid that is no number; a nonce that is not 32 hex digits; a log that does not exist: exit code 2, one line, nothing opened. A process that is not its parent — given the right pid, creation time and nonce of a live block: exit code 2, the process lives |
| The lifecycle matrix (round 3) | 21 call orders, the random walk and 9 controls, one process each. The whole render tier: 99 passed and one control reported, not asserted, in 321 s on the GPU, 97 passed, the two hardware-only budgets skipped and the one control reported, in 244 s on WARP, 92 passed and 8 skipped in 184 s on xcb in the container |
| The frozen gate after review round 3 (built from 324fcf3, locked Python 3.11) | 646,651,032 bytes, 2,442 files (+10,090 bytes against round 2's build). Smoke: exit 124. `--selftest` through `Start-Process -Wait -PassThru`, three runs each: exit 0 in 4.05–4.09 s on the GPU and 4.03–6.08 s on WARP; in every run a supervising process started, was released and left with exit code 0 (`[selftest_supervisor] ok=True`), and `other_threads=0`. The frozen exe started as a supervisor by anything else — malformed arguments (six cases), a live process that is not its parent, its real parent running another image: exit code 2 in 0.2–1.1 s, one ASCII line, the process it named alive, nothing written. Its TERMINATE path cannot be reached from outside any more, by design; from source it runs in every run of its pin |

**Review round 4 (2026-10-12).** The scoped check confirmed round 3's two P1 and ten P2 fixes
— and CI was red: on `windows-latest` the story's own seeded walk reported 7 problems in 252
looks. One blocking finding and five P2; none refuted.

1. *A shown pane that never came up.* Round 3's tenth fact could only become true through an
   `Expose`. The walk asked for 1203 and 1500 px wide windows on whatever screen it found;
   on the runner's small screen the pane lay beyond the edge, where Windows sends none. The
   host read "starting", and every `wait_ready()` took its whole timeout. Never a wrong
   frame — the refusal was truthful; liveness was broken. → decisions 5 and 6.
2. *The matrix depended on the screen it ran on* — "the local render tiers pass only because
   every window fits on this screen". → every window of the matrix is placed on the screen
   on purpose; the walk runs twice, once fitted to the screen it finds and once where a
   1024 × 768 screen leaves the window; rows for the pane beyond the edge, for a 2 × 60 px
   pane, and for a view that nothing draws.
3. *`wait_ready(0)` took 1.0 to 1.4 s, and the default was 10 s on the GUI thread.*
   → decision 6.
4. *A supervisor that never supervised exited 0*, and *a watchdog that failed while arming
   stayed "armed"*. → decision 9.

| Question (review round 4) | Measured (Qt 6.11, Direct3D 11 on an RTX 4070, one 5120 × 1440 screen, unless a row says otherwise) |
|---|---|
| What does a pane get that GROWS beyond the screen's edge? | With the display asleep (2026-10-11): `Resize`, `Move` — nothing else. A raw grab is 49 × 500 px for a 136 × 500 window, for as long as the pane stays there; `view.update()` and 1.5 s change nothing (the review: 4 of 13 steps). With the display awake (2026-10-12), the same pane beyond the same edge: `Resize`, `Move`, `UpdateRequest` — still no expose — and the raw grab has the new size. Later that day, the session idle for 25 min with a display-off time of 5 min: `Resize`, `Move` again, the grab stale, the host "live" and `wait_ready(5)` False. On WARP in those same minutes, the display still asleep: `Resize`, `Move`, `UpdateRequest`, and the frame is right — the update request depends on the adapter too; the EXPOSE round 3 waited for came in none of these. A pane SHOWN there was exposed in none of them either |
| The same condition made on purpose: the pane ON the screen, an event filter eats the view's `Expose` / `UpdateRequest` / `Paint` | grown and shrunk, Qt's frame stays 447 × 500 px for a 600 × 500 and a 200 × 500 window. The host says "live" — every fact Qt reports is in place — and refuses on the evidence of the frame. `wait_ready(5)`: False in 0.50 s; `wait_ready(60)`: False in 0.50 s; `wait_ready(0)`: False in 0.00 s. Painting resumes: True, and a frame of the window's size |
| A raw pick right after a resize, no frame in between | MISS — at once after `showFullScreen()`, and for the pane that grew beyond the edge; after one frame, even one of the old size, it hits. The projection is right in both |
| What does a probe frame cost? | 0.7 to 4 ms; 18 to 27 ms right after `showFullScreen()`; about 0.25 s for a 5120 × 1440 frame, or behind a frame Qt is presenting. A whole `wait_ready()` on a host that is live, its probe included: 2 to 6 ms on the GPU, 26 to 31 ms on WARP (447 × 500 px) |
| How long until the expose arrives? | after a resize: 1.0 to 1.5 ms, in the first pass of the event loop; after `show()`: 12 to 91 ms. The pass that handles the first expose takes 0.83 to 1.0 s (it creates the graphics device); one that handles an expose after a grab, about 1 s on this machine |
| `wait_ready()` in the walks | the longest wait beyond its timeout — what Qt had queued for the window when the wait's last pass began (*round 5:* not "ONE handler", as this row said: a pass delivers the whole queue): 0.75 s on the GPU with the display awake, 1.22 s with it asleep, 0.20 s on WARP, 0.007 s on xcb. `wait_ready(0)`: at most 11 ms (31 calls). A False that was not behind such a handler: 0.500 to 0.504 s. Longest quiet spell before a host came up: 0.0 s on Direct3D 11, 0.0 s on xcb + llvmpipe — the bound is 0.5 s |
| The default `wait_ready()` on the FIRST show of a process (18 processes) | top-level: True after 0.86–0.92 s (GPU), 0.70–0.75 s (WARP). Embedded in a splitter: True after 1.67–1.73 s (GPU), 1.52–1.63 s (WARP) — beyond its second by the expose handler of its own window, which was running when the second was up |
| The size check | it allowed two pixels: a 447 × 500 frame was handed out for a 448 × 500 window. "Less than one device pixel" from then on (*round 5:* exact at 100 %, 150 % and 200 % — and not in between; the table below) |
| The walk, fitted to the screen (seed 20261011, 250 steps) | GPU: 252 looks — 67 frames, 185 refusals; `wait_ready()` answered True 47 times, each followed by a frame, and False 108 times; the host took 110 frames for itself and refused none for its size. WARP: the same 67 / 185 and 47 / 108. xcb + llvmpipe: 61 frames, 191 refusals; True 42 times, False 113 times. No wrong frame, every host came up, every wait within its bound |
| The same walk where a 1024 × 768 screen leaves the window | GPU: 61 frames, 191 refusals; True 43, False 112; 11 looks with the pane shown beyond the edge; 9 frames refused for their size (the display was asleep). WARP: 63 / 189 and 44 / 111; 11 looks beyond the edge; no frame refused for its size. xcb + llvmpipe: 61 / 191 and 42 / 113; 26 looks beyond the edge; 1 frame refused for its size. No wrong frame; no wait beyond its bound; no False later than 0.5 s after the last sign of progress plus one Qt handler |
| A supervisor that cannot find its block (a creation time that is not the process's) | it is gone 1.5 s into a 20 s block — with exit code 4 now (it was 0), and the block says "left without having supervised". One that comes up after its block is over: exit code 0, released |
| The whole render tier (round 4: 104 tests) | 103 passed and one control reported, not asserted, in 458 s on the GPU; 101 passed, the two hardware-only budgets skipped and the control reported, in 355 s on WARP — both with the display asleep, the condition in which round 3's head showed the runner's failure on this machine; 96 passed and 8 skipped in 241 s on xcb in the container |

**Review round 5 (2026-10-12).** CI on round 4's head was green on all jobs — `Render 3D
(windows-latest)` 101 passed, 2 skipped, 1 xfailed; `ubuntu-latest` 96 passed, 8 skipped, as
predicted — and the independent re-check confirmed the blocking finding fixed with the display
off. It found two small P1 and five P2; none refuted. What they have in common: each was a
statement that was one measurement short.

1. *"Exact to the device pixel"* was "less than one pixel off". Between 100 % and 150 % that
   lets a neighbour's frame through. And the tests' judge used the same inequality, so it
   was blind exactly where the host was wrong. → decision 5; the judge computes Qt's rounding
   itself.
2. *"`pick()` and `project()` take a frame once per resize"* — once per CALL while the render
   target was behind. → decision 6.
3. *"`wait_ready(t)` returns within `t`, plus the one handler that is running"* — plus the
   whole queue. And *"`STALL_S` after the last sign of progress"* counted wall time, in which
   a busy GUI thread looks like silence. → decision 6.
4. *`wait_ready(inf)` overflowed; a supervisor's failed wait said 0; `supervised` and `gap`
   disagreed.* → decisions 6 and 9.

| Question (review round 5) | Measured (Qt 6.11, Direct3D 11 on an RTX 4070 and on WARP; ratios set with `QT_SCALE_FACTOR` on a 100 % screen) |
|---|---|
| How does Qt size a render target at a fractional ratio? | `QSize(logical) * ratio` — `qRound` per side, half a pixel up: a 442 px pane at 1.25 has a 553 px frame (552.5), a 443 px pane a 554 px one (553.76), a 447 px pane at 1.5 a 671 px one. The reviewer: 161 of 161 sizes at 1.25, 1.5 and 1.75 within 0.5 px |
| "Less than one pixel off" at 125 % | the pane made one logical pixel wider, 442 → 443, with the render target behind (the no-paint filter): `grab()` handed out the 553 px frame and `pick()` answered with the old viewport — on the GPU and on WARP (the reviewer). In the arithmetic 750 of 11,993 neighbour frames passed at 1.25, and every ratio strictly between 1 and 1.5 had some; 1.0, 1.5 and above had none |
| The half-pixel rule | every logical width from 2 to 3000 at 1.0, 1.1, 1.2, 1.25, 1.3, 1.4, 1.5, 1.75, 2.0, 2.25, 2.5 and 3.0, against `QSize * ratio` asked of Qt: 0 of 2,999 right frames refused and 0 of 11,993 neighbour frames accepted, at each of the twelve. On a real window at 1.25: 442 → 443 and 446 → 447 px with the target behind — a raw grab is 553 and 558 px wide, the pane's own frame 554 and 559 — refused by `grab()`, `pick()` and `project()`, on Direct3D 11 (GPU, WARP) and on xcb + OpenGL alike; the reviewer's probe: 0 of 12 handed out (it was 1 of 13) |
| `pick()` / `project()` while the render target is behind | before: 200 `project()` took 200 frames, all refused — 2.0 ms each on the GPU, 4.1 ms on WARP; 13 and 33 ms a frame at 2560 × 1369 (the reviewer). Now: 200 `project()` take ONE frame — 0.06 ms a call, 12 ms for the tick where it was 399 ms — and the 200 `pick()` after them none (0.013 ms a call), on the GPU |
| The steady state, and a resize | 500 `project()` + 500 `pick()`: 0 frames; 60 resize steps: exactly 60 frames (the reviewer; unchanged). What that one frame costs per step: with the display ASLEEP, on the GPU, 33 ms a step for a 60-step splitter drag without a call and 1,031 ms a step with one `project()` (the reviewer: +1.0 s on the GPU, +25 ms on WARP) — a present that waits for a display that is off. With the display awake it is NOT measured: it slept through this round, and "drag the splitter with 3D visible" is on the manual-test checklist |
| `wait_ready(0.2)` behind six queued handlers of 0.3 s | 1.80 s (the reviewer): one dispatcher pass delivers them all. Unchanged — it cannot be changed from the thread those handlers run on — and it is what the contract says now |
| The GUI thread busy for 0.7 s inside the wait, the repaint posted 10 ms after | before: `wait_ready(5)` False after 0.75 s, and True when asked again. Now: True after 1.80 s (the display asleep: the expose that mends it takes a second) |
| `wait_ready(inf)`, `wait_ready(3e6)`, `wait_ready(nan)` | before: `OverflowError` for the first two. Now: a timeout is clamped to a day, one that is not a number is 0; on a host that makes no progress each is False after 0.5 s |
| A supervisor whose `WaitForMultipleObjects` fails | before: exit code 0, "supervised". Now: 3, one line on stderr, nothing terminated |
| The whole render tier (round 5: 105 tests, the 125 % row among them) | 104 passed and one control reported, not asserted, in 411 s on the GPU; 102 passed, the two hardware-only budgets skipped and the control reported, in 287 s on WARP — both with the display asleep. The lifecycle file on xcb + llvmpipe in the container, where the 125 % row had never run: 41 passed, 4 skipped in 159 s; that row gives the same 553 / 554 and 558 / 559 px there |

**Not measured** — stated so nobody assumes it: platforms that un-expose an occluded window
(macOS, Wayland) — a visible, covered window may read "starting" there for as long as it is
covered; `wait_ready()` then answers False after 0.5 s, like for every other cause; a change
of the device pixel ratio in mid-session (a window dragged to a display with another scale);
real display scaling of the operating system (the ratios between 1 and 3 were set with
`QT_SCALE_FACTOR` on a 100 % screen); what the one frame after each resize costs with the
display AWAKE (asleep it was about 1 s a step on the GPU and 25 ms on WARP — a present that
waits for a display that is off; the reviewer expects one vblank when it is on);
what GitHub's Windows runner does with a pane beyond its screen (the walk failed there; this
tree has not run there — the stuck condition is made on purpose in the tier instead). The
round-2 tree on GitHub's own runners (the
Linux numbers above are from a container with the job's packages on the developer's machine,
not from the runner). The `frozen-selftest.yml` workflow: written without access to the
runners and unproven until its first run, in particular the 8-second smoke, which no workflow
ran before, and the supervising process inside a GitHub job. macOS. An integrated GPU; a
display at a scale other than 100 % (the code and the tests carry the device pixel ratio, the
machine did not have one); a failed device creation on OpenGL or Vulkan (only Direct3D 11's
was forced); the memory curve of criterion 10, which stays with L1.3.

## Addendum L1.3 — criterion 2's deferred half and criterion 10's leak half, in the production view (2026-10-12, #385 story L1.3)

Two things this decision left to the workspace story (criterion 2's coexistence with Qt
WebEngine in the product, and "criterion 10's leak half is open on D3D11" in entry 10 of the
evidence log above; ADR-060 is the workspace's own record). Both are answered in the REAL app — its own `main()` with
`OGP_QUICK3D=1`, in a child process on a settings store that is never the developer's
(`tests/integration/workspace_gate_hook.py`) — on the dev box: Windows 11, Direct3D 11, RTX 4070,
Qt 6.11. The bounds are asserted in `tests/integration/test_view3d_workspace_render.py`.

**Criterion 2 — Qt WebEngine beside the production host.** A `QWebEngineView` on a page of one
colour loads and paints (the colour read back from its centre) BEFORE the 3D host was created
and AFTER, in the same session, with the 3D view drawing its garden beside it (131 and 138
distinct colours in a 2334 × 1203 frame, two runs); zero Qt warnings. The automated check uses the map picker's
ENGINE on a local page — the picker's own page needs the network and a key — so the picker
itself stays on the owner's manual checklist. The main window is still a raster window with the
3D pane embedded (`surfaceType() == RasterSurface`), and a 2D pan step costs 1.04 times what it
costs without the 3D view (six alternating rounds of 60 steps along one path at the same canvas
size; bound 1.3).

**Criterion 10, the leak half — located, and closed by a release — reopened by the ground bake (L1.5, #532): every release keeps about half of the same-size ground-tile textures (a Qt Quick 3D 6.11.0 bug, up to ~42 MB per release for the largest ground); G7 measures the product with an allowance derived from its own ground (§8.29.5 limit 11, ADR-059 addendum "Part B").** The pre-registered gate
(private bytes, Theil–Sen over reloads 11–20 of 20, below 10 MB per reload, with its positive
control on the same machine) read **34.6 MB per reload** in the production host on the small
bench plan (98 parts) when every reload rebuilt the engine scene, 0.2 when it rebuilt nothing,
58.8 for the control (the display was asleep: every frame of those runs was a readback). So
the growth this log could not explain (entry 10: 1.5 to 9.0 MB per reload on WARP, +62 to +222
MB by reload 50) is real, grows with what is REBUILT, and is larger on a hardware adapter with
the production scene's shadow passes. Where it is:

- **Not in Python.** `tracemalloc` between reloads 5 and 15 of the same soak: 0.045 MB per reload.
  No geometry wrapper survives its Model (a weak set of every `BufferGeometry`: 0 alive).
- **Not in dedicated GPU memory.** `IDXGIAdapter3::QueryVideoMemoryInfo` (node 0, the local
  segment group, called through `ctypes` — `CurrentUsage` is the figure for the calling process):
  298.1 MB before, 305.6 MB after the first reload, the same after the twentieth.
- **Two retentions inside Qt Quick 3D, separated with a bare host** (100 Models of 3,000
  vertices — 14.9 MB of buffers — created, drawn and destroyed per round, 20 rounds):

  | What the round does | MB per round |
  |---|---|
  | builds the buffers and drops them (no Qt object) | −0.13 |
  | builds the geometries and drops them (no Model) | 0.00 |
  | Models created and destroyed, never drawn (hidden host, or shown and not read back) | 0.8 – 1.0 |
  | drawn through readbacks only (`grabWindow()`), no sun | 22.0 – 22.5 |
  | drawn in PRESENTED frames (no readback), no sun | 6.3 – 7.7 |
  | presented, sun up — 300 / 3,000 / 12,000 vertices per Model | 18.2 / 18 – 20 / 22 – 25 |
  | presented, sun up, the Models cast no shadow | 6.2 |
  | presented, sun up, `QQuickWindow.releaseResources()` once per round | 2.4 – 3.9 (20 rounds), 0.85 – 1.14 (60 rounds) |

  1. **What a frame holds for destroyed Models comes back at the end of a PRESENTED frame —
     and a readback is a frame that is never presented.** `grabWindow()` renders a frame of
     its own and reads it back: it emitted `afterFrameEnd` 0 times in 40 grabs, 40 presented
     frames emitted it 40 times. On Windows update requests come from a display-vblank
     thread, and with the display asleep a visible window presents its first frame and no
     more (the addendum "L1.2" above) — so every soak run with the display asleep, whose
     every frame was a readback, kept everything it drew. Qt's own
     `QT_D3D_NO_VBLANK_THREAD=1` paces update requests by timer; the soak runs with it.
     *This entry was written twice before it was right.* First: "a measuring fact, not a
     product leak". Then — after the ground story read +16 MB per re-bake in a view that did
     not present — "a view that presents nothing keeps every byte uploaded to it", and a
     pacing rule was built on that sentence. Both soaks READ BACK once per cycle. With the
     readback out of the loop a view that presents nothing is drawn by nobody: nothing is
     uploaded (dedicated GPU memory does not move) and what grows is the 1.5 MB per rebuild
     that replacing 98 QML Models costs anyway (the tables below). The growth was per frame
     rendered by a readback and never presented — not per upload, not per edit. The rule
     that follows is about the readback, not about the pipeline (ADR-060 decision 17), and
     the pacing was taken out again.
  2. **Per Model that was ever drawn, Qt keeps cached draw-call state after the Model is
     destroyed** — about 62 kB without shadow passes, about 190 kB with the sun's two cascades,
     independent of the vertex count (the 300-vertex row), 0.16 to 0.2 MB per Model in the
     production host. `QQuickWindow.releaseResources()` gives it back — on a visible window Qt
     keeps the scene graph and drops what it caches. Nothing else does: more frames, the QML
     engine's garbage collection, `clear()` instead of single destroys, an embedded instead of
     a top-level window and the material kind made no difference. No readback is involved
     in this one: the bare host's "presented" rows took none (and read the same with two
     readbacks per round: 6.4 and 18.7 against 6.4 and 18.0).

**The fix** (ADR-060 decisions 15 and 17): `Quick3DHost.release_cached_resources()` — the
pipeline counts the items whose Models each pass destroyed, and the workspace releases when 64
piled up and the pipeline has been quiet for half a second, or at once at 512; one release
costs 2 to 10 ms on the GUI thread — and nothing in the product takes a frame from the live
view.

**The gate, through the product's own path.** No readback inside the measured loop: ONE frame
before it and ONE after it, equal in every run below. Each rebuild is followed by the
workspace's own release, as a user who opened a plan gives it the time. Private bytes,
Theil–Sen over rebuilds 11–20 of 20; the small bench plan (98 parts); RTX 4070; 2026-10-12.
"Frames withheld" is the engine story's no-paint device for the length of the loop — an event
filter that eats the view's expose, update-request and paint events: shown, exposed, on the
screen, 0 frames presented.

| The view | Variant | MB per rebuild | growth over 20 | releases |
|---|---|---|---|---|
| presenting | rebuild on | **2.00** | +125 MB | 20 |
| frames withheld | rebuild on | **1.48** | +34 MB | 20 |
| presenting | rebuild off | 0.01 | +1.4 MB | 0 |
| presenting | positive control (rebuild on, 25 MB kept per rebuild) | 27.3 — fails, as it must | +603 MB | 20 |
| presenting | rebuild on, the workspace's release out of reach | 19.3 | +391 MB | 0 |
| frames withheld | rebuild on, the release out of reach | 1.54 | +27 MB | 0 |
| presenting | rebuild on, the release INSIDE every pass (the "at once" rule, threshold 1) | 1.82 | +42 MB | 20 |

The curve with the release, presenting, in MB: 1374, 1436, 1472, 1472, 1468, 1449, 1452, 1462,
1464, 1466, 1468, 1469, 1470, 1472, 1489, 1476, 1511, 1497, 1478, 1499 — a rise of about 100
MB over the first three rebuilds, then about 2 MB per rebuild with a scatter of ±15. Dedicated
GPU memory rises with it over the first releases (289 → 346 → 362 → 378 MB) and stays there
(slope 0.0); without the release it never leaves 289. So with the release the driver keeps a
larger pool, once: about +90 MB dedicated and +100 MB committed. Not explained further, and
not growing. With frames withheld dedicated GPU memory does not move during the loop at all
(282.5 MB, twenty readings: nothing is drawn), and the same single step comes with the first
frame after the dark spell (committed 1382 → 1498 MB).

**What a readback per rebuild adds** — the way this soak measured until the independent review
of the ground story took the readback out of its own loop; reported, never judged:

| The view | with the release | without it |
|---|---|---|
| presenting | 3.85 (the first runs of this addendum, with up to two readbacks per rebuild: 4.90 and 3.88) | 16.4 (those runs: 29.0, 27.9, 38.5) |
| frames withheld | **8.48** (+266 MB; about 94 MB of it came back with the first presented frame) | **26.0** (+526 MB) |

In a presenting view the readback's frame is given back with the next presented frame, and
the numbers stay in the spread of the ones without it. In a view that presents nothing they
do not come back: that is the whole of what the withdrawn pacing rule was aimed at.

**The same soak elsewhere** (no readback in the loop; one run each, the same day):

| Where | with the release | without it |
|---|---|---|
| the large bench plan (421 parts), RTX 4070, presenting | **6.38** MB per rebuild (+164 MB), 20 releases; dedicated GPU memory 346 → 378 MB in the first five rebuilds, slope 0.0 after | 65.5 MB per rebuild (+1,111 MB over 20) |
| the small bench plan on WARP ("Microsoft Basic Render Driver", the whole process), presenting | **3.32** MB per rebuild (+139 MB) | 20.1 MB per rebuild (+396 MB) |
| the same on WARP, frames withheld | 1.23 MB per rebuild (−1 MB over 20) | — |
| the same on WARP, frames withheld AND a readback per rebuild | 6.20 MB per rebuild (+250 MB) | — |

So the retention is Qt's own and not the hardware driver's: WARP keeps the same 20 MB per
rebuild, and a readback into a view that presents nothing costs there too.

**Longer.** 60 rebuilds through the same path, presenting: **1.78 MB per rebuild over rebuilds
31–60** (2.07 over all 60; +203 MB, of which the first rebuild's step, 1372 → 1445 MB, is 73).
60 releases, the frame after the loop equal to the frame before it, dedicated GPU memory
between 362 and 378 MB throughout (slope 0.0 over the second half).

**What remains, and where its floor is.** After the release about **2 MB per rebuild of 98
Models** stays (6.4 per rebuild of 421) — 15 to 20 kB per destroyed Model, linear over 60
rebuilds, not converging. It is not the cached draw-call state (that is what the release
removes: 19 → 2) and not the mesh, **and it is not graphics state at all: the same rebuilds
in a view that draws nothing leave 1.5 MB each** (1.2 on WARP). A floor of it is Qt's own,
measured in bare Qt with no product code and nothing ever drawn: 100 objects created with
`Component.createObject()` and destroyed with `destroy()` per round, 120 rounds, the QML
engine's garbage collector called every round — **0.78 kB per `QtObject`, 1.4 per `Node`, 2.2
per `Model`, 3.4 per `Model` with a `PrincipledMaterial`**, each a straight line. The engine
package's own parts cost 6.6 to 7.8 kB each that way (never drawn), and 15 to 20 kB in the
production host. Not located further. What it means: a plan change costs about 2 MB, an edit
that replaces one Model about 20 kB — and anything that replaces MANY Models per tick (a date
played back day by day regrows every dated plant) pays that per Model per tick, with or
without the release. Two ways out, neither tried: keep the Model and give it a new geometry
(the spike measured that a GEOMETRY does not survive its Model; the reverse was not measured),
or scale a grown plant instead of rebuilding it.

**What this closes and what it does not.** Criterion 10's leak half holds under its
pre-registered gate, in the production view, presenting and with its frames withheld, on a
hardware adapter and on WARP, over 20 and over 60 rebuilds, with its control firing and with
dedicated GPU memory read for the first time. Open: the residual above; the one-time step of
both memories with the first releases. Not measured: a frozen exe; a CI runner (the
workspace's render tier is not part of CI's render job).

## Addendum L1.10 — closing: Qt 3D removed (2026-10-19, #385 story L1.10)

**Status**: Executed. The decision above is carried out: Qt Quick 3D is the product's only 3D
engine and Qt 3D (ADR-038, now *Superseded*) is out of the code, the dependencies and the
bundle. Nothing of criterion 10 changes with it — its leak half stays reopened by L1.5's ground
textures (#532, above).

**What left.** The US-E6 / E7 window and its adapter (`ui/view3d/view3d_window.py`,
`qt3d_adapter.py`), the pre-L1.1 scene module (`core/scene3d/legacy.py`), the walkthrough helper
(`core/walk_camera.py`), every path of the main window that drove them, the L0 spike
(`spike_q3d/`, `--spike-q3d`, `scripts/bench_view3d.py`, eleven test files), `--selftest`'s Qt 3D
import block, the spec's six Qt 3D hidden imports with `QtQuickWidgets` and the spike's data,
and the two wheels `PyQt6-3D` / `PyQt6-3D-Qt6` 6.11.0. The scars the old window carried and why
the workspace's host needs none of them: ADR-060 addendum "the default and the removal", L1.10
part. The spike's measured values outlive it in `tests/data/l0_spike_reference.json` (the drift
guards read it, §8.10.13); this ADR's evidence log and `adr-048-evidence/` stay as they are.

**The lock** (ADR-050): `uv lock --offline` (uv 0.12.23) after removing the two pins — `uv.lock`
lost the two packages and reordered three resolution-marker lines (the same strings; no version
changed), and `uv export --locked --all-extras --group build --no-emit-project --no-header
--format pylock.toml --output-file pylock.toml --offline` removed exactly the two packages' 26
lines from `pylock.toml`. `scripts/check_dependency_lock.py` agrees; the dependency provenance
record drops the two entries and says why.

**The bundle**, built twice in ONE clean environment (Python 3.11.9, the release pin): synced from
the L1.9 tree's lock and built, then synced from the L1.10 tree's lock — which uninstalled
exactly `pyqt6-3d` and `pyqt6-3d-qt6` — and built again (2026-10-19, the dev box, Git Bash):

| | Before (L1.9 tree) | After (L1.10, with L1.5 merged) | Difference |
|---|---|---|---|
| total | 652,687,676 bytes, 2,876 files | 639,202,072 bytes, 2,819 files | −13,485,604 bytes (−13.5 MB), −57 files |
| Qt 3D bindings (`PyQt6/Qt3D*.pyd`) | 6 files, 2,382,336 bytes | none | all left |
| Qt 3D runtime (`Qt6/bin/Qt63D*.dll`, 11, and `Qt6Concurrent.dll`, which nothing left in the bundle links) | 12 files, 6,078,624 bytes | none | all left |
| Qt 3D plugins (`geometryloaders/`, `renderers/`, `sceneparsers/`) | 7 files, 4,169,352 bytes | none | all left |
| QML modules `Qt3D/` and `QtQuick/Scene2D/` | 15 files, 688,952 bytes | none | all left |
| the spike's QML and shaders | 5 files, 20,612 bytes | none | left |
| the two wheels' metadata | 12 files | none | left |
| Qt Quick 3D + ShaderTools | 610 files, 21,923,461 bytes | the same | nothing new since master |
| SBOM components / `THIRD_PARTY_NOTICES.md` | 74 / 13,200 lines | 72 / 12,348 lines | exactly `pyqt6-3d` and `pyqt6-3d-qt6`: one deleted block, nothing added |

No file arrived; nine changed size — the exe (−82,512 bytes, its archive of Python modules: the
removed modules, with L1.5's ground bake added), the collected-distributions record, the six
translation catalogues and `Garden.qml` (L1.5's ground). Both bundles pass the 8-second smoke and
`--selftest` on the RTX 4070 and on WARP (after: 5.1 s and 4.0 s; the log names "a baked ground of
12 tiles … the selection ring"). A bundle built in a development venv that still has the two
wheels installed carries their DLLs and QML modules anyway (PF-E3D-09 item 10): judge bundles
built from a locked environment.

**Start-up** is unchanged: Qt 3D was never loaded at start (it was imported when the window
opened), and the workspace loads no engine before 3D is asked for — 2.20 s to the first turn of
the event loop on the L1.9 tree against 2.19 s before the flip (median of five), 0 engine modules
in both; after L1.10 with L1.5 merged: 2.12–2.14 s in three runs, 0 engine modules.

**What it leaves open.** The residual per destroyed Model (above) is still Qt's; L1.9 bounded the
one path that destroyed many Models per second (date playback, ADR-060 addendum D3). #532 stays
open: the owner shipped the default with it at the L1 pull request (ADR-060 addendum D5).
(#532 is closed as a tracker by PR #654; the leak remains: QTBUG-151940, TD-040, §8.29.5
known limit 11.)

## Addendum L7 — Qt 6.12 LTS and the atmosphere sky (2026-11-03, #391)

**Status**: Shipped in v1.36.0 (PR #721) after the owner's manual test, 2026-11-03. Two parts: the Qt pins
move to the 6.12 LTS, and an opt-in **atmosphere sky** — Qt 6.12's new `SkyMaterial` with a port
of Qt's `skymaterial` example (Hillaire's atmosphere, ray-marched volumetric clouds) — joins the
painted sky. Preconditions of #391 met: PyQt6 6.12.0 was published on 2026-10-28, and L1.10 had
removed Qt 3D.

**The pins.** `PyQt6` and `PyQt6-Qt6` 6.12.0 (`uv lock --upgrade-package` per package with the
pinned uv 0.12.23, `pylock.toml` re-exported with `check_dependency_lock.py`'s arguments; the
gate agrees). Two things moved with them that ADR-038's scope note did not foresee:

- **WebEngine can no longer float a minor behind.** `PyQt6-WebEngine` 6.10.0 next to Qt 6.12.0
  failed `import PyQt6.QtWebEngineWidgets` with *"DLL load failed … Die angegebene Prozedur wurde
  nicht gefunden"* — the import `main.py` makes at module level, so the app would not start.
  Its 6.12-era release is numbered **6.140.0** (`qWebEngineVersion()` 6.140.0, Chromium
  140.0.7339.225, published 2026-11-02) and requires `PyQt6>=6.12.0`; the pin is
  `PyQt6-WebEngine>=6.140.0,<6.141`, the governance test holds both bounds.
- **QtPdf left the WebEngine wheel** for `PyQt6-Pdf` 6.140.0. The app never imports it; two
  integration tests and `scripts/validate_exports.py` read exported PDFs back with it, so it is a
  `dev` extra. Its runtime files (`Qt6Pdf.dll`, `Qt6PdfQuick.dll`, the `QtQuick/Pdf` QML module,
  the `qpdf` image plugin) still land in the bundle, as they did from `PyQt6-WebEngine-Qt6`
  before: PyInstaller's QML and image-format hooks collect what lies under `PyQt6/Qt6`, and the
  build environment carries every extra. No WebEngine DLL links `Qt6Pdf.dll` (import tables
  read); the notices and the SBOM now name `PyQt6-Pdf-Qt6`.

**What 6.12 changed that this repository had pinned** (each measured or read at the tag, both
versions):

| Fact | 6.11 | 6.12 | What changed here |
|---|---|---|---|
| Pick and cull mode (`qssgrenderray.cpp`) | positive determinants only: front faces of every material | the material's cull mode decides: `NoCulling` picks both sides | the selection witness keeps front faces of culled kinds and every face of `TWO_SIDED_KINDS` (foliage, grass, glass), pinned against the QML; the render tier's selection gate passed in full on 6.12. Accepted as the click hitting what the user sees: a two-sided part is drawn from behind, so it is picked from behind — a crown seen from below, a greenhouse's glass from inside (walk mode). Open for the owner to confirm (PR); `TWO_SIDED_KINDS` treats `vc` as culled although Cutaway draws it two-sided (#720) |
| `QAccessibilityHints.motionPreference` | absent | `NoPreference` / `ReducedMotion`, with a change signal (Windows: `SPI_GETCLIENTAREAANIMATION`, the "Animation effects" switch) | honoured beside the app's setting (FR-3D-LOOK-04): either stops the wind; the drift guard now fails on a SECOND motion hint |
| A destroyed window's lambda-connection proxies | freed in the first deferred-delete round | one round later | the widget-leak test flushes two rounds with a collection after each (PF-TST-36); not a product leak — the event loop keeps turning |
| Destroying an EARLIER sky Texture (`buildSky`'s deferred `old.destroy()`) | the environment's watcher on it was gone with the switch | its destroyed-watcher still fires and sets the light probe to null although the probe is the current sky: after a host's first sun change (in the 3D review's run without the fix: the first rebuild, once also the second; later rebuilds never) the view drew the clear colour (sky-sequence test: (161, 154, 122) against (97, 126, 137); `master`'s code fails identically on the 6.12 wheels) | the environment restores its own `lightProbe` binding in `onLightProbeChanged`, synchronously, before a frame renders (PF-E3D-16); the board, a fresh host per frame, cannot see it |
| Colour-property linearisation (`qssgutils.cpp`) | polynomial | unchanged (byte-identical source) | none |
| `sampleProbe.glsllib` (`qt_sampleDiffuse` / `qt_sampleGlossy`, used by `water.frag`) | — | unchanged (byte-identical) | none |
| `QSGRendererInterface.GraphicsApi` member names | `OpenGL`, `Direct3D11Rhi`, … | identical | none |
| QTBUG-151940 (#532, TD-040) | closed upstream (dev `fd941509f`; 6.12 backport 786236 pending) | the committed reproducer still leaks on the 6.12.0 wheels: 16 → 96 textures over 10 cycles, 8 a cycle (WARP, frames presented); upstream closed on merge in `dev` (Gerrit 785272), backport to `6.12` pending (Gerrit 786236, +2/+1) (2026-11-04) | the versions named move; nothing else |

**The atmosphere sky — the decision.** A second **sky model** (`SkySpec.model`, setting
`view3d/sky_model`, Preferences → 3D View → **Sky**: *Painted* / *Atmosphere with clouds*). The
**default stays the painted sky**: every look of L1–L5 was accepted on it, and changing the
default is the owner's call (asked in the PR). The model is never a quality preset's choice; on
a software adapter there is no sky at all, as before. A change of model is built at once, like
a change of phase.

**The design: the painted sky is the base, the atmosphere is painted over it.** `atmosphere.frag`
is the example's shader up to its `MAIN()`; the app's `MAIN()` evaluates Qt's
`ProceduralSkyTextureData` formula per direction (`paintedSky()`, the same colours the look gives
the painted sky) and mixes the atmosphere over it by
`share = atmosphereWeight × smoothstep(0, hazeDeg, elevation)`:

- **at and below the horizon, and through a 6° haze band, the painted sky shows** — the fog is
  calibrated on the painted horizon (`FOG_OF_HORIZON`), so the meadow meets the same horizon in
  either model and in every direction (the atmosphere's horizon changes with the azimuth, the
  fog's colour cannot);
- **`atmosphereWeight` = 1 − the look's twilight**: the atmosphere fades out through civil
  twilight, so the night is the painted night exactly (measured: −8° sun, frame luma 23.98
  against 23.99, sky 0.9/1.3/6.1 against 0.9/1.4/6.1);
- **the gain is computed per sky**, not chosen: scaled by `atmosphereGain` the atmosphere sends
  the same cosine-weighted luminance onto a horizontal surface as the painted sky it replaces
  (`atmosphere_lut.atmosphere_gain`, 48 × 96 directions of the upper hemisphere). The physical
  sky's radiance changes about sevenfold between a 60° and a 2° sun; the gain runs from 0.055 to
  0.31 (and 0.95 at −4°): the auto-exposure the accepted look implies. Measured on the GPU, the
  sunlit grass reads the same under both skies at every sun height (60°: 197.7 / 197.7; 15°:
  139.0 / 139.0; 2°: 62.9 / 63.3; −2°: 47.6 / 47.2): the probe's light balance against the sun is
  the accepted one, only the sky's hue and structure are new;
- **clouds**: coverage = the weather's cloud (overcast and rain 1.0, snow 0.85, clear 0). Their
  scattered light takes the atmosphere's one gain: `cloudLightGain` = `ATMOSPHERE_CLOUD_GAIN`
  0.064 × the clear sky's gain at the actual sun (`quick3d.look.cloud_light_gain`; the example's
  scale saturates a full cover to white — its own comment says so), calibrated so a full
  Overcast lights the ground at noon as the painted Overcast does (ground luminance 0.198 /
  0.207, about 2 luma). A thick deck diffuses: its forward lobe and its silver lining fade with
  the cover (`atmosphere.frag`, `CLOUD_DIFFUSION` 0.8). Without that, a full overcast was bright
  toward a low sun, a cloudy sunset read 0.96–1.0 of its noon and the L5 weather gates (which
  had not run on the atmosphere) failed; a scale of the clouds' own at a fixed high sun dimmed
  the deck twice (garden at a cloudy sunset 0.6–0.75 of the painted one) and deepened a bright
  band round the horizon (3D reviews). Measured (Medium, 640 × 360): sunset over noon 0.750 /
  0.776 / 0.668 for overcast / rain / snow against the painted 0.761 / 0.781 / 0.674; the
  garden under a cloudy sky 0.96–0.99 of the painted one at noon, 0.90–0.92 at golden hour,
  0.87–0.89 at the sunset mood. The deck also loses the sun through civil twilight as the look
  does (its sunlight × `atmosphereWeight`): the example clamps the sun's slant at the horizon,
  so its deck kept the horizon sun's light down to −6°; every cloudy dusk is monotone, the
  sunset step 0.0088 / 0.0088 / 0.0142 against day ramps of 0.041 / 0.042 / 0.057. Left over
  (#719): under the deck at a low sun the painted haze band reads brighter than the deck above
  it — 30 / 42 / 55 luma toward / across / away from a 0.5° sun (painted sky: 6), 11–20 at 6°.
  The clouds take the look's horizon hue (under a weather, the weather's own grey) in
  proportion to the cover (`cloudHueShare`: the example's analytic sun reddening read beige to
  mustard), and fade out between 120 and 240 km (`cloudMaxDistanceKm`, the example's 80 faded
  them at 2.4–4.7° elevation, where the clear sky's bright horizon then showed as a stripe);
- the disc: the look's sun colour × `ATMOSPHERE_DISC_ENERGY` 4 in its core, shown while the sun
  is up and as far as the cloud lets it (`sunAlpha` = 1 − cloud) — at the painted disc's energy
  the aerosol halo outshone it (240,239,237 under a glow of 248,244,230). The glow around the
  core keeps the painted disc's colour and energy: × 4 there clipped a sunset disc and its glow
  to white (255,255,253 against the painted 222,196,154; 3D review);
- the water: Qt 6.12 lights a custom material through its `IBL_PROBE()` under a `SkyMaterial`
  but leaves `QSSG_ENABLE_LIGHT_PROBE` false, so `water.frag` / `water_door.frag` guard their
  sky term on that macro OR `SAMPLE_PROBE_GLSLLIB` (Qt's probe-sampler include guard) —
  measured on the render tier's raised pool, the atmosphere's water at a 4° sun read
  (1, 18, 32) against the painted (5, 40, 65), and (6, 41, 65) with the guard; the painted
  sky's frames are identical with either guard (PF-E3D-15);
- the air: the example's composition with half its aerosol haze
  (`atmosphere_lut.EARTH_ATMOSPHERE`, turbidity 0.5): at 1 the noon sky read pale and a
  camera facing a low sun washed to cream.

**Why the look-up tables are computed on the CPU** (the example renders both in the frame with
`QuadTextureProvider`). A `SkyMaterial` compiles its shader only once every texture it samples
exists (`qssgrenderskymaterial.cpp`, `skyShaderTexturesReady`: "the GLSL sampler type depends on
the actual texture"), and a provider's texture exists only after its first render. Measured: the
first frame after the atmosphere appeared was white on a shown window; with a texture input left
empty the shader never compiled and Qt drew its built-in debug sky; and the app's offscreen
frames — the board, the probes, `--selftest` — may render only ONCE (a second `grabWindow()` on
the never-shown view was an access violation), so they were white every time. As texture DATA
(`core/scene3d/atmosphere_lut.py`, a numpy port of `transmittance.frag` and `skytexture.frag`,
float32 as the shader computes, within 0.75 % of float64), the table is ready before the first
frame, it is computed once per sun instead of every frame, and the sky's colour is known to
Python — which is what makes the gain exact. The cloud noise volume is likewise texture data
(`core/scene3d/cloud_noise.py`, a port of `CloudNoiseTextureData`, checked voxel by voxel against
a scalar transcription of the C++ to 1e-12); it costs about a second of numpy, so the look
controller makes it on a worker when the model is chosen and shows the painted sky until it is
ready. The volume and the table each have ONE `Texture` for the host's life; the table's data is
refilled in place for a new sun.

**The sun.** The example derives its sun from a light's forward vector; here it is SET from the
solar position (at night the key light is the moon): the engine-frame vector at the sun through
the one scene → engine map, then `(x, y, z) → (−x, −z, y)` — derived from the two shaders (the
LUT reads z as up; `MAIN()` turns it back with `(−s.x, s.z, −s.y)`) and pinned by a unit test over
30 sun positions; the painted sky's measured `sunLongitude = azimuth + 90°` is not assumed for
it. Measured by the board's sky probe (gate G4, disc read 25° off centre in the east, south and
west): bearing error at most 0.02° (the painted sky: 0.08°), the disc read at
11.98° for a 12° sun. (Before the disc energy above, the probe locked onto the horizon glow 9°
below the sun with the bearing still within 0.35° — a gate that checks the bearing alone would
have passed the wrong blob; the render tier also checks the elevation.).

**Cost** (RTX 4070, Direct3D 11, a shown 960 × 540 host): the first atmosphere sky's frame
783 ms against the painted sky's 663 ms (a one-time shader compile); each later sun change
~200 ms on the GUI thread against the painted sky's 122 ms (the sky-view table ~110 ms, the gain
~30 ms), the next frame 1–7 ms after it. The board renders a fresh host per frame and so pays
the compile per frame (~2.5 s).

**Truth gates on the atmosphere** (`render_beauty_board.py --sky atmosphere`, 640 × 360,
low and high): every gate green on the final configuration, the painted
sky's numbers from the same machine and day in brackets — shadow IoU 0.918 / 0.967 / 0.962
(low) and 0.985 / 0.968 / 0.962 (high) at 15° / 35° / 60°, identical (the key light is the
same); north-up identity NCC 0.757 (identical); night over noon 0.093 / 0.086 (0.100 / 0.092;
bound 0.25); the night rows' luma 53.60 / 51.31 (53.61 / 51.32); dusk monotone, the sunset
step 0.0089 / 0.0087 against the day ramp's largest 0.030 (0.0067 / 0.0066 against 0.028 /
0.029); the low preset's picket alias error 7.91 (8.07); the plan edge 0.43 / line 1.36
(0.21 / 1.64; bounds 1.0 / 2.0); no Qt warning or error in either board. The mood order is read on the garden: the render tier gates
noon > golden hour > sunset > night on `ground_luminance` (the rows below the horizon,
`board_probes.ground_luminance`) on both skies, and on the whole frame on the painted sky
only — facing a low sun, the atmosphere's sun and its halo enter the frame and its sunset
frame read up to 1.9 % above its golden hour while the garden below darkened 23–25 %, as
under the painted sky. (Before the 3D review the tier allowed that swap within 3 %; the
review replaced the tolerance with the garden's own order.) The distant-horizon rows (`--horizon`) read the same as the painted
sky's and failed its then-3.0-luma bound on BOTH skies and on `master` with Qt 6.11 alike (403 m / 15°:
3.44 / 3.48; 67 m / 31.6° high: 3.11) — #714, closed by re-measuring the smooth fog ramp
at the render tier's 640 × 360 and re-deriving the bound to 3.6 (ADR-059's addendum).

**Self-test** (`--selftest`, point 8): the frozen exe now renders the atmosphere from the bundle,
clear and under 0.7 of cloud, with no probe (a machine without a GPU can afford that), against
a frame without a sky. With the revision below (half resolution, the sky's own exposure) it
reads 81.4 apart from the plain background and 24.5 between clear and cloudy, on the GPU and on
WARP alike (bounds 11 and 7, a quarter of the first build's 44.3 and 28.1); the three frames
took 10.2 s / 9.5 s, the cloud volume made once included.

**Licences** (per-file check at the tag; `qml/PROVENANCE.md`, `qml/LICENSE-qt-skymaterial.txt`):
the example's sky shader (`advancedsky.frag`, three marked changes) and the two look-up-table
shaders ported to numpy (`core/scene3d/atmosphere_lut.py`) are MIT (© 2023 Fernando García Liñán,
© 2026 The Qt Company), the QML
and the noise generator BSD-3-Clause (offered as "LicenseRef-Qt-Commercial OR BSD-3-Clause"); the
painted-sky arithmetic re-expressed in `paintedSky()` and `painted_radiance()` comes from Qt
Quick 3D itself ("LicenseRef-Qt-Commercial OR GPL-3.0-only"), the module the app already ships
under GPLv3. All compatible with the app's GPL-3.0-or-later; the per-file table and the one
statement of the rule are `qml/PROVENANCE.md`.

**Left open.** The default model: the painted sky stays the default as built. The owner accepted
this build ("works perfectly as is") without answering that question by name, and an integrated
GPU is unmeasured (#720). The first-frame shader compile could be
pre-warmed like the Cutaway's (`shaderWarmer`). (Whether a "partly cloudy" weather should exist
was answered by the owner's manual test: see the revision below.)

**Revision after the owner's manual test (2026-11-03): the atmosphere only draws the sky.** The
owner's frozen exe crashed natively while testing *Atmosphere with clouds*. The cause is Qt
6.12.0's `SkyMaterial` light cube: its pre-filter (`QSSGRenderSkyMaterialManager::
runPrefilterCycle`) used a freed QRhi resource (PF-E3D-17, with the dump, the probe and the
numbers). The owner also saw no difference between the skies: Clear has no cloud, and Overcast
and Rain close the deck, so the clouds never showed. The owner chose to keep the atmosphere,
fix the crash, and add a partly cloudy weather. What changed:

- **The painted sky lights the garden under both models.** The atmosphere is `enableIBL:
  false` and `skyboxMode: ScreenSpaceHalf`. Qt draws it on screen per frame
  (`SkyMaterialBackgroundPass`) and never builds its cube (`resolveLayerIblTexture` builds one
  only for image-based light, Cubemap mode, reflection probes or a screen texture). For the
  atmosphere model the host builds the painted sky first (`buildSky`) and then writes the
  atmosphere (`buildAtmosphere`) in the same GUI-thread turn. The painted texture stays the
  environment's `lightProbe`. So the light balance above is now exact by construction, and the
  cloudy-light numbers (0.96–0.99 at noon, 0.87–0.92 toward sunset) no longer apply: the
  garden is lit as under the painted sky in every weather. `atmosphere_gain` and
  `cloudLightGain` still scale the sky and the deck to the painted sky's brightness. The
  water's widened probe guard (PF-E3D-15) is no longer reached under the atmosphere, because a
  `lightProbe` is set; it stays, correct for any `SkyMaterial`.
- **The sky applies its own exposure** (`atmosphere.frag` `skyExposed`, `skyExposure` =
  the look's `probeExposure`): `1 − exp(−radiance × exposure)`, the curve of Qt's `qt_exposure`
  that the painted sky's skybox shader runs. Qt's screen path passes `FRAGCOLOR` straight
  through under our post effects, because its tonemap variant has no
  `QSSG_FORCE_IBL_EXPOSURE`. The first build of this revision missed that (3D review, round 3,
  REJECT): the sky read 1.8× too bright by day and 2.9× at night, 25–28 % of a low-sun frame
  clipped, the disc vanished, and the horizon step rose to 36–56 luma. With the curve (no fitted
  constant; a multiply needed an unexplained 0.80 by day because the curve compresses bright
  values): clipping 0.0 / 0.8 / 0.04 % at golden hour / sunset / morning, horizon steps 1.1–3.4
  luma (bound 6.0), the disc read at 12.06° for a 12° sun with a bearing error of 0.01°.
- **The crash is gone.** A full-app probe of the manual checklist crashed 3 of 5 times at one
  painted to atmosphere switch before the fix. After it, the same sequence ran 4 × 240 s with
  no crash.
- **Partly cloudy** (`weather.WEATHER_SPECS["partly_cloudy"]`): cloud 0.4 is the atmosphere's
  cover; the sun stays out, because the light takes 0.15 of the overcast's changes
  (`WeatherSpec.light`) and the sky 0.25 of its grey (`WeatherSpec.grey`). Every other weather
  has one share for all three, so its look under the painted sky is unchanged (under the
  atmosphere Snow's disc went from 0.15 to 0.30 and its clouds' light × 1.09). Wind 3.0, haze
  0.9, dry, and the mood
  stays a day (it is overcast from 0.5). The cover sheet of the owner pass read scattered clouds
  at 0.35 and 0.6 and a closed deck at 1.0. Separate clouds take
  `ATMOSPHERE_THIN_CLOUD_LIFT` 4.2 × (1 − cover)² more light (× 2.5 at 0.4, × 1 at Overcast and
  Rain, × 1.09 at Snow), because the 0.064 was calibrated on a full deck and they read as dark
  smoke at noon; `sunAlpha` goes only as the deck closes (1 − max(cloud − 0.5, 0) / 0.5), since
  the clouds themselves hide the disc. Today's Weather maps WMO code 2 (partly cloudy) to it;
  codes 0 and 1 stay clear. The painted sky shows only its slightly greyer blue; the clouds are
  the atmosphere's. ADR-070's weather gates run on it (`HORIZON_WEATHERS`).
- **Cost** (RTX 4070, Direct3D 11, a shown 1280 × 720 host looking into the sky, the median of
  40 frames, the range of three runs of the same code): painted 2.1–2.3 ms; atmosphere at
  cover 0: 2.2–3.6 ms (Half), 3.2–3.7 (Full), 2.1–3.5 (Quarter); at cover 0.4: 3.1–5.6 ms
  (Half), 4.5–8.9 (Full), 3.7–4.9 (Quarter). The atmosphere's numbers move by up to × 1.9
  between runs. The GPU idles at 210 MHz between them, so we read that as its clock state, but
  did not pin it down; compare ranges, not single runs. Half and Full look the same, so the
  default is Half. A sun change now also builds the painted sky (~120 ms) beside the sky-view
  table, about 0.32 s of GUI thread in all, and the light cube's one-time filter is gone. An
  integrated GPU is still unmeasured (owner question), and a playing day stalls on those
  builds (#722).
- **The self-test** renders the atmosphere without the painted probe (`sky_probe=False`): a
  machine without a GPU cannot afford a probe filter. The rule it checks is unchanged.

## Addendum L7.1 — the atmosphere sky meets the painted horizon (2026-11-09, #716, #719)

**Status**: Accepted; shipped in v1.39.0 (PR #882, visual-polish package; owner's manual test 2026-11-10). Both issues
are one problem: at and below the 6° haze band the painted sky shows, so the fog meets the
same horizon in every direction (unchanged), and above it nothing tied the atmosphere's
LEVEL to that horizon. The clear sky's low band was too bright (#716), the cloud deck too
dark (#719). The painted sky, the default, is untouched: the painted board's seven shots
are identical to `master`'s to the level (max difference 0). The sun's azimuth and
elevation, the shadows and every truth gate are untouched: the key light and the probe are
the painted sky's, as since L7's revision.

**Measured with a new board phase** (`render_beauty_board.py --sky-bands`): sky-only frames
over the empty meadow at a 300° sun, toward, across and away from it, Medium, 640 × 360, RTX
4070, binned by WORLD elevation in 0.5° bands within ±4° of the bearing
(`board_probes.sky_profile`; an image row is a plane, PF-L3D-19). The render tier gates it on
both skies (`test_view3d_looks_render.py`); every gate below was observed failing on `master`
with the same phase first.

**#716 — one gain, redistributed per elevation.** `atmosphere_gain` scaled the whole sky by
one number, so the atmosphere's steep fall from horizon to zenith stayed: its 6–15° band read
1.37–1.60× the painted sky's luminance over the azimuth (up to 2.1× toward a low sun), its
zenith 0.5–0.8× (Python model of the drawn sky), and its bright low band stood over the
painted horizon of the haze band, so the sky darkened toward 0.5°. The reviewer's proposal —
one `lowBandScale` faded out between 6° and 25°, the gain re-integrated over the sky as drawn —
was modelled first and not built: it removes the darkening, but with the light kept the gain
rises and the faded band becomes a bright belt (rings at 1.3–1.5× the painted sky at 25°),
the 6–15° band stays at 1.10–1.19× (over 1.15 at 6°, 2° and 0.5°) and the zenith at
0.57–0.83×. Instead `atmosphere_lut.sky_profile` gives every ring of the clear
atmosphere the mean luminance of the painted sky's GRADIENT at its elevation (the painted
sky without its sun) × one glow factor, and rides in the sky-view table's alpha, relative to
the gain. Normalising on the painted ring MEANS was modelled first and rejected: the painted
disc's glow spread round the ring at the sun's elevation (+10 % at a 60° sun, PF-L3D-22). The
gain and the glow factor are integrated over the sky as drawn (each direction weighted by the
atmosphere's haze share), so the drawn sky still sends the painted sky's light onto a
horizontal surface (model: 1.0002–1.0003; the gain moves by at most 0.9 % against L7's).

| Clear sky, 300° sun | `master` | branch | painted |
|---|---|---|---|
| darkening 20° → 0.5°, away (luma), suns 60 / 15 / 6 / 2 / 0.5° | 1.7 / 18.3 / 21.9 / 20.8 / 16.7 | 0.0 at every sun | 0.0 |
| darkening 20° → 0.5°, across | 0.1–0.7 | 0.0 | 0.0 |
| 6–15° band over the azimuth (1 : 2 : 1), over the painted sky's | 1.37 / 1.44 / 1.49 / 1.59 / 1.60 | 1.05 / 0.94 / 0.96 / 0.99 / 0.99 | 1 |
| … toward the sun at 2° / 0.5° | 1.98 / 2.10 | 1.35 / 1.42 | 1 |
| meadow under the frames, atmosphere minus painted (luma) | 0.00 | 0.00 | — |

Toward a low sun the sky still darkens below the sun's glow into the painted horizon (24–26
luma at 6–0.5°; `master` 39–46; the painted sky 10 at a 15° sun): that is the disc's own glow
meeting a horizon that must be the same in every direction, and is not gated. The issue's
grass criterion (±1 luma at 60°, 15°, 2°) holds trivially: the painted probe lights the garden
under both models since L7's revision (PF-E3D-17), so `atmosphere_gain` no longer reaches the
ground; the meadow under the sky-band frames is identical on `master` and the branch
(mean luma of the −6…−3° bands, away: 200.99 / 150.35 / 69.01 at 60° / 15° / 2°, the same
under both skies).

**#719 — the deck anchored on the painted haze band.** The deck 10° up read 11–14 luma under
the painted band from noon down to a 6° sun and 37–45 at sunset (its light is the example's
sun through a ground airmass, which dies faster than the painted sky dims: 0.29 of its noon
luminance at a 0° sun against the painted sky's 0.6; then the clear sky's gain lifted it again
in twilight, the "rise after sunset"). Two changes, both measured:

- **the sun side of the clouds' ambient diffuses with the cover** (`atmosphere.frag`, a fourth
  marked change to the example's `raymarchClouds`: `sunFacing` toward 0.5 by
  `CLOUD_DIFFUSION × cover`, as the forward lobe already did). Its sample is the clear sky's
  aerosol glow beside a low sun: a closed deck read 138 / 120 / 102 luma toward / across / away
  at a 0.5° sun, 126 / 120 / 119 after. One scale cannot meet a band with a spread of 36 luma;
- **a deck's light takes an anchor** (`quick3d.look.deck_anchor`, on `cloudLightGain`):
  `ATMOSPHERE_DECK_LEVEL` 1.48 by day, to the power of how closed the deck is (0.5 → 1, as
  `sunAlpha`; Snow is 0.7), times `ATMOSPHERE_DECK_SUNSET` per sun elevation (1 by day, 2.08 at
  0°, 0.53 at −4°; log-linear) for every deck (cloud ≥ 0.5, the overcast mood's boundary).
  Partly cloudy takes neither. Measured in the frame: the deck rendered at factors 1 and 2 at
  14 suns from 60° to −5°, the factor solved from the local response so that under a full
  Overcast the deck 10° up reads the painted sky's luminance over the azimuth, then checked.
  A two-source CPU model of the deck through `skyExposed` missed by −74 % to +23 % (the frame
  passes the scene's tone mapping after the shader, PF-L3D-23). The reviewer's proposal — a
  factor table on `cloud_light_gain` — is what was built, plus the diffusion it lacked; the
  failed slant clamp (deck 231 at a 0° sun) was not repeated: the slant is unchanged.
  Snow's own sunset needed the shape in full and its level only by closure (with both by
  closure its across view read 13.4 at 0.5°).

| Band (3°) minus deck (10°), luma, toward / across / away | `master` | branch | painted |
|---|---|---|---|
| Overcast and Rain, 6° sun | 9.9 / 14.0 / 16.9 | −0.9 / 0.8 / 0.0 | 3.0 / 5.7 / 5.7 |
| Overcast and Rain, 0.5° sun | 26.5 / 37.5 / 51.0 | 1.1 / 3.9 / 5.6 | 6.2 / 6.0 / 6.0 |
| Snow, 6° sun | 1.5 / 13.9 / 4.3 | −4.4 / 4.2 / −8.1 | 4.1 / 7.4 / 7.4 |
| Snow, 0.5° sun | 19.2 / 37.6 / 38.4 | −1.9 / 8.0 / −0.1 | 8.9 / 8.6 / 8.6 |
| Overcast, 14 suns 60° … −5° (before: the diffusion alone) | up to 44.8 (0°) | −1.7 … 7.6 | 1.2 … 7.2 |
| Snow, 14 suns 60° … −5° (before: the diffusion alone) | up to 43.1 (0°) | −8.1 … 9.7 | 2.7 … 9.6 |

The colour step at the haze line went down with it (ΔE76 band against deck, toward a 0.5° sun:
Overcast 9.9 → 0.3, Snow 8.8 → 3.5 before the hue share below; the painted sky's own 4.1).

**Cost**: none measurable — the profile reuses the gain's pass and the cached table (a new sun's
Python work 244–270 ms median against `master`'s 259–275 ms; a new weather at the same sun
1.9 ms).

**Snow's deck at a low sun** (the owner's note on this addendum's first build; fixed and
measured). The clouds' hue share was the cover alone, so Snow's 0.85 kept 15 % of the deck's
own colour, lit by the example's sun through a ground airmass, which is nearly pure red at a low
sun. The blend keeps luminance, so a pure red brings a large red channel: the deck read pink over
a grey haze band. `quick3d.look.cloud_hue_share` now keeps a cloud's own colour only where the
cloud is thin AND the deck open: 1 − (1 − cover) × (1 − closed). `deck_closure` is the one
measure of "closed" for the disc (`sunAlpha`), the anchor and the hue. Partly cloudy keeps 0.4,
Overcast and Rain 1, Snow 0.955. A share of 1 was measured too (the weather's neutral grey,
C*ab 1.3–1.5). 0.955 is continuous in the cover and keeps the painted deck's chroma; how warm a
snowy sunset may be stays the owner's call.

| Snow deck 10° up (`--sky-bands`), sun 1 / 0.5 / 0 / −1° | `master` (0.5°) | before | after | painted (0.5°) |
|---|---|---|---|---|
| chroma C*ab, toward / across / away | 8.7–11.5 | 7.3–9.7, hue 14–32° | 3.2–4.0, hue 359–27° | 3.3–3.6 |
| ΔE76 deck against the band (3°) | 8.4–20.5 | 3.1–6.5 | 1.0–4.8 | 4.2–4.3 |
| deck chroma at any of the 14 suns 60° … −5° | — | up to 9.7 | up to 4.0 | — |
| band minus deck (luma) over the 14 suns | — | −8.1 … 9.7 | −7.5 … 9.6 | 2.7 … 9.6 |

Both columns were rendered on the same tree, "before" with the old share patched in. The deck's
lightness moved by at most 0.3 L* at every one of the 14 suns.

**Render tier on the merged tree** (this branch with `feature/3d-visual-polish`: `master`
v1.37.10, #737, #743/#744; RTX 4070, 2026-11-10):

- `test_living_garden_render.py::test_the_living_board_renders_every_shot` passes on both skies
  (the atmosphere again after the hue share). L5 on the atmosphere, branch against `master`:
  cloudy sunset over noon 0.737 / 0.776 / 0.796 / 0.720 against 0.772 / 0.770 / 0.792 / 0.712
  (Partly cloudy / Overcast / Rain / Snow; gate < 0.85). Every cloudy dusk is monotone, with
  `sky_dusk_ok` everywhere. The hue share moved only Snow (0.719 → 0.720). Under Overcast, Rain
  and Snow the garden's ground luminance, atmosphere over painted, is 1.000 at noon, golden hour
  and sunset. #719's "0.87–0.99" predates L7's revision: the painted probe lights the garden under
  both models since then;
- `test_quick3d_selftest.py`: 11 passed, on the GPU and on WARP. The atmosphere frames lie 82.3
  off the plain background (bound 11) and the cloudy band (cloud 0.7, hue share 0.82) lies 26.1
  off the clear one (bound 7; 27.6 with the old share);
- `test_view3d_looks_render.py`, the board, moods, night and sky-band subset (26 tests): 22
  passed. On this machine an offscreen grab takes 2.0–3.3 s per 640 × 360 frame (with and
  without `QT_D3D_NO_VBLANK_THREAD`, on any tree), so the production board needs 935–1004 s
  against the tier's 780 s watchdog. The run lengthened only the timeouts, with a pytest plugin
  outside the repository; the bounds were not touched. The sky-band gates on the merged tree:
  darkening 0.0 across and away at every sun; the 6–15° band at 1.05 / 0.94 / 0.96 / 0.99 / 0.99;
  band minus deck −0.9 … 5.6 (Overcast, Rain) and −7.5 … 7.4 (Snow); the meadow unchanged. The
  night/day test reads the night 0.000 luma off the painted night at every preset and the day
  sky 15.66 off the painted one (bound 5; 17.7 before the profile). The four failures:
  - G4 on the atmosphere, in two tests: the 6° disc read 0.49° low. The finder was at fault, not
    the disc (next paragraph). After the fix the night/day test passes, with the atmosphere's
    worst errors at 0.06° bearing and 0.07° elevation. The production board was not rendered
    again; its own 48 sky views, read again offline by the new finder, give 0.07° (atmosphere)
    and 0.13° (painted) at worst;
  - `test_dusk_fades_and_sunset_is_no_cliff` on BOTH skies: at Medium, High and Ultra the night
    frame reads 0.004 above the −5° frame (0.0402 → 0.0445 painted). This change did not cause
    it. The merged base's own full painted board (`d319bce0`) shows the same rise to the digit
    (+0.00425 / +0.00400 / +0.00412). The `--dusk` phase alone is monotone and identical on the
    base and on the branch (night 0.0300), and inside the full board the night reads 0.0445, so
    an earlier phase leaves state behind. It is left for a follow-up.

**The sun-disc finder (G4) keys on a clipped core.** It took a plateau of pixels with every
channel ≥ 250. Whether a warm core clips blue depends on the sky behind the disc. The
atmosphere's 6° core read (255, 255, 252) on `master` and on the merged base, and
(255, 255, 243) once the profile dimmed the sky round a low sun. The disc stood where it was,
but no plateau was found, and the warm fallback read it 0.49° low over the haze band.
`board_probes.sun_disc` now takes luma ≥ 250, because a warm core clips red and green first:
the 6° plateau is 169 px at 5.96°, the 12° plateau 130 px at 12.05°. The painted discs peak at
200–216, keep the fallback and read as before.

## Addendum #798 — the meadow's grass (2026-11-10)

**Status**: Accepted; shipped in v1.39.0 (PR #882, visual-polish package; owner's manual test 2026-11-10). The 3D survey's top
visual defect: from the app's default framing 73–80 % of the picture was flat green (local luma
std under 1.5 over 9 × 9 px; the survey read 80 % on the family garden, measured here 79.0 %),
the meadow's own texture a luma std of 0.54–0.62, and at eye height the plan's open ground a
football pitch against the textured lawn beside it. Cause, confirmed in the code: the endless
meadow and the bare plan rectangle were `PrincipledMaterial`s with only `baseColor:
root.meadowColor` (`look.MEADOW_ALBEDO`), and the bake paints uncovered plan ground in the same
flat colour (`ground.MEADOW_RGB`). The issue's references held but one: `MEADOW_ALBEDO` is
defined in `core/scene3d/look.py`; `quick3d/look.py` only maps it onto `meadowColor`.

**Decisions.**

1. **One shader for every piece of ground.** `ground.frag` draws the baked tiles, the bare plan
   rectangle and the meadow (three `CustomMaterial`s with the same inputs, pinned by
   `test_quick3d_qml.py`). The plan's edge is therefore the same function on both sides, and its
   step is zero by construction instead of a tuned match. The issue proposed a separate
   `meadow.frag`; rejected: a second shader is a second function at the edge.
2. **The grass is the canvas's own GRASS texture**, untinted (`resources/textures/grass.png`, no
   new asset), laid in world space at the canvas's scale (one texel a centimetre), uploaded once
   per host as its LINEAR colour over its own mean (`core/scene3d/meadow.grass_detail`, RGBA16F,
   `GrassDetailTexture`). The mips of a linear float texture keep the mean; the mips of the sRGB
   bytes would darken minified grass to 0.983 of its luminance (about a code) and shift its hue
   (PF-L3D-30). The texture's linear mean IS `MEADOW_ALBEDO` (to the code, by the sRGB curve,
   as L0 derived it; within 1.2 % per channel by the engine's polynomial), and dividing the
   texture's own mean out keeps the edge even for a changed texture.
3. **No visible repeat.** Round 1 (the texture as it lies and turned 37° at 1.618×, summed
   around the mean so the variance stays; 9 m and 41 m octaves) drew a lattice from above: the
   texture's mottle repeats every 2.56 m (folded amplitude 2.15 luma at 60 m height). The
   detail is high-passed (Gaussian sigma 16 cm, wrapped: the blades stay), and a 3.1 m octave of
   value noise takes the mottle's place; every octave is turned its own way. Brightness 4 / 6 /
   7 % at 3.1 / 9 / 41 m, hue 3.5 % at 17 m (`GRASS_VARIATION`), all of mean 1. After: 0.86 luma,
   no visible lattice. A value noise has no mips: each octave fades as a pixel's reach on the
   ground (`fwidth` of the world position) grows from 0.05 to 0.15 of its wavelength
   (`meadowOctave`). Without that the board's distant-horizon rows failed their gate: 3.80 luma
   at 403 m and 15° against 3.48 on the flat meadow (bound 3.6; at 0.15–0.4 of the wavelength
   still 3.58); with it 3.48, and the far meadow is the flat mean, as before.
4. **Open plan ground is marked by the bake's alpha.** The bake starts each tile as the meadow's
   colour at alpha 0 (`ground_bake.OPEN_ALPHA`) and `QPainter`'s premultiplied source-over leaves
   every colour byte as it was (of the bake's 477 tests only the one that pinned the bare
   alpha changed) while the alpha becomes
   the items' coverage; `ground.frag` adds the grass's deviation in proportion to `1 − alpha`
   (PF-L3D-31). Rejected: painting the grass into the bake on the CPU — two implementations of one
   function, a plan baked at ½ or ¼ px/cm would be blurrier than the meadow at its own edge, and
   every bare tile would need bytes of its own.
5. **The owner's call — the plan's open ground takes the grass too** (`look.OPEN_GROUND_GRASS`
   = True, `LookSpec.open_ground_grass`, `Garden.qml`'s `openGroundGrass`). At L0 the owner
   answered question 6 ("Meadow grass as now (a flat colour, an honest 'no lawn here'), meadow
   with subtle value noise …, a neutral mown texture, or bare soil?") with "keep as-is". This
   build changes the meadow outside (what #798 asks) and, by default, the open ground inside;
   setting the constant to False is the veto: open plan ground keeps the flat colour and only
   the meadow is grass. Both variants are rendered for the handoff.
6. **The truth view keeps the flat colour** (`groundSurface` 0 in `topDown`): shadow IoU and the
   orientation probe are unchanged.
7. **The weather reaches the meadow in the shader only.** `apply_weather` no longer weathers
   `meadow_albedo` (it darkened and snowed the flat meadow in Python while the tiles were
   weathered in `ground.frag`); the meadow now takes the ground's one tint and cover, as the
   tiles do. The twilight fill (#802) lights it like the tiles (default lighting of a custom
   material).
8. **The Low preset draws the grass without its variation** (`PresetSpec.meadow_surface = MEADOW_GRASS`;
   Medium and up `MEADOW_GRASS_VARIED`). The issue allowed a cheaper Low past about 1 ms. On
   the software adapter (WARP, the compatibility mode, which is Low; 960 × 540, the family
   garden) the full surface cost +3.65 ms over the base's 47.3 (paired median of six rounds,
   IQR +1.6 … +5.2): the variation's value noise 2.1 ms of it, the grass's two fetches 0.4.
   Without the variation: +1.63 ms over 44.3 (IQR +0.7 … +3.5). The default framing's flat
   share at Low stays 0.135 (0.125 with the variation).

**Measured with a new board phase** (`render_beauty_board.py --meadow`; `board_probes.flat_share`,
`meadow_mask`, `track_luma` / `temporal_noise`, `repeat_amplitude`, each with a positive control in
`test_board_probes.py`): the app's default framing (`camera.frame_pose`) and the walk shot's eye
level at the noon shot's sun (21 June, 11:00 UTC), High, 1280 × 720, RTX 4070; "before" is the
production board on the base (`56ab8e0c`, an archive), "after" the final surface as the render
tier measured it on the merged tree (`test_meadow_render.py`). The far-meadow flicker follows up to 400
ground points 30–150 m out (nearer for a small plan's view) through ten frames of the default
framing orbiting 0.5° a frame and of a flight 2.5 m high along the plan's south side, 25 cm a frame
(7.5 m/s at 30 fps).

| | family garden | food forest | raised bed | balcony |
|---|---|---|---|---|
| flat green, default framing (before → after) | 0.790 → 0.137 | 0.804 → 0.092 | 0.734 → 0.001 | 0.753 → 0.000 |
| flat green, eye level | 0.112 → 0.005 | 0.091 → 0.041 | 0.262 → 0.073 | 0.242 → 0.071 |
| meadow's texture (mean local luma std) | 0.54 → 5.66 | 0.55 → 6.37 | 0.62 → 9.72 | 0.56 → 9.16 |
| meadow's mean luma | 155.18 → 154.93 | 154.81 → 154.61 | 150.18 → 151.27 | 154.26 → 155.78 |
| at 1920 × 1080: flat green, default / eye | 0.804 → 0.059 / 0.129 → 0.011 | 0.814 → 0.026 / 0.099 → 0.041 | 0.745 → 0.001 / 0.269 → 0.062 | 0.762 → 0.000 / 0.278 → 0.062 |
| far-meadow zigzag, orbit (luma RMS) | 0.094 → 0.231 | 0.098 → 0.231 | 0.085 → 0.241 | 0.088 → 0.332 |
| far-meadow zigzag, flight | 0.027 → 0.099 | 0.027 → 0.094 | 0.032 → 0.099 | 0.036 → 0.101 |

What is left flat in the default framing is the fogged band at the top of the frame (the family
garden's rows 0–120 read 62–88 % flat, the rest under 7 %): the haze flattens it, as it should.
The repeat from 60 m above, folded onto one 2.56 m period: flat 0.002 luma, round 1 2.15 (the
lattice, visible), after 0.86 (not visible); the grass without mipmaps (a mutated `Garden.qml`,
the flicker gate's positive control) reads 3.38 / 5.40 zigzag in the orbit / flight. The
meadow's mean luma moves within ±0.4 in every mood of the board's shots and living shots on the
family garden (noon, golden hour, sunset, morning, December noon, night, walk; overcast, rain,
snow, dew, the lights' night), e.g. snow 163.83 → 164.22, rain 85.02 → 85.09, night 41.07 → 41.15.
The track was first read on whole pixels and flickered on its own (0.91 luma on the same frames,
debug-verbose case study 227).

**Gates on the merged tree** (base `1138b0aa` against this branch; bench plan, 640 × 360, RTX
4070, the painted sky unless said; the board's phases run one at a time with a longer watchdog,
this machine's offscreen grab taking 4–5 s, and judged with the render tier's own assertions):

| Gate | before (Low / High) | after (Low / Medium / High / Ultra) |
|---|---|---|
| plan edge, frame less its plan-free twin: step / line | 0.00 / 0.72 | 0.00 / 0.93 (atmosphere sky 0.00 / 0.72) |
| plan edge on the frame itself (the grass's pattern): step / line | 0.21 / 1.64 | 2.12 / 3.93 |
| horizon, per mood (gate 3.6): step / dip / ridge | 3.12 / 0.08 / 0.82 | 3.12 / 0.20 / 0.82 (atmosphere 3.52 / 0.08 / 1.31) |
| distant horizon rows (gate 3.6) | 3.48 | 3.49 (3.80 before the octave clamp) |
| shadow IoU 15 / 35 / 60° | 0.918 / 0.967 / 0.962; 0.985 / 0.968 / 0.962 | 0.920 / 0.962 / 0.953; 0.922 / 0.967 / 0.960; 0.984 / 0.967 / 0.961; 0.985 / 0.969 / 0.962 |
| north-up NCC (identity) | 0.7637 | 0.7637 |
| sky disc azimuth error | 0.08° | 0.08° (atmosphere 0.06°) |
| night over noon | 0.0998 / 0.0926 | 0.0998 / 0.0931 / 0.0927 / 0.0931 |
| dusk monotone, garden monotone, sunset step under the day ramp | yes, yes, yes | yes, yes, yes at every preset |

On the tree merged again with #800/#805 (its AO floor and plant sway; Low / Medium / High /
Ultra): plan edge (twin) 0.00 / 0.03 / 0.01 / 0.02, line 0.93 at most; distant horizon rows
3.48; per-mood horizon 3.12; IoU 0.920–0.985; north-up 0.7637; night over noon 0.094–0.100;
every dusk and garden dusk monotone; the fence's aliasing at Low 8.11 against Medium's 8.79
(base 8.05 / 8.91). Render tier: `test_meadow_render.py` 4 passed, `test_quick3d_selftest.py`
11, `test_quick3d_render.py` 51, `test_scene3d_ground_render.py` 27 (its WARP keep-alive
soak failed its own precondition — a cycle presenting one frame — on the base and the branch
alike while other agents rendered, and passed on the next run).

The plan's edge cannot be judged on the frame any more: a 2 m line of grass is not flat, and the
fits read its pattern (the same in every preset and mood: −2.1 on one view). The board renders
every edge view a second time without a plan (`ground=None`) and measures the difference
(`board_probes.difference_frame`): the plan's ground and the meadow are the same picture to
0.00 luma. Its positive control is the owner's veto itself: with the plan's open ground flat
(`--open-ground flat`) the same probe reads a step of 1.84 and a line of 7.5 — the flat colour
beside the varied grass. Under the veto the edge gate as it stands would fail; its
`raw_step` on the frame itself reads ±1.6 there (see the handoff). The software adapter (WARP,
the compatibility mode) renders it with no Qt message (the family garden's default framing
0.79 → 0.30 flat green at 640 × 360, no light probe there). OpenGL on Mesa llvmpipe could not be
checked on Windows: the `opengl32sw.dll` PyQt6 ships is Mesa with LLVM 3.6, OpenGL 3.0, and the
base fails on it as the branch does (Qt Quick's own shaders need GLSL 150).

**Cost** (RTX 4070, Direct3D 11, 1920 × 1080, the family garden's default framing at noon; one
process holding two hosts — the base's `Garden.qml` and this branch's — shown in turn; per
round the median readback time of twelve NEW frames, the camera nudged 0.01 cm between them):

| Preset | run 2: base → branch (paired median, IQR) | run 3: base → branch (paired median, IQR) |
|---|---|---|
| Low | 8.66 → 8.94 ms (−0.12, −1.1 … +0.4) | 15.07 → 17.12 (+0.69, −0.3 … +2.0) |
| Medium | 11.65 → 11.36 (−0.70, −2.1 … +1.0) | 15.00 → 18.55 (+0.62, −1.0 … +5.9) |
| High | 16.60 → 25.18 (+1.82, −0.2 … +8.1) | 21.27 → 25.09 (+2.14, −1.2 … +5.4) |
| Ultra | 21.49 → 22.08 (−0.80, −1.8 … +2.7) | — (the run's timeout came first) |

Two other agents rendered on the same GPU throughout, and both sides drifted 10 → 18 ms within
run 3: no difference stands out of that noise. The ground shader is the same at Medium, High
and Ultra (surface 2, relief 3), so a difference that depends on the preset is the shared
GPU's; the branch's best frames per side were not slower (Low 7.30 against 8.77 ms, Medium 7.08
against 7.28; High 15.10 against 13.58). Measured where it does show, on the software adapter:
the Low decision above. Memory: one 256² RGBA16F texture per host — 512 KiB, about 683 KiB with
its mips on the GPU — and its 512 KiB of upload data, for the host's life. Vsync could not be
switched off for a windowed Direct3D 11 view (`QSurfaceFormat.setSwapInterval(0)`: every
side presented at 16.0 ms), so presented frames could not measure it.
