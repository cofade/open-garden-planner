---
name: ogp-lush-cinematic
description: "The art-direction contract for Open Garden Planner's 3D mode ('Lush Cinematic', Phase 17 / ADR-048) and the shared knowledge base of the ogp-3d-creator and ogp-3d-reviewer agents. Load when: building or reviewing anything that shows up in the 3D view (plants, buildings, ground, sky, light, shadows, materials, post-processing, camera shots); producing or judging a Beauty Board; choosing colours, roughness, light colour or exposure; deciding whether a 3D look is 'done'; or recording owner feedback on a render. Contains the truth-before-beauty gates, the style table, measured light rigs per mood, material value ranges, foliage rules, the Beauty Board procedure, the review rubric with severities, the spike's artifact→fix log and the owner taste log."
---

# ogp-lush-cinematic reference guide

Read the scope/introduction and the relevant reference below **before acting**.
All rules in the references remain binding. Read method/runbook sections for
the task; load historical case studies only when the symptom matches. Search
the index by subsystem, issue or symptom. Do not infer current delivery status
from dated measurements. New lessons belong in a new reference and index row.

| Topic / symptom | Reference |
|---|---|
| Lush Cinematic — the 3D art-direction contract | [Read](references/000-lush-cinematic-the-3d-art-direction-contract.md) |
| 1. Truth before beauty (non-negotiable) | [Read](references/001-1-truth-before-beauty-non-negotiable.md) |
| 2. Style table | [Read](references/002-2-style-table.md) |
| 3. Light rigs per mood (*spike* values, `look_for` / `sun_light` / `sun_state` of the spike's `runner.py`, frozen in `tests/data/l0_spike_reference.json`) | [Read](references/003-3-light-rigs-per-mood-spike-values-look-for-sun-light-sun-state-of-the-spike-s-runner.md) |
| 4. Material value ranges (PBR, roughness 0–1) | [Read](references/004-4-material-value-ranges-pbr-roughness-0-1.md) |
| 5. Beauty Board procedure | [Read](references/005-5-beauty-board-procedure.md) |
| 6. Review rubric (the reviewer agent's checklist) | [Read](references/006-6-review-rubric-the-reviewer-agent-s-checklist.md) |
| 7. Spike artifact → fix log (keep growing) | [Read](references/007-7-spike-artifact-fix-log-keep-growing.md) |
| 8. Owner taste log (append-only, newest last) | [Read](references/008-8-owner-taste-log-append-only-newest-last.md) |
| Owner gravel rim correction (29 October 2026) | [Read](references/009-owner-gravel-rim-2026-10-29.md) |
| The living garden — weather, dew and life values (L5) | [Read](references/010-living-garden-weather-l5.md) |
| The atmosphere sky — values and open taste questions (L7) | [Read](references/011-atmosphere-sky-l7.md) |
| Photo mode and tours — the values (L6) | [Read](references/012-photo-mode-and-tours-l6.md) |
| Low-sun shadow edges — steps, lit teeth, streaks and the `--stairs` probe (#734) | [Read](references/013-low-sun-shadow-edges-734.md) |
| The living garden's polish — occlusion under cloud, snow on built tops, leaves, lamp pools, no dew mist (#687) | [Read](references/014-living-garden-polish-687.md) |
| A tour video good enough to publish, and the orbit that films it — how to measure, the numbers, promo settings (#807) | [Read](references/015-review-grade-video-and-the-promo-orbit-807.md) |
| The atmosphere sky at the painted horizon — profile and deck anchor (#716, #719) | [Read](references/016-atmosphere-horizon-716-719.md) |
| The meadow's grass — one ground shader, the texture, its variation and the owner's open-ground switch (#798) | [Read](references/017-meadow-grass-798.md) |
| Foliage in motion, the leaves' stripes and the autumn crown — the wind's values, AO not acne, the leaf-size options, why the autumn crown is muddy (#800, #805) | [Read](references/018-foliage-wind-leaf-stripes-and-autumn-800-805.md) |
