---
name: ogp-lush-cinematic
description: "The art-direction contract for Open Garden Planner's 3D mode ('Lush Cinematic', Phase 17 / ADR-048) and the shared knowledge base of the ogp-3d-creator and ogp-3d-reviewer agents. Load when: building or reviewing anything that shows up in the 3D view (plants, buildings, ground, sky, light, shadows, materials, post-processing, camera shots); producing or judging a Beauty Board; choosing colours, roughness, light colour or exposure; deciding whether a 3D look is 'done'; or recording owner feedback on a render. Contains the truth-before-beauty gates, the style table, measured light rigs per mood, material value ranges, foliage rules, the Beauty Board procedure, the review rubric with severities, the spike's artifact→fix log and the owner taste log."
---

# Lush Cinematic — the 3D art-direction contract

**Status:** v1, written from the Package L0 spike (ADR-048, *Accepted — GO 2026-10-05*). Values marked
*spike* are measured starting points from `src/open_garden_planner/spike_q3d/`, not dogma —
tune them, but only with a before/after board and a note in the taste log below.

**Owner decisions (2026-10-03):** look = *Lush Cinematic* (stylised-realistic, cozy-game
light, consistent with the 2D "Lush" sprites/textures — ADR-040, ADR-042); role = *experience
+ analyze* (editing stays in 2D; 3D only selects); models = *100 % procedural* (generator =
provenance; no external model libraries, no paid services).

## 1. Truth before beauty (non-negotiable)

OGP is a planning tool. A beautiful render that misstates the plan is a **P0**, full stop.

