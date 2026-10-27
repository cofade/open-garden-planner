---
name: ogp-3d-renderer
description: "Measured facts and runbook for Open Garden Planner's Qt Quick 3D renderer (Phase 17, ADR-048; production package ui/view3d/quick3d/ since L1.2; the L0 spike it was measured in, src/open_garden_planner/spike_q3d/, was deleted in L1.10). Load when: writing or debugging anything that imports QtQuick3D/QtQuick/QtQml/QtQuickWidgets; feeding numpy geometry or textures to the engine; placing the sun, sky, shadows or camera; choosing render presets or post effects; hosting a View3D in a QQuickWidget or QQuickView; picking; taking screenshots or offscreen renders; rendering in CI (xvfb + Mesa, Windows WARP); packaging Qt Quick 3D in the PyInstaller exe; or when a 3D frame is black, white, mirrored, washed out, slow or seems to hang. Only facts measured in this repo, each with where and how it was measured."
---

# Qt Quick 3D renderer — measured facts and runbook

**Status:** v0, written from the Package L0 spike (ADR-048, *Accepted — GO 2026-10-05*). Every number below
was measured in this repo; the machine is named because software rasterisers (Mesa llvmpipe,
Windows WARP) say nothing about absolute GPU speed — only about correctness, ratios and
relative cost. Art direction lives in `ogp-lush-cinematic`; this skill is the engine.
Since L1.2 the production package `ui/view3d/quick3d/` exists: its measured facts and commands
are §12, and rows it added to the tables below say "(L1.2)". **L1.10 deleted the spike**
(`spike_q3d/`, `--spike-q3d`, `scripts/bench_view3d.py`): where a row below names a spike module,
flag or class, it names where the fact was measured. docs/05 §5.8 says where each spike part
lives now; the values production was drift-guarded against are frozen in
`tests/data/l0_spike_reference.json`.

## 1. Boundary rules (pinned by tests)

- The L0 spike was **dormant** — dispatched from `main()` on `--spike-q3d`, never imported at
  app start — and **L1.10 deleted it** (ADR-048's closing addendum);
  `tests/unit/test_quick3d_boundary.py::test_the_spike_is_gone_and_nothing_names_it` keeps it
  gone.
- **One engine module (L0).** Only the spike's `quick.py` imported `PyQt6.QtQuick3D`, `QtQuick`,
  `QtQml` or `QtQuickWidgets`. The production package inherited the rule as
  `ui/view3d/quick3d/`.
- **One engine package (L1.2).** In the product, only `ui/view3d/quick3d/` imports those
  bindings — and inside it only `geometry.py`, `host.py` and (L1.5, the ground's tile
  textures) `ground_tiles.py` do; `selftest.py` names them as
  strings to import them one by one. Pinned over the WHOLE tree, imports by name included
  (`__import__("PyQt6.QtQuick3D")` is an import), by `tests/unit/test_quick3d_boundary.py`,
  which also pins that app start loads neither the bindings nor the package and that the
  package never uses a `QQuickWidget`.
- **QML carries no user-visible strings** — `pylupdate6` does not extract `qsTr`, so any text
  goes through a QWidget overlay with `self.tr()` (§8.3).
- The spike's `meshes.py` was **Qt-free numpy**; it graduated into `core/scene3d/` (L1.1,
  L1.6, L1.7).
- **`core/scene3d/` is Qt-free** (standard library + numpy; AST scan in
  `tests/unit/test_scene3d_contract.py`). That is a rule about its source — no module there uses
  Qt — not about the interpreter: importing the package runs `core/__init__.py`, which loads
  PyQt6 for other `core` modules. It is the production side of the engine boundary since
  L1.1 (ADR-059, §8.29.1): an engine adapter implements `core/scene3d/sink.py::EngineSink` and is
  driven by `SceneSync`; builders are tested against `RecordingSink` with no GPU.
- **`EngineSink` has eleven methods (the eleventh, `set_selection`, is the selection ring —
  §14), and `clear()` is the one an adapter gets wrong.** After
  `clear()` the engine holds nothing — no items, no sun, no ground, no open transaction — and it
  must work at any time: inside a transaction (abort it), on an empty scene, and after one of the
  adapter's own calls failed half way. `SceneSync.reset()` recovers through it and through
  nothing else. Test an adapter's recovery the way `tests/unit/test_scene3d_sync.py` tests the
  double: fail a call in mid-transaction, `reset()`, apply, and compare with a from-scratch
  apply (`sync.expected_state()`).
- **A record's `footprints` are outer rings only; its `holes` are cut out of them.** A closed
  fence is one outer ring and one hole. Anything that gives a footprint area — a mesh, the ground
  bake, a pick shape — iterates `record.regions`. `verify_builder` refuses a solid built over a
  hole.
- **`core/plant_art/` is standard library only** (no Qt, no numpy; AST scan in
  `tests/unit/test_plant_art.py`): the plant recipe tables and the species → sprite rule, read by
  the sprite generator script (which executes `recipes.py` by file path — importing the package
  by name runs `core/__init__.py` and loads PyQt6), by `core/plant_renderer` and by the plant
  builder `core/scene3d/builders/plants.py` (L1.7, §8.22.4, §8.29.7).
- **A plant's 3D recipe is resolved from the record's `sprite_species`** — the item's own
  species string, raw — its `plant_category` and its kind: the 2D renderer's three inputs.
  `species_name` / `species_key` describe the species DATA and are for labels and lookups; a
  builder that resolved a look from them built a squash where the plan drew a pumpkin.
- **The plant builder remembers shapes** (`PROPORTION_STEP`, `SHAPE_CACHE_BYTES` in
  `builders/plants.py`): the mesh arrays it hands a sink are read-only and their colours, uvs and
  indices are SHARED between the meshes of one plant at different sizes (the same array objects;
  pinned by `tests/unit/test_scene3d_plants.py::TestShapeCache`). An adapter must copy what it
  wants to change — and cannot do otherwise: every array of a `Mesh.from_arrays` mesh sits on
  immutable memory (`setflags(write=True)` raises, on the array and on its base). The cache is
  capped in bytes (256 MB); beyond the cap a date scrub rebuilds only the plants that do not fit,
  and `shape_cache_info()` says how many shapes were built. Call `clear_shape_cache()` when a
  plan is closed: it forgets the shapes AND the request log (which lives outside the cap, up to
  about 20 MB) — at the cap a shape that was dropped comes back in two builds, so going back to
  a dropped plan costs two cold ticks and a backward scrub twice the forward one. GUI thread
  only; the cache is untested under threads.
- **The production builders are `core/scene3d/builders/`** (L1.6, ADR-059 addendum):
  `production_registry()` returns the `BuilderRegistry` the wiring hands to `SceneSync` — the
  built world's twelve kinds (`register`) and the plant builder's three (`plants.register`,
  above), no kind in both. The built world's
  rules (the top is the height by construction, polylines from the centre line — `lines.py`
  decides what a fence or wall line becomes, an unknown style is a plain panel — a polygon
  record that is not ONE plain outline (several rings, a hole, or `params["outline_resolved"]`)
  is the plain block of its regions and gets no roof, frame or leaves — corners
  bevelled beyond a mitre of two offsets, tinted parts, the mirrored palette) and the how-to
  are §8.29.6; a record's `transform.base_cm` — where a plant stands on its bed — reaches the
  engine through `engine_pose`, never through a mesh. Their shadows are NOT the 2D model's:
  the measured table (`scripts/measure_built_world_shadows.py`) is in §8.29.6 and next to the
  Shadows gate of `ogp-lush-cinematic` §1.

## 2. PyQt6 6.11 binding facts

| Need | What works | Measured trap |
|---|---|---|
| Custom geometry | `QQuick3DGeometry` subclass, `setVertexData`/`setIndexData` | — |
| Textures from Python | `QQuick3DTextureData`, `Format.RGBA8` | detached from its `Texture` and attached again, the same object draws the surface **untextured (white)**; `update()` does not help, `setTextureData(textureData())` + `update()` (or a fresh object) does — §5 |
| Instancing | not bound → merge meshes (static batching) | — |
| Geometry lifetime | one `QQuick3DGeometry` per Model lifetime | once its Model is destroyed, the same geometry given to a new Model **renders and picks nothing** (frame = empty scene, 0/20 picks); `update()` does not help, a full re-upload (`set_mesh`) does |
| Geometry built in QML (L4) | not `ProceduralMesh` (`QtQuick3D.Helpers`): load the data from Python into a `ReloadableGeometry` that a declared Model holds for life, as the selection ring and the meadow do | a declared `ProceduralMesh` whose lists were replaced kept DRAWING its first data, though its lists read back the new ones; a `ProceduralMesh` created later — set at creation or after, in the live Model or in a new one — drew NOTHING (D3D11, RTX 4070; PF-L3D-14) |
| One large triangle near another surface (L4) | triangles of at most 100 m, and no surface just under another | a 4 km quad of two triangles 5 cm under the plan won the depth test against it from normal cameras: its interpolated depth was more than 5 cm off at 55-90 m; the same quad in 100 m cells lost no view (24-bit depth resolves about 0.3 cm at 50 m; PF-L3D-13) |
| `Repeater3D` over a JS array | fine for a fixed set | **any** change of the array destroys and recreates **every** delegate — combined with the row above, every model came back blank; use per-item creation or a list model with incremental inserts |
| Pick result | `View3D.pick()` inside a QML helper that returns a plain JS object | the return value arrives as **`QJSValue`**: call `.toVariant()` before `dict()` |
| Surface format | — | `QQuick3D.idealSurfaceFormat()` **before** `QGuiApplication` exists **segfaults** (Linux) |
| Models from Python (L1.2) | a QML function (`createPart`) that calls `Component.createObject(parentNode, {...})`, invoked with `QMetaObject.invokeMethod(root, "createPart", Qt.ConnectionType.DirectConnection, Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", …))` | the Model arrives as a `QQuick3DObject`; `setProperty("position" / "eulerRotation", QVector3D)` works; pass the geometry as an ARGUMENT (QML converts it), keep the Python reference as long as the Model lives |
| Destroying a Model (L1.2) | `retired = true` (a property of ours), `visible = false`, `pickable = false`, `geometry = null`, then `destroy()` | `destroy()` is deferred: a frame in between would still draw the Model. A listing must skip it by `retired`, never by `visible` — a Model hidden on purpose is still the engine's |
| Writing a scene property from Python (L1.2) | `metaObject().indexOfProperty(name) >= 0` first, then `setProperty` and its result (`host._set`) | every `setProperty` result was ignored at first; a property renamed in `Garden.qml` is now an `EngineError` that names it, at host construction (Qt documents that an undeclared name becomes a dynamic property and returns False — silently) |
| The graphics API's name (L1.2) | `rendererInterface().graphicsApi()` through a table keyed by the enum MEMBER (`host.GRAPHICS_API_NAMES`: `Direct3D11`, `OpenGL`, …) | PyQt6 6.11 names the members `OpenGL` but `Direct3D11Rhi`, `VulkanRhi`, `MetalRhi`, `NullRhi`, and `Direct3D12`: a list of strings typed on Windows (`OpenGLRhi`) failed the first Linux run |
| A vertex shader that sways (L1.2) | multiply the displacement by a factor that is exactly 0 at rest: `smoothstep(0.0, 2.0, uTime)` | the spike's `sin(phase) × strength × weight` is not 0 at time 0: boxes with full wind weight, in a wind 40 × the look's, were drawn 10.2 px and 18.9 px (20 cm, 38 cm) beside their meshes, with no message |
| Exposure (L1.2) | `ExtendedSceneEnvironment.exposure` (`QtQuick3D.Helpers`) | the plain `SceneEnvironment` has no `exposure`: a QML load error |
| Fill light without a probe (L1.2) | a second `DirectionalLight { brightness: 0; ambientColor: … }` | — (measured: it still contributes its ambient term, so the fill stays when the sun is switched off) |
| `baseColor` vs a shader uniform (L1.2) | `PrincipledMaterial.baseColor` takes sRGB and is linearised by the engine; a `vector3d` uniform of a `CustomMaterial` is passed as it is | the engine's sRGB curve is an approximation: the same tint read 171 through `baseColor` and 169 through an exact linear uniform |
| Vertex colour in a fragment-only custom shader (L1.2) | `VAR_COLOR` | — (D3D11 on GPU and WARP; OpenGL unverified) |
| A texture in a `CustomMaterial` (L4.5) | `property TextureInput uBaseMap: TextureInput { texture: … }`, sampled with `texture(uBaseMap, uv)` | the `Texture`'s `flipV` is NOT applied to a `TextureInput` (it is applied by `PrincipledMaterial`'s own lookup): the north-up ground tiles drew mirrored north–south until `ground.frag` sampled at `vec2(UV0.x, 1.0 - UV0.y)` (PF-L3D-11) |
| Transparency (L4.3) | the sorted per-Model blend (the `glass` material) | scene-wide `oitMethod: OITWeightedBlended` re-blends L2's MULTIPLY drapes with its own equation: under a shadow drape pixels read up to 243 levels lighter (four drape tests failed; PF-L3D-12) — not used |

