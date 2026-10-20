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
Package F1/F2 shipped in [v1.30.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.0) via [PR #433](https://github.com/cofade/open-garden-planner/pull/433): species traits, food-forest layers, plant guilds, template editing and diagnostics. F3 sun diagnostics and the #428 heatmap lifecycle fix shipped in [v1.30.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.1) via [PR #436](https://github.com/cofade/open-garden-planner/pull/436) after owner acceptance; F4/F5 remain planned.

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

The line-appearance follow-ups (#524, #525, #526, #471) are being delivered together:
exact preset/type undo, consistent round line corners, and complete styled-line
canvas bounds. Owner acceptance and merge remain pending; see the
[implementation contract](https://github.com/cofade/open-garden-planner/blob/master/docs/08-crosscutting-concepts/README.md#830-line-appearance-snapshots-and-paint-containment-524-525-526-471).

## Community

- [Discussions](https://github.com/cofade/open-garden-planner/discussions): public questions and ideas.
- [Issues](https://github.com/cofade/open-garden-planner/issues): bugs and confirmed tasks.
- [Code of Conduct](https://github.com/cofade/open-garden-planner/blob/master/CODE_OF_CONDUCT.md): behaviour and abuse reporting.
- [Security](https://github.com/cofade/open-garden-planner/blob/master/SECURITY.md): private vulnerability reports.
- [Accessibility](https://github.com/cofade/open-garden-planner/blob/master/ACCESSIBILITY.md): current support and known barriers.
- [Repository](https://github.com/cofade/open-garden-planner) and [licence](https://github.com/cofade/open-garden-planner/blob/master/LICENSE).
