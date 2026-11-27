---
id: ADR-037
title: "Sun/Shade Foundation — Qt-Free Solar Engine + Object-Height Resolver (Phase 14, US-E1+E2)"
status: "Accepted (2026-07-19)"
legacy_anchor: adr-037-sunshade-foundation--qt-free-solar-engine--object-height-resolver-phase-14-us-e1e2
---

# ADR-037: Sun/Shade Foundation — Qt-Free Solar Engine + Object-Height Resolver (Phase 14, US-E1+E2)

**Status**: Accepted (2026-07-19) | **Context**: Epic #255, issues #256 + #257, campaign skill `ogp-3d-sunshade-campaign`

Phase 14's sun/shade features (shadow overlay US-E3, hours-of-sun heatmap US-E4, 3D sun light US-E6) all reduce to two primitives: *where is the sun?* and *how tall is this object?* Both are delivered as Qt-free `core/` modules so they are unit-testable headless and consumable by 2D and 3D alike.

**Solar engine (`core/solar.py`, US-E1).** Implements the NOAA "General Solar Position Calculations" (Meeus-derived, ±0.1° class over 1900–2100) with stdlib `math`/`datetime` only. The math is copied **verbatim** from the campaign oracle (`.claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py`), which self-checks against independent physical facts (axial-tilt declination extremes, the solstice-noon identity `α = 90 − |φ − δ|`, almanac EoT extremes, equinox sunrise azimuth); production must never "improve" constants locally — regenerate the oracle and re-pin the tests instead. **Rejected**: adding `pysolar` (GPL-3, redundant) or `astral` (Apache-2.0, redundant) — ~120 lines of stdlib math replace both, and a dependency we didn't write is one we can't pin numbers for. Conventions (each guards a classic sign bug, all pinned in `tests/unit/test_solar.py`): longitude **+east** (the NOAA spreadsheet itself uses +west), timezone-aware UTC input (naive datetimes raise), azimuth clockwise-from-north via the singularity-free **atan2** form (the acos form divides by cos α and blows up near the zenith — pinned by the equator-equinox test). Campaign accuracy claim: **±0.5°** — at the worst realistic case (winter Berlin, α ≈ 13°, 2 m object) that moves a shadow tip ~35 cm on an ~8.6 m shadow, inside gardening decision noise, yet tight enough to catch every classic implementation bug. Tests pin the oracle gate table at ±0.05° (drift detection) plus an external-literature row (Meeus *Astronomical Algorithms* 2nd ed., Example 25.a: 1992-10-13, δ = −7.78507°) and the physical identities (third-party validation).

