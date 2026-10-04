---
name: ogp-3d-renderer
description: "Measured facts and runbook for Open Garden Planner's Qt Quick 3D renderer (Phase 17, ADR-047; spike in src/open_garden_planner/spike_q3d/, production package ui/view3d/quick3d/ from L1.2). Load when: writing or debugging anything that imports QtQuick3D/QtQuick/QtQml/QtQuickWidgets; feeding numpy geometry or textures to the engine; placing the sun, sky, shadows or camera; choosing render presets or post effects; hosting a View3D in a QQuickWidget or QQuickView; picking; taking screenshots or offscreen renders; rendering in CI (xvfb + Mesa, Windows WARP); packaging Qt Quick 3D in the PyInstaller exe; or when a 3D frame is black, white, mirrored, washed out, slow or seems to hang. Only facts measured in this repo, each with where and how it was measured."
---

# Qt Quick 3D renderer — measured facts and runbook

**Status:** v0, written from the Package L0 spike (ADR-047, *Proposed*). Every number below
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
| Textures from Python | `QQuick3DTextureData`, `Format.RGBA8` | — |
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
  interleave + copy): median **10.5 ms**, p95 25 ms (cloud container CPU, `--update-bench`).
  GO criterion 6 says ≤ 10 ms — borderline on this CPU; measure on the owner box before
  optimising, and look at the interleave copy first.

## 4. Light, sky, shadows

- A `DirectionalLight` shines down its **local −Z**. Orient it with
  `QQuaternion.rotationTo(QVector3D(0, 0, -1), travel)`; `lookAt` exists on **cameras only**
  (QML: "lookAt is not a function"). Light travel = −sun vector from `core/solar` (ADR-037).
- **Property names differ:** Models use `castsShadows` / `receivesShadows`; Lights use
  `castsShadow`. The wrong one is a QML load error, not a warning.
- `ProceduralSkyTextureData`: **`sunLongitude = azimuth + 90°`** (sky probe, error ±0.3°,
  Linux GL). The environment pre-filters the light probe **once per Texture object** and ignores
  later `textureData` changes, so build a fresh sky `Texture` on every sun change
  (`createObject(view.scene)`, destroy the old one — parenting to `view.scene` avoids the "not
  placed in the graphics scene" warning).
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
  quality/cascades/PCF per preset as in `GardenSpike.qml`.
- **SSGI renders a black frame on Mesa llvmpipe** (`--ssgi`; isolated by toggling SSGI and SSR
  separately) → opt-in until verified on real GPUs. SSR renders fine there.

## 5. Ground texture

- A `QImage` → `QQuick3DTextureData` (RGBA8) on a `#Rectangle` needs **`flipV: true`**: texture
  rows are north-up. Orientation probe (`--orient`): NCC identity 0.94 vs flip_v −0.10.
- `QGraphicsScene.render()` always paints the canvas background — the spike swaps that exact
  colour for meadow; the production bake paints records directly (plan L1.5).

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
- **Pipeline caches are per window:** a second renderer in the same process took as long to its
  first frame as the first one (llvmpipe: 15.1 s vs 14.9 s, `--warm`). Keep one host alive and
  hide/show it: re-entry (show → next frame) median **7 ms** on llvmpipe, 31–53 ms on WARP
  (`--soak`; measured on a fully rendered scene — before the re-attach fix in §2, a soak that
  re-added models measured an empty garden).

## 7. Picking

`pickAt(x, y)` in QML → `{hit, id, x, y, z}` (engine frame). Against a CPU oracle (topmost
triangle under a vertical ray over every pickable mesh): **20/20**, 0.15 ms per pick
(container and frozen Windows D3D11, orthographic top-down, `--pick`), and 20/20 again after a
detach/re-attach cycle — which reads 0/20 without the re-upload rule in §2. Models must set
`pickable: true`.

## 8. Screenshots and CI rendering

- **Linux:** the `offscreen` QPA selects the *software* scene graph, which cannot render 3D.
  Use `xvfb-run` + `QT_QPA_PLATFORM=xcb` + `QSG_RHI_BACKEND=opengl` (+ `LIBGL_ALWAYS_SOFTWARE=1`
  in a container). Packages: `libegl1` (the QtQuick3D binding links libEGL), `libxcb-cursor0`
  (xcb plugin). As root, Qt WebEngine needs `QTWEBENGINE_DISABLE_SANDBOX=1`.
- **Windows runner** (windows-latest, no GPU): `Direct3D11Rhi` on WARP. Frozen exe: QML load
  1.0 s, first frame 2.0 s, 960×540 low 14.2 fps / high 4.8 fps. **Each new sky light probe
  costs 40–70 s once** on WARP (in the frames or the grab right after a sun change); later
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
