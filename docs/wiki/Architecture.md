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
| Solar and 3D | Qt-free solar, shadow, growth, and 3D scene calculations (`core/scene3d/`); the 3D view is the Plan / 3D / Split workspace of the main window on Qt Quick 3D (Phase 17 L1–L4, ADR-048 / ADR-059 / ADR-060 / ADR-063 / ADR-064 / ADR-065), with the engine confined to one package. |

Since v1.30.14 (Phase 17 L1) the 3D view is the Qt Quick 3D workspace beside the plan; it follows every edit and casts shadow-map shadows checked against the 2D shadows. The Qt 3D viewer window it replaces is removed. Flat terrain (no elevation or slope) remains a current limitation. Since v1.31.0 (Phase 17 L2, ADR-063) its Analyze menu shows the 2D side's own shadow polygons and hours-of-sun map on the 3D ground; it never computes a second analysis. Since v1.32.0 (Phase 17 L3, ADR-064) plant species get procedural 3D models instead of generic silhouettes. Since v1.34.0 (Phase 17 L4, ADR-065) buildings, paths and all 24 placeable object kinds are procedurally built rather than flat sprites, with real roofs, path surfaces and grass-blade lawns; the ground itself stays level.
The 2D analytic shadow and sun-hours calculations are separate from the 3D renderer's lighting. Unknown plant heights can use labelled illustrative category heights in 3D; analytical heights remain unknown. Panel edit and history boundaries are documented in the runtime view and crosscutting section 8.32.

## Detailed documentation

Constraint row presentation has an enum-complete immutable descriptor, separate
from geometric solving. Solver checks assert actual residuals, pinned anchors and
feasibility, with a reproducible sampled mutation experiment. A5 (#457) shipped in
[v1.30.4](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.4) after
owner acceptance; see [its evidence and scope](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/audits/2026-10/audit-2026-10-a5-evidence.md)
and [ADR-012](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md#adr-012-hybrid-constraint-solver-gauss-seidel-warm-start--newton-raphson-refinement).

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

Package F1/F2 keeps species niches/functions separate from artwork and drawing-layer names. Guilds use explicit saved metadata and immutable template snapshots, independent of bed parentage. The Diagnostics sidebar and Agent API share the warning converter. See [the contracts and authoring guide](https://github.com/cofade/open-garden-planner/blob/master/docs/08-crosscutting-concepts/README.md#826-recorded-permaculture-traits-and-guild-templates) and [ADRs](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md).

F3 sun diagnostics use explicit cached ground-level exposure excluding each receiving plant's own shadow. Shared date and document/geometry ownership prevent stale measurements; unavailable evaluations are visible information records. Mature-canopy groups are geometric only. Shipped in [v1.30.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.1) via [PR #436](https://github.com/cofade/open-garden-planner/pull/436) after owner acceptance. See [ADR-056](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md#adr-056-runtime-sun-diagnostics-and-document-owned-exposure-314-428) and [sun diagnostics contracts](https://github.com/cofade/open-garden-planner/blob/master/docs/08-crosscutting-concepts/README.md#827-cached-sun-exposure-and-shared-diagnostics).

Audit A1 adds shared strict plan persistence, verified installer downloads, bounded
image ingestion and owner-only Linux settings. Contracts and evidence live in the
[architecture decisions](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md)
and [runtime documentation](https://github.com/cofade/open-garden-planner/blob/master/docs/06-runtime-view/README.md).

F4 shipped in [v1.30.17](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.17) via [PR #533](https://github.com/cofade/open-garden-planner/pull/533). The permanent Plan & Sun strip shares one
simulation date for plant presence, growth and sunlight. While enabled, the 2D
Hours of Sun map refreshes after exposure inputs change; time-only animation does
not recalculate a full day. Visual exports wait for a current map. See
[the timeline and export contracts](https://github.com/cofade/open-garden-planner/blob/master/docs/08-crosscutting-concepts/README.md#831-plan-date-visibility-and-lifetime-us-f4-adr-062)
and ADR-062 in the architecture decision register.

The [v1.30.20](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.20)
follow-up adds an actionable location prerequisite beside Hours of Sun when
coordinates are missing, opening the existing location dialog. It also unifies
position-lock badges across object menus. Shipped after owner executable
acceptance in [PR #566](https://github.com/cofade/open-garden-planner/pull/566);
see [the implementation contract](https://github.com/cofade/open-garden-planner/blob/master/docs/08-crosscutting-concepts/README.md#832-panel-edit-boundaries-and-position-locks-552-558560).

Plant Forge (L3) shipped in [v1.32.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.32.0)
via [PR #593](https://github.com/cofade/open-garden-planner/pull/593) after owner
acceptance. It adds shared sprite traits, procedural species
meshes, camera LOD and background upgrades. Its seasonal material state uses
the same recorded frost-relative harvest calendar as tasks; flower and fruit
parts are independent. See the [Plant Forge decision](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md#adr-064-plant-forge--procedural-3d-species-models-from-the-2d-sprite-recipes-lods-and-phenology-387).


## CI coverage scheduling

The #601 implementation preserves the protected Coverage check and all branch
data. Two non-perf test-ID partitions and one serial performance measurement feed
a required combine/floor check; the uninstrumented Test job remains separate.
See the [investigation and evidence](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/audits/2026-10/ci-latency-601.md)
and [deployment contract](https://github.com/cofade/open-garden-planner/blob/master/docs/07-deployment-view/README.md#74-cicd-pipeline-github-actions).


## Audit responsibility boundaries

The remaining audit delivery introduces shared configuration/model leaves,
composed canvas/property/agent adapters and measured performance workloads.
See [ADR-068](https://github.com/cofade/open-garden-planner/blob/master/docs/09-architecture-decisions/README.md#adr-068-audit-boundaries-responsibility-extraction-and-progressive-agent-context-392)
and [per-finding evidence](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/audits/2026-10/audit-392-remaining.md).
Owner acceptance and protected merge remain pending while the PR is a draft.
