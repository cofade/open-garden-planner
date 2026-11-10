# Low-sun shadow edges — what made the steps, and how to measure them (#734)

ADR-059 addendum (#734). A low sun stretches everything a caster is made of: a shadow's far
edge moves `1 / tan(elevation)` cm on the ground for every centimetre of height (3.7 at 15°,
9.7 at 6°, 19 at 3°), and a shadow map's texel becomes `texel / sin(elevation)` long. Before
blaming the shadow map, find out which of the two a step is.

## The fix log (artifact → cause → fix)

| Artifact | Cause | Fix |
|---|---|---|
| A regular staircase along a picket fence's long shadow at golden hour, the same at every preset and map size (the issue's "stair steps") | the builder: the L0 fence lowered its pickets 0.3–4 cm by `index * 7919 % 13`, which is `2 * index % 13` — seven pickets climbing 0.6 cm each, then a drop. The fence's own top line was a sawtooth too, and every picket fence in every plan the same | each picket's drop is a hash of the item's seed (`fences.unit_hash`, `picket_seed`), 0.5–1.5 cm (`PICKET_DROP_CM`): the posts stay proud, no two neighbours level, and a 6° sun stretches the spread to 9.7 cm. Every frame, the view's included |
| Coarse steps on a SOLID caster's long shadow 20–40 m out (the app's default framing), worst at High | `lockShadowmapTexels`: the last cascade spans the bounding sphere of its slice up to `shadowMapFar` (≥ 90 m): 8.3 cm texels on High | a STILL frame — a photo, an agent's picture, a held camera's time-lapse — fits its cascades to the casters (`Quick3DHost.capture(fitted_shadows=True)`). The live view and a moving tour keep the locked fit: a fitted map follows the camera and crawls |
| Lit teeth along the foot of every caster at a low sun (a fence's base, a wall, a bed frame) | the ground does not cast: a ground point whose texel misses the caster's foot is lit; each tooth is `texel / sin(elevation)` long (81 cm at 5.9° on High) | the same: about 1 cm texels in a still frame |
| Bright streaks scattered through a picket fence's shadow at sunset | at an oblique sun the 2.2 cm thick pickets close the 4.6 cm slits to about 0.5 cm in light space (8 % open at 31.5°): far under a texel, so a texel whose centre falls in a slit leaks a full texel of light 5 m long, its neighbours none | the same: in a still frame the slits resolve into fine regular stripes. A larger `pcfFactor` only smeared the streaks into broad bands |

What is left and is TRUE: the posts stand 0.5–1.5 cm proud of the pickets (a small bump in the
shadow every 2 m), the pickets' comb, the 10 cm shadow bias's lit sliver at a caster's foot,
and Qt's per-pixel PCF dither (`ogp-3d-renderer` §23). The family garden's fence edge at golden
hour also carries the shadows of the perennials behind it (200 cm tall, 90 cm behind a 120 cm
fence: their shadows reach past the fence's at 15°) — the 2D overlay's outline shows them.

What is left and is a CHOICE: the live view (and the photo-mode preview, and an orbit or a
flight) still shows the locked map's far steps, foot teeth and streaks at a low sun; the saved
photo does not. A reviewer judging a low-sun look judges the saved picture (`--photo-shadows`),
and the view's look on the view's board (the default).

## Measuring a long shadow (`--stairs`)

```bash
venv/Scripts/python.exe scripts/render_beauty_board.py --out <dir> --presets high,ultra --shots none --stairs --size 1920x1080
```

A 23.8 m solid panel and a picket fence at the plan's south edge (bench_small), the board's
golden hour (15.2°) and sunset (5.9°), the golden-hour camera and the app's default framing,
every frame in a still picture's fit. Per frame `metrics.json` `stairs` holds: the far edge
traced against the analytic line per view-depth bin (`probes.shadow_edge_trace` — an area
estimator, sub-pixel; `edge_staircase`: `wobble_cm` / `wobble_px`, the 95th − 5th percentile of
the detrended edge, and `jump_px`); for the panel the lit share of a line 15 cm out from its
shaded face (`foot`); for the fence at the lowest sun the streaks inside its shadow
(`probes.shadow_streaks`: the luma box-filtered over one picket pitch — true stripes cancel, a
texel beat stays — judged only where a pitch spans 8 px, so 1080p or larger; which lines that
is depends on the camera alone: the hero camera's 100 and 250 cm lines, the framed camera's
100 cm line); `stairs_orbit` the edge's crawl over an orbit of 0.5° a frame in both fits
(`view`, `fitted`), averaged over 30 cm along the edge (the pixel dither cancels, a texel
crawl would not); `stairs_timelapse` the same with the camera held and the sun stepping
0.4° / 0.55° a frame, each frame traced against its own sun's edge (the true motion drops
out). `--photo-shadows` puts every other frame of the board in a picture's fit too.
Render-tier gate: `test_view3d_looks_render.py::test_a_long_low_sun_shadow_has_no_stairs_no_lit_teeth_and_no_streaks`.

Measured (RTX 4070, 1080p, 2026-11-10; locked → a still frame's fit, High / Ultra): the
panel's edge 20–40 m out at 15.2° 5 / 1 → 0.64 / 0.63 cm, at 5.9° 11 / 2 → 2.24 / 2.27 cm; its
foot lit 0.339 / 0.011 → 0.023 / 0.023 (worst of four frames); streaks 0.49 / 0.30 → 0.165 /
0.136 (worst line). The orbit at 0–10 / 10–20 m: locked 0.079 / 0.094 px (Ultra 0.082 / 0.087),
fitted 0.21 / 0.146 (Ultra 0.106 / 0.117) — a fitted map crawls MORE when the camera moves. The
time-lapse: locked 0.336 / 0.682 px (Ultra 0.175 / 0.321), fitted 0.265 / 0.517 (Ultra 0.167 /
0.298) — LESS when only the sun moves. Hence the routing: a photo, an agent's picture and a
held camera's frames fitted; the view, an orbit and a flight locked. The picket fence's edge at golden hour in the hero
camera, 0–10 m: 6.65 → 4.59 px (what is left: the posts); the builder's references against the
2D caster model moved by +0.01 (area ratio 1.01 / 1.01 / 1.00, IoU 0.66 / 0.67 / 0.68, tip
unchanged +2.0 / +2.0 / +2.4 cm; `scripts/measure_built_world_shadows.py`).

Lessons for a reviewer: an artifact that does NOT change when the map doubles is geometry;
overlay the 2D shadow outline (`compute_scene_shadows`) on the frame before measuring an edge
that other casters may share; a "jitter" from a multiplicative step modulo a small number
is a ramp — check its autocorrelation, not its look in one frame; and judge a shadow setting
in MOTION on a real plan too — a lone synthetic caster hid the fitted map's crawl.
