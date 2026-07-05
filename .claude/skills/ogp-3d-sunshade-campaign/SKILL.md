---
name: ogp-3d-sunshade-campaign
description: >
  Executable, decision-gated campaign to deliver Phase 14 — 3D Visualization &
  Sun/Shade (v2.0) for Open Garden Planner. Load this skill when starting or
  resuming ANY Phase 14 work: 3D view, Qt3D/PyVista evaluation, sun path or
  solar position math, shadow projection/casting, shade or hours-of-sun
  heatmaps, object height property, seasonal/time-of-day sun animation,
  first-person walkthrough, or growth visualization. Also load when someone
  says "sun study", "shade map", "solar", "azimuth", "elevation angle",
  "shadow length", "height of fence/wall/tree", or asks which 3D engine to
  use. Contains verified repo asset inventory, the NOAA solar formulas with
  pinned reference numbers, Y-axis discipline for azimuth→scene conversion,
  and GO/NO-GO gates for the 3D engine spike.
---

# Phase 14 Campaign: 3D Visualization & Sun/Shade (v2.0)

**Status of this document (2026-07-04):** Everything under "EXISTS (verified)"
was read from the repo at v1.23.0 (post-US-D1.3). Everything marked
**TO BUILD** is FUTURE work — none of it exists yet. Do not conflate the two.

This is a runbook, not an essay. Work the phases in order. Every phase ends
in a **gate**: a command, an expected observation (often an exact number),
and an explicit branch if you see something else. Success at each gate is
*measurable* — never judged by eye (a shadow that "looks about right" on a
Y-flipped canvas is the single most likely way to ship a wrong feature here).

**When NOT to use this skill:**
- Ordinary 2D feature/bug work → `ogp-change-control` + `ogp-debugging-playbook`.
- The decorative per-item drop shadows (`View → shadows`, settings key
  `appearance/show_shadows`) — those are cosmetic paint effects, NOT solar
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

## 0. Verified foundation inventory (EXISTS — all verified 2026-07-04)

You are NOT starting from zero. These assets exist and were read from source:

