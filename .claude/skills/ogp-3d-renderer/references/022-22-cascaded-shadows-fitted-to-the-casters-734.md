## 22. Cascaded shadows: what Qt 6.12 fits, filters and stores (#734)

Read in the Qt 6.12.0 sources (`runtimerender/rendererimpl/qssgrenderhelpers.cpp`:
`setupCascadingCamerasForShadowMap`, `computeShadowCameraFromFrustum`;
`runtimerender/res/effectlib/shadowMapping.glsllib`; `runtimerender/qssgrendershadowmap.cpp`)
and measured with the board's `--stairs` probe (bench_small, RTX 4070, Direct3D 11, 1080p,
2026-11-09). How to measure: `ogp-lush-cinematic` reference 13.

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
  set the last cascade.
- **`false` fits x and y of each cascade to the shadow CASTERS' box clipped to the slice**
  (plus one texel each side), z to the slice's receivers; no snapping. In this scene every
  caster is a record's part (`MeshPart.casts_shadow`): the meadow, the ground tiles, water,
  bulbs, particles and the ring cast nothing, so the map spans the plan's own items — about
  1 cm texels on a 24 m plan at every preset, at no cost (the same atlas pages). A cascade
  whose slice holds no caster has no map (nothing to shadow there).
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
  shaded face lit, the default framing), 1 % fitted to the casters.

What decided #734 (one setting at a time, High, the board's default framing, the panel's
edge 20–40 m out, spread across it in px at 1080p; streaks: the picket fence's 5.9° shadow,
one-pitch-filtered spread over the shadow's contrast):

| Setting (High) | 15.2° | 5.9° | streaks | cost |
|---|---|---|---|---|
| as shipped (locked, `shadowMapFar` ≥ 9000) | 2.24 | 6.23 | 0.49 | — |
| reach = plan corners + 10 m (no 9000 floor) | 1.68 | 5.70 | — | none; the golden-hour camera's 10–20 m band got WORSE (1.08 → 2.04 px): it moved into the coarser last cascade |
| `pcfFactor` 4 / 6 | 1.89 / 1.56 | 2.91 / 1.97 | streaks smeared into bands | none; every edge softer |
| 4096 map | 0.99 | 1.70 | 0.29 | 4 × the shadow passes' texels and memory |
| `csmSplit2` 0.45 | 1.30 | 3.38 | 0.76 | none; worse near |
| **unlocked (fitted to the casters)** | **0.32** | **1.40** | **0.12** | none measurable (ADR-059 addendum, #734) |

Ultra as shipped: 0.45 / 1.33 / 0.30; fitted 0.30 / 1.47 / 0.10. What is left at 5.9° is the
pixel dither above, not texels.
