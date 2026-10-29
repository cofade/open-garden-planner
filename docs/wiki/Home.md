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

[#392](https://github.com/cofade/open-garden-planner/issues/392) remains open for
packages A3–A4 and A6–A13.

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
[PR #640](https://github.com/cofade/open-garden-planner/pull/640); and precision,
UI and diagnostic bugfixes in
[v1.34.6](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.6) via
[PR #645](https://github.com/cofade/open-garden-planner/pull/645).

## Community

- [Discussions](https://github.com/cofade/open-garden-planner/discussions): public questions and ideas.
- [Issues](https://github.com/cofade/open-garden-planner/issues): bugs and confirmed tasks.
- [Code of Conduct](https://github.com/cofade/open-garden-planner/blob/master/CODE_OF_CONDUCT.md): behaviour and abuse reporting.
- [Security](https://github.com/cofade/open-garden-planner/blob/master/SECURITY.md): private vulnerability reports.
- [Accessibility](https://github.com/cofade/open-garden-planner/blob/master/ACCESSIBILITY.md): current support and known barriers.
- [Repository](https://github.com/cofade/open-garden-planner) and [licence](https://github.com/cofade/open-garden-planner/blob/master/LICENSE).
