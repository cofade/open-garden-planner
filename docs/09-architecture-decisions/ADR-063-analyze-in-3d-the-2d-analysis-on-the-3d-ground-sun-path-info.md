---
id: ADR-063
title: "Analyze in 3D — the 2D analysis on the 3D ground, sun path, info card v1, growth jump, Cutaway"
status: "Accepted; owner acceptance confirmed on 24 October 2026 (two manual passes), shipped in [v1.31.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.31.0) via [PR #584](https://github.com/cofade/open-garden-planner/pull/584)."
refs: ["Phase 17 L2", "#386"]
legacy_anchor: adr-063-analyze-in-3d--the-2d-analysis-on-the-3d-ground-sun-path-info-card-v1-growth-jump-cutaway-phase-17-l2-386
---

# ADR-063: Analyze in 3D — the 2D analysis on the 3D ground, sun path, info card v1, growth jump, Cutaway

**Status:** Accepted; owner acceptance confirmed on 24 October 2026 (two manual passes), shipped in [v1.31.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.31.0) via [PR #584](https://github.com/cofade/open-garden-planner/pull/584).

## Context

ADR-048 (the scope note of criterion 8) settled that the engine's shadow maps are
illustrative and the analysis stays with the 2D model, "draped onto the 3D ground".
L2 makes the 3D view a place to READ the sun: the two 2D maps on its ground, a ground
probe, the sun's path, a day sweep, a richer info card, jumps of the plan date with a
before/after, and a cutaway that sees the selection. Every piece meets an engine rule
that L1 measured: a destroyed Model leaves 15–20 kB behind for good (#531), every cache
release leaks half the same-size textures (#532), a re-pointed `Texture` draws white,
QML carries no text, a readback from the live view is a frame that is never presented
(ADR-060 decision 17), and the 3D strip of a 1366 px window has no pixel to spare.

## Decision

1. **The 2D analysis is the source; nothing computes a shadow or a sun hour a second
   time.** The shadow drape lays `SunShadowController.drape_polygons()` — the polygons
   the canvas overlay paints (the union, the whole canvas at night) — announced by a
   new `shadows_changed` signal, cut at the plan rectangle as the canvas cuts them
   (`shadow_geometry.clip_to_rect`) and triangulated (`polygon.triangulate_region`;
   a region the triangulator refuses is laid as a 5 cm raster, never lost). The
   hours-of-sun drape lays `SunHeatmapController.result()` — a new plain-data
   `SunHoursMap` — announced by a new `computed` signal, in the canvas's own ramp
   (`build_sun_lut`), one vertex per cell centre plus a clamped edge (the canvas's
   smooth scaling), row 0 = SOUTH as everywhere. Choosing it switches the SHARED
   Hours of Sun on (`LiveSunMap.set_enabled`: the toolbar follows); leaving it leaves
   the 2D map alone.
2. **Overlays are meshes in Models that live as long as the scene** — one for the drape
   (blended, no depth write), one for the lines (sun path, compass, probe pin) —
   re-loaded in place (`ReloadableGeometry`, the selection ring's pattern) through ONE
   host call, `Quick3DHost.set_overlay(layer, buffers)`. No analysis change creates or
   destroys a Model or a texture. A texture drape was rejected for exactly that: the
   day sweep and the sun ball change the overlays several times a second. The
   overlays are not items: the sink's `clear()` leaves them (like the sky); the
   controller says what they show. `EngineSink` keeps its eleven methods.
3. **Blending keeps the frame's alpha.** A blended custom material uses
   `sourceAlphaBlend: Zero` / `destinationAlphaBlend: One`. Measured on the first
   build: with the colour factors applied to alpha too, the frame's alpha became
   1 − a(1 − a) and the view's texture let the window's white through — black at
   a = 0.5 read 64 grey levels too BRIGHT, the shadow drape brightened the meadow
   (rgb(79, 107, 75) over rgb(25, 73, 11)). Pinned by the self-test's judge and the
   render tier (PF-L3D-06).
4. **The sun path is drawn from `core.solar` and nothing chosen.** Four arcs — the plan
   date, 21 June, 21 December, 20 March of the plan's year — each one LOCAL day of the
   clock's zone (`SimInstant`), cut where the sun crosses the horizon, with solar noon
   found to the second and inserted; ONE mapping to the dome (`sun_path.dome_point`,
   radius 0.55 × the plan's diagonal). The gate: the noon point IS `solar_position` at
   its instant and the day's highest sun (brute force at 20 s). The compass rose lies
   on the ground at the dome's rim; its four letters are TRANSLATED (context
   `Compass`) and handed to the core as glyph outlines from the application font
   (`ui/view3d/compass_glyphs.py`) — text drawn as geometry, not as a texture.
5. **The day sweep moves the ONE clock and fills the map from its own samples.** The
   clock's time of day runs from sunrise to sunset of the plan date (10 min every
   100 ms) and is given back at the end. The heatmap now keeps every daylight sample's
   shade mask (`np.packbits`, up to 64 MB), so the drape shows the minutes collected
   up to the current time — samples taken by their LOCAL time of day, because the map
   samples a UTC civil day (Sydney's runs 10:00 → 10:00): at sunset the sweep ends on
   the whole map, everywhere. No second heatmap run.
6. **The ground probe reads the shown map.** A click that picks nothing (the existing
   pick, `OrbitInput.ground_clicked`) while the hours of sun lie on the ground meets
   the ground where the view ray through it does (`pick_oracle.perspective_ray`); the
   card's place below the view says the minutes of that cell
   (`SunHoursMap.minutes_at`) and their band (`sun_mismatch_service.band_of`, the
   glossary's bands), and a pin marks the spot. The reading follows a new map.
7. **The info card v1's facts each come from their one home**: the height's source at
   the plan date (`object_height.height_source_at`, new `SOURCE_GROWN`), the growth
   share (`growth_model.growth_share`, only where the plant grows on the timeline),
   the sun the Hours-of-Sun run published for the plant, and the sowing / harvest
   windows of the plan's year (`task_generator.calendar_windows` — extracted from
   `generate_calendar_tasks`, which now calls it: one frost-relative formula). Five
   lines of facts (was three); a species' week offset beyond 520 weeks is ignored
   (plan files are untrusted).
8. **A growth jump is a date change of the ONE clock, and its before/after takes two
   frames — the user's action, like the click.** +1 / +3 / +10 years (29 February →
   1 March, the frost dates' rule of ADR-049; the clock's range bounds it); "Back"
   returns to the date before the first jump. The before-picture is taken in the jump,
   the after-picture in the pipeline's first pass that read the new date (the
   `applied` slot, where readbacks already belong); both through
   `growth_jump._grab`, the second sanctioned frame-taker after the click (a source
   scan pins both, and that `_grab` is reached from `jump` and `on_applied` only).
   The wipe (`ui/view3d/wipe.py`) replaces the view in its pane — nothing is drawn
   over the native window — and gives it back on "Back to 3D View" or Escape.
9. **Cutaway = roofs off + X-ray, with no Model touched.** Roofs: one scene property
   (`roofsHidden`) every roof part binds, so a roof built while it is on is born
   hidden. X-ray: `core/scene3d/xray.py` casts segments from the eye to nine points of
   each selected item's box (at most 16 items) through the meshes the ENGINE holds,
   box-culled, with the pick oracle's own triangle test (`pick_oracle.cast_segment`,
   no second ray code); the items met fade (`set_faded_items`: a `fade` property per
   part Model, opacity 0.22, not pickable — a click meets what is behind). Custom
   materials blend only while they fade. Recomputed 150 ms after the camera, the
   selection or the records last changed — never per frame.
10. **One "Analyze" menu in the strip, and the strip's control row wraps.** In German
    a Split pane of a 1366 px window had 7 px beside "Reset 3D View" and "Walk"; the
    row is now a wrapping layout (`_WrapRow`) that asks for its widest control, not
    the sum. The sun path's legend is a line of the notices.

## Alternatives rejected

- **Painting the drapes into the ground tiles.** Every sun step would re-bake tiles:
  new Models and textures per step, the two leaks (#531, #532) at animation rate, and
  the analysis lit by the engine's own (illustrative) shadows.
- **A texture per drape update.** Same leaks; an attached `QQuick3DTextureData`
  cannot be updated in place.
- **Engine shadows as the 3D answer.** ADR-048 criterion 8's scope note: they differ
  from the 2D model by design (gable roofs, porous fences, crowns on trunks).
- **A second heatmap run for the sweep, or sampling the sweep by instant.** The first
  costs seconds per date; the second, at the end of the local day, misses the morning
  of every garden whose local day is far from the UTC day.
- **A split screen of two live engine views for before/after.** Two hosts, two
  graphics devices, and every Model twice; two readbacks of one host cost a few ms.

## Consequences

No new dependency, persisted key or `FILE_VERSION` change; `.ogp` files are untouched.
`EngineSink` is unchanged; `Quick3DHost` gains `set_overlay`, `set_roofs_hidden`,
`set_faded_items`; `Garden.qml` two overlay Models, a `fade` per part, `roofsHidden`
and the alpha rule; `overlay.vert` / `overlay.frag` ship beside it and are compiled by
`--selftest` (it now draws a drape patch and a lines patch and judges their colours).
The shade masks add one bit per cell and sample to a heatmap result.

**Pinned by:** `tests/unit/test_scene3d_drape.py`, `test_scene3d_sun_path.py` (the noon
gate), `test_scene3d_xray.py`, `test_plant_card_facts.py`, `test_quick3d_selftest.py`;
`tests/ui/test_view3d_analysis_host.py` (one Model per overlay, roofs, fades, in the
real QML scene); `tests/integration/test_view3d_analysis.py` (§8.10 — the workflow with
the real 2D analysis beside the workspace); `tests/integration/test_view3d_analysis_render.py`
(the render tier: the drape darkens, row 0 south, north up, fades and the cutaway, on
the GPU, WARP and OpenGL); the frame-taker scan in `test_view3d_workspace_widget.py`.

### Addendum: review round 1 (2026-10-24) — what the 3D and the senior review changed

The `ogp-3d-reviewer` rejected the first build (one P0, four P1s) with every truth gate
green (drape IoU against the canvas 0.993–0.999, row 0 south, noon = `solar_position`,
the L1 frames bit-identical); the `senior-reviewer` found three P1s at the boundary to
the 2D Hours of Sun. Decisions 2, 3, 6 and 9 change as follows.

- **The 2D shadows MULTIPLY the frame (decision 2/3).** A third overlay Model, the
  `"shade"` layer (`sourceBlend: DstColor`, `destinationBlend: Zero`, the alpha rule
  kept), carries the shadow drape; its vertex colour is a linear multiplier,
  `drape.SHADE_MULTIPLIER` (0.60, 0.62, 0.95: every channel below 1, ordered like the
  canvas's shadow colour). Over-blended, the canvas colour was unlit and went through
  the mood's exposure: at night (exposure 2.4) the "shadow" turned the garden LIGHTER
  (+17.6 / +24.1 luma, up to +43.7), and at golden hour it was a −4 luma wash.
  Measured on D3D11, the lit lawn under the shade now reads 0.83 of its luma at noon,
  0.76 at golden hour, 0.74 at sunset, 0.78 on a December noon and 0.76 at night, the
  engine's own shadow under it 0.71–0.84; the render tier asserts that no pixel under
  it brightens in three moods (PF-L3D-07). The hours-of-sun map stays blended over.
- **Overlay colours divide by the exposure (decision 2).** `overlay.frag` writes
  `vColor.rgb / uExposure` (1 for the shade, 1 in the top-down truth view), and the
  arcs are BUILT in pre-compensated colours (`sun_path.ARC_ENGINE_RGBA`) while the
  legend keeps `ARC_RGBA`: the filmic curve bent the legend colours by up to +14° /
  −11° by day and washed them to near white at night. Re-measured: within 2.7° of the
  legend's hue in five moods. The plan date's arc is drawn last and 1.5 × thicker (it
  lay hidden under its twin on a key day); the compass letters are 0.12 of the dome's
  radius (0.065 left E and W 6 px high).
- **X-ray and Cutaway draw screen doors, not blends or hidden Models (decision 9).** A
  blended or hidden part drops out of the shadow map: Cutaway took the house's shadow
  off the lawn and X-ray a faded tree's 30 m shadow. A faded built part now switches
  to a screen-door material (`screen.frag`: a 4 × 4 ordered dither keeps `uOpacity` of
  its pixels and discards the rest; foliage, grass and water dither in their own
  shaders), and a cut roof is the same screen door with nothing left. Both stay opaque
  casters — measured top-down: ground outside the footprints unchanged (max 0.0 for
  the faded trees, about 10 edge pixels for the cut roofs). The principled look stays
  the material while nothing fades, so the L1 frames do not change. The walls drop
  back-face culling while Cutaway is on (the roofless house read as one wall and a free
  gable); a cut roof is not pickable (a click goes inside). The stipple, its 25 % share
  and whether a selected bed's own plants should fade are owner questions.
- **X-ray sees flat items, and a cut roof is no occluder.** An item the engine holds no
  mesh for (a bed without a height, a lawn, a path) is looked at on its posed
  footprint, 5 cm above its base (`xray.flat_targets`); the board's Cutaway row selected
  such a bed and faded nothing in all 14 rows. Roof parts are left out of the X-ray
  scene: X-ray runs only in Cutaway.
- **One owner of the hours-of-sun state (decisions 1 and 6).** `LiveSunMap` gained
  `enabled_changed`; the analysis takes the live map itself as its `SunHoursSource`.
  When the shared Hours of Sun goes off (the toolbar, a document replace) the 3D drape
  falls back to "Nothing on the Ground" and the menu follows; choosing the hours-of-sun
  drape always switches it on. Before, a document replace left the 3D menu on the
  drape with the 2D side off and the probe saying "not computed yet" for good.
- **The probe measures only a current map (decision 6).** While the shown map is a
  dated preview of a changed plan (ADR-056) the probe reads `"updating"` and says so;
  it re-reads on `exposure_changed`. It meets the drape's plane (1.5 cm), not z = 0 — at
  a walk-mode grazing angle that is 19 cm, two cells. Leaving the hours of sun takes
  the pin along.
- **Every exit of the sweep gives the time back; a jump owes only its own comparison
  (decisions 5 and 8).** A time the user sets during a sweep ends it and stays; a date
  change ends it and gives the time back a turn later (the clock refuses a write from
  its own notification, ADR-053); the engine going (`shutdown`) gives it back. While a
  sweep runs, the hours-of-sun drape is built with at most 65,536 vertices (62 ms per
  step at a 50 × 50 m garden on the GUI thread at full size). A jump stops a sweep
  before its before-picture; a jump whose date the user moves away from owes no
  comparison. The controller dispatches only `HOST_CALLS` (no frame-taking call can
  slip past the frame-taker scan by name).

Also: the shadow drape's fallback for rings that do not group rasters the whole set
even-odd (a sunny island stayed shaded); the card takes week offsets as the task
generator does (it truncated them).

**Round 2 (both reviews).** The depth pass that fills ambient occlusion's depth texture
does not run the screen door's discard: from the Medium preset (the AUTO start) a cut
roof left a ghost of itself and a faded occluder its silhouette as AO. Every
screen-door material collapses in that pass (`#if QSSG_ENABLE_DEPTH_PASS` in
`screen.vert`, `foliage_door.vert`, `grass_door.vert`); the shadow pass keeps the part
(measured: AO adds at most 1.5 luma for a cut roof or a faded box, up to 26 without;
`NeverDepthDraw` instead lost the shadow and kept the ghost). Foliage, grass and water
switch to screen-door copies of their shaders as the built parts do, so the look
shaders are master's to the byte and carry no discard while nothing fades. The probe
says "could not be computed" after a failed run (`LiveSunMap.unavailable`), and the
legend names a key day whose arc the plan date's arc covers (noons within 0.5°). Pinned by the render tier's new mood, shadow and
screen-door tests, `test_quick3d_qml.py` (blends, screen doors), the self-test (four
faded cubes — built part, crown, grass, pond: every screen-door shader compiled from
the bundle), and `test_view3d_analysis.py`
with the real `LiveSunMap`.

**Owner manual pass (2026-10-24).** With Hours of Sun switched on in the toolbar the
canvas showed its map and the 3D ground nothing: the drape followed the shared switch
going OFF (round 1) but never going ON, so it lay on the ground only when chosen in
the Analyze menu. The real app on the real engine was reproduced first (the owner's
ultra preset, a 50 × 30 m plan at 45° N, Animate running): chosen in the menu the
drape loads and draws on screen in every order tried — the data path and the engine
were sound. Decision 1 now reads: the hours-of-sun drape comes AND goes with the
shared Hours of Sun — switched on (the toolbar), it replaces what lay on the 3D ground,
also the 2D shadows, and switched off, what lay there before comes back (the 3D
review's point: on and off are a pair); a 3D view opened while it is on shows it at
once — also an engine rebuilt while it is on (a quality change), which therefore starts
on the hours of sun rather than on the user's earlier 3D choice, as a rebuild already
started from "Nothing on the Ground" before. Pinned by
`test_view3d_analysis.py::test_the_toolbar_switching_hours_of_sun_on_lays_the_3d_drape`
and `::test_3d_opened_with_hours_of_sun_already_on_shows_it_on_the_ground` (both fail
without the change). The same pass found the 2D overlays hidden under lawns: ADR-043's
addendum "ground surfaces lie under the sun study".

---
