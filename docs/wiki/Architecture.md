# Architecture Overview

Open Garden Planner uses Python, PyQt6, and QGraphicsView/Scene for the 2D canvas.
Its detailed architecture follows [arc42](https://arc42.org/).

## Main subsystems

| Subsystem | Responsibility |
|---|---|
| Application | Main window, document lifecycle, settings, and UI state. |
| Canvas and tools | Drawing, selection, snapping, constraints, annotations, layers, and item rendering. |
| Commands and project data | Undo/redo, snapshots, shared serialization, clipboard data, and atomic plan loading. |
| Garden models and services | Plant data, companion planting, crop rotation, succession, soil, weather, tasks, harvest, and journal records. |
| Export services | Shared PNG, SVG, PDF, DXF, CSV, and shopping-list output used by GUI and Agent API surfaces. |
| Agent API | Embedded loopback MCP server with main-thread dispatch. Reads and exports remain open locally. Editing requires explicit enablement and a token. |
| Solar and 3D | Qt-free solar, shadow, growth, and 3D scene calculations (`core/scene3d/`); the 3D view is the Plan / 3D / Split workspace of the main window on Qt Quick 3D (Phase 17, ADR-048 / ADR-059 / ADR-060 / ADR-063 / ADR-064 / ADR-065 / ADR-070 / ADR-072), with the engine confined to one package. |

The 3D view follows every edit and casts shadow-map shadows checked against the 2D
shadows. Its Analyze menu shows the 2D side's own shadow polygons and hours-of-sun map
on the 3D ground; it never computes a second analysis. Buildings, paths and all 24
placeable object kinds are procedurally built, with real roofs, path surfaces and
grass-blade lawns. Day and year playback write through the shared simulation clock;
weather is only a look that never moves the sun. Flat terrain (no elevation or slope)
remains a current limitation. The 2D analytic shadow and sun-hours calculations are
separate from the 3D renderer's lighting. Unknown plant heights can use labelled
illustrative category heights in 3D; analytical heights remain unknown.

## Detailed documentation

| Document | Purpose |
|---|---|
| [Introduction](https://github.com/cofade/open-garden-planner/tree/master/docs/01-introduction-and-goals) | Goals and audience. |
| [Constraints](https://github.com/cofade/open-garden-planner/tree/master/docs/02-constraints) | Platform and licensing constraints. |
| [Context](https://github.com/cofade/open-garden-planner/tree/master/docs/03-context-and-scope) | External systems and providers. |
| [Strategy](https://github.com/cofade/open-garden-planner/tree/master/docs/04-solution-strategy) | Design approach. |
| [Building blocks](https://github.com/cofade/open-garden-planner/tree/master/docs/05-building-block-view) | Modules and responsibilities. |
| [Runtime](https://github.com/cofade/open-garden-planner/tree/master/docs/06-runtime-view) | Runtime flows. |
| [Deployment](https://github.com/cofade/open-garden-planner/tree/master/docs/07-deployment-view) | Builds, CI, releases, and wiki publication. |
| [Crosscutting concepts](https://github.com/cofade/open-garden-planner/tree/master/docs/08-crosscutting-concepts) | Shared invariants and testing policy. |
| [Architecture decisions](https://github.com/cofade/open-garden-planner/tree/master/docs/09-architecture-decisions) | ADRs, including renderer and documentation decisions. |
| [Quality](https://github.com/cofade/open-garden-planner/tree/master/docs/10-quality-requirements) | Quality goals and measured gates. |
| [Risks and debt](https://github.com/cofade/open-garden-planner/tree/master/docs/11-risks-and-technical-debt) | Living debt register and lessons. |
| [Glossary](https://github.com/cofade/open-garden-planner/tree/master/docs/12-glossary) | Terms and keyboard shortcuts. |

## Recorded traits and guild templates

Species niches and functions are separate from artwork and drawing-layer names. Guilds
use explicit saved metadata and immutable template snapshots, independent of bed
parentage. The Diagnostics sidebar and Agent API share the warning converter. See
[the contracts and authoring guide](https://github.com/cofade/open-garden-planner/blob/master/docs/08-crosscutting-concepts/README.md#826-recorded-permaculture-traits-and-guild-templates)
and the [ADRs](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md).

## Sun diagnostics and plan time

Sun diagnostics use explicit cached soil-plane receiver exposure excluding each
receiving plant's own shadow and applicable soil holders, alongside the unchanged
ground heatmap. Receiver elevation follows the canonical plant base; obstacles are
sliced above that exact plane. Shared date and document/geometry ownership prevent
stale measurements; unavailable evaluations are visible information records.
Mature-canopy groups are geometric only. See
[ADR-056](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md#adr-056-runtime-sun-diagnostics-and-document-owned-exposure-314-428)
and [sun diagnostics contracts](https://github.com/cofade/open-garden-planner/blob/master/docs/08-crosscutting-concepts/README.md#827-cached-sun-exposure-and-shared-diagnostics).

The permanent Plan & Sun strip shares one simulation date for plant presence, growth and
sunlight. While enabled, the 2D Hours of Sun map refreshes after exposure inputs change;
time-only animation does not recalculate a full day. Visual exports wait for a current
map. See [the timeline and export contracts](https://github.com/cofade/open-garden-planner/blob/master/docs/08-crosscutting-concepts/README.md#831-plan-date-visibility-and-lifetime-us-f4-adr-062)
and ADR-062 in the architecture decision register.

A plan may also carry its own north orientation: **File > Set North Orientation…** stores
where true north lies on the drawing (clockwise from plan-up) without rotating any object.
The 2D shadows, the hours-of-sun sampling, the plant sun-exposure diagnostics, the 3D light
and sun path, and the PDF's north arrow all turn a compass bearing by that angle once. See
FR-SUN-14 and the ADR-037 addendum.

## Plant Forge

Plant Forge adds shared sprite traits, procedural species meshes, camera LOD and
background upgrades. Its seasonal material state uses the same recorded frost-relative
harvest calendar as tasks; flower and fruit parts are independent. See the
[Plant Forge decision](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md#adr-064-plant-forge--procedural-3d-species-models-from-the-2d-sprite-recipes-lods-and-phenology-387).

## CI coverage scheduling

The Coverage check preserves all branch data. Two non-perf test-ID partitions and one
serial performance measurement feed a required combine/floor check; the uninstrumented
Test job remains separate. See the
[investigation and evidence](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/audits/2026-10/ci-latency-601.md)
and [deployment contract](https://github.com/cofade/open-garden-planner/blob/master/docs/07-deployment-view/README.md#74-cicd-pipeline-github-actions).

## Audit responsibility boundaries

Shared configuration/model leaves, composed canvas/property/agent adapters and measured
performance workloads define the audit delivery boundaries. See
[ADR-068](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md#adr-068-audit-boundaries-responsibility-extraction-and-progressive-agent-context-392)
and [per-finding evidence](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/audits/2026-10/audit-392-remaining.md).
