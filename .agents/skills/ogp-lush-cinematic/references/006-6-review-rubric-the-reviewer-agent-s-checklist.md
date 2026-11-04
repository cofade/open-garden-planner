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

