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

## Root cause

Two bugs. (1) The builder's picket tops climbed in a ramp (0.6 cm a picket for seven pickets,
then a drop); at 15° every centimetre is 3.7 cm of shadow, so the ramp became a staircase,
and every picket fence in every plan was the same. (2) `lockShadowmapTexels: true` sizes
each cascade by the bounding sphere of its whole slice (Qt 6.12 source), not by what casts:
8.3 cm texels 20–40 m out on High, so long edges stepped, every caster's foot showed lit
teeth (`texel / sin(elevation)` long: the ground does not cast), and the 0.5 cm slits an
oblique sun leaves between 2.2 cm thick pickets aliased into streaks. `pcfFactor` is a radius
in scene units, a quarter of such a texel — it could not hide it.

## Fix

Each picket's drop is a hash of the item's seed, 0.5–1.5 cm (`fences.PICKET_DROP_CM`,
`unit_hash`, `picket_seed`). The perspective view fits each cascade to the casters
(`lockShadowmapTexels: root.topDown`): about 1 cm texels on a 24 m plan at no cost; an orbit
showed no extra crawl (averaged over 30 cm: 0.19 px fitted against 0.23 px locked). The
render-tier gate was observed failing on the base (4.97 cm > 2.5) and passing after; the
builder pin fails on the base for clones and the ramp.

## Lesson

Name the mechanism before the setting: an artifact that survives doubling the map is not
the map. Isolate the caster in a synthetic scene and overlay the analytic outline before
measuring an edge other casters share. Measure a "random" sequence's autocorrelation — a
multiplicative step modulo a small prime is a ramp. And read the engine's source for what a
property means: `pcfFactor` is centimetres, `lockShadowmapTexels` is a sphere.
