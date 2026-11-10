## 23. Cascaded shadows: what Qt 6.12 fits, filters and stores, and why only a still frame is fitted (#734)

Read in the Qt 6.12.0 sources (`runtimerender/rendererimpl/qssgrenderhelpers.cpp`:
`setupCascadingCamerasForShadowMap`, `computeShadowCameraFromFrustum`;
`runtimerender/res/effectlib/shadowMapping.glsllib`; `runtimerender/qssgrendershadowmap.cpp`)
and measured with the board's `--stairs` probe and through the product's capture path
(RTX 4070, Direct3D 11, 1080p, 2026-11-09/10). How to measure: `ogp-lush-cinematic`
reference 13.

- **Splits are fractions of `[clipNear, min(shadowMapFar, camera clipFar)]`, linear in view
  depth.** Defaults `csmSplit1/2/3` 0.1 / 0.25 / 0.5; `csmNumSplits` n gives n + 1 cascades;
  each cascade's slice runs `csmBlendRatio` (of the range) past its split, and the shader
  blends over `shadowMapFar × csmBlendRatio` after each split. Beyond the last split a
  fragment is lit (a hard end, no fade).
- **`lockShadowmapTexels: true` sizes every cascade by the BOUNDING SPHERE of its whole
  frustum slice** (`diam = 2 × (pcfRadius + radius)`, centre snapped to a texel) — whatever
  casts or receives. At the board's golden-hour camera (46° vertical, 16:9) with
  `shadowMapFar` 9000: High (2048 texels, 3 cascades) 1.32 / 2.45 / **8.29 cm** per texel;
  Ultra (4096, 4) 0.66 / 1.23 / 2.2 / 3.96 cm. The 9000 cm floor of the reach, not the plan,
  set the last cascade. The sphere's size does not change as the camera turns and its centre
  snaps to whole texels, so an edge holds still while the camera moves.
- **`false` fits x and y of each cascade to the shadow CASTERS' box clipped to the slice**
  (plus one texel each side), z to the slice's receivers; no snapping. In this scene every
  caster is a record's part (`MeshPart.casts_shadow`): the meadow, the ground tiles, water,
  bulbs, particles and the ring cast nothing, so the map spans the plan's own items — about
  1 cm texels on a 24 m plan at every preset (a 50 m plan about 2.5 cm), the same atlas
  pages. A cascade whose slice holds no caster has no map (nothing to shadow there).
- **A fitted map follows the camera.** The box is clipped to the camera's slices, so it
  changes size and place with every camera move, and the texel grid slides under the
  casters. Orbiting the family garden through the capture path (hero camera, golden hour,
  0.5° a frame, the fence's edge averaged over 30 cm): locked 0.16 / 0.17 px a frame at
  0–10 / 10–20 m, fitted 0.69 / 0.38; one fitted cascade (`csmNumSplits` 0) 0.32 / 0.39. A lone panel
  in the far cascade did NOT show it (its box hardly changes): the synthetic orbit needs a
  tall caster at each plan corner (locked 0.079 / 0.094 px, fitted 0.21 / 0.15 at 0–10 /
  10–20 m, High).
- **`pcfFactor` is a radius in SCENE UNITS of light space, the same for every cascade:**
  `radiusUV = pcfFactor * dimensionsInverted.xy`, and `dimensionsInverted.x = 0.5 /
  |inverse(viewProjection) · (1, 0, 0, 0)|` = 1 / the cascade's width. The day's 2 cm is a
  quarter of an 8.3 cm texel: it filters nothing there. `shadowBias` is centimetres of light
  depth the same way; a directional light's shader has no slope term.
- **The PCF kernel turns per screen PIXEL** (`randomRotation2D(gl_FragCoord.xy)`, a 64 px blue
  noise): a moving camera re-dithers every soft edge. That is the floor of any frame-to-frame
  comparison — an orbit of 0.5° a frame, 20–40 m out: p95 0.21 px at a 15.2° sun, 0.98 px at
  5.9°; averaged over 30 cm along the edge 0.06 / 0.19–0.23 px (`probes.edge_swim`).
- **The atlas** gives each cascade a page of `shadowMapRes`; the format is R16F unless
  `use32BitShadowmap` (a 32-bit map changed nothing visible on the family garden at golden
  hour or sunset).
- **The ground does not cast, so a caster's FOOT is quantised:** a ground point whose texel
  centre misses the caster's bottom edge reads an empty texel — lit. At a low sun the foot of
  every caster shows lit teeth one texel tall in light space, `texel / sin(elevation)` long on
  the ground: 81 cm for High's 8.3 cm texel at 5.9° (34 % of a line 15 cm out from a panel's
  shaded face lit, the default framing), 1–2 % fitted to the casters.

