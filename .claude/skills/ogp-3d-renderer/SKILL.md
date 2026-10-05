---
name: ogp-3d-renderer
description: "Measured facts and runbook for Open Garden Planner's Qt Quick 3D renderer (Phase 17, ADR-048; spike in src/open_garden_planner/spike_q3d/, production package ui/view3d/quick3d/ from L1.2). Load when: writing or debugging anything that imports QtQuick3D/QtQuick/QtQml/QtQuickWidgets; feeding numpy geometry or textures to the engine; placing the sun, sky, shadows or camera; choosing render presets or post effects; hosting a View3D in a QQuickWidget or QQuickView; picking; taking screenshots or offscreen renders; rendering in CI (xvfb + Mesa, Windows WARP); packaging Qt Quick 3D in the PyInstaller exe; or when a 3D frame is black, white, mirrored, washed out, slow or seems to hang. Only facts measured in this repo, each with where and how it was measured."
---

# Qt Quick 3D renderer — measured facts and runbook

**Status:** v0, written from the Package L0 spike (ADR-048, *Proposed*). Every number below
was measured in this repo; the machine is named because software rasterisers (Mesa llvmpipe,
Windows WARP) say nothing about absolute GPU speed — only about correctness, ratios and
relative cost. Art direction lives in `ogp-lush-cinematic`; this skill is the engine.

## 1. Boundary rules (pinned by tests)

- The spike is **dormant**: dispatched from `main()` on `--spike-q3d`, never imported at app
  start (`tests/unit/test_spike_q3d_isolation.py`).
- **One engine module.** Only `spike_q3d/quick.py` may import `PyQt6.QtQuick3D`, `QtQuick`,
  `QtQml` or `QtQuickWidgets` (AST scan in the same test). The production package inherits the
  rule as `ui/view3d/quick3d/`.
- **QML carries no user-visible strings** — `pylupdate6` does not extract `qsTr`, so any text
  goes through a QWidget overlay with `self.tr()` (§8.3).
- `spike_q3d/meshes.py` is **Qt-free numpy** (it graduates into `core/`).

## 2. PyQt6 6.11 binding facts

| Need | What works | Measured trap |
|---|---|---|
| Custom geometry | `QQuick3DGeometry` subclass, `setVertexData`/`setIndexData` | — |
| Textures from Python | `QQuick3DTextureData`, `Format.RGBA8` | detached from its `Texture` and attached again, the same object draws the surface **untextured (white)**; `update()` does not help, `setTextureData(textureData())` + `update()` (or a fresh object) does — §5 |
| Instancing | not bound → merge meshes (static batching) | — |
| Geometry lifetime | one `QQuick3DGeometry` per Model lifetime | once its Model is destroyed, the same geometry given to a new Model **renders and picks nothing** (frame = empty scene, 0/20 picks); `update()` does not help, a full re-upload (`set_mesh`) does |
| `Repeater3D` over a JS array | fine for a fixed set | **any** change of the array destroys and recreates **every** delegate — combined with the row above, every model came back blank; use per-item creation or a list model with incremental inserts |
| Pick result | `View3D.pick()` inside a QML helper that returns a plain JS object | the return value arrives as **`QJSValue`**: call `.toVariant()` before `dict()` |
| Surface format | — | `QQuick3D.idealSurfaceFormat()` **before** `QGuiApplication` exists **segfaults** (Linux) |

## 3. Frame and geometry

- **Frame mapping, exactly once:** scene (E, N, up) → engine (x = E, y = up, z = −N);
  determinant +1, so triangle winding survives. Done in `quick.py`, never in QML.
- **Vertex layout, stride 48 bytes:** position f32×3 @0, normal f32×3 @12, colour f32×4 @24
  (**linear**, not sRGB), uv f32×2 @40 (spike convention: u = wind weight, v = phase), indices
  U32; `setBounds` + `update()`.
- **Update cost** of replacing a 100k-vertex geometry (`NumpyGeometry.set_mesh`: frame mapping +
  interleave + copy): median **10.5 ms** (n = 10, max 25 ms; cloud container CPU,
  `--update-bench`), 14–27 ms on Windows runner instances. GO criterion 6 says ≤ 10 ms —
  borderline; measure on the owner box before optimising, and look at the interleave copy
  first.