| Asset | Where (verified) | What it gives Phase 14 |
|---|---|---|
| Real-world lat/lng in `.ogp` | `core/project.py` — `set_location()` (~line 742): dict `{latitude, longitude[, elevation_m][, frost_dates]}`; saved as top-level `"location"` key (save ~line 142, load ~line 191). Built by `ui/dialogs/location_dialog.py` (~line 347), frost lookup via `services/climate_service.py` (Open-Meteo ERA5) | Solar position needs exactly lat/lng + a UTC instant. Already persisted per project. May be `None` — every sun feature needs a "no location set" empty-state. |
| Geo-referenced satellite background | ADR-019; `services/google_maps_service.py` (`meters_per_pixel()` line ~100, Web-Mercator), `ui/canvas/items/background_image_item.py` (`geo_metadata` dict incl. `meters_per_pixel`) | True-to-scale ground imagery under the shadow overlay; a second lat source if `location` is unset (do NOT auto-copy — prompt the user). |
| cm-calibrated Y-up model | ADR-002; `docs/08-crosscutting-concepts/README.md` §8.1 (+y = North/up, origin bottom-left). §8.10's "Qt scene is Y-down / `scene_to_canvas`" is the abstract-Qt wording — see `ogp-qt-cad-reference` §1 (owner) for why the data path treats scene as Y-up | A ready ground plane: 1 scene unit = 1 cm, +y(scene) = North. The Y-flip is the #1 trap — see Phase 3. |
| Polygon booleans | `pyclipper>=1.3.0` (pyproject line 34), used with an integer scale factor in `core/tools/offset_tool.py` (line 22, `PyclipperOffset`). Separately `core/shape_boolean.py` = **QPainterPath-based** union/intersect/subtract (Qt-DEPENDENT, not pyclipper) | Shadow-polygon union. For the Qt-free core, use `pyclipper` (offset_tool precedent). `shape_boolean.py` is fine only in the Qt overlay layer. |
| numpy | pyproject dependency (`numpy>=1.24`) | Heatmap accumulation without a new dependency. |
| Layers system | `models/layer.py` (`Layer`), `canvas_scene.layers` (line ~571), `ui/panels/layers_panel.py`; all layer ops undoable (#207/#208) | Home for a non-serialized "Sun/Shade" overlay layer; per-layer visibility already respected by render pipeline. |
| Render/export pipeline | `services/scene_rendering.py` `render_scene_region()` (line 132, `y_flip=True` default); Agent API `render_canvas_image` (`agent_api/render.py` line 120, `px_per_cm = width_px / source_rect.width()` line 146). Pixel formula (§8.19; canonical statement: `ogp-qt-cad-reference` §1): `px_x = (x_cm − region_x_cm)·px_per_cm`; `px_y = image_height_px − (y_cm − region_y_cm)·px_per_cm` | **Machine-checkable visual validation**: render the canvas, compute where a shadow tip must land in pixels, assert on actual pixels. Use it — never eyeball. |
| Weather/climate services + async precedent | `services/weather_service.py` (stdlib urllib, 3 h disk cache), `services/climate_service.py`; QThread workers: `ui/widgets/weather_widget.py::_WeatherFetchWorker` (line 33), `services/update_checker.py::UpdateChecker` (line 98) | The blessed off-GUI-thread pattern for Phase 4 heatmap computation. |
| Species height data | `src/open_garden_planner/resources/data/plant_species.json` — top key `plants`, **118 records, 118/118 have `max_height_cm`** (plus `min_height_cm`, `max_spread_cm`). Model: `models/plant_data.py` `min/max_height_cm` (lines 96–97), `current_height_cm` (line 313) | Default plant heights for shadows AND the growth-over-time slice (min→max interpolation). |
| Additive item metadata | `garden_item.py` `_metadata` dict (line 202), `set_metadata`/`get_metadata` (line 739+); `project.py` serializes `item.metadata` wholesale (lines ~1400/1444/1475). Precedent: `core/container_model.py` documents additive `container_*` keys incl. **`container_height_cm`** (default 30) — Qt-free, mirrors `core/plant_sizing` | New `object_height_cm` key round-trips with ZERO serializer changes and old apps ignore it. **No FILE_VERSION bump** (currently `"1.4"`, `core/project.py` line 34 — bump only for new item *types*). |
| Undo machinery | `ChangePropertyCommand` (`core/commands.py` line 463, takes `apply_func` — works for metadata keys); two-chokepoint invariant `execute()`/`register_applied()` (#209); `stack_changed` signal for panel refresh (#223) | Height edits become one undoable command. NOTE: the existing container section mutates `meta[...]` directly (NOT undoable) — that is debt, not a precedent to copy. |
| `ObjectType` inventory | `core/object_types.py` line 148+: `FENCE`, `WALL` (polyline), `HOUSE`, `GARAGE_SHED`, `GREENHOUSE`, `HEDGE_*`, `TREE`/`SHRUB`/`PERENNIAL` (circle), `TRELLIS`, containers, furniture | The height-default table in Phase 2 keys off these. |
| Decorative shadows toggle | `app/settings.py` `KEY_SHOW_SHADOWS = "appearance/show_shadows"` (line 28, property line 246) → `application.py` `_on_toggle_shadows` (~line 2628) → `canvas_scene.set_shadows_enabled` (line 154) → per-item painted drop shadow (`garden_item.py` lines 211/718) | **Cosmetic only.** Phase 14 must NOT reuse this key or its menu item; rename risk is a UX decision — see Phase 3 step 5. |
| Roadmap + open question | `docs/roadmap.md` line 2447 "Phase 14: 3D Visualization & Sun/Shade (Future, v2.0)" (Qt3D integration, object heights, sun path sim, walkthrough, growth vis); `docs/11-risks-and-technical-debt/README.md` line 10: "Qt6 3D capabilities vs dedicated engine? Prototype with Qt3D, evaluate PyVista" | The scope contract and the mandated Phase 5 spike. |
| License | `pyproject.toml` line 10: **GPL-3.0-or-later** | Any new dep must be GPL-compatible (Phase 5 table). |
| ADR home | `docs/09-architecture-decisions/README.md` — single file, ADR-001…ADR-034. **Next free number: ADR-035** | Where the solar-architecture and 3D-engine ADRs go. |

Quick re-verification (run before trusting this table if months have passed —
also see "Provenance and maintenance" at the end):

```bash
# Linux/container (repo checkout, no venv needed for grep-level checks):
grep -n "FILE_VERSION" src/open_garden_planner/core/project.py            # -> line 34: "1.4"
grep -n "location: Dict with latitude" src/open_garden_planner/core/project.py  # -> ~747
grep -n "pyclipper" pyproject.toml                                        # -> "pyclipper>=1.3.0"
python3 -c "import json;d=json.load(open('src/open_garden_planner/resources/data/plant_species.json'));print(sum(1 for r in d['plants'] if r.get('max_height_cm')),'/',len(d['plants']))"
# -> 118 / 118
```

---

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

## 2. Phase 0 — Prerequisites & scope contract

**Required reading (in order):**
1. `docs/roadmap.md` line ~2447 (Phase 14 goals — the 5 bullets).
2. `docs/08-crosscutting-concepts/README.md` §8.1 (coordinates) and the
   §8.10 "Coordinate system reminder" — read BOTH; the Y-up/Y-down split is
   the campaign's central trap. The reconciliation (which one the data path
   follows) is owned by `ogp-qt-cad-reference` §1 — read it too.
3. `docs/09-architecture-decisions/README.md`: ADR-002 (Y-up), ADR-019
   (satellite geo), ADR-031 (predicate split — height interacts with
   plant-parents), ADR-034 (agent API — your validation instrument).
4. `docs/11-risks-and-technical-debt/README.md` §11.1 (the Qt3D open
   question, line 10) and §11.4 (pitfall chronicle).
5. Sibling skill `ogp-change-control` (the gates you will pass at each PR).

**Verify the assets** (Windows dev machine, Git-Bash; Linux second form):

| # | Command (Windows / Linux) | Expected | If not → |
|---|---|---|---|
| 0.1 | `venv/Scripts/python.exe -c "import pyclipper, numpy; print('deps ok')"` / `venv/bin/python -c "..."` | `deps ok` | `pip install -e .` in the venv; if pyclipper missing from pyproject, STOP — inventory table is stale, re-verify everything. |
| 0.2 | `grep -n "FILE_VERSION" src/open_garden_planner/core/project.py` | `FILE_VERSION = "1.4"` (or later) | If bumped since 2026-07: read the bump's ADR before assuming additive-metadata rules still hold. |
| 0.3 | `python3 .claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py` (stdlib only — works in any Python ≥3.11, venv not required) | `RESULT: ALL CHECKS PASSED`, exit 0 | The oracle itself is broken or Python's math changed (it didn't) — debug the script BEFORE writing `core/solar.py`; the campaign's numbers all flow from it. |
| 0.4 | `venv/Scripts/python.exe -m pytest tests/ -x -q` (Linux: `venv/bin/python -m pytest tests/ -x -q`) | All green on `master` | Fix master first (`ogp-debugging-playbook`); never start a campaign on a red base. |

**Deliverable (gate to exit Phase 0):** a US breakdown proposal for
`docs/roadmap.md`, filed through `ogp-change-control` (issue or roadmap PR),
e.g.:

- US-E1 Solar position engine (Qt-free) — Phase 1
- US-E2 Object height property — Phase 2
- US-E3 Shadow overlay + time-of-day/date control — Phase 3
- US-E4 Hours-of-sun heatmap — Phase 4
- US-E5 3D view spike (GO/NO-GO) — Phase 5
- US-E6 (conditional on E5 GO) 3D view MVP; US-E7 walkthrough; US-E8 growth vis

Each US = its own feature branch, senior-reviewer pass, draft PR. Do not
megabranch the campaign.

---

## 3. Phase 1 — Solar position engine (`core/solar.py`) — TO BUILD

**Contract:** Qt-free module, stdlib `math`/`datetime` only, implementing the
NOAA "General Solar Position Calculations" (Meeus-derived). The shipped
reference implementation is in
`.claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py` —
**copy `solar_position()` and `_julian_day()` from it verbatim**; it passed
all 10 self-checks on 2026-07-04 (Appendix). API:

```python
def solar_position(lat_deg: float, lon_deg: float, dt_utc: datetime) -> SolarPosition:
    """lat +north, lon +EAST (modern convention — NOAA's sheet uses +west!),
    dt_utc timezone-aware. Returns elevation/azimuth/declination/EoT/hour angle."""
```

(Wrap the dict in a frozen dataclass for the production module.)

### The formulas (theory obligation — these ARE the algorithm)

All angles degrees; `T` = Julian centuries since J2000.0 = (JD − 2451545)/36525.

1. **Julian Day** (Meeus ch. 7, Gregorian): with month ≤ 2 → year−1, month+12;
   `A = ⌊y/100⌋`, `B = 2 − A + ⌊A/4⌋`;
   `JD = ⌊365.25(y+4716)⌋ + ⌊30.6001(m+1)⌋ + D + B − 1524.5` (D includes the
   time-of-day fraction).
2. **Geometric mean longitude** `L₀ = 280.46646 + 36000.76983·T + 0.0003032·T²` (mod 360).
3. **Mean anomaly** `M = 357.52911 + 35999.05029·T − 0.0001537·T²`.
4. **Eccentricity** `e = 0.016708634 − 0.000042037·T − 0.0000001267·T²`.
5. **Equation of center**
   `C = sin M·(1.914602 − 0.004817·T − 0.000014·T²) + sin 2M·(0.019993 − 0.000101·T) + 0.000289·sin 3M`.
6. **Apparent longitude** `λ = L₀ + C − 0.00569 − 0.00478·sin Ω`, with
   `Ω = 125.04 − 1934.136·T` (nutation/aberration correction).
7. **Obliquity** `ε₀ = 23°26′21.448″ − 46.815″·T − 0.00059″·T² + 0.001813″·T³`;
   corrected `ε = ε₀ + 0.00256·cos Ω`.
8. **Declination** `δ = asin(sin ε · sin λ)`.
9. **Equation of time (minutes)**, `y = tan²(ε/2)`:
   `EoT = 4·deg[ y·sin 2L₀ − 2e·sin M + 4e·y·sin M·cos 2L₀ − ½y²·sin 4L₀ − 1.25e²·sin 2M ]`.
10. **True solar time (min)** `TST = (UTC_min + EoT + 4·lon_east) mod 1440`
    — **+east longitude ADDS 4 min/deg**; sign errors here are the classic bug.
11. **Hour angle** `H = TST/4 − 180` (0 at solar noon, + afternoon/west).
12. **Elevation** `sin α = sin φ·sin δ + cos φ·cos δ·cos H` (φ = latitude).
13. **Azimuth** (clockwise from north, singularity-free atan2 form):
    `A_south = atan2( sin H, cos H·sin φ − tan δ·cos φ )` (from south, +west);
    `Az = (A_south + 180°) mod 360`. Do NOT use the acos formulation — it
    divides by cos α and blows up near the zenith (equator test case!).
14. **Refraction (optional output)**: NOAA piecewise correction; ≤0.02° above
    30° elevation, ~0.5° at the horizon. Shadows use *geometric* elevation by
    default; expose both. Rationale below.

**Accuracy & tolerance:** this formulation is good to ~±0.1° over 1900–2100
(full NOAA SPA reaches ±0.0003° — irrelevant here). Campaign tolerance is
**±0.5°** for elevation/azimuth: at the worst realistic case (winter Berlin,
α ≈ 13°, 2 m object) a 0.5° elevation error moves a shadow tip ~35 cm on an
~8.6 m shadow (~4%) — well inside gardening decision noise, while ±0.5° is
tight enough to catch every classic implementation bug (EoT sign → minutes ≈
degrees·¼ error; longitude sign → 2×4·13.4 ≈ 107 min of solar time; degrees/
radians mixups → tens of degrees).

### Build steps

1. Branch per `ogp-change-control` (e.g. `feature/US-E1-solar-engine`).
2. Create `src/open_garden_planner/core/solar.py` — copy from the reference
   script; add the dataclass; NO PyQt6 imports.
3. Create `tests/unit/test_solar.py` pinning the Appendix numbers (below) and
   the self-check identities (solstice-noon `α = 90 − |φ − δ|`, EoT extremes,
   equinox sunrise azimuth ≈ 90°).
4. Run the quality battery (pytest/ruff/bandit — commands in Phase 6).

### Gate P1