**Object-height resolver (`core/object_height.py`, US-E2).** One source of truth for "how tall above ground?", precedence: explicit `metadata["object_height_cm"]` → container **fill** height (`container_height_cm`) → embedded species `max_height_cm` → per-type default table (fence 120, wall 200, house 450, …) → `None` (casts no shadow). Decisions:
- **Two keys, never aliased**: `object_height_cm` (above-ground height, shadows/3D) vs `container_height_cm` (soil fill, drives volume) — a tall pot on legs can be 90 cm tall with a 30 cm fill. The resolver arbitrates; nothing else reads both. **Known simplification (review-flagged, revisit in US-E3/#258)**: with no explicit override the fill height *stands in* for a container's above-ground height (there is no separate source in this slice), so an on-legs pot under-shadows until the user sets a height — marked in a code comment at the fallback.
- **Additive metadata, NO FILE_VERSION bump** (stays "1.4"): the serializer round-trips `item.metadata` wholesale, old apps ignore unknown keys (precedent: the `container_*` keys). Graceful degrade both directions is pinned by `tests/integration/test_height_property.py`.
- **Qt-free by name-matching**: `core/object_types.py` imports PyQt6 (translated labels), so the resolver matches object types by enum **name** (`"FENCE"`) instead of importing the enum — same spirit as `plant_sizing`/`container_model`'s metadata-only duck-typing. The name sets (`DEFAULT_HEIGHTS_CM` keys, container/plant name sets) are pinned against the real enum by unit tests, so a rename breaks a test rather than silently orphaning a default.
- **Undoable UI**: the properties-panel "Object height:" spin displays the *resolved effective* height (0 = "Auto" clears the override — the exact semantics of the existing spacing-radius field) and commits via `ChangePropertyCommand(apply_func=…)` — one undo step (#209). The container section's direct-metadata mutation was documented debt, not a precedent; it is paid now (#530 - each of those edits is one `ChangePropertyCommand`).

**Consequences**: US-E3 consumes `solar_position()` + `effective_height_cm()` without new plumbing; US-E5/E6's extrusion uses the same resolver, so 2D shadows and 3D heights can never disagree. `height_source()` gives the UI (and future diagnostics) provenance for free.

## ADR-037 addendum: 2D analytic shadow overlay (US-E3, #258)

**Status**: Accepted (2026-07-19) | **Context**: issue #258, campaign Phase 3

**Geometry core (`core/shadow_geometry.py`, Qt-free).** For each caster with effective height `h` and geometric sun elevation `α > 0.5°`: shadow length `L = h / tan α`; scene-space direction `(−sin Az, −cos Az)` (scene +y IS North — ADR-002; there is deliberately NO Y-flip anywhere in the shadow math, the pixel-facing render applies its own). The shadow polygon is the filled footprint swept along `D = L·dir`: `pyclipper.MinkowskiSum(segment, footprint, True)` **probed live on 2026-07-19** (returns the swept-boundary annulus as integer polygons) unioned with the footprint and its translated copy (all CCW-normalized, `PFT_NONZERO`) — exact for convex and concave footprints. A translate-in-8-steps fallback covers binding failures (a few % of area in cm-scale edge notches; tip and direction exact — pinned by test). Everything stays on the integer grid (`CLIPPER_SCALE = 1000`, the `offset_tool` precedent) until one final scene-wide union: a 200-caster recompute measures in single-digit milliseconds. Below `MIN_SUN_ELEVATION_DEG = 0.5°` no shadows render (near-horizon lengths explode toward infinity and are noise, not information).

**Footprint extraction** happens Qt-side (`sun_shadow_controller._item_footprints`) via `mapToScene` — rotation/position are Qt's answer, not a re-derivation (#218/#219 lessons): polygons/rects map their vertices, circles/ellipses polygonalize at 24 segments, polylines (fence/wall) inflate their centerline by half the pen width (`PyclipperOffset`, square joins, butt ends).

**Overlay (`SunShadowOverlayItem`)** is a runtime-only `QGraphicsPathItem` (NOT a `GardenItemMixin`): z = −500 (above the −1000 background image, below every layer item), odd-even fill so union holes (sunny courtyards enclosed by shadow rings) stay sunny, never serialized (`project._serialize_item` whitelists classes; pinned by test), and recreated defensively when `scene.clear()` (project load) deletes its C++ object. The overlay is **clipped to the canvas bounds** (a long shadow is cut off at the garden edge, never spilling onto the grey area outside) and painted with a soft, effect-free **outward feather** (translucent strokes clipped to the region outside the shadow — the scene avoids `QGraphicsEffect`); when the sun is below `MIN_SUN_ELEVATION_DEG` the **whole canvas is shaded** (night), rather than the shadows vanishing.

**Recompute discipline** (the #206/#200 lesson — never in `paint()`): `scene.changed` → 150 ms debounced recompute (the companion/spacing precedent, #230 teardown-guarded) plus `command_manager.stack_changed` for metadata-only edits (a height change repaints nothing, so `scene.changed` alone would miss it). A snapshot key (sun position + caster geometry) makes duplicate triggers cheap — the caster snapshot is still collected to build the key, but the expensive pyclipper union + `QPainterPath` rebuild is skipped — and breaks the overlay's own `setPath` → `scene.changed` echo loop. Time-control changes recompute immediately (no debounce) for slider responsiveness.

**Time control (`SunSimToolbar`)** operates in the system local timezone (the garden and the computer share one in practice), emits aware datetimes, and the controller stores UTC. *Superseded by ADR-053 (Phase 17 L1.0): the toolbar now emits a naive wall reading into the one `SimClock`, which stores the plan date as picked; the controller reads the clock.* The sim instant is deliberately NOT persisted (and never in the `.ogp`): it defaults to the current date/time on each app start, so a fresh simulation always reflects today. The View-menu action **"Sun & Shade Simulation"** is named distinctly from the cosmetic "Show Shadows" toggle (`appearance/show_shadows` untouched — the campaign's naming-collision fence); the simulation always starts OFF per session.

**Validation**: the binding pixel test renders the live scene through `render_scene_region` (`y_flip=True`) and asserts the shadow tip lands at the pixel the §8.19 formula predicts from raw scene coordinates — machine-checked, never eyeballed. **Rejected**: computing shadows in `paint()` (recompute storm), reusing the cosmetic shadow toggle (one toggle, two meanings), serializing the overlay (runtime visuals must not touch save-time geometry).

## ADR-037 addendum: hours-of-sun heatmap aggregation (US-E4, #259)

**Status**: Accepted (2026-07-19) | **Context**: issue #259, campaign Phase 4

**Aggregation strategy — route 1 (rasterize per sample) chosen.** For each daylight sample (15-min step over the UTC civil day) the US-E3 shadow union is painted into a grid-resolution monochrome `QImage` off the GUI thread and accumulated with numpy (`sun_minutes += step` where unshaded). The alternative (pure-numpy even-odd rasterization, fully Qt-free) was retained only as the test-side reference (`point_rasterizer_reference`, cell-center point-in-polygon) — the production QImage rasterizer is pinned against it (<3 % boundary-cell mismatch) and its off-thread use is licensed by a **2-thread smoke test** (two concurrent painter threads, identical output), per the documented QImage-is-thread-safe / QPixmap-is-not rule. **Measured**: the stated budget (30 m × 20 m at 10 cm cells = 60 000 cells, full summer day ≈ 67 samples) completes in well under a second on dev hardware — the 2 s worker budget holds with an order of magnitude to spare; the GPU/raycast route stays rejected.

**Core split**: `core/shade_aggregation.py` is Qt-free — daylight sampling (gate α > 0 with the shadow call clamped to ≥ 0.5°: dropping grazing dawn/dusk samples entirely would undercount every cell by ~10 min/day at Berlin's solstice, while at 0.5° a shadow is already ~115 m per meter of height so sunward cells stay correctly shaded — this is what keeps the toy case at exactly 0 min winter / 540 min summer), band thresholds (<2 h / 2–4 h / 4–6 h / ≥6 h), grid math (row 0 = SOUTH edge, §8.20 discipline), and the sampling loop with an injected rasterizer. The Qt side (`ui/canvas/sun_heatmap.py`) holds the QImage rasterizer, the `_WeatherFetchWorker`-shaped `HeatmapWorker(QThread)` (plain-data snapshots in — `collect_shadow_casters` runs on the GUI thread — signals out), the runtime-only `SunHeatmapOverlayItem(QGraphicsPixmapItem)` (z −450, never serialized, `scene.clear()`-guarded like the shadow overlay), and the controller.

**Recompute on demand only**: the heatmap costs seconds, not milliseconds, so it is NEVER wired to `scene.changed` — an explicit "Hours of Sun" toolbar button computes it, a date change (not a time-of-day change — the map aggregates the whole day) or disabling the sim clears it, and `closeEvent` joins a running worker (`shutdown()`) because a `QThread` destroyed while running aborts the process (#230 class).

**Rendering redesign (2026-07, `feature/sun-display-polish`).** The original 4-band discrete fill (hard colours + nearest-neighbour scaling) read as blocks. The overlay now renders a **continuous cool→warm ramp** — Qt-free `core/heatmap_render.py::build_sun_lut` (deep indigo in shade → amber/pale-yellow in full sun; alpha fades out toward full sun so a good spot shows the garden through) drawn with `SmoothTransformation` — plus **topographic contour lines every hour** (pure-numpy marching squares `iso_segments`, drawn as cosmetic-pen `QGraphicsPathItem`s that follow the terrain) with **even-hour `{n} h` labels** (`QGraphicsSimpleTextItem` + `ItemIgnoresTransformations`, the dimension-line idiom — zoom-stable). The labeled contours are the key, so the toolbar swatch legend is removed. **Display-only**: the aggregation, the toy-case gates and the worker are unchanged; contour extraction is cheap GUI-thread work after the compute. The horticultural bands (`BAND_THRESHOLDS_MINUTES`) stay as the domain classification the even-hour contours align with.

## ADR-037 addendum — the sun map's key, its labels and what is painted with it (#794, #793; 2026-11-10)

**Status**: Accepted (2026-11-10), shipped in v1.38.0 (PR #838); decisions 1, 3, 6 and the narrow-gap rule of decision 7 were confirmed in the owner's manual test of 2026-11-10; amended the same day after the second review of the 2D branch — the day's format in decision 1 and the invariant of decision 7 are that round's | **Context**: issue #794 (the hours-of-sun map in the 2D plan: no legend, labels cut by plants, blurred badges, time-of-day shadows over the map) and the last point of #793 (the shadow's soft edge shows as bands when zoomed in). Mechanics: §8.9.18.

**1. The map has a key. This revises "the labeled contours are the key" of the addendum above.** A number on a contour says what the line is; it does not say what a colour is, and between two contours the colour is all there is. The key is a bar of the map's tints from no sun to sun all day, a mark at every contoured hour, numbers at the numbered hours, and a title with the day — written as every label, card and legend of the application writes a date (`core.i18n.format_short_date`: day, month name, year, in the UI language), not in ISO, which is for a date field, a file and the Agent API (until the second review the title wrote `2026-06-21`). What it shows is derived from the tables the map is drawn from (`core.heatmap_render.sun_legend`); there is no second colour table and no second "which hours are numbered" rule, and a unit test searches the sources for one. The bar shows the tints on the bare plan's colour: the map is translucent, so on a lawn its colours are the lawn's too — no key can show that, and an opaque map (which could) would hide the garden the map is read against. *Rejected*: a swatch legend in the toolbar (removed in 2026-07 for good reason: it is not on the picture and not in an export); discrete hour classes (the map is continuous since the 2026-07 redesign; the horticultural bands stay the domain classification the even contours align with).

**2. Where the key lies.** On the canvas it is drawn by the view over the viewport, bottom left, in the strip the scale bar stands in — the one strip every overlay widget already keeps clear, and the margin a fitted plan leaves. It is not a scene item there: a key at a place in the plan is out of sight as soon as the user zooms into the map, which is when it is needed. Zoomed in it lies over the plan as the scale bar does; where the view is too narrow it loses its title, then moves one strip up, and is left out rather than drawn over the scale bar or the minimap. *Rejected*: a widget in the toolbar or the status bar (off the picture; "Map: date" is already there); a panel with a backing (the scale bar beside it has none; the halo is the canvas's one answer to "readable on any ground", §8.9.15).

**3. A picture of the plan with the map on carries the key** — PNG, SVG, the PDF report, print and the Agent API's `render_canvas_image` alike, because all of them already carry the map (FR-SUN-05: "it appears in exports while shown"), and a map without its key is a picture of colours. It lies inside the picture, in the plan's south-west corner, over whatever the plan holds there: a picture of the plan is exactly the plan, and a strip added for the key would change the picture's size and the pixel-to-plan mapping the Agent API documents. It is a scene item that the export seam shows for the render only (`ExportService._hide_overlay_items`, now the one place for what a picture leaves out AND puts in), and a `HaloTextItem`, so it is sized by the same step that sizes every other constant-size text of that picture. Consequences: a bed-detail page of the PDF report and a tile of a scaled printout show the key only if they show that corner; the minimap and the canvas never show it. *Rejected*: painting the key from each export path (five call sites, the arrangement §8.9.16 was written against); painting it from the scene's foreground hook (it would be in the minimap and in every print tile).

**4. The hours on the contours are labels of the plan.** They were scene items under every plant and object, with a halo made of a second, wider copy of the text: on the family-garden example 32 of 64 had less than nine tenths of their glyphs visible. They are `PlanLabelItem`s without an owner now — the one halo, painted after every item, left out where two labels would touch — and rank below every object's own labels: where an hour and a name compete, the name stays. They are *placed* off plants and objects and off the plan's edge, for the zoom at which the plan fits a window; a contour that is covered all the way gets no label, because a number over a tree's crown names a line nobody can see there. After: 40 of 41 painted (one left out by the label pass), none cut, contrast 12.4:1 at least and 13.2:1 in the median, measured with the suite's own instrument (before: 8.4:1 in the median of the 32 uncut ones, the worst of them counted as unreadable). *Rejected*: raising the old items above the plants (two halos, no declutter, numbers on crowns); a paint-time test of every label against every object (the label pass runs on every repaint).

**5. While a map is shown, the time-of-day shadows are not painted.** The issue reads "the shadows stay on top of the map". They do not — the map's z is -450, the overlay's -500, since US-E4. But the map is translucent (alpha 32 where the ground is sunny all day), so the overlay showed *through* it: 33.5 % of the viewport's pixels changed with it on the family-garden example at 15:00, by 61 of 765 on average, and a 14-hour spot took a 6-hour spot's colour. Drawing it "under" the map is therefore what the defect was. With a key beside the map that is a wrong reading, so the overlay is hidden while a map is shown, on the canvas and in exports. Only its picture: the shadows are solved and published as before, because the 3D view lays them on its ground (`drape_polygons`), which itself shows one of the two at a time (`DrapeMode`). There is one toggle in the user's hands, "Hours of Sun"; the shadows are permanent since ADR-062, so no label is contradicted — but the time slider and "Animate" move nothing in the 2D plan while the map is on. *Rejected*: an opaque map; composing the map without the instant's shadow by subtraction (the overlay is under it, not in it — nothing to subtract).

**6. The sun-mismatch badge stays out of every picture of the plan** (the decision of #786 and FR-VIS-09, confirmed here: it is a warning about the plan, not part of it) and is drawn for the painter that shows it. It was a 24-pixel pixmap scaled with its plant and enlarged up to 19 times on the example, nearest neighbour. It is painted through the rule of every canvas bitmap now (§8.9.14), from the icon's vector, so there is no second rasteriser.

**7. The shadow's soft edge is a field.** Four stacked strokes are four flat bands (1.25 to 2.5 cm wide), and the innermost was 15 levels darker than the shade it edged; more strokes are more bands and more cost (the strokes were 95 % of the overlay's paint). The edge is a blurred raster of the shade read as a distance and mapped to a linear falloff from the shade's own tone to nothing at 7 cm — the reach the strokes had, and half the tone on average as they had (0.51). The shade's geometry is not touched: the full tone is the outline's fill to the pixel, and the 2D-3D shadow agreement and the golden caster tests are unchanged. Largest step of the falloff, of 97 levels: 29 → 15 at 100 %, 35 → 8 at 200 %, 39 → 4 at 400 %, 35 → 2 at 1000 %; flat runs of three pixels or more inside it: 2-4 → 0. The exact paint costs less where it was dear (48 → 17 ms at fit on the family garden) and more where it was cheap (3.3 → 10 ms at 400 %); §8.37. An SVG holds the edge as an embedded picture now, not as stroke outlines (+0.4 to +0.6 MB on the two examples), and still no `<clipPath>`. **The edge is never darker than the shade** (second review): blurred coverage is a distance beside a straight edge only, and in an inside corner, in the cusp between two round shades, in a sunlit hole or a narrow sunlit gap the first version painted sunlit ground up to 41 of 97 levels darker than the shade beside it. The falloff's weight is therefore clamped to the shade's own tone where the ground is painted, after the enlargement, at the device's resolution (a mask added to itself with saturation); where the shade has regions of different tone (#698) the limit is the darkest shade within the blur's reach, and beside one region alone that region's tone. What a concave place shows instead is the shade's own tone: an inside corner is rounded by the reach, and a sunlit gap between two shades is filled by the two edges that meet in it — measured in its middle: the shade's full tone up to a gap of 4 cm, 0.82 of it at 6 cm, 0.42 at 10 cm, nothing from 14 cm on (twice the reach). That is what a 7 cm soft edge on both sides of a gap means, but a gap of 4 cm that the geometry says is lit is painted as shade, so it is the owner's to confirm. The geometry, the solves, the 3D drape and the hours-of-sun map are untouched by it. Cost: 11.9 → 12.3 ms at 100 %, 8.2 → 9.5 ms at 400 %, 4.6 → 5.7 ms at 1000 % for the exact paint into 1149 × 821 pixels (§8.37). *Rejected*: clamping on the lattice — the cells the shade does not cover (a cell's width of too-dark ground is left along every concave outline: 29 levels in an 8 cm hole) or every cell (every falloff then starts under the shade's tone: a step of 3 levels and three flat pixels at 1000 %, a band again); more strokes; `QGraphicsEffect` blur (the scene avoids effects; it would blur the shade's own edge); a clip instead of cutting the shade out of a layer (`QSvgRenderer` ignores a clip, PF-CAN-53); three blur passes (half as dear again, no closer to the linear falloff).

**Not decided here** (#830, the owner's): the parasol as a raised canopy, what glasshouse glass transmits, and the 0 h cell under every plant — which is why contours still crowd round every solid.

## ADR-037 addendum — narrow gaps in the 2D soft edge (#880)

**Status.** Shipped in v1.40.10 (PR #978).

Keep the 7 cm reach confirmed in the #838 manual test. A gap up to 4 cm
and an enclosed hole of 8 cm can show at full shade tone because neighboring
feathers overlap. The overlay is a display of computed shade with a visual
falloff. The shadow solution, the 3D drape and the hours-of-sun map continue
to use the computed geometry. FR-SUN-03 states the display limit and the
measured widening sequence.

## ADR-037 addendum - the plan's north orientation (#663, 2026-11-11)

**Status**: Shipped in v1.39.1 (PR #903; owner's manual test 2026-11-12).

**Decision.** A plan-level `north_angle_deg` says where **true north** lies on the
drawing, in degrees clockwise from plan-up: 0 = up, 90 = right, 135 = down-right.
It is additive plan metadata in the `.ogp` (`FILE_VERSION` stays 1.4), read as 0 for
every older file and kept by a template export. **No object coordinate is ever
rewritten.** Rotating the whole drawing was rejected: it destroys the alignment of
an imported survey or satellite background, dimensions and construction geometry,
and cannot express "north is off the sheet".

**Frame rule.** `core.solar.scene_azimuth(azimuth, north)` returns
`(azimuth + north) % 360`. Scene +Y is plan-up (ADR-002), and the shadow and 3D
formulas read an azimuth clockwise from +Y, so a compass azimuth is turned **once**
into that frame. The 2D shadow overlay, the hours-of-sun sampling
(`daylight_samples`), the plant sun-exposure diagnostics, the 3D light (`SunState`
carries the compass bearing and the plan north, and `scene_azimuth_deg` is their
sum), and the 3D sun path and compass all use this rule; the PDF overview arrow
applies the same angle as a painter rotation. None of them invents its own sign. A sun
due east (compass 90°) on a plan whose north lies at 45° is at scene bearing 135° and
throws its shadow up-left. The issue's shorthand `solar_azimuth - north_angle`
assumed the inverse definition of the angle; the arrow's stated meaning (135° points
down-right) fixes the sign recorded here.

**Write path and staleness.** `SetPlanNorthCommand` is one undo step;
`ProjectManager.set_north_angle` is the only writer besides load and new, and refuses
a bool, a non-number or a non-finite angle **before** mutating. `ExposureSnapshot`
carries the angle, so a worker result computed for the old north is refused rather
than shown as current; the app invalidates the shown heatmap on every change. The 2D
`N` arrow is a viewport overlay (never an export); the PDF draws its own arrow with
the same angle.

Cross-refs: §8.20, §8.36; FR-SUN-14; PF-DOM-34.

## ADR-037 addendum: base stacking in the shared caster model (Phase 17, L1.6)

**Status**: Accepted (2026-10-11, #385 story L1.6); amended the same day after the senior review's first round — the membership half of decision 5, the container soil rule in decision 4, the strict caster type in decision 1 and the two gates of decision 3 are that round's — and after its second: the POINT the lift asks and the per-walk shape, both in decision 5. **Changes shipped 2D behaviour** — the sun & shade overlay (FR-SUN-03) and the hours-of-sun heatmap (FR-SUN-05) — for one class of item: a plant that is linked to, and stands inside, a soil container with a height (FR-SUN-11).

**Context.** The resolver above answers *how tall*; nothing answered *standing on what*. Every caster was a prism from the ground: a 60 cm perennial in a 40 cm raised bed cast as if it grew out of the lawn *through* the bed. Two consequences, both measured. (a) In 3D the same plant would stand inside its box, breaking the "Base" truth gate of `ogp-lush-cinematic` §1. (b) In 2D the plant was simply **invisible in the shadow map**: at a 35° sun its tip reached 85.7 cm past its footprint, the bed's own shadow 57.1 cm past the bed's edge — a plant in the middle of a bed never left the bed's shadow. Its real tip is 140.0 cm out. And the two views were about to disagree: 3D needs the base (L1.6 stands plants on their soil), the 2D casters had none.

**Decision.**

1. **A caster is a solid `footprint × [base, base + h]`** — `core/shadow_geometry.ShadowCaster(footprint, height_cm, base_cm = 0.0)`, a `NamedTuple` (plain data: it still crosses to the heatmap worker thread). `height_cm` stays `effective_height_cm`, measured from the caster's own ground. The shadow functions also accept the pre-L1.6 pair `(footprint, height)` — which stands on the ground — and **nothing else**: `caster_fields` unpacks by TYPE and raises `TypeError` for any other shape (a list, a bare 3-tuple, another named tuple), so a third element is a base only when a `ShadowCaster` says so. The first cut read any 3-tuple's last element as a height above ground.
2. **The shadow of a raised caster, defined once**: with the sun at elevation α and unit shadow direction `d`,
   `S(F, b, h) = { p + t·d : p ∈ F, t ∈ [b / tan α, (b + h) / tan α] }` —
   the footprint projected from the base, swept on to its projection from the top; equivalently the ground shadow `S(F, 0, h)` translated by `(b / tan α)·d`. The **tip lies `b / tan α` further from the sun** and so does the near edge: what is below the base is not this caster's shadow but that of whatever it stands on (the bed is a caster of its own, so the union stays one region). Implemented as one step in front of the unchanged sweep: `_caster_paths_int` translates the integer footprint by `round(b / tan α · d · 1000)` and then sweeps exactly as before.
3. **`base = 0` is the released code — and that is proven on every platform, by two gates that are not the same gate.** For a caster on the ground the translation step does not run, so the integer paths are the ones the old code produced. **(i) Platform-independent.** `tests/unit/shadow_geometry_v1_29_10.py` is `core/shadow_geometry.py` as released in v1.29.10 — the same git blob (`bde1030`), which the test checks — kept as an oracle. The released functions and today's return identical polygons and identical integer paths for 276 ground casters, a whole scene and a heatmap, compared exactly, on whatever machine the test runs: old and new then share its C library. This is what carries the claim "nothing on the ground changed". **(ii) A golden fixture** generated from the unchanged code pins absolute numbers: `compute_scene_shadows` over 120 footprint × height × sun cases, the caster walk and shadow unions of both bench plans, the real overlay's painter path at a high and a low sun, and the heatmap toy case. "Unchanged" is release **v1.29.10**: `core/shadow_geometry.py` and `core/shade_aggregation.py` are byte-identical to that tag (the generating commit `aaec048` and the fixture's first commit `8d1cd0a` are on branches a squash merge makes unreachable; the tag stays). **What the fixture enforces depends on the platform**: on win32, where it was generated, every float bit for bit and the SHA-256 of the bench plans' caster lists and unions; anywhere else — the CI test jobs run on Linux — the same structure (polygon and vertex counts, path element types), every coordinate within 2e-3 cm (two steps of pyclipper's 1/1000 cm grid) and every union area within 1e-6 relative, without the hashes. It cannot be made exact everywhere cheaply: a coordinate leaves the integer grid only as `k / 1000`, which is correctly rounded on any IEEE machine, so comparing integer paths instead of floats would change nothing; what can differ is how a value gets ONTO the grid — a sweep displacement is `round(sin(az) · h / tan α · 1000)` with the C library's `sin` / `cos` / `tan`, which are not correctly rounded everywhere. The tolerant comparison runs on every platform (it was dead code on the generating one), and `test_the_portable_comparison_can_fail` shows it refuses three grid steps, a lost vertex or polygon and a changed area.
4. **One rule for where an item stands** — `core/object_height.standing_base_cm(parent_type, parent_metadata, at_date)`: the **soil surface** of a soil-capable parent that has a resolved height, `0.0` for every other parent. `soil_surface_cm(type, h)` has two cases, because the plan says two different things. A **container** (`CONTAINER`, `CONTAINER_ROUND`, `WALL_PLANTER`) has its soil AT its resolved height: that height IS its soil fill height (the resolver above — the fill stands in for the above-ground height; the plan holds no rim), so the plan's one soil datum is not lowered for the look of a lip, and where the user overrode the height the soil is at the top they gave, so a plant never stands inside the solid. A **bed** (`RAISED_BED`, a `GARDEN_BED` that carries a height) has a rim height and no fill, so its soil is ASSUMED `SOIL_DROP_CM = 2.0` under the rim: `max(h − 2, 0)`. **`SOIL_DROP_CM` is a modelling assumption, not a datum of the plan**, and it moves shadows in the shipped sun study: the shadow of every plant in a raised bed shifts by `2 / tan α` — 7.5 cm at a 15° sun, 2.9 cm at 35°, 1.2 cm at 60°. (The first cut applied the drop to containers too, which put a plant in a pot 2 cm below the plan's own soil level.) "Soil-capable" is the repo's one predicate, `is_bed_type` (`SOIL_CONTAINER_TYPES`), mirrored by name in the Qt-free module and pinned against the real set (the module's existing convention); "above ground" is not a type property but *the parent has a height* — so an in-ground `GARDEN_BED` is the ground, a `GARDEN_BED` that carries a height is raised, and a `TRELLIS` (a plant parent that holds no soil) is the ground. A `GARDEN_BED` gets a height only through its metadata — a hand-edited or generated `.ogp`, or an item that had a height before its type changed: the properties panel offers no Height field for a garden bed without one, and no Agent API tool writes it. **No base is derived from a height beyond `MAX_PARENT_HEIGHT_CM`** (10 km — the scene contract's `MAX_LENGTH_CM`, mirrored into the Qt-free 2D module and pinned equal), as none is from an infinite one: a base is itself a length of a scene record, and one derived from a taller parent would be out of range, so the plant would lose its record over its parent's nonsense height (measured on the merged contract: a bed of 20 km took its plant out of the scene with it). That is ALL this bound says. **"Nothing stands on a parent the 3D scene does not hold" is not the height module's rule** — it cannot know which parents have a record — and is settled in `snapshot_records` (decision 5).
5. **One caller for items, and the link alone never lifts** — `ui/canvas/footprints.item_base_cm(item, lookup, at_date)` lifts an item only when BOTH hold: its `parent_bed_id` (a `GardenItem` property, never metadata) names a *visible* parent for which rule 4 gives a base, **and the item's stable geometric centre lies inside that parent's shape**. The second half exists because the link is bookkeeping, not geometry. *(Superseded in part by the #443 addendum below, 2026-10-29: every edit path now reconciles the link, and the link decisions ask `standing_point`; this paragraph records the L1.6 decision.)* The app evaluates it when a plant is created — one by one, in bulk or pasted (`core/commands._auto_parent_plant`, called by `CreateItemCommand` and `CreateItemsCommand`) —, when a selected plant is dropped after a drag (`CanvasView._update_plant_bed_relationships`) and when the agent moves a plant (`_agent_reconcile_bed_membership`, after `move_object` and `set_object_position`, which share one path); never when a BED changes — no resize and no vertex edit touches it — and `set_parent_bed` sets it on purpose without containment (`link_is_geometric: false`). In the first cut the link alone decided: a raised bed shrunk away from its plant left a plant on the lawn casting from 38 cm, and at a 15° sun its shadow began 141.8 cm away — 111.8 cm of lit ground between a plant and its own shadow, new wrong output in the shipped overlay and heatmap (senior review, round 1). **One predicate, two points.** The containment PREDICATE is the app's own construct, extracted once — `footprints.shape_contains(parent, scene_point)`, Qt's `contains` in the parent's frame — and asked by every link decision (auto-parenting, the re-link after a drag, the agent's re-link and its `link_is_geometric`, through `find_smallest_bed_containing` or `centre_is_inside`) and by the lift; a drift guard counts the construct in both of its spellings. The POINT it is asked with differs, deliberately (review round 2). The link decisions keep theirs exactly as shipped: `bed_membership_point`, the centre of the item's `boundingRect()`. The lift asks `standing_point`, the item's stable geometric centre — `item_outline`'s anchor in scene coordinates: a plant circle's mapped centre, the origin of its footprint and of its 3D record. The two are one point until something is painted asymmetrically over the plant: the antagonist badge grows the bounding rect towards +x / +y by `0.3 · min(0.45 · radius, 12)` cm, which moves its centre by up to 1.8 cm along EACH axis — 2.55 cm in all, the margin against an edge at 45° (pinned on a bed turned by 45°: a plant 2.2 cm inside the edge is outside for the link decisions). Round 1 asked the lift with the link point, and a linked plant 1 cm inside its bed's east edge read base 38 without the badge and 0 with it — in the 3D record and in the 2D caster: a shadow that flipped with a warning. Where a solid stands must not depend on what is painted over it. **So within the badge's margin of a bed's edge a link decision and the lift can differ**: a plant created under a badge 1 cm outside a bed's west edge is linked and stays on the ground; `set_parent_bed` can report `link_is_geometric: false` for a plant that is lifted. Shipped parenting behaviour is not changed here — the badge dependence of the drop-time decision goes into the follow-up issue. `TestWhichPointEachDecisionAsks` pins the point of each of the six decisions (before it, swapping the link point for the geometric centre passed every parenting, agent-write, container, trellis and base-stacking test). **The parent's shape is built once per walk** — `ItemLookup.shape_of`, handed to `shape_contains`: Qt's `contains` rebuilds an item's shape on every call, 240 times a walk on bench_large. A lookup therefore lives for ONE walk (kept across a bed resize it still answers 38): a source-reading test holds that the identifier `ItemLookup` appears in the application only as an import, the class, a parameter's annotation and a call inside the two walks, and that a lookup is handed to `item_base_cm` / `_record_of` and to nothing else (what a reading cannot see — a dynamic spelling such as `type(lookup)(…)` — is stated in the test). **A parent that got no record lifts nothing, whatever the reason** (review round 3): `snapshot_records` knows, once every record is built, which parents the 3D scene holds — a raised bed 30 km wide is `out_of_range`, another's outline cannot be built, a third's record failed — and puts every record whose parent has none on the ground. Before, such a plant stood at 38 over nothing. The 2D casters are a different view with their own facts and are not touched: there that bed casts, and its plant casts from its soil. Otherwise base 0 — exactly the behaviour before L1.6. `item_base_cm` is called by `collect_shadow_casters` (→ overlay **and** heatmap, which share that one walk) and by `snapshot_records` (→ `transform.base_cm`). A parent that is not *visible* is not there: it casts nothing and has no solid, so its plants stand on the ground rather than float.
6. **The overlay's change key carries the base**, so an edit that changes only what a plant stands on (a re-parent) recomputes.

**What changes for the user.** A plant on raised soil now casts from the soil: its shadow tip is `base / tan α` further out (54.3 cm for the example above; 141.8 cm at a 15° winter sun) and the plant becomes visible in the overlay and in the hours-of-sun map where it was hidden inside its bed's shadow. Everything on the ground is unchanged (decision 3). On the bench plans: 22 of 87 casters (bench_small: 19 at 38 cm in raised beds, 3 at 30 cm in pots) and 240 of 379 (bench_large) are raised, and every one of them stands inside its parent.

**Known limits — a plant can be IN a raised bed and not ON it.** *(Superseded for the link half by the addendum below, 2026-10-29: membership is now reconciled by every edit path and both decisions ask the same point. The nesting limits (c)/(d) remain as described.)* The rule needs the link, and the app does not reconcile links (follow-up issue: *bed membership is not reconciled when a bed is created or resized* — which also takes the link decisions' dependence on the antagonist badge, decision 5). Three standing states, each pinned by a test so that the reconciliation, when it comes, changes them knowingly. **(b) A raised bed drawn around a plant** links nothing: the plant has no parent and stays at ground level — in 2D it casts from the ground, inside the bed's own shadow; in 3D it is drawn inside the box — while the same-looking plan drawn bed-first gives 38. **(c) A climber on a trellis that stands in a raised bed** is linked to the trellis, the smallest parent that contains it; a trellis holds no soil and has no base of its own (parents do not nest), so the climber is at 0 while its neighbour in the same bed is at 38. **(d) A pot standing on a raised bed** is on the ground — only plants carry a parent link — and its plant stands at the pot's own soil, 30, not at 68. Case (a), a bed resized away from its plant, is what decision 5's second half handles: the link survives, the plant is back on the ground. **Two more ways into the same state** (found in the last review pass; shipped behaviour, pinned in `TestCopiesAndMovesFollowTheLink`): a plant **mirror-copied** into its source's raised bed without the bed gets no link — base 0 beside its source at 38 —, and an **array copy** takes its source's link unevaluated and is missing from the bed's child list — inside the bed it stands at 38, outside at 0 with a stale link. And two moves the link does not follow: a linked plant moved by anything but a mouse drop or an agent move keeps its link (where it stands still follows its centre: 38 → 0 → 38), and a bed moved by a typed coordinate or by align / distribute leaves its plants where they were, linked and on the ground.

**Alternatives considered (rejected).**
- *A base only in 3D.* Two answers to one question; the Split view would show a 3D shadow and a 2D overlay that disagree by half a metre.
- *Lift the height instead (`h' = h + base`, base 0).* The tip would be right and the near edge wrong — the plant would also shade the ground under and beside its bed's far side that the bed alone does not — and the 3D solid would be a pole from the ground.
- *A new name set for "raised parents" (the spike's four names).* It left out a `GARDEN_BED` with a height and would drift from `is_bed_type`; the height test needs no list.
- *Counting a hidden parent.* Its plants would float in 3D and cast from thin air in 2D.
- *The link alone as the test (the first cut).* Decision 5: the link is not geometric, and a bed resized away from its plant produced a shadow that began 1.4 m from the plant.
- *The link decisions' point for the lift (the first round's fix), or the stable centre for the link decisions too.* The first lets a shadow flip with a badge (decision 5). The second is the cleaner end state and changes shipped parenting behaviour — which plants a drop links at a bed's edge — so it belongs to the follow-up, not to a story about where solids stand.
- *Guessing a parent from geometry where there is no link* (which would also lift cases b and c). It would make the base disagree with the Properties panel, the bed's plant list, the soil-mismatch borders and the agent's read tools, which all follow the link; the place to fix a missing link is where links are made.
- *The bed's 2 cm soil drop for containers too (the first cut).* Decision 4: a container's height is its fill height.
- *Tightening the golden's non-Windows tolerance blind, or comparing integer paths.* Decision 3: neither removes the C library from the path onto the grid; the released-code oracle does the proving instead.
- *Fixing the closed-polyline footprint in the same change.* `polyline_footprint` of a closed line returns an outer ring and a hole, and both shipped consumers shade the enclosed area. It is a separate defect with its own issue; the golden deliberately pins today's behaviour, defect included, so this change proves it moved nothing else.
- *Keeping the 2-tuple and adding a parallel list of bases.* Two lists that must stay in step; six test call sites unpack the tuple and now name the third field instead.

**Consequences.** The rule costs time on the two walks every edit runs. Measured on bench_large (505 items, 240 lifted plants; best of 80, three alternating runs per tree, a shared machine): the caster walk 3.7–4.0 ms before L1.6, 6.5–6.9 ms after round 1, **5.0–5.3 ms** now; `snapshot_records` 8.5–8.8 / 12.1–12.5 / **9.9–10.6 ms**. Per lifted plant the rule takes 2.8 µs — of round 1's 7.6 µs (its parts, summed), 4.1 were the plant's `boundingRect()` (a Python override; the stable centre costs 0.3) and 1.4 the parent's shape rebuilt per plant. A plan without raised soil pays nothing: the geometric test runs last, and only for an item that would be lifted. `collect_shadow_casters` returns `list[ShadowCaster]`. `transform.base_cm` of a scene record is real (ADR-059): a bed that changes height reaches its plants as `update_transform` — no plant mesh is rebuilt — and a re-parent is a transform change (it was an empty diff). No `.ogp` change, no `FILE_VERSION` bump, no user-visible string. Not changed: the shipped Qt 3D view (`collect_scene3d_records`) still extrudes a plant from the ground; it has no shadows and retires in L1.10. Parents do not nest (only plants are parented), so there is nothing to sum.

**Validation.** `tests/unit/test_shadow_caster_base.py` — tip shift = `base / tan α` at 15° / 35° / 60° × five azimuths × three footprints (≤ 0.1 cm; measured ≤ 2e-3, the integer grid); `S(F, b, h)` = the translated ground shadow; a ray oracle that knows no polygons (a ground point is shaded iff the ray toward the sun crosses the solid), 4,000 points per case; the bed casts the part below; `TestTheGroundPathIsTheReleasedCode` — the v1.29.10 functions against today's (decision 3 i); `TestACasterIsATypeNotALength`; the soil rule for beds and for containers. `tests/integration/test_shadow_caster_golden.py` — the golden on every platform as far as that platform can hold it, plus on both bench plans: same walk, grounded union unchanged, ground casters unchanged, raised count = an independent oracle's. `tests/integration/test_scene3d_base_stacking.py` — gate G3 through a real scene; 3D base = 2D caster base for nine parent cases; `TestMembershipIsReconciledAndTheLinkAloneNeverLifts` — (a) the bed shrunk with the real resize command now UNLINKS the plant, (b) a bed drawn around a plant links and lifts it, (c)–(d) the nesting limits, an explicit link without containment, and the one-predicate drift guard; `TestWhereAPlantStandsDoesNotDependOnABadge` — badge on and off: the 3D record, the 2D caster base and the real overlay's path unchanged; `TestLinkAndLiftAskTheSamePoint` — create, bulk create / paste, the drop, the agent's move re-link and `link_is_geometric` on the real application window, all asserting the SAME standing point; `TestCopiesAndMovesFollowTheLink` — array and mirror copies, moves in and out, and a bed moved by align/typed coordinate; `TestTheParentShapeIsBuiltOncePerWalk` — the cached path against Qt's `contains` on 7,128 points over four parent shapes, one shape per parent and walk, and the lookup's lifetime (constructed only in the two walks, never kept); `TestTheOneRule::test_a_parent_without_a_record_lifts_nothing` (30 km wide; a failed record; an unbuildable outline) and `::test_a_plant_is_grounded_whichever_of_the_two_is_stacked_higher`; `TestTheOverlaysOwnEcho` — the overlay's own `scene.changed` echo, made deterministic; one caster walk and its consumers (AST guard); a bed height change and a re-parent reaching the real overlay through the command stack; `TestHeatmapEndToEnd` — a raised plant through `SunHeatmapController` and its worker, the tip read off the grid. `tests/integration/test_bed_membership_reconciliation.py` — the #443 edit paths and their one-step undo. `tests/unit/test_object_height.py::test_soil_parent_names_match_the_soil_predicate`.

## ADR-037 addendum — bed membership is reconciled by geometry (#443, 2026-10-29)

**Status:** Shipped in v1.34.9 (PR #649) after owner manual acceptance on 2026-10-30.

**Context.** Decision 5's second half ("the link AND the centre inside the parent")
made the lift honest, but the LINK itself was only evaluated on a few paths: a
plant's creation, a mouse drop, the agent's move. Everything else kept whatever
link it had — a bed resized, turned or vertex-edited away from its plants; a
bed drawn around standing plants; a plant moved by the arrow keys, a typed
coordinate or align/distribute; a plant moved INTO a bed; every array copy
(which inherited its source's `parent_bed_id` while the bed's `child_item_ids`
never held it); a mirror copy without its bed; a bed moved by a typed
coordinate or align/distribute (which left its plants behind). The Properties
panel, the soil-mismatch and companion logic and the diagnostics could follow
a link to a bed the plant no longer stood in, or miss one it did. The link
decision's point was also the centre of `boundingRect()`, which the antagonist
badge moves by up to 1.8 cm per axis, so it could disagree with the lift.

**Decision.**

1. **One rule.** A plant's link is the smallest plant-parent
   (`find_smallest_bed_containing`) that contains its **standing point** —
   ``footprints.bed_membership_point`` now returns ``standing_point``. The link
   decision and the lift therefore ask the SAME question; a badge, a selection
   or a spacing ring can change neither.
2. **One mutator.** ``core/commands.set_parent_link(scene, plant, parent_id)``
   sets ``parent_bed_id`` and the parent's ``child_item_ids`` together (and heals
   a stale id whose child list never got it). ``_auto_parent_plant``,
   ``SetParentBedCommand``, the neighbourhood reconcile and every command below
   call it. A few deliberate writers still set the id directly; the
   authoritative list is ``set_parent_link``'s docstring (the loader, delete
   snapshots/restores, the paste/duplicate remap, and the mirror tool's remap
   and identity stamp).
3. **Every edit path applies it, in the same undo step.**
   ``MoveItemsCommand``/``AlignItemsCommand`` reconcile after moving (covering
   arrow keys, typed coordinates, align/distribute and constraint propagation)
   and expand a moved plant-parent with its children; ``ResizeItemCommand`` and
   ``RotateItemCommand`` carry a ``BedMembershipChange`` tracker for a plant or
   plant-parent edit; ``AddConstraintCommand`` and
   ``EditConstraintDistanceCommand`` build that tracker from the payload —
   moves, rotations AND vertex moves — at each ``execute``, because the
   constraint tools trial-execute, undo and only then inject the solver payload;
   the live-applied drag paths (resize, corner edit, vertex edit) go through
   ``register_applied_with_membership``; the create, paste, duplicate, array and
   mirror commands reconcile the items they add; a new bed reconciles the plants
   that already stood where it lands. ``undo`` restores the recorded links, so
   one Ctrl+Z reverses geometry AND membership. (The properties panel's trailing
   live constraint-solver pass and the fillet/chamfer + object-type conversions
   are not routed through this yet; the next edit of the plant or its parent bed
   re-decides them.)
4. **A copy never inherits its source's link.** Array, mirror-copy and paste
   paths drop the serialised link for plants and let geometry decide; a
   non-plant child's deliberate remap (mirror of a bed with its contents) is
   kept.
5. **An explicit link is not overruled until the next geometry edit.**
   ``set_parent_bed`` / the panel's Link action may link a plant outside a bed
   (``link_is_geometric: false``); the link alone still never lifts it, and
   the plant's next move re-decides it. This is deliberate: the user's Link
   action is a decision, not a stale link.
6. **Nesting is unchanged (decision (ii) of #443).** Only plants carry a link;
   parents do not nest, so the smallest parent wins and the base is that
   parent's soil — a climber on a trellis inside a bed stands at 0, and a pot's
   plant at the pot's soil, not the sum. A nesting model is a separate feature.
7. **"Inside" keeps Qt's shape semantics (decision (vii) of #443).** The
   predicate is the parent's own ``shape()`` (with its clip path), which
   includes half the pen stroke for polygons and round containers. The lift and
   the link ask the same predicate, so they agree; changing the definition
   would move every plan's soil line and is not part of this fix.

8. **Explicit constraints outrank implicit bed carrying (#649 review, 2026-10-30).**
   A child with its own constraints keeps its solver-controlled position, or
   stays where it is when outside the solve component. Only unconstrained
   children inherit the parent's translation. This includes FIXED and zero-delta
   solver results. The shared `bed_child_has_constraints` predicate applies to
   live propagation, move/align expansion and one-shot constraint commands.
   Membership is reconciled against the resulting geometry. The agent's
   existing preflight remains stricter: a bed move with any constrained child
   refuses the entire operation before geometry or history can change.
9. **No-op means the complete gesture is unchanged.** Returning a rotation to
   its initial angle can leave partner translations or vertex corrections.
   Such changes still produce one undo entry; a click without any geometry
   change produces none.

**Consequences.** ``.ogp`` unchanged (``parent_bed_id`` already serialised; the
loader's ``_relink_parent_child_relationships`` remains the file-level heal).
One gesture is still one undo entry. Cost: a plant move tracks only that plant
(one containment query); a focused bed edit tracks the scene's plants and asks
``find_smallest_bed_containing`` per plant, which scans the scene's items —
O(plants × items) per bed edit, fine at plan scale but not a hot path. It only
CHANGES links whose target or current parent is that bed, so a deliberate link
to another bed is left alone. Each changed link refreshes its layer's z once.
The agent's move/set-position reconcile and the drag-release link commands
remain as belt-and-braces and are idempotent. FR-SUN-11 and FR-STACK-10's known
limit (b) are updated; the tests that pinned the old behaviour in
``test_scene3d_base_stacking.py`` changed knowingly (classes
``TestMembershipIsReconciledAndTheLinkAloneNeverLifts``,
``TestLinkAndLiftAskTheSamePoint``, ``TestCopiesAndMovesFollowTheLink``).

**Validation.** ``tests/integration/test_bed_membership_reconciliation.py`` —
resize/turn/vertex of a bed, plants moved in and out, a bed moved over a plant,
a bed moved with its plants, array copy links by landing position, an explicit
link surviving until the move, undo/redo of each; plus the updated pinned suite
above. The full suite, ruff, bandit and the frozen exe gates ran before the
draft PR.

## ADR-037 addendum — one resolver for (height, source) (#581, 2026-10-25)

**Context.** L2's info card added `height_source_at` beside `effective_height_cm` and
`height_source`; the three carried hand-copied versions of the same precedence ladder
(custom → container → grown → current → species → default). Any change to the ladder had
to be made three times.

**Decision.** `core/object_height.resolve_height(object_type, metadata, at_date)`
returns `(height, source)` and is the only implementation. `effective_height_cm` returns
`resolve_height(...)[0]`; `height_source` and `height_source_at` return the source from
the same call (with and without the date). The public names, their docstrings and their
answers are unchanged; the private `_species_height_cm` copy is gone. The growth branch
is the only date-dependent one and reports `SOURCE_GROWN`.

**Pins.** `tests/unit/test_object_height.py::TestOneResolver` projects the public
functions from the resolver over explicit/container/species/current/grown/default/none
cases and checks the grown source; all existing precedence, shadow and 3D height tests
are unchanged. No `.ogp`, UI or behaviour change.

## ADR-037 addendum — one caster's ring set is one REGION (#444, 2026-10-27)

**Status**: Accepted. **Changes shipped 2D behaviour** — the sun & shade overlay
(FR-SUN-03) and the hours-of-sun heatmap (FR-SUN-05) — for exactly two classes of item:
a fence, wall or hedge stroke whose centre line closes on itself, and an outline that
crosses itself. It closes the alternative this ADR's base-stacking addendum deliberately
left open ("*Fixing the closed-polyline footprint in the same change* … a separate defect
with its own issue").

**Context.** A closed polyline comes back from `PyclipperOffset` as an outer ring **and a
hole** (`polyline_footprint([(0,0),(1000,0),(1000,800),(0,800),(0,0)], 10)` → +818,062
and −782,100 cm²). `_caster_paths_int` normalised each ring counter-clockwise and swept it
as a **solid**, so the hole cast the shadow of a slab the size of the enclosed garden.
Measured on master (`81d2b62f`, and in v1.30.0 as shipped): a 10 m × 8 m loop, 10 cm
stroke, 1.2 m high, 60° sun, azimuth 180° — **888,037 cm² of shade where the stroke's
prisms give 174,526 cm²**. The issue's four-rectangle reference gives 174,564: the 38 cm²
is the ring's own chamfered corners (outer area 818,062.1, not the rectangles' 818,100),
so the repaired ring's figure is the exact one for the outline the plan holds. A
self-crossing outline had the same shape of defect: `[(0,0),(400,300),(400,0),(0,300)]` at
300 cm and 60° drew **80,000 cm²** where its two lobes' prisms give **129,282 cm²**, and a
pentagram of radius 400 drew **334,617 cm²** where its five lobes give **321,565**.

**Decision.** One caster is one REGION, and the region is repaired once per WALK, where
the item is still known — `core.shadow_geometry.shadow_region(footprints)`.

1. **Detection is structural, not a type test.** A ring set needs the repair when (a) some
   ring's enclosed area is negative while there is more than one ring — a hole — or (b)
   some ring's even-odd decomposition is not exactly ONE ring (`SimplifyPolygons`) — a
   self-crossing outline. (b) is not an area difference: a pentagram decomposes into an
   outer plus a hole whose total area is SMALLER than the ring's printed area (235,114
   cm² printed, 124,108 in five lobes), so the sign of that difference is not fixed. A
   LONE ring is never a hole whatever its winding: a solid drawn clockwise is a solid,
   and the sweep already normalises winding. Everything else is returned **point for
   point**, which is what keeps `tests/fixtures/shadows/shadow_golden.json` valid — every
   footprint it pins
   is a simple ring (measured: no hole-bearing and no self-crossing caster in
   `bench_small.ogp`'s 87 or `bench_large.ogp`'s 379).
2. **A hole is cut open by a zero-width slit.** `_bridge_holes_int` runs a vertical ray
   from the hole's topmost vertex to the nearest boundary above it (at x offsets
   0, ±1, ±2 … grid steps; a ray that still lands on a vertex duplicates it, and the
   region is exact either way — measured), and the ring visits it down
   and up again. The slit encloses no ground, so the ring's region is exactly
   `outer − holes`; the sweep of a region is the sweep of its rings, so nothing else
   changes. Holes are bridged highest-first, so a lower hole's slit meets the boundary
   above it and the result stays simple; a hole is attached to the INNERMOST outer ring
   that contains it. Containment is asked of ONE vertex normally — a full scan would be
   O(vertices × vertices) and cost seconds on a crafted 16,384-point closed fence — and a
   MAJORITY only when that vertex lies exactly on the boundary, which is how two pieces
   of a pinched outline (sharing that vertex) are told apart.
3. **A self-crossing outline is split into its lobes** by `SimplifyPolygons` (even-odd),
   and each lobe is swept as the solid it is — whichever way the outline winds. A
   mirrored or clockwise star draws the same ground as a counter-clockwise one, and the
   app's own mirror tool flips the winding, so the split must not ask the ring's sign
   whether it is a hole (measured: a clockwise pentagram swept as one ring also drew
   334,617 cm² where its lobes give 321,565). The SIGN selects that branch; the ROLE is
   decided by CONTAINMENT, because a lone reversed solid has a negative sign too: a ring
   whose majority of vertices lies strictly inside another ring is a hole (its lobes
   reversed), and one inside nothing is a solid (its lobes positive). "Crosses itself" is decided by the
   decomposition returning more than one ring — not by an area difference, because a
   pentagram decomposes into an outer **plus a hole** whose total area is SMALLER than
   the ring's printed area (printed 235,114 cm², five lobes 124,108). Measured: one
   5-vertex pentagram swept as one ring drew 334,617 cm² where its five lobes' prisms
   give 321,565 cm². Above `MAX_REGION_VERTICES = 256` the test is skipped, so a
   crafted 16,384-vertex outline pays no `SimplifyPolygons` call on every walk (measured
   257 ms) and is swept exactly as it was before this repair — the hole half of the
   repair has no such bound.
4. **The role of a ring is its winding sign**, which is what every pyclipper offset hands
   out; a negative ring inside no outer ring is kept as a piece of its own rather than
   dropped (it is a caller's lone reversed ring, not a hole).

The repair lives in `collect_identified_casters` — the one walk the overlay
(`collect_shadow_casters`), the heatmap (`compute_grouped_shadows`) and the per-plant
estimates all read. `item_footprints` is unchanged: it answers *which ground does the
item cover* (the 3D records and the golden-pinned extraction), not *what does this shadow
sweep*. The sweep functions still take simple rings; a hole passed to them on its own
would still be cast as a solid, which is why the repair is not inside them.

**Cost, and the gate that keeps it.** The repair needs `pyclipper` work, so the walk asks
for it only where the extractor can have produced something to repair: more than one ring,
or `footprints.footprints_can_self_cross(item)` — True exactly for a `PolygonItem`, whose
vertices are the user's own order (a polyline's crossing centre line is resolved by the
offset into separate rings, and circles, ellipses and rectangles are generated from a
centre/radius/rect). Measured on bench_large (379 casters: 320 circles, 56 rectangles, 2
polygons, 1 polyline; best of 30, Windows, against an `origin/master` worktree in the same
session): **10.5 ms a walk with the repair on every ring, 6.7 ms with the gate, 6.8 ms on
master.** The base-stacking addendum measured this walk at 5.0–5.3 ms, so the gate restores
the released cost. A ring above `MAX_REGION_VERTICES = 256` skips only the self-crossing
test: the loader's ceiling is 16,384 vertices and one `SimplifyPolygons` call costs 0.12 ms
at 256, 20 ms at 4,096 and **257 ms at 16,384**, per walk. The premise is measured, not
asserted: `tests/integration/test_shadow_region.py::test_only_a_polygon_s_own_outline_can_cross_itself`
walks every `OUTLINE_SHAPES` value, checks the predicate and that each non-polygon ring is
one positively wound ring, and pins that a crossing closed polyline arrives as several
rings. Two known limits of this decision, both stated rather than hidden: a self-crossing
outline above 256 vertices is swept as one ring (as it was before this repair), and an
outline whose crossing the decomposition resolves into ONE ring would not be detected (no
such ring was produced by 4,000 fuzzed 5–9-gons; a ring that touches itself is resolved
into two).

**Validation.** `tests/integration/test_shadow_region.py` - both before/after numbers
above; a pentagram whose decomposition is an outer plus a hole; a clockwise and a
mirrored pentagram and a pinched outline in both windings and through the mirror tool
(the winding must not decide the role); a hole inside an island
inside a hole (the innermost-outer rule); a **ray oracle** that knows no polygons (a
ground point is shaded iff some point between it and the sun's footprint of it is in the
region) agreeing with the polygon answer on every cell of a 20 cm grid over the loop, and
rejecting the old answer on >1,500 cells; the simple-ring pass-through (including a
clockwise ring); a 16,384-vertex ring passing through with no `SimplifyPolygons` call at
all (the vertex bound, pinned by a monkeypatch that raises); idempotence; the
walk handing out one ring and one `ShadowCaster` for a closed `FENCE` item; the real
`SunShadowController` overlay leaving the garden inside a loop in the sun while still
drawing the fence's own shadow; and a self-crossing `PolygonItem` in a plan keeping both
lobes. The full golden gate is unchanged - regenerating it was not needed and was not
done. The mutation check keeps its shadow mutants killed (`scripts/mutation_check_built_world.py`).

**Left out.** The pore/gable modelling of a porous fence or a gabled roof (#440) is a
product decision and stays open. The 3D meshes of fences and walls are not the prisms
this ADR casts (ADR-059). The mesh of a closed loop in 3D still builds its own shape,
not this region. Nothing serialized; no `FILE_VERSION` change; no new user-visible string.

## ADR-037 addendum — every item with a footprint can be given a height (#628, 2026-10-27)

**Context.** The precedence ladder above honours an explicit `object_height_cm` for ANY
type, and `lies_on_ground` already yields the moment a ground surface has one. The
Properties panel, however, showed its Height field only when
`has_height_semantics(type, metadata)` was true — and for a type with no per-type default
that predicate's last clause is "an explicit height already exists". The field that would
create that value could therefore never appear: a generic polygon (the owner's star), an
in-ground bed, a terrace, a pond, a lawn, a path and a driveway had no way to become a
solid, and the only workaround was to change the object's TYPE to one with a default
(Garage), losing its look and its 3D builder.

**Decision.** The question splits in two. `has_height_semantics` stays the TYPE-level
answer (a default, a container's fill, a plant's species/measurement, or an explicit
value). The new `shows_height_field(object_type, metadata, has_footprint=...)` answers
what the panel asks: true for every item that HAS a footprint — asked of
`footprints.item_has_footprint(item)`, the yes/no form of `item_outline(item)`, which the
casters and the 3D records use — and for every type with height semantics. The yes/no form
exists because the panel asks it for every selected item on every rebuild and materialising
a 16 000-vertex polygon's outline to answer it cost 8.9 ms; a drift guard pins it equal to
`item_outline(...) is not None` over every placeable kind, including the one clause that is
not a class check (an ellipse with no area has no outline). "Auto" (0) remains no height,
so an object that was not given one behaves exactly as before: a lawn, path, terrace,
driveway or pond keeps lying on the ground (and under the sun overlays, FR-STACK-09), and a
generic shape casts nothing and stands as nothing in 3D. Typing a value stores the explicit
override, one undo step, and that is all: the ladder, `is_solid_soil_parent` (a mounded bed
becomes a soil parent), the shadow casters and the 3D builders already agreed.

**Not offered.** An item without a footprint — a text annotation, a callout, a group, an
arc, a bezier or a journal pin — has no closed outline to extrude, so the field stays
absent (pinned for all six through the real panel).

**Pins.** `tests/integration/test_height_property.py`: a generic rectangle shows the row,
reads "Auto", stores 150 on one undo step and clears back to none; a terrace's
`lies_on_ground` flips when it is given 30 cm; the six outline-less kinds have no row; and
the whole set (generic polygon/rectangle/circle/ellipse, in-ground bed, terrace, pond,
lawn, path, driveway) offers the field with the "No height — no shadow on the 2D plan"
tooltip; a generic polygon given a height becomes a caster with a non-empty shadow and
stops being one when cleared.
`tests/unit/test_footprint_predicate.py` pins `item_has_footprint` against `item_outline`
for every placeable kind. PF-UI-29 records the class ("a control that is the only way to
set a value must not be gated on the value existing"), and FR-SUN-02 states the rule.

**Follow-up — the solid keeps the fill the ground baked (owner manual pass of #627).** The
field worked, but every surface the owner raised lost its texture: a 40 cm lawn became a flat
green slab and a 10 cm soil bed a plain brown one, because a solid was ONE tinted prism and no
3D solid had ever shown a fill pattern (a height on these kinds could not be set before this
requirement). The fix is a part flag and one picture rule: `MeshPart.fill_texture` says "this
part shows the item's own fill", and the sink supplies
`core.fill_patterns.tinted_pattern_pixels` — the very picture the 2D brush paints (the same
`_tint_texture`, RGBA8, opaque, its mean the fill colour) — as `vcPart`'s `baseColorMap`
(the Model's `patternMap`). It is per (pattern, colour), shared and refcounted by the sink
(`release_fill` with the last Model), so a recolour is a material update and leaves no texture
behind. UVs are `(position + paint_origin) / PATTERN_TILE_CM` — `paint_origin` is
`params["paint_origin"]`, the anchor the canvas phases the fill from, so the solid shows the
bake's own picture: NCC **0.995** against the bake with the mesh's own UVs on a real
rectangle (MULCH; BRICK 0.995), while the opposite sign reads 0.759 / 0.866
(`tests/integration/test_scene3d_fill_phase.py`, measured 2026-10-27) — and the 256 cm ruler is
pinned against every shipped texture's size. A SOLID fill has no picture and shows its colour
through the same `set_part_fill` call, so the two cases cannot diverge. A GARDEN_BED's soil cap
is the item's fill too — the Properties panel calls it "Boden-Substrat" — while a raised bed's
and a container's soil stay the builder's palette soil, and a raised deck keeps its boards.

**Second manual pass — the TOP keeps the picture, the SIDES are the tint, and a lawn still
grows (2026-10-28).** The owner confirmed the field and reported three residues, each a
different layer:

- **A raised lawn lost its blades** ("looks like a lower quality setting"). The fill picture is
  the paint; the *blades* are the relief geometry that made the ground lawn read as grass, and
  `_lawn` returned the plain prism at a height. It now builds the solid AND the sward, lifted to
  the new top. `top_cm`/`fit_scale` and `verify_builder`'s G1 height gate ignore `ground_detail` parts:
  relief standing 0.3-9.4 cm above the solid (swept h = 1..200; 20.3-29.4 cm for h = 20) is not
  the item's height, and counting it failed G1 for every raised lawn - the blades are the one
  registered relief, so the exception is written into the gate rather than hidden in a test.
- **One fill-textured prism smeared the picture down the sides** (a lawn's grass stretched the
  full height of the edge, a generic shape's pattern ran down its wall). The canvas paints a
  texture on the TOP and no texture down an edge. A raised flat surface is now TWO Models:
  tinted sides (`walls_mesh`, no UVs) and a fill cap (`cap_mesh`, plan UVs). `default_builder`,
  `raised_surface` (a terrace/platform) and the raised lawn share one helper. `plain_block` — a
  building's or an odd outline's honest block — stays one tinted part.
- **A raised pond was the flat fill colour** ("the water became unreflective"): `_raised_pool`
  drew its water with the water material's tint only. The water part now takes
  `fill_texture=True`, and `water.frag` samples it through a `TextureInput` (`uFill`, gated by
  `uHasFill`) as its albedo — linearised with the ground's own polynomial — while keeping the
  hue-in-every-mood rule and the sky reflection. A ground pond has no picture and is unchanged.
- **A bed dragged on its own left its child plant behind** (found by the review of the fix
  above, pre-existing): the child's origin was recorded as `child.pos() - delta` on its first
  sighting, when it had not moved yet, so a two-step drag left the plant short by the first
  frame and undo overshot it the other way (measured: bed +600 cm, plant +300, undo -300). The
  origin is the child's own position; the bed's cumulative delta is then the whole story.
- **A plant dropped into a bed linked, but Ctrl+Z undid only the link** — the move and the link
  were two stack entries. A finished drag now executes its move and the links it decides as ONE
  `CompoundCommand` (`core/commands.py`), which undoes in reverse. The link commands are asked
  where the drag LEFT everything — its final positions — so a bed dragged in the same gesture is
  found at its new place and a plant that travelled with it keeps its parent (a first version
  predicted the centre from the pre-drag point plus the delta, against beds still at their old
  place, and unlinked the plant).

**Why a picture and not a luminance map multiplied by a tint.** The obvious smaller design — a
greyscale detail map per pattern with the fill colour as the tint — was rejected: an 8-bit
texture has no value above white, so every texel brighter than the pattern's mean would clip.
For soil those bright specks are what make it read as soil (the owner's L4 pass made the same
point about the 2D fills). The engine holds 256 KB per picture actually in use (the tinted
QPixmap it is made from is another 256 KB, shared with the canvas and cleared with its
200-entry cache), and the sink's refcount is what keeps the engine side bounded.

**One tint rule.** `materials.part_tint` is the ONE answer every engine read-back compares
against (the render driver, the engine test, the adapter's double): a `fill_texture` part is
white when its pattern has a picture — the picture carries the colour — and the fill colour for
SOLID. `set_part_fill` still writes `tintLinear` from the fill colour when `tint` is white,
because the X-ray screen door samples no picture and must ghost in the colour: left at 1, a
faded raised lawn measured a white ghost (max 255) instead of its green.

**Measured** (dev box, Direct3D 11, 1000 × 400 top-down frame, two 300 cm squares at 40 cm): the
GRASS square's top reads luma std **26.0**, the SOLID one **0.0**, at the same mean (121.3 /
120.8) — the texture is there and the average brightness is the fill colour. A raised lawn's
blades measure 20.3–29.4 cm above the ground for a 20 cm lawn (rooted on its top, ±30 %
variation), and its sides carry no UVs. A raised pool's water carries PLAN UVs, without which
`texture(uFill, UV0)` sampled one texel: measured luma std **17.25** with the UVs against
**0.000** (7.1e-15) without, on the same 300 × 220 cm pond at 40 cm. Engine traps, measured: `baseColorMap: patternMap` logs
"Unable to assign [undefined] to QQuick3DTexture*" until the binding is
`patternMap ? patternMap : null`; and a `Texture` is made with its data at birth — re-pointing
one at another `QQuick3DTextureData` renders white (`ogp-3d-renderer` §5).

**Pins.** `tests/unit/test_fill_patterns.py::TestThe3DFillPicture` (the picture is the canvas's:
256 × 256 RGBA, opaque, mean = the fill; names resolve; every texture is 256 px);
`tests/unit/test_scene3d_mesh.py` (the default solid is sides + cap, the cap carries
`(position + paint_origin) / 256`, a fill part must be `vc` or `water`, untinted and not ground
detail); `tests/unit/test_scene3d_builders.py::TestSoilRule`
(a garden bed's soil is the item's fill, a container's is not);
`tests/unit/test_scene3d_l4_surfaces.py` (a raised platform is a fill cap beside tinted sides, a
raised deck is not; a raised lawn's blades ride its top; a raised pool's water is a fill part);
`tests/unit/test_quick3d_adapter.py::TestTheItemsOwnFill` (the picture reaches the engine,
a recolour swaps it without an upload, one picture per key, released with its last user);
`tests/unit/test_quick3d_qml.py::test_a_fill_part_shows_the_plans_own_picture` (the binding and
the one-Texture-per-data rule) and `test_every_custom_shader_multiplies_with_the_tint` (water's
`uFill` branch); `tests/unit/test_quick3d_pure.py` (the fill branch of the one tint rule);
`tests/integration/test_scene3d_fill_phase.py` (the mesh's own UVs against the ground bake: NCC
0.995, the opposite sign 0.759 / 0.866); `tests/integration/test_plant_drop_undo.py` (a drag
into a bed is one Ctrl+Z, and one Ctrl+Y, and a bed dragged with its plant keeps the link); and
the render gate
`tests/integration/test_quick3d_render.py` — the raised GRASS square's top std > 5 against a
SOLID twin's < 0.5 at the same mean, a faded GRASS ghost below 235 (no white), the raised
POOL's water luma std > 4 (the caustics, which a constant UV cannot show), and the live
lifetime counts (1 picture, 2 after a recolour, 0 after the removal, geometry uploads 1).
`tests/unit/test_scene3d_mesh.py` also refuses a heighted record whose every part is
`ground_detail`: the gate may skip relief, never the solid itself.
PF-L3D-17 records the traps, FR-3D-BUILT-09 and FR-SUN-02 state the rule, and
`ogp-lush-cinematic`'s owner taste log holds the pass itself.
