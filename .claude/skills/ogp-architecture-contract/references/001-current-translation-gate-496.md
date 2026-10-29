## Current translation gate (#496)

`scripts/check_translations.py` is the required source/catalog/binary gate for every
locale in `SUPPORTED_LANGUAGES`. New wrapped UI keys require all target translations;
new locales require all current keys. Run `update_translations.py`, complete targets
(the fill helper is German-only), compile, then check. No coverage allowances or manual
locale test lists. The compiler rejects incomplete/blank targets and unsupported plural
input; vanished records cannot satisfy coverage. See section 8.3 and docs/TRANSLATING.md.
The older German-only check mentioned in historical examples below is supplementary.
Truly unwrapped UI prose and linguistic quality still require review.


This skill is the binding design contract for `open-garden-planner`
(PyQt6 desktop garden-CAD app). It states **what must stay true**, **why**,
**what breaks if you violate it**, and **what enforces it**. Everything below
was verified against the repo on **2026-07-03** (app v1.23.0, `FILE_VERSION`
`"1.4"`, master after Package D US-D1.3). Re-verify volatile facts with the
commands in "Provenance and maintenance" at the end.

Jargon used once and defined here:

- **`.ogp`** — the JSON project file (ADR-003). **`FILE_VERSION`** — its schema
  version string in `src/open_garden_planner/core/project.py` (currently `"1.4"`).
- **ADR** — Architecture Decision Record; all live in one file:
  `docs/09-architecture-decisions/README.md` (**ADR-001 onward — read the file's
current index; there is deliberately no count written here**, because a hardcoded
range is exactly what rots: this line once said "ADR-001…ADR-034" while the file
already carried ADR-036 and ADR-043. `tests/unit/test_skill_facts_drift.py` fails
if a closed range is ever pinned here again).
- **Seam** — a single chokepoint function/module through which a whole class of
  behavior is routed (this codebase's favorite pattern).
- **Qt-free** — a module with no PyQt6 import, unit-testable without a QApplication.
- **Agent API** — the embedded, loopback-only MCP-over-HTTP server in
  `src/open_garden_planner/agent_api/` (ADR-033/034).