## 3. Frame and geometry

- **Frame mapping, exactly once:** scene (E, N, up) → engine (x = E, y = up, z = −N);
  determinant +1, so triangle winding survives. Done in `quick.py`, never in QML.
  The production mapping is `core/scene3d/frame.py` (`scene_to_engine_points` / `_vectors` and
  their inverses, exact column selection). Meshes there are in the **item-local** frame and a
  record's transform poses them: `engine_pose(transform)` gives the Model position
  `(east_cm, base_cm, −north_cm)` and a turn of `+rotation_deg` about the engine's +Y — proven
  equal to posing in the scene and mapping the result (`tests/unit/test_scene3d_frame.py`), and
  **measured on the engine in L1.2**: `eulerRotation.y = +rotation_deg` is the
  counter-clockwise turn seen from above — a 240 × 60 cm bar matched the CPU prediction with
  mask IoU 0.9994 at 17° and 0.9895 at 213.5°, the opposite sense with 0.288 and 0.157
  (`tests/integration/test_quick3d_render.py`).
- **The byte layout is Qt-free since L1.2:** `core/scene3d/interleave.py::engine_buffers(mesh)`
  builds the vertex and index bytes (and maps the frame, once);
  `ui/view3d/quick3d/geometry.py::BufferGeometry` only hands them to Qt — one upload per
  object, no re-upload method.