| Gate | Rule | How it is measured |
|---|---|---|
| Height | mesh top = resolved height (`effective_height_cm(at_date)`) ±3 % | bounding box; `fit_to` enforces it for every plant archetype |
| Spread | widest crown span = 2D canopy diameter ±10 % | bounding box vs `plant_canopy_radius_cm` (`ui/canvas/footprints.py`; a record's `params["radius_cm"]`) |
| Base | a plant that is linked to AND stands inside a raised bed / container stands on its soil, not inside the box | base = `ui/canvas/footprints.item_base_cm`: a bed's effective height − 2 cm (the assumed soil drop: the plan holds no fill for a bed); a container's effective height itself (it IS its soil fill height — no lip is invented); 0 when the plant is not linked, or its centre is outside the parent's shape — its stable geometric centre (`footprints.standing_point`), never the centre of its paint-dependent `boundingRect()`: a warning badge must not move a plant off its soil. Known limits, pinned by tests: a bed drawn around an existing plant links nothing (the plant is drawn inside the box), a climber on a trellis in a raised bed stays at 0, a pot on a raised bed stands on the ground (ADR-037 addendum "base stacking") |
| Sun | light direction comes only from `core/solar` (never a "nice-looking" angle) | light = −sun vector (ADR-037 pin) |
| Shadows | engine shadow footprint of a box caster vs the analytic 2D shadow | IoU ≥ 0.85 at 15°/35°/60° (spike at 960×540: 0.98/0.98/0.96 on OpenGL **and** on Direct3D 11; 0.96/0.95/0.92 at 1280×720; orthographic, no cascades — table in `ogp-3d-renderer` §4). **Defined on a solid box caster.** Built-world meshes are not boxes: judge them against their own measured IoU with the 2D caster model at 15°/35°/60° (`scripts/measure_built_world_shadows.py`; `tests/unit/test_scene3d_shadow_agreement.py` holds the builders to it within 0.05), not against this gate — raised bed, box, plain panel 0.99–1.00 (the same prism); hedges 0.93–0.97; round tub 0.89–0.91 and terracotta pot 0.81–0.83 (taper); house 0.74–0.88, shed 0.83–0.88 (gable roof vs flat-topped prism); wall 0.96/0.91/0.81, stone-wall fence 0.94/0.87/0.73, hedge fence 0.96/0.89/0.76 (nominal section — the plan holds no thickness for a line: the 3D shadow is WIDER, more at a high sun); picket fence 0.65/0.66/0.68, metal fence 0.19/0.20/0.24, chain-link fence 0.12/0.13/0.19 (porosity: the 3D shadow is a FRACTION of the solid strip the 2D sun study casts — an open owner question, not a builder defect). **What the listed numbers are:** analytic references for the BUILDERS — one item, the sun square to a straight 10 m line (a building: square to or along its ridge), the mesh projected onto the ground without a shadow map. Against that reference a builder's number below the listed one is a finding; the listed number is not. They are NOT what an engine render must read: the engine's shadow map is judged on solid casters (the box gate above), and thin members — 0.8 cm wires, 1.6 cm bars, about one shadow-map texel — are exempt from a per-pixel IoU; a render that reads lower there is no builder defect. **Where the tip is** (reach along the shadow direction, 3D − 2D, cm at 15°/35°/60°, same script and test, within 1 cm): it agrees within 2.5 cm for the prisms (−0.6/−0.6/−0.3; plain panel 0.0), the pots (−0.6 … −0.3) and the post fences (picket fence +2.0/+2.0/+2.4, metal +0.8, chain link +1.5); hedges +2.7 … +4.4 (leaf tips). It does NOT agree for a gabled building with the sun square to its ridge — house −270.0/−270.0/−108.2, shed −150.0/−81.4/−21.0: the 2D model extrudes the footprint to the ridge height, so its top edge is at the far wall while the gable's ridge is mid-house, half the depth short at a low sun. That is the two models' difference, not a roof to "fix". Sun along the ridge: +30.0 (the overhang). Nominal sections reach further: wall +15.0/+15.0/+15.8, stone-wall fence +14.5/+14.5/+15.3, hedge fence +19.6/+19.5/+19.6. No universal sentence about shadows goes into this row unless the script prints the number behind it |
| North | ground texture is north-up; nothing is mirrored | orientation probe NCC: identity must win |
| Sky | the sky's sun disc sits at the solar azimuth | sky probe error < 6° (spike, disc 25° off-centre: max 0.85° OpenGL, 1.4° D3D11) |
| Date | season/growth shown = the plan's sim date | models are built for each shot's own date; every shot row records `sun_date` = `build_date` (`metrics.json`) |
| Season | fruit and flowers only inside the plan's OWN frost-free season: `location["frost_dates"]` `last_spring_frost` ≤ day ≤ `first_fall_frost` (`"MM-DD"`, the keys the task generator reads); fruit whose species carries harvest weeks follows the shared task generator's harvest window instead — last spring frost + `harvest_start` … + `harvest_end` weeks, anchored on every frost year whose window can reach the day (a 29 February frost and the spike's fallback for it: ADR-048 entry 18; `task_generator.generate_for_date_window`, behind the agent's `get_tasks` and `get_task_calendar`; every GUI task surface anchors on one year, TD-037; bench: tomato 18 Jun–27 Aug, sweet pepper 2 Jul–13 Aug, so the 21 June board shows no peppers); no frost dates → no seasonal claim (accents stay). Crowns never go bare: the growth model has no leaf-off — an owner question, not a look lever | `runner.in_frost_free_season`, `runner.in_harvest_window` / `accents_in_season`; every shot row's build records `in_season` (`metrics.json` `builds`); exact accent-colour markers in `test_spike_q3d_board.py` / `test_spike_q3d_meshes.py` |
| Built heights | every built object's top = its resolved height ±1 % | builders exact to `h`, `fit_height` as the safety net; objects with no resolved height (rain barrel, fire pit) cast no shadow — as in 2D |
| Faces | the sun lights the face that faces it | stored normal · winding normal ≥ 0.99 on every flat face (the first board lit the wrong roof slope) |

Never tune a domain number (species height, spread, planting date) to make a shot prettier.

## 2. Style table

| Layer | Rule |
|---|---|
| Light | One key light = the real sun. Warm when low, neutral-white when high. The sky is the fill (image-based lighting) and must **not** out-shine the sun — the first spike renders read flat and blue precisely because the probe dominated. |
| Colour | Plants and objects take colours only from the 2D tables (sprite `PALETTES`/`FRUITS`/`FLOWERS`, object `MATERIALS`). Seasonal colour is a function of those palettes, never a new literal. Albedo stays inside sRGB ~40–240 (no pure black/white surfaces). |
| Form | Chunky, readable silhouettes; bevels on built things; vegetation slightly fuller than nature; real-world dimensions; nothing floats, nothing is cloned. |
| Foliage | Geometric micro-leaves (2 triangles each), **no alpha cards** (aliasing + sort + shadow-pass problems). Normals spherized toward the crown centre (0.55–0.75) so a crown shades like one soft volume. Leaf count follows crown surface area (coverage ≈ 1.6), not a magic number — inside the plant's triangle budget (tree 25,000, bounded by construction: `meshes.TREE_TRIANGLE_BUDGET`; any other plant has a 6,000 target it meets on the bench, max 3,252, but is NOT bounded by — builders dispatch by species archetype, so a tree-archetype species on a non-tree item can reach the tree's count; L1.7 budgets by archetype): wood and fruit/flowers first, then leaves; a crown over it gets fewer, LARGER leaves at the same coverage (conifers: ≤ 12,000 sprays, same spray area), never a sparser crown. A canopy tree is bounded **by construction** (`meshes.TREE_NODES_MAX`): branch segments sized from the crown's larger dimension (max(height, spread) / 28), at most 1,000 skeleton nodes (wood ≤ 13,986), at most 140 fruit or flowers (fruit ≤ 140 × 32 = 4,480; flowers with 8-triangle octahedron centres 140 × 20 = 2,800) and the floor of 2 leaves per twig (≤ 4,000) — 22,466 ≤ 25,000. Gate: every plant of both bench plans on both board dates, and wide crowns up to 4 × wider than tall. |
| Atmosphere | Filmic/ACES tonemapping, gentle glow, depth fog whose colour equals the sky horizon (hides the meadow/sky seam) at **every** preset — low included, or the meadow meets the sky in a one-row cliff — SSAO from Medium up. **No sharpening** (`sharpnessAmount` 0): 0.08 overshot every thin lit edge into near-black dots; every board row records them (`isolated_dark_px`, §5). DOF/vignette only in photo mode. |
| Motion | Wind sways grass and crowns via shader values (uv.x = sway weight, uv.y = phase); animation only while the 3D view is visible; reduced-motion setting stops it. |

**Plant v0 (Package L1.7) — what the production plants are, and are not.** The plants the
pipeline builds (`core/scene3d/builders/plants.py`, §8.32.7) are not the spike's: one cheap
silhouette per 2D sprite archetype — soft volumes and a shell of large geometric leaves, at most
2,000 triangles a plant, bounded per archetype and by construction (measured: canopy 1,904 …
flower 316). Judge them as v0:

- Archetype and palette come from the recipe of the sprite the plan shows
  (`core/plant_art/recipes.py`, resolved by `core/plant_art/resolve.py` — the 2D rule, on the 2D
  renderer's own inputs: the item's type, its own species string as it is, its category). A plant
  whose 3D shape or green contradicts its sprite is a finding; a plant whose *sprite* is odd
  (Lemon Balm drawn as a lemon tree; a plant given a species from the plant database that still
  shows its old sprite) is a 2D finding that 3D reproduces faithfully.
