---
name: ogp-lush-cinematic
description: "The art-direction contract for Open Garden Planner's 3D mode ('Lush Cinematic', Phase 17 / ADR-048) and the shared knowledge base of the ogp-3d-creator and ogp-3d-reviewer agents. Load when: building or reviewing anything that shows up in the 3D view (plants, buildings, ground, sky, light, shadows, materials, post-processing, camera shots); producing or judging a Beauty Board; choosing colours, roughness, light colour or exposure; deciding whether a 3D look is 'done'; or recording owner feedback on a render. Contains the truth-before-beauty gates, the style table, measured light rigs per mood, material value ranges, foliage rules, the Beauty Board procedure, the review rubric with severities, the spike's artifact→fix log and the owner taste log."
---

# Lush Cinematic — the 3D art-direction contract

**Status:** v1, written from the Package L0 spike (ADR-048, *Proposed*). Values marked
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
| Spread | widest crown span = 2D canopy diameter ±10 % | bounding box vs `_plant_canopy_radius_cm` |
| Base | plants in raised beds / containers stand on the soil, not inside the box | base = parent's effective height (− 2 cm soil drop) |
| Sun | light direction comes only from `core/solar` (never a "nice-looking" angle) | light = −sun vector (ADR-037 pin) |
| Shadows | engine shadow footprint of a box caster vs the analytic 2D shadow | IoU ≥ 0.85 at 15°/35°/60° (spike at 960×540: 0.98/0.98/0.96 on OpenGL **and** on Direct3D 11; 0.96/0.95/0.92 at 1280×720; orthographic, no cascades — table in `ogp-3d-renderer` §4) |
| North | ground texture is north-up; nothing is mirrored | orientation probe NCC: identity must win |
| Sky | the sky's sun disc sits at the solar azimuth | sky probe error < 6° (spike, disc 25° off-centre: max 0.85° OpenGL, 1.4° D3D11) |
| Date | season/growth shown = the plan's sim date | models are built for each shot's own date; every shot row records `sun_date` = `build_date` (`metrics.json`) |
| Season | fruit and flowers only inside the plan's OWN frost-free season: `location["frost_dates"]` `last_spring_frost` ≤ day ≤ `first_fall_frost` (`"MM-DD"`, the keys the task generator reads); fruit whose species carries harvest weeks follows the shared task generator's harvest window instead — last spring frost + `harvest_start` … + `harvest_end` weeks, anchored on every frost year whose window can reach the day (`task_generator.generate_for_date_window`, behind the annual calendar and the agent tools; the GUI calendar view anchors on one year only; bench: tomato 18 Jun–27 Aug, sweet pepper 2 Jul–13 Aug, so the 21 June board shows no peppers); no frost dates → no seasonal claim (accents stay). Crowns never go bare: the growth model has no leaf-off — an owner question, not a look lever | `runner.in_frost_free_season`, `runner.in_harvest_window` / `accents_in_season`; every shot row's build records `in_season` (`metrics.json` `builds`); exact accent-colour markers in `test_spike_q3d_board.py` / `test_spike_q3d_meshes.py` |
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

## 3. Light rigs per mood (*spike* values, `look_for` / `sun_light` / `sun_state` in `spike_q3d/runner.py`)

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
| Night | < 0.5° | moonlight `#8ea4d6` / 0.32 from az 165°, elev 38°; soft faint moon shadows (factor 25, PCF 8); saturation 0.6 | `#070d22` / `#1b2747` (`#9fb2e0`) | 0.35 / 2.4 |

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
regenerate with `scripts/make_bench_plans.py`, never hand-edit). Until the production harness
exists (Package L1.2), render through the spike:

```bash
QSG_RHI_BACKEND=opengl QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 \
  xvfb-run -a -s "-screen 0 1920x1080x24" \
  venv/bin/python -m open_garden_planner --spike-q3d --out <dir> \
  --presets high --shots all --iou --orient --watchdog-s 1800
```