- **The top-down view is linear (L1.2).** With `TonemapModeNone` a pixel is linear radiance,
  so it can be computed: a lit horizontal face reads `255 × tint × (brightness × sin(elevation)
  × sun colour + fill)`, all in linear light — predicted 167.2, measured 171.
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
- **Fog distance (L4 owner pass):** fixed at 26 m → 160 m, the fog drowned a plan framed from
  80 m (a third of the way in) and washed it out three times further. `look.fog_depth_cm`
  ties `Fog.depthNear` / `depthFar` to the camera's distance to its target (1.5× / 6×, floors
  26 m / 160 m, far ≤ 760 m, near ≤ 0.75 far); `set_camera` sets them. What the fog hid
  then showed (3D review): `shadowMapFar` follows `fogNear` (top-down keeps 9000), AO fades
  out from 45 m to 90 m (its pass draws a line about 101 m out), and `clipFar` is 3 km —
  at 800 m the cut meadow showed against the sky's darker lower half, fog or not. Still
  open (#624): `shadowMapFar` follows the target's distance, not the plan's reach, so a
  camera aimed at a plan corner, or 600 m out, loses the far shadows.
- **`setAoStrength` switches AO on (L4, PF-L3D-15):** whenever the strength is not 0, Qt
  sets `aoEnabled` true, whatever its binding says. A strength that changes after load (a
  fade) must be 0 wherever AO is meant to be off, or Low draws SSAO. Read the live state
  off the `ExtendedSceneEnvironment` (`test_quick3d_host.py::_scene_environment`).
- **`clipFar` moves the cascaded shadow fit** even when `shadowMapFar` is below it (L4,
  3D re-review): 800 m → 3 km changed 1–6 % of every board frame by more than 8 luma (at
  most 114) through the cascades, and the shadow IoU by at most 0.0023. A far-plane change
  is not "bit-identical" without a board that says so.
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

- **The ground tiles' material is the endless meadow's** (roughness 1.0, specular amount 0.15,
  `Garden.qml`'s `groundTile`): PrincipledMaterial scales the sky's diffuse light by
  (1 − specular amount), and 0.92 / 0.2 measured 2–8 luma darker than the meadow at the plan's
  edge (L1.4 look review, 2026-10-19). Pinned by
  `tests/unit/test_quick3d_ground_tiles.py::TestTheTileComponent::test_its_material_is_the_meadows_so_the_plan_edge_shows_no_step`.
- **Slices of work on the GUI thread may chain posted events.** A chain of 40 posted events of
  10 ms each starved no timer: a 5 ms `QTimer` fired after the first slice, offscreen and on the
  Windows platform (L1.5 Part B, 2026-10-19) — the controller's ground passes rely on it.
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
- **Production ground (L1.5): tiles, not one texture.** `ui/view3d/ground_bake.py` paints the
  flat records into 512 px tiles (`core/scene3d/ground.py`: the finest of 1, ½, ¼ … px/cm within
  4096 × 4096 px and 256 tiles; every tile a crop of ONE pixel grid);
  `ui/view3d/quick3d/ground_tiles.py` shows one `#Rectangle` quad and one `QQuick3DTextureData`
  per tile, and uploads only a tile whose `bytes` changed. Concept and bounds: docs §8.29.5.
  Measured on bench_small (20 tiles, RTX 4070): first show 20 uploads; a 3 m item moved: ≤ 2
  uploads, bake 3–6 ms, a finished `grab()` 4–10 ms later.
- **The ground arrives in PASSES.** `GroundBaker()` paints for 10 ms a call (`BAKE_BUDGET_S`; at
  least one tile, nearest to the last edit first) and leaves the rest pending — stale tiles, the
  same objects as before, bare on first open. `SceneSync.ground_pending` says so;
  `sync.continue_ground()` is one more pass (one transaction when a tile changed). bench_small
  opens in 2 passes, bench_large in 8; one tile a pass on the RTX 4070: 14 transactions, each
  uploading the tile it painted. A test or a screenshot that needs the FINISHED ground uses
  `GroundBaker(budget_s=None)` or loops until nothing is pending (`render_records` loops); a
  test of the budget injects a clock (`clock=`), never sleeps. Two rules of the queue: a call
  that brings an EDIT while older tiles are pending paints the edit's own tiles first and then
  one tile of the backlog whatever the budget says (a drag used to keep 14 of 15 tiles pending
  for as long as it lasted) — so a pass is the budget plus up to two tiles; and a tile whose
  paint raises as a whole keeps its picture, is listed in `GroundBaker.tile_failures`, is NOT
  pending, and is retried by the next call that brings a change (clearing the baker instead
  made the next edit blank 15 of 16 tiles). A bake that raises anywhere else is the sync's
  `ground_failure`, and the sync calls `baker.restart()` — books forgotten, PICTURES kept until
  each tile is painted anew — never `clear()`, which is for a new plan.
- **A full tile loses its SMALLEST records, never a large one.** More than 256 records (or
  262,144 vertex passes) in a tile: the members are ranked by how much of the tile their paint
  box overlaps — box against box, ties to the topmost — and the lowest go; the rest is painted
  in z order and the tile is in `GroundBaker.capped`. A lawn under 2,000 pavers stays wherever
  its edge runs. The ranking does not know a shape: a thin diagonal line counts as large, and a
  small item on top of 256 larger ones is lost.
- **`ClampToEdge` on both axes of a tile texture.** With the default Repeat, linear filtering at
  a tile's edge blends in its OPPOSITE edge. Invisible on a uniform lawn; on a lawn with another
  colour at the tiles' far edges the luma spread at a four-tile corner was 7.9 (and 24.9 along a
  border, minified) against 0.0 clamped. A seam test needs that second lawn.
- **Lay each quad a hair wider than its tile** (`SEAM_OVERLAP_CM` = 0.02): two quads whose
  shared edge is computed twice in float32 must not leave a line of the meadow below. The
  control — quads 1 cm SHORT on every side — reads a luma spread of 48 magnified and a line dip
  of 29 in a low oblique view (0.46 without the gap). The bare plan rectangle is hidden while
  tiles lie on it (two coplanar surfaces fight for the depth buffer).
- **An attached `QQuick3DTextureData` cannot be updated in place.** `setTextureData(new)` +
  `update()` on a texture a `Texture` shows changed nothing on screen; nor did emitting
  `textureDataNodeDirty` by hand, nor setting the `Texture`'s property to null and back in the
  same turn (each variant rendered and read back: twelve cycles, the first picture every time).
  A fresh object per change shows. (`markAllDirty()` is not exposed by PyQt6 6.11.)
- **ONE texture per `Texture` element, for life — a re-pointed `Texture` goes WHITE.** When a
  `QQuick3DTextureData` that a `Texture` once held is destroyed, Qt resets that element's
  `textureData` to null, whatever it holds by then (a QML binding `textureData: someProperty`
  does not run again). Measured, two tiles, RTX 4070 and WARP: tile A re-textured, then tile B,
  then a frame — A is white; a tile re-textured, a frame, its replaced texture let go — white one
  frame later. Hidden for a whole story because every scenario re-baked the SAME tiles after each
  frame (which sets the property again) and the hardware window presented no frames (so the
  release after a frame never ran). So a re-baked tile is a NEW Model with its own texture
  (`ground_tiles._replace` = drop + create), like "one geometry per Model". Test updates WITHOUT
  a frame between them, on different objects, and look again one frame later.
- **Count texture objects on the C++ side, not Python references.** `ground_tiles.textures_alive()`
  counts the textures made (held in a weak set) whose C++ object `sip.isdeleted` says still
  exists: over twenty full re-bakes of 16 tiles it never exceeds 32 (the shown generation and
  the one it replaced), and reads 320 with the spike's keep-alive list. A Python-owned `QObject`
  subclass instance IS destroyed when Python lets go of it. (It first counted down on Qt's
  `destroyed` signal; a Python callable on `destroyed` may never run once the cyclic collector
  reached the wrapper first, so the product hangs none — `test_sim_clock_subscription.py`.)
- **No repeated `grab()` on a live host that is not presenting — it is the grab that grows a
  Direct3D 11 process, not the upload.** Direct3D frees what was released when a frame is
  PRESENTED; a frame rendered by `grab()` is rendered (its textures are uploaded for it) and
  never presented. Twenty full re-bakes of a 16 MB ground on the RTX 4070 while its window
  presented 0 frames, private bytes per re-bake: a `grab()` after every re-bake **+16 to
  +17 MB** (one generation, given back only when the view closes; 32 texture objects alive, never
  more); a `grab()` every fifth **+3.2**; NO `grab()` **+0.0** (nothing is rendered, so nothing is
  uploaded). Flat in all three on WARP (33–41 frames presented), on OpenGL, and on the same
  hardware window once it presented (38 frames, a grab a cycle: +0.04). The first diagnosis here
  — "keeps every upload until a frame is presented; apply edits no faster than frames" — came
  from a soak that grabbed every cycle, and its remedy targeted the wrong variable. So: (1) a
  leak soak takes NO frame in its measured loop (a live view takes none) — and asks the QML
  scene nothing there either: per cycle it reads counters on the Python side — and is then an
  unconditional gate; the grabbing soak is its control. Say which CELL a run measured: in a
  hardware window that presents nothing the soak renders nothing, so it shows the process side
  only (half a gate); a hardware window that presents is a manual check ("watch Commit size
  while dragging a lawn with the display on"). (2) A still picture of a live view goes
  through the offscreen path (`offscreen.render_records`: its own hidden view, closed after one
  frame — everything is given back), never through repeated `host.grab()`. (3) Record
  `host.health().frames_presented` with every memory curve. Why that window presented nothing is
  not established (an OpenGL window on the same GPU presented 45 frames in the same session).
- **Compare a top-down frame with a baked image like with like.** The truth view is linear
  light and each frame pixel covers several texels: the bake against the frame scored NCC 0.93
  compared naively and 0.98 after linearising the bake and averaging the texels a pixel covers
  (flips: 0.08 / −0.11 / −0.07 either way).

## 6. Hosts

| | `QQuickView` (+ window container) | `QQuickWidget` |
|---|---|---|
| Frame signal | `frameSwapped` | **none** — count `quickWindow().afterRendering` |
| Request a frame | `view.update()` | **`quickWindow().update()`**; `widget.update()` only re-composites the old texture |
| "Is it on screen?" | `isExposed()` — and "can it give a frame?" needs `isSceneGraphInitialized()` and `isVisible()` as well (the predicate bullets below) | `quickWindow().isExposed()` is **always False** (offscreen) → `isVisible()` |
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
- **The window container keeps the main window a raster surface (L1.2).** With
  `QWidget.createWindowContainer(view)` beside the 2D canvas, the top-level window's
  `surfaceType()` stays `RasterSurface` and a 2D pan step costs the same: median 2.56 ms with
  the container vs 2.63 ms without (×0.97; WARP ×0.92). The control — a `QQuickWidget` in the
  same place — turns the surface into `Direct3DSurface`. The surface type is the direct test;
  the timing only says what it would cost. A container belongs to its parent widget: when
  that widget is destroyed Qt destroys the view too, and a Python wrapper used afterwards
  raises "wrapped C/C++ object … has been deleted". `Quick3DHost` asks `sip.isdeleted` on
  every call: such a host reads `closed` and never raises sip's error (what a closed host
  answers is part of the contract, §12).
- **A window without a scene graph can be grabbed exactly once — and only if it is never
  shown (L1.2).** `create()` + `grabWindow()` on a never-shown `QQuickView` gives a correct
  frame once (pixel-identical to a shown grab); the second such grab is the bare clear colour —
  every Model gone, `#Rectangle` included (mean abs difference 161; GPU and WARP). `pick()`
  finds nothing on such a window. Offscreen rendering is therefore one host per frame
  (0.4–0.5 s with one material, 1.1–1.3 s with six).
- **`show()`, then `grabWindow()` before the first expose, kills the process (L1.2, review
  round 1).** The grab RETURNS A CORRECT IMAGE; the process dies in the next passes of the
  event loop — exit 3, `0xC0000005` or `0xC0000374` (3 of 3 on the GPU and 3 of 3 on WARP
  here; the review: 5 of 5, 3 of 3, and 4 of 4 embedded in a splitter). The same death: one
  hidden grab followed by `show()` (3 of 3 on each adapter), and an embedded, never-shown view
  grabbed and then shown by its parent (2 of 2, 1 of 1 on WARP). NOT when the window is
  destroyed before the event loop runs again (6 of 6 survived) — a test whose host goes out of
  scope proves nothing. The condition is `isSceneGraphInitialized()`, never `isVisible()`.
- **Qt's window predicates, measured as (visible, exposed, scene graph initialised) on
  Direct3D 11 (L1.2, review round 1):** new F F F · after `show()` T F F · after one
  `processEvents()` T T T · right after `hide()` F **T** T, then F F T · shown again T F T ·
  minimised **T** F T. Under `QT_QPA_PLATFORM=offscreen` the scene graph reports initialised
  from the window's birth and draws no 3D. These three are NOT enough to know whether a frame
  can be had (the bullets that follow); `Quick3DHost.state` derives new / starting / live /
  hidden / spent / closed from the facts it reads on every call (the contract: §12). There
  is no "was shown" flag, because the parent of an embedded container shows and hides it
  without asking.
- **"Never shown" means "no platform window was ever created" (L1.2, review round 2).**
  `show()` + `hide()` before any event leaves a window with no scene graph that is not visible
  — and that HAS a platform window. The one offscreen grab taken then is a correct image;
  on **xcb the process segfaults in the next event-loop pass** (5 of 5; it was the red CI
  job), on Direct3D 11 it survives. A window the user closed with its X button: platform
  window destroyed, scene graph kept; a raw grab is an access violation (Direct3D 11) or a
  segfault (xcb). The fact to ask is Qt's `PlatformSurface` / `SurfaceCreated` event, latched
  by an event filter: `QWindow.handle()` is not bound by PyQt6 6.11, and `winId()` creates
  the window it asks about.
- **A collapsed splitter pane is visible, exposed and 0 px wide (L1.2, review round 2).** A
  raw grab there returns an image of the OLD size without a pixel of the scene, a raw pick
  returns a hit, `mapFrom3DScene` (0, 0). After an ASYNCHRONOUS change of size (a splitter
  move, `resize()`, `showMaximized()`) the QML root item keeps the old size until the resize
  event is delivered (reopened from 0, the scene is still 0 wide — a blank frame). A window
  1 px wide or high draws no 3D (the bare clear colour); 2 px does. A pane re-shown in a
  splitter keeps its stale empty geometry until the pending layout request is delivered.
- **A resize can arrive INSIDE the call that caused it — `showFullScreen()` (L1.2, review
  round 3).** Measured with an event filter on the view, Direct3D 11: `showFullScreen()`
  delivers `Resize`, `Move` and `WindowStateChange` before it returns — window AND root item
  have the new size at once — and `Expose` in the next event-loop pass. `grabWindow()` on a
  shown window renders into the swap chain as it is, and Qt resizes the swap chain with that
  expose: a grab in between has the OLD size (20 of 20). `showNormal()` delivers its expose
  inside the call too; `showMaximized()` and a splitter move deliver nothing inside the
  call; a main window that was maximised has not touched an embedded view at all until its
  layout ran. In every one of those lines a grab has the wrong size between a `Resize` event
  and the next `Expose` event of the exposed window — **an observation, NOT a rule to wait
  on** (round 3 latched it with an event filter; the next bullet is what that cost). Never
  from `frameSwapped` either: it is queued from the render thread, and one emitted before a
  resize can arrive after it. And "one event-loop pass" is not a unit: that pass took
  6–13 ms, and up to about 1 s after a grab with the display asleep.
- **Qt resizes the render target when it next DRAWS the window — and nobody owes you a paint
  message. Take a frame and look at its size (L1.2, review round 4).** Measured, Direct3D 11:
  a pane that GROWS beyond the screen's edge got `Resize`, `Move` and nothing else while the
  display slept — a raw grab stayed 49 × 500 px for a 136 × 500 window for as long as the
  pane was there — and `Resize`, `Move`, `UpdateRequest` (still no expose) with a frame of
  the right size while the display was awake: same machine, same edge, both ways on one
  day; on WARP the update request came with the display asleep too. A pane SHOWN there
  was exposed in none of these. With an event filter that eats the view's `Expose` /
  `UpdateRequest` / `Paint` the same stale target appears ON the screen, on Direct3D 11 and
  on xcb + OpenGL: 447 × 500 px for a 600 × 500 and for a 200 × 500 window, for ever.
  So: no state fact that only an OS paint message can set (a host that waits for one waits
  for ever — CI was red on a 1024 px runner for exactly that), and no geometry test
  either ("is it on a screen?" does not say whether Qt draws). `grabWindow()` costs 0.7 to
  4 ms; compare its size with what QT makes for the window — `QSize(logical) * ratio`,
  `qRound` per side, so the right frame is at most HALF a device pixel off `logical ×
  ratio`. (Two pixels of tolerance handed out a 447 px frame for a 448 px window; "less
  than one pixel" handed out the 553 px frame of a 442 px pane for a 443 px one at 125 % —
  r5. 100 %, 150 % and 200 % are exact whatever the tolerance: test a ratio strictly
  between 1 and 1.5.) And a raw `pick()` right after a resize, with no frame
  in between, MISSES — the engine picks with the viewport of the frame it rendered last;
  `mapFrom3DScene` is right. One frame, even of the old size, and the pick hits.
- **`QEventLoop.exec()` returns −1 at once while the application is quitting (L1.2, review
  round 3)** — inside a running main loop after `QCoreApplication.quit()`, about 2 µs a
  call. A wait built on a local event loop spins then (158,574 passes in 3 s): check
  `exec()`'s return and bound the number of passes. Without a running main loop `quit()`
  does nothing, so no in-process test meets this — use a child that runs `app.exec()`.
- **Harmless, also measured:** a grab while hidden WITH a scene graph (a correct frame, 2 of 2
  on Direct3D 11 — the host refuses it all the same); wrapping a view that is live, starting
  or hidden in a window container.
- **NEVER install a Python Qt message handler while a Qt Quick window is shown (L1.2, review
  round 2).** Qt Quick renders a shown window on a thread of its own — `qt.scenegraph.general`
  says "threaded render loop" on Direct3D 11 (GPU and WARP) and on xcb + OpenGL (llvmpipe).
  `qInstallMessageHandler` is process-wide, and PyQt calls a Python handler under the GIL on
  whichever thread emits. The GUI thread holds the GIL inside a Python-called `hide()` and
  waits for the render thread; the render thread emits a message and waits for the GIL:
  **deadlock, every run**, on all three. A recorder is safe only around rendering on the
  calling thread — the one-shot offscreen grab of a never-shown window, where every message
  (shader errors included) was measured to arrive on that thread. To read a shown window's
  messages in a TEST, let Qt print them: `QT_FORCE_STDERR_LOGGING=1` (on Windows a process
  without a console logs to the debugger otherwise) + `QT_MESSAGE_PATTERN`, and parse the
  child's stderr. To see which loop runs: `QT_LOGGING_RULES=qt.scenegraph.general.debug=true`.
  The product's guard is static — `tests/unit/test_quick3d_boundary.py` scans all of `src/`:
  `qInstallMessageHandler` / `QLoggingCategory.installFilter` only in `quick3d/qt_messages.py`
  (and the dormant spike's own), the recorder's `install` only from `offscreen.py`, a
  render-thread signal (`frameSwapped`, `sceneGraphError`, the `afterRendering` family) only
  through `host._connect_queued`. Necessary, not sufficient: it cannot see a third-party
  handler, nor a Python override of a virtual Qt calls on the render thread.
- **A Windows process deadlocked inside Qt survives `_exit` (L1.2, review round 2).**
  `faulthandler.dump_traceback_later(exit=True)` writes the stacks and the process stays alive:
  `_exit` is `ExitProcess`, which waits in DLL detach code. On Linux `_exit` ends it. Only
  `TerminateProcess` from ANOTHER process ends it with a chosen exit code —
  `runlog.watchdog(…, supervised=True)`.
- **Connect `sceneGraphError`, or a missing graphics device takes the app down (L1.2, review
  round 2).** With a slot: `(ContextNotAvailable, "Failed to initialize graphics backend for
  D3D11.")`, the process lives, the window never gets a scene graph. With none: a native modal
  error box, then abort (`0xC0000409`). Force it with `QT_D3D_ADAPTER_INDEX=9`.
  (`QSG_RHI_BACKEND=bogus` just falls back.)
- **A QML function that throws returns `None` to `QMetaObject.invokeMethod`, silently** (L1.2,
  review round 2); a missing one raises `RuntimeError`. Check the return, and read the QML
  engine's `warnings` signal — it arrives on the GUI thread, with file and line.
- **On Windows `QStandardPaths` follows `USERPROFILE`, not `APPDATA`** (L1.2, review round 2):
  to keep a child process out of the real profile set `USERPROFILE` (Qt's shader cache and the
  driver's caches go with it); `APPDATA` alone redirects only code that reads the variable.
- **Do not wait for `frameSwapped` to be sure of a frame (L1.2).** On Windows, Qt 6.11
  delivers update requests from a thread that waits for the display's vertical blank. With the
  monitor asleep, a visible, exposed, active window presented its first frame and then none
  (1 frame after 40 `update()` calls; `QT_D3D_NO_VBLANK_THREAD=1` → about 4 per second; on WARP
  they flow). `grabWindow()` renders and reads back synchronously regardless (1–9 ms): it is
  the synchronisation point. A `QQuickWidget`'s window composition waited 262 ms per 2D pan
  step on that machine.

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
  (`ui/view3d/quick3d/qt_messages.py` since L1.2 — the spike had its own:
  `qInstallMessageHandler`, into the log and `metrics.json`) and
  fail on shader/QML errors — a frozen exe has no stderr to read them from. A clean llvmpipe
  run emits no Qt messages at all, so the gate has no false alarms there.
- **Aim probes at the actual view size** (measured in the spike, `SpikeRenderer.view_size()`), not the requested
  one: a window larger than the screen is clamped.
- **Which device rendered? (L1.2)** `rendererInterface().graphicsApi()` names the API, not the
  adapter. Switch on Qt's `qt.rhi.general` debug output
  (`QLoggingCategory.setFilterRules("qt.rhi.general.debug=true")`) and read it from the message
  handler: Direct3D lists every adapter and prints `using this adapter` after the chosen one;
  OpenGL prints the context's `RENDERER`. `quick3d/qt_messages.py::graphics_adapter` does it.
  **Force the software rasteriser on Windows with `QSG_RHI_PREFER_SOFTWARE_RENDERER=1`** — the
  log then says `Microsoft Basic Render Driver` (WARP), which is what a GPU-less runner has.
- **A recorder that replaces the Qt message handler must forward (L1.2).**
  `qInstallMessageHandler` keeps ONE handler: a recorder installed for one frame hid a shader
  error from the recorder of the whole run. `qt_messages.install` chains to the handler it
  replaced. Warnings that belong to the machine are a class of their own, listed exactly —
  so far one: `qt.qpa.screen: "Unable to open monitor interface to …"` (display asleep).
- **Classify a Qt message by its level first (L1.2, review round 1).** Only a WARNING is
  promoted to an error by its text; debug and info lines are information whatever they say.
  With `qt.rhi.general.debug=true` switched on, the first version ran the error patterns over
  debug output — the wording of a Qt debug line could have failed a release. And switch that
  rule off again: `QLoggingCategory.setFilterRules` holds ONE rule set per process and has no
  getter; `qt_messages.graphics_info()` is a context manager that nests.

- **Linux:** the `offscreen` QPA selects the *software* scene graph, which cannot render 3D.
  Use `xvfb-run` + `QT_QPA_PLATFORM=xcb` + `QSG_RHI_BACKEND=opengl` (+ `LIBGL_ALWAYS_SOFTWARE=1`
  in a container). Packages: `libegl1` (the QtQuick3D binding links libEGL), `libxcb-cursor0`
  (xcb plugin). As root, Qt WebEngine needs `QTWEBENGINE_DISABLE_SANDBOX=1`.
- **Windows runner** (windows-latest, no GPU): `Direct3D11Rhi` on WARP (the spike printed
  PyQt's enum member name; the production host says `Direct3D11` — §2). Frozen exe: QML load
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
    venv/bin/python -m pytest tests/integration/test_quick3d_render.py -n 0
  ```

  (Until L1.10 the tier's only file was the spike's `test_spike_q3d_render.py`; CI's `render3d`
  job runs the engine package's render files on Linux and on Windows WARP, §12.)

## 9. Packaging (PyInstaller)

- The spec needs a data loop for the QML + shader files and hidden imports for
  `PyQt6.QtQuick`, `QtQml`, `QtQuick3D` (`QtQuickWidgets` left the spec with the spike in
  L1.10: the product never uses a `QQuickWidget`).
- **The Qt Quick 3D runtime already ships in today's bundle.** Windows dist, branch vs master
  built in the same job: 626.2 MB vs 624.5 MB → **+1.7 MB** (only `QtQuick3D.pyd` and the QML
  files are new). Quick3D + ShaderTools files: 21.1 MB (Windows), ~23 MB (Linux); the Qt 3D DLLs
  it replaced: 5.8 MB (L1.10 removed them; the bundle before and after is ADR-048's closing
  addendum).
- Frozen Windows exe with the spike bundled: the `--selftest` gate exited 0 (ogp-change-control
  §2.8 is its home); it exits 0 without the spike and the Qt 3D wheels too (L1.10, ADR-048's
  closing addendum).
- **L1.2:** the production package adds its five QML and shader files (a data loop in
  `installer/ogp.spec`) and eleven modules: **+79,008 bytes** (650,815,562 vs 650,736,554,
  same machine, same day, same shell). `--selftest` now also RENDERS one hidden 160 × 120
  frame from the bundle's QML and shaders and judges its pixels (§12); frozen exe 2.9–4.1 s on
  an RTX 4070 and 2.9–3.3 s on WARP for the whole command (6.1–7.2 s on a busy machine).
- **A local bundle's content depends on PATH (L1.2, review round 1).** Built from Git Bash it
  carries `libcrypto-3-x64.dll` and `libssl-3-x64.dll` (5,531,448 bytes) — byte for byte the
  files in Git for Windows' `mingw64/bin`, which is on that shell's PATH; built from a plain
  PowerShell process it does not (650,815,562 vs 645,326,627 bytes, 2,450 vs 2,448 files).
  Both exes pass the smoke and `--selftest`. Compare bundle sizes only between builds made
  from the same shell.

## 10. CPU-side baselines (not engine)

`bench_small.ogp` (99 items): plan load 0.1–0.5 s, ground bake 0.1–0.3 s, mesh build ~0.5 s
for 185k triangles (Linux and Windows alike). `bench_large.ogp` (425 items): 2.28 s for 1.46M
triangles (`scripts/bench_view3d.py`, deleted with the spike in L1.10; its last run, on the
L1.9 tree: small 260 ms for 205,032 triangles, large 1,523 ms for 1,429,032, the spike's
build).

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
| Private bytes climb by one ground upload per cycle, and fall back when the view closes | `grab()` on a Direct3D 11 hardware window that presents no frame: the grabbed frame's uploads stay committed until a Present | not a lifetime bug if `textures_alive()` stays ≤ 2 generations; take the grab out of the loop — the curve is flat; screenshots through the offscreen path (§5) |
| A ground tile turns WHITE after another tile was re-baked, or one frame after its own re-bake | its `Texture` element was pointed at a second `QQuick3DTextureData`; destroying the first reset `textureData` to null | one texture per `Texture`, for life: a re-baked tile is a new Model (§5) |
| A tile border shows as a line only on patterned ground | the tile texture repeats: its opposite edge is blended in | `tilingModeHorizontal` / `Vertical: Texture.ClampToEdge` (§5) |
| A re-baked tile keeps its old picture | its `QQuick3DTextureData` was updated in place | a NEW Model with a new texture object per change (§5) |
| Plan ground white after a probe; the second window "differs" by ~10 luma | the same `QQuick3DTextureData` re-attached after being detached | re-upload it on re-attach; assert `probe_restore_frame_diff` < 1 |
| The second offscreen frame is an empty sky (L1.2) | a never-shown window renders one frame, then its scene is gone | one host per offscreen frame |
| A wait for frames times out although the window is visible (L1.2) | display asleep: no vertical blank, no update requests | never wait for presented frames; `grab()` |
| QML: Cannot assign to non-existent property "exposure" (L1.2) | plain `SceneEnvironment` | `ExtendedSceneEnvironment` |
| A broken shader raises, but the run's summary counts 0 errors (L1.2) | a nested message recorder replaced the outer one | recorders forward to the handler they replaced |
| `--selftest` fails with `RenderError: Qt Quick runs on the Software backend` (L1.2) | it ran under `QT_QPA_PLATFORM=offscreen` | run it with a real platform |
| "wrapped C/C++ object of type QQuickView has been deleted" on close (L1.2) | the widget that parented the window container was destroyed first | the host asks `sip.isdeleted` and reads `closed` (what a closed host answers: the contract, §12) |
| The process dies a moment AFTER a grab that returned a good image (L1.2) | the window was shown but not exposed yet (no scene graph), or was shown after its one offscreen grab | `wait_ready()` (check its answer) before `grab()`; a spent host is replaced, never shown |
| `TypeError` / `ValueError` / "not a live part" from a sink's `clear()` after the window closed (L1.2) | two owners of Model lifetime: the sink destroyed part by part with handles the dead host no longer knew | the host owns every Model; `clear()` asks it once and forgets in a `finally` |
| A file of 30+ engine tests reports only skips (L1.2) | its canary ran product code, and the product was broken | a canary of bare Qt; a positive control that a broken scene FAILS the file |
| `'OpenGL'` is not in a list that says `'OpenGLRhi'` (L1.2) | PyQt's enum member names are inconsistent | map the enum member, not a string |
| Foliage drawn beside its mesh although the clock stands still (L1.2) | the wind shader's sway is not 0 at time 0 | a rest factor that is exactly 0 at time 0 |
| `io.UnsupportedOperation: fileno` when a watchdog is armed (L1.2) | `faulthandler` writes to a descriptor; stderr was captured or replaced | dump into the log's own handle, else into the null device — the exit still happens |
| A CI step prints its verdict and nothing after it (L1.2) | `Write-Error` under GitHub's pwsh (`$ErrorActionPreference = 'stop'`) ends the step | `Write-Host "::error::…"`, the log in `try`/`catch`, `exit 1` at the end |
| Two identical frames around an edit (L1.2) | the edited item was hidden behind another | edit something the camera sees |
| `hide()` (or `close()`) never returns; the watchdog's stack dump is in the log and the process is still there (L1.2 r2) | a Python Qt message handler + Qt's render thread + the GIL | no Python message handler beside a shown Qt Quick window; `health()` for a shown host |
| A segfault on Linux one event-loop pass after an offscreen grab that worked on Windows (L1.2 r2) | the window had been shown and hidden: it has a platform window | only a window whose platform window was NEVER created has the offscreen frame |
| A blank frame of the old size, a pick that hits nothing real, `project()` == (0, 0) (L1.2 r2) | the pane is collapsed (0 px wide), or was resized a moment ago | through the host there is no such frame: `grab()` / `pick()` / `project()` answer for the window's current size or raise `HostStateError`. `wait_ready()` (act on its answer) when you need the frame; else just call and take the refusal |
| A modal "Failed to initialize graphics backend" box, then the app is gone (L1.2 r2) | nothing connected to `QQuickWindow.sceneGraphError` | connect it; read `health().scene_graph_error` |
| `reset()` "succeeds" and the old Models are still drawn (L1.2 r2) | a QML function that threw returned `None`, taken for success | a Model leaves the books only when the engine confirms it; `None` is an `EngineError` |
| A test run is killed minutes after a watchdog test passed (L1.2 r2) | a supervising process that found its release event already gone and waited on the process alone | a missing event means "released" |
| An empty folder appears in the real `%APPDATA%` after a test (L1.2 r2) | the test set `APPDATA`; Qt's standard paths follow `USERPROFILE` | give the child a profile of its own; ask `writableLocation` before anything is created |
| "The host is ready" — and the next grab is an image of the OLD size (L1.2 r3) | `showFullScreen()` delivers its resize inside the call; the swap chain is resized by the NEXT expose | the host takes a frame and compares its size with the window's, by Qt's own rounding (half a device pixel) — another size is a refusal; `wait_ready()` delivers pending events and proves "ready" with such a frame. (r3 waited for that expose instead: the next row) |
| A shown pane never becomes ready, `wait_ready()` burns its whole timeout — on a small CI screen only (L1.2 r4) | a state fact that only an `Expose` could set; no expose reaches a pane that grows or is shown beyond the screen's edge | no fact an OS paint message must set: the frame is the witness. `wait_ready()` gives up 0.5 s after the last sign of progress, whatever its timeout |
| `wait_ready(0)` takes a second (L1.2 r4) | a `processEvents()` pass outside the deadline; one Qt expose handler can take 1 s | the delivery of events is inside the timeout; a zero timeout runs none. What cannot be cut short is the ONE handler already running |
| A pick right after a resize misses; the projection is right (L1.2 r4) | the engine picks with the viewport of the frame it rendered last | take a frame first — `host.pick()` / `host.project()` do when the host knows of none for the window's size: one after a resize, none in the steady state, ONE per refusal while the target stays behind (r5: it was one per call) |
| A stale frame handed out at 125 % only; every tier green at 100 %, 150 %, 200 % (L1.2 r5) | the size check was "less than one pixel off"; Qt rounds a render target to `qRound(logical × ratio)` — and the tests' judge used the host's inequality | `abs(frame − logical × ratio) <= 0.5`; a ratio strictly between 1 and 1.5 in the tests; a judge that computes `qRound` itself and never imports the host's rule |
| A tick that projects 200 labels takes 0.4 to 0.8 s and draws nothing (L1.2 r5) | `pick()` / `project()` took a probe frame per call while the render target was behind | one probe per refusal — renewed by a sign of progress, by other facts, or after 0.25 s; the caller's tick stops at its first `HostStateError` |
| `wait_ready(5)` says False after 0.75 s, and True when asked again (L1.2 r5) | the stall bound counted wall time; the GUI thread was busy in another handler, the repaint queued behind it | count silence pass by pass: a pass of the event loop that overran its step was busy, not silent |
| `wait_ready(0.2)` returns after 1.8 s (L1.2 r5) | one pass of Qt's event loop delivers the WHOLE queue (six handlers of 0.3 s), not one event | nothing to fix from that thread: it is a nested event loop that takes user input — the workspace calls it nowhere on the GUI thread |
| A lifecycle matrix green on the dev box, red on the runner (L1.2 r4) | its windows were where the window system put them, sized for a large screen | place every window on purpose; cap sizes by `availableGeometry()`; run the walk once as on 1024 × 768; make "nothing draws the view" with an event filter instead of hoping for it |
| `[selftest_supervisor] ok=True` although the supervisor left 1.5 s into the block (L1.2 r4) | exit code 0 meant both "released" and "found nothing to wait for" | 4 for a supervisor that never supervised; the block keeps its signalled event until the supervisor has left, so "late" is 0 and "lost" is 4 |
| A healthy block is terminated a few seconds in, and ANOTHER block's log says why (L1.2 r3) | the supervisor's release event was named after the process: a finished block's late supervisor found the next block's event | a random nonce per block in the event's name; one armed watchdog per process |
| A bounded wait burns a core while the app is closing (L1.2 r3) | `QEventLoop.exec()` returns at once after `quit()` | check `exec()`'s return value; bound the passes |
| `--selftest` fails with "FAIL self-test supervisor" although every block passed (L1.2 r3) | on Windows its supervising process did not start, refused, or did not leave | that IS the failure: read the `[watchdog]` and `[selftest_supervisor]` lines of the log; a deadlock would not have been ended |

## 12. The production package — `ui/view3d/quick3d/` (L1.2)

Concept and module map: §8.29.2 of `docs/08-crosscutting-concepts/README.md`; the decision and
every measurement: ADR-048, addendum L1.2. What you need at the keyboard:

- **Sink and host.** `adapter.Quick3DSink(host)` is the `EngineSink`; `host.Quick3DHost(size)`
  is the `QQuickView` and implements the sink's `EngineScene` — it OWNS every Model.
  `SceneSync(Quick3DSink(host)).apply(records, sun=…, ground=…)` is the whole wiring.
  `host.container()` embeds it; `host.pick(x, y)` returns a `PickHit` in the SCENE frame;
  `host.engine_parts()` reads the Models back from the QML scene (what the engine holds, not
  what the sink believes).
- **The host's states.** `host.state` is `lifecycle.state_of` over the facts the host reads
  from Qt on every call. **The contract — the facts, the six states, what each promises,
  which call is legal in which, what `wait_ready()` means, what raises what — is the module
  docstring of `src/open_garden_planner/ui/view3d/quick3d/lifecycle.py`. Read it THERE; it
  is deliberately written down nowhere else** (it stood in nine places once, this skill
  among them, and three were wrong; a test now fails a second copy of the state table). At
  the keyboard: **the workspace needs `wait_ready()` nowhere on the GUI thread** — it is a
  NESTED EVENT LOOP that takes user input. A click, a hover, a tick that draws just calls
  `host.pick(x, y)` / `host.project(...)` in `try` / `except HostStateError`, and **a tick
  stops at its first `HostStateError`** (while the render target is behind, the next call
  gets the same refusal without another frame). Where a frame must be HAD and the caller
  can wait — an export, a tool, a test — `if not host.wait_ready(): …`, and act on the
  answer; never count event-loop passes (§6). It starts no pass once its timeout is up
  (1 s by default) and returns within that plus whatever was queued on the event loop —
  one pass delivers the whole queue — and the first show of a process takes 0.7 to 1.7 s;
  it says False after 0.5 s of silence. Never from a timer slot, a sync tick, a paint or a
  resize handler. `grab()`, `pick()` and `project()` never pump; each answers for the
  window's current size or refuses. A
  refusal is a `HostStateError` whose text names what is missing and what to do. Under
  the software scene graph `host.renders_3d()` is False and `grab` / `pick` raise
  `EngineError`.
- **Recovery.** After a sink call raised: `sync.reset()` (it calls `Quick3DSink.clear()`, which
  is legal in a half-applied transaction and on a dead host), then `sync.apply(...)`. When the
  host itself died: `sink.attach(fresh_host)` in between. Check with
  `sink.state() == sync.expected_state()` AND against the engine: `host.part_count()`,
  `host.engine_parts()`. A LIVE engine that cannot destroy a Model keeps it in the host's
  books and raises — `reset()` stays poisoned and the next one tries again; the sink refuses
  `begin()` until a `clear()` went through. One sink per host: a host that holds Models is
  refused by `Quick3DSink(host)` and by `attach`.
- **Trouble in a SHOWN view: `host.health()`** — poll it on the GUI thread (a timer). It
  returns `HostHealth(frames_presented, qml_warnings, qml_warning_count, scene_graph_error)`
  with `.ok`, in every state; each item was also logged when it arrived. There is NO message
  watch (`watch_messages` / `engine_errors` were removed: they deadlock, §6). A shader of a
  shipped material that does not compile is NOT in it — that is checked before release: the
  render tier and `--selftest` compile every shipped shader under a recorder.
- **One frame without a window:** `offscreen.render_records(records, shot=TopDownShot(...),
  sun=SunState(...), ground=GroundSpec(...), size=(w, h))` → `OffscreenFrame` (`.image`,
  `.rgba()`, `.open_ms`, `.build_failures`, `.adapter` with `graphics_info=True`). A QML or
  shader error, or a backend without 3D, raises `RenderError`. For processes that own
  themselves — a tool, a test, the self-test — NOT for the running app: it blocks 0.4–1.3 s
  and builds and destroys a graphics device per call. Silent unless `log=` is passed. It
  records Qt's messages with a Python handler, so it REFUSES (`RenderError`) while a Qt Quick
  window is shown in the process; `frame.qt["other_threads"]` must be 0 (the render tier and
  the self-test both require it).
- **The engine boundary without a GPU.** Under the offscreen platform `Garden.qml` loads and
  Models are created, posed and read back — no pixels, but every sink call, the state rules,
  the teardown orders and the recovery are checkable: `tests/ui/test_quick3d_host.py` (default
  tier). Its canary is bare Qt with inline QML — NO product code — so a broken scene file
  fails the tests instead of skipping them; `render_records` raises `RenderError` naming the
  `Software` backend there.
- **The render tier** (opt-in, opens windows):

  ```bash
  # Windows (Git Bash) — the real GPU, then WARP
  OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_quick3d_render.py \
      tests/integration/test_quick3d_engine.py tests/integration/test_quick3d_selftest.py \
      tests/integration/test_quick3d_lifecycle.py
  OGP_RENDER3D=1 QSG_RHI_PREFER_SOFTWARE_RENDERER=1 venv/Scripts/python.exe -m pytest \
      tests/integration/test_quick3d_render.py tests/integration/test_quick3d_lifecycle.py
  # Linux
  OGP_RENDER3D=1 QSG_RHI_BACKEND=opengl LIBGL_ALWAYS_SOFTWARE=1 \
    xvfb-run -a -s "-screen 0 1920x1080x24" venv/bin/python -m pytest \
    tests/integration/test_quick3d_render.py tests/integration/test_quick3d_engine.py
  ```

  No Linux machine? The CI job's stack fits in a container: `ubuntu:24.04`, the job's apt
  packages plus what a bare image lacks for Qt (fontconfig, dbus, nss, the X11 and xcb
  libraries), `uv sync --locked --python 3.11 --all-extras --group build`, then the Linux
  command above inside it. That is how xcb was measured before a push in review round 2 —
  the Windows numbers had said nothing about it. The matrix's children get their environment
  from `quick3d_render_support.isolated_env` / `render_env` only: never hand a child the
  developer's `APPDATA` or profile (`USERPROFILE` on Windows, `HOME` elsewhere). The app's
  SETTINGS are a registry key on Windows, which no variable moves: the helper puts a
  `sitecustomize.py` first on every child's path, which rebinds the store's names the
  moment the child imports `app/settings.py` (docs §8.8). A probe you run by hand gets
  none of this — rebind `app.settings.ORGANIZATION_NAME` / `APPLICATION_NAME` to a test
  key BEFORE anything builds a store, or loading a plan writes your own Recent Files. And
  pytest-qt installs a Python Qt message handler for every test: a test that shows a host IN
  the pytest process is marked `@pytest.mark.no_qt_log`. (Under `offscreen` Qt names no
  render loop and nothing ever hung — an absence, not a guarantee; on a real platform it is
  a deadlock.) Real-platform hosts live in child processes.

  The driver alone, to look at frames (`<out>/*.png`, `result.json`, `render.log`):
  `venv/Scripts/python.exe tests/integration/quick3d_render_driver.py --out <out> --scenarios
  truth,materials,rest,states,edits,recovery,pick,sun,integration,embed`. One call order of the
  host's lifecycle, in a process of its own: `venv/Scripts/python.exe
  tests/integration/quick3d_lifecycle_child.py show_grab` (it lists the orders when called
  without one). From a git worktree set `PYTHONPATH` to that checkout's `src` first for
  anything that is not pytest.
- **The self-test's 3D block:** `quick3d/selftest.py::run_selftest()`; the log is
  `OpenGardenPlanner-selftest-3d.log` in the app's log directory (beside `app.log`), or
  `OGP_SELFTEST_LOG`. The whole `--selftest` runs under ONE watchdog (300 s, the reason in the
  log before the exit) — `faulthandler` has a single timer per process, so ONE watchdog per
  process at a time: a second `runlog.watchdog` while one is armed raises `WatchdogError`.
  It is SUPERVISED: a second process (the exe with the INTERNAL flag `--selftest-supervisor`;
  from source the base interpreter running `runlog.py`) terminates the first at 310 s if it
  is still there. It acts for one block of its own parent process only — pid, creation time,
  a random nonce per block — and refuses anything else with exit code 2. Its exit code says
  what it did: 0 it held the block's release event (released, or it ended a hang), 4 it
  found no block to wait for and never supervised (review round 4: that used to be 0), 3
  it failed itself (round 5: also when its own wait fails — that was 0 too). The log's `[watchdog] armed=True … supervisor=process <pid>` line says
  it started, `[selftest_supervisor] ok=True` that it was released and left, a
  `[supervisor] fired=True` line that it had to act. On Windows the self-test FAILS without
  it (`FAIL self-test supervisor -> …`). There is no start timeout while the block runs;
  the block waits 15 s at its end for the supervisor to have come up and left. Never run
  `--selftest` under `QT_QPA_PLATFORM=offscreen`.
- **Numbers** (RTX 4070 / WARP, 2026-10-11): open of `bench_small.ogp` (98 records, 87 Models)
  to the first finished readback 0.40–1.11 s / 0.17–0.39 s (the device creation varies);
  edit → finished readback median 7.1–7.5 ms (p95 18.0) / 23.2–26.5 ms; pick 0.01–0.2 ms;
  shadow IoU vs the analytic 2D shadow 0.976–0.978 at 35° and 480 × 360; engine import 17 ms
  on top of 17 ms for `core/scene3d`. The render tier after review round 2: 96 tests, about
  four minutes on either adapter (237 s / 251 s, the machine busy); on xcb + llvmpipe in a
  container 88 passed and 8 skipped in under two minutes. After round 3 (100 tests, the
  seeded random walk among them): 99 passed and one control reported in 321 s on the GPU;
  97 passed, the two hardware-only budgets skipped and the control reported in 244 s on
  WARP; 92 passed and 8 skipped in 184 s in the container. After round 4 (104 tests: a
  second walk as on 1024 × 768, rows for the pane beyond the edge, a 2 × 60 px pane and a
  view that nothing draws): 103 passed and one control reported, not asserted, in 458 s on the GPU; 101 passed, the two hardware-only budgets skipped and the control reported, in 355 s on WARP; 96 passed and 8 skipped in 241 s
  in the container. After round 5 (105 tests: the 125 % row joined): 104 passed and one control reported, not asserted, in 411 s on the
  GPU; 102 passed, the two hardware-only budgets skipped and the control reported, in 287 s on WARP; the lifecycle file on xcb in the container 41 passed, 4 skipped in 159 s.
- **Not measured:** real display scaling of the operating system (the ratios between 1 and 3
  were set with `QT_SCALE_FACTOR` on a 100 % screen); what the one frame `pick()` /
  `project()` take after each resize costs with the display awake (asleep: about 1 s a
  step on the GPU, 25 ms on WARP); platforms that un-expose an occluded window (macOS, Wayland) — a visible,
  covered host may read `starting` there (`wait_ready()` then says False after 0.5 s, as
  for every other cause); a change of the device pixel ratio in mid-session (L1.3's manual
  checklist: drag the window between two monitors); what GitHub's Windows runner does with
  a pane beyond its screen under the round-4 tree; `frozen-selftest.yml` on any runner —
  the FROZEN exe as its own supervisor never ran on one (from source the supervising
  process does start inside a GitHub job); macOS; an integrated GPU; a display scale other
  than 100 %; a failed device creation on OpenGL or Vulkan.

## 13. The engine inside the app — the workspace (L1.3)

Concept: docs §8.29.3; decisions and every number: ADR-060 and the ADR-048 addendum "L1.3"; the
test patterns: docs §8.10.9. What the ENGINE taught once it ran inside the real app:

- **`releaseResources()` LEAKS same-size `QQuick3DTextureData` textures (Qt 6.11.0, #532).**
  `QSSGBufferManager::clear()` (`qssgrenderbuffermanager.cpp` ~2049–2052) iterates
  `customTextureMap` with `++it` while `releaseTextureData(it.key())` erases through its own
  lookup (~1516); Qt 6's `QHash` back-shifts the next entry of a collision run into the freed
  slot, `++it` skips it, and the final `clear()` of the map drops it unreleased. The key's hash
  (~2290; `qssgrendertexturedata_p.h` 74–77) is size / depth / format / transparency only, so
  same-size textures all collide: about half leak per release (WARP, 16 × 512²: +10.8 MB a
  cycle). Static textures too (release, then a redraw). Distinct sizes only help below ~16
  textures; in-place `setTextureData` updates show a STALE picture; `Texture.sourceItem` images
  avoid the map but still kept one generation per rebuild in the workspace (holder unknown).
  The `imageMap` loop (~2043–2046) has the same pattern; the mesh branch copies keys first.
  Measured on the L1.5 branch, 2026-10-19 (probes in the plans' `scratch/L1.5/fu22/`).
  **In the product EVERY release leaks** (the bake asks for none, but item changes do —
  64 retired Models + 0.5 s quiet, or 512 at once; a date change on a planted plan retires
  every plant): up to ~42 MB per release for the largest ground (4096² px, ~85 MB with
  mips). Gate what ships: the workspace's G7 soak runs with the bake ON against
  `LEAK_BOUND` + 0.6 × its OWN tile-texture bytes per release × releases per reload
  (the driver reports `ground_texture_mb`) — not with the bake off, not against a fixed
  ceiling (L1.5 review 3).
- **Qt keeps graphics state for every Model it ever drew — release it.** After a Model is
  destroyed, Qt Quick 3D still holds its cached per-draw-call state: about 62 kB per Model, about
  190 kB when it casts into the sun's two shadow cascades, independent of the mesh's size
  (measured with 300, 3,000 and 12,000 vertices). Only `QQuickWindow.releaseResources()` gives
  it back — `Quick3DHost.release_cached_resources()`, 2 to 10 ms, and the next frame is the same
  frame. More frames, the QML engine's garbage collection, `clear()` instead of single
  destroys: no effect. The workspace counts what each pass destroyed (`TickReport.retired`)
  and releases when 64 piled up and the pipeline is quiet, or at once at 512
  (`src/open_garden_planner/ui/view3d/workspace.py`). **Anything new that creates and destroys
  engine objects per edit or per tick — a ground texture per bake, a selection outline, plants
  regrown by an animated date — must be counted the same way, or measured to leave nothing.**
  20 rebuilds of `bench_small` in the production host, the view presenting, no readback:
  19 MB per rebuild without the release, 2.0 with it (the large plan 65 and 6.4; WARP 20 and
  3.3; over 60 rebuilds 1.8).
- **Creating and destroying a Model is never free.** After the release 15 to 20 kB per
  destroyed Model remain (2 MB per rebuild of 98 Models, linear over 60) — and it is not
  graphics state: the same rebuilds in a view that draws nothing leave 1.5 MB each. Bare Qt,
  no product code, nothing drawn, `createObject()` then `destroy()`, the QML engine's
  collector called every round: 0.78 kB per `QtObject`, 2.2 per `Model`, 3.4 per `Model`
  with a `PrincipledMaterial` — straight lines over 120 rounds. So: do not design a feature
  around replacing many Models per tick (a date played back regrows every dated plant).
  Untried ways out: keep the Model and hand it a new geometry; scale instead of rebuilding.
- **Never take a frame from a live, shown host by yourself — a readback is a frame that is
  never presented.** `grab()` (and `wait_ready()`, `pick()`, `project()`, which need a frame)
  renders a frame of its own: `grabWindow()` emitted `afterFrameEnd` 0 times in 40 grabs.
  What that frame holds comes back when a PRESENTED frame ends — and with the display asleep
  Windows presents one frame and no more (§6). Twenty rebuilds with the view's frames
  withheld: 1.5 MB per rebuild without a readback (nothing is drawn, dedicated GPU memory
  does not move), 8.5 with one readback per rebuild, 26 without the release; on WARP 1.2 and
  6.2. So no steady path of the workspace — the pass, the health poll, a timer, a resize,
  the splitter — calls any of the four (a recording stand-in host and a source scan pin it);
  a picture for a file goes through `quick3d/offscreen.py`; a click that picks is a user's
  action, once. **The pipeline is NOT paced or held for a view that presents nothing** — that
  was built and taken out again: it fixed nothing and added a way to get stuck.
- **A memory soak takes no frame inside its measured loop.** One before, one after (they must
  be equal), and in between it waits on `health().frames_presented`. A soak that reads back
  every cycle measures the readback — this one did, twice, and a wrong rule was built on
  it. Judge it presenting AND with frames withheld (`scenario_soak(frames="withheld")`), and
  let the children present by timer (`run_gate` sets `QT_D3D_NO_VBLANK_THREAD=1` by default)
  so that no scenario depends on whether the box's display is awake.
- **Software rendering is chosen per window, not per process.**
  `QSG_RHI_PREFER_SOFTWARE_RENDERER=1` is read ONCE: set before the first Qt Quick window it
  selects WARP, set after it does nothing. `QQuickGraphicsConfiguration.setPreferSoftwareDevice(True)`
  on the window works at any time (`Quick3DHost(prefer_software=True)`; Qt's log then names
  "Microsoft Basic Render Driver"). That is the workspace's compatibility mode after a start
  that died (`src/open_garden_planner/ui/view3d/init_guard.py`).
- **Nothing overlays the view; its input is its own.** The view is a native window: a sibling
  widget is drawn UNDER it. Notices go into a strip above it or replace it. Mouse, wheel and
  keys go to the native window — `host.install_event_filter(watcher)` sees them; pass on every
  key you do not use and Qt's shortcut map keeps working with the keyboard in the 3D window
  (measured: Ctrl+Z, Alt+1).
- **Embedding does not cost the 2D side.** The main window stays a raster window
  (`surfaceType() == RasterSurface`); a pan step of the canvas beside the live view costs 1.04
  times what it costs alone (bound 1.3).
- **A pass is a posted event.** `QTimer.singleShot(0)` waits behind every timer that is due
  (the large bench plan: 5 % of the passes more than 228 ms late); a posted event at HIGH
  priority overtakes the scene's own queued `changed` and costs a second snapshot per edit.
  Normal priority.
- **Measure edit → frame inside the pass.** The readback is taken in a slot on the controller's
  `applied` signal. "Edit, `processEvents()`, grab" measures the 2D side's turn with it (56.6
  ms p95 instead of 17.6). `bench_small`, Split at 1600 × 900, RTX 4070: p50 15.2 / p95 20.6 ms;
  maximised at 5120 × 1369: 18.5 / 29.2; `bench_large`: 29.9 / 80.3 (the snapshot alone is 15
  ms there — a whole-plan snapshot is O(total vertices) even fully cached, so it runs on a
  real change only, never on a timer).
- **The first pass of a plan freezes the GUI thread for the sum of its items.** The workspace
  starts it from the PAINT of "Building the 3D view…", not from a timer that hopes the paint
  came first.
- **Dedicated GPU memory can be read without a counter.** `IDXGIAdapter3::QueryVideoMemoryInfo`
  through `ctypes` — `tests/integration/workspace_gate_measure.py`, `gpu_dedicated_mb()` — gives
  the calling process's usage on the adapter's local segment. With the release in place it
  rises ONCE, by about 90 MB over the first releases (289 → 378 MB), and is flat after; in a
  view that presents nothing it does not move at all.

Running the workspace's tiers:

```bash
# default tier (no GPU): the engine replaced at Workspace.engine_factory
venv/Scripts/python.exe -m pytest tests/integration/test_view3d_workspace.py \
    tests/integration/test_view3d_workspace_widget.py tests/integration/test_view3d_sync_controller.py
# render tier: the app's own main() in a child, on a throw-away settings store (about 9 minutes)
OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_view3d_workspace_render.py -s
# the frozen gate build (the product recipe plus one runtime hook), then its three scenarios
venv/Scripts/python.exe -m PyInstaller installer/workspace_gate.spec --noconfirm --distpath <dir> --workpath <dir>
OGP_RENDER3D=1 OGP_WORKSPACE_GATE_EXE=<dir>/OpenGardenPlannerGate/OpenGardenPlannerGate.exe \
    venv/Scripts/python.exe -m pytest tests/integration/test_view3d_workspace_render.py -k frozen
```

**Never script the product exe or `-m open_garden_planner` onto a plan.** A plan load writes
Recent Files and a clean close the window geometry, into the user's own settings. The gate's hook
(`tests/integration/workspace_gate_hook.py`) moves the store first and ends the process (exit
code 97) before a store under any other organisation exists.

**Not measured (L1.3):** where the 15 to 20 kB per destroyed Model go beyond Qt's own floor; why
dedicated GPU memory and committed memory step up ONCE with the first releases; the soak in a frozen
exe or on a CI runner (the workspace's render tier is not in CI's render job); time to photons
(edit latency ends at a finished readback); a change of the device pixel ratio in mid-session
and OS display scaling (manual checklist); the real map picker beside the 3D view (the
automated check uses its engine on a local page).

## 14. Looks, sky and wind on the engine (L1.4)

Concept: docs §8.29.4; decisions and the evidence table: the ADR-059 addendum "looks, sky and
the animation policy (L1.4)"; tests: docs §8.10.11; lessons: PF-L3D-05. The art-direction values
are `ogp-lush-cinematic` §3. What the ENGINE taught (RTX 4070, Direct3D 11; WARP on the same
machine):

- **A colour property is linearised with a polynomial, not the sRGB curve.** Qt Quick 3D turns a
  `color` property into linear light as `x·(x·(x·0.3053 + 0.6822) + 0.0125)`. From about 0.3 up
  the two agree; for dark colours they do not — sRGB code 5 is 0.0015 by the curve and 0.0005 to
  the engine (a flat ambient light on a white box, read in the un-tone-mapped top-down view).
  A colour you computed in linear light goes in as `QColor.fromRgbF(engine_srgb(linear))`
  (`quick3d/look.py`), as floats. Re-measure after a Qt upgrade.
- **A sky build is a fresh `Texture` with its own `ProceduralSkyTextureData` as its child**,
  every input set at `SkyTextureQualityLow` and the quality raised LAST (one generation). Only the
  Texture is ever destroyed — after the scene shows the new one — so a pair lives and dies
  together (a Texture loses its data when a data object it held earlier dies — the Qt texture trap the ground bake found, PF-L3D-05 item 4). A sequence
  A → B → C with a frame after each, then two frames after the old pairs are gone: the same sky,
  its disc at the solar azimuth (`test_a_sky_rebuilt_three_times_…`).
- **Medium sky quality is enough.** 1024 × 512 float texels (8 MB) against High's 2048 × 1024
  (32 MB): the GUI-thread generation 95 → 215 ms in a round-3 A/B on a quiet machine, every shot's
  mean luma within 0.02, the disc's bearing within 0.07°. In the 2026-10-19 boards (a fresh host
  per frame, other test runs sharing the CPU) one Medium build read 123–301 ms, median 171–201.
- **The light probe is the cost on a software adapter.** On WARP the generation itself is the
  same CPU work (145–340 ms at High), but the first frame after each new sky took 11.1 / 13.2 /
  12.3 s (the probe's filtering; 40–85 s on a CI runner, ADR-048), later frames 4 ms. So no sky
  on the software adapter, ever (`LookController(sky_light=False)`).
- **A retired sky needs no `releaseResources()`.** Twenty sun changes, each a new 8 MB sky and
  probe, frames presented and frames withheld: no growth per change in committed memory or in
  dedicated GPU memory (Theil–Sen over the second half: 0.0 presenting, 0.125 withheld, against
  the pre-registered 1.0 MB per change); the positive control — a `buildSky` that never destroys
  the old Texture — reads 8.2 MB per change. Unlike a destroyed Model (§13), it does not count towards the workspace's
  release policy.
- **A hidden window's `FrameAnimation` keeps running.** With the window hidden and the wind's
  clock running, `windTime` went on advancing (0.59 s of clock in 0.6 s hidden). The animation policy stops the clock when the
  pane hides; "hidden" stops nothing by itself. A stopped clock holds its value (the sway of that
  moment) — rest is `windTime = 0` (`Quick3DHost.rest_wind`).
- **Shadow bias is per backend and preset.** At the spike's bias 5, a lit wall grazed at n·l 0.33
  hatched at high and ultra on Direct3D 11 (pixel noise 1.15 % of its luma); bias 10 there
  (0.18 %, the dither's floor), 15 at low and medium; IoU unchanged.
- **Shadow IoU in a PERSPECTIVE view with the preset's cascades** (box 100 × 100 × 200 cm,
  azimuth 225°, the board's `--iou`; the L0 table above was orthographic without cascades):
  bench_small 960 × 540, GPU — low (1 cascade) 0.921 / 0.985 / 0.974, high (2) 0.976 / 0.986 /
  0.978 at 15° / 35° / 60°. At 640 × 360 the render tier holds all four presets ≥ 0.85 on the GPU
  and on WARP (min 0.919 on both; every cell in the ADR-059 addendum). The weakest cell is always low at 15°: one
  cascade over a 7.5 m shadow.
- **The frame rate to the display is capped by vsync** on a 60 Hz screen: count presented frames
  (`health().frames_presented`) and report a readback's time only as the cost of a finished
  frame, labelled as such. A `grab()` per frame measures the readback, not the frame.
- **MSAA quality is a sample count**: `SceneEnvironment.Medium` 2x, `High` 4x, `VeryHigh` 8x.
  2x does not resolve a picket fence (luma error 12.0 against a 2x-supersampled render; 4x 6.2;
  FXAA 20.0). On the RTX 4070 (bench_large, 1280 × 720, a new frame's readback) FXAA, 2x and 4x
  read 23–28, 23–30 and 24–32 ms — inside the run-to-run spread; on WARP under a shared CPU
  67–152, 96–147 and 107–199 ms. A truth view that must not depend on a preset pins its own
  quality (`Garden.qml`: the top-down view at 4x).
- **An animated view on a software adapter renders continuously**: the wind running on WARP
  drew 139 frames in 4 s at 1,351 % of one core (still: 1 frame, 18 %). Nothing animates in
  compatibility mode.
- **Committed memory grew while the wind ran** (FU-L14-2, L1.4): 2.1–2.6 MB per minute,
  linear over 6 minutes (21,594 frames), dedicated GPU memory flat; 0.8 with the QML engine's
  `collectGarbage()` every 5 s. Not isolated. **Re-measured 2026-10-19 (L1.9): not reproduced** — six alternating 4–5 min soaks, three with this `FrameAnimation` and three with a C++ `NumberAnimation` as the clock: 0.46–2.03 MB a minute overall, second-half slopes 0.0–1.51, the two clocks inside each other's spread. The clock change was reverted. But the final render tier the same day read 2.637 (bound 2.0): intermittent, not gone — `test_the_wind_running_for_two_minutes_leaves_nothing_behind` is a non-strict xfail citing #534.
- **A software adapter presents frames while the GPU's display sleeps**: with the display
  asleep the GPU host presented 0 frames (only readbacks measure there), the WARP host 30–60 in
  5 s. Say which a frame-rate number is.
- **Qt 6.11 exposes no "reduce motion" preference** (`QStyleHints`); the drift guard
  `test_qt_still_exposes_no_motion_preference` fails the day one appears.

## 15. Selection, picking in perspective, walk mode (L1.8)

Concept: docs §8.29.8; decisions and every number: ADR-060 addendum "selection, info card and
walk (L1.8)"; test patterns: docs §8.10.12; traps: PF-E3D-08. What the ENGINE taught:

- **`View3D.pick()` agrees with a ray caster of our own in the perspective view too.** 400
  seeded view positions per plan, from the orbit camera's own framing, against
  `src/open_garden_planner/core/scene3d/pick_oracle.py` (Möller–Trumbore over the records' posed
  meshes; a camera model of ours — eye, target, vertical field of view, no roll):
  `bench_small` 360 of 360 and `scene3d_edge_cases` 362 of 362 positions OFF the silhouette
  edges agree, the same numbers on the RTX 4070 and on WARP; ON an edge (the oracle's answer
  changes within 1.5 px) 36 of 40 and 38 of 38 — either answer is right there. 0.03 to 0.11 ms
  a pick with 98 Models. Judge picks off the edges only, and say how many were on one.
- **`View3D.pickAll()` is the whole chain, nearest first, one entry per MODEL.** An item of
  several parts is in it several times: keep first appearances per item id. Against the
  oracle's `cast_all`: 349 of 349 and 362 of 362 whole chains equal (34 of them two or more
  items deep, the longest four). `host.pick()` returns the first hit with the rest in
  `PickHit.behind` — ONE call and one probe frame for "the click falls through a locked item".
- **The ground and the sky are not pickable: nothing is `None`.** A click on the lawn clears
  the selection; a flat item (a lawn, a path — no height, no solid) cannot be selected from 3D.
- **A `QQuick3DGeometry` can be re-loaded in place while its Model lives.**
  `setVertexData` / `setIndexData` / `setBounds` / `update()` on the same object: 120
  selection changes in the real workspace re-loaded the ring 120 times into ONE geometry —
  no Model created, `BufferGeometry.uploads` unmoved (`quick3d/geometry.py`,
  `ReloadableGeometry`). §2's
  "one geometry per Model lifetime" is about a geometry that OUTLIVES its Model — the opposite
  case. Give it generous bounds: a vertex shader that moves vertices is culled by the bounds
  of the mesh it was handed.
- **A band of constant width on screen is a vertex shader, not a mesh.** `ring.vert`: every
  outline point three times at ONE position; `UV0.x` = band widths outward along the stored
  mitre normal, `UV0.y` = band widths up; one band width is `uFlat` cm in the orthographic view
  and `depth × uPerDepth` cm in perspective (`2·tan(fov/2) / view height × pixels`). Top-down
  every ring pixel lies within 3.82 px of OUR projection of the outline (bound 3·√2 + 1 =
  5.24) and the outline is covered 100 %.
- **"In front of everything" without a second pass: pull clip z towards the near plane —
  and ask the backend where that is.** `POSITION.z = mix(NEAR_CLIP_VALUE * POSITION.w,
  POSITION.z, 0.01)`. The first version scaled z (`POSITION.z *= 0.01`): right on Direct3D
  (clip z 0..1), and on OpenGL (−1..1) it moves the fragment to the MIDDLE of the depth range
  — behind the ground of the orthographic view: **0 ring pixels in every top-down frame**,
  1,548 with the fix (the perspective frame hid the bug: 587 px either way, because nearly
  all of a perspective scene lies in the far half of the range). Run anything that touches
  clip space with `QSG_RHI_BACKEND=opengl` once — it works on the Windows dev box too. Why in
  front at all: a WALL is built 30 cm thick on a 5 cm stroke; the depth-tested ring of its
  footprint, seen from above, shows 3.6 % of the outline (48 px of 1,548). Cost: the ring
  writes a near depth — a depth-reading post effect will see it.
- **An `Unshaded` custom material still goes through exposure and the tone curve** in the
  perspective view: the canvas blue (0, 120, 215), handed over in linear light, arrives as
  rgb(0, 142, 226) — hue 202.3° against 206.5°. A look that changes the exposure changes the
  ring's brightness.
- **A shader is compiled when something first uses it.** The ring's two shaders compile with
  the first selection — so the frozen `--selftest` selects one swatch (`selftest.SELECTED`)
  and its judge looks for the band; without that a broken `ring.vert` ships and the first
  user to click finds it.
- **Whatever resizes the native view between two clicks takes the second click's aim.** An
  info card that appeared below the view with the selection took 152 px from it; the vertical
  field of view is fixed, so the picture was re-scaled, and a Ctrl+click on the neighbour of
  the item just selected met the lawn and CLEARED the selection. A resize is also a new
  swapchain, and a host between two sizes answers `HostStateError`. Reserve the room
  (`View3DCardSlot`: one height, card or no card; `QSizePolicy.setRetainSizeWhenHidden` for a
  control that comes and goes) and pin the engine widget's geometry in a test. What found
  it: `QTest`'s own warning "Mouse event at … occurs outside target window" in the judge's
  message list.
- **Real input in a test.** `QTest.mouseClick(host._view, button, modifiers, QPoint)` and
  `QTest.keyPress` / `keyRelease(host._view, key)` reach the event filters as a user's do; a
  drag needs its buttons said — `QCoreApplication.sendEvent(view, QMouseEvent(...))`.
- **A key in the embedded view meets the MAIN window's shortcuts first** (fix round 1,
  measured on Windows with the real main window). The `QQuickView` sits in a window
  container, so the main window stays the active window and its window shortcuts are live.
  Qt sends `ShortcutOverride` to the view's window (and then to its active focus item, if it
  has one) BEFORE it tries a shortcut: an event filter on the view that accepts it
  (`event.accept()`, return True) owns the key — the `KeyPress` follows. A filter that takes
  only `KeyPress` lost S to Snap to Grid. To give the view the keyboard,
  `QQuickView.requestActivate()` (or the container's `setFocus()`): afterwards
  `QGuiApplication.focusWindow()` is the view and the container is the focus widget; the
  previous widget's `activateWindow()` + `setFocus()` gives it back. Under the offscreen
  platform the focus window changes at once but its focus events come later — let the loop
  run before the first key.
- **Near plane 5 cm, walk field of view 60°.** The farthest corner of the near rectangle is
  6.94 cm from the eye at 4:3 (`walk.near_plane_reach_cm`; below the walker's 22.5 cm up to
  an aspect of 7:1). Pressed against a 180 cm wall and into an inside corner of two, all
  round in 15° steps, level and ±35°, at 165 and 110 cm: 288 frames, 0 pixels of the marker
  behind the wall. Control: an eye 2 cm in front of the masonry sees 114,560 — back faces
  are culled, so from inside a wall the camera looks out.
- **Walk collision is with what is DRAWN.** The builders make a wall 30 cm thick with a 38 cm
  coping whatever stroke the plan drew; the walker's world is the footprints PLUS the
  plan-view edges of the built meshes between step height (25 cm) and headroom (200 cm).

Running the story's tiers:

```bash
# default tier (no GPU)
venv/Scripts/python.exe -m pytest tests/unit/test_scene3d_walk.py tests/unit/test_scene3d_selection.py \
    tests/unit/test_scene3d_pick_oracle.py tests/integration/test_view3d_selection_workspace.py \
    tests/integration/test_view3d_selection_walk.py tests/integration/test_view3d_walk_bench.py
# render tier, on the GPU and on WARP (about two minutes each)
OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_view3d_selection_render.py -s
OGP_RENDER3D=1 QSG_RHI_PREFER_SOFTWARE_RENDERER=1 venv/Scripts/python.exe -m pytest \
    tests/integration/test_view3d_selection_render.py -s
```

**Not measured (L1.8):** a device pixel ratio other than 1 through the real window (the click
is handed over in logical pixels; pinned on the stand-in host only); the ring under L1.4's
looks and post effects; the pick's cost on the large bench plan; walk mode in a frozen exe;
the whole render file on OpenGL (one row runs there: the ring's depth); pointer capture.

## 16. Analyze in 3D on the engine (L2)

Concept: docs §8.29.10; decisions: ADR-063 (and its review addendum); lessons: PF-L3D-06,
PF-L3D-07, PF-L3D-08. What the ENGINE taught (RTX 4070, Direct3D 11; WARP and OpenGL on
the same machine, 2026-10-24):

- **An Unshaded material goes through the exposure and the tone curve.** Its colour is
  emitted, then multiplied by the mood's exposure (2.4 at night): an over-blended
  "shadow" colour LIGHTENED the night garden by up to 44 grey levels. A shadow on the
  ground must MULTIPLY the frame — `sourceBlend: DstColor`, `destinationBlend: Zero`
  (the shade layer; measured darker in every mood, top-down the product exactly) — and
  an overlay colour that must read the same in every mood is divided by the exposure in
  its shader (`overlay.frag`, `uExposure`). The filmic curve still bends a saturated
  hue: the arcs are built in pre-compensated colours (`ARC_ENGINE_RGBA`).
- **A hidden or blended Model drops out of the shadow map.** `visible: false` and any
  opacity took the cut roof's and the faded tree's shadows off the ground. A fragment
  `discard` does not: the shadow pass does not run it — a screen door (`screen.frag`:
  `screenDoor(FRAGCOORD.xy) >= uOpacity`, a 4 × 4 Bayer dither) keeps the part an opaque
  caster; measured unchanged ground outside the footprints on D3D11 (GPU, WARP) and
  OpenGL. `FRAGCOORD` works in a custom material's fragment shader on all three.
  **Measured limit:** the DEPTH pass (the depth texture SSAO reads, Medium preset and
  up) does not run the discard either — a cut roof left a ghost of itself. Collapse the
  part there: `#if QSSG_ENABLE_DEPTH_PASS` / `VERTEX = vec3(0.0)` (or `POSITION =
  vec4(0.0)` after a custom POSITION) — the shadow pass does not define the macro, so
  the shadow stays (all three backends). `depthDrawMode: NeverDepthDraw` is NOT the
  tool: it dropped the part from the shadow pass and kept the AO ghost.
- **A Model can switch materials by binding** — `materials: fade < 1.0 ? [screen] : [look]`
  with both declared inside the Model: the look material stays bit-identical while
  nothing fades (the L1 frames did not move).

- **A blended CustomMaterial blends ALPHA too — keep it.** `sourceBlend: SrcAlpha` /
  `destinationBlend: OneMinusSrcAlpha` alone leave the frame's alpha at 1 − a(1 − a) and
  the View3D's texture lets the window's white through: black at a = 0.5 read 64 grey
  levels too bright, the drape brightened the meadow. `sourceAlphaBlend: Zero` /
  `destinationAlphaBlend: One` keep it at 1 (black at 0.5 = half the ground, exactly).
  PrincipledMaterial's own blending (glass) needs nothing.
- **An overlay is a Model of the scene, re-loaded in place.** The drape and the lines
  each live in ONE Model declared in `Garden.qml` with a `ReloadableGeometry` — the
  selection ring's pattern; a sun step, a sweep step or a probe creates and destroys
  nothing (`ReloadableGeometry.created` moves once per layer and host). Their shaders
  (`overlay.vert` / `overlay.frag`) compile only when an overlay is SHOWN: the frozen
  `--selftest` shows a drape patch and a lines patch for that reason.
- **An Unshaded material with a custom vertex shader passes vertex colour through a
  VARYING** (`vColor = COLOR`, as `foliage.vert`): the lines' magenta came through
  exactly — (171, 9, 90) for the pin's linear colour in the truth view.
- **Fading a part: a property per Model, not `Node.opacity`.** Each part Model has
  `fade` (1 = as it is); below 1 a vc or roof part switches to the screen-door material
  and foliage, grass and water discard in their own shaders — never a blend (above).
  `pickable: fade >= 1.0` — a faded occluder is clicked through. `listParts()` reports
  `drawn`, the share of pixels the ACTIVE material draws.
- **A binding cuts a kind of part for every Model, born later included.**
  `materials: root.roofsHidden || fade < 1.0 ? [roofScreen] : [roofLook]` with
  `uOpacity: root.roofsHidden ? 0.0 : fade`: no iteration over Models, a roof built while
  Cutaway is on is born cut, and it still casts (`tests/ui/test_view3d_analysis_host.py`).
  The vc walls bind `cullMode` to `roofsHidden` (their inner faces show).
- **The drape lies 1.5 cm above the ground** (the tiles and the meadow's frame at 0): a 24-bit depth
  buffer at a 5 cm near plane resolves about 0.3 cm at 50 m and 1.2 cm at 100 m.

Running the story's tiers:

```bash
# default tier (no GPU)
venv/Scripts/python.exe -m pytest tests/unit/test_scene3d_drape.py tests/unit/test_scene3d_sun_path.py \
    tests/unit/test_scene3d_xray.py tests/ui/test_view3d_analysis_host.py tests/integration/test_view3d_analysis.py
# render tier, on the GPU, on WARP and on OpenGL (about 15 s each)
OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_view3d_analysis_render.py -n 0
OGP_RENDER3D=1 QSG_RHI_PREFER_SOFTWARE_RENDERER=1 venv/Scripts/python.exe -m pytest \
    tests/integration/test_view3d_analysis_render.py -n 0
OGP_RENDER3D=1 QSG_RHI_BACKEND=opengl venv/Scripts/python.exe -m pytest \
    tests/integration/test_view3d_analysis_render.py -n 0
```

**Not measured (L2):** the overlays' cost per frame on the large bench plan; the X-ray's
GUI-thread cost on a large selection of a dense plan (bounded to 16 selected items and
box-culled, not timed); the drape under the looks' post effects at grazing angles.

## 17. The built world complete on the engine (L4)

Concept: docs §8.29.12; decisions: ADR-065; lessons: PF-L3D-11, PF-L3D-12. Measured on the
RTX 4070 (Direct3D 11), 2026-10-26:

- **Relief on the painted ground is a `ground_detail` part** (`MeshPart.ground_detail`): a
  Model with `groundDetail: true`, never pickable, no shadow, and the item stays painted by the
  bake. The "ground alone" gates take it off (`ground_bake_render_driver._without_relief`):
  they judge the tiles, and stones, water and blades stand on them.
- **Lawn blades are one Model per lawn**, built at every preset and shown by the root's
  `lawnBlades` (re-applied to `lawn_blades` parts when it changes): a preset step creates
  and destroys nothing. They are the grass material, so the wind sways them.
- **Detail normals are a material switch, not a texture:** `materials: root.detailNormals > 0.0
  ? [tileDetail] : [tileFlat]` on the ground tile; `tileDetail` is `ground.frag` with the tile's
  own `Texture` as a `TextureInput` (one Texture per tile for life, PF-L3D-04, unchanged).
- **The scene file's look defaults ARE `NEUTRAL_DAY`** (High): `lawnBlades: true`,
  `detailNormals: 3.0`, inside the look block (`test_quick3d_qml.py` holds them to the mapping).

**Not measured (L4):** the blades' fill-rate cost at Ultra on a weak GPU (they are bounded at
60,000 per plan, 180,000 triangles); the detail normals at grazing angles under the looks'
post effects.