- **No fruit, no flowers, no flower heads, by decision** — the season gates need the plan's frost
  dates, which a record does not carry (Package L3). Their absence against the L0 board is not a
  regression. Crowns are never bare.
- One bark for every species (the 2D BARK texture's mean, `#5d432d`), no species crown forms, no
  support under a climber. Species-accurate plants are Package L3.
- **The placeholder**: a plant without a height — every category plant from the gallery and
  every tool-drawn plant until someone types or measures one, and any plant whose species string
  names one of the twelve sprites without a bundled species record (squash, turnip, arugula,
  chard, okra, tarragon, lemongrass, marjoram, bay laurel, stevia, sorrel, lovage) — is a low,
  smooth, neutral grey dome over its canopy circle
  (the 2D white × 0.5 linear, sRGB 170 / 167 / 158), at most 25 cm high, casting no shadow. It is a truth statement ("the plan does not know"), not
  an unfinished asset — review whether it reads as a marker, never ask for a guessed tree.
- What the builder GUARANTEES (by construction — the last steps of its fit; tested on hostile
  input to the fit itself): top = height and widest span = canopy diameter exactly, base on the
  ground, and no FOLIAGE vertex further than 1.09 canopy radii from the axis (`REACH_MAX`; the
  gate is 1.10). That this bounds the whole plant rests on an invariant of the trunk builders —
  foliage is the outermost part: wood is built within 0.32 canopy radii of the axis and is never
  moved by the fit (a new archetype with wood must keep it; the tests hold wood inside 0.5). What is MEASURED (re-measure with `scripts/measure_plant_art_3d.py`, command `truth`;
  do not trust; a sample of 63,099 plants — every recipe × every proportion step × three ids):
  the plant is BUILT to those numbers, not scaled into them — the builder's own top is the
  height before the fit touches it (`fit_report`: 1.0000 in every plant), nothing is pressed
  onto the ground, at most 2.2 % of the foliage vertices are pulled back onto the canopy circle —
  and the foliage's mass reaches the top (95 % / 99 % area quantiles per archetype; the smallest
  measured: a mound 0.719 / 0.884 of its height, a rosette 0.605 / 0.719, a hedge 0.877 / 0.938). No
  foliage triangle lies flat on the ground; at least six vertices touch it. Never quote a
  measured number as a guarantee: "at most 1.092 radii" stood in a requirement until one id in
  300,000 read 1.1006. Foliage hue within 10° of the rendered sprite (measured ≤ 5.0°) — of the
  UNTINTED sprite: the canvas lays the item's fill colour over a plant's sprite at 60 / 255, 3D
  does not (an open owner question: should a recoloured plant be tinted in 3D?).
  Two ids: over 30 ids a recipe the most alike pair is 97.5 % alike (two hedge sections), 99 %
  of all pairs are below 95.2 %; a clipped hedge and a flat ground cover repeat by nature.
- A bounding box that is exact after a fit says nothing about the plant. When judging a plant's
  size on a board, look at where its MASS ends, not where its highest leaf tip is: the first
  version built a squash 1.6 times too tall and squashed it back — exact box, body in the lower
  two thirds.
- A date scrub scales remembered shapes (a daily tick of 320 plants: 15 ms on a busy box, 342 ms
  without the cache); the form of a plant changes only when its proportion crosses a 5 % step, by
  at most 2.5 % of stretch in one axis. At a step a plant stays itself — measured, its side
  silhouette in the unit box is 0.99–1.00 the one before (another id: 0.71–0.92); the visible
  steps on a slow scrub are single leaves turning to stay inside the canopy circle (0.94) and a
  conifer gaining a whorl (0.87: the stack is re-divided). Judge those two on a board.
- Not yet seen through the production engine. The author looked through a numpy rasteriser and
  the dormant spike's renderer only (scratch) — enough to find a floating cushion and bald crown
  tops, not enough to judge the look. The Beauty Board decides.

## 3. Light rigs per mood (*spike* values, `look_for` / `sun_light` / `sun_state` in `spike_q3d/runner.py`)

**In production** (L1.4) the rig is DATA in `core/scene3d/look.py` (`NOON`, `GOLDEN`, `LOW_SUN`,
`NIGHT`, `day_rig`, `look_for(sun, preset) -> LookSpec`), ported with these values and pinned
against the spike's functions at every quarter degree until the spike retires. Deliberate
differences, each from a board: the night fog carries the night sky's energy (× 0.25); the
night sky's ground hemisphere is drawn at the sky's energy (0.25, the spike 0.15); and civil
twilight is a ramp (fix round 1) — the sun's key light goes where the 2D shadow overlay ends
(`core.shadow_geometry.MIN_SUN_ELEVATION_DEG`, 0.5°), night begins at −6° (`TWILIGHT_DEG`) — §7.

By day the rig is three **anchors** joined by **continuous ramps** (`runner._day_ramp`):
low → golden over 0.5° → 6°, golden → noon over 6° → 30°, the noon rig above. Every value
ramps — sun colour and brightness, sky top / horizon, sun disc, probe, exposure (fog follows
the horizon) — colours mixed in linear light, exposure in stops (log2), the rest linearly.
Night is a separate rig below 0.5°. Steps made moods jump: the sun colour at 15°/6° (a
14° December noon warmer than a 15° June golden hour), exposure 1.15 → 0.85 within a
degree at 20°, sky/fog/probe at 8° and 20°. The key light is **never brighter than at
noon** (a low sun crosses more air): the golden mood is its exposure and colour.