| Command | Expected | If not → |
|---|---|---|
| `venv/Scripts/python.exe -m pytest tests/unit/test_solar.py -v` (Linux: `venv/bin/python …`) | All pass; pinned values (tolerance ±0.05° vs the oracle, since it's the same algorithm): Berlin 52.52N/13.405E 2026-06-21 12:00 UTC → **elev 59.29°, az 203.74°, δ +23.44°, EoT −1.82 min**; 2026-12-21 12:00 UTC → **elev 13.08°, az 193.06°**; Equator 0/0 2026-03-20 12:00 UTC → **elev 88.14°, az 91.34°** | See branch table below. |
| `grep -rn "PyQt6" src/open_garden_planner/core/solar.py` | no output | Remove the import; solar math never touches Qt (fenced wrong path). |

> **Independent-oracle note (aligns with `ogp-research-frontier` step 1):** the
> pinned rows above share the production algorithm, so ±0.05° "vs the oracle"
> is a self-consistency check, not third-party validation. The oracle earns
> trust through **independent physical-identity cross-checks** it already runs
> (axial tilt, solstice-noon `α = 90 − |φ−δ|`, almanac EoT extremes, equinox
> azimuth). To fully meet the frontier's "precomputed third-party numbers"
> bar, paste **≥1 externally-sourced NOAA/Meeus row per test location** (with a
> provenance comment) alongside the oracle rows.

**Branch: numbers off by >1°** (the classic-bugs checklist, in order of
likelihood):
1. **Equation of time dropped or mis-signed** → symptom: elevation right at
   solar noon but wrong at fixed clock times; azimuth shifted ~¼°·EoT_min.
   Check step 10: `+ EoT`.
2. **Timezone / longitude sign** → symptom: hours-scale error or E/W mirror.
   `dt_utc` must be real UTC (`tzinfo=UTC`, `.astimezone(UTC)` first);
   longitude is +EAST (Berlin +13.405, not −13.405). NOAA's own spreadsheet
   uses +west — if you "corrected" against it, you double-flipped.
3. **Degrees/radians** → symptom: garbage (tens of degrees off). Every `sin`/
   `cos` input must pass through `radians()`; every `asin`/`atan2` output
   through `degrees()`.
4. **Azimuth quadrant** → symptom: elevation perfect, azimuth mirrored around
   180°. Use the atan2 form (step 13), verify the +180 shift with:
   northern-hemisphere solar noon MUST give Az ≈ 180.
5. Only then suspect coefficients — diff your constants against the reference
   script character by character.

---

## 4. Phase 2 — Object height property — TO BUILD

**Contract:** additive metadata key **`object_height_cm`** on garden items —
follow the `container_height_cm` precedent (`core/container_model.py`
docstring; `.ogp` round-trips metadata wholesale, old apps ignore unknown
keys → graceful degrade, **no FILE_VERSION bump**).

**Old-app graceful-degrade statement (put it in the PR body):** a `.ogp`
saved by v2.0 with `object_height_cm` opens in v1.x unchanged — the key rides
in `metadata`, which v1.x preserves on load/save (verified: `project.py`
serializes `item.metadata` wholesale, and unknown keys are untouched). No
migration, no warning needed.

### Design decisions (make them explicitly, record in ADR-035)

1. **One Qt-free resolver** — `core/object_height.py` (pattern:
   `core/plant_sizing.py`). Precedence:
   `metadata["object_height_cm"]` (explicit) → container: `container_height_cm`
   → plant with species: `plant_species["max_height_cm"]` (present in 118/118
   bundled records) → per-`ObjectType` default table → `None` (casts no shadow).
   Suggested defaults (agree with the owner in Phase 0 review): FENCE 120,
   WALL 200, HEDGE_* 150, HOUSE 450, GARAGE_SHED 250, GREENHOUSE 220,
   TRELLIS 180, RAISED_BED 40, furniture 75–90, everything else `None`.
2. **Do NOT alias `container_height_cm`.** It means *soil fill height* and
   drives soil volume; a tall pot on legs can have `object_height_cm` 90 with
   fill 30. Two keys, resolver arbitrates.
3. **Properties panel**: "Height" spin in a new/existing section — but
   **undoable**, via `ChangePropertyCommand` with an `apply_func` writing the
   metadata key (`core/commands.py` line 463 supports exactly this). The
   existing container section mutates `meta[...]` directly with no command —
   that is documented debt (#-file if you touch it), NOT the pattern.
   Respect the #206 incremental-refresh contract: `_register_refresh` for the
   new widget; and the #210 lesson does not apply (spin, not free text).
4. **i18n**: `self.tr("Height:")`, `self.tr("cm")` suffix if any, the command
   description fragment registered under the `Commands` context in
   `scripts/fill_translations.py` (per the ChangePropertyCommand localization
   scheme, #210).

### Gate P2

| Command | Expected | If not → |
|---|---|---|
| `venv/Scripts/python.exe -m pytest tests/unit/test_object_height.py tests/integration/test_height_property.py -v` | Round-trip test green: set height 250 on a WALL → save `.ogp` → load → resolver returns 250; unset item of type FENCE → default 120; plant w/ species Tomato → 200 (from `max_height_cm`) | If round-trip loses the key: you bypassed `set_metadata` or built the item without passing `metadata=` through the deserializer — trace `project.py` item-load path for your item class. |
| `venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished -v` after `PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py && PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py` | pass | A UI string missed `tr()` — remember the f-string trap (CLAUDE.md i18n section). |
| Manual: edit height, Ctrl+Z | Height reverts in one step; dirty flag set (the #209 invariant) | You mutated metadata outside `execute()`/`register_applied()` — route through the command. |

---

## 5. Phase 3 — 2D shadow projection MVP — TO BUILD

The high-value cheap slice. **Definition:** for each item with effective
height `h` and sun at (α, Az) with α > 0:

- **Shadow length** `L = h / tan α` (cm, on flat ground — elevation_m of the
  *site* shifts nothing on-site; slopes are out of scope v2.0, state that in
  the FR).
- **Shadow direction** (unit vector, **canvas frame**, +x=E, +y=N):
  `d_canvas = (−sin Az, −cos Az)` — the shadow extends *opposite* the sun's
  compass bearing `(sin Az, cos Az)`.
- **Shadow polygon** = footprint swept along `D = L·d_canvas` = Minkowski sum
  of the footprint with segment [(0,0) → D]. For convex footprints this is
  `convex_hull(P ∪ (P+D))`; for arbitrary polygons use
  `pyclipper.MinkowskiSum(pattern, path, True)` (available in pyclipper ≥1.3 —
  **REQUIRES VERIFICATION at implementation**: probe
  `venv/Scripts/python.exe -c "import pyclipper; print(pyclipper.MinkowskiSum([[0,0],[100,50]], [[0,0],[400,0],[400,300],[0,300]], True))"` — expect a list of
  integer polygons; if absent/odd, fall back to union of the footprint
  translated in N=8 steps along D, which is visually identical at garden
  scale). Then union all per-item shadows via `pyclipper.Pyclipper` CT_UNION.
  Use the integer scale-factor discipline from `core/tools/offset_tool.py`
  (line 22) — pyclipper is integer-only.

### Y-axis discipline (THE trap — fence it with a test)

**Owner of the Y-axis convention: `ogp-qt-cad-reference` §1** — read it once and
defer to it. Its operative rule: scene coordinates ARE the CAD coordinates the
user sees; scene +y is already North/up in the data path; there is **no
`scene_to_canvas` conversion** in production (that helper computes `H − y` but
has zero production callers). So there is **no extra flip** between "canvas
frame" and "Qt scene frame" for shadow math — do the math once, in scene cm.

**Derivation (one line).** Az is a compass bearing clockwise from North, so in
the CAD Y-up frame (East=+x, North=+y) the sun's horizontal direction is
`(sin Az, cos Az)`; the shadow points *opposite* the sun →
`d = (−sin Az, −cos Az)`. Because scene +y is already North (no conversion
layer), the scene-space shadow vector is the **same**:
`d_scene = d_canvas = (−sin Az, −cos Az)`. (This matches the sign convention the
existing linear/grid-array code already uses in scene cm — §11.4 "Canvas
Y-axis flip".) Do **not** re-flip the y-component at an "item-construction
boundary"; that double-flip is exactly the mirrored-shadow bug.

**Worked example** (numbers from the shipped oracle, Appendix): Berlin,
2026-06-21 12:00 UTC → Az = 203.74°, α = 59.29°.
`sin Az = −0.4025`, `cos Az = −0.9154`.
- Shadow direction (scene = canvas): `(−sin Az, −cos Az) = (+0.4025, +0.9154)`
  — mostly **+y = NORTH**, slightly east. Correct: early-afternoon sun is just
  west of south, so the shadow falls north-northeast. 100 cm object → L = 59.4 cm,
  so `tip_scene = base_scene + 59.4·(0.4025, 0.9154)`.
- Rendered pixels (`y_flip=True`, §8.19):
  `px_y = image_height_px − (y_cm − region_y_cm)·px_per_cm` with `y_cm` the
  **raw scene y**. The shadow tip has the *larger* scene-y (it went North) →
  the *smaller* px_y → nearer the image **top**. That is exactly where North
  renders. No paradox: the arithmetic is settled — larger scene-y renders
  higher, in agreement with the live view.

**The binding test** (the regression pin, not the tiebreaker): place a 100 cm-tall
40×40 item at a known scene position, set sim time to Berlin 2026-06-21 12:00 UTC,
render via `render_canvas_image` (or `render_scene_region` directly in the
test), compute the expected shadow-tip pixel with the RenderMeta formula from
the raw scene coordinates `tip_scene = base_scene + 59.4·(0.4025, 0.9154)` (no
`canvas_to_scene` step — scene IS the CAD frame), and assert the shadow color
at that pixel ± 2 px. If it passes, your frames are consistent; if the shadow
appears mirrored, you re-flipped y where you shouldn't have — remove the flip,
keep the math in scene cm.

### Rendering rules (existing-pattern compliance)

- **Overlay item(s)** on a dedicated, non-serialized layer (or scene-level
  overlay item like the existing warning badges): one `QGraphicsPathItem`-ish
  item holding the unioned shadow path, z-order above background image, below
  garden items. Runtime-only — **never serialized** (the #219 lesson: runtime
  visuals must not perturb save-time geometry; also don't let the overlay
  affect any item's `boundingRect`).
- **Precompute, never in `paint()`**: recompute the union when (a) an item
  with height moves/resizes/rotates/changes height, (b) sim date/time changes,
  (c) location changes (`ProjectManager.location_changed` — already a signal,
  `application.py` line 158). Debounce with the established
  `QTimer`+`contextlib.suppress(RuntimeError)` pattern (#230 teardown pitfall).
- **Time control UI**: a small toolbar/dock with date + time-of-day slider and
  an animate button (the roadmap's "time-of-day animation" = just advancing
  the slider on a QTimer; each tick only re-runs the precompute + one
  `update()`). Persist last-used sim time in `UiStateStore`
  (`app/ui_state.py`), NOT in `.ogp` (defer project-persisted sun settings
  until a user asks).
- **Empty states**: no `project.location` → overlay disabled + one-line hint
  ("Set garden location first: File → Set Garden Location"), i18n'd. Sun below
  horizon → no shadows + "night" hint.
- **Naming collision**: the View menu already has the cosmetic shadows toggle
  (`appearance/show_shadows`). Name the new action distinctly — "Sun & Shade
  Simulation…" — and file a UX note; do not touch the old toggle's key.

### Gate P3

| Command | Expected | If not → |
|---|---|---|
| `python3 .claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py \| grep "shadow"` | `Berlin Jun 21 12:00Z: … shadow 59.4 cm, canvas dir (dx=+0.403, dy=+0.915)`; `Berlin Dec 21 12:00Z: … shadow 430.4 cm, canvas dir (dx=+0.226, dy=+0.974)` | Oracle drift — re-run full script; if self-checks fail, stop. |
| `venv/Scripts/python.exe -m pytest tests/unit/test_shadow_geometry.py -v` | Qt-free geometry tests: 100 cm object, α=59.29° → L=59.4±0.1 cm; α=13.08° → 430.4±1 cm; direction vectors ±0.01 | tan/atan mixup or degrees passed raw into `math.tan` — the L formula takes RADIANS internally. |
| `venv/Scripts/python.exe -m pytest tests/integration/test_shadow_overlay.py -v` | The pixel assertion described above passes; shadow recompute count ≤1 per change event (assert with a counter, the #206 discipline) | Mirrored → Y-boundary flip misplaced. Recompute storm → you wired recompute to `scene.changed` raw instead of debounced. |
| Profile: `venv/Scripts/python.exe -m pytest tests/integration/test_shadow_overlay.py -k perf -v` (write one: 200 items with heights, one recompute) | < 50 ms per recompute on dev hardware (pyclipper is C++; 200 Minkowski+union at garden vertex counts is small) | >50 ms: check you're not converting through QPainterPath per item (stay in raw coordinate lists until the final path build); check integer scale factor isn't absurd (1000 is plenty). |

---

## 6. Phase 4 — Shade aggregation: hours-of-sun heatmap — TO BUILD

**Definition:** for a chosen date (or season = set of dates), sample the
daylight period at Δt = 15 min; for each sample with α > 0 compute the
unioned shadow polygon (Phase 3 machinery); accumulate per grid cell:
`sun_minutes[cell] += Δt if cell not in shadow`. Output: heatmap layer
(e.g. <2 h deep shade … >6 h full sun — the horticultural bands; put the
band definitions in `docs/12-glossary/`).

**Performance budget (stated up front):** target garden 30 m × 20 m at 10 cm
cells = 60 000 cells × ~64 daylight samples (Jun 21 Berlin ≈ 16.7 h / 15 min).
Python point-in-polygon per (cell, sample) is ~4 M tests — too slow. Use one
of two vectorized routes (pick in ADR-035):
1. **Rasterize per sample** (recommended): paint the sample's shadow polygons
   into a monochrome `QImage` at grid resolution and accumulate with numpy
   (`QImage` painting is documented thread-safe off the GUI thread, unlike
   QPixmap — but VERIFY with a 2-thread smoke test before relying on it, and
   keep the worker to `QImage` only). 64 fills of a 300×200 image is
   milliseconds.
2. **Pure numpy even-odd rasterization** in the Qt-free core (slower to write,
   fully unit-testable headless; keeps the whole aggregation Qt-free). Numpy
   is already a dependency.

**Threading:** NEVER on the paint path, never blocking the GUI. Run the
aggregation in a `QThread` worker — copy the shape of
`_WeatherFetchWorker` (`ui/widgets/weather_widget.py` line 33) or
`UpdateChecker` (`services/update_checker.py` line 98): worker emits a
`ready(result)` signal; the slot swaps the cached heatmap image and calls
`update()`. Inputs to the worker must be *snapshots* (plain lists of
(polygon, height)) — never live QGraphicsItems across threads (the D1.x
`MainThreadBridge` exists for exactly this reason; for an in-process worker a
plain data snapshot is sufficient).

**Budget gate:** full-day heatmap for the 60 k-cell garden completes < 2 s in
the worker, UI never freezes (scroll the canvas during compute).

### Validation gate P4 — the hand-computable toy case

Single infinite east-west wall, height 200 cm, flat ground, Berlin. Point
50 cm NORTH of the wall. (Northern hemisphere: the sun tracks the *southern*
sky in winter, so the wall's **north** side is the dark side — if your
mental model said "south side", stop and re-derive; the sun never goes north
of the E–W line between the equinoxes' azimuth limits in winter.)

Numbers from the shipped oracle (5-min sampling, geometric elevation —
Appendix):
- **Dec 21: 0 min of direct sun.** Hand argument: winter sun azimuth stays in
  (90°, 270°) (south of the E–W line) all day, so the shadow always has a
  northward component; escaping a 200 cm wall at 50 cm distance would need
  `L·(−cos Az) < 50`, i.e. tan α > 4·|cos'| ⇒ at minimum α ≥ 75.96° for the
  pure-south case — Berlin's winter max is 14.04°. Impossible ⇒ exactly 0.
- **Jun 21: 540 min (9.0 h).** Structure (hourly trace verified): sunrise
  azimuth ≈ 51° (NE) — sun north of the wall line until ~06:00 UTC, and even
  after crossing east the shadow's northward reach stays < 50 cm until
  ~07:30 UTC (high sun, short shadow); blocked through midday
  (reach 73–111 cm); lit again from ~14:40 UTC through NW sunset (az 309°).
  Morning ≈ 4.8 h + evening ≈ 4.2 h ≈ 9 h.

| Command | Expected | If not → |
|---|---|---|
| `python3 .claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py \| grep -A3 "toy-case"` | `Dec 21: 0 min`, `Jun 21: 540 min (9.0 h)` | Oracle drift — full re-run. |
| `venv/Scripts/python.exe -m pytest tests/unit/test_shade_aggregation.py -v` | Your production aggregator reproduces 0 min (Dec) and 540 ± 15 min (Jun — one sample of slack for grid discretization) on the same toy scene | Dec ≠ 0 → your shadow polygons leak or azimuth window wrong (Y-flip again — check the direction test first). Jun far off → daylight window or sampling step wrong; print the per-sample lit/shaded trace and compare to the Appendix hourly table. |
| Manual + machine: render the heatmap via `render_canvas_image`, sample the pixel at the toy point | Deep-shade band color (Dec), ~9 h band (Jun) — assert via the RenderMeta pixel formula | Overlay drawn in the wrong frame — same fix path as Phase 3 gate. |

---

## 7. Phase 5 — 3D view decision spike (GO/NO-GO) — TO BUILD

This answers §11.1's open question. Timebox: **5 working days**. The
sun/shade features (Phases 1–4) ship regardless of this outcome — that is the
campaign's insurance policy.

**Do not assert the current state of Qt3D from memory.** Qt3D's status in the
Qt 6 series has been in flux (module maintenance, wheel availability for
PyQt6 vs PySide6 differ). Everything in this table is **REQUIRES VERIFICATION
at spike time** — the commands are the deliverable, not remembered claims:

| Criterion | How to verify (exact commands) | GO threshold |
|---|---|---|
| PyQt6 Qt3D availability & maintenance | `venv/Scripts/python.exe -m pip index versions PyQt6-3D` ; then `venv/Scripts/python.exe -m pip install PyQt6-3D` in a THROWAWAY venv; probe `python -c "from PyQt6.Qt3DCore import QEntity; from PyQt6.Qt3DExtras import Qt3DWindow; print('qt3d ok')"`; check the release date/version skew vs installed PyQt6 (`pip show PyQt6 PyQt6-3D`); check Riverbank's roadmap page for deprecation notices | Wheel exists for current PyQt6 minor, imports clean on Windows, release < 12 months old |
| Alternative: PyVista (VTK) | `pip install pyvista pyvistaqt` in throwaway venv; probe `python -c "import pyvista; print(pyvista.__version__)"`; embed test: `QtInteractor` inside a QDialog | Same import + embed bar. **License: PyVista MIT, VTK BSD-3, pyvistaqt MIT — all GPL-3 compatible** (project is GPL-3.0-or-later, pyproject line 10). Note VTK wheel size (~100 MB) → installer-size criterion below |
| Alternative: pyqtgraph.opengl | `pip install pyqtgraph PyOpenGL`; probe `GLViewWidget` | MIT, tiny; weakest feature set (no shadow mapping out of box — you'd project shadows yourself, which Phase 3 already does analytically → genuinely viable for a 2.5D look) |
| Zero-dep fallback: 2.5D isometric | No install — prototype a `QGraphicsScene` isometric projection (items extruded by `object_height_cm`, painter-sorted) | Always available; this is the DEFER outcome, not a failure |
| **Packaging under PyInstaller (MANDATORY, the decisive gate)** | Add the candidate to a spike branch, `venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm` then `timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe` (exit 124 = alive). Then open the 3D spike window in the frozen exe on a real Windows box | Frozen exe shows a lit, rotating extruded box textured from a real `.ogp`'s items. Precedent for hidden-import pain: the mcp/uvicorn saga (§8.19 packaging note; expect `collect_submodules`/`copy_metadata`/binaries work for VTK especially) |
| Installer size delta | compare `dist/` size before/after | < +150 MB or owner explicitly accepts |
| GPL compatibility of the chosen dep | read its license file, cross-check SPDX | Must be GPL-3-compatible; if a sibling `ogp-external-positioning` skill exists, follow its process |

**Spike deliverable:** ADR-036 "3D engine choice" with the filled-in table,
the frozen-exe screenshot, and the decision.

**Kill criteria (write them in the ADR before starting):**
- Frozen-exe gate not passed for ANY candidate after 5 days → **NO-GO**:
  ship Phases 1–4 as v2.0's sun/shade story + the 2.5D isometric fallback as
  a later US; keep §11.1's row updated with what you learned.
- Candidate imports but needs per-machine GPU driver workarounds in testing →
  NO-GO for that candidate (support burden).
- GO → US-E6 (3D MVP: extruded footprints by `object_height_cm`, orbit
  camera, sun-directional light using Phase 1's vector — elevation/azimuth to
  a 3D light direction is `(cos α·sin Az, cos α·cos Az, sin α)` in
  (E, N, up)), then US-E7 walkthrough (first-person camera on the ground
  plane), US-E8 growth visualization (scale plant height between
  `min_height_cm`→`max_height_cm` from the species DB across a date slider —
  data verified present for 118/118 species).

---

## 8. Phase 6 — Validation & promotion (per slice)

Run for EVERY US in the campaign; route everything through
`ogp-change-control` (it owns the canonical sequence; this is the
campaign-specific overlay).

| Step | Command (Windows; Linux swap `venv/bin/python`) | Expected |
|---|---|---|
| Tests | `venv/Scripts/python.exe -m pytest tests/ -v` | green, incl. the new pinned-number tests |
| Lint | `venv/Scripts/python.exe -m ruff check src/` | clean |
| Security | `venv/Scripts/python.exe -m bandit -r src/ --severity-level high` | clean |
| i18n | `PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py && PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py && venv/Scripts/python.exe -m pytest "tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished" -v` | pass — remember: f-strings bypass `tr()` (the CLAUDE.md trap); sun/shade has LOTS of user-visible strings (menu, hints, band labels, command descriptions) |
| Exe | `venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm && timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe` | exit code 124 |
| Integration test | mandatory per §8.10 — each phase's gate table above names the file | in `tests/integration/` |
| Review | `senior-reviewer` agent on the branch diff, fresh worktree; fix P0/P1; re-run for a clean pass | clean pass BEFORE the PR |
| PR | draft PR (`gh pr create --draft`), stays draft until the owner's manual test | per `ogp-change-control` — never merge on your own say-so |

**Manual-test checklist (owner-facing, per slice — the owner's judgment is
sovereign, but hand them numbers, not vibes):** e.g. for Phase 3: "Set
location Berlin (52.52, 13.405). Set sim time 21 Jun 12:00 UTC (14:00 CEST).
Place a 1 m-tall post. EXPECTED: shadow ~59 cm long pointing north-northeast
(up-right on screen). Set 21 Dec 12:00 UTC. EXPECTED: ~4.3 m shadow, nearly
due north." — the numbers come from the Appendix, so a failed manual test
localizes instantly to render-vs-math.

**Documentation duties (per `ogp-change-control` / CLAUDE.md matrix):**
- **ADR-035**: solar engine + shadow architecture (Qt-free core, canvas-frame
  math, overlay non-serialization, aggregation strategy). **ADR-036**: 3D
  engine GO/NO-GO. (ADRs live in `docs/09-architecture-decisions/README.md`;
  034 is the last used as of 2026-07-04.)
- **FR entries** in `docs/functional-requirements.md` (suggest FR-SUN-01…):
  height property, shadow overlay, time control, heatmap, empty states, and
  the explicit exclusions (flat-ground assumption; refraction ignored;
  terrain slopes out of scope v2.0).
- **§8 concept section** in `docs/08-crosscutting-concepts/README.md`
  (next free §8.x — check; §8.19 was Agent API): the three-frame coordinate
  discipline for solar math, with the worked example.
- **Glossary** (`docs/12-glossary/` — a directory): azimuth, declination,
  elevation angle, equation of time, hour angle, solar noon, full sun /
  partial shade / full shade bands.
- **Roadmap + wiki**: mark the USes, sync `../open-garden-planner.wiki/Roadmap.md`.
- **§11.1**: close/update the Qt3D open-question row with the ADR-036 outcome.

---

## Appendix — Pinned reference numbers (generated 2026-07-04)

Produced by running the shipped oracle in this container
(`python3 .claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py`,
Python 3.x stdlib, exit code 0). Regenerate after ANY edit to the script and
re-paste; never hand-edit numbers.

Cross-checks passed (10/10), with the arithmetic shown:
- Declination Jun 21 2026 = **+23.4381°**, Dec 21 = **−23.4373°** (known
  axial tilt ±23.44°; deltas −0.002/+0.003).
- Solstice-noon identity `α_max = 90 − |φ − δ|`: Berlin summer
  `90 − |52.52 − 23.44| = 60.92` vs scanned max **60.9181** (Δ 0.0000 vs
  identity); winter `90 − |52.52 + 23.44| = 14.04` vs **14.0427**.
- EoT extremes: 2026-02-11 → **−14.2262 min** (almanac ≈ −14.2);
  2026-11-03 → **+16.4922 min** (almanac ≈ +16.4).
- Equinox: Berlin sunrise azimuth Mar 20 → **90.31°** (due-east fact, Δ 0.31°
  at 1-min sampling); equator max elevation Mar 20 → **89.88°** (near-zenith).

Gate table (pin in `tests/unit/test_solar.py`; oracle tolerance ±0.05°
since production copies the same algorithm; campaign accuracy claim ±0.5°):

```
location                UTC instant             elev elev+refr  azimuth    decl    EoT
Berlin 52.52N 13.405E   2026-06-21 12:00       59.29     59.30   203.74   23.44  -1.82
Berlin 52.52N 13.405E   2026-12-21 12:00       13.08     13.15   193.06  -23.44   1.92
Equator 0N 0E           2026-03-20 12:00       88.14     88.14    91.34   -0.04  -7.43
Equator 0N 0E           2026-06-21 12:00       66.56     66.56     1.05   23.44  -1.82
```

Phase 3 shadow gate (100 cm object, geometric elevation):

```
Berlin Jun 21 12:00Z: elev 59.29°, az 203.74° -> shadow  59.4 cm, canvas dir (dx=+0.403, dy=+0.915)  [dy>0 = NORTH]
Berlin Dec 21 12:00Z: elev 13.08°, az 193.06° -> shadow 430.4 cm, canvas dir (dx=+0.226, dy=+0.974)
```

Worked azimuth→vector example: Az = 203.74°; sin Az = −0.4025,
cos Az = −0.9154; canvas dir (−sin, −cos) = **(+0.4025, +0.9154)**;
Qt-scene dir (−sin, +cos) = (+0.4025, −0.9154).

Phase 4 toy-case gate (200 cm E–W wall, point 50 cm north, Berlin, 5-min
sampling): **Dec 21 = 0 min; Jun 21 = 540 min (9.0 h)**. Hourly structure
(from the verification trace): lit 03:00–07:30 UTC (sun NE→E, shadow reach
< 50 cm until α high enough), shaded 07:30–14:40 (reach 73–111 cm),
lit 14:40–sunset (~19:20, sun W→NW).

---

## Provenance and maintenance

All repo facts verified 2026-07-04 against the working tree at v1.23.0.
One-line re-verification commands (run from repo root):

- Solar oracle still green: `python3 .claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py --quiet; echo $?` → expect final `RESULT: ALL CHECKS PASSED`, exit 0.
- Phase 14 roadmap section: `grep -n "Phase 14" docs/roadmap.md` → line ~2447.
- Qt3D open question still open: `grep -n "Qt3D" docs/11-risks-and-technical-debt/README.md` → line ~10 (delete the Phase 5 spike if this row is closed by an ADR).
- Location dict: `grep -n "latitude, longitude, elevation_m" src/open_garden_planner/core/project.py` → ~line 747.
- FILE_VERSION: `grep -n "FILE_VERSION" src/open_garden_planner/core/project.py` → `"1.4"` (if higher, re-read the bumping ADR before trusting the additive-metadata rules).
- pyclipper + numpy deps: `grep -nE "pyclipper|numpy" pyproject.toml`.
- Species height coverage: the python3 one-liner in §0 → `118 / 118` (or more records, same full coverage expected).
- Cosmetic-shadow collision: `grep -n "KEY_SHOW_SHADOWS" src/open_garden_planner/app/settings.py` → `appearance/show_shadows` still cosmetic-only.
- Next ADR number: `grep -c "^## ADR-" docs/09-architecture-decisions/README.md` and take max+1 (034 as of 2026-07-04).
