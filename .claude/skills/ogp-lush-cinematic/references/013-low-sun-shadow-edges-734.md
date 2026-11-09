# Low-sun shadow edges — what made the steps, and how to measure them (#734)

ADR-059 addendum (#734). A low sun stretches everything a caster is made of: a shadow's far
edge moves `1 / tan(elevation)` cm on the ground for every centimetre of height (3.7 at 15°,
9.7 at 6°, 19 at 3°), and a shadow map's texel becomes `texel / sin(elevation)` long. Before
blaming the shadow map, find out which of the two a step is.

## The fix log (artifact → cause → fix)

| Artifact | Cause | Fix |
|---|---|---|
| A regular staircase along a picket fence's long shadow at golden hour, the same at every preset and map size (the issue's "stair steps") | the builder: the L0 fence lowered its pickets 0.3–4 cm by `index * 7919 % 13`, which is `2 * index % 13` — seven pickets climbing 0.6 cm each, then a drop. The fence's own top line was a sawtooth too, and every picket fence in every plan the same | each picket's drop is a hash of the item's seed (`fences.unit_hash`, `picket_seed`), 0.5–1.5 cm (`PICKET_DROP_CM`): the posts stay proud, no two neighbours level, and a 6° sun stretches the spread to 9.7 cm |
| Coarse steps on a SOLID caster's long shadow 20–40 m out (the app's default framing), worst at High | `lockShadowmapTexels`: the last cascade spans the bounding sphere of its slice up to `shadowMapFar` (≥ 90 m): 8.3 cm texels on High | the perspective view's cascades are fitted to the casters (`lockShadowmapTexels: root.topDown`) |
| Lit teeth along the foot of every caster at a low sun (a fence's base, a wall, a bed frame) | the ground does not cast: a ground point whose texel misses the caster's foot is lit; each tooth is `texel / sin(elevation)` long (81 cm at 5.9° on High) | the same: about 1 cm texels |
| Bright streaks scattered through a picket fence's shadow at sunset | at an oblique sun the 2.2 cm thick pickets close the 4.6 cm slits to about 0.5 cm in light space (8 % open at 31.5°): far under a texel, so a texel whose centre falls in a slit leaks a full texel of light 5 m long, its neighbours none | the same: the slits resolve into fine regular stripes. A larger `pcfFactor` only smeared the streaks into broad bands |

What is left and is TRUE: the posts stand 0.5–1.5 cm proud of the pickets (a small bump in the
shadow every 2 m), the pickets' comb, the 10 cm shadow bias's lit sliver at a caster's foot,
and Qt's per-pixel PCF dither (`ogp-3d-renderer` §22). The family garden's fence edge at golden
hour also carries the shadows of the perennials behind it (200 cm tall, 90 cm behind a 120 cm
fence: their shadows reach past the fence's at 15°) — the 2D overlay's outline shows them.

## Measuring a long shadow (`--stairs`)

```bash
venv/Scripts/python.exe scripts/render_beauty_board.py --out <dir> --presets high,ultra --shots none --stairs --size 1920x1080
```

A 23.8 m solid panel and a picket fence at the plan's south edge (bench_small), the board's
golden hour (15.2°) and sunset (5.9°), the golden-hour camera and the app's default framing.
Per frame `metrics.json` `stairs` holds: the far edge traced against the analytic line per
view-depth bin (`probes.shadow_edge_trace` — an area estimator, sub-pixel; `edge_staircase`:
`wobble_cm` / `wobble_px`, the 95th − 5th percentile of the detrended edge, and `jump_px`);
for the panel the lit share of a line 15 cm out from its shaded face (`foot`); for the fence
at the lowest sun the streaks inside its shadow (`probes.shadow_streaks`: the luma box-filtered
over one picket pitch — true stripes cancel, a texel beat stays — judged only where a pitch
spans 8 px, so 1080p or larger); `stairs_orbit` the edge's crawl over an orbit of 0.5° a
frame, averaged over 30 cm along the edge (the pixel dither cancels, a texel crawl would not).
Render-tier gate: `test_view3d_looks_render.py::test_a_long_low_sun_shadow_has_no_stairs_no_lit_teeth_and_no_streaks`.

Measured (RTX 4070, 1080p, base → fix; High / Ultra): the panel's edge 20–40 m out at 15.2°
5 / 1 → 1 cm, at 5.9° 11 / 2 → 2 cm; its foot lit 0.339 / 0.011 → 0.011; streaks 0.49 / 0.30
→ 0.12 / 0.10. The picket fence's edge at golden hour in the hero camera, 0–10 m: 6.65 → 4.59 px
(what is left: the posts); the builder's references against the 2D caster model moved by
+0.01 (area ratio 1.01 / 1.01 / 1.00, IoU 0.66 / 0.67 / 0.68, tip unchanged +2.0 / +2.0 /
+2.4 cm; `scripts/measure_built_world_shadows.py`).

Lessons for a reviewer: an artifact that does NOT change when the map doubles is geometry;
overlay the 2D shadow outline (`compute_scene_shadows`) on the frame before measuring an edge
that other casters may share; and a "jitter" from a multiplicative step modulo a small number
is a ramp — check its autocorrelation, not its look in one frame.