| Anchor | Sun elevation | Sun colour / brightness | Sky top / horizon (sun disc) | Probe / exposure |
|---|---|---|---|---|
| Noon | ≥ 30° | `#fff1dc` / 1.9 | `#3f78c9` / `#cfe2f2` (`#fff0d8`) | 0.55 / 0.85 (0.92 clipped a channel on 4.6 % of noon_low) |
| Golden | 6° | `#ffb878` / 1.9 (2.1 put a 2.03 sun into the 14° December noon and clipped the roof) | `#4f7fc8` / `#f4d2a6` (`#ffd09a`) | 0.50 / 1.15 |
| Low sun | 0.5° | `#ff9655` / 1.7 | `#4a6fb0` / `#f2b47c` (`#ffb070`) | 0.42 / 1.25 |
| Twilight (production, L1.4) | 0.5° → −6° | the low-sun rig mixed into the night rig by t = (0.5 − e) / 6.5 (colours in linear light, exposure in stops); the key light is the moon at 0.32 · t — none, and no shadow, just under 0.5° | mixed; no sun disc; sky and ground energy 1 → 0.25 | mixed; saturation 1.06 → 0.6 |
| Night | < 0.5° (spike), < −6° (production) | moonlight `#8ea4d6` / 0.32 from az 165°, elev 38°; soft faint moon shadows (factor 25, PCF 8); saturation 0.6 | `#070d22` / `#1b2747` (`#9fb2e0`) | 0.35 / 2.4 |

On the board (bench_small, Berlin): golden_hour 15.23° → sun `#ffd0a8` / 1.9, horizon
`#e7d8c8`, probe 0.519, exposure 1.024 (was 1.15: mean luma 109.8 → 105.2, low);
december_noon 14.04° → sun `#ffcda3` / 1.9, exposure 1.039 (clipped 2.45 → 1.56 → 0.27 % of
the frame, low; 1.11 → 0.45 → 0.27 % high — what is left is the south wall and the birch
trunk, near-white faces a 14° sun lights at n·l ≈ 0.97); sunset 5.89° → the golden anchor
(`#ffb777` / 1.896, exposure 1.152, probe 0.498); morning 26.16° → 0.892 (was 0.85); noon
60.9° and walk 42.2° keep the noon rig. A 15° "golden hour" is between rigs — truthfully
less golden than the 6° anchor, which `sunset` shows.

## 4. Material value ranges (PBR, roughness 0–1)

| Material | Roughness | Notes |
|---|---|---|
| Lawn blades, leaves | 0.75–0.85 | specular ≈ 0.25; vertex colours from palettes |
| Bark, soil, mulch | 0.85–0.95 | |
| Plaster walls | 0.85–0.95 | warm off-white, never `#ffffff` |
| Roof tiles | 0.70–0.85 | terracotta `#b4553d` range (matches the 2D roof texture); their own material (`roofMat`, roughness 0.80, specular 0.15: `gable_house_parts` emits the roof as kind `"roof"`). Specular is NOT what makes a sun-facing roof read coral at noon: PrincipledMaterial scales its image-light diffuse by (1 − `specularAmount`), so 0.35 → 0.15 lifted the sky diffuse 1.31× and cancelled the lost highlight (noon_low roof sRGB (248, 135, 92) → (248, 135, 90)); the coral is the per-channel filmic shoulder (R compressed, G linear: hue 12.1° → 16.7°, inside the 10° line) |
| Wood (deck, fence, beds) | 0.60–0.80 | |
| Terracotta pots | 0.80–0.90 | |
| Water | 0.02 | 2D water colour `#4d92c5` (linear); a tight sun glint (0.05 still clipped ~23 % of the visible pond at morning, 0.3 blew it over the whole pond); a small custom shader (`qml/water.frag`) keeps its hue in every mood and adds a Fresnel × 0.15 sky reflection — PrincipledMaterial's grazing sky reflection turned the pond lavender at golden hour and ignores `specularAmount`/`fresnelScale`/`fresnelPower` |
| Glass | 0.02–0.06 | opacity 0.2–0.35, blended, no depth write, casts no shadow |
| Aluminium frames | 0.30–0.50 | |

## 5. Beauty Board procedure

Fixture: `tests/fixtures/plans/bench_small.ogp` (24×16 m showcase garden, every object class;
regenerate with `scripts/make_bench_plans.py`, never hand-edit). Render through the
**production pipeline** (L1.4) — `snapshot_records` → `SceneSync(production_registry())` →
`Quick3DSink` → a never-shown `Quick3DHost` per frame, lit by `core/scene3d/look.look_for`:

```bash
venv/Scripts/python.exe scripts/render_beauty_board.py --out <dir>   --presets low,high --shots all --iou --orient --horizon --moods --watchdog-s 1800
```

