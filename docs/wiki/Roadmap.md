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

## Package F: planned

| Story | Work | Issue |
|---|---|---|
| F1 | Permaculture layers and plant-function tags. Foundation, first. | [#312](https://github.com/cofade/open-garden-planner/issues/312) |
| F2 | Plant guilds. Depends on F1. | [#313](https://github.com/cofade/open-garden-planner/issues/313) |
| F3 | Sun requirements compared with computed hours of sun. | [#314](https://github.com/cofade/open-garden-planner/issues/314) |
| F4 | Plan timeline. | [#315](https://github.com/cofade/open-garden-planner/issues/315) |
| F5 | Example plans and templates. Last in the package. | [#316](https://github.com/cofade/open-garden-planner/issues/316) |

## Package G: complete

| Story | Status | Issue |
|---|---|---|
| G1: data licence and attribution | ✅ v1.28.1 | [#311](https://github.com/cofade/open-garden-planner/issues/311) |
| G2: plant profile header | ✅ v1.28.1 | [#317](https://github.com/cofade/open-garden-planner/issues/317) |
| G3: provider companion data and cache | ✅ v1.28.1 | [#318](https://github.com/cofade/open-garden-planner/issues/318) |
| G4: plant favourites and named collections | ✅ [PR #421](https://github.com/cofade/open-garden-planner/pull/421) | [#320](https://github.com/cofade/open-garden-planner/issues/320) |

## Phase 14: 3D and sun/shade complete

All nine stories shipped across **v1.24.5–v1.24.12**.
The product includes solar calculations, analytic 2D shadows, hours-of-sun heatmaps,
a Qt 3D view, walkthrough, and plant growth over time.
Ground remains flat. The shipped 3D renderer has lighting but no engine shadow maps.
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

Issues #399, #401, #402, and #404 completed in v1.29.6.
Remaining audit work includes logging [#405](https://github.com/cofade/open-garden-planner/issues/405),
constraint-tool coverage [#406](https://github.com/cofade/open-garden-planner/issues/406),
and canvas performance [#409](https://github.com/cofade/open-garden-planner/issues/409).
Harvest-data correction remains tracked in [#418](https://github.com/cofade/open-garden-planner/issues/418).
Garlic's calculated harvest window remains about three months late under both existing interpretations.
