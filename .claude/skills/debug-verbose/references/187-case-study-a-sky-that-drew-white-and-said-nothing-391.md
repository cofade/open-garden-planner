## Case study: a sky that drew white and said nothing (#391)

- **Symptom:** the ported atmosphere sky (Qt 6.12 `SkyMaterial`) was pure white in every
  board frame, at every sun height — even at night, where its shader returns the painted sky
  unchanged. No Qt warning in any logging category; the ground and the light were fine.
- **Wrong theories:** an exposure or gain off by orders of magnitude (but the night frame
  must equal the painted night whatever the gain); the cube rendered one frame late (but the
  screen-space mode, which needs no cube, read the same numbers to the hundredth).
- **Key evidence:** a minimal harness, one `View3D` per case: `SkyMaterial {}` drew Qt's debug
  sky, an inline shader drew, ours drew `255,255,255` on frame 1 and then the DEBUG sky — with
  one texture input left null. Qt's source (`qssgrenderskymaterial.cpp`,
  `skyShaderTexturesReady`): the shader is compiled only once every sampled texture exists,
  "since the GLSL sampler type depends on the actual texture". The example's look-up tables
  are `QuadTextureProvider` textures, which exist only after their first render. A second
  `grabWindow()` on the never-shown offscreen view, to warm it up: access violation.
- **Root cause:** a texture rendered IN the frame is not ready for the sky's compile in that
  frame; the app's offscreen frames (board, probes, self-test) render exactly once.
- **Fix:** compute both tables in numpy (`core/scene3d/atmosphere_lut.py`) and hand them, with
  the cloud volume, over as `QQuick3DTextureData` — ready before frame 1 (PF-E3D-14).
- **Lesson:** when a frame is wrong in the SAME way for opposite inputs (noon and night),
  stop tuning values and bisect the pipeline with a harness of known-good variants; and read
  the engine's source for silent fallbacks before trusting "no warning".
