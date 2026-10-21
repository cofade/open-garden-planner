# Development Roadmap

This page summarises the [canonical roadmap](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md).
That document owns requirements and completion records. GitHub issues own the current work list.
The overview, infrastructure table, and Phase 17 section below come directly from that document.

## Overview

<!-- ogp:include roadmap-overview -->

## Dev Infrastructure

These improvements apply across the project.

<!-- ogp:include roadmap-infrastructure -->

The repository audit remains open under [#392](https://github.com/cofade/open-garden-planner/issues/392).
The [living debt register](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/README.md)
records individual outcomes. The dated audit snapshot preserves the original findings.
The [current reconciliation and package map](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/audits/2026-10/audit-2026-10-reconciliation.md)
links the remaining work to thematic bundle issues.
All 15 original standalone P0/P1 remediation issues are complete after #406 shipped in [v1.30.2](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.2) via [PR #477](https://github.com/cofade/open-garden-planner/pull/477).
The rotation/constraint interaction discovered during manual testing is a separate follow-up, [#485](https://github.com/cofade/open-garden-planner/issues/485).
Audit package A1 (#453: numeric input safety, verified release downloads, bounded image ingestion and owner-only Linux settings) shipped in [v1.30.3](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.3) via [PR #487](https://github.com/cofade/open-garden-planner/pull/487) after owner acceptance.
Audit package A5 (#457: constraint descriptors, numerical solver assertions,
fixed-state feasibility and German default object labels) shipped in
[v1.30.4](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.4) via
[PR #489](https://github.com/cofade/open-garden-planner/pull/489) after owner acceptance.
Audit package A2 (#454: pinned build tools, dependency review, frozen-package notices
and SBOM) shipped in [v1.30.5](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.5) via [PR #490](https://github.com/cofade/open-garden-planner/pull/490) after owner acceptance.
Translation completeness for every registered locale (#496) shipped in [v1.30.6](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.6) via [PR #497](https://github.com/cofade/open-garden-planner/pull/497) after owner acceptance.
Worker lifecycle safety, bounded caches, and test hygiene (#480, #483, #482, #474, #449, #448) shipped in [v1.30.7](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.7) via [PR #498](https://github.com/cofade/open-garden-planner/pull/498) after owner acceptance.

## Phases 1–12: complete

These phases established drawing, calibration, plants, layers, constraints, exports,
climate calendars, seed inventory, companion planting, crop rotation, and garden records.
See the canonical roadmap for each user story and its acceptance criteria.

## Phase 13: Packages A–D complete

### Package A: CAD precision ✅

Relative and polar coordinates, midpoint and intersection snapping, and dynamic input shipped in v1.11.0.

### Package B: curves and precision tools ✅

Bezier and arc tools, fillet and chamfer, and additional snapping modes shipped from v1.12.0.
Follow-ups completed constraint enforcement, curve editing, and mirroring.
Paper Space was dropped during manual review. PDF reports provide the supported page-output workflow.

### Package C: garden smart features ✅

Tasks, harvest records, containers, trellises, and smart-symbol support completed in v1.20.0.
The smart-symbol engine, persistence, properties editing, and DXF export shipped.
The Smart Symbols sidebar remains hidden pending demand.

### Package D: Agent Integration ✅

Package D completed in **v1.29.1**, [PR #382](https://github.com/cofade/open-garden-planner/pull/382).
The embedded MCP server supports live-plan reads, images, exports, optional token-gated editing,
and companion, succession, task, and soil tools.
It runs on loopback. Reads and exports do not require a token. Writes require editing to be enabled and a valid token.
Geometry writes refuse constrained objects. Task-status writes remain unavailable because they are not undoable.

## Package F: F1–F4 complete; F5 planned

F1/F2 passed owner frozen-app acceptance and shipped via [PR #433](https://github.com/cofade/open-garden-planner/pull/433).

| Story | Work | Status | Issue |
|---|---|---|---|
| F1 | Species traits, function filters and food-forest layers. | ✅ v1.30.0 | [#312](https://github.com/cofade/open-garden-planner/issues/312) |
| F2 | Plant guilds, template editing, saved membership and diagnostics. | ✅ v1.30.0 | [#313](https://github.com/cofade/open-garden-planner/issues/313) |
| F3 | Sun requirements compared with computed hours of sun. | ✅ v1.30.1 (with #428, PR #436) | [#314](https://github.com/cofade/open-garden-planner/issues/314) |
| F4 | Plan lifetimes and combined sun controls. | Shipped v1.30.17, PR #533 | [#315](https://github.com/cofade/open-garden-planner/issues/315) |
| F5 | Example plans and templates. Last in the package. | Planned | [#316](https://github.com/cofade/open-garden-planner/issues/316) |

## Package G: complete

| Story | Status | Issue |
|---|---|---|
| G1: data licence and attribution | ✅ v1.28.1 | [#311](https://github.com/cofade/open-garden-planner/issues/311) |
| G2: plant profile header | ✅ v1.28.1 | [#317](https://github.com/cofade/open-garden-planner/issues/317) |
| G3: provider companion data and cache | ✅ v1.28.1 | [#318](https://github.com/cofade/open-garden-planner/issues/318) |
| G4: plant favourites and named collections | ✅ [PR #421](https://github.com/cofade/open-garden-planner/pull/421) | [#320](https://github.com/cofade/open-garden-planner/issues/320) |

## Phase 14: 3D and sun/shade complete

All nine stories shipped across **v1.24.5–v1.24.12**.
Phase 14 delivered solar calculations, analytic 2D shadows, hours-of-sun heatmaps,
a Qt 3D view, walkthrough, and plant growth over time.
Ground remains flat. The Phase 14 renderer had lighting but no engine shadow maps; Phase 17 L1 replaced it in v1.30.14.
These releases retained patch versioning. There was no v2.0 release.

## Phase 15: visual refresh complete

- **Package 1:** themed icons, typography, and application chrome.
- **Package 2:** procedural plant illustrations.
- **Package 3:** object illustrations, additional garden objects, refreshed textures, and menu organisation.

All three packages shipped across **v1.25.0–v1.27.0**.

## Phase 16: future

Planned areas include plugins, shared templates, irrigation planning, advanced cost estimates,
and cross-platform packaging. These capabilities are not shipped.
The community documentation in this wiki does not mark Phase 16 complete.

<!-- ogp:include roadmap-phase-17 -->

## Recent hardening

- **v1.29.2:** display-language and translation-registration corrections.
- **v1.29.4:** annotation persistence, shared clipboard serialization, background placeholders, and atomic plan loading.
- **v1.29.5:** task windows across year boundaries, propagation dates, explicit MCP Host/Origin checks, and array-tool tests.
- **v1.29.6:** locked dependencies, platform type budgets, coverage floors, and administrator-enforced branch checks.
- **v1.29.8:** persistent handled-error logging and corrected harvest offsets, including garlic calibration ([PR #426](https://github.com/cofade/open-garden-planner/pull/426), #405/#418).
- **v1.29.9:** canvas performance correction on the 500-object reference plan ([PR #430](https://github.com/cofade/open-garden-planner/pull/430), #409).
- **v1.30.2:** constraint-tool characterization and coverage ([PR #477](https://github.com/cofade/open-garden-planner/pull/477), #406).
- **v1.30.6:** source-derived translation completeness for every registered locale ([PR #497](https://github.com/cofade/open-garden-planner/pull/497), #496).

Issues #399, #401, #402, and #404 completed in v1.29.6.
Logging [#405](https://github.com/cofade/open-garden-planner/issues/405),
constraint-tool coverage [#406](https://github.com/cofade/open-garden-planner/issues/406),
canvas performance [#409](https://github.com/cofade/open-garden-planner/issues/409),
and harvest-data correction [#418](https://github.com/cofade/open-garden-planner/issues/418)
are complete. Use [the canonical roadmap](https://github.com/cofade/open-garden-planner/blob/master/docs/roadmap.md)
and [audit epic #392](https://github.com/cofade/open-garden-planner/issues/392) for the remaining work.
