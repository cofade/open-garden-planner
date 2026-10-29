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

