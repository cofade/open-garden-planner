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