(Linux: prefix `QSG_RHI_BACKEND=opengl QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a
-s "-screen 0 1920x1080x24"` and use `venv/bin/python`.) `--plan` takes another plan
(`bench_large.ogp`), `--size` the frame (`960x540` is what the L0 and L1.4 boards were judged
at), `--dusk` the evening from 6° to −7° on the golden-hour camera (must fade monotonically;
sunset no larger a step than a half degree of the day ramp), `--fence` the plan's fences alone
against a 2x-supersampled render (aliasing), `--edge` the plan ground against the meadow along
its edges (a step ≤ 1 luma), `--software` renders on the graphics API's software adapter (WARP: the workspace's
compatibility mode — no sky texture, a plain sky and a flat fill), `--fps-seconds N` shows a
window and measures the frames it PRESENTS per preset with the wind running (and, labelled as
such, the cost of a finished readback), `--list` prints the shots and their suns. `<dir>/board.log`
records every phase (line-flushed; `--watchdog-s` dumps every thread's stack into it and exits
1) and `metrics.json` is rewritten after every phase; on a software rasteriser one frame can
take a minute (`ogp-3d-renderer` §8) — a slow board is not a hung board, read the log. The
script is isolated from the user's settings and stores (`scripts/script_isolation.py`). Exit
codes: 0 ok · 1 watchdog · 2 error · 4 a Qt shader or QML error.

