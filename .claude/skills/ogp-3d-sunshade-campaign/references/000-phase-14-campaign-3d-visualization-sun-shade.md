

# Phase 14 Campaign: 3D Visualization & Sun/Shade

> ## ⚠️ CAMPAIGN COMPLETE (2026-07-31) — READ THIS FIRST
>
> **Phase 14 shipped in full.** US-E1…E9 all merged across **v1.24.5 – v1.24.12**;
> [epic #255](https://github.com/cofade/open-garden-planner/issues/255) is **closed**.
> The 3D engine gate returned **GO: PyQt6-3D** (ADR-038).
>
> **Renderer decision made (2026-10-05, Phase 17 "Living Garden 3D").** ADR-048
> (*Accepted — GO*) chose Qt Quick 3D as Qt 3D's replacement. For anything about the
> *new* renderer load `ogp-3d-renderer` (measured engine facts) and `ogp-lush-cinematic`
> (art direction and truth gates). The solar math, shadow geometry and Y-axis discipline
> in this skill stay authoritative for both renderers.
>
> **The new view is the product since Phase 17 L1.9 (#385).** View → "3D View"
> shows the 3D pane of the main window's Plan / 3D / Split workspace (ADR-060, docs/08
> §8.29). **L1.10 deleted the Qt 3D viewer window of US-E6/E7** — its adapter, the window,
> `core/scene3d/legacy.py`, `core/walk_camera.py`, the L0 spike and the two Qt 3D wheels.
> What FR-SUN-06 / 07 / 08 promised and what the new view does instead is the parity
> table of §8.29.9. Debug the 3D view with `ogp-3d-renderer`, not with this skill. Below,
> every mention of Qt 3D, its window or its modules is the Phase 14 campaign's history.
> (`tests/unit/test_no_qt3d_left.py` lists this file among the history documents.)
>
> **Every "TO BUILD" marker below is now STALE — that code EXISTS.** Do not
> re-implement it. `core/solar.py`, `core/object_height.py`, `core/shadow_geometry.py`,
> `core/shade_aggregation.py`, `core/heatmap_render.py`, `core/growth_model.py` and
> `ui/canvas/sun_heatmap.py` are shipped and gated by tests. `core/scene3d/` (a package
> since Phase 17 L1.1; the pre-L1.1 `legacy.py` module left with L1.10), `core/scene3d/walk.py`
> (which replaced `core/walk_camera.py` in L1.8) and `ui/view3d/` are Phase 17's — see
> `ogp-3d-renderer`.
>
> **This skill is now a REFERENCE, not a runbook.** What stays valid and load-bearing:
> the NOAA/Meeus solar formulas with their pinned reference numbers, the
> `scripts/solar_reference.py` oracle, the Y-axis discipline for azimuth→scene
> conversion, and the measure-don't-eyeball gate philosophy. Load it for
> *maintenance* of those subsystems — never as a plan for unstarted work.
> Phase/gate ordering and "next free ADR/§8.x" numbers are historical. So is every
> **"v2.0"** in the text below: that release was **never minted** — Phase 14 shipped as
> patch bumps and the framing was formally retired on 2026-07-31 (the 3D view isn't
> prominent enough to carry a major-version claim). Read "v2.0" as "Phase 14" — the
> scope exclusions it labels (flat ground, no terrain slopes, geometric sun elevation)
> are all still real.
>
> **A caster has a base since Phase 17 L1.6 (ADR-037 addendum "base stacking").**
> The shared caster is `core/shadow_geometry.ShadowCaster(footprint, height_cm, base_cm)`:
> a plant that is LINKED to a raised bed or container (`parent_bed_id`) AND whose centre
> lies inside it casts from that parent's soil (`ui/canvas/footprints.item_base_cm` →
> `core/object_height.standing_base_cm`: 2 cm under a bed's rim — an assumption — and AT a
> container's height, which is its soil fill height), so its shadow starts, and its tip
> lies, `base / tan α` further from the sun. The link alone never lifts: the app does not
> keep it geometric (a bed resized away from its plant keeps the link). "Centre" is the
> plant's stable geometric centre (`footprints.standing_point`), NOT the centre of its
> `boundingRect()` — that one moves by up to 1.8 cm along each axis (about 2.5 cm
> diagonally) while the antagonist badge shows, and
> it stays the link decisions' point (`bed_membership_point`), exactly as shipped. Where the text
> below says `(polygon, height)`, read `ShadowCaster`; the shadow functions take a
> `ShadowCaster` or an exact `(footprint, height)` pair and raise `TypeError` for anything
> else. A caster on the ground runs the Phase 14 code unchanged — proven on every platform
> against the released v1.29.10 module kept as an oracle
> (`tests/unit/test_shadow_caster_base.py::TestTheGroundPathIsTheReleasedCode`); the golden
> `tests/integration/test_shadow_caster_golden.py` pins the absolute numbers, bit for bit
> on win32 only, to 2e-3 cm on Linux. §8.20 has the worked example, the ADR the known
> limits (a bed drawn round a plant, a trellis in a raised bed, a pot on a bed).

**Status of the inventory below (2026-07-04):** Everything under "EXISTS (verified)"
was read from the repo at v1.23.0 (post-US-D1.3). Items marked **TO BUILD** were
future work *at the time of writing* — see the completion banner above; they have
all since shipped.

**Re-verified 2026-07-19 at v1.24.3 (epic filed as #255, US issues #256–#264):**
inventory facts held EXCEPT ADR numbering — US-D1.6/D2.0 consumed ADR-035/036,
so the campaign's ADRs are now **ADR-037** (solar + shadow architecture) and
**ADR-038** (3D engine choice); next free §8.x is **§8.20**. All ADR references
below have been updated accordingly.

This is a runbook, not an essay. Work the phases in order. Every phase ends
in a **gate**: a command, an expected observation (often an exact number),
and an explicit branch if you see something else. Success at each gate is
*measurable* — never judged by eye (a shadow that "looks about right" on a
Y-flipped canvas is the single most likely way to ship a wrong feature here).

**When NOT to use this skill:**
- Ordinary 2D feature/bug work → `ogp-change-control` + `ogp-debugging-playbook`.
- The automatic decorative per-item drop shadows (the obsolete
  `appearance/show_shadows` setting is ignored under ADR-062) — those are cosmetic paint effects, NOT solar
  shadows. Fixing them is not Phase 14 work (but see the naming-collision
  warning in Phase 3).
- Weather *forecast* work (US-12.1/12.2) — that's `weather_service.py`,
  unrelated to sun geometry.

**Sibling skills** (cross-reference, do not duplicate): `ogp-architecture-contract`
(invariants: Qt-free core, additive `.ogp`, two-chokepoint undo),
`ogp-change-control` (branch/PR/release gates), `ogp-validation-and-qa`
(evidence bar), `ogp-build-and-run` (exe smoke), `ogp-debugging-playbook` +
`ogp-failure-archaeology` (pitfall precedents), `ogp-garden-domain-reference`
(species/geo data). If present in `.claude/skills/`, also:
`ogp-qt-cad-reference` (Y-up coordinate theory), `ogp-proof-and-analysis-toolkit`,
`ogp-research-methodology` (hypothesis→numbers discipline). Some of these are
all sibling skills now exist on disk (the full 16-skill library).

**Jargon (defined once):**
- **Declination (δ):** angle of the sun above/below the Earth's equatorial
  plane. Ranges ±23.44° over the year (the axial tilt).
- **Equation of time (EoT):** true solar time minus mean clock time, in
  minutes. Ranges about −14.2 … +16.4 min over the year.
- **Hour angle (H):** how far the sun is past local solar noon, 15°/hour,
  negative in the morning.
- **Elevation (α):** sun's angle above the horizon. **Azimuth (Az):** compass
  bearing of the sun, degrees clockwise from true north (N=0, E=90, S=180, W=270).
- **Scene / canvas frame (they are the same numbers):** the project's
  data/display convention — cm units, **+x = East/right, +y = North/up**, origin
  bottom-left (§8.1, ADR-002). Items live in these coordinates and the data path
  consumes raw `scene_pos.y()` directly as CAD Y-up — there is **no
  `scene_to_canvas` conversion** in production. `scale(zoom, −zoom)` in the view
  makes larger scene-y render higher. **`ogp-qt-cad-reference` §1 owns this
  reconciliation** — the "§8.10 Qt-scene-is-Y-down / convert with
  `scene_to_canvas`" wording is the abstract-Qt description (true only for
  un-flipped renders); §11.4 states the operative rule. Do your shadow math in
  scene cm and flip only at pixel-facing surfaces (render/minimap/thumbnail).

---

