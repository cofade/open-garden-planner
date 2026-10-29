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