**What the product does.** `Garden.qml`: `lockShadowmapTexels: root.topDown ||
!root.fittedShadows`. `Quick3DHost.capture(..., fitted_shadows=False)` — the default is the
view's locked fit, so a capture at the view's size is the view to the level (the self-test's
check: a fitted default failed it by 24 levels). The still pictures ask by name:
`WorkspaceCaptureCoordinator.write_photo` (a photo), `agent_picture` (`render_3d_view`) and the
frames of a `HeldCamera` tour; an orbit, a flight and the live view stay locked. The flag is set
for the capture's own frame and put back in the capture's `finally`, like its AO scale; the
view after a fitted capture is the view to the level. A fitted still differs from the view
along shadow edges only (bench plan, 38°, medium, 640 × 360: 6.0 % of pixels more than 8
levels apart, mean 1.32). `set_fitted_shadows`, `render_records(fitted_shadows=)` and the
board's `--photo-shadows` render a picture's fit outside a capture.

**A held camera's time-lapse.** The sun moves every frame, so the light space turns under
either fit: the locked sphere's grid turns with it, at its coarser texels. The board's
`--stairs` time-lapse (the orbit's scene, the golden-hour camera held, the sun stepping
0.4° / 0.55° a frame, each frame traced against its own sun's edge): locked 0.336 / 0.682 px
a frame at 0–10 / 10–20 m (Ultra 0.175 / 0.321), fitted 0.265 / 0.517 (Ultra 0.167 / 0.298);
24 frames from golden hour to sunset: locked 0.66 / 0.79, fitted 0.35 / 0.37. So a held
camera's frames are fitted; the render gate keeps that reason on High.

**Cost.** Fitting changes which texels a cascade covers, not the passes or the pages.
Family garden, golden hour, fitted and locked captures strictly alternating in one process
(minimum of 12 each; the GPU was shared, which only adds time): 1920 × 1080 fitted − locked
−0.7 / +2.3 / −0.6 / +2.1 ms on low / medium / high / ultra (17.8 / 21.0 / 25.3 / 40.3 ms
locked); 3840 × 2160 on High +2.9 ms minimum, +0.7 ms median (12 pairs). Nothing beyond
the noise. A board readback A/B on a shared GPU swung 3 × between rounds: interleave
within one process and read minima instead.

What decided #734 (one setting at a time, High, the board's default framing, the panel's
edge 20–40 m out, spread across it in px at 1080p; streaks: the picket fence's 5.9° shadow,
one-pitch-filtered spread over the shadow's contrast):

| Setting (High) | 15.2° | 5.9° | streaks | cost / catch |
|---|---|---|---|---|
| as shipped (locked, `shadowMapFar` ≥ 9000) — the view | 2.24 | 6.23 | 0.49 | — |
| reach = plan corners + 10 m (no 9000 floor) | 1.68 | 5.70 | — | none; the golden-hour camera's 10–20 m band got WORSE (1.08 → 2.04 px): it moved into the coarser last cascade |
| `pcfFactor` 4 / 6 | 1.89 / 1.56 | 2.91 / 1.97 | streaks smeared into bands | none; every edge softer |
| 4096 map | 0.99 | 1.70 | 0.29 | 4 × the shadow passes' texels and memory |
| `csmSplit2` 0.45 | 1.30 | 3.38 | 0.76 | none; worse near |
| **fitted to the casters — a still frame only** | **0.32** | **1.40** | **0.12** | see Cost; crawls with a moving camera |

Ultra as shipped: 0.45 / 1.33 / 0.30; fitted 0.30 / 1.47 / 0.10. What is left at 5.9° is the
pixel dither above, not texels.
