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
| Solar and 3D | Qt-free solar, shadow, growth, and 3D scene calculations (`core/scene3d/`); the 3D view is the Plan / 3D / Split workspace of the main window on Qt Quick 3D (Phase 17 L1, ADR-048 / ADR-059 / ADR-060), with the engine confined to one package. |

On the Phase 17 L1 branch the 3D view is the Qt Quick 3D workspace beside the plan; it follows every edit and casts shadow-map shadows checked against the 2D shadows. The Qt 3D viewer window it replaces is removed there. Flat ground remains a current limitation.
The 2D analytic shadow and sun-hours calculations are separate from the 3D renderer's lighting.

## Detailed documentation

Constraint row presentation has an enum-complete immutable descriptor, separate
from geometric solving. Solver checks assert actual residuals, pinned anchors and
feasibility, with a reproducible sampled mutation experiment. A5 (#457) shipped in
[v1.30.4](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.4) after
owner acceptance; see [its evidence and scope](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/audit-2026-10-a5-evidence.md)
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
