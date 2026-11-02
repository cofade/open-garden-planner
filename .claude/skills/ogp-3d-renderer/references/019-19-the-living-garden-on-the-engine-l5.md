## 19. The living garden on the engine (L5, #389)

Concept: docs §8.29.13; decisions and numbers: ADR-070; tests: §8.10.16; lesson: PF-L3D-18.
What the ENGINE taught (RTX 4070, Direct3D 11, 2026-11-02):

- **Particles need no particle module.** A `CustomMaterial` vertex shader places a quad from
  per-vertex seeds and `windTime` (`precipitation.vert`, `ambient.vert`); `CAMERA_POSITION`,
  `CAMERA_DIRECTION` and `VIEWPROJECTION_MATRIX` billboard it; a particle whose kind is off is
  written to `POSITION = vec4(0, 0, 2, 1)` — beyond the far plane on every backend, so it is
  clipped. Two Models, two `ReloadableGeometry`s, loaded once; the buffers are the package's
  one vertex layout with the slots holding seeds (`core/scene3d/particles.py`). An Unshaded
  material still goes through exposure and tone curve: a particle multiplied by the look's
  light (`particleLight`) sits in the frame like a lit surface; a firefly's colour above the
  glow threshold blooms.
- **The NORMAL attribute arrives raw** in a custom vertex shader (not normalised): the ambient
  buffer carries (phase, speed, radius in cm) in it and the shaders read them back.
- **`POINT_LIGHT` with `LIGHT_ATTENUATION` compiles in a shaded `CustomMaterial`** next to
  `DIRECTIONAL_LIGHT` (foliage, foliage door, lawn): without it a custom leaf shader would
  light point lights through Qt's default, not with its translucency.
- **Six point lights made once** (`Component.createObject` at load — the scene forbids a
  `Repeater3D`): only filled slots are visible, and only after dusk; `quadraticFade` 3.5 with
  brightness 7 gave a lantern a pool of a few metres at night exposure 2.4 (1.0 lit the whole
  lawn). The 3D review then found the lantern heads white with dark cores: the light stood
  INSIDE the bulb's ball (a closed, culled sphere lit from within renders dark) and 4–11 cm
  from glass. Fix: the light 3 cm under the lantern, `constantFade` 4 with brightness 9.4
  (same pool at 1.5 m, near field a third), and the bulb's glow particle drawn 6 cm towards
  `CAMERA_POSITION` — a depth-tested quad through a ball's centre is half hidden by the
  ball. A pane round a lamp is still lit at the near-field strength (the constant fade is a
  floor, so moving the light does not help): × night exposure 2.4 through Filmic it drew
  cream (hue ~50°) whatever its tint — the lantern lost its pane, and the glow is a small
  hot centre in a warm halo (1.0, 0.48, 0.13) kept under the shoulder.
- **`ProceduralSkyTextureData` with `sunEnergy` 0 draws a BLACK sun.** The disc and its
  falloff are blended towards sun colour × sun energy, so a "hidden" sun is a black disc with
  a dark halo (luma 0 against 150, measured under overcast). Hide a sun by its COLOUR (the
  horizon's), never by its energy. A SET sun (below 0.5°) is hidden by MATCHING the sky: the
  horizon's colour at the sky's own `skyEnergy` — energy 0 drew a black disc through all of
  twilight (luma 0 against 170-182 at +0.4°, in every weather; the board's dusk camera hid it
  behind a tree for three reviews, #695), and energy 1 with the horizon's colour leaves a
  23-luma glow at -3° and a lit spot at night. Matched: dip ≤ 1.6 luma, no halo, no glow.
- **Never cut a quad per vertex.** Sending some corners of a quad to `vec4(0, 0, 2, 1)` (beyond
  the far plane) and not the others draws a torn sliver towards the screen centre. Collapse a
  particle as a whole (every corner, decided by its anchor) or scale its size to 0.
- **A particle share is a count, not an alpha.** Blending happens in linear HDR before the
  tone curve: a quad at 9 % opacity lifted a dark lawn by 39 luma. Collapse the particles
  whose seed `fract(phase * 7.919)` lies above the share instead.
- **Cost of a weather** (bench_small, 1280 × 720, Medium, a finished frame read back,
  interleaved 40 rounds): no L5 7.02 ms, clear with life 7.06, snow 7.15, rain 7.28. Blocks of
  seconds per look drifted 24 % with nothing changed — interleave (PF-L3D-18).
- **The first frame of the bench plan came ~3 s after its update requests** under the render
  tier's environment (pipelines + the sky's probe). "No frame for a second" before it is not
  idle (PF-L3D-18). With reduced motion and rain: 0 frames over 2.5 s after it; animated: ~60/s.
- **A presented-frame count stays display-paced with `swapInterval(0)`** under
  `QT_D3D_NO_VBLANK_THREAD=1` (62.6 fps at every weather): it cannot measure a GPU cost here;
  the readback can.