## 4. Light, sky, shadows

- A `DirectionalLight` shines down its **local −Z**. Orient it with
  `QQuaternion.rotationTo(QVector3D(0, 0, -1), travel)`; `lookAt` exists on **cameras only**
  (QML: "lookAt is not a function"). Light travel = −sun vector from `core/solar` (ADR-037).
- **Property names differ:** Models use `castsShadows` / `receivesShadows`; Lights use
  `castsShadow`. The wrong one is a QML load error, not a warning.
- `ProceduralSkyTextureData`: **`sunLongitude = azimuth + 90°`** (sky probe, disc read 25°
  off-centre: max 0.85° on OpenGL, 1.4° on D3D11 — including up to ~0.6° of the probe's own
  error before `probes.pixel_bearing` inverted the camera's 14° pitch; a centred disc only
  proves the direction). The environment pre-filters the light probe **once per Texture object** and ignores
  later `textureData` changes, so build a fresh sky `Texture` on every sun change
  (`createObject(view.scene)`, destroy the old one — parenting to `view.scene` avoids the "not
  placed in the graphics scene" warning).
- **`ProceduralSkyTextureData` regenerates the whole sky synchronously, on the GUI thread, on
  every input change** (~190 ms each at `SkyTextureQualityHigh`, llvmpipe). Never bind its
  inputs live, and build no sky before the first sun is known: the spike's live-bound sky
  regenerated for each look and sun input during an open, and its initial one was thrown away.
  Build it once per sun change — create the data at `SkyTextureQualityLow`, set every input,
  raise the quality last (one full generation). Measured once (llvmpipe, 640×360, golden hour;
  commit a275da2, the number every record cites): QML load 1709 → 70 ms, `set_look` 791 →
  0.1 ms, `set_sun` 2192 → 344 ms, a mood + sun change 3110 → 365 ms; frames bit-identical.
- If the image-based light out-shines the sun, the whole frame reads flat and blue —
  `probeExposure` 0.35–0.55 against sun brightness 1.7–2.1 (rigs in `ogp-lush-cinematic` §3).
- **Shadow truth** (box 100 × 100 × 200 cm, azimuth 225°, IoU of the engine's shadow-map
  footprint vs the analytic 2D shadow, top-down orthographic, `--iou`):

  | Backend / machine | Size | 15° | 35° | 60° |
  |---|---|---|---|---|
  | OpenGL, Mesa llvmpipe (container) | 1280×720 | 0.959 | 0.950 | 0.920 |
  | OpenGL, Mesa llvmpipe (container) | 960×540 | 0.980 | 0.985 | 0.964 |
  | Direct3D 11, WARP (windows-latest) | 960×540 | 0.980 | 0.984 | 0.963 |

  Settings behind those numbers: `shadowBias` 5, `shadowMapFar` 9000, `lockShadowmapTexels`,
  the High preset's quality and PCF — but **no cascades**: the orthographic probe view forces
  `csmNumSplits: 0`, so the cascaded configuration of the beauty views is not covered yet.
  The value depends on frame size (pixel grid), not on the backend. Low preset (VeryHigh map
  since creator round 4, one cascade, bias 15; the probe still runs without cascades):
  0.953 / 0.959 / 0.922 at 1280×720, 0.985 / 0.983 / 0.967 at 640×360 (High map before:
  0.963 / 0.968 / 0.937 at 1280×720).
- **Shadow bias at grazing light:** 1024-texel maps (low, medium) at `shadowBias` 5 left a
  sun-grazed roof acned and stair-stepped (33–40 % of the slope); 15 measured clean with the IoU
  gate unchanged. VeryHigh quality alone: 33 %; one cascade split: 8 %; 32-bit map: 15 %.
- **Fog vs sky:** the skybox is drawn × `probeExposure`, `Fog` is not — fog = sky horizon ×
  probe exposure × 0.8 (linear) meets the sky within ±1.3 luma. The sky's
  `groundHorizonColor` shows in a sliver under a far-clipped ground plane: give it the sky
  horizon colour, not the fog colour (that drew a dark line). That alone still left a
  1–3 px dark line (dip 9–10 luma, llvmpipe): `ProceduralSkyTextureData`'s default
  `groundCurve` 0.02 is ~32 % of the way to `groundBottomColor` 0.7° below the horizon —
  about one texel of the sky texture — so the filtered horizon row darkens. `groundCurve`
  0.1 with `groundEnergy` 1.0 measured 0.1–0.2 (the brighter lower sky lifts shaded walls
  ~5 luma; ground shadows unchanged).
- **PrincipledMaterial and water:** its grazing sky reflection ignores `specularAmount`,
  `fresnelScale` and `fresnelPower`, and its image-light diffuse is scaled by
  (1 − `specularAmount`). A custom material may sample the probe with Qt's
  `qt_sampleDiffuse` / `qt_sampleGlossy` — but only inside `#if QSSG_ENABLE_LIGHT_PROBE`,
  or the shader fails to compile in views without a probe (OpenGL verified; D3D11 is the
  Windows evidence run's job).
- **Double-sided leaves:** with `cullMode: NoCulling` back faces get the flipped normal — a
  front-only light term turns grass into black stubble; light both sides.
- **Sharpening is on or off:** `sharpnessAmount` 0.08 overshot into near-black, red-less pixels
  (1,500–3,100 per daytime frame at 1280×720: teal-black slits in picket fences, black stubble
  on lawns); 0.03 is nearly as bad (noon 1,502 vs 1,554), and only 0.0 is clean. Leave it at
  0 (edge energy −16–29 %, an owner taste question), and keep the render tier's speckle gate.
- **Anti-aliasing at low:** `fxaaEnabled` lives on `ExtendedSceneEnvironment`,
  `specularAAEnabled` on `SceneEnvironment`; keep FXAA off in probe views (it softens the
  measured pixels).
- **Deterministic boards:** stop the wind and reset `windTime` to 0 — otherwise every frame
  after an fps measurement freezes foliage at a run-dependent sway.
- **SSGI renders a black frame on Mesa llvmpipe** (`--ssgi`; isolated by toggling SSGI and SSR
  separately) → opt-in until verified on real GPUs. SSR renders fine there.

## 5. Ground texture

- A `QImage` → `QQuick3DTextureData` (RGBA8) on a `#Rectangle` needs **`flipV: true`**: texture
  rows are north-up. Orientation probe (`--orient`): NCC identity 0.94 vs flip_v −0.10.
- **Re-attach renders white** (the texture twin of the geometry rule in §2): the IoU and
  orientation probes set `groundTexture` to null, which detaches the `QQuick3DTextureData`;
  setting the same object back left the plan ground white until the next reload (mean luma
  difference 13.1 on the frame, all of it in the ground half; llvmpipe, 640×360).
  `preserved_state()` re-uploads a detached ground. It was caught only because
  `--second-window` compared frames, then misdiagnosed once as a stale reference by a run
  without `--iou`; check a restore in pixels (`probe_restore_frame_diff` < 1), not by object
  identity.
- `QGraphicsScene.render()` always paints the canvas background — the spike swaps that exact
  colour for meadow; the production bake paints records directly (plan L1.5).
- **Ownership:** a texture created in Python is owned by Python, so something must hold it
  while QML shows it — exactly the one shown. An append-only keep-alive list grew RSS by one
  baked ground (2400×1600 RGBA ≈ 15 MB + GPU copy) per project reload, linearly; holding only
  the shown texture and releasing the old one *after* the scene shows the new one settled
  (A/B, 10 reloads, llvmpipe). Judge leaks by `leak_slope_mb_per_reload` (Theil–Sen over the
  second half of the reloads), never by total growth — the first reload adds ~70 MB either way
  — in committed memory (private bytes on Windows: its working set is trimmed and regrown, so
  v7 could not judge a leak at all), over **20 reloads**: at 10, five points could not resolve
  10 MB/reload against ±30–60 MB swings (WARP v8; llvmpipe once read 14.3 at ±35 MB). Trust
  the gate only with its positive control on the same machine (`--soak-leak-mb 25` must fail
  it). Private bytes do not see VRAM: on a discrete GPU the gate is blind to GPU-side leaks.
  The gate answers "a trend over the last ten reloads?", not "did memory grow?". On WARP every
  run (v9–v19) first dips 94–146 MB (consistent with memory the probes held: the probe-less
  controls, at a smaller window, never dip), then rises 5–10 MB per reload; the tail gate read
  1.5–9.0 (1.8 and 9.0 for identical code), and the controls read 28–34 MB/reload for the 25
  MB they hold. Longer soaks (v13–v19; v15–v19 ran 100 reloads): identical code rose +196 and
  +62 MB by reload 50, and over reloads 51–100 the five 100-reload runs (the same soak path)
  had slopes of 0.21, 2.03, 3.05, 0.08 and 3.50 MB/reload, the 0.08 an interval that includes
  zero. Over reloads 11–20 llvmpipe RSS read 0.00–0.46 MB/reload where WARP read 1.5–9.0, so
  over that window it is not Python-side growth of WARP's size (no Linux soak runs past reload
  20); a D3D11 resource retained per reload is not ruled out (WARP keeps GPU memory in private
  bytes; a discrete GPU keeps it in VRAM, unseen). Cause unidentified; locate it with an A/B
  soak, not a longer one. Record the whole curve (`leak_curve_mb`) with the verdict, and write
  numbers, not shapes: "ceiling", "slowing" and "threefold" each overreached on these curves.

## 6. Hosts

| | `QQuickView` (+ window container) | `QQuickWidget` |
|---|---|---|
| Frame signal | `frameSwapped` | **none** — count `quickWindow().afterRendering` |
| Request a frame | `view.update()` | **`quickWindow().update()`**; `widget.update()` only re-composites the old texture |
| "Is it on screen?" | `isExposed()` | `quickWindow().isExposed()` is **always False** (offscreen) → `isVisible()` |
| Screenshot | `grabWindow()` | `grabFramebuffer()` |

- **A `QQuickWidget` in a window moves the whole top-level window onto RHI composition.**
  2D canvas pan step, median: 5.5 ms without → 7.9 ms with a 3D widget beside it (**×1.42**,
  llvmpipe) and 2.8 → 15.9 ms (**×5.7**, Windows WARP, frozen) — `--pan-bench`; GO criterion 3
  asks ≤ ×1.3 on owner hardware. A synchronous
  `repaint()` does **not** include the flush/composition (it measured 0.08 ms "with 3D") —
  measure pan cost with `processEvents()`.
- **A second 3D window is not faster:** with the same view it took as long to its first
  finished readback as the first window (`--second-window`; WARP: 63.7 s vs 63.0 s) —
  consistent with per-window pipeline state (inferred, not verified). Keep one host alive and
  hide/show it: re-entry (show → next frame) median **7 ms** on llvmpipe, 31–53 ms on WARP
  (`--soak`; measured on a fully rendered scene — before the re-attach fix in §2, a soak that
  re-added models measured an empty garden).

## 7. Picking

`pickAt(x, y)` in QML → `{hit, id, x, y, z}` (engine frame). Models must set
`pickable: true`. `--pick` checks it in a top-down orthographic view against a CPU oracle (the
topmost triangle under a vertical ray over every pickable mesh, merged per item):

- **Easy targets** (each item's highest unoccluded triangle): **20/20**, 0.15–0.24 ms per pick
  (llvmpipe); 20/20 in the frozen Windows D3D11 exe. Easy targets alone prove little — a picker
  that only tests bounding boxes scores 18/20 on them.
- **Adversarial targets** (points inside a tall item's bounding box but off its mesh, where a
  box picker names the wrong item): **10/10** on llvmpipe at 6f0c4f4.
- **Independent projection:** the click pixel comes from the engine's `mapFrom3DScene`, so a
  wrong engine projection could aim and pick consistently wrong. An orthographic projection of
  our own (`measure.top_down_pixel`) agreed with it to **0.0 px**, and the picked point lay
  **0.0 cm** from the target (llvmpipe, 6f0c4f4).
- **Re-attach:** 20/20 again after a detach/re-attach cycle, and the frame is pixel-identical
  (mean abs diff 0.0) — 0/20 and a blank frame without the re-upload rule in §2.

## 8. Screenshots and CI rendering

- **Open time** (criterion 5) runs from the user's request to the first *finished readback*:
  ground bake, model build, QML load, scene apply, show → grab (`open_ms`,
  `open_breakdown_ms`). Never stop the clock at `afterRendering`/`frameSwapped`: that marks
  submission, and on a software rasteriser the real cost lands in the next grab.
- **Cold vs warm must be recorded, not assumed.** Qt keeps `q3dshadercache-*`,
  `qtpipelinecache-*` and `qmlcache` in the app's cache folder (`~/.cache/<argv0 basename>/`,
  `__main__.py` for `python -m`) and `qtshadercache-*` one level up; Mesa keeps
  `mesa_shader_cache`. The spike lists what it found (`shader_caches.found_before_run`).
  `--cold` sets `QT_DISABLE_SHADER_DISK_CACHE`, `QSG_RHI_DISABLE_DISK_CACHE`,
  `QT_QUICK3D_NO_SHADER_CACHE_LOAD`, `QML_DISABLE_DISK_CACHE` and `MESA_SHADER_CACHE_DISABLE`
  (all in the 6.11 runtime): nothing is loaded **or written**. GPU drivers keep their own
  shader caches, which no flag reaches. On llvmpipe cold vs warm is noise (first frame's
  render cost dominates); the GPU decides.
- **A shader that does not compile is only a warning.** `QSpirvCompiler: Failed to parse
  shader` and `Failed to compile fragment shader` arrive as `QtWarningMsg`, and the frame
  still renders (measured: one renamed call in `water.frag` changed 449 pond pixels' colour,
  exit 0, `status: ok`). Record every Qt message
  (`spike_q3d/qt_messages.py`: `qInstallMessageHandler`, into the log and `metrics.json`) and
  fail on shader/QML errors — a frozen exe has no stderr to read them from. A clean llvmpipe
  run emits no Qt messages at all, so the gate has no false alarms there.
- **Aim probes at the actual view size** (`SpikeRenderer.view_size()`), not the requested
  one: a window larger than the screen is clamped.

- **Linux:** the `offscreen` QPA selects the *software* scene graph, which cannot render 3D.
  Use `xvfb-run` + `QT_QPA_PLATFORM=xcb` + `QSG_RHI_BACKEND=opengl` (+ `LIBGL_ALWAYS_SOFTWARE=1`
  in a container). Packages: `libegl1` (the QtQuick3D binding links libEGL), `libxcb-cursor0`
  (xcb plugin). As root, Qt WebEngine needs `QTWEBENGINE_DISABLE_SANDBOX=1`.
- **Windows runner** (windows-latest, no GPU): `Direct3D11Rhi` on WARP. Frozen exe: QML load
  1.0–2.7 s, first *presented* frame 2.0–3.0 s, 960×540 low 11.5–14.2 fps / high 4.3–4.8 fps
  (runs v3/v4, `docs/09-architecture-decisions/adr-048-evidence/`). `frameSwapped` marks
  submission, not completion — on a software rasteriser the real cost lands in the next
  readback, so time open-to-ready with a grab. **Each new sky light probe costs 40–85 s
  once** on WARP (in the frames or the grab right after a sun change); later
  grabs of the same sky take 20–500 ms, and `QSG_RENDER_LOOP=basic` changes nothing. Never
  rebuild the probe per frame; on software rendering drop image-based light. Evidence run
  v1's 56-minute "hang" was this cost, times many shots, with no log.
- **A frozen GUI exe has no stdout** (`print` is a no-op; #291 is the precedent). The spike
  writes `<out>/spike.log` (flushed per line), rewrites `metrics.json` after every phase, and
  `--watchdog-s N` arms `faulthandler` to dump every thread's stack into the log and exit
  non-zero. Use the same pattern for any headless render path.
- Commands (Linux render tier, opt-in):

  ```bash
  OGP_RENDER3D=1 QSG_RHI_BACKEND=opengl QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 \
    xvfb-run -a -s "-screen 0 1920x1080x24" \
    venv/bin/python -m pytest tests/integration/test_spike_q3d_render.py
  ```

## 9. Packaging (PyInstaller)

- The spec needs a data loop for the QML + shader files and hidden imports for
  `PyQt6.QtQuick`, `QtQml`, `QtQuickWidgets`, `QtQuick3D`.
- **The Qt Quick 3D runtime already ships in today's bundle.** Windows dist, branch vs master
  built in the same job: 626.2 MB vs 624.5 MB → **+1.7 MB** (only `QtQuick3D.pyd` and the QML
  files are new). Quick3D + ShaderTools files: 21.1 MB (Windows), ~23 MB (Linux); the Qt3D DLLs
  this replaces: 5.8 MB.
- Frozen Windows exe with the spike bundled: the unchanged `--selftest` gate still exits 0
  (ogp-change-control §2.8 is its home).

## 10. CPU-side baselines (not engine)

`bench_small.ogp` (99 items): plan load 0.1–0.5 s, ground bake 0.1–0.3 s, mesh build ~0.5 s
for 185k triangles (Linux and Windows alike). `bench_large.ogp` (425 items): 2.28 s for 1.46M
triangles (`scripts/bench_view3d.py`).

## 11. Symptom → cause (spike chronicle)

| Symptom | Cause | Fix |
|---|---|---|
| Segfault at start | `idealSurfaceFormat()` before `QGuiApplication` | call nothing Quick-3D before the app object |
| Frame renders nothing 3D under CI | `offscreen` QPA → software scene graph | xvfb + xcb + `QSG_RHI_BACKEND=opengl` |
| QML: non-existent property `castsShadow` | Model vs Light naming | `castsShadows` on Models |
| QML: `lookAt is not a function` | only cameras have it | quaternion from Python |
| Whole garden pale blue, no shadows | the light was never oriented | `rotationTo((0,0,-1), travel)` |
| Lawn white, gravel around the beds | ground texture upside down | `flipV: true` |
| Sky sun stuck after a sun change | probe cached per Texture object | new Texture per change |
| Ultra preset black | SSGI on Mesa | SSGI opt-in |
| `'QJSValue' object is not iterable` | QML function returned a JS object | `.toVariant()` |
| QQuickWidget never reports frames | it has no `frameSwapped` | `quickWindow().afterRendering` |
| QQuickWidget renders only once | `widget.update()` re-composites | `quickWindow().update()` |
| Windows run "hangs" for an hour | `grabWindow()` ~100 s on WARP, no output | time every grab; log + watchdog |
| Frozen spike fails in 1 s | default plan path is the source tree | pass `--plan` explicitly |
| Models blank and unpickable after a list change | geometry outlived its Model; array `Repeater3D` recreates all delegates | re-upload on re-attach; one geometry per Model lifetime |
| A sun change stalls for a minute (WARP) | new sky light probe is prefiltered | rebuild only on noticeable sun moves; no IBL on software |
| Windows RSS reads `None` | ctypes default `int` restype truncates the process pseudo-handle | declare `HANDLE` restype/argtypes |
| `--iou` crashes / `--orient` says mirrored at 150 % display scale | pixel grid built from the logical size | build it from the grabbed image and `devicePixelRatio()` |
| A measurement changes when the flag order changes | a probe left camera/preset/ground/sun behind | run probes inside `SpikeRenderer.preserved_state()` |
| "Open time 2 s" but the first grab takes a minute (WARP) | `frameSwapped` marks submission | time request → first finished readback (`open_ms`) |
| A custom material renders the wrong colour, run "ok" | shader compile error is a `QtWarningMsg` | record Qt messages; fail on shader/QML errors |
| "Cold" open time on the second run of the day | Qt/Mesa disk caches from the first | `--cold`, and read `shader_caches.found_before_run` |
| RSS climbs ~30 MB per project reload | append-only keep-alive list of ground textures | hold only the shown texture; judge by the tail slope |
| Plan ground white after a probe; the second window "differs" by ~10 luma | the same `QQuick3DTextureData` re-attached after being detached | re-upload it on re-attach; assert `probe_restore_frame_diff` < 1 |
