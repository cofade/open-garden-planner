# Case study: stair steps on a long fence shadow that were two bugs, neither the one named (#734)

## Symptom

The family garden's golden-hour photo (4K, #729's demo material) showed coarse stair steps
along the outer fence's long shadow on the meadow; at the 5.9° sunset the same meadow was
strewn with elongated bright streaks between the pickets' shadows. Inside the garden the
shadows looked clean. The issue asked which shadow setting decides it: the cascade's reach,
the map's size or the filter.

## Wrong theories

1. **The cascade's reach / texel density.** Plausible: `shadowMapFar` never drops under
   9000 cm, so the last cascade is coarse. But the fence's edge in that shot lies 10–20 m
   from the camera, in High's MIDDLE cascade (2.45 cm texels), and the notches were 3–5 px —
   three to four times what that texel can make there.
2. **The map's size, the depth format.** A 4096 map, a 4284 cm reach and a 32-bit map each
   left the notches exactly where they were, pixel for pixel.
3. **The picket "jitter" alone.** Setting it to zero did not remove the big notches either:
   they were the shadows of 2 m perennials just behind the fence, reaching past its shadow.
4. **"A fitted map costs nothing, so fit the view too."** The first fix fitted the live view's
   cascades to the casters. A synthetic orbit (a lone panel) showed no extra crawl — because
   the panel sat deep in the far cascade, where the casters' box hardly changes as the camera
   turns. Orbiting the real family garden through the product's capture path, the fence's edge
   crawled 0.69 / 0.38 px a frame fitted against 0.16 / 0.18 locked (0–10 / 10–20 m, averaged
   over 30 cm); one fitted cascade crawled as far (0.32 / 0.39).
5. **"A capture is a still picture, so a capture fits by default."** The second design made
   `Quick3DHost.capture(fitted_shadows=True)` the default. The routing tests passed; the real
   self-test did not: its check that a capture at the view's size IS the view failed on the
   renderer ("the capture differs from the view by up to 24 levels") — the frozen exe's
   `--selftest`, a release gate, would have failed.

## Key evidence

- Changing the shadow map changed NOTHING about the notches (a crop strip of five variants):
  whatever does not move with the map is geometry.
- An overlay of the 2D shadow outline per caster (`compute_scene_shadows`, projected with the
  board's `Pinhole`) separated the fence's own edge from the plants' shadow lobes.
- A synthetic probe (`--stairs`: the fence alone and a solid panel of the same size) made the
  two mechanisms measurable apart: the panel's edge stepped 5 / 11 cm 20–40 m out (15.2° /
  5.9°, High), and 34 % of a line along its foot was lit at sunset; the fence carried a
  regular sawtooth that no shadow setting touched.
- `index * 7919 % 13` — the picket drop — is `2 * index % 13`: autocorrelation 1.0 at lag 13.
- Qt 6.12's `setupCascadingCamerasForShadowMap`: locked, a cascade spans the bounding sphere of
  its whole slice; unlocked, the casters' box clipped to the slice — a box that moves with the
  camera's slices.
- `tests/integration/test_quick3d_selftest.py::test_the_3d_selftest_passes_on_the_default_adapter`
  on the merged tree: `FAIL capture view -> EngineError: the capture differs from the view by
  up to 24 levels`.

## Root cause

Two bugs. (1) The builder's picket tops climbed in a ramp (0.6 cm a picket for seven pickets,
then a drop); at 15° every centimetre is 3.7 cm of shadow, so the ramp became a staircase,
and every picket fence in every plan was the same. (2) `lockShadowmapTexels: true` sizes
each cascade by the bounding sphere of its whole slice, not by what casts: 8.3 cm texels
20–40 m out on High, so long edges stepped, every caster's foot showed lit teeth
(`texel / sin(elevation)` long: the ground does not cast), and the 0.5 cm slits an oblique sun
leaves between 2.2 cm thick pickets aliased into streaks. `pcfFactor` is a radius in scene
units, a quarter of such a texel — it could not hide it. The cure for (2), a fitted map, is
camera-dependent: right for a frame whose camera holds still, wrong for a moving one.

## Fix

Each picket's drop is a hash of the item's seed, 0.5–1.5 cm (`fences.PICKET_DROP_CM`,
`unit_hash`, `picket_seed`), in every frame. The shadow fit is chosen per frame:
`lockShadowmapTexels: root.topDown || !root.fittedShadows`. `Quick3DHost.capture` keeps the
view's locked fit by default (a capture at the view's size stays the view); the still pictures
ask for the fitted map by name — `write_photo`, `agent_picture` and a `HeldCamera` tour's frames
(`fitted_shadows=True`); the live view, an orbit and a flight stay locked. The held camera's
rule was first an argument ("the sun moves, it re-fits either way"); measured with the camera
held and only the sun moving, the fitted edge crawls LESS (0.265 / 0.517 px a frame against
0.336 / 0.682 locked, High, 0–10 / 10–20 m), the opposite of the orbit. Pins: the render gate
`test_a_long_low_sun_shadow_has_no_stairs_no_lit_teeth_and_no_streaks` (observed failing on the
base, 4.97 cm against 2.5); the builder pin (fails on the base for clones and the ramp); the
routing pin `test_a_still_camera_fits_its_shadows_and_a_moving_one_keeps_the_views` (fails when a
picture path does not ask); `test_a_still_pictures_fitted_shadows_change_only_its_own_frame`
and the self-test (a default capture is the view, 0 levels).

## Lesson

Name the mechanism before the setting: an artifact that survives doubling the map is not
the map. Isolate the caster in a synthetic scene and overlay the analytic outline before
measuring an edge other casters share — but measure MOTION on the real plan through the
product's own path: an isolated caster hid the fitted map's crawl. Measure a "random"
sequence's autocorrelation — a multiplicative step modulo a small prime is a ramp. Read the
engine's source for what a property means: `pcfFactor` is centimetres, `lockShadowmapTexels`
is a sphere. And a new per-call option defaults to the old behaviour, with the new callers
asking by name: a default that changes what every existing caller gets breaks the checks
that pin the old contract — run them (here the self-test) before trusting a fake host.