(on a Windows dev box: drop the xvfb/env prefix). `<dir>/spike.log` records every phase; on a
software rasteriser one screenshot can take minutes (`ogp-3d-renderer` §8), so a slow board is
not a hung board — read the log. Shots: `golden_hour`, `sunset` (the 6° golden anchor,
golden_hour's camera), `noon`, `morning`, `december_noon`, `night`, `walk`; add
`--presets low,medium,ultra --shots golden_hour` for the preset strip. Every shot row of
`metrics.json` carries the frame's own numbers: `isolated_dark_px` (luma < 40 inside a lit
8-neighbourhood > 110 — the sharpening's speckles), `clipped_pct` (a channel ≥ 254) and
`mean_luma`. Always show **before vs after** with the same plan, date and camera, and attach
`metrics.json` — a board without its numbers is not evidence.

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
| Red tomatoes from the 9 April last frost | fruit followed the frost window | fruit follows the planting calendar's harvest window (§1 Season); flowers keep the frost window |
| Species crowns overlap (side-silhouette IoU across species, mean 0.730) | weak per-species forms | apple 0.20 / droop 0.45, pear taper 0.7, maple −0.15, walnut 0.40 / −0.2: mean 0.700 (within one species 0.786); 15 of 28 pairs stay above 0.70 — trunk and taper are weak levers once `fit_to` normalises every crown to the same box; the next lever is the crown envelope |
| Teal-black slits in every picket fence, black stubble on lawns and crowns (isolated dark pixels, 1280×720: noon 1,554 / 2,355, december_noon 2,587 / 3,102, low / high) | `ExtendedSceneEnvironment.sharpnessAmount` 0.08 overshot every thin lit/dark edge to near-black, red-less pixels | sharpening 0 (§2): noon 260 / 488, december_noon 28 / 186, walk 71 / 56 — what is left is shaded picket gaps; noon's mean luma within 0.8. Gate: `isolated_dark_px` in every board row; render tier ≤ 170 at 640×360 medium (0 → 38 / 42, 0.08 → 737 / 700 in noon / december_noon) with a 0.08 positive control |
| December noon roof clipped red (1.56 % of the frame, low; 0.45 % high) | the golden anchor's 2.1 put a 2.03 sun into the 14° ramp, under exposure 1.04 | golden brightness 1.9, the noon value (§3): 0.27 % at both presets, the roof no longer clips; golden_hour −0.8 luma, december_noon −2.3 (low) |
| Wide crowns over the tree budget (32 of 448 swept trees; wood up to 23,730 triangles on a 400 × 1600 cm plum) | segment length from the height alone, so a wide crown grew ~1,600 short segments; the 1,800-node cap was checked once per growth step | segments from max(height, spread) / 28, a hard 1,000-node cap, at most 140 fruit (§2's bound): 0 of 448 over, wood ≤ 8,330; both bench plans within budget, height and spread exact |
| A blooming magnolia's leaves ×1.46 larger than uncapped (bench_large) | 140 flower centres as 32-triangle spheres: 4,480 of the 25,000 | octahedron centres, 8 triangles (`spheres(dot=True)`, every flower): ×1.25 alone, ×1.19 with the segment rule; the 2.5 cm dot reads the same at the walk distance |
| ~25 px scallops of ~11 luma under the ridge cap (morning, low) | the low preset's High (1024-texel) shadow map | VeryHigh at low: columns darkened ≥ 7 rows under the cap 25 → 2 (high: 0), p95 reach 10 → 6 rows (high 5); low IoU 0.963 / 0.968 / 0.937 → 0.953 / 0.959 / 0.922; low fps 4.90 → 4.97 (creator) and 4.70 (3D reviewer), llvmpipe, one run each: within noise; the owner's integrated GPU decides |
| The 6° golden anchor never rendered; golden_hour (15.2°) and december_noon (14.0°) sampled almost one point of the rig | the shot list | `sunset`: 21 June 18:38 UTC, 5.89° / 301.5° from `core/solar`, golden_hour's camera — long picket shadows streak the meadow, ground shadows are faint (a horizontal surface gets sin 5.9° ≈ 0.10 of the sun) |

## 8. Owner taste log (append-only, newest last)

- **2026-10-03** — chose Lush Cinematic, experience + analyze, 100 % procedural; asked for
  both a creator and an independent reviewer agent; wants "really usable, beautiful, modern".
