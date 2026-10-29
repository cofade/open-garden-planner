## 1. Campaign map, scope slices, and the solution menu

### Slice order (why this order)

Phase 14's roadmap bullets look 3D-first. **Do not build 3D first.** The
sun/shade value is deliverable entirely in 2D and stands alone even if the
3D spike NO-GOs; heights and solar math are prerequisites for both. Order:

1. **Phase 1 — Solar position engine** (Qt-free `core/solar.py`). Zero UI risk,
   fully unit-testable, everything else consumes it.
2. **Phase 2 — Object height property** (additive metadata). Prerequisite for
   shadows AND 3D extrusion.
3. **Phase 3 — 2D analytic shadow overlay** (the high-value cheap slice).
   Users get "where does the fence shadow fall on the equinox at 17:00" —
   the actual gardening question — without any 3D engine.
4. **Phase 4 — Hours-of-sun heatmap** (aggregation over a day/season). This is
   the killer feature for bed placement ("full sun" = 6+ h direct sun).
5. **Phase 5 — 3D engine spike** (GO/NO-GO gate). Only now spend risk budget
   on Qt3D-vs-alternatives; walkthrough + growth visualization ride on GO.
6. **Phase 6 — Validation & promotion** (applies per-slice; each slice ships
   as its own US → branch → draft PR through `ogp-change-control`).

### Solution menu, ranked (each with its theory obligation)

| Rank | Approach | Theory you must own | Verdict |
|---|---|---|---|
| 1 | **2D analytic shadows** (this campaign, Phases 1–4): NOAA solar position + `L = h/tan α` sweep + polygon union | NOAA/Meeus formulas (§Phase 1 — written out below); Minkowski-sum shadow geometry (§Phase 3) | **Recommended first.** No new deps, Qt-free core, exact numbers, testable to ±0.5°. |
| 2 | **Precomputed sun-path tables** (sample `core/solar.py` daily/hourly into cached tables) | Same formulas; only a caching layer | Use as an *optimization inside* Phase 4 if profiling demands it — not a separate track. Do NOT add `pysolar`/`astral` deps for this: `pysolar` is GPL-3 (compatible but redundant), `astral` Apache-2.0 (compatible but redundant); ~120 lines of stdlib math replaces both, and a dep you didn't write is a dep you can't pin numbers for. |
| 3 | **Full 3D scene + real-time shadow mapping** (Qt3D or alternative) | Scene-graph + depth-map shadow theory; per-engine API | Phase 5 spike ONLY, behind the GO/NO-GO gate. Big packaging + maintenance risk. |
| 4 | **GPU raycast / raytraced sun** (compute per-pixel occlusion on GPU) | GLSL/compute pipeline, OpenGL context mgmt in Qt | Over-engineering for a garden planner at this scale (a garden is ~10³–10⁴ m², not a city). Rejected unless Phase 4 profiling proves Python+numpy cannot hit budget — it can. |

### Known wrong paths — FENCED (do not enter)

- **Computing shadows in `paint()`.** The #206/#200 firehose lesson: paint runs
  constantly; per-paint trig + polygon booleans will melt the canvas.
  Precompute on change (item moved/height changed/sim-time changed), cache
  polygons, paint only cached `QPainterPath`s.
- **Tying solar math to Qt transforms.** The engine must be Qt-free
  (`core/solar.py`, pattern of `core/plant_sizing.py`/`core/container_model.py`)
  and unit-tested against the pinned numbers in the Appendix. If your solar
  code imports PyQt6, you have already failed the review gate.
- **Trusting eyeballed shadow directions on the canvas.** The scene is Y-flipped
  relative to the data model (§8.1 vs §8.10; the §11.4 Y-flip bug family, e.g.
  the D1.3 render frame note). A shadow pointing "up" on screen is NORTH in
  canvas coords but "toward smaller scene-y" in Qt coords. Validate with the
  pixel formula (Phase 3 gate), never by eye.
- **Bumping FILE_VERSION for the height key.** `object_height_cm` is additive
  item metadata — the serializer already round-trips it (verified: `project.py`
  copies `item.metadata` wholesale). FILE_VERSION (currently `"1.4"`) moves
  only for new item *types* (precedent: bezier/arc → 1.4; containers/smart
  symbols did NOT bump).
- **Adopting a heavyweight 3D dep without the frozen-exe gate.** Precedent:
  the mcp/uvicorn packaging saga (§8.19 / §7 — `collect_submodules` +
  `copy_metadata`, do-not-walk `mcp.cli`, do-not-exclude `multiprocessing`).
  A 3D engine that imports cleanly in dev and dies in `dist/OpenGardenPlanner.exe`
  is a NO-GO, not a "fix later".
- **Sun positions from memory.** Every solar number in code/tests must trace to
  `scripts/solar_reference.py` output (Appendix) or a re-run of it. No
  "the sun is about 60° high in summer" constants.
- **Reusing `appearance/show_shadows` or `set_shadows_enabled` for solar
  shadows.** That machinery is cosmetic drop-shadow paint (verified above).
  Overloading it makes one toggle mean two unrelated things.

---