Shots: `golden_hour`, `sunset` (the 6° golden anchor, golden_hour's camera), `noon`, `morning`,
`december_noon`, `night`, `walk` — the spike's dates, times and cameras, so a production board
lies beside an L0 board like for like; add `--presets low,medium,high,ultra --shots golden_hour`
for the preset strip. Every shot row of `metrics.json` carries `sun_elev` / `sun_az`,
`sun_date` = `build_date`, `isolated_dark_px` (luma < 40 inside a lit 8-neighbourhood > 110 —
the sharpening's speckles), `clipped_pct` (a channel ≥ 254), `mean_luma` and `mean_luminance`
(linear light), `sky_builds` and the frame's Qt message counts; the run carries
`shadow_iou` (`--iou`: a box caster at 15° / 35° / 60° in a PERSPECTIVE view with the preset's
cascades), `orientation` and `sky` (`--orient`: north-up NCC; the sky's sun disc read 25° off
centre in the east, south and west), `horizon` (`--horizon`: the row-mean step, dip and ridge
where fog meets sky, per mood and preset), `moods` (`--moods`: one camera and date under the
suns of noon, golden hour, sunset and night — `night_over_noon`), `frame_rate`,
`probe_restore_frame_diff` (the first shot rendered again after the probes; must be 0),
`wind_time` (0: every frame at rest), `builds.<date>.digest` (a digest of (item, height) per
snapshot: June and December must differ; `build_date` is read back from the records rendered)
and, with the flags above, `dusk`, `fence_moire` and `plan_edge`. The instruments are `scripts/board_probes.py` (numpy
only, each with a positive control in `tests/unit/test_board_probes.py`).

The L0 spike's board stays the reference for "before" until the spike retires (L1.10):
`venv/Scripts/python.exe -m open_garden_planner --spike-q3d --out <dir> --presets low,high
--shots all --iou --orient --size 960x540 --watchdog-s 1800` (its `spike.log`; it isolates
its own settings). Always show **before vs after** with the same plan, date, camera and size,
and attach `metrics.json` — a board without its numbers is not evidence.

## 6. Review rubric (the reviewer agent's checklist)

Score each shot on: readability (silhouettes, value grouping), light (direction, warm/cool
balance, contact shadows, acne/peter-panning, exposure histogram), colour (palette conformance,
saturation, season), form (proportions, bevels, density, clones, floating, ground contact),
materials (value ranges above), artifacts (z-fighting, sorting, shimmer, LOD pops, seams,
black frames, isolated dark pixels from `metrics.json`), motion (wind, reduced motion), **truth** (§1 gates from `metrics.json`),
performance (fps per preset vs budget), 2D consistency (same shape language and colours).

Severity: **P0** = truth gate failed, mirrored/black/broken frame, unreadable scene, crash.
**P1** = artifact visible at a default camera, clones, floating objects, palette hue off by
>10°, budget exceeded, a mood that contradicts its time of day. **P2** = polish.

## 7. Spike artifact → fix log (keep growing)

| Symptom | Cause | Fix |
|---|---|---|
| Whole garden pale blue, no shadows | sun never oriented (`lookAt` is camera-only) → only sky light | rotate the light: `QQuaternion.rotationTo((0,0,-1), travel)` |
| Lawn white, gravel around the beds | ground texture vertically flipped | `flipV: true`; pinned by the orientation probe |
| Empty plan areas light grey | `scene.render()` paints the beige canvas background | bake swaps the canvas colour for meadow green |
| Sky sun stuck in the north | light probe is pre-filtered once per Texture object | recreate the sky Texture on every sun change |
| Sky sun 90° off | ProceduralSkyTextureData longitude convention | `sunLongitude = azimuth + 90°` (measured) |
| Ultra preset renders black | SSGI on Mesa llvmpipe | SSGI opt-in until verified on real GPUs |
| Hard meadow/sky seam | fog colour ≠ sky horizon | fog colour = sky horizon, depth 26→160 m |
| Sparse "dead" crowns | fixed leaf count | leaf count from crown surface area |
| Faceted kettle | 1× subdivided sphere | `smooth=True` for close-up props |
| Wrong roof slope lit | each slab stored the other slope's normal | flat normals from the triangle winding; gate normal · winding ≥ 0.99 |
| December shot full of June plants | models built once for June | build per shot date; `build_date` in every shot row |
| BBQ +15.6 % tall, posts over the fence top | decoration added above `h` | builders exact to `h`, `fit_height` safety net |
| White band at the horizon | fog ignores probe exposure, the skybox does not | fog = sky horizon × probe exposure × 0.8 (linear); meadow 4 km |
| Night plan glows as an island | baked meadow ≠ meadow model albedo | one meadow albedo `#487f34`; night from light, never albedo |
| Pond beige/lavender | PrincipledMaterial sky reflection | `water.frag` (see §4) |
| Banded trunks | per-segment shade + 8.5 % ledges at joints | continuous limb tubes, one shade per branch |
| Acne/staircase on a grazed roof (low) | Medium map, no cascades, bias 5 | High map + 1 cascade, bias 15 at low/medium |
| Backlit crowns read as dark confetti | Lambert only from the front | foliage back-light term 0.35 (golden-hour crowns +18…34 luma) |
| One-row meadow/sky cliff at low (84.5 / 65.8 / 27.4 luma: golden hour, morning, walk) | fog was disabled at low | fog at every preset: 8.1 / 13.1 / 3.5 alone, 2.8 / 0.4 / 3.6 with the sky fix below; fps at low unchanged on llvmpipe (fog off 4.90, on 4.93, mean of 3 alternating runs) |
| Thin dark line at the horizon in every fogged view (dip 9–10 luma, morning) | the sky's ground hemisphere reaches `groundBottomColor` too fast (`groundCurve` 0.02: ~32 % dark 0.7° below the horizon, about one sky texel) and was drawn × 0.9 | `groundEnergy` 1.0 by day and `groundCurve` 0.1 (dip 0.1–0.2; shaded walls +5 luma, ground shadows unchanged; 0.3 cost +13) |
| Stair-stepped moon shadow on the east gable (night) | fixed moon (az 165°, elev 38°) grazes the wall at n·l ≈ 0.2 | night shadow factor 25 (was 40), PCF factor 8 (was 2); day values unchanged — edge contrast 23–25 → 11–14 luma |
| December board full of red fruit and open flowers | fruit/flower accents ignored the date | accents only inside the plan's frost-free season (§1 "Season"); December fruit-red pixels 223–300 → 3–7 |
| December noon sun (14.0°) warmer than June golden hour (15.2°) | 15°/6° colour steps | continuous 30°→6° ramp (§3) |
| Night more saturated than noon (0.550 vs 0.537) | colour adjustment 0.85 at night | 0.6 (0.430 high, 0.413 low) |
| Sun-lit roof at noon low clipped (R 254), a channel clipped on 4.6 % of the frame | noon exposure 0.92 | 0.85: clipped 0.26 %, lawn luma 163 → 158, saturation unchanged; the roof still reads light orange (hue 16.5° vs albedo 12.1°, the tonemap shoulder) |
| Morning sun glint clipped ~23 % of the visible pond | water roughness 0.05 | 0.02 (11.8 %; water hue 206°, 2D 205.5°) |
| Terracotta ridge cap on the shingle shed roof (hue 11° on 30°) | one fixed cap colour | cap = roof × 0.8 in linear (shed 29°, house 12° = its roof) |
| Squashed kettle (and flower disks) lit as round balls | unit-sphere normals kept after the squash | inverse-transpose of the squash (error 6.3° → 0 for the 0.8 kettle, 18.4° → 0 at 0.5) |
| Blade flower heads (lily, tulip, iris) all facing straight up | fixed +z facing | each faces along its own blade's tip tangent (16.7–47.7° off vertical) |
| Five deciduous species with one silhouette (0.34 trunk under an ellipsoid) | one crown recipe | `CANOPY_FORM` per species: trunk, taper, droop, bark, 2D `leaf_scale`; the default is bit-identical to L0 |
| Trees over the 25,000-triangle budget (bench_small December: birch 30,808, spruce 28,016; bench_large: 14 / 15 trees over, max 40,954) | the 16,000-leaf cap (32,000 triangles) and the 14,000-spray conifer cap were over the budget by construction; `leaf_scale` 0.75 = 1.78× the leaves; the budget test built four small plants | leaves = (25,000 − wood − fruit/flowers) / 2, a capped crown keeps its coverage with larger leaves (placed count × l² constant; magnolia's 140 flowers cost 6,160 triangles, so no fixed margin); conifers ≤ 12,000 sprays, `ln` × √(n/12,000); gate: every plant of both bench plans on both board dates (max 24,994) |
| Exposure 1.15 → 0.85 within one degree at 20°; sky, fog and probe stepped at 8° and 20°; the key light fell back to the low rig under 6° | stepped rigs | three anchors joined by continuous ramps (§3); december_noon clipped 2.45 → 1.56 % (low), 1.11 → 0.45 % (high) |
| Birch trunk clipped on its lit side (441 px in december_noon, 874 px in walk at a channel ≥ 254, low) | the 2D white at full albedo | white × 0.7 in linear light (`WHITE_BARK_SHADE`, `#c6c3b8`, the ridge cap's rule): 291 / 13 px; a 14° sun still lights a vertical trunk at n·l ≈ 0.97 |
| Bare spruce trunk stub above the leader | trunk to 0.97 × the height at 0.6 % radius | trunk ends at 0.90 × the height, radius 0 (dark bark pixels at the noon tip: 16 → 0) |
| Trampoline mat a black hole (`#1d2126`) | a literal in no 2D table, under the albedo floor | the 2D `MATERIALS["rubber"]["mid"]` `#303336` (noon mat luma 56 → 81) |
| BBQ kettle rim a 16-gon at 1.5 m (walk) | 2× subdivided sphere | 3× for `smooth=True` (512 triangles, a 32-gon) |
| Red tomatoes from the 9 April last frost | fruit followed the frost window | fruit follows the task generator's harvest window, as the agent's task tools anchor it (§1 Season); flowers keep the frost window |
| Species crowns overlap (side-silhouette IoU across species, mean 0.730) | weak per-species forms | apple 0.20 / droop 0.45, pear taper 0.7, maple −0.15, walnut 0.40 / −0.2: mean 0.700 (within one species 0.786); 15 of 28 pairs stay above 0.70 — trunk and taper are weak levers once `fit_to` normalises every crown to the same box; the next lever is the crown envelope |
| Teal-black slits in every picket fence, black stubble on lawns and crowns (isolated dark pixels, 1280×720: noon 1,554 / 2,355, december_noon 2,587 / 3,102, low / high) | `ExtendedSceneEnvironment.sharpnessAmount` 0.08 overshot every thin lit/dark edge to near-black, red-less pixels | sharpening 0 (§2): noon 260 / 488, december_noon 28 / 186, walk 71 / 56 — what is left is shaded picket gaps; noon's mean luma within 0.8. Gate: `isolated_dark_px` in every board row; render tier ≤ 170 at 640×360 medium (0 → 38 / 42, 0.08 → 737 / 700 in noon / december_noon) with a 0.08 positive control |
| December noon roof clipped red (1.56 % of the frame, low; 0.45 % high) | the golden anchor's 2.1 put a 2.03 sun into the 14° ramp, under exposure 1.04 | golden brightness 1.9, the noon value (§3): 0.27 % at both presets, the roof no longer clips; golden_hour −0.8 luma, december_noon −2.3 (low) |
| Wide crowns over the tree budget (32 of 448 swept trees; wood up to 23,730 triangles on a 400 × 1600 cm plum) | segment length from the height alone, so a wide crown grew ~1,600 short segments; the 1,800-node cap was checked once per growth step | segments from max(height, spread) / 28, a hard 1,000-node cap, at most 140 fruit (§2's bound): 0 of 448 over, wood ≤ 8,330; both bench plans within budget, height and spread exact |
| A blooming magnolia's leaves ×1.46 larger than uncapped (bench_large) | 140 flower centres as 32-triangle spheres: 4,480 of the 25,000 | octahedron centres, 8 triangles (`spheres(dot=True)`, every flower): ×1.25 alone, ×1.19 with the segment rule; the 2.5 cm dot reads the same at the walk distance |
| ~25 px scallops of ~11 luma under the ridge cap (morning, low) | the low preset's High (1024-texel) shadow map | VeryHigh at low: columns darkened ≥ 7 rows under the cap 25 → 2 (high: 0), p95 reach 10 → 6 rows (high 5); low IoU 0.963 / 0.968 / 0.937 → 0.953 / 0.959 / 0.922; low fps 4.90 → 4.97 (creator) and 4.70 (3D reviewer), llvmpipe, one run each: within noise; the owner's integrated GPU decides |
| The 6° golden anchor never rendered; golden_hour (15.2°) and december_noon (14.0°) sampled almost one point of the rig | the shot list | `sunset`: 21 June 18:38 UTC, 5.89° / 301.5° from `core/solar`, golden_hour's camera — long picket shadows streak the meadow, ground shadows are faint (a horizontal surface gets sin 5.9° ≈ 0.10 of the sun) |
| A plant fitted to its bounding box left its 2D canopy circle by up to 39 % (feathery; allium 37 %, flower 23 %, every leaf shell ~20 %) — invisible to the spread gate, which reads the box | outlines of any reach at any angle: a sparse plant fits its box and pokes out at the diagonals; scaling the farthest vertex onto the circle instead leaves a box of 72 % of the diameter | regular outlines (`_RIM_REACH` 0.97, `_RIM_JITTER` 0.10 in `builders/plants.py`), shell leaves turned to stay inside the circle, box still exact — and the fit's LAST step puts any vertex beyond 1.09 canopy radii onto that circle (`REACH_MAX`), so the bound holds by construction (a measured "≤ 1.092 over 117,000 builds" had been stated as a limit; one id in 300,000 read 1.1006). Measure the distance from the axis, not only the box; and never state a sample's maximum as a bound |
| A squash 60 × 360 cm was built 1.4–1.6 times too tall and squashed back: exact bounding box, its body in the lower two thirds (at 15 × 800 cm nine archetypes were 3.5–11.6 times too tall) — every gate green | shell leaves faced along the ray from the plant's heart, not along the lobe's surface normal (on a flat cushion they stood on edge); leaf length grew with the plant's width; and the fit's z-scale made the height gate true for anything | build TO the data: highest point placed at the height, leaves set by the surface normal and kept inside by turning (lie down without headroom, quarter turns at the canopy's edge), bow / ripple / fold held to the height; the fit returns a `FitReport`; tests assert it, the foliage's area quantiles and off-proportion sizes. A gate the code forces cannot fail — measure before the repair |
| Up to 6.7 % of a mound's foliage triangles lay flat at z = 0, coplanar with the ground (z-fighting at the plant's edge) | lobes that reach below the ground were pressed onto it; their undersides became discs in the ground plane | `_lobes` leaves out the triangles within 1 % of the height above the ground; leaves keep a floor of 1.5 %; gate: no ground-flat foliage triangle |
| A lavender cushion floated 9 cm (13 % of its height) above the ground; 59 of 123 plant recipes floated once counted — and `min z == 0` held | one shell leaf dipped below the base and the fit lifted the whole plant to put that leaf's tip at zero | `_fit` presses what dips below the ground onto it and only ever sets a plant down; gate: at least six vertices on the ground. Never make a constraint hold by translating the result |
| Crowns and mounds bald on top, a skirt of leaves below (first look through an engine; every gate green) | shell leaves placed on an ellipsoid envelope: buried where a lobe reached it, hovering between lobes | `_on_lobes`: each leaf is cast from the crown's heart onto the lobes' outer surface |
| Two hedge sections were the same drum (side silhouettes 99.9 % alike) | a perfect surface of revolution has no individuality; a first, under-sampled silhouette metric had reported them 26 % different | cut by hand in five ways per id — batter (0.72–0.98), shoulder height, how square the shoulder is, a bulging side, an uneven top a little out of level: over 30 ids the most alike pair is 97.5 % alike, the median 92.5 %. A metric needs a case whose answer is known, and a gate over ids needs enough ids to state a distribution (five fixed ids had said "≤ 0.95") |
| A bright line along the whole night horizon (a one-row step of 10.5 luma at high, 21.2 at low, eye height, bench_small) | the spike's fog = horizon × probe exposure × 0.8 had no sky energy in it: the night sky is drawn × 0.25, so the fog was four times brighter than the sky it met — and Qt Quick 3D linearises a colour property with a polynomial, not the sRGB curve, so the dark fog's sRGB code read three times too dark | fog = horizon × the sky's energy × probe exposure × 0.8, in linear light (`core/scene3d/look.fog_linear`), handed over as the float triple the engine's own linearisation turns back into it (`quick3d/look.engine_srgb`, `QColor.fromRgbF`): 2.4 / 3.2; day moods unchanged (0.6–3.4). L1.4 round 1 |
| A sun-grazed LIT wall hatched at high and ultra on Direct3D 11 (a wall at n·l 0.33: pixel noise 1.15 % of its luma, the face 3.7 luma darker; RTX 4070) | shadow bias 5 (the spike's, measured on llvmpipe) against the larger maps and more cascades of high / ultra | bias 10 at high and ultra (8 and above: 0.18 %, the dither's own floor; a grazed top face needs 10 down to a 12° sun); low and medium keep 15; shadow IoU unchanged (0.976 / 0.986 / 0.978). L1.4 round 2 |
| A sky rebuild held the GUI thread 215 ms while the time slider moved | the spike's `SkyTextureQualityHigh` (2048 × 1024 float texels, 32 MB) | Medium (1024 × 512, 8 MB): 95 ms; every shot's mean luma within 0.02, the sun's azimuth read back within 0.07° (0.03° at High), horizon step 3.4 → 2.9 (bench_small, 960 × 540, all seven shots). L1.4 round 3 |
| A thin dark line at the NIGHT horizon (dip 2.07 / 1.04 luma, low / high, eye height) | the spike's night ground hemisphere at energy 0.15 under a sky at 0.25 — the day lesson (ground energy = sky energy) had not been carried to night | night ground energy 0.25, the sky's: dip 0.01 / 0.12, fog step 2.51 / 2.50 → 2.75 / 2.80, ridge 0.29 → 0.13 / 0.21, night luminance +0.2 %. L1.4 round 5 |
| All of civil twilight drew as full moonlit night; at 0.5° the frame fell from luma 77 to 37 within 90 s of plan time, the key light jumping from the sun (az 310°) to the moon (az 165°) | night was a switch at the 2D sunset threshold | a twilight ramp 0.5° → −6° (data): the low-sun rig mixed into the night rig (colours in linear light, exposure in stops), sky and ground energy 1 → 0.25, saturation 1.06 → 0.6, no sun disc, the moon key at 0.32 × the fraction. Dusk sweep, golden-hour camera, low: 0.116 (0.6°) → 0.105 (0.4°) → 0.099 (0°) → 0.052 (−3°) → 0.034 (−6°), monotone; sunset's step 0.011 against the day ramp's largest half degree 0.027. Mixed in stops the sky was smoother but the frame dipped to 0.023 and rose again. L1.4 fix round 1 |
| A moiré band on the picket fences at low (the look review's P1) | FXAA cannot resolve pickets thinner than a pixel; 2x MSAA can't either | 4x MSAA at low (= medium): the fences' luma error against a 2x-supersampled render 20.0 → 6.2 (2x: 12.0; medium 7.2), dark share 12.7 → 13.1 % (2x: 18.8 %); cost on the RTX 4070 inside the run-to-run spread. L1.4 fix round 1 |
| Compatibility mode +22 luma brighter than the GPU at golden hour, sunset and in the walk | the flat fill at the sky's full mean radiance, from every direction | fill × 0.5 (`FILL_OF_SKY`); the review's sRGB × 0.72 test read 120.8 → 106.3 against the GPU's 98.9. L1.4 fix round 1 |
| The plan rectangle a shade off the meadow under a grazing view (up to 4.65 luma, looking along an edge; the look review read −7.8 at golden hour) | plan ground roughness 0.92 / specular 0.2, meadow 1.0 / 0.15 | the meadow's material on the plan ground: 0.21 at most in every view along the west and south edge. L1.4 fix round 1 |

## 8. Owner taste log (append-only, newest last)

- **2026-10-03** — chose Lush Cinematic, experience + analyze, 100 % procedural; asked for
  both a creator and an independent reviewer agent; wants "really usable, beautiful, modern".
- **2026-10-05** — signed off the L0 Beauty Board on his dedicated GPU ("images look good, day and
  night"). No open taste points: his fifteen open questions (winter leaves, moon shadows,
  path/wall widths, partial-shade truth, grade, unplanned ground, pond hue, unmodelled heights,
  golden-hour ramp, roof hue, fruit without data, small-leaved crowns, sunset framing, crispness)
  are all answered *keep as-is*. Gave **GO** on ADR-048 (Qt Quick 3D replaces Qt 3D; `QQuickView`
  host; the D3D11 leak accepted open, closing in L1.3). Owner-GPU numbers in ADR-048 entry 19.
