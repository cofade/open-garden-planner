---
name: ogp-architecture-contract
description: >
  The load-bearing architecture contract for Open Garden Planner: the invariant
  table, the module dependency map, the command-pattern write path, and the
  known weak points. Load this BEFORE designing any feature, adding a module or
  package, or touching serialization (.ogp / FILE_VERSION), undo/redo, layers,
  beds/containers/plant-parents, task status, plant sizing, rotation/resize
  geometry, or the agent_api (MCP) surface — and whenever you are asking "is
  this allowed architecturally?", "does an ADR already cover this?", or "which
  predicate / write path / chokepoint do I use?". Also load it before reviewing
  someone else's design.
---

# ogp-architecture-contract reference guide

Read the scope/introduction and the relevant reference below **before acting**.
All rules in the references remain binding. Read method/runbook sections for
the task; load historical case studies only when the symptom matches. Search
the index by subsystem, issue or symptom. Do not infer current delivery status
from dated measurements. New lessons belong in a new reference and index row.

| Topic / symptom | Reference |
|---|---|
| OGP Architecture Contract | [Read](references/000-ogp-architecture-contract.md) |
| Current translation gate (#496) | [Read](references/001-current-translation-gate-496.md) |
| When NOT to use this skill | [Read](references/002-when-not-to-use-this-skill.md) |
| 1. Invariants (the heart of this skill) | [Read](references/003-1-invariants-the-heart-of-this-skill.md) |
| 2. Module map and dependency rules | [Read](references/004-2-module-map-and-dependency-rules.md) |
| 3. The write path: command pattern (§8.2, ADR-004) | [Read](references/005-3-the-write-path-command-pattern-8-2-adr-004.md) |
| 4. Known weak points — stated plainly | [Read](references/006-4-known-weak-points-stated-plainly.md) |
| 5. Before you design anything — checklist | [Read](references/007-5-before-you-design-anything-checklist.md) |
| Provenance and maintenance | [Read](references/008-provenance-and-maintenance.md) |
| Package F1/F2 seams (ADR-054/055) | [Read](references/009-package-f1-f2-seams-adr-054-055.md) |
