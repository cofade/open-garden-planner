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
| Solar and shipped 3D | Qt-free solar, shadow, growth, and mesh calculations with a Qt 3D presentation adapter. |
| Dormant Qt Quick 3D spike | Phase 17 L0 evidence implementation behind `--spike-q3d`. L1 will deliver the production replacement. |

The shipped 3D view remains Qt 3D. Flat ground and the absence of engine shadow maps remain current limitations.
The 2D analytic shadow and sun-hours calculations are separate from the 3D renderer's lighting.

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
