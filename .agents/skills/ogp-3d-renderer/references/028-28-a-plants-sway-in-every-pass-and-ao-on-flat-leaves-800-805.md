## 28. A plant's sway in every pass, a material swapped while the clock runs, and ambient occlusion on flat leaves (#800, #805)

Concept: docs §8.29.4; decisions and the evidence table: the ADR-059 addendum "the wind that
shows, and the leaves' stripes"; lessons PF-L3D-32, PF-L3D-33; the values `ogp-lush-cinematic`
reference 018. Measured on the dev box (RTX 4070, Direct3D 11, PyQt6-Qt6 6.12.0, 2026-11-10),
the family garden through `Quick3DHost.capture` (the tour's path, the clock set per picture);
what Qt's binaries say is read from the strings of `Qt6Quick3DRuntimeRender.dll` and says so.

- **A CustomMaterial's vertex `MAIN` runs in the shadow pass**, so a displacement there moves
  the shadow with the part (a crown's shadow on the lawn changed 5,777 / 7,015 px between two
  clock values in a 20 × wind). `QSSG_ENABLE_ORTHO_SHADOW_PASS` is defined in a directional
  light's (cascaded) shadow pass: a control that wraps the sway in `#if
  !QSSG_ENABLE_ORTHO_SHADOW_PASS` left the ground nearly still (872 / 1,661 px, the leaf tips
  that swung past the mask) while the crowns moved — the way to prove a test of "the shadow
  follows" can fail.
- **`MODEL_MATRIX[3].xyz` is where the Model stands; `v * mat3(MODEL_MATRIX)` turns a vector in
  the garden's axes into the Model's own** (GLSL row-vector product = the transpose; the host
  poses with position and yaw only, no scale). A wind in world axes is applied in the local
  `VERTEX` that way, and a plant turned by 90° sways the same way as an unturned one
  (`test_scene3d_wind.py` states the same in numpy).
- **A `materials` binding that swaps a PrincipledMaterial for a CustomMaterial while the clock
  runs is invisible** when the custom one hands `COLOR` through its own varying and uses the
  principled roughness and specular (`plant_sway.vert` + `built_snow.frag`, the #687 path): a
  QML copy whose sway is multiplied by 0, rest (principled) against clock 5 s (custom), 1080p:
  0 levels on low, high and ultra, one pixel 1 level on medium. Keep the swap behind the clock
  (`root.windTime > 0`) and every still frame stays the principled look by construction; the
  shader warmer draws the custom material once so the first windy frame compiles nothing new.
- **Qt's SSAO bands a flat surface seen at a slant.** Its normal faces the camera (reference
  24), so a flat micro-leaf occludes itself in bands 2–4 px apart along its depth gradient.
  The shadow bias (10 → 40 cm: stripe share 0.326 → 0.320) and a fitted map (0.330) do not
  touch it; AO off (0.164) and Low (no AO) never show it. `aoBias` 1 cm: 0.184 with a box
  caster's contact unchanged; 2 cm: 0.175 but the lit-side contact halved. `aoDither: true`
  turned the bands into per-pixel noise (0.545); `aoSoftness` 90: 0.212.
- **A custom fragment can only scale the AO, not read it.** The generated shader multiplies
  `qt_aoFactor *= qt_customOcclusionAmount` (`OCCLUSION_AMOUNT` in a custom `MAIN`) and defines
  `QSSG_ENABLE_SSAO` where the pass runs; the SSAO value itself
  (`qt_screenSpaceAmbientOcclusionFactor()`) is Qt's internal — a per-material "less AO" needs
  that value and is not offered. A fix that must hold for one material is a scene-wide AO
  setting.
- **Shader clocks wrap: give every frequency whole cycles per wrap.** `Garden.qml` wraps
  `windTime` from 3602 s to 2 s (#689); a term `sin(w t)` jumps at the wrap unless
  `w = 2π n / 3600` (`swayHourly`). Float32 keeps `t` to 0.24 ms near 3600 s — a 5 Hz flutter
  steps by 0.008 rad, invisible.
- **Cost.** One more 40-odd-operation function per vertex in every pass (main, depth, AO
  depth, each cascade) on the family garden's 598,582 LOD0 vertices: 1080p captures with the
  wind running, minimum of 12 then 16 strictly alternating against a second host on the base
  QML in one process (a shared GPU): +0.1 to +4.0 ms per preset, high once −4.8 — inside the
  run-to-run spread. The frame is one uniform vector per Model (no vertex attribute; stride
  stays 48 B).
