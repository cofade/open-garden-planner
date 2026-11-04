# Open Garden Planner Wiki

Open Garden Planner is a free desktop application for garden planning with metric precision.
It combines a 2D canvas, plant records, garden tasks, exports, and a 3D view.

## Start here

- [Installation](Installation): download, verify, and install the application.
- [Roadmap](Roadmap): shipped features and planned work.
- [Architecture](Architecture): the main subsystems and detailed technical documentation.
- [Contributing](Contributing): development and contribution guidance.
- [Download statistics](https://cofade.github.io/open-garden-planner/): UTC installer-download
  bars grouped by day, week, month or year. Historical and gap estimates are labelled;
  the counters include bots and retries and do not represent unique users.

## Current status

The **9 October 2026** documentation audit used **v1.29.6** as its release baseline.
Phases 1–15 and Phase 13 Packages A–D are complete.
Package G's attribution, plant profiles, and provider companion data (G1–G3) shipped in v1.28.1.
Package G is complete: G4, plant favourites and collections, merged in [PR #421](https://github.com/cofade/open-garden-planner/pull/421).
Package F1/F2 shipped in [v1.30.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.0) via [PR #433](https://github.com/cofade/open-garden-planner/pull/433): species traits, food-forest layers, plant guilds, template editing and diagnostics. F3 sun diagnostics and the #428 heatmap lifecycle fix shipped in [v1.30.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.1) via [PR #436](https://github.com/cofade/open-garden-planner/pull/436) after owner acceptance; F4 plan lifetimes, combined date/sun controls and live-map updates shipped in [v1.30.17](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.17) via [PR #533](https://github.com/cofade/open-garden-planner/pull/533) after owner acceptance. F5 (#316) completed Package F in [v1.33.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.33.0) via [PR #610](https://github.com/cofade/open-garden-planner/pull/610) after owner executable acceptance.

Constraint-tool characterization (#406) shipped in [v1.30.2](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.2) via [PR #477](https://github.com/cofade/open-garden-planner/pull/477) after owner acceptance. Audit package A1 (#453: numeric input safety, verified release downloads, bounded image ingestion and owner-only Linux settings) shipped in [v1.30.3](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.3) via [PR #487](https://github.com/cofade/open-garden-planner/pull/487) after owner acceptance.
Audit package A5 (#457: constraint presentation, solver assertions, fixed-state
feasibility and German default object labels) shipped in
[v1.30.4](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.4) via
[PR #489](https://github.com/cofade/open-garden-planner/pull/489) after owner acceptance.
Audit package A2 (#454: pinned build tools, dependency review, frozen-package notices
and SBOM) shipped in
[v1.30.5](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.5) via
[PR #490](https://github.com/cofade/open-garden-planner/pull/490) after owner acceptance.

Translation completeness for every registered locale (#496) shipped in
[v1.30.6](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.6) via
[PR #497](https://github.com/cofade/open-garden-planner/pull/497) after owner acceptance.
New languages must cover all current UI keys, and new wrapped UI strings require every
target translation. See the [translation workflow](https://github.com/cofade/open-garden-planner/blob/master/docs/TRANSLATING.md).

Worker lifecycle safety, bounded caches, and test hygiene (#480, #483, #482, #474, #449, #448) shipped in
[v1.30.7](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.7) via
[PR #498](https://github.com/cofade/open-garden-planner/pull/498) after owner acceptance:
clean worker shutdown on application exit, bounded furniture rendering cache, FR ID deduplication, and Ctrl+F/Ctrl+H shortcut resolution.

[#392](https://github.com/cofade/open-garden-planner/issues/392) is complete: the
remaining audit packages A4/A6/A7/A9/A12/A13 shipped in v1.34.5 (PR #640).

Phase 17's L0 investigation is complete with a **GO** decision, and L1 is complete: one shared simulation date and time for the sun, shadow, heatmap and 3D tools shipped in v1.29.10 ([PR #429](https://github.com/cofade/open-garden-planner/pull/429)), and the new 3D view shipped in [v1.30.14](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.14) via [PR #484](https://github.com/cofade/open-garden-planner/pull/484) after owner acceptance.
The 3D view is now a Qt Quick 3D workspace beside the plan (Plan / 3D / Split), and the separate Qt 3D window is removed.

Use the [latest release](https://github.com/cofade/open-garden-planner/releases/latest)
for the current version. The [canonical roadmap](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md)
owns phase status. [Open issues](https://github.com/cofade/open-garden-planner/issues) own the work list.

The line-appearance follow-ups (#524, #525, #526, #471) shipped in [v1.30.16](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.16) via [PR #545](https://github.com/cofade/open-garden-planner/pull/545) after owner acceptance: exact preset/type undo, consistent round line corners, and complete styled-line canvas bounds; see the [implementation contract](https://github.com/cofade/open-garden-planner/blob/master/docs/08-crosscutting-concepts/README.md#830-line-appearance-snapshots-and-paint-containment-524-525-526-471).
The 2D canvas defect batch (#522, #530, #445, #446, #528) shipped in [v1.30.18](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.18) via [PR #556](https://github.com/cofade/open-garden-planner/pull/556) after owner acceptance: whole-word species sprite matching, species assignment sync, selection transparency through locked layers, undoable Properties-panel bed/container edits, and class-scoped perf guard analysis; see the [implementation contract](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#2d-canvas-defect-batch-522-530-445-446-528).

Plant Details follow-ups (#552, #557–#560) shipped in
[v1.30.20](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.20) via
[PR #566](https://github.com/cofade/open-garden-planner/pull/566) after owner
executable acceptance: undoable plant edits, centered species-width updates,
consistent position-lock badges, labelled illustrative 3D height estimates and a
location link beside Hours of Sun. See the [canonical delivery record](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#plant-details-follow-ups-552-557560--shipped-as-v13020-pr-566).

Phase 17 L2, Analyze in 3D (#386), shipped in [v1.31.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.31.0) via [PR #584](https://github.com/cofade/open-garden-planner/pull/584) after owner acceptance: the 2D shadows or the hours-of-sun map draped on the 3D ground with a ground probe, the sun's path with a compass, a day sweep, a richer plant info card (height source, growth, measured sun, sowing and harvest windows), +1/+3/+10-year jumps with a before/after wipe, and a cutaway that takes roofs off and fades what hides the selection. See the [canonical delivery record](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#l2-acceptance-highlights--analyze-in-3d-386-adr-063--shipped-v1310-pr-584).

Plant Forge (L3, #387) shipped in [v1.32.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.32.0)
via [PR #593](https://github.com/cofade/open-garden-planner/pull/593) after owner
executable acceptance. Procedural models cover all 123 sprite recipes, with
camera-driven LOD, background upgrades, support-aware climbers and independent
seasonal flowers, fruit and foliage. See the
[canonical delivery record](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#l3-acceptance-highlights--plant-forge-387-adr-064--shipped-v1320-pr-593).

Non-3D follow-up batch 2 (#562/#573, #574, #581, #587, #590, #592, #594) shipped in
[v1.32.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.32.1) via
[PR #596](https://github.com/cofade/open-garden-planner/pull/596) after owner
acceptance: real offscreen fonts on Windows, the settings guard for tooling probes,
command-scoped canvas refresh, cached dense-overlay panning, one height resolver, a
generated version artifact (About now reports 1.32.1), species-sized gallery drops,
and a single 120 px Properties control column. See the
[canonical delivery record](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#non-3d-follow-up-hardening-batch-2--shipped-2026-10-26-as-v1321-pr-596).

## Offline examples and reusable templates

F5 shipped three localized offline learning layouts and portable template copies
in [v1.33.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.33.0) after owner executable acceptance. See the
[delivery record](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#f5-examples-and-templates-v1330-pr-610).
Templates remove named site/history fields and paths; review free-form names and
text before sharing. Example dates are illustrative calendar dates.

## Built world complete (Phase 17 L4)

L4 (#388) shipped in [v1.34.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.0)
via [PR #613](https://github.com/cofade/open-garden-planner/pull/613) after the
owner's third manual pass. All 24 furniture, play, utility and structure object
kinds now have procedural 3D builders and a default height, so every one casts a
shadow in 2D and 3D; houses, garages and tool sheds get an optional roof style,
pitch, overhang, windows and a door; paths show their surface on the 3D ground at
their real width; lawns grow individual blades from the Medium preset up. See the
[canonical delivery record](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#l4-acceptance-highlights--built-world-complete-388-adr-065--shipped-v1340-pr-613).

Patch releases since then: L4 follow-up hardening in
[v1.34.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.1) via
[PR #630](https://github.com/cofade/open-garden-planner/pull/630); internal test-lifecycle and
workspace work in [v1.34.2](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.2)
via [PR #632](https://github.com/cofade/open-garden-planner/pull/632); and the 2D sun study's
geometry, plant stacking and object heights in
[v1.34.3](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.3) via
[PR #627](https://github.com/cofade/open-garden-planner/pull/627) after owner acceptance;
agent move atomicity and holder sun in
[v1.34.4](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.4) via
[PR #639](https://github.com/cofade/open-garden-planner/pull/639); and audit packages
A4/A6/A7/A9/A12/A13 (completing epic #392) in
[v1.34.5](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.5) via
[PR #640](https://github.com/cofade/open-garden-planner/pull/640); precision,
UI and diagnostic bugfixes in
[v1.34.6](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.6) via
[PR #645](https://github.com/cofade/open-garden-planner/pull/645); 3D visual and
engine hardening in
[v1.34.7](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.7) via
[PR #647](https://github.com/cofade/open-garden-planner/pull/647); and canvas
touch gestures, region-work pricing and the render tier's workspace rows in
[v1.34.8](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.8) via
[PR #650](https://github.com/cofade/open-garden-planner/pull/650).

Bed membership reconciliation and atomic constrained rotations (#443, #485) shipped in
[v1.34.9](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.9) via [PR #649](https://github.com/cofade/open-garden-planner/pull/649) after full owner manual acceptance.
Parallel/Perpendicular creation preserves locked objects and marks the selected edge.

The CAD-precision integrity package (#655, #656, #657, #658, #661, #662, #668, #669, #670)
shipped in [v1.34.10](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.10) via
[PR #672](https://github.com/cofade/open-garden-planner/pull/672) after full owner manual
acceptance: FIXED locks round-trip, grouped rotated shapes keep their frame, bed identity
survives corner edits, the fillet arc is baked into its host, and constraint incidence has one
resolver. Follow-ups: a converted raised bed becomes a garden bed with its soil pattern, and
offsetting an open fence/path creates a parallel line.

The first slice of the 3D performance and stability work (#452) shipped in
[v1.34.11](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.11) via
[PR #676](https://github.com/cofade/open-garden-planner/pull/676): whole-plan preparation is
sliced into 4 ms turns (heartbeat p95 1.7–3.6 ms on the issue's plans, from 4.0–12.6 s in one
block), heavy mesh builders run on one worker lane, and `mapbox-earcut` replaces the O(n²) ear
clipper for large regions. The in-place Model experiment (#531) was withdrawn after both
render tiers drew a replaced geometry as nothing, and the sparse seasonal-index experiment
went with it on the same files; those issues stay open.

Site-plan-sized background images (#659, #660) shipped in
[v1.34.12](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.12) via
[PR #683](https://github.com/cofade/open-garden-planner/pull/683): a background whose decoded
size exceeds Qt's 256 MB default (a 9000 × 8000 PNG is a 294 kB file and 275 MiB decoded) now
imports and reopens instead of degrading to a placeholder, an image above 120 megapixels is
refused with a translated message before the image is decoded, and the embedded PNG is encoded
once and re-encoded only when the image itself changes, instead of about 1.2 s on every plan
read and autosave.

Symbol and shadow correctness, Slice B (#599, #440) shipped in
[v1.34.13](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.13) via
[PR #686](https://github.com/cofade/open-garden-planner/pull/686): smart symbols now instantiate
typed objects (`ObjectType.RAISED_BED`, `ObjectType.GREENHOUSE`, `ObjectType.COMPOST`,
`ObjectType.FENCE`) via canonical items with stable deterministic UUIDs (`uuid5`), preserving child
plant parenting across parameter edits, with atomic single-command undo and versioned definition fallback;
and the 2D overlay, heatmap, plant exposure, and 3D drape consume unified geometry-aware caster
representations with structural roof/wall triangle projection for ridged buildings (`gable`, `hip`, `shed`),
angle-dependent structural fence porosity (`WOODEN_FENCE`, `METAL_FENCE`, `CHAIN_LINK`), owner-grouped
casting, and independent multiplicative overlap ($T_1 \times T_2$).

## Director's cut (Phase 17 L6)

Photo mode (exposure, focus, colour grades, a vignette; saved up to 4K), camera tours (a drone orbit, your own keyframes, a time-lapse of a day or a year; saved as an MP4 video or a PNG sequence) and the read-only `render_3d_view` agent tool. The plan of the project's own renders ships as the **Family garden** example. Phase 17 L6 shipped in [v1.37.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.37.0) via [PR #729](https://github.com/cofade/open-garden-planner/pull/729) after owner acceptance. The blur needs a focus: moving the slider focuses what the camera looks at, and a click on the view moves it. On the Ultra quality level the reflections are off while the blur is drawn. See [#390](https://github.com/cofade/open-garden-planner/issues/390).

## Living garden (Phase 17 L5)

Phase 17 L5, the living garden (#389), shipped in
[v1.35.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.35.0) via
[PR #699](https://github.com/cofade/open-garden-planner/pull/699) after owner acceptance.
- **Playback:** the day and the year play through the shared simulation clock, and the 2D shadows and the 3D light turn together.
- **Weather:** clear, overcast, rain and snow are a look in 3D, set with the **Weather** button in the 3D strip. They never move the sun or change the sun study, and they pause while an analysis is draped on the ground.
- **Life:** falling rain, snow and leaves, butterflies and fireflies are shader particles on the wind's clock. Reduced motion stills them.
- **Today's Weather:** while the plan date is today, it shows the forecast for the plan's location; on any other date it shows clear and says why.
- **Lights:** a Garden Light, and String Lights drawn as a LINE like a fence, with a post at every click. They glow and light the garden after dusk, and a string casts no 2D shadow.

See the [canonical delivery record](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#l5-acceptance-highlights--living-garden-389-adr-070--shipped-v1350-pr-699).

## Sky 6.12 (Phase 17 L7)

Phase 17 L7 (#391) shipped in
[v1.36.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.36.0) via
[PR #721](https://github.com/cofade/open-garden-planner/pull/721) after owner acceptance.
- **Qt 6.12:** the app moved to the Qt 6.12 LTS. Windows' **Animation effects** setting now also stops the wind in 3D.
- **Atmosphere sky (optional):** Preferences, 3D View, Sky, **Atmosphere with clouds** draws a physically based sky with volumetric clouds. Clouds follow the weather, so there are none under Clear, and the view opens looking down at the garden: tilt the camera towards the horizon to see the sky. The painted sky stays the default and lights the garden under both, so the garden is equally bright with either.
- **Partly cloudy:** a new weather with the sun out. Its scattered clouds show with the atmosphere sky; on the painted sky it is a sunny day with a slightly greyer blue.
- **Known limits:** the atmosphere costs more of the graphics card every frame, measured only on an RTX 4070 and a software renderer; a pale band can show at the horizon under a closed cloud deck at a low sun ([#719](https://github.com/cofade/open-garden-planner/issues/719)); and playing a day pauses briefly while its sky rebuilds ([#722](https://github.com/cofade/open-garden-planner/issues/722)).

See the [canonical delivery record](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#l7-acceptance-highlights--sky-612-391-adr-048-addendum-l7--shipped-v1360-pr-721).

## Drawing tools and Russian localization (v1.36.1-v1.36.2)

Russian localization (#492, FR-I18N-09) shipped in
[v1.36.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.36.1) via
[PR #495](https://github.com/cofade/open-garden-planner/pull/495): a complete Russian
catalog, collision-free menu accelerators, installer support and translated example
metadata.

The 2D drawing-tools package (#674, #665, #690) shipped in
[v1.36.2](https://github.com/cofade/open-garden-planner/releases/tag/v1.36.2) via
[PR #713](https://github.com/cofade/open-garden-planner/pull/713) after owner acceptance:
**Group / Ungroup** in every groupable object's context menu, per-object **fill pattern
angle / scale / offset** with roof-frame composition, and a linked **roof ridge** created
when a shape is converted to HOUSE. See the
[canonical delivery record](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md#2d-drawing-tools-package-674-665-690--shipped-in-v1362-pr-713).

## Community

- [Discussions](https://github.com/cofade/open-garden-planner/discussions): public questions and ideas.
- [Issues](https://github.com/cofade/open-garden-planner/issues): bugs and confirmed tasks.
- [Code of Conduct](https://github.com/cofade/open-garden-planner/blob/master/CODE_OF_CONDUCT.md): behaviour and abuse reporting.
- [Security](https://github.com/cofade/open-garden-planner/blob/master/SECURITY.md): private vulnerability reports.
- [Accessibility](https://github.com/cofade/open-garden-planner/blob/master/ACCESSIBILITY.md): current support and known barriers.
- [Repository](https://github.com/cofade/open-garden-planner) and [licence](https://github.com/cofade/open-garden-planner/blob/master/LICENSE).
