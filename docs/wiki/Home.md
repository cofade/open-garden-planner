# Open Garden Planner Wiki

Open Garden Planner is a free desktop application for garden planning with metric precision.
It combines a 2D canvas, plant records, garden tasks, exports, and a 3D view.

## Start here

- [Installation](Installation): download, verify, and install the application.
- [Roadmap](Roadmap): shipped features and planned work.
- [Architecture](Architecture): the main subsystems and detailed technical documentation.
- [Contributing](Contributing): development and contribution guidance.

## Current status

The **9 October 2026** documentation audit used **v1.29.6** as its release baseline.
Phases 1–15 and Phase 13 Packages A–D are complete.
Package G's attribution, plant profiles, and provider companion data (G1–G3) shipped in v1.28.1.
Package G is complete: G4, plant favourites and collections, merged in [PR #421](https://github.com/cofade/open-garden-planner/pull/421).
Package F1/F2 shipped in [v1.30.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.0) via [PR #433](https://github.com/cofade/open-garden-planner/pull/433): species traits, food-forest layers, plant guilds, template editing and diagnostics. F3 sun diagnostics and the #428 heatmap lifecycle fix shipped in [v1.30.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.1) via [PR #436](https://github.com/cofade/open-garden-planner/pull/436) after owner acceptance; F4 plan lifetimes, combined date/sun controls and live-map updates shipped in [v1.30.17](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.17) via [PR #533](https://github.com/cofade/open-garden-planner/pull/533) after owner acceptance. F5 (#316) remains planned.

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

## Community

- [Discussions](https://github.com/cofade/open-garden-planner/discussions): public questions and ideas.
- [Issues](https://github.com/cofade/open-garden-planner/issues): bugs and confirmed tasks.
- [Code of Conduct](https://github.com/cofade/open-garden-planner/blob/master/CODE_OF_CONDUCT.md): behaviour and abuse reporting.
- [Security](https://github.com/cofade/open-garden-planner/blob/master/SECURITY.md): private vulnerability reports.
- [Accessibility](https://github.com/cofade/open-garden-planner/blob/master/ACCESSIBILITY.md): current support and known barriers.
- [Repository](https://github.com/cofade/open-garden-planner) and [licence](https://github.com/cofade/open-garden-planner/blob/master/LICENSE).
