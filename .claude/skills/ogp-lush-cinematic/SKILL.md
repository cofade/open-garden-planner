---
name: ogp-lush-cinematic
description: "The art-direction contract for Open Garden Planner's 3D mode ('Lush Cinematic', Phase 17 / ADR-047) and the shared knowledge base of the ogp-3d-creator and ogp-3d-reviewer agents. Load when: building or reviewing anything that shows up in the 3D view (plants, buildings, ground, sky, light, shadows, materials, post-processing, camera shots); producing or judging a Beauty Board; choosing colours, roughness, light colour or exposure; deciding whether a 3D look is 'done'; or recording owner feedback on a render. Contains the truth-before-beauty gates, the style table, measured light rigs per mood, material value ranges, foliage rules, the Beauty Board procedure, the review rubric with severities, the spike's artifact→fix log and the owner taste log."
---

# Lush Cinematic — the 3D art-direction contract

**Status:** v1, written from the Package L0 spike (ADR-047, *Proposed*). Values marked
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
| Shadows | engine shadow footprint of a box caster vs the analytic 2D shadow | IoU ≥ 0.85 at 15°/35°/60° (spike: 0.98/0.98/0.96 on OpenGL **and** on Direct3D 11; table in `ogp-3d-renderer` §4) |
| North | ground texture is north-up; nothing is mirrored | orientation probe NCC: identity must win |
| Sky | the sky's sun disc sits at the solar azimuth | sky probe error < 6° (spike: ±0.3°) |
| Date | season/growth shown = the plan's sim date | same date drives 2D shadows, heatmap and 3D |

Never tune a domain number (species height, spread, planting date) to make a shot prettier.

## 2. Style table

| Layer | Rule |
|---|---|
| Light | One key light = the real sun. Warm when low, neutral-white when high. The sky is the fill (image-based lighting) and must **not** out-shine the sun — the first spike renders read flat and blue precisely because the probe dominated. |
| Colour | Plants and objects take colours only from the 2D tables (sprite `PALETTES`/`FRUITS`/`FLOWERS`, object `MATERIALS`). Seasonal colour is a function of those palettes, never a new literal. Albedo stays inside sRGB ~40–240 (no pure black/white surfaces). |
| Form | Chunky, readable silhouettes; bevels on built things; vegetation slightly fuller than nature; real-world dimensions; nothing floats, nothing is cloned. |
| Foliage | Geometric micro-leaves (2 triangles each), **no alpha cards** (aliasing + sort + shadow-pass problems). Normals spherized toward the crown centre (0.55–0.75) so a crown shades like one soft volume. Leaf count follows crown surface area (coverage ≈ 1.6), not a magic number. |
| Atmosphere | Filmic/ACES tonemapping, gentle glow, depth fog whose colour equals the sky horizon (hides the meadow/sky seam), SSAO from Medium up. DOF/vignette only in photo mode. |
| Motion | Wind sways grass and crowns via shader values (uv.x = sway weight, uv.y = phase); animation only while the 3D view is visible; reduced-motion setting stops it. |

## 3. Light rigs per mood (*spike* values, `look_for` / `sun_state` in `spike_q3d/runner.py`)

| Mood | Sun elevation | Sun colour / brightness | Sky top / horizon | Probe / exposure |
|---|---|---|---|---|
| Noon | ≥ 30° | `#fff1dc` / 1.9 | `#3f78c9` / `#cfe2f2` | 0.55 / 0.92 |
| Afternoon–golden | 6–30° | `#ffdcaa`→`#ffb878` / 2.0–2.1 | `#4f7fc8` / `#f4d2a6` | 0.50 / 1.15 |
| Low sun | 0.5–6° | `#ff9655` / 1.7 | `#4a6fb0` / `#f2b47c` | 0.42 / 1.25 |
| Night | < 0.5° | moonlight `#8ea4d6` / 0.32 from az 165°, elev 38° | `#070d22` / `#1b2747` | 0.35 / 2.4 |

## 4. Material value ranges (PBR, roughness 0–1)

| Material | Roughness | Notes |
|---|---|---|
| Lawn blades, leaves | 0.75–0.85 | specular ≈ 0.25; vertex colours from palettes |
| Bark, soil, mulch | 0.85–0.95 | |
| Plaster walls | 0.85–0.95 | warm off-white, never `#ffffff` |
| Roof tiles | 0.70–0.85 | terracotta `#b4553d` range (matches the 2D roof texture) |
| Wood (deck, fence, beds) | 0.60–0.80 | |
| Terracotta pots | 0.80–0.90 | |
| Water | 0.02–0.06 | dark teal base; reflections come from the sky probe |
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
not a hung board — read the log. Shots: `golden_hour`, `noon`, `morning`,
`december_noon`, `night`, `walk`; add `--presets low,medium,ultra --shots golden_hour` for the
preset strip. Always show **before vs after** with the same plan, date and camera, and attach
`metrics.json` — a board without its numbers is not evidence.

## 6. Review rubric (the reviewer agent's checklist)

Score each shot on: readability (silhouettes, value grouping), light (direction, warm/cool
balance, contact shadows, acne/peter-panning, exposure histogram), colour (palette conformance,
saturation, season), form (proportions, bevels, density, clones, floating, ground contact),
materials (value ranges above), artifacts (z-fighting, sorting, shimmer, LOD pops, seams,
black frames), motion (wind, reduced motion), **truth** (§1 gates from `metrics.json`),
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

## 8. Owner taste log (append-only, newest last)

- **2026-10-03** — chose Lush Cinematic, experience + analyze, 100 % procedural; asked for
  both a creator and an independent reviewer agent; wants "really usable, beautiful, modern".
