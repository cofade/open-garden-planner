## 22. Post effects in the environment: user effects, the glow chain, the photo blur (#743, #744)

Concept: docs §8.29.15; decisions and numbers: ADR-072 addendum "photo mode's own depth of field";
lessons: PF-E3D-21, PF-E3D-27. Measured on the dev box (RTX 4070, Direct3D 11; WARP where named),
2026-11-09, PyQt6 / PyQt6-Qt6 6.12.0, with small QML probes and the product's scene:

- **A user `Effect` in an `ExtendedSceneEnvironment`'s `effects` runs BEFORE Qt's scene effect**:
  on the linear colour, before exposure, tone mapping, glow, the adjustments, the colour table and
  the vignette. A pass writing a constant 0.25 came out `#acacac` with filmic tone mapping,
  `#404040` with `TonemapModeNone`, `#d9d9d9` at exposure 2. Blur there is blur in linear light
  (a blurred picture's mean rose 1.3 levels against the sharp one), and a blurred highlight still
  glows. Qt's own effects (SSGI, SSR, depth of field, the scene effect) are not in the `effects`
  list: a `QQmlListReference` of it holds only the user's.
- **With glow on, two effects ahead of the scene effect break the chain** (PF-E3D-21). Cube scene,
  one fresh process per row: glow + SSR + Qt's depth of field crashed at the first frame; two
  pass-through user effects + glow drew grey where the cube was; SSR + one user effect + glow drew
  black, or crashed when SSR came on after the first frame; any pair without glow, and any single
  effect with glow (one with three passes and two buffers included), drew right. Reproducer:
  `docs/09-architecture-decisions/adr-048-evidence/qt-effect-chain-glow/`.
- **A `Shader`'s plain relative path inside an Effect component resolves against the file that
  INSTANTIATES the component**, not the component's own: the bench fixture in `tests/integration`
  read no shader ("Failed to read shader code from tests/integration/photoblur_layer.frag") until
  `PhotoBlur.qml` wrapped each path in `Qt.resolvedUrl`. Garden.qml worked either way only because
  it sits beside the component.
- **Pass mechanics that hold:** `BufferInput { sampler: "name" }` without a buffer binds the
  effect's input in any pass, also after an earlier pass bound `INPUT` to a buffer; one `Buffer`
  written by a pass after the pass before read it (the photo blur's layer buffer, four times) gave
  the same picture as a buffer of its own; `SetUniformValue` on an Effect property sets it for one
  pass. `OUTPUT_SIZE` is the pass's output size: `sizeMultiplier: 1.0` is the view's, or the
  capture view's explicit size, so a sigma of `share x OUTPUT_SIZE.y` is the same share of every
  picture (a thin line's blurred width 0.0139 of the height at 360 px, 0.0153 at 4K).
- **`DEPTH_TEXTURE` holds the GL-style depth mapped to 0..1 on Direct3D 11 too**: linear depth is
  `2nf / (f + n - (2d - 1)(f - n))` with `CAMERA_PROPERTIES` (n, f), as Qt's own depth-of-field
  shader reads it; a focus on a picked crown kept 0.97 of its 60 px tile at the strongest blur. The
  depth pass takes ONE sample while the colour is multisampled: a silhouette pixel's colour is
  partly its neighbour's (PF-E3D-27).
- **Qt's ambient occlusion makes a small picture brighter, and its radius does not fix it.** Family
  garden, medium, sun 38°: a 360 px picture read +4.75 luma (mean) and up to +12.3 in a 40-row band
  against 1080p; 720 px +1.4 / +4.5; 4K -0.1 / -4.6..+2.5 (with #733's AO distance scale). AO off:
  0.25 mean, 1.0 worst band; glow on or off moved it by 0.15. Scaling `aoDistance` by 1080/height
  below 1080p moved the 360 px mean to +4.86. `aoSoftness` is the pixel-sized term: at 360 px,
  softness 45 / 25 / 20 / 15 read +4.75 / +0.5 / -1.33 / -3.51 mean, but a 40-row band stayed 8.9
  brighter at 25; at 1080p, softness 0 read 14.9 darker than 45.
- **Cost of the photo blur** (five RGBA16F buffers at the picture's size, nine passes; A/B
  interleaved with other GPU work on the machine, so ranges): a 1280 x 720 frame, blur off / on,
  median of 60 grabs: low 8.0 / 10.2 ms, medium 9.4 / 11.0, high 8.9 / 7.3, Ultra 3.1-4.2 /
  3.5-5.7 (reflections stand down under the blur). A 4K capture: Ultra 1691 / 1692 ms, medium
  781 / 1245 ms in one run. About 330 MB of buffers during a 4K picture, given back when the capture
  view rests.
- **Traps met on the way, already in this skill:** `show()` then `grabWindow()` before the first
  expose killed every probe process (reference 6); a pick right after a capture, with no frame of
  the view in between, picked another point (the engine picks in the frame it drew last, reference
  6): grab the view first. With the machine's commit charge near its limit (other processes), a 4K
  Ultra capture aborted once in two runs and the HLSL compiler reported `E_OUTOFMEMORY`
  (0x8007000e): check free memory before blaming a shader.
